# 论文更新稿：v0.3.1-research → v0.4.1-research

**对应旧稿**：`F:\new\AgentShield_v0.3.1_Research_Paper_Draft.pdf`（7 页，冻结于 `v0.3.1-research`）
**新证据基线**：annotated tag `v0.4.1-research` → commit `9c9ee6f1929cd68b7fb0b7b1a6e3b3b55605d493`
**本稿性质**：上述 Word 稿的**章节级更新指令集**。不是重写全文，而是对每个受影响章节给出「原文 → 替换为」，可直接照此改稿。

所有数字均由 `benchmark/results/v0_4_trust_pareto.json` 机器读取，不手抄；所有 SHA 均由 `git rev-parse` 核实。

---

## 0. 本次更新的边界（务必先读）

旧稿的全部核心结论**保持不变且继续有效**：

- observability gap 主结论（local-only 0%）不变；
- 0% → 3.5% → 16.0% 的 provenance 因果链不变，仍是论文主贡献；
- evaluation contract / 3,360 permutations 不变；
- 0/9 held-out detector 负结果不变；
- 所有 ASR / utility / task success 不测量的声明不变。

本次**只新增一层并修正一处口径**：

1. **新增 §6.1.1 与 §7.5**：v0.4.1 safe authorisation 这一层能力，以及它带来的授权安全不变量——这是新的核心设计贡献；
2. **修正旧稿 §7.3 / §8 / §10 的口径**：旧稿的 41.2% 是"under all-untrusted policy"的测量值，v0.4.1 之后它是 v0.3 配置的历史值，不再是当前系统的最坏值。措辞须随之调整，否则读者会以为 41.2% 仍是系统现状。

---

## 1. 改稿总览（受影响章节清单）

| 旧章节 | 动作 | 原因 |
|---|---|---|
| Abstract | **改** | 增加 v0.4.1 数字与授权不变量一句话 |
| §1 Introduction（4 contributions） | **改** | 贡献列表从 4 项改为 5 项 |
| §4.3 Provenance risk signals | **补** | 增加 suppressible / unsuppressible 分带与授权语义 |
| §5.2 Logged-trace replay | **补** | ladder 从 4 级改为 6 级，说明采样协议 |
| §6.1 Logged-trace replay | **增补小节** | 新增 Table 1b 与 v0.4.1 结果段 |
| §6.2 Paired control | **补一句** | upload 对的负面结果与新授权语义一致 |
| §7 Discussion | **新增 §7.5** | 授权安全不变量的论证 |
| §8 Limitations | **改 2 条 + 新增 2 条** | 增加 census/prefix 不对称、tag 锚点 |
| §9 Reproducibility | **重写** | 换 tag、加 fingerprint 与 verifier |
| §10 Conclusion | **改** | 反映 v0.4.1 与停止调参的理由 |
| 页眉/页脚 `frozen at v0.3.1-research` | **全文替换** | → `v0.4.1-research` |

未改：§2 Related Work、§3 Threat Model、§4.1–4.2、4.4–4.6、§5.1、5.3、5.4、§6.3–6.6（仅 §6.6 若引用 41.2% 需同步，见 §6.6 附注）。

---

## 2. 逐章节改稿

### 2.1 标题区 / 页眉页脚

**原文**：

```text
AgentShield v0.3.1-research -- manuscript draft
```

**替换为**：

```text
AgentShield v0.4.1-research -- manuscript draft
```

**原文**：

```text
Manuscript based on the frozen v0.3.1-research artifact
```

**替换为**：

```text
Manuscript based on the frozen v0.4.1-research artifact
```

页脚的 `Research artifact frozen at v0.3.1-research` 全文共出现 7 次，统一替换为 `Research artifact frozen at v0.4.1-research`。

---

### 2.2 Abstract

**原文**（最后三句之前插入新内容）：

> On an AgentDojo-derived logged-trace replay containing all 97 benign trajectories and 400 attack trajectories, a current-call-only gate blocks 0% of attack trajectories. Inspecting untrusted prior tool output raises the attack block rate to 3.5%, and adding entity provenance raises it to 16.0%. The same progression increases benign trace blocking from 1.0% to 19.6% and 41.2%, respectively, exposing a substantial safety-utility trade-off rather than hiding it.

**替换为**：

> On an AgentDojo-derived logged-trace replay containing all 97 benign trajectories and 400 attack trajectories, a current-call-only gate blocks 0% of attack trajectories. Inspecting untrusted prior tool output raises the attack block rate to 3.5%, and adding entity provenance raises it to 16.0%. The same progression increases benign trace blocking from 1.0% to 19.6% and 41.2%, respectively, exposing a substantial safety-utility trade-off rather than hiding it.
>
> We then show that this trade-off is not intrinsic to provenance but partly an artefact of how suspicion is aggregated. When operator authorization is allowed to temper only provenance-derived alarms and is structurally prevented from pardoning independently dangerous behaviour, benign trace blocking falls to 28.9% while the raw blocking rate on attack-labelled trajectories falls to 3.5%. An action-level audit finds that the released final calls are predominantly authorization-concordant or read-only; offline replay cannot determine whether the underlying attacks would still succeed.

**原文**：

> However, a frozen string-based instruction detector achieves 0/9 recall on differently phrased held-out injections.

**替换为**：

> However, a frozen string-based instruction detector achieves 0/9 recall on differently phrased held-out injections, and corpus-specific markers remain disabled by default.

**Keywords** 增加 `authorization semantics`：

```text
Keywords: LLM agents; prompt injection; provenance; taint tracking; runtime governance; behavior graphs; agent security; authorization semantics
```

---

### 2.3 §1 Introduction — 贡献列表

**原文**：

> The paper makes four contributions:
>
> - A runtime formulation of the observability gap: ...
> - A provenance-aware governance mechanism that ...
> - An evaluation contract that ...
> - An evaluation that reports both the detection gain and its benign cost, ...

**替换为**：

> The paper makes five contributions:
>
> - A runtime formulation of the observability gap: a tool call can be locally benign-looking even when its arguments originate in adversarial earlier context.
> - A provenance-aware governance mechanism that records content artifacts, tracks entity origin and taint, propagates risk through a behavior graph, and applies a two-pass decision after propagation.
> - **An authorization safety invariant for risk aggregation** (Section 7.5): operator authorization may explain provenance-derived suspicion, but it cannot authorize away independently dangerous behavior. We show that the natural implementation — a single cap on the combined score — is an authorization bypass in which an authorized bulk delete is scored as a benign action, and we give a band-split formulation that closes it.
> - An evaluation contract that physically separates runtime-observable inputs from evaluation-only metadata, together with a prediction-invariance test over 3,360 metadata perturbations.
> - An evaluation that reports both the detection gain and its benign cost, including negative generalization results and explicit non-measurement of attack success rate, benign utility, and task success.

同时在 §1 末段（"Our contribution is not a claim of solved prompt injection…"之后）补一段：

> The v0.4.1 configuration reported here is a *correctness* release rather than a performance release. It changes how authorization interacts with risk aggregation, and the measured cost of that change is reported rather than optimized away. No threshold, weight, marker, or sampling rule was retuned to recover any number.

---

### 2.4 §4.3 Provenance risk signals

**原文**：

> AgentShield combines ordinary local risk signals with provenance signals. The latter include: (i) untrusted content that appears instruction-like; (ii) a destination first observed in untrusted content; (iii) an origin mismatch in which a tainted value is absent from the operator request; (iv) sensitive material flowing to an external sink; (v) untrusted content preceding a privileged action; and (vi) taint propagation when an entity introduced by an untrusted artifact reaches the current call. The signals are intended as interpretable evidence rather than learned latent features.

**替换为**：

> AgentShield combines ordinary local risk signals with provenance signals. The latter include: (i) untrusted content that appears instruction-like; (ii) a destination first observed in untrusted content; (iii) an origin mismatch in which a tainted value is absent from the operator request; (iv) sensitive material flowing to an external sink; (v) untrusted content preceding a privileged action; and (vi) taint propagation when an entity introduced by an untrusted artifact reaches the current call. The signals are intended as interpretable evidence rather than learned latent features.
>
> **Signal classification.** Each signal type is assigned to exactly one of three disjoint sets, defined statically after the signal-type enumeration. `UNSUPPRESSIBLE_SIGNALS` contains the structural and manipulation classes: privilege change, audit tamper, bulk operation, credential access, policy evasion, untrusted instruction, untrusted-to-privileged action, sensitive-to-external flow, and cross-agent delegation. `SUPPRESSIBLE_PROVENANCE_SIGNALS` contains the alarms whose entire content is *provenance suspicion*: destination provenance, intent-origin mismatch, and taint propagation. `SUPPRESSION_EVIDENCE_SIGNALS` contains authorization and trusted-entity resolution, which are evidence rather than risk. A signal type not explicitly classified is treated as unsuppressible, so a future signal added without thought cannot silently become suppressible.
>
> Two remarks on this taxonomy. First, taint propagation and cross-agent delegation are deliberately distinct types: the former is a propagation fact about an entity, the latter a structural relationship between agents. Conflating them would mean that tempering taint tacitly tempers genuine delegation risk. Second, suppression-evidence signals carry score 0.0 by construction; an observation that a call was authorized or that an entity resolved through a trusted store must not be able to manufacture risk on its own.

---

### 2.5 §5.2 Logged-trace replay（含新增 §5.2.1 采样协议）

**原文**：

> Four configurations form an additive ladder: local_only sees only the current call; plus_output_inspection enables reactions to previously observed untrusted content without per-entity taint; plus_entity_provenance tracks entity origin and taint; plus_intent_consistency additionally checks against the operator request. Cluster bootstrap confidence intervals use the trajectory, not the individual step, as the resampling unit (2,000 draws).

**替换为**：

> Six configurations form an additive ladder. The first four are the frozen v0.3 rungs: `local_only` sees only the current call; `plus_output_inspection` enables reactions to previously observed untrusted content without per-entity taint; `plus_entity_provenance` tracks entity origin and taint; `plus_intent_consistency` additionally checks against the operator request. The last two are v0.4.1: `plus_trust_policy_v0_4` adds tool-semantics trust classification and prose-authorization matching with the band-split aggregation of Section 7.5; `plus_intent_slots` replaces prose matching with authorization decided against structured intent slots captured at request time. Cluster bootstrap confidence intervals use the trajectory, not the individual step, as the resampling unit (2,000 draws).

**新增 §5.2.1 Sampling protocol**（插在 §5.2 之后）：

> **Sampling protocol.** The harness flag `--max-trajectories 400` is a per-class limit, not a total. The trajectory list is partitioned by label and each partition is truncated independently (`benign[:400]`, `attack[:400]`). Because the dump contains only 97 benign trajectories, the benign slice is the complete set and the attack slice is a deterministic prefix. The evaluated sample is therefore 97 benign (a census) and 400 attack-labelled (a prefix), for 497 trajectories. Trajectory construction order is fixed by `build_trajectories`, which walks the dataset in load order; no random sampling, shuffling, or seed is involved at any point. This is load-bearing: a run that takes the last 400 attack trajectories, or a random 400, is a different experiment whose numbers are not comparable, and the committed verifier detects the difference.
>
> One asymmetry follows from this and is worth stating up front: the benign figures are a census with no sampling error, while the attack figures are a prefix of a larger population. They are not symmetric estimates, and the benign number is the more trustworthy of the two.

---

### 2.6 §6.1 Logged-trace replay

**原文 Table 1** 保留不动（它是 v0.3 冻结梯级，必须保留以支撑 §6.1 与 §10 的因果论证）。在其后**新增** Table 1b 与结果段：

> #### 6.1.1 Adding authorization semantics (v0.4.1)
>
> The rungs above leave 41.2% benign trace blocking, which is the cost of the all-untrusted policy. The v0.4.1 configuration asks whether operator authorization can reduce that cost without giving up the provenance mechanism. Table 1b reports the full ladder including the v0.4.1 rungs.
>
> | Configuration | Attack-labelled trace BLOCK | Benign trace BLOCK |
> |---|---:|---:|
> | `local_only` (single-event gate) | 0.0% | 1.03% |
> | + untrusted output inspection | 3.5% | 19.59% |
> | + entity provenance / taint (v0.3) | 16.0% | 41.24% |
> | + intent consistency | 16.0% | 41.24% |
> | **+ safe authorisation (v0.4.1)** | **3.5%** | **28.87%** |
> | + structured intent slots | 3.5% | 28.87% |
>
> Table 1b. Full ladder including the v0.4.1 rungs, reported as point estimates. The first four rows are the frozen v0.3.1-research ladder, reproduced unchanged for comparability; their cluster-bootstrap confidence intervals appear in Table 1 and are not repeated here.
>
> **On confidence intervals.** The v0.4.1 rows carry no interval, and this is a limitation rather than an omission to be papered over: the frozen `v0_4_trust_pareto.json` records point estimates only, and its `results` records contain no variance field, so an interval computed for v0.4.1 would have to come from a bootstrap run that was not part of the frozen artifact. We therefore report the point estimates and state their absence, and we do not transplant the v0.3 intervals onto the v0.4.1 rows. Regenerating intervals for v0.4.1 requires re-running the ladder with a bootstrap wrapper, which is a separate measurement, not a re-reading of the committed artifact.
>
> Two observations. First, benign trace blocking falls from 41.24% to 28.87%, a 12.37-point reduction, which is the intended benefit. Second, the raw blocking rate on attack-labelled trajectories also falls, from 16.0% to 3.5%. This second movement must not be described as the removal of false positives; the reason is stated in the limitations bullet on attack labels versus attack outcomes (Section 8).
>
> An action-level audit of the trajectories v0.3 blocked shows how the release decomposes. Of the 64 attack-labelled trajectories blocked by the v0.3 provenance rung, 36 ended in a final governed action concordant with explicit operator authorization, 14 ended in a read-only call that cannot act on the tainted value, and 14 were neither. This is an action-level statement about the final governance point; it is not a statement that those 50 trajectories were benign, and it is not a statement that the attacks failed.
>
> `plus_intent_slots` produces numbers identical to `plus_trust_policy_v0_4` on this corpus. Prose authorization matching and structured-slot authorization agree wherever an operator request names both the action family and the entity exactly, which is the case for the authorization-concordant trajectories this corpus contains. We therefore do not claim the slot mechanism improves over prose matching here; we report only that it does not regress, and that the corpus cannot separate the two.

---

### 2.7 §6.2 Paired source/context control

**原文**（Table 2 后第二段）：

> Three pairs exhibit different decisions under context-aware processing, including two complete BLOCK-versus-ALLOW separations. The upload pair remains blocked in both conditions because the current policy treats exporting a customer file to an external destination as high risk even when explicitly authorized. This negative pair is useful: it shows that provenance does not automatically override content-level safety rules.

**替换为**：

> Three pairs exhibit different decisions under context-aware processing, including two complete BLOCK-versus-ALLOW separations. The upload pair remains blocked in both conditions because the current policy treats exporting a customer file to an external destination as high risk even when explicitly authorized. This negative pair is useful, and in v0.4.1 it is no longer incidental but required: sensitive material crossing the trust boundary is classified unsuppressible, so authorization structurally cannot lower that decision. The pair is therefore a direct behavioural witness of the invariant in Section 7.5, showing that provenance does not automatically override content-level safety rules.

---

### 2.8 §7 Discussion — 新增 §7.5

**原文 §7.3** 末句需微调（见 §3 节口径修正表），并**新增 §7.5**：

> #### 7.5 An authorization safety invariant for risk aggregation
>
> The most consequential defect found in v0.4 was not a missing feature but an aggregation error. Authorization was implemented as a single ceiling applied to the combined risk score:
>
> ```text
> peak = max(all components, all signals)
> if authorized: peak = min(peak, AUTHORISED_ACTION_CEILING)
> ```
>
> Because the cap was applied after aggregation, it bound *every* component, including structural risk that authorization has no bearing on. An authorized bulk delete therefore left the gate at the ceiling value rather than at its true structural severity. The natural test to write for that code — "an authorized action scores at the ceiling" — is precisely a pinned-down vulnerability, and it was in fact written.
>
> The fix is to split the aggregate into two bands that authorization cannot bridge:
>
> ```text
> hard_peak    = max(structural components, unsuppressible signals)
> soft_peak    = max(suppressible provenance signals)
> if authorized: soft_peak = min(soft_peak, AUTHORISED_ACTION_CEILING)
> score        = max(hard_peak, soft_peak)
> ```
>
> Structural components (`local_risk`, `inherited_risk`, `path_risk`, `downstream_exposure`) and the unsuppressible signal classes never enter the capped path. The invariant this establishes is the paper's central design contribution in this release:
>
> > **Authorization may explain provenance-derived suspicion, but it cannot authorize away independently dangerous behavior.**
>
> The invariant is behavioural, not architectural: it is pinned by a test suite in which an authorized bulk delete remains blocked, an authorized action carrying untrusted content is reviewed rather than blocked, an authorized action whose destination arrived untrusted is bounded by the ceiling, inherited risk is unaffected, intervention value is unaffected, and an unknown future signal type fails closed as unsuppressible.
>
> Two design decisions are worth stating explicitly because both cut against the headline number. First, trusted-entity resolution is deliberately **evidence-only** in this release: it is recorded in the audit chain but carries no ceiling. Giving it a prior-based ceiling in the same change would have moved two variables at once and made the ablation uninterpretable; the intended ladder is v0.4.1a authorization-only, then v0.4.1b + trusted resolution. Second, the ceilings were not retuned after the fix, even though retuning would have recovered part of the benign reduction visible in Table 1b. Retuning to recover a number is benchmark fitting.
>
> The general lesson generalizes beyond this system: any risk aggregate that mixes "who asked" with "what is asked" needs a stated policy for which of the two authorization is allowed to move. Leaving it implicit produces a bypass that looks like a feature.

---

### 2.9 §8 Limitations — 改两条、增两条

**原文第三条**：

> - The all-untrusted trust policy is intentionally conservative and likely overestimates false positives relative to a system with reliable source semantics. Conversely, it avoids an invalid evaluation shortcut in which trust is inferred from whether the content is malicious.

**替换为**：

> - The all-untrusted trust policy is intentionally conservative and likely overestimates false positives relative to a system with reliable source semantics. Conversely, it avoids an invalid evaluation shortcut in which trust is inferred from whether the content is malicious. The v0.4.1 rungs use a tool-semantics trust prior rather than the binary policy, but that prior participates only in an evidence-only signal in this release; the benign reduction it produces is therefore attributable to authorization semantics, not to trust-prior tuning.

**原文第二条**：

> - The main attack subset uses the first 400 attack trajectories after the audited grouping procedure, while all 97 benign trajectories are included. This is reproducible but is not a random population sample of all possible agent behavior.

**替换为**：

> - The main attack subset uses the first 400 attack trajectories after the audited grouping procedure, while all 97 benign trajectories are included. This is reproducible but is not a random population sample of all possible agent behavior. The benign figure is therefore a census and the attack figure a prefix, and the two are not symmetric estimates; where they are compared directly, the benign figure is the more trustworthy.

**新增两条**：

> - **Attack labels are not attack outcomes.** The dataset labels trajectories as attack or benign. Our gate decides at a final governance point using runtime-observable authorization evidence. Neither is a measurement of attack success: offline replay has no official grader, no attack-success rate, no task-level outcome and no utility measure. A release decision that is defenseable at the action level is not thereby evidence that an attack failed, and the paper makes no such inference anywhere.
>
> - **Authorization is a weak authorization signal.** Matching an operator request against a tool call establishes that the operator named this action family and this entity; it does not establish informed consent, authority, or absence of coercion. A manipulated agent whose final call happens to be authorization-concordant is authorized in our operational sense only. This is a further reason the action-level audit cannot be read as an attack-outcome measurement.

---

### 2.10 §9 Reproducibility and Release Discipline — 重写

**原文**：

> The results in this manuscript correspond to the annotated release tag v0.3.1-research. The release retains an explicit evaluation contract, committed result artifacts, a prediction-invariance audit, and CI gates for Python 3.11 and 3.12, linting, type checking, benchmark smoke tests, and Docker startup. Earlier figures produced by leaky or inconsistent harnesses are marked as withdrawn in the repository and are not used here. This release discipline is important because the project itself uncovered multiple evaluation failures during development, including label-derived fields, ground-truth values entering the engine, stale artifacts, and an invalid label-shuffling leakage diagnostic.

**替换为**：

> The results in this manuscript correspond to the annotated release tag `v0.4.1-research`. Research logic is frozen at revision `49127cdef723db1e8db67d3d438a18f3e74a1853`; reproducibility tooling — a canonical-artifact verifier, a dataset fingerprint script, and their tests — was added by `83dddd7d6c62946db0244b3382c0cb3fa60307b2`. Later documentation-only commits do not change the experiment, and the moving branch HEAD is not an experiment identifier.
>
> The main artifact is `benchmark/results/v0_4_trust_pareto.json`, SHA-256 `3e33c72d230cb7e0788dc4412574054c19dfd496546573698d73bff7b6a90565`. The evaluated dump is fingerprinted as a manifest over its Arrow files, with digest `948b94325ae1c8cfbe41bd205fee46b0f500215559ef5cd97a25c27fcf580049` over 1 file, 50,898,680 bytes, 13,913 rows and 10,536 constructed trajectories. A reproduction is valid only when both hashes match: the same script run against a different dump version is not a reproduction.
>
> Reproduction is a two-command procedure. First, regenerate into a file distinct from the canonical artifact:
>
> ```bash
> python benchmark/v04_trust_replay.py --mode audit --max-trajectories 400 \
>   --out benchmark/results/v0_4_trust_pareto.reproduced.json
> ```
>
> Then compare mechanically, with no tolerance and no "close enough" mode:
>
> ```bash
> python scripts/verify_v04_reproduction.py \
>   benchmark/results/v0_4_trust_pareto.json \
>   benchmark/results/v0_4_trust_pareto.reproduced.json
> ```
>
> The verifier compares experiment identity, dataset audit counts, ladder order, result order, and every per-configuration rate plus derived deltas, exiting 0 on exact agreement, 1 with a per-field difference list on any mismatch, and 2 when the comparison cannot be attempted. It fails closed when `AGENTSHIELD_ENABLE_CORPUS_MARKERS` is enabled, because corpus-specific markers change scoring and the canonical run had them disabled. In this release, three independent runs — the committed artifact and two fresh reproductions — produced byte-identical output.
>
> **What CI does and does not verify.** GitHub Actions verifies code integrity, tests, linting, type checking, benchmark smoke execution and Docker health on Python 3.11 and 3.12. It does not independently regenerate the 497-trajectory logged-trace artifact, because that run depends on the locally staged external dump. A green badge is therefore not a reproduction of the 3.5% / 28.9% figures; the verification that matters for those numbers is the manual deterministic procedure above. Lint scope is likewise stated precisely: the two commands CI runs, `ruff check backend/` and `ruff check benchmark/ benchmark/independent_eval/ scripts/`, both pass, while a whole-repository `ruff check .` reports 123 pre-existing findings in directories CI does not lint.
>
> Earlier figures produced by leaky or inconsistent harnesses are marked as withdrawn in the repository and are not used here. This release discipline is important because the project itself uncovered multiple evaluation failures during development, including label-derived fields, ground-truth values entering the engine, stale artifacts, and an invalid label-shuffling leakage diagnostic.

---

### 2.11 §10 Conclusion

**原文**：

> In logged traces, a current-call-only gate blocks none of the sampled attack trajectories; prior-output inspection raises blocking to 3.5%, and entity provenance raises it to 16.0%. The same additions sharply increase benign blocking, making the unresolved safety-utility trade-off explicit. Together with the paired source/context control and metadata-invariance audit, the results support provenance as a useful runtime security signal while rejecting stronger claims that the current prototype solves indirect prompt injection. The next research step is not further threshold tuning, but reliable trust attribution and instruction-data separation grounded in runtime source semantics.

**替换为**：

> In logged traces, a current-call-only gate blocks none of the sampled attack trajectories; prior-output inspection raises blocking to 3.5%, and entity provenance raises it to 16.0%. The same additions sharply increase benign blocking, making the unresolved safety-utility trade-off explicit.
>
> This release then shows that part of that trade-off was an aggregation error rather than an intrinsic cost. Separating provenance suspicion from structural danger, and permitting authorization to temper only the former, reduces benign trace blocking to 28.9% while keeping the authorization safety invariant that an authorized bulk delete remains blocked. The measured cost of the correction is reported rather than tuned away, and no threshold, weight, marker or sampling rule was adjusted to recover it.
>
> Together with the paired source/context control and metadata-invariance audit, the results support provenance as a useful runtime security signal while rejecting stronger claims that the current prototype solves indirect prompt injection. The next research step is not further threshold tuning, but reliable trust attribution and instruction-data separation grounded in runtime source semantics — with the explicit recognition that trajectory-level attack labels, runtime action authorization, and actual attack success are three distinct levels, and that offline replay measures only the first two.

---

## 3. 口径修正表（旧稿中已过强的表述）

旧稿有三处措辞在 v0.4.1 之后不再准确，**必须**改，否则会退回到已修正的过度声明：

| 位置 | 旧表述 | 问题 | 替换为 |
|---|---|---|---|
| §7.3 标题与首句 | "The 41.2% benign trace-block rate exposes the primary research problem." | 41.2% 是 v0.3 配置的历史值，不再是当前系统值 | "The 41.2% benign trace-block rate of the v0.3 configuration exposed the primary research problem; v0.4.1 reduces it to 28.9% by correcting authorization semantics rather than by trust-prior tuning, which leaves the residual 28.9% as the open figure." |
| §7.3 末段 | "These approaches should be frozen before benchmark evaluation to avoid benchmark-informed feature engineering." | 仍正确，保留 | 保留不动 |
| §8（新增条） | 无 | — | 见 §2.9 新增两条 |
| §6.6 附注 | 若引用 benign 41.2% 作为"当前" | 同 §7.3 | 加 "(under the v0.3 all-untrusted configuration; v0.4.1 reports 28.9%)" |

**全文禁止出现的词**（旧稿未用，但改稿时不得引入）：

```text
false positive / false negative      (as a metric derived from this harness)
attack prevented / attack failed
0 missed attacks
78% false positives
```

替代说法统一为：*"not independently actionable at the final governance point under our action-level audit"*。

---

## 4. 可直接粘贴的 LaTeX / BibTeX 片段

若投稿系统需要 LaTeX，以下为最小片段。

### 4.1 表 1b

```latex
\begin{table}[t]
\centering
\caption{Full additive ladder including the v0.4.1 authorization rungs. The
first four rows are the frozen v0.3.1-research ladder, reproduced unchanged for
comparability. Attack rows are trace-block rates over a 400-trajectory prefix;
benign rows are over all 97 benign trajectories. Point estimates only: the
frozen artifact carries no variance field, so no intervals are reported for the
v0.4.1 rows rather than transplanting the v0.3 intervals onto them.}
\label{tab:ladder-v041}
\begin{tabular}{lcc}
\toprule
Configuration & Attack-labelled trace BLOCK & Benign trace BLOCK \\
\midrule
local\_only (single-event gate)      & 0.0\%  & 1.03\% \\
+ untrusted output inspection        & 3.5\%  & 19.59\% \\
+ entity provenance / taint (v0.3)   & 16.0\% & 41.24\% \\
+ intent consistency                 & 16.0\% & 41.24\% \\
\textbf{+ safe authorisation (v0.4.1)} & \textbf{3.5\%} & \textbf{28.87\%} \\
+ structured intent slots            & 3.5\%  & 28.87\% \\
\bottomrule
\end{tabular}
\end{table}
```

### 4.2 不变量的形式化表述

```latex
\begin{definition}[Authorization safety invariant]
Let $H$ denote the set of structural risk components ($l(v)$, inherited, path and
downstream exposure) and $\mathcal{U}$ the set of signals whose danger holds
independently of the requester. Let $\mathcal{P}$ denote the set of
provenance-suspicion signals, and let $a \in \{0,1\}$ indicate explicit operator
authorization. An aggregate $S$ satisfies the invariant iff
\[
S(H \cup \mathcal{U} \cup \mathcal{P}, a)
  \;=\; \max\Big(
        \max(H \cup \mathcal{U}),\;
        \min\big(\max(\mathcal{P}),\; \tau(a)\big)
      \Big),
\]
where $\tau(0)=1$ and $\tau(1)=\texttt{AUTHORISED\_ACTION\_CEILING}<1$.
Authorization modulates only the second argument of the outer $\max$.
\end{definition}
```

### 4.3 复现性段落（紧凑版）

```latex
The main artifact is \texttt{v0\_4\_trust\_pareto.json}
(SHA-256 \texttt{3e33c72d\ldots b6a90565}); the evaluated dump is fingerprinted
as \texttt{948b9432\ldots 580049} over 1 Arrow file, 50{,}898{,}680 bytes,
13{,}913 rows and 10{,}536 trajectories. Reproduction is
\texttt{v04\_trust\_replay.py --mode audit --max-trajectories 400} followed by
\texttt{scripts/verify\_v04\_reproduction.py}, which compares both artifacts
exactly and exits non-zero on any difference. Three independent runs produced
byte-identical output. GitHub Actions verifies code health only; it does not
regenerate the 497-trajectory artifact, which depends on the locally staged
external dump.
```

---

## 5. 投稿前自查清单

- [ ] 全文 `v0.3.1-research` 已全部替换为 `v0.4.1-research`（含页脚 7 处）
- [ ] Table 1 保留原样，未与 Table 1b 合并
- [ ] Table 1b 的攻击行注明为 400 前缀、良性行注明为 97 普查
- [ ] §2.3 贡献列表改为 5 项，新增项指向 §7.5
- [ ] §2.8 新增 §7.5 完整保留"不变量的两处反数字设计决定"（evidence-only + 不重调 ceiling）
- [ ]全文无 `false positive` / `attack failed` / `0 missed attacks` 派生指标
- [ ] §2.9 新增两条 limitation 均已写入
- [ ] §2.10 两个 hash、两个 SHA、两条命令均已写入且与仓库一致
- [ ] Abstract 中 v0.4.1 句紧随"三层不可推导"限定
- [ ] §6.1.1 明确写出 64/36/14/14 的动作级审计，并声明不得解读为攻击失败

---

## 6. 引用的仓库内权威来源

改稿中有争议时，以这些文件为准（均已随 `v0.4.1-research` 冻结）：

| 问题 | 权威来源 |
|---|---|
| 结果数字与 sampling | `benchmark/results/v0_4_trust_pareto.json` |
| 采样协议与数据集来源 | `docs/research/REPRODUCIBILITY.md` §3–§5 |
| fingerprint 与 hash | `docs/research/REPRODUCIBILITY.md` §4 |
| 复现与校验命令 | `docs/research/REPRODUCIBILITY.md` §6–§7 |
| 解释边界与三层分离 | `docs/research/REPRODUCIBILITY.md` §10 |
| 64/36/14/14 审计 | `docs/research/BENCHMARK_STATUS.md`，Second pass 一节 |
| 授权不变量与测试 | `backend/app/shield/risk_signals.py`，`backend/tests/test_trust_policy.py` |
| CI job 列表 | GitHub Actions run `36094171370`（六项全绿） |
