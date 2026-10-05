# Report outline

The official evaluation report must be written by the participant personally;
it may not be AI-authored. This outline therefore states, per section, **what
the participant needs to explain**, **which real data may be cited**, and
**where the supporting artifact lives**.

No analysis prose, no subjective rating, and no conclusion paragraph is
supplied here.

---

## 1. 评测对象与设置

- **你需要说明**: which model and harness were evaluated, how sessions were
  run, and what isolation the benchmark enforced.
- **可引用的真实数据**: Harness `Qoder`; model `qwen-latest-series-invite-2609`;
  8 frozen tasks; fresh session per task; no git remote in any workspace.
- **证据**: `06_Environment/evaluation_manifest.json`,
  `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`

## 2. Benchmark 来源与构建

- **你需要说明**: why this benchmark exists, where its tasks come from, and how
  a private instance was constructed.
- **可引用的真实数据**: 2 source repositories; 12 candidates → 8 frozen; the
  construction chain (re-injected defect → private snapshot → dual-state
  verification → checksum freeze); why 4 tasks were rejected or deferred.
- **证据**: `01_Benchmark_Facts/METHODOLOGY.md`,
  `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`

## 3. 能力维度与适用范围

- **你需要说明**: which capabilities the 8 tasks exercise, and what they do
  **not** cover.
- **可引用的真实数据**: 4 task types; per-task `capabilities` (7 tasks declare
  4 each; RB-AS-001 is `UNSPECIFIED` and must be reported as such).
- **证据**: `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`,
  `02_Results/FINAL_RESULTS_TABLE.csv`

## 4. 评分指标与公式

- **你需要说明**: how a task is scored and what TaskSuccess requires.
- **可引用的真实数据**: 60/20/10/10; the boolean TaskSuccess conjunction; the
  baseline-relative `RegressionPass` and `TargetFixPass` formulas; why
  pre-existing upstream failures are exempt.
- **证据**: `01_Benchmark_Facts/GRADING.md`

## 5. 主指标与样本量

- **你需要说明**: which number is the headline metric and what its denominator
  is.
- **可引用的真实数据**: benchmark sample size **8**; valid model runs **7**;
  valid-run Task Success Rate **7/7 = 100%**; harness valid submission rate
  **7/8 = 87.5%**; **no 8-task TSR exists**.
- **证据**: `02_Results/FINAL_METRICS.json`,
  `02_Results/TASK_RESULT_TABLE.md`

> 原文要求明确区分这两个指标，不得合并表述为 "Qwen 87.5%"。

## 6. 逐题结果

- **你需要说明**: how each task went, and what the failures were.
- **可引用的真实数据**: the per-task table; 7 successes at 100/100; RB-AS-004 as
  an infrastructure failure with no model output; patch sizes 1–2 files.
- **证据**: `02_Results/TASK_RESULT_TABLE.md`,
  `02_Results/FINAL_RESULTS_TABLE.csv`,
  `02_Results/failure_cases.jsonl`

## 7. Harness 可靠性与基础设施问题

- **你需要说明**: how reliable the harness was, and what happened on RB-AS-004.
- **可引用的真实数据**: Exact manual-resume and runtime-error counts are
  NOT_AVAILABLE for 7 of 8 tasks; RB-EM-001 is the only task with recovered
  counts of 0. 1 infrastructure failure; the RB-AS-004 evidence
  (0 tracked `.py` modified, only a SQLite runtime-state file changed).
- **证据**: `04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`,
  `04_Harness_Reliability/RB-AS-004_HARNESS_FAILURE.md`

## 8. 局限与边界条件

- **你需要说明**: what this run cannot support.
- **可引用的真实数据**: `evaluation_complete_under_original_protocol: false`;
  n=7 with 7 successes supports no difficulty gradient; no cross-model
  comparison; ceiling-effect statement is limited to "consistent with" on the
  valid runs.
- **证据**: `02_Results/CEILING_EFFECT_EVIDENCE.md`

## 9. 脱敏与附件完整性

- **你需要说明**: that the bundle was scanned and how redaction was handled.
- **可引用的真实数据**: secret scan clean; embargoed-material scan clean;
  `NOT_AVAILABLE` fields listed rather than filled.
- **证据**: `06_Environment/REDACTION_LOG.md`,
  `02_Results/QA_CHECKLIST.md`

## 10. 结论

- **你需要说明**: your own judgement, including an overall experience rating.
- **可引用的真实数据**: the evidence table under
  `EVIDENCE_FOR_PARTICIPANT_JUDGMENT` in
  `05_Submission_Field_Materials/SUBMISSION_FIELD_FACTS.md`.
- **证据**: `02_Results/FINAL_METRICS.json` and everything above

---

## Fields only you can fill

| field | why |
|---|---|
| 操作系统 (of the Qoder session host) | NOT_AVAILABLE from the artifacts |
| Overall experience rating (好/中/差) | a judgement, not a fact |
| Benchmark domain label | proposed classification, needs confirmation |
| Any prose, conclusion, or comparison | official rules require participant authorship |
