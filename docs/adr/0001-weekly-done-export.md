# ADR-0001: 周报导出工具的落点、复用与访问决策

日期：2026-10-13 ｜ 状态：Accepted ｜ 关联票：Plane OPENTEA seq 4（uuid `245628e5-e293-483f-9ab6-ce0d4611b3b6`）
规范源：`opentea-workspace/docs/research/weekly-done-export/validation.md`（裁决 GO）

## 背景

OPENTEA 项目需要一条只读命令，把当前周 Done 票导出为 Markdown 周报。票面冻结：入口 `python3 tools/export_weekly_report.py`、默认输出 `reports/week.md`、issue 链接与 `#comment-{comment_id}` 证据链接格式、Asia/Shanghai 周界。

## 决策

1. **落点 `opentea/tools/`，仓库根 = `opentea/`**。票面入口 `python3 tools/export_weekly_report.py` 从 opentea/ 根逐字成立；与同目录 `ready-watchdog.py`（同为 OPENTEA Plane 只读运维工具）共存。备选"starter 模板（项目管理脚手架）"被否：从 starter 根运行入口是 `python3 template/tools/...`，与冻结入口矛盾，且模板 project.toml 全为占位符，不是 OPENTEA 本体。
2. **复用 `ready-watchdog.py` 的 `api_get` 模式**（stdlib `urllib`、`X-API-Key` 头、timeout 10s、GET 显式置 method），不引入 requests 等外部依赖——与项目现有工具零依赖风格一致。分页按 `next_cursor`/`next_page_results` 循环（当前单页，循环为正确性兜底）。
3. **认证：环境变量 `PLANE_API_KEY` 优先**（`opentea-workspace/docs/agents/issue-tracker.md` 契约），**缺失时回退 `~/ai-plan/openrig/.secrets/plane-api-key` 文件**（看门狗已验证的路径）。两者皆缺报错退出。密钥永不打印、永不写入任何仓库文件。
4. **Asia/Shanghai 用固定 +08:00 偏移**（`timezone(timedelta(hours=8))`），不依赖 zoneinfo 数据库。该时区 1991 年后无夏令时，周界语义不变。
5. **纯函数核心 + 注入式 IO**：周界计算、入窗过滤、证据筛选、Markdown 渲染全部是可独立调用的纯函数；`fetch_issues`/`fetch_comments` 为模块级函数供测试替换；`api_get` 单一接缝可录制请求方法。这样 AC-01 边界与 AC-05 GET-only 都有确定性自动化测试。
6. **异常语义**：`completed_at` 缺失/不可解析的 Done 票排除（实测 TEA-0 即此情形，属预期排除非缺陷）；网络/HTTP 错误输出 `{"status":"ERROR"}` 并以退出码 2 结束，与 `projectctl.py` 报错风格一致；对 Plane 仅发 GET（AC-05），仅写所选输出文件（`w` 模式，自动创建父目录）。

## 后果

- 周报是生成物，重跑覆盖同一路径；`reports/` 无需入库（opentea/ 目前非 git 仓库，未来入库时应 ignore）。
- 链接格式为冻结常量，若 Plane web 路由变更需同步改 `WEB_BASE` 与对应票面决策。
- 多项目、日期区间、评论正文导出明确出范围（票面 Out of scope），本 ADR 不为它们预留接口。
