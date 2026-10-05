# Redaction log

Original evidence is unmodified. This log records what the submission
copy changed and what it omits.

## Path relativisation

20 file(s) in the submission copy had operator absolute
paths rewritten so the published attachments do not carry this
machine's directory layout:

- the frozen-benchmark root became `RealRepoBench-Q2609/`
- the evaluation root was removed, leaving workspace-relative paths
- user-home segments became `<user-home>`

The originals in `evaluation_runs/` retain their paths and were not
modified. Only the submission copies were rewritten.

- 03_Execution_Evidence/evaluation_runs/RB-AS-001/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-001/terminal.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-002/metadata.json
- 03_Execution_Evidence/evaluation_runs/RB-AS-002/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-002/terminal.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-003/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-003/terminal.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-005/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-AS-005/regression_test.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-001/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-001/terminal.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-002/metadata.json
- 03_Execution_Evidence/evaluation_runs/RB-EM-002/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-002/regression_test.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-002/terminal.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-004/metadata.json
- 03_Execution_Evidence/evaluation_runs/RB-EM-004/public_test.log
- 03_Execution_Evidence/evaluation_runs/RB-EM-004/terminal.log
- 06_Environment/evaluation_manifest.json
- 06_Environment/REVERIFICATION.json

## Operator-side material not published

Scoring scratch and hidden-grading output stay in `evaluation_runs/` as
operator-side evidence and are not carried into this bundle:

- grader_stdout.txt
- hidden_test.log
- grader_stdout.txt
- hidden_test.log

## Not collected at all

No API key, token, credential, password or `.env` file was copied into
this bundle. The build refuses credential-shaped filenames and scans
every file for secret-shaped content.
