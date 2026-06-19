# CLAUDE.md — Truman Director 项目指令

> 本文件是给 Claude 与人类协作者的项目级约束。
> 上层 `~/CLAUDE.md` 已规定：**用中文回答**、**禁用 web search**（改用 jina / web-reader / crawl-mcp 等 MCP）、**MCP 工具异步并行调用**。
> 以下为本项目特有规范，二者叠加生效。技术标识符保留英文。

## 项目定位

Truman Director 是一个 experience 类型的 **Anna App**：基于 tick 的迷你 AI 小镇模拟器。
当前架构（P1，**纯云**）下，**整个引擎活在 `bundle/world.js` 里**，只用平台原生 Host API：

- `anna.llm.complete` —— 居民决策（**全项目唯一**的 LLM 调用点）；
- `anna.storage` —— 世界快照（KV `truman:run:world`）。

**没有 Executa、没有 Matrix Agent、没有本地 Python**：用户在 Anna 平台打开即用，零本地依赖。bundle 推进时钟、递交世界快照、原样执行模型返回的事件；**模型是唯一的决策者**。

一个 Anna App = `manifest.json` + `app.json` + `bundle/`（界面 + 引擎）。`bundle/world.js` 是唯一的真相来源。

> `src/truman_director/`（Python Executa）是 P1 迁移前的旧架构，**暂留作参考、非活跃**（见文末「参考实现」一节）。

## 不可违背的核心原则（红线）

改动代码前先逐条对照。任何与下列原则冲突的「优化」都不算优化。红线约束的是**活跃架构（bundle）**：

1. **模型是唯一决策者** — 不引入启发式、规则引擎、行为树、概率表。居民动作只能来自 `anna.llm.complete`（`world.js#decide`）。bundle **绝不**替模型决策（如「没人说话就让大家都 rest」这种默认行为是禁区）。
2. **单一真相来源** — `WorldState`（内存对象，定义于 `bundle/world.js`）与 `anna.storage` 的 KV `truman:run:world` 是同一份序列化的两端：`snapshot()` 写入、`fromSnapshot()` 读出。不在别处维护影子状态；bundle 渲染直接读 storage 快照（`refresh()`）。
3. **单一编排入口** — `tick()`（`world.js`）是**唯一**推进世界的函数：推进时钟 → 排空导演注入（先于决策）→ 决策 → 应用/留痕每个事件 → 持久化。不绕过它直接改 world + storage，不引入第二个推进路径。（迁移前是「一个工具一个分发器」；去 Executa 后改写为本条。）
4. **失败要响亮** — `decide` 的模型输出解析不成 JSON events、`llm.complete` / `storage` 调用失败，**必须**抛出并冒泡到 UI（`setStatus(..., "err")`）。**绝不**静默吞错、**绝不**降级到默认行为、**绝不** dev-mode 回退。
5. **不玩并发花样** — JS 单线程，`tick` 串行；不加乐观锁、不加事件上限、不加阶段门控。引擎就是「推进 → 问模型 → 应用 → 存」。

## 架构与文件组织

扁平结构，引擎集中在 `bundle/world.js` 一个文件（plain object + 纯函数，无 class、无子模块）。其余文件各司其职：

| 文件 | 职责 |
| --- | --- |
| `bundle/world.js` | **唯一真相来源 + 唯一 LLM 调用点**：`WorldState` 构造、`snapshot`/`fromSnapshot`、`advanceTick`、`applyEvent`/`recordEvent`、`decide`、`tick`、`applyInjectEvent`、`cafeTown`/`buildFromSpec`/`validateSpec` |
| `bundle/app.js` | UI 接线：`connect` runtime → `hydrate` → `onStart`/`onTick`/`onInject` → `refresh` 渲染。**只渲染、只接线，不决策** |
| `bundle/index.html` / `style.css` | 静态 SPA（map + timeline + director 注入框） |
| `manifest.json` | `permissions`（host_api：`storage`/`llm`/`chat`/`window`，**无 `tools`**）、`system_prompt_addendum`（Anna 为顾问） |
| `app.json` | App 描述（无 `bundled_executas`） |

数据流（无环）：

```
app.js → world.js → {anna.llm.complete, anna.storage}
app.js → anna.storage（渲染读取）
```

新增能力时：能并入 `world.js` 的就不开新文件；开新文件前先确认不破坏数据流、且确实无法并入。`world.js` 内部按「常量 → 构造 → snapshot → 时间 → apply/record → 注入 → decide → tick → 场景 → 校验」分区，新增函数落到对应区。

## JS / bundle 风格

- ES module（`<script type="module">`），`import` 用相对路径（`./world.js`）。
- plain object + 纯函数，贴合现有 bundle 风格；**不用 class**。
- 公开 API 带 JSDoc 注释；私有 helper 不导出。
- 枚举用 `Object.freeze({...})` 的值映射（如 `LocationType`），`snapshot()` 依赖其 `.value` 序列化 —— **不要**拿裸字符串字面量充当类型。
- 字符串模板/拼接注意 `escapeHtml`（防 XSS）：任何居民名、reason、描述进 `innerHTML` 前必须转义。
- 无构建步骤：`index.html` 直接 `<script src="app.js" type="module">`，SDK 走 `/static/anna-apps/_sdk/latest/index.js`。改完即生效（dev harness 热加载）。

## LLM 调用约定

- `world.js#decide(anna, worldView)` 是**全项目唯一**的 LLM 调用点。新功能若需模型决策，走它或它的直接封装，**不要**在别处另起 `anna.llm.complete`。
- **`anna.llm.complete` 不支持 `response_format`/json_schema**（结构化输出只有 Executa `sampling/createMessage` 有）。所以 decide 靠 `SYSTEM_PROMPT` 强约束输出 JSON `{events:[...]}`，再 `parseEvents` 稳健解析：去 ```` ```json ```` 围栏 → `JSON.parse` → 失败则切最外层 `{…}`/`[…]` → dict 取 `.events`、list 直取。解析失败**响亮 throw**（红线 4），不静默。这是纯云架构下唯一的可靠性妥协。
- 消息体：`[{role:"user", content:{type:"text", text:JSON.stringify(worldView)}}]`，带 `systemPrompt: SYSTEM_PROMPT`、`maxTokens: 1024`、第二参 `{timeoutMs: 60_000}`。
- 兼容 host 返回的两种形态：`content.text`（对象）或裸字符串。
- `SYSTEM_PROMPT`（常量，定义于 `world.js` 顶部）指示模型「相信自己的判断、不要拒绝、不要追问、只输出 JSON」—— 不要往里塞保守的安全护栏削弱导演权限。改文案**只动** `world.js` 的 `SYSTEM_PROMPT` 常量（单一来源）。`manifest.json` 的 `system_prompt_addendum` 是给宿主**对话** LLM（Anna）的协议字段，与此不同、不在此管理。

## 状态模型约定

- `snapshot(world)` 是喂给 prompt 与写进 storage 的**同一份**序列化；`fromSnapshot(data)` 是它的逆。改其一必须同步改另一个。
- `snapshot()` 的 `events` 只取最近 20 条（上下文窗口约束）；内存 events 列表**不截断**（持续累积）。bundle 刷新页面后 `fromSnapshot` 会恢复这 20 条 —— **与 Python 参考实现不同**（Python 进程不重启，故 `from_snapshot` 不恢复 events）；bundle 必须恢复，否则刷新后下一个 tick 会用空 events 覆盖历史。
- 时间推进：`world_time`（`"HH:MM"`）→ 分钟数 `+tick_minutes` → 模 1440 防跨日 → 补零。等价于 Python 的 `datetime(2000,1,1,...) + timedelta` 锚点。
- `locations[id].occupants` 是 JS `Set`（等价 Python `set[str]`）：`snapshot` 排序转数组、`fromSnapshot` 转回 Set。`move` 事件双向同步（旧位置 `delete`、新位置 `add`、更新 `current_location_id`）；`talk` 事件双向 `familiarity +0.05`（min 1.0）+ `last_interaction_tick`。
- 模型返回的事件 `{agent_id, action, target, reason}` 由 `applyEvent`（改状态）+ `recordEvent`（留痕）成对处理；导演注入走 `applyInjectEvent`，排队 `effective_tick = current + 1`，在 `tick()` 内**先于** decide 排空（让居民在同一 tick 内对导演的「既成事实」做出反应）。注入是瞬态队列（`_pending_injections`），**不**持久化进 snapshot —— 刷新页面会丢失未消费的注入，可接受。

## Anna（对话智能体）角色约定

去 Executa 后，Anna **没有 tick 工具可调**（它的工具只有原生 Host API + Executa，而我们去了 Executa）。所以 Anna 是**观察者 / 顾问**，不是时钟：

- **观察**：`anna.storage.get({key:"truman:run:world"})` 读世界（时钟、谁在哪、近期事件、关系演变）。
- **叙事**：把冷快照讲成故事。
- **建议而非执行**：用户想干预（暴雨、陌生人登场）时，Anna 用自然语言描述，并提示用户在前端注入框输入、按 tick 按钮。Anna **不能**自己发起注入 —— 注入由用户在前端执行。

详见 `manifest.json` 的 `system_prompt_addendum`。

## Git 与提交

- Conventional Commits：`type(scope): subject`。允许的 type 见 `.pre-commit-config.yaml`（feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert）。
- `node_modules/`、`.venv/`、`__pycache__/`、各类缓存已在 `.gitignore`，**不要**提交。
- 仅在明确要求时提交 / 推送；直接在 `main` 分支提交，**不开分支**（项目简单，分支开销大于收益）。

## 命令速查

```bash
pnpm exec anna-app dev                   # dev harness（dashboard http://localhost:5180）；默认 real 模式，llm.complete+storage 代理 staging。非交互 shell 必须 `pnpm exec`（`anna-app` 不在 PATH，直接跑 exit 127）。5180 被占先杀旧进程树（node + uvx anna-app-bridge + python bridge）
node bundle/world.test.mjs               # bundle 引擎回归测试（零依赖，断言 world.js 移植正确性：推进/双向同步/snapshot 对称/inject 时序/parse 容错/spec 校验）
# —— 以下仅维护 src/ 参考实现时用 ——
uv sync                                  # 安装依赖（executa-sdk 为本地路径依赖）
uv run pytest -q                         # Python 参考版测试
uv run ruff format . && uv run ruff check .   # 格式化 + lint
```

---

## 参考实现（`src/truman_director/`，**暂留、非活跃**）

P1 迁移前的 Executa stdio 架构，逻辑已 1:1 移植到 `bundle/world.js`。保留是为了 git 可回退与行为对比。**以下约束仅在维护该参考实现时生效**，与上面的活跃架构约束互不覆盖：

- 扁平包结构：`plugin.py`（stdio JSON-RPC 主循环 + `world` 分发器）、`engine.py`（唯一 LLM 调用点 `decide`/`tick`/`apply_inject_event`）、`state.py`（`WorldState`）、`scenarios.py`（`cafe_town`）、`storage.py`（APS KV）、`errors.py`（`TrumanError` 体系）。依赖无环：`plugin → engine → {state, storage}`、`plugin → scenarios → {state, errors}`、`plugin → {state, storage, errors}`。
- Python ≥ 3.12，`from __future__ import annotations`，PEP 604 联合；枚举一律 `StrEnum`；ruff line-length 100，规则集 `E F W I N UP B SIM RUF ASYNC`，忽略 `E501`；测试放宽 `tests/*` 忽略 `B` 与 `S101`。
- 异步线程模型：主线程 asyncio loop + 守护线程读 stdin；invoke 经 `asyncio.run_coroutine_threadsafe` 调度；反向 RPC（sampling/storage）经 `make_response_router` 路由，不进方法分发器；阻塞用 `asyncio.Event`，不用 `while True: await asyncio.sleep(...)`（ASYNC110）。模块级单例 `_sampling`/`_storage`/`_route_response`/`_world`。
- Executa/JSON-RPC：协议 `PROTOCOL_VERSION_V2`；`describe` 返回 `MANIFEST`；`invoke` 成功包 `{"success":True,"tool":...,"data":...}`；错误码 `-32000` 框架兜底 / `-32001` 未初始化 / `-32002` 非法 spec / `-32003` 未知场景 / `-32004` 超预算。
- 结构化输出用 `response_format={"type":"json_schema","json_schema":{"name":...,"strict":True,"schema":...}}`（Executa sampling 独有能力，bundle 版 `anna.llm.complete` 没有此能力 —— 这正是 P1 迁移的可靠性妥协点）。
- `SYSTEM_PROMPT` 存于 `src/truman_director/prompts.yaml`（`sampling.system_prompt`），`engine` 模块级加载一次；`DECISION_SCHEMA` 留 `engine.py`。
- 测试：`pytest-asyncio`，`asyncio_mode=auto`，`pythonpath=["src"]`，`testpaths=["tests"]`；conftest 用 `from conftest import ...`；Fakes（`FakeSampling`/`FakeStorage`）集中 `tests/conftest.py`；stdio 契约测试走子进程 `uv run python -m truman_director.plugin`。
- `tool_id` 改写：`scripts/set-tool-id.py apply --tool <minted>` 批量改 `pyproject.toml` / `executa.json` / `bundle/app.js` 三处（幂等）。
