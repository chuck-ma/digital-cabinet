# Digital Cabinet（数字内阁 · v0.3.0 拆锁参谋长版）

> **Chuck 的 AI 折腾实验室 · 实验 01 配套开源小工具与 Skill**  
> 拒绝把 AI 总管搭成“事事求盖章、早晚背冷饭”的收发室秘书——借明代内阁大学士**「先调档查清原委、算透利弊，再拟方案请批红」**的真票拟逻辑，在多窗口之上单立一层**只读求证免批算穿、零冷饭折叠、跨窗违纪置顶吹哨**的统筹参谋。

## 一、v0.3.0 三刀换脑升级（对照第一版“盖章秘书”纠偏）

1. **第一刀 · 拆锁自治（`pre_verify_auto` vs `owner_approval`）**：把“只看不动的查日志、拉七天底数、算值不值”从人工审批锁里拆出来免批自查算穿，算不过账的伪点子直接淘汰，绝不跑 21 分钟只为请示“批不批准我去查只读日志”；只有改代码、发版等不可逆动作才带账本请批红。
2. **第二刀 · 零冷饭折叠与跨窗违纪置顶（`--prev-state` + `pinned_alerts`）**：传入上一期 `cabinet-state.json` 自动将零新变化的在途项折叠略过；遇到跨窗口口径打架、跳过前置算账盲干或《关于分析报告的分析》假忙活，直接破格置顶吹哨拦停。
3. **第三刀 · 留硬账与好坏判断默契档案（`learn`）**：每次拍板沉淀「好判断 + 坏判断 + 为什么 + 适用前提」，区分内部试跑放行与正式对外红线。

## 二、10 秒零配置体验（跑内置 8 窗口合成样例）

纯 Python 3 标准库（零第三方依赖），克隆后直接运行：

```bash
python3 digital-cabinet/scripts/cabinet.py demo --out ./demo-out --open
```

## 三、扫你自己的本地会话记录（严格只读）

常见本地会话目录位置：
- **Claude Code**：用户主目录下的 `.claude/projects/<项目目录名>/`
- **Codex CLI**：用户主目录下的 `.codex/sessions/2026/11/`

```bash
python3 digital-cabinet/scripts/cabinet.py scan \
  --dir /path/to/your/selected-session-folder \
  --prev-state ./my-cabinet-out/cabinet-state.json \
  --since-days 7 \
  --playbook ./my-decision-playbook.md \
  --out ./my-cabinet-out --open
```

## 四、能力边界诚实说明

- **本仓库直接提供**：多窗口 JSONL 只读盘点、拆锁自治分流、上期比对零冷饭折叠、违纪/假忙活置顶预警、一页作战面板 `.html` 生成与完整 [`SKILL.md`](digital-cabinet/SKILL.md)。
- **本轻量包不包含**：个人 IM 机器人常驻推送与夜间守护进程（保持 100% 零配置、零联网、零隐私风险）。

## 开源许可与致谢

- [MIT License](LICENSE) · 统筹与执行分离思路受开源社区多代理编排启发，代码与合成样例均为独立净室编写。
