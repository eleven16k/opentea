# OPENTEA

**A multi-agent development system where you only state what you want.**
**你只管提需求，团队负责交付。**

[OpenRig](https://github.com/mvschwarz/openrig) 编排 · [Plane](https://github.com/makeplane/plane) 状态 · Skills 认知 · 工程纪律 —— 四层整合的开箱即用多 agent 开发团队。

```
你: tea "我想要一个导出周报的功能"
      │
      ▼
┌─────────────────────────────────────────────────────────┐
│ PM 席 (codex)                                            │
│  需求验证（六问）→ 追问澄清 → GO → 自动建票（冻结 AC）      │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ Ready 看门狗（launchd，零 LLM 轮询）→ 自动派发             │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ build 席 (claude)                                        │
│  按六步纪律实现 → TDD → 逐 AC 证据 → SUBMIT_REVIEW         │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ 看门狗发现 In Review → 自动唤醒审核席（同样零人工）          │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌─────────────────────────────────────────────────────────┐
│ review 席 (codex) — 独立 pod，只观察不派单                 │
│  独立核对全部 AC → PASS / 退回 / 补证                      │
└─────────────────────────────────────────────────────────┘
```

**设计原则**：审核独立性靠结构（分 pod + 只观察边 + 技能隔离），不靠自觉；
所有产出带逐 AC 证据链；"完成"必须由未参与实现的审核者判定。

---

## 它和"开三个终端跑 agent"的区别

| | 临时开 agent | opentea |
|---|---|---|
| 需求入口 | 你写清楚 AC | **PM 席验证你的想法，追问模糊点，自动拆票** |
| 质量保证 | 靠模型自觉 | 冻结 AC + 独立审核席 + 工具级反自审（开发者的 MET 不算数） |
| 持续性 | 关终端就没了 | 持久席位 + Plane 证据链 + 看门狗自动派发 |
| 上下文污染 | 审核者常被实现者带偏 | 结构性隔离：审核席收不到实现上下文，只读冻结 AC 和已提交制品 |

---

## 快速开始

```bash
git clone https://github.com/eleven16k/opentea.git && cd opentea
./install.sh
```

**这一条命令会自动处理全部第三方依赖**：Node.js 22（含 nvm）、tmux、Python、
OpenRig CLI、Codex 认证检查、Plane 检测（未部署时加 `--deploy-plane` 自动部署）、
API key 引导与校验、**OPENTEA 项目与标签自动创建**、凭据脚手架、看门狗注册。
最后给出 `READY` / `NEEDS_ATTENTION` 的诚实结论。

```bash
./install.sh --dry-run        # 先预览将要做什么
./install.sh --deploy-plane   # 本机没有 Plane 时自动部署
```

装完后：

```bash
source ~/.opentea/secrets/daemon.env && rig daemon start
rig up rig.yaml --cwd <你的项目目录> --yes

tea "我想要一个导出周报的功能"        # 提需求（详见下方使用指南）
```

> 不想用安装器？手动分步安装见 [docs/TUTORIAL.md](docs/TUTORIAL.md)。

---

## 使用指南

### 一张票的生命周期

```
你提需求 ──→ PM 验证 ──→ GO ──→ 自动建票(ready-for-agent) ──→ 看门狗派发
                │                                              │
                ├─ REFINE ──→ PM 向你追问（≤3 问）──→ 你答 ──→ 重新裁决
                └─ PAUSE ──→ 附理由退回（证据不足，不投入）        ▼
                                                    build 实现 → SUBMIT_REVIEW
                                                                │
                你拍板 ←── 显式分歧 ──(如有)── 独立审核 ←────────┘
                                            │
                            PASS → Done │ 退回 → build 修复循环
```

### 你要做的只有三件事

**① 提需求** —— 大白话即可，不要求格式：

```bash
tea "我想要一个登录页，支持手机号验证码登录"
# 等价于: rig send dev-pm@opentea "[用户需求] ... 请按需求入口规程处理"
```

**② 答 PM 的追问** —— PM 验证后可能回来问（最多 3 个），答得越具体越好
（"大家都需要"这类回答会被追着不放，这是故意的）：

```bash
rig capture dev-pm@opentea --lines 40                    # 看它问了什么
rig send dev-pm@opentea "[用户澄清] 1... 2... 3..."       # 回答
```

**③ 拍板** —— 出现以下两种情况时需要你：
- **架构/选型类需求**：deep-research 辩论后给出带选项和代价的决策点，你选一个
- **审核退回且 PM 判断需仲裁**：看票 comment 里的 ESCALATE 项

### 命令速查

```bash
tea --status                              # 三席状态一览
tea --log                                 # build 席最近输出
rig capture dev-pm@opentea --lines 40     # 看 PM 窗口（追问/裁决在这）
rig capture review-review@opentea --lines 40
rig send dev-build@opentea "补充信息..."   # 给实现席加背景
pi --provider qoder-cn --model GLM-5.3 -p "问题"   # GLM 跨模型第二意见
tail -5 /tmp/opentea-watchdog.log         # 看门狗日志

# 开工 / 收工
source <凭据目录>/daemon.env && rig daemon start
rig up opentea --existing
rig down opentea
```

---

## 席位职责

### `dev.pm` — PM 席（codex）· 需求入口与裁定

| 职责 | 描述 |
|---|---|
| **需求验证** | 收到需求先跑 `idea-validation` 六问（需求真实性/现状/最渴望用户/最窄楔子/意外发现/未来价值）；缺证据向你追问，一次 ≤3 问；PAUSE 的需求附理由退回，不投入 |
| **研究组织** | 架构/选型类需求先跑 `deep-research`：多研究员并行调研 → 三角色对抗辩论 → 方案 + 显式分歧清单交你拍板 |
| **拆票建票** | GO 后经 Plane API 自动建票：故事 + 冻结 AC（可观测）+ 范围/非范围 + 依赖，打 `ready-for-agent` |
| **裁定权** | 范围、优先级、例外仲裁；**无权跳过验证直接建票**（用户催促也不行） |
| **不做** | 不写实现代码、不代替独立审核下结论、不擅自扩范围 |

### `dev.build` — 开发者席（claude-code）· 实现与证据

| 职责 | 描述 |
|---|---|
| **六步纪律** | 图探索 → 实读源码 → domain-modeling → 复用最小设计 → 实现/验证 → 独立审核；每步留下明确产物 |
| **按冻结 AC 实现** | 不擅自缩减 AC 让自己通过；改动范围限定在当前 AC |
| **证据交付** | SUBMIT_REVIEW 必含：逐 AC 对照表（MET/NOT_MET/**UNPROVEN**）+ SHA-256 制品指纹 + 精确命令与观察 + 盲区声明 |
| **不做** | 不自宣通过（工具层拒绝开发者自审）；不把"完成 90%"当结论 |

### `review.review` — 独立审核席（codex）· 质量门禁

| 职责 | 描述 |
|---|---|
| **结构独立** | 独立 pod、只有 `can_observe` 边（收不到实现上下文与派单）；技能集**刻意不含** implement/TDD |
| **独立核对** | 只读冻结 AC 与已提交制品（不读未提交工作区）；逐 AC 核对，不抽样；不接受转述 |
| **四态结论** | PASS / CHANGES_REQUESTED（附阻断项+对应 AC+预期行为）/ NEEDS_EVIDENCE（不假称代码错误）/ ESCALATE（交 PM） |
| **不做** | 不用开发者身份自审；建议与阻断分开写，防止混优先级 |

### `ready-watchdog` — 派发看门狗（launchd 常驻）

| 职责 | 描述 |
|---|---|
| **双队列自动派发** | 每 3 分钟零 LLM 轮询 Plane：Ready 队列有新票 → 唤醒 build 席；In Review 队列有新票 → 唤醒 review 席。整条回路无人工 |
| **多机队列拆分** | `OT_QUEUE=all\|ready\|review`——审核机上设 `review` 即成为专职审核机（多机架构，见下节） |
| **安全省电** | 防重复唤醒（原子状态文件）；seat 离线时静默跳过；票名净化后才进日志；不消耗模型额度 |

---

## 多机部署

单机是完整形态，多机是可选扩展。推荐架构 **Plane 中枢星型**：机器之间零直连，
Plane（任务/证据）+ Git 远端（制品）是唯一共享基底，每台机器一套独立 rig + 独立看门狗、各扫各的队列段。

| 机器 | 角色 | 看门狗配置 |
|---|---|---|
| 机器 A | `dev.pm` + `dev.build` | `OT_QUEUE=ready` |
| 机器 B（审核机） | `review.review` | `OT_QUEUE=review`（用 `rigs/review-host.yaml`） |

- 价值：developer 与 reviewer **物理上不同机器**，"同机自审"从制度禁止升级为物理不可能
- B 离线时 A 可临时切回 `OT_QUEUE=all`（单机回退，零配置成本）
- 完整手册（含 Plane 远程迁移、数据搬运脚本、验收清单）：[docs/RUNBOOK-multi-machine.md](docs/RUNBOOK-multi-machine.md)

---

## 自研 skills

| 技能 | 干什么 |
|---|---|
| **idea-validation** | YC 式六问压力测试需求，GO/REFINE/PAUSE 裁决（移植自 OpenRig office-hours，去耦合） |
| **deep-research** | 多研究员并行调研 → 研究员/架构师/PM 三角色对抗辩论 → 整合方案 + 显式分歧 |
| **code-audit** | 分层审核（改编自 [open-code-review](https://github.com/alibaba/open-code-review) Delegation Mode）：确定性筛选 → 分批判断 → 主控复核 → AC 判定 |

## 目录

```
opentea/
├── rig.yaml                          编排拓扑（开发 pod + 独立审核 pod）
├── rigs/review-host.yaml             多机版：纯审核机 rig（见多机部署节）
├── bundle.yaml                       bundle 清单 + 前置条件
├── install.sh                        一键安装器（自动处理全部第三方依赖）
├── agents/                           各席位定义 + 角色规程
├── skills/                           自研 skills
├── shared/                           共享资源池（OpenRig 原生 skills 精选 + openrig-core）
├── plane/                            Plane 集成（tracker 契约 / 标签映射 / MCP fragment）
├── governance/                       工程规约模板（AGENTS / CONTEXT / ADR / runbooks）
├── tools/                            ready-watchdog.py（双队列看门狗）· tea（需求入口）
│                                     migrate-plane-tickets.py（跨实例搬票）· bootstrap-plane.sh
│                                     export_weekly_report.py（周报导出）
├── tests/                            11 个回归用例（python3 -m unittest discover -s tests）
└── docs/                             TUTORIAL（教程）· RUNBOOK-multi-machine（多机手册）
```

## 质量与安全

- 本仓库发布前经过四阶段代码审核（确定性规则扫描 → 分批子审 → 主控逐条复核 → 修复闭环），
  全部阻断/建议项已处置
- `install.sh` 的全部 API 调用带 `-f`、凭据落盘即 600、第三方引用 pin 版本
- 回归：`python3 -m unittest discover -s tests`（11 用例）

## 前置条件与凭据纪律

- **永不**把 API key 写进本仓库或 bundle（`rig bundle create` 也会拒绝）
- 席位凭据经 daemon 环境注入（`PLANE_API_KEY` 等），启动前 source 你的环境文件
- Claude 席需标准 `claude auth login`；代理式认证（ANTHROPIC_BASE_URL）需自行将令牌注入 daemon 环境
- 详见 [docs/TUTORIAL.md](docs/TUTORIAL.md) 的「故障排查」

## 已知限制（诚实清单）

- **单机模式**下 build 与 review 同机，`host/cli` 分离门禁会亮黄——按「多机部署」节把审核席放到独立机器后清零（B 离线回退单机时警告会如实亮起，属正确行为）
- Plane MCP fragment 合并存在兼容性问题；seat 当前走 REST API（docs/agents/issue-tracker.md 的 curl 约定，完全可用）
- pi 席位仅放行 openrouter/zai/kimi/minimax 四种 provider key（OpenRig 限制）
- Plane 票状态名（In Review 等）需与实例实际状态名一致，跨实例部署时先核对

---

## 致谢

- [OpenRig](https://github.com/mvschwarz/openrig)（Apache-2.0）— 编排层本体，`shared/` 内含其原生 skills 与 openrig-core 插件副本
- [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）— 工程方法论来源（domain-modeling 等）
- [alibaba/open-code-review](https://github.com/alibaba/open-code-review) — code-audit 的 Delegation Mode 灵感
- [Plane](https://github.com/makeplane/plane)（Apache-2.0）— 状态层

## License

Apache-2.0。`shared/plugins/openrig-core/` 与 `shared/skills/` 下第三方文件保留其原始许可与版权声明。
