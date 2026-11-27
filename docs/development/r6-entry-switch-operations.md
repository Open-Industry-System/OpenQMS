# R6 入口切换与安全兼容操作说明

日期：2026-11-18（Asia/Shanghai；既有执行收据保留其原始 UTC 时间）。本文描述已实现接口与已登记的本地演练事实。用户环境尚未切换，正式目标与批准未提供；本文不授权发布、合并、部署或环境切换。完整执行账目见 [R6 台账](r6-entry-switch.md)，逐故事检查见 [R6 验证剧本](../user-stories/US-E2E-01-capa-8d-closed-loop/R6-verify.md)。缺必要证据保持 blocked，不能写“上线完成”。

## 本次冻结身份与实际进度

实际源码为 `be42580ab640e216253032931d35f70d9ce939d5`。用户已明确允许验收程序接受公共 HTTPS 域名的签名 IPv4 `198.18.0.0/15` DNS 映射；生产 TLS/SNI、当前 DNS 与批准 pins 一致性、当前权限及完整来源检查均未改。地址的实际 `is_global=false` 仍如实记录，不把它改写为公网地址。

本次新 main 报告 `d4a2b072-6918-4ba3-bcd4-0c83770eba95` 已完成原始真实 Terra C9：stock 1/1 PASS、314.81 秒、零跳过，正常员工复核后采纳建议一、正式更正、按同任务检查点撤回建议二，完成本地人工 D7/文档门禁、四个 NOT_EXECUTED 通道、正常审批及 PPT。实际 9 次模型请求与 18 条配对外发审计、2 条 D5 保存命令均保留；单独只读核验没有新增模型请求或重新导出。它是 `FRESH_SINGLE_PASS`，不是旧构建的 COMPOSED_PASS。

| 字段 | 本次实际冻结值 |
|---|---|
| 候选 / 关闭生成兼容 build | `83b68956ffabf531150e2135eb6e4cbe622e1cf2aa7adba10aa21491f747692d`；同安全核心、生成配置分别 true / false |
| 1188 运行文件摘要 | `9f076840c8e7dc29c4f03afe5d7e3c65df87041395174f0d7e20a0f71a05fb62` |
| 演练配置摘要 | `97fa790e312b6454f4eb47187e613a4091ae93df8c6a91958ed01e714f5d83cd` |
| 完整源码 / SDK / 工件清单 | `/private/tmp/openqms-r6-final-20261118/executed-source-manifest.json`，SHA-256 `2382ac23910049bb5761a246e461d29b9950792fec661775e76e03565a917a99`；1867 仓库项及 1309 外部项 |
| 候选 / 关闭生成环境文件摘要 | `8364e416f795ef984a6134df4b1e74abbad563aa5c92a6a876e47243f1e894ce` / `a48239ed810cef6ad59bc062184ea8e3737ce58eaf40b88960ef5a50e4c73926` |
| 实际 fresh C9 证据 | `c9-fresh-summary.json`，SHA-256 `e562b9dc408a5bd03f6b5c8cc726f0ec308ddf8219a02c1aa18c6bf6b8fcfcdb` |
| C9 同报告只读快照 | `c9-readonly-snapshot.json`，SHA-256 `7708f6bd97a28eb1d4f47c63881e2ce0db9ce86db84ac48bd29e85bb2d195b04` |

C10 同份新数据已完整通过：stock 21/21、54.70 秒，包含双模式真实 TCP 与 20 个故障用例；四组内部合同及启用来源探针实际执行 589 个用例，31 条语义覆盖均绑定本次源码、配置、JUnit/hooks 与实际 flag。全部必要节点零跳过及非通过。原始审计 62→候选 64→兼容 66，差量仅为精确匹配的安全退役入口审计；非审计业务数据及原审批/PPT 保持一致，模型新增调用为 0。独立合法 D5/健康 LOCAL 接收方另证明关闭生成返回精确 503，任务 2→2、外发审计 14→14、接收方新增调用 0。最终交接 `fresh-c9-c10-local-handoff.json` 的 SHA-256 为 `64f518646e65e9a19dab37146436e31ef38ebb89e2403df2961f45871c98689a`。完整 Task11 仍须最终独立 SPEC→fresh QUALITY 及本地文档提交；正式 release manifest、目标与批准仍是独立条件。

`policy.json` 是正常激活 profile 的运行副本：预付费冻结时等于不可变 D4 profile 文件，随后正常 C9 激活 D5 后等于不可变 D5 profile 文件。两份 per-profile 文件仍匹配原冻结摘要；历史预付费 hash 对应原 D4 不可变文件，不回写原收据。实际映射见 `active-policy-lifecycle.json`，SHA-256 `9d47d1ea498f1b2b0dd90fc75882f98e373c33dddeaa7d138d959702a48a450c`。

## 上一轮冻结候选：未通过资格

下表保留上一轮隔离演练的冻结事实。当时验收证据的公网地址限制拦下了该轮 C9。经独立模型和地址绑定 TLS 探测及用户授权，验收程序现允许签名清单中的 IPv4 198.18.0.0/15 映射地址。新 C9 和同报告 C10 按本次冻结版本另行记录。

| 字段 | 上一轮实际冻结值 |
|---|---|
| 实际源码 | `a80467e4fb61c7b12da5e1ac70cb1b0e89227f18` |
| 候选 / 关闭生成兼容 build | `b0dd56cbbbe588718365c689b65c110d0e05470f2b8873659c00b63d1c837f7f`；同安全核心，生成配置分别 true / false |
| 1188 运行文件摘要 | `9f076840c8e7dc29c4f03afe5d7e3c65df87041395174f0d7e20a0f71a05fb62` |
| 当前演练配置摘要 | `f3c1859a657f7ed2485df961b18766cd83c21c3d4064897121da6c94c2ee9f5a` |
| 实际完整源码 / SDK / 工件清单 | `/private/tmp/openqms-r6-c11-requal-v8/executed-source-manifest.json`，SHA-256 `24200b478c1549294a020e049ca0cbbb39e9b7703ee05048346dd5de466e5aba`；1867 仓库项及 1309 外部项 |
| 预付费资格状态 | `final-prepaid-freeze-v2.json`，SHA-256 `ed82c6e5f98983f00235cbcf89a17386ac2ede50b41fdd7dcdda9cf22596349b`；HOLD、provider calls 0 |

## 历史通过身份与当前重验状态

下表仅为 Task10 历史通过源码 `027d3e97e41054d4d7f05ed336f7a17a9a1a0b54` 及 Task9 `03180f4f71663381987b0e519c65768a76536221` 的原构建。Task11 首轮全量暴露的过期 ORM 入参回归已通过元数据 identity 恢复修复；旧源码、清单、环境、pins、报告及所有失败收据保留，不能用旧通过为新构建签收。

`4c231fb5024a7cac6ebbbf656d5c13798f97653c` 的完整 `make check` 已实际 exit0：SDK 604/17/1，普通 API 6007 通过及 4 个明确普通环境跳过，原生 68/68。后续仅浏览器测试契约修复后，`a80467e4fb61c7b12da5e1ac70cb1b0e89227f18` 完整 `make check-browser` 14/14 + 2/2、全量 Vitest 107 文件/967 测试、E2E TypeScript、新增 R6 定向 API 535/535、native/process 103/103、更新剧本 Chrome 3/3 均实际通过；定向层逐项核对 expanded 选集/JUnit/hooks，每节点恰一次通过且零缺失/额外/非通过。原始失败及修复的独立复审仍见台账。

本次 `be42580ab640e216253032931d35f70d9ce939d5` 只改验收证据 helper 与其测试；实际重跑 99 个受影响证据测试和 5 个 manifest 测试通过，应用/SDK/浏览器运行文件未变。新增 7 个普通用例后，不声称当前全树或普通选集总数与旧源码相等；旧完整父命令仅以已核定未变依赖闭包、原 SHA 及原命令收据保留。新真实 C9 已单次原始通过，同报告新 C10 已完整通过；最终独立复审及本地交接仍是签收条件。

| 字段 | 历史实际演练身份 |
|---|---|
| 原登记源码 | `c6b0a2cdff8c53bd7b6cb6fa2d8ccb9924f22220`；不可把后续 Git SHA 反写原收据 |
| 候选/安全兼容 build | 两者均 `2995115728be2af133aa694aa6c37b56a844f838c0e1cf7f1b29c6194bc03b09`；同安全核心、精确配置不同 |
| 1188 运行文件摘要 | `74fc2b2f75005b0c4e25a15f48e4ad63264f81bafcd7769da38bca58b0b1b60e` |
| 已执行配置摘要 | `672e4eef5836924d67f4651e03fa0fb7d8d54a45cac76040e29898eed3aa430a` |
| public / tenant head | `20261116_r6_local_capa_sources` / `tv024_r6_local_capa_sources` |
| 1200 项实际执行清单 | `/private/tmp/openqms-r6-c9/final2/executed-source-manifest.json`，SHA-256 `fd3c31c230c70995a738dd8a0fdd8848c6b1e8dde223d4fc3fe50c3ddf70f072` |
| 候选环境文件摘要 | `53aded928213cf14176a8053ca5c9389a111dad008f7538810466cf5427badc2` |
| 关闭生成兼容环境文件摘要 | `456d9f05c4884707572b6f4cbcdc7a77924a0916147c78c757facc32adaed7db` |

环境文件只在原 owner-only 目录读取，禁止输出/复制凭据。build/config/环境文件各自摘要不可混用。C10 补强 checker、兼容测试、manifest 测试的三文件冻结另见 `task10-source-freeze-v4.json`，摘要 `bdc705f817f2a2fbd1c6fdb50ce1ad75e522dc140ff929adf9b2480a870ceacd`。该历史候选事实为 `/private/tmp/openqms-r6-c9/task10-release-candidate-facts-v2.json`，摘要 `582f632a59301d83e483351cd3f9144c617fef7cc31ac70d1452ec35fedc7f39`；这是演练事实，不是 `release_manifest`，其当时 pending-review 状态不追写，后续审阅记录另存。

新候选须满足的安全兼容合同：保留完整来源、D4 正式继承、D5 正式更正及原始采纳/历史、当前权限读保护、材料版本、旧 API 退役屏障和安全人工维护。原 R5、旧 main 或缺任一上述能力的构建均不是正常回退目标。数据库不降级，不重写已发布 public20–24/tenant 历史，不删除来源、审批或措施记录。

## 操作者、条件与顺序

操作者必须是平台信任登记中允许的员工 UUID，且持有针对精确目标的独立授权文书；普通浏览器管理员、环境开关或命令参数不能构造平台信任。权威配置通过 `R6_SWITCH_AUTHORITY_FILE` / `R6_SWITCH_AUTHORITY_KEY` 解析，实例核验还绑定启动 PID、启动时间、可执行文件、配置与来源摘要；禁止输出密钥。正式发布额外要求匹配批准人及独立 release authorization，不用演练输入替代。

以下在仓库根目录运行，只展示命令形态；`R6_PYTHON` 必须显式选择与权威登记固定可执行文件及摘要一致的已核验解释器。下例是本轮本地解释器，未来目标须使用其独立登记的可信路径；参数必须来自已登记目标，不要把本地演练 UUID/目录拿到用户环境执行。

```bash
R6_PYTHON=/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python
"$R6_PYTHON" backend/scripts/r6-entry-switch.py status --tenant "$R6_TENANT"
"$R6_PYTHON" backend/scripts/r6-entry-switch.py close --tenant "$R6_TENANT" \
  --actor "$R6_ACTOR" --operation "$R6_OPERATION" --document "$R6_DOCUMENT"
"$R6_PYTHON" backend/scripts/r6-entry-switch.py finish --tenant "$R6_TENANT" \
  --actor "$R6_ACTOR" --operation "$R6_OPERATION" --document "$R6_DOCUMENT" --timeout-ms 5000
"$R6_PYTHON" backend/scripts/r6-entry-switch.py status --tenant "$R6_TENANT"
```

1. 先只读核验精确数据库系统身份、租户/schema/generation、owner、schema heads、候选与兼容工件、授权文书、实际 server/worker inventory 和现有状态；确认必要证据已通过且仍匹配源码。演练目的为 `r6-rehearsal.v1`，正式为 `r6-release.v1`；exercise UUID 与带时区有效期不可缺或混用。
2. `close` 先在独立短事务持久关闭旧推荐写准入，追加 draining epoch；不能等排空后才关闭。此时新旧页面不得重新接收旧推荐写入。
3. 按登记 inventory 识别并排空旧实例/worker，保留每个已准入事务的见证。未知提交必须核对实际提交/回滚、操作键与原子审计；不能盲重试或把进程退出等同回滚。只控制确切自有实例，不杀未知 PID。
4. `finish` 在排他屏障内等待已准入事务结束，核对结果及原子审计，并重新核验当前权威、文书有效期和实例清单，全部确定后才追加 switched 和 T。超时 exit2、拒绝 exit1 均保持已持久 draining；命令 exit0 后仍用 `status` 核对同 operation/epoch 及材料。
5. 接续沿用原 operation，核对账本后只精确重放原键及原 body。文书过期不自动延长：在同目标/操作/exercise、原文书 digest 与实际 closed epoch 下取得新有效期并重新登记，再显式执行 `renew`，追加 draining epoch，随后 `finish`。不重置账本或创建新操作绕过旧状态。

```bash
"$R6_PYTHON" backend/scripts/r6-entry-switch.py renew --tenant "$R6_TENANT" \
  --actor "$R6_ACTOR" --operation "$R6_OPERATION" --document "$R6_RENEWED_DOCUMENT"
```

原 C9 演练文书摘要 `6461ef97bc24da0143a84a743e39e4a40fe2d8d20a04c5dd2e11945483569980` 与实际接受的续期摘要 `75fdbc4875f0d6ee0a68903b9d4d64f79d5aa6bbe0fece14496fa2e5fedf0511` 分别保存；提议文书/登记不能替代真实 renew/finish/status 收据。

## 故障与兼容操作

任务运行与受控执行总开关默认 false；`R6_GENERATION_ENABLED` 自身默认 true，只有全部固定安装、模型部署、当前权限/来源和工件准入同时满足才生效。异常时将已批准精确兼容配置的 `R6_GENERATION_ENABLED=false`，按登记的受信部署流程替换受影响实例并核对新 PID/配置。本文不授权在用户环境执行此替换。

关闭生成不改变 switched 状态，不恢复旧 D4/D5 推荐、草稿、采纳入口，也不删除或改写原任务/候选/建议。保留当前权限下的历史、来源、审核/PPT、安全人工正文及正式措施更正；人工写仍校验材料版本和 entry epoch，终态仍冻结，来源不完整仍拒绝。禁止通过放宽 ACL、补假证明、改模型 DNS pins、重开结案报告或降级数据库来让检查变绿。待审建议可逐项撤回；已采纳措施只能经正式版本化更正，二者不能互换。

历史 C10 原主模型 DNS 与不可变 pins 不一致时，资格校验先 403 的失败收据保留；这不证明生成开关 503。旧 `a80467e4` / owner751928 演练又曾因额外 global 验收限制 HOLD，诊断当时如实记录 `198.18.14.88`、未发真实请求。两者均不回写为新成功。

用户授权后的 `be42580` 仅调整额外证据地址分类，保留 TLS/SNI、DNS-pins、来源及权限，接受签名的公共 HTTPS 域名 IPv4 198.18/15 映射而继续拒绝其他非 global 地址。本次采用新的正常登记部署、配置和隔离报告，真实 C9 已通过；同份新数据 C10 不新增真实模型调用、不重开结案或重新导出。未来目标环境若需新生成，仍须按正常流程新建获批并重新资格核验的部署、复核完整来源及实际接收方；不得修改历史部署的 pins、策略或证书来制造通过。

## 最终签收与仍需独立授权的事项

C6/6B/7/8、C9、C10 与 C11 收据必须精确引用并验证摘要、源等价与当前文档版本。C11 必须完整父命令 exit0、所有必要原生节点真实运行且零跳过，不能用中断分组、平台 skip 或旧结果拼接为新通过。阻塞发现为零并完成独立 SPEC→fresh QUALITY 后，才交接本地实现；正式目标、批准及生产启用依旧分开。

本轮只读元数据复核的远端 main 为 `e8b91f1bb7ac0b4a9bdacbac464af1e9d1a42ded`，较先前记录 `e4bc51f9f528c2b28da3366c1bfe1fe0b0adf86e` 前进 9 commits / 19 files：增量为 CAPA 文档门禁测试/锁 helper、剪枝文档及 CI/预览人工验收基础设施，没有生产 backend/frontend/SDK/迁移变更；这不代表组合树已验证。本分支未合并/rebase，后续还须完成 PR40 引入的受信预览人工验收及组合回归，不能记为本次已执行。未来合并其 `20261116_security_main_merge` / `platform_login_limits` 与 R6 public head 必须追加 merge revision，tenant024 不改；权限空范围拒绝、创建/认证/会话、附件等需重新组合回归。实际远端原生 CI 是 main-only workflow_dispatch、自托管 macOS/openqms-r5-sandbox、冻结 GITHUB_SHA；本地旧 lane 源码与本地结果不能代表最新 main 或远端 CI 验证。本轮没有 R6 push、远端 CI、合并、部署或用户环境切换。

C11 的必要前端门禁为全量 Vitest、普通/E2E 类型与构建；全仓 lint 未作为本轮必要命令重新执行。Task8 在未改文件中的四项历史 lint 错误仍单列保留，不能把必要 R6 门禁通过写成全仓 lint、无关积压或远端 CI 已全绿。
