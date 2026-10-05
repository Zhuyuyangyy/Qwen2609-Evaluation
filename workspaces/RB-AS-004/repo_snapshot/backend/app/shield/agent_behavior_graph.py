"""
AgentBehaviorGraph - V3 Layer 1
===============================
多 Agent 行为链追踪与状态图谱。

将单个会话中多个 Agent 的工具调用序列建模为有向图：
- 节点（BehaviorNode）：Agent 身份 + 工具调用请求 + 熔断决策 + 风险状态
- 边（BehaviorEdge）：Agent 间调用关系（invoke/subagent/delegate）或数据流向
- 关键能力：识别风险沿调用链如何扩散

每个 ToolCallRequest 进入这个图，产生/更新一个节点。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

# 上游传导风险超过该阈值时，节点被标记为「放大了下游风险」。
_AMPLIFICATION_THRESHOLD = 0.1
# 判定「关键节点」的本地风险阈值（与 get_critical_nodes 的默认参数一致）。
_CRITICAL_RISK_THRESHOLD = 0.7


class NodeRiskStatus(Enum):
    SAFE = "safe"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class BehaviorNode:
    """
    行为图中的一个节点：对应一次工具调用
    """
    node_id: str = field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    agent_id: str = "unknown"
    session_id: str = "unknown"
    tool_name: str = ""
    params_summary: str = ""          # 参数摘要（脱敏后，用于图谱展示）
    fuse_action: str = "allow"        # allow / block / human_review
    shadow_risk_score: float = 0.0    # V2 的影子风险评分
    risk_status: NodeRiskStatus = NodeRiskStatus.SAFE
    timestamp: datetime = field(default_factory=datetime.now)
    # 该节点是否产生了风险扩散（沿某条边传到下游）
    downstream_risk_amplified: bool = False
    # 该节点触发的干预次数
    intervention_count: int = 0
    # 因果归因：该节点的风险有多少传导自上游
    inherited_risk: float = 0.0
    # 节点标签（用于可视化）
    labels: list[str] = field(default_factory=list)
    # 元数据
    metadata: dict = field(default_factory=dict)

    def is_risk_amplifier(self) -> bool:
        """该节点是否放大了上游风险"""
        return self.downstream_risk_amplified

    def to_summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "agent_id": self.agent_id,
            "tool_name": self.tool_name,
            "fuse_action": self.fuse_action,
            "risk_score": self.shadow_risk_score,
            "risk_status": self.risk_status.value,
            "inherited_risk": round(self.inherited_risk, 3),
            "intervention_count": self.intervention_count,
        }


@dataclass
class BehaviorEdge:
    """
    行为图中的边：表示 Agent 间的调用关系或数据流向
    """
    edge_id: str = field(default_factory=lambda: f"edge_{uuid.uuid4().hex[:8]}")
    from_node_id: str = ""
    to_node_id: str = ""
    edge_type: str = "calls"          # calls / invokes / data_flow / returns
    # Pure transfer coefficient in [0, 1]. Risk lives on nodes, not edges: an
    # edge says how much of the upstream node's *total* risk reaches the
    # downstream node. It used to be set to the upstream node's own risk, while
    # propagation also multiplied by it -- so three chained calls attenuated
    # 0.8 as 0.8 * 0.8 * 0.8. One concept, one place.
    transfer_weight: float = 1.0
    description: str = ""
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def risk_flow(self) -> float:
        """Deprecated alias for :attr:`transfer_weight`."""
        return self.transfer_weight

    def to_summary(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "from": self.from_node_id,
            "to": self.to_node_id,
            "type": self.edge_type,
            "transfer_weight": round(self.transfer_weight, 3),
        }


#: Default transfer coefficient per edge type. ``calls`` loses something
#: across an agent boundary; ``data_flow`` carries the value through intact.
TRANSFER_WEIGHTS = {
    "calls": 0.7,
    "invokes": 0.7,
    "data_flow": 1.0,
    "consumes": 1.0,
    "returns": 0.5,
}


def transfer_weight_for(edge_type: str) -> float:
    """Transfer coefficient for ``edge_type`` (unknown types default to 1.0)."""
    return TRANSFER_WEIGHTS.get(edge_type, 1.0)


class AgentBehaviorGraph:
    """
    Agent 行为图谱

    将一个 session 中所有 Agent 的工具调用组织为有向图，
    支持：
    - 节点和边的增删查
    - 风险沿边的传播计算
    - 识别关键风险节点（风险放大器）
    - 关键路径提取（从某节点到另一节点的最风险路径）
    - 单次工具调用作为节点加入图谱
    """

    def __init__(self, session_id: str = "unknown"):
        self.session_id = session_id
        self.nodes: dict[str, BehaviorNode] = {}
        self.edges: dict[str, BehaviorEdge] = {}
        self._node_list: list[BehaviorNode] = []   # 按时间顺序
        self._adjacency: dict[str, list[str]] = {}  # node_id → [child_node_ids]
        # 增量风险传播的缓存与脏标记
        self._total_risk_cache: dict[str, float] = {}
        self._dirty_nodes: set[str] = set()
        self._topo_cache: Optional[list[str]] = None
        # 增量统计计数器（summary() 依赖，O(1) 而非 O(V)）
        self._status_counts: dict[NodeRiskStatus, int] = {
            status: 0 for status in NodeRiskStatus
        }
        self._action_counts: dict[str, int] = {}
        self._critical_node_ids: set[str] = set()

    # ─── 图写入 ──────────────────────────────────────────────

    def add_node(self, node: BehaviorNode) -> BehaviorNode:
        """将一个工具调用节点加入图谱"""
        if node.node_id in self.nodes:
            # 已存在则更新（同一工具调用可能产生多个审计结果）
            existing = self.nodes[node.node_id]
            before = (existing.risk_status, existing.fuse_action)
            for k, v in node.__dict__.items():
                if v != getattr(existing, k):
                    setattr(existing, k, v)
            self._bump_status_counters(before, existing)
            # 本地风险等字段可能被改写，需重算该节点及其下游。
            self._mark_dirty(node.node_id)
            return existing

        self.nodes[node.node_id] = node
        self._node_list.append(node)
        self._adjacency[node.node_id] = []
        self._bump_status_counters(None, node)
        self._mark_dirty(node.node_id)
        return node

    def add_edge(self, edge: BehaviorEdge) -> BehaviorEdge:
        """添加一条边（Agent 间调用关系）"""
        if edge.edge_id in self.edges:
            return self.edges[edge.edge_id]
        if edge.from_node_id not in self.nodes:
            raise ValueError(f"from_node {edge.from_node_id} not in graph")
        if edge.to_node_id not in self.nodes:
            raise ValueError(f"to_node {edge.to_node_id} not in graph")

        self.edges[edge.edge_id] = edge
        self._adjacency[edge.from_node_id].append(edge.to_node_id)
        # 新边让下游节点多了一条风险来源，并使拓扑序失效。
        self._mark_dirty(edge.to_node_id)
        self._topo_cache = None
        return edge

    def add_tool_call_as_node(
        self,
        agent_id: str,
        tool_name: str,
        params_summary: str,
        fuse_action: str,
        shadow_risk_score: float,
        parent_node_id: Optional[str] = None,
        edge_type: str = "calls",
        inherited_risk: float = 0.0,
        labels: Optional[list[str]] = None,
    ) -> BehaviorNode:
        """
        将一次工具调用快速加入图谱。
        如果指定了 parent_node_id，自动创建边。
        """
        node = BehaviorNode(
            agent_id=agent_id,
            session_id=self.session_id,
            tool_name=tool_name,
            params_summary=params_summary,
            fuse_action=fuse_action,
            shadow_risk_score=shadow_risk_score,
            risk_status=self._score_to_status(shadow_risk_score),
            inherited_risk=inherited_risk,
            labels=labels or [],
        )
        self.add_node(node)

        if parent_node_id and parent_node_id in self.nodes:
            edge = BehaviorEdge(
                from_node_id=parent_node_id,
                to_node_id=node.node_id,
                edge_type=edge_type,
                # Transfer coefficient only -- the upstream node's risk is
                # already on that node, so putting it here too squared it.
                transfer_weight=transfer_weight_for(edge_type),
            )
            self.add_edge(edge)

        return node

    def update_node_risk(
        self,
        node_id: str,
        total_risk: float,
        fuse_action: Optional[str] = None,
    ) -> Optional[BehaviorNode]:
        """Write a governed risk back onto a node.

        Used by the engine's two-pass governance: the node is first inserted at
        its local risk so the parent edge exists, propagation then computes the
        effective risk, and this records that outcome so the graph, its counters
        and the audit chain all agree with the decision that was made.

        Marks the node dirty so the next propagation recomputes it and its
        descendants rather than serving a stale cache entry.
        """
        node = self.nodes.get(node_id)
        if node is None:
            return None

        before = (node.risk_status, node.fuse_action)
        node.shadow_risk_score = max(0.0, min(float(total_risk), 1.0))
        node.risk_status = self._score_to_status(node.shadow_risk_score)
        if fuse_action is not None:
            node.fuse_action = fuse_action
        self._bump_status_counters(before, node)
        self._mark_dirty(node_id)
        return node

    # ─── 图查询 ──────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[BehaviorNode]:
        return self.nodes.get(node_id)

    def get_session_nodes(self) -> list[BehaviorNode]:
        """返回该会话所有节点（按时间顺序）"""
        return self._node_list

    def get_critical_nodes(self, threshold: float = 0.7) -> list[BehaviorNode]:
        """
        识别风险放大器节点（高风险 + 放大了上游风险）
        """
        return [
            n for n in self._node_list
            if n.shadow_risk_score >= threshold and n.downstream_risk_amplified
        ]

    def get_risk_path(self, start_node_id: str, end_node_id: str) -> list[BehaviorNode]:
        """返回从 start 到 end 的**最风险路径**。

        “最风险”定义为路径上所有节点的总风险（传播后）之和最大的那条路径。
        与旧实现不同：旧版本是纯 BFS 最短路径，docstring 却写着
        "risk-weighted shortest path / higher risk = shorter effective distance"，
        即声称按风险加权而实际没有。

        采用 Dijkstra（最大化路径风险之和）；若图中存在环，
        则退化为按访问顺序的有界搜索，保证终止。
        """
        if start_node_id not in self.nodes or end_node_id not in self.nodes:
            return []
        if start_node_id == end_node_id:
            return [self.nodes[start_node_id]]

        # 路径风险之和（越大越好）作为 Dijkstra 的“距离”。
        best: dict[str, float] = {start_node_id: self._path_risk(self.nodes[start_node_id])}
        prev: dict[str, Optional[str]] = {start_node_id: None}
        # 最大堆：Python 只有最小堆，因此存取正号。
        import heapq

        heap: list[tuple[float, str]] = [(-best[start_node_id], start_node_id)]
        settled: set[str] = set()

        while heap:
            # ``best`` remains the authoritative score; the heap only orders.
            _neg_score, node_id = heapq.heappop(heap)
            if node_id in settled:
                continue
            settled.add(node_id)
            if node_id == end_node_id:
                break

            for child_id in self._adjacency.get(node_id, []):
                if child_id not in self.nodes or child_id in settled:
                    continue
                candidate = best[node_id] + self._path_risk(self.nodes[child_id])
                if candidate > best.get(child_id, float("-inf")):
                    best[child_id] = candidate
                    prev[child_id] = node_id
                    heapq.heappush(heap, (-candidate, child_id))

        if end_node_id not in prev:
            return []

        # 回溯路径
        path_ids: list[str] = []
        cursor: Optional[str] = end_node_id
        while cursor is not None:
            path_ids.append(cursor)
            cursor = prev.get(cursor)
        path_ids.reverse()
        return [self.nodes[nid] for nid in path_ids if nid in self.nodes]

    @staticmethod
    def _path_risk(node: BehaviorNode) -> float:
        """路径评估中一个节点的风险贡献（本地风险）。"""
        return node.shadow_risk_score

    def get_downstream_nodes(self, node_id: str) -> list[BehaviorNode]:
        """获取某节点的所有下游节点"""
        result = []
        visited = set()
        queue = list(self._adjacency.get(node_id, []))

        while queue:
            child_id = queue.pop(0)
            if child_id in visited:
                continue
            visited.add(child_id)
            if child_id in self.nodes:
                result.append(self.nodes[child_id])
                queue.extend(self._adjacency.get(child_id, []))

        return result

    def compute_risk_propagation(self) -> dict[str, float]:
        """从上游向下游传播，计算每个节点继承了多少上游风险。

        风险传播规则::

            local[node]      = node.shadow_risk_score
            total[node]      = max(local[node],
                                   max over incoming edges e of total[e.from] * e.transfer_weight)
            inherited[node]  = total[node] - local[node]

        返回值是**传播后的总风险** ``total[node]``（即该节点在考虑上游传导
        后的风险水平），与 ``risk_local_context`` 等上游消费方的语义一致。
        每个节点的 :attr:`BehaviorNode.inherited_risk` 则被更新为
        ``inherited[node]`` —— 纯粹来自上游传导的增量，本地风险不计入。

        计算走**拓扑序**（自根向叶），与节点插入顺序、边遍历顺序无关：
        同一张图始终得到同一结果。

        这是**增量**实现：只有自上次计算以来图发生变化（新增节点/边，或某
        节点的本地风险被改写）才会重算，且只重算受影响的下游子图。典型
        的「追加一次工具调用」场景下，本次调用只影响新节点及其后代，
        因此单次成本与图规模无关。
        """
        if not self._node_list:
            return {}

        dirty = self._collect_dirty_nodes()
        if not dirty:
            # 图未变化：返回缓存结果（与全量重算完全一致）。
            return dict(self._total_risk_cache)

        order = self._topological_order()
        total_risk = dict(self._total_risk_cache)

        for nid in order:
            if nid not in dirty and nid in total_risk:
                continue  # 未受影响且已有缓存值，跳过
            candidates = [
                total_risk[src] * flow
                for src, flow in self._incoming_edges(nid)
                if src in total_risk
            ]
            base = self.nodes[nid].shadow_risk_score if nid in self.nodes else 0.0
            total_risk[nid] = max([base, *candidates])

        # 回写 inherited_risk（相对本地风险的增量），并标记放大器节点。
        for nid, total in total_risk.items():
            if nid not in self.nodes:
                continue
            node = self.nodes[nid]
            inherited = max(0.0, total - node.shadow_risk_score)
            node.inherited_risk = inherited
            if inherited > _AMPLIFICATION_THRESHOLD:
                node.downstream_risk_amplified = True

        self._total_risk_cache = total_risk
        self._dirty_nodes.clear()
        return dict(total_risk)

    def _incoming_edges(self, node_id: str) -> list[tuple[str, float]]:
        """node_id 的入边列表 [(from, transfer_weight), ...]。"""
        edges = []
        for edge in self.edges.values():
            if edge.to_node_id == node_id and edge.from_node_id in self.nodes:
                edges.append((edge.from_node_id, edge.transfer_weight))
        return edges

    def _collect_dirty_nodes(self) -> set[str]:
        """返回需要重算的节点集合。

        显式标记（新增节点/边、本地风险被改写）的节点，加上它们的所有
        下游后代 —— 上游变化会沿边传导下来。
        """
        dirty = set(self._dirty_nodes)
        # 首次计算（缓存为空）时所有节点都脏。
        if not self._total_risk_cache:
            dirty.update(self.nodes.keys())
        # 沿出边扩展，把下游后代纳入。
        frontier = list(dirty)
        while frontier:
            nid = frontier.pop()
            for child in self._adjacency.get(nid, []):
                if child in self.nodes and child not in dirty:
                    dirty.add(child)
                    frontier.append(child)
        return dirty

    def _mark_dirty(self, *node_ids: str) -> None:
        """标记节点为待重算（内部使用）。"""
        self._dirty_nodes.update(node_ids)

    def invalidate_risk_cache(self) -> None:
        """丢弃传播缓存，下次 compute 时全量重算。"""
        self._total_risk_cache = {}
        self._dirty_nodes.clear()
        self._topo_cache = None

    def _topological_order(self) -> list[str]:
        """返回自根向叶的处理顺序。

        使用 Kahn 算法：每个节点排在其所有上游节点之后。遇到环时
        （agent 互相调用），环上剩余节点按 id 稳定追加，保证算法必然
        终止且结果可复现。

        结果会被缓存：拓扑序只取决于**边集**，因此仅当新增边时才失效。
        工具调用不断追加但不成环的典型场景下，这避免了每次传播都对全图
        重新排序。
        """
        if self._topo_cache is not None:
            return self._topo_cache

        out_edges: dict[str, list[str]] = {
            nid: list(children) for nid, children in self._adjacency.items()
        }
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        for nid, children in out_edges.items():
            for child in children:
                if child in in_degree:
                    in_degree[child] += 1

        ready = sorted(nid for nid, deg in in_degree.items() if deg == 0)
        order: list[str] = []
        seen: set[str] = set()

        while ready:
            nid = ready.pop(0)
            if nid in seen:
                continue
            seen.add(nid)
            order.append(nid)
            newly_ready = []
            for child in out_edges.get(nid, []):
                if child not in in_degree:
                    continue
                in_degree[child] -= 1
                if in_degree[child] == 0 and child not in seen:
                    newly_ready.append(child)
            if newly_ready:
                ready.extend(sorted(newly_ready))

        # 环上残留节点：稳定追加，确保不遗漏
        for nid in sorted(self.nodes):
            if nid not in seen:
                order.append(nid)

        self._topo_cache = order
        return order

    def to_graph_dict(self) -> dict:
        """导出为 dict（用于序列化或前端图谱渲染）"""
        return {
            "session_id": self.session_id,
            "nodes": [n.to_summary() for n in self._node_list],
            "edges": [e.to_summary() for e in self.edges.values()],
            "critical_nodes": [n.node_id for n in self.get_critical_nodes()],
        }

    # ─── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def _score_to_status(score: float) -> NodeRiskStatus:
        if score >= 0.90:
            return NodeRiskStatus.CRITICAL
        elif score >= 0.70:
            return NodeRiskStatus.HIGH
        elif score >= 0.50:
            return NodeRiskStatus.MEDIUM
        elif score >= 0.20:
            return NodeRiskStatus.LOW
        return NodeRiskStatus.SAFE

    def summary(self) -> dict:
        """图谱统计摘要。

        计数由 :meth:`_bump_status_counters` 在写入路径上增量维护，
        因此本方法是 O(1) 而非 O(V)。长时间会话下 ``process_tool_call``
        每次都会调用 summary，全量遍历曾是主要热点。
        """
        return {
            "session_id": self.session_id,
            "total_nodes": len(self._node_list),
            "total_edges": len(self.edges),
            "risk_distribution": {
                status.value: self._status_counts[status]
                for status in NodeRiskStatus
            },
            "critical_node_count": len(self._critical_node_ids),
            "blocked_count": self._action_counts.get("block", 0),
            "review_count": self._action_counts.get("human_review", 0),
        }

    # ─── 增量计数器维护 ───────────────────────────────────────────

    def _bump_status_counters(self, before, node: BehaviorNode) -> None:
        """把节点迁移到当前状态时更新所有增量计数器。

        ``before`` 为 ``None`` 表示新节点；否则是写入前的
        ``(risk_status, fuse_action)`` 快照。
        """
        if before is not None:
            old_status, old_action = before
            if old_status != node.risk_status:
                self._status_counts[old_status] -= 1
                self._status_counts[node.risk_status] += 1
            if old_action != node.fuse_action:
                self._action_counts[old_action] = (
                    self._action_counts.get(old_action, 0) - 1
                )
                self._action_counts[node.fuse_action] = (
                    self._action_counts.get(node.fuse_action, 0) + 1
                )
        else:
            self._status_counts[node.risk_status] += 1
            self._action_counts[node.fuse_action] = (
                self._action_counts.get(node.fuse_action, 0) + 1
            )
        self._refresh_critical(node)

    def _refresh_critical(self, node: BehaviorNode) -> None:
        """按当前 shadow_risk_score / amplified 标志维护关键节点集合。"""
        is_critical = (
            node.shadow_risk_score >= _CRITICAL_RISK_THRESHOLD
            and node.downstream_risk_amplified
        )
        if is_critical:
            self._critical_node_ids.add(node.node_id)
        else:
            self._critical_node_ids.discard(node.node_id)
