# -*- coding: utf-8 -*-
"""
AgentShield V3 - FastAPI 主入口 (端口8011)
POST /api/evaluate  - 工具调用风险评估（限流50次/分钟）
GET  /health        - 健康检查
"""
import logging
import os
import uuid
from typing import Any, Dict, Optional

from app.shield.persistence import save_engine_state
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)


def _rate_limit_key(request: Request) -> str:
    """限流 key：优先取反代透传的客户端 IP。

    ``get_remote_address`` 在反向代理后面会拿到代理的 IP，导致所有请求共享一个配额、
    限流形同虚设。这里优先读 ``X-Forwarded-For`` 的第一个条目（最左端即原始客户端）。
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
        if client_ip:
            return client_ip
    return request.client.host if request.client else "unknown"


# ── CORS ───────────────────────────────────────────────────────────────────
# ``allow_origins=["*"]`` 与 ``allow_credentials=True`` 的组合会被浏览器拒绝，credentials 实际从未生效。
_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

# ── Rate Limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=_rate_limit_key)

# ── Pydantic Models ────────────────────────────────────────────────────────────

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


# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AgentShield V3",
    description="多主体行为链风险治理系统 - ASF-BGT Framework",
    version="3.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=bool(_ALLOWED_ORIGINS),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 引擎存储 ────────────────────────────────────────────────────────────────

_engine_store: Dict[str, Any] = {}


def _save_engine_to_db(session_id: str, engine: Any):
    """将引擎状态落盘（非阻塞，具体实现在 app.shield.persistence）。

    每次请求都同步写入全量 audit chain + graph 会阻塞
    asyncio event loop，且随会话增长逐次变慢。现改为按
    session 去重 + 线程池执行，写入失败不影响请求。
    """
    save_engine_state(session_id, engine)


def get_engine(session_id: str) -> Any:
    """获取或创建 V3 引擎（与 /api/v3/* 共享同一份状态）。

    引擎注册表集中在 app.engine_registry，带 TTL 与 LRU 容量上限；
    之前 8090 入口与 /api/v3/* 各自保留一份 ``_engine_store``，同一个
    session 会解析成两个不同引擎。
    """
    from app.api.routes import get_or_create_engine as _routes_get

    return _routes_get(session_id)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "version": "3.0.0",
        "engine": "AgentShield_V3",
        "framework": "ASF-BGT",
        "port": 8011,
    }


@app.post("/api/evaluate")
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
        # 引擎异常时降级拦截（fail-closed）。完整堆栈进服务端日志，
        # 不把 str(e) 返回客户端（可能泄露内部路径或 SQL）。
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


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """获取治理状态"""
    if session_id not in _engine_store:
        raise HTTPException(status_code=404, detail="Session not found")
    return _engine_store[session_id].get_governance_status()


@app.get("/api/behavior_graph/{session_id}")
async def get_behavior_graph(session_id: str):
    """获取行为图谱"""
    if session_id not in _engine_store:
        raise HTTPException(status_code=404, detail="Session not found")
    engine = _engine_store[session_id]
    if hasattr(engine.behavior_graph, "to_graph_dict"):
        return engine.behavior_graph.to_graph_dict()
    return {}


@app.post("/api/agent/behavior_chain")
async def agent_behavior_chain(data: dict):
    """多 Agent 行为链追踪。

    每个 step 都走真实的 V3 引擎（行为图谱 + 治理门），风险分来自调用方显示提供的
    ``risk_score``；未提供时由 :func:`_resolve_step_risk` 从可观察信号推导。

    旧实现用 ``len(str(input))/200 * random.random()`` 作为风险分
    —— 即使输入完全相同，返回的风险也每次都不同。
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
        node_id = result.get("node_id")
        node = engine.behavior_graph.get_node(node_id) if node_id else None
        step = {
            "step_id": i + 1,
            "agent_id": aid,
            "action": action,
            "target": target,
            "input_summary": str(inp)[:50],
            "risk_score": round(step_risk, 3),
            "risk_level": result.get("risk_level", "high"),
            "decision": decision,
            "node_id": node_id,
            "inherited_risk": round(node.inherited_risk, 3) if node else 0.0,
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
        parent_node_id = node_id or parent_node_id

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


#: 动词 -> 基线风险（调用方未提供 risk_score 时的推导）。
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
    """确定一个行为链 step 的风险分：显式 risk_score 优先，否则从动词/目标/输入推导。"""
    explicit = agent.get("risk_score")
    if isinstance(explicit, (int, float)):
        return max(0.0, min(1.0, float(explicit)))

    action = str(agent.get("action", "")).lower()
    target = str(agent.get("target", "")).lower()
    text = str(inp).lower()

    risk = 0.10
    for keyword, weight in _ACTION_RISK_HINTS.items():
        if keyword in action:
            risk = max(risk, weight)
            break
    for keyword, bump in _TARGET_RISK_HINTS.items():
        if keyword in target or keyword in text:
            risk += bump
    if action and risk <= 0.10:
        risk = 0.30
    return round(max(0.0, min(1.0, risk)), 3)


@app.get("/api/agent/registry")
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


@app.post("/api/agent/evaluate_intent")
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

@app.get("/api/sessions")
async def list_sessions(limit: int = 20):
    """列出最近的 sessions（从 SQLite）"""
    try:
        from app.shield.session_store import list_sessions as db_list
        return {"sessions": db_list(limit=limit), "count": limit}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@app.get("/api/session/{session_id}")
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


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """删除指定 session（从内存和 SQLite）"""
    _engine_store.pop(session_id, None)
    try:
        from app.shield.session_store import delete_session as db_delete

        db_delete(session_id)
        return {"deleted": session_id}
    except Exception as e:
        return {"deleted": session_id, "warning": str(e)}


@app.get("/api/health_detailed")
async def health_detailed():
    """详细健康状态（含 session 数量与淘汰策略）"""
    from app.api.routes import _ttl_manager

    return {
        "status": "ok",
        "version": "3.0.0",
        "framework": "ASF-BGT",
        "port": 8011,
        "active_sessions": len(_ttl_manager.get_stats().get("sessions", []))
        if isinstance(_ttl_manager.get_stats().get("sessions"), list)
        else _ttl_manager.get_stats().get("active_sessions", 0),
        "ttl_stats": _ttl_manager.get_stats(),
        "db_file": os.environ.get("SHIELD_DB", "shield_sessions.db"),
    }


# ── 启动入口（uvicorn直接运行此文件） ───────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # 直接传 app 对象。uvicorn.run("app:app") 会按 sys.path 解析字符串 "app"，
    # 在 backend/ 目录下运行时会找到 app 包而不是本模块，报
    # "Attribute 'app' not found in module 'app'"。
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8011,
        reload=False,
        log_level="info",
    )
