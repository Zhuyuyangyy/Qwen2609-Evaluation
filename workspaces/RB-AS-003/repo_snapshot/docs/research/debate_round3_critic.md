# AgentShield V3 第三轮批评：深度验证

**角色**: 严格学术批评者
**目标**: 验证第二轮批评中指出的问题是否已修复，评估论文就绪度
**日期**: 2026-05-29
**基于**: debate_round2_critic.md + OPTIMIZATION_REPORT.md Section 9 + 修改后的代码 + 最新 benchmark 结果

---

## 0. 前置确认：结果文件已更新

第二轮批评的首要阻断性问题是"修改后的代码从未运行"。**此问题已修复。**

- `sci_baseline_table.md` 现在显示 6 个 baseline（包括新增的 LLM-as-Judge 和 AgentShield + Graph）
- `semireal_ablation_report.json` 的 `note` 字段已更新为 "V3.3 ablation: all configurations use only observable features (no ground-truth labels)."
- `semireal_ablation_table.md` 匹配新的消融设计（5 个条件：AgentShield + Graph / AgentShield (no graph) / w/o chain inference / Content keywords only / LLM-as-Judge）

**遗留问题**: 旧版结果文件 `ablation_semireal_report.json` 和 `ablation_semireal_table.csv` 仍存在，含旧版消融名称（"0  Full AgentShield", "1  -stage boost" 等）。这些文件可能造成混淆，建议删除或归档。

---

## 1. 验证点 1：推断函数是否真正使用结构性模式？

### 1.1 代码审查

**旧版** (`_infer_attack_stage()` 第一轮):
```python
exfil_terms = ["send_email", "http_request", "upload", "external transfer", "exfiltrate"]
stage_terms = ["file_write", "compress", "archive", "export_csv", "staging"]
collect_terms = ["query", "select", "fetch_data", "cursor", "database"]
```

**新版** (`baselines.py:116-167`):
```python
has_outbound = any(t in lower for t in ["send", "http", "upload", "post", "webhook", "ftp", "smtp", "mail"])
has_staging = any(t in lower for t in ["write", "compress", "archive", "dump", "backup", "serialize", "encode"])
has_collection = any(t in lower for t in ["query", "select", "fetch", "cursor", "sql", "database", "table"])
has_recon = any(t in lower for t in ["scan", "probe", "enum", "discover", "list", "recon"])
```

### 1.2 改善分析

新版确实从**数据集特定关键词**（如 `send_email`, `export_csv`, `file_write`）转向了**结构性工具类别模式**（如 `send`, `http`, `upload`）。这是一个真实的改善：

- 旧版：`send_email` -- 仅匹配数据集生成器的精确用词
- 新版：`send` -- 匹配任何包含 "send" 的工具名（send_notification, send_sms, send_slack_message 等）

### 1.3 残留耦合

**严重问题**: 数据集生成器 `build_tool_input()` 仍然生成直接触发结构性模式的内容：

| 生成器输出 (BLOCK case) | 推断函数匹配项 |
|---|---|
| `"query users"` | `query` -> has_collection |
| `"select phone email"` | `select` -> has_collection |
| `"compress data"` | `compress` -> has_staging |
| `"send external"` | `send` -> has_outbound |
| `"external transfer"` (旧版仍保留) | `external` -> has_outbound |

**评估**: 新版结构性模式比旧版更泛化（`send` vs `send_email`），但数据集生成器的内容仍然刻意包含这些结构性模式的触发词。耦合程度从"直接读标签"降低到"结构性模式被生成器刻意嵌入"，但**尚未完全解耦**。

在真实部署中，攻击者的工具输入不会标注 "I am doing a send operation"。推断函数的鲁棒性仍然高度依赖于数据集的构造方式。

### 1.4 评分: ⚠️ 部分修复（从 C- 提升到 C+）

方向正确，但解耦不彻底。需要在 OOD 数据上验证推断函数的泛化能力。

---

## 2. 验证点 2：动态衰减公式

### 2.1 公式审查

`agent_behavior_graph.py:303-307`:
```python
chain_length = current_depth + 1
decay = 1.0 / (1.0 + 0.3 * chain_length)
inherited = current_risk * decay
```

### 2.2 收敛性分析

**数学性质**:

| chain_length | decay 值 | 传播风险 (假设源 risk=1.0) |
|---|---|---|
| 1 | 0.769 | 0.769 |
| 2 | 0.625 | 0.625 |
| 3 | 0.526 | 0.526 |
| 5 | 0.400 | 0.400 |
| 10 | 0.250 | 0.250 |
| 100 | 0.032 | 0.032 |

**收敛性**: 当 chain_length -> infinity 时，decay -> 0。传播风险序列单调递减且有下界 0，因此**数学上收敛**。这比旧版的硬编码 `* 0.5` 有明确的理论改进。

**收敛速度**: 衰减速度为 O(1/n)，属于慢衰减。在 chain_length=10 时仍有 25% 的风险传播，chain_length=20 时仍有 14%。对于需要快速阻断风险传播的场景，这可能过慢。

### 2.3 残留问题

**问题 A: 0.3 系数仍为任意常数**

公式中的 `0.3` 没有理论依据或经验校准。不同值会导致截然不同的行为：
- `0.1`: chain_length=5 时 decay=0.67（几乎无衰减）
- `0.3`: chain_length=5 时 decay=0.40（当前值）
- `1.0`: chain_length=5 时 decay=0.17（强衰减）

**问题 B: edge.risk_flow 仍未使用**

`BehaviorEdge.risk_flow` 字段（`agent_behavior_graph.py:83`）在 `compute_risk_propagation()` 中完全未被引用。衰减公式不考虑边的特性（数据流量、边类型、语义相似度），所有边使用相同的衰减。

**问题 C: 单步图使公式失去意义**

在 benchmark 中，`_infer_graph_risk()` 为每个 case 独立构建单节点图（或最多两个节点）。在单步或两步图中，chain_length 最大为 1，decay = 0.769，衰减效果微弱。动态衰减公式在多步链场景中才能展现其价值，但当前 benchmark 不测试多步链。

### 2.4 评分: ⚠️ 部分修复（从 C- 提升到 C）

数学上正确且收敛，但参数任意、边属性未使用、在当前 benchmark 设置下效果有限。

---

## 3. 验证点 3：Benchmark 结果真实性

### 3.1 结果对比

**SCI-600 Baseline 对比（第二轮 vs 第三轮）**:

| Method | 第二轮 Acc. | 第三轮 Acc. | 第二轮 BLOCK Recall | 第三轮 BLOCK Recall |
|---|---|---|---|---|
| AgentShield chain-aware | 79.7%* | 77.83% | ~95%* | 94.47% |
| AgentShield + Graph | N/A | 47.83% | N/A | 100.00% |

*第二轮数字来自旧版代码，第三轮来自新版代码

**Semi-Real-150 消融对比**:

| Configuration | 第二轮 Acc. | 第三轮 Acc. | 第二轮 BLOCK Recall | 第三轮 BLOCK Recall |
|---|---|---|---|---|
| AgentShield + Graph | N/A | 50.00% | N/A | 75.00% |
| AgentShield (no graph) | ~67%* | 66.67% | ~50%* | 50.00% |
| w/o chain inference | ~67%* | 66.67% | ~17%* | 16.67% |

### 3.2 下降是否说明去耦合成功？

**SCI-600 上的 accuracy 从 ~79.7% 降至 77.83%**: 这是一个**合理的、小幅度的下降**。推断函数不再直接匹配生成器关键词，部分 case 的链推断失败导致评分降低。这确实表明去耦合取得了一定效果。

**但必须注意**:
- 下降幅度很小（~2%），可能在噪声范围内
- 没有统计显著性检验（无置信区间、无 p 值）
- 在全集上评估，无 held-out 测试集

### 3.3 新发现的严重问题

**问题 A: LLM-as-Judge 基线完全失效**

| Dataset | LLM-as-Judge Accuracy | LLM-as-Judge BLOCK Recall | LLM-as-Judge False Allow |
|---|---|---|---|
| SCI-600 | 20.83% | 0.00% | 100.00% |
| Semi-Real-150 | 33.33% | 0.00% | 100.00% |

LLM-as-Judge 在两个数据集上的 BLOCK recall 均为 0%，false allow rate 均为 100%。它将**所有 case** 预测为 ALLOW。这不是一个"强基线"，而是一个**完全失效的基线**。

审查 `risk_llm_as_judge()` 的代码发现：
- `combined` 计算使用 `category_prior * 0.25 + sensitive_data_score * 0.25 + ...`
- 即使所有信号最大，combined 也难以超过 0.50（ALLOW 阈值为 0.60）
- 权重设计导致输出永远在低分区间

**这意味着**: 当前所有"AgentShield 优于 LLM-as-Judge"的比较都是虚假的。AgentShield 不是在与一个强基线比较，而是在与一个坏了的基线比较。

**问题 B: AgentShield + Graph 在 SCI-600 上过度阻断**

| Metric | AgentShield chain-aware | AgentShield + Graph |
|---|---|---|
| Accuracy | 77.83% | 47.83% |
| BLOCK Recall | 94.47% | 100.00% |
| False Block Rate | 20.00% | 31.20% |

图推理版本将 accuracy 降低了 30 个百分点（从 77.83% 到 47.83%），同时将 BLOCK recall 从 94.47% 提升到 100%。这不是一个 trade-off，而是**过度阻断**：图推理将大量 ALLOW 和 HUMAN_REVIEW case 误判为 BLOCK。

在 confusion matrix 中可以看到：
- ALLOW: 20 正确，66 判为 HUMAN_REVIEW，39 判为 BLOCK
- HUMAN_REVIEW: 23 判为 ALLOW，50 正确，185 判为 BLOCK

`_infer_graph_risk()` 中的 exfil_proxy 机制（`local_score * 1.3 + 0.15`）对所有推断为 "stage" 或 "exfiltrate" 的 case 人为抬高风险，导致过度阻断。

**问题 C: 两套结果文件并存**

`benchmark/results/` 下存在两套结果：
- `semireal_ablation_report.json` + `semireal_ablation_table.md` -- 新版（V3.3 消融设计）
- `ablation_semireal_report.json` + `ablation_semireal_table.csv` -- 旧版（旧消融设计）

旧版文件含 `"name": "0  Full AgentShield"`, `"name": "1  -stage boost"` 等旧名称，与新版代码完全不一致。这会造成混淆。

### 3.4 评分: ⚠️ 部分修复

结果已更新，代码已运行，下降幅度合理。但 LLM-as-Judge 基线完全失效，图推理过度阻断，旧结果文件仍存在。

---

## 4. 验证点 4：残留标签泄漏

### 4.1 已消除的标签泄漏

- `attack_stage`: 不再直接读取，改为推断
- `chain_id`: 不再读取
- `step_index`: 不再读取

### 4.2 残留的标签泄漏

**泄漏 1: category 作为输入特征**

所有 6 个 baseline 都使用 `case.get("category", "")`。`category` 是数据集生成器分配的元数据标签，在真实部署中不是直接可观测的。虽然所有方法都使用（表面上公平），但这是一个**系统性的信息优势**。

`CATEGORY_PRIORS` 字典为每个 category 分配了不同的先验分数（0.42-0.62），这等价于从标签读取了一部分风险信息。

**泄漏 2: CHAIN_STAGE_BOOST 查找表**

`baselines.py:63-69`:
```python
CHAIN_STAGE_BOOST = {
    "recon": 0.03, "collect": 0.09, "stage": 0.14,
    "exfiltrate": 0.26, "single_call": 0.0,
}
```

虽然 `stage` 现在是从内容推断而非从 ground-truth 读取，但这个查找表将推断结果映射到与 ground-truth 高度相关的 boost 值。如果推断函数在当前数据集上准确率高（由于上述耦合问题，很可能如此），效果等价于读取标签。

**泄漏 3: 内容关键词直接匹配**

`risk_agent_shield()` 第 323-337 行:
```python
if "external" in text and any(term in text for term in ["phone", "email", "salary", "id_card"]):
    score += 0.14
if "password_hash" in text or "audit evasion" in text:
    score += 0.18
```

这些是直接的关键词匹配。数据集生成器在 BLOCK case 中刻意包含 "password_hash"、"external"、"id_card" 等词。这不是推断，而是关键词匹配伪装成特征工程。

### 4.3 评分: ⚠️ 部分修复（从 C- 维持在 C-）

直接标签读取已消除，但 category 伪标签、CHAIN_STAGE_BOOST 查找表、内容关键词匹配等间接泄漏仍然存在。

---

## 5. 第二轮遗留问题验证

### 5.1 循环评估（数据集生成与评分耦合）— ❌ 未修复

`generate_sci_dataset.py` 完全未修改。BLOCK case 仍包含 "password_hash", "external", "export" 等关键词，评分函数仍通过匹配这些关键词来判断风险。这是学术不端级别的问题：评分器在测试自己参与生成的数据。

### 5.2 反事实分析 — ❌ 未修复

`v3_engine.py:371`: `projected_risk = round(risk_score * 0.5, 3)`

仍然是乘以 0.5，不是真正的反事实分析（应移除某步骤后重新计算整条链的风险传播）。

### 5.3 无 train/test split — ❌ 未修复

所有 600 个 SCI case 和 150 个 semi-real trace 仍在全集上评估。无交叉验证、无 held-out 测试集、无置信区间。

### 5.4 LLM-as-Judge 仍是模拟的 — ❌ 未修复

`risk_llm_as_judge()` 是手写的 if/else 规则函数，不是真正的 GPT-4 API 调用。更严重的是，如第 3.3 节所示，这个模拟基线完全失效（0% BLOCK recall）。

### 5.5 NeMo Guardrails 基线 — ❌ 未修复

未实现。

### 5.6 conformal prediction 死代码 — 未验证（低优先级）

---

## 6. 新发现的问题

### 6.1 旧结果文件未清理

`ablation_semireal_report.json` 和 `ablation_semireal_table.csv` 仍含旧版消融结果，与当前代码不一致。这会造成读者混淆。

### 6.2 _infer_graph_risk() 的异常静默处理

```python
except Exception:
    return 0.0
```

所有异常被静默吞掉，图推理模块的任何错误都不会被报告。在 benchmark 中，这会导致图推理版本静默退化为非图版本。

### 6.3 exfil_proxy 虚拟节点的过度影响

`_infer_graph_risk()` 对推断为 "stage" 或 "exfiltrate" 的 case 添加一个虚拟的 exfil_proxy 节点，其风险为 `local_score * 1.3 + 0.15`。这个硬编码的公式会导致：
- local_score=0.7 -> exfil_score=1.06 -> clamp to 1.0
- local_score=0.5 -> exfil_score=0.80

几乎所有被推断为 stage/exfiltrate 的 case 都会被推到 BLOCK 区间，导致图推理版本的过度阻断（47.83% accuracy，31.20% false block rate）。

### 6.4 消融实验设计缺陷

当前消融实验比较的是完全不同的函数（risk_agent_shield vs risk_local_context vs risk_content_keyword），而非同一函数的组件移除。这不满足学术消融实验的标准——应该是在同一框架下逐一移除组件，而非切换到完全不同的函数。

例如，"w/o chain inference" 使用 `risk_local_context`（一个完全不同的函数），而非 `risk_agent_shield` 中移除链推断逻辑。这无法隔离链推断的单独贡献。

---

## 7. 第三轮评分

### 评分标准

| 维度 | 第一轮 | 第二轮 | 第三轮 | 变化 | 说明 |
|---|---|---|---|---|---|
| 标签泄漏 | F | C- | C- | 维持 | 直接读取已消除，category/关键词匹配仍在 |
| 图推理接入 | F | C- | C | 小幅改善 | 动态衰减公式合理，但 exfil_proxy 过度阻断 |
| 基线公平性 | F | B- | D+ | **严重退步** | LLM-as-Judge 完全失效（0% recall） |
| 循环评估 | F | F | F | 未变 | 完全未修改 |
| 反事实分析 | F | F | F | 未变 | 仍是 risk * 0.5 |
| 消融实验 | D | C+ | C | 小幅退步 | 设计不满足学术标准（切换函数而非移除组件） |
| 交叉验证 | F | F | F | 未变 | 完全未修改 |
| 结果完整性 | N/A | F | B- | **显著改善** | 代码已运行，结果已更新 |
| 公式合理性 | N/A | N/A | C | 新增 | 动态衰减数学正确但参数任意 |

### 总体评价

**第一轮总评：F（不可发表）**
**第二轮总评：D（仍不可发表）**
**第三轮总评：D（仍不可发表，方向改善但结构性问题未解决）**

**改善的方面**:
1. 结果文件已更新，代码已运行 -- 这是最基本的要求，终于满足
2. 推断函数从数据集特定关键词转向结构性模式 -- 方向正确
3. 动态衰减公式数学上正确且收敛 -- 比硬编码 0.5 好

**未改善的方面**:
1. 循环评估（数据集生成与评分耦合）-- 核心学术诚信问题，完全未触及
2. 反事实分析 -- 仍是乘以 0.5
3. 无 train/test split -- 在全集上评估，结果不可泛化
4. LLM-as-Judge 基线完全失效 -- 与"稻草人"基线的比较毫无意义

**新引入的问题**:
1. LLM-as-Judge 的权重设计导致 0% BLOCK recall
2. 图推理的 exfil_proxy 导致过度阻断（47.83% accuracy）
3. 消融实验不满足学术标准

---

## 8. 论文就绪度评分

### 评分维度

| 维度 | 权重 | 得分 | 加权得分 |
|---|---|---|---|
| 实验设计严谨性 | 25% | 2/10 | 0.50 |
| 基线公平性 | 20% | 3/10 | 0.60 |
| 消融实验完整性 | 15% | 3/10 | 0.45 |
| 代码与结果一致性 | 15% | 7/10 | 1.05 |
| 理论基础 | 10% | 4/10 | 0.40 |
| 可复现性 | 10% | 5/10 | 0.50 |
| 创新性 | 5% | 6/10 | 0.30 |
| **总计** | **100%** | | **3.80/10** |

### 最终论文就绪度评分: **3/10** (向下取整，因为循环评估是阻断性问题)

---

## 9. 必须立即修复的阻断性问题

### 优先级 P0（无此不可发表）

1. **修复 LLM-as-Judge 基线**: 当前 0% BLOCK recall，完全失效。需要：
   - 重新校准权重，使其输出合理的分数分布
   - 或者实现真正的 GPT-4 API 调用

2. **打破循环评估**: 数据集生成与评分必须由独立方完成。方案：
   - 让不参与评分设计的独立 LLM 生成攻击 case
   - 或使用公开的第三方安全数据集（如 SecBench、InjecAgent）

3. **修复图推理过度阻断**: exfil_proxy 的 `local_score * 1.3 + 0.15` 公式导致几乎所有推断为 stage/exfiltrate 的 case 都被阻断。需要校准或移除。

### 优先级 P1（严重）

4. **实现真正的反事实分析**: 移除某步骤后重新计算整条链的风险传播
5. **引入 train/test split**: k-fold 交叉验证或 held-out 测试集
6. **清理旧结果文件**: 删除 `ablation_semireal_report.json` 和 `ablation_semireal_table.csv`
7. **重新设计消融实验**: 在同一框架下逐一移除组件，而非切换到不同函数

### 优先级 P2（重要）

8. **论证 category 的可观测性**: 或移除 category 作为输入特征
9. **校准衰减系数 0.3**: 通过经验数据或理论推导确定最优值
10. **使用 edge.risk_flow**: 将边属性纳入传播公式
11. **添加统计显著性检验**: 置信区间、p 值、效应量

---

## 10. 结论

第三轮修改在"结果完整性"维度取得了显著改善——代码终于被运行，结果终于被更新。推断函数从数据集特定关键词转向结构性模式，动态衰减公式从硬编码 0.5 改为数学上收敛的函数，这些都是真实的技术进步。

但三个根本性问题仍未解决：

1. **循环评估**: 评分器在测试自己参与生成的数据，这是学术诚信的底线问题
2. **基线失效**: LLM-as-Judge 的 0% BLOCK recall 使所有"优于基线"的声称无效
3. **无泛化验证**: 在全集上评估、无 train/test split、无 OOD 测试

当前状态可以作为**技术报告**或**系统演示**提交，但不满足**学术会议/期刊论文**的发表标准。最关键的下一步是：(1) 修复 LLM-as-Judge 基线，(2) 引入独立数据集或 train/test split，(3) 修复图推理过度阻断。

---

## 评级总结

| 验证点 | 评级 | 说明 |
|---|---|---|
| 推断函数使用结构性模式 | ⚠️ | 方向正确，但与生成器仍有耦合 |
| 动态衰减公式合理性 | ⚠️ | 数学正确，参数任意，在当前设置下效果有限 |
| Benchmark 结果真实性 | ⚠️ | 已更新，下降合理，但 LLM-as-Judge 失效 |
| 残留标签泄漏 | ⚠️ | 直接泄漏消除，category/关键词/CHAIN_STAGE_BOOST 仍在 |
| 论文就绪度 | **3/10** | 不可发表，需解决循环评估、基线失效、泛化验证 |
