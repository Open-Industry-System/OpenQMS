# 8D 报告 AI 草拟模块设计文档

**日期**: 2026-06-04  
**状态**: 待实现  
**方案**: 结构化草稿服务（方案2）  
**预估工期**: 3-4 天

---

## 1. 需求摘要

在 CAPA 8D 报告编辑页中，为 D2-D8 每个步骤提供 AI 辅助草拟功能。用户点击对应步骤旁的"AI草拟"按钮，AI 基于前置步骤内容 + 关联 FMEA 数据生成草稿，直接填充到表单文本框。

### 关键决策

| 维度 | 决策 |
|------|------|
| 草拟范围 | D2-D8 每个步骤独立触发 |
| 呈现方式 | 直接填充到表单文本框 |
| 输出格式 | 结构化文本（默认）/ 段落文本（可选） |
| 格式偏好存储 | 前端 localStorage |
| LLM 调用 | 复用现有 `LLMProvider` |

---

## 2. 架构

```
前端 (CAPADetailPage.tsx)
    │
    ├─ D2 文本框 ── [AI草拟 ▼] 按钮
    ├─ D3 文本框 ── [AI草拟 ▼] 按钮
    ├─ D4 文本框 ── [AI草拟 ▼] 按钮
    │      ...
    └─ POST /api/capa/{id}/draft/{step}
            │
            ▼
后端 (capa_draft_service.py)
    │
    ├─ 1. 读取 CAPA 当前数据 + 关联 FMEA
    ├─ 2. 根据 step + user_preference 组装 prompt + JSON schema
    ├─ 3. 调用 LLMProvider.complete()
    └─ 4. 将结构化 JSON 渲染为文本 → 返回前端
```

### 新增文件

| 文件 | 作用 |
|------|------|
| `backend/app/services/capa_draft_service.py` | 核心草稿服务：prompt 组装 + LLM 调用 + 渲染 |
| `backend/app/api/capa_draft.py` | API 路由 |
| `backend/app/schemas/capa_draft.py` | Pydantic schema |
| `frontend/src/api/capaDraft.ts` | 前端 API 调用 |
| `frontend/src/components/capa/AIDraftButton.tsx` | 按钮组件 |
| `frontend/src/components/capa/useAIDraft.ts` | Hook |

### 复用文件

- `LLMProvider`（`llm_provider.py`）
- `capa_service.py`
- `fmea_service.py`

---

## 3. API 设计

### 端点

```
POST /api/capa/{id}/draft/{step}
```

- `step` ∈ `{d2, d3, d4, d5, d6, d7, d8}`

### 请求体

```json
{
  "format": "structured" | "paragraph"
}
```

- `format` 默认 `"structured"`

### 响应

```json
{
  "content": "string",
  "structured_data": {}
}
```

- `content`：渲染后的文本，直接填充到表单
- `structured_data`：结构化 JSON 原始数据（可选，供未来扩展）

### 错误码

| 状态码 | 场景 | 前端处理 |
|--------|------|---------|
| 404 | CAPA 不存在 | 标准 404 |
| 403 | 无编辑权限 | 按钮不渲染 |
| 503 | LLM 未配置 | 按钮 disabled，tooltip 提示 |
| 504 | LLM 超时 | message.error("AI 响应超时") |
| 422 | 格式解析失败 | message.error("AI 输出格式异常") |
| 500 | 其他异常 | message.error("AI 服务异常") |

---

## 4. LLM Prompt 设计

### Prompt 模板结构

每个步骤共享相同 prompt 框架：

```
你是一位资深质量工程师，正在协助草拟 8D 报告。

【报告信息】
- 报告编号: {document_no}
- 标题: {title}
- 产品线: {product_line_code}

【前置步骤内容】
{preceding_steps}

【关联 FMEA 信息】
{fmea_context}

【当前任务】
请为步骤 {step_name} 草拟内容。

要求:
1. 基于前置步骤的内容进行逻辑推导，不要编造数据
2. 使用专业质量术语
3. 输出格式: {format_instruction}
4. 如果是中文内容请保持中文输出

请严格按照以下 JSON schema 输出:
{json_schema}
```

### 各步骤 JSON Schema

#### D2 问题描述

```json
{
  "problem_statement": "问题陈述（一句话概括）",
  "affected_product": "受影响的产品/工序",
  "defect_description": "缺陷/问题具体描述",
  "occurrence_context": "发生场景（何时、何地、何种条件）",
  "impact_scope": "影响范围（数量、批次、客户）"
}
```

渲染格式：
```
问题陈述：{problem_statement}
影响产品：{affected_product}
缺陷描述：{defect_description}
发生场景：{occurrence_context}
影响范围：{impact_scope}
```

#### D3 临时措施

```json
{
  "containment_actions": [
    {"action": "措施描述", "responsible": "负责人", "deadline": "完成期限"}
  ],
  "verification_method": "验证方法"
}
```

#### D4 根因分析

```json
{
  "root_causes": [
    {
      "category": "人 | 机 | 料 | 法 | 环 | 测",
      "description": "根因描述",
      "evidence": "支持证据"
    }
  ]
}
```

渲染格式（编号列表）：
```
1. 【{category}】{description}
   证据：{evidence}
2. 【{category}】...
```

#### D5 永久措施

```json
{
  "corrective_actions": [
    {
      "action": "措施描述",
      "target_root_cause": "针对的根因",
      "responsible": "负责人",
      "deadline": "完成期限"
    }
  ]
}
```

#### D6 实施验证

```json
{
  "verification_method": "验证方法",
  "verification_result": "验证结果",
  "effectiveness_proof": "有效性证据"
}
```

#### D7 预防复发

```json
{
  "preventive_actions": [
    {"action": "预防措施", "implementation_plan": "实施计划"}
  ],
  "standardization_plan": "标准化计划（更新文件/作业指导书）",
  "training_plan": "培训计划"
}
```

#### D8 关闭

```json
{
  "summary": "处理过程总结",
  "lessons_learned": "经验教训",
  "closure_approval": "关闭确认意见"
}
```

### 段落模式

当 `format="paragraph"` 时，prompt 追加：

```
请用连贯的段落书写上述内容，不要使用 bullet points、编号或分点符号。
直接输出一段完整的文本。
```

段落模式不返回 `structured_data`。

---

## 5. 前端交互设计

### 按钮位置

每个 D 步骤的文本区域 **右上角** 放置按钮：

```
┌─────────────────────────────────────┐
│ D2 问题描述                [AI草拟 ▼] │
├─────────────────────────────────────┤
│                                     │
│  [多行文本输入区域]                  │
│                                     │
│                              [保存] │
└─────────────────────────────────────┘
```

### 格式切换下拉菜单

```
┌─────────────┐
│  结构化格式  │  ← 默认选中
│  段落格式   │
├─────────────┤
│  切换偏好... │  ← 打开设置抽屉
└─────────────┘
```

### 按钮状态

| 状态 | 表现 |
|------|------|
| 初始 | 幽灵按钮样式（`type="text"` + AI 图标） |
| Loading | `Spin` 图标 + "草拟中..." + disabled |
| 完成 | 文本框闪烁高亮（300ms 边框变色） |
| 错误 | 红色，hover 显示错误 tooltip |

### 用户偏好存储

```typescript
// localStorage key: "openqms_ai_draft_preference"
interface AIDraftPreference {
  format: "structured" | "paragraph";
}
```

---

## 6. 错误处理

### LLM 超时与降级

- 超时时间：**10 秒**
- 重试策略：前端 **1 次自动重试**
- 降级：LLM 不可用时按钮 disabled

### 错误码映射

| 状态码 | 后端原因 | 前端表现 |
|--------|---------|---------|
| 503 | LLM 未配置 | 按钮 disabled + tooltip "AI 功能未启用" |
| 504 | LLM 超时 | message.error("AI 响应超时，请重试") |
| 422 | JSON 解析失败 | message.error("AI 输出格式异常，请重试") |
| 500 | 其他异常 | message.error("AI 服务异常，请稍后重试") |

---

## 7. 审计日志

每次 AI 草拟调用记录 AuditLog：

```python
AuditLog(
    action="AI_DRAFT_GENERATED",
    entity_type="capa_eightd",
    entity_id=report_id,
    details={
        "step": "d4",
        "format": "structured",
        "has_fmea_context": True,
    }
)
```

---

## 8. 安全与权限

- 权限检查复用现有 `canEdit` 逻辑
- LLM prompt 中不注入敏感信息（用户密码、内部系统等）
- 仅注入 CAPA 已有字段和关联 FMEA 的公开节点名称

---

## 9. 未来扩展

1. **一键生成正式报告**：复用 `structured_data` 生成 PDF/Word
2. **多语言支持**：prompt 中增加语言参数
3. **历史学习**：记录用户修改后的最终版本，用于微调 prompt
