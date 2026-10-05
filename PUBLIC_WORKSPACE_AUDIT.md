# Public workspace audit

Read-only audit of the exported public evaluation workspaces.
Nothing in the frozen benchmark was modified to produce this.

- frozen tasks: **8**
- workspaces audited: 8
- passed: **8**

## Scan scope

- every file's path and name checked (binary included)
- every text file scanned in full, in 4 MiB chunks
- file types scanned: .bat, .cfg, .csv, .ini, .json, .jsonl, .md, .ps1, .py, .sh, .toml, .txt, .xml, .yaml, .yml
- binary types path-checked only: .arrow, .bin, .db, .db-shm, .db-wal, .dll, .docx, .dylib...

Matching is on private-artifact names, unambiguous phrases, and exact
defect fingerprints -- never on ordinary words, so the upstream
projects' own engineering files (e.g. their `grader_parity.json`) are
not false positives.

## Per-task results

### RB-AS-001

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: 2 upstream failure(s), matching the frozen defective baseline
  - baseline commit: 77b2387

### RB-AS-002

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: 87c6de0

### RB-AS-003

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: 1cbdd33

### RB-AS-004

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: e5b2fd8

### RB-AS-005

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: no injected defect declared (clean task)
  - baseline commit: 4fabe1b

### RB-EM-001

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: 2caa075

### RB-EM-002

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: f47e9fc

### RB-EM-004

- workspace_exists: **True**
- prompt_exists: **True**
- public_tests_present: **True**
- git_baseline_clean: **True**
- git_remote_empty: **True**
- private_path_scan_pass: **True**
- private_content_scan_pass: **True**
- exported_defect_reproduced: **True**
- unexpected_missing_dependency: **False**
- audit_status: **True**

  - defect note: defective pattern present in exported workspace
  - baseline commit: 4ecf9d4

## Verdict

**PUBLIC EVALUATION WORKSPACES READY: 8/8**
