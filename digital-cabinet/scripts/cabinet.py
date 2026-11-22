#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digital Cabinet CLI v0.2 — Zero-dep read-only multi-window steward for Claude Code & Codex."""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, subprocess, sys
from pathlib import Path
from typing import Any

DROP_PAT = re.compile(r"(不用管|不用处理|先放放|暂缓|作废不管|dropped)", re.I)
OVERTURN_PAT = re.compile(r"(作废|推翻|放弃|改走|统一画横线|别用昨晚)")
ASK_PAT = re.compile(r"(得你定|等你确认|请确认|选哪一套|取决于你的|画横线.*还是|要不要|[?？]\s*$)")
THEATER_PAT = re.compile(r"(关于分析报告的分析|analysis_of_analysis|重新离线分析了一遍|又从头分析了一遍)", re.I)
DONE_PAT = re.compile(r"(已完成|全部通过|已合入|已收口)")
SYS_NOISE_PAT = re.compile(r"^(<environment_context>|<permissions|AGENTS\.md|# AGENTS|<system-reminder>)", re.I)


def _clean_goal_title(text: str, fallback: str) -> str:
    s = re.sub(r"\s+", " ", text).strip()
    s = re.sub(r"^[#>*\-\d.\s]+", "", s)
    for sep in ("。", "！", "？", "\n", "——", "；"):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
    return (s[:26] + "…") if len(s) > 26 else (s or fallback)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text", None):
                if p.get("text"):
                    parts.append(str(p["text"]))
        return " ".join(parts).strip()
    return ""


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    lines = path.read_text("utf-8", errors="replace").splitlines()
    if not lines:
        return []
    # Check if synthetic multi-window format (explicit goal + window_id per row)
    first_obj = None
    for raw in lines:
        if raw.strip():
            try:
                first_obj = json.loads(raw)
                break
            except json.JSONDecodeError:
                continue
    if isinstance(first_obj, dict) and "goal" in first_obj and "window_id" in first_obj:
        out: list[dict[str, Any]] = []
        for idx, raw in enumerate(lines, 1):
            if not raw.strip():
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            out.append({
                "window_id": str(obj["window_id"]), "tool": str(obj.get("tool", "Agent")),
                "goal": str(obj["goal"]), "updated_at": str(obj.get("updated_at", "")),
                "turn": int(obj.get("turn", idx)), "role": str(obj.get("role", "assistant")),
                "text": str(obj.get("text", "")), "source_ref": f"{path.name}#L{idx}",
            })
        return out

    # Real Claude Code or Codex session file -> 1 file = 1 conversation window!
    turns: list[tuple[int, str, str, str, str]] = []
    tool_label = "Claude Code"
    file_mtime_iso = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc).isoformat()
    for idx, raw in enumerate(lines, 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            continue
        ts = str(obj.get("timestamp") or "")
        # Codex response_item schema
        if obj.get("type") == "response_item" and isinstance(obj.get("payload"), dict):
            tool_label = "Codex CLI"
            pl = obj["payload"]
            role = str(pl.get("role") or "")
            if role not in ("user", "assistant"):
                continue
            txt = _extract_text(pl.get("content", ""))
            if not txt or SYS_NOISE_PAT.search(txt):
                continue
            turns.append((idx, role, txt[:320], ts or file_mtime_iso, tool_label))
        # Claude Code message schema
        elif obj.get("type") in ("user", "assistant") or isinstance(obj.get("message"), dict):
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else obj
            role = str(msg.get("role") or obj.get("type") or "")
            if role not in ("user", "assistant"):
                continue
            txt = _extract_text(msg.get("content", ""))
            if not txt or SYS_NOISE_PAT.search(txt):
                continue
            turns.append((idx, role, txt[:320], ts or file_mtime_iso, tool_label))

    if not turns:
        return []
    first_user = next((t[2] for t in turns if t[1] == "user"), turns[0][2])
    goal = _clean_goal_title(first_user, path.stem[:20])
    # Keep first user turn + last 4 turns for crisp evidence
    kept = ([turns[0]] if turns[0][1] == "user" else []) + turns[-4:]
    dedup: list[tuple[int, str, str, str, str]] = []
    seen_i: set[int] = set()
    for item in kept:
        if item[0] not in seen_i:
            seen_i.add(item[0])
            dedup.append(item)
    return [
        {
            "window_id": path.stem[:18], "tool": tl, "goal": goal,
            "updated_at": ts, "turn": idx, "role": role,
            "text": txt, "source_ref": f"{path.name}#L{idx}",
        }
        for idx, role, txt, ts, tl in dedup
    ]


def load_events(target_dir: Path, since_days: float | None = None, ref_now: dt.datetime | None = None) -> list[dict[str, Any]]:
    if not target_dir.exists():
        raise FileNotFoundError(f"Directory not found: {target_dir}")
    now = ref_now or dt.datetime.now(dt.timezone.utc)
    evs: list[dict[str, Any]] = []
    for p in sorted(target_dir.rglob("*.jsonl")):
        if since_days is not None and since_days > 0:
            age_d = (now.timestamp() - p.stat().st_mtime) / 86400.0
            if age_d > since_days:
                continue
        evs.extend(_parse_jsonl(p))
    return evs


def parse_playbook_rules(pb_txt: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    for blk in re.split(r"\n##\s+", pb_txt):
        if "好判断" not in blk:
            continue
        title = blk.splitlines()[0].strip()
        good = re.search(r"好判断[^：:]*[：:]\s*(.+)", blk)
        prem = re.search(r"(?:适用前提|为什么与适用前提)[^：:]*[：:]\s*(.+)", blk)
        rules.append({"title": title, "good": good.group(1).strip() if good else "", "premise": prem.group(1).strip() if prem else ""})
    return rules


def _draft_proposal(all_txt: str, rules: list[dict[str, str]]) -> str:
    if not rules:
        return ""
    if re.search(r"(空值|没数据|横线|格式|命名)", all_txt):
        r = rules[0]
        return f"【内阁拟办】{r['good']}（依据：{r['title']} · 前提：{r['premise']}）"
    if len(rules) > 1 and re.search(r"(警告|慢查询|重试|小样)", all_txt):
        r = rules[1]
        return f"【内阁拟办】{r['good']}（依据：{r['title']} · 前提：{r['premise']}）"
    return f"【内阁拟办】对照《{rules[0]['title']}》先给可逆默认方案推进，仅不可逆取舍留待拍板。"


def build_work_view(events: list[dict[str, Any]], pb_txt: str = "", ref_now: dt.datetime | None = None) -> list[dict[str, Any]]:
    now = ref_now or dt.datetime.now(dt.timezone.utc)
    rules = parse_playbook_rules(pb_txt)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        grouped.setdefault(ev["goal"], []).append(ev)

    items: list[dict[str, Any]] = []
    for goal, evs in grouped.items():
        wins = sorted({e["window_id"] for e in evs})
        latest = evs[-1]
        u_evs = [e for e in evs if e["role"] == "user"]
        last_u = u_evs[-1]["text"] if u_evs else ""
        u_txt = " ".join(e["text"] for e in u_evs)
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
        dropped = bool(last_u) and len(last_u) <= 80 and bool(DROP_PAT.search(last_u)) and (latest["role"] == "user" or not ASK_PAT.search(latest["text"])) and not clash
        done = bool(DONE_PAT.search(latest["text"])) and not ASK_PAT.search(latest["text"])
        prop = ""
        if dropped:
            st, q, b, s = "dropped", "Q4_已收口或免催", "你说过不用管", "最新指示明确暂不处理，已自动划掉不再催办。"
        elif done:
            st, q, b, s = "completed", "Q4_已收口或免催", "已收口", "已确认完成收口。"
        elif theater:
            st, q, b, s = "theater_blocked", "Q1_需你拍板与拦截", "拦截写报告分析报告", "检测到把已有报告再分析一遍的假忙活（无实质可验证进展），已自动拦停。"
        elif clash:
            st, q, b, s = "waiting_owner", "Q1_需你拍板与拦截", "跨窗口口径打架", f"涉及 {len(wins)} 个窗口：一边刚改了新口径，另一边还在按旧方案跑，需统一。"
            prop = _draft_proposal(a_txt, rules)
        elif ASK_PAT.search(latest["text"]):
            prop = _draft_proposal(a_txt, rules)
            if hrs >= 20.0:
                st, q, b, s = "stalled", "Q2_昨天聊一半没下文", f"已搁置 {int(hrs)}h", "昨天聊到一半等你定夺、隔天零新消息，自动跨天保留防遗忘。"
            else:
                st, q, b, s = "waiting_owner", "Q1_需你拍板与拦截", "卡在原地等你定", "窗口遇到分岔停下等拿主意。"
        else:
            st, q, b, s = "in_progress", "Q3_正常推进免打扰", "平稳推进", "正在按既定方向推进，合并一行报平安。"
        items.append({"goal": goal, "state": st, "quadrant": q, "badge": b, "windows": wins, "summary": s, "proposal": prop, "evidence": evs})
    order = {"Q1_需你拍板与拦截": 0, "Q2_昨天聊一半没下文": 1, "Q3_正常推进免打扰": 2, "Q4_已收口或免催": 3}
    items.sort(key=lambda x: order.get(x["quadrant"], 9))
    return items


def render_html(items: list[dict[str, Any]], pb_txt: str) -> str:
    qs = [
        ("Q1_需你拍板与拦截", "急需过目 · 跨窗打架 / 卡住等你定 / 假忙活拦截", "#C84B31", "#FFF5F2"),
        ("Q2_昨天聊一半没下文", "跨天防忘 · 昨天聊到一半没下文的事", "#D97706", "#FFFBEB"),
        ("Q3_正常推进免打扰", "正常推进 · 合并报平安", "#1F6358", "#ECFDF5"),
        ("Q4_已收口或免催", "已收口 · 含你说过“不用管”自动划掉的事", "#64748B", "#F8FAFC"),
    ]
    secs = []
    for qk, ql, col, bg in qs:
        sub = [it for it in items if it["quadrant"] == qk]
        rows = []
        for it in sub:
            evs = "".join("<li><code>" + html.escape(e["source_ref"]) + "</code> [" + html.escape(e["tool"]) + "·" + html.escape(e["role"]) + "]: " + html.escape(e["text"]) + "</li>" for e in it["evidence"])
            prop_html = "<div class=\"pr\">" + html.escape(it["proposal"]) + "</div>" if it.get("proposal") else ""
            rows.append(
                "<div class=\"it\" style=\"border-left:4px solid " + col + ";background:" + bg + "\">"
                "<div class=\"hd\"><b>" + html.escape(it["goal"]) + "</b><span class=\"tg\" style=\"background:" + col + "\">" + html.escape(it["badge"]) + "</span></div>"
                "<div class=\"sm\">" + html.escape(it["summary"]) + "</div>" + prop_html +
                "<details><summary>查看原始对话出处（" + str(len(it["evidence"])) + " 条）</summary><ul>" + evs + "</ul></details></div>"
            )
        body_html = "".join(rows) or "<div class=\"em\">当前无事项</div>"
        secs.append("<section class=\"qd\"><h3>" + ql + "（" + str(len(sub)) + "）</h3>" + body_html + "</section>")
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        "<title>数字内阁 Digital Cabinet · 一页待办总览与票拟</title>"
        "<style>body{font-family:PingFang SC,-apple-system,sans-serif;background:#F6F1E7;color:#231D18;margin:0;padding:28px 36px;line-height:1.6}"
        ".gr{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:18px;margin:18px 0 24px}"
        ".qd{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:16px;padding:18px 20px}"
        ".it{padding:12px 14px;border-radius:10px;margin-bottom:10px}"
        ".hd{display:flex;justify-content:space-between;align-items:center;gap:8px}"
        ".tg{color:#fff;font-size:12px;font-weight:700;padding:2px 10px;border-radius:999px}"
        ".sm{font-size:13.5px;margin:4px 0 6px}"
        ".pr{background:#ECFDF5;border:1px solid #4FA882;color:#065F46;font-size:13px;font-weight:700;padding:6px 10px;border-radius:8px;margin-bottom:6px}"
        "summary{cursor:pointer;font-size:12.5px;color:#1F6358;font-weight:700}"
        "pre{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:14px;padding:16px 20px;white-space:pre-wrap;font-size:13px}</style></head>"
        "<body><h1>数字内阁 Digital Cabinet · 一页待办总览与票拟意见</h1>"
        "<div>只读盘点 · 昨天聊一半防忘 · 跨窗打架提醒 · 拟好默认意见供你拍板（共 " + str(len(items)) + " 件事）</div>"
        "<div class=\"gr\">" + "".join(secs) + "</div>"
        "<h2>个人判断默契档案（好坏例子 + 为什么 + 适用前提）</h2><pre>" + html.escape(pb_txt.strip() or "尚未录入规则") + "</pre></body></html>"
    )


def run_cabinet(sdir: Path, pb: Path | None, out: Path, do_open: bool, since_days: float | None = None, ref_now: dt.datetime | None = None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    pb_txt = pb.read_text("utf-8") if pb and pb.exists() else ""
    items = build_work_view(load_events(sdir, since_days=since_days, ref_now=ref_now), pb_txt=pb_txt, ref_now=ref_now)
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
    p2 = sub.add_parser("scan"); p2.add_argument("--dir", required=True); p2.add_argument("--playbook", default=""); p2.add_argument("--since-days", type=float, default=7.0); p2.add_argument("--out", default="./cabinet-out"); p2.add_argument("--open", action="store_true")
    p3 = sub.add_parser("learn"); p3.add_argument("--playbook", required=True); p3.add_argument("--scene", required=True); p3.add_argument("--good", required=True); p3.add_argument("--bad", required=True); p3.add_argument("--why", required=True); p3.add_argument("--premise", required=True)
    a = ap.parse_args()
    if a.cmd == "demo":
        ex = root / "examples/synthetic-multi-window"
        run_cabinet(ex, ex / "playbook-seed.md", Path(a.out), a.open, None, dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc))
    elif a.cmd == "scan":
        run_cabinet(Path(a.dir), Path(a.playbook) if a.playbook else None, Path(a.out), a.open, a.since_days if a.since_days > 0 else None)
    elif a.cmd == "learn":
        p = Path(a.playbook); p.parent.mkdir(parents=True, exist_ok=True)
        cur = p.read_text("utf-8") if p.exists() else "# 个人判断默契档案\n"
        p.write_text(cur.rstrip() + f"\n\n## 规则 · {a.scene}\n- **触发处境**：{a.scene}\n- **好判断（Good）**：{a.good}\n- **坏判断（Bad）**：{a.bad}\n- **为什么（Why）**：{a.why}\n- **适用前提（Premise）**：{a.premise}\n", "utf-8")
        print(f"OK:已沉淀新默契至 {p}")


if __name__ == "__main__":
    main()
