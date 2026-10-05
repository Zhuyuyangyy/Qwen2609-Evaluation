# RB-AS-001

**Repository:** AgentShield_V3
**Difficulty:** medium

## Task

A benchmark adapter passes evaluation-only fields into the model input path. Locate the leak and fix it without changing the output schema

<details><summary>中文说明</summary>

当前 benchmark 的模型输入链路中至少有一个仅用于评测的字段被泄漏了出去。请定位评测专用字段进入可观测/运行时字段的位置并修复，使引擎只能依据运行时观测做判断。要求保持 public API、输出 schema、CLI 及现有测试套件兼容。

</details>

## Constraints

- 不得修改 grader
- 不得删除测试
- 保持 CLI backward compatibility
- 保持输出 schema 不变

## How your work is checked

- Test command: `pytest -q`
- Time budget: 1200 seconds
- Public checks are in `public_tests/` and are the ones you can run yourself.
- Additional checks you cannot see are applied after you finish.

Work inside this directory. Do not look for, download, or reproduce the upstream project's history; the repository here is a private snapshot and its history is intentionally absent.
