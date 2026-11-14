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

真实迁移首轮72通过/2失败，根因为Alembic从merge降某单支只拆merge、不移除另一支；未放宽parity或删sibling，补上述DDL前/提交前守卫。新27项guard及两旧tenant分支专属数据保留已补，最终实际通过结果见下节。旧附件cycle/public配对真实RED2后修为历史tv005，当前parity用tv009，复跑5通过；旧迁移state矩阵真实RED9后对齐main映射并加入两侧head，17通过。权限位置参数旧测试真实RED1后按已发布main slots重建验证，整套纯权限/适配器150通过；CI pure321通过/3既有Pydantic警告。这些均为本轮实际中间证据，不代替最终候选门禁。

## 本轮专用测试资源

- owner：`26a2159e6e037e8d9e421c06`；容器 `openqms-r4b-integration-26a2159e6e037e8d9e421c06`。
- 完整容器ID：`e0f58ff43b7c9abaffebe3feb0442253c984acd8f800945d89436e25b8a9665b`。
- 专属卷：`openqms-r4b-integration-26a2159e6e037e8d9e421c06-data`；容器/卷均使用本owner。仅用缓存镜像 `pgvector/pgvector:pg15`，image ID `sha256:bd12d6788a617f4147d5a2ae0b56d07921398adabfe5a033bd3f50c245df55a1`。
- 数字回环端点 `127.0.0.1:62563`；完整门禁主库 `qms_test`；初始迁移/焦点库 `qms_r4b_integration_26a2159e6e03_test` 另行保留；应用哨兵 `qms_r4b_integration_26a2159e6e03_sentinel`。
- 固定本地socket `unix:///Users/sam/.docker/run/docker.sock`，context `desktop-linux`，daemon ID `aaa6bf3b-6bc0-468e-88c5-f6f60da83210`。首次sandbox拒绝，经正式工具权限申请后只读核实daemon。
- 私有目录 `/private/tmp/openqms-r4b-integration-20261114-xjym36on`，独立登记 `resource.json`、凭据 `credentials.json`/`postgres.env` 均0600；不打印或提交秘密。允许本独占实例内串行创建/清理UUID迁移库，不借业务或其他任务资源。
- 初始焦点964项通过后，main真实事务夹具要求精确库名qms_test而拒绝继续（1个setup error）。保留隔离守卫；在同一已核验独占实例内登记并创建qms_test，原库不删除。`resource.initial.json`、`credentials.initial.json`保留初始登记和凭据（0600）；当前resource.json/credentials.json指向qms_test，口令从未打印。
- 两个主测试库均实际从空库迁到新public head；public三路径及tenant专项由本实例内独立UUID迁移库串行验证。PR #29剩余真实事务用例在qms_test复跑27通过/3警告，未以补值或放宽校验掩盖生产问题。

## 最终本地候选验收

执行候选为 `78b428d27e686587f89011eb97a0cd12ce5f2949`，包含集成merge `ebc502c2`。对backend/frontend/SDK/scripts/CI/Make等1575个已跟踪执行文件冻结内容与权限，前后核验一致，私有 `execution-manifest-v2.json` SHA256为 `27bcbdf738c63787934a29877ea608c08997a8e54b10d715fcd931f1a87a70bd`。本节后续文档收尾不改变执行字节；最终PR自动CI仍须针对实际推送head完成，不拿本地通过冒充远端结果。本机Python3.11.15/pytest9.0.3、Node26.13.0/npm11.20.0；远端平台差异由CI验证。

| 门禁 | 本轮结果 | 证据（均位于上述私有目录） |
|---|---|---|
| make check | exit0；backend **4973 passed /4 skipped /19 deselected /6 warnings**，0 failed/error/xfail/xpass；前端tsc/build通过 | run-1794634548796572000.log；artifacts/api-20261114T053600534135-receipt.json，frozen_sha精确78b428d2，后端4073.85s |
| SDK（make check内） | unit562、loopback16、wheel1，均PASS且0skip/fail/error | artifacts/sdk/sdk-all-itbYPU/sdk-check-xgr90vr8/ 三份receipt；wheel SHA256 `855e6573f3f828d16b9179a69f8f2ca390daa75af2227267893c2071f38d7ae9` |
| 真实Chromium | **11 passed /0 skipped /6 warnings**，exit0 | run-1794638749933039000.log；artifacts/browser-20261114T064551498647-receipt.json，frozen_sha精确78b428d2，179.66s |
| CI pure | **321 passed /3 warnings**，exit0 | run-1794632939662273000.log |
| 前端单测 | **95文件/822 passed**，exit0 | 最终候选run-1794633882873089000.log；前轮记录保留，不冒充新候选 |
| E2E TypeScript | exit0 | 最终候选run-1794633032329589000.log |
| 清理器隔离检查 | 普通/-O各55通过，无Docker/DB I/O | 当前候选上直接执行同目录maintenance测试；不操作延期资源 |

后端4个skip精确为：未配置Redis的1个memory测试，以及未开启E2E_MODE/未初始化共享seed的3个旧E2E endpoint测试。快照再生成不再skip，使用本次容器完整ID的PG15工具实际通过。19个未选择来自原层级标记；浏览器另跑，live provider与real scanner未请求，原Make两个graph文件排除保持不变。未调用真实模型、未重新执行独立手工PR #29全UI审批演练、未启动真实ClamAV层，不将附件授权回归当作scanner验收；生产/部署未开启。

实际命令（URL/口令仅由私有控制器注入，不在命令行展开）：

```sh
make check PYTHON_BIN=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python SDK_PYTHON_BIN=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
make check-browser PYTHON_BIN=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
python -B scripts/check-ci-pure.py tests/ci tests/e2e/test_capa_outcome_runner.py -q --tb=short
npm --prefix frontend run test -- --run --maxWorkers=1
frontend/node_modules/.bin/tsc -p frontend/tsconfig.e2e.json
```

最终后端日志逐节点确认public三路径（空库/main `20261108_merge_characteristics`/R4b `20261113_d4_recovery`）均到同一 `20261114_r4b_main_merge`，双分支有值保留且重复upgrade不变。tenant空建和两旧head有值升级到 `tv009_r4b_main_merge`、full parity、27项损坏/证据/回滚guard均通过。原历史前驱升级及冻结快照再生成也在完整门禁覆盖。

## 资源状态与发布交接

验收后只读收据 `post-validation-1794639012547739000.json`：当前public版本单行20261114，UUID迁移库0、测试客户端0、tenant登记0、tenant schema0，应用哨兵哈希与基线相同。本轮容器、卷、qms_test、初始测试库、哨兵和私有凭据保留用于PR迭代，未执行删除；不套用只绑定旧资源的R4b清理器。

**R4B-CLEANUP-01继续延期**：原测试容器/卷、诊断容器、凭据及daemon bind身份阻塞全部保留，未用于本轮测试；见[延期清理清单](capa-d4-local-text-delivery.md#保留资源与后续清理入口)。功能签收与资源清理仍分开，T11保持“功能验收完成，清理待办”。

发布前再次fetch确认origin/main仍为5b712d94，远端同名集成分支未占用。本地独立规格、质量复核均通过，包括真实迁移暴露的单head回退修正再复核。接下来只普通推送独立分支、创建面向main的草稿PR，并在PR跟踪实际自动CI；最终合并由用户决定。
