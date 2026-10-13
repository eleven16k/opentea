# opentea 使用教程（含完整真实案例）

> 你只需要：**说需求、答追问、拍板**。其余全部自动。
> 详细架构见 [INTEGRATION-PLAN.md](INTEGRATION-PLAN.md)，命令速查见 [CHEATSHEET.md](CHEATSHEET.md)

---

## 一、三条铁律

1. **一切从 `tea` 开始**——你只对 PM 席说自然语言，永远不要自己建票
2. **PM 会先验证再动手**——它可能向你追问（最多 3 个问题），答了才继续；被 PAUSE 的需求是证据不足，不是系统坏了
3. **所有产出落 Plane**——每张票有逐 AC 证据链，"完成"必须由独立审核判定，开发者说了不算

---

## 二、完整真实案例：「周报导出功能」从一句话到交付

以下是 2026-10-13 真实发生的全过程（未删节）。

### 第 1 步：你提需求（一句话）

```bash
tea "我想要一个命令，能一键把 Plane 里本周所有 Done 的票导出成一份 markdown 周报，包含每张票的标题、完成时间和证据链接"
```

输出：
```
→ 已提交给 PM 席（它会先跑需求验证，有疑问会在这里回复你）
```

### 第 2 步：PM 验证，向你追问（自动，约 2 分钟）

PM 没有直接动手。它跑了 `idea-validation` 六问，裁决 **REFINE**，回来问你：

```
需求验证：REFINE（待 3 项澄清）
1. 时间窗：「本周」是否指 Asia/Shanghai 的周一 00:00 至当前，按 completed_at 过滤？
2. 命令形态：命令放哪里、默认输出到哪里？
3. 证据链接：链接到 issue、完成报告 comment，还是两者都列？
已确认现状：项目内 3 张票均为 Done，Plane 提供 completed_at，尚无统一导出命令。
你确认这 3 点后我再给 GO 裁决并建票。
```

> 注意它顺手做了现状调研（3 张 Done 票、字段存在、无重复建设）——这就是"研究探索"环节。

### 第 3 步：你回答澄清（每问一两句话）

```bash
rig send dev-pm@opentea "[用户澄清] 1. 本周=Asia/Shanghai 周一00:00至当前，按 completed_at 过滤；2. 命令放 tools/export_weekly_report.py，默认输出 reports/week.md，可 --output 覆盖；3. 每票列 issue 链接 + 最主要证据 comment 链接（最多2条）。请给裁决并继续。"
```

### 第 4 步：PM 裁决 GO，自动建票（自动，约 2 分钟）

PM 经 Plane API 建票：冻结 AC（AC-01..05）+ 打 `ready-for-agent` 标签 + 写决策 comment（含验证结论 `docs/research/weekly-done-export/validation.md`）。然后向你回报票链接。

### 第 5 步：看门狗自动派发（自动，≤3 分钟）

launchd 看门狗（3 分钟周期）发现新票 → 日志：
```
[21:51:53] 发现 Ready 票: 导出本周 Plane Done 票 Markdown 周报
[21:51:54] kick dev-build@opentea: 已发送
```

### 第 6 步：build 席领取、实现、交证据（自动，约 10 分钟）

claude 席领取后按六步纪律执行，交付 SUBMIT_REVIEW：

```
结论：已实现只读周报导出工具并通过 11/11 自动化测试与真实命令验证；
     AC-01..05 自测全部 MET（待独立审核确认）；另报 2 条非阻断数据观察。
报告标识：report_id=TEA4-SUBMIT-...; artifact_revision=sha256:tool=c8c795f6,...
```

### 第 7 步：独立审核（自动，review 席）

review 席（codex，与 build 异 CLI）拉 In Review 队列，逐 AC 独立核对：
- **PASS** → 票转 Done，完事
- **CHANGES_REQUESTED** → 退回 build 修复，循环
- **NEEDS_EVIDENCE** → 要求补证据，不冤枉也不放水

### 你全程做了什么？

> 一句话需求 + 三句澄清。**共约 80 个字。**

---

## 三、三种典型场景

### 场景 A：日常提需求（上面案例的循环）

```bash
tea "需求描述"
# PM 若追问 → rig send dev-pm@opentea "[用户澄清] ..."
# 等 Done → 打开 Plane 看证据链
```

### 场景 B：架构/选型类需求

```bash
tea "我们是否应该把数据层从 SQLite 迁到 PostgreSQL"
```
PM 会先跑 **deep-research**：多研究员并行调研 → 三角色对抗辩论 → 给你一份带「显式分歧→决策点」的方案。**分歧会列出选项和代价等你拍板**——这是系统的设计，不是缺陷。

### 场景 C：PM 裁决 PAUSE

```
PAUSE — 需求真实性证据不足：目前没有用户主动提出过此功能...
```
这不是故障。要么补充证据重新提，要么放弃。被 PAUSE 挡住的需求，比你三个月后才发现没人用的需求便宜得多。

---

## 四、命令速查

```bash
# ── 每日 ──
tea "需求"                              # 提需求
rig send dev-pm@opentea "[用户澄清] ..." # 答 PM 的追问
tea --status                             # 三席状态
tea --log                                # build 席屏幕

# ── 盯进度 ──
rig capture dev-pm@opentea --lines 40    # PM 窗口（看追问/裁决）
rig capture dev-build@opentea --lines 40 # build 窗口
rig capture review-review@opentea --lines 40
tail -5 /tmp/opentea-watchdog.log        # 看门狗日志
open http://localhost                    # Plane 看板（票+证据链）

# ── 跨模型第二意见 ──
pi --provider qoder-cn --model GLM-5.3 -p "你的问题"

# ── 开机 / 收工 ──
source ~/ai-plan/openrig/.secrets/daemon.env && rig daemon start
rig up opentea --existing
rig down opentea
```

---

## 五、故障排查

| 症状 | 原因 | 处理 |
|---|---|---|
| `tea` 发了没反应 | PM 在跑验证（约 2 分钟） | `rig capture dev-pm@opentea` 看它窗口 |
| seat 停在选项提示 | 新会话的权限确认 | `rig send <席> "2" --dangerously-interact --reason "切auto"` |
| 票建了没人领 | 看门狗没跑或 seat 离线 | `tail /tmp/opentea-watchdog.log`；`rig ps` 查席位 |
| build 报 429 | codex 限流（多席并发） | 等几分钟；保持同时活跃任务 ≤2 |
| claude 席要登录 | 桌面 app 没开（代理令牌失效） | 打开 Claude 桌面 app，重启 daemon |
| Plane 打不开 | Docker/Plane 栈问题 | 见 INTEGRATION-PLAN § Docker 运维规则 |
| 全停后恢复 | — | `rig up opentea --existing`；改过 rig.yaml 则先 `rig down` 再 `rig up rig.yaml --cwd ~/ai-plan/openrig/opentea-workspace` |

---

## 六、体系地图（哪天府哪个文件）

```
~/ai-plan/openrig/
├── tea                     ← 你的入口命令（已装，全局可用）
├── CHEATSHEET.md           速查（含硬规矩）
├── INTEGRATION-PLAN.md     架构与决策全档
├── TUTORIAL.md             ← 本文件
├── opentea/                rig bundle（拓扑/席位/技能/Plane 契约）
│   ├── agents/pm/guidance/role.md        PM 需求入口规程
│   ├── agents/builder/…                   开发者六步纪律
│   ├── agents/reviewer/…                  独立审核规程
│   ├── skills/{idea-validation,deep-research,code-audit}/
│   └── tools/ready-watchdog.py            自动派发看门狗
├── opentea-workspace/      团队工作区（AGENTS.md=工作流宪法）
├── dist/opentea.rigbundle  可分发产物（Integrity PASS）
└── .secrets/               凭据（600，勿动勿传）
```

## 七、别忘了还有这些没建（诚实清单）

自动化已闭环，但：Agent Mail 未部署（通知靠你看窗口）、GLM 席位等你续费智谱套餐、ZCode 未接入、LICENSE 未选。全部细节见 CHEATSHEET「诚实清单」。
