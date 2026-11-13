# CAPA D4 本地正文交付：来源与修订基础

## 当前范围（Task 2、Task 3 已签收）

Task 2 增加租户本地元数据表；Task 3 接续实现内部 FMEA 来源访问与根因字段修订，不提供正文交付、证明签发、插件来源授权、任务准入或新 API。运行时仍默认关闭；迁移成功不是启用许可，也不会创建任何 grant 或提升旧 metadata 能力。本文不提供尚未实现的启用命令。

## 迁移链

- public 新 head：`20261109_d4_text_delivery`，前驱为原双分支 no-op merge `20261102_agent_mainline_merge`。
- tenant 新 head：`tv007_d4_text_delivery`，前驱 `tv006_agent_read_tasks`。
- public/tenant 使用独立、手写自含且等价的增量 DDL；不从当前 ORM 动态生成、不以 `create_all` 替代迁移。
- `tv001` 至 `tv006`、业务快照、manifest 和其中冻结 public head 均保持字节不变。
- tenant 升级沿用原 owner-bound maintenance、同物理连接 session advisory lock、代际更新和全对象 parity；所有旧前驱仍受支持。`delivery_predecessor` 专指 `tv006`，既有 `predecessor`（`tv005`）等状态名不变。

## 六张表

| 表 | 内容与边界 |
|---|---|
| `capa_d4_root_cause_revisions` | CAPA 字段修订号、HMAC、操作者/时间/写入路径，无正文 |
| `capa_d4_root_cause_source_proofs` | 修订、验证版本、精确来源坐标与 HMAC、声明/历史状态；每个 report/revision 最多一个 active proof |
| `agent_restricted_projection_receipts` | 独立 restricted 投影回执元数据，无正文，不接入旧 internal 回执链 |
| `agent_plugin_derived_source_scopes` | 插件 grant 的精确派生来源旁表，不代表 ALL 或额外 FMEA 权限 |
| `agent_task_derived_source_scopes` | 任务 grant 的精确派生来源旁表，无独立 enabled 开关 |
| `agent_task_source_requests` | task 主键与不可变请求身份指纹，仅身份而非授权；本阶段无服务写入，后续任务才接入 blocked 请求记录 |

全部属于 `TenantBase`，无 `tenant_id`，未加入平台表或 parity 排除集合。新外键明确 `RESTRICT`，包括 proof 到实际 `capa_root_cause_verification.verification_id`；源 FMEA/节点不新增删除阻塞外键，`superseded_by` 仅保存历史 UUID，不自引用。时间字段均为 timezone-aware，普通新主键由 Python UUIDv4 生成（请求旁表复用 task 主键）。

## 内部来源访问与字段修订（Task 3）

FMEA 内部来源服务先刷新当前员工、角色、FMEA VIEW、工厂及产品线范围，仅查可见对象的标量坐标。无权、不可见或不存在统一拒绝，不读取节点。节点查询先检查唯一性和 64 KiB 预算，实际读取语句再次限制大小及唯一性；返回节点版本 HMAC，不返回整图。节点处理成功或失败后再次核验来源可见性，JSON 无法安全规范化时也返回固定拒绝。

根因修订元数据与实际字段变更在同一事务写入，helper 不提交事务：普通 CAPA 编辑及建议采纳沿用父行锁；审核发现创建新 CAPA 时记录初始修订。审核建单从实际 finding 和同厂关联 audit plan 继承工厂/产品线，工厂缺失、关联计划工厂不符或计划产品线为 NULL 时拒绝，不借默认产品线或客户端输入绕过约束。既有员工接口的权限、业务状态、审核与 outbox 流程保持。

每次实际文本变化产生新修订号和 UUID，同值更新不追加；A→B→A 不复用旧修订，即使字段 HMAC 再次相同。字段 HMAC 区分 NULL 和空串，绑定服务端类型化命名空间与报告 UUID：租户使用真实 tenant UUID，single/public 使用显式 `single_public` 标记。HMAC 不绑定可变的工厂、产品线或 generation；这些当前坐标由后续交付检查承担。`single_public` 不因此获得正文准入。

写入站点测试按文件、所属函数、AST 写入形态及数量维护白名单；同一文件新增写入口也必须显式复核。动态编辑另有业务行为测试。上述修订不是来源完整性证明、脱敏认证或任何插件授权；显式证明签发属于 Task 4，正文交付仍待后续任务。

## 回退与证据保留

两条新 migration 在任何 DROP 前逐表检查：六张表任意一张有记录即拒绝 downgrade，事务保留版本、六表、证据和旧记录。仅六表全空时允许沿既有历史链回退/重新升级。不自动删除证据，不提供清库或强制回退入口。

维护前提：tenant 必须使用既有 owner-bound 排他维护锁路径，正常业务事务遵守 shared advisory 锁；普通 public Alembic 不持该租户锁，只用于本片离线、无并发 writer 的受控维护。EXISTS 不是写排他锁，不提供在线 public 并发回退安全保证，也不认证生产回退。

## 验证边界

验收使用独占登记 PostgreSQL 15，串行 fixture 临时迁移库；不创建额外容器/卷，不连接业务实例，不调用 provider。焦点测试覆盖空库、两个旧 public 分支、原 merge、tenant empty 与 tv001–tv006 前向升级、全 parity、空回退重升及逐表非空拒绝回退。实际执行计数与首次失败修正记录见项目进度；这些结果不代替后续 Lead SPEC → QUALITY 或整片门禁。
