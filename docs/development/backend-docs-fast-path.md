# 纯文档 PR 的后端检查

面向 main 的 PR 如果只修改根目录的 README.md、README_EN.md、PROGRESS.md，或 docs/superpowers/specs/、docs/superpowers/plans/ 的直接 Markdown 文件，backend-tests 会报告分类结果，跳过带 PostgreSQL 的 backend-full。浏览器、前端及其他检查仍按各自规则执行。

分类使用 PR 基线提交中的策略，读取从共同祖先到 PR head 的完整差异，检查重命名两端以及文件类型。混合代码、未知路径或没有基线策略时执行完整后端。分类失败时请求完整验证，最终检查保留失败状态。

main 推送始终执行完整后端。Oracle 自动部署和预览部署同时启用时，PR 也执行完整后端，以提供发布所需的真实 API 测试收据。更新规则后需触发使用新基线的 PR 运行才能验证线上效果。

[工作流](../../.github/workflows/test.yml) · [分类器](../../scripts/ci/backend_route.py) · [路由回归测试](../../backend/tests/ci/test_backend_fast_path.py)
