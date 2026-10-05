# AgentShield V3 -- SCI Paper Preparation Checklist

Last updated: 2026-05-28

---

## Phase 1: Manuscript Draft

- [x] Define paper title and abstract draft
- [x] Create detailed manuscript outline (`papers/manuscript_v0_1_outline.md`)
- [x] Organize all experiment tables (`papers/experiment_tables.md`)
- [ ] Write Section 1: Introduction (target: 1.5 pages)
- [ ] Write Section 2: Related Work (target: 2 pages, 20+ references)
- [ ] Write Section 3: Threat Model and Problem Formulation (target: 1.5 pages)
- [ ] Write Section 4: AgentShield Framework (target: 2 pages)
- [ ] Write Section 5: Risk Propagation Algorithm (target: 1.5 pages)
- [ ] Write Section 6: Counterfactual Intervention (target: 1 page)
- [ ] Write Section 7: Experimental Setup (target: 1.5 pages)
- [ ] Write Section 8: Results (target: 2 pages)
- [ ] Write Section 9: Ablation Analysis (target: 1 page)
- [ ] Write Section 10: Case Studies (target: 1.5 pages)
- [ ] Write Section 11: Limitations and Future Work (target: 0.5 pages)
- [ ] Write Section 12: Conclusion (target: 0.5 pages)
- [ ] Total target: 15-16 pages (excluding references and appendix)

---

## Phase 2: Experiments and Evidence

### 2.1 Completed Experiments

- [x] SCI-600 synthetic dataset generation (`benchmark/generate_sci_dataset.py`)
- [x] SCI-600 baseline comparison (`benchmark/baselines.py`)
- [x] Semi-Real-150 trace generation (`benchmark/generate_semireal_traces.py`)
- [x] Semi-Real-150 evaluation (`benchmark/evaluate_semireal.py`)
- [x] Ablation study on SCI-600 (`scripts/run_ablation.py --dataset sci`)
- [x] Ablation study on Semi-Real-150 (`scripts/run_ablation.py --dataset semireal`)
- [x] All result tables generated in `benchmark/results/`

### 2.2 Additional Experiments Needed

- [ ] **Per-category breakdown**: Action accuracy and F1 per category (sensitive_access, external_transfer, etc.)
- [ ] **Confusion matrix extraction**: Full 3x3 confusion matrices from `sci_baseline_report.json` and `semireal_baseline_report.json`
- [ ] **Case study visualizations**: Generate behavior graph diagrams for 3 representative cases
- [ ] **Counterfactual report examples**: Extract what-if analysis reports for case studies
- [ ] **Latency profiling**: Detailed latency breakdown (graph construction, risk propagation, decision) at p50/p95/p99
- [ ] **Scalability test**: Measure runtime at varying chain lengths (10, 50, 100, 500 steps)

### 2.3 Evidence Gaps (from paper_plan.md)

- [ ] **Real-world trace validation**: At least one of:
  - [ ] Traces from controlled LangChain experiment
  - [ ] Traces from controlled AutoGen experiment
  - [ ] Public task traces converted to AgentShield schema
  - [ ] Internal agent workflow logs (anonymized)
- [ ] **Human evaluation**: Auditor efficiency with/without counterfactual explanations (optional but strengthens paper)

---

## Phase 3: Figures and Visualizations

- [ ] **Figure 1**: AgentShield architecture diagram (tool call -> behavior graph -> governance decision)
- [ ] **Figure 2**: Behavior graph example for data exfiltration chain
- [ ] **Figure 3**: Risk propagation illustration across a 4-step chain
- [ ] **Figure 4**: Baseline comparison bar chart (Action Acc. and Macro F1 across methods)
- [ ] **Figure 5**: Ablation study visualization (component contribution)
- [ ] **Figure 6**: Case study -- behavior graph with counterfactual intervention
- [ ] **Figure 7** (optional): Runtime overhead comparison

---

## Phase 4: References

- [ ] Collect 25-35 references covering:
  - [ ] LLM safety and guardrails (5-8 refs)
  - [ ] Agent tool-use safety (4-6 refs)
  - [ ] Multi-agent system security (4-6 refs)
  - [ ] Graph-based risk analysis (4-6 refs)
  - [ ] Counterfactual reasoning (3-5 refs)
  - [ ] Benchmark methodology (3-5 refs)
- [ ] Format all references in target journal style
- [ ] Verify all citations are accessible (no broken links)

---

## Phase 5: Paper Polish

- [ ] Internal review pass (clarity, flow, argument strength)
- [ ] Check all numbers in text match tables
- [ ] Verify all figures are referenced in text
- [ ] Spell check and grammar check
- [ ] Check acronym consistency (define on first use)
- [ ] Verify mathematical notation consistency
- [ ] Add acknowledgments section
- [ ] Prepare supplementary material (code, datasets, reproduction instructions)

---

## Phase 6: Submission Preparation

### 6.1 Target Journal Selection

Candidate journals (ranked by fit):

1. **IEEE Transactions on Information Forensics and Security (TIFS)** -- IF ~6.8, strong fit for security + AI
2. **ACM Computing Surveys** -- IF ~16.6, if framed as comprehensive survey + method
3. **Artificial Intelligence (AIJ)** -- IF ~14.0, broad AI audience
4. **Journal of Artificial Intelligence Research (JAIR)** -- IF ~4.5, open access, AI methods
5. **Computers & Security** -- IF ~5.6, applied security
6. **Neurocomputing** -- IF ~6.0, applied AI/ML

**Recommended**: IEEE TIFS or Computers & Security (best fit for security + governance framing)

### 6.2 Submission Checklist

- [ ] Read target journal's author guidelines thoroughly
- [ ] Format paper according to journal template (LaTeX or Word)
- [ ] Prepare title page with author affiliations and contact
- [ ] Write cover letter highlighting novelty and contributions
- [ ] Prepare supplementary materials package
- [ ] Check page limits
- [ ] Verify figure resolution requirements (typically 300+ DPI)
- [ ] Prepare conflict of interest statement
- [ ] List suggested reviewers (3-5 experts in agent safety / LLM governance)
- [ ] List opposed reviewers (if applicable)
- [ ] Final PDF generation and review
- [ ] Submit through journal portal

---

## Phase 7: Post-Submission

- [ ] Prepare rebuttal template for common reviewer concerns:
  - "Synthetic data only" -> Emphasize Semi-Real-150 controlled traces + plan for real-world validation
  - "Small scale" -> Note 600 + 150 cases is standard for method papers; plan for larger datasets
  - "Comparison with LLM-based methods" -> Add discussion of LLM-based governance as future work
  - "Latency concerns" -> Present detailed runtime profiling
- [ ] Track submission status
- [ ] Plan revision timeline (typically 4-8 weeks for first response)

---

## File Inventory

| File | Status | Description |
|---|---|---|
| `papers/manuscript_v0_1_outline.md` | Done | Detailed paper outline with all sections |
| `papers/experiment_tables.md` | Done | All tables formatted for paper + LaTeX snippets |
| `papers/SCI_PREPARATION_CHECKLIST.md` | Done | This checklist |
| `benchmark/results/sci_baseline_table.md` | Done | SCI-600 baseline results |
| `benchmark/results/semireal_baseline_table.md` | Done | Semi-Real-150 baseline results |
| `benchmark/results/ablation_sci_table.csv` | Done | SCI-600 ablation data |
| `benchmark/results/ablation_semireal_table.csv` | Done | Semi-Real-150 ablation data |
| `benchmark/results/ablation_sci_deltas.csv` | Done | SCI-600 ablation deltas |
| `benchmark/results/ablation_semireal_deltas.csv` | Done | Semi-Real-150 ablation deltas |
| `benchmark/results/sci_baseline_report.json` | Done | Full SCI-600 report (for confusion matrix extraction) |
| `benchmark/results/semireal_baseline_report.json` | Done | Full Semi-Real-150 report |
| `benchmark/results/ablation_sci_report.json` | Done | Full SCI-600 ablation report |
| `benchmark/results/ablation_semireal_report.json` | Done | Full Semi-Real-150 ablation report |
| `docs/paper_plan.md` | Done | Original paper plan and roadmap |
| `benchmark/label_policy.md` | Done | Label definitions for ALLOW / HUMAN_REVIEW / BLOCK |

---

## Priority Action Items (Next Steps)

1. **HIGH**: Extract confusion matrices from JSON reports and add to experiment tables.
2. **HIGH**: Write Sections 1-3 (Introduction, Related Work, Threat Model) -- these set the paper's framing.
3. **MEDIUM**: Generate case study visualizations (behavior graph diagrams).
4. **MEDIUM**: Add per-category breakdown experiment.
5. **MEDIUM**: Select target journal and download template.
6. **LOW**: Real-world trace validation (can be added in revision if needed).
7. **LOW**: Human evaluation study (strengthening evidence, not strictly required for initial submission).
