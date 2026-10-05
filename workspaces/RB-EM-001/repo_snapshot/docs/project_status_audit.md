# Project Status Audit — Phase 0 + Phase 0.5

**Date**: 2026-06-09
**Branch**: main (commit a8b7158 → Phase 0.5 pending)
**Auditor**: Agent (automated)
**Rule**: No results modified, no features added. Only paths, commands, and gaps verified.

---

## Q1: pytest 能否从零跑通？

**命令**: `python -m pytest tests/ -v`

**结果**: 125 passed, **1 failed**

**失败测试**:
- `tests/test_v0_3.py::TestEventSimilarity::test_encode_event_delete`
- 原因: 测试用 `"delete file /data/important.txt"` 期望 `data_loss_potential > 0.5`，但当前 `encode_event` 的 `data_loss_words` 不包含 `"file"` 或 `"/data/important.txt"` 中的任何词。这是我们在扩展关键词时移除了 `"all files"` 等多词短语后引入的回归。
- 修复方案: 在 `data_loss_words` 中添加 `"file"` 或修复测试用例以匹配当前词表。

**通过率**: 125/126 = 99.2%

---

## Q2: Semi-Real-300 原始 source JSON 是否存在？

**不存在。** 缺失。

- `AffectiveBenchmark` 类（`emotion_agent/affective_benchmark.py`）从**代码内嵌模板**动态生成 300 个任务，不是从外部 JSON 加载。
- 300 个任务只有 **60 个唯一描述字符串**（每个模板重复约 5 次）。
- 仓库中无 `semi_real_300.json` 或任何独立的 source JSON 文件。
- `dataset_card.md` 已明确标注："Original source JSON not available in current codebase"。

**缺口**: 没有独立于代码的数据文件。数据完全由 `AffectiveBenchmark.__init__` 中的模板列表 + `random.choice` 生成。

---

## Q3: 主表结果能否一键重跑？

**不能。**

| 结果 | 能否重跑 | 缺什么 |
|------|---------|--------|
| benchmark_v2 (5-fold CV) | ✅ 能 | `python experiments/benchmark_v2/run_real_benchmark.py` |
| R-Judge 外部验证 | ✅ 能 | `python experiments/benchmark_v2/run_rjudge_benchmark.py` |
| DeepSeek LLM baseline | ⚠️ 部分 | 需要有效 API key；脚本在 `experiments/llm_baseline/` |
| **论文主表 (FullCalibratorAdapter 等)** | ❌ 不能 | 原始结果来自 `scripts/generate_benchmark_results.py`，但该脚本使用 `DummyAgent`（agent 参数从未使用），结果由 baseline 字符串硬编码决定，不是真实组件输出 |
| 论文中的 Acc=0.753, Composite=0.860 | ❌ 不能 | 这些数字在当前代码中无法复现；`reproducibility_audit.md` 已承认："Main method results are reported from prior work and cannot be independently reproduced from the current codebase" |

**关键缺口**:
1. 论文主表数字与 benchmark_v2 真实管线结果**不一致**（主表是 DummyAgent 恒等映射，benchmark_v2 是真实组件）
2. 没有一键脚本同时产出论文所有表格和图
3. `scripts/generate_figures.py` 能出图，但数据来源是硬编码数字而非管线输出

---

## Q4: DeepSeek baseline 数据集定位

- **原始 DeepSeek baseline (100 条)**: `experiments/results/llm_baseline/` — gold_labels.json 有 100 条
- **Full-300 DeepSeek baseline**: `experiments/results/llm_baseline/full300/` — gold_labels.json 有 300 条
- 两者都使用 `AffectiveBenchmark(seed=42, size=100/300)` 生成的任务
- **与 Semi-Real-300 完全一致**: 同样的模板生成，同样的任务集
- `submission_pack_v0_4/llm_baseline_full300_report.md` 已将其定位为 "auxiliary stress test"
- `dataset_equivalence_audit_full300.md` 承认 AB-300 是 "regenerated, not equivalent" to Semi-Real-300

**问题**: 论文主表中的 "Semi-Real-300" 实际上就是 `AffectiveBenchmark(size=300)` 生成的合成模板数据，不是真正的半真实数据。DeepSeek baseline 跑在完全相同的数据上，但 gold labels 来自 `RISK_TO_DECISION` 规则映射（循环验证风险）。

---

## Q5: annotation reliability 完成状态

**未完成。**

- 没有第二标注者的标注结果
- Cohen's kappa 未生成
- `blind_annotation_sample_100.csv` 的 `annotator_label` 和 `annotator_rationale` 列全部为空
- `annotation_reliability_pending_report.md` 已承认 "pending"
- `annotation_protocol_v1.md` 存在但未被执行

---

## Q6: blind annotation / gold / kappa script 路径

| 文件 | 路径 | 状态 |
|------|------|------|
| Gold reference (hidden) | `experiments/annotation/gold_reference_hidden.json` | ✅ 存在，100 条 |
| Blind sample | `experiments/annotation/blind_annotation_sample_100.csv` | ✅ 存在，但标注列为空 |
| Blind sample (with gold hidden) | `experiments/annotation/blind_annotation_sample_100_with_gold_hidden_reference.csv` | ✅ 存在 |
| Generate gold script | `experiments/annotation/generate_gold_reference.py` | ✅ 存在 |
| Generate blind sample script | `experiments/annotation/generate_blind_sample.py` | ✅ 存在 |
| Compute kappa script | `experiments/annotation/compute_kappa.py` | ✅ 存在，但无输入数据（第二标注者标注为空） |

**缺口**: 第二标注者标注结果。没有标注数据，kappa 脚本无法运行。

---

## Q7: README / paper / audit / dataset_card 表述一致性

**基本一致，但有几处微妙差异：**

| 主题 | README | dataset_card | reproducibility_audit |
|------|--------|-------------|----------------------|
| 数据来源 | "Semi-Real-300 benchmark" | "semi-real, template-generated" | "Original source JSON not available" |
| Kappa | "pending" | "pending" | "not completed" |
| DeepSeek 定位 | "auxiliary stress test" | "auxiliary" | "can be fully reproduced" |
| 主表可复现 | 未明确说不可复现 | — | "cannot be independently reproduced" |

**不一致处**:
1. README 暗示 Semi-Real-300 是半真实数据，但 `AffectiveBenchmark` 实际是纯模板生成。`dataset_card` 更诚实（"semi-real, template-generated"），但 "semi-real" 这个词仍然有误导性——60 个手写模板重复 5 次不是 "semi-real"。
2. README 没有明确说主表结果不可复现，但 `reproducibility_audit` 承认了这一点。

---

## Q8: LICENSE / pyproject.toml / requirements / CI

| 项目 | 状态 |
|------|------|
| LICENSE | ❌ 不存在 |
| pyproject.toml | ❌ 不存在 |
| requirements.txt | ❌ 不存在 |
| requirements-dev.txt | ❌ 不存在 |
| setup.py | ✅ 存在（`/workspace/setup.py`） |
| CI workflow (.github/workflows/) | ❌ 不存在 |
| .gitignore | ✅ 存在 |

**严重缺口**: 没有 LICENSE 意味着法律上他人无权使用代码；没有 requirements.txt 意味着无法一键安装依赖；没有 CI 意味着测试通过徽章是假的。

---

## Q9: 根目录临时文件 / zip / 重复包

| 文件 | 大小 | 性质 | 建议 |
|------|------|------|------|
| `files.zip` | 10KB | 临时传输包（benchmark_v2 原始文件） | 删除或移到 archive |
| `revised_files.zip` | 27KB | 临时传输包（修改后的模块） | 删除或移到 archive |
| `rjudge_data/` | — | R-Judge 克隆（第三方数据） | 不应提交到仓库，已加入 .gitignore |

**注意**: 之前的 `dist/*.zip`（teacher_review_pack 和 full_archive）在当前工作目录中不存在，可能已被清理或仅在 origin/main 上。

---

## Q10: experiments/ 一键复现

**不能。**

现有脚本：
- `experiments/benchmark_v2/run_real_benchmark.py` — 能跑 5-fold CV，但产出的是 benchmark_v2 结果，不是论文主表
- `experiments/benchmark_v2/run_rjudge_benchmark.py` — 能跑 R-Judge 外部验证
- `scripts/generate_benchmark_results.py` — 使用 DummyAgent，结果不反映真实组件
- `scripts/generate_figures.py` — 用硬编码数字生成图

**缺口**:
1. 没有 `experiments/reproduce/reproduce_main_tables.py`
2. 没有 `experiments/reproduce/reproduce_figures.py`
3. 论文主表数字与 benchmark_v2 数字不一致，无法统一

---

## Q11: 数据类型和条数

| 数据集 | 类型 | 条数 | 唯一模板 | 来源 |
|--------|------|------|---------|------|
| AffectiveBenchmark-300 | 模板生成（合成） | 300 | 60 | 代码内嵌模板 + random.choice |
| AffectiveBenchmark-100 | 模板生成（合成） | 100 | ~60 | 同上，size=100 |
| DeepSeek LLM baseline (100) | 同上 | 100 | — | AffectiveBenchmark(size=100) |
| DeepSeek LLM baseline (full300) | 同上 | 300 | — | AffectiveBenchmark(size=300) |
| R-Judge (外部) | 真实人工标注 | 571 | 571 | 第三方公开数据集 |
| Blind annotation sample | 模板生成子集 | 100 | — | 从 AffectiveBenchmark 抽样 |

**关键事实**: 所有"主实验"数据都是 60 个手写模板的重复。没有任何真正的半真实或真实部署数据。

---

## Q12: Q2 投稿三大 reviewer attack point

### Attack 1: 主实验是同义反复（致命级）
原始 benchmark 使用 `DummyAgent`，action 完全由 baseline 字符串决定，agent 参数从未使用。消融对照是恒等映射，不是真实机制对比。benchmark_v2 修复了这个问题，但暴露出更深层问题：risk 通路 ≈ 关键词检测器预测按关键词标的标签。5-fold CV 证实 memory 净负、affect 落在噪声里。

### Attack 2: 无独立标注，gold 标签循环验证（致命级）
gold labels 来自 `RISK_TO_DECISION` 规则映射（项目自己写的确定性规则），不是独立人工标注。Cohen's kappa 未完成（第二标注者标注为空）。DeepSeek baseline 的 gold 也是同一套规则。审稿人会指出：你在测"系统能不能复现你自己写的规则"。

### Attack 3: R-Judge 外部验证全面失效（严重级）
在 571 条真人标注的真实数据上，整个框架 unsafe recall = 0.000（risk/memory）或 0.030（full）。关键词检测器对社会工程/钓鱼/隐私泄露类风险完全无效。这直接否定框架的外部效度。

---

## 缺口汇总（按严重程度排序）

| # | 缺口 | 严重程度 | 修复难度 |
|---|------|---------|---------|
| 1 | 主表结果不可复现（DummyAgent 恒等映射 vs 真实组件结果不一致） | 致命 | 高 |
| 2 | 无独立标注，kappa 未完成 | 致命 | 中（需找人标注） |
| 3 | R-Judge 外部验证全面失效 | 致命 | 极高（需重写 risk encoder） |
| 4 | 无 LICENSE | 严重 | 低 |
| 5 | 无 requirements.txt / pyproject.toml | 严重 | 低 |
| 6 | 无 CI workflow | 严重 | 低 |
| 7 | 1 个 pytest 失败（encode_event 回归） | 中等 | 低 |
| 8 | 根目录临时 zip 文件 | 低 | 低 |
| 9 | "Semi-Real-300" 命名误导（实为纯模板生成） | 中等 | 低（改名即可） |
| 10 | 无一键复现脚本 | 中等 | 中 |

---

## Phase 0.5 执行记录

**执行日期**: 2026-06-09
**原则**: 不改实验结果，不加功能，只做仓库可信度修复。

### 1. 修复 pytest 失败 ✅

- **问题**: `test_encode_event_delete` 期望 `data_loss_potential > 0.5`，但 `encode_event` 的 `data_loss_words` 不包含测试用例中的词
- **修复**: 在 `event_similarity.py` 中，当 `irreversible_action` 触发时自动提升 `data_loss_potential` 到 0.7（逻辑：不可逆操作本身意味着数据丢失风险）
- **同时修复**: `test_calculate_similarity_identical` 的浮点精度问题（`== 1.0` → `abs(x - 1.0) < 1e-9`）
- **结果**: `python -m pytest tests/ -v` → **126/126 passed**

### 2. 新增 LICENSE ✅

- **文件**: `/workspace/LICENSE`
- **类型**: MIT License
- **版权**: Copyright (c) 2024-2026 Zhuyuyangyy

### 3. 新增 requirements.txt ✅

- **文件**: `/workspace/requirements.txt`
- **内容**: numpy, matplotlib, pytest

### 4. 新增 CI workflow ✅

- **文件**: `/workspace/.github/workflows/tests.yml`
- **内容**: Python 3.10/3.11/3.12 矩阵测试，运行 `python -m pytest tests/ -v`

### 5. 删除临时 zip 文件 ✅

- 已删除: `files.zip` (10KB), `revised_files.zip` (27KB)

### 6. README 修改摘要 ✅

| 修改项 | 旧内容 | 新内容 |
|--------|--------|--------|
| 徽章 | "tests-passing"（假 CI） | "tests-126/126"（实际数字）+ LICENSE 徽章 |
| "Semi-Real-300" | 暗示为半真实数据 | 明确标注 "synthetic/template-generated, NOT semi-real" |
| 主表可复现性 | 未提及 | 明确标注 "NOT reproducible from current repository" |
| R-Judge 结果 | 未提及 | 明确标注 "external validation failed, unsafe recall = 0.000" |
| Claim "structured safety calibration on semi-real benchmarks" | 存在 | 改为 "synthetic benchmarks (mechanism sanity check only)" |
| NOT Claimed | 5 项 | 新增 "Validated effectiveness on non-synthetic benchmarks" |
| Known Limitations | 无 | 新增 5 项（关键词编码器、memory 净负、affect 噪声级、无独立标注、主表不可复现） |
| Data Availability | 无 | 新增表格，列出所有数据集类型和状态 |
| Reproduce section | 无 | 新增，明确标注主表不可复现，列出可复现实验 |
| V0.4-paper status | ✅ | ⚠️ "preliminary, not reproducible" |

### 7. 是否还有不可复现或误导 claim？

**README 层面已清除。** 但以下位置仍需后续处理：
- `submission_pack_v0_4/` 内的 manuscript 仍包含旧主表数字和 "Semi-Real-300" 用法（Phase 1R 处理）
- `dataset_card.md` 仍使用 "semi-real" 描述（Phase 1R 处理）
- `q2_acceptance_gate.md` 的 BORDERLINE+ 评级未更新（Phase 1R 处理）

---

## Phase 1R 执行记录

**执行日期**: 2026-06-09
**原则**: 不复现旧论文主表，不使用 Semi-Real-300 命名。旧主表标记为 prior unreproducible result。将 synthetic 数据冻结为可检查的数据资产。

### 1. 冻结 Synthetic-AB300 数据 ✅

- **脚本**: `experiments/rebuild/export_synthetic_ab300.py`
- **命令**: `python experiments/rebuild/export_synthetic_ab300.py --seed 42`
- **输出**: `data/rebuild/synthetic_ab300_seed42.json`
- **内容**: 300 条记录，60 个唯一模板，每条记录包含 id、category、description、expected_risk_level、heuristic_gold_decision、source_type、template_id、seed、generation_note
- **验证**: 运行成功，输出 300 条记录（60 唯一模板）

### 2. Dataset Card ✅

- **文件**: `data/rebuild/dataset_card_synthetic_ab300.md`
- **明确说明**:
  - 这是 synthetic/template-generated benchmark
  - 60 unique templates repeated approximately 5 times
  - 只能用于 mechanism sanity check
  - 不能作为真实世界有效性证据
  - 不能替代 human-validated benchmark
  - 旧名 "Semi-Real-300" 已弃用，禁止使用

### 3. 重建合成消融实验 ✅

- **脚本**: `experiments/rebuild/run_synthetic_ablation.py`
- **命令**: `python experiments/rebuild/run_synthetic_ablation.py --input data/rebuild/synthetic_ab300_seed42.json`
- **输出**: `results/rebuild/synthetic_ablation_results.json`
- **指标**: accuracy、macro_f1、per-class precision/recall/f1、confusion_matrix、severity_mae、risky_auto_exec_rate、over_caution_rate
- **所有 gold labels 明确标记为 heuristic labels，不是 human labels**

### 4. 结果说明 ✅

- **文件**: `results/rebuild/synthetic_ablation_report.md`
- **包含**: 命令、输入数据路径、输出结果路径、指标表、limitations、why this does not validate real-world safety
- **关键发现**:
  - risk encoder 是唯一有意义的改进（plain→risk: +0.233 acc）
  - memory 层损害性能（risk→memory: -0.166 acc）
  - affect 层为噪声级（memory→full: +0.003 acc）
  - BLOCK 类在所有 baseline 中基本无法检测

### 5. Phase 1R 新增文件列表

| 文件 | 类型 | 说明 |
|------|------|------|
| `data/rebuild/synthetic_ab300_seed42.json` | 数据 | 冻结的 Synthetic-AB300 数据集 |
| `data/rebuild/dataset_card_synthetic_ab300.md` | 文档 | 数据集卡片 |
| `experiments/rebuild/export_synthetic_ab300.py` | 脚本 | 导出冻结数据集 |
| `experiments/rebuild/run_synthetic_ablation.py` | 脚本 | 运行合成消融实验 |
| `results/rebuild/synthetic_ablation_results.json` | 结果 | 消融实验结果 JSON |
| `results/rebuild/synthetic_ablation_report.md` | 报告 | 消融实验报告 |

### 6. 结果摘要

| Baseline | Accuracy | Macro-F1 | Severity MAE | Risky-Auto ↓ |
|----------|----------|----------|--------------|--------------|
| plain    | 0.060    | 0.028    | 1.207        | 1.000        |
| risk     | 0.293    | 0.191    | 0.873        | 0.546        |
| memory   | 0.127    | 0.110    | 1.020        | 0.546        |
| full     | 0.130    | 0.108    | 1.233        | 0.515        |

### 7. 旧主表状态

**旧主表仍不可复现。** 旧主表数字（Acc=0.753, Composite=0.860 等）来自 DummyAgent（agent 参数未使用），与当前真实管线结果不一致。旧主表标记为 prior unreproducible result，不应在任何新文档中引用。

### 8. Synthetic-AB300 不是 Semi-Real-300

**Semi-Real-300 命名已正式弃用。** 当前数据集重命名为 Synthetic-AB300，反映其真实性质：60 个手写模板重复约 5 次的合成数据。所有新增文档均使用 Synthetic-AB300 命名，不使用 Semi-Real-300。

### 9. 仍需后续处理

- `submission_pack_v0_4/` 内的 manuscript 仍包含旧主表数字和 "Semi-Real-300" 用法（Phase 1.5 已加降级声明）
- `dataset_card.md`（旧版）仍使用 "semi-real" 描述（Phase 1.5 已加 warning）
- `q2_acceptance_gate.md` 的 BORDERLINE+ 评级未更新（Phase 1.5 已标记为 historical preliminary assessment）
- 无独立人类标注（Phase 2: pilot 30 条，双人标注，算 kappa）

---

## Phase 1.5 执行记录

**执行日期**: 2026-06-09
**原则**: 不改实验结果，不加功能，只给旧 submission pack 加降级声明和 warning。
**工作分支**: `phase-1-5-deprecate-submission-pack`

### 1. 建立 DEPRECATION_NOTICE.md ✅

- **文件**: `archive/research_packs_v0_4/submission_pack_v0_4/DEPRECATION_NOTICE.md`
- **内容**: 明确声明此 pack 是 historical/preliminary，不应作为当前 Q2-ready submission package；Semi-Real-300 命名弃用；主表结果不可复现；Acc=0.753/Composite=0.860 是历史结果；Q2 BORDERLINE+ 是历史初稿评估；标注可靠性未完成；R-Judge 外部验证失败

### 2. 给旧论文包 README 加顶部警告 ✅

- **文件**: `archive/research_packs_v0_4/submission_pack_v0_4/README.md`
- **修改**: 在标题下方加入醒目 blockquote warning，标注 Deprecated naming / Not Q2-ready / Not independently reproducible / See DEPRECATION_NOTICE.md
- **Q2 Readiness 行**: 加注 "(historical preliminary assessment — see deprecation notice above)"

### 3. 给 13 个危险文件顶部加 warning ✅

以下文件均在标题下方加入了统一的 deprecation warning：

1. `q2_acceptance_gate.md`
2. `q2_submission_strategy.md`
3. `q2_blocker_closure_report.md`
4. `phase5_acceptance_audit.md`
5. `dataset_card.md`
6. `data_authenticity_statement.md`
7. `numeric_consistency_audit_v0_3.md`
8. `manuscript_v0_4_q2_attempt.md`
9. `manuscript_v0_4_q2_attempt_blind.md`
10. `manuscript_v0_4_q2_attempt_final_review.md`
11. `manuscript_v0_4_q2_attempt_blind_final_review.md`
12. `cover_letter_draft.md`
13. `论文投稿说明_中文.md`

Warning 内容统一为：
> **Deprecated historical draft.** The claims in this file were written before the Phase 0–1R audit. Do not treat Semi-Real-300, Q2 BORDERLINE+, or the old main-table metrics as current reproducible evidence.

### 4. 生成 deprecated_claims_inventory.md ✅

- **文件**: `archive/research_packs_v0_4/submission_pack_v0_4/deprecated_claims_inventory.md`
- **内容**: 完整列出 96 处危险 claim，按类别分：
  - Semi-Real-300 occurrences: 59 处
  - BORDERLINE+ occurrences: 16 处
  - Acc=0.753 / Composite=0.860 occurrences: 2 处
  - Q2-ready / Q2 cautious attempt occurrences: 14 处
  - "semi-real" claim occurrences: 5 处
- 每项包含 file path、line number、phrase、status (deprecated / historical)

### 5. 未修改实验结果声明

**确认**: Phase 1.5 没有修改任何实验结果 JSON、figure、metrics。所有修改仅限于添加 deprecation notice 和 warning 文本。

### 6. 旧论文包状态变更

| 方面 | Phase 1R 前 | Phase 1.5 后 |
|------|------------|-------------|
| submission_pack_v0_4 定位 | Active submission pack | **Historical preliminary pack** |
| Semi-Real-300 命名 | 作为正式名称使用 | 标记为 deprecated/misleading |
| Q2 BORDERLINE+ | 作为当前就绪评估 | 标记为 historical preliminary assessment |
| Acc=0.753 / Composite=0.860 | 作为当前结果引用 | 标记为 historical prior results |
| DEPRECATION_NOTICE.md | 不存在 | 存在 |
| deprecated_claims_inventory.md | 不存在 | 存在（96 处清单） |
| 文件 warning | 无 | 14 个文件已加 warning |

### 7. Phase 1.5 新增/修改文件列表

| 文件 | 操作 | 说明 |
|------|------|------|
| `submission_pack_v0_4/DEPRECATION_NOTICE.md` | 新建 | 降级声明 |
| `submission_pack_v0_4/deprecated_claims_inventory.md` | 新建 | 危险 claim 清单 |
| `submission_pack_v0_4/README.md` | 修改 | 加顶部 warning block |
| `submission_pack_v0_4/q2_acceptance_gate.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/q2_submission_strategy.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/q2_blocker_closure_report.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/phase5_acceptance_audit.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/dataset_card.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/data_authenticity_statement.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/numeric_consistency_audit_v0_3.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/manuscript_v0_4_q2_attempt.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/manuscript_v0_4_q2_attempt_blind.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/manuscript_v0_4_q2_attempt_final_review.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/manuscript_v0_4_q2_attempt_blind_final_review.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/cover_letter_draft.md` | 修改 | 加 deprecation warning |
| `submission_pack_v0_4/论文投稿说明_中文.md` | 修改 | 加 deprecation warning |
| `docs/project_status_audit.md` | 修改 | 新增 Phase 1.5 section |

### 8. 进入 Phase 2 前必须完成的条件

1. ✅ Phase 1.5 merge 到 main
2. ✅ 旧论文包已标记为 historical preliminary pack
3. ✅ 所有危险 claim 已列清单并加 warning
4. ⬜ Phase 2 需要独立人工标注（pilot 30 条，双人盲注，Cohen's kappa）
5. ✅ Phase 3: R-Judge Failure Reproduction Pack (PR #13 open) — 待跑 571 条官方数据后出 failure matrix
6. ✅ Phase 4: Risk Encoder v2 MVP (PR #14 open) — 待修 injection branch 与 threshold 双重计算后合入
7. ⬜ Phase 5 需要扩展到 100 条 human-validated benchmark
8. ⬜ Phase 6 需要新建 v0.5 honest manuscript
---

## Phase 2 执行记录 (docs/data-only)

**执行日期**: 2026-06-13
**原则**: 不自动标注，不伪造完成文件，不做 human-validated 声明。
**工作分支**: `phase-2-pilot30-docs-only`
**范围**: 仅提交数据和文档，不包含可执行脚本或 CI 增强。

### 1. pilot30_cases.json 生成

- **文件**: `data/human_validated/pilot30_cases.json`
- **内容**: 30 个 pilot cases，4-label 分布
- **分布**: AUTO_EXECUTE=6, SIMULATE_FIRST=8, HUMAN_REVIEW=10, BLOCK=6
- **风险覆盖**: 全部 8 种风险类型

### 2. 盲注 CSV 生成

- **文件**: `data/human_validated/annotator_A_pilot30.csv`, `data/human_validated/annotator_B_pilot30.csv`
- **CSV 列**: case_id, source_type, user_request, task_context, proposed_agent_action, risk_factors, allowed_tools, annotator_label, annotator_rationale, uncertainty_flag
- **禁止列**: expected_decision_hidden, model_prediction, final_label, annotator_A_label, annotator_B_label
- **标注状态**: 全部空白（AWAITING_ANNOTATION）

### 3. 标注指南

- **文件**: `data/human_validated/annotation_guideline_v2.md`
- **内容**: 4 标签定义、8 风险类型、冲突规则、标注规则

### 4. 状态报告

- **文件**: `results/human_validation/phase2_status_report.md`
- **状态**: AWAITING_ANNOTATION

### 5. Phase 2 新增文件列表

| 文件 | 类型 | 说明 |
|------|------|------|
| `data/human_validated/pilot30_cases.json` | 数据 | 30 个 pilot cases |
| `data/human_validated/annotation_guideline_v2.md` | 文档 | 标注指南 v2 |
| `data/human_validated/annotator_A_pilot30.csv` | 数据 | 标注者 A 空白标注表 |
| `data/human_validated/annotator_B_pilot30.csv` | 数据 | 标注者 B 空白标注表 |
| `results/human_validation/phase2_status_report.md` | 报告 | Phase 2 状态报告 |
| `docs/project_status_audit.md` | 文档 | 新增 Phase 2 section |

### 6. 不包含的内容

- 不包含 experiments/human_validation/*.py 脚本
- 不包含 CI 增强
- 不包含 completed annotation
- 不包含 model prediction
- 不包含 final label

### 7. 仍需后续处理

- 标注者 A 完成标注
- 标注者 B 完成标注
- 计算 Cohen kappa（后续单独提交脚本）
- Phase 3: R-Judge Failure Reproduction Pack (PR #13, open)
- Phase 4: Risk encoder v2 实现 (PR #14, pending)
- Phase 5: HV-100 扩展
- Phase 6: 新 v0.5 honest manuscript

---

## Phase 4.1 执行记录 (2026-09-22)

**范围**: 按 review 的 P0 优先级执行;本地分支 `phase41-main`(= main + #13)、`phase41-pr14`(= #14 rebase 到 #13 后 + 修复),待 token 推送后合入。

### 1. R-Judge 计数审计:571 vs 569(钉死)

- 旧 loader `glob("**/*.json")` 会把 `eval/results`、`results/**`、`config` 全吞进 → **1243 条**。
- 官方 repo `data/` 目录 = **571 条**,id 全唯一;ACL 论文 = **569**(论文期快照,2024-10-05 "update data" 加了 2 条 injection);NEXUS(2026)= 564(571 剔除 7 条泄露)。
- 修复:`convert_rjudge.py` loader 限定 `data/**` + id 去重 + `_source` 溯源;产出 **571 条**并透明记录 569/571/564 差异。
- 结论:基准以官方数据目录(571)钉死;论文对照数字在 matrix 中列出。

### 2. #14 P0 修复(3 处)

- `threshold_calibrator.py`:`>=0.85 → BLOCK` 分支不可达(被 `>=0.55 → HUMAN_REVIEW` 拦截),已重排并加回归测试。
- `threshold_calibrator.py`:`adjustment` 双重计算(既提分又降阈值),改为只作用 score 一次,决策对固定 base thresholds。
- `semantic_risk_encoder.py`:`prompt_injection` / `social_engineering` 移出加权合成(交给专用 expert detector),避免同一攻击被计分两次。

### 3. 官方 571 条 V1/V2 结果(matrix:`results/rjudge_v2/v1_v2_failure_matrix.md`)

| Baseline | Unsafe recall | Evidence coverage | Over-escalation |
|---|---|---|---|
| V1 [plain] | 0.0000 | 0.00 | — |
| V1 [full] | 0.2558 | 0.33 | 0.54 |
| V2 | 0.0066 | **1.00** | **0.196** |

- 零覆盖修复:unsafe 中 zero-risk 71.8% → 0%;over-escalation 减半。
- V2 只抓 2/301 unsafe:**R-Judge injection 是间接注入**(恶意指令藏在环境载荷,礼貌措辞),TF-IDF + regex 抓不到 → 印证论文"多维推理"结论,V2 定位为 heuristic hybrid baseline。

### 4. V0.9 设计(Phase 5 协议,待审)

- 文档:`docs/design/phase5_v09_affective_core_design.md`
- 三处机制缺陷已定位(见文档 §0);协议冻结:AffectiveCore / Episodic Retrieval / PolicyModulator / 连续 PE 学习 / 在线闭环 / Different-History & Same-Task benchmark。

### 5. V0.9 实现完成(根据批准的设计)

- 协议落地:`emotion_agent/affective_core.py`(online PE 更新+decay)、`policy_modulator.py`(budget/阈值调制,单次计分)、`v09_agent.py`(闭环 Agent);`semantic_risk_map.py` 改连续 PE 学习;`experience_memory.py` 增加 `record_outcome`/`retrieve`(任务语义检索,修复 memory 未参与决策)。
- Different-History/Same-Task:"相同任务/相同客观风险,不同历史 → 不同策略"成立。

| 指标 | 结果 |
|---|---|
| History Sensitivity | 1.000 [1.0, 1.0] |
| State Persistence | 1.000 |
| Recovery Lag | 1.14 步 [1.0, 1.4] |
| Decay Half-life(拟合) | 40.4 步(≈内置 40) |
| Generalization monotone | 1.00 |
| Neg/Pos Asymmetry | 1.0(对称 lr 下单步冲击相等,负性偏差体现在恢复动力学) |

- 图:`results/benchmark_v3/affect_state_trajectory.png`、`affect_decay_recovery.png`(可复现,均已 gitignore)。
- 测试:新增 `tests/test_v09_affective_core.py` 12 例,全套 **192 passed**。
- 说明:部分模板 r_base 为 0.0(如 "Trust anonymous PR"),即 V2 TF-IDF 对该短句评估为无风险——与 indirect-injection 同源的词法局限,留待 V3 embedding。
