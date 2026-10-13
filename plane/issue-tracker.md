# Issue tracker: Plane (self-hosted)

本文件是 opentea 全部 skills（triage / to-spec / to-tickets / implement / pr / wayfinder 等）
的 tracker 契约。下游 skill 按本文件的章节标题查找操作方式；**改章节结构 = 破坏所有 skills**。

- Base URL: `http://localhost`（本地实例；换环境改此处）
- API 版本: `/api/v1/`（本版本**无** workspace 列表端点，直接用 slug 访问：
  `/api/v1/workspaces/{slug}/...`）
- 认证: 请求头 `X-API-Key: <token>`；token 从环境变量 `PLANE_API_KEY` 读取，**绝不写入任何仓库文件**
  （本机已存 `~/ai-plan/openrig/.secrets/plane-api-key`，0600）
- Workspace slug: `ai-plan`；已有项目：Scrum Loop（`SCRUMLOOP`）、晶项（`JINGXIANG`）；opentea 用 `OPENTEA`
- **分页**：列表端点返回 dict（`results` / `count` / `next_cursor`），不是裸数组——
  遍历时取 `results`，翻页用 `next_cursor` 参数
- 逻辑身份: agent 用 API key 操作时，Plane 记录的是 token 属主（`admin@ai-plan.local`）。
  逻辑 agent 名（如 `opentea.build`）写在 comment 正文的报告标识里，**不冒充独立登录身份**。

## Conventions

### Create a work item

```bash
curl -s -X POST "http://localhost/api/v1/workspaces/ai-plan/projects/$PROJECT_ID/issues/" \
  -H "X-API-Key: $PLANE_API_KEY" -H "Content-Type: application/json" \
  -d '{"name": "<故事标题>", "description_html": "<p>...</p>", "priority": "medium"}'
```

响应中的 `id` 是 issue UUID（32 位 hex，无连字符）。**工单显示编号**（如 `TEA-12`）是
project 前缀 + 递增序号，用 `GET .../issues/<id>/` 里的 `sequence_id` 字段拿。

### Read / list / filter

```bash
# 列出某状态的票（state 是 UUID，需先查项目的 state 列表做名称→id 映射）
curl -s -H "X-API-Key: $PLANE_API_KEY" \
  "http://localhost/api/v1/workspaces/ai-plan/projects/$PROJECT_ID/issues/?state=$STATE_ID"

# 读单票（含 description、labels、assignees）
curl -s -H "X-API-Key: $PLANE_API_KEY" \
  "http://localhost/api/v1/workspaces/ai-plan/projects/$PROJECT_ID/issues/$ISSUE_ID/"
```

### Comment（所有任务报告的唯一去处）

```bash
curl -s -X POST "http://localhost/api/v1/workspaces/ai-plan/projects/$PROJECT_ID/issues/$ISSUE_ID/comments/" \
  -H "X-API-Key: $PLANE_API_KEY" -H "Content-Type: application/json" \
  -d '{"comment_html": "<p>...</p>"}'
```

**先写 comment 并回读取得 comment id，再改状态，再发短通知。** 状态转换失败时保留
comment 并如实记录，不声称已进入下一状态。

### Labels / states

```bash
# 项目的 state 列表（名称→UUID 映射，按现有流程映射，不新建状态）
curl -s -H "X-API-Key: $PLANE_API_KEY" .../projects/$PROJECT_ID/states/
# labels
curl -s -H "X-API-Key: $PLANE_API_KEY" .../projects/$PROJECT_ID/labels/
```

**打标（实测本版本）**：`POST .../issues/<id>/labels/` 不存在（404），
用 PATCH issue 直接带 labels 数组：

```bash
curl -s -X PATCH ".../issues/$ISSUE_ID/" -H "X-API-Key: $PLANE_API_KEY" \
  -H "Content-Type: application/json" -d '{"labels": ["<label_uuid>"]}'
```

### Close / sub-issue

- 关闭 = 把 state 改为 Done 对应的 state UUID（`PATCH .../issues/$ISSUE_ID/` + `{"state": "<uuid>"}`）
- 父子关系: `PATCH issue` + `{"parent": "<parent_issue_uuid>"}`

## PRs as a triage surface

**(flag): no.** 本地实例未配 Git 集成；PR 不进 Plane。PR 评审走 code-audit 流程，
结论由 agent 写回对应 issue 的 comment。

## When a skill says "publish to the issue tracker"

spec / to-tickets 的产出发布为 issue body（`description_html`）。规格较长时正文放全文 +
`<spec-template>` 结构；拆出的每张票是独立 issue，打 `ready-for-agent` 标签（见下）。

## When a skill says "fetch the relevant ticket"

按 issue 编号（`TEA-N`）查：先 list filter `?search=N` 或遍历 `sequence_id`；
拿到 UUID 后读详情。**缓存 UUID 不超过一个会话**，跨会话必须重查。

## Wayfinding operations

- **Map**: `GET .../issues/?state=<uuid>&priority=...` 按状态+优先级列出当前前沿
- **Child ticket**: 建 issue 时带 `parent` 字段；读取时 `GET .../issues/?parent=<uuid>`
- **Blocking**: Plane 社区版无原生 blocking 关系 → 在 issue body 里写
  `Blocked by: TEA-N` 行，并在依赖解除后**手动删除该行**（这是纪律，工具不强制）
- **Frontier query**: 状态 ∈ Ready 且无 `Blocked by` 行且 assignee 为空 = 可领取
- **Claim**: `PATCH issue` + `{"assignees": ["<member-uuid>"]}`。
  **"读→写负责人"不是原子操作**：多 agent 环境预分配互不重叠的队列，不并发抢单
- **Resolve**: state 改 Done + comment 写完整报告（逐 AC 对照表 + 证据索引）

## Triage labels

| Label in mattpocock/skills | Plane label | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | 待评估 |
| `needs-info` | `needs-info` | 等报告人补充 |
| `ready-for-agent` | `ready-for-agent` | 规格完整，agent 可直接领取 |
| `ready-for-human` | `ready-for-human` | 需要人来做 |
| `wontfix` | `wontfix` | 不做 |

标签不存在时先在项目里创建（`POST .../labels/`），**不要静默跳过打标**。

## Report integrity rules（与脚手架协议一致）

1. 完整报告写 comment（结论 / 报告标识 / 逐 AC 对照表 / 证据索引 / 差异与下一步）
2. 短通知 ≤300 字符，只做定位（事件 + 工单号 + comment 引用），由 projectctl.py notice 生成
3. **先写 comment → 回读 id → 转状态 → 回读 → 发通知**；失败如实记录，不假称已交接
4. `external_id` 只是关联字段，不假定 API 幂等去重；重试用 `report_id` 查重
