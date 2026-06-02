# 8D D4/D5 智能推荐设计规格

**日期**: 2026-06-02  
**状态**: 待实施  
**优先级**: P2  
**依赖**: FMEA 知识图谱基础设施（已完成）

---

## 背景

当前 CAPA 8D 流程中，D4（根因分析）和 D5（纠正措施）步骤是纯 TextArea 手动输入。D7（预防复发）已有基于 FMEA 图匹配的推荐系统，但 D4/D5 缺乏智能辅助。

本设计为 D4/D5 步骤引入 FMEA 图匹配推荐，帮助质量工程师快速复用已有知识，减少重复分析工作。

## 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 触发时机 | 进入 D4 步骤时自动触发 | 体验最佳，用户无需知道功能存在 |
| 数据来源 | FMEA 图匹配（v1） | 先实现核心能力，全混合管道（规则+图+历史CAPA+LLM）记入 roadmap 后续实现 |
| D5 推荐内容 | FMEA 已有措施 + 规则引擎通用建议 | 覆盖面最广，既有具体措施又有通用兜底 |
| UI 形态 | 推荐面板（表单上方） | 与 D7RecPanel 模式一致，复用现有组件模式 |

---

## 架构

### 数据流

```
CAPA 进入 D4 步骤 (status = D4_ROOT_CAUSE)
    |
    v
前端 CAPADetailPage 检测状态变化
    |
    +--> GET /api/capa/{id}/d4-fmea-recommendations
    |       |
    |       v
    |    capa_recommendation_service.get_d4_recommendations()
    |       |
    |       +--> 提取 D2 描述关键词 (extract_keywords)
    |       |
    |       +--> 策略 A: 关联 FMEA (fmea_ref_id)
    |       |    图遍历: FailureMode <--CAUSE_OF-- FailureCause
    |       |    关键词匹配: FailureCause.name/description vs D2 关键词
    |       |
    |       +--> 策略 B: 跨 FMEA 关键词匹配
    |       |    同产品线其他 FMEA 的 FailureCause 名称/描述
    |       |
    |       +--> 策略 C: 规则引擎补充
    |       |    复用 FAILURE_CHAIN_MAP + 动词模式
    |       |
    |       v
    |    返回 D4RecommendationResponse
    |
    +--> GET /api/capa/{id}/d5-fmea-recommendations
    |       |
    |       v
    |    capa_recommendation_service.get_d5_recommendations()
    |       |
    |       +--> 基于 D4 根因文本提取关键词
    |       |
    |       +--> 图遍历三条路径:
    |       |    FailureCause --PREVENTED_BY--> PreventionControl
    |       |    FailureCause --DETECTED_BY--> DetectionControl
    |       |    FailureMode --DETECTED_BY--> DetectionControl
    |       |
    |       +--> 规则引擎: 基于 AP 级别 + 失效模式关键词生成通用措施
    |       |
    |       v
    |    返回 D5RecommendationResponse (两区: 已有措施 + 通用建议)
    |
    v
前端 D4RecPanel / D5RecPanel 组件
    |
    +--> 显示推荐列表 (表单上方)
    +--> 用户点击"采纳" --> 追加到 TextArea
    +--> 用户可跳过
```

### 系统边界

- **输入**：CAPA 的 D2 描述、D3 临时措施、D4 根因（D5 用）、FMEA 关联信息
- **输出**：推荐列表（D4 根因候选 / D5 措施候选）
- **依赖**：FMEA 图数据（JSONB）、`extract_keywords()`、规则引擎模式
- **不影响**：CAPA 状态机、FMEA 数据、D7 推荐系统

---

## 后端实现

### 新建文件

`backend/app/services/capa_recommendation_service.py`

### 核心函数

#### D4 推荐

```python
def get_d4_recommendations(
    capa_data: dict,        # {d2_description, d3_interim, fmea_ref_id, fmea_node_id, product_line_code}
    fmea_docs: list[dict],  # 同产品线所有 FMEA 文档 (graph_data + document_no + fmea_id)
    allowed_product_lines: set[str] | None = None,
) -> list[D4Recommendation]:
```

**匹配策略**：

1. **关联 FMEA 匹配**：
   - 有 `fmea_ref_id` 时，从图中定位 FailureMode 节点
   - **节点解析逻辑**（与 D7 一致）：
     - 若 `fmea_node_id` 是 FailureCause → 沿 CAUSE_OF 正向边找到父 FailureMode
     - 若 `fmea_node_id` 是 FailureMode → 直接使用
     - 若 `fmea_node_id` 是 Function → 沿 HAS_FAILURE_MODE 正向边找到子 FailureMode
     - 若 `fmea_node_id` 为空 → 用 D2 关键词对所有 FailureMode 名称做子串匹配
   - 遍历 `CAUSE_OF` 反向边获取所有 FailureCause 节点
   - 用 D2 关键词对 FailureCause 的 name + description 做子串匹配
   - 匹配到的根因按匹配关键词数量排序

2. **跨 FMEA 关键词匹配**：
   - 从 D2 描述提取关键词（`extract_keywords()`）
   - 遍历同产品线其他 FMEA 的 FailureCause 节点
   - 子串匹配 + 匹配计数排序，top 5
   - 关联 FMEA 已匹配的关键词排除（`seen_keys` 去重）

3. **规则引擎补充**：
   - 从 D2 描述匹配动词模式（复用 FAILURE_CHAIN_MAP）
   - 质量标记为 `generic`，confidence 0.3

#### D5 推荐

```python
def get_d5_recommendations(
    capa_data: dict,        # {d4_root_cause, d2_description, fmea_ref_id, fmea_node_id, product_line_code}
    fmea_docs: list[dict],
    allowed_product_lines: set[str] | None = None,
) -> D5RecommendationResponse:
```

**已有措施匹配**：
- 从 D4 根因文本提取关键词
- 图遍历三条路径：
  - FailureCause —(PREVENTED_BY)→ PreventionControl
  - FailureCause —(DETECTED_BY)→ DetectionControl
  - FailureMode —(DETECTED_BY)→ DetectionControl
- 关键词匹配排序

**通用建议生成**：
- 复用 RuleEngine 的 `_suggest_measures` 逻辑
- 输入：从关联 FMEA 获取 AP 级别（若有），否则用 D2 关键词推断失效模式类型
- 输出：按 AP 级别分层的通用预防 + 探测措施

---

## API 端点

### 新增端点（在 `backend/app/api/capa.py` 中）

```
GET /api/capa/{report_id}/d4-fmea-recommendations
GET /api/capa/{report_id}/d5-fmea-recommendations
```

**权限**：
- 路由依赖：`user: User = Depends(require_permission(Module.CAPA, PermissionLevel.VIEW))`
- 程序内校验：`fmea_level = await get_user_permission(user, Module.FMEA, db)`，不足则 403
- 产品线访问控制

**逻辑**：
1. 获取 CAPA 记录
2. 校验产品线访问权限
3. 获取同产品线所有 FMEA 文档
4. 构造 `capa_data` 字典
5. 调用推荐函数
6. 返回响应

### 新增 Schema（在 `backend/app/schemas/capa.py` 中）

```python
class D4Recommendation(BaseModel):
    failure_cause_node_id: str | None = None
    failure_cause_name: str
    failure_cause_desc: str | None = None
    failure_mode_node_id: str | None = None
    failure_mode_name: str | None = None
    fmea_document_no: str | None = None
    fmea_id: str | None = None
    match_source: str            # "linked" | "keyword" | "rule"
    match_reason: str
    related_d2_keywords: list[str] = []
    confidence: float = 0.5

class D4RecommendationResponse(BaseModel):
    items: list[D4Recommendation]

class D5ExistingControl(BaseModel):
    failure_mode_node_id: str
    failure_mode_name: str
    failure_cause_node_id: str | None = None   # DetectionControl 可直接关联 FailureMode
    failure_cause_name: str | None = None
    control_node_id: str
    control_name: str
    control_type: str            # "prevention" | "detection"
    match_source: str
    match_reason: str
    fmea_id: str | None = None                  # 跨 FMEA 推荐时标识来源
    fmea_document_no: str | None = None

class D5GeneralSuggestion(BaseModel):
    content: str
    category: str                # "预防措施" | "探测措施"（注意：规则引擎输出"检测措施"，需映射为"探测措施"）
    basis: str
    confidence: float

class D5RecommendationResponse(BaseModel):
    existing_controls: list[D5ExistingControl]
    general_suggestions: list[D5GeneralSuggestion]
```

---

## 前端实现

### 新建组件

**`frontend/src/components/capa/D4RecPanel.tsx`**

```typescript
interface D4RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;  // 父组件传入回调，采纳时追加到 TextArea
}
```

- 触发条件：CAPA status === `D4_ROOT_CAUSE`
- 调用 `getD4Recommendations(reportId)`
- 显示分组：关联 FMEA → 相似失效模式 → 规则引擎建议
- 每项操作：采纳（调用 `onAdopt`，父组件追加到 TextArea 并触发 `handleUpdate`）、跳过（灰色+删除线）
- 空状态："暂无推荐"

**`frontend/src/components/capa/D5RecPanel.tsx`**

```typescript
interface D5RecPanelProps {
  capaId: string;
  onAdopt: (adoptedText: string) => void;
}
```

- 触发条件：CAPA status === `D5_CORRECTION`
- 调用 `getD5Recommendations(reportId)`
- 两区显示：FMEA 已有控制措施 / 通用建议
- 每项操作：采纳（调用 `onAdopt`）、跳过

### 修改文件

**`frontend/src/pages/capa/CAPADetailPage.tsx`**

- D4 步骤表单上方插入 `<D4RecPanel />`
- D5 步骤表单上方插入 `<D5RecPanel />`
- 与现有 D7RecPanel 模式完全一致

**`frontend/src/api/capa.ts`**

```typescript
export async function getD4Recommendations(reportId: string): Promise<D4RecommendationResponse>
export async function getD5Recommendations(reportId: string): Promise<D5RecommendationResponse>
```

**`frontend/src/types/index.ts`**

新增 `D4Recommendation`、`D5ExistingControl`、`D5GeneralSuggestion`、`D5RecommendationResponse` 接口。

---

## UI 设计

### D4RecPanel

```
┌─────────────────────────────────────────────────┐
│  🔍 D4 根因推荐                                  │
│  基于 D2 问题描述和关联 FMEA 分析                 │
├─────────────────────────────────────────────────┤
│                                                  │
│  [关联 FMEA]                                     │
│  ┌─────────────────────────────────────────┐     │
│  │ 虚焊           FailureCause             │     │
│  │ SMT焊接工序PFMEA · 焊接不良             │     │
│  │ 匹配关键词: 焊接, 虚焊                   │     │
│  │                    [采纳] [跳过]         │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
│  [相似失效模式]                                   │
│  ┌─────────────────────────────────────────┐     │
│  │ 连接器接触不良    FailureCause           │     │
│  │ 电源模块PFMEA · 连接失效                │     │
│  │ 匹配关键词: 连接                         │     │
│  │                    [采纳] [跳过]         │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
│  [规则引擎建议]                                   │
│  ┌─────────────────────────────────────────┐     │
│  │ 元器件老化           通用建议            │     │
│  │ 基于 AP=H 推断                          │     │
│  │                    [采纳] [跳过]         │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
└─────────────────────────────────────────────────┘
```

### D5RecPanel

```
┌─────────────────────────────────────────────────┐
│  🛡️ D5 纠正措施推荐                              │
├─────────────────────────────────────────────────┤
│                                                  │
│  ▼ FMEA 已有控制措施 (2)                         │
│  ┌─────────────────────────────────────────┐     │
│  │ 焊接温度实时监控   PreventionControl     │     │
│  │ 虚焊 → 预防措施                         │     │
│  │ [采纳]                                   │     │
│  ├─────────────────────────────────────────┤     │
│  │ AOI光学检测       DetectionControl      │     │
│  │ 虚焊 → 探测措施                         │     │
│  │ [采纳]                                   │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
│  ▼ 通用建议 (3)                                  │
│  ┌─────────────────────────────────────────┐     │
│  │ 采用防错夹具防止装配错误    预防措施     │     │
│  │ 基于 AP=H                               │     │
│  │ [采纳]                                   │     │
│  ├─────────────────────────────────────────┤     │
│  │ 增加过程巡检频次            探测措施     │     │
│  │ 基于失效模式匹配                        │     │
│  │ [采纳]                                   │     │
│  └─────────────────────────────────────────┘     │
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## 测试策略

### 后端测试（`backend/tests/test_capa_recommendation.py`）

| 测试场景 | 说明 |
|---------|------|
| 关联 FMEA 匹配 | CAPA 有 fmea_ref_id，图中有匹配的 FailureCause → 返回 linked 结果 |
| 跨 FMEA 关键词匹配 | 无 fmea_ref_id，D2 关键词匹配其他 FMEA 的 FailureCause → 返回 keyword 结果 |
| 无匹配时返回空列表 | D2 描述无有效关键词 → 返回空 items |
| D5 已有措施匹配 | D4 根因匹配 FailureCause → 沿 PREVENTED_BY/DETECTED_BY 找到控制措施 |
| D5 通用建议生成 | 无关联 FMEA 时，规则引擎仍返回基于 AP 级别的通用措施 |
| 产品线隔离 | 不同产品线的 FMEA 不互相推荐 |
| 权限校验 | viewer 角色调用 → 403 |

复用 `test_d7_recommendations.py` 的 fixture 模式。

### 前端测试

手动验证（项目已知 gap：无 Vitest 框架）。

---

## 边界情况

| 场景 | 处理方式 |
|------|---------|
| D2 描述为空 | 返回空推荐，不报错 |
| 无关联 FMEA 且无同产品线 FMEA | 仅返回规则引擎通用建议 |
| FMEA 图中无 FailureCause 节点 | 跳过图匹配，降级到规则引擎 |
| D4 已有内容时采纳 | 追加到已有内容末尾（换行分隔） |
| 重复采纳同一推荐 | 允许，用户可能需要多次参考 |
| DetectionControl 直接关联 FailureMode（无 FailureCause） | `failure_cause_*` 字段返回 null，前端显示"—" |
| D2 描述为长句无标点 | `extract_keywords` 可能返回单个长 token，匹配率低；UX 提示用户用标点/空格分隔关键词 |

---

## 后续演进（记入 Roadmap）

**全混合管道（Phase 3+）**：

在 FMEA 图匹配基础上扩展：
1. 中文分词升级：将 `extract_keywords` 从纯标点分割升级为混合分词器（jieba 或 RAG 向量检索），提升长句匹配率
2. 历史 CAPA 匹配：从历史 CAPA 报告中找相似 D4 根因（关键词 + 语义相似度）
3. LLM 增强：当规则引擎质量为 `generic` 时，调用 LLM 生成更具体的建议
4. PostgreSQL 缓存：复用 `recommendation_cache` 表模式
5. 与 RAG 语义搜索集成：当 RAG 上线后，用向量检索替代关键词子串匹配

触发类型扩展：
- `d4_root_cause`：D4 根因推荐
- `d5_correction`：D5 纠正措施推荐

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `backend/app/services/capa_recommendation_service.py` | D4/D5 推荐核心逻辑 |
| 新建 | `backend/tests/test_capa_recommendation.py` | 后端测试 |
| 修改 | `backend/app/api/capa.py` | 新增两个 API 端点 |
| 修改 | `backend/app/schemas/capa.py` | 新增 D4/D5 Schema |
| 新建 | `frontend/src/components/capa/D4RecPanel.tsx` | D4 推荐面板组件 |
| 新建 | `frontend/src/components/capa/D5RecPanel.tsx` | D5 推荐面板组件 |
| 修改 | `frontend/src/pages/capa/CAPADetailPage.tsx` | 插入 D4/D5 推荐面板 |
| 修改 | `frontend/src/api/capa.ts` | 新增 API 调用函数 |
| 修改 | `frontend/src/types/index.ts` | 新增类型定义 |
