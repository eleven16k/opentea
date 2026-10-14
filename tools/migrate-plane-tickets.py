#!/usr/bin/env python3
"""migrate-plane-tickets.py — 把旧 Plane 实例的项目数据搬到新实例。

只读源实例；目标实例需已部署并有一个空项目（或 --create 自动建 OPENTEA）。
搬运范围：labels（按名映射）→ issues（正文/优先级/状态按名映射）→ comments（HTML 原样，保序）。
明确不搬运（诚实边界）：附件、assignees（跨实例身份不同）、自定义 state（需 --state-map 显式映射）。

用法（仓库根 opentea/ 下）:
  export SRC_PLANE_URL=http://localhost SRC_API_KEY=<旧实例token> SRC_PROJECT_ID=<旧项目id>
  export DST_PLANE_URL=https://plane.example.com DST_API_KEY=<新token>
  python3 tools/migrate-plane-tickets.py --dry-run     # 只统计将搬什么
  python3 tools/migrate-plane-tickets.py               # 执行
  python3 tools/migrate-plane-tickets.py --create      # 目标没有项目时自动建 OPENTEA
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def api(url, key, path, method="GET", body=None, retries=2):
    req = urllib.request.Request(
        url + path,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
        method=method,
        data=json.dumps(body).encode() if body is not None else None)
    last = None
    for _ in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return json.loads(raw) if raw else {}
        except json.JSONDecodeError as e:
            last = e  # 空响应（实例偶发），退避重试
            time.sleep(2)
    raise last


def fetch_all(url, key, path):
    """分页协议：next_page_results=False 终止；cursor 原样回传。"""
    items, cursor, seen = [], None, set()
    for _ in range(100):
        d = api(url, key, f"{path}?cursor={cursor}" if cursor else path)
        items += d.get("results", [])
        if d.get("next_page_results") and d.get("next_cursor") and d["next_cursor"] not in seen:
            seen.add(d["next_cursor"])
            cursor = d["next_cursor"]
        else:
            return items
    sys.stderr.write("[migrate] 分页护栏触发，结果可能不完整\n")
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--create", action="store_true",
                    help="目标实例无项目时自动创建 OPENTEA + 标签")
    a = ap.parse_args()

    src = {"url": os.environ["SRC_PLANE_URL"], "key": os.environ["SRC_API_KEY"],
           "pid": os.environ["SRC_PROJECT_ID"]}
    dst = {"url": os.environ["DST_PLANE_URL"], "key": os.environ["DST_API_KEY"]}
    # 补全 API 前缀：BASE_URL 只是根，真正端点在 /api/v1/workspaces/<slug> 下
    ws = lambda base, slug_env: base.rstrip("/") + "/api/v1/workspaces/" + \
        os.environ.get(slug_env, "ai-plan")
    src = {"url": ws(os.environ["SRC_PLANE_URL"], "SRC_WORKSPACE_SLUG"),
           "key": os.environ["SRC_API_KEY"],
           "pid": os.environ["SRC_PROJECT_ID"]}
    dst = {"url": ws(os.environ["DST_PLANE_URL"], "DST_WORKSPACE_SLUG"),
           "key": os.environ["DST_API_KEY"]}
    # 目标项目 id：环境变量优先，否则读仓库 plane/project.json
    dst["pid"] = os.environ.get("DST_PROJECT_ID")
    if not dst["pid"]:
        pj = Path(__file__).resolve().parents[1] / "plane/project.json"
        dst["pid"] = json.load(open(pj)).get("id", "")
    if not dst["pid"] or dst["pid"].startswith("<"):
        if not a.create:
            sys.exit("目标项目 id 未配置：传 DST_PROJECT_ID 或加 --create")
        pid = api(dst["url"], dst["key"], "/projects/", "POST",
                  {"name": "OpenTea", "identifier": "OPENTEA",
                   "description": "opentea multi-agent dev system"}).get("id")
        if not pid:
            sys.exit("目标项目创建失败")
        for name, desc in [("needs-triage", "待评估"), ("needs-info", "等补充"),
                           ("ready-for-agent", "agent 可领取"),
                           ("ready-for-human", "需人来做"), ("wontfix", "不做")]:
            api(dst["url"], dst["key"], f"/projects/{pid}/labels/", "POST",
                {"name": name, "description": desc, "color": "#6b7280"})
        dst["pid"] = pid
        print(f"目标项目已创建: OPENTEA ({pid})")

    # 1) 源数据
    src_labels = {l["name"]: l for l in
                  fetch_all(src["url"], src["key"], f"/projects/{src['pid']}/labels/")}
    src_states = {s["id"]: s["name"] for s in
                  fetch_all(src["url"], src["key"], f"/projects/{src['pid']}/states/")}
    issues = fetch_all(src["url"], src["key"], f"/projects/{src['pid']}/issues/")
    total_comments = sum(len(fetch_all(src["url"], src["key"],
                          f"/projects/{src['pid']}/issues/{i['id']}/comments/"))
                         for i in issues)
    print(f"将搬运: {len(issues)} 张票, {total_comments} 条 comment, {len(src_labels)} 个标签")
    if a.dry_run:
        for i in issues:
            print(f"  - [{src_states.get(i.get('state'),'?')}] {i.get('name','?')}")
        return 0

    # 2) 目标侧映射准备
    dst_labels = {l["name"]: l["id"] for l in
                  fetch_all(dst["url"], dst["key"], f"/projects/{dst['pid']}/labels/")}
    dst_states = {s["name"]: s["id"] for s in
                  fetch_all(dst["url"], dst["key"], f"/projects/{dst['pid']}/states/")}
    root = Path(__file__).resolve().parents[1] / "plane/project.json"
    dst_web = json.load(open(root)).get("id", dst["pid"])

    moved = 0
    for i in issues:
        body = {
            "name": i.get("name", "?"),
            "description_html": i.get("description_html", "<p></p>"),
            "priority": i.get("priority") or "none",
            "completed_at": i.get("completed_at"),
        }
        state_name = src_states.get(i.get("state"), "")
        if state_name in dst_states:
            body["state"] = dst_states[state_name]
        lbl_ids = [dst_labels[l["name"]] for l in (i.get("labels") or [])
                   if isinstance(l, dict) and l.get("name") in dst_labels]
        if lbl_ids:
            body["labels"] = lbl_ids
        new = api(dst["url"], dst["key"], f"/projects/{dst['pid']}/issues/", "POST", body)
        if not new.get("id"):
            print(f"  ✗ 建票失败: {body['name']}")
            continue
        moved += 1
        time.sleep(0.4)
        for c in reversed(fetch_all(src["url"], src["key"],
                          f"/projects/{src['pid']}/issues/{i['id']}/comments/")):
            api(dst["url"], dst["key"],
                f"/projects/{dst['pid']}/issues/{new['id']}/comments/", "POST",
                {"comment_html": c.get("comment_html", "<p></p>")})
            time.sleep(0.2)
        print(f"  ✓ [{state_name}] {body['name']} → {new['id'][:8]}")

    print(f"\n完成: {moved}/{len(issues)} 张票已迁移至 {dst['url']}")
    print(f"把 plane/project.json 的 id 更新为 {dst['pid']}，"
          f"并同步更新 issue-tracker.md 的 base_url 与凭据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
