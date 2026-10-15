#!/usr/bin/env bash
# anthropic-failover.sh — claude-code 席位的模型端点故障转移
#
# 机制：每 5 分钟（launchd）探测当前激活的 ANTHROPIC 端点；
#   认证失效（401/403）或套餐失效（429 plan）→ 自动切换到备用 provider，
#   改写 daemon.env 的 ANTHROPIC 块并重启 daemon 恢复席位。
#   网络不可达（连接失败）不切换——那是网络问题，不是认证问题。
# 防抖：30 分钟内最多切换一次（状态文件记时间戳）。
#
# 用法:
#   anthropic-failover.sh            # 探测，必要时切换
#   anthropic-failover.sh --check    # 只探测报告，不切换
#   anthropic-failover.sh --swap     # 手动强制切换
set -u

SECRETS_DIR="${OT_SECRETS_DIR:-$HOME/ai-plan/openrig/.secrets}"
DAEMON_ENV="$SECRETS_DIR/daemon.env"
STATE_FILE="$HOME/.opentea/failover.state"
LOG="${OT_FAILOVER_LOG:-/tmp/opentea-failover.log}"
MIN_SWITCH_INTERVAL=1800   # 30s × 60 = 30 分钟防抖

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

# 当前激活的 provider（从 daemon.env 的未注释 ANTHROPIC_BASE_URL 判断）
active_provider() {
  local base
  base=$(grep -E '^export ANTHROPIC_BASE_URL=' "$DAEMON_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"')
  case "$base" in
    *bigmodel*) echo "glm" ;;
    *claude-desktop*) echo "claude-proxy" ;;
    *) echo "unknown" ;;
  esac
}

# 探测：对指定 provider 发 1-token 最小请求。输出 OK / AUTH_FAIL / NET_FAIL
probe() {
  local base="$1" token="$2" model="$3"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 25 \
    -X POST "$base/v1/messages" \
    -H "x-api-key: $token" -H "Authorization: Bearer $token" \
    -H "anthropic-version: 2023-06-01" -H "Content-Type: application/json" \
    -d '{"model":"'"$model"'","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}' \
    2>/dev/null) || { echo "NET_FAIL"; return; }
  case "$code" in
    200) echo "OK" ;;
    401|403) echo "AUTH_FAIL" ;;
    429) echo "PLAN_FAIL" ;;
    *) echo "OTHER_$code" ;;
  esac
}

creds_for() {
  # 输出: base|token|model|probe_model（probe_model 用最便宜的 flash 档做探测）
  case "$1" in
    glm)          echo "https://open.bigmodel.cn/api/anthropic|$(cat "$SECRETS_DIR/bigmodel-api-key" 2>/dev/null)|glm-5.3|glm-5.3-flash" ;;
    claude-proxy) echo "http://127.0.0.1:15721/claude-desktop|$(cat "$SECRETS_DIR/claude-proxy-token" 2>/dev/null)|claude-sonnet-4-5|claude-sonnet-4-5" ;;
  esac
}

swap_env_to() {
  # daemon.env 使用显式标记块（BEGIN/END-ANTHROPIC-<provider>）：
  # 目标块内 export 行去注释（激活），其余块加注释（停用）；对称可逆。
  # 写前校验：处理后必须恰好有一个激活的 ANTHROPIC_BASE_URL，否则放弃修改。
  local target="$1"
  python3 - "$DAEMON_ENV" "$target" <<'EOF'
import sys
path, target = sys.argv[1], sys.argv[2]
begin, end = "# BEGIN-ANTHROPIC-", "# END-ANTHROPIC-"
lines = open(path).read().splitlines()
out, region, changed = [], None, 0
for ln in lines:
    if ln.startswith(begin):
        region = "glm" if "GLM" in ln else "claude-proxy"
        out.append(ln); continue
    if ln.startswith(end):
        region = None; out.append(ln); continue
    if region and "export ANTHROPIC" in ln:
        stripped = ln.lstrip("#").strip()
        new_line = stripped if region == target else "# " + stripped
        if new_line != ln: changed += 1
        out.append(new_line)
    else:
        out.append(ln)
active = sum(1 for ln in out if ln.startswith("export ANTHROPIC_BASE_URL="))
if active != 1:
    sys.exit(f"refusing: after toggle, active ANTHROPIC_BASE_URL count = {active} (need 1)")
open(path, "w").write("\n".join(out) + "\n")
print(f"toggled to {target} ({changed} lines changed)")
EOF
}

REPO_DIR="${OT_REPO_DIR:-$HOME/ai-plan/openrig/opentea}"
bounce_daemon() {
  local nvm="$HOME/.nvm/nvm.sh"
  rig down opentea >/dev/null 2>&1
  tmux kill-server 2>/dev/null
  rig daemon stop >/dev/null 2>&1
  sleep 3
  . "$nvm" 2>/dev/null; nvm use 22 >/dev/null 2>&1
  . "$DAEMON_ENV"
  rig daemon start >/dev/null 2>&1
  sleep 4
  ( cd "$REPO_DIR" && rig up rig.yaml --cwd "$HOME/ai-plan/openrig/opentea-workspace" --yes >/dev/null 2>&1 )
}

case "${1:-}" in
  --swap)
    cur=$(active_provider)
    alt=$([ "$cur" = "glm" ] && echo "claude-proxy" || echo "glm")
    log "手动切换: $cur → $alt"
    swap_env_to "$alt"
    bounce_daemon
    log "切换完成，当前激活: $alt"
    exit 0 ;;
esac

cur=$(active_provider)
IFS='|' read -r base token model probe_model <<< "$(creds_for "$cur")"
result=$(probe "$base" "$token" "$probe_model")
log "探测 $cur ($base): $result"

case "$result" in
  OK|NET_FAIL|OTHER_5*)
    # 正常或网络类失败——不动
    exit 0 ;;
esac

# 认证/套餐失效 → 尝试切换
[ "$1" = "--check" ] && { log "--check 模式：本应切换，未执行"; exit 1; }

now=$(date +%s)
last=0
[ -f "$STATE_FILE" ] && last=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
if [ $((now - last)) -lt "$MIN_SWITCH_INTERVAL" ]; then
  log "防抖期内（上次切换距今 $(( (now - last) / 60 )) 分钟），不切换"
  exit 0
fi

alt=$([ "$cur" = "glm" ] && echo "claude-proxy" || echo "glm")
IFS='|' read -r abase atoken amodel aprobe <<< "$(creds_for "$alt")"
alt_result=$(probe "$abase" "$atoken" "$aprobe")
if [ "$alt_result" != "OK" ]; then
  log "备用 $alt 也不可用（$alt_result），保持现状并升级人工处理"
  exit 1
fi

log "认证失效确认（$result），自动切换: $cur → $alt"
swap_env_to "$alt"
echo "$now" > "$STATE_FILE"
bounce_daemon
log "切换完成，当前激活: $alt；席位已恢复"
exit 0
