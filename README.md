# Digital Cabinet（数字内阁）

> **Chuck 的 AI 折腾实验室 · 实验 01 配套开源 Skill**  
> 在所有低头干活的 AI 窗口之上，单搭一间**不抢活干、严格只读、专帮你理清多窗口轻重缓急与个人判断默契**的数字内阁。

同时开着七八个 Claude Code、Codex、Cursor 或 Gemini 对话框推进事情时，最累的往往不是写代码，而是：
- **小事逼你定、大事甩锅给你**：空值画横线还是留白要问你，真两难列完八条利弊甩一句“并非不能兼容……锅你自己背”；
- **多窗口各自为战、隔夜沉底**：左窗刚推翻旧方案，右窗还在按昨晚废稿猛改；昨天聊到一半忘了回的事，隔天没新消息就悄无声息沉了底；
- **管太死又滑向“安全感表演”**：立了一堆死规矩后，AI 怕犯错，干脆把昨天写好的分析报告又从头分析了一遍（产出《关于分析报告的分析》）。

`digital-cabinet` 把我们在日常多窗口实战里磨出来的核心解法浓缩成一套**零外部依赖、默认严格只读**的轻量开源 Skill。

## 一、10 秒零配置体验（跑内置合成多窗口样例）

纯 Python 3 标准库零依赖，进入仓库目录后直接运行：

```bash
python3 digital-cabinet/scripts/cabinet.py demo --out ./demo-out --open
```

立即可打开 `./demo-out/cabinet-brief.html`，查看 6 个多窗口样例如何自动归拢为：**跨窗方案撞车预警、隔夜静默防沉底、随口“不用管”自动销账、以及拦截《关于分析报告的分析》空转套娃**。

## 二、在常见编程 Agent 中启用

将本仓库中的 [`digital-cabinet/`](digital-cabinet/SKILL.md) 目录放入你的工作区 `skills/` 目录即可按需唤起。

## 三、只读扫描你显式指定的会话目录（绝不扫全盘）

```bash
python3 digital-cabinet/scripts/cabinet.py scan \
  --dir /path/to/selected-sessions \
  --playbook ./my-decision-playbook.md \
  --out ./my-cabinet-out
```

追加一条「好判断 + 坏判断 + 为什么 + 适用前提」长期默契：

```bash
python3 digital-cabinet/scripts/cabinet.py learn \
  --playbook ./my-decision-playbook.md \
  --scene "小样测试遇到非核心字段警告" \
  --good "本地跑小样先放行看整体效果，切正式环境自动恢复拦截" \
  --bad "把小样阶段的放行豁免顺手带进正式上线" \
  --why "脱离适用前提照搬旧决定会埋下暗雷" \
  --premise "仅限本地小样试跑"
```

## 开源许可与致谢

- [MIT License](LICENSE) · 统筹层与执行层分离思路受 `deepseek-ai/dsh-superagent-prototype`（MIT）启发，代码与合成样例均为独立净室编写。
