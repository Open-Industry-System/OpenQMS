# 慢 fixture 优化：租户重建 setup

2026-11-16，独立分支 `codex/slow-fixture-optimization`，起点为已合并 CI 基线的 `origin/main=193746abb7c1eb9d196ef3997b6b91767490e3d1`。main 合并保护配置在另一独立分支，不与本批混合。

## 测量范围

PR #36 的远端后端执行为70分05秒，5269 passed /4 skipped /19 deselected；pytest collection 9.55秒、execution 4114.31秒、setup累计2496.15秒。合并后的 main push [run43732857321](https://github.com/Open-Industry-System/OpenQMS/actions/runs/43732857321) 也已成功。setup 总量用于选择调查方向，不能直接归因于某个 fixture。

本轮针对已有慢用例集中的 `test_test_tenant_rebuild.py` 与 `test_tenant_migrator.py`，实际运行同一组74项，无 skip/deselection/xfail。通过现有 `run_pytest_layer` 的诊断 pytest entry 加入只读计时插件；沿用 bootstrap、固定 marker、gate_results、JUnit/收据及失败退出码。插件只观察这一次 fixture setup 和 test report，不重复收集或执行。fixture 时间统计实际执行次数（不计命中缓存的重复请求）、累计/均值/最大值；常规静态 fixture 依赖已在 setup hook 前解析，动态 fixture 请求可能产生包含关系，因此不将各 fixture 数字解释为严格互斥 CPU 成本。

本地 macOS/arm64、既有 Python3.11.15/pytest9.0.3、同一缓存 PG15 镜像与本任务独占容器/随机回环端口；原配置与优化配置顺序执行。依赖已安装，未安装或测量 pip 冷/热缓存；操作系统/数据库缓存未做清空控制。以下是本地源码前后对照，不是同一 Git commit，也不是 Actions runner 对照，不能外推整套 CI 的收益。

## 按累计成本选择

| fixture | 次数 | 原累计秒 | 原均值秒 | 原最大秒 | 优化后累计秒 | 优化后均值秒 |
|---|---:|---:|---:|---:|---:|---:|
| sample | 29 | 53.4120 | 1.8418 | 1.9819 | 0.9876 | 0.0341 |
| rebuild_db | 30 | 48.5949 | 1.6198 | 1.7864 | 2.8609 | 0.0954 |
| rebuild_template（新增，共用只读源） | 1 | — | — | — | 4.3293 | 4.3293 |
| disposable_public_db（未改的对照模块） | 22 | 35.5990 | 1.6181 | 1.8769 | 34.7120 | 1.5778 |
| tenant_record（未改的对照模块） | 14 | 21.1769 | 1.5126 | 1.7162 | 20.8928 | 1.4923 |

本组最高累计项是 sample，包含真实租户迁移/校验/seed；其依赖 rebuild_db 为每项从空库执行 public upgrade head。优化针对这条重复 setup 链，未声称它是全套后端累计最高 fixture。原 `mig_db_url` 本组66次总计1.59秒，创建空库本身并非主要成本。

## 实现与隔离

仅重建测试模块使用新模板：从已核验的独占实例创建随机 `_test` 数据库，实际执行 public upgrade head 与 `provision_new` 的租户迁移/seed，然后关闭该源库的新连接。每项仍使用函数级独立克隆库和独立 NullPool engine；不共享可写 Session、事务或数据库。sample 从克隆加载新的 Tenant 对象，并深拷贝请求；discard_me 和 PUBLIC_KEEP 数据仍在每项实际写入。

没有修改生产代码、密码哈希成本、空库迁移 fixture、迁移专用测试、租户迁移链或迁移版本；不以 ORM create_all/stamp/public历史复制替代租户迁移。实际 rebuild/resume、故障注入、维护锁、schema parity、身份及清理断言均保持原样。模板只存在于当前 pytest module 生命周期，不持久化、不进入 pip 缓存。重建模块末尾不请求 sample 的 disposal 用例也使用这个基准克隆（多一个未使用的已初始化租户）；其原有事务与存储断言保持不变。

pure 模式在任何 Docker/数据库 I/O 前明确失败。`fixture_database` 每次核验登记实例与原测试库身份，只接受同一实例、本辅助工具命名的禁连接模板。SQL identifier 使用 psycopg 引用。finally 仅删除本上下文创建的随机数据库，失败路径相同；模板初始化后关闭并释放 engine，不终止共享库或其他任务客户端。既有 `mig_db_url` 原样保留。

## 同组前后结果

| 本地指标 | 原配置 | 优化配置 |
|---|---:|---:|
| 通过/失败/跳过/退出码 | 74 /0 /0 /0 | 74 /0 /0 /0 |
| 外层 wall（含准备、预检、子进程） | 262.91秒 | 166.97秒 |
| pytest 收据 elapsed | 261.47秒 | 165.49秒 |
| collection | 0.1803秒 | 0.1937秒 |
| execution loop | 256.95秒 | 161.45秒 |
| 重建模块 setup | 102.81秒 | 8.20秒 |
| 重建模块 call | 44.59秒 | 44.91秒 |
| 重建模块 teardown | 1.18秒 | 0.98秒 |
| 未改迁移模块 setup/call/teardown 合计 | 108.35秒 | 107.31秒 |

两次74项原测试均4项既有 warnings，所有原测试函数/参数/marker/断言 AST 相同。组级收益主要出现在 setup，而调用体与对照组接近；没有测量优化后完整后端、浏览器或远端 Actions，不将此差异转换为 PR 等待时间或全套节省比例。工作流、Makefile、测试层选择、pip 安装/版本校验及所有门禁保持不变。

新增回归实际提交 registry/schema/seed 污染，验证后续用例得到新数据库、原始租户/seed/请求；另覆盖可变模板拒绝和注入异常后的克隆清理。正序烟测4通过；全部74项原测试与4项新增回归反序执行78通过、无skip/失败、退出0；正常正式 runner CLI（默认 pytest bootstrap，无计时插件）43通过、退出0。独立故意失败探针实际1 failed、收据FAILED、CLI退出1，未把故障转成通过。最后增加pure提前拒绝，RED为1 failed，修正后全部CI基础设施纯测试351通过/3项既有warnings。1075文件的优化源码指纹在前后对照/反序验证期间一致；pure前置检查是此后唯一源码补充，并已在正式入口和纯测试验证。

本机私有证据：`/tmp/openqms-ci-followup/fixture-evidence/`，包括 before/after-profile.json、*-result.json、既有格式脱敏日志/收据、诊断 run.py 与源指纹。数据库环境与登记为0600；已核对零额外客户端及无残留fixture数据库，精确删除本任务容器和唯一匿名卷并回读不存在，删除凭据文件；仅保留非敏感证据。诊断脚本不作为新 CI 入口。

## 后续

先在独立 PR 的同类 runner 上复核该组 setup 与整套 backend 的计数、总耗时、缓存冷热及数据库清理，再决定是否扩大到其他重复准备；下一候选为本组未改的 disposable_public_db，但不能把有意验证空库迁移或旧 revision 的测试改成当前 head 模板。现有证据优先支持缩减 fixture 重复准备，暂不实施两个 PostgreSQL job、分片、选择性测试或减少覆盖。
