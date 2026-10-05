"""Standalone API surface for AgentShield V3 (port 8090).

Routes::

    POST /api/evaluate                  tool-call risk assessment
    GET  /api/status/{session_id}       governance status
    GET  /api/behavior_graph/{id}       behavior graph
    POST /api/agent/behavior_chain      multi-agent chain tracking
    GET  /api/agent/registry            agent registry
    POST /api/agent/evaluate_intent     intent-consistency evaluation
    GET  /api/sessions                  recent sessions
    GET  /api/session/{id}              session detail
    DELETE /api/session/{id}            delete session
    GET  /api/health_detailed           health + registry stats
    GET  /health                        liveness (never rate limited)

The router is mounted by :func:`app.factory.build_app`, so this surface and
the ``/api/v3/*`` router share one application, one CORS policy and one rate
limiter.

Note: this module deliberately avoids ``from __future__ import annotations``.
With postponed evaluation FastAPI sees annotations as plain strings and cannot
tell that ``body: EvaluateRequest`` is a Pydantic model, so it treats the
parameter as a query field and every call fails with HTTP 422.
"""

import logging
import os
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter

from app.engine_registry import get_or_create_engine
from app.shield.persistence import save_engine_state

logger = logging.getLogger(__name__)


def get_engine(session_id: str):
    """Return the shared engine for ``session_id`` (creating it if needed)."""
    return get_or_create_engine(session_id)


def _save_engine_to_db(session_id: str, engine: Any) -> None:
    """Persist engine state without blocking the request."""
    save_engine_state(session_id, engine)


def _rate_limit_key(request: Request) -> str:
    """Rate-limit key: prefer the client IP forwarded by a reverse proxy.

    ``get_remote_address`` sees the proxy's address behind a reverse proxy, so
    every request would share one quota and the limit becomes meaningless.
    Read the left-most ``X-Forwarded-For`` entry (the original client) and
    fall back to the socket peer.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    return request.client.host if request.client else "unknown"


limiter = Limiter(key_func=_rate_limit_key)

# Mount point for the standalone routes.  Registered by app.factory.build_app.
standalone_router = APIRouter()


# ── Pydantic models ─────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    agent_id: str
    tool_name: str
    params: Dict[str, Any]
    risk_score: float = 0.0
    session_id: str = ""
    labels: Optional[list[str]] = None


class EvaluateResponse(BaseModel):
    session_id: str
    decision: str          # "allow" | "block" | "review"
    risk_level: str        # "low" | "medium" | "high" | "critical"
    risk_score: float
    reasoning: str
    shield_version: str = "3.0.0"


@standalone_router.post("/api/evaluate")
@limiter.limit("50/minute")
async def evaluate(request: Request, body: EvaluateRequest):
    """
    工具调用风险评估 API
    - rate limit: 50次/分钟（全局）
    - 返回决策: allow / block / review
    """
    session_id = body.session_id or str(uuid.uuid4())
    engine = get_engine(session_id)

    try:
        result = engine.process_tool_call(
            agent_id=body.agent_id,
            tool_name=body.tool_name,
            params=body.params,
            risk_score=body.risk_score,
            fuse_action="allow",
            labels=body.labels or [],
        )
    except Exception:
        # 引擎异常时降级拦截（fail-closed）。
        # 只把异常类型返回给客户端：str(e) 可能包含内部路径、SQL 或堆栈
        # 细节，属于信息泄露。完整堆栈进服务端日志。
        logger.exception("Engine failure for session %s; failing closed", session_id)
        result = {
            "node_id": str(uuid.uuid4()),
            "decision": "block",
            "risk_level": "high",
            "risk_score": 0.9,
            "reasoning": "Engine exception fallback (fail-closed)",
        }

    # 持久化 session
    _save_engine_to_db(session_id, engine)
    return EvaluateResponse(
        session_id=session_id,
        decision=result.get("decision", "block"),
        risk_level=result.get("risk_level", "high"),
        risk_score=result.get("risk_score", 0.9),
        reasoning=result.get("reasoning", ""),
    )


@standalone_router.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """获取治理状态"""
    engine = get_engine(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return engine.get_governance_status()


@standalone_router.get("/api/behavior_graph/{session_id}")
async def get_behavior_graph(session_id: str):
    """获取行为图谱"""
    engine = get_engine(session_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if hasattr(engine.behavior_graph, "to_graph_dict"):
        return engine.behavior_graph.to_graph_dict()
    return {}


@standalone_router.post("/api/agent/behavior_chain")
async def agent_behavior_chain(data: dict):
    """多 Agent 行为链追踪。

    每个 step 都走真实的 V3 引擎（行为图谱 + 治理门），风险分来自
    调用方显示提供的 ``risk_score``；未提供时由
    :func:`_infer_step_risk` 从可观察信号（动词/目标/输入）推导。

    旧实现用 ``len(str(input))/200 * random.random()`` 作为风险分
    —— 即使输入完全相同，返回的风险也每次都不同，不具备任何评估语义。
    """
    agents = data.get("agents", [])
    session_id = data.get("session_id") or f"chain_{uuid.uuid4().hex[:12]}"
    engine = get_engine(session_id)

    steps = []
    violations = []
    overall_risk = 0.0
    parent_node_id = None

    for i, agent in enumerate(agents):
        aid = agent.get("id", f"agent_{i}")
        action = agent.get("action", "")
        target = agent.get("target", "")
        inp = agent.get("input", {})

        risk = _resolve_step_risk(agent, inp)
        tool_name = action or "agent_action"
        try:
            result = engine.process_tool_call(
                agent_id=aid,
                tool_name=tool_name,
                params=inp if isinstance(inp, dict) else {"input": inp},
                risk_score=risk,
                fuse_action="allow",
                parent_node_id=parent_node_id,
                labels=[f"step_{i + 1}"] + ([f"target:{target}"] if target else []),
            )
        except Exception:
            logger.exception("behavior_chain step %d failed; failing closed", i + 1)
            result = {
                "decision": "block",
                "risk_score": 0.9,
                "risk_level": "high",
                "reasoning": "Engine exception fallback (fail-closed)",
            }

        step_risk = float(result.get("risk_score", risk))
        decision = result.get("decision", "block")
        step = {
            "step_id": i + 1,
            "agent_id": aid,
            "action": action,
            "target": target,
            "input_summary": str(inp)[:50],
            "risk_score": round(step_risk, 3),
            "risk_level": result.get("risk_level", "high"),
            "decision": decision,
            "node_id": result.get("node_id"),
            "inherited_risk": round(
                float(
                    engine.behavior_graph.get_node(result["node_id"]).inherited_risk
                )
                if result.get("node_id")
                and engine.behavior_graph.get_node(result["node_id"])
                else 0.0,
                3,
            ),
        }
        if decision != "allow":
            violations.append(
                {
                    "step": i + 1,
                    "agent_id": aid,
                    "reason": result.get("reasoning", f"{action} -> {target}"),
                    "risk_score": round(step_risk, 3),
                }
            )
        steps.append(step)
        overall_risk = max(overall_risk, step_risk)
        parent_node_id = result.get("node_id") or parent_node_id

    verdict = (
        "block" if overall_risk > 0.85 else "review" if overall_risk > 0.5 else "allow"
    )
    _save_engine_to_db(session_id, engine)
    return {
        "chain_id": str(uuid.uuid4()),
        "session_id": session_id,
        "steps": steps,
        "risk_score": round(overall_risk, 3),
        "verdict": verdict,
        "violations": violations,
        "behavior_graph": engine.behavior_graph.summary(),
    }


#: 动词 -> 基线风险（用于调用方未提供 risk_score 时的推导）。
_ACTION_RISK_HINTS = {
    "delete": 0.75,
    "drop": 0.80,
    "rm": 0.75,
    "format": 0.85,
    "export": 0.55,
    "download": 0.45,
    "send": 0.50,
    "email": 0.50,
    "upload": 0.55,
    "post": 0.40,
    "write": 0.35,
    "update": 0.30,
    "modify": 0.40,
    "execute": 0.45,
    "query": 0.15,
    "read": 0.10,
    "list": 0.05,
    "get": 0.05,
    "search": 0.10,
    "analyze": 0.20,
}

#: 目标关键词 -> 风险增量。
_TARGET_RISK_HINTS = {
    "external": 0.25,
    "public": 0.25,
    "internet": 0.25,
    "webhook": 0.20,
    "smtp": 0.15,
    "email": 0.15,
    "production": 0.30,
    "prod": 0.25,
    "database": 0.20,
    "admin": 0.25,
    "root": 0.30,
    "credential": 0.30,
    "secret": 0.30,
    "backup": 0.15,
}


def _resolve_step_risk(agent: dict, inp) -> float:
    """确定一个行为链 step 的风险分。

    优先使用调用方显示给出的 ``risk_score``；否则从动词、目标和输入视观信号推导。
    """
    explicit = agent.get("risk_score")
    if isinstance(explicit, (int, float)):
        return max(0.0, min(1.0, float(explicit)))

    action = str(agent.get("action", "")).lower()
    target = str(agent.get("target", "")).lower()
    text = str(inp).lower()

    risk = 0.10  # 空动作的基线
    for keyword, weight in _ACTION_RISK_HINTS.items():
        if keyword in action:
            risk = max(risk, weight)
            break
    for keyword, bump in _TARGET_RISK_HINTS.items():
        if keyword in target or keyword in text:
            risk += bump
    # 未知动词给一个中等基线，避免默认删除类高危动作。
    if action and risk <= 0.10:
        risk = 0.30
    return round(max(0.0, min(1.0, risk)), 3)


@standalone_router.get("/api/agent/registry")
async def agent_registry():
    """Agent注册表"""
    agents = [
        {"type": "TCM-Cognition", "description": "中医辨证推理Agent", "capabilities": ["症状分析", "证型判断", "方剂推荐"]},
        {"type": "Visual-Perception", "description": "3D视觉感知Agent", "capabilities": ["点云处理", "碰撞检测", "路径规划"]},
        {"type": "Risk-Analysis", "description": "风险分析Agent", "capabilities": ["漏洞扫描", "威胁评估", "缓解建议"]},
        {"type": "Content-Audit", "description": "内容审计Agent", "capabilities": ["幻觉检测", "RAG溯源", "合规检查"]},
        {"type": "Narrative-Generation", "description": "叙事生成Agent", "capabilities": ["市场叙事", "KOL传播", "情绪放大"]},
        {"type": "Market-Regulation", "description": "市场监管Agent", "capabilities": ["干预策略", "风险预警", "效果评估"]},
        {"type": "Hypothesis-Engine", "description": "假设引擎Agent", "capabilities": ["假设生成", "KG约束", "贝叶斯验证"]},
        {"type": "Lab-Automation", "description": "实验自动化Agent", "capabilities": ["DoE设计", "FMEA分析", "结果统计"]},
    ]
    return {"agents": agents, "total": len(agents)}


@standalone_router.post("/api/agent/evaluate_intent")
async def evaluate_intent(data: dict):
    """意图一致性评估（Theory of Mind）"""
    agent_id = data.get("agent_id", "unknown")
    stated_goal = data.get("stated_goal", "")
    observed_actions = data.get("observed_actions", [])
    if not observed_actions:
        return {"intent_alignment": 0.5, "deception_score": 0.1, "reasoning": "无观察数据，无法评估", "agent_id": agent_id}
    goal_keywords = ["查询", "分析", "评估", "生成", "优化"]
    action_keywords = ["删除", "导出", "发送", "修改", "取消"]
    goal_match = sum(1 for kw in goal_keywords if kw in stated_goal) / max(len(goal_keywords), 1)
    action_risk = sum(1 for kw in action_keywords if any(kw in str(a) for a in observed_actions)) / max(len(observed_actions), 1)
    alignment = round(max(0.1, min(0.95, goal_match * 0.6 + (1 - action_risk) * 0.4)), 3)
    deception = round(max(0, min(0.9, action_risk * 0.7 - goal_match * 0.3)), 3)
    reasoning = f"目标表述包含{sum(1 for kw in goal_keywords if kw in stated_goal)}个操作类关键词，观察到{len(observed_actions)}个行动，其中{sum(1 for kw in action_keywords if any(kw in str(a) for a in observed_actions))}个存在风险"
    return {"agent_id": agent_id, "stated_goal": stated_goal, "intent_alignment": alignment, "deception_score": deception, "reasoning": reasoning}

# ── Session 管理 ────────────────────────────────────────────────────────────

@standalone_router.get("/api/sessions")
async def list_sessions(limit: int = 20):
    """列出最近的 sessions（从 SQLite）"""
    try:
        from app.shield.session_store import list_sessions as db_list
        return {"sessions": db_list(limit=limit), "count": limit}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@standalone_router.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """获取指定 session 详情（从 SQLite）"""
    try:
        from app.shield.session_store import load_session
        saved = load_session(session_id)
        if not saved:
            raise HTTPException(status_code=404, detail="Session not found in DB")
        return saved
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("Failed to load session %s", session_id)
        raise HTTPException(
            status_code=500, detail="Internal error loading session"
        ) from err


@standalone_router.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """删除指定 session（从内存和 SQLite）"""
    from app.engine_registry import drop_engine

    drop_engine(session_id)
    try:
        from app.shield.session_store import delete_session as db_delete

        db_delete(session_id)
        return {"deleted": session_id}
    except Exception as e:
        return {"deleted": session_id, "warning": str(e)}


@standalone_router.get("/api/health_detailed")
async def health_detailed():
    """详细健康状态（含 session 数量与淘汰策略）"""
    from app.engine_registry import active_session_count, registry_stats

    return {
        "status": "ok",
        "version": "3.0.0",
        "framework": "ASF-BGT",
        "port": 8090,
        "active_sessions": active_session_count(),
        "registry": registry_stats(),
        "db_file": os.environ.get("SHIELD_DB", "shield_sessions.db"),
    }


# ── 启动入口（uvicorn直接运行此文件） ───────────────────────────────────────


