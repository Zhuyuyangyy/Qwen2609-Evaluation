# AgentShield V3.3 权利要求-证据映射表

**生成日期**: 2026-05-28
**关联文档**: `docs/PATENT_DISCLOSURE_V3.md`, `docs/PATENT_SUPPLEMENT.md`

---

## 一、映射说明

本表建立专利权利要求与代码实现、实验数据之间的对应关系，用于：
1. 验证权利要求的技术支撑是否充分
2. 准备专利审查时的举证材料
3. 识别哪些代码文件需要保护

---

## 二、独立权利要求映射

### 权利要求1：行为链风险传播治理方法

**权利要求要点**: 有向图建模 + 贝叶斯风险传播 + 三级硬门控 + 反事实分析

| 技术特征 | 代码文件 | 关键函数/类 | 实验证据 |
|---------|---------|------------|---------|
| S1. 有向图建模 | `backend/app/shield/agent_behavior_graph.py` | `AgentBehaviorGraph`, `BehaviorNode`, `BehaviorEdge` | 消融实验: local-only BLOCK Recall 16.67% vs chain-aware 75.00% |
| S2. 贝叶斯风险传播 | `backend/app/shield/agent_behavior_graph.py` | `compute_risk_propagation()` | 消融实验: w/o chain propagation BLOCK Recall 8.33% |
| S3. 三级门控决策 | `backend/app/shield/v3_engine.py` | `_action_for_score()`, `process_tool_call()` | SCI-600基线对比表 (Table 3.1) |
| S4. 反事实分析 | `backend/app/shield/v3_engine.py` | `_counterfactual_whatif()`, `_BranchTree` | 消融实验: w/o future branch 指标不变 |

**实验数据文件**:
- `benchmark/results/sci_baseline_table.md` - SCI-600基线对比
- `benchmark/results/semireal_baseline_table.md` - Semi-Real-150基线对比
- `benchmark/results/ablation_semireal_report.json` - 消融实验报告

**测试用例文件**:
- `backend/tests/test_v3_engine.py` - V3引擎单元测试
- `backend/tests/test_semireal_benchmark.py` - 半真实评测测试

---

### 权利要求2：MCP协议安全检测方法

**权利要求要点**: 工具描述验证 + 协议威胁检测 + 风险放大建模 + 级联深度追踪

| 技术特征 | 代码文件 | 关键函数/类 | 实验证据 |
|---------|---------|------------|---------|
| S1. 多层次工具验证 | `backend/app/security/tool_validator.py` | `ToolDescriptionValidator.validate()`, `_validate_structure()`, `_validate_semantic()`, `_validate_safety()` | 工具验证测试用例 |
| S2. 有状态协议检测 | `backend/app/security/mcp_detector.py` | `MCPAttackDetector`, `register_tool()`, `analyze_tool_call()` | MCP安全测试用例 |
| S3. 风险放大建模 | `backend/app/security/mcp_detector.py` | `_compute_amplification()` | 研究数据: 23%-41%放大率 |
| S4. 级联深度追踪 | `backend/app/security/mcp_detector.py` | `_compute_cascade_depth()` | cascade_threshold=3 |

**实验数据文件**:
- `docs/MCP_SECURITY.md` - MCP安全模块文档
- `benchmark/test_cases/` - 测试用例集

**关键常量**:
- `DEFAULT_AMPLIFICATION_FACTOR = 0.32` (23%-41%范围中点)
- `MAX_AMPLIFICATION_FACTOR = 0.41`
- `CRITICAL_CASCADE_DEPTH = 3`

---

### 权利要求3：多智能体级联攻击防御方法

**权利要求要点**: 跨Agent风险追踪 + 三种级联模式检测 + SHA-256审计 + 统一审计视图

| 技术特征 | 代码文件 | 关键函数/类 | 实验证据 |
|---------|---------|------------|---------|
| S1. 跨Agent风险追踪 | `backend/app/shield/agent_behavior_graph.py` | `add_tool_call_as_node()`, `add_edge()` (invokes/data_flow边类型) | 多Agent委托风险场景测试 |
| S2. 级联攻击模式检测 | `backend/app/shield/agent_behavior_graph.py` | `get_critical_nodes()`, `compute_risk_propagation()` | 消融实验: critical_node_count |
| S3. SHA-256审计链 | `backend/app/shield/v3_audit_logger.py` | `V3AuditLogger`, `log()`, `export_chain()` | 审计日志完整性测试 |
| S4. 统一审计视图 | `backend/app/shield/v3_engine.py` | `export_chain()`, `get_governance_status()` | 行为链导出测试 |

**实验数据文件**:
- `benchmark/results/` 下的审计日志JSON文件
- `backend/tests/test_v3_engine.py` 中的审计相关测试

---

## 三、从属权利要求映射

### 权利要求4：节点属性限定

**引用**: 权利要求1
**技术特征**: 节点属性包括工具名称、输入参数、风险状态、继承风险值、放大器标志、链阶段、链位置

| 属性 | 代码位置 | 备注 |
|------|---------|------|
| `tool_name` | `BehaviorNode.tool_name` | 直接对应 |
| `tool_input` | `BehaviorNode.params_summary` | 脱敏后的参数摘要 |
| `risk_status` | `BehaviorNode.risk_status` | Enum: SAFE/LOW/MEDIUM/HIGH/CRITICAL |
| `inherited_risk` | `BehaviorNode.inherited_risk` | 风险传播计算结果 |
| `amplifier_detected` | `BehaviorNode.downstream_risk_amplified` | 布尔值 |
| `chain_stage` | 交底书描述 | 当前代码中未显式实现，属于权利要求扩展 |
| `chain_position` | 交底书描述 | 当前代码中未显式实现，属于权利要求扩展 |

**注意**: `chain_stage` 和 `chain_position` 在交底书中描述，但当前代码实现中未显式包含这两个字段。消融实验显示 "w/o chain propagation" 导致BLOCK Recall暴跌，证明链上下文是关键，但具体实现方式可能与权利要求描述略有差异。

---

### 权利要求5：衰减因子和计算公式

**引用**: 权利要求1
**技术特征**: 衰减因子0.5，公式 I(i) = Σ [R(j) × decay^(d(i,j))]

| 技术特征 | 代码位置 | 备注 |
|---------|---------|------|
| decay = 0.5 | `agent_behavior_graph.py` line 299: `inherited = current_risk * 0.5` | 硬编码在代码中 |
| 反向BFS遍历 | `compute_risk_propagation()` | 从叶子节点逆向传播 |
| 最短路径距离 | 当前实现使用直接父子关系 | 权利要求中的 `d(i,j)` 在当前实现中简化为1 |

---

### 权利要求6：语义攻击检测类型

**引用**: 权利要求2
**技术特征**: 7类语义攻击检测

| 攻击类型 | 代码位置 | 正则模式名称 |
|---------|---------|------------|
| 权限诉求 | `tool_validator.py` | `authority_appeal` |
| 紧迫性操纵 | `tool_validator.py` | `urgency_manipulation` |
| 指令覆盖 | `tool_validator.py` | `instruction_override` |
| 角色劫持 | `tool_validator.py` | `role_reassignment` |
| 模板注入 | `tool_validator.py` | `template_injection` |
| 链垄断 | `tool_validator.py` | `chain_monopolization` |
| 虚假能力声明 | `tool_validator.py` | `false_capability` |

---

### 权利要求7：安全扫描类型

**引用**: 权利要求2
**技术特征**: 5类安全扫描

| 扫描类型 | 代码位置 | 正则模式名称 |
|---------|---------|------------|
| 凭证访问 | `tool_validator.py` | `credential_access` |
| 数据外泄 | `tool_validator.py` | `data_exfiltration` |
| 破坏性操作 | `tool_validator.py` | `destructive_operation` |
| 权限提升 | `tool_validator.py` | `privilege_escalation` |
| 嵌套参数注入 | `tool_validator.py` | `_scan_parameter_descriptions()` |

---

### 权利要求8：描述净化

**引用**: 权利要求2
**技术特征**: 输出安全描述副本，移除注入标记

| 技术特征 | 代码位置 | 备注 |
|---------|---------|------|
| 净化函数 | `tool_validator.py` `_sanitize_description()` | 移除chat template注入标记和指令覆盖尝试 |
| 输出安全副本 | `ToolValidationResult.sanitized_description` | 返回清洗后的描述 |

---

### 权利要求9：半真实Trace数据生成方法

**引用**: 独立权利要求
**技术特征**: 真实日志提取 + 合成风险注入 + 多步骤Trace + 三级标注

| 技术特征 | 代码文件 | 备注 |
|---------|---------|------|
| 真实日志提取 | `benchmark/generate_semireal_traces.py` | 从Agent调用模式中提取 |
| 合成风险注入 | `benchmark/generate_semireal_traces.py` | 基于场景模板生成 |
| 多步骤Trace | `benchmark/test_cases/test_cases_semireal_150.json` | 150条Trace, 405步骤 |
| 三级标注 | `benchmark/evaluate_semireal.py` | ALLOW/HUMAN_REVIEW/BLOCK |

---

### 权利要求10：场景模板库

**引用**: 权利要求9
**技术特征**: 9类场景模板

| 场景类型 | 数据文件 | 测试覆盖 |
|---------|---------|---------|
| 正常业务查询 | `test_cases_semireal_150.json` | 20条Trace |
| 正常报告生成 | `test_cases_semireal_150.json` | 20条Trace |
| 仅敏感查询 | `test_cases_semireal_150.json` | 20条Trace |
| 敏感查询后导出 | `test_cases_semireal_150.json` | 20条Trace |
| 敏感查询后压缩发送 | `test_cases_semireal_150.json` | 20条Trace |
| 权限提升 | `test_cases_semireal_150.json` | 15条Trace |
| 审计日志绕过 | `test_cases_semireal_150.json` | 15条Trace |
| 批量删除 | `test_cases_semireal_150.json` | 10条Trace |
| 多智能体委托风险 | `test_cases_semireal_150.json` | 10条Trace |

---

### 权利要求11：系统权利要求

**引用**: 独立权利要求
**技术特征**: 6个系统模块

| 模块 | 代码文件 | 备注 |
|------|---------|------|
| 行为链建模模块 | `backend/app/shield/agent_behavior_graph.py` | AgentBehaviorGraph |
| 风险传播引擎 | `backend/app/shield/agent_behavior_graph.py` | compute_risk_propagation() |
| 硬门控模块 | `backend/app/shield/v3_engine.py` | _action_for_score() |
| MCP协议安全模块 | `backend/app/security/` | tool_validator.py + mcp_detector.py |
| 审计日志模块 | `backend/app/shield/v3_audit_logger.py` | V3AuditLogger |
| 评测基准模块 | `benchmark/` | generate + evaluate |

---

### 权利要求12：MCP模块为预处理层

**引用**: 权利要求11
**技术特征**: MCP模块不修改V3核心代码

| 技术特征 | 证据 | 备注 |
|---------|------|------|
| 模块独立性 | `mcp_detector.py` 和 `tool_validator.py` 不导入V3核心模块 | 代码依赖关系验证 |
| 预处理层设计 | `routes.py` 中先调用validator/detector，再调用V3引擎 | API处理流程验证 |

---

## 四、证据完整性评估

### 4.1 强证据（充分支撑权利要求）

- 权利要求1: 行为链风险传播 - 消融实验证据充分
- 权利要求2: MCP协议安全 - 代码实现完整，测试覆盖
- 权利要求3: 级联攻击防御 - 代码实现和审计日志完整
- 权利要求9-10: 半真实Trace - 数据集文件完整
- 权利要求11-12: 系统权利要求 - 代码结构清晰

### 4.2 弱证据（需要补充）

- 权利要求4: `chain_stage` 和 `chain_position` 字段在当前代码中未显式实现
- 权利要求5: `d(i,j)` 最短路径距离在当前实现中简化为直接父子关系

### 4.3 建议

1. 在提交前确认 `chain_stage` 和 `chain_position` 是否需要在代码中显式实现
2. 考虑是否需要补充更详细的链阶段识别逻辑
3. 权利要求5中的公式描述可能需要与实际实现对齐

---

## 五、核心代码文件清单（需要保护）

| 文件路径 | 功能 | 保护级别 |
|---------|------|---------|
| `backend/app/shield/v3_engine.py` | V3核心治理引擎 | **CRITICAL** |
| `backend/app/shield/agent_behavior_graph.py` | 行为图建模与风险传播 | **CRITICAL** |
| `backend/app/security/mcp_detector.py` | MCP协议攻击检测器 | **CRITICAL** |
| `backend/app/security/tool_validator.py` | 工具描述验证器 | **CRITICAL** |
| `backend/app/shield/v3_audit_logger.py` | 防篡改审计日志 | **HIGH** |
| `benchmark/generate_semireal_traces.py` | 半真实Trace生成器 | **HIGH** |
| `benchmark/evaluate_semireal.py` | 半真实评测框架 | **MEDIUM** |
| `benchmark/ablation_semireal.py` | 消融实验框架 | **MEDIUM** |

---

*本映射表由专利材料Agent自动生成，仅供内部参考。*
