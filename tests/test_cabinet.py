#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "digital-cabinet/scripts/cabinet.py"

class DigitalCabinetTests(unittest.TestCase):
    def test_01_cleanroom_privacy_zero_hits(self) -> None:
        banned = re.compile(
            rb"/(?:Users|home)/[A-Za-z0-9._-]+/|[.]local\b"
            rb"|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}",
            re.I,
        )
        tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
        self.assertTrue(tracked, "No tracked files to scan")
        for name in tracked.split(b"\0")[:-1]:
            path = os.fsdecode(name)
            with self.subTest(path=path):
                self.assertFalse(bool(banned.search((ROOT / path).read_bytes())), "Privacy leak in file contents")

    def test_02_demo_and_diff_sensitivity(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out1 = Path(td) / "demo1"
            subprocess.run([sys.executable, str(SCRIPT), "demo", "--out", str(out1)], check=True)
            st1 = json.loads((out1 / "cabinet-state.json").read_text("utf-8"))
            by_goal = {x["goal"]: x for x in st1["items"]}
            self.assertEqual(by_goal["重构本地缓存读取层"]["badge"], "跨窗口口径打架")
            self.assertIn("已搁置", by_goal["补齐接口超时重试测试"]["badge"])
            self.assertEqual(by_goal["旧版演示页配色微调"]["state"], "dropped")
            self.assertEqual(by_goal["夜间自主推进任务候选"]["state"], "theater_blocked")
            self.assertIn("【内阁拟办】", by_goal["导出周度实验对比表"]["proposal"])

            sess_dir = Path(td) / "sess"
            shutil.copytree(ROOT / "digital-cabinet/examples/synthetic-multi-window", sess_dir)
            with (sess_dir / "sessions.jsonl").open("a", encoding="utf-8") as fh:
                fh.write("{\"window_id\":\"win-04-gemini-doc\",\"tool\":\"Gemini CLI\",\"goal\":\"补齐接口超时重试测试\",\"updated_at\":\"2026-11-22T11:00:00Z\",\"turn\":6,\"role\":\"user\",\"text\":\"超时重试这块不用管，先放放。\"}\n")
            out2 = Path(td) / "demo2"
            subprocess.run([sys.executable, str(SCRIPT), "scan", "--dir", str(sess_dir), "--since-days", "0", "--out", str(out2)], check=True)
            st2 = json.loads((out2 / "cabinet-state.json").read_text("utf-8"))
            by_goal2 = {x["goal"]: x for x in st2["items"]}
            self.assertEqual(by_goal2["补齐接口超时重试测试"]["state"], "dropped")

    def test_03_real_claude_and_codex_jsonl_schemas(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            in_dir = Path(td) / "real_fmt"
            (in_dir / "2026/11").mkdir(parents=True)
            # Claude Code session with multiple cwd changes & an early "先放放" followed by active work
            claude_f = in_dir / "claude-sess-a.jsonl"
            claude_f.write_text("\n".join([
                json.dumps({"type": "user", "cwd": "/proj/root", "message": {"role": "user", "content": "整理商品导出脚本并对齐测试"}}),
                json.dumps({"type": "user", "cwd": "/proj/root/sub1", "message": {"role": "user", "content": "图标微调先放放"}}),
                json.dumps({"type": "user", "cwd": "/proj/root/scripts", "message": {"role": "user", "content": "继续把主流程跑完"}}),
                json.dumps({"type": "assistant", "cwd": "/proj/root/out", "message": {"role": "assistant", "content": "主流程代码已就绪，正在运行回归检查"}}),
            ]), "utf-8")
            # Codex CLI response_item session
            codex_f = in_dir / "2026/11/rollout-codex-without-uuid.jsonl"
            codex_f.write_text("\n".join([
                json.dumps({"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "<environment_context>noise</environment_context>"}]}}),
                json.dumps({"type": "response_item", "payload": {"role": "user", "content": [{"type": "input_text", "text": "帮我检查导出表格里没数据的格子怎么处理"}]}}),
                json.dumps({"type": "response_item", "payload": {"role": "assistant", "content": [{"type": "output_text", "text": "没数据的格子画横线还是留白？这事得你定。"}]}}),
            ]), "utf-8")
            out3 = Path(td) / "out3"
            pb = ROOT / "digital-cabinet/examples/synthetic-multi-window/playbook-seed.md"
            subprocess.run([sys.executable, str(SCRIPT), "scan", "--dir", str(in_dir), "--playbook", str(pb), "--since-days", "0", "--out", str(out3)], check=True)
            st3 = json.loads((out3 / "cabinet-state.json").read_text("utf-8"))
            self.assertEqual(st3["total_goals"], 2)  # NOT 4 cwd junk items, and Codex IS parsed!
            by_g = {x["goal"]: x for x in st3["items"]}
            self.assertEqual(by_g["整理商品导出脚本并对齐测试"]["state"], "in_progress")  # NOT falsely dropped!
            self.assertEqual(by_g["帮我检查导出表格里没数据的格子怎么处理"]["state"], "waiting_owner")
            self.assertIn("【内阁拟办】", by_g["帮我检查导出表格里没数据的格子怎么处理"]["proposal"])
            self.assertEqual(by_g["帮我检查导出表格里没数据的格子怎么处理"]["windows"], [codex_f.stem])


    def test_04_v03_split_lock_zero_rehash_and_pinned_alerts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out1 = Path(td) / "v03_r1"
            subprocess.run([sys.executable, str(SCRIPT), "demo", "--out", str(out1)], check=True)
            st1 = json.loads((out1 / "cabinet-state.json").read_text("utf-8"))
            self.assertEqual(st1["schema_version"], "0.3.0")
            by_g = {x["goal"]: x for x in st1["items"]}
            self.assertEqual(by_g["核算近七天构建慢查询占比"]["state"], "pre_verify_auto")
            self.assertEqual(by_g["核算近七天构建慢查询占比"]["autonomy_tier"], "pre_verify_auto")
            self.assertEqual(by_g["冷门导出插件专项重写"]["state"], "violation_blocked")
            alert_types = {a["type"] for a in st1["pinned_alerts"]}
            self.assertTrue({"theater", "violation", "clash"}.issubset(alert_types))

            # Run a second scan passing --prev-state: unchanged in_progress items fold cleanly
            in_dir = Path(td) / "steady"
            in_dir.mkdir()
            (in_dir / "s1.jsonl").write_text(json.dumps({
                "window_id": "w1", "tool": "Claude Code", "goal": "常规文档索引重建",
                "updated_at": "2026-11-22T10:00:00Z", "turn": 2, "role": "assistant", "text": "正在平稳构建索引分片"
            }, ensure_ascii=False) + "\n", "utf-8")
            r_a, r_b = Path(td) / "ra", Path(td) / "rb"
            subprocess.run([sys.executable, str(SCRIPT), "scan", "--dir", str(in_dir), "--since-days", "0", "--out", str(r_a)], check=True)
            subprocess.run([sys.executable, str(SCRIPT), "scan", "--dir", str(in_dir), "--since-days", "0", "--prev-state", str(r_a / "cabinet-state.json"), "--out", str(r_b)], check=True)
            st_b = json.loads((r_b / "cabinet-state.json").read_text("utf-8"))
            self.assertIn("常规文档索引重建", st_b["dormant_folded"])

    def test_05_same_day_codex_rollout_clash_and_natural_readonly_ask(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sessions = Path(td) / "sessions" / "2026/11/26"
            sessions.mkdir(parents=True)
            clash_goal = "调整本地缓存刷新方案"
            readonly_goal = "核算上周构建成功率"
            windows = [
                ("10-00-01", "11111111-2222-3333-4444-555555555551",
                 clash_goal, "推翻旧案，改走增量刷新。"),
                ("14-30-09", "11111111-2222-3333-4444-555555555552",
                 clash_goal, "继续按旧案推进，可以先翻上周的日志吗？"),
                ("15-00-00", "11111111-2222-3333-4444-555555555553",
                 readonly_goal, "我能先看看上周构建的记录，统计失败比例吗？"),
            ]
            for time, session_id, goal, request in windows:
                rows = [
                    {
                        "type": "response_item",
                        "timestamp": f"2026-11-26T{time.replace('-', ':')}Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": message}],
                        },
                    }
                    for message in (goal, request)
                ]
                path = sessions / f"rollout-2026-11-26T{time}-{session_id}.jsonl"
                path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", "utf-8")

            out = Path(td) / "out"
            subprocess.run(
                [sys.executable, str(SCRIPT), "scan", "--dir", str(Path(td) / "sessions"),
                 "--since-days", "0", "--out", str(out)],
                check=True,
            )
            state = json.loads((out / "cabinet-state.json").read_text("utf-8"))
            by_goal = {item["goal"]: item for item in state["items"]}
            with self.subTest(goal=clash_goal):
                self.assertEqual(by_goal[clash_goal]["badge"], "跨窗口口径打架")
                self.assertEqual(len(by_goal[clash_goal]["windows"]), 2)
                self.assertIn((clash_goal, "clash"), [(a["goal"], a["type"]) for a in state["pinned_alerts"]])
                brief = (out / "cabinet-brief.html").read_text("utf-8")
                self.assertIn('<div class="al">', brief)
                self.assertIn(f"<b>[{clash_goal}]</b> 跨窗撞车", brief)
            with self.subTest(goal=readonly_goal):
                self.assertEqual(by_goal[readonly_goal]["state"], "pre_verify_auto")
                self.assertEqual(by_goal[readonly_goal]["autonomy_tier"], "pre_verify_auto")

if __name__ == "__main__":
    unittest.main()
