# Paper outline — material for the participant to write

This is **not** a draft. The official rules require the report and any paper to
be authored by the participant. What follows is the section structure, the
question each section must answer, the real data available, and where the
evidence lives.

**Suggested framing (participant's call):**

> Evaluating Repository-Level Coding Agents Under Reproducible Execution and
> Partial Observability

The measurement-coverage finding is a genuine methodology contribution, not an
apology: a zero is only meaningful when the underlying field was actually
observed.

---

## 1 Introduction

- **要说明**: what problem a real-repository benchmark addresses that toy
  algorithm tasks do not, and what "reproducible execution" adds on top.
- **可引用**: 8 frozen tasks from 2 real repositories; 112 automated tests; each
  task a private snapshot with one injected defect; grading on public + hidden
  checks plus SHA-256 frozen files.
- **证据**: `01_Benchmark_Facts/METHODOLOGY.md`, `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`

## 2 Benchmark Design

- **要说明**: how tasks were constructed and why the snapshot is private.
- **可引用**: construction chain (real repo → re-injected equivalent defect →
  private snapshot → dual-state verification → checksum freeze); no snapshot
  carries `.git`, because the upstream fixes live in public commits.
- **证据**: `01_Benchmark_Facts/METHODOLOGY.md`, `01_Benchmark_Facts/tasks.jsonl`

### 2.4 Patch-based grading

- **要说明**: why grading consumes a patch plus recorded evidence rather than
  re-running the agent's session.
- **可引用**: 60/20/10/10 components; `TestRun.ok` requires exit code 0 and zero
  failures; TaskSuccess is the conjunction of five legs.
- **证据**: `01_Benchmark_Facts/GRADING.md`

## 3 Evaluation Harness

### 3.2 Resume / runtime instrumentation — and why it was not enough

- **要说明**: what the harness recorded, and where recording was missing.
- **可引用**: manual-resume and runtime-error counts recoverable for **1 of 8**
  tasks; duration for **2 of 8**; semantic-intervention for **7 of 8**.
- **证据**: `release/v0.1/AVAILABILITY_MATRIX.md`

### 3.4 Coverage semantics ← the methodological core

- **要说明**: the rule that a zero is only meaningful when the field was
  observed, and how partial coverage is reported instead of being filled in.
- **可引用**: `confirmed_*` fields with explicit coverage ratios and
  `PARTIAL_COVERAGE`; aggregates withheld rather than emitted; a negative control
  proving the guard fires.
- **证据**: `release/v0.1/FINAL_SUBMISSION_RECORD.md`,
  `release/v0.1/QA_SUMMARY.md`,
  `release/v0.2/HARNESS_METADATA_SCHEMA.md`

## 4 RealRepoBench-Q2609 v0.1

- **要说明**: the frozen set and its taxonomy.
- **可引用**: 8 tasks; 4 declared task types across 7 tasks plus 1 `UNSPECIFIED`
  (RB-AS-001 predates the field); AgentShield ×5, emotion ×3.
- **证据**: `01_Benchmark_Facts/BENCHMARK_FACT_SHEET.md`

## 5 Results

- **要说明**: what was measured, with denominators stated.
- **可引用**:
  - valid-run Task Success Rate **7/7 = 100%** (denominator: valid model runs)
  - harness valid submission rate **7/8 = 87.5%** (denominator: frozen tasks)
  - **no 8-task Task Success Rate exists**
  - scores: all 7 graded runs at 100/100
  - patch size: 6 of 7 runs changed one file; one changed two
- **证据**: `02_Results/FINAL_METRICS.json`, `02_Results/TASK_RESULT_TABLE.md`

> Do not merge the two rates into "87.5%". They have different denominators.

## 6 Harness Reliability Audit

### 6.1–6.3 Missing metadata, partial coverage, unknown ≠ zero

- **要说明**: the audit found that a `null` telemetry field had been read both
  as zero and as missing, and each reading produced a wrong aggregate once.
- **可引用**: the corrected fields and their coverage; the two deprecated
  readings named explicitly.
- **证据**: `04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`,
  `release/v0.1/AVAILABILITY_MATRIX.md`

### 6.4 Re-verification

- **要说明**: recorded grades were independently recomputed, and one
  discrepancy found.
- **可引用**: an independent re-run of the frozen grader on isolated copies;
  one recorded grade corrected for a nodeid path-root mismatch, with the before
  and after values recorded in the grade file itself.
- **证据**: `02_Results/REVERIFICATION.json`, `01_Benchmark_Facts/GRADING.md`

## 7 Threats to Validity

- **要说明**: what this run cannot support.
- **可引用**:
  - n=7 with 7 successes supports no difficulty gradient;
  - no cross-model comparison from a single run;
  - heterogeneous telemetry coverage limits aggregate claims;
  - one task produced no model output, so no 8-task rate exists;
  - a ceiling effect is *consistent with* the data but does not locate a
    capability ceiling.
- **证据**: `02_Results/CEILING_EFFECT_EVIDENCE.md`,
  `04_Harness_Reliability/HARNESS_RELIABILITY_FACTS.md`

## 8 Reproducibility

- **要说明**: how a third party can verify the exact artifact reviewed.
- **可引用**: archive SHA-256, 81 entries, `testzip()`, and the command that
  reproduces the hash.
- **证据**: `release/v0.1/FINAL_SUBMISSION_RECORD.md`,
  `release/v0.1/checksums.sha256`

## 9 Conclusion

- **要说明**: the participant's own judgement, including the overall experience
  rating. Facts available for it are in
  `05_Submission_Field_Materials/SUBMISSION_FIELD_FACTS.md` under
  `EVIDENCE_FOR_PARTICIPANT_JUDGMENT`.

---

## The one sentence worth carrying into the paper

> A zero count is only meaningful when the underlying field was actually
> observed.

It is the shortest accurate summary of the measurement lesson, and it applies
well beyond this benchmark.

## Extending to a multi-model paper

When a second model is run against the same frozen set, section 5 becomes a
paired comparison. The protocol and the comparability rule are already written:
`release/v0.2/PAIRED_EVALUATION_PROTOCOL.md`. Eight high-quality frozen
workspaces support a credible benchmark paper without needing more tasks.
