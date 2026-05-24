# 智能质量管理平台（QMS）产品需求文档

**版本**: v1.2
**日期**: 2026-05-19
**状态**: 草案（基于ISO 9001:2015和IATF 16949:2016完善，AI模块深化）

---

## 目录

1. [产品概述与定位](#1-产品概述与定位)
2. [核心模块规格](#2-核心模块规格)
3. [技术架构](#3-技术架构)
4. [数据模型设计](#4-数据模型设计)
5. [权限与安全模型](#5-权限与安全模型)
6. [UI/UX规范](#6-uiux规范)
7. [实施路线图](#7-实施路线图)
8. [关键风险与缓解](#8-关键风险与缓解)
9. [测试策略](#9-测试策略)
10. [附录](#10-附录)

---

## 1. 产品概述与定位

### 1.1 产品愿景

打造以"知识库 + 智能推荐"为核心差异化的新一代智能质量管理平台，实现质量管理的知识驱动与智能化升级。

### 1.2 产品定位

区别于市场上以**流程管理**为核心的传统QMS产品（如Opcenter Quality、QAD EQMS、QT9 QMS、云质QMS、格创东智QMS等），本产品聚焦以下三大差异化价值主张：

| 维度 | 传统QMS | 本产品 |
|------|---------|--------|
| 核心理念 | 流程驱动 | 知识驱动 |
| FMEA管理 | 静态表单 | 知识图谱动态关联 |
| 经验复用 | 人工检索 | LLM智能推荐 |
| 变更管理 | 手动追溯 | 图谱影响分析 |
| 标准报告 | 模板填空 | AI辅助生成 |

### 1.3 目标用户

- **质量工程师**: FMEA编制、控制计划制定、SPC分析
- **工艺工程师**: 过程设计与优化、失效模式分析
- **质量经理**: 质量KPI监控、CAPA审批、质量决策
- **生产管理人员**: 质量数据监控、异常响应
- **采购/SQE工程师**: 供应商准入、来料检验、供应商审核与绩效评价
- **客户质量工程师(CQE)**: 客诉处理、RMA分析、客户质量评审
- **研发工程师**: 新产品FMEA参考、经验复用

### 1.4 相关方及其需求

基于 ISO 9001:2015 §4.2 的要求，识别以下相关方及其对系统的期望：

| 相关方类别 | 相关方 | 核心期望 |
|-----------|--------|---------|
| 内部 | 最高管理者 | 质量目标达成率可视化、管理评审数据汇总、不良质量成本追踪 |
| 内部 | 质量经理 | FMEA完整性与合规性、CAPA闭环率、审核结果与趋势 |
| 内部 | 质量/工艺工程师 | FMEA编辑效率、历史经验复用、SPC实时监控与异常告警 |
| 内部 | 生产管理人员 | 过程能力可视化、异常告警、不合格品处理流程 |
| 内部 | 采购/SQE | 供应商绩效看板、IQC检验效率、SCAR跟踪闭环 |
| 内部 | CQE | 客诉处理效率、RMA分析、客户PPM趋势 |
| 外部 | 客户(OEM) | 质量绩效透明化（PPM/CPK）、8D报告时效性、CSR满足 |
| 外部 | 供应商 | 清晰的SCAR要求、协同改进计划、绩效评价透明 |
| 外部 | 认证机构(IATF审核员) | 符合IATF 16949条款要求的证据链、可追溯性 |
| 外部 | 监管机构 | 产品安全合规、召回可追溯性 |

### 1.5 核心能力

1. **结构化知识管理**: 基于图数据库的FMEA知识图谱（DFMEA + PFMEA），覆盖系统项/设计参数/接口/工序/功能/失效/原因/影响/控制措施等节点的系统化关联
2. **智能推荐引擎**: 基于历史数据的FMEA自动推荐、SPC异常关联分析、相似案例语义搜索
3. **AI辅助生成**: LLM辅助FMEA初稿生成、8D报告自动草拟
4. **变更影响分析**: 当某一过程或控制措施变更时，自动追溯影响范围
5. **多系统集成**: 与MES、PLM等系统深度集成，打通数据孤岛

---

## 2. 核心模块规格

### 2.1 仪表盘 (Dashboard)

#### 2.1.1 功能描述
提供面向不同角色的质量KPI可视化主页，支持各级管理者快速掌握质量状况。

#### 2.1.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 质量KPI卡片 | P0 | 综合缺陷率、CPK/PPK、开放CAPA数量、FMEA覆盖数、来料合格率、客户PPM、供应商PPM |
| 趋势图 | P0 | 7日/30日/季度质量趋势折线图 |
| 近期预警 | P0 | SPC异常告警、超期CAPA提醒、关键特性偏移通知 |
| 任务列表 | P1 | 待审批FMEA、待处理CAPA、即将到期任务 |
| 车间地图 | P2 | 多工厂/多产线质量热力图 |
| 自定义看板 | P3 | 拖拽式自定义KPI布局 |
| 产品线KPI明细 | P1 | 按产品线维度的下钻统计（缺陷率/CPK/CAPA/FMEA覆盖数），支持产品线对比柱状图 |
| 产品线健康度热力图 | P2 | 以产品线×质量维度热力图展示风险分布，一目了然识别问题产品线 |

#### 2.1.3 数据来源
- 缺陷率: MES生产过程数据
- CPK/PPK: SPC统计分析模块
- CAPA统计: CAPA/8D模块
- FMEA统计: FMEA管理模块
- 来料合格率: IQC来料检验模块
- 客户PPM: 客户质量管理模块
- 产品线维度数据: 以上所有数据均可按产品线下钻（DC-DC转换器/PCB焊接组件/注塑外壳等）

### 2.2 质量目标管理

#### 2.2.1 功能描述
支撑 ISO 9001:2015 §6.2 要求的质量目标设定、展开、监视和沟通，实现公司级→产品线级→过程级的三级目标树管理，并将目标达成情况自动汇总为管理评审输入。

#### 2.2.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 目标设定与展开 | P0 | 公司级→产品线级→过程级三级目标树，支持层级分解与对齐，每个目标关联责任人和完成期限 |
| 目标监控仪表盘 | P0 | 各层级目标达成率实时仪表盘，支持红黄绿灯状态标识、达成趋势折线图 |
| 目标沟通 | P1 | 目标变更通知、定期目标达成报告自动推送至相关责任人 |
| 目标评审 | P1 | 目标评审记录、调整审批流程，目标历史版本追溯 |
| 管理评审汇总 | P1 | 质量目标达成情况自动汇总为管理评审输入数据包 |

#### 2.2.3 数据来源
- 目标定义: 手动设定 + 历史基线自动推荐
- 达成率计算: 仪表盘KPI数据、SPC过程能力数据、供应商/客户质量数据
- 趋势对比: 同比/环比自动计算

### 2.3 FMEA管理 + 知识图谱 (DFMEA & PFMEA)

#### 2.2.1 功能概述
FMEA模块统一管理DFMEA（设计失效模式与影响分析）和PFMEA（过程失效模式与影响分析），两者共享版本管理、知识图谱可视化模板、AI推荐引擎等基础能力，同时在编辑器形态、评分标准、数据模型上保持独立。

| 维度 | DFMEA | PFMEA |
|------|-------|-------|
| 分析对象 | 产品设计/零部件/系统 | 制造过程/工序 |
| 分析阶段 | 产品设计阶段 | 过程设计阶段 |
| 核心粒度 | 功能→失效→设计措施 | 工序→功能→失效→控制措施 |
| 评分标准 | 严重度(S)面向最终用户 | 严重度(S)面向过程/产品 |
| 图谱重心 | 设计参数/物料/功能树 | 工序流/控制特性/检验点 |
| 典型用户 | 研发/设计工程师 | 工艺/质量工程师 |

#### 2.2.2 DFMEA 功能规格

**功能描述**
提供面向产品设计阶段的DFMEA结构化编辑，支持从系统层级向零部件层级逐级展开的功能分析与失效模式管理。

**功能规格**

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| DFMEA编辑器 | P0 | 系统→子系统→零部件三级展开，功能→失效模式→原因→设计措施的逐级编辑，支持RPN/AP自动计算 |
| 功能树分析 | P0 | 产品功能树结构编辑器，支持从产品总功能逐级分解至零部件功能，可视化展示功能层级关系 |
| 设计参数矩阵 | P1 | 将DFMEA中的失效原因关联到具体设计参数（尺寸、公差、材料牌号、热处理方式等），支持参数变更对FMEA影响自动标注 |
| 接口失效分析 | P1 | 系统间/零部件间接口失效模式识别，支持P-diagram参数图输入 |
| 严重度评估 | P0 | 严重度(S)、频度(O)、探测度(D)三级评分（采用AIAG & VDA新版标准），自动RPN计算(S×O×D)，支持AP行动优先级判定 |
| 特殊特性标识 | P1 | 在DFMEA中自动标注关键特性(CC)和重要特性(SC)，与控制计划联动 |
| 产品安全特性管理 | P0 | 识别产品安全相关特性（IATF 16949 §4.4.1.2），DFMEA特殊批准流程，供应链安全要求传递 |
| 设计验证关联 | P2 | DFMEA中的控制措施与DVP(Design Verification Plan)条目绑定，验证结果反馈至FMEA评分更新 |
| 版本管理 | P1 | DFMEA版本历史、变更对比、差异高亮、审批流程 |
| DFMEA模板库 | P1 | 行业标准DFMEA模板导入（VDA、AIAG标准格式），支持企业级模板定制 |
| 批量导入/导出 | P2 | 支持xls/xlsx/Excel标准格式导入导出，兼容主流OEM DFMEA格式 |
| 多人协同编辑 | P2 | 并行编辑、批注回复、变更冲突合并 |

**DFMEA特有字段**

| 字段 | 说明 |
|------|------|
| 系统层级 | 系统/子系统/零部件（可定义最多5级） |
| 功能ID | 按功能树层级编码，如 F.01.02.01 |
| 设计特性 | 关联的图纸编号、尺寸编号、材料规格 |
| 接口类型 | 机械/电气/软件/液压/气动/热管理等 |
| 特殊特性分类 | CC(关键)/SC(重要)/OS(一般) |
| DVP编号 | 关联的设计验证计划条目号 |
| 供应商影响 | 是否涉及外协件/供应商设计责任 |

#### 2.2.3 DFMEA 数据模型（图数据库扩展）

在通用FMEA图模型基础上，DFMEA引入以下特有节点和关系：

```
Node: SystemItem (系统项)
  Properties: item_id, name, level, parent_item_id, part_number, drawing_number

Node: DesignParameter (设计参数)
  Properties: param_id, name, value, tolerance, unit, specification

Node: Interface (接口)
  Properties: interface_id, name, type(mechanical/electrical/software/hydraulic), 
              from_system, to_system

Node: DVPTask (设计验证任务)
  Properties: dvp_id, name, test_condition, sample_size, acceptance_criteria, status, result

// DFMEA 特有关系
(:SystemItem)-[:PERFORMS_FUNCTION]->(:Function)
(:Function)-[:SPECIFIED_BY]->(:DesignParameter)
(:FailureCause)-[:CAUSED_BY_DESIGN]->(:DesignParameter)   // 失效原因追溯至设计参数
(:SystemItem)-[:HAS_INTERFACE]->(:Interface)               // 接口定义
(:Interface)-[:HAS_INTERFACE_FAILURE]->(:FailureMode)     // 接口失效模式
(:ControlMeasure)-[:VERIFIED_BY]->(:DVPTask)               // 控制措施与DVP绑定
(:DVPTask)-[:RESULT_UPDATES]->(:FailureMode)               // DVP结果反馈更新失效评分
```

#### 2.2.4 PFMEA 功能规格

**功能描述**
提供面向制造过程的PFMEA结构化编辑，从工序级开始逐级向下展开失效模式分析，并与控制计划、SPC深度关联。

**功能规格**

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| PFMEA编辑器 | P0 | 过程(OP)/功能/失效模式/原因/影响/控制措施的逐级编辑，支持RPN/AP自动计算 |
| 工序流编辑 | P0 | 工序流程图可视化编辑，支持顺序调整、并行工序标注、操作编号(OP10/OP20等) |
| 控制计划联动 | P0 | PFMEA中的控制措施可一键生成控制计划条目，控制计划变更自动回写FMEA |
| 特性矩阵表 | P1 | 工序编号×产品特性的矩阵表，标注过程特性(P)和产品特性(SC/CC) |
| 严重度评估 | P0 | 严重度(S)、频度(O)、探测度(D)三级评分（支持AIAG VDA新旧双标准），自动RPN计算(S×O×D)，AP行动优先级判定 |
| 风险优先级排序 | P1 | 按RPN/AP对失效模式进行优先级排序，高RPN项标红预警 |
| 版本管理 | P1 | PFMEA版本历史、变更对比、差异高亮、审批流程 |
| PFMEA模板库 | P1 | 行业标准PFMEA模板导入（VDA、AIAG标准格式），设备/工装/来料等分类模板 |
| 批量导入/导出 | P2 | 支持xls/xlsx/Excel标准格式导入导出，含特性矩阵表 |
| 产品安全控制 | P0 | 制造过程安全特性识别与控制（IATF 16949 §4.4.1.2），PFMEA特殊批准，反应计划（含顾客通知和升级流程） |
| 多人协同编辑 | P2 | 并行编辑、批注回复、变更冲突合并 |

**PFMEA特有字段**

| 字段 | 说明 |
|------|------|
| 工序编号 | OP10/OP20/OP30 … 按工艺路线排序 |
| 工序类型 | 加工/装配/检验/运输/存储 |
| 过程特性 | 过程参数（温度/压力/速度等），关联SPC监控点 |
| 产品特性 | 产品的尺寸/性能等特性，关联检验标准 |
| 控制方法 | 防错(Poka-Yoke)/SPC/首检/巡检/全检等 |
| 反应计划 | 超出控制限时的处理方案（隔离/返工/报废等） |

#### 2.2.5 知识图谱交互（通用）

```
图谱节点类型（颜色区分）:

【通用节点】
- 功能 (Function): 绿色  
- 失效模式 (FailureMode): 红色
- 失效原因 (FailureCause): 橙色
- 失效影响 (FailureEffect): 紫色
- 控制措施 (ControlMeasure): 青色

【DFMEA特有节点】
- 系统项 (SystemItem): 深蓝
- 设计参数 (DesignParameter): 棕色
- 接口 (Interface): 粉色

【PFMEA特有节点】
- 工序 (Process): 蓝色
- 产品 (Product): 灰色
```

**交互能力：**
- 力导向图布局（Force-directed），支持缩放/拖拽/框选
- 双击节点展开该节点的关联子图（展开深度可配置）
- 右键菜单：编辑/关联新节点/删除/查看详情/展开关联
- 筛选栏：按节点类型/风险等级(RPN范围)/工序/产品过滤
- 高亮路径：选中节点后高亮显示该节点到FMEA根节点的完整路径
- 保存视图：用户可将当前图谱视角保存为自定义视图
- 风险热力图模式：节点和关系按RPN值映射颜色深浅，直观展示风险分布

### 2.3 8D/CAPA工作流

#### 2.3.1 功能描述
支持8D（八步问题解决法）报告的结构化编制和CAPA（纠正与预防措施）的闭环管理。

#### 2.3.2 8D步骤

| 步骤 | 名称 | 功能 |
|------|------|------|
| D1 | 团队组建 | 录入团队成员、角色、职责 |
| D2 | 问题描述 | 5W2H结构化描述，关联FMEA失效模式 |
| D3 | 临时措施 | 遏制措施定义、责任人与期限 |
| D4 | 根因分析 | 鱼骨图/5Why分析工具，关联历史FMEA原因 |
| D5 | 永久措施 | 纠正措施定义、验证方案 |
| D6 | 实施验证 | 措施完成确认、效果跟踪 |
| D7 | 预防复发 | 系统化预防、FMEA更新触发 |
| D8 | 团队表彰 | 关闭确认、经验入库 |

#### 2.3.3 工作流状态

```
草稿 → D2问题描述 → D3临时措施 → D4根因分析 → D5永久措施 
→ D6实施验证 → D7预防复发 → D8关闭 → 已归档
```

每个状态转换需要指定角色审批。超时自动升级通知。

#### 2.3.4 AI辅助功能

- 根因分析时自动推荐历史相似FMEA失效原因
- D5永久措施推荐历史类似案例的有效控制措施
- D7自动提示需更新的相关FMEA条目

### 2.4 SPC控制图

#### 2.4.1 功能描述
提供过程统计控制（SPC）的实时监控图表和分析能力。

#### 2.4.2 图表类型

| 图表 | 适用场景 |
|------|---------|
| X-bar & R 控制图 | 连续变量，子组≥2 |
| X-bar & S 控制图 | 连续变量，子组≥10 |
| I-MR 控制图 | 单值-移动极差 |
| P 控制图 | 计数值-不合格品率 |
| C 控制图 | 计数值-缺陷数 |
| 直方图 | 过程能力分布 |
| 六合一过程能力图 | CPK/PPK综合分析 |

#### 2.4.3 判异规则 (8大判异准则)

1. 1点超出3σ控制限
2. 连续9点在中心线同一侧
3. 连续6点上升或下降
4. 连续14点交替上下
5. 连续3点中有2点超出2σ
6. 连续5点中有4点超出1σ
7. 连续15点在1σ内
8. 连续8点无1点在1σ内

#### 2.4.4 SPC-FMEA关联

当控制图触发异常时：
1. 自动识别异常特性关联的FMEA（DFMEA设计特性/PFMEA过程特性）失效模式
2. 推荐历史类似异常的8D处理方案
3. 一键启动CAPA流程

### 2.5 AI助手

#### 2.5.1 功能描述
基于LLM + RAG（检索增强生成）的智能质量助手。本节定义AI在质量管理全流程中的角色定位、能力边界、以及分阶段落地路径。

#### 2.5.2 模块关系与AI定位

系统围绕三条核心数据链运转，AI在各链中承担不同的角色：

**链1：产品实现链（APQP串联）**

```
APQP/项目质量策划(§2.15)
  ├─ 阶段2 → DFMEA(§2.3)
  │    ├─ 特殊特性(CC/SC) → 特殊特性管理(§2.13)
  │    └─ 控制措施 → DVP设计验证
  ├─ 阶段3 → PFMEA(§2.3)
  │    └─ 控制措施 → 控制计划(§2.9) ─── 一键生成
  │         ├─ SPC监控项 → SPC控制图(§2.4)
  │         └─ 检验项 → MSA测量系统(§2.14)
  ├─ 阶段4 → PPAP(§2.6)
  └─ 阶段5 → SPC量产监控 + 持续改进
```

**链2：问题解决链（CAPA串联）**

```
异常触发源:
  ├─ SPC判异(§2.4) ── 8大判异规则
  ├─ IQC来料拒收(§2.6) ── SCAR
  ├─ 客诉(§2.7) ── 8D
  ├─ 内部审核(§2.11) ── 不符合项升级
  └─ 管理评审(§2.12) ── 改进机会
          ↓
    8D/CAPA(§2.3)
    ├─ D4根因分析 → 关联FMEA失效原因
    ├─ D5永久措施 → 推荐历史有效控制措施
    └─ D7预防复发 → FMEA更新 → 经验沉淀至知识库(§2.8)
```

**链3：治理保障链**

```
质量目标管理(§2.2) ── 目标达成趋势 ──→ 管理评审(§2.12)
内部审核(§2.11) ── 审核结果 ──→ 管理评审(§2.12)
所有模块 ── KPI数据 ──→ 仪表盘(§2.1)
所有模块 ── 审批后脱敏数据 ──→ 全局知识库(§2.8)
```

**AI角色定位**：AI不替代质量工程师的判断，而是作为**知识检索加速器**和**模式推荐引擎**，在正确时机提供正确信息，减少人工检索和重复劳动。

#### 2.5.3 AI能力地图

按 **"已规划"** 和 **"新增机会"** 两个层次列出AI可以提升效率的场景：

##### 2.5.3.1 已规划能力（§2.5.2 原优先级）

| 能力 | 涉及模块 | AI能力描述 | 效率提升 | 阶段 |
|------|---------|-----------|---------|------|
| FMEA草稿生成 | FMEA(§2.3) | 输入新产品/新过程信息，推荐历史相似FMEA结构生成初稿 | 减少60-80%空白FMEA编制时间 | Phase 3 |
| 语义搜索 | 全局知识库(§2.8) | "查找所有与焊接温度相关的失效模式" — 自然语言搜索历史FMEA/8D报告 | 替代逐份翻阅 | Phase 3 |
| 变更影响分析 | FMEA+控制计划 | 某控制措施变更时，图遍历自动追溯受影响的过程和FMEA条目 | 替代人工逐条排查 | Phase 3 |
| SPC-FMEA异常关联 | SPC(§2.4)+FMEA | 控制图触发异常→自动识别关联FMEA失效模式→推荐历史8D方案 | 响应链从小时级降至分钟级 | Phase 3 |
| 8D报告草拟 | 8D/CAPA(§2.3) | 基于历史经验自动填充8D报告模板 | 减少报告编写时间 | Phase 4 |
| 质量趋势解读 | SPC+仪表盘 | 对SPC趋势、质量报表进行自然语言解读 | 降低数据分析门槛 | Phase 4 |
| 标准法规检索 | AI助手 | 自动查询IATF 16949、ISO 9001等相关条款 | 减少合规查证时间 | Phase 4 |

##### 2.5.3.2 新增AI能力（待纳入路线图）

| 能力 | 涉及模块 | AI能力描述 | 效率提升 | 推荐阶段 |
|------|---------|-----------|---------|---------|
| FMEA编辑时智能推荐 | FMEA(§2.3) | 编辑失效模式时底部弹出推荐卡片，展示历史相似条目（含来源/相似度） | 高频操作直接受益，避免遗漏 | Phase 3 |
| 8D根因+措施推荐 | 8D/CAPA(§2.3) | D4阶段自动推荐历史相似FMEA失效原因；D5阶段推荐类似案例的有效控制措施 | 缩短根因定位和措施选择时间 | Phase 3 |
| D7预防复发提示 | 8D/CAPA→FMEA | 自动提示需更新的相关FMEA条目，防止经验遗失 | 闭环最后一环自动化 | Phase 3 |
| 经验教训智能推送 | 全局知识库(§2.8) | 用户新建FMEA或处理8D时，AI主动推送"同类产品线/工序/失效模式"历史经验 | 变"拉"为"推"，复用率最大化 | Phase 4 |
| 控制计划智能校验 | CP(§2.9)+FMEA | AI校验控制计划与PFMEA的一致性（CP是否遗漏了PFMEA的控制措施？抽样频次是否合理？） | 消除FMEA→CP"翻译偏差"，审核高频不符合项 | Phase 4 |
| APQP阶段门智能检查 | APQP(§2.15) | AI自动检查阶段输出物完整性（如"阶段3的PFMEA是否覆盖了所有特殊特性"），给出放行建议 | 减少阶段评审遗漏 | Phase 4 |
| MSA结果智能解读 | MSA(§2.14) | 自动解读GR&R报告（"%GR&R=28%，条件接受。建议：检查量具分辨率"），而非仅展示数字 | 降低统计专业知识门槛 | Phase 4 |
| IQC抽样方案智能优化 | IQC(§2.6) | 基于历史来料质量表现，动态推荐调整AQL水平（加严/放宽/正常） | 减少过度检验或漏检风险 | Phase 4 |
| 供应商风险智能预警 | 供应商质量(§2.6) | 综合PPM趋势+交付准时率+SCAR关闭速度，预测供应商质量风险 | 从被动响应变为主动预防 | Phase 4 |
| 客户投诉智能分类路由 | 客户质量(§2.7) | 基于投诉描述自动分类（安全/功能/外观/交付）、判定严重等级、推荐处理优先级 | 减少人工分类误判 | Phase 4 |
| 审核检查表智能生成 | 内部审核(§2.11) | 基于上次审核发现+过程变更历史+顾客投诉趋势，自动生成风险导向的审核检查表 | 审核更有针对性 | Phase 4 |
| 管理评审报告自动生成 | 管理评审(§2.12) | 自动汇总所有输入数据，生成管理评审报告初稿（含趋势分析/异常标注/改进建议） | 准备时间从数天压缩至数小时 | Phase 5 |
| 质量目标基线推荐 | 质量目标(§2.2) | 基于历史绩效数据推荐下一年度质量目标值 | 目标设定更科学 | Phase 5 |
| 不良质量成本智能归因 | 管理评审+CAPA | AI自动归集内部失败成本(报废/返工/降级)和外部失败成本(客诉/退货/保修)，关联到具体产品线和失效模式 | 从财务视角驱动改进优先级 | Phase 5 |
| 特殊特性冲突检测 | 特殊特性(§2.13)+FMEA | 当同一特性在不同模块被标注为不同等级(一个CC、一个SC)时，AI自动检测并告警 | 防止特性等级不一致导致的控制漏洞 | Phase 5 |

#### 2.5.4 AI价值密度排序

按 **效率提升 × 使用频次 × 风险可控** 三维评估：

| 优先级 | AI场景 | 理由 |
|--------|--------|------|
| ★★★ 最高 | FMEA编辑时智能推荐 | 高频操作（质量工程师每天编辑FMEA），推荐历史已验证条目风险可控，直接减少遗漏 |
| ★★★ 最高 | SPC-FMEA异常关联 | 自动化异常→根因→方案的响应链，将响应时间从小时级降至分钟级 |
| ★★ 高 | 经验教训智能推送 | 变被动搜索为主动推送，是全局知识库价值最大化的关键 |
| ★★ 高 | 控制计划智能校验 | FMEA→CP一致性是审核高频不符合项，AI校验直接提升合规性 |
| ★★ 高 | 8D根因+措施推荐 | 问题解决的核心瓶颈是根因定位，AI推荐直接加速瓶颈环节 |
| ★ 中 | 审核检查表智能生成 | 风险导向审核是IATF 16949要求，AI提升审核有效性 |
| ★ 中 | 管理评审报告自动生成 | 频次低（年度/季度）但单次耗时巨大（数天→数小时） |
| ★ 中 | 供应商风险智能预警 | 从被动转主动，但依赖数据积累 |
| ★渐进 | FMEA草稿生成 | 价值高但风险也高，需严格人工审核，建议从推荐模式（非生成模式）起步 |

#### 2.5.5 AI落地三阶段

```
Phase 1 (对应原Phase 3): 检索式AI — 低风险
  └── 语义搜索 + 历史推荐 + 变更影响分析
      核心逻辑: 只推荐已有数据，不生成新内容

Phase 2 (对应原Phase 4): 生成式AI — 中风险，需审核
  └── FMEA草稿生成 + 8D报告草拟 + 质量趋势解读 + 各模块智能推荐
      核心逻辑: 生成初稿，强制人工审核

Phase 3 (未来): 主动式AI — 需数据积累和信任建立
  └── 智能推送 + 风险预警 + 目标推荐 + 成本归因
      核心逻辑: AI主动发现问题推送建议，人做最终决策
```

#### 2.5.6 AI安全边界与约束

AI助手在质量管理领域的错误建议可能导致严重后果（产品缺陷、召回风险），因此必须严格定义安全边界：

**输出约束**

| 约束 | 规则 |
|------|------|
| 标注义务 | 所有AI生成内容必须标注"AI建议"标签，与人工编写内容视觉区分 |
| 人工审核 | AI生成的FMEA初稿/8D报告必须经过至少一名质量工程师审核后方可正式发布 |
| 推荐优先 | AI优先推荐历史数据中的已验证条目，而非生成全新内容；推荐时标注数据来源(产品线/FMEA编号/时间) |
| 置信度展示 | 推荐结果附带相似度分数，低于阈值(如<0.7)的推荐标注"低置信度" |
| 采纳追踪 | 记录每条AI推荐的采纳/修改/拒绝率，用于持续优化推荐质量 |

**数据隐私边界**

| 规则 | 说明 |
|------|------|
| 禁止外传数据 | 客户名称/编号、供应商名称/编号、具体产品型号、具体缺陷数量等敏感字段禁止发送至外部LLM API |
| 脱敏检索 | RAG检索使用脱敏后的全局知识库数据，原始数据仅在本地推理时可访问 |
| 私有部署优先 | 生产环境推荐私有部署LLM（如本地微调的开源模型），外部API仅用于开发/评估阶段 |
| 数据留存 | 发送给LLM的提示词(Prompt)和响应均记录审计日志，保留180天 |

**降级策略**

| 场景 | 降级策略 |
|------|---------|
| LLM服务不可用 | AI推荐功能自动降级为基于Elasticsearch的关键词检索 |
| 推荐响应超时(>5s) | 自动取消，不阻塞用户主操作流程 |
| 特定模块关闭 | 所有AI功能均可按产品线/全局级别开关，不影响核心FMEA/CAPA业务流程 |

---


### 2.6 供应商质量管理 (Supplier Quality Management)

#### 2.6.1 功能描述
管理供应商准入、来料检验（IQC）、供应商审核、绩效评价与纠正措施（SCAR），构建从进料到生产全链条的供应商质量闭环。

#### 2.6.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 供应商档案 | P0 | 供应商主数据管理：基本信息、资质证书（ISO/IATF）、供应品类、批准状态（临时/批准/受限/淘汰） |
| IQC来料检验 | P0 | 来料检验批管理：AQL抽样方案、检验项目（外观/尺寸/性能/包装）、合格/让步/拒收判定、检验报告生成 |
| 供货质量看板 | P0 | 按供应商维度的PPM/批次合格率/交付准时率趋势图，红黄绿评级 |
| SCAR管理 | P1 | 供应商纠正措施申请（SCAR）：从IQC拒收/产线发现/客诉触发，跟踪8D闭环，超期升级 |
| 供应商审核 | P1 | 审核计划管理（体系审核/过程审核/产品审核）、审核检查表、审核报告、纠正项追踪 |
| 特采/让步管理 | P1 | 不合格品让步接收流程：影响评估（关联FMEA）、客户确认、限次/限批审批 |
| 供应商绩效评价 | P2 | 季度/年度评价：质量（PPM/批合率）+ 交付（准时率）+ 服务（响应速度）综合打分、自动评级 |
| 新供应商准入 | P2 | 问卷调查、现场评审、样件验证（PPAP）、小批量试产流程管理 |
| PPAP管理 | P1 | 生产件批准18要素提交与审批：设计记录、工程变更、DFMEA、PFMEA、控制计划、MSA、全尺寸检验、初始过程能力、实验室资质、外观批准、散装材料检查表、样品产品、标准样品、检验辅具、顾客特殊要求、零件提交保证书(PSW) |
| 供应链风险地图 | P3 | 供应风险热力图：单一来源、地缘政治、质量问题频次、交付波动等多维评估 |

#### 2.6.3 IQC来料检验流程

```
来料登记 → 抽样方案自动生成(AQL) → 检验执行(外观/尺寸/功能) 
→ 判定(合格/让步/拒收) → 合格入库 / 让步审批 / 拒收+SCAR触发
                              ↑                           ↓
                     产线发现来料不良 ──→ 补充检验 ──→ SCAR升级
```

#### 2.6.4 供应商质量数据模型（关键表）

```sql
-- 供应商主数据
CREATE TABLE suppliers (
    supplier_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_code  VARCHAR(20) UNIQUE NOT NULL,
    name           VARCHAR(200) NOT NULL,
    category       VARCHAR(50),  -- 电子件/结构件/辅料/包装
    approval_status VARCHAR(20) CHECK (approval_status IN ('临时','批准','受限','淘汰')),
    cert_list      JSONB,        -- 资质证书 [{cert_name, cert_no, expire_date}]
    contact_name   VARCHAR(100),
    contact_email  VARCHAR(200),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by     VARCHAR(100)
);

-- IQC检验批
CREATE TABLE iqc_lots (
    lot_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lot_no         VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    supplier_id    UUID REFERENCES suppliers(supplier_id),
    material_code  VARCHAR(50),
    material_name  VARCHAR(200),
    quantity        INTEGER,
    aql_level      VARCHAR(10),   -- AQL抽样水平
    sample_size    INTEGER,       -- 抽样数
    result         VARCHAR(20) CHECK (result IN ('合格','让步','拒收','待检')),
    defect_count   INTEGER DEFAULT 0,
    inspector      VARCHAR(100),
    inspected_at   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- SCAR
CREATE TABLE scar (
    scar_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scar_no        VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    supplier_id    UUID REFERENCES suppliers(supplier_id),
    source         VARCHAR(50),  -- IQC拒收/产线发现/客诉
    fmea_ref_id    UUID,         -- 关联FMEA
    status         VARCHAR(20) DEFAULT 'open',
    due_date       DATE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.7 客户质量管理 (Customer Quality Management)

#### 2.7.1 功能描述
管理客户投诉、退货分析（RMA）、客户端质量表现、客户审核与满意度，构建从客诉接收到根因关闭的全流程闭环。

#### 2.7.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 客诉管理 | P0 | 客诉接单、分类（安全/功能/外观/交付）、严重等级（致命/严重/一般/轻微）、8D关联、超期预警 |
| 退货RMA管理 | P0 | 退货接收登记→不良分析→判定（供应商责任/自制责任/运输损坏）→纠正措施→归档 |
| 客户质量看板 | P0 | 按客户维度的PPM/投诉数/退货率趋势图、客户风险红黄绿灯 |
| 客户审核管理 | P1 | 客户审核日程、审核准备清单、审核发现项追踪、整改措施闭环 |
| 0公里PPM追踪 | P1 | 出厂后0公里（客户端接收）PPM统计，与厂内PPM对比分析 |
| 客户特殊要求(VOC) | P2 | 客户特定要求（CSR）管理：特殊特性要求、包装标识要求、追溯要求等 |
| 满意度调查 | P2 | 年度/季度客户满意度评分（质量/交付/服务/响应），趋势分析 |
| 保修管理 | P2 | 保修件退回分析流程、NTF（未发现故障）统计、保修绩效趋势、与FMEA失效模式关联（IATF 16949 §10.2.5-6） |
| 质量会议纪要 | P3 | 客户质量例会纪要管理、行动项追踪、关联客诉与CAPA |

#### 2.7.3 客诉-RMA-8D 联动流程

```
客户投诉接收 → 客诉登记(严重等级/影响评估) 
  → 判定是否退货 → RMA登记(退货数量/批次)
  → 不良分析(关联FMEA/8D) 
  → 根因确认 → 纠正措施(CAPA/SCAR)
  → 8D报告发送客户 
  → 效果验证(PPM趋势/复检) → 关闭

重大安全客诉 → 即时通知管理层 → 启动应急响应 → 24小时初步回复客户
```

#### 2.7.4 客户质量数据模型（关键表）

```sql
-- 客户主数据
CREATE TABLE customers (
    customer_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_code  VARCHAR(20) UNIQUE NOT NULL,
    name           VARCHAR(200) NOT NULL,
    segment        VARCHAR(50),   -- 汽车/消费电子/工业/医疗
    csr_list       JSONB,         -- 客户特殊要求清单
    ppm_target     DECIMAL(6,2),  -- 客户要求PPM目标
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by     VARCHAR(100)
);

-- 客诉
CREATE TABLE customer_complaints (
    complaint_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    complaint_no   VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线归属
    customer_id    UUID REFERENCES customers(customer_id),
    product_id     VARCHAR(50),
    severity       VARCHAR(20) CHECK (severity IN ('致命','严重','一般','轻微')),
    defect_desc    TEXT,
    impact_qty     INTEGER,          -- 影响数量
    fmea_ref_id    UUID,             -- 关联FMEA
    capa_ref_id    UUID,             -- 关联CAPA/8D
    status         VARCHAR(20) DEFAULT 'open',
    due_date       DATE,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- RMA
CREATE TABLE rma_records (
    rma_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rma_no          VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线归属
    complaint_id    UUID REFERENCES customer_complaints(complaint_id),
    return_qty      INTEGER,
    defect_type     VARCHAR(50),  -- 功能不良/外观缺陷/包装损坏/数量短缺
    responsibility  VARCHAR(50),  -- 供应商责任/自制责任/运输损坏/客户误用
    analysis_result TEXT,
    corrective_action TEXT,
    status          VARCHAR(20) DEFAULT 'open',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```


### 2.8 全局知识库 (Global Knowledge Base)

#### 2.8.1 功能描述
跨产品线的FMEA知识沉淀平台，聚合所有产品线的DFMEA和PFMEA数据，形成企业级的质量管理知识资产，用于指导新产品线研发设计和工艺规划。

#### 2.8.2 核心定位

| 维度 | 产品线模块 | 全局知识库 |
|------|----------|-----------|
| 数据范围 | 单一产品线 | 跨产品线聚合 |
| 写入权限 | 产品线质量工程师 | 知识库管理员 + AI自动沉淀 |
| 使用场景 | 日常质量管理 | 新产品线研发参考、企业质量规划 |
| 数据来源 | 本产品线数据 | 所有产品线的FMEA/8D/SPC数据脱敏聚合 |

#### 2.8.3 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| DFMEA知识库 | P1 | 按产品类别（汽车/消费/工业）聚合所有产品线DFMEA，提供按系统类型（电源/控制/结构）的失效模式分类索引 |
| PFMEA知识库 | P1 | 按工序类型（焊接/注塑/装配/测试）聚合所有产品线PFMEA，形成通用工艺FMEA模板 |
| 失效模式搜索引擎 | P1 | 全文+语义搜索所有产品线的失效模式和根因，支持按行业/产品类型/工序类型筛选 |
| 新产品线研发助手 | P2 | 输入新产品线的基本描述（产品类型/关键工艺/目标行业），自动推荐所有产品线的相关FMEA经验和规避措施 |
| 工艺FMEA模板库 | P2 | 基于历史数据生成的标准化PFMEA模板（如"SMT焊接"通用模板、"注塑成型"通用模板） |
| 知识图谱全览 | P2 | 跨产品线的失效模式-原因-措施关联全图，支持识别系统性的共性问题 |
| 质量知识词云 | P3 | 按产品线/问题类型的关键词云，可视化常见质量问题分布 |

#### 2.8.4 全局知识库数据来源

```
产品线A的DFMEA ──┐
产品线A的PFMEA ──┤
产品线A的8D根因 ──┤
产品线B的DFMEA ──┼──→ 全局知识库（脱敏+聚合）
产品线B的PFMEA ──┤      ├── 通用DFMEA模板
产品线B的8D根因 ──┤      ├── 通用PFMEA模板
产品线B的SPC异常 ──┤      ├── 失效模式分类索引
...               │      ├── 根因-措施关联图
                  └──────└── AI推荐引擎
```

#### 2.8.5 与产品线模块的关系

全局知识库是**只读聚合层**，不替代各产品线的FMEA编辑器：
- **写入**: 产品线工程师在各自产品线的FMEA编辑器中写入数据
- **沉淀**: 经审批后自动脱敏同步到全局知识库（去除产品线/客户/供应商敏感信息）
- **复用**: 新产品线研发时从知识库检索和参考历史经验


### 2.9 控制计划 (Control Plan)

#### 2.9.1 功能描述
管理产品/过程控制计划（CP），将PFMEA中识别的关键控制措施转化为标准化的过程控制要求，并与SPC监控、检验标准深度关联，确保从设计意图到生产执行的闭环落地。

#### 2.9.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 控制计划编辑器 | P0 | 按工序编号逐项编辑：过程名称/编号、产品特性、过程特性、特殊特性分类(CC/SC)、控制方法、抽样频次、反应计划 |
| FMEA联动生成 | P0 | 从PFMEA一键生成控制计划初稿，自动填充工序/特性/控制方法，变更时双向同步 |
| SPC监控关联 | P0 | 控制计划中的SPC监控项自动关联SPC控制图，异常时触发反应计划 |
| 检验标准引用 | P1 | 控制计划条目关联检验作业指导书（SOP），支持内联查看检验方法和判定标准 |
| 特殊特性清单 | P1 | 自动从控制计划中提取所有CC/SC特性，生成特殊特性清单（含图纸编号、测量方法、CP条目号） |
| 版本管理 | P1 | 控制计划版本历史、变更对比、差异高亮、审批流程（ECN触发） |
| 客户CSR映射 | P2 | 客户特殊要求（CSR）自动映射到控制计划对应条目，确保客户要求完整覆盖 |
| 批量导入/导出 | P2 | 支持xls/xlsx格式导入导出，兼容AIAG标准控制计划模板 |

#### 2.9.3 控制计划-FMEA-SPC联动流程

```
PFMEA编制完成 
  → 一键生成控制计划初稿（自动填充工序/失效模式/控制措施）
  → 工程师补充：抽样方案、检验频次、量具、反应计划
  → 审批发布
  → SPC监控项自动创建控制图
  → 生产执行：按CP要求检验
  → SPC异常触发 → 执行反应计划 → 记录处置 → 必要时触发CAPA

PFMEA变更时：
  → 自动标注受影响的CP条目 → 工程师确认更新 → CP版本升级
```

#### 2.9.4 控制计划数据模型

```sql
-- 控制计划主表
CREATE TABLE control_plans (
    cp_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cp_no            VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    title            VARCHAR(200) NOT NULL,
    fmea_ref_id      UUID REFERENCES fmea_documents(fmea_id),        -- 关联PFMEA
    cp_type          VARCHAR(20) CHECK (cp_type IN ('原型','试生产','量产')),
    status           VARCHAR(20) DEFAULT 'draft',
    version          INTEGER DEFAULT 1,
    created_by       VARCHAR(100),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    approved_by      VARCHAR(100),
    approved_at      TIMESTAMP
);

-- 控制计划条目
CREATE TABLE control_plan_items (
    item_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cp_id              UUID REFERENCES control_plans(cp_id),
    process_number     VARCHAR(20),    -- OP10/OP20/...
    process_name       VARCHAR(200),
    product_characteristic VARCHAR(200),  -- 产品特性（尺寸/性能等）
    process_characteristic VARCHAR(200),  -- 过程特性（温度/压力等）
    special_char_class VARCHAR(10),       -- CC/SC/无
    control_method     VARCHAR(100),      -- SPC/防错/首检/巡检/全检
    sample_size        VARCHAR(50),       -- 抽样数量
    sample_frequency   VARCHAR(50),       -- 抽样频次
    measurement_tool   VARCHAR(100),      -- 量具/检具
    reaction_plan      TEXT,              -- 超出控制限时的处理方案
    sop_ref            VARCHAR(50),       -- 关联SOP编号
    spc_chart_id       UUID,             -- 关联SPC控制图
    sort_order         INTEGER DEFAULT 0,
    created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_cp_pl ON control_plans(product_line_code);
```


### 2.10 模块间数据流与协作

#### 2.10.1 供应商质量 ↔ 其他模块

| 协作点 | 数据流向 | 说明 |
|--------|----------|------|
| IQC拒收 → SCAR → 8D | 供应商 → CAPA | 来料不良触发SCAR，SCAR可升级为内部8D |
| IQC不良 → FMEA | 检验数据 → 知识图谱 | 来料不良模式自动关联FMEA失效原因，丰富"材料类"原因库 |
| 供应商变更 → 变更影响分析 | 供应商主数据 → AI | 供应商关键参数变更时自动触发变更影响分析 |
| 供应商PPM → 仪表盘 | 供货数据 → KPI | 供应商PPM趋势、批次合格率等数据归入仪表盘 |
| 特采审批 → FMEA | 让步审批 → 风险评估 | 让步接收时关联FMEA评估对产品风险的影响 |

#### 2.10.2 客户质量 ↔ 其他模块

| 协作点 | 数据流向 | 说明 |
|--------|----------|------|
| 客诉 → 8D/CAPA | 客诉 → 根因分析 | 客诉触发8D，8D根因关联FMEA |
| 0公里PPM ↔ SPC | 客户PPM ↔ 厂内CPK | 对比客户端与厂内过程能力，发现出货检验盲区 |
| 客诉退货 → FMEA | 不良分析 → 知识图谱 | 客诉退货的不良模式补入FMEA失效原因库 |
| 客户审核 → 8D/CAPA | 审核发现 → 纠正措施 | 客户审核发现项直接进入CAPA跟踪 |
| 客户CSR → 控制计划 | 特殊要求 → CP条目 | 客户特殊要求（如标识/追溯/特性）自动同步至控制计划 |

#### 2.10.3 控制计划 ↔ 其他模块

| 协作点 | 数据流向 | 说明 |
|--------|----------|------|
| PFMEA → 控制计划 | 控制措施 → CP条目 | PFMEA中的控制措施自动生成控制计划初稿 |
| 控制计划 → SPC | CP监控项 → 控制图 | 控制计划中标注SPC的特性自动创建对应控制图 |
| SPC异常 → 反应计划 | 异常告警 → CP | SPC触发异常后按控制计划中的反应计划执行 |
| 控制计划 → SOP | CP条目 → 作业指导 | 控制计划条目引用SOP作为检验执行标准 |
| 客户CSR → 控制计划 | 特殊要求 → CP | 客户特殊要求自动映射至控制计划相应条目 |

### 2.11 内部审核管理

#### 2.11.1 功能描述
支撑 ISO 9001:2015 §9.2 和 IATF 16949:2016 §9.2.2.1-9.2.2.4 要求的内部审核方案管理，涵盖质量管理体系审核、制造过程审核和产品审核三种类型。

#### 2.11.2 审核类型

| 审核类型 | 依据 | 频次要求 |
|---------|------|---------|
| 质量管理体系审核 | ISO 9001 + IATF 16949 全部条款 | 每3个日历年覆盖全部质量管理体系过程 |
| 制造过程审核 | PFMEA + 控制计划 + 作业指导书 | 每3个日历年覆盖全部制造过程（含所有班次） |
| 产品审核 | 产品规范/图纸/顾客要求 | 按策划频次，在生产及交付的适当阶段实施 |

#### 2.11.3 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 审核方案管理 | P0 | 年度审核方案编制（审核类型/频次/范围/准则），基于风险和绩效趋势确定审核优先级 |
| 审核计划与执行 | P0 | 审核计划制定、检查表模板库、审核发现记录（符合/不符合/改进机会） |
| 不符合项管理 | P0 | 不符合项分类（严重/一般/改进机会）、根因分析、纠正措施跟踪、效果验证闭环 |
| 审核报告 | P1 | 自动生成审核报告，审核发现统计与趋势分析，审核结果自动推送至管理评审数据包 |
| 审核员管理 | P1 | 合格审核员清单、资格矩阵（体系/过程/产品）、年度审核次数统计与能力维持追踪 |
| 审核发现→CAPA联动 | P1 | 审核中发现的不符合项可一键升级为CAPA，进入8D问题解决流程 |

#### 2.11.4 数据模型

```sql
CREATE TABLE audit_programs (
    program_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_year     INTEGER NOT NULL,
    audit_type       VARCHAR(20) CHECK (audit_type IN ('system','process','product')),
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),
    status           VARCHAR(20) DEFAULT 'planned',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_plans (
    audit_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id       UUID REFERENCES audit_programs(program_id),
    audit_scope      TEXT NOT NULL,
    audit_criteria   TEXT NOT NULL,
    planned_date     DATE NOT NULL,
    actual_date      DATE,
    lead_auditor     UUID REFERENCES users(user_id),
    status           VARCHAR(20) DEFAULT 'planned',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE audit_findings (
    finding_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    audit_id         UUID REFERENCES audit_plans(audit_id),
    clause_ref       VARCHAR(50),
    finding_type     VARCHAR(20) CHECK (finding_type IN ('major_nc','minor_nc','ofi','observation')),
    description      TEXT NOT NULL,
    root_cause       TEXT,
    correction       TEXT,
    corrective_action TEXT,
    capa_ref_id      UUID,
    status           VARCHAR(20) DEFAULT 'open',
    due_date         DATE,
    closed_at        TIMESTAMP
);
```

### 2.12 管理评审

#### 2.12.1 功能描述
支撑 ISO 9001:2015 §9.3 和 IATF 16949:2016 §9.3.1.1 要求的管理评审，自动汇总各模块数据形成管理评审输入包，记录评审输出和措施跟踪。

#### 2.12.2 管理评审输入数据源

| ISO 9001 §9.3.2 要求 | IATF 16949 补充 | 系统数据源 |
|----------------------|----------------|-----------|
| 以往管理评审措施落实 | — | 管理评审模块（历史记录） |
| 内外部因素变化 | — | 手动输入 |
| 顾客满意与反馈 | 顾客计分卡、保修绩效 | 客户质量模块 |
| 质量目标实现程度 | — | 质量目标管理模块 |
| 过程绩效与产品符合性 | 过程有效性/效率测量 | SPC + 检验数据 |
| 不合格与纠正措施 | 使用现场失效分析 | 8D/CAPA模块 |
| 监视测量结果 | 维护目标绩效（OEE/MTBF/MTTR） | SPC + 设备管理 |
| 审核结果 | — | 内部审核模块 |
| 外部供方绩效 | — | 供应商质量模块 |
| 资源充分性 | — | 手动输入 |
| 风险机遇措施有效性 | FMEA识别的潜在使用现场失效 | FMEA + 风险分析 |
| 改进机会 | — | 汇总分析 |
| — | 不良质量成本（内部+外部不符合成本） | 质量成本统计 |
| — | 制造可行性评估 | 供应商/制造模块 |

#### 2.12.3 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 管理评审数据包 | P1 | 一键汇总所有输入数据，自动生成管理评审输入报告（含趋势图） |
| 管理评审记录 | P1 | 评审会议记录、输出项（改进机会/体系变更/资源需求）、措施跟踪闭环 |
| 顾客绩效目标跟踪 | P1 | 未达成顾客绩效目标时自动触发文件化措施计划，纳入管理评审输出跟踪 |

### 2.13 特殊特性管理

#### 2.13.1 功能描述
支撑 IATF 16949:2016 §8.3.3.3 要求的特殊特性识别、标识和贯穿管理。确保特殊特性（CC关键特性/SC重要特性）在图纸、DFMEA、PFMEA、控制计划、作业指导书、检验标准中的一致标识和联动更新。

#### 2.13.2 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 特殊特性识别 | P0 | 多方论证方法识别特殊特性（顾客指定 + 组织风险分析），支持在FMEA中标注CC/SC |
| 特殊特性清单 | P0 | 自动从各模块提取CC/SC特性，生成统一清单（含特性描述/图纸编号/控制方法/FMEA条目/CP条目） |
| 贯穿标识与联动 | P0 | 特殊特性在DFMEA→PFMEA→控制计划→SOP→检验标准中自动同步标识，任一模块变更时联动更新 |
| 符号转换表 | P1 | 组织符号↔顾客符号映射表管理，支持向顾客提交 |
| 控制与监视策略 | P1 | 为每个特殊特性定义控制方法（SPC/防错/100%检验）和监视策略 |

#### 2.13.3 数据模型

```sql
CREATE TABLE special_characteristics (
    sc_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sc_code          VARCHAR(50) UNIQUE NOT NULL,
    sc_name          VARCHAR(200) NOT NULL,
    sc_type          VARCHAR(10) CHECK (sc_type IN ('CC','SC','OS')),
    sc_category      VARCHAR(20) CHECK (sc_category IN ('产品特性','过程特性')),
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),
    source           VARCHAR(20) CHECK (source IN ('顾客指定','组织识别')),
    customer_symbol  VARCHAR(50),
    org_symbol       VARCHAR(50),
    drawing_ref      VARCHAR(50),
    fmea_ref_id      UUID,
    cp_item_ref_id   UUID,
    sop_ref          VARCHAR(50),
    control_method   VARCHAR(100),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2.14 MSA 测量系统分析

#### 2.14.1 功能描述
支撑 IATF 16949:2016 §7.1.5.1.1 要求的测量系统分析，对控制计划中识别的检验、测量和试验设备进行统计研究。

#### 2.14.2 分析类型

| 分析类型 | 适用场景 | 方法 |
|---------|---------|------|
| GR&R（量具重复性和再现性） | 计量型数据，评估测量系统变异 | 均值极差法（X-bar R）/ 方差分析法（ANOVA） |
| 偏倚分析 | 评估测量系统准确性 | 单样本 t 检验 |
| 线性分析 | 评估量具在量程范围内的偏倚一致性 | 线性回归 |
| 稳定性分析 | 评估测量系统随时间变化的稳定性 | X-bar R / I-MR 控制图 |

#### 2.14.3 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| GR&R 分析 | P1 | 量具重复性和再现性研究（交叉/嵌套），支持均值极差法和ANOVA法，自动计算%GR&R、ndc |
| 偏倚与线性 | P2 | 偏倚分析和线性分析，支持自动计算和判定 |
| 稳定性分析 | P2 | 量具稳定性控制图，定期监测测量系统漂移 |
| 与控制计划关联 | P1 | 控制计划中标注的测量设备自动关联MSA分析结果 |
| MSA报告 | P1 | 自动生成MSA分析报告（含%GR&R、ndc、判定结论），纳入PPAP文档包 |

#### 2.14.4 判定标准

| 指标 | 可接受 | 条件接受 | 不可接受 |
|------|--------|---------|---------|
| %GR&R | ≤10% | 10%-30% | >30% |
| ndc（可区分类别数） | ≥5 | — | <5 |

### 2.15 APQP/项目质量策划

#### 2.15.1 功能描述
支撑产品质量先期策划（APQP）方法论，将 FMEA、控制计划、MSA、SPC、PPAP 五大工具串联为结构化的新产品/新过程开发质量策划流程。

#### 2.15.2 APQP 阶段

| 阶段 | 名称 | 关键输出 |
|------|------|---------|
| 阶段1 | 策划与定义 | 项目范围、质量目标、初始BOM、初始过程流程图 |
| 阶段2 | 产品设计与开发 | DFMEA、设计验证计划(DVP)、样件控制计划、特殊特性初始清单 |
| 阶段3 | 过程设计与开发 | PFMEA、量产控制计划、过程流程图、MSA计划、SOP初稿 |
| 阶段4 | 产品与过程确认 | 试生产、MSA结果、初始过程能力(PPK)、PPAP提交 |
| 阶段5 | 反馈评定与纠正 | 量产SPC、CPK监控、持续改进、经验教训入库 |

#### 2.15.3 功能规格

| 功能项 | 优先级 | 描述 |
|--------|--------|------|
| 项目阶段门管理 | P1 | 五阶段门评审，阶段输出物检查清单，阶段放行审批 |
| 五大工具串联 | P1 | 从APQP项目一键创建DFMEA/PFMEA/控制计划/MSA/PPAP关联文档 |
| 项目时间线 | P1 | 甘特图展示项目进度，关键节点延期预警 |
| 多方论证协作 | P2 | 跨职能团队（设计/制造/质量/采购/供应商）协作空间 |



---

## 3. 技术架构

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      前端层 (React/Vue)                      │
│  ├─ Dashboard  ├─ FMEA Editor  ├─ Knowledge Graph Viewer   │
│  ├─ CAPA Forms ├─ SPC Charts   ├─ AI Chat Interface        │
│  ├─ 供应商管理 ├─ IQC检验      ├─ 客户质量看板              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      API 网关层 (Kong/APISIX)               │
│             认证鉴权 限流 日志 路由                           │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  核心服务层       │ │  智能服务层       │ │  集成服务层       │
│                  │ │                  │ │                  │
│ • FMEA服务       │ │ • 推荐引擎       │ │ • MES连接器       │
│ • CAPA/8D服务    │ │ • 语义搜索       │ │ • PLM连接器       │
│ • SPC服务        │ │ • RAG服务        │ │ • ERP连接器       │
│ • 供应商质量     │ │ • LLM Agent      │ │ • 客户反馈接入   │
│ • 客户质量       │ │ • 影响分析       │ │ • IoT数据接入     │
│ • 文档管理       │ │ • 文档智能       │ │ • SRM/CRM连接器  │
│ • 用户权限       │ │                  │ │                  │
└──────────────────┘ └──────────────────┘ └──────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────┐
│                       数据层                                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ Redis 缓存   │ │ Kafka/MQ     │ │ MinIO/OSS 对象存储    │ │
│  │ 热点缓存     │ │ CDC事件分发   │ │ 附件/报告存储         │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ PostgreSQL   │ │ Elasticsearch│ │ 向量数据库            │ │
│  │ (主数据仓库) │ │ (全文搜索)   │ │ (Milvus/PGVector)    │ │
│  │              │ │              │ │ 语义检索+LLM Embedding│ │
│  │ 检验记录     │ │ FMEA描述     │ │                      │ │
│  │ SPC数据      │ │ 8D报告       │ │                      │ │
│  │ 用户/权限    │ │ 文档索引     │ │                      │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────┐│
│  │          图数据库 (Neo4j) - FMEA知识图谱               ││
│  │  节点: DFMEA + PFMEA 统一模型详见§4.1-4.2            ││
│  │  SystemItem, Function, FailureMode, FailureCause,     ││
│  │  FailureEffect, ControlMeasure, DesignParameter, ...  ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 3.2 技术选型

| 组件 | 选型 | 选型理由 |
|------|------|----------|
| 前端框架 | React 18+ 或 Vue 3+ | 生态成熟，组件库丰富 |
| UI组件库 | Ant Design / Element Plus | 企业级中后台组件库 |
| 知识图谱可视化 | D3.js / G6 / Cytoscape.js | 图可视化能力强，支持力导向布局 |
| SPC图表 | Chart.js / ECharts | 原生支持多种统计图表 |
| 后端框架 | Spring Boot / FastAPI | 微服务架构，按团队技术栈选择 |
| 消息队列 | Kafka / RabbitMQ | 异步处理，CDC事件分发，系统解耦 |
| 缓存 | Redis 7+ | 热点数据缓存、会话存储、API限流计数 |
| 对象存储 | MinIO / 阿里云OSS / AWS S3 | 附件(报告/图片/检验记录)存储，按产品线桶隔离 |
| 可观测性 | Prometheus + Grafana + Loki | 指标采集、仪表盘监控、日志聚合与告警 |
| 图数据库 | Neo4j (Enterprise) | 原生图计算能力强，Cypher查询 |
| 关系数据库 | PostgreSQL 15+ | 稳定性好，支持JSON/全文搜索/PGVector |
| 搜索引擎 | Elasticsearch 8.x | 全文搜索、聚合分析 |
| 向量数据库 | Milvus / PGVector | 语义相似度检索 |
| LLM | 工业微调模型 / GPT-4 + RAG | 结合工业语料微调或通过RAG接入 |
| 容器化 | Docker + Kubernetes | 弹性伸缩，多工厂部署 |
| API网关 | Kong / APISIX | 统一鉴权、限流、路由 |

### 3.3 部署架构

支持三种部署模式：
- **单工厂部署**: 单体节点，简化运维
- **多工厂部署**: 每个工厂独立实例 + 集团汇总中心
- **SaaS云部署**: 多租户，弹性资源

---



## 3.4 产品线中心架构 (Product Line Architecture)

### 3.4.1 设计原则

系统以**产品线(Product Line)**为数据组织和权限隔离的核心维度。每个产品线拥有独立的质量管理闭环（FMEA/SPC/8D/CP/SOP/供应商/客户），同时通过全局知识库实现跨产品线的知识复用。

### 3.4.2 产品线维度模型

```
智能质量管理平台
├── 仪表盘（汇总视图）
│   ├── 公司级质量总览
│   └── 按产品线分区统计
│
├── 产品线: DC-DC转换器
│   ├── FMEA管理 (DFMEA + PFMEA)
│   ├── 8D/CAPA
│   ├── SPC控制图
│   ├── 控制计划
│   ├── SOP文档库
│   ├── 供应商质量
│   └── 客户质量
│
├── 产品线: PCB焊接组件
│   ├── ...（同上全部模块）
│
├── 产品线: 注塑外壳
│   ├── ...（同上全部模块）
│
└── 全局知识库（跨产品线）
    ├── DFMEA 知识库（设计经验沉淀）
    ├── PFMEA 知识库（工艺经验沉淀）
    ├── 失效模式-原因-措施关联图谱
    └── 新产品线研发指导引擎
```

### 3.4.3 数据隔离规则

| 维度 | 隔离策略 | 说明 |
|------|---------|------|
| FMEA/8D/SPC/CP | 按 product_line_code 字段隔离 | 每个产品线只能查看和编辑本产品线的数据 |
| SOP | 按 product_line_code 隔离，支持全局模板 | 跨产品线通用的SOP可标记为"全局模板"并共享 |
| 供应商 | 共享供应商档案，供应商业绩按产品线统计 | 同一供应商可能供应多条产品线 |
| 客户 | 共享客户档案，客诉按产品线归属 | 同一客户可能购买多条产品线 |
| 全局知识库 | 全产品线可读 | 聚合所有产品线的FMEA数据，供新产品线参考 |

### 3.4.4 产品线主数据

```sql
CREATE TABLE product_lines (
    pl_code        VARCHAR(20) PRIMARY KEY,
    pl_name        VARCHAR(200) NOT NULL,
    pl_category    VARCHAR(50),         -- 汽车电子/消费电子/工业/医疗
    pl_status      VARCHAR(20) DEFAULT 'active',  -- active/dormant/eol
    parent_pl_code VARCHAR(20),         -- 产品线继承（平台化产品线）
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 示例数据
INSERT INTO product_lines VALUES
  ('DC-DC-100',  'DC-DC转换器',     '汽车电子', 'active', NULL),
  ('PCB-SMT-200','PCB焊接组件',     '消费电子', 'active', NULL),
  ('IM-HG-300',  '注塑外壳',        '工业',     'active', NULL);
```

### 3.5 非功能性需求

#### 3.5.1 性能要求

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 页面加载时间 | ≤ 2s (P95) | 首屏渲染时间，含FMEA编辑器、控制图等复杂页面 |
| API响应时间 | ≤ 500ms (P95) | 常规CRUD接口；列表查询（含分页+筛选）≤ 1s |
| SPC数据采集延迟 | ≤ 3s | 从MES/IoT数据源到控制图刷新的端到端延迟 |
| 知识图谱查询 | ≤ 2s (单次展开) | 展开深度 ≤ 3层、节点数 ≤ 500 的子图查询 |
| AI推荐响应 | ≤ 5s | 包含LLM推理 + RAG检索的完整链路；超时自动取消 |
| FMEA编辑器并发 | Phase 1: 乐观锁+行级锁定防冲突；Phase 3(P2): 升级为OT/CRDT实时协同（5人并发，延迟 ≤ 1s） | 与§2.2 多人协同编辑(P2)优先级对齐 |
| 批量导入 | 1000行FMEA / 30s | 含数据校验、图谱节点创建 |

#### 3.5.2 可用性与灾备

| 指标 | 目标值 |
|------|--------|
| SLA | 99.5%（单工厂部署）/ 99.9%（SaaS云部署） |
| RPO (恢复点目标) | ≤ 1小时（PostgreSQL WAL日志 + 定时快照） |
| RTO (恢复时间目标) | ≤ 4小时（单工厂）/ ≤ 30分钟（SaaS） |
| 数据库备份 | 每日全量 + 每小时增量，保留30天 |
| Neo4j备份 | neo4j-admin backup 每日全量 + Transaction Log增量归档；恢复使用 neo4j-admin restore |
| 健康检查 | 所有服务 /health 端点，30s探测间隔 |

#### 3.5.3 可扩展性

| 维度 | 目标 |
|------|------|
| 产品线数 | 支持 ≤ 100 条产品线同时运行 |
| 并发用户数 | 200人并发（单工厂）/ 2000人并发（SaaS） |
| FMEA知识图谱规模 | 单产品线 ≤ 5万节点；全局知识库 ≤ 50万节点 |
| SPC数据量 | 每特性每天 ≤ 1000组数据，系统总量 ≤ 10亿条（3年保留）|
| 数据归档 | SPC原始数据在线保留90天，90天以上数据降采样(保留子组均值)后归档至冷存储，3年以上按审计要求决定是否删除 |
| 附件存储 | 每产品线 ≤ 50GB（报告/图片/检验记录），总量 ≤ 5TB |
| 水平扩展 | 核心服务无状态化，支持K8s HPA自动扩缩容 |

#### 3.5.4 国际化与本地化

| 维度 | 说明 |
|------|------|
| 多语言 | Phase 1: 中文简体(zh-CN)；Phase 2: 英文(en-US)；后续按需扩展 |
| 时区 | 所有时间戳以UTC存储，前端按用户locale自动转换显示 |
| 日期格式 | 跟随用户locale设置（zh: YYYY-MM-DD / en: MM/DD/YYYY） |
| 数字格式 | 跟随用户locale设置（千分位/小数点符号） |
| 术语表 | 维护中英文质量管理术语映射表（FMEA/SPC/CAPA等专业术语），保证翻译一致性 |
| 标准引用 | 支持切换AIAG(英文)与VDA(德文/英文)标准版本的评分表和模板 |

#### 3.5.5 标准合规性对照

系统功能对 ISO 9001:2015 和 IATF 16949:2016 关键条款的覆盖：

| 标准 | 条款 | 要求 | 系统支撑模块 |
|------|------|------|-------------|
| ISO 9001 | §4.1-4.2 组织环境与相关方 | 识别内外部因素及相关方需求 | 相关方分析（§1.4） |
| ISO 9001 | §6.2 质量目标 | 质量目标设定、展开、监视、沟通 | 质量目标管理（§2.2） |
| ISO 9001 | §7.1.6 组织知识 | 确定、保持和更新过程运行所需知识 | 全局知识库（§2.8） |
| ISO 9001 | §7.4 沟通 | 内外部沟通机制 | 异常告警与升级通知（§2.1/§2.4） |
| ISO 9001 | §9.2 内部审核 | 审核方案、审核实施、纠正措施 | 内部审核管理（§2.11） |
| ISO 9001 | §9.3 管理评审 | 管理评审输入/输出、措施跟踪 | 管理评审（§2.12） |
| IATF 16949 | §4.4.1.2 产品安全 | 产品安全特性识别、特殊批准、可追溯性 | DFMEA/PFMEA产品安全特性（§2.3） |
| IATF 16949 | §6.1.2.3 应急计划 | 关键设备故障、供应中断等应急预案 | 应急计划管理（待规划） |
| IATF 16949 | §7.1.5.1.1 MSA | 测量系统统计研究（GR&R/偏倚/线性/稳定性） | MSA测量系统分析（§2.14） |
| IATF 16949 | §8.3.3.3 特殊特性 | 特殊特性识别、贯穿标识、符号转换表 | 特殊特性管理（§2.13） |
| IATF 16949 | §8.3.4.4 产品批准(PPAP) | 生产件批准18要素提交与审批 | PPAP管理（§2.6） |
| IATF 16949 | §8.5.1.5 全面生产维护 | TPM系统、OEE/MTBF/MTTR目标 | 设备维护管理（待集成MES） |
| IATF 16949 | §9.2.2.1-4 三类审核 | 体系审核+制造过程审核+产品审核 | 内部审核管理（§2.11） |
| IATF 16949 | §9.3.2.1 不良质量成本 | 内部和外部不符合成本统计 | 质量成本统计（纳入管理评审§2.12） |
| IATF 16949 | §10.2.3 问题解决 | 结构化问题解决、根因分析、防错 | 8D/CAPA（§2.4） |
| IATF 16949 | §10.2.4 防错 | 防错方法识别、防错装置失效试验 | PFMEA控制措施（§2.3） |
| IATF 16949 | §10.2.5-6 保修与失效分析 | 保修管理、NTF分析、使用现场失效分析 | 客户质量保修管理（§2.7） |

## 4. 数据模型设计

### 4.1 FMEA知识图谱统一模型 (DFMEA + PFMEA)

FMEA知识图谱采用统一的图数据库（Neo4j）承载DFMEA和PFMEA两个分析维度。两者共享Function、FailureMode、FailureCause、FailureEffect、ControlMeasure等核心节点类型，同时各自扩展特有节点和关系。

**核心通用节点类型（DFMEA & PFMEA 共享）:**

```
Node: Function (功能)
  Properties: function_id, name, description, requirement_spec, version,
              fmea_type(pfmea|dfmea), source_ref
  Index: function_id (unique)

Node: FailureMode (失效模式)
  Properties: fm_id, name, description, potential_harm, version,
              detection_method, severity_rating(1-10)
  Index: fm_id (unique)

Node: FailureCause (失效原因)
  Properties: fc_id, name, description, occurrence_rating(1-10), version,
              cause_type(design|process|material|environment)
  Index: fc_id (unique)

Node: FailureEffect (失效影响)
  Properties: fe_id, name, description, severity_rating(1-10), version,
              effect_level(end_user|product|process|system)
  Index: fe_id (unique)

Node: ControlMeasure (控制措施)
  Properties: cm_id, name, description, type(prevention/detection),
              detection_rating(1-10), status, owner, due_date, version
  Index: cm_id (unique)
```

**PFMEA 特有节点:**

```
Node: Process (工序/过程)
  Properties: process_id, name, description, process_number(OP10/OP20/...),
              process_type, station_id, line_id, version
  Index: process_id (unique), process_number

Node: Product (产品)
  Properties: product_id, sku, name, category, product_family, version
  Index: product_id (unique)
```

**DFMEA 特有节点（详见§2.2.3）:**

```
Node: SystemItem (系统项)
  Properties: item_id, name, level(1-5), parent_item_id, part_number,
              drawing_number, material_spec
  Index: item_id (unique)

Node: DesignParameter (设计参数)
  Properties: param_id, name, value, tolerance_lsl, tolerance_usl, unit,
              specification, parameter_type(dimensional|material|performance)
  Index: param_id (unique)

Node: Interface (接口)
  Properties: interface_id, name, type(mechanical|electrical|software|hydraulic|thermal),
              from_system, to_system, interface_function
  Index: interface_id (unique)

Node: DVPTask (设计验证任务)
  Properties: dvp_id, name, test_condition, sample_size,
              acceptance_criteria, status(pending|passed|failed), result,
              completion_date
  Index: dvp_id (unique)
```

**通用关系类型（DFMEA & PFMEA 共享）:**

```
Relationship: HAS_FAILURE_MODE
  From: Function → To: FailureMode
  Properties: created_at, created_by, notes

Relationship: HAS_CAUSE
  From: FailureMode → To: FailureCause
  Properties: occurrence_rating, rpn_contribution, data_source

Relationship: HAS_EFFECT
  From: FailureMode → To: FailureEffect
  Properties: severity_rating, rpn_contribution

Relationship: SEVERITY
  From: FailureMode → To: FailureEffect
  Properties: rating, rpn(severity*occurrence*detection), ap(action_priority)

Relationship: RELATED_TO
  From: FailureMode → To: FailureMode
  Properties: relation_type(similar|cascading|coupling), confidence_score
```

**PFMEA 特有关系:**

```
Relationship: HAS_FUNCTION
  From: Process → To: Function
  Properties: sequence_order, characteristic_type(process|product)

Relationship: CONTROLLED_BY
  From: FailureCause → To: ControlMeasure
  Properties: control_type(prevention), control_method(poka-yoke|spc|inspection)

Relationship: DETECTED_BY
  From: FailureEffect → To: ControlMeasure
  Properties: control_type(detection), detect_method

Relationship: BELONGS_TO
  From: Process → To: Product
  Properties: association_date
```

**DFMEA 特有关系（详见§2.2.3）:**

```
Relationship: PERFORMS_FUNCTION
  From: SystemItem → To: Function
  Properties: item_level, design_owner

Relationship: SPECIFIED_BY
  From: Function → To: DesignParameter
  Properties: parameter_type, criticality(cc|sc|os)

Relationship: CAUSED_BY_DESIGN
  From: FailureCause → To: DesignParameter
  Properties: deviation_direction(low|high|either), tolerance_sensitivity

Relationship: HAS_INTERFACE
  From: SystemItem → To: Interface
  Properties: interface_position

Relationship: HAS_INTERFACE_FAILURE
  From: Interface → To: FailureMode
  Properties: failure_mechanism

Relationship: VERIFIED_BY
  From: ControlMeasure → To: DVPTask
  Properties: verification_method, sample_size, required_result

Relationship: RESULT_UPDATES
  From: DVPTask → To: FailureMode
  Properties: updated_at, new_detection_rating
```

**知识图谱查询示例:**

```cypher
// 查询某PFMEA工序的所有风险及对应措施
MATCH (p:Process {process_id: 'OP10'})-[:HAS_FUNCTION]->(f:Function)
      -[:HAS_FAILURE_MODE]->(fm:FailureMode)
OPTIONAL MATCH (fm)-[:HAS_CAUSE]->(fc:FailureCause)
      -[:CONTROLLED_BY]->(cm:ControlMeasure)
OPTIONAL MATCH (fm)-[:HAS_EFFECT]->(fe:FailureEffect)
      -[:DETECTED_BY]->(dm:ControlMeasure)
RETURN p.name, f.name, fm.name, fc.name, cm.name, fe.name, dm.name, fm.severity

// 查询某DFMEA系统项的所有设计失效及关联参数
MATCH (si:SystemItem {item_id: 'SYS-001'})-[:PERFORMS_FUNCTION]->(f:Function)
      -[:HAS_FAILURE_MODE]->(fm:FailureMode)
OPTIONAL MATCH (fm)-[:HAS_CAUSE]->(fc:FailureCause)
      -[:CAUSED_BY_DESIGN]->(dp:DesignParameter)
OPTIONAL MATCH (si)-[:HAS_INTERFACE]->(i:Interface)
      -[:HAS_INTERFACE_FAILURE]->(ifm:FailureMode)
RETURN si.name, f.name, fm.name, fc.name, dp.name, i.name, ifm.name

// 变更影响分析：某设计参数修改影响的范围
MATCH (dp:DesignParameter {param_id: 'DIM-001'})<-[:CAUSED_BY_DESIGN]-(fc:FailureCause)
      <-[:HAS_CAUSE]-(fm:FailureMode)<-[:HAS_FAILURE_MODE]-(f:Function)      <-[:PERFORMS_FUNCTION]-(si:SystemItem)
RETURN dp.name, fc.name, fm.name, f.name, si.name
```


### 4.2 关系数据模型 (PostgreSQL)

**FMEA视图映射表** (将图数据库部分属性映射至关系表以便快速查询):

```sql
-- FMEA主表
CREATE TABLE fmea_documents (
    fmea_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_no    VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    title          VARCHAR(200) NOT NULL,
    product_id     VARCHAR(50),
    process_id     VARCHAR(50),
    fmea_type      VARCHAR(20) CHECK (fmea_type IN ('PFMEA', 'DFMEA')),
    status         VARCHAR(20) DEFAULT 'draft',
    version        INTEGER DEFAULT 1,
    created_by     VARCHAR(100),
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_by     VARCHAR(100),
    approved_by    VARCHAR(100),
    approved_at    TIMESTAMP
);

CREATE INDEX idx_fmea_status ON fmea_documents(status);
CREATE INDEX idx_fmea_product ON fmea_documents(product_id);
CREATE INDEX idx_fmea_pl ON fmea_documents(product_line_code);

-- SPC采集数据表
CREATE TABLE spc_measurements (
    measurement_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    characteristic_id VARCHAR(50) NOT NULL,
    process_id       VARCHAR(50) NOT NULL,
    sub_group        INTEGER NOT NULL,
    sample_values    DOUBLE PRECISION[],
    sub_group_mean   DOUBLE PRECISION,
    sub_group_range  DOUBLE PRECISION,
    measured_at      TIMESTAMP NOT NULL,
    device_id        VARCHAR(50),
    operator         VARCHAR(100)
);

CREATE INDEX idx_spc_char ON spc_measurements(characteristic_id, process_id, measured_at);
CREATE INDEX idx_spc_pl ON spc_measurements(product_line_code);

-- 8D报告表
CREATE TABLE capa_eightd (
    report_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_no      VARCHAR(50) UNIQUE NOT NULL,
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- 产品线隔离
    title            VARCHAR(200) NOT NULL,
    d1_team          JSONB,  -- 团队信息JSON
    d2_description   TEXT,   -- 5W2H问题描述
    d3_interim       JSONB,  -- 临时措施
    d4_root_cause    TEXT,   -- 根因分析
    d5_correction    JSONB,  -- 永久措施
    d6_verification  JSONB,  -- 验证结果
    d7_prevention    TEXT,   -- 预防复发
    d8_closure       JSONB,  -- 关闭信息
    status           VARCHAR(20) DEFAULT 'draft', -- draft/d2/d3/d4/d5/d6/d7/closed
    fmea_ref_id      UUID,   -- 关联FMEA
    scar_ref_id      UUID,   -- 关联SCAR（供应商纠正措施）
    defect_source    VARCHAR(50),  -- 问题来源：IQC拒收/产线发现/客诉/审核发现
    severity_level   VARCHAR(20),  -- 严重等级
    due_date         DATE,
    created_by       VARCHAR(100),
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fmea_ref_id) REFERENCES fmea_documents(fmea_id)
);

CREATE INDEX idx_capa_pl ON capa_eightd(product_line_code);

-- 用户与角色
CREATE TABLE users (
    user_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username     VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    email        VARCHAR(100),
    avatar       VARCHAR(255),
    locale       VARCHAR(10) DEFAULT 'zh-CN',
    is_active    BOOLEAN DEFAULT TRUE,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- RBAC: 角色定义
CREATE TABLE roles (
    role_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_code    VARCHAR(50) UNIQUE NOT NULL,  -- admin, quality_manager, quality_engineer, process_engineer, sqe, cqe, viewer
    role_name    VARCHAR(100) NOT NULL,
    description  TEXT,
    is_system    BOOLEAN DEFAULT FALSE  -- 系统内置角色不可删除
);

-- RBAC: 权限定义
CREATE TABLE permissions (
    permission_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    module          VARCHAR(50) NOT NULL,   -- fmea, capa, spc, supplier, customer, knowledge_base, dashboard, admin
    action          VARCHAR(50) NOT NULL,   -- view, create, edit, delete, approve, export
    description     TEXT,
    UNIQUE(module, action)
);

-- RBAC: 角色-权限关联
CREATE TABLE role_permissions (
    role_id         UUID REFERENCES roles(role_id),
    permission_id   UUID REFERENCES permissions(permission_id),
    PRIMARY KEY (role_id, permission_id)
);

-- RBAC: 用户-角色-产品线关联（同一用户在不同产品线可以拥有不同角色）
CREATE TABLE user_role_assignments (
    assignment_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID REFERENCES users(user_id),
    role_id          UUID REFERENCES roles(role_id),
    product_line_code VARCHAR(20) REFERENCES product_lines(pl_code),  -- NULL表示全局角色
    granted_by       UUID REFERENCES users(user_id),
    granted_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, role_id, product_line_code)
);
```

### 4.3 数据同步策略 (PostgreSQL ↔ Neo4j)

系统采用 **PostgreSQL 为写主库（Write Master）、Neo4j 为读优化副本** 的架构模式。

#### 4.3.1 数据写入流

```
用户操作（创建/更新FMEA条目）
  │
  ▼
① 写入 PostgreSQL（事务保证，立即生效）
  │
  ▼
② 发送变更事件到消息队列 (Kafka/RabbitMQ)
  │
  ▼
③ 图同步服务消费事件，写入 Neo4j（异步，延迟 ≤ 5s）
  │
  ▼
④ 同步结果记录到 sync_log 表（成功/失败/重试次数）
```

#### 4.3.2 同步规则

| 规则 | 说明 |
|------|------|
| 写主库 | 所有业务写操作以 PostgreSQL 为准（ACID事务保证） |
| 异步同步 | PostgreSQL → Neo4j 通过 Debezium CDC 监听 WAL 日志，事件发送至 Kafka，延迟目标 ≤ 5s |
| 最终一致性 | Neo4j 数据允许短暂滞后，不影响业务写入操作 |
| 幂等同步 | 同步消息支持幂等重放，重复消费不产生脏数据 |
| 失败重试 | 同步失败自动重试3次（间隔1s/5s/30s），仍失败则记入dead-letter队列并告警 |
| 全量校验 | 每日凌晨运行一致性校验Job，对比PostgreSQL与Neo4j的节点/关系计数，差异自动修复 |

#### 4.3.3 读取策略

| 场景 | 数据源 | 说明 |
|------|--------|------|
| FMEA编辑器（表格模式） | PostgreSQL | 结构化查询、分页、排序、筛选 |
| 知识图谱可视化 | Neo4j | 图遍历、路径查询、子图展开 |
| 变更影响分析 | Neo4j | 多跳关系遍历，优势明显 |
| AI语义搜索 | Elasticsearch + 向量DB | 全文检索 + 语义相似度 |
| SPC/KPI数据 | PostgreSQL | 聚合统计查询 |
| FMEA列表/筛选 | PostgreSQL | 常规关系查询 |

#### 4.3.4 降级策略

- **Neo4j不可用时**: 知识图谱可视化降级为PostgreSQL JSONB树形结构渲染（功能受限，不支持多跳遍历）
- **同步延迟超阈值(>30s)时**: 前端图谱界面显示"数据同步中"提示，引导用户切换至表格视图
- **全量校验发现差异**: 自动从PostgreSQL重建Neo4j中受影响的子图，不中断在线服务

#### 4.3.5 同步日志表

```sql
CREATE TABLE sync_logs (
    sync_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_table    VARCHAR(100) NOT NULL,    -- 源表名
    record_id       UUID NOT NULL,            -- 源记录ID
    operation       VARCHAR(20) NOT NULL,     -- INSERT/UPDATE/DELETE
    target          VARCHAR(20) DEFAULT 'neo4j',  -- 同步目标
    status          VARCHAR(20) NOT NULL,     -- pending/synced/failed/dead_letter
    retry_count     INTEGER DEFAULT 0,
    error_message   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    synced_at       TIMESTAMP
);

CREATE INDEX idx_sync_status ON sync_logs(status, created_at);
```

---

## 5. 权限与安全模型

### 5.1 RBAC权限矩阵

系统采用基于角色的访问控制（RBAC），并结合产品线维度实现数据隔离。同一用户在不同产品线可拥有不同角色。

#### 5.1.1 系统内置角色

| 角色代码 | 角色名称 | 说明 |
|----------|---------|------|
| admin | 系统管理员 | 全局管理权限，不受产品线限制 |
| quality_manager | 质量经理 | 按产品线分配，拥有审批权限 |
| quality_engineer | 质量工程师 | 按产品线分配，FMEA/CAPA/SPC核心操作 |
| process_engineer | 工艺工程师 | 按产品线分配，PFMEA/控制计划/SPC操作 |
| sqe | 供应商质量工程师 | 按产品线分配，供应商质量管理操作 |
| cqe | 客户质量工程师 | 按产品线分配，客户质量管理操作 |
| viewer | 只读查看者 | 按产品线分配，仅查看权限 |

#### 5.1.2 权限矩阵（模块 × 角色）

| 模块 | admin | quality_manager | quality_engineer | process_engineer | sqe | cqe | viewer |
|------|-------|-----------------|------------------|-----------------|-----|-----|--------|
| 仪表盘 | 全部 | 查看+导出 | 查看 | 查看 | 查看 | 查看 | 查看 |
| DFMEA | 全部 | 查看+审批 | CRUD+导出 | 查看+编辑 | 查看 | 查看 | 查看 |
| PFMEA | 全部 | 查看+审批 | CRUD+导出 | CRUD+导出 | 查看 | 查看 | 查看 |
| 控制计划 | 全部 | 查看+审批 | CRUD+导出 | CRUD+导出 | 查看 | 查看 | 查看 |
| 8D/CAPA | 全部 | 查看+审批 | CRUD | CRUD | 创建+编辑 | 创建+编辑 | 查看 |
| SPC | 全部 | 查看+导出 | CRUD+导出 | CRUD+导出 | 查看 | 查看 | 查看 |
| 供应商质量 | 全部 | 查看+审批 | 查看 | 查看 | CRUD+审批 | 查看 | 查看 |
| 客户质量 | 全部 | 查看+审批 | 查看 | 查看 | 查看 | CRUD+审批 | 查看 |
| 全局知识库 | 全部 | 查看+导出 | 查看+导出 | 查看+导出 | 查看 | 查看 | 查看 |
| 内部审核 | 全部 | 查看+审批 | 查看 | 查看 | 查看 | 查看 | — |
| 系统管理 | 全部 | — | — | — | — | — | — |

> 注：CRUD = 创建(Create)、查看(Read)、更新(Update)、删除(Delete)

#### 5.1.3 数据隔离规则

- **产品线隔离**: 用户只能访问其被授权产品线的业务数据
- **全局角色**: `product_line_code = NULL` 时角色适用于所有产品线
- **跨产品线查看**: 全局知识库对所有用户只读开放
- **审批链**: 审批操作要求至少 `quality_manager` 角色

### 5.2 审计日志

所有关键业务操作需记录审计日志，包括：
- 数据的创建、修改、删除
- 状态流转（CAPA/8D状态变更、FMEA审批等）
- 权限变更（角色分配、产品线授权）
- 登录/登出事件

```sql
CREATE TABLE audit_logs (
    log_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    table_name      VARCHAR(100) NOT NULL,
    record_id       UUID NOT NULL,
    action          VARCHAR(20) NOT NULL,  -- INSERT/UPDATE/DELETE/STATUS_CHANGE/LOGIN
    changed_fields  JSONB,
    old_values      JSONB,
    new_values      JSONB,
    product_line_code VARCHAR(20),
    operated_by     UUID REFERENCES users(user_id),
    operated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip_address      VARCHAR(50),
    user_agent      TEXT
);

CREATE INDEX idx_audit_table ON audit_logs(table_name, record_id);
CREATE INDEX idx_audit_time ON audit_logs(operated_at);
CREATE INDEX idx_audit_user ON audit_logs(operated_by);
```

### 5.3 数据安全

| 维度 | 要求 |
|------|------|
| 传输加密 | 全链路HTTPS/TLS 1.3 |
| 存储加密 | 敏感字段（密码、API Key）AES-256加密存储 |
| 密码策略 | 最低8位，含大小写+数字+特殊字符，90天过期 |
| 会话管理 | JWT Token，有效期2小时，支持刷新 |
| API安全 | 基于API Key + RBAC的接口鉴权，速率限制 |
| 数据脱敏 | 全局知识库数据脱敏（去除客户/供应商敏感信息） |
| 合规 | 支持数据导出/删除请求（GDPR合规预留） |

---

## 6. UI/UX规范

### 6.1 设计原则

| 原则 | 说明 |
|------|------|
| 一致性 | 所有模块统一设计语言，组件复用率 > 80% |
| 效率优先 | 质量工程师高频操作（FMEA编辑、SPC查看）≤ 3次点击可达 |
| 信息密度 | 支持紧凑/宽松布局切换，适配不同工作场景 |
| 响应式 | 支持1280px～2560px屏幕宽度，优先适配1920px桌面端。**移动端/平板暂不支持**（Phase 2评估车间平板场景：IQC检验录入、SPC看板巡检） |
| 无障碍 | WCAG 2.1 AA级合规，支持键盘导航 |

### 6.2 全局导航结构

```
┌─────────────────────────────────────────────────────────────┐
│  Logo    [产品线选择器 ▼]      搜索栏        通知🔔  用户头像  │
├──────────┬──────────────────────────────────────────────────┤
│ 侧边导航  │                  主内容区                        │
│          │                                                 │
│ 📊 仪表盘  │                                                 │
│ 📋 FMEA   │     面包屑导航 > 当前页面                         │
│   DFMEA  │                                                 │
│   PFMEA  │     ┌─────────────────────────────────┐         │
│ 📝 控制计划 │     │       页面内容区                 │         │
│ 🔧 8D/CAPA│     │                                 │         │
│ 📈 SPC    │     │                                 │         │
│ 🏭 供应商  │     │                                 │         │
│ 👥 客户   │     └─────────────────────────────────┘         │
│ 📚 知识库  │                                                 │
│ ⚙️ 设置   │                                                 │
├──────────┴──────────────────────────────────────────────────┤
│  状态栏：当前产品线 | 系统状态 | 版本号                        │
└─────────────────────────────────────────────────────────────┘
```

### 6.3 核心页面规范

#### 6.3.1 FMEA编辑器

- **布局**: 左侧功能树/工序流 + 右侧FMEA表格编辑区
- **表格**: 支持行内编辑、冻结列（工序/功能/失效模式）、条件格式（RPN高值标红）
- **图谱面板**: 右侧可展开的知识图谱面板，显示当前选中行的关联图谱
- **AI推荐**: 编辑失效模式时底部弹出推荐卡片，展示历史相似条目

#### 6.3.2 SPC控制图

- **布局**: 上方控制图 + 下方数据表格
- **交互**: 支持区间缩放、数据点悬浮详情、异常点高亮标注
- **告警**: 判异规则触发时控制图区域边框变红，并弹出告警卡片

#### 6.3.3 知识图谱可视化

- **布局**: 全屏图谱画布 + 左侧筛选面板 + 右侧节点详情面板
- **交互**: 力导向布局，支持缩放/拖拽/框选，双击展开子图
- **模式切换**: 支持图谱视图 / 表格视图 / 树形视图三种展示模式

#### 6.3.4 控制计划

- **布局**: 工序流导航条（顶部横向OP编号） + 下方CP表格编辑区
- **联动**: 选中CP条目时高亮关联的PFMEA行，支持跳转编辑
- **特殊特性标注**: CC/SC特性行底色区分（CC红底/SC黄底），一键生成特殊特性清单

#### 6.3.5 供应商质量管理

- **布局**: 左侧供应商列表（含评级标签） + 右侧详情面板（Tab切换：档案/IQC/SCAR/绩效）
- **看板**: 供应商PPM趋势图、批次合格率瀑布图、红黄绿评级卡片
- **IQC**: 检验批列表支持扫码快速录入，AQL方案自动计算抽样数

#### 6.3.6 客户质量管理

- **布局**: 左侧客户列表 + 右侧详情面板（Tab切换：客诉/RMA/审核/CSR/满意度）
- **看板**: 客户PPM趋势图、客诉分类饼图、严重等级分布柱状图
- **时效**: 客诉卡片显示倒计时（距离回复期限），超期项自动置顶并标红

#### 6.3.7 全局知识库

- **布局**: 搜索栏（支持自然语言） + 分类索引面板 + 结果列表/图谱切换
- **推荐**: 新建FMEA时弹出"相关经验推荐"侧边栏，按相似度排序展示历史条目
- **溯源**: 每条知识条目标注来源产品线和原始FMEA编号（脱敏后），支持点击查看上下文

### 6.4 主题与色彩

| 类别 | 色值 | 用途 |
|------|------|------|
| 主色 | #1677FF | 导航、按钮、链接 |
| 成功 | #52C41A | 合格状态、正常SPC点 |
| 警告 | #FAAD14 | 接近控制限、即将到期 |
| 危险 | #FF4D4F | 不合格、SPC异常、高RPN |
| 中性灰 | #F5F5F5 ~ #1F1F1F | 背景、边框、文字层级 |
| 图谱节点色 | 详见§2.2.5 | 按节点类型区分 |

### 6.5 可观测性与运维

为达成 §3.5.2 承诺的 99.5%/99.9% SLA，系统需内置完整的可观测性基础设施：

| 层级 | 工具 | 监控项 |
|------|------|--------|
| 指标(Metrics) | Prometheus + Grafana | API响应时间P50/P95/P99、QPS、错误率、数据库连接池、Neo4j查询耗时、Kafka消费延迟 |
| 日志(Logging) | Loki / ELK | 结构化JSON日志、请求追踪ID、错误堆栈、审计日志聚合 |
| 追踪(Tracing) | Jaeger / OpenTelemetry | 跨服务调用链路追踪、慢查询定位、Neo4j同步链路 |
| 告警(Alerting) | Alertmanager + 企业微信/钉钉 | API错误率>1%、SPC同步延迟>30s、CAPA超期未处理、磁盘>80%、数据库连接池耗尽 |
| 健康检查 | K8s Liveness/Readiness | 所有服务 /health 端点，30s探测间隔，连续3次失败自动重启 |

---

## 7. 实施路线图

### 7.1 总体规划

```
Phase 1 (M1-M4)        Phase 2 (M5-M8)        Phase 3 (M9-M12)       Phase 4 (M13-M16)
基础平台 + 核心FMEA     供应商/客户质量模块       AI + 知识图谱增强        高级分析 + 生态集成
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 7.2 阶段详情

#### Phase 1: 基础平台 + 核心模块 (Month 1-4)

> **MVP范围 (M1-M2)**: 用户认证 + PFMEA编辑器 + 8D/CAPA基础流程 + 简版仪表盘。MVP以单产品线可跑通PFMEA→8D闭环为验收标准。

| 交付物 | 优先级 | 里程碑 | 说明 |
|--------|--------|--------|------|
| 用户认证与RBAC权限系统 | P0 | M1 | MVP必须项 |
| 产品线数据架构与隔离 | P0 | M1 | MVP必须项 |
| PFMEA编辑器（含RPN/AP计算） | P0 | M2 | MVP核心交付 |
| 8D/CAPA工作流（基础版） | P0 | M2 | MVP核心交付，D1-D5步骤 |
| DFMEA编辑器 | P0 | M3 | MVP后补充 |
| 控制计划编辑器 + FMEA联动 | P0 | M3 | MVP后补充 |
| SPC控制图（X-bar R、I-MR） | P0 | M3 | MVP后补充 |
| 仪表盘（KPI卡片+趋势图） | P0 | M4 | 聚合各模块数据 |
| 特殊特性贯穿管理 | P0 | M2 | 与FMEA/CP联动 |
| 产品安全特性管理 | P0 | M2 | DFMEA/PFMEA安全特性 |
| 质量目标管理 | P1 | M3 | 三级目标树 |
| 内部审核管理 | P0 | M3 | 体系/过程/产品审核 |
| 基础审计日志 | P0 | M4 | 合规基础 |

#### Phase 2: 供应商/客户质量 + 版本管理 (Month 5-8)

| 交付物 | 优先级 | 里程碑 |
|--------|--------|--------|
| 供应商档案 + IQC来料检验 | P0 | M5 |
| SCAR管理 + 8D关联 | P1 | M5 |
| 客诉管理 + RMA退货 | P0 | M6 |
| 供应商/客户质量看板 | P0 | M6 |
| FMEA/CP版本管理与变更对比 | P1 | M7 |
| 批量导入/导出（Excel） | P2 | M7 |
| 供应商审核与绩效评价 | P1 | M8 |
| 客户审核管理 | P1 | M8 |
| MSA测量系统分析 | P1 | M6 |
| APQP项目质量策划 | P1 | M7 |
| PPAP管理 | P1 | M8 |
| 管理评审模块 | P1 | M8 |

#### Phase 3: AI + 知识图谱增强 (Month 9-12)

| 交付物 | 优先级 | 里程碑 |
|--------|--------|--------|
| Neo4j知识图谱数据迁移 | P1 | M9 |
| 知识图谱可视化（D3.js/G6） | P1 | M9 |
| 全局知识库（跨产品线聚合） | P1 | M10 |
| LLM RAG语义搜索 | P2 | M10 |
| FMEA草稿AI推荐 | P2 | M11 |
| 变更影响分析（图遍历） | P2 | M11 |
| SPC-FMEA异常关联推荐 | P2 | M12 |
| 多人协同编辑 | P2 | M12 |

#### Phase 4: 高级分析 + 生态集成 (Month 13-16)

| 交付物 | 优先级 | 里程碑 |
|--------|--------|--------|
| MES集成连接器 | P2 | M13 |
| PLM/ERP集成连接器 | P2 | M13 |
| 8D报告AI草拟 | P3 | M14 |
| 质量趋势AI解读 | P3 | M14 |
| 供应链风险地图 | P3 | M15 |
| 自定义看板（拖拽式） | P3 | M15 |
| 多工厂部署支持 | P3 | M16 |
| SaaS多租户架构 | P3 | M16 |

### 7.3 关键里程碑

```
M2  ──── FMEA编辑器可用（内部Alpha）
M4  ──── 核心模块上线（内部Beta）
M6  ──── 供应商/客户模块上线（有限客户试用）
M8  ──── Phase 2完成（GA v1.0发布）
M12 ──── AI + 知识图谱上线（GA v2.0发布）
M16 ──── 全功能发布（GA v3.0发布）
```

---

## 8. 关键风险与缓解

### 8.1 风险矩阵

| # | 风险 | 影响 | 概率 | 等级 | 缓解策略 |
|---|------|------|------|------|---------|
| R1 | **知识图谱性能瓶颈** — 大规模FMEA图谱（>10万节点）查询响应慢 | 高 | 中 | 🟠 高 | Phase 1使用PostgreSQL JSONB存储图结构，Phase 3再迁移Neo4j；引入图缓存层；限制单次查询深度 |
| R2 | **LLM幻觉风险** — AI推荐的FMEA条目包含错误信息，误导质量决策 | 高 | 高 | 🔴 极高 | 所有AI输出标注"AI建议"标签；强制人工审核节点；限制AI仅推荐历史数据，不生成新内容；记录AI推荐的采纳/拒绝率 |
| R3 | **数据隐私泄露** — 敏感质量数据通过LLM API外泄 | 高 | 低 | 🟡 中 | 采用私有部署LLM或本地推理；全局知识库数据脱敏后再用于RAG检索；禁止将客户/供应商敏感信息发送至外部API |
| R4 | **多系统集成复杂度** — MES/PLM/ERP接口标准不统一导致集成延期 | 中 | 高 | 🟠 高 | Phase 4再启动集成；定义标准化连接器接口；先支持CSV/API批量导入作为过渡方案 |
| R5 | **用户采纳阻力** — 质量工程师习惯Excel管理FMEA，抵触新系统 | 中 | 高 | 🟠 高 | 支持Excel导入导出作为过渡；UI操作体验对标Excel习惯；提供FMEA模板一键导入；安排驻场培训与种子用户计划 |
| R6 | **图数据库与关系数据库同步** — Neo4j与PostgreSQL数据不一致 | 高 | 中 | 🟠 高 | PostgreSQL作为主库（Write Master）；Neo4j通过Change Data Capture (CDC)异步同步；定期一致性校验Job；关键路径降级为PostgreSQL JSONB查询 |
| R7 | **FMEA标准合规性** — 系统不完全符合AIAG & VDA FMEA手册要求 | 中 | 低 | 🟡 中 | 邀请IATF 16949审核员参与需求评审；严格按AIAG & VDA新版手册7步法设计FMEA编辑器；内置合规性检查清单 |
| R8 | **多租户数据串扰** — SaaS模式下不同租户数据隔离失效 | 高 | 低 | 🟡 中 | Phase 4再启用多租户；采用Schema级别隔离（每租户独立Schema）；定期安全审计与渗透测试 |
| R9 | **标准合规性缺失** — 系统功能未覆盖ISO 9001/IATF 16949关键条款，影响认证审核通过 | 高 | 中 | 🟠 高 | 按§3.5.5合规性对照表逐条覆盖；邀请IATF 16949审核员参与需求评审；内部审核/管理评审/特殊特性/MSA等模块纳入Phase 1-2 |

### 8.2 技术决策待定项

| 决策项 | 候选方案 | 决策时间点 | 决策依据 |
|--------|---------|-----------|---------|
| 前端框架 | React 18+ vs Vue 3+ | Phase 1 M1 | 团队技术栈、组件库成熟度、招聘难度 |
| 后端框架 | Spring Boot vs FastAPI | Phase 1 M1 | 团队语言偏好、微服务生态、性能需求 |
| 图数据库时机 | Phase 1引入 vs Phase 3引入 | Phase 1 M1 | 初期数据量评估、团队图数据库经验 |
| LLM选型 | 私有部署开源模型 vs 商业API + RAG | Phase 3 M9 | 数据安全策略、推理成本、精度要求 |
| 部署模式 | 单体先行 vs 微服务起步 | Phase 1 M1 | 团队规模、运维能力、扩展预期 |

---

## 9. 测试策略

### 9.1 测试分层

| 层级 | 范围 | 工具 | 覆盖目标 |
|------|------|------|---------|
| 单元测试 | 业务逻辑、工具函数、数据校验 | Jest / Pytest / JUnit | ≥ 80% 行覆盖率 |
| 集成测试 | API接口、数据库操作、服务间调用 | Supertest / TestContainers | 所有API端点100%覆盖 |
| E2E测试 | 关键用户流程 | Playwright / Cypress | FMEA编辑→保存→审批、8D全流程、SPC异常→CAPA |
| 性能测试 | API响应时间、并发压力 | k6 / Locust | 验证§3.5.1所有性能指标 |
| 安全测试 | 权限隔离、RBAC、注入防护 | OWASP ZAP / 手动渗透 | 产品线数据隔离、角色权限边界 |

### 9.2 质量管理专项测试

作为质量管理系统，以下专项测试直接影响产品合规性和用户信任：

| 专项 | 测试内容 | 验证标准 |
|------|---------|---------|
| FMEA评分计算 | RPN = S×O×D 计算、AP行动优先级判定 | 严格对照 AIAG & VDA FMEA手册第5版评分标准表 |
| SPC判异规则 | 8大判异准则的触发逻辑 | 使用已知异常数据集（含各规则触发场景）回归验证 |
| AQL抽样方案 | IQC检验的AQL抽样数计算 | 对照 GB/T 2828.1 / ISO 2859-1 抽样表 |
| 数据隔离 | 跨产品线数据不可见 | 自动化测试：用户A(产品线X)无法查询/修改产品线Y数据 |
| 审批流 | FMEA/CP/CAPA状态流转 | 验证越权操作被拒绝、审批链完整性 |
| Neo4j同步 | PostgreSQL写入后Neo4j一致性 | 写入后轮询验证，5s内同步完成率 ≥ 99.9% |

### 9.3 持续集成

```
代码提交 → 单元测试(≤2min) → 集成测试(≤10min) → 构建镜像
  → 部署到Staging → E2E测试(≤15min) → 性能测试(每日)
  → 人工审批 → 部署到Production
```

---

## 附录

### 附录A: 质量管理术语表

| 英文 | 中文 | 缩写 | 说明 |
|------|------|------|------|
| Failure Mode and Effects Analysis | 失效模式与影响分析 | FMEA | 识别潜在失效模式、评估影响和风险、制定控制措施的系统方法 |
| Design FMEA | 设计失效模式与影响分析 | DFMEA | 面向产品设计阶段的FMEA |
| Process FMEA | 过程失效模式与影响分析 | PFMEA | 面向制造过程的FMEA |
| Risk Priority Number | 风险优先级数 | RPN | S×O×D，用于失效模式风险排序 |
| Action Priority | 行动优先级 | AP | AIAG & VDA新版标准中替代RPN的优先级判定方法 |
| Severity | 严重度 | S | 失效影响的严重程度评级(1-10) |
| Occurrence | 频度 | O | 失效原因的发生概率评级(1-10) |
| Detection | 探测度 | D | 现有控制措施的检出能力评级(1-10) |
| Control Plan | 控制计划 | CP | 定义过程控制要求的文档，源自PFMEA |
| Statistical Process Control | 统计过程控制 | SPC | 利用统计方法监控过程稳定性 |
| Corrective and Preventive Action | 纠正与预防措施 | CAPA | 问题的根因分析与闭环纠正预防 |
| 8 Disciplines | 八步问题解决法 | 8D | 结构化问题解决方法论 (D1-D8) |
| Critical Characteristic | 关键特性 | CC | 影响安全/法规的关键产品/过程特性 |
| Significant Characteristic | 重要特性 | SC | 影响功能/性能的重要产品/过程特性 |
| Incoming Quality Control | 来料质量检验 | IQC | 对供应商来料的进货检验 |
| Supplier Corrective Action Request | 供应商纠正措施申请 | SCAR | 向供应商发起的质量问题纠正要求 |
| Return Merchandise Authorization | 退货授权 | RMA | 客户退货流程管理 |
| Parts Per Million | 百万分之缺陷率 | PPM | 质量水平指标 = 不良数/总数×10⁶ |
| Process Capability Index | 过程能力指数 | CPK | 衡量过程满足规格的能力 |
| Acceptance Quality Limit | 接收质量限 | AQL | IQC抽样检验的可接受质量水平 |
| Change Data Capture | 变更数据捕获 | CDC | 捕获数据库变更并同步至下游系统的技术 |
| Retrieval Augmented Generation | 检索增强生成 | RAG | 结合知识库检索与LLM生成的AI技术 |

---
