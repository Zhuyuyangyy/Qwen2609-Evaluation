# RB-AS-005

**Repository:** AgentShield_V3
**Difficulty:** hard

## Task

Tool-name canonicalisation is implemented identically in two places: a private helper in the provenance-signals module, and an inlined expression in the trust-policy module's classification path. The two must not be allowed to drift. Converge them onto a single canonical implementation used by both call paths, without changing any observable behaviour. Classifying a tool, computing a provenance signal, and the public API surface must all behave exactly as before, for every input, including empty and non-string ones.

<details><summary>中文说明</summary>

工具名规范化在两处以完全相同的方式实现：一处是 provenance-signals 模块中的私有 helper，另一处是 trust-policy 模块分类路径中的内联表达式。二者不应被允许各自演化而分叉。请把它们收敛到一个被两条调用路径共用的单一规范化实现，且不改变任何可观测行为。对任意输入（包括空值与非字符串），工具分类、provenance 信号计算以及 public API 表面都必须与之前完全一致。

</details>

## Constraints

- 不得修改测试
- 不得修改 grader
- 不得改变任何可观测行为
- 不得改变 public API 签名或返回结构
- 不得删除既有函数或改变其可见性以外的属性
- 两条调用路径都必须真正使用同一个实现

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1800 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
