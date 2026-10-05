# AgentShield V3 API 文档

> 多主体行为链风险治理系统 — ASF-BGT Framework（端口 8090）

**版本**: 3.0.0  
**基础路径**: `/api/agent`  
**限流**: 50次/分钟（全局）  
**认证**: 无

---

## 目录

- [POST /behavior_chain](#post-behavior_chain) — 多Agent行为链追踪
- [GET /registry](#get-registry) — Agent注册表
- [POST /evaluate_intent](#post-evaluate_intent) — 意图一致性评估

---

## POST /behavior_chain

对多Agent协作的行为链进行全链路风险评估，识别违规步骤。

### 请求

**URL**: `POST /api/agent/behavior_chain`

**Content-Type**: `application/json`

**Body 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agents` | `object[]` | ✅ | Agent行为列表 |

**agents 数组元素**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | `string` | ❌ | Agent标识，默认 `agent_0`, `agent_1`... |
| `action` | `string` | ✅ | 执行的动作 |
| `target` | `string` | ❌ | 动作目标 |
| `input` | `object` | ❌ | 输入参数 |

### 请求示例

```json
{
  "agents": [
    {
      "id": "TCM-Cognition",
      "action": "查询患者病历",
      "target": "medical_database",
      "input": {"patient_id": "P12345"}
    },
    {
      "id": "Risk-Analysis",
      "action": "生成风险报告",
      "target": "report_service",
      "input": {"report_type": "weekly"}
    },
    {
      "id": "Content-Audit",
      "action": "审核报告内容",
      "target": "audit_queue",
      "input": {"content": "敏感数据泄露"}
    }
  ]
}
```

### 响应

**Content-Type**: `application/json`

**Body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `chain_id` | `string` | 行为链唯一标识（UUID） |
| `steps` | `object[]` | 各步骤分析结果 |
| `steps[].step_id` | `number` | 步骤序号 |
| `steps[].agent_id` | `string` | Agent标识 |
| `steps[].action` | `string` | 执行动作 |
| `steps[].target` | `string` | 动作目标 |
| `steps[].input_summary` | `string` | 输入摘要（前50字符） |
| `steps[].risk_score` | `number` | 该步骤风险评分（0~1） |
| `steps[].decision` | `string` | 该步骤决策：`allow` / `review` / `block` |
| `risk_score` | `number` | 整体风险评分（0~1，取最大值） |
| `verdict` | `string` | 整体裁决：`allow` / `review` / `block` |
| `violations` | `object[]` | 违规步骤列表 |

### 决策阈值

| 风险评分 | 决策 |
|----------|------|
| ≤ 0.6 | `allow` |
| 0.6 ~ 0.85 | `review` |
| > 0.85 | `block` |

### 响应示例

```json
{
  "chain_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "steps": [
    {
      "step_id": 1,
      "agent_id": "TCM-Cognition",
      "action": "查询患者病历",
      "target": "medical_database",
      "input_summary": "{'patient_id': 'P12345'}",
      "risk_score": 0.12,
      "decision": "allow"
    },
    {
      "step_id": 2,
      "agent_id": "Risk-Analysis",
      "action": "生成风险报告",
      "target": "report_service",
      "input_summary": "{'report_type': 'weekly'}",
      "risk_score": 0.08,
      "decision": "allow"
    },
    {
      "step_id": 3,
      "agent_id": "Content-Audit",
      "action": "审核报告内容",
      "target": "audit_queue",
      "input_summary": "{'content': '敏感数据泄露'}",
      "risk_score": 0.72,
      "decision": "review"
    }
  ],
  "risk_score": 0.72,
  "verdict": "review",
  "violations": [
    {
      "step": 3,
      "reason": "审核报告内容 to audit_queue risk=0.72"
    }
  ]
}
```

---

## GET /registry

获取所有已注册的Agent类型及其能力描述。

### 请求

**URL**: `GET /api/agent/registry`

**Query 参数**: 无

### 响应

**Content-Type**: `application/json`

**Body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `agents` | `object[]` | Agent列表 |
| `agents[].type` | `string` | Agent类型标识 |
| `agents[].description` | `string` | 功能描述 |
| `agents[].capabilities` | `string[]` | 支持的能力列表 |
| `total` | `number` | 注册Agent总数 |

### 响应示例

```json
{
  "agents": [
    {
      "type": "TCM-Cognition",
      "description": "中医辨证推理Agent",
      "capabilities": ["症状分析", "证型判断", "方剂推荐"]
    },
    {
      "type": "Visual-Perception",
      "description": "3D视觉感知Agent",
      "capabilities": ["点云处理", "碰撞检测", "路径规划"]
    },
    {
      "type": "Risk-Analysis",
      "description": "风险分析Agent",
      "capabilities": ["漏洞扫描", "威胁评估", "缓解建议"]
    },
    {
      "type": "Content-Audit",
      "description": "内容审计Agent",
      "capabilities": ["幻觉检测", "RAG溯源", "合规检查"]
    },
    {
      "type": "Narrative-Generation",
      "description": "叙事生成Agent",
      "capabilities": ["市场叙事", "KOL传播", "情绪放大"]
    },
    {
      "type": "Market-Regulation",
      "description": "市场监管Agent",
      "capabilities": ["干预策略", "风险预警", "效果评估"]
    },
    {
      "type": "Hypothesis-Engine",
      "description": "假设引擎Agent",
      "capabilities": ["假设生成", "KG约束", "贝叶斯验证"]
    },
    {
      "type": "Lab-Automation",
      "description": "实验自动化Agent",
      "capabilities": ["DoE设计", "FMEA分析", "结果统计"]
    }
  ],
  "total": 8
}
```

### Agent能力矩阵

| Agent | 核心能力 |
|-------|----------|
| TCM-Cognition | 症状分析、证型判断、方剂推荐 |
| Visual-Perception | 点云处理、碰撞检测、路径规划 |
| Risk-Analysis | 漏洞扫描、威胁评估、缓解建议 |
| Content-Audit | 幻觉检测、RAG溯源、合规检查 |
| Narrative-Generation | 市场叙事、KOL传播、情绪放大 |
| Market-Regulation | 干预策略、风险预警、效果评估 |
| Hypothesis-Engine | 假设生成、KG约束、贝叶斯验证 |
| Lab-Automation | DoE设计、FMEA分析、结果统计 |

---

## POST /evaluate_intent

基于 Theory of Mind 评估Agent声明目标与实际行为的一致性，检测欺骗风险。

### 请求

**URL**: `POST /api/agent/evaluate_intent`

**Content-Type**: `application/json`

**Body 参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `agent_id` | `string` | ❌ | Agent标识，默认 `"unknown"` |
| `stated_goal` | `string` | ✅ | Agent声明的目标 |
| `observed_actions` | `array` | ✅ | 观察到的实际行动列表 |

### 请求示例

```json
{
  "agent_id": "Narrative-Generation",
  "stated_goal": "生成市场分析报告，查询相关数据",
  "observed_actions": [
    "查询销售数据",
    "导出客户信息到外部服务器",
    "发送数据到第三方API"
  ]
}
```

### 响应

**Content-Type**: `application/json`

**Body 参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `agent_id` | `string` | 输入的Agent标识 |
| `stated_goal` | `string` | 输入的声明目标 |
| `intent_alignment` | `number` | 意图一致性评分（0~1，1为完全一致） |
| `deception_score` | `number` | 欺骗风险评分（0~1，0为无风险） |
| `reasoning` | `string` | 评估推理说明 |

### 评分说明

| 评分维度 | 计算逻辑 |
|----------|----------|
| `intent_alignment` | 目标关键词匹配 × 0.6 + (1 - 行动风险) × 0.4 |
| `deception_score` | 行动风险 × 0.7 - 目标匹配度 × 0.3 |

**目标关键词**: 查询、分析、评估、生成、优化  
**行动风险关键词**: 删除、导出、发送、修改、取消

### 响应示例

```json
{
  "agent_id": "Narrative-Generation",
  "stated_goal": "生成市场分析报告，查询相关数据",
  "intent_alignment": 0.512,
  "deception_score": 0.437,
  "reasoning": "目标表述包含2个操作类关键词，观察到3个行动，其中2个存在风险"
}
```

### 欺骗风险阈值

| 欺骗评分 | 风险等级 | 说明 |
|----------|----------|------|
| < 0.3 | 低 | 行为与目标基本一致 |
| 0.3 ~ 0.6 | 中 | 存在一定偏差，需关注 |
| > 0.6 | 高 | 高度可疑，建议阻断 |

---

## 其他端点（补充）

### GET /health

健康检查（独立于 `/api/agent` 前缀）。

```json
{
  "status": "ok",
  "version": "3.0.0",
  "engine": "AgentShield_V3",
  "framework": "ASF-BGT",
  "port": 8090
}
```

### GET /api/status/{session_id}

获取指定会话的治理状态。

**响应**: V3ShieldEngine 的治理状态对象，包含 `risk_threshold`、`branch_count`、`gate_count` 等。

### GET /api/behavior_graph/{session_id}

获取指定会话的行为图谱。

**响应**: 行为图谱的字典表示（依赖 `to_graph_dict()` 方法）。

---

## 通用错误响应

所有端点在出错时返回标准HTTP状态码和以下JSON结构：

```json
{
  "detail": "错误描述"
}
```

| HTTP状态码 | 说明 |
|-----------|------|
| `400` | 请求参数错误 |
| `404` | Session/资源不存在 |
| `429` | 触发限流（60/minute for health, 50/minute for evaluate） |
| `500` | 服务器内部错误（引擎异常时降级放行） |

---

## 技术栈

- **框架**: FastAPI
- **限流**: slowapi (每分钟限制)
- **引擎**: V3ShieldEngine（ASF-BGT Framework）
  - 引擎加载失败时自动降级为 DummyEngine（内存模式）
- **依赖注入**: 会话级引擎存储 `_engine_store`