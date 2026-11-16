# R5 D5 消费策略（2026-11-14，T3）

基线为 T1 `c0cd8abf`、T2 `e4e8f39b`。正式措施只存在于 `capa_d5_measures`，原有 `d5_correction` 仍为普通 legacy 文本；不能把员工看见的条目列表当作完整材料。建议保存/采纳、实际模型接收方准入属于后续任务，本项不开放这些写能力。

核对入口为 `rg -n 'd5_correction' backend/app frontend/src`，T3 开始时共 66 个字面命中（包括模型、DTO、种子、翻译和测试）。下表按实际消费链归并；新增消费路径须先选择同等策略，不能默认把正式文本拼入旧字段。

| 路径 | 策略 | 实际验证入口 |
|---|---|---|
| 报告普通详情、列表、D5 legacy 编辑框 | 排除受限内容：普通 DTO/字段保留 legacy；不追加正式措施，不暴露隐藏总数或来源坐标 | `test_d5_measure_visibility.py::test_hidden_detail_is_missing_and_legacy_dto_unchanged` |
| `capa_d5_measures` 员工建议/措施 GET | 作用域投影：当前身份、报告与所有原始来源先授权，再计数/分页/读正文；隐藏详情等同不存在 | `test_d5_measure_visibility.py`；T2 30 项 |
| `capa_service` D5→D6 | 业务资格检查：legacy 或实际、关联有效且来源元数据一致的正式措施即可，不以员工过滤后的数量判断 | `test_d5_consumers.py::test_restricted_only_d5_advances_without_legacy_copy`、`test_d5_business_completeness_requires_real_formal_material` |
| `capa_outcome_review` GET、批准/驳回；既有归档 | GET 与批准/驳回受控完整读取：逐项与原始正式集合比较，任何缺来源/损坏关联/无权均拒绝；独立 `d5_measures` 含 ID、最终正文 HMAC 版本、采纳信息、依据修订/proof、完整来源坐标。core legacy 不变。完整集合及当前受控来源版本进入现有材料 HMAC、轮次与父锁后二次复核。归档沿用既有无正文状态转换及权限检查，不增加 full-D5 读取或重新签名要求；归档后的审核 GET 仍要求完整材料权限 | `test_d5_outcome_fence.py` 的实际 GET、完整批准/归档和父锁等待后正文/次要来源 ACL 变化；既有 outcome decision/concurrency/source 测试 |
| `CapaOutcomeReviewPanel` | 完整读取后的独立只读正式措施区，显示每项及来源绑定；解析器要求正式集合与来源文档绑定完整，缺失不能提供审批 token；正文按文本转义 | `CapaOutcomeReviewPanel.test.tsx`、`CAPADetailPage.test.tsx` |
| `capa_review_guard`、`capa_review_source_guard` | 同一终态保护：正式/建议材料名及次要正式来源都纳入既有 CAPA 父锁与来源引用守卫，结案/归档不能绕过 | `test_d5_outcome_fence.py::test_source_reference_guard_includes_secondary_d5_source`、`test_new_d5_material_names_use_same_terminal_guard` |
| `capa_ppt_service` / PPT API / `capa_ppt_review_service` | 受控完整读取：无模型生成由当前员工全来源权限读取；缺任一项即拒绝。已有模型审查缺逐项接收方合同，存在正式措施时明确不可用，不把局部 PPT 当完整 | `test_d5_consumers.py::test_full_ppt_requires_current_complete_authority`、既有 `test_capa_ppt_api.py` |
| `capa_doc_gate_service` | 人工/审核写入在父锁下要求完整来源读取，并在集中 `_insert_decision` 的最后 analysis/document 等锁后重新解析当前角色、完整来源 ACL 与 C9 绑定；C9 hash 在存在正式措施时加入完整条目绑定。已有模型影响分析未接正式条目接收方准入，存在正式措施即 `D5_FULL_MATERIAL_UNAVAILABLE`；不发送其正文。后续模型准入前不能产生声称覆盖它们的新分析 | `test_d5_consumers.py::test_model_path_without_item_recipient_contract_is_unavailable`、实际批准的完整 C9 围栏 |
| `capa_draft_service` | 现有整份报告模型草稿无法认证正式条目接收方，存在正式措施时明确不可用，不生成遗漏正式材料的草稿 | `require_legacy_d5_only` 共用守卫；正式措施与模型路径测试 |
| `capa_d7_action_service` / `capa_service` D7 推荐 | 排除受限内容：既有结构推荐只消费 legacy；自动回填会把正文写进没有逐项 ACL 的 FMEA，存在正式措施时明确不可用 | `test_d5_consumers.py` 共用守卫；推荐原有业务测试 |
| `knowledge_sink_service` | 排除受限内容：确定性字段、知识派生及其模型提示只取 legacy，不读取正式条目表，不向下游传播其正文 | `test_legacy_knowledge_and_background_embedding_exclude_formal_text` |
| `embedding_sync_worker.fetch_chunks/process_batch_once` | 排除受限内容：CAPA chunks 仅映射旧字段，后台入队/取块/向量持久化不追加正式文本 | 同上，真实数据库 outbox→worker→持久化；仅外部 embedding 返回确定性向量 |
| `lessons_learned/sources/historical_capa` | 排除受限内容：历史 action 为 legacy；召回源不读取正式条目 | `test_historical_sources_exclude_formal_text` |
| `recommendation_sources.HistoricalCAPASource/HistoricalCAPAMeasureSource` | 排除受限内容：历史 D2/D4 检索与 D5 建议仅取 legacy，不能被解释为完整正式措施集 | 同上，真实 SQL 两条 `_search` 路径 |
| `capa_verification_service` 旧建议采纳、旧种子、schemas/models、翻译/前端旧类型 | 保留 legacy 合同，不作为 R5 正式采纳入口；R5 后续写服务须使用相同父锁和终态保护 | 既有 legacy 与 T2 DTO 回归 |

## 完整性及锁约定

`full_d5_material` 不把 T2 过滤后的子集当作完整集合。它先比较报告原始持久措施 ID 集合与通过关联和所有来源 ACL 的集合，才加载正文；读取后再次核集合和来源元数据。坏关联同样导致完整读取不可用。D5 当前依据新鲜度不用于抹除已经采纳的历史措施。

审批继续使用现有 CAPA 父锁、analysis→产品线→排序来源父锁、当前角色/行/来源权限复核、材料版本与轮次围栏。归档继续沿用既有状态/权限转换，不把批准时的完整读取要求扩大为归档的新前置。新增 D5 来源加入同一个受控文档版本/来源锁集合；来源删除或移动会经 CAPA 引用守卫。没有正式条目时，旧 outcome HMAC 和 C9 hash 输入保持不变；新 DTO 显式返回空正式集合。没有引入 R4b 正文或 metadata 协议扩展。

## 验证限制

实际 tenant 向量消费初跑暴露既有扩展查找问题：安全 search_path 不包含 public，而旧 SQL 使用未限定 `vector` 类型/`<=>`。此项未修改其生产行为。两个向量消费用例仅在测试 `execute` 适配中将扩展类型/运算符限定为 `public.vector`/`OPERATOR(public.<=>)`；业务表仍在原隔离租户中解析，真实取块/outbox/SQL/持久化没有被模拟。该证据证明 D5 排除策略，不代表原生产 tenant 向量查询已通过。该原始失败须保留，不用适配后的通过掩盖。没有实际模型调用。

R5 采纳能力继续关闭，直到后续任务逐项通过。完整 `make check`、浏览器与远端 CI 不由本项焦点测试替代。大历史材料扫描的性能尚未量测。
