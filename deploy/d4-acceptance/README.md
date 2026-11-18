# D4 浏览器入口

本入口部署在受信 HTTPS 域名。它为一次发放展示合成报告标识和两项固定操作，浏览器向 `/scenario/d4-deliver` 或 `/scenario/d4-revoke` 发送空 POST。只能用本轮专用账号登录。入口拒绝跨来源操作、超期发放及身份不一致的回执。缺少执行器或真实回执时显示「受阻」。

服务实例通过受保护的独立配置文件绑定 PR、head、merge、计划、测试位、合成报告和起止时间。配置文件归服务用户所有，权限为 `0600`。它包含独立的 `username`、16 字节十六进制 `salt`、以 scrypt 参数 `n=16384,r=8,p=1` 生成的十六进制 `password_digest`、`origin`、`executor_socket` 和 `report_label`。在 `binding` 中填写 `pr`、`head`、`merge`、`plan`、`lease`、`report_id`、整数 Unix 秒 `issued_at` 和 `expires_at`。单轮最长一小时。使用与候选应用不同的独立登录凭据。

部署入口的调用形式：

```bash
python3 deploy/d4-acceptance/browser.py \
  --config "$D4_ACCEPTANCE_CONFIG" --port 8444 \
  --cert "$D4_ACCEPTANCE_TLS_CERT" --key "$D4_ACCEPTANCE_TLS_KEY"
```

服务绑定回环地址，由受信网关提供入口。执行器通过 root 所有的专用 Unix socket 提供服务，其父目录不得允许普通组成员修改。连接关闭写侧后，入口读取一份 JSON。请求含 `binding`、固定 `scenario` 和本次 `operation`。执行器必须独立复核当前版本、发放和报告，运行受审固定 receiver 场景，并从平台侧读取实际记录。响应只回显请求三项及 `task_id`、`run_id`、`delivery_before`、`delivery_after`、`denial`。正常交付要求数量加一。撤权要求 `denial=source_revoked` 且数量不变。正文、口令和安装 secret 不进入响应。

浏览器入口和测试夹具已可运行。专用 Linux 执行器、真实业务回执提交以及 Oracle 启用尚待接线和审批。夹具不会写共享队列签收。参见 [Oracle 共享测试接入](../../docs/shared-test-queue.md)。
