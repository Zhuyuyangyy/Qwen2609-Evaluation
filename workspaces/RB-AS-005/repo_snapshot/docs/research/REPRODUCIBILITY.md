# Reproducing the v0.4.1 logged-trace experiment

This document is the contract for reproducing the committed v0.4.1 artifact
from a clean checkout. A third party holding the same AgentDojo dump should be
able to follow it end to end and get a **byte-identical** artifact, and should
be able to detect automatically — rather than by eye — any deviation.

Research logic is frozen. Nothing in this document changes, tunes or
reinterprets any detector, threshold, signal weight, marker, tool
classification, authorisation rule, sampling rule, trajectory grouping, label
definition or metric. It only records how to run what already exists and how to
check the result.

---

## 1. Frozen revision

Two immutable anchors identify this experiment. They do not move:

```text
Research logic revision:
49127cdef723db1e8db67d3d438a18f3e74a1853

Reproducibility tooling revision:
83dddd7d6c62946db0244b3382c0cb3fa60307b2
```

The research logic is frozen at `49127cd`. Commit `83dddd7` adds only
reproducibility tooling and documentation -- the verifier, the fingerprint
script, their tests, this document and a `.gitignore` entry. Later
documentation-only commits do not change the experiment.

`83dddd7` is named because that commit adds this file; the document is
self-referential by necessity. Everything below describes the state of the code
as of `49127cd`, which `83dddd7` does not alter.

**Do not use the moving branch HEAD as the experiment identifier.** `main`
advances with documentation and hygiene commits, so a checkout whose HEAD is
newer than `83dddd7` is still a correct checkout of this experiment. Verify the
release tag and the dataset fingerprint instead:

```bash
git describe --tags        # expect v0.4.1-research on the audited lineage
python scripts/fingerprint_agentdojo_dump.py   # expect the hash in section 4
```

For an exact released state, use the annotated `v0.4.1-research` tag rather than
the moving `main` branch. The historical `v0.3-research` and `v0.3.1-research`
tags remain untouched as earlier freeze points and must not be moved.

---

## 2. Environment

| Item | Value |
|---|---|
| Python supported by CI | 3.11 and 3.12 (see `.github/workflows/`) |
| Dependencies | `requirements-test.txt` |
| OS | not a variable of this experiment; no OS-specific claim is made or needed |

The replay is pure Python over local files. It makes no network calls, no LLM
API calls, and reads no wall-clock time or RNG state. Two consecutive runs on
the same machine produced byte-identical output (see §8), which is the
evidence for that claim rather than an assertion about any particular platform.

Install:

```bash
pip install -r requirements-test.txt
```

## 3. Dataset provenance

| Item | Value |
|---|---|
| Dataset | `ffuuugor/agentdojo-dump` (Hugging Face dump) |
| Location | `benchmark/external_datasets/ffuuugor___agentdojo-dump/**/*.arrow` |
| Loading | `benchmark/agentdojo_trace_replay.py::load_rows` |
| Rows parsed | 13913 |
| Trajectories constructed | 10536 |
| Benign trajectories available | 97 |
| Attack-labelled trajectories available | ≥ 400 |

Two caveats, stated plainly:

* **The dump is staged locally, not fetched.** `load_rows` reads the local
  Arrow file; the harness does not download anything. A clean checkout of this
  repository reproduces the *code path* but not the *data* — you must supply
  the same dump yourself.
* **The AgentDojo Arrow file is currently committed to the repository**
  (50,898,680 bytes at
  `benchmark/external_datasets/ffuuugor___agentdojo-dump/default/0.0.0/a5513c37f4d22e4dd4f2e7d064e1911e858118f0/agentdojo-dump-train.arrow`).
  This predates this pass and is recorded here as a repository-hygiene issue
  rather than fixed by it: removing it would change repository contents, which
  is outside a reproducibility-only scope. If you obtain the dump from the
  source above instead, verify it against §4 — the fingerprint is what matters,
  not where the bytes came from.

Other datasets staged under `benchmark/external_datasets/` (AgentHarm,
`agentdojo_tiny`) are **not** part of this experiment and are not fingerprinted
by the script below, so their presence or absence cannot affect this manifest.

## 4. Dataset fingerprint

The single largest external variable in a reproduction is not Python, it is the
version of the dump. `scripts/fingerprint_agentdojo_dump.py` records it.

```bash
python scripts/fingerprint_agentdojo_dump.py
```

Canonical run:

```text
dataset:          ffuuugor/agentdojo-dump
files:            1
total_bytes:      50898680
rows:             13913
trajectories:     10536
excluded_total:   0
manifest_sha256:  948b94325ae1c8cfbe41bd205fee46b0f500215559ef5cd97a25c27fcf580049
```

What the digest covers: every `*.arrow` file under the dump directory, hashed
with SHA-256, combined as `SHA256(relative_path + "\0" + file_sha256)` over
files in sorted relative-path order. The NUL separator prevents two different
`(path, hash)` pairs from producing the same concatenation. Relative paths mean
the digest is machine-independent — it does not depend on where you cloned the
repository.

The script is read-only with respect to the data: it hashes, it never modifies.
It also refuses to emit a fingerprint when no Arrow file is present, so an
empty or mis-staged dataset cannot masquerade as a valid fingerprint.

For machine-readable output use `--json`, which additionally lists each file's
path, size and SHA-256.

> "The same script" run against "a different dump version" is **not** a
> reproduction. Compare the manifest hash first; if it differs, stop and
> acquire the matching dump before comparing any numbers.

## 5. Sampling protocol

This is the section most likely to be misread, so it is stated exactly.

`benchmark/v04_trust_replay.py --max-trajectories 400` does **not** mean
"400 benign + 400 attack". The harness applies the limit to each class
independently:

```python
benign = benign[:400]
attack = attack[:400]
```

Only 97 benign trajectories exist in the dump, so `benign[:400]` is all of them
and the evaluated sample is:

```text
97 benign  (all available — nothing is sampled away)
400 attack (the first 400 in the deterministic build order)
```

Properties of this selection, all of which are load-bearing:

* **deterministic prefix slice** — the trajectory list order comes from
  `build_trajectories`, which walks the dataset in load order; no random
  sampling is involved;
* **no shuffle, no seed** — no RNG is consulted at any point, so there is no
  seed to pin and none was introduced;
* **`--max-trajectories 0` (or omitted value falsy) disables both slices** —
  the canonical run passes `400` explicitly;
* **changing this changes the experiment.** A future run that takes the last
  400 attack trajectories, or a random 400, is a different experiment and its
  numbers are not comparable to the canonical artifact. The verifier compares
  `sampling` and `benign_traces` / `attack_traces`, so it will catch this.

Because the benign set is the *complete* set rather than a sample, the benign
figures are a census and carry no sampling error. The attack figures are a
prefix of a larger population and must not be described as a property of
"AgentDojo attacks" in general.

## 6. Exact reproduction command

Run from the repository root.

bash:

```bash
python benchmark/v04_trust_replay.py \
  --mode audit \
  --max-trajectories 400 \
  --out benchmark/results/v0_4_trust_pareto.reproduced.json
```

Windows PowerShell:

```powershell
python benchmark/v04_trust_replay.py --mode audit --max-trajectories 400 --out benchmark/results/v0_4_trust_pareto.reproduced.json
```

The output path is deliberately different from the canonical artifact's. The
canonical file

```text
benchmark/results/v0_4_trust_pareto.json
```

must remain untouched. The reproduced copy is ignored by `.gitignore`
(`benchmark/results/*.reproduced.json`) so it cannot be committed by accident
and then mistaken for canonical.

Two environment conditions, both required:

```bash
# Must NOT be set to a truthy value. The canonical run had it unset.
echo "$AGENTSHIELD_ENABLE_CORPUS_MARKERS"
```

PowerShell:

```powershell
$env:AGENTSHIELD_ENABLE_CORPUS_MARKERS
```

`AGENTSHIELD_ENABLE_CORPUS_MARKERS` must be unset, or set to `0`/`false`/`no`/
`off`. It switches on corpus-specific markers that change scoring. The
canonical artifact was produced with the variable unset; a reproduction run
with it enabled is measuring your environment, not your code. The verifier
refuses to report a pass in that state (see §7).

## 7. Verification command

```bash
python scripts/verify_v04_reproduction.py \
  benchmark/results/v0_4_trust_pareto.json \
  benchmark/results/v0_4_trust_pareto.reproduced.json
```

PowerShell:

```powershell
python scripts/verify_v04_reproduction.py benchmark/results/v0_4_trust_pareto.json benchmark/results/v0_4_trust_pareto.reproduced.json
```

On success it prints exactly this and exits 0:

```text
PASS: v0.4.1 reproduction matches canonical artifact
configs: 6
sampling: 97 benign + 400 attack trajectories
audit rows: 13913
audit trajectories: 10536
```

On any mismatch it prints `FAIL: ...`, then **every** differing field, and exits
1. On a comparison that could not be attempted (missing file, malformed JSON) it
exits 2. There is no tolerance mode and no "close enough" mode: the rates are
quotients of small integers rounded to five decimals by the harness, so any
difference at all means a different run rather than rounding noise.

Fields compared, exhaustively:

```text
identity:   experiment, mode, dataset_source, detector_label_free,
            trajectory_reconstructed_from_attack_metadata, native_runtime_trace,
            asr_measured, utility_measured, trust_policy_frozen_before_measurement,
            sampling, baseline_for_delta
audit:      rows, trajectories, excluded, excluded_total
structure:  ladder config order, results config order (order is semantic)
per config: benign_traces, benign_steps, benign_step_block_fpr,
            benign_step_review_rate, benign_trace_block_rate,
            attack_traces, attack_trace_detection_rate,
            attack_trace_block_rate, delta_vs_v03_provenance
```

plus a fail-closed check that corpus markers are off.

The verifier is a comparison tool, not a predictor. It contains no expected
numbers: it diffs two artifacts and reports. Nothing it does feeds back into the
detector, the engine or the harness. Its own behaviour is unit-tested in
`tests/test_verify_v04_reproduction.py`, which uses in-memory fixtures and runs
no replay.

## 8. Expected deterministic output

Canonical ladder (mode `audit`, 97 benign / 400 attack):

| Configuration | attack-labelled trace block | attack trace detection | benign trace block |
|---|---:|---:|---:|
| `local_only` | 0.00000 | 0.03500 | 0.01031 |
| `plus_output_inspection` | 0.03500 | 0.07000 | 0.19588 |
| `plus_entity_provenance` | 0.16000 | 0.19500 | 0.41237 |
| `plus_intent_consistency` | 0.16000 | 0.19500 | 0.41237 |
| `plus_trust_policy_v0_4` | 0.03500 | 0.07000 | 0.28866 |
| `plus_intent_slots` | 0.03500 | 0.07000 | 0.28866 |

Per-config detail for the two v0.4.1 rows (the rest are in the artifact):

```text
plus_trust_policy_v0_4   benign_traces 97   benign_steps 339
                         benign_step_block_fpr 0.10914
                         benign_step_review_rate 0.05900
                         attack_traces 400
plus_intent_slots        identical to plus_trust_policy_v0_4
```

Audit header, which is the dataset fingerprint as the harness saw it:

```text
rows 13913   trajectories 10536   excluded_total 0
median_steps 1.0   p95_steps 2.0   max_steps 18   duplicate_step_keys 3377
```

Verified during this pass, three independent runs (canonical as committed, run
A, run B) all produced SHA-256:

```text
3e33c72d230cb7e0788dc4412574054c19dfd496546573698d73bff7b6a90565
```

That is byte-identity, which is stronger than the field-level PASS the verifier
reports. If your run differs at the byte level but the verifier passes, the
difference is confined to fields the verifier does not compare (for example key
ordering) and is worth investigating; if it differs in a compared field, the
verifier will say so.

## 9. What CI does and does not reproduce

CI green means **code health**. It does not regenerate this research artifact.

> GitHub Actions verifies code integrity, tests, linting, type checking,
> benchmark smoke execution and Docker health. It does not independently
> regenerate the 97-benign/400-attack v0.4.1 logged-trace artifact because that
> run depends on the locally staged external AgentDojo dump.

Specifically, the `benchmark` job runs the harness's smoke path on whatever
small fixture is staged for it. It does not read the 50 MB dump, does not replay
497 trajectories, and therefore cannot confirm 3.5% / 28.9%.

Do not read a green badge as "28.9% has been reproduced by GitHub". Those are
two different claims. The verification that matters for the research numbers is
the manual deterministic reproduction in §6–§8, which is why it is written down
as a procedure rather than automated into CI:

* full replay needs the external dump, whose availability, size, licensing and
  redistribution terms are not settled in CI;
* it would add network, cache, runtime and flakiness failure modes that have
  nothing to do with the research question;
* the split is deliberate: **CI = code health, manual deterministic
  reproduction = research artifact verification.**

Lint, for the same reason that a single merged number is misleading:

```text
CI lint scope: All checks passed
whole-repository ruff check: 123 pre-existing findings outside CI scope
```

CI runs exactly these two commands, both green:

```bash
ruff check backend/
ruff check benchmark/ benchmark/independent_eval/ scripts/
```

The 123 findings come from `ruff check .` scanning `dashboard.py`,
`benchmark_expand.py`, `docs/experiments/`, `tests/` and `sdk/` — directories CI
does not lint, with findings that predate this work.

## 10. Interpretation limits

The numbers above are trace-blocking rates on logged trajectories. What follows
is what they do and do not establish, and it is not optional when quoting them.

Allowed, with the caveat that must accompany it:

> v0.4.1 reduces benign trace blocking from 41.2% under the v0.3 provenance
> configuration to 28.9%, while the raw blocking rate on attack-labelled
> trajectories falls from 16.0% to 3.5%.
>
> An action-level audit shows that many released final calls are
> authorization-concordant or read-only. Offline replay does not establish
> whether the underlying attacks would still succeed.

Three levels are distinct and must not be collapsed:

1. **trajectory-level attack label** — what the dataset asserts about the whole
   trajectory;
2. **runtime action authorisation** — what the operator named at the final
   governance point, which is what this gate decides on;
3. **actual attack success** — whether harm occurred.

This harness uses (1) as input and (2) as its decision variable. It does not
measure (3). Conflating (2) with (3) is the specific inference to avoid.

Therefore, none of the following may be derived from these numbers:

```text
false positive rate
false negative rate
attack prevented / attack failed
0 missed attacks
attack success rate
benign utility or task success
```

Not measured, and not inferable from anything above: attack success rate,
benign utility, task success (these need the official AgentDojo sandbox and a
grader), behavioural adaptation after an intervention (offline replay only sees
logged behaviour), and instruction-detector generalisation, which is 0/9 on
held-out phrasings — the reason corpus-specific markers are off by default.

One asymmetry worth stating, because it cuts against the headline: the 28.9%
benign figure is a **census** (all 97 benign trajectories), while the 3.5%
attack figure is a **prefix** of a larger population. They are not symmetric
estimates, and the benign number is the more trustworthy of the two.
