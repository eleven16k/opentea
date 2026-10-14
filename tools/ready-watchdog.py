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
import os
import sys
import time
import urllib.request
from pathlib import Path

REPO_DIR = Path(os.environ.get("OT_REPO_DIR", Path(__file__).resolve().parents[1]))
SECRETS = Path(os.environ.get("OT_SECRETS_DIR",
                              Path.home() / "ai-plan/openrig/.secrets"))
STATE_FILE = Path.home() / ".openrig/opentea-watchdog.state"
PLANE = os.environ.get("PLANE_URL", "http://localhost") + "/api/v1/workspaces/ai-plan"


def _project_id():
    """从 plane/project.json 读取；占位符或缺失时明确报错，不猜。"""
    override = os.environ.get("OT_PROJECT_ID")
    if override:
        return override
    pj = REPO_DIR / "plane/project.json"
    try:
        pid = json.load(open(pj)).get("id", "")
    except Exception:
        pid = ""
    if not pid or pid.startswith("<"):
        sys.stderr.write(
            f"[watchdog] plane/project.json 的 id 未配置（当前: {pid!r}）。"
            f"运行 install.sh 或手动填入实际 project_id。\n")
        sys.exit(2)
    return pid


PROJECT_ID = _project_id()
TARGET_SEAT = "dev-build@opentea"
RIG = "opentea"
# 候选票 = 打了 ready-for-agent、无 assignee、state 不在终态
READY_LABEL = "ready-for-agent"
DONE_STATES = {"Done", "Cancelled"}
REVIEW_SEAT = os.environ.get("OT_REVIEW_SEAT", "review-review@opentea")
# 本机看门狗管哪些队列：all（默认）| ready | review
# 多机部署时按角色拆分：A 机设 ready，B 机设 review，避免双机同审
QUEUE = os.environ.get("OT_QUEUE", "all")


def log(msg):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def api_get(path, params=""):
    key = (SECRETS / "plane-api-key").read_text().strip()
    url = f"{PLANE}{path}"
    if params:
        url = f"{url}?{params}"
    req = urllib.request.Request(url, headers={"X-API-Key": key}, method="GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def fetch_all_issues():
    """跨分页拉全量票——只取第一页会静默漏掉后排的 ready 票。
    本版 Plane：默认页大小 1000，终止信号是 next_page_results=False；
    盲目回传 next_cursor 会得到空页，故仅在服务端声明还有下一页时翻页。"""
    issues, cursor, seen = [], None, set()
    for _ in range(50):  # 死循环护栏
        d = api_get(f"/projects/{PROJECT_ID}/issues/",
                    f"cursor={cursor}" if cursor else "")
        page = d.get("results", []) if isinstance(d, dict) else []
        issues += page
        if isinstance(d, dict) and d.get("next_page_results") and d.get("next_cursor"):
            cursor = d["next_cursor"]
            if cursor in seen:
                break
            seen.add(cursor)
        else:
            return issues
    sys.stderr.write("[watchdog] 分页超过护栏，结果可能不完整\n")
    return issues


def seat_alive(seat):
    """指定席位的 tmux 会话处于 run 态才值得踢。"""
    import subprocess
    try:
        out = subprocess.run(
            ["rig", "ps", "--nodes", "--rig", RIG],
            capture_output=True, text=True, timeout=20)
        return any(seat in line and " run " in line
                   for line in out.stdout.splitlines())
    except Exception:
        return False


def rig_alive():
    return seat_alive(TARGET_SEAT)


def find_in_review_tickets():
    """In Review 且未指派审核者的票（审核席领取后 assignees 非空即跳过）。"""
    states = {s["id"]: s["name"]
              for s in api_get(f"/projects/{PROJECT_ID}/states/").get("results", [])}
    review_state = next((sid for sid, n in states.items() if n == "In Review"), None)
    if not review_state:
        return []
    tickets = []
    for issue in fetch_all_issues():
        if issue.get("state") != review_state:
            continue
        if issue.get("assignees"):
            continue
        tickets.append((issue["id"], issue.get("name", "?")))
    return tickets


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
    for issue in fetch_all_issues():
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
    if QUEUE not in ("all", "ready", "review"):
        log(f"ERROR OT_QUEUE 非法: {QUEUE}（应为 all|ready|review）")
        return 2
    try:
        tickets = find_ready_tickets() if QUEUE in ("all", "ready") else []
    except Exception as e:
        log(f"ERROR 查询 Plane 失败: {e}")
        return 2
    state = load_state()
    kicked_any = False
    # ① Ready 票 → 踢 build 席
    if tickets:
        fresh = [(i, n) for i, n in tickets if f"ready:{i}" not in state]
        if not fresh:
            pass
        elif not rig_alive():
            log(f"发现 {len(fresh)} 张 Ready 票但 {TARGET_SEAT} 不在线，跳过（rig 未起或 seat 异常）")
        else:
            for tid, name in fresh:
                log(f"发现 Ready 票: {name}")
                if kick(TARGET_SEAT, f"看门狗发现 Ready 票 {tid[:8]}「{name}」，请按 AGENTS.md 工作流检查 Plane Ready 队列并领取执行。"):
                    state.add(f"ready:{tid}")
                    save_state(state)
                    kicked_any = True
                    time.sleep(2)
    # ② In Review 票 → 踢 review 席（同一防重逻辑）
    if QUEUE not in ("all", "review"):
        return 1 if kicked_any else 0
    try:
        in_review = find_in_review_tickets()
    except Exception as e:
        log(f"ERROR 查询 In Review 失败: {e}")
        in_review = []
    fresh_rev = [(i, n) for i, n in in_review if f"rev:{i}" not in state]
    if fresh_rev and seat_alive(REVIEW_SEAT):
        for tid, name in fresh_rev:
            log(f"发现 In Review 票: {name}")
            if kick(REVIEW_SEAT, f"看门狗发现 In Review 票 {tid[:8]}「{name}」，请按独立审核规程拉取并核对。"):
                state.add(f"rev:{tid}")
                save_state(state)
                kicked_any = True
                time.sleep(2)
    return 1 if kicked_any else 0


if __name__ == "__main__":
    sys.exit(main())
