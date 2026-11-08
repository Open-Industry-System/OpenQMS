# 子故事 US-E2E-01.8：8D 知识库沉淀

**状态**: 定稿 v2（2026-10-27）
**所属 epic**: US-E2E-01（README.md v8.1）
**关联 skill**: `verify-capa-8d-knowledge-sink`
**前置**: 01.1、01.2、01.3、01.4、01.5、01.6、01.7（完整 8D 报告 + 联动 + 门禁就绪）
**AI_REQUIRED**: true（沉淀的摘要/标签生成可能用 LLM；无 LLM 凭证 → `BLOCKED`）

> **2026-10-27 实现契约同步，不是验收签字**：集中结果审核 Task 1–6 已独立复核；Task 7 正向真实 provider/浏览器、知识沉淀及横向扩散仍因缺少本工作树授权 `.env.e2e` 而 BLOCKED。普通单测/保护验收不替代这些门禁。见[操作指南](../../development/capa-outcome-review.md)与 PROGRESS 的 Task 8 交接。下文既有能力和未改范围保持不变。

## 故事

**作为** 现场质量工程师 / 8D 团队负责人，**我想** 在 8D 报告完成（D8 关闭）后，
系统自动把 8D 报告数据**结构化沉淀**到对应产品的知识库，
未来 8D/FMEA 触发推荐时可被检索命中，后续产品开发设计可按产品检索历史 8D 经验，
**以便** 8D 经验不流失、可被未来设计复用、形成"当前 8D → 知识库 → 未来 8D"闭环。

## 背景 / 前置条件

- 系统已部署，8D 已完成 D8 关闭（01.1-01.7 全部交付）。
- 对应产品已有知识库（pgvector 语义检索，01.2 全局知识库 RAG 源已就绪）。
- AI 步骤必须配置 `.env.e2e` 的 LLM 凭证（沉淀的摘要/标签生成可能用 LLM）。

## 能力：8D 报告数据入知识库

D8 关闭时，系统自动把 8D 报告数据**结构化沉淀**到对应产品的知识库：

- **沉淀内容**（结构化知识条目，非纯文本）：
  - 8D 单号、标题、严重度、产品/产品线
  - D2 问题描述（现象）
  - D4 确认根因（含验证记录摘要）
  - D5 永久措施
  - D3 遏制措施（含受影响范围摘要）
  - D7 预防 node-action（含 FMEA 节点引用）
  - 8D 联动关联（FMEA/SCAR/供应商风险）
  - 关闭结论与经验教训摘要
- **可检索**：沉淀的知识条目进入 01.2 的"经验教训库检索"与"全局知识库 RAG"源，
  未来 8D/FMEA 触发推荐时可被检索命中（形成闭环）。
- **可调用参考**：后续产品开发设计时，可通过产品/产品线检索到该产品的历史 8D 经验。

## v2：未审补充的来源语义

- D8 批准接受正式实施结果；`d8_closure` 是“结案后补充，未纳入本次审核”，不是已审更正、已审根因或已验证效果。补写不改变核心 revision/round、决定或历史来源版本；ARCHIVED 下补充仍冻结。
- 知识 `fields.closure_review_scope` 固定为 `unreviewed_supplement`；D8 经验 `source_d_step=d8` 的 tags 追加且不重复 `review_scope:unreviewed_supplement`。D7 经验不因此取得 approved 身份。
- 摘要提示、embedding/推荐派生文本保留“未审核补充”警示；原 closure 文本、分类、权限和 provider 调用次数不因标记而改变。列表/详情/经验及知识推荐读取旧数据时仅投影来源标记，不更新 ORM、历史 fields/tags 或 embedding，不回填迁移。
- 补充修改人/时间仅取最近适用的 UPDATE 审计；无记录即 null，不猜测 created_by/主表 updated_at。正式根因、措施、验证、驳回与审批记录不适用原候选 7 天清理。
- 沉淀/重沉淀不改变 D8 决定授权，不开放 Agent/plugin/model 正文交付。知识检索命中不证明补充已被接受；真实 provider/embedding/检索闭环仍是独立验收，当前 BLOCKED，普通测试不能签字。

**新增验收场景**：真实 D8 关闭后补写、resink，核对核心/receipt 不变，知识 fields、D8 tags 与推荐文本保留未审语义；旧知识只读投影无数据库变动；混合 PUT 拒绝和归档冻结无副作用。继承 v1 新 8D 推荐命中等门禁，未执行时逐项记 BLOCKED。

## 主流程

1. 8D 团队负责人审批关闭：D7_COMPLETED →（01.7 文档门禁通过）→ D8_APPROVAL_PENDING →（manager 审批通过）→ D8_CLOSURE（01.3 审批壳 + 01.7 门禁）。
2. D8 关闭时，系统自动触发知识库沉淀：8D 报告数据 → 结构化知识条目 → 对应产品知识库。
3. 沉淀完成后，知识条目可被未来 8D/FMEA 推荐检索命中（闭环）。
4. 后续产品设计可按产品/产品线检索到历史 8D 经验。
5. 沉淀记录写审计日志。

## 业务规则 / 验收标准

- **自动触发**：D8 关闭时自动触发沉淀，无需人工干预（也可手动重新触发）。
- **结构化条目**：沉淀为结构化知识条目（含上述 8 字段），非纯文本。
- **检索命中闭环**：沉淀后可被 01.2 的经验教训库/全局知识库检索源命中（E2E 验证：新发 8D 触发推荐时能命中本条沉淀）。
- **按产品检索**：后续产品设计可按产品/产品线检索到历史 8D 经验。
- **审计**：沉淀记录写审计日志。
- **数据落库**：知识库沉淀条目（结构化）正确持久化。
- **执行验证**：E2E 断言沉淀闭环（8D 关闭 → 知识库 → 新 8D 推荐命中）。
- **LLM 不可降级**：无 LLM 凭证 → `BLOCKED`；LLM 阶段 `skipped`/`error` → `FAILED`。

## 验收契约（字段级）

| 项 | 定义 |
|---|---|
| 落库实体 | `knowledge_entries`（source_type=capa，source_id=capa_id，fields 为结构化内容）、`document_embeddings`（向量）；D8 经验在 `capa_lessons_learned` |
| 关键字段 | entry.source_id、product_line_code、fields（问题/根因/措施/预防/关联/closure 等）、summary、tags、embedding_status；fields.closure_review_scope=unreviewed_supplement；D8 lesson.tags 含 review_scope:unreviewed_supplement；检索命中返回 entry |
| 状态枚举 | 沉淀条目状态：active（可检索） |
| 审计事件 | `KNOWLEDGE_SUNK`（含 capa_id、product_line_code、entry_id）、`KNOWLEDGE_RETRIEVED`（闭环验证，含命中 entry） |
| E2E seed 前置 | 8D 完成 D8 关闭；产品有知识库；后续新 8D 触发推荐验证命中 |
| 通过条件 | D8 关闭自动沉淀 + 8 字段结构化 + 新 8D 推荐命中本条 + 按产品检索可见 + 审计 |
| 失败条件（FAILED） | 沉淀未触发；字段非结构化（纯文本）；检索未命中；未审计 |
| 阻塞条件（BLOCKED） | 无 LLM 凭证 |

## 不在本子故事范围

- 知识库的检索质量/召回率评测（epic 范围外）。
- 知识条目的人工编辑/审核工作流（本子故事只管自动沉淀，人工审核为后续迭代）。
- 横向扩散预警（见 01.9）、PPT 输出（见 01.10）。

## 后续

- 知识条目的人工审核/编辑工作流为后续迭代。
