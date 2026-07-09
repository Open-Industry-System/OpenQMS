# 子故事 US-E2E-01.10：8D 报告 PPT 输出

**状态**: 定稿 v3（2026-07-09）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-ppt-output`
**前置**: 01.1-01.9（完整 8D 报告 + 联动 + 沉淀就绪，方有完整 PPT 内容）
**AI_REQUIRED**: PPT 生成本身 false（模板渲染，非 AI 步骤）；**sub-agent 内容审查需 LLM**（无凭证→跳过审查 + 提示「大模型未配置」，PPT 仍可生成；功能错误 → `FAILED`）

> **v3 变更（2026-07-09）**：将原 v2 §101 延后的「LLM 按建议改写内容呈现」校正拉入实现（代码审查反馈：3 轮闭环在纯重新查数据下对内容类建议无效）。校正现分两类：规则 issues（结构/数据缺口）→ 重新查数据 + 残留短路 needs_review；LLM 内容建议 → LLM 改写各页 section 的 value（**仅呈现层，不编造数据、不动 linked/verification 落库事实**，结构不符回退原内容）。完整「LLM 生成新内容」仍不在范围。
> **v2 变更（2026-07-08）**：新增 sub-agent 审查闭环（生成后自动审查 + 校正，3 轮上限）+ 审查 skill 管理（admin 可配置审查标准，按租户隔离）+ LLM 未配置提示。原 v1 的一键生成 + 模板渲染不变。

## 故事

**作为** 现场质量工程师 / 8D 团队负责人，**我想** 在 8D 报告完成（D8 关闭）后，
能**一键生成 8D 报告的完整 PPT 版本**（标准 8D 模板，用于汇报/归档/跨部门共享），
**生成后由 sub-agent 自动审查内容是否符合审查标准，不通过则自动校正重生成，直到合格或达 3 轮上限**，
可重复生成取最新数据，
**以便** 8D 报告可便捷输出为标准格式且内容质量经自动校验，便于汇报与归档。

> **范围说明**：本故事验 D8 关闭后的完整 PPT 生成 + sub-agent 审查闭环。"阶段性草稿 PPT"（D8 关闭前任意已完成阶段生成）不在本故事范围，如需可另立。

## 背景 / 前置条件

- 系统已部署，8D 已完成 D8 关闭（01.1-01.9 全部交付，完整报告数据落库）。
- 系统后端可生成文件供前端下载。

## 能力：8D 报告 PPT 自动化输出 + sub-agent 内容审查

D8 关闭后，可**一键生成 8D 报告 PPT 版本**，生成后由 sub-agent 自动审查内容：

- **PPT 结构**（标准 8D 报告模板）：
  - 封面（8D 单号、标题、严重度、产品、发起人、状态、日期）
  - D1 团队
  - D2 问题描述
  - D3 遏制措施（含受影响范围摘要）
  - D4 根因分析（含验证记录摘要）
  - D5 永久措施
  - D6 实施验证
  - D7 预防复发（含 node-action 摘要）
  - D8 关闭结论
  - 联动关联附录（FMEA 关联节点详情 + SCAR/供应商风险预警单号与状态）
  - 生成信息（版本、审查状态、审查轮数）
- **生成方式**：后端生成 PPT 文件，前端浏览器下载（原生保存对话框）；内容来自 8D 各步落库数据 + 证据附件引用。
- **可重复生成**：8D 数据变更后可重新生成（取最新落库数据）。
- **sub-agent 内容审查**（生成后自动）：
  - 生成后派遣 sub-agent 依据**审查 skill**（admin 可配置的审查标准）审查 PPT 内容是否符合要求
  - 审查不通过 → 按审查反馈自动校正 → 重生成 → 再审查。校正分两类（v3）：规则 issues（结构/数据缺口）→ 重新查数据，残留短路 needs_review；LLM 内容建议 → LLM 改写各页 section 的 value（**仅呈现层、不编造数据、不动 linked/verification 落库事实**；结构不符回退原内容）
  - **3 轮上限**：达上限仍不合格 → 返回最后 PPT + 审查报告（标记「需人工复核」），不报错
  - **LLM 未配置** → 跳过 sub-agent 审查，PPT 仍生成（只跑内置规则校验），前端提示「大模型未配置，已跳过自动审核」；配置完成后方可进行自动化审核
- **审查 skill 管理**（admin）：
  - 审查标准以 skill 形式存储（DB 表，按租户隔离），admin 可查看/编辑 content
  - sub-agent 审查时从表读 skill content 作为审查标准
  - 本故事固定单 skill（`capa_ppt_review`）；多 skill 选择规则为后续迭代

## 主流程

1. 8D 完成 D8 关闭（01.1-01.9 全部就绪）。
2. field_qe 或 8D 团队负责人（engineer+）在 8D 详情触发【生成 PPT】。
3. 系统从落库数据生成 8D 报告 PPT（D1-D8 + 封面 + 联动附录 + 生成信息页）。
4. 内置规则校验（页数/必填字段非空/内容来源匹配）；不通过则按规则校正重生成（不耗 LLM 轮次）。
5. 若 LLM 已配置：派遣 sub-agent 依据审查 skill 审查 PPT 内容；不通过则按反馈校正重生成，再审查，3 轮上限。
6. 若 LLM 未配置：跳过 sub-agent 审查，前端提示「大模型未配置，已跳过自动审核」。
7. 前端浏览器下载 PPT 文件（原生保存对话框）。
8. 可重复生成（数据变更后取最新）。
9. 生成记录 + 审查结果写审计日志（`PPT_GENERATED`，含 capa_id、generated_by、version、review_status、review_rounds）。

## 业务规则 / 验收标准

- **一键生成**：D8 关闭后（D8_CLOSURE 或 ARCHIVED）可一键生成 PPT。
- **权限**：engineer+（L2 quality_engineer 及以上）可生成；viewer 不可。
- **PPT 结构**：覆盖 D1-D8 各页 + 封面 + 联动附录 + 生成信息页，内容来自落库数据。
- **联动附录**：列关联 FMEA/SCAR/供应商风险预警的单号与状态，并展开 CAPA 关联的 FMEA 节点（`fmea_ref_id` + `fmea_node_id` 指向的失效模式节点）详情（失效模式/原因/控制），非全部节点。
- **生成成功**：生成成功且可下载（文件非空、可打开）。
- **sub-agent 审查**（LLM 已配置时）：生成后自动审查，不通过则校正重生成，3 轮上限；审查通过 → `review_status=passed`；达上限仍不合格 → `review_status=needs_review`（返回最后 PPT + 审查报告，不报错）。
- **LLM 未配置**：跳过 sub-agent 审查（`review_status=skipped`），PPT 仍生成，前端提示「大模型未配置，已跳过自动审核」；配置完成后方可进行自动化审核。
- **审查 skill 管理**：admin（L5）可查看/编辑审查 skill content（按租户隔离）；sub-agent 审查时从表读 skill content 作为审查标准。
- **可重复生成**：可重新生成，取最新落库数据。
- **审计**：生成记录写审计日志（`PPT_GENERATED`，含时间、生成人、version、review_status、review_rounds）。
- **数据落库**：PPT 生成记录（`capa_ppt_export`）正确持久化（含审查状态、轮数、报告）。
- **执行验证**：E2E 断言 PPT 生成（文件可下载、结构完整、内容来自落库数据、审查状态正确、审计写入）。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `capa_ppt_export`（生成记录）+ `agent_review_skill`（审查 skill，admin 管理） |
| 关键字段 | export.capa_id、export.generated_at、export.generated_by、export.version（=generated_at 时间戳）、export.file_url（恒 None，不落盘）、export.review_status、export.review_rounds、export.review_report；skill.name（固定 `capa_ppt_review`）、skill.content、skill.version、skill.tenant_schema；PPT 结构页 D1-D8 + 封面 + 联动附录 + 生成信息页 |
| 状态枚举 | export.review_status: `passed`（审查通过）/ `skipped`（LLM 未配置跳过）/ `needs_review`（3 轮上限仍不合格）；文件存在且可打开 |
| 审查轮数 | export.review_rounds: 0=未审查/跳过，1=首轮通过，2-3=校正后通过或达上限 |
| 审计事件 | `PPT_GENERATED`（含 capa_id、generated_by、version、review_status、review_rounds）+ `SKILL_UPDATED`（admin 改 skill content） |
| E2E seed 前置 | 8D 完成 D8 关闭；各步数据落库；审查 skill 已 seed |
| 通过条件 | D8 关闭后一键生成 + D1-D8+封面+附录+生成信息页齐全 + 文件非空可下载 + 可重复生成 + 审查闭环（LLM 配置时 passed/needs_review，未配置时 skipped+提示）+ skill admin 可编辑 + 审计 |
| 失败条件（FAILED） | 生成失败；文件空/不可打开；结构缺页；内容非来自落库数据；审查闭环异常（非 LLM 缺失）；未审计；非 admin 改 skill |
| 阻塞条件（BLOCKED） | 无（PPT 生成 AI_REQUIRED=false；sub-agent 审查 LLM 未配置时降级为 skipped，不阻塞） |

## 不在本子故事范围

- 阶段性草稿 PPT（D8 关闭前任意已完成阶段生成 PPT；本故事只验 D8 关闭后完整 PPT，如需可另立）。
- PPT 模板的自定义/编辑（本子故事用标准模板，模板可配置为后续迭代）。
- 8D 报告的 PDF/Excel 输出（本子故事只做 PPT，其他格式后续）。
- 多审查 skill + 选择规则（本故事固定单 skill `capa_ppt_review`；多 skill 选择为后续迭代）。
- sub-agent 审查的 LLM 改写内容**呈现层**已实现（v3，不编造数据、不动落库事实）；完整「LLM 生成新内容」仍为后续迭代。
- 知识库沉淀（见 01.8）、横向扩散（见 01.9）。

## 后续

- PPT 模板可配置化、支持自定义品牌/格式为后续迭代。
- 8D 报告导出为 PDF/Excel 为后续迭代。
- 多审查 skill + 按规则选择（如按 severity 匹配不同审查标准）为后续迭代。
- sub-agent 审查支持 LLM 重写内容建议（而非仅查数据/修结构）为后续迭代。
