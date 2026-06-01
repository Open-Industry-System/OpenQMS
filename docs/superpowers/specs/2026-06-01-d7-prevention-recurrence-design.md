# D7 预防复发提示模块设计

**日期**: 2026-06-01  
**状态**: 已批准  
**范围**: 8D/CAPA D7 步骤的 FMEA 关联推荐与防复发门禁

---

## 1. 目标

当 CAPA 进入 D7（预防复发）步骤时，自动提示需要关注或更新的 FMEA 失效模式节点，支持一键跳转和自动填充预防措施，并在推进 D8 时执行软门禁确认。

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

### 3.1 新增 API 端点

```
GET /api/capa/{report_id}/d7-fmea-recommendations
```

**响应结构：**

```json
{
  "recommendations": [
    {
      "fmea_id": "uuid",
      "fmea_document_no": "PFMEA-2026-001",
      "node_id": "uuid",
      "node_name": "焊接虚焊",
      "node_type": "FailureMode",
      "match_source": "linked",
      "match_reason": "关联FMEA失效模式",
      "related_d4_keywords": ["虚焊", "焊接不良"],
      "suggested_prevention": "D5永久措施文本"
    }
  ]
}
```

### 3.2 匹配算法

#### 3.2.1 图结构匹配（match_source = "linked"）

1. 取 CAPA 的 `fmea_ref_id`，读取该 FMEA 的 `graph_data`
2. 若有 `fmea_node_id`，从该节点出发：
   - 沿 `CAUSE_OF` 边追溯原因节点
   - 沿 `EFFECT_OF` 边追溯影响节点
   - 沿 `HAS_FAILURE_MODE` 边找到同功能下的其他失效模式
3. 若无 `fmea_node_id`，遍历所有 FailureMode 节点，按名称与 D4 根因关键词匹配
4. 返回相关 FailureMode 节点列表

#### 3.2.2 关键词搜索（match_source = "keyword"）

1. 从 D4 根因文本中提取关键词：
   - 中文：按标点/空格分词，取 ≥2 字的词
   - 英文：按空格分词
2. 查询同产品线（`product_line_code`）下其他 FMEA 文档（排除已关联的）
3. 在 `graph_data` 的节点 `name` 和 `description` 字段中搜索关键词匹配
4. 按匹配关键词数量排序，取 Top 5

#### 3.2.3 合并去重

- 按 `fmea_id + node_id` 去重
- linked 结果优先，keyword 补充
- 最终列表按 match_source 排序（linked 在前）

### 3.3 自动填充建议

- 取 CAPA 的 `d5_correction` 文本作为 `suggested_prevention` 值
- 前端可选择将此值填充到 FMEA 节点的预防措施字段

### 3.4 关键词提取工具函数

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
- 每个推荐项的操作按钮：跳转 FMEA、标记已更新、标记无需更新
- 自动填充 D5 措施按钮
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

- `confirmedNodes` 为本地 useState，不持久化到后端
- 组件挂载时调用 API 获取推荐列表
- 确认状态变化时通知父组件（用于 D8 推进门禁判断）

### 4.3 D8 推进软门禁

修改 `CAPADetailPage` 的 `handleAdvance` 函数：

```typescript
const handleAdvance = async () => {
  // D7 步骤且有未确认推荐项
  if (capa.status === "D7_PREVENTION" && hasUnconfirmed) {
    // 弹出确认对话框
    const confirmed = await showSkipConfirmDialog(unconfirmedItems);
    if (!confirmed) return; // 用户取消
  }
  // 正常推进
  const updated = await advanceCAPA(id);
  // ...
};
```

确认对话框内容：
- 列出所有未确认的推荐项
- 提供跳过理由输入框（可选填写）
- 确认后继续推进，取消则中止

### 4.4 CAPADetailPage 集成

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
| `backend/app/schemas/capa.py` | 修改 | 新增 `D7Recommendation` / `D7RecommendationResponse` schema |
| `backend/app/services/capa_service.py` | 修改 | 新增 `get_d7_recommendations()` 函数 |
| `backend/app/api/capa.py` | 修改 | 新增 `GET /{id}/d7-fmea-recommendations` 路由 |
| `frontend/src/api/capa.ts` | 修改 | 新增 `getD7Recommendations()` API 函数 |
| `frontend/src/components/capa/D7RecPanel.tsx` | **新增** | 推荐面板组件 + 确认状态管理 |
| `frontend/src/pages/capa/CAPADetailPage.tsx` | 修改 | D7 步骤嵌入 D7RecPanel + 软门禁逻辑 |

## 6. 不涉及的文件

- FMEA 编辑器（只读跳转，不修改其逻辑）
- 状态机（无新状态，D7→D8 转换不变）
- 数据库模型（无新表/列，复用现有 `graph_data`）
- 路由配置（无新页面路由）

## 7. 验收标准

1. 进入 D7 步骤时，自动显示推荐面板（已关联 FMEA 节点 + 同产品线相似失效模式）
2. 点击"跳转 FMEA"可导航到对应 FMEA 编辑器并定位到目标节点
3. 点击"自动填充 D5 措施"可将 D5 文本建议填充到 FMEA 节点
4. 点击"已更新"/"无需更新"可标记确认状态
5. 推进 D8 时，若有未确认项弹出确认对话框，可填理由跳过
6. 所有推荐项可正常显示，无匹配时显示空状态提示
