# 文档与低风险前端 PR 的后端检查

面向 main 的 PR 满足以下任一范围时，可以跳过带 PostgreSQL 的后端分片。`backend-tests` 仍报告分类理由；前端检查、浏览器检查及其他必需检查照常执行。

- 文档：根目录 `README.md`、`README_EN.md`、`PROGRESS.md`，或 `docs/superpowers/specs/`、`docs/superpowers/plans/` 的直接 Markdown 文件。文档可以添加、删除或在允许路径之间重命名。
- 纯样式：仅修改已有 `frontend/src/pages/public/PublicHomePage.css` 的有限声明值。允许既存不透明颜色、有界数值间距和非零字体值替换；透明色、零字号和超出范围的间距不放行。选择器、属性名、声明结构、媒体规则、URL、显示/定位/可见性、内容和其他 CSS 代码必须完全相同。
- 展示文案：仅修改已有 `frontend/src/locales/zh-CN/home.json` 或 `frontend/src/locales/en-US/home.json` 的 `hero.eyebrow`、`hero.title`、`footer.tagline` 字符串。这三项只在公共首页以普通文本展示，不控制业务行为。JSON 的其他值、键、类型和数组结构必须相同；新旧字符串均须为 1–240 字符的非空普通文本，不能引入插值、嵌套翻译、HTML 或控制字符。

上述文档与展示资源可以组合。前端资源添加、删除、重命名、符号链接或可执行模式变化均执行完整后端。规则不按 `.tsx`、`.css`、`.json` 扩展名通用放行；普通组件、权限、API、业务配置及其文案、数据库、依赖、CI、测试配置、未知路径和混合改动都执行完整后端。公共首页其他字段（例如演示入口、导航、权限说明、架构和业务能力）也不在文案快路径内。

分类使用 **PR 基线提交中的策略**，从唯一共同祖先到 PR head 读取完整差异，检查重命名两端、两侧 Git 文件类型，并读取两侧已提交资源内容。PR 不能通过修改自己的分类器扩大快路径。历史不完整、内容无法解析或分类失败时请求完整验证，最终检查保留分类失败状态。

新策略输出 `backend_required=true/false` 与 `route_reason`；`docs_only` 保持兼容，只在纯文档改动时为 `true`。合法跳过理由为 `allowlisted_markdown_only`、`presentation_styles_only`、`presentation_text_only`、`presentation_only` 或 `docs_and_presentation_only`。旧基线没有 `backend_required` 时执行完整后端，不能根据旧 `docs_only` 推断允许跳过。

main 推送始终执行完整后端。Oracle 自动部署和预览部署同时启用时，PR 也执行完整后端，以提供发布所需的真实 API 测试收据。只有分类成功、明确允许跳过且理由有效时，最终门禁才认可分片未启动；完整路线仍要求两片实际成功及其真实收据。更新规则后，需触发使用新基线的 PR 运行才能验证线上效果。

本地分类回归使用真实 Git 提交，覆盖样式、两种语言文案、文档组合、混合后端/权限/API/依赖/配置、重命名/删除、文件模式、共同祖先、解析错误与显式跳过输出：

```sh
backend/.venv/bin/python scripts/check-ci-pure.py --pyargs tests.ci.test_backend_fast_path -q
```

[工作流](../../.github/workflows/test.yml) · [分类器](../../scripts/ci/backend_route.py) · [分类回归测试](../../backend/tests/ci/test_backend_fast_path.py)
