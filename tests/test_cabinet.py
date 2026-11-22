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
            self.assertEqual(by_goal["重构本地缓存读取层"]["badge"], "跨窗口方案撞车")
            self.assertIn("防沉底", by_goal["补齐接口超时重试测试"]["badge"])
            self.assertEqual(by_goal["旧版演示页配色微调"]["state"], "dropped")
            self.assertEqual(by_goal["夜间自主推进任务候选"]["state"], "theater_blocked")
            self.assertTrue((out1 / "cabinet-brief.html").exists())

            # Diff-sensitivity: user says "这块不用管" on stalled item -> flips to dropped!
            sess_dir = Path(td) / "sess"
            shutil.copytree(ROOT / "digital-cabinet/examples/synthetic-multi-window", sess_dir)
            with (sess_dir / "sessions.jsonl").open("a", encoding="utf-8") as fh:
                fh.write("{\"window_id\":\"win-04-gemini-doc\",\"tool\":\"Gemini CLI\",\"goal\":\"补齐接口超时重试测试\",\"updated_at\":\"2026-11-22T11:00:00Z\",\"turn\":6,\"role\":\"user\",\"text\":\"超时重试这块不用管，先放放。\"}\n")
            out2 = Path(td) / "demo2"
            subprocess.run([sys.executable, str(SCRIPT), "scan", "--dir", str(sess_dir), "--out", str(out2)], check=True)
            st2 = json.loads((out2 / "cabinet-state.json").read_text("utf-8"))
            by_goal2 = {x["goal"]: x for x in st2["items"]}
            self.assertEqual(by_goal2["补齐接口超时重试测试"]["state"], "dropped")

if __name__ == "__main__":
    unittest.main()
