# D7 预防复发提示模块设计

**日期**: 2026-06-01  
**状态**: 已批准（v2 — 审查修复版）  
**范围**: 8D/CAPA D7 步骤的 FMEA 关联推荐与防复发门禁

---

## 1. 目标

当 CAPA 进入 D7（预防复发）步骤时，自动提示需要关注或更新的 FMEA 失效模式节点，支持一键跳转和自动填充预防措施，并在推进 D8 时执行软门禁确认（跳过理由写入审计日志）。

## 2. 架构

```
┌─────────────────────────────────────────────────────┐
│  CAPADetailPage (D7 步骤)                           │
│  ┌───────────────────────┐  ┌──────────────────────┐│
│  │ D7 TextArea (现有)     │  │ D7RecPanel (新增)    ││
│  │ 预防复发措施文本        │  │ FMEA 推荐列表        ││
│  └───────────────────────┘  │ • 已关联FMEA节点      ││
│                              │ • 同产品线相似失效模式  ││
│                              │ • [跳转] [标记已更新]  ││
│                              │ • [自动填充D5措施]     ││
│                              └──────────────────────┘│
│  ┌──────────────────────────────────────────────────┐│
│  │ D8 推进按钮 → 软门禁检查                          ││
│  │ 未确认项 → 弹出确认对话框（可填理由跳过）           ││
│  │ 跳过理由 → 写入 AuditLog                          ││
│  └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘

         ↓ API 调用

┌─────────────────────────────────────────────────────┐
│  Backend: capa_service.get_d7_recommendations()      │
│  ┌──────────────┐  ┌──────────────┐                  │
│  │ 图结构匹配    │  │ 关键词搜索    │                  │
│  │ 已关联FMEA    │  │ 同产品线其他  │                  │
│  │ → 相关节点    │  │ FMEA匹配     │                  │
│  └──────┬───────┘  └──────┬───────┘                  │
│         └───────┬──────────┘                         │
│          合并去重 + 排序                               │
│              ↓                                       │
│     返回 Recommendation[]                            │
└─────────────────────────────────────────────────────┘
```

## 3. 后端设计

### 3.1 补充 fmea_node_id 支持

现有 `CAPAResponse` 和 `CAPAUpdate` schema 未暴露 `fmea_node_id`，导致 linked 匹配无法定位到具体节点。需补充：

**schemas/capa.py 修改：**
- `CAPAResponse` 增加 `fmea_node_id: str | None`
- `CAPAUpdate` 增加 `fmea_node_id: str | None`

**services/capa_service.py 修改：**
- `link_fmea()` 增加可选参数 `fmea_node_id: str | None`，同时写入 `fmea_ref_id` 和 `fmea_node_id`

**api/capa.py 修改：**
- `POST /{report_id}/link-fmea` 端点增加可选 query 参数 `fmea_node_id`

### 3.2 新增推荐 API 端点

```
GET /api/capa/{report_id}/d7-fmea-recommendations
```

**权限要求：**
- 同时要求 CAPA VIEW 和 FMEA VIEW 权限（推荐内容包含 FMEA 图节点详情，属于 FMEA 数据）
- 候选 FMEA 按用户可访问产品线过滤（`get_user_product_line_codes`）
- 端点内部对每个候选 FMEA 执行 `enforce_product_line_access`

**响应结构：**

```json
{
  "recommendations": [
    {
      "fmea_id": "uuid",
      "fmea_document_no": "PFMEA-2026-001",
      "failure_mode_node_id": "uuid",
      "failure_mode_name": "焊接虚焊",
      "failure_cause_node_id": "uuid",
      "failure_cause_name": "焊接参数偏移",
      "prevention_control_node_id": "uuid | null",
      "prevention_control_name": "焊接参数监控 | null",
      "match_source": "linked",
      "match_reason": "关联FMEA失效模式",
      "related_d4_keywords": ["虚焊", "焊接不良"],
      "suggested_prevention": "D5永久措施文本"
    }
  ]
}
```

字段说明：
- `failure_mode_node_id` / `failure_mode_name`：推荐关注的失效模式
- `failure_cause_node_id` / `failure_cause_name`：该失效模式下的原因节点（自动填充的目标层级）。**linked 匹配必填；keyword 匹配可能为 null**（当匹配到的 FailureMode 无 FailureCause 时）
- `prevention_control_node_id` / `prevention_control_name`：已有的预防控制节点（若存在则为"更新"，若为 null 则为"新增"）。当 `failure_cause_node_id` 为 null 时此项也为 null
- `suggested_prevention`：CAPA 的 `d5_correction` 文本，用于自动填充建议

**无 FailureCause 的处理：**
- linked 匹配：算法已过滤，不返回无 FailureCause 的 FailureMode
- keyword 匹配：可能匹配到无 FailureCause 的 FailureMode，此时 `failure_cause_node_id` 和 `prevention_control_node_id` 均为 null，前端禁用自动填充按钮，仅允许跳转/人工处理

### 3.3 匹配算法

#### 3.3.1 图结构匹配（match_source = "linked"）

1. 取 CAPA 的 `fmea_ref_id`，读取该 FMEA 的 `graph_data`
2. 若有 `fmea_node_id`，从该节点出发：
   - 若节点是 FailureCause：找到其父 FailureMode（沿 `CAUSE_OF` 反向），再沿 `PREVENTED_BY` 找 PreventionControl
   - 若节点是 FailureMode：沿 `CAUSE_OF` 反向找到所有 FailureCause 节点；对每个 FailureCause 沿 `PREVENTED_BY` 找 PreventionControl；**每个 FailureCause 生成一条推荐**
   - 若节点是其他类型（Function 等）：沿 `HAS_FAILURE_MODE` 找 FailureMode，再按 FailureMode 流程处理
3. 若无 `fmea_node_id`，遍历所有 FailureMode 节点，按名称与 D4 根因关键词匹配，再按上述 FailureMode 流程展开
4. **过滤**：排除没有 FailureCause 的 FailureMode（无挂载目标，无法生成预防控制）
5. 返回结果包含 FailureMode → FailureCause → PreventionControl 三层信息

#### 3.3.2 关键词搜索（match_source = "keyword"）

1. 从 D4 根因文本中提取关键词：
   - 按中文标点、英文标点、空格、换行拆分
   - 过滤掉纯数字和长度 < 2 的词
   - 去重保序
2. 查询同产品线（`product_line_code`）下其他 FMEA 文档（排除已关联的）
3. **产品线过滤**：仅返回用户有访问权限的产品线下的 FMEA（`get_user_product_line_codes`）
4. 在 `graph_data` 的节点 `name` 和 `description` 字段中搜索关键词匹配
5. 按匹配关键词数量排序，取 Top 5
6. 对每个匹配的 FailureMode，沿图边找到 FailureCause 和 PreventionControl

#### 3.3.3 合并去重

- 按 `fmea_id + failure_mode_node_id` 去重
- linked 结果优先，keyword 补充
- 最终列表按 match_source 排序（linked 在前）

### 3.4 自动填充 API

前端点击"自动填充 D5 措施"时，调用现有 FMEA 更新接口：

```
PUT /api/fmea/{fmea_id}
```

请求体包含完整的 `graph_data`（与现有 FMEA 编辑器保存逻辑一致）。

填充逻辑（前端执行）：
- 若 `prevention_control_node_id` 存在：更新该节点的 `name` 字段（FMEA 表格"预防控制"列显示和编辑的是 `name`，GraphNode 无 `description` 字段）
- 若 `prevention_control_node_id` 为 null：在 FailureCause 节点下新增 PreventionControl 节点（`name` 设为 D5 文本），通过 `PREVENTED_BY` 边连接

### 3.5 跳过理由写入审计日志

扩展现有 `POST /api/capa/{report_id}/advance` 端点，接受可选请求体：

```json
// 现有调用（无变更）：
POST /api/capa/{report_id}/advance

// D7 推进时携带跳过理由：
POST /api/capa/{report_id}/advance
{
  "d7_skip_reasons": [
    {"fmea_id": "uuid", "node_id": "uuid", "reason": "已手动更新过"}
  ]
}
```

**实现方式：**
- `advance_capa` 路由增加可选 `AdvanceRequest` body（`d7_skip_reasons: list | None`）
- 当 `d7_skip_reasons` 非空且当前状态为 `D7_PREVENTION` 时，写入 AuditLog：

```python
if d7_skip_reasons and capa.status == "D7_PREVENTION":
    audit_log = AuditLog(
        table_name="capa_eightd",
        record_id=capa.report_id,
        action="D7_SKIP_CONFIRMATION",
        changed_fields={"skipped_nodes": d7_skip_reasons},
        operated_by=user_id,
    )
    db.add(audit_log)
```

### 3.6 关键词提取工具函数

新增 `backend/app/utils/text.py`：

```python
import re

def extract_keywords(text: str, min_length: int = 2) -> list[str]:
    """从文本中提取关键词。

    策略（纯标准库，不引入 jieba 依赖）：
    - 按中文标点、英文标点、空格、换行拆分
    - 过滤掉纯数字和长度 < min_length 的词
    - 去重保序
    """
```

## 4. 前端设计

### 4.1 新增组件

**`frontend/src/components/capa/D7RecPanel.tsx`**

D7 推荐面板组件，包含：

- 推荐列表（按 match_source 分组：已关联 FMEA / 同产品线相似）
- 每个推荐项展示：FailureMode 名称、FailureCause 名称（若有）、已有 PreventionControl 状态
- 每个推荐项的操作按钮：跳转 FMEA、标记已更新、标记无需更新
- 自动填充 D5 措施按钮（区分"更新已有"和"新增"场景；当 `failure_cause_node_id` 为 null 时禁用，显示 tooltip 提示"无原因节点，请手动处理"）
- 确认进度统计（已确认 X / 共 Y）

**Props：**

```typescript
interface D7RecPanelProps {
  capaId: string;
  d5Correction: string | null;  // 用于自动填充建议
  onConfirmationChange: (allConfirmed: boolean) => void;
}
```

### 4.2 状态管理

```typescript
const [recommendations, setRecommendations] = useState<D7Recommendation[]>([]);
const [confirmedNodes, setConfirmedNodes] = useState<Map<string, "updated" | "skipped">>(new Map());
const [loading, setLoading] = useState(false);
```

- `confirmedNodes` 为本地 useState，不持久化到后端（仅 UX 提示，不具备服务端约束）
- 组件挂载时调用 API 获取推荐列表
- 确认状态变化时通知父组件（用于 D8 推进门禁判断）

### 4.3 D8 推进软门禁

修改 `CAPADetailPage` 的 `handleAdvance` 函数：

```typescript
const handleAdvance = async () => {
  // D7 步骤且有未确认推荐项
  if (capa.status === "D7_PREVENTION" && hasUnconfirmed) {
    // 弹出确认对话框
    const result = await showSkipConfirmDialog(unconfirmedItems);
    if (!result.confirmed) return; // 用户取消
    // 跳过理由随 advance 请求一起提交
    const updated = await advanceCAPA(id, { d7_skip_reasons: result.skipReasons });
    setCapa(updated);
  } else {
    const updated = await advanceCAPA(id);
    setCapa(updated);
  }
};
```

确认对话框内容：
- 列出所有未确认的推荐项
- 每项提供跳过理由输入框
- 确认后继续推进（跳过理由随 advance 请求提交），取消则中止

**注意**：软门禁仅存在于前端 UX 层面，不具备服务端强制约束。直接调用 API 推进可绕过。跳过理由写入审计日志以留痕。

### 4.4 FMEA 编辑器跳转支持

现有 FMEA 编辑器支持两种 URL 参数定位：
- `?node={nodeId}` — 高亮表格中的失效模式行
- `?tab=graph&highlightNode={nodeId}` — 图谱 tab 高亮指定节点

D7 面板的"跳转 FMEA"使用 `?node={failure_mode_node_id}` 定位到失效模式行，与现有行为一致。

### 4.5 CAPADetailPage 集成

在 D7 步骤的 Card 中，TextArea 下方嵌入 D7RecPanel：

```tsx
{capa.status === "D7_PREVENTION" && (
  <>
    <Form layout="vertical">
      <Form.Item label="预防复发措施">
        <TextArea ... />
      </Form.Item>
    </Form>
    <Divider />
    <D7RecPanel
      capaId={id}
      d5Correction={localData.d5_correction}
      onConfirmationChange={setAllD7Confirmed}
    />
  </>
)}
```

## 5. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/utils/text.py` | **新增** | `extract_keywords()` 关键词提取函数 |
| `backend/app/schemas/capa.py` | 修改 | 新增 `D7Recommendation` / `D7RecommendationResponse` / `AdvanceRequest`；`CAPAResponse` 增加 `fmea_node_id`；`CAPAUpdate` 增加 `fmea_node_id` |
| `backend/app/services/capa_service.py` | 修改 | 新增 `get_d7_recommendations()`；`link_fmea()` 增加 `fmea_node_id` 参数；`advance_capa()` 增加 `d7_skip_reasons` 参数 |
| `backend/app/api/capa.py` | 修改 | 新增 `GET /{id}/d7-fmea-recommendations` 路由；`POST /{id}/link-fmea` 增加 `fmea_node_id` 参数；`POST /{id}/advance` 增加可选 `AdvanceRequest` body |
| `frontend/src/api/capa.ts` | 修改 | 新增 `getD7Recommendations()`；`advanceCAPA()` 增加可选 skip reasons 参数 |
| `frontend/src/components/capa/D7RecPanel.tsx` | **新增** | 推荐面板组件 + 确认状态管理 |
| `frontend/src/pages/capa/CAPADetailPage.tsx` | 修改 | D7 步骤嵌入 D7RecPanel + 软门禁逻辑 |
| `frontend/src/pages/planning/fmea/FMEAEditorPage.tsx` | 修改 | 确保 `?node=` 参数支持 FailureCause 节点定位（现有仅高亮 FailureMode 行） |

## 6. 不涉及的文件

- 状态机（无新状态，D7→D8 转换不变）
- 数据库模型（无新表/列，复用现有 `graph_data`）
- 路由配置（无新页面路由）

## 7. 验收标准

1. 进入 D7 步骤时，自动显示推荐面板（已关联 FMEA 节点 + 同产品线相似失效模式）
2. 推荐项展示三层信息：FailureMode → FailureCause → PreventionControl（若有）
3. 点击"跳转 FMEA"可导航到对应 FMEA 编辑器并定位到目标失效模式行
4. 点击"自动填充 D5 措施"：
   - 若已有 PreventionControl → 更新其 `name` 字段
   - 若无 PreventionControl → 新增节点（`name` = D5 文本）并连接到 FailureCause
5. 点击"已更新"/"无需更新"可标记确认状态
6. 推进 D8 时，若有未确认项弹出确认对话框，可填理由跳过
7. 跳过理由写入 AuditLog（action = "D7_SKIP_CONFIRMATION"）
8. 推荐 API 同时要求 CAPA VIEW + FMEA VIEW 权限，并执行产品线行级过滤
9. 所有推荐项可正常显示，无匹配时显示空状态提示
