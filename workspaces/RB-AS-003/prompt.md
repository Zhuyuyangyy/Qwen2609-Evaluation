# RB-AS-003

**Repository:** AgentShield_V3
**Difficulty:** hard

## Task

Writing a governed risk back onto an existing node updates the node's own recorded risk and its status counters, but the aggregate risk that downstream queries serve does not always reflect that change. Repeated queries return the previously computed value instead of recomputing, so the graph reports a stale total for a node that was just rewritten. Fix the freshness tracking so that rewriting a node's risk causes the affected part of the graph to be recomputed. Do not disable or bypass the incremental cache: unchanged parts of the graph must still be served from cache, and the cache must still be correct for an unchanged graph.

<details><summary>中文说明</summary>

把受治理的风险写回已存在的节点时，该节点自身记录的风险与状态计数器会更新，但下游查询所聚合的风险并不总是反映该变化。重复查询会返回此前计算的值而不是重算，导致刚被改写的节点仍报告一个陈旧的总风险。请修复新鲜度追踪，使改写节点风险后，图中受影响的部分会被重新计算。不得关闭或绕过增量缓存：未变化的部分仍必须由缓存提供，且缓存在图未变化时仍必须正确。

</details>

## Constraints

- 不得修改测试
- 不得修改 grader
- 不得关闭或禁用缓存
- 不得改为每次全量重算
- 不得删除 _total_risk_cache / _topo_cache / _dirty_nodes
- 不得改变 public API 或返回结构

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1800 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
