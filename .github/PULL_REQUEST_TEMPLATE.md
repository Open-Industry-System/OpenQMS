## 改动说明

说明本次修改解决的问题。

<!-- preview-test-plan:start -->
### 影响范围
<!-- openqms-preview-fixture: none -->
<!-- 需要专项测试数据时，将上一行的 none 改为 required，并提交 backend/app/preview_fixtures/pr_<PR编号>.py。验收步骤注明样本名称。 -->
请填写：受影响的页面、角色、业务流程及不涉及的范围。

### 验收步骤
<!-- 对需要直达页面的非 D4 项目，可在本节填写检查点声明，见下方说明。 -->
| 编号 | 检查项 | 环境 | 角色 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| 请填写 | 请填写 | 请填写 | 请填写 | 请填写 | 请填写 | 请填写 |

### 权限与回归
请填写：权限拒绝、边界/异常和已有功能的回归检查；不适用时说明具体原因。
<!-- preview-test-plan:end -->

## 人工预览验收

每个编号使用唯一的小写短标识。只读使用 `public / viewer / read-only`，合成业务操作使用 `shared / field_qe 或 manager / write`。D4 正文和撤权分别使用 `d4-deliver`、`d4-revoke`。共享部署按声明准备专用任务、执行器和网页。共享测试按编号填结果，例如 `report-read: 通过`。

需要直达业务页面时，在验收步骤一节按项目编号添加 `<!-- openqms-preview-checkpoint: report-read /capa -->`。写入所需的预置状态由本 PR 的专项种子创建，并在验收步骤中写明如何找到样本。

CI 通过并发布预览后，在实际环境逐项执行上面的步骤。从 PR 下“测试环境已就绪”的自动评论（或 `PR preview acceptance` 工作流 Summary）复制绑定本次提交、部署和计划的 `/preview-accept` 命令，作为 PR 评论提交，并附实际结果/截图链接。机器人不能代替人工确认；新提交或修改验收计划后须重新确认。
