---
name: digital-cabinet
description: 跨窗口全局统筹、待办票拟与个人判断默契沉淀（数字内阁）。用于同时开多个 Claude Code / Codex 对话框推进工作时，只读盘点散落各窗口的真实进度、跨天保留未收尾事项、结合个人好坏判断档案预先拟好默认处理意见（票拟），只把真正不可逆的取舍留给用户拍板。
---

# Digital Cabinet（数字内阁）

借古代内阁“先替你分清奏折轻重、拟好处理意见，只留关键处供你动笔勾一下”的思路，在所有低头干活的 AI 窗口之上，单设一层**不抢活干、严格只读、专盯全局与个人分寸**的统筹参谋。

## Agent 标准五步「票拟」操作流程

当用户唤起本 Skill（如说“帮我理一下现在开的几个窗口”或“跑一下数字内阁”）时，严格按以下五步执行：

1. **确认授权目录（绝不扫全盘）**：若用户未指明路径，先询问要盘点哪个项目的会话目录（Claude Code 默认位于用户主目录下的 `.claude/projects/<项目名>/`，Codex 默认位于 `.codex/sessions/年/月/日/`），或先跑 `demo` 展示效果。
2. **运行只读盘点脚本**：
   ```bash
   python3 scripts/cabinet.py scan --dir <用户指定目录> --since-days 7 --playbook ./decision-playbook.md --out ./cabinet-out
   ```
3. **精读状态与判断默契档案**：读取生成的 `./cabinet-out/cabinet-state.json` 与 `decision-playbook.md`（若尚无档案，参考 `examples/synthetic-multi-window/playbook-seed.md` 初始化）。
4. **逐项“票拟”默认意见（核心价值）**：
   - 对每个卡在原地等拿主意的窗口，**禁止原样把琐碎选择题抛回给用户**；必须结合判断档案与上下文，**直接拟出一条首选默认建议 + 理由 + 适用前提**（检查当前是本地小样试跑还是正式上线，严禁把小样阶段的放行豁免带入正式环境）；
   - 对“把昨天的报告又重新分析一遍”这类无实质验证进展的假忙活，直接标红建议拦停。
5. **交出一页清爽待办与随口沉淀**：向用户输出精炼的一页总览（只留真正不可逆的分岔请用户拍板），并提示打开 `./cabinet-out/cabinet-brief.html` 查看原话出处；用户拍板或纠偏后，立即调用 `scripts/cabinet.py learn` 将新习惯（触发处境 + 好判断 + 坏判断 + 为什么 + 适用前提）写入 `decision-playbook.md`。

详细三本账原理与反假忙活检查单见 [`references/three-ledgers-and-anti-theater.md`](references/three-ledgers-and-anti-theater.md)。
