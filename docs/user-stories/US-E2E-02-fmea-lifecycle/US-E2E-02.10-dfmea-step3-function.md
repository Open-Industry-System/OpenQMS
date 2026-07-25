# 子故事 US-E2E-02.10：DFMEA Step3 功能分析

**状态**: 定稿 v1（2026-07-25）
**所属 epic**: US-E2E-02（README.md v1）
**关联 skill**: `verify-fmea-lifecycle-dfmea-step3-function`
**前置**: 02.9（Step2 结构树已就绪）
**AIAG-VDA 引用**: `Reference/FMEA.md` §2.3（设计 FMEA 步骤三：功能分析）
**AI_REQUIRED**: false

## 故事

**作为** 设计质量工程师，**我想** 在向导 Step3 定义功能树（系统功能 / 子系统功能 / 零部件功能），含参数图(P图)辅助，区分要求与功能，
**以便** 明确每个结构节点的功能与要求，为失效分析（Step4）的"功能否定→失效模式"推导提供基础。

## 背景 / 前置条件

- Step2 结构树已落库。

## 主流程

1. `planning_qe` 在 Step3 为每个结构节点录入功能：
   - `SystemFunction`、`SubsystemFunction`、`ComponentFunction`
2. `HAS_FUNCTION` / `FUNCTION_MAPPED_TO` 边连接功能与结构节点。
3. 保存草稿。
4. 推进到 Step4。

## 业务规则 / 验收标准

### 结构完整性
- 3 层功能节点齐全，`HAS_FUNCTION` 边挂载到对应结构节点。
- DFMEA 无 CC/SC 列（AIAG-VDA DFMEA 已移除，PFMEA 才有）。

### 门禁
- 推进 Step4 前：至少 1 个功能节点。

### 审计与落库
- Step3 保存写 AuditLog。

## 验收契约（字段级）

| 项 | DFMEA 定义 |
|---|---|
| 落库实体 | `SystemFunction`、`SubsystemFunction`、`ComponentFunction` |
| 关键字段 | Function.name |
| 边类型 | `HAS_FUNCTION`、`FUNCTION_MAPPED_TO` |
| AI 触发器 | 无（AI_REQUIRED=false） |
| 状态枚举 | FMEAState 不变（DRAFT） |
| 审计事件 | `fmea.updated` |
| E2E seed 前置 | 02.9 结构树 |
| 通过条件 | 3 层功能树齐全 + 边正确 + 审计 |
| 失败条件（FAILED） | 功能树断层；边缺失；未审计 |
| 阻塞条件（BLOCKED） | 无（AI_REQUIRED=false） |

## 不在本子故事范围

- Step4 失效分析（见 02.11）。
- 参数图(P图)的深度可视化（现有 `dfmea-wizard-pcdc-ai`，本子故事只验功能树）。

## 后续

- 功能树为 Step4 失效分析提供 FM 挂载点。
