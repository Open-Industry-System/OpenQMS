# R4b 主线集成验收与交接

## 基线和边界

- 刷新后的 origin/main：`5b712d94ed08412a6c3d92e4dca2d9193b5959d3`，包含 PR #29。
- 已签收输入：`dcda1d5590d083c6732bb3fad0d7b5d4156ba4f6`；合并基点 `4a00636f2928d0a4d3ca2de56599ad1ae3b57fb6`。
- 独立分支 `integration/r4b-main-20261114`，独立工作树 `/Users/sam/.codex/worktrees/0cd0/OpenQMS`。主目录未提交改动、原R4b工作树及全部旧资源保留。应用会话与Git分支清单未发现另一活跃集成执行者。
- 只推送本分支并创建草稿PR，不直接写main、不强推、不合并、不部署或启用生产/模型。

## 冲突决策

实际17个冲突文件，逐段处理而非整批选边：

- 权限 access/catalog/types：保留main对未知/伪造能力的统一DENY、原位置参数兼容；加入R4b显式FMEA发现权限及插件/任务双层精确来源范围。
- readonly_delivery/runtime_access/task_service：保留main历史receipt服务端固定合同识别、旧metadata语义，保留R4b单父grant、blocked请求指纹和text运行来源身份；自动合并的消息门禁、checkpoint/restart、撤权后pause/cancel围栏另行复核。
- 模型注册：保留AgentReadTask与全部R4b证据/恢复模型；CP与特殊特性模型沿main保持。投影回归使用真实当前编辑者，保留两种缺租户绑定拒绝测试。
- Make：保留main的RELEASE_SECRET_ENV及应用.env解析，不由Make注入运维测试口令；R4b增加SDK三层和backend wheel供应。CI自动合并保留main的ubuntu-24.04浏览器运行环境，加入SDK矩阵与正文必选测试。
- 迁移/tenant parity及测试：新增双图merge，不重写发布ID、旧DDL或冻结快照；详见下节。
- PROGRESS/architecture：保留双方已发生的进度与业务边界，追加本轮结果，不将历史数字冒充本轮验证。

自动合并测试真实复现：权限拒绝文案与缺grant_id夹具2失败/18通过，按main合同及真实模型修正后20通过；Make两份合同2失败/15通过，保留main运维解析并修过期R4b断言后17通过。日志保存在本轮私有目录。

## 迁移合同

public merge `20261114_r4b_main_merge` 汇合 `20261108_merge_characteristics` 与 `20261113_d4_recovery`；tenant merge `tv009_r4b_main_merge` 汇合 `tv007_characteristic_refs` 与 `tv008_d4_recovery`。特性分支增加两列，D4分支增加9表，两者DDL兼容，merge无DDL。不删旧merge节点、不stamp。

tenant降级检查严格图祖先关系且所有父路径必须到同一目标，不能按版本列表顺序跨分支，也不能拆merge留下多个head；合并后只允许共同祖先tv006及更早，旧分支内部回退保留，执行后再核单版本。各旧head的parity仅从public参考扣除其缺失增量，不筛除tenant实际对象。tv006采用main已发布字节；与R4b仅首行docstring不同，双方hash及去docstring AST等价另测，不能声称两者字节相同。冻结snapshot和manifest不重生成。

真实迁移首轮72通过/2失败，根因为Alembic从merge降某单支只拆merge、不移除另一支；未放宽parity或删sibling，补上述DDL前/提交前守卫。新27项guard及两旧tenant分支专属数据保留已补，真实新一轮结果待记。旧附件cycle/public配对真实RED2后修为历史tv005，当前parity用tv009，复跑5通过；旧迁移state矩阵真实RED9后对齐main映射并加入两侧head，17通过。权限位置参数旧测试真实RED1后按已发布main slots重建验证，整套纯权限/适配器150通过；CI pure321通过/3既有Pydantic警告。这些均为本轮实际中间证据，不代替最终候选门禁。

## 本轮专用测试资源

- owner：`26a2159e6e037e8d9e421c06`；容器 `openqms-r4b-integration-26a2159e6e037e8d9e421c06`。
- 完整容器ID：`e0f58ff43b7c9abaffebe3feb0442253c984acd8f800945d89436e25b8a9665b`。
- 专属卷：`openqms-r4b-integration-26a2159e6e037e8d9e421c06-data`；容器/卷均使用本owner。仅用缓存镜像 `pgvector/pgvector:pg15`，image ID `sha256:bd12d6788a617f4147d5a2ae0b56d07921398adabfe5a033bd3f50c245df55a1`。
- 数字回环端点 `127.0.0.1:62563`；主库 `qms_r4b_integration_26a2159e6e03_test`；应用哨兵 `qms_r4b_integration_26a2159e6e03_sentinel`。
- 固定本地socket `unix:///Users/sam/.docker/run/docker.sock`，context `desktop-linux`，daemon ID `aaa6bf3b-6bc0-468e-88c5-f6f60da83210`。首次sandbox拒绝，经正式工具权限申请后只读核实daemon。
- 私有目录 `/private/tmp/openqms-r4b-integration-20261114-xjym36on`，独立登记 `resource.json`、凭据 `credentials.json`/`postgres.env` 均0600；不打印或提交秘密。允许本独占实例内串行创建/清理UUID迁移库，不借业务或其他任务资源。
- 已通过仓库owned-resource验证与 `make check-test-db`，新空主库实际升级到新public head。后续验收尚在进行，不以此代替三路径及完整门禁。

## 验证与剩余事项

迁移与多租户整组中间结果：378通过/5失败/1跳过/3警告（run-1794631164079280000.log，886.80s）；其中新三public路径、两侧tenant专属数据与27 guards通过。5失败均为旧current-head硬编码，修正后单独复跑5通过/3警告（run-1794632232971970000.log，18.56s），未放宽parity。唯一跳过为未显式指定PG15工具容器的快照再生成，现将本次完整容器ID通过PG15_CONTAINER传给验证入口，正在实际重跑，不作为最终允许skip。一次复跑请求因自动权限复核超时未执行，工具允许的一次重试成功启动；不是测试失败。

焦点、完整候选及远端CI结果待逐项追加。R4B-CLEANUP-01仍延期，其测试容器/卷、诊断容器、凭据和阻塞均保留，详见[延期清理清单](capa-d4-local-text-delivery.md#保留资源与后续清理入口)。本轮新实例独立登记，清理状态另记，不自动关闭旧待办。
