# CLAUDE.md — Truman Director 项目指令

> 本文件是给 Claude 与人类协作者的项目级约束。
> 上层 `~/CLAUDE.md` 已规定：**用中文回答**、**禁用 web search**（改用 jina / web-reader / crawl-mcp 等 MCP）、**MCP 工具异步并行调用**。
> 以下为本项目特有规范，二者叠加生效。技术标识符保留英文。

## 项目定位

Truman Director 是一个 experience 类型的 **Anna App**：基于 tick 的迷你 AI 小镇模拟器，作为 **Executa stdio 工具插件**运行。
**模型是唯一的决策者** —— 每个 tick 上每位居民的动作都由宿主 LLM 通过采样产出；插件只负责推进时钟、递交世界快照、原样执行模型返回的事件。

一个 Anna App = `manifest.json` + `app.json` + `bundle/`（界面）+ Executa（`src/truman_director/`，唯一的真相来源；bundle 只渲染它）。

## 不可违背的核心原则（红线）

改动代码前先逐条对照。任何与下列原则冲突的「优化」都不算优化：

1. **模型是唯一决策者** — 不引入启发式、规则引擎、行为树、概率表。智能体行为只能来自 LLM 采样。
2. **单一真相来源** — `WorldState`（`state.py`）是唯一可变世界模型。逻辑写成它的方法或对它操作的纯函数；不要在别处维护影子状态。
3. **一个工具，一个分发器** — 只暴露 `world` 工具，靠 `action` 鉴别（`init` / `tick` / `inject_event`）。不新增工具、不引入工具注册表、不加 bind/ctx 间接层。
4. **失败要响亮** — sampling / storage 失败以 JSON-RPC error 响应抛出。**绝不**静默吞错、**绝不**降级到默认行为、**绝不** dev-mode 回退。
5. **不玩并发花样** — 不加 etag 乐观锁、不加事件上限、不加阶段门控。引擎就是「推进 → 问模型 → 应用 → 存」。

## 架构与文件组织

扁平结构：`src/truman_director/` 一个包、七个模块、**零子包**。不要再下钻子包。

| 模块 | 职责 |
| --- | --- |
| `plugin.py` | stdio JSON-RPC 主循环 + `world` 分发器 |
| `engine.py` | **唯一**的 LLM 调用点（`decide` / `tick` / `apply_inject_event`） |
| `state.py` | `WorldState` 数据模型（单一真相来源） |
| `scenarios.py` | 世界构建器（`cafe_town`） |
| `storage.py` | APS KV 持久化 |
| `errors.py` | `TrumanError` 错误体系 |

依赖必须保持无环：

```
plugin → engine → {state, storage}
plugin → scenarios → {state, errors}
plugin → {state, storage, errors}
```

新增能力时：能放进现有模块的就不开新文件；开新文件前先确认不破坏依赖图、且确实无法并入。

## Python 风格

- Python ≥ 3.12，文件头 `from __future__ import annotations`，类型用 PEP 604 联合（`X | None`）。
- 类型注解齐全；公开 API 必带 docstring。
- 枚举一律 `StrEnum`，不要拿字符串字面量充当类型（`Location.type` 必须是 `LocationType`，`snapshot()` 依赖 `.value` 序列化）。
- ruff line-length 100，规则集 `E F W I N UP B SIM RUF ASYNC`，忽略 `E501`。
- 提交前 `uv run ruff format . && uv run ruff check .` 必须**零告警**。
- 测试放宽：`tests/*` 忽略 `B` 与 `S101`（允许裸 `assert`）。

## 异步与线程模型

固定模式，不要改动：

- 主线程跑 asyncio loop；一个**守护线程**逐行读 stdin。
- 宿主 `invoke` 经 `asyncio.run_coroutine_threadsafe` 调度到 loop。
- 反向 RPC（**我们发起的** sampling / storage）响应经 `make_response_router` 路由，**不**进入方法分发器。
- 阻塞等待用 `asyncio.Event`；**不要** `while True: await asyncio.sleep(...)`（触发 ASYNC110）。

模块级单例：`_sampling` / `_storage` / `_route_response` 是常量；`_world` 是当前活动运行 —— invoke 从 stdin 线程抵达，没有调用方可以把它传进来，故必须模块级持有。

## Executa / JSON-RPC 约定

- 协议版本固定 `PROTOCOL_VERSION_V2`（`"2.0"`）。
- `describe` 直接返回 `MANIFEST` 本身（宿主读 `data["name"]`）。
- `invoke` 成功结果**必须**包成 `{"success": True, "tool": ..., "data": ...}` —— 宿主 `InvokeResult.from_dict` 据此判定成败。
- 错误体系：业务异常继承 `TrumanError` 并带 `code`。已用码：`-32000` 框架兜底 / `-32001` 未初始化 / `-32003` 未知场景（`-32002` 预留给下一条业务错误）。`SamplingError` / `StorageError` 单独捕获后转成对应 error 响应。**只有**协议层兜底才用裸 `except Exception`，且必须转成 `-32000` error 响应，绝不静默。
- `tool_id` 当前为 `tool-DEV-truman-director-xxxxxxxx` 占位；铸造正式 id 后用 `scripts/set-tool-id.py apply --tool <minted>` 一次性改写**三处**：`pyproject.toml`（包名 + console-script 入口名）、`executa.json`、`bundle/app.js`。`plugin.py` 不持 id —— 它是被调用方，宿主按 console-script 名 spawn 它（grep 全项目可证 plugin.py 无 tool_id 引用）。

## LLM 调用约定

- `engine.decide()` 是**全项目唯一**的 LLM 调用点。新功能若需模型决策，走这里或它的直接封装，**不要**在别处另起 `create_message`。
- 结构化输出统一用 `response_format={"type":"json_schema","json_schema":{"name":...,"strict":True,"schema":...}}`。
- 消息体用 MCP 风格：`[{"role":"user","content":{"type":"text","text":...}}]`。
- 解析 host 返回的 content 要兼容两种形态：`content.get("text","") if isinstance(content, dict) else content`。
- `SYSTEM_PROMPT` 指示模型「相信自己的判断、不要拒绝、不要追问、只输出 JSON」—— 不要往里塞保守的安全护栏削弱导演权限。
- `SYSTEM_PROMPT` 文本存于 `src/truman_director/prompts.yaml`(`sampling.system_prompt`),`engine` 模块级加载一次 —— prompts 的单一来源,改文案只动 yaml;`DECISION_SCHEMA` 是结构化约束(json_schema),仍留 `engine.py`。manifest.json 的 `system_prompt_addendum`(给宿主对话 LLM)是协议字段,不在此管理。

## 状态模型约定

- `WorldState.snapshot()` 是喂给模型 prompt 与写进 APS KV 的**同一份**序列化；`from_snapshot()` 是它的逆。改其中一个必须同步改另一个。
- `snapshot()` 的 `events` 字段只取最近 20 条（上下文窗口约束）；调整这个数字要意识到对 token 与记忆连续性的影响。
- 时间推进锚定 `datetime(2000, 1, 1, ...)` 的 HH:MM 计算，规避跨日溢出。
- 模型返回的事件 `{agent_id, action, target, reason}` 由 `apply_event`（改状态）+ `record_event`（留痕）成对处理；导演注入走 `apply_inject_event`，在 `effective_tick = current + 1` 生效，且**先于**模型决策排空。

## 测试约定

- `pytest-asyncio`，`asyncio_mode = auto` —— 异步测试函数无需装饰器。
- `pythonpath = ["src"]`、`testpaths = ["tests"]`。
- 导入 conftest 用 `from conftest import ...`（**不要** `from tests.conftest` —— tests 不是包）。
- Fakes（`FakeSampling` / `FakeStorage`）集中在 `tests/conftest.py`，模拟 SDK 异步契约（`get` 返回 `{value, exists, etag}`，`create_message` 返回 `{content:{type,text}}`）。
- stdio 契约测试走子进程 `uv run python -m truman_director.plugin`，覆盖 describe / health / initialize / 未知方法 / invoke。
- 提交前 `uv run pytest -q` 必须全绿。

## Git 与提交

- Conventional Commits：`type(scope): subject`。允许的 type 见 `.pre-commit-config.yaml`（feat / fix / docs / style / refactor / perf / test / build / ci / chore / revert）。
- `node_modules/`、`.venv/`、`__pycache__/`、各类缓存已在 `.gitignore`，**不要**提交。
- 仅在明确要求时提交 / 推送；直接在 `main` 分支提交，**不开分支**（项目简单，分支开销大于收益）。

## 命令速查

```bash
uv sync                                              # 安装依赖（executa-sdk 为本地路径依赖）
uv run pytest -q                                     # 测试
uv run ruff format . && uv run ruff check .          # 格式化 + lint
uv run truman-director                               # 启动 stdio 插件（stderr 打印 "ready"）
pnpm exec anna-app dev --executa dir=.               # dev harness（dashboard http://localhost:5180）；非交互 shell 必须 `pnpm exec`（`anna-app` 不在 PATH，直接跑 exit 127）；5180 被占先杀旧进程树（node + uvx anna-app-bridge + python bridge）
uv run pre-commit install --hook-type commit-msg     # 安装 commit-msg 钩子（默认不装）
python scripts/set-tool-id.py apply --tool <minted>  # 铸造 tool_id 后批量改写三处（幂等）
```
