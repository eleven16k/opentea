"""export_weekly_report 的 AC 边界测试。运行：仓库根 opentea/ 下
python3 -m unittest discover -s tests
"""
import http.server
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

BASE = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj

exp = module('export_weekly_report', BASE / 'tools' / 'export_weekly_report.py')

# 保存模块原函数：main 路径测试 monkeypatch 后必须 setattr 还原（delattr 会真删掉）
ORIG = {name: getattr(exp, name)
        for name in ("fetch_states", "fetch_issues", "fetch_comments")}


def patch_and_restore(exp, states, issues, comments):
    exp.fetch_states, exp.fetch_issues, exp.fetch_comments = states, issues, comments
    def restore():
        exp.fetch_states = ORIG["fetch_states"]
        exp.fetch_issues = ORIG["fetch_issues"]
        exp.fetch_comments = ORIG["fetch_comments"]
    return restore

SH = timezone(timedelta(hours=8))
# 固定"现在"：2026-10-14 周三 10:00 Asia/Shanghai → 本周一是 2026-10-12 00:00 +08
NOW = datetime(2026, 10, 14, 10, 0, 0, tzinfo=SH)
ISSUE_ID = "906cc4b422264aa385d93df288523e1f"
MONDAY_00 = "2026-10-12T00:00:00+08:00"
SUNDAY_LAST = "2026-10-11T15:59:59Z"          # = 周日 23:59:59 +08，上周期
TEA1_DONE = "2026-10-13T12:49:16.741356Z"     # → 2026-10-13 20:49 Asia/Shanghai
DONE = "done-state-uuid"
TODO = "todo-state-uuid"


def issue(iid=ISSUE_ID, state=DONE, completed=TEA1_DONE, name="TEA-1: 回归验证"):
    return {"id": iid, "name": name, "state": state, "completed_at": completed}


def states_fetch(*_):
    return [{"id": DONE, "name": "Done"}, {"id": TODO, "name": "Todo"}]


def no_comments(_issue_id):
    return []


class AC01BoundaryTests(unittest.TestCase):
    def test_week_window_monday_boundary(self):
        start, end = exp.week_window(NOW)
        self.assertEqual(start, datetime(2026, 10, 12, 0, 0, 0, tzinfo=SH))
        self.assertEqual(end, NOW)

    def test_boundary_inclusive_and_exclusive(self):
        start, end = exp.week_window(NOW)
        self.assertTrue(exp.in_window(MONDAY_00, start, end))          # 周一 00:00 整点入窗
        self.assertFalse(exp.in_window(SUNDAY_LAST, start, end))       # 上周期最后 1 秒出窗
        self.assertTrue(exp.in_window("2026-10-14T02:00:00Z", start, end))  # == 执行时刻入窗
        self.assertFalse(exp.in_window("2026-10-14T02:00:01Z", start, end)) # 晚于执行时刻出窗

    def test_filter_requires_done_state_and_parseable_completed_at(self):
        text = exp.build_report(
            NOW, fetch_states=states_fetch,
            fetch_issues=lambda: [
                issue(),                                   # Done + 落窗 → 收
                issue(state=TODO),                         # 非 Done → 排除
                issue(completed=None),                     # completed_at 缺失 → 排除
                issue(completed="not-a-date"),             # 不可解析 → 排除
                issue(completed=SUNDAY_LAST),              # Done 但上周期 → 排除
                issue(iid="x", completed=MONDAY_00),       # Done + 边界整点 → 收
            ],
            fetch_comments=no_comments)
        self.assertIn("TEA-1: 回归验证", text)
        self.assertEqual(text.count("\n## "), 2)


class AC02ReportTests(unittest.TestCase):
    def test_section_contains_title_and_formatted_time(self):
        text = exp.build_report(NOW, fetch_states=states_fetch,
                                fetch_issues=lambda: [issue()],
                                fetch_comments=no_comments)
        self.assertIn("## TEA-1: 回归验证", text)
        self.assertIn("- Completed: 2026-10-13 20:49 Asia/Shanghai", text)

    def test_default_output_creates_reports_week_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            restore = patch_and_restore(exp, states_fetch, lambda: [issue()], no_comments)
            try:
                code = exp.main([])
                self.assertEqual(code, 0)
                out = Path(tmp) / "reports" / "week.md"
                self.assertTrue(out.is_file())
                self.assertIn("## TEA-1: 回归验证", out.read_text(encoding="utf-8"))
            finally:
                os.chdir(old)
                restore()


class AC03EvidenceTests(unittest.TestCase):
    def test_two_newest_matching_links_newest_first(self):
        comments = [
            {"id": "old", "created_at": "2026-10-12T01:00:00Z",
             "comment_html": "<p><strong>REVIEW</strong> old pass</p>"},
            {"id": "noise", "created_at": "2026-10-12T02:00:00Z", "comment_html": "<p>闲聊</p>"},
            {"id": "mid", "created_at": "2026-10-13T09:00:00Z",
             "comment_html": "<p><strong>结论</strong>：一致</p>"},
            {"id": "new", "created_at": "2026-10-13T12:49:16Z",
             "comment_html": "<strong>REVIEW</strong> PASS"},
            {"id": "noise2", "created_at": "2026-10-13T13:00:00Z", "comment_html": "<b>PM复核</b>"},
            {"id": "new2", "created_at": "2026-10-13T14:00:00Z",
             "comment_html": "<strong>REVIEW</strong> second"},
        ]
        text = exp.build_report(NOW, fetch_states=states_fetch,
                                fetch_issues=lambda: [issue()],
                                fetch_comments=lambda _i: comments)
        expected = [
            exp.WEB_BASE + "/" + ISSUE_ID + "#comment-new2",
            exp.WEB_BASE + "/" + ISSUE_ID + "#comment-new",
        ]
        for url in expected:
            self.assertIn("  - " + url, text)
        self.assertNotIn("#comment-mid", text)     # 第 3 新被截断
        self.assertNotIn("#comment-old", text)
        self.assertNotIn("#comment-noise", text)   # 非证据评论永不出现
        # 恰好一条 issue 链接（证据链接带 #comment- 片段，不与其互计）
        self.assertEqual(text.count("- Issue: " + exp.WEB_BASE + "/" + ISSUE_ID), 1)
        self.assertEqual(text.count("- Evidence:"), 1)
        self.assertEqual(text.count("  - " + exp.WEB_BASE + "/" + ISSUE_ID + "#comment-"), 2)
        lines = text.splitlines()                  # 按整行定位，避免 URL 前缀互为子串
        self.assertLess(lines.index("  - " + expected[0]),
                        lines.index("  - " + expected[1]))  # 顺序：新→旧

    def test_fewer_when_fewer_exist(self):
        comments = [{"id": "only", "created_at": "2026-10-13T00:00:00Z",
                     "comment_html": "<strong>结论</strong>"}]
        text = exp.build_report(NOW, fetch_states=states_fetch,
                                fetch_issues=lambda: [issue()],
                                fetch_comments=lambda _i: comments)
        self.assertIn(exp.WEB_BASE + "/" + ISSUE_ID + "#comment-only", text)
        self.assertEqual(text.count("#comment-"), 1)

    def test_issue_link_frozen_format_exactly_once(self):
        text = exp.build_report(NOW, fetch_states=states_fetch,
                                fetch_issues=lambda: [issue()],
                                fetch_comments=no_comments)
        self.assertEqual(text.count(exp.WEB_BASE + "/" + ISSUE_ID), 1)


class AC04OutputOverrideTests(unittest.TestCase):
    def test_custom_output_never_touches_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            (Path(tmp) / "reports").mkdir()
            default = Path(tmp) / "reports" / "week.md"
            default.write_text("PRE-EXISTING MARKER", encoding="utf-8")
            restore = patch_and_restore(exp, states_fetch, lambda: [issue()], no_comments)
            try:
                code = exp.main(["--output", "reports/custom.md"])
                self.assertEqual(code, 0)
                custom = Path(tmp) / "reports" / "custom.md"
                self.assertTrue(custom.is_file())
                self.assertIn("TEA-1", custom.read_text(encoding="utf-8"))
                self.assertEqual(default.read_text(encoding="utf-8"), "PRE-EXISTING MARKER")
            finally:
                os.chdir(old)
                restore()

    def test_custom_output_in_fresh_dir_creates_only_custom(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = os.getcwd()
            os.chdir(tmp)
            restore = patch_and_restore(exp, states_fetch, lambda: [], no_comments)
            try:
                code = exp.main(["--output", "out/weekly.md"])
                self.assertEqual(code, 0)
                created = sorted(
                    str(p.relative_to(tmp)) for p in Path(tmp).rglob("*") if p.is_file())
                self.assertEqual(created, ["out/weekly.md"])
                self.assertFalse((Path(tmp) / "reports" / "week.md").exists())
            finally:
                os.chdir(old)
                restore()


class AC05ReadOnlyTests(unittest.TestCase):
    def test_only_get_requests_through_real_http_path(self):
        commands = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                commands.append(self.command)
                body = json.dumps({"results": [], "next_page_results": False}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        old_api, old_key = exp.PLANE_API, os.environ.get("PLANE_API_KEY")
        os.environ["PLANE_API_KEY"] = "test-key"
        exp.PLANE_API = "http://127.0.0.1:%d" % server.server_address[1]
        try:
            self.assertEqual(exp.fetch_issues(), [])
            self.assertEqual(exp.fetch_states(), [])
            self.assertEqual(exp.fetch_comments(ISSUE_ID), [])
            self.assertTrue(commands)
            self.assertEqual(set(commands), {"GET"})
        finally:
            exp.PLANE_API = old_api
            if old_key is None:
                del os.environ["PLANE_API_KEY"]
            else:
                os.environ["PLANE_API_KEY"] = old_key
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
