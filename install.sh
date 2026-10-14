#!/usr/bin/env sh
# opentea installer — 一条命令装好全部第三方依赖，并引导完成凭据配置。
#
# 用法:
#   ./install.sh              # 安装 + 引导配置
#   ./install.sh --dry-run    # 只预览将要做什么，不改系统
#   ./install.sh --deploy-plane  # Plane 未部署时，自动用官方 compose 部署
#
# 退出码: 0 = READY / READY_WITH_LIMITATIONS, 1 = NEEDS_ATTENTION
set -u

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=0
DEPLOY_PLANE=0
PLANE_URL="${PLANE_URL:-http://localhost}"
WS_SLUG="${PLANE_WORKSPACE_SLUG:-ai-plan}"
SECRETS_DIR="${SECRETS_DIR:-$HOME/.opentea/secrets}"

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --deploy-plane) DEPLOY_PLANE=1 ;;
    *) echo "未知参数: $arg"; exit 2 ;;
  esac
done

ok()   { printf '\033[32m[OK]\033[0m %s\n' "$1"; }
inst() { printf '\033[36m[INSTALL]\033[0m %s\n' "$1"; }
skip() { printf '\033[33m[SKIP]\033[0m %s\n' "$1"; }
fail() { printf '\033[31m[FAIL]\033[0m %s\n' "$1"; }
act()  { printf '\033[36m[ACTION]\033[0m %s\n' "$1"; }
run()  { if [ "$DRY_RUN" = "1" ]; then skip "(dry-run) $1"; else inst "$1"; if eval "$2"; then :; else fail "上一命令失败（已计入 NEEDS_ATTENTION）"; ACTIONS=$((ACTIONS+1)); fi; fi; }

have() { command -v "$1" >/dev/null 2>&1; }

pkg_install() {
  if have brew; then brew install "$1"
  elif have apt-get; then sudo apt-get update -qq && sudo apt-get install -y "$1"
  else fail "无法自动安装 $1（无 brew/apt），请手动安装"; return 1; fi
}

ACTIONS=0

printf '\n== opentea 安装器 %s ==\n\n' "$([ "$DRY_RUN" = "1" ] && echo "(dry-run 预览)")"

# ---------- 1. 基础运行时 ----------
if [ "$(uname)" = "Darwin" ] && ! have brew; then
  fail "需要 Homebrew：https://brew.sh"; ACTIONS=$((ACTIONS+1))
fi

if have node; then
  NMajor=$(node -p 'process.versions.node.split(".")[0]')
  if [ "$NMajor" = "22" ] || [ "$NMajor" = "24" ]; then
    ok "Node.js $(node -v)"
  elif [ -s "$HOME/.nvm/nvm.sh" ] && . "$HOME/.nvm/nvm.sh" 2>/dev/null && nvm ls 2>/dev/null | grep -q "v22\."; then
    nvm use 22 >/dev/null 2>&1
    ok "Node.js $(node -v) (nvm)"
  else
    act "Node.js $(node -v) 不在支持范围（22/24）"
    ACTIONS=$((ACTIONS+1))
    if ! have nvm && [ ! -s "$HOME/.nvm/nvm.sh" ]; then
      run "安装 nvm" 'git clone --depth 1 https://github.com/nvm-sh/nvm.git "$HOME/.nvm" 2>/dev/null; true'
    fi
    run "安装 Node 22 (nvm)" '. "$HOME/.nvm/nvm.sh" && nvm install 22 && nvm use 22'
  fi
else
  run "安装 Node 22 (nvm)" 'git clone --depth 1 https://github.com/nvm-sh/nvm.git "$HOME/.nvm" 2>/dev/null; . "$HOME/.nvm/nvm.sh" && nvm install 22 && nvm use 22'
fi

if have tmux; then ok "tmux $(tmux -V 2>/dev/null || echo '?')"
else run "安装 tmux" 'pkg_install tmux'; fi

if have python3; then ok "python3 $(python3 -V 2>/dev/null)"
else run "安装 python3" 'pkg_install python3'; fi

# ---------- 2. OpenRig ----------
if have rig; then
  ok "OpenRig $(rig --version 2>/dev/null | head -1)"
else
  run "安装 @openrig/cli" 'npm install -g @openrig/cli'
fi

# ---------- 3. Provider 认证（至少一个）----------
AUTH_OK=0
if have codex && codex login status 2>&1 | grep -qi "logged in"; then
  ok "Codex 已认证"; AUTH_OK=1
else
  act "Codex 未认证：运行 codex login（pm/review 席需要）"
  ACTIONS=$((ACTIONS+1))
fi
if [ -f "$HOME/.claude/.credentials.json" ] || [ -n "${ANTHROPIC_AUTH_TOKEN:-}" ]; then
  ok "Claude 认证可用"; AUTH_OK=1
else
  skip "Claude 未认证（可选；build 席将退回 codex）"
fi
[ "$AUTH_OK" = "0" ] && { fail "没有任何可用的 provider 认证"; ACTIONS=$((ACTIONS+1)); }

# ---------- 4. Plane ----------
PLANE_STATE="unknown"
if curl -s -o /dev/null -m 5 "$PLANE_URL/health/"; then
  ok "Plane 可达 ($PLANE_URL)"; PLANE_STATE="up"
else
  if [ "$DEPLOY_PLANE" = "1" ] && have docker; then
    run "部署 Plane（官方 compose，约 3-5 分钟）" \
      'git clone --depth 1 https://github.com/makeplane/plane.git /tmp/plane-deploy && cd /tmp/plane-deploy && ./setup.sh launcher'
    PLANE_STATE="deploying"
  else
    act "Plane 不可达。两种选择：a) 重跑并加 --deploy-plane 自动部署；b) 已有实例则 export PLANE_URL=<地址>"
    ACTIONS=$((ACTIONS+1))
    PLANE_STATE="down"
  fi
fi

# ---------- 5. API key + 项目自举 ----------
if [ "$PLANE_STATE" = "up" ] && [ "$DRY_RUN" != "1" ]; then
  if [ -z "${PLANE_API_KEY:-}" ]; then
    printf '\n%s\n%s\n' "需要 Plane API token（在 $PLANE_URL/workspace/<slug>/settings/api-tokens 生成）" "粘贴 token 后回车: "
    read -r KEY </dev/tty || read -r KEY
    if [ -n "$KEY" ]; then
      if curl -s -m 8 -H "X-API-Key: $KEY" "$PLANE_URL/api/v1/users/me/" | grep -q '"id"'; then
        mkdir -p "$SECRETS_DIR"; printf '%s' "$KEY" > "$SECRETS_DIR/plane-api-key"; chmod 600 "$SECRETS_DIR/plane-api-key"
        PLANE_API_KEY="$KEY"; ok "Plane token 验证通过，已存 $SECRETS_DIR/plane-api-key"
      else
        fail "token 验证失败"; ACTIONS=$((ACTIONS+1))
      fi
    fi
  else
    ok "PLANE_API_KEY 已在环境"
  fi

  if [ -n "${PLANE_API_KEY:-}" ]; then
    WS="${WS_SLUG}"
    EXIST=$(curl -s -m 8 -H "X-API-Key: $PLANE_API_KEY" "$PLANE_URL/api/v1/workspaces/$WS/projects/" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(next((p['id'] for p in d.get('results',[]) if p.get('identifier')=='OPENTEA'),''))
except Exception: print('')")
    if [ -n "$EXIST" ]; then
      ok "Plane 项目 OPENTEA 已存在 ($EXIST)"
    else
      run "自动创建 Plane 项目 OPENTEA + 5 个规范标签" \
        'KEY="$PLANE_API_KEY" WS="$WS" PLANE_URL="$PLANE_URL" REPO_DIR="$REPO_DIR" sh "$REPO_DIR/tools/bootstrap-plane.sh"'
    fi
  fi
fi

# ---------- 6. 凭据脚手架 ----------
if [ ! -f "$SECRETS_DIR/daemon.env" ] && [ "$DRY_RUN" != "1" ]; then
  mkdir -p "$SECRETS_DIR"
  cat > "$SECRETS_DIR/daemon.env" <<EOF
# opentea daemon 环境凭据 — source 后再 rig daemon start
export PLANE_API_KEY="\$(cat "$SECRETS_DIR/plane-api-key" 2>/dev/null)"
export PLANE_URL="$PLANE_URL"
# 可选：Claude 席（标准 OAuth 则不需要）
# export ANTHROPIC_BASE_URL=... ; export ANTHROPIC_AUTH_TOKEN=...
EOF
  chmod 700 "$SECRETS_DIR"; chmod 600 "$SECRETS_DIR/daemon.env" 2>/dev/null
  ok "凭据脚手架 $SECRETS_DIR/daemon.env"
fi

# ---------- 7. tea 命令 + 看门狗 ----------
if [ "$DRY_RUN" != "1" ]; then
  chmod +x "$REPO_DIR/tools/tea" 2>/dev/null
  TEA_TARGET="${TEA_BIN_DIR:-$HOME/.local/bin}"
  mkdir -p "$TEA_TARGET"
  ln -sf "$REPO_DIR/tools/tea" "$TEA_TARGET/tea" && \
    ok "tea 命令已装（$TEA_TARGET/tea）— 确保该目录在 PATH 中"
fi
if [ "$DRY_RUN" != "1" ] && [ "$(uname)" = "Darwin" ]; then
  PLIST="$HOME/Library/LaunchAgents/dev.opentea.ready-watchdog.plist"
  sed -e "s|__REPO_DIR__|$REPO_DIR|g" -e "s|__SECRETS_DIR__|$SECRETS_DIR|g" \
    "$REPO_DIR/tools/ready-watchdog.plist.template" > "$PLIST" 2>/dev/null && {
    launchctl bootout "gui/$(id -u)/dev.opentea.ready-watchdog" 2>/dev/null
    launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null && ok "看门狗已注册（launchd，3 分钟周期）"
  } || skip "看门狗注册跳过（plist 模板缺失或非 macOS）"
fi

# ---------- 8. 最终校验 ----------
printf '\n== 校验 ==\n'
if have rig; then
  rig doctor 2>/dev/null | grep -E "^\s+\[(OK|FAIL)\]" | sed 's/^/  /' | head -12
else
  skip "rig 未安装，跳过 doctor"
fi

printf '\n== 结论 ==\n'
if [ "$ACTIONS" -eq 0 ] && [ "$PLANE_STATE" != "down" ]; then
  printf '\033[32mREADY\033[0m — 启动团队: source %s/daemon.env && rig daemon start && rig up rig.yaml --cwd <你的项目>\n' "$SECRETS_DIR"
  exit 0
elif [ "$PLANE_STATE" = "deploying" ]; then
  printf '\033[33mREADY_WITH_LIMITATIONS\033[0m — Plane 部署中，完成后重跑 ./install.sh 完成自举\n'
  exit 0
else
  printf '\033[31mNEEDS_ATTENTION\033[0m — 还有 %s 项需要处理（见上方 [ACTION]/[FAIL]）\n' "$ACTIONS"
  exit 1
fi
