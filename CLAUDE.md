# CLAUDE.md — Truman Director 项目指令

> 本文件是给 Claude 与人类协作者的项目级约束。
> 上层 `~/CLAUDE.md` 已规定：**用中文回答**、**禁用 web search**（改用 jina / web-reader / crawl-mcp 等 MCP）、**MCP 工具异步并行调用**。
> 以下为本项目特有规范，二者叠加生效。技术标识符保留英文。

## 项目定位

Truman Director 是一个 experience 类型的 **Anna App**：基于 tick 的迷你 AI 小镇模拟器。当前架构是 **本地 Executa 版（focus-flow）**：

- **引擎活在 `src/truman_director/`**（Python stdio JSON-RPC plugin），bundle 经 `anna.tools.invoke` 驱动它；
- 居民决策来自 **`engine.decide`** —— 全项目唯一的 LLM 调用点，走 Executa `sampling/createMessage` + **`response_format: json_schema strict`**（Executa 独有能力，纯云 `anna.llm.complete` 拿不到）；
- 世界快照存 APS KV `truman:run:world`（`storage.set` 反向 RPC）。

**用户需 Matrix Agent 在线** —— Executa 是本地子进程，Agent 离线则全断。bundle 只渲染 + 驱动时钟，不替模型决策；**模型是唯一的决策者**。

> 历史注记：本仓库曾有「纯云版」（引擎活在 `bundle/world.js`，用 `anna.llm.complete`，零本地依赖，0.2.2 已发布）。已并入本地 Executa 版统一主线；纯云源码在 git 历史 `5fcdf61` 及之前可回溯。两版取舍见 `docs/question.md`（纯云 vs Executa 的三难）。

一个 Anna App = `manifest.json` + `app.json` + `bundle/`（界面）+ `src/truman_director/`（引擎）+ `executa.json`（发布声明）。

## 不可违背的核心原则（红线）

改动代码前先逐条对照。任何与下列原则冲突的「优化」都不算优化。

1. **模型是唯一决策者** — 不引入启发式、规则引擎、行为树、概率表。居民动作只能来自 `engine.decide`（`src/truman_director/engine.py`）。bundle/plugin **绝不**替模型决策。
2. **单一真相来源** — `WorldState`（`state.py`，内存对象）与 APS KV `truman:run:world` 是同一份序列化的两端：`snapshot()` 写入、`from_snapshot()` 读出。不在别处维护影子状态；bundle 渲染直接读 storage 快照（`refresh()`）。
3. **单一编排入口** — plugin 的 `world` 工具（`plugin.py#_tool_world`，action 分发 `init`/`tick`/`inject_event`）是**唯一**推进世界的入口。`engine.tick` 推进时钟 → 排空导演注入（先于决策）→ 决策 → 应用/留痕每个事件 → 持久化。不绕过它直接改 world + storage，不引入第二个推进路径。bundle 驱动 tick 只能 `anna.tools.invoke({action:"tick"})`。
4. **失败要响亮** — `decide` 的模型输出解析不成 JSON events、`sampling` / `storage` 反向 RPC 失败，**必须**抛出并冒泡（JSON-RPC error code，见下）。**绝不**静默吞错、**绝不**降级到默认行为、**绝不** dev-mode 回退。
5. **不玩并发花样** — plugin 主线程 asyncio loop 串行处理 invoke（`run_coroutine_threadsafe`）；`tick` 串行；不加乐观锁、不加事件上限、不加阶段门控。引擎就是「推进 → 问模型 → 应用 → 存」。

## 架构与文件组织

引擎集中在 `src/truman_director/`（扁平包，无子模块）。bundle 是渲染层。

| 文件 | 职责 |
| --- | --- |
| `src/truman_director/plugin.py` | stdio JSON-RPC 主循环 + `world` 分发器（`init`/`tick`/`inject_event`）+ initialize 握手 + 反向 RPC 路由。模块级单例 `_sampling`/`_storage`/`_route_response`/`_world` |
| `src/truman_director/engine.py` | **唯一 LLM 调用点** `decide`（`sampling.createMessage` + json_schema）+ `tick` + `apply_inject_event` + `DECISION_SCHEMA` |
| `src/truman_director/state.py` | `WorldState` + `snapshot`/`from_snapshot` + `apply_event`/`record_event` + `advance_tick` |
| `src/truman_director/scenarios.py` | `cafe_town` 场景 + `build`/`build_from_spec` + spec 校验 |
| `src/truman_director/storage.py` | APS KV 反向 RPC（`KEY="truman:run:world"`，`load`/`save`） |
| `src/truman_director/errors.py` | `TrumanError` 体系 + 错误码 |
| `src/truman_director/prompts.yaml` | `SYSTEM_PROMPT`（`sampling.system_prompt`，engine 模块级加载一次） |
| `bundle/app.js` | UI 接线：`connect` runtime → `invokeWorld` 驱动 `init`/`tick`/`inject_event` → `refresh` 渲染。**只渲染、只接线，不决策** |
| `bundle/index.html` / `style.css` | 静态 SPA（map + timeline + director 注入框） |
| `src/_entry.py` | PyInstaller 打包入口 shim（绝对 import，见 binary 分发） |
| `manifest.json` | `permissions`（`tools.invoke` + host_api）、`required_executas`（`bundled:truman-director`）、`system_prompt_addendum`（平台 Anna 驱动） |
| `app.json` | App 描述 + `bundled_executas` |
| `executa.json` | Executa 发布声明（slug/version/tool_id/distribution） |

数据流（无环）：

```
bundle/app.js → anna.tools.invoke → plugin.world → engine.tick → {sampling.createMessage, storage.set}
bundle/app.js → anna.storage.get（渲染读取 plugin 写的同一 KV key）
```

## Python / Executa 风格

- Python ≥ 3.12，`from __future__ import annotations`，PEP 604 联合；枚举一律 `StrEnum`。
- ruff line-length 100，规则集 `E F W I N UP B SIM RUF ASYNC`，忽略 `E501`；测试放宽 `tests/*` 忽略 `B` 与 `S101`。
- 扁平包，依赖无环：`plugin → engine → {state, storage}`、`plugin → scenarios → {state, errors}`、`plugin → {state, storage, errors}`。新增能力优先并入现有文件。
- 异步线程模型：主线程 asyncio loop + 守护线程读 stdin；invoke 经 `asyncio.run_coroutine_threadsafe` 调度；反向 RPC（sampling/storage）经 `make_response_router` 路由，不进方法分发器；阻塞用 `asyncio.Event`，不用 `while True: await asyncio.sleep(...)`（ASYNC110）。

## Executa / JSON-RPC 约定

- 协议 `PROTOCOL_VERSION_V2`；`describe` 返回 `MANIFEST`；invoke 成功包 `{"success":True,"tool":...,"data":...}`。
- 错误码：`-32000` 框架兜底 / `-32001` 未初始化 / `-32002` 非法 spec / `-32003` 未知场景 / `-32004` 超预算。注意：call API（`/api/session/call`）把 plugin error code 抹成 `"tool_failed"`，业务 code 只留 message 的 `[code]` 前缀 —— 靠 code 区分业务错误**不可行**，客户端/测试解析 message 前缀。
- **initialize 握手必须返回 `client_capabilities.sampling`**（否则真实平台 Nexus gate 静默忽略 `sampling/createMessage`，decide 挂到超时）。dev harness 宽松不校验此字段 —— 别用 dev 通过去否定平台报告。

## LLM 调用约定

- `engine.decide(sampling, world_view)` 是**全项目唯一**的 LLM 调用点。新功能若需模型决策，走它或它的直接封装，**不要**在别处另起 `sampling.createMessage` / `anna.llm.complete`。
- decide 用 `response_format={"type":"json_schema","json_schema":{"name":"truman_tick_decision","strict":True,"schema":DECISION_SCHEMA}}`。**`DECISION_SCHEMA` 是 strict-compatible**（顶层 `additionalProperties:False`、`required:["events"]`、events items `required:["agent_id","action","target","reason"]`、`target` required-but-nullable）。
- **strict json_schema 不保证输出形状** —— host 偶尔返回裸数组 `[{...}]` 而非 `{"events":[...]}`。`decide` 对 `json.loads(text)` 必须 dict|list 双容错（`data["events"]` if dict else `data`）。这是解析层适配，非失败静默降级，不触犯红线 1。
- 消息体：`[{role:"user", content:{type:"text", text:json.dumps(world_view)}}]`，`system_prompt=SYSTEM_PROMPT`、`max_tokens=1024`、`timeout=60.0`。
- prompt 文案集中在 `prompts.yaml`（`sampling.system_prompt`），`engine` 模块级加载一次。指示模型「相信自己的判断、不要拒绝、不要追问、只输出 JSON」—— 不要往里塞保守的安全护栏削弱导演权限。改文案**只动** `prompts.yaml`（单一来源）。`manifest.json` 的 `system_prompt_addendum` 是给宿主**对话** LLM（Anna）的协议字段，与此不同、不在此管理。

## 状态模型约定

- `snapshot(world)` 是喂给 prompt 与写进 storage 的**同一份**序列化；`from_snapshot(data)` 是它的逆。改其一必须同步改另一个。
- `snapshot()` 的 `events` 只取最近 20 条（上下文窗口约束）；内存 events 列表**不截断**（持续累积）。
- 时间推进：`world_time`（`"HH:MM"`）→ 分钟数 `+tick_minutes` → 模 1440 防跨日 → 补零（`datetime` 锚点）。
- `locations[id].occupants` 是 `set[str]`：`move` 事件双向同步（旧位置 remove、新位置 add、更新 `current_location_id`）；`talk` 事件双向 `familiarity +0.05`（min 1.0）+ `last_interaction_tick`。
- 模型返回的事件 `{agent_id, action, target, reason}` 由 `apply_event`（改状态）+ `record_event`（留痕）成对处理；导演注入走 `apply_inject_event`，排队 `effective_tick = current + 1`，在 `tick` 内**先于** decide 排空（让居民在同一 tick 内对导演的「既成事实」做出反应）。注入是瞬态队列（`_pending_injections`），**不**持久化进 snapshot。

## bundle 风格（渲染层）

- ES module（`<script type="module">`），`AnnaAppRuntime.connect()` 直连 host_api。
- `tool_id` 运行时从 `window.__ANNA_TOOL_IDS__["truman-director"]` 解析（`anna-app dev`/`apps publish` 注入），dev 无 sidecar 时 fallback 到字面量。
- `invokeWorld(args)` 调 `anna.tools.invoke({tool_id, method:"world", args})`，容错三种返回形态（`{success,data}`/`{ok,result}`/裸 payload）。
- `onTick` 用 for 循环**逐 tick invoke**（每次 `action:"tick", n:1`），贴合 per-invoke sampling budget（max_calls 默认 8）；**不要**一次 `tick n=N`（会烧 budget 后半途失败留半应用世界）。
- 字符串模板/拼接注意 `escapeHtml`（防 XSS）：任何居民名、reason、描述进 `innerHTML` 前必须转义。
- 无构建步骤：`index.html` 直接 `<script src="app.js" type="module">`，SDK 走 `/static/anna-apps/_sdk/latest/index.js`。

## Anna（对话智能体）角色

平台 Anna（主对话）是**导演 / 叙事者**，时钟由 bundle 的 tick 按钮或 Anna invoke `world` 工具推进：

- **观察**：`anna.storage.get({key:"truman:run:world"})` 读世界（时钟、谁在哪、近期事件、关系演变）。
- **驱动**：可直接 invoke `method='world'` + `action='tick'/'inject_event'/'init'`（含 spec 自定义世界）。详见 `manifest.json` 的 `system_prompt_addendum`。
- **叙事**：把冷快照讲成故事。叙事基于 snapshot，不要凭空捏居民/地点/事件。

## Binary 分发

见 `docs/binary-distribution.md`。PyInstaller 把 plugin 打成平台二进制（`scripts/package_binary.sh` + `src/_entry.py` shim），GitHub Actions matrix 构建多平台，Agent 下载 spawn。`binary_urls` 在平台 Tool 配置页配，不写 `executa.json`。

## Git 与提交

- Conventional Commits：`type(scope): subject`。允许的 type 见 `.pre-commit-config.yaml`（feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert）。
- `node_modules/`、`.venv/`、`__pycache__/`、`build/`、`dist/`、`dist-anna/`、各类缓存已在 `.gitignore`，**不要**提交。
- 仅在明确要求时提交 / 推送。

## 命令速查

```bash
uv sync                                  # 安装依赖（executa-sdk 为本地路径依赖 ../anna-executa-examples/sdk/python）
uv run pytest -q                         # 引擎测试
uv run ruff format . && uv run ruff check .   # 格式化 + lint
pnpm exec anna-app dev --executa dir=.   # dev harness（dashboard http://localhost:5180，real 模式代理 staging）。非交互 shell 必须 `pnpm exec`；executa 不在默认 executas/ 下须显式 `--executa dir=.`
bash scripts/package_binary.sh           # 本地 PyInstaller 打包（单平台）→ dist-anna/<tool_id>-<platform>.tar.gz
# —— 平台契约坑（踩了才知，详见 forum topic 140 / 84）——
# • manifest 必须 grant llm.complete，否则 sampling 反向 RPC 报 [-32603]
# • initialize 必须返回 client_capabilities.sampling，否则平台 Nexus 静默忽略 sampling
# • Matrix Agent 必须在线，否则平台 Anna 调 executa 不通（dev harness 本地直连，掩盖此问题）
# • storage 在 dev 的 legacy 后端按 session 隔离，验证 init→tick→get 必须同一 session_id
```
