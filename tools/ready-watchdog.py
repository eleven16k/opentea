#!/usr/bin/env python3
"""opentea Ready 看门狗 — 确定性轮询 Plane，发现可领票时唤醒 builder 席。

设计原则（脚手架 §8）：轻量周期检查兜底，只在有可执行变化时调用 agent。
本脚本不消耗任何 LLM 额度；rig send 的启动成本由发现的票数证明其必要性。

用法:
  python3 ready-watchdog.py            # 单次检查（launchd 周期调用）
  python3 ready-watchdog.py --once     # 同上，显式
退出码: 0 无票/已踢过  1 踢了 builder  2 出错
状态文件: ~/.openrig/opentea-watchdog.state（记录已踢过的票，防重复唤醒）
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

SECRETS = Path.home() / "ai-plan/openrig/.secrets"
STATE_FILE = Path.home() / ".openrig/opentea-watchdog.state"
PLANE = "http://localhost/api/v1/workspaces/ai-plan"
PROJECT_ID = "884817bb-df58-447b-829f-f87eaf7f0378"
TARGET_SEAT = "dev-build@opentea"
RIG = "opentea"
# 候选票 = 打了 ready-for-agent、无 assignee、state 不在终态
READY_LABEL = "ready-for-agent"
DONE_STATES = {"Done", "Cancelled"}


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def api_get(path):
    key = (SECRETS / "plane-api-key").read_text().strip()
    req = urllib.request.Request(
        f"{PLANE}{path}", headers={"X-API-Key": key}, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def rig_alive():
    """daemon 和目标 seat 都活着才值得踢。"""
    import subprocess
    try:
        out = subprocess.run(
            ["rig", "ps", "--nodes", "--rig", RIG],
            capture_output=True, text=True, timeout=20)
        for line in out.stdout.splitlines():
            if TARGET_SEAT in line and " run " in line:
                return True
        return False
    except Exception:
        return False


def load_state():
    if STATE_FILE.exists():
        return set(STATE_FILE.read_text().split())
    return set()


def save_state(kicked):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text("\n".join(sorted(kicked)))


def find_ready_tickets():
    labels = api_get(f"/projects/{PROJECT_ID}/labels/").get("results", [])
    ready_id = next((l["id"] for l in labels if l["name"] == READY_LABEL), None)
    if not ready_id:
        return []
    states = {s["id"]: s["name"]
              for s in api_get(f"/projects/{PROJECT_ID}/states/").get("results", [])}
    tickets = []
    for issue in api_get(f"/projects/{PROJECT_ID}/issues/").get("results", []):
        label_ids = issue.get("labels") or []
        if ready_id not in label_ids:
            continue
        if issue.get("assignees"):
            continue
        if states.get(issue.get("state"), "") in DONE_STATES:
            continue
        tickets.append((issue["id"], issue.get("name", "?")))
    return tickets


def kick(ticket_id, name):
    import subprocess
    msg = (f"看门狗发现 Ready 票 {ticket_id[:8]}「{name}」，"
           f"请按 AGENTS.md 工作流检查 Plane Ready 队列并领取执行。")
    r = subprocess.run(["rig", "send", TARGET_SEAT, msg],
                       capture_output=True, text=True, timeout=30)
    ok = r.returncode == 0
    log(f"kick {TARGET_SEAT}: {'已发送' if ok else '失败 ' + r.stderr[:120]}")
    return ok


def main():
    try:
        tickets = find_ready_tickets()
    except Exception as e:
        log(f"ERROR 查询 Plane 失败: {e}")
        return 2
    if not tickets:
        return 0
    state = load_state()
    fresh = [(i, n) for i, n in tickets if i not in state]
    if not fresh:
        return 0
    if not rig_alive():
        log(f"发现 {len(fresh)} 张 Ready 票但 {TARGET_SEAT} 不在线，跳过（rig 未起或 seat 异常）")
        return 0
    kicked = False
    for tid, name in fresh:
        log(f"发现 Ready 票: {name}")
        if kick(tid, name):
            state.add(tid)
            save_state(state)
            kicked = True
            time.sleep(2)
    return 1 if kicked else 0


if __name__ == "__main__":
    sys.exit(main())
