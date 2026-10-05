# AgentShield V3.3 专利提交材料包

**生成日期**: 2026-05-28
**提交类型**: 发明专利申请
**技术领域**: 人工智能安全 / 多智能体系统

---

## 一、材料包总览

### 1.1 核心提交材料

| 序号 | 文件名 | 文件类型 | 说明 | 状态 |
|------|--------|---------|------|------|
| 1 | 专利技术交底书_AgentShield.docx | Word文档 | 专利交底书主文档 | **已完成** |
| 2 | PATENT_DISCLOSURE_V3.md | Markdown | 交底书Markdown版本（内容与docx一致） | **已完成** |
| 3 | PATENT_SUPPLEMENT.md | Markdown | 补充材料（实验验证数据） | **已完成** |
| 4 | 附图1-4 | PNG/SVG | 4张技术附图 | **待制作** |

### 1.2 辅助材料（供代理机构参考）

| 序号 | 文件名 | 文件类型 | 说明 | 状态 |
|------|--------|---------|------|------|
| 5 | PATENT_SUBMISSION_CHECKLIST.md | Markdown | 提交前检查清单 | **已完成** |
| 6 | PATENT_CLAIM_EVIDENCE_MAP.md | Markdown | 权利要求-证据映射表 | **已完成** |
| 7 | PATENT_FIGURES_LIST.md | Markdown | 附图清单及说明 | **已完成** |
| 8 | PATENT_SUBMISSION_PACKAGE.md | Markdown | 本文件（材料包清单） | **已完成** |

---

## 二、材料详细说明

### 2.1 专利技术交底书

**文件**: `docs/专利技术交底书_AgentShield.docx`

**内容结构**:
1. 发明名称
2. 技术领域
3. 背景技术（5项现有技术缺陷）
4. 发明内容（6个核心创新点）
5. 技术效果（量化实验数据）
6. 附图说明（4张图）
7. 具体实施方式（4种部署形态）
8. 权利要求书（3项独立权利要求 + 9项从属权利要求）
9. 附录（术语定义、参考文献、代码文件索引）

**页数**: 约25-30页（含附图）

### 2.2 补充材料

**文件**: `docs/PATENT_SUPPLEMENT.md`

**内容结构**:
1. 实验验证数据（SCI-600、Semi-Real-150数据集规格）
2. 性能对比结果（基线对比表）
3. 消融实验证据（5种配置对比）
4. 技术效果量化证明
5. 代码复现说明
6. 权利要求支持映射

### 2.3 附图

**当前状态**: ASCII文本格式，需要转换为标准图形格式

**目标格式**:
- PNG: 300dpi, 适合打印
- SVG: 矢量格式，适合缩放

**附图清单**:
1. 图1: AgentShield V3.3系统架构图
2. 图2: 行为链风险传播示意图
3. 图3: MCP协议安全检测流程图
4. 图4: 半真实Trace Benchmark数据生成流程

---

## 三、文件获取路径

### 3.1 核心文件路径

```
D:/ZYY Project/AgentShield_V3/
├── docs/
│   ├── 专利技术交底书_AgentShield.docx    # 交底书主文档
│   ├── PATENT_DISCLOSURE_V3.md            # Markdown版本
│   ├── PATENT_SUPPLEMENT.md               # 补充材料
│   ├── PATENT_SUBMISSION_CHECKLIST.md     # 检查清单
│   ├── PATENT_CLAIM_EVIDENCE_MAP.md       # 权利要求映射
│   ├── PATENT_FIGURES_LIST.md             # 附图清单
│   └── PATENT_SUBMISSION_PACKAGE.md       # 本文件
├── backend/
│   └── app/
│       ├── shield/
│       │   ├── v3_engine.py               # V3核心引擎
│       │   ├── agent_behavior_graph.py    # 行为图建模
│       │   └── v3_audit_logger.py         # 审计日志
│       └── security/
│           ├── mcp_detector.py            # MCP检测器
│           └── tool_validator.py          # 工具验证器
├── benchmark/
│   ├── generate_semireal_traces.py        # Trace生成器
│   ├── evaluate_semireal.py               # 评测框架
│   ├── ablation_semireal.py               # 消融实验
│   └── results/                           # 实验结果
└── backend/tests/
    ├── test_v3_engine.py                  # 引擎测试
    └── test_semireal_benchmark.py         # 评测测试
```

---

## 四、文件安全分级

### 4.1 不要上传到公开GitHub的文件

| 文件 | 原因 | 保护级别 |
|------|------|---------|
| `docs/专利技术交底书_AgentShield.docx` | 专利交底书，包含完整技术方案 | **CRITICAL** |
| `docs/PATENT_DISCLOSURE_V3.md` | 专利交底书Markdown版本 | **CRITICAL** |
| `docs/PATENT_SUPPLEMENT.md` | 专利补充材料 | **CRITICAL** |
| `docs/PATENT_*.md` | 所有专利相关文档 | **CRITICAL** |
| `backend/app/shield/v3_engine.py` | 核心算法实现 | **HIGH** |
| `backend/app/shield/agent_behavior_graph.py` | 核心算法实现 | **HIGH** |
| `backend/app/security/mcp_detector.py` | 核心算法实现 | **HIGH** |
| `backend/app/security/tool_validator.py` | 核心算法实现 | **HIGH** |
| `backend/app/shield/v3_audit_logger.py` | 审计链实现 | **HIGH** |
| `benchmark/generate_semireal_traces.py` | 数据生成算法 | **MEDIUM** |
| `benchmark/results/` | 实验结果数据 | **MEDIUM** |

### 4.2 可以公开的文件

| 文件 | 原因 | 备注 |
|------|------|------|
| `README.md` | 项目介绍，已脱敏 | 注意移除具体公式和阈值 |
| `CHANGELOG.md` | 版本记录 | 无核心技术泄露 |
| `requirements.txt` | 依赖列表 | 标准Python包 |
| `Dockerfile` | 部署配置 | 标准配置 |
| `frontend/index.html` | 前端界面 | UI代码，无核心算法 |
| `docs/USER_GUIDE.md` | 用户指南 | 使用说明，非技术实现 |

### 4.3 当前.gitignore状态

当前 `.gitignore` 已包含 `docs/` 规则，`docs/` 目录下的文件不会被提交到公开仓库。

**已确认被排除**:
- 所有 `docs/` 目录下的文件
- `__pycache__/`
- `*.pyc`
- `.env`
- `dist/`
- `build/`

---

## 五、代理机构提交指引

### 5.1 提交材料清单

请将以下材料打包提交给代理机构：

```
AgentShield_V3_Patent_Submission/
├── 01_交底书/
│   ├── 专利技术交底书_AgentShield.docx
│   └── PATENT_DISCLOSURE_V3.md
├── 02_补充材料/
│   └── PATENT_SUPPLEMENT.md
├── 03_附图/
│   ├── 图1_系统架构图.png
│   ├── 图2_行为链风险传播示意图.png
│   ├── 图3_MCP协议安全检测流程图.png
│   └── 图4_半真实Trace数据生成流程.png
├── 04_辅助材料/
│   ├── PATENT_SUBMISSION_CHECKLIST.md
│   ├── PATENT_CLAIM_EVIDENCE_MAP.md
│   └── PATENT_FIGURES_LIST.md
└── 00_README.txt
```

### 5.2 代理机构沟通要点

1. **技术领域**: 人工智能安全 / 多智能体系统
2. **申请类型**: 发明专利
3. **核心创新点**:
   - 行为链风险传播建模（贝叶斯网络）
   - 三级硬门控阻断机制
   - MCP协议安全检测（V3.3新增）
   - 半真实Trace Benchmark
   - 多Agent级联攻击防御
4. **权利要求**: 3项独立权利要求 + 9项从属权利要求
5. **附图**: 4张技术附图（待制作）

### 5.3 预期时间线

| 阶段 | 时间 | 负责人 |
|------|------|--------|
| 材料整理完成 | 2026-05-28 | 专利材料Agent |
| 附图制作完成 | 提交前7天 | 待定 |
| 代理机构审核 | 提交前5天 | 代理机构 |
| 正式提交 | 待定 | 代理机构 |

---

## 六、新颖性风险提示

### 6.1 已公开内容

| 内容 | 公开渠道 | 风险评估 |
|------|---------|---------|
| README.md 技术描述 | GitHub公开仓库 | **MEDIUM** - 高层描述，无具体公式 |
| WHITEPAPER.md 实验数据 | 待确认 | **HIGH** - 如已公开需评估影响 |
| ONE_PAGER_CN.md 核心能力 | 待确认 | **LOW** - 仅能力列表 |

### 6.2 建议措施

1. **提交前**: 确认WHITEPAPER.md是否已对外发布
2. **提交前**: 从README.md中移除具体公式和阈值
3. **提交后**: 在专利申请号获得后再考虑公开技术白皮书

---

## 七、联系方式

- **项目负责人**: ZYY
- **技术文档**: `D:/ZYY Project/AgentShield_V3/docs/`
- **代码仓库**: `D:/ZYY Project/AgentShield_V3/`

---

## 八、附录：文件MD5校验

提交前请确认以下文件的完整性：

| 文件 | MD5 | 备注 |
|------|-----|------|
| 专利技术交底书_AgentShield.docx | 待计算 | 提交前计算 |
| PATENT_DISCLOSURE_V3.md | 待计算 | 提交前计算 |
| PATENT_SUPPLEMENT.md | 待计算 | 提交前计算 |

---

*本文件由专利材料Agent自动生成，仅供内部参考。*
