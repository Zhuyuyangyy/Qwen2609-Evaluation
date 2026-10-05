# AgentShield: Closing the Observability Gap in Tool-Using LLM Agents with Provenance-Aware Runtime Governance

Anonymous Authors

Manuscript based on the frozen v0.4.1-research artifact

> **Status note.** This is the submission-ready English manuscript corresponding to
> annotated tag `v0.4.1-research` (commit `9c9ee6f1929cd68b7fb0b7b1a6e3b3b55605d493`).
> Research logic is frozen at `49127cdef723db1e8db67d3d438a18f3e74a1853`. Sections
> marked *[unchanged from v0.3.1]* are carried over verbatim; the remainder have been
> revised for the v0.4.1 evidence. The chapter-by-chapter rationale lives in
> `docs/research/PAPER_UPDATE_v041.md`.

---

## Abstract

Tool-using large language model (LLM) agents increasingly act on information obtained from external tools, files, web pages, and other agents. This creates an observability problem for runtime guardrails: the decisive malicious instruction may occur in an earlier tool output, while the eventual tool call is locally ordinary. We study this gap and present AgentShield, a provenance-aware runtime governance prototype that records tool outputs as typed artifacts, tracks the first origin of entities such as destinations and file paths, propagates risk across a behavior graph, and gates each tool call with ALLOW, HUMAN_REVIEW, or BLOCK. The evaluation is deliberately separated from grading metadata by an explicit evaluation contract and a prediction-invariance test over 3,360 metadata permutations, under which no prediction changes. On an AgentDojo-derived logged-trace replay containing all 97 benign trajectories and 400 attack trajectories, a current-call-only gate blocks 0% of attack trajectories. Inspecting untrusted prior tool output raises the attack block rate to 3.5%, and adding entity provenance raises it to 16.0%. The same progression increases benign trace blocking from 1.0% to 19.6% and 41.2%, respectively, exposing a substantial safety-utility trade-off rather than hiding it.

We then show that this trade-off is not intrinsic to provenance but partly an artifact of how suspicion is aggregated. When operator authorization is allowed to temper only provenance-derived alarms and is structurally prevented from pardoning independently dangerous behavior, benign trace blocking falls to 28.9% while the raw blocking rate on attack-labelled trajectories falls to 3.5%. An action-level audit finds that the released final calls are predominantly authorization-concordant or read-only; offline replay cannot determine whether the underlying attacks would still succeed. A paired counterfactual test further shows that identical final tool calls can receive different decisions when their source context differs. However, a frozen string-based instruction detector achieves 0/9 recall on differently phrased held-out injections, and corpus-specific markers remain disabled by default. These results support provenance as a useful missing runtime signal while identifying trust attribution and instruction-data separation as the primary unresolved problems.

**Keywords:** LLM agents; prompt injection; provenance; taint tracking; runtime governance; behavior graphs; agent security; authorization semantics

---

## 1. Introduction

LLM agents differ from chat systems in a security-critical way: they do not merely generate text, but select tools and cause side effects. An agent can read a calendar, inspect a document, query a database, call an API, transfer funds, send an email, or delete a file. At the same time, many of the inputs an agent consumes are not authored by the operator. They arrive through tool responses, web pages, retrieved documents, email bodies, or other agents. Indirect prompt injection exploits exactly this boundary by placing adversarial instructions in data that later becomes part of the model context [1–3].

Most runtime guardrails are naturally attached to the point where an agent is about to execute a tool. This is attractive because the enforcement point is concrete: inspect the tool name and arguments, estimate risk, then allow, review, or block. Yet this placement can create a structural observability gap. Suppose the operator asks an agent to summarize a document. The document contains an injected instruction to send a copy to an attacker-controlled address. When the model later calls `send_email`, the current call may contain a syntactically ordinary recipient and subject. The information that makes the call suspicious is not necessarily present in the call itself; it is the fact that the recipient was introduced by an untrusted artifact rather than by the operator.

This paper asks a narrower question than end-to-end prompt-injection defense: can runtime governance improve by tracking the provenance of values that flow from prior observations into later actions? AgentShield is a research prototype designed to study that question. It turns observed tool outputs into first-class artifacts, extracts entities from those artifacts, records the first origin and trust level of each entity, links tool calls in a behavior graph, and computes deterministic provenance signals before each side-effecting call.

Our contribution is not a claim of solved prompt injection. The frozen evaluation shows the opposite. Provenance materially increases attack interception in logged traces, but under a deliberately conservative all-untrusted trust policy it also increases benign blocking. Moreover, a string-marker instruction detector fails completely on a small set of differently phrased held-out attacks. We therefore frame AgentShield as evidence for a missing signal and as an instrument for measuring the trade-off, not as a complete defense.

The v0.4.1 configuration reported here is a *correctness* release rather than a performance release. It changes how authorization interacts with risk aggregation, and the measured cost of that change is reported rather than optimized away. No threshold, weight, marker, or sampling rule was retuned to recover any number.

The paper makes five contributions:

- A runtime formulation of the observability gap: a tool call can be locally benign-looking even when its arguments originate in adversarial earlier context.

- A provenance-aware governance mechanism that records content artifacts, tracks entity origin and taint, propagates risk through a behavior graph, and applies a two-pass decision after propagation.

- **An authorization safety invariant for risk aggregation** (Section 7.5): operator authorization may explain provenance-derived suspicion, but it cannot authorize away independently dangerous behavior. We show that the natural implementation — a single cap on the combined score — is an authorization bypass in which an authorized bulk delete is scored as a benign action, and we give a band-split formulation that closes it.

- An evaluation contract that physically separates runtime-observable inputs from evaluation-only metadata, together with a prediction-invariance test over 3,360 metadata perturbations.

- An evaluation that reports both the detection gain and its benign cost, including negative generalization results and explicit non-measurement of attack success rate, benign utility, and task success.

---

## 2. Related Work

**[unchanged from v0.3.1 except as marked: §2.2 and §2.3 revised and §2.4–§2.7 added in v0.4.1]**

### 2.1 Indirect prompt injection in tool-integrated agents

InjecAgent demonstrates that indirect prompt injection can manipulate tool-integrated agents through externally supplied content, and evaluates a large collection of injected agent tasks [1]. AgentDojo provides a dynamic environment for evaluating attacks and defenses in tool-using agents and makes explicit that untrusted tool outputs can carry instructions that conflict with the operator intent [2]. These benchmarks motivate the threat model studied here: dangerous behavior may emerge only after the model has consumed earlier external content.

Subsequent work broadened the attack surface in directions our replay does not model. ToolHijacker poisons the tool document itself rather than a tool *response*, manipulating tool selection [7]. Automated optimization-based attackers inject adversarial suffixes learned by reinforcement learning and transfer them to models fine-tuned for injection resistance [21]. Role confusion offers a mechanistic account, showing that injected text occupies the same representational space as the role it imitates [17]. These results bound the scope of our contribution: we study the runtime governance point, not the model's internal role perception, and our measurements are taken against the frozen dump rather than against adaptive attackers.

### 2.2 Input separation and provenance-aware defenses

StruQ separates instructions from data through structured queries and trains models to follow only the instruction channel [3]. Spotlighting similarly emphasizes source separation by transforming untrusted inputs so that the model can distinguish them from trusted instructions [4]. AgentShield is complementary: rather than changing the model input format or training objective, it operates at runtime after observations have already entered the session. It asks whether arguments to a proposed action can be traced to untrusted content and whether they are consistent with the operator request.

The same separation idea has been pursued architecturally. An f-secure LLM system disaggregates the pipeline and filters untrusted input out of the planning process, with formal models of the resulting guarantees [6]. IPIGuard decouples action planning from interaction with external data by traversing a planned tool dependency graph [8]. SPA adopts a plan-first design and applies dual-lattice information-flow control across explicit data and control dependencies, extending the threat model to cross-query state reuse [12]. These are structural redesigns of the agent. AgentShield instead accepts the agent as given and adds a governance point in front of the tool boundary, which is why it can be evaluated on logged traces produced without it.

### 2.3 Agent harmfulness and runtime governance

AgentHarm broadens evaluation from chatbot refusals to multi-step harmful agent behavior [5]. Its focus is malicious task completion under jailbreaks rather than indirect prompt injection, but it underscores why agent safety cannot be reduced to response classification. AgentShield instead studies a runtime control point before tool execution. It does not claim AgentHarm benchmark performance; the repository contains only a metadata-derived proxy, which is excluded from the main evidence in this paper.

Several recent systems share our enforcement point. ClawGuard derives task-specific access constraints from the user's stated objective and enforces a user-confirmed rule set at every tool-call boundary [15]; AgentWatcher attributes an agent action to causally influential context segments and reasons over explicit rules, trading attribution cost for explainability [16]; AttriGuard verifies a proposed tool call by counterfactual re-execution under an attenuated view of external observations [9]. All three are closer to our setting than model-side defenses, and all three require either a monitor model or a re-execution. AgentShield's distinguishing commitment is deterministicity: the provenance signals in Section 4.3 are computed without any model call, which is what makes the prediction-invariance audit in Section 5.1 decidable and the latency in Section 6.5 free of model time.

### 2.4 Information flow control and taint tracking for agents

**[new in v0.4.1]** Classical taint analysis assumes propagation through program memory, an assumption that breaks when propagation is governed by probabilistic language reasoning; NeuroTaint makes this argument explicitly and reconstructs provenance offline from untrusted sources to privileged sinks using semantic and causal evidence rather than exact string matching [10]. Our taint propagation signal is deliberately the weaker, string-based variant — it is what a deterministic, model-free gate can compute — and NeuroTaint's TaintBench results are best read as the upper bound that a semantic tracker could reach on traces like ours. FLOWSEAL grounds confidentiality enforcement in data provenance and an information-flow-control lattice with controlled declassification, and shows that enforcement living inside the LLM context coincides with the attack surface [14]; APPA argues that monotone taint tracking either over-blocks benign work or strands execution, and adds policy-governed recovery [11]. GIF provides a locally sound geometric bound on information flow with a mechanized proof, addressing the taint-explosion problem directly [13].

These works converge on the diagnosis that motivated v0.4.1: the difficulty is not producing a taint label but deciding what to *do* with it when the label conflicts with an action the operator asked for. That is an aggregation question, and Section 7.5 treats it as one.

### 2.5 Governance before the tool boundary

**[new in v0.4.1]** STPA-derived safety requirements formalized as enforceable specifications on data flows and tool sequences move agent safety toward proactive guardrails with stated guarantees rather than reliability fixes [18]. AgentRaft defines data over-exposure as transmitting sensitive data beyond user intent and functional necessity, detecting it with runtime taint tracking over a cross-tool call graph [19]. ToolMinimize goes further and *rewrites* tool arguments to the minimum data necessary, a capability a gate that only returns ALLOW, REVIEW or BLOCK does not have [23].

AgentShield occupies a specific position in this space: it neither rewrites arguments nor re-executes the agent. It decides a ternary action at the boundary from deterministic evidence, and it treats the boundary's *aggregation policy* as a first-class design object with its own invariant.

### 2.6 Automated attacks and benchmark sensitivity

**[new in v0.4.1]** Maatphor generates prompt-injection variants automatically so that candidate defenses are tested against more than the single successful payload that motivated them [20]. This is the methodological reason our held-out evaluation in Section 6.4 exists, and it is also why we report it as a failure: a detector tuned on the benchmark's own phrasing does not survive variant generation.

The same pattern has been observed outside agent benchmarks: cybersecurity tooling built on LLMs was turned against itself by prompt injection in a way explicitly compared to cross-site scripting, with mitigations layered at the tool boundary rather than in the model [22]. We cite it as convergent evidence that the boundary is the right enforcement point, and as a caution that a boundary rule which is not deterministic is itself part of the attack surface.

### 2.7 Positioning

**[new in v0.4.1]** The closest neighbors to AgentShield are the runtime, deterministic gate [15, 16] and the offline provenance reconstruction [10]. AgentShield differs from the former in requiring no monitor model, and from the latter in operating online at the decision point rather than as a post-hoc audit. Its contribution relative to both is the safety invariant of Section 7.5, which is a statement about how *any* such gate should aggregate authorization evidence against structural risk.

---

## 3. Threat Model and Problem Formulation

**[unchanged from v0.3.1]**

We consider an LLM agent that receives an operator request and then alternates between model reasoning and external tool calls. Tool outputs may contain data controlled by external parties. The adversary can place text in such an output but does not directly modify the runtime gate, the operator request, or the evaluation labels. The target is a downstream high-consequence call such as sending data to an external destination, deleting a resource, or invoking a privileged tool.

A single-event gate observes the current event e_t = (tool_t, args_t) and decides d_t ∈ {ALLOW, HUMAN_REVIEW, BLOCK}. The central limitation is that two executions can present the same current event while differing in the origin of an argument. Let origin(x) denote the earliest observed source of entity x. If x first appears in an untrusted tool output in the attack execution but in the operator request or trusted context in the benign execution, a gate restricted to e_t cannot distinguish the pair. A provenance-aware gate augments the observation with session history H_<t and origin information P_t, producing d_t = G(e_t, H_<t, P_t).

We do not assume that all untrusted content is malicious. In fact, this distinction is the main unresolved problem. The conservative evaluation policy treats recorded external tool outputs as untrusted, which prevents label-derived trust assignment but necessarily creates false positives when ordinary retrieved content legitimately influences an action.

*Figure 1. The observability gap. The final tool call may look ordinary; the security-relevant distinction is the provenance of arguments introduced by earlier content.*

---

## 4. AgentShield Design

### 4.1 Observed content artifacts

**[unchanged from v0.3.1]**

Every runtime-observed content object is represented as an ObservedContentArtifact with a session identifier, source event, origin type, trust level, content hash, and extracted entities. Entity extraction targets values whose origin is operationally meaningful, including email addresses, URLs, hosts, paths, and command fragments. The artifact abstraction turns prior context from an opaque text buffer into an auditable runtime object.

### 4.2 Entity origin and taint tracking

**[unchanged from v0.3.1]**

The TaintTracker records the first observed origin of each normalized entity and the set of artifacts in which it later appears. For an entity x, the tracker stores origin(x) = (artifact_id, trust_level, origin_type, first_seen). A downstream tool call can therefore ask whether a destination in its arguments was first introduced by untrusted content. The implementation is intentionally deterministic and does not read evaluation metadata.

### 4.3 Provenance risk signals

AgentShield combines ordinary local risk signals with provenance signals. The latter include: (i) untrusted content that appears instruction-like; (ii) a destination first observed in untrusted content; (iii) an origin mismatch in which a tainted value is absent from the operator request; (iv) sensitive material flowing to an external sink; (v) untrusted content preceding a privileged action; and (vi) taint propagation when an entity introduced by an untrusted artifact reaches the current call. The signals are intended as interpretable evidence rather than learned latent features.

**Signal classification.** Each signal type is assigned to exactly one of three disjoint sets, defined statically after the signal-type enumeration. `UNSUPPRESSIBLE_SIGNALS` contains the structural and manipulation classes: privilege change, audit tamper, bulk operation, credential access, policy evasion, untrusted instruction, untrusted-to-privileged action, sensitive-to-external flow, and cross-agent delegation. `SUPPRESSIBLE_PROVENANCE_SIGNALS` contains the alarms whose entire content is *provenance suspicion*: destination provenance, intent-origin mismatch, and taint propagation. `SUPPRESSION_EVIDENCE_SIGNALS` contains authorization and trusted-entity resolution, which are evidence rather than risk. A signal type not explicitly classified is treated as unsuppressible, so a future signal added without thought cannot silently become suppressible.

Two remarks on this taxonomy. First, taint propagation and cross-agent delegation are deliberately distinct types: the former is a propagation fact about an entity, the latter a structural relationship between agents. Conflating them would mean that tempering taint tacitly tempers genuine delegation risk. Second, suppression-evidence signals carry score 0.0 by construction; an observation that a call was authorized or that an entity resolved through a trusted store must not be able to manufacture risk on its own.

### 4.4 Behavior graph and risk propagation

**[unchanged from v0.3.1]**

Each tool call becomes a node in a session behavior graph, and edges represent relations such as calls, invocations, or data flow. Let l(v) be the local node risk and w(u,v) the transfer coefficient on an incoming edge. The propagated total risk is computed as:

R(v) = max( l(v), max_{(u,v)∈E} R(u) · w(u,v) ).

The current implementation uses type-specific transfer weights (for example, 0.7 for call/invocation edges and 1.0 for data-flow edges). Risk lives on nodes; edge weights represent transfer only. This avoids a previous failure mode in which upstream risk was encoded both in the node and the edge, effectively squaring risk during propagation.

### 4.5 Two-pass governance

**[unchanged from v0.3.1]**

Governance is performed after the current node has been inserted into the graph. First, the engine computes local and provenance signals. Second, it inserts the call at local risk and creates its parent edge. Third, it propagates risk through the graph. Finally, the propagated state is used to choose ALLOW, HUMAN_REVIEW, or BLOCK, and the governed result is written back to the node. This ordering matters: deciding before propagation would make graph awareness observational only rather than decision-relevant.

### 4.6 Risk aggregation across the two bands

**[new in v0.4.1]**

The final score is the maximum of two bands, and only one of them is reachable by authorization. Let H denote the structural components — local, inherited, path and downstream exposure — and let U and P denote the unsuppressible and suppressible signal classes of Section 4.3. With a ∈ {0,1} indicating explicit operator authorization and τ(0) = 1, τ(1) = AUTHORISED_ACTION_CEILING, the aggregate is

S(H, U, P, a) = max( max(H ∪ U), min( max(P), τ(a) ) ).

Structural components and unsuppressible signals never enter the capped path. Counterfactual and intervention values are also outside it: they measure the value of stopping here, not who asked, so an intervention value above both bands raises the score rather than being pardoned by it. Section 7.5 states the invariant this enforces and reports the defect it replaced.

### 4.7 Auditing and counterfactual support

**[renumbered from v0.3.1 §4.6; content unchanged]**

Decisions retain references to the artifacts and risk signals that contributed to them, enabling an evidence chain from a blocked sink back to the content that introduced a suspicious value. The engine also contains counterfactual support for estimating how earlier intervention could alter downstream risk; we treat this as an audit mechanism rather than an evaluated causal guarantee in the present paper.

---

## 5. Evaluation Methodology

### 5.1 Evaluation contract and leakage isolation

**[unchanged from v0.3.1]**

The benchmark harness separates fields into runtime-observable, runtime-derived, and evaluation-only classes. Labels, expected actions, expected risk scores, attack names, injection goals, fixture chain identifiers, rationales, and fields derived from these are forbidden from detector input. Adapters construct runtime observations before prediction; labels are consulted only afterward for scoring. To test this boundary, the frozen release permutes evaluation-only metadata while holding runtime observations fixed. Across seven methods, 60 cases, and eight perturbations per case (3,360 prediction checks), no prediction changes.

### 5.2 Logged-trace replay

The main external experiment replays recorded tool-call and tool-response triples from the ffuuugor/agentdojo-dump dataset. We use all 97 benign trajectories (339 steps) and the first 400 attack trajectories, for 497 trajectories total. The replay is an offline interception experiment: it does not rerun an agent, invoke an LLM, or measure what the agent would do after a block. All recorded tool responses are assigned untrusted status independently of their labels or contents. This conservative policy prevents trust leakage but is expected to increase false positives.

Six configurations form an additive ladder. The first four are the frozen v0.3 rungs: `local_only` sees only the current call; `plus_output_inspection` enables reactions to previously observed untrusted content without per-entity taint; `plus_entity_provenance` tracks entity origin and taint; `plus_intent_consistency` additionally checks against the operator request. The last two are v0.4.1: `plus_trust_policy_v0_4` adds tool-semantics trust classification and prose-authorization matching with the band-split aggregation of Section 4.6; `plus_intent_slots` replaces prose matching with authorization decided against structured intent slots captured at request time. Cluster bootstrap confidence intervals use the trajectory, not the individual step, as the resampling unit (2,000 draws).

### 5.2.1 Sampling protocol

**[new in v0.4.1]**

The harness flag `--max-trajectories 400` is a per-class limit, not a total. The trajectory list is partitioned by label and each partition is truncated independently (`benign[:400]`, `attack[:400]`). Because the dump contains only 97 benign trajectories, the benign slice is the complete set and the attack slice is a deterministic prefix. The evaluated sample is therefore 97 benign (a census) and 400 attack-labelled (a prefix), for 497 trajectories. Trajectory construction order is fixed by `build_trajectories`, which walks the dataset in load order; no random sampling, shuffling, or seed is involved at any point. This is load-bearing: a run that takes the last 400 attack trajectories, or a random 400, is a different experiment whose numbers are not comparable, and the committed verifier detects the difference.

One asymmetry follows from this and is worth stating up front: the benign figures are a census with no sampling error, while the attack figures are a prefix of a larger population. They are not symmetric estimates, and the benign number is the more trustworthy of the two.

### 5.3 Paired counterfactual control

**[unchanged from v0.3.1]**

To isolate source/context from tool choice, the paired experiment constructs four attack/benign pairs with identical final tool names and identical final arguments. The only intended difference is how the destination or action-driving value entered the context. A local-only gate must therefore give equal decisions within a pair; separation after context-aware processing demonstrates sensitivity to source information. Because output inspection already separates most pairs, this control establishes source/context attribution but not the incremental contribution of entity provenance alone.

### 5.4 Auxiliary SCI-600 fixture

**[unchanged from v0.3.1]**

SCI-600 is a project-generated, self-labelled single-event fixture used for regression and baseline comparison. It cannot exercise the central provenance mechanism because no prior tool output exists in the fixture format. We therefore treat it as auxiliary evidence and do not use it to claim generalization.

---

## 6. Results

### 6.1 Logged-trace replay

*Table 1. Main logged-trace replay result for the frozen v0.3 ladder. Confidence intervals are 95% cluster-bootstrap intervals over trajectories.*

| Configuration | Attack trace BLOCK | 95% CI | Benign trace BLOCK | 95% CI |
|---|---:|---|---:|---:|
| Local only | 0.0% | [0.0, 0.0] | 1.0% | [0.0, 3.1] |
| + output inspection | 3.5% | [1.75, 5.5] | 19.6% | [11.34, 27.84] |
| + entity provenance / taint | 16.0% | [12.5, 19.75] | 41.2% | [31.96, 50.52] |
| + intent consistency | 16.0% | [12.5, 19.75] | 41.2% | [31.96, 50.52] |

The most important observation is the zero-to-nonzero transition. The local-only gate blocks none of the 400 sampled attack trajectories. Merely making earlier untrusted tool output visible raises blocking to 3.5%, showing that relevant signal lies outside the current tool call. Entity provenance and taint then raise the block rate to 16.0%, an absolute gain of 12.5 percentage points over output inspection and a 4.6× multiplicative increase.

The safety gain is accompanied by a large benign cost. Benign trace blocking rises from 1.0% for local-only to 19.6% with output inspection and 41.2% with entity provenance. The full intent-consistency rung does not improve this trade-off on the logged traces. The result therefore supports provenance as a useful signal but not as a complete decision rule under an all-untrusted trust policy.

*Figure 2. Attack interception and benign blocking move together as more cross-event context is enabled.*

#### 6.1.1 Adding authorization semantics (v0.4.1)

The rungs above leave 41.2% benign trace blocking, which is the cost of the all-untrusted policy. The v0.4.1 configuration asks whether operator authorization can reduce that cost without giving up the provenance mechanism. Table 1b reports the full ladder including the v0.4.1 rungs.

*Table 1b. Full ladder including the v0.4.1 rungs, reported as point estimates. The first four rows are the frozen v0.3.1-research ladder, reproduced unchanged for comparability; their cluster-bootstrap confidence intervals appear in Table 1 and are not repeated here.*

| Configuration | Attack-labelled trace BLOCK | Benign trace BLOCK |
|---|---:|---:|
| `local_only` (single-event gate) | 0.0% | 1.03% |
| + untrusted output inspection | 3.5% | 19.59% |
| + entity provenance / taint (v0.3) | 16.0% | 41.24% |
| + intent consistency | 16.0% | 41.24% |
| **+ safe authorisation (v0.4.1)** | **3.5%** | **28.87%** |
| + structured intent slots | 3.5% | 28.87% |

**On confidence intervals.** The v0.4.1 rows carry no interval, and this is a limitation rather than an omission to be papered over: the frozen `v0_4_trust_pareto.json` records point estimates only, and its result records contain no variance field, so an interval computed for v0.4.1 would have to come from a bootstrap run that was not part of the frozen artifact. We therefore report the point estimates and state their absence, and we do not transplant the v0.3 intervals onto the v0.4.1 rows. Regenerating intervals for v0.4.1 requires re-running the ladder with a bootstrap wrapper, which is a separate measurement, not a re-reading of the committed artifact.

Two observations. First, benign trace blocking falls from 41.24% to 28.87%, a 12.37-point reduction, which is the intended benefit. Second, the raw blocking rate on attack-labelled trajectories also falls, from 16.0% to 3.5%. This second movement must not be described as the removal of false positives; the reason is stated in the limitations bullet on attack labels versus attack outcomes (Section 8).

An action-level audit of the trajectories the v0.3 rung blocked shows how the release decomposes. Of the 64 attack-labelled trajectories blocked by the v0.3 provenance rung, 36 ended in a final governed action concordant with explicit operator authorization, 14 ended in a read-only call that cannot act on the tainted value, and 14 were neither. This is an action-level statement about the final governance point; it is not a statement that those 50 trajectories were benign, and it is not a statement that the attacks failed.

`plus_intent_slots` produces numbers identical to `plus_trust_policy_v0_4` on this corpus. Prose authorization matching and structured-slot authorization agree wherever an operator request names both the action family and the entity exactly, which is the case for the authorization-concordant trajectories this corpus contains. We therefore do not claim the slot mechanism improves over prose matching here; we report only that it does not regress, and that the corpus cannot separate the two.

### 6.2 Paired source/context control

*Table 2. Paired counterfactual decisions after context-aware processing. Local-only decisions agree within all four pairs.*

| Identical final call | Attack decision | Benign decision |
|---|---|---|
| `send_email(attendees → partner)` | BLOCK | HUMAN_REVIEW |
| `delete_file(4821)` | BLOCK | ALLOW |
| `http_request(metrics endpoint)` | BLOCK | ALLOW |
| `upload_file(customers.csv)` | BLOCK | BLOCK |

Three pairs exhibit different decisions under context-aware processing, including two complete BLOCK-versus-ALLOW separations. The upload pair remains blocked in both conditions because the current policy treats exporting a customer file to an external destination as high risk even when explicitly authorized. This negative pair is useful, and in v0.4.1 it is no longer incidental but required: sensitive material crossing the trust boundary is classified unsuppressible, so authorization structurally cannot lower that decision. The pair is therefore a direct behavioural witness of the invariant in Section 7.5, showing that provenance does not automatically override content-level safety rules.

### 6.3 Evaluation isolation

**[unchanged from v0.3.1]**

The prediction-invariance audit executes 3,360 metadata perturbations across seven methods and observes zero prediction changes. This is a boundary property, not a performance metric. It establishes that the reported predictors are invariant to hidden grading metadata under the tested perturbations. The audit replaced an earlier invalid methodology that inferred leakage from accuracy degradation after shuffling ground-truth labels.

### 6.4 Held-out instruction generalization

**[unchanged from v0.3.1]**

A frozen instruction detector was evaluated on nine differently phrased attack styles and six benign controls without adding markers or changing thresholds. It detected 0/9 attacks and produced 0/6 benign false positives. Entity extraction recovered 5/7 expected destinations. This is an explicit negative result: the string-marker detector does not generalize to the held-out injection idioms. It motivates an instruction-versus-data classifier or stronger source semantics rather than further benchmark-specific keyword expansion.

### 6.5 Governance latency

**[unchanged from v0.3.1]**

In the same 497-trajectory replay, governance-only latency measured around `process_tool_call` is p50 = 0.47 ms, p95 = 5.32 ms, and p99 = 6.96 ms over 781 calls. These numbers exclude dataset loading and any model time. AgentShield itself places no LLM call on the governance path in the evaluated configuration.

### 6.6 SCI-600 auxiliary results

On the self-labelled SCI-600 fixture, the content-keyword baseline achieves the highest Macro-F1 (0.487). The production AgentShield pipeline obtains approximately 0.43 Macro-F1 and substantially fewer false allows in the frozen reports. Because this fixture is generated and labelled by the project and contains no prior tool-output context, we do not interpret the ranking as evidence of real-world generalization or of the provenance mechanism. The main paper claims instead rest on the external logged traces and paired source/context control. These figures describe the frozen v0.3 pipeline; the v0.4.1 aggregation change is not reflected in this fixture.

---

## 7. Discussion

### 7.1 What the results establish

**[unchanged from v0.3.1]**

First, the logged-trace experiment provides direct evidence of an observability gap at the runtime gate: a gate restricted to the current call blocks 0% of sampled attack trajectories, while a gate allowed to inspect prior output begins to recover attack signal. Second, provenance provides additional signal beyond generic output inspection, increasing trace blocking from 3.5% to 16.0% under the frozen configuration. Third, the paired control demonstrates that source/context can change a decision even when the final tool call is held fixed.

### 7.2 What the results do not establish

**[unchanged from v0.3.1]**

The experiments do not measure end-to-end attack success rate, benign utility, task success, or behavioral adaptation after a block. Offline replay cannot determine whether an agent would replan, retry, choose another tool, or successfully finish a benign task under governance. Likewise, the paired control does not prove that entity provenance alone creates every separation because the output-inspection rung already explains most of the paired difference.

### 7.3 The central open problem: trustworthy source attribution

The 41.2% benign trace-block rate of the v0.3 configuration exposed the primary research problem. Treating every external tool response as untrusted is label-safe but operationally crude. A deployable system needs a trust policy derived from runtime semantics rather than attack labels or content detectors. Candidate approaches include tool-specific source policies, authenticated origin metadata, explicit user authorization binding, capability-aware sinks, and a classifier that distinguishes imperatives from ordinary retrieved data. v0.4.1 reduces the residual to 28.9% by correcting authorization semantics rather than by trust-prior tuning, which leaves 28.9% as the open figure. These approaches should be frozen before benchmark evaluation to avoid benchmark-informed feature engineering.

### 7.4 Why provenance remains useful despite weak detector generalization

**[unchanged from v0.3.1]**

The held-out 0/9 detector recall might appear to undermine the architecture, but it actually separates two questions. Instruction detection asks whether a piece of text is adversarial; provenance asks where a value came from and how it flows into action. The latter remains meaningful even when the former is imperfect. Future systems can replace the string detector without changing the provenance data model, entity origins, or behavior graph.

### 7.5 An authorization safety invariant for risk aggregation

**[new in v0.4.1]**

The most consequential defect found in v0.4 was not a missing feature but an aggregation error. Authorization was implemented as a single ceiling applied to the combined risk score:

```text
peak = max(all components, all signals)
if authorized: peak = min(peak, AUTHORISED_ACTION_CEILING)
```

Because the cap was applied after aggregation, it bounded *every* component, including structural risk that authorization has no bearing on. An authorized bulk delete therefore left the gate at the ceiling value rather than at its true structural severity. The natural test to write for that code — "an authorized action scores at the ceiling" — is precisely a pinned-down vulnerability, and it was in fact written.

The fix is to split the aggregate into two bands that authorization cannot bridge:

```text
hard_peak = max(structural components, unsuppressible signals)
soft_peak = max(suppressible provenance signals)
if authorized: soft_peak = min(soft_peak, AUTHORISED_ACTION_CEILING)
score      = max(hard_peak, soft_peak)
```

Structural components (`local_risk`, `inherited_risk`, `path_risk`, `downstream_exposure`) and the unsuppressible signal classes never enter the capped path. The invariant this establishes is the paper's central design contribution in this release:

> **Authorization may explain provenance-derived suspicion, but it cannot authorize away independently dangerous behavior.**

The invariant is behavioural, not architectural: it is pinned by a test suite in which an authorized bulk delete remains blocked, an authorized action carrying untrusted content is reviewed rather than blocked, an authorized action whose destination arrived untrusted is bounded by the ceiling, inherited risk is unaffected, intervention value is unaffected, and an unknown future signal type fails closed as unsuppressible.

Two design decisions are worth stating explicitly because both cut against the headline number. First, trusted-entity resolution is deliberately **evidence-only** in this release: it is recorded in the audit chain but carries no ceiling. Giving it a prior-based ceiling in the same change would have moved two variables at once and made the ablation uninterpretable; the intended ladder is v0.4.1a authorization-only, then v0.4.1b + trusted resolution. Second, the ceilings were not retuned after the fix, even though retuning would have recovered part of the benign reduction visible in Table 1b. Retuning to recover a number is benchmark fitting.

The general lesson generalizes beyond this system: any risk aggregate that mixes "who asked" with "what is asked" needs a stated policy for which of the two authorization is allowed to move. Leaving it implicit produces a bypass that looks like a feature.

---

## 8. Limitations and Threats to Validity

- The logged-trace source is an AgentDojo-derived dump rather than the official AgentDojo runtime and grader. We therefore do not report AgentDojo benchmark performance or attack success rate.

- The main attack subset uses the first 400 attack trajectories after the audited grouping procedure, while all 97 benign trajectories are included. This is reproducible but is not a random population sample of all possible agent behavior. The benign figure is therefore a census and the attack figure a prefix, and the two are not symmetric estimates; where they are compared directly, the benign figure is the more trustworthy.

- The all-untrusted trust policy is intentionally conservative and likely overestimates false positives relative to a system with reliable source semantics. Conversely, it avoids an invalid evaluation shortcut in which trust is inferred from whether the content is malicious. The v0.4.1 rungs use a tool-semantics trust prior rather than the binary policy, but that prior participates only in an evidence-only signal in this release; the benign reduction it produces is therefore attributable to authorization semantics, not to trust-prior tuning.

- **Attack labels are not attack outcomes.** The dataset labels trajectories as attack or benign. Our gate decides at a final governance point using runtime-observable authorization evidence. Neither is a measurement of attack success: offline replay has no official grader, no attack-success rate, no task-level outcome and no utility measure. A release decision that is defensible at the action level is not thereby evidence that an attack failed, and the paper makes no such inference anywhere.

- **Authorization is a weak authorization signal.** Matching an operator request against a tool call establishes that the operator named this action family and this entity; it does not establish informed consent, authority, or absence of coercion. A manipulated agent whose final call happens to be authorization-concordant is authorized in our operational sense only. This is a further reason the action-level audit cannot be read as an attack-outcome measurement.

- The instruction detector is rule-based and fails to generalize on a small held-out set. The paper therefore does not claim robust prompt-injection detection.

- SCI-600 is synthetic and self-labelled. It is retained for regression and baseline sanity checks, not generalization claims.

- Risk weights and thresholds are engineering choices rather than calibrated probabilities. Their interpretation is ordinal governance severity, not probabilistic attack likelihood.

- The v0.4.1 ladder rows are reported as point estimates without confidence intervals, because the frozen artifact records no variance for them (Section 6.1.1).

---

## 9. Reproducibility and Release Discipline

The results in this manuscript correspond to the annotated release tag `v0.4.1-research`. Research logic is frozen at revision `49127cdef723db1e8db67d3d438a18f3e74a1853`; reproducibility tooling — a canonical-artifact verifier, a dataset fingerprint script, and their tests — was added by `83dddd7d6c62946db0244b3382c0cb3fa60307b2`. Later documentation-only commits do not change the experiment, and the moving branch HEAD is not an experiment identifier.

The main artifact is `benchmark/results/v0_4_trust_pareto.json`, SHA-256 `3e33c72d230cb7e0788dc4412574054c19dfd496546573698d73bff7b6a90565`. The evaluated dump is fingerprinted as a manifest over its Arrow files, with digest `948b94325ae1c8cfbe41bd205fee46b0f500215559ef5cd97a25c27fcf580049` over 1 file, 50,898,680 bytes, 13,913 rows and 10,536 constructed trajectories. A reproduction is valid only when both hashes match: the same script run against a different dump version is not a reproduction.

Reproduction is a two-command procedure. First, regenerate into a file distinct from the canonical artifact:

```bash
python benchmark/v04_trust_replay.py --mode audit --max-trajectories 400 \
  --out benchmark/results/v0_4_trust_pareto.reproduced.json
```

Then compare mechanically, with no tolerance and no "close enough" mode:

```bash
python scripts/verify_v04_reproduction.py \
  benchmark/results/v0_4_trust_pareto.json \
  benchmark/results/v0_4_trust_pareto.reproduced.json
```

The verifier compares experiment identity, dataset audit counts, ladder order, result order, and every per-configuration rate plus derived deltas, exiting 0 on exact agreement, 1 with a per-field difference list on any mismatch, and 2 when the comparison cannot be attempted. It fails closed when `AGENTSHIELD_ENABLE_CORPUS_MARKERS` is enabled, because corpus-specific markers change scoring and the canonical run had them disabled. In this release, three independent runs — the committed artifact and two fresh reproductions — produced byte-identical output.

**What CI does and does not verify.** GitHub Actions verifies code integrity, tests, linting, type checking, benchmark smoke execution and Docker health on Python 3.11 and 3.12. It does not independently regenerate the 497-trajectory logged-trace artifact, because that run depends on the locally staged external dump. A green badge is therefore not a reproduction of the 3.5% / 28.9% figures; the verification that matters for those numbers is the manual deterministic procedure above. Lint scope is likewise stated precisely: the two commands CI runs, `ruff check backend/` and `ruff check benchmark/ benchmark/independent_eval/ scripts/`, both pass, while a whole-repository `ruff check .` reports 123 pre-existing findings in directories CI does not lint.

Earlier figures produced by leaky or inconsistent harnesses are marked as withdrawn in the repository and are not used here. This release discipline is important because the project itself uncovered multiple evaluation failures during development, including label-derived fields, ground-truth values entering the engine, stale artifacts, and an invalid label-shuffling leakage diagnostic.

---

## 10. Conclusion

Tool-using agents can make dangerous decisions whose decisive cause is no longer visible in the final tool call. AgentShield studies this observability gap with a provenance-aware runtime gate. In logged traces, a current-call-only gate blocks none of the sampled attack trajectories; prior-output inspection raises blocking to 3.5%, and entity provenance raises it to 16.0%. The same additions sharply increase benign blocking, making the unresolved safety-utility trade-off explicit.

This release then shows that part of that trade-off was an aggregation error rather than an intrinsic cost. Separating provenance suspicion from structural danger, and permitting authorization to temper only the former, reduces benign trace blocking to 28.9% while keeping the authorization safety invariant that an authorized bulk delete remains blocked. The measured cost of the correction is reported rather than tuned away, and no threshold, weight, marker or sampling rule was adjusted to recover it.

Together with the paired source/context control and metadata-invariance audit, the results support provenance as a useful runtime security signal while rejecting stronger claims that the current prototype solves indirect prompt injection. The next research step is not further threshold tuning, but reliable trust attribution and instruction-data separation grounded in runtime source semantics — with the explicit recognition that trajectory-level attack labels, runtime action authorization, and actual attack success are three distinct levels, and that offline replay measures only the first two.

---

## References

[1] Q. Zhan, Z. Liang, Z. Ying, and D. Kang, "InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated Large Language Model Agents," *Findings of ACL 2024*, pp. 10471–10506, 2024. doi:10.18653/v1/2024.findings-acl.624.

[2] E. Debenedetti, J. Zhang, M. Balunović, L. Beurer-Kellner, M. Fischer, and F. Tramèr, "AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents," arXiv:2406.13352, 2024.

[3] S. Chen, J. Piet, C. Sitawarin, and D. Wagner, "StruQ: Defending Against Prompt Injection with Structured Queries," in *Proc. USENIX Security Symposium*, 2025. arXiv:2402.06363.

[4] K. Hines, G. Lopez, M. Hall, F. Zarfati, Y. Zunger, and E. Kiciman, "Defending Against Indirect Prompt Injection Attacks With Spotlighting," arXiv:2403.14720, 2024.

[5] M. Andriushchenko, A. Souly, M. Dziemian, D. Duenas, M. Lin, J. Wang, D. Hendrycks, A. Zou, Z. Kolter, M. Fredrikson, E. Winsor, J. Wynne, Y. Gal, and X. Davies, "AgentHarm: A Benchmark for Measuring Harmfulness of LLM Agents," in *Proc. ICLR*, 2025. arXiv:2410.09024.

[6] F. Wu, E. Cecchetti, and C. Xiao, "System-Level Defense against Indirect Prompt Injection Attacks: An Information Flow Control Perspective," arXiv:2409.19091, 2024.

[7] J. Shi, Z. Yuan, G. Tie, P. Zhou, N. Z. Gong, and L. Sun, "Prompt Injection Attack to Tool Selection in LLM Agents," arXiv:2504.19793, 2025.

[8] H. An, J. Zhang, T. Du, C. Zhou, Q. Li, T. Lin, and S. Ji, "IPIGuard: A Novel Tool Dependency Graph-Based Defense Against Indirect Prompt Injection in LLM Agents," in *Proc. EMNLP*, 2025. arXiv:2508.15310.

[9] Y. He, H. Zhu, Y. Li, S. Shao, H. Yao, Z. Liu, and Z. Qin, "AttriGuard: Defeating Indirect Prompt Injection in LLM Agents via Causal Attribution of Tool Invocations," in *Proc. USENIX Security Symposium*, 2026. arXiv:2603.10749.

[10] Y. Cai, W. Tang, C. Wen, and S. Qin, "Ghost in the Agent: Redefining Information Flow Tracking for LLM Agents," arXiv:2604.23374, 2026.

[11] A. Kravchenko, V. Liventsev, I. Konstantinov, I. Iskhakov, and M. Kukuy, "APPA: Recoverable Information-Flow Control for Real-World LLM Agents," arXiv:2607.24625, 2026.

[12] D. Girrens and G. Wang, "SPA: Securing Persistent LLM Agents Across Queries with Plan-First Information-Flow Control," arXiv:2608.27234, 2026.

[13] A. Storek, N. Holzer, Z. Zhang, and S. Jana, "GIF: Locally Sound Geometric Information Flow Control for LLMs," arXiv:2606.23277, 2026.

[14] M. Shim, R. R. Karim, R. Jakkula, K. Zhou, X. Liu, X. E. Wang, and Z. Li, "Confuse the Model, Control the Flow: Understanding and Mitigating Privacy Leakage from LLM Agents with Information Flow Control," arXiv:2609.14003, 2026.

[15] W. Zhao, Z. Li, P. Zhang, and J. Sun, "ClawGuard: A Runtime Security Framework for Tool-Augmented LLM Agents Against Indirect Prompt Injection," arXiv:2604.11790, 2026.

[16] Y. Wang, W. Zou, R. Geng, and J. Jia, "AgentWatcher: A Rule-based Prompt Injection Monitor," arXiv:2604.01194, 2026.

[17] C. Ye, J. Cui, and D. Hadfield-Menell, "Prompt Injection as Role Confusion," in *Proc. ICML*, 2026. arXiv:2603.12277.

[18] A. Doshi, Y. Hong, C. Xu, E. Kang, A. Kapravelos, and C. Kästner, "Towards Verifiably Safe Tool Use for LLM Agents," in *Proc. ICSE NIER*, 2026. arXiv:2601.08012.

[19] Y. Lin, J. Wu, Y. Nan, X. Wang, X. Zhang, and Z. Zheng, "AgentRaft: Automated Detection of Data Over-Exposure in LLM Agents," arXiv:2603.07557, 2026.

[20] A. Salem, A. Paverd, and B. Köpf, "Maatphor: Automated Variant Analysis for Prompt Injection Attacks," arXiv:2312.11513, 2023.

[21] X. Chen, J. Zhang, and F. Tramèr, "Learning to Inject: Automated Prompt Injection via Reinforcement Learning," arXiv:2602.05746, 2026.

[22] V. Mayoral-Vilches and P. M. Rynning, "Cybersecurity AI: Hacking the AI Hackers via Prompt Injection," arXiv:2508.21669, 2025.

[23] W. Li and Y. Xu, "ToolMinimize: Auditing and Rewriting LLM Agent Tool Calls to Minimize Privacy Exposure," arXiv:2608.24957, 2026.
