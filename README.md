# Digital Cabinet（数字内阁）

> **Chuck 的 AI 折腾实验室 · 实验 01 配套开源小工具与 Skill**  
> 借“内阁先分轻重、拟好意见，只留关键处供你拍板”的思路，在所有干活的 AI 窗口之上单设一层**严格只读、跨天防忘、越用越懂你分寸**的统筹参谋。

## 一、10 秒零配置体验（跑内置 6 窗口合成样例）

纯 Python 3 标准库（零第三方依赖），克隆仓库后直接运行：

```bash
python3 digital-cabinet/scripts/cabinet.py demo --out ./demo-out --open
```

立即可打开 `./demo-out/cabinet-brief.html` 一页待办总览，看到 6 个窗口如何被自动归拢并附上**【内阁拟办】默认意见**、跨窗打架提醒、昨天聊一半没下文防忘、你说过“不用管”自动划掉、以及拦截《关于分析报告的分析》假忙活。

## 二、扫你自己的 Claude Code / Codex 会话记录（严格只读）

常见本地会话目录位置：
- **Claude Code**：用户主目录下的 `.claude/projects/<你的项目目录名>/`
- **Codex CLI**：用户主目录下的 `.codex/sessions/2026/11/`（支持递归扫描近 N 天记录）

```bash
python3 digital-cabinet/scripts/cabinet.py scan \
  --dir /path/to/your/selected-session-folder \
  --since-days 7 \
  --playbook ./my-decision-playbook.md \
  --out ./my-cabinet-out --open
```

当你拍板定下一条新习惯时，用 `learn` 记下「好判断 + 坏判断 + 为什么 + 适用前提」：

```bash
python3 digital-cabinet/scripts/cabinet.py learn \
  --playbook ./my-decision-playbook.md \
  --scene "表格没数据的格子怎么显示" \
  --good "先统一画短横线跑通导出，结尾注明默认规则" \
  --bad "为这点小事停工弹窗等人工拍板" \
  --why "把人的注意力留给不可逆的关键决定" \
  --premise "仅限内部试跑与常规报表；正式外部合同表仍须人工确认"
```

## 三、能力边界诚实说明（本轻量包做什么 / 不做什么）

- **本仓库直接提供**：多窗口 JSONL（Claude Code & Codex）只读盘点、一页待办 `.html` 生成、好坏判断与前提档案维护、以及供你的 Agent 执行“五步内阁票拟”的完整 [`SKILL.md`](digital-cabinet/SKILL.md)（放入项目的 `skills/digital-cabinet` 即可使用）。
- **本轻量包不包含**：个人飞书机器人后台常驻推送与午夜定时守护进程（涉及个人 IM 凭证与本机常驻调度，我们刻意将其剥离在外，保持本工具 100% 零配置、零联网、零隐私风险）。

## 开源许可与致谢

- [MIT License](LICENSE) · 统筹与执行分离思路受 `deepseek-ai/dsh-superagent-prototype`（MIT）启发，代码与合成样例均为独立净室编写。
