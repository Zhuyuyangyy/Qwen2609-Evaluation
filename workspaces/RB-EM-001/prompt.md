# RB-EM-001

**Repository:** emotion-like-functional-modulation-main
**Difficulty:** medium

## Task

A seed configuration is not propagated to the experiment runner, so repeated experiments all run with the same seed. Fix the propagation

<details><summary>中文说明</summary>

实验 runner 本应对每个逻辑 seed 各跑一个 episode。记录的逐 run 元数据看起来是对的，但跨 seed 的离散度报告退化、配对显著性检验也紧得不合理，说明这些 run 实际上并不独立。请定位逻辑 seed 在何处不再被遵循并修复。CLI 语义、记录的元数据、以及报告的键都必须保持不变。

</details>

## Constraints

- 不得修改测试
- 不得固定随机数以迎合结果

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1200 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
