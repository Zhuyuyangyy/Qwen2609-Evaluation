# Release notes — RealRepoBench-Q2609 v0.1 submission

Frozen submission package for the Qwen 2609 professional evaluation.

## Contents

```text
FINAL_SUBMISSION_RECORD.md   canonical interpretation entry point
QA_SUMMARY.md                machine facts only
checksums.sha256             SHA-256 over the archived zip
submission_bundle.zip        the submitted archive (81 entries)
```

## What v0.1 is

8 frozen repository-level tasks built from two real local repositories
(AgentShield_V3 ×5, emotion-like-functional-modulation-main ×3), each shipped as
a private snapshot with one defect present, a task statement, public checks, and
embargoed hidden checks. 112 automated tests guard the benchmark itself.

Partial-coverage semantics are part of the release, not an afterthought: a zero
count is reported only where the underlying field was actually observed, and
every such field carries an explicit coverage ratio and status.

## Change discipline

`v0.1` is permanently frozen. If a wording defect is found after submission:

```text
v0.1     submitted, frozen
v0.1.1   revision package, only if the platform accepts replacements
```

Changelog for any revision must state:

```text
Changed:
- wording only (or: nothing)
- no benchmark change
- no grade change
- no patch change
- no TaskSuccess change
```

## Known limits carried into this release

- 7 of 8 tasks produced a valid model submission; the 8th is a harness
  infrastructure failure, so no 8-task Task Success Rate exists.
- manual-resume and runtime-error counts are recoverable for 1 of 8 tasks;
  semantic-intervention counts for 7 of 8.
- durations exist for 2 of 8 tasks; no representative median is published.
- RB-AS-001 predates the `task_type` / `capabilities` fields and is recorded as
  `UNSPECIFIED` rather than assigned one retroactively.
