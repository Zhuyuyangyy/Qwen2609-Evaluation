# Task results — RealRepoBench-Q2609 v0.1

One row per frozen task. `null` / `NOT_AVAILABLE` means the artifact
did not establish the value; it was not estimated.

| task_id | repository | task_type | diff | run_status | valid | success | total | target_fix | regression_pass | constraint_violation | resume | duration_s | files |
|---|---|---|---|---|---|---|---|---|---|---|---|---:|---:|---:|
| RB-AS-001 | AgentShield_V3 | UNSPECIFIED | medium | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | 0.943 | 1 |
| RB-AS-002 | AgentShield_V3 | hidden_only_bug | medium | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | n/a | 1 |
| RB-AS-003 | AgentShield_V3 | hidden_only_bug | hard | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | 147.2 | 1 |
| RB-AS-004 | AgentShield_V3 | docs_consistency | easy | INFRASTRUCTURE_FAILURE | no | — | n/a | — | — | — | n/a | n/a | 0 |
| RB-AS-005 | AgentShield_V3 | behavior_preserving_refactor | hard | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | n/a | 2 |
| RB-EM-001 | emotion-like-functional-modulation-main | hidden_only_bug | medium | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | 0 | n/a | 1 |
| RB-EM-002 | emotion-like-functional-modulation-main | hidden_only_bug | hard | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | n/a | 1 |
| RB-EM-004 | emotion-like-functional-modulation-main | public_visible_bug | medium | VALID_SUBMISSION | yes | yes | 100 | yes | yes | no | n/a | n/a | 1 |

## Reading this table

- `run_status = INFRASTRUCTURE_FAILURE` means no stable model
  submission existed. Its `task_success` is `null`, **not** `false`,
  and it is excluded from the model denominator.
- `task_type = UNSPECIFIED` is retained truthfully: RB-AS-001 was built
  before the task_type and capabilities fields existed.
- `duration_s = n/a` means the value could not be recovered from the
  archived metadata and was not guessed.
