# RB-EM-002

**Repository:** emotion-like-functional-modulation-main
**Difficulty:** hard

## Task

The multi-seed aggregation computes the mean and standard deviation incorrectly and mishandles missing runs. Fix both

<details><summary>中文说明</summary>

多 seed 聚合在报告均值的同时还报告了一个离散度指标。其中一个离散度指标使用了有偏估计量，导致报告的数值系统性低估跨 seed 的变异程度。请修正该估计量，且不得改变聚合函数的公开契约（返回的键、每个键的含义、以及它报告的均值）。

</details>

## Constraints

- 不得修改测试
- 不得丢弃缺失 run 的记录

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1200 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
