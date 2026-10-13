# opentea 业务语言

状态：随首个工具票（周报导出）建立初始术语。PM 可用 domain-modeling 消歧后修订。

**周报（Weekly Done Report）**：当前周内 `completed_at` 落入时间窗的 Done 票导出成的 Markdown 报告，含票据标题、完成时间、issue 链接和 ≤2 条证据评论链接。
_Avoid_：日报；cycle report（Plane 的 cycle 是迭代概念，与本工具的"自然周"无关）。

**当前周（current week）**：Asia/Shanghai 时区本周一 00:00 起、至命令执行时刻止的左闭右闭时间窗。Asia/Shanghai 自 1991 年起无夏令时，实现用固定 +08:00 偏移。
_Avoid_：Plane cycle 的起止；UTC 周。

**完成时间（completed_at）**：Plane issue 进入 Done 状态的确切时间戳（UTC ISO-8601）。入窗判定的唯一依据；缺失或不可解析即视为不在窗内。
_Avoid_：`updated_at`（任何状态变更都会刷新它）；创建时间。

**证据评论（evidence comment）**：票评论中 HTML 含 `<strong>REVIEW</strong>` 或 `<strong>结论</strong>` 者，按创建时间倒序取最新 ≤2 条，以 `#comment-{comment_id}` 锚点链接进周报。
_Avoid_：全部评论；PM 复核（实测其 HTML 标记为"PM复核"，不命中证据规则，属预期排除）。
