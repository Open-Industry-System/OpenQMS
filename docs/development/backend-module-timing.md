# 单次全量逐模块计时与受控对照

2026-11-16。计时补丁基于 a0f291be；PR #37 前一轮8项全绿，但job为热缓存84分42秒，冷缓存参考70分05秒，不能据此归因。main相同基线树另一次冷缓存96分24秒，说明必须控制条件。

每次正常 pytest 由已有 gate_results 按 report.location[0] 的测试源模块统计 selected 与 setup/call/teardown。模块包含该模块测试实际付出的fixture时间；module/session级fixture成本计在首次使用它的测试上，不是fixture定义文件归属。collection仍为全套指标，不把导入/收集时间伪分配到模块。所有模块以 OPENQMS_GATE_MODULE_TIMING 独立JSON行写入同一既有脱敏log和控制台，避免单行过长；只读已有report，不追加收集或执行，receipt schema及退出规则不变。可选诊断的字段/数值校验、白名单和redaction保持，坏诊断不能改变原通过/失败。

selection_sha256 对按执行顺序排列的源模块/完整case identity做SHA256，参数值不公开。前后需此摘要、selected/passed/skip/deselected及模块计数相同，才能作同组比较。解析既有log最后一条父 OPENQMS_GATE_TIMING 后的模块记录，不能把烟测的嵌套样本混入全套数据。

本轮计划：同一macOS机器、同一既有Python3.11解释器/依赖，不安装依赖；两轮各创建同一已缓存镜像的全新独占PG15容器/匿名卷，随机回环端口、相同数据库名及配置，走真实 make check-backend 正常入口。前后使用相同计时代码和全部测试。对照源码仅将rebuild_db/sample恢复为原实现，并保留两边相同的一次模板初始化（对照侧不使用它），以保留新增隔离回归、相同集合和公共初始化成本。原测试体/参数/marker不变，不以减少5项新回归换取可比性。此对照隔离fixture复用的效果，不等同完全重演旧commit的job。

先串行A（原fixture）/B（复用fixture）。记录源码、解释器/依赖、镜像与PG配置指纹、负载样本、正常Make wall、pytest及模块分项；结束核验无残留fixture库与其他客户端，再仅清理该轮资源。依赖预装，两边不测pip冷/热；不清空共享宿主OS缓存，不声称本机CPU独占。若未改模块的call也明显漂移，应补B/A而不是直接归因。此结果不能代替Actions job总耗时，后者仍需新PR run读取。

已完成基础验证：pure358 passed /3既有warnings；模块两项烟测包含成功/失败exit0/1与phase守恒，原collection失败exit2和单次收集保护保留。全量A/B尚未完成，不预写性能结论。原始证据及最终报告将保存在 /tmp/openqms-controlled-backend/，PR描述补录结果，不提前合并。

补充一致性修正：显式pytest配置下复现不同模块同名测试的短nodeid覆盖旧durations键，导致旧全套phase汇总低估。计时键改为源模块＋case identity；新增显式配置/默认配置的同名用例守恒回归，纯测试358通过。wall time与门禁计数不受该旧缺陷影响。两侧对照使用同一修正，不将旧分项直接当受控基线。

## 2026-11-16：优先处理PR #37并同步当前main

PR #37从804f8551正常合入当前main d0c7394e；仅PROGRESS并发记录需要解决冲突。保留main已合入的R5、#39测试精简、8项普通PR门禁和独立macOS手动试点工作流。runner计时发布与R5固定目录逻辑共存，不覆盖新主线配置。

此前本地全量A实际5280 passed／5 skipped／exit0，Make4326.03秒；B为5279 passed／5 skipped／1 failed，Make4398.99秒，失败是未改动的test_concurrent_first_sink_unique_race唯一键冲突。两侧集合摘要相同，但失败的B不能签收为成功的性能对照；没有删除该并发测试或放宽退出码。原始证据保留在/tmp/openqms-controlled-backend/，并将PR中过时的“仍在运行”状态改为这一实际结果。

新的R5/main基线与旧804f8551的测试集合不同，旧CI全绿及旧阶段时间不代替本次验收。先在同一台机器、固定解释器／依赖／PG15镜像下对相同重建、迁移及隔离集合重新验证；两轮使用各自独占新实例与相同公共模板初始化，唯一执行源码差异为rebuild_db/sample准备实现。完整后端的模块诊断继续随正常一次全量运行生成，不预写整套收益。
