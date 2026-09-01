# Marketplace 审核反馈闭环

> 最后核对：2026-09-01。这里区分“本地已验证”和“平台已复审”；只有后者才能写成 Marketplace 审核通过。

## 1. 来源与基线

- 2026-08-19，Anna Developer Team 对 **World Director (Local) v0.3.3** 给出 `Changes Required`。
- 原始附件保存在仓库外的 `../review/review_3.3/`，包括中英文 Marketplace Review 和 Functional Test Evidence。
- 审核时 App 安装、Related Tools 安装和 Tool bundling 已通过；失败集中在 frontend / Tool execution / permission，导致 TC-01～TC-05 与 Security 全部未验证。
- 平台当前状态（2026-09-01 CLI 实查）：线上 latest v0.3.3，v0.4.3（version_id=521）仍为 `pending_review`。

## 2. 审核问题闭环矩阵

| 审核项 | 原结果 | 当前状态 | 当前证据 | 仍需补充 |
|---|---|---|---|---|
| App frontend invocation | Fail | 本地已修 | `manifest.json#ui.host_api` 改为嵌套对象；harness 可开镇并正常渲染 | 平台 QA 复跑并截图/录屏 |
| Related Tool execution | Fail | 本地已修 | `initialize`、`describe`、`world` invoke 均成功；真实 LLM 连续 3 tick 成功 | 平台环境保存 tool trace |
| Permission configuration | Needs Fix | 本地已修 | `host_api.agent.session.auto: true`；`anna-app validate` 通过 | 平台权限保存成功证据 |
| Marketplace product page / screenshots | Needs Fix | 新版候选图已生成 | Developer Console 已填 homepage/support/privacy/cover；2026-09-01 以 Anna CLI + OpenCLI 生成 7 张当前 UI 图 | 选定 4～5 张后上传新 Release，并更新 Console URL |
| Language support | Needs Fix（截图缺失牵连） | 本地已修 | 中文/英文地点、居民、控件和同 tick 时间码切换通过 | 两种语言各留一张当前版本证据 |
| Security | Needs Confirmation | 本地已验证 | CSP、最小权限、动态文本 `escapeHtml`、无已跟踪密钥；未知 action/agent/target 明确失败；浏览器 XSS smoke 未执行 payload | 平台 QA 复跑 |
| Product differentiation | Needs Confirmation | 本地已验证 | APS 世界快照、居民自主 LLM 决策、定向注入、关系/位置/活动持久化、插件重启恢复 | 平台 QA 复跑 TC-04 / TC-05 |

## 3. TC-01～TC-05 当前状态

### TC-01 — Observe current town state

**本地通过。** Bundle 能显示地点、居民位置、当前活动和时间线；`get_agent` 能返回目标、关系与近事。

复审证据应同时包含：输入 prompt、`get_agent` 或 storage/tool trace、前端居民档案截图。

### TC-02 — Observe autonomous resident interactions

**本地通过。** 2026-09-01 harness 真实 LLM 连续推进 3 tick；居民产生 move/work/talk/rest，关系和字幕同步更新。

复审时应明确“不注入事件”，再推进至少 3 tick，保存每 tick 的工具输出和最终前端。

### TC-03 — Intervene with a town-wide event

**本地通过。** 戏剧开场通过 `inject_event` 注入 `world_change`，下一 tick 先落账、再进入模型上下文；真实 LLM 后续理由持续引用陌生人事件。

复审建议使用原 QA 暴雨 prompt，并保存：注入 ack、同 tick 模型输入中的 world_change、后续 3 tick 反应和天气/字幕 UI。

### TC-04 — Intervene with an individual resident

**本地通过，平台待复核。** 2026-09-01 使用结构化 `inject_event` 将“Alice 获得 500 元机会基金”以 `agent_id=alice`、`importance=0.95` 注入。事件以 `actor_agent_id=alice` 落账；真实 LLM 在同一 tick 让 Alice 移动到咖啡馆，并在理由中明确引用“中了 500 块”。居民档案的近事同时显示注入事件和后续动作。

当前 bundle 的自由文本注入默认只发送 `{reason}`，没有可视化居民选择器；定向干预需要输入结构化 JSON。数据模型也没有“金钱”专用字段，长期效果由事件、模型后续决策和关系/位置/活动状态共同表达。

提审前二选一：

1. 最小方案：用结构化 `inject_event` 对指定居民注入机会，连续推进 3～5 tick，证明该居民及其他居民的后续行为可追溯到事件；把输入/输出固化成 fixture。
2. 产品方案：在 bundle 增加居民选择器，并为需要长期保持的个人状态设计明确字段；这属于更强的产品差异化改动。

本地证据见 [`QA-EVIDENCE-2026-09-01.md`](QA-EVIDENCE-2026-09-01.md)；在平台 QA 复跑前仍不能宣称 Marketplace 闭环。

### TC-05 — Observe continued world evolution

**本地通过，平台待复核。** 新增 acceptance runner 使用真实 stdio 插件和共享 APS-like KV：定向事件落账后连续推进，关闭插件进程，再启动新插件；`get_agent` 恢复同一 run、Alice↔Bob familiarity 和 500 元事件，随后仍能继续 tick。

世界快照会保存位置、活动、关系、最近事件和日终故事。事件只在模型快照中保留最近窗口，因此更长周期后果仍应落到关系、位置、活动或故事等持久字段，而不能只依赖一条旧事件永远留在上下文里。

复审证据应覆盖：一次注入 → 至少 5 个后续 tick → 进程/Agent 重启 → 恢复同一世界 → 再推进 1 tick，并对比注入前后的关系、活动、位置或故事。

## 4. BYOK 平台反馈

- 2026-08-18：报告三家 provider 在 `app/complete` 全部 HTTP 500。
- 2026-08-24：Jiao 邮件确认平台侧 bug，并要求发到论坛统一追踪。
- 2026-08-24：已发布官方论坛 topic 256。
- 2026-08-27：Anna 工程团队在 topic 256 回复“Confirmed & fixed”，修复 BYOK model-selection 路径并加入端到端回归；修复随 `v1.1.0-beta.144` 发布。
- 2026-09-01：本地 harness 的真实 LLM bridge 已成功完成 3 tick，说明开发链路可用；但仍应按原三 provider 矩阵做一次精确复测，并在 topic 256 回帖确认，才算沟通闭环。

官方线程：<https://forum.anna.partners/t/app-complete-returns-http-500-for-every-byok-provider-glm-deepseek-minimax-while-the-non-byok-path-stays-healthy/256>

## 5. 下一次提交审核前的证据包

- 当前版本空舞台、开场选择、居民点亮、定向干预、日终故事截图。2026-09-01 已生成本地 QA 截图，正式 Marketplace 图仍需去掉 harness/RPC 外框后重拍。
- TC-01～TC-05 每项：用户输入、tool_id/method/args、工具输出、最终前端结果、QA 结论。
- 一份默认 Windows 环境 mock E2E 日志，证明无需手动 `PYTHONUTF8=1`。
- 一份真实 LLM harness 日志，证明 BYOK / sampling 正常。
- 一份重启恢复证据，证明 APS KV 中的世界状态和可见后果未丢失。
- Security：动态文本转义、CSP、权限最小化、非法 action/agent_id、存储或 sampling 失败响亮返回。

## 6. 当前不能宣称的事项

- v0.4.3 尚未获得 Marketplace 审核通过。
- 当前 `main` 不是平台正在审核的 v0.4.3 冻结快照。
- TC-04 / TC-05 / Security 已本地通过，但尚未由平台 QA 复核。
- BYOK 官方修复尚未在论坛由本账号回帖确认。
