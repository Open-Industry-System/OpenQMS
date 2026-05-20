# DFMEA 编辑器 + 生成规则引擎 设计文档

**日期**: 2026-05-20
**版本**: v1.0
**状态**: 已确认，待实现

---

## 1. 目标

完成 OpenQMS Phase 1 M3-M4 核心扩展中的两个 P0 模块：

1. **DFMEA 编辑器** — 系统→子系统→零部件展开 + 设计参数矩阵
2. **DFMEA 生成规则引擎** — 基于 AIAG-VDA 七步法的引导式规则

---

## 2. 架构方案

**方案 C：前端模块化 + 后端最小改动**

- 前端拆分独立组件，保持后端 API 不变
- 结构树/参数图通过更新 `graph_data` JSONB 实现
- 规则引擎为纯前端静态逻辑
- 预留后端历史数据推荐接口（Phase 3 实现）

---

## 3. 后端变更

### 3.1 GraphNode 类型扩展

在 `backend/app/schemas/fmea.py` 中扩展 `NodeType` 枚举，新增 DFMEA 专用语义类型：

```python
# 新增（语义区分，字段与现有 Function 节点相同）
SystemFunction = "SystemFunction"
SubsystemFunction = "SubsystemFunction"
ComponentFunction = "ComponentFunction"
```

**注意**：字段保持与现有 `ProcessStepFunction` / `ProcessWorkElementFunction` 一致，仅类型名称语义化。

### 3.2 预留 API 接口

在 `backend/app/api/fmea.py` 中添加占位路由：

```python
@router.post("/{fmea_id}/recommend")
async def recommend_fmea(...):
    """预留：Phase 3 接入历史数据推荐"""
    raise HTTPException(status_code=501, detail="历史数据推荐功能将在 Phase 3 实现")
```

### 3.3 无其他变更

- 复用现有 `PUT /api/fmea/{id}` 更新 graph_data
- 复用现有 `FMEADocument` 模型和状态机

---

## 4. 前端组件架构

### 4.1 组件拆分

```
FMEAEditorPage.tsx (主容器，管理全局状态)
├── EditorTabs (页签切换)
│   ├── FailureAnalysisTab (现有功能提取)
│   │   ├── StructureFunctionPanel (左侧节点列表)
│   │   ├── FailureAnalysisTable (右侧 19 列表格)
│   │   └── InlineRecommendations (底部推荐卡片)
│   └── StructureAnalysisTab (新增)
│       ├── StructureTree (嵌套树形结构)
│       └── NodeDetailPanel (节点属性 + 参数图)
└── DFMEAGenerationWizard (模态框，7 步向导)
    ├── Step1Scope.tsx (5T 范围定义)
    ├── Step2Structure.tsx (结构树构建)
    ├── Step3Function.tsx (功能树 + 参数图)
    ├── Step4Failure.tsx (失效链 FE-FM-FC)
    ├── Step5Risk.tsx (风险分析 S/O/D + AP)
    ├── Step6Optimization.tsx (优化措施)
    └── Step7Documentation.tsx (结果预览)
```

### 4.2 新增文件清单

| 文件 | 说明 |
|------|------|
| `frontend/src/components/dfmea/StructureTree.tsx` | 嵌套树形结构（Ant Design Tree） |
| `frontend/src/components/dfmea/ParameterDiagram.tsx` | 参数图编辑面板（输入-输出-噪声-控制） |
| `frontend/src/components/dfmea/GenerationWizard.tsx` | 7 步向导容器 |
| `frontend/src/components/dfmea/InlineRecommendations.tsx` | 底部推荐卡片 |
| `frontend/src/utils/dfmeaRules.ts` | AIAG-VDA 规则引擎 |
| `frontend/src/utils/dfmeaWizard.ts` | 向导步骤验证 |

---

## 5. 规则引擎设计

### 5.1 规则类型

| 规则 | 输入 | 输出 | 触发条件 |
|------|------|------|---------|
| **功能否定** | 功能描述文本 | 失效模式列表 | 用户输入/修改功能描述 |
| **失效链关联** | 失效模式 | 失效影响 + 失效原因 | 用户确认失效模式 |
| **AP 查表** | S, O, D | H/M/L + 优化方向 | 用户输入 S/O/D 后 |
| **措施建议** | 失效模式 + AP | 预防/探测措施 | AP = H 时强制提示 |

### 5.2 规则数据

纯前端静态配置：

- **中文动词否定词典**：采集→无法采集/采集延迟/采集精度不足
- **AP 查表矩阵**：S×O×D → H/M/L（复用现有 `frontend/src/utils/fmea.ts`）
- **常见失效模式库**：按行业分类的模板库（汽车电子、BMS 等）

### 5.3 7 步向导流程

| 步骤 | 内容 | 规则引擎作用 |
|------|------|-------------|
| 1. 范围定义 (5T) | 团队/时间/工具/任务/趋势 | 纯表单，无规则 |
| 2. 结构分析 | System→Subsystem→Component | 层级提示下级分解建议 |
| 3. 功能分析 | 功能描述 + 参数图 | 结构名称自动提示功能模板 |
| 4. 失效分析 | FE-FM-FC 失效链 | **功能否定自动生成失效模式** |
| 5. 风险分析 | S/O/D + AP | **AP 自动查表**，三级 severity 引导 |
| 6. 优化 | 预防/探测措施 | **AP=H 强制提示优化** |
| 7. 结果文件化 | 预览骨架 | 汇总验证 |

---

## 6. 权限集成

基于 `docs/permissions.md`，复用现有 `isViewer` / `isAdminOrManager` 模式：

| 功能 | viewer | engineer | manager/admin |
|------|:------:|:--------:|:-------------:|
| 查看编辑器 | ✅ | ✅ | ✅ |
| 编辑失效分析 | ❌ | ✅ | ✅ |
| 编辑结构树 | ❌ | ✅ | ✅ |
| 编辑参数图 | ❌ | ✅ | ✅ |
| 触发规则推荐 | ❌ | ✅ | ✅ |
| 使用生成向导 | ❌ | ✅ | ✅ |
| 审批 FMEA | ❌ | ❌ | ✅ |

---

## 7. 交互流程

### 7.1 创建新 DFMEA

```
用户点击"新建 DFMEA" → 弹出 7 步向导
  Step 1: 填写 5T → 下一步
  Step 2: 构建结构树 → 下一步
  Step 3: 填写功能 + 参数图 → 下一步
  Step 4: 确认/修改推荐的失效模式 → 下一步
  Step 5: 输入 S/O/D，AP 自动计算 → 下一步
  Step 6: 填写优化措施（AP=H 强制） → 下一步
  Step 7: 预览 → 确认创建 → 进入编辑器
```

### 7.2 编辑现有 DFMEA

```
进入编辑器 → 默认"失效分析"页签
  ├─ 点击"结构分析" → 编辑结构树 + 节点参数图
  ├─ 失效分析中输入功能 → 底部弹出推荐卡片
  └─ 保存 → PUT /api/fmea/{id}
```

---

## 8. 数据结构

### 8.1 结构树在 graph_data 中的表示

```json
{
  "nodes": [
    { "id": "sys-1", "type": "System", "name": "BMS", "description": "电池管理系统" },
    { "id": "sub-1", "type": "Subsystem", "name": "BMU", "description": "电池管理单元" },
    { "id": "comp-1", "type": "Component", "name": "LTC6811", "description": "电压采集芯片" },
    { "id": "func-1", "type": "ComponentFunction", "name": "实时采集单体电压", "specification": "±5mV@25°C" }
  ],
  "edges": [
    { "source": "sys-1", "target": "sub-1", "type": "HAS_PROCESS_STEP" },
    { "source": "sub-1", "target": "comp-1", "type": "HAS_WORK_ELEMENT" },
    { "source": "comp-1", "target": "func-1", "type": "HAS_FUNCTION" }
  ]
}
```

### 8.2 参数图在节点中的表示

```json
{
  "id": "comp-1",
  "type": "Component",
  "name": "LTC6811",
  "p_diagram": {
    "inputs": ["电池单体电压", "温度信号"],
    "outputs": ["数字电压值", "温度值"],
    "controls": ["ADC采样率", "滤波算法"],
    "noise_factors": ["电磁干扰", "温度漂移"]
  }
}
```

---

## 9. 验收标准

- [ ] 结构分析页签可增删改 System/Subsystem/Component 层级
- [ ] 点击 Component 节点可编辑参数图（输入/输出/噪声/控制）
- [ ] 创建 DFMEA 时弹出 7 步向导，完成可生成骨架
- [ ] 功能否定规则可自动生成失效模式建议
- [ ] AP 查表自动计算 H/M/L 并给出优化方向
- [ ] viewer 角色所有输入禁用，engineer+ 可编辑
- [ ] 完成后更新 `docs/ROADMAP.md` 状态

---

## 10. 依赖与风险

| 风险 | 缓解措施 |
|------|---------|
| FMEAEditorPage.tsx 已有 770 行，拆分引入回归 | 先提取组件，保持原有逻辑不变，逐步替换 |
| 中文动词否定规则覆盖率低 | 初期提供常见动词模板，后续迭代扩展 |
| 参数图 UI 复杂度高 | 先用简单表单实现（4 个文本列表），后续升级可视化 |

---

## 11. 后续扩展（Phase 3）

- 实现 `POST /api/fmea/{id}/recommend` 后端推荐接口
- 接入历史 FMEA 数据相似度检索
- 参数图可视化（方块图/边界图渲染）
