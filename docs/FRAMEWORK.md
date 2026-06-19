# Framework Initialization & Extensibility Guide

> 给 `anna-truman-director/` 的"如何初始化一个 Anna App + 未来如何无痛扩展"的工程基线。
> 综合自 `../anna-executa-examples/` 的 SDK、focus-flow、visual-brand、embed-demo、llm-demo、aps-files-demo、storage-notebook、sampling-summarizer，以及 `../crawl-mcp/` 的 src layout / pre-commit / uv 工程范式。

**核心立场**：模型是唯一决策者。Plugin 不实现规则、不做本地降级、不为模型能力兜底。所有"决定"都通过 SamplingClient 问模型。

---

## 0. 不动的架构决策

1. **依赖 `executa_sdk`** — 覆盖 stdio loop + StorageClient + SamplingClient + `make_response_router`，省 ≈500 行模板。
2. **协议走 v2**（capabilities + reverse RPC）— sampling / files / embeddings 都要求 v2；省一次破坏性升级。
3. **Plugin 一个工具 + `action` 判别** — Anna UI Runtime 给每 tool 分一行 Executa。三个 action：`init` / `tick` / `inject_event`。
4. **决策权 100% 交给模型** — 没有 heuristic、没有 registry 装饰器、没有 phase gating、没有 dev-mode fallback、没有 etag 乐观并发、没有"events cap 100"。

---

## 1. 目录结构（src layout，对齐 crawl-mcp）

```
anna-truman-director/
├── pyproject.toml
├── .python-version                # 3.12
├── .pre-commit-config.yaml        # ruff format → ruff check --fix → pytest -q
├── README.md
├── src/
│   └── truman_director/
│       ├── __init__.py
│       ├── plugin.py              # Initialize 握手 + stdio loop + dispatcher
│       ├── manifest.py            # MANIFEST dict
│       ├── world/
│       │   ├── __init__.py
│       │   ├── state.py           # WorldState / Location / Agent + advance_tick
│       │   └── scenarios.py       # SCENARIOS dict + build()
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── decision.py        # decide() — 唯一：调 SamplingClient
│       │   └── reactor.py         # tick 编排：调模型 → apply → persist
│       ├── storage.py             # load / save 单 key snapshot
│       ├── api/
│       │   └── world_dispatch.py  # TOOL_DISPATCH = {"world": tool_world}
│       └── errors.py              # JSON-RPC 错误码映射
├── bundle/                        # static SPA
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── icon.svg
├── tests/
│   ├── test_world_dispatch.py     # 用 FakeHost 跑整轮 RPC
│   ├── test_storage.py
│   ├── test_clock.py
│   └── test_decision.py           # 用 mock SamplingClient
├── manifest.json                  # host_capabilities + required_executas + host_api
├── app.json                       # slug / name / bundled_executas
└── scripts/
    └── set-tool-id.py             # mint 后同步 tool_id
```

---

## 2. `pyproject.toml`

```toml
[project]
name          = "tool-<yourhandle>-truman-director-<hash>"
version       = "0.1.0"
description   = "Truman Director — Executa stdio tool plugin for the Truman Town Anna App"
requires-python = ">=3.12"
authors       = [{ name = "..." }]
license       = { text = "MIT" }
dependencies  = [
    "executa-sdk>=0.4",          # StorageClient + SamplingClient + rpc
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.6",
    "anna-executa-test>=0.1",
]

[project.scripts]
"tool-<minted>" = "truman_director.plugin:main"

[build-system]
requires      = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/truman_director"]

[tool.ruff]
line-length    = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "ASYNC", "SIM"]
```

---

## 3. Initialize 握手 + capability 声明

```python
# src/truman_director/plugin.py
from executa_sdk import PROTOCOL_VERSION_V2
from .manifest import MANIFEST

def handle_initialize(_params):
    return {
        "protocolVersion": PROTOCOL_VERSION_V2,
        "serverInfo":     {"name": MANIFEST["display_name"], "version": MANIFEST["version"]},
        "capabilities":   {
            "storage":  {"kv": True, "files": True},
            "sampling": {"enabled": True},
        },
    }
```

`manifest.json`：

```jsonc
{
  "schema": 2,
  "permissions": ["tools.invoke", "chat.write_message"],
  "host_capabilities": [
    "aps.kv",
    "aps.scope.app.read",
    "aps.scope.app.write",
    "aps.files",
    "llm.sample"
  ],
  "required_executas": [
    { "tool_id": "bundled:truman-director", "min_version": "0.1.0", "version": "latest" }
  ],
  "ui": {
    "bundle":   { "format": "static-spa", "entry": "index.html" },
    "views":    [{ "name": "main", "title": "Truman Town", "default": true, "entry": "index.html" }],
    "host_api": {
      "storage": ["get", "set", "list", "delete"],
      "tools":   ["required:bundled:truman-director"],
      "chat":    ["write_message"],
      "window":  ["set_title"]
    }
  }
}
```

---

## 4. async stdio loop

```python
# src/truman_director/plugin.py
import asyncio, json, sys, threading
from executa_sdk.storage  import StorageClient
from executa_sdk.sampling import SamplingClient
from executa_sdk.rpc      import make_response_router
from .manifest            import MANIFEST
from .api.world_dispatch  import TOOL_DISPATCH

METHOD_DISPATCH = {
    "describe": lambda _p: MANIFEST,
    "health":   lambda _p: {"status": "ok"},
    "invoke":   _invoke,
}

def _invoke(params):
    tool, args = params["tool"], params.get("arguments") or {}
    return {"success": True, "data": TOOL_DISPATCH[tool](**args)}

def main():
    sampling = SamplingClient.from_stdio()
    storage  = StorageClient.from_stdio()
    _state["sampling"] = sampling
    _state["storage"]  = storage
    asyncio.run(_serve())

def _serve():
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    router = make_response_router(SamplingClient, StorageClient)
    for line in sys.stdin:
        msg = json.loads(line)
        if msg.get("method") == "invoke":
            result = _invoke(msg["params"])
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": result}) + "\n")
            sys.stdout.flush()
```

**为什么 `make_response_router`**：StorageClient / SamplingClient 都会发 reverse RPC 请求，它们的 reader 必须共享 stdin。SDK 已经处理。

JSON-RPC 顶层**不**捕获业务异常——异常上抛走 JSON-RPC `error` 响应，host 会处理。`json.loads` 解析失败也直接 raise，让 host 重启 plugin。

---

## 5. Bundle 直连 host_api

```js
// bundle/app.js
import { AnnaAppRuntime } from "/static/anna-apps/_sdk/latest/index.js";

const SCENARIO_KEY = "truman-director:current-scenario";

async function init() {
  bindUi();
  window.anna = await AnnaAppRuntime.connect();
  const r = await window.anna.storage.get({ key: SCENARIO_KEY });
  if (r?.exists) document.getElementById("scenario").value = r.value;
}

document.getElementById("start").onclick = async () => {
  const scenario = document.getElementById("scenario").value;
  await window.anna.storage.set({ key: SCENARIO_KEY, value: scenario });
  await window.anna.tools.invoke({
    tool_id: window.__ANNA_TOOL_IDS__["truman-director"],
    method:  "world",
    args:    { action: "init", scenario },
  });
};
```

Bundle 持有 UI 状态（scenario、tick 速率、视图模式）。Plugin 持有 WorldState + 调用模型。`AnnaAppRuntime.connect()` 失败直接挂；不要"Standalone preview"。

Plugin 端存储用同一个 key：`truman:run:world`。Bundle 读它就是只读世界视图，不需要 plugin 开 `get_state` / `get_agent` / `get_timeline` action。

---

## 6. 决策（唯一：调 SamplingClient）

```python
# src/truman_director/agents/decision.py
import json
from executa_sdk.sampling import SamplingClient

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "agent_id":  {"type": "string"},
                    "action":    {"enum": ["move", "rest", "work", "talk"]},
                    "target":    {"type": ["string", "null"]},
                    "reason":    {"type": "string"},
                },
                "required": ["agent_id", "action", "reason"],
            },
        },
    },
    "required": ["events"],
}

SYSTEM = """You are the director of a small simulated town. Each tick (5 simulated minutes) you receive a JSON snapshot of the world (current_time, locations with occupants and types, agents with occupation/personality/state/relationships, recent events) and emit a JSON array `events` describing what each agent does.

`events` is `[{agent_id, action, target, reason}, ...]`:
- `action` is one of: `move`, `rest`, `work`, `talk`
- `target` is a `location_id` (move/work) or `agent_id` (talk), `null` for `rest`
- `reason` is a short natural-language justification (for logging)

Trust your judgment. Pick actions that make narrative sense. Don't refuse. Don't ask for clarification. Emit the JSON and nothing else."""

def decide(sampling: SamplingClient, world_view: dict) -> list[dict]:
    resp = sampling.create_message({
        "system":   SYSTEM,
        "messages": [{"role": "user", "content": json.dumps(world_view, ensure_ascii=False)}],
        "response_format": {"type": "json_schema", "schema": DECISION_SCHEMA},
    })
    return json.loads(resp.content)["events"]
```

**没有 heuristic、没有 fallback、没有 registry、没有 "on_unsupported" 降级**。模型返回什么用什么；解析失败让 host 看到错误。

---

## 7. Reactor（tick 编排）

```python
# src/truman_director/agents/reactor.py
from . import decision
from ..storage import save
from ..world.state import WorldState

def tick(world: WorldState, sampling, storage, n: int = 1) -> list[dict]:
    results = []
    for _ in range(n):
        world.advance_tick()
        world_view = world.snapshot()
        events = decision.decide(sampling, world_view)
        for evt in events:
            world.apply_event(evt)
            world.record_event(evt)
        storage.set("truman:run:world", world.snapshot())
        results.append({
            "tick":       world.current_tick,
            "world_time": world.current_time.isoformat(),
            "events":     events,
        })
    return results
```

每次 tick：推进时间 → 问模型 → 应用 → 持久化。**不**维护 events cap、**不**挑 highlight、**不**做 energy/social_battery 衰减——bundle 渲染时按 `importance` 排序、过期事件 model 自己判断要不要落进 timeline。

---

## 8. Storage（单 key，失败让 SDK 抛）

```python
# src/truman_director/storage.py
from executa_sdk.storage import StorageClient

KEY = "truman:run:world"

def load(storage: StorageClient) -> dict | None:
    r = storage.get(KEY, scope="app")
    return r["value"] if r["exists"] else None

def save(storage: StorageClient, snapshot: dict) -> None:
    storage.set(KEY, snapshot, scope="app")
```

单一 plugin 实例持有 WorldState；写入是单线程顺序的。失败让 SDK 抛，由 host 处理（重试 / 重置 plugin）——不要静默吞掉。

---

## 9. Scenarios（dict，不做装饰器注册）

```python
# src/truman_director/world/scenarios.py
from datetime import datetime
from .state import WorldState, Location, Agent

def _cafe_town(start: datetime) -> WorldState:
    return WorldState(
        current_time=start,
        locations={
            "home_alice": Location(id="home_alice", name="Alice's Home", capacity=2),
            "cafe":        Location(id="cafe",        name="Bean & Bite", capacity=8),
            "park":        Location(id="park",        name="Riverside Park", capacity=20),
            # ...
        },
        agents={
            "alice": Agent(id="alice", name="Alice", home="home_alice", occupation="barista"),
            # ...
        },
    )

SCENARIOS: dict[str, "callable"] = {
    "cafe_town": _cafe_town,
}

def build(slug: str, start: datetime) -> WorldState:
    if slug not in SCENARIOS:
        raise ValueError(f"unknown scenario: {slug!r}; available: {sorted(SCENARIOS)}")
    return SCENARIOS[slug](start)
```

加场景 = 加 builder 函数 + 一行 dict entry。**不**需要 `@register_scenario`、**不**需要 `_REGISTRY`、**不**需要 Protocol。

---

## 10. `manifest.json` / `executa.json` / `bundle/anna-tool-ids.js` 三件套

`executas/truman-director/executa.json`：

```jsonc
{
  "slug": "truman-director",
  "name": "Truman Director",
  "version": "0.1.0",
  "executa_type": "tool",
  "description": "LLM-directed tick-based town simulator.",
  "tool_id": "tool-<yourhandle>-truman-director-<hash>",
  "type": "python",
  "enabled": true,
  "distribution": {
    "active": "local",
    "profiles": { "local": { "type": "local", "supports_protocol": true } }
  }
}
```

`scripts/set-tool-id.py apply --tool <minted>` 同步 `executa.json` + `pyproject.toml [project.scripts]` + `bundle/app.js` 的 tool_id。`anna-app apps publish` 自动调用。

---

## 11. pre-commit（local hooks，对齐 crawl-mcp）

`.pre-commit-config.yaml`：

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
        pass_filenames: false
      - id: ruff-check
        name: ruff check --fix
        entry: uv run ruff check --fix
        language: system
        types: [python]
        pass_filenames: false
      - id: pytest
        name: pytest -q
        entry: uv run pytest -q
        language: system
        types: [python]
        pass_filenames: false
```

---

## 12. 与 docs/TECHNICAL.md 的关系

| 关注点 | TECHNICAL.md | FRAMEWORK.md |
|---|---|---|
| Anna 协议 / Reverse RPC | ✅ §7-§8 | — |
| UV / hatchling / pre-commit | ✅ §3-§5 | §2 + §11 |
| Tool ID 生命周期 | ✅ §12 | §10 |
| **决策 = SamplingClient，无 fallback** | — | §6 |
| **Reactor 单循环** | — | §7 |
| **Scenarios 字典** | — | §9 |
| **Storage 单 key** | — | §8 |
| **Bundle 直连 host_api** | — | §5 |

读文档顺序：`MVP.md`（需求） → `FRAMEWORK.md`（工程蓝图） → `TECHNICAL.md`（平台 reference）。

---

## 13. 初始化 checklist

1. `uv init --package anna-truman-director --python 3.12 src/truman_director`
2. `uv add executa-sdk`
3. `uv add --dev pytest pytest-asyncio ruff anna-executa-test`
4. 按 §1 建目录骨架
5. 拷 §2 的 `pyproject.toml`，name 占位 `tool-test-truman-director-12345678`
6. 写 `src/truman_director/plugin.py`（§3 握手 + §4 stdio loop + §5 init action）
7. 从 MVP §3 抽 `WorldState / Location / Agent`，写 `src/truman_director/world/state.py`
8. 写 `src/truman_director/agents/decision.py`（§6）
9. 写 `src/truman_director/agents/reactor.py`（§7）
10. 写 `src/truman_director/world/scenarios.py`（§9）
11. 写 `src/truman_director/storage.py`（§8）
12. 拷 focus-flow `scripts/set-tool-id.py`
13. 拷 §11 的 `.pre-commit-config.yaml`，`uv run pre-commit install`
14. `manifest.json` + `bundle/` 从 focus-flow + visual-brand 拷入口模板
15. `uv run pytest -q` 全绿后，去 https://anna.partners/executa mint 真 `tool_id`，跑 `set-tool-id.py apply`
16. `anna-app dev`

---

## 14. 参考链接

- `../anna-executa-examples/sdk/python/executa_sdk/` — Storage / Sampling / RPC
- `../anna-executa-examples/examples/python/storage-notebook/` — v2 握手 + stdio loop 范式
- `../anna-executa-examples/examples/python/sampling-summarizer/` — sampling 反向 RPC
- `../anna-executa-examples/examples/anna-app-focus-flow/` — bundled Executa + 三件套
- `../anna-executa-examples/examples/anna-app-visual-brand/bundle/app.js` — 纯 bundle 直连 host_api
- `../crawl-mcp/.pre-commit-config.yaml` — local hooks
- `../TrumanWorld/backend/app/sim/world.py` — WorldState 数据结构