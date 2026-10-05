# Submission field facts

Facts for the participant to fill the official "专业评测" submission form.
Each section separates **facts**, **evidence path**, and anything the
participant must decide personally.

Nothing here is a subjective evaluation. Where the artifacts do not establish a
value it is marked `NOT_AVAILABLE` or `PARTICIPANT_CONFIRM_REQUIRED`.

---

## 评测使用的 Agent / Harness

**事实**

- Harness: **Qoder**
- Model under test: **qwen-latest-series-invite-2609**
- Session protocol: one fresh session per task (`fresh_session_required: true`
  in `evaluation_manifest.json`); baseline commit
  `RealRepoBench frozen baseline`; no git remote in any workspace.

**已观察到的 Harness 运行现象（来自真实 metadata / logs）**

- **7 of 8 tasks produced a stable final submission.**
- Exact manual-resume and runtime-error counts are **NOT_AVAILABLE for 7 of the
  8 tasks**: those counts could not be recovered from the archived metadata.
- **Only RB-EM-001 has recovered counts of 0** (0 manual resume, 0 runtime
  error). No other task's count is known, so no run-wide resume or runtime-error
  total is claimed.
- **No task recorded a semantic human intervention.** A semantic intervention
  means a human supplied solution information; this is distinct from a manual
  resume, and neither appears anywhere in the archived evidence.
- RB-AS-004 produced **no** stable final submission: 0 tracked `.py` files
  modified, no untracked non-cache files, and the only tracked delta a SQLite
  runtime-state file. Recorded `INFRASTRUCTURE_FAILURE`.

**证据**

- `06_Environment/evaluation_manifest.json`
- `04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`
- `03_Execution_Evidence/evaluation_runs/RB-AS-004/`

---

## 操作系统

**事实**: NOT_AVAILABLE

The grading operator's OS was recorded during the workspace audit
(`Windows 10`, per `06_Environment/PUBLIC_WORKSPACE_AUDIT.md` /
    `06_Environment/environment.json`), but that is
the *grading* host. The artifacts do not establish the OS of the machine on which
Qoder executed the agent sessions.

**证据**: `06_Environment/environment.json`

**参与者需确认**: PARTICIPANT_CONFIRM_REQUIRED

---

## Benchmark 任务所属领域

**事实分类**: software engineering / programming / repository-level coding

- 8 tasks, all drawn from real Python repositories
- repository-level scope (multi-file codebases with existing test suites)
- **4 declared task types across 7 tasks**: `hidden_only_bug` ×4,
  `public_visible_bug` ×1, `docs_consistency` ×1,
  `behavior_preserving_refactor` ×1
- **plus 1 UNSPECIFIED task (RB-AS-001)**, which predates the `task_type` field;
  it is reported as UNSPECIFIED rather than assigned a type after the fact

**标记**: PARTICIPANT_CONFIRM_REQUIRED — this is a proposed classification, not
a value read from an artifact.

**证据**: `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`

---

## 评测描述

Bullet facts only. The participant writes the prose.

- Benchmark name: **RealRepoBench-Q2609**
- Version: **0.1**
- Frozen task count: **8** (formal sample size)
- Original candidate count: 12 rows in `tasks.jsonl`; 4 rejected/deferred and
  excluded from every denominator
- Repository sources: **2** — AgentShield_V3 (5 tasks),
  emotion-like-functional-modulation-main (3 tasks)
- Task types: 4 distinct types (see above)
- Capability dimensions measured: defect localisation, propagation-chain
  tracing, statistical correctness, cache-invalidation reasoning,
  authority determination, behaviour-preserving refactoring, constraint
  compliance, regression safety
- Test isolation: hidden tests and the grader are never present in the agent's
  workspace; grading runs on an isolated staging copy outside the workspace
- Session protocol: fresh session per task; each workspace a separate git repo
  with no remote and no upstream history
- Grading protocol: 60/20/10/10 weighted components plus a binary TaskSuccess
  verdict; baseline-relative regression; SHA-256 frozen-file checks

**证据**: `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`,
`01_Benchmark_Facts/GRADING.md`, `01_Benchmark_Facts/METHODOLOGY.md`

---

## 评测体系介绍

Structured outline + evidence paths. The participant writes the section.

1. Benchmark provenance and construction
   — `01_Benchmark_Facts/METHODOLOGY.md`
2. Task set and distributions
   — `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`
3. Why 12 candidates became 8 frozen tasks (rejection and deferral)
   — `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`
4. Public/private workspace separation and the audit that enforces it
   — `06_Environment/PUBLIC_WORKSPACE_AUDIT.md`
5. Scoring components and the TaskSuccess definition
   — `01_Benchmark_Facts/GRADING.md`
6. Baseline-relative regression rationale
   — `01_Benchmark_Facts/GRADING.md`
7. Metric separation: model performance vs harness reliability
   — `02_Results/FINAL_METRICS.json`

---

## 评测对象输入 / 输出描述

**Input given to the model**

- defective repository snapshot (`repo_snapshot/`)
- task statement (`prompt.md`)
- public checks (`public_tests/`) — the checks the agent may run itself
- the repository's normal files and configuration

**Explicitly NOT given to the model**

- hidden tests
- the grader and any grading metadata
- reference repair / reference metadata
- defect scripts and `defect.json`
- `baseline_failures.json`
- git history of the upstream repository

**Model output**

- modified repository
- code/document patch (`patch.diff`, produced by `git diff` against the frozen
  baseline)
- terminal and tool execution trace (`terminal.log`)

**Evaluation output (operator-side)**

- `grade.json` — the grader's own `Score.to_dict()`
- `metadata.json`
- `public_test.log`
- `interventions.log` where present
- `git_status.txt`

**证据**: `03_Execution_Evidence/evaluation_runs/`, `evaluation_manifest.json`

---

## 评测逻辑

Factual pipeline, from the grader's own code:

```
defective repository snapshot
  → Agent execution (fresh session, Qoder)
  → public verification  (public_tests/)
  → private hidden grading  (isolated staging copy, outside the workspace)
  → regression check     (baseline-relative)
  → constraint check     (SHA-256 frozen-file verification)
  → TaskSuccess  (boolean, all legs must hold)
```

Boolean conditions, as implemented in `grader/score.py`:

- `TestRun.ok` ⇔ `exit_code == 0 AND failed == 0 AND errors == 0`
- **TaskSuccess** ⇔ `public_tests.ok AND hidden_tests.ok AND no violations AND
  no_new_regression AND target_fix_pass`
- `RegressionPass` ⇔ `candidate_failures − (baseline ∪ target) = ∅`
- `TargetFixPass` ⇔ `target_failures ∩ candidate_failures = ∅`

**证据**: `01_Benchmark_Facts/GRADING.md`,
`01_Benchmark_Facts/benchmark_manifest.json`

---

## 评测分析报告事实

Tables and metrics only; no analysis prose is supplied.

- per-task results: `02_Results/TASK_RESULT_TABLE.md`
- machine-readable table: `02_Results/FINAL_RESULTS_TABLE.csv`
- aggregate metrics: `02_Results/FINAL_METRICS.json`,
  `02_Results/summary.json`, `02_Results/results.csv`
- failure cases: `02_Results/failure_cases.jsonl` (**empty** — 7/7 valid runs
  succeeded)
- infrastructure case and evidence: `04_Harness_Reliability/`
- runtime information: per-task `metadata.json`; `duration_seconds` is `null`
  where it could not be recovered
- limitation evidence: `02_Results/CEILING_EFFECT_EVIDENCE.md`,
  `04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`

---

## 整体体验评价所需证据

`EVIDENCE_FOR_PARTICIPANT_JUDGMENT`

The participant selects the rating. The observable facts:

| evidence | value |
|---|---|
| valid model runs / benchmark tasks | 7 / 8 |
| successes among valid runs | 7 / 7 |
| perfect scores among valid runs | 7 / 7 |
| correctness failures among valid runs | 0 |
| constraint violations | 0 |
| regressions under the baseline rule | 0 |
| confirmed tasks needing manual resume | 0 |
| resume-count known tasks | 1/8 |
| resume-count unknown tasks | 7/8 |
| semantic human interventions | none recorded anywhere |
| infrastructure failures | 1 (RB-AS-004) |
| median patch size (files) | 1 |
| public/private grading isolation | verified by audit, 8/8 workspaces clean |
| ceiling effect on valid runs | consistent with, per |
| 8-task protocol completeness | **incomplete** — no 8-task TSR exists |

**证据**: `02_Results/FINAL_METRICS.json`,
`02_Results/CEILING_EFFECT_EVIDENCE.md`,
`04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`
