---
name: digital-cabinet
description: 跨窗口拆锁参谋长、前置只读求证分流与个人判断默契沉淀（数字内阁 v0.3）。用于同时开多个 Claude Code / Codex 窗口时，免批完成只读查数与底数核算、对照上期折叠零进展冷饭、置顶吹哨跨窗口撞车与盲干违纪，仅将不可逆取舍附默认票拟交用户拍板。
---

# Digital Cabinet（数字内阁 · v0.3 拆锁参谋长版）

切忌做成“把奏折抄成目录等盖章”的收发室秘书。本 Skill 执行明代内阁真正的**「票拟」**：**只看不动的求证免批自己算穿，收不回来的真改动才带实证账本请批红**。

## Agent 标准五步「拆锁票拟」操作流程

1. **确认授权目录（绝不扫全盘）**：若用户未指明路径，询问要盘点的项目会话目录（如 `.claude/projects/<项目名>/` 或 `.codex/sessions/年/月/日/`），或先跑 `demo`。
2. **运行只读盘点与上期增量比对**：
   ```bash
   python3 scripts/cabinet.py scan --dir <用户指定目录> --prev-state ./cabinet-out/cabinet-state.json --since-days 7 --playbook ./decision-playbook.md --out ./cabinet-out
   ```
3. **拆锁自治（禁止拿“去不去查日志”烦用户）**：
   - 对 `autonomy_tier == "pre_verify_auto"`（查日志、拉近七天底数、算耗时占比等纯只读求证），**禁止原样抛给用户求批准**——当场调用只读命令把底数算清，收益过低的伪命题直接替用户毙掉并附一句理由；
   - 对 `dormant_folded`（对照上期零新进展项），简报正文 **0 字略过**，绝不早晚炒冷饭。
4. **违纪吹哨与不可逆事项票拟**：
   - 优先汇报 `pinned_alerts`（跨窗口口径打架、未查底数盲目开工、写报告分析报告的假忙活）；
   - 对真正不可逆的分岔，结合 `decision-playbook.md` 给出**首选拟办 + 硬账量纲 + 适用前提**（严防把内部试跑豁免带入正式对外环境）。
5. **交出清爽作战卡并沉淀新默契**：提示查看 `./cabinet-out/cabinet-brief.html`；用户拍板后调用 `scripts/cabinet.py learn` 沉淀「好判断 + 坏判断 + 为什么 + 适用前提」。

详见 [`references/three-ledgers-and-anti-theater.md`](references/three-ledgers-and-anti-theater.md)。
