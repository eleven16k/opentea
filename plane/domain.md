# Domain docs — 词汇表与 ADR 的位置

## Before exploring, read these

1. 项目根 `CONTEXT.md` — 业务词汇（本仓库的 glossary 载体）
2. `docs/adr/` — 正式决议（编号递增，Accepted 才是有效约束）

## File structure

```
<project>/
├── CONTEXT.md          ← 词汇表（= mattpocock skills 的 GLOSSARY.md）
└── docs/
    └── adr/
        ├── 0001-*.md
        └── NNNN-slug.md
```

**命名映射（重要）**：mp-skills 全套 skill 硬编码找 `GLOSSARY.md`；opentea 用
`CONTEXT.md`。**读到 skill 说 "read GLOSSARY.md" 时，读 `CONTEXT.md`**；
说 "write to GLOSSARY.md" 时写 `CONTEXT.md`。格式不变：
`**术语**：一两句话定义` + `_Avoid_：易混淆别名`。

## Use the glossary's vocabulary

写 spec、comment、ADR 时用 CONTEXT.md 的规范术语；引入新术语先消歧并落 CONTEXT.md，
再使用。发现 skill 措辞与 CONTEXT.md 冲突时，以 CONTEXT.md 为准并在报告里标注。

## Flag ADR conflicts

实现或审核中发现与 Accepted ADR 冲突时，不得静默绕过。引用格式：

> _Contradicts ADR-0007 (…), but worth reopening because…_

写进当前任务的报告，交 PM 裁定：要么改实现，要么开新 ADR 取代旧的。
