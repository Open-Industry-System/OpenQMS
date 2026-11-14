# D4 固定接收器 T5 交接

本页只描述独立标准库接收器和启动器。不是 T6–T10 服务端准入或业务授权验收；不改变旧 SDK、元数据 worker 或生产可信集合。

## 执行合同

`backend/examples/readonly_d4_text_receiver.py` 同文件定义固定六步：claim → capabilities → messages/claim(limit=1) → capa/d4/root-cause-text → messages/ack(实际 batch/sequence) → finish(completed)。没有重试、续租、历史查询、远程 finally-finish、任意 URL 或模型调用。非固定启动消息在第三步结束；正文未获完整确认不 ACK；finish 开始发送后未获完整有效确认只报告 unknown。

CLI：

```sh
python -I -S -B backend/scripts/agent_d4_text_local.py \
  --config /absolute/private-directory/config.json \
  --worker-sha256 <reviewed-worker-sha256>
```

配置恰含 `origin/tenant_slug/installation_id/secret/request_key/expected_report_id` 六字段。目录 owner/0700，文件 owner/0600/单硬链接/普通文件；拒绝路径符号链接，使用 pinned directory fd 和 O_NOFOLLOW 打开。不得把配置或秘密放进命令行。origin 仅 http(s) 数字 127.0.0.1 或 [::1]，无路径、userinfo、query、fragment。启动器只执行固定文件的已核 hash 字节快照，副本在0700私有目录内且0600；子进程 `-I -S -B`、repo外cwd、私有HOME/TMPDIR，仅必要JSON经stdin。POSIX new session/进程组在正常、异常、超时、leader提前退出后均 TERM/grace/KILL/wait；会话上限60秒，清理宽限另0.2秒。不声称防恶意setsid逃逸或OS sandbox。

stdout 仅固定状态、字段计数和已确认完成时的受限收据ID，不显示正文、token、安装secret、未知响应字段。失败或 close 不释放服务器租约；操作者应通过正常任务控制 API cancel/pause，重新交付须正常新建或重启。unconfirmed/unknown 不表示服务器未创建收据或未发送字节，也不能推断远端终态。Python内存不承诺安全擦除。

## SDK 源码参照与刻意收窄

参照 `sdk/python/src/openqms_agent_sdk/_transport.py`、`_codec.py`、`tests/unit/test_transport.py`、`tests/unit/test_finish.py` 以及 `tests/loopback/test_deadline_http.py`。这些文件未修改；接收器没有运行时 SDK/app/provider import。

| 方面 | SDK参照 | 本接收器 |
|---|---|---|
| 操作/目标 | 10操作，通用配置/查询编码，带DNS resolver | 仅六固定路由；只数字127.0.0.1/::1；没有resolver、任意query或报告URL |
| Deadline | 配置期限，raw-read wrapper与partial send共享剩余预算 | 固定10秒，编码前启动；connect/TLS/send/recv/JSON/schema/绑定/close后最终返回逐次检查；body视图验证仍检查原deadline |
| 缓冲/生命周期 | HTTPConnection + HTTPResponse，makefile IO ref保活 | 自有有界RawReader直接recv；TLS socket在解析完毕前持有并最终close，无makefile/ref提前释放路径 |
| 头部 | stdlib头行数量/长度 + 自定义trailer上限 | status行4KiB；头部总32KiB、最多100项；拒绝重复header、非法名称/折行；trailer另相同上限 |
| Framing | 严格chunk扩展/CRLF，TE尾OWS规范化；允许EOF定界与100 interim | 规范化TE OWS；拒绝TE+CL、重复/列表CL；必须单CL或单chunked；拒绝EOF定界和interim，chunk行4KiB、size最多16hex；trailer不能覆盖framing/type/encoding |
| 预算 | request1MiB，默认response4MiB可配置 | 固定request64KiB包含编码后头部+body；response256KiB；分块累计与CL预检；无压缩解码 |
| DTO | SDK十操作不可变视图 | 仅固定六操作视图；正文全安全标签、strict bool/str/整数、canonical UUID、aware时间、opaque digest、四项绑定；unknown非安全字段丢弃 |
| Finish | 400/401/403/404/409/410/422明确拒绝；其余不确定 | 同名单；3xx/5xx/429/格式/预算/断连/晚decode/最终超时均unknown；只允许一次finish尝试 |

TLS仍使用`ssl.create_default_context()`，验证证书与主机名；真实TLS测试仅将fixture自签IP SAN证书作为测试信任根，不修改生产TLS策略。HTTP拒绝只报告rejected，不推断任务failed/completed。

## 测试与证据

独立测试故意用 `--noconftest` 不加载backend/app、DB或全局环境；这是T5源码协议验证，不能代替T10正常策略真实API集成。测试服务器只绑定fixture自有随机数字回环端口；OS sandbox最初拒绝bind，已通过正式require_escalated执行同一测试；没有外部DNS、数据库、共享服务或真实模型。

```sh
/Users/sam/Documents/Code/OpenQMS/backend/.venv/bin/python -B -m pytest \
  --noconftest -o addopts='' backend/tests/cli/test_d4_text_receiver.py \
  backend/tests/cli/test_d4_text_launcher.py -q --tb=short
```

覆盖SDK慢滴八阶段、TE尾OWS、CL/TE歧义、分块分隔符/扩展/trailer、头数量、精确256KiB与+1、部分发送、TLS原始IO、JSON重复键/NaN/UTF8、晚decode/close最终deadline、所有正文安全标签/绑定、实际ACK水位、一次finish、不确定结果、未知字段与repr、真实隔离CLI和自有进程组清理。

过程保留：初始缺文件assertion RED；首批fixture导入缺文件是setup errors不当作行为RED；最终返回deadline反例1 failed后修复；finish 302/500/429反例3 failed/1 passed后修复；macOS真实cwd路径别名和OS注入`__CF_USER_TEXT_ENCODING`测试预期已核实调整。启动环境显式只传HOME/TMPDIR，CPython/OS可能增加LC_CTYPE和上述平台变量；无父环境凭据传递。

最终测试计数/hash由父级独立复核后登记，T5未提交、未勾选，也未进入T6。
