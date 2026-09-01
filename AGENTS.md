# AGENTS.md — Truman Director 项目指令（权威版）

> 本文件是给所有 AI 编码代理（Claude Code / Codex / Cursor / ZCode …）与人类协作者的项目级约束。
> 上层用户级规则（中文回答、工具偏好等）与本文叠加生效。技术标识符保留英文。
> `CLAUDE.md` 只是指向本文件的薄指针——**改规则只改这里**。

## 项目定位

Truman Director 是一个 experience 类型的 **Anna App**：基于 tick 的迷你 AI 小镇模拟器。当前架构是 **本地 Executa 版**：

- **引擎活在 `src/truman_director/`**（Python stdio JSON-RPC plugin），bundle 经 `anna.tools.invoke` 驱动它；
- 居民决策来自 **`engine.decide`** —— 全项目唯一的居民决策 LLM 调用点（`narrate` 是日终叙事的认知调用，同样只经 sampling）；走 `sampling/createMessage` + `response_format: json_schema strict`；
- 世界快照存 APS KV `truman:run:world`（`storage.set` 反向 RPC）；
- **BYOK 时代**：开发/体验走用户自带 API key（平台 sampling 配额不再手动发放）。BYOK 链路的 `response_format` **会被平台转发层丢弃**——schema 约束不可依赖，见「LLM 调用约定」。

**用户需 Matrix Agent 在线** —— Executa 是本地子进程，Agent 离线则全断。bundle 只渲染 + 驱动时钟，不替模型决策；**模型是唯一的决策者**。

一个 Anna App = `manifest.json` + `app.json` + `bundle/`（界面）+ `src/truman_director/`（引擎）+ `executa.json`（发布声明）。

## 权威文档索引

| 文档 | 权威范围 |
| --- | --- |
| `docs/DESIGN.md` | 产品/架构设计契约（五层、红线、D1–D6、§8 前端 IA 与动效层、§13 可观测性、里程碑） |
| `docs/PUBLISH.md` | **发布流程唯一权威**（tag→Release→executa publish→cut→submit-review→release 状态机、checklist、坑表） |
| `docs/binary-distribution.md` | PyInstaller 二进制分发细节 |
| `docs/PRIVACY.md` | 隐私政策（Marketplace privacy_url 指向它） |

## 不可违背的核心原则（红线）

改动代码前先逐条对照。任何与下列原则冲突的「优化」都不算优化。

1. **模型是唯一决策者** — 不引入启发式、规则引擎、行为树、概率表。居民动作只能来自 `engine.decide`。bundle/plugin **绝不**替模型决策。解析层适配（`_extract_json` 的 think/fence/brace 剥离）与纠正式重试（`_sample_json`）是**解析**不是决策，不触犯本条。
2. **单一真相来源** — `WorldState`（`state.py`）与 APS KV `truman:run:world` 是同一份序列化的两端。不在别处维护影子状态；bundle 渲染直接读 storage 快照（`refresh()`）。
3. **单一编排入口** — plugin 的 `world` 工具是**唯一**推进世界的入口（8 个 action：`init`/`reset`/`tick`/`inject_event`/`list_scenarios`/`get_agent`/`get_timeline`/`get_story`）。`engine.tick`：推进时钟 → 排空导演注入（先于决策）→ 决策 → 应用/留痕 → 持久化 →（跨午夜）日终 narrate。
4. **失败要响亮** — 解析失败、反向 RPC 失败必须抛出冒泡；`_sample_json` 的重试（1 次，带模型自己的坏输出回炉）耗尽后响亮失败。**绝不**静默吞错、**绝不**降级默认行为。
5. **不玩并发花样** — 主线程 asyncio loop 串行处理 invoke；tick 串行。引擎就是「推进 → 问模型 → 应用 → 存」。

## 架构与文件组织

| 文件 | 职责 |
| --- | --- |
| `src/truman_director/plugin.py` | stdio JSON-RPC 主循环 + `world` 分发器（8 action + `lang` 参数）+ 反向 RPC 路由；`_build_world` 校验 lang（zh/en）；`tick` 可中途切语言；`get_agent` 返回双语档案字段 |
| `src/truman_director/engine.py` | **唯一 LLM 调用点**：`decide`（tick 决策）+ `narrate`（日终故事）+ `day_close`；`_sample_json`（json_schema + 纠正式重试 + 形状校验）；`_extract_json`（think/fence/brace 剥离，路径进取证日志）；`localized_view`（按 world.lang 单语言投影喂模型）；`MAX_TOKENS=4096`/`NARRATE_MAX_TOKENS=3072` |
| `src/truman_director/state.py` | `WorldState`（含 `lang`/`day`/`stories`）+ 双向序列化 + `apply_event`/`record_event`/`advance_tick`；Location.name_zh、Agent.name_zh/occupation_zh/goal_en |
| `src/truman_director/scenarios.py` | `cafe_town` 双语场景 + `DRAMATIC_OPENINGS`（title/hint/event 各有 `_en` 镜像）+ `build_from_spec` 校验 |
| `src/truman_director/storage.py` | APS KV 反向 RPC（`KEY="truman:run:world"`）；日志含字节数兼作快照体积监控 |
| `src/truman_director/prompts.yaml` | LLM prompt 单一来源：`system_prompt`（含 **OUTPUT FORMAT (strict)** 段）、`lang_rules`（zh/en）、`narrator_prompt`/`narrator_lang`/`narrator_tail` |
| `bundle/app.js` | 渲染层全部接线 + 动效（见 DESIGN §8 三波动效）；`window.__truman` 调试钩子（invokeWorld/refresh/onStart/onTick/showOpenings/pickOpening/dismissOpenings/toggleLang/lang） |
| `bundle/index.html` / `style.css` | 「导演监视器」：顶栏时间码 + 舞台（时相天色/剪影灯火/天气粒子/发光居民点）+ 今日故事/字幕（tick 分组）+ 导演注入栏；token 制 + rem 流体缩放；看戏模式；live-card 浮卡 |
| `scripts/local_e2e.py` | 协议级真 E2E 驱动：spawn 真插件 + 真 LLM 全链路（`MOCK=1` 离线回放）；Node 子进程 fetch 绕 Cloudflare TLS 指纹（1010） |
| `scripts/package_binary.sh` / `src/_entry.py` | PyInstaller 打包（单平台本地 / CI matrix） |
| `manifest.json` | `permissions`、`required_executas`、`system_prompt_addendum`、`ui.host_api`（**必须嵌套对象**，含 `agent.session.auto: true`——否则 Permission 保存失败，QA 整个 App 起不来） |
| `app.json` / `executa.json` | App 描述 + bundled executas / Executa 发布声明（`binary_urls` 镜像 GitHub Release，指向当前 tag） |

数据流（无环）：

```
bundle/app.js → anna.tools.invoke → plugin.world → engine.tick → {sampling.createMessage, storage.set}
bundle/app.js → anna.storage.get（渲染读取 plugin 写的同一 KV key）
```

## i18n 约定（zh/en）

- 语言三处生效：**UI 文案**（bundle `T` 字典 + 顶栏 中/EN 按钮 + localStorage `truman:lang`）、**人名/地名/目标**（快照 `name_zh`/`occupation_zh`/`goal_en`，缺失回退 canonical）、**LLM 输出**（`world.lang`，init/reset/tick 接受 `lang` 参数，`prompts.yaml#lang_rules` 按语言拼接）。
- `engine.localized_view` 保证模型只见单一语言（zh 换入 name_zh，en 换入 goal_en；缺失回退 canonical；另一语言的字段**剥离**，不泄漏进 prompt）。
- **历史内容保持生成时的语言**——不做机器翻译。
- 章节卡序号 zh=壹贰叁 / en=I II III。

## LLM 调用约定（BYOK 时代的关键坑）

- `decide`/`narrate` 是仅有的两个调用点。新认知需求走它们或 `_sample_json` 封装，**不要**另起 `sampling.createMessage`。
- **平台 BYOK 转发丢弃 `response_format`**（已向平台反馈，修复前 schema 不可依赖）：靠三层防御——① `prompts.yaml` 的 OUTPUT FORMAT (strict) 段；② `_extract_json` 剥 `<think>`/markdown 栅栏/最外层括号跨度；③ `_sample_json` 纠正式重试（1 次，形状校验失败也重试）。取证日志记录 `parse=direct/brace_span` 与重试次数。
- **思考模型（MiniMax-M3、glm-5.x）的 `<think>` 块吃 token 预算**——`MAX_TOKENS=4096`（平台 per-call 上限，mint token 内 `max_tokens_per_call` 可读）、narrate 3072。设小了 JSON 会在输出前被截断（症状：`resp` 很大但 `char 0` 解析失败）。
- strict json_schema 的历史怪癖仍在：host 偶尔解包单属性对象返回裸数组——dict|list 双容错保留。
- prompt 文案**只动** `prompts.yaml`（单一来源）。`manifest.json` 的 `system_prompt_addendum` 是给宿主对话 LLM 的协议字段，另管。

## 状态模型约定

- `snapshot()`/`from_snapshot()` 必须同步修改；`events` 快照取最近 20 条，内存列表上限 `MAX_EVENTS=500`；`stories` 上限 `MAX_STORIES=7`。
- `world.lang` 持久化在快照（0.3.x 旧快照回退 zh）。
- `apply_event`（改状态）+ `record_event`（留痕）成对；导演注入排队 `effective_tick = current + 1`，tick 内**先于** decide 排空；注入队列不持久化。

## bundle 风格（渲染层）

- ES module、无构建步骤；`tool_id` 从 `window.__ANNA_TOOL_IDS__` 解析；`invokeWorld` 容错三种返回形态。
- `onTick` 逐 tick invoke（`n:1` 循环），贴合 per-invoke sampling budget；**不要**一次 `tick n=N`。
- 任何动态文本进 `innerHTML` 前必须 `escapeHtml`。
- **真机踩过的前端坑**：
  - `world.locations`/`agents` 是 dict——用 `Object.keys/values`，不能 `for...of`（曾致 `object is not iterable` 开镇白屏）；
  - 自定义类名避免裸全局选择器（`.sub` 曾命中空舞台文案把它变成 grid 逐字竖排）——限定容器（`.subtitles .sub`）；
  - `stage.innerHTML = html` 会抹掉之前 `insertAdjacentHTML` 插入的图层——**附加层必须在 innerHTML 赋值之后插**（天气层踩过）;
  - 动画相位用 id 哈希播种负延迟，避免全员同步闪烁；一律只动 `transform/opacity`；`prefers-reduced-motion` 全局降级（已内置）。
- 动效层全景（三波）见 `docs/DESIGN.md` §8：时相天色、呼吸 glow、灯火、天气粒子、章节卡 stagger、时间码翻动、故事纸展开 + 打字机、字幕 tick 分组、看戏模式、live-card。

## 真机调试（opencli + harness）

- `window.__truman` 钩子驱动内部动作，不进 UI；`console` 是订阅制，事后 `opencli console` 读不到历史——要抓错误栈先在代码里埋日志再复现。
- harness 的 legacy 存储按 **session 隔离**：验证 init→tick→get 必须同一 tab；重启 harness / 新开 tab = 全新空世界（不是 bug）。
- iframe 报 `unknown session_id: sess-N` = stale session——**新开 tab** 即好。
- 视觉模型分析截图会误报（误读布局、输出退化）——**以 DOM 实测为准**（`getBoundingClientRect`、Range.getClientRects 数行数）。
- harness 顶部 **record 按钮** = golden fixture 录制入口（DESIGN §13.4 回归基线）。

## 发布（概要）

完整流程/状态机/checklist 见 `docs/PUBLISH.md`。发布顺序是：目标版本和四平台 `binary_urls` 先写入 git → tag 触发四平台构建 → Release 资产完整性门禁 → `apps push` → `executa publish` 冻结 ExecutaVersion → **真实 Windows Agent 安装 + App 开镇/tick** → `apps cut`。只看到 GitHub 资产或当前 Executa 记录不算通过，必须验证冻结快照。Marketplace 截图从 v0.4.5 起追加到同一个版本 Release；任何仍被 `app.json`/平台元数据引用的旧截图 Release 不得删除。`pending_review` 下不要重复 submit，cut 后必须回读审核候选。

## Git 与提交

- Conventional Commits：`type(scope): subject`；`node_modules/`、`.venv/`、`.shot*.png`、`docs/*-email.md` 等过程产物已 gitignore，**不要**提交（对外邮件草稿放 `../mail/`）。
- 仅在明确要求时提交 / 推送。

## 命令速查

```bash
uv sync                                  # 安装依赖（executa-sdk 为本地路径依赖 ../anna-executa-examples/sdk/python）
uv run pytest -q                         # 全量测试（80+）
uv run ruff format . && uv run ruff check .
pnpm exec anna-app validate              # manifest 校验（发布前必过）
pnpm exec anna-app dev --executa dir=.   # dev harness（:5180）。executa 在仓库根，必须显式 --executa dir=.
pwsh -File scripts/review_smoke_opencli.ps1  # Windows/OpenCLI 真实 LLM smoke + 5 张审核截图
env -u MOCK uv run python scripts/local_e2e.py   # 真 LLM 全链路 E2E（需 BYOK 健康 + Agent 在线）
MOCK=1 uv run python scripts/local_e2e.py        # 离线 mock 回放（协议链路验证）
# 直连 anna.partners 的探针若 TLS 断连（本机代理环境）：
#   NODE_USE_ENV_PROXY=1 HTTPS_PROXY=http://127.0.0.1:7890
bash scripts/package_binary.sh           # 本地 PyInstaller 打包（单平台）
```

## 平台契约坑速查（每条都真踩过）

1. manifest 必须 grant `llm.complete`，否则 sampling 反向 RPC `[-32603]`。
2. initialize 必须返回 `client_capabilities.sampling`，否则平台 Nexus 静默忽略 sampling（dev harness 不校验——别用 dev 通过否定平台报告）。
3. `ui.host_api` 是**嵌套对象**且需 `agent.session.auto: true`，否则权限保存失败、App/Tools 全部起不来（QA 审核拒稿根因）。
4. BYOK 转发丢 `response_format`（平台已确认修复中，防御层保留）。
5. 思考模型 `<think>` 吃 token——max_tokens 给满 4096。
6. call API 把 error code 抹成 `tool_failed`，业务 code 只剩 message 前缀——客户端解析前缀。
7. dev 存储按 session 隔离；stale session 报 `unknown session_id`。
8. Matrix Agent 必须在线（dev harness 本地直连会掩盖此问题）。
9. ExecutaVersion 是不可变快照：后来补 `windows-x86_64` 不会修复已冻结版本；Windows 真机安装失败时必须发新的 patch 版本，禁止继续 App cut/release。
10. Executa Hub 的 Install 页面在 `defaultAgentClientId` 为空时可能误选 `agents[0]`（实测落到 Cloud）；Network 中的 `/agents/<client_id>/plugins/reinstall` 才是实际目标证据。
