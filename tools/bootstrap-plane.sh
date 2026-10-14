#!/usr/bin/env sh
# bootstrap-plane.sh — 在 Plane 实例中自动创建 OPENTEA 项目与 5 个规范标签
# 需要环境变量: KEY(API token) WS(workspace slug) PLANE_URL REPO_DIR
set -eu
: "${KEY:?missing KEY}" "${WS:?missing WS}" "${PLANE_URL:?missing PLANE_URL}" "${REPO_DIR:?missing REPO_DIR}"

API="$PLANE_URL/api/v1/workspaces/$WS"
H="X-API-Key: $KEY"
CT="Content-Type: application/json"

echo "创建项目 OPENTEA..."
PID=$(curl -sf -m 15 -X POST "$API/projects/" -H "$H" -H "$CT" \
  -d '{"name":"OpenTea","identifier":"OPENTEA","description":"opentea multi-agent dev system"}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin).get('id',''))") || true
[ -n "$PID" ] || { echo "项目创建失败（可能已存在或权限不足）"; exit 1; }
echo "  project_id=$PID"

echo "创建规范标签..."
FAILS=0
for pair in "needs-triage:待评估" "needs-info:等报告人补充" "ready-for-agent:agent 可领取" "ready-for-human:需人来做" "wontfix:不做"; do
  name=${pair%%:*}; desc=${pair##*:}
  code=$(curl -sf -m 10 -X POST "$API/projects/$PID/labels/" -H "$H" -H "$CT" \
    -d "{\"name\":\"$name\",\"description\":\"$desc\",\"color\":\"#6b7280\"}" \
    -o /dev/null -w "%{http_code}") || code="ERR"
  echo "  $name → $code"
  [ "$code" = "201" ] || FAILS=$((FAILS+1))
done
[ "$FAILS" -gt 0 ] && { echo "有 $FAILS 个标签创建失败"; exit 1; }

# 写回 project.json（模板化 → 实际 id）
PJ="$REPO_DIR/plane/project.json"
if [ -f "$PJ" ]; then
  python3 - "$PID" "$PJ" <<'EOF'
import json, sys
pid, path = sys.argv[1], sys.argv[2]
d = json.load(open(path))
d["id"] = pid
d.pop("_comment", None)
json.dump(d, open(path, "w"), ensure_ascii=False, indent=2)
print(f"  project.json 已写入实际 id")
EOF
fi

echo "完成。Plane 项目: $PLANE_URL/$WS/projects/$PID"
