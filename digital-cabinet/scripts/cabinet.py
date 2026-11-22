#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digital Cabinet CLI — Zero-dependency Python 3 stdlib read-only multi-window steward."""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, subprocess, sys
from pathlib import Path
from typing import Any

DROP_PAT = re.compile(r"(不用管|不用处理|先放放|暂缓|作废不管|dropped)", re.I)
OVERTURN_PAT = re.compile(r"(作废|推翻|放弃|改走|别用昨晚)")
ASK_PAT = re.compile(r"(得你定|等你确认|请确认|选哪一套|取决于你的|要不要)")
THEATER_PAT = re.compile(r"(关于分析报告的分析|analysis_of_analysis|重新离线分析了一遍|又从头分析了一遍)", re.I)
DONE_PAT = re.compile(r"(已完成|全部通过|已合入|已收口)")

def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, raw in enumerate(path.read_text("utf-8", errors="replace").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "goal" in obj and "window_id" in obj:
            out.append({
                "window_id": str(obj["window_id"]), "tool": str(obj.get("tool", "Agent")),
                "goal": str(obj["goal"]), "updated_at": str(obj.get("updated_at", "")),
                "turn": int(obj.get("turn", idx)), "role": str(obj.get("role", "assistant")),
                "text": str(obj.get("text", "")), "source_ref": f"{path.name}#L{idx}",
            })
        else:
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
            role = str(msg.get("role") or obj.get("type") or "assistant")
            c = msg.get("content", "")
            if isinstance(c, list):
                c = " ".join(str(p.get("text", "")) for p in c if isinstance(p, dict))
            text = str(c or obj.get("text") or "").strip()
            if not text:
                continue
            goal = Path(str(obj.get("cwd") or path.stem)).name or path.stem
            out.append({
                "window_id": path.stem, "tool": "Claude/Codex", "goal": goal,
                "updated_at": str(obj.get("timestamp") or ""), "turn": idx,
                "role": role, "text": text[:360], "source_ref": f"{path.name}#L{idx}",
            })
    return out

def load_events(target_dir: Path) -> list[dict[str, Any]]:
    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: {target_dir}")
    evs: list[dict[str, Any]] = []
    for p in sorted(target_dir.glob("*.jsonl")):
        evs.extend(_parse_jsonl(p))
    return evs

def build_work_view(events: list[dict[str, Any]], ref_now: dt.datetime | None = None) -> list[dict[str, Any]]:
    now = ref_now or dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        grouped.setdefault(ev["goal"], []).append(ev)
    items: list[dict[str, Any]] = []
    for goal, evs in grouped.items():
        wins = sorted({e["window_id"] for e in evs})
        latest = evs[-1]
        u_txt = " ".join(e["text"] for e in evs if e["role"] == "user")
        a_txt = " ".join(e["text"] for e in evs)
        hrs = 0.0
        if latest["updated_at"]:
            try:
                ts = dt.datetime.fromisoformat(latest["updated_at"].replace("Z", "+00:00"))
                hrs = max(0.0, (now - ts).total_seconds() / 3600.0)
            except ValueError:
                hrs = 0.0
        clash = len(wins) >= 2 and bool(OVERTURN_PAT.search(u_txt)) and not bool(DONE_PAT.search(latest["text"]))
        theater = bool(THEATER_PAT.search(a_txt))
        dropped = bool(DROP_PAT.search(u_txt)) and not clash
        done = bool(DONE_PAT.search(latest["text"])) and not ASK_PAT.search(latest["text"])
        if dropped:
            st, q, b, s = "dropped", "Q4_免催归档", "已随口免催", "本人已明确表示暂不处理，自动归档不再催办。"
        elif done:
            st, q, b, s = "completed", "Q4_免催归档", "已收口", "已确认完成收口。"
        elif theater:
            st, q, b, s = "theater_blocked", "Q1_急等拍板", "拦截安全感表演", "检测到「把已有分析报告再分析一遍」空转套娃（0 实质推进），已自动拦停。"
        elif clash:
            st, q, b, s = "waiting_owner", "Q1_急等拍板", "跨窗口方案撞车", f"涉及 {len(wins)} 个窗口：主窗口已推翻旧方案，另一窗口仍按昨晚废稿推进，需同步对齐。"
        elif ASK_PAT.search(latest["text"]):
            if hrs >= 20.0:
                st, q, b, s = "stalled", "Q2_跨天未完", f"隔夜静默 {int(hrs)}h 防沉底", "昨日聊到一半待确认、隔天零新消息，已跨天强制保留防止遗忘沉底。"
            else:
                st, q, b, s = "waiting_owner", "Q1_急等拍板", "卡在原地等拍板", "执行窗口遇分岔停工等待拿主意（可按判断默契档案直接给默认倾向）。"
        else:
            st, q, b, s = "in_progress", "Q3_正常推进", "平稳推进", "目标清晰推进中，合并一行报平安免打扰。"
        items.append({"goal": goal, "state": st, "quadrant": q, "badge": b, "windows": wins, "summary": s, "evidence": evs})
    order = {"Q1_急等拍板": 0, "Q2_跨天未完": 1, "Q3_正常推进": 2, "Q4_免催归档": 3}
    items.sort(key=lambda x: order.get(x["quadrant"], 9))
    return items

def render_html(items: list[dict[str, Any]], pb_txt: str) -> str:
    qs = [
        ("Q1_急等拍板", "一象限 · 需你拍板 / 跨窗撞车与空转拦截", "#C84B31", "#FFF5F2"),
        ("Q2_跨天未完", "二象限 · 隔夜零新消息 · 跨天咬死防沉底", "#D97706", "#FFFBEB"),
        ("Q3_正常推进", "三象限 · 正常推进（免打扰合并）", "#1F6358", "#ECFDF5"),
        ("Q4_免催归档", "四象限 · 已收口 / 随口“不用管”自动销账", "#64748B", "#F8FAFC"),
    ]
    secs = []
    for qk, ql, col, bg in qs:
        sub = [it for it in items if it["quadrant"] == qk]
        rows = []
        for it in sub:
            evs = "".join(f"<li><code>{html.escape(e['source_ref'])}</code> [{html.escape(e['tool'])}·{html.escape(e['role'])}]: {html.escape(e['text'])}</li>" for e in it["evidence"])
            rows.append(f"<div class='it' style='border-left:4px solid {col};background:{bg}'><div class='hd'><b>{html.escape(it['goal'])}</b><span class='tg' style='background:{col}'>{html.escape(it['badge'])}</span></div><div class='sm'>{html.escape(it['summary'])}</div><details><summary>展开一手原话出处（{len(it['evidence'])} 条）</summary><ul>{evs}</ul></details></div>")
        body_html = "".join(rows) or "<div class='em'>当前无事项</div>"
        secs.append(f"<section class='qd'><h3>{ql}（{len(sub)}）</h3>{body_html}</section>")
    return f"<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'><title>数字内阁 Digital Cabinet · 全局轻重缓急简报</title><style>body{{font-family:'PingFang SC',-apple-system,sans-serif;background:#F6F1E7;color:#231D18;margin:0;padding:28px 36px;line-height:1.6}}.gr{{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:18px;margin:18px 0 24px}}.qd{{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:16px;padding:18px 20px}}.it{{padding:12px 14px;border-radius:10px;margin-bottom:10px}}.hd{{display:flex;justify-content:space-between;align-items:center;gap:8px}}.tg{{color:#fff;font-size:12px;font-weight:700;padding:2px 10px;border-radius:999px}}.sm{{font-size:13.5px;margin:4px 0 6px}}summary{{cursor:pointer;font-size:12.5px;color:#1F6358;font-weight:700}}pre{{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:14px;padding:16px 20px;white-space:pre-wrap;font-size:13px}}</style></head><body><h1>数字内阁 Digital Cabinet · 多窗口全局简报</h1><div>严格只读 · 跨天未完防沉底 · 跨窗撞车预警 · 反“安全感表演”门禁（共归拢 {len(items)} 件事）</div><div class='gr'>{''.join(secs)}</div><h2>个人判断默契档案（好坏例子 + 为什么 + 适用前提）</h2><pre>{html.escape(pb_txt.strip() or '尚未录入规则')}</pre></body></html>"

def run_cabinet(sdir: Path, pb: Path | None, out: Path, do_open: bool) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    items = build_work_view(load_events(sdir))
    pb_txt = pb.read_text("utf-8") if pb and pb.exists() else ""
    hp, jp = out / "cabinet-brief.html", out / "cabinet-state.json"
    hp.write_text(render_html(items, pb_txt), "utf-8")
    res = {"total_goals": len(items), "items": items}
    jp.write_text(json.dumps(res, ensure_ascii=False, indent=2), "utf-8")
    if do_open and sys.platform == "darwin":
        subprocess.run(["open", str(hp)], check=False)
    print(f"OK:归拢 {len(items)} 件事 -> {hp}")
    return res

def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("demo"); p1.add_argument("--out", default="./cabinet-demo-out"); p1.add_argument("--open", action="store_true")
    p2 = sub.add_parser("scan"); p2.add_argument("--dir", required=True); p2.add_argument("--playbook", default=""); p2.add_argument("--out", default="./cabinet-out"); p2.add_argument("--open", action="store_true")
    p3 = sub.add_parser("learn"); p3.add_argument("--playbook", required=True); p3.add_argument("--scene", required=True); p3.add_argument("--good", required=True); p3.add_argument("--bad", required=True); p3.add_argument("--why", required=True); p3.add_argument("--premise", required=True)
    a = ap.parse_args()
    if a.cmd == "demo":
        ex = root / "examples/synthetic-multi-window"
        run_cabinet(ex, ex / "playbook-seed.md", Path(a.out), a.open)
    elif a.cmd == "scan":
        run_cabinet(Path(a.dir), Path(a.playbook) if a.playbook else None, Path(a.out), a.open)
    elif a.cmd == "learn":
        p = Path(a.playbook); p.parent.mkdir(parents=True, exist_ok=True)
        cur = p.read_text("utf-8") if p.exists() else "# 个人判断默契档案\n"
        p.write_text(cur.rstrip() + f"\n\n## 规则 · {a.scene}\n- **触发处境**：{a.scene}\n- **好判断（Good）**：{a.good}\n- **坏判断（Bad）**：{a.bad}\n- **为什么（Why）**：{a.why}\n- **适用前提（Premise）**：{a.premise}\n", "utf-8")
        print(f"OK:已沉淀新默契至 {p}")

if __name__ == "__main__":
    main()
