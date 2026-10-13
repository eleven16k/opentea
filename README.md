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

前置：Node.js 22/24、tmux、已认证的 [Codex](https://openai.com/codex)（可选：Claude Code 桌面版 / pi + 任一 provider）。

```bash
# 1. 安装 OpenRig
npm install -g @openrig/cli
rig setup

# 2. 部署 Plane（本地 Docker）
#    https://developers.plane.so/self-hosting/overview
#    建项目后把 id 写入 plane/project.json

# 3. 配置 tracker 契约
cp plane/issue-tracker.md <你的项目>/docs/agents/issue-tracker.md
#    （把 base_url / workspace slug / project_id 换成你的）

# 4. 启动团队
source <你的凭据目录>/daemon.env     # PLANE_API_KEY 等
rig daemon start
rig up rig.yaml --cwd <你的项目目录> --yes

# 5. 提需求
rig send dev-pm@opentea "[用户需求] 我想要xxx —— 请按需求入口规程处理"
```

建一个 `tea` 快捷命令（可选）：

```bash
cat > /usr/local/bin/tea <<'EOF'
#!/usr/bin/env zsh
rig send dev-pm@opentea "[用户需求] $* —— 请按需求入口规程处理：验证（idea-validation）→ 必要时追问 → GO 后拆票建票（打 ready-for-agent）→ 回报。"
EOF
chmod +x /usr/local/bin/tea

tea "我想要一个导出周报的功能"
```

之后：PM 可能追问（`rig capture dev-pm@opentea` 查看，`rig send dev-pm@opentea "[用户澄清] ..."` 回答），
看门狗自动派发，builder 实现，review 独立核对——你只在两头出现。

---

## 席位与技能矩阵

| 席位 | runtime | 职责 | 技能 |
|---|---|---|---|
| `dev.pm` | codex | 需求验证、拆票建票、架构裁定 | idea-validation · deep-research · office-hours · context-builder |
| `dev.build` | claude-code | 按冻结 AC 实现 + TDD | development-team · TDD · systematic-debugging · domain-modeling |
| `review.review` | codex | 独立审核（**刻意不含** implement/TDD） | code-audit · verification-before-completion |

**多模型扩展**：GLM/DeepSeek/Kimi 可作跨模型顾问（`pi --provider qoder-cn` 或 ZCode 无头模式）；
若持有智谱 Coding Plan，review 席可切 `runtime: pi`（`ZAI_CODING_CN_API_KEY` 在 OpenRig 白名单内）。

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
├── rig.yaml           编排拓扑（pod / seat / 边）
├── bundle.yaml        bundle 清单 + 前置条件
├── agents/            各席位定义 + 角色规程
├── skills/            自研 skills
├── shared/            共享资源池（OpenRig 原生 skills 精选 + openrig-core）
├── plane/             Plane 集成（tracker 契约 / 标签映射 / MCP fragment）
├── governance/        工程规约模板（AGENTS / CONTEXT / ADR / runbooks）
├── tools/             ready-watchdog.py（自动派发看门狗）
└── docs/              使用教程 / 架构说明
```

## 前置条件与凭据纪律

- **永不**把 API key 写进本仓库或 bundle（`rig bundle create` 也会拒绝）
- 席位凭据经 daemon 环境注入（`PLANE_API_KEY` 等），启动前 source 你的环境文件
- Claude 席需标准 `claude auth login`；代理式认证（ANTHROPIC_BASE_URL）需自行将令牌注入 daemon 环境
- 详见 [docs/TUTORIAL.md](docs/TUTORIAL.md) 的「故障排查」

## 已知限制（诚实清单）

- review 与 pm 同为 codex 时，`host/cli` 分离门禁会亮黄——建议 build 与 review 用不同 runtime
- Plane MCP fragment 合并存在兼容性问题；seat 当前走 REST API（docs/agents/issue-tracker.md 的 curl 约定，完全可用）
- pi 席位仅放行 openrouter/zai/kimi/minimax 四种 provider key（OpenRig 限制）

---

## 致谢

- [OpenRig](https://github.com/mvschwarz/openrig)（Apache-2.0）— 编排层本体，`shared/` 内含其原生 skills 与 openrig-core 插件副本
- [mattpocock/skills](https://github.com/mattpocock/skills)（MIT）— 工程方法论来源（domain-modeling 等）
- [alibaba/open-code-review](https://github.com/alibaba/open-code-review) — code-audit 的 Delegation Mode 灵感
- [Plane](https://github.com/makeplane/plane)（Apache-2.0）— 状态层

## License

Apache-2.0。`shared/plugins/openrig-core/` 与 `shared/skills/` 下第三方文件保留其原始许可与版权声明。
