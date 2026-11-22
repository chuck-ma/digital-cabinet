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
            codex_f = in_dir / "2026/11/rollout-codex-b.jsonl"
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

if __name__ == "__main__":
    unittest.main()
