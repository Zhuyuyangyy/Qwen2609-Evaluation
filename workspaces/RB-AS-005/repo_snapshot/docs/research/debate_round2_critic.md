# AgentShield V3 第二轮批评：缺陷修复验证

**角色**: 严格学术批评者
**目标**: 验证第一轮致命缺陷是否已修复
**日期**: 2026-05-29

---

## 0. 关键前置发现：结果文件未更新

在逐一验证代码修改之前，必须指出一个基础问题：**benchmark/results/ 下的所有结果文件均未重新生成**。

- `sci_baseline_table.md` 仍只显示 4 个 baseline（旧版），缺少新增的 "LLM-as-Judge" 和 "AgentShield + Graph"
- `semireal_ablation_table.md` 仍显示旧版消融结构（"Full AgentShield" / "w/o chain propagation" / "w/o parent_step relation" 等），与新代码 `ablation_semireal.py` 中定义的 5 个消融条件完全不一致
- `semireal_ablation_report.json` 的 `note` 字段仍写着 "Full AgentShield reuses the V3.1 evaluate_semireal.py risk_agent_shield(case) path"，与新版 label-free 设计矛盾

**这意味着：当前所有汇报的数字（75.33% accuracy, 84.79% BLOCK recall 等）仍来自有标签泄漏的旧版代码。修改后的代码从未被运行过。**

这是一个严重问题。代码修改的价值为零，除非它能被运行并产生可验证的结果。

---

## 1. 致命缺陷 #1：标签泄漏 — 状态：⚠️ 部分修复

### 1.1 已修复的部分

第一轮批评指出 `risk_agent_shield()` 直接读取 `case.get("attack_stage")`, `case.get("chain_id")`, `case.get("step_index")` 这三个 ground-truth 字段。**这一问题已修复。**

新版代码（`baselines.py:248-298`）：
- 不再读取 `attack_stage`、`chain_id`、`step_index`
- 用 `_infer_chain_position(full_context)` 和 `_infer_attack_stage(full_context)` 从可观测内容推断链上下文
- 推断函数基于工具名和工具输入中的关键词模式

### 1.2 未修复 / 新引入的问题

**问题 A：推断函数与生成器耦合**

`_infer_attack_stage()` 的推断逻辑是：
```python
exfil_terms = ["send_email", "http_request", "upload", "external transfer", "exfiltrate"]
stage_terms = ["file_write", "compress", "archive", "export_csv", "staging"]
collect_terms = ["query", "select", "fetch_data", "cursor", "database"]
```

而 `generate_sci_dataset.py` 的 `build_tool_input()` 在 BLOCK case 中生成的内容恰好包含这些关键词：
```python
# behavior_chain_risk, block:
steps = ["query users", "select phone email", "compress data", "send external"]
# external_network_transfer, block:
body = "customer phone id_card salary password_hash external export"
```

推断函数找到的模式正是生成器故意放进去的。这不是真正的推断，而是换了一种方式读取标签。在真实部署中，攻击者不会在工具输入中标注 "I am in the exfiltrate stage"。

**问题 B：category 仍作为输入特征使用**

`risk_agent_shield()` 第 255 行：`category = case.get("category", "")`

`category` 是数据集生成器分配的 ground-truth 元数据。虽然所有 baseline 都使用 `category`（通过 `CATEGORY_PRIORS`），表面上是公平的，但在真实部署场景中，`category` 不是可观测特征——它是标注者事后分配的分类标签。

如果假设 `category` 是"任务描述中可推断的元信息"（如：这个 agent 是 "data_pipeline_agent"，那么它大概属于 "sensitive_data_access"），则需要明确论证这一假设，并确保所有方法对 `category` 的获取方式一致。当前代码没有这一论证。

**问题 C：CHAIN_STAGE_BOOST 查找表仍存在**

`baselines.py:63-69` 定义了 `CHAIN_STAGE_BOOST` 字典，在 `risk_agent_shield()` 第 268 行使用：`score += CHAIN_STAGE_BOOST.get(stage, 0.0)`

虽然 `stage` 现在是从内容推断而非从 ground-truth 读取，但这个查找表本身就是硬编码的特征工程。如果推断函数总能正确推断出 stage（在当前数据集上确实如此），那么这与直接读取 ground-truth 在效果上等价。

### 1.3 评分：⚠️ 部分修复

直接标签读取已消除，但推断函数与数据集生成器存在隐式耦合。在当前数据集上，推断函数的准确率可能接近 100%，因为关键词模式是生成器故意嵌入的。需要在 OOD（out-of-distribution）数据上验证推断函数的鲁棒性。

---

## 2. 致命缺陷 #2：图推理是否真正接入？ — 状态：⚠️ 部分修复

### 2.1 已修复的部分

新增 `risk_agent_shield_graph()` 函数（`baselines.py:301-311`）：
```python
def risk_agent_shield_graph(case):
    base_score = risk_agent_shield(case)
    graph_risk = _infer_graph_risk(case)
    enhanced = _apply_graph_risk_boost(base_score, graph_risk)
    return clamp(enhanced)
```

`_infer_graph_risk()` 函数（`baselines.py:129-174`）：
- 创建 `AgentBehaviorGraph` 实例
- 将当前 case 作为节点加入图谱
- 如果推断出 stage 为 "stage" 或 "exfiltrate"，添加一个下游代理节点
- 调用 `compute_risk_propagation()` 获取传播结果
- 返回最大风险值

图推理的结果确实通过 `_apply_graph_risk_boost()` 影响了最终评分。

### 2.2 未修复 / 新引入的问题

**问题 A：衰减因子仍为硬编码 0.5**

`agent_behavior_graph.py:299`：`inherited = current_risk * 0.5`

第一轮批评明确指出这是任意常数，无理论依据、无收敛分析、无条件传递。**此问题完全未修改。** 图传播的核心公式没有变化。

**问题 B：单步图无传播价值**

`_infer_graph_risk()` 为每个 case 独立构建一个新图。大多数 case 只有一个节点（当前工具调用）。只有当推断出 stage 为 "stage" 或 "exfiltrate" 时，才添加一个虚拟的 "exfil_proxy" 下游节点。

这意味着：
- 对于 80%+ 的 case，图只有一个节点，`compute_risk_propagation()` 返回该节点自身的 `shadow_risk_score`，图推理无任何附加价值
- 对于少数 case，添加了一个由 `local_score * 1.3 + 0.15` 计算风险的代理节点，然后用 `* 0.5` 衰减传播回父节点

这不是图推理。这是在单步评分上加了一个条件性的固定偏移。

**问题 C：edge.risk_flow 仍未使用**

`agent_behavior_graph.py:83` 定义了 `risk_flow: float = 0.0`，但在 `compute_risk_propagation()` 中，传播公式使用的是硬编码的 `0.5` 而非 `edge.risk_flow`。边级别的风险流量信息被完全忽略。

**问题 D：图推理对最终分数的影响微弱**

`_apply_graph_risk_boost()` 的逻辑：
```python
if graph_risk > 0.1:
    score += 0.15 * graph_risk
```

即使 `graph_risk` 为 1.0（最大值），也只增加 0.15 分。而 `risk_agent_shield()` 的基础评分范围是 0.0-1.0。图推理的最大贡献是将分数提升约 15%，且仅在 graph_risk > 0.1 时生效。考虑到大部分 case 的 graph_risk 等于自身的 local_score（因为图只有一个节点），这个 boost 的实际效果是 `0.15 * local_score`，即对高风险 case 增加约 0.12-0.15 分，对低风险 case 几乎无影响。

### 2.3 评分：⚠️ 部分修复

图推理在架构上已接入评分管线，但其实质仍是一个条件性的固定偏移。核心传播公式（0.5 衰减）、单步图无传播价值、edge.risk_flow 未使用等问题均未解决。第一轮批评说"图结构是装饰性的链表"——这一判断在当前代码中仍然成立。

---

## 3. 致命缺陷 #3：基线是否公平？ — 状态：⚠️ 大部分修复

### 3.1 已修复的部分

新增 `risk_llm_as_judge()` 基线（`baselines.py:314-412`）：
- 模拟 GPT-4 级别的风险评估
- 7 步推理过程：敏感数据检测、外部传输风险、权限升级、体量指标、链推断、信号组合、安全边际调整
- 仅使用可观测特征（tool_name, tool_input, category）
- 与 AgentShield 访问相同的信息

所有 6 个 baseline 现在使用相同的信息集：
| Baseline | tool_name | tool_input | category | 图推理 |
|---|---|---|---|---|
| Tool-name rules | Y | - | - | - |
| Content keywords | Y | Y | - | - |
| Local context | Y | Y | Y | - |
| LLM-as-Judge | Y | Y | Y | - |
| AgentShield chain-aware | Y | Y | Y | - |
| AgentShield + Graph | Y | Y | Y | Y |

### 3.2 未修复 / 新引入的问题

**问题 A：LLM-as-Judge 是模拟的，不是真正的 LLM**

`risk_llm_as_judge()` 是一个手写的规则函数，不是真正的 GPT-4 调用。它的 7 步"推理"实际上是硬编码的 if/else 逻辑和权重乘法。第一轮批评和裁决都要求与真正的 LLM-as-Judge（GPT-4 with chain context prompt）对比，当前实现不满足这一要求。

一个真正的 LLM-as-Judge baseline 应该：
- 调用 GPT-4 API，传入工具调用上下文
- 让 LLM 输出风险评估和推理过程
- 测试 LLM 在有/无 chain context 时的表现差异

**问题 B：NeMo Guardrails 基线仍缺失**

裁决要求增加 NeMo Guardrails 作为基线，当前代码中没有实现。

**问题 C：category 的公平性假设未论证**

如第 1.2 节所述，所有 baseline 使用 `category`，但 `category` 是否真的是"可观测特征"需要论证。在真实部署中，工具调用进入时没有 `category` 标签——它需要从上下文推断。

### 3.3 评分：⚠️ 大部分修复

基线间的信息公平性已大幅改善。新增的 LLM-as-Judge 基线使用相同的信息集。但 LLM-as-Judge 是模拟的而非真实的，NeMo Guardrails 基线仍缺失。

---

## 4. 其他缺陷验证

### 4.1 循环评估（数据集生成与评分耦合）— ❌ 未修复

`generate_sci_dataset.py` 未做任何修改：
- BLOCK case 仍包含 "password_hash", "external", "export" 等关键词
- 评分函数仍通过匹配这些关键词来判断风险
- 生成器和评分器仍是同一团队编写的耦合规则

这是第一轮的致命缺陷之一，完全未被触及。

### 4.2 反事实分析 — ❌ 未修复

`v3_engine.py:371`：`projected_risk = round(risk_score * 0.5, 3)`

第一轮批评指出这不是反事实分析，而是乘以 0.5。代码未做任何修改。

### 4.3 消融实验的 identity controls — ⚠️ 部分修复

新代码 `ablation_semireal.py` 定义了 5 个新的消融条件，不再包含旧版的 identity controls（"w/o parent_step relation" 和 "w/o future branch / what-if"）。新的消融设计更合理：
1. AgentShield + Graph（完整管线）
2. AgentShield (no graph)（无图推理）
3. w/o chain inference（无链推断）
4. Content keywords only（仅关键词）
5. LLM-as-Judge

但结果文件未更新，旧的消融报告（含 identity controls）仍是公开状态。

### 4.4 无 train/test split — ❌ 未修复

所有 600 个 SCI case 和 150 个 semi-real trace 仍在全集上评估，无交叉验证或 held-out 测试。

### 4.5 conformal prediction 死代码 — 未验证

未检查 `cp/core.py` 是否仍为死代码，但鉴于评分管线未变，很可能仍然如此。

---

## 5. 新发现的问题

### 5.1 结果与代码不一致（新增严重问题）

修改后的代码定义了 6 个 baseline，但结果文件只显示 4 个。消融实验的代码定义了 5 个新条件，但结果文件显示旧的 5 个条件。这意味着：

1. 修改后的代码从未被运行过
2. 所有汇报的数字来自有标签泄漏的旧版代码
3. 无法验证修改是否真正改善了任何指标

**这是一个比原始缺陷更严重的问题**：它表明修改是表面性的，目的是回应批评而非真正改进系统。

### 5.2 _infer_graph_risk() 的异常处理掩盖错误

```python
except Exception:
    return 0.0
```

`_infer_graph_risk()` 捕获所有异常并返回 0.0。如果图推理模块有任何导入错误、依赖缺失或运行时错误，函数会静默失败，返回 0.0。在基准测试中，这意味着图推理版本会退化为非图推理版本，且不会有任何错误提示。这使得图推理的效果无法被正确测量。

### 5.3 推断函数的脆弱性

`_infer_attack_stage()` 和 `_infer_chain_position()` 依赖硬编码的关键词列表。这些列表：
- 与数据集生成器的关键词高度重叠
- 无法处理同义词、变体或编码后的攻击
- 在真实攻击场景中可能完全失效

例如：如果攻击者使用 "transmit" 而非 "send_email"，或使用 base64 编码的工具输入，推断函数将返回 "single_call"，所有链感知功能将失效。

---

## 6. 第二轮评分

### 评分标准

| 维度 | 第一轮评分 | 第二轮评分 | 变化 | 说明 |
|---|---|---|---|---|
| 标签泄漏 | F (致命) | C- | 改善 | 直接读取已消除，但推断函数与生成器耦合 |
| 图推理接入 | F (致命) | C- | 改善 | 架构上已接入，但实质仍是固定偏移 |
| 基线公平性 | F (致命) | B- | 显著改善 | 信息集统一，但 LLM-as-Judge 是模拟的 |
| 循环评估 | F (致命) | F | 未变 | 完全未修改 |
| 反事实分析 | F | F | 未变 | 仍是 risk * 0.5 |
| 消融实验 | D | C+ | 部分改善 | 新设计合理，但结果未更新 |
| 交叉验证 | F | F | 未变 | 完全未修改 |
| 结果完整性 | N/A | F | 新问题 | 结果文件与代码不一致 |

### 总体评价

**第一轮总评：F（不可发表）**
**第二轮总评：D（仍不可发表，但有方向性改善）**

代码层面的修改方向是正确的：消除直接标签读取、新增 LLM-as-Judge baseline、重新设计消融条件。但存在三个阻断性问题：

1. **结果未更新**：修改后的代码从未运行，所有汇报数字来自旧版代码。这是最严重的问题——它使所有代码修改失去意义。
2. **推断函数的虚假改进**：`_infer_attack_stage()` 在当前数据集上可能等价于直接读取 ground-truth，因为关键词模式是生成器故意嵌入的。
3. **核心问题未触及**：循环评估、反事实分析、交叉验证等致命缺陷完全未修改。

---

## 7. 致作者的建议

### 必须立即做的（阻断性）

1. **运行修改后的代码，更新所有结果文件**。没有运行结果的代码修改等于没有修改。
2. **验证推断函数的准确率**：在当前数据集上计算 `_infer_attack_stage()` 与真实 `attack_stage` 的一致率。如果 >90%，说明推断函数只是换了一种方式读标签。
3. **在 OOD 数据上测试**：生成一批不包含明显关键词的攻击 case，验证推断函数是否仍然有效。

### 必须做的（严重）

4. **解耦数据集与评分**：让不参与评分设计的人（或独立的 LLM）生成攻击 case。
5. **实现真正的 LLM-as-Judge**：调用 GPT-4 API，而非手写规则模拟。
6. **实现真正的反事实分析**：移除某步骤后重新计算整条链的风险传播。
7. **引入 train/test split**。

### 建议做的（重要）

8. **用条件衰减替代硬编码 0.5**：衰减因子应依赖于边类型、语义相似度、数据流量等。
9. **用多步链替代单步图**：在 benchmark 中测试真正的多步工具调用链，而非为每个 case 独立构建单节点图。
10. **添加 NeMo Guardrails baseline**。

---

## 结论

第二轮修改展示了正确的意图和方向，但执行不够彻底。标签泄漏从"直接读取"变为"间接推断"，图推理从"未接入"变为"名义上接入"，基线从"稻草人"变为"较强但仍模拟的对手"。这些是真实的改善。

但三个阻断性问题——结果未更新、推断函数可能虚假、核心缺陷未触及——使得当前状态仍不满足发表标准。最关键的下一步不是写更多代码，而是**运行现有代码并诚实报告结果**。如果修改后的系统在公平条件下仍能展现链级推理的价值，那才是真正的进展。
