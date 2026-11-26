#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Digital Cabinet CLI v0.3 — Zero-dep read-only multi-window steward for Claude Code & Codex."""
from __future__ import annotations
import argparse, datetime as dt, html, json, re, subprocess, sys
from pathlib import Path
from typing import Any

DROP_PAT = re.compile(r"(不用管|不用处理|先放放|暂缓|作废不管|dropped)", re.I)
OVERTURN_PAT = re.compile(r"(作废|推翻|放弃|改走|统一画横线|别用昨晚)")
ASK_PAT = re.compile(r"(得你定|等你确认|请确认|选哪一套|取决于你的|画横线.*还是|要不要|[?？]\s*$)")
THEATER_PAT = re.compile(r"(关于分析报告的分析|analysis_of_analysis|重新离线分析了一遍|又从头分析了一遍)", re.I)
READONLY_INQUIRY_PAT = re.compile(
    r"只读日志|只读核账|算笔账"
    r"|(?:看看|看一下|查看|查一下|(?<!推)翻(?!新|写|改|译)|读一下)[^\n。！？?，,；;]*(?:日志|记录|会话|明细|底数|占比)"
    r"|拉[^\n。！？?，,；;]*底数"
    r"|(?:统计|算算|算一下|核算)[^\n。！？?，,；;]*(?:比例|占比|率|分布|次数)",
    re.I,
)
CODEX_UUID_PAT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
IRREVERSIBLE_PAT = re.compile(r"(改代码|修改线上|发版|发布|迁移|删除|合并分支|drop table)", re.I)
RULE_VIOLATION_PAT = re.compile(r"(跳过前置算账|未拉.*底数.*开工|没查占比就先改)", re.I)
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
    session_uuid = CODEX_UUID_PAT.search(path.stem) if tool_label == "Codex CLI" else None
    window_id = f"codex-{session_uuid.group().lower()}" if session_uuid else path.stem
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
            "window_id": window_id, "tool": tl, "goal": goal,
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


def _fp(evs: list[dict[str, Any]]) -> str:
    last = evs[-1] if evs else {}
    return f"{len(evs)}|{last.get('turn',0)}|{last.get('updated_at','')}|{last.get('text','')[:80]}"

def build_work_view(events: list[dict[str, Any]], pb_txt: str = "", ref_now: dt.datetime | None = None, prev_fp: dict[str, str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    now = ref_now or dt.datetime.now(dt.timezone.utc)
    rules, pmap = parse_playbook_rules(pb_txt), (prev_fp or {})
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        grouped.setdefault(ev["goal"], []).append(ev)
    items, alerts, folded = [], [], []
    for goal, evs in grouped.items():
        wins = sorted({e["window_id"] for e in evs})
        latest = evs[-1]
        u_evs = [e for e in evs if e["role"] == "user"]
        last_u = u_evs[-1]["text"] if u_evs else ""
        u_txt, a_txt, fp = " ".join(e["text"] for e in u_evs), " ".join(e["text"] for e in evs), _fp(evs)
        hrs = 0.0
        if latest["updated_at"]:
            try:
                hrs = max(0.0, (now - dt.datetime.fromisoformat(latest["updated_at"].replace("Z", "+00:00"))).total_seconds() / 3600.0)
            except ValueError:
                hrs = 0.0
        clash = len(wins) >= 2 and bool(OVERTURN_PAT.search(u_txt)) and not bool(DONE_PAT.search(latest["text"]))
        theater = bool(THEATER_PAT.search(a_txt))
        viol = bool(RULE_VIOLATION_PAT.search(a_txt))
        ro_ask = bool(ASK_PAT.search(latest["text"])) and bool(READONLY_INQUIRY_PAT.search(latest["text"])) and not bool(IRREVERSIBLE_PAT.search(latest["text"]))
        dropped = bool(last_u) and len(last_u) <= 80 and bool(DROP_PAT.search(last_u)) and (latest["role"] == "user" or not ASK_PAT.search(latest["text"])) and not clash
        done = bool(DONE_PAT.search(latest["text"])) and not ASK_PAT.search(latest["text"])
        prop, tier = "", "observe"
        if dropped:
            st, q, b, s = "dropped", "Q4_已收口或免催", "你说过不用管", "最新指示明确暂不处理，已自动划掉不再催办。"
        elif done:
            st, q, b, s = "completed", "Q4_已收口或免催", "已收口", "已确认完成收口。"
        elif theater:
            st, q, b, s, tier = "theater_blocked", "Q1_需你拍板与拦截", "拦截写报告分析报告", "检测到把已有报告再分析一遍的假忙活，已自动拦停。", "pinned_guard"
            alerts.append({"goal": goal, "type": "theater", "msg": "假忙活拦截：拿报告套报告零真进展"})
        elif viol:
            st, q, b, s, tier = "violation_blocked", "Q1_需你拍板与拦截", "违纪盲干吹哨", "跳过前置底数核验盲目开工，已破格置顶拦停。", "pinned_guard"
            alerts.append({"goal": goal, "type": "violation", "msg": "违纪吹哨：未拉七天真实占比底数即盲干"})
        elif clash:
            st, q, b, s, tier = "waiting_owner", "Q1_需你拍板与拦截", "跨窗口口径打架", f"涉及 {len(wins)} 个窗口口径不一致，需统一。", "owner_approval"
            prop = _draft_proposal(a_txt, rules)
            alerts.append({"goal": goal, "type": "clash", "msg": f"跨窗撞车：{len(wins)} 窗口径打架待对齐"})
        elif ro_ask:
            st, q, b, s, tier = "pre_verify_auto", "Q3_正常推进免打扰", "免批只读算穿", "只读查日志算底数免批直跑，低收益直接淘汰，绝不拿查数烦人。", "pre_verify_auto"
            prop = "【拆锁自治】只看不动的求证免批算穿，划算再上桌请批红。"
        elif ASK_PAT.search(latest["text"]):
            tier, prop = "owner_approval", _draft_proposal(a_txt, rules)
            if hrs >= 20.0:
                st, q, b, s = "stalled", "Q2_昨天聊一半没下文", f"已搁置 {int(hrs)}h", "隔天零新消息，自动跨天保留防遗忘。"
            else:
                st, q, b, s = "waiting_owner", "Q1_需你拍板与拦截", "不可逆分岔请批红", "触及不可逆取舍，已附内阁默认拟办供拍板。"
        elif pmap.get(goal) == fp:
            folded.append(goal)
            st, q, b, s = "dormant_folded", "Q4_已收口或免催", "零新进展已折叠", "对照上期零变化，自动零字略过不炒冷饭。"
        else:
            st, q, b, s = "in_progress", "Q3_正常推进免打扰", "平稳推进", "按既定方向推进，合并一行报平安。"
        items.append({"goal": goal, "state": st, "autonomy_tier": tier, "quadrant": q, "badge": b, "windows": wins, "summary": s, "proposal": prop, "fingerprint": fp, "evidence": evs})
    order = {"Q1_需你拍板与拦截": 0, "Q2_昨天聊一半没下文": 1, "Q3_正常推进免打扰": 2, "Q4_已收口或免催": 3}
    items.sort(key=lambda x: order.get(x["quadrant"], 9))
    return items, alerts, folded


def render_html(items: list[dict[str, Any]], pb_txt: str, alerts: list[dict[str, str]] | None = None, folded: list[str] | None = None) -> str:
    als, fld = alerts or [], folded or []
    ab = ""
    if als:
        lis = "".join("<li><b>[" + html.escape(a["goal"]) + "]</b> " + html.escape(a["msg"]) + "</li>" for a in als)
        ab = "<div class=\"al\"><b>🚨 跨线诊断与违纪吹哨置顶（" + str(len(als)) + "）</b><ul>" + lis + "</ul></div>"
    qs = [
        ("Q1_需你拍板与拦截", "不可逆拍板与违纪吹哨 · 仅真分岔请批红", "#C84B31", "#FFF5F2"),
        ("Q2_昨天聊一半没下文", "跨天防忘 · 昨天聊到一半没下文的事", "#D97706", "#FFFBEB"),
        ("Q3_正常推进免打扰", "免批只读求证 & 平稳在途 · 拆锁自治", "#1F6358", "#ECFDF5"),
        ("Q4_已收口或免催", "已收口与零冷饭折叠 · 不炒陈年旧账", "#64748B", "#F8FAFC"),
    ]
    secs = []
    for qk, ql, col, bg in qs:
        sub = [it for it in items if it["quadrant"] == qk]
        rows = []
        for it in sub:
            evs = "".join("<li><code>" + html.escape(e["source_ref"]) + "</code> [" + html.escape(e["tool"]) + "·" + html.escape(e["role"]) + "]: " + html.escape(e["text"]) + "</li>" for e in it["evidence"])
            ph = "<div class=\"pr\">" + html.escape(it["proposal"]) + "</div>" if it.get("proposal") else ""
            rows.append("<div class=\"it\" style=\"border-left:4px solid " + col + ";background:" + bg + "\"><div class=\"hd\"><b>" + html.escape(it["goal"]) + "</b><span class=\"tg\" style=\"background:" + col + "\">" + html.escape(it["badge"]) + "</span></div><div class=\"sm\">" + html.escape(it["summary"]) + "</div>" + ph + "<details><summary>原始对话出处（" + str(len(it["evidence"])) + " 条）</summary><ul>" + evs + "</ul></details></div>")
        secs.append("<section class=\"qd\"><h3>" + ql + "（" + str(len(sub)) + "）</h3>" + ("".join(rows) or "<div>当前无事项</div>") + "</section>")
    return (
        "<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>数字内阁 Digital Cabinet v0.3</title>"
        "<style>body{font-family:PingFang SC,-apple-system,sans-serif;background:#F6F1E7;color:#231D18;margin:0;padding:28px 36px;line-height:1.6}"
        ".al{background:#231D18;color:#FDE68A;border:2px solid #C84B31;border-radius:14px;padding:14px 20px;margin:14px 0}.al ul{margin:6px 0 0;color:#FFFDF9}"
        ".gr{display:grid;grid-template-columns:repeat(auto-fit,minmax(440px,1fr));gap:18px;margin:18px 0 24px}.qd{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:16px;padding:18px 20px}"
        ".it{padding:12px 14px;border-radius:10px;margin-bottom:10px}.hd{display:flex;justify-content:space-between;align-items:center;gap:8px}.tg{color:#fff;font-size:12px;font-weight:700;padding:2px 10px;border-radius:999px}"
        ".sm{font-size:13.5px;margin:4px 0 6px}.pr{background:#ECFDF5;border:1px solid #4FA882;color:#065F46;font-size:13px;font-weight:700;padding:6px 10px;border-radius:8px;margin-bottom:6px}"
        "summary{cursor:pointer;font-size:12.5px;color:#1F6358;font-weight:700}pre{background:#FFFEFB;border:1px solid #DFD2BA;border-radius:14px;padding:16px 20px;white-space:pre-wrap;font-size:13px}</style></head>"
        "<body><h1>数字内阁 Digital Cabinet v0.3 · 拆锁参谋长作战面板</h1><div>只读求证免批算穿 · 不可逆动作带账请批红 · 零冷饭折叠 " + str(len(fld)) + " 项（共 " + str(len(items)) + " 件事）</div>" + ab +
        "<div class=\"gr\">" + "".join(secs) + "</div><h2>个人判断默契档案</h2><pre>" + html.escape(pb_txt.strip() or "尚未录入规则") + "</pre></body></html>"
    )


def run_cabinet(sdir: Path, pb: Path | None, out: Path, do_open: bool, since_days: float | None = None, ref_now: dt.datetime | None = None, prev_state: Path | None = None) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    pb_txt = pb.read_text("utf-8") if pb and pb.exists() else ""
    pmap = {}
    if prev_state and prev_state.exists():
        old = json.loads(prev_state.read_text("utf-8"))
        pmap = {str(x["goal"]): str(x.get("fingerprint", "")) for x in old.get("items", []) if x.get("goal")}
    items, alerts, folded = build_work_view(load_events(sdir, since_days=since_days, ref_now=ref_now), pb_txt=pb_txt, ref_now=ref_now, prev_fp=pmap)
    hp, jp = out / "cabinet-brief.html", out / "cabinet-state.json"
    hp.write_text(render_html(items, pb_txt, alerts, folded), "utf-8")
    res = {"schema_version": "0.3.0", "total_goals": len(items), "active_in_flight": sum(1 for x in items if x["state"] not in ("dropped", "completed", "dormant_folded")), "pinned_alerts": alerts, "dormant_folded": folded, "items": items}
    jp.write_text(json.dumps(res, ensure_ascii=False, indent=2), "utf-8")
    if do_open and sys.platform == "darwin":
        subprocess.run(["open", str(hp)], check=False)
    print(f"OK:归拢 {len(items)} 件事（在途 {res['active_in_flight']} · 置顶预警 {len(alerts)} · 折叠冷饭 {len(folded)}）-> {hp}")
    return res


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("demo"); p1.add_argument("--out", default="./cabinet-demo-out"); p1.add_argument("--prev-state", default=""); p1.add_argument("--open", action="store_true")
    p2 = sub.add_parser("scan"); p2.add_argument("--dir", required=True); p2.add_argument("--playbook", default=""); p2.add_argument("--prev-state", default=""); p2.add_argument("--since-days", type=float, default=7.0); p2.add_argument("--out", default="./cabinet-out"); p2.add_argument("--open", action="store_true")
    p3 = sub.add_parser("learn"); p3.add_argument("--playbook", required=True); p3.add_argument("--scene", required=True); p3.add_argument("--good", required=True); p3.add_argument("--bad", required=True); p3.add_argument("--why", required=True); p3.add_argument("--premise", required=True)
    a = ap.parse_args()
    if a.cmd == "demo":
        ex = root / "examples/synthetic-multi-window"
        run_cabinet(ex, ex / "playbook-seed.md", Path(a.out), a.open, None, dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc), Path(a.prev_state) if a.prev_state else None)
    elif a.cmd == "scan":
        run_cabinet(Path(a.dir), Path(a.playbook) if a.playbook else None, Path(a.out), a.open, a.since_days if a.since_days > 0 else None, None, Path(a.prev_state) if a.prev_state else None)
    elif a.cmd == "learn":
        p = Path(a.playbook); p.parent.mkdir(parents=True, exist_ok=True)
        cur = p.read_text("utf-8") if p.exists() else "# 个人判断默契档案\n"
        p.write_text(cur.rstrip() + f"\n\n## 规则 · {a.scene}\n- **触发处境**：{a.scene}\n- **好判断（Good）**：{a.good}\n- **坏判断（Bad）**：{a.bad}\n- **为什么（Why）**：{a.why}\n- **适用前提（Premise）**：{a.premise}\n", "utf-8")
        print(f"OK:已沉淀新默契至 {p}")


if __name__ == "__main__":
    main()
