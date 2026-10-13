#!/usr/bin/env python3
"""导出 OpenTea 当前周 Done 票 Markdown 周报。只读：对 Plane 仅发 GET，只写输出文件。

用法（仓库根 opentea/ 下）:
  python3 tools/export_weekly_report.py                 # 默认输出 reports/week.md
  python3 tools/export_weekly_report.py --output PATH   # 覆盖输出路径

当前周 = Asia/Shanghai 本周一 00:00 至执行时刻；仅收 Done 且 completed_at 落窗的票。
证据评论 = HTML 含 <strong>REVIEW</strong> 或 <strong>结论</strong> 的最新 ≤2 条（新→旧）。
认证: 环境变量 PLANE_API_KEY 优先，缺失时回退 ~/ai-plan/openrig/.secrets/plane-api-key。
退出码: 0 成功  2 出错（网络/认证/写文件）
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import urllib.request

PLANE_API = "http://localhost/api/v1/workspaces/ai-plan"
PROJECT_ID = "884817bb-df58-447b-829f-f87eaf7f0378"
WEB_BASE = "http://localhost/ai-plan/projects/" + PROJECT_ID + "/issues"
SECRETS = Path.home() / "ai-plan/openrig/.secrets/plane-api-key"
TZ_SH = timezone(timedelta(hours=8))  # Asia/Shanghai：1991 年后无夏令时，固定偏移
DONE_STATE = "Done"
EVIDENCE_MARKERS = ("<strong>REVIEW</strong>", "<strong>结论</strong>")
MAX_EVIDENCE = 2
TIMEOUT = 10


def api_key():
    key = os.environ.get("PLANE_API_KEY", "").strip()
    if key:
        return key
    try:
        return SECRETS.read_text(encoding="utf-8").strip()
    except OSError:
        raise ValueError("PLANE_API_KEY not set and secrets file missing: " + str(SECRETS))


def api_get(path):
    req = urllib.request.Request(PLANE_API + path,
                                 headers={"X-API-Key": api_key()}, method="GET")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def fetch_all(path):
    """GET 列表端点并跟随 next_cursor 翻页，返回拼接后的 results。"""
    rows, cursor = [], None
    while True:
        p = path
        if cursor:
            p += ("&" if "?" in p else "?") + "cursor=" + cursor
        data = api_get(p)
        rows.extend(data.get("results", []))
        if data.get("next_page_results") and data.get("next_cursor"):
            cursor = data["next_cursor"]
        else:
            return rows


def fetch_issues():
    return fetch_all("/projects/%s/issues/" % PROJECT_ID)


def fetch_states():
    return fetch_all("/projects/%s/states/" % PROJECT_ID)


def fetch_comments(issue_id):
    return fetch_all("/projects/%s/issues/%s/comments/" % (PROJECT_ID, issue_id))


# ---------- 纯函数核心（时间窗 / 过滤 / 证据 / 渲染） ----------

def parse_ts(value):
    """UTC ISO-8601 → aware datetime；缺失或不可解析返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        return None
    return stamp


def week_window(now):
    """now（aware）所在周的 Asia/Shanghai 周一 00:00 → (start, end=now 的本地时刻)。"""
    local = now.astimezone(TZ_SH)
    start = (local - timedelta(days=local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0)
    return start, local


def in_window(completed_at, start, end):
    stamp = parse_ts(completed_at)
    return stamp is not None and start <= stamp <= end


def format_sh(stamp):
    return stamp.astimezone(TZ_SH).strftime("%Y-%m-%d %H:%M") + " Asia/Shanghai"


def issue_url(issue_id):
    return WEB_BASE + "/" + issue_id


def comment_url(issue_id, comment_id):
    return issue_url(issue_id) + "#comment-" + comment_id


def evidence_comments(comments):
    """按冻结标记筛选，创建时间倒序，取最新 MAX_EVIDENCE 条。"""
    matched = [c for c in comments
               if any(m in (c.get("comment_html") or "") for m in EVIDENCE_MARKERS)]
    matched.sort(key=lambda c: parse_ts(c.get("created_at")) or
                 datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return matched[:MAX_EVIDENCE]


def build_report(now=None, fetch_issues=fetch_issues, fetch_states=fetch_states,
                 fetch_comments=fetch_comments):
    """采集并渲染周报文本。fetch_* 默认绑定模块函数，测试可传替身；now 为 None 取当前时刻。"""
    if now is None:
        now = datetime.now(timezone.utc)
    start, end = week_window(now)
    done_ids = {s["id"] for s in fetch_states() if s.get("name") == DONE_STATE}
    sections = []
    for issue in fetch_issues():
        if issue.get("state") not in done_ids:
            continue
        if not in_window(issue.get("completed_at"), start, end):
            continue
        issue_id = issue["id"]
        evidence = [comment_url(issue_id, c["id"])
                    for c in evidence_comments(fetch_comments(issue_id))]
        sections.append({
            "title": issue.get("name", "(untitled)"),
            "completed_at": parse_ts(issue["completed_at"]),
            "url": issue_url(issue_id),
            "evidence": evidence,
        })
    sections.sort(key=lambda s: s["completed_at"])
    return render(sections, start, end)


def render(sections, start, end):
    lines = ["# OpenTea Weekly Done Report", "",
             "Window: %s – %s" % (format_sh(start), format_sh(end)), ""]
    for section in sections:
        lines += ["## " + section["title"], "",
                  "- Completed: " + format_sh(section["completed_at"]),
                  "- Issue: " + section["url"]]
        if section["evidence"]:
            lines.append("- Evidence:")
            lines += ["  - " + url for url in section["evidence"]]
        lines.append("")
    return "\n".join(lines)


def write_report(text, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as out:
        out.write(text)
    return path


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="reports/week.md",
                        help="output path (default: reports/week.md, relative to CWD)")
    args = parser.parse_args(argv)
    try:
        # 显式传模块级函数：调用时解析全局名，测试替换 mod.fetch_* 即可作用于完整路径
        text = build_report(fetch_issues=fetch_issues, fetch_states=fetch_states,
                            fetch_comments=fetch_comments)
        path = write_report(text, args.output)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        emit({"status": "ERROR", "reason": str(exc)})
        return 2
    emit({"status": "OK", "output": str(path)})
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main())
