# RUNBOOK：Plane 迁移与多机接入手册

> 版本：1.0（2026-10-14）· 适用：opentea 单机 → 多机（架构 A，Plane 中枢星型）
> 前置阅读：[INTEGRATION-PLAN.md](../../INTEGRATION-PLAN.md) · [MULTI-MACHINE-PLAN.md](../../MULTI-MACHINE-PLAN.md)
> 执行者：维护者本人（涉及服务器、凭据、公网暴露的决策）

---

## 触发条件

满足其一即执行本手册：
- 第二台机器要加入团队（审核分离 / 容量扩展）
- Mac 需要睡眠/移动，但团队要保持 7×24 响应

## 范围与边界

- **做**：Plane 迁到远程、机器 B 接入为审核机、队列按角色拆分
- **不做**：Tailscale/VPN 层（二期按需）、生产部署权限、Agent Mail（另册）

## 前置检查（全部满足才开工）

```bash
docker ps | grep -c plane-app        # 本地 Plane 在跑（数据源）
git -C ~/ai-plan/openrig/opentea pull # 本仓库最新
ssh root@<远程服务器IP> echo ok       # 服务器可达，SSH 互信
```

---

## 阶段 P：远程部署 Plane

### P1 服务器准备（一次性）

| 项 | 要求 |
|---|---|
| 系统 | 任意 Linux（Ubuntu 22+/Debian 均可），2C4G 起 |
| Docker | `curl -fsSL https://get.docker.com | sh` |
| 端口 | 80/443（或自定义），**只对 Tailscale/内网开放，不放公网** |
| 时间同步 | `timedatectl` 确认 NTP 生效（票时间戳依赖） |

### P2 部署（全新实例，推荐——干净且配置即代码）

```bash
ssh root@<服务器>
git clone --depth 1 https://github.com/makeplane/plane.git /opt/plane && cd /opt/plane
./setup.sh launcher          # 交互生成 plane.env；一路默认即可
# 编辑 plane.env：
#   WEB_URL=https://<你的域名或内网IP>     APP_DOMAIN=<同 WEB_URL 的域名部分>
docker compose up -d
curl -s -o /dev/null -w "%{http_code}\n" http://<服务器地址>/health/   # 期望 200
```

浏览器打开 `http://<服务器地址>` 注册管理员（这是新实例的唯一人工步骤）。

**运维铁律（本机踩过的坑，远程同样适用）**：
- 该栈的一切操作必须带 `--env-file plane.env`（不带会丢 SECRET_KEY → api crash-loop）
- Plane 不可达时先查 `docker logs plane-app-proxy-1`（Caddy 配置错误是头号嫌疑）

### P3 数据迁移（把本机 5 张票+证据搬过去）

在本机执行（源=本地实例只读，目标=新实例）：

```bash
cd ~/ai-plan/openrig/opentea
export SRC_PLANE_URL=http://localhost SRC_API_KEY=$(cat ~/ai-plan/openrig/.secrets/plane-api-key) SRC_PROJECT_ID=884817bb-df58-447b-829f-f87eaf7f0378
export DST_PLANE_URL=https://<服务器地址> DST_API_KEY=<新实例token>
python3 tools/migrate-plane-tickets.py --dry-run --create   # 先预览
python3 tools/migrate-plane-tickets.py --create             # 执行（自动建项目+标签+搬票+搬comment）
```

脚本诚实边界（设计如此，不是缺陷）：不搬附件、不搬 assignees（跨实例身份不同）、自定义 state 需手工映射。搬完**人工抽查 2 张票**：正文完整、comment 数一致、AC 表未变形。

**每步预期**：`--dry-run` 列出 5 张票；执行后打印 `完成: 5/5`。
**停止条件**：任何票迁移失败且无法解释 → 停，目标实例是新的，删掉重来零成本。

### P3'（备选路径：Docker 卷整体迁移）

要原样保住实例（含用户/设置/历史），版本一致时可用卷迁移：
本机 `docker compose down` → 打包 `plane-app_plane-db-data` 等卷 → 服务器恢复 → `up`。
**风险**：版本不一致会炸 schema；没把握就走 P3 的 API 路径（推荐）。

---

## 阶段 K：凭据与配置切换（本机，15 分钟）

| 步骤 | 动作 | 验证 |
|---|---|---|
| K1 | 新实例生成 API token（设置→API tokens） | `curl -H "X-API-Key: <t>" https://<服务器>/api/v1/users/me/` 返回 200 |
| K2 | `daemon.env` 更新 `PLANE_URL` 与 token；`.secrets/` 同步 | `source daemon.env && curl .../users/me/` 200 |
| K3 | `opentea/plane/project.json` 的 `id` 改为迁移脚本输出的新 id | watchdog 手动跑一次 exit 0 |
| K4 | `docs/agents/issue-tracker.md` 的 base_url/workspace 更新 | — |
| K5 | 重启 daemon（`tmux kill-server` + `rig daemon stop/start`，老规矩） | 三席 run、能读到票 |
| K6 | 本地旧 Plane：`docker compose down`（**先别删卷**，观察一周再清理） | — |

---

## 阶段 M：机器 B 接入（审核机）

### M1 初始化

```bash
# 在机器 B 上
git clone https://github.com/eleven16k/opentea.git && cd opentea
./install.sh        # 全部依赖 + 引导（token 用新实例的，队列角色见 M2）
```

### M2 角色化配置（机器 B = 纯审核）

```bash
# 看门狗只扫 In Review（写进 B 的 launchd 环境，install.sh 已支持模板渲染）
launchctl setenv OT_QUEUE review
launchctl bootout gui/$(id -u)/dev.opentea.ready-watchdog 2>/dev/null
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.opentea.ready-watchdog.plist
```

```bash
# 启动审核 rig（B 上不跑 pm/build）
rig up rigs/review-host.yaml --cwd ~/opentea-workspace --yes
```

### M3 机器 A 的对应收缩

```bash
# A 的看门狗只扫 Ready 队列（双机在场时避免 A 兼审）
launchctl setenv OT_QUEUE ready
launchctl bootout gui/$(id -u)/dev.opentea.ready-watchdog
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.opentea.ready-watchdog.plist
```

**B 缺席回退（本机韧性）**：B 关机时把 A 的 OT_QUEUE 切回 all 即可回到单机全流程（`launchctl setenv OT_QUEUE all` + 重载）。心跳自动检测是二期增强。

---

## 阶段 V：验收清单

| 检查 | 通过条件 |
|---|---|
| 跨机交接 | A 上 build 提交 In Review → **B 看门狗 ≤3 分钟**自动唤醒 review 席 |
| 制品复验 | review 席在 B 上按 `reviewed_revision` 的 SHA 拉到同一制品 |
| host 分离 | `projectctl check` 的 host/cli 警告清零 |
| 故障切换 | B 关机 → A 日志记录"In Review 无人接管"；B 复活/回退后补审 |
| 凭据隔离 | B 上只有审核所需凭据 |
| Plane 迁移完整性 | 抽查 2 张票：正文/comment 数/AC 表与源一致 |

**全绿 = 多机架构 A 上线。** 记录本 runbook 实际执行版本与日期到票面。

---

## 回退

| 场景 | 回退动作 |
|---|---|
| 迁移后新实例有问题 | K6 未删的本地卷 `docker compose up` + daemon.env 改回 localhost——10 分钟回原状 |
| 机器 B 不稳定 | A 的 OT_QUEUE 切回 all，review 席回 A（B 缺席回退） |
| 迁移脚本中途失败 | 目标是新实例，删项目重来；源实例全程只读无损 |

## 已知坑（本机实录，远程同样适用）

1. compose 必带 `--env-file plane.env`，否则 SECRET_KEY 丢失 → api crash-loop
2. Plane 不可达先看 proxy 日志：Caddy 空环境变量破坏全局块语法（CERT_* 留空即触发）
3. API 分页：`next_page_results=False` 才是终止信号；乱传 cursor 得到空页
4. macOS 上 Docker VM 长时间运行 + 休眠会 I/O 退化 → 重启 Docker Desktop
