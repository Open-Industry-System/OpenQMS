# 后端 CI 优化与验收记录

本次从 main `051d4b0663008179bd9a74683446f465164e9e0a` 建立独立 worktree，连续实施慢测试准备、双分片和前端展示快路径。原工作区已有改动保持原样。保留主线已有 fixture 模板、marker、必选真实进程用例、文档快路径、main push 和连续提交取消规则。

## 三步实现

1. [慢测试测量与覆盖映射](backend-slow-tests-2026-11-19.md)：复用只读租户准备，每项测试独立克隆数据库，纯规则在无网络快速层执行。原始断言、真实事务与进程覆盖及新增辅助代码均计入报告。
2. [完整后端双分片](backend-parallel-ci.md)：每组独立 PostgreSQL 和收据，`backend-tests` 核对两组实际执行清单并保留原发布收据接口。
3. [文档与前端展示快路径](backend-docs-fast-path.md)：使用可信 base 中的分类器检查完整 PR 差异，合法跳过在分类摘要和最终门禁中显示理由，前端与浏览器门禁继续执行。

## 本地统一验收（2026-11-19）

本机为 macOS / arm64、Python 3.11.15，同一现有 venv；两侧 PG15 镜像 ID 相同、没有额外 CPU / 内存限额，宿主负载未独占。以下均为本地实测。

| 步骤 | 结果与前后对照 |
| --- | --- |
| 慢测试 | 原 165 个逻辑场景两侧均全部 passed，无 skip；runner 959.32 → 481.29 秒，setup / call / teardown 为 769.117 / 102.903 / 76.096 → 328.182 / 97.159 / 46.697 秒。tenant provision / migration / seed 各 163 → 2 次；业务准备仍每项独立。Python 物理行数 2902 → 3092，原 344 条断言保持。 |
| 双分片 | 正常插件完整收集 5843 项，runtime 997 + remainder 4846，交集 0；实际执行收据的完整集合及并集也与独立收集逐节点一致。全量为 5838 passed / 5 skipped / 0 failed / 0 errors，72 个必选节点全部实际 passed。 |
| 前端快路径 | 原策略中纯样式、展示文案需完整后端；新策略仅对明确允许的既存首页样式值、3 个展示文案字段跳过两片，并显示原因。分类 93 项通过，包含混合改动、重命名、删除、分类失败等反例。远端 PR 等待变化待验证。 |

| 双分片本地阶段 | 实测 |
| --- | ---: |
| runtime：Make 前置及 pytest | 2112.20 秒（35 分 12 秒） |
| remainder：Make 前置、pytest、手工脚本、D8、8 个引擎导入 | 2299.86 秒（38 分 20 秒） |
| 两组启动至汇总验证完成 | 2300.25 秒（38 分 20 秒） |
| 两组及汇总测试进程分钟之和 | 73.54 |
| 汇总校验活动耗时 | 0.09 秒 |

这是共享宿主上的测试进程墙钟，不含 checkout、pip 安装、容器启动或 GitHub 排队，**不是 GitHub runner 分钟**。未运行相同候选的串行完整套件，不能用这组数值计算完整后端的提速或计算成本变化，也不能与下表远端 89 分钟直接相减。单轮 A/B 的约 49.83% 改善仅适用于第一步的相同 165 场景。

runtime 在目录前缀之外接收两个整模块：`test_d4_recovery_checkpoint.py` 与 `test_r4b_main_merge_guards.py`。按成功 A/B 各模块比例加权主线阶段计时，初始估算两组阶段累计为 2315.39 / 2309.07 秒；该估算只用于分组。实际本地两组相差 187.66 秒，较长组比另一组约长 8.9%。

其他证据：禁网络 / 禁数据库的 CI、runner 与合同组 554 passed；调平后专项 73 passed；Oracle automation 242 passed，另 16 subtests passed。手工 schema / SPC、D8 preflight 与 8 个引擎导入均 exit 0。独立审查确认汇总只需标准库，兼容现有 Oracle API 收据消费方。

全量 5 项 skip 中，PG15 快照重建因本机没有 `pg_dump` 跳过；随后通过登记的本轮 PG15 容器工具、同一源码和 runner 单独补跑 **1 passed / 0 skipped，5.58 秒**。其余 4 项为既有 Redis 不可用及 3 项未启用 E2E_MODE。保留原全量 5 项 skip 收据及补跑收据，不覆盖原记录。前端类型、构建及浏览器 job 的接线与门禁已核对，本轮未重复执行这些未修改的前端门禁。

源码、实际收据、独立集合证明及全部失败 / 中断样本保存在本机私有验收目录；完整执行前后受检源码指纹未变。6 个本轮专属 PG 容器及 6 个卷已在身份、独占挂载和零活动客户端核对后删除并回读确认，临时凭据文件已删除。开发指南现有 5 个路径检查诊断在冻结 main 上同样存在；新增 CI 文档与链接另行通过检查。

## 已观察的远端基线

[Actions 44445156751](https://github.com/Open-Industry-System/OpenQMS/actions/runs/44445156751) 与上述 main SHA 相同。以下是 GitHub Jobs API 和安全模块计时日志的实测，非新实现的结果。

| 指标 | 主线单组基线 |
| --- | ---: |
| pytest 选中 / 通过 / 跳过 | 5,709 / 5,705 / 4 |
| pytest 收据耗时 | 5,276.99 秒 |
| backend-full job | 5,338 秒（88.97 分钟） |
| workflow 开始至 backend-tests 完成 | 5,356 秒（89.27 分钟） |
| backend-route 开始至 backend-tests 完成 | 5,353 秒 |
| 后端 runner 分钟（route + worker + gate） | 89.12 |
| 整个工作流 runner 分钟 | 104.32 |
| Agent runtime 模块阶段累计 | 2,650.79 秒，其中 setup 2,170.94 秒 |
| 其余后端模块阶段累计 | 2,573.98 秒 |
| 四个目标文件 | 165 项，阶段累计 1,195.40 秒，其中 setup 977.16 秒 |

阶段累计不等于 job 耗时；job 还包含依赖、收集、迁移、wheel 和上传等工作。runner 分钟按实际 job 区间求和，排除没有分配 runner 的 skipped job，不包含计费取整。

## 远端对照方法

本实现于 2026-11-20 按用户授权进入 PR 交付，双分片各自耗时、员工实际等待、runner 总分钟及快路径节省均为**待 GitHub Actions 验证**。本地 macOS / arm64、Python 3.11、PG15 的测试不能换算为 Linux x64 / Python 3.12 的 CI 提速比例。

在同一候选提交、相同 runner 标签与资源配置上取得完整运行后，用以下只读命令计算；失败或取消的结果也保留 conclusion，不能作为成功性能样本。

```sh
REPO=Open-Industry-System/OpenQMS
RUN=填入运行编号
gh api "repos/$REPO/actions/runs/$RUN/jobs" --paginate --slurp > jobs.json
gh api "repos/$REPO/actions/runs/$RUN" > run.json
python scripts/ci/backend_metrics.py jobs.json --run-json run.json
```

输出同时给出两个 worker 的实际区间、workflow 开始到最终门禁的等待、后端与整个工作流的 runner 分钟。比较单组与双组时使用同一测试集合，并列出 pip 缓存、重复迁移、两组收集及产物验证成本。并行可能缩短等待，同时增加 runner 分钟，二者分别评估。
