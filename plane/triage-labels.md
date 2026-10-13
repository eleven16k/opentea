# Triage labels — canonical → Plane 映射

| Label in mattpocock/skills | Plane label | Meaning |
|---|---|---|
| `needs-triage` | `needs-triage` | Maintainer needs to evaluate this issue |
| `needs-info` | `needs-info` | Waiting on reporter for more information |
| `ready-for-agent` | `ready-for-agent` | Fully specified, ready for an agent to claim |
| `ready-for-human` | `ready-for-human` | Requires human implementation |
| `wontfix` | `wontfix` | Will not be actioned |

## 规则

- `/triage` 产出 `ready-for-agent` 或 `ready-for-human`，二者必居其一
- `to-spec` / `to-tickets` 直接打 `ready-for-agent`（spec 已冻结，免 triage）
- label 不存在时 `POST .../labels/` 创建，不静默跳过
- label 用名称匹配；Plane label 无全局唯一约束（project 内唯一），逐 project 确认
