# Truman Director — 技术文档

> **版本**: v0.2 (清理防御模式)
> **日期**: 2026-06-18
> **配套文档**: [`MVP.md`](./MVP.md)（产品 / 范围 / 用户旅程）、[`FRAMEWORK.md`](./FRAMEWORK.md)（工程蓝图）
> **目标读者**: 接手本项目的开发者、Anna 平台审核人员、参赛评委
> **设计立场**: 模型是唯一决策者。Plugin 不实现规则、不做本地降级、不为模型能力兜底。

---

## 〇、文档元信息

| 项目 | 值 |
|------|---|
| **项目名** | `anna-app-truman-director`（bundle handle） / `truman-director`（executa handle） |
| **Tool ID（开发期）** | `tool-DEV-truman-director-xxxxxxxx` |
| **Python 版本** | `>=3.12`，通过 `.python-version` 锁定 |
| **包管理器** | [UV](https://docs.astral.sh/uv/)（Astral） |
| **构建后端** | hatchling（包） + PyInstaller（多平台二进制） |
| **布局** | `src` layout（包代码在 `executas/truman-director/src/truman_director/`，不在仓库根） |
| **风格** | ruff format + ruff check（line-length=100） |
| **测试** | pytest + pytest-asyncio + pytest-cov |
| **CI** | GitHub Actions：lint / unit / protocol / build |

---

## 一、项目概览

### 1.1 一句话定义

**Truman Director 是一款 Anna App。它在 Anna 聊天里运行一个迷你 AI 小镇：3-6 个 Agent 在咖啡馆、公园、图书馆之间自由生活；用户作为"导演"通过 SKILL 对话和 iframe UI 观察、注入事件，但不能替 Agent 思考。所有 Agent 决策由 SamplingClient 调模型完成。**

### 1.2 技术栈

```
┌─────────────────────────────────────────────────────────────┐
│  Bundle (iframe SPA)        │  Pure HTML/CSS/JS ES module   │
│  AnnaAppRuntime SDK         │  /static/anna-apps/_sdk/...   │
├─────────────────────────────────────────────────────────────┤
│  Skill (SKILL.md)           │  Markdown + YAML frontmatter  │
├─────────────────────────────────────────────────────────────┤
│  Executa (truman-director)  │  Python 3.12+ stdio JSON-RPC  │
│  ┌─────────────────────┐    │  uv-managed, src layout       │
│  │ truman_director/     │    │  hatchling + PyInstaller      │
│  │  ├── plugin.py      │    │                               │
│  │  ├── world.py       │    │  dataclass 数据模型           │
│  │  ├── engine.py      │    │  Tick 编排                    │
│  │  ├── decision.py    │    │  SamplingClient 调模型        │
│  │  ├── scenarios.py   │    │  cafe_town 预设               │
│  │  └── storage.py     │    │  APS KV 反向 RPC              │
│  └─────────────────────┘    │                               │
├─────────────────────────────────────────────────────────────┤
│  Anna Host                  │  matrix-nexus + dashboard     │
│   - APS (KV 存储)           │  - Anna Storage 反向 RPC      │
│   - Tool runtime            │  - Chat 前缀 / host_api ACL   │
│   - LLM (供 SKILL + 插件调用)│  - Tool ID 路由               │
└─────────────────────────────────────────────────────────────┘
```

### 1.3 与两份参考项目的对应关系

| 参考 | 我们从中抄了什么 | 改写 / 砍掉了什么 |
|------|----------------|-----------------|
| [`anna-executa-examples/anna-app-focus-flow`](https://github.com/whtcjdtc2007/anna-executa-examples) | manifest.json / app.json / bundle 三件套、单 dispatcher 模式、stdio loop 框架、SKILL.md frontmatter 格式、annoa-app CLI 用法 | dispatcher 名 `session` → `world`；state 持久化本地文件 → APS KV；8 个 action → 3 个 action（删 get_state/get_agent/get_timeline/reset/list_scenarios） |
| [`TrumanWorld/backend`](https://github.com/your-org/truman-world) | `sim/world.py` 的 WorldState dataclass 设计 | PostgreSQL + SQLAlchemy → APS KV JSON；Claude SDK Reactor → SamplingClient；heuristics.py + Director AI 三件套 → 删，模型直接决策 |

### 1.4 与 crawl-mcp 的工程基线对齐

[本仓库从 `gqy20/crawl-mcp`](https://github.com/gqy20/crawl-mcp) 继承了三个工程基线决策：

1. **Python 3.12**（`requires-python = ">=3.12"` + `.python-version = "3.12"`）
2. **`uv` 唯一包管理**（无 pip / poetry / pdm）
3. **`.pre-commit-config.yaml` 用 local hooks**：`ruff format` → `ruff check --fix` → `pytest -q`

差别：crawl-mcp 用 hatchling 打包 MCP server，本项目同样用 hatchling 打包 **Executa plugin**（`[project.scripts]` 暴露 `tool-DEV-truman-director-xxxxxxxx = "truman_director.plugin:main"`）。

---

## 二、架构总览

### 2.1 Anna App 三件套

```
Anna App
├── manifest.json          Anna 平台读到这份 → 决定权限 / Tool ID 路由 / CSP / UI 入口
├── app.json               "商店元数据"：slug / 名称 / 截图 / bundled_executas 映射
├── bundle/                iframe SPA（用户看的窗口）
│   ├── index.html         Anna App Runtime 装载入口
│   ├── app.js             SDK 通信 + 状态管理 + 渲染
│   ├── style.css          Anna 品牌色变量
│   ├── icon.svg           任务栏图标
│   └── anna-tool-ids.js   发布期生成：handle → minted tool_id 映射
├── executas/              一个或多个 Executa 子目录
│   └── truman-director/   我们的核心插件
│       ├── SKILL.md       行为剧本（不是插件代码，是 LLM 的指令集）
│       ├── executa.json   发布期元数据（slug/name/version/executa_type）
│       ├── pyproject.toml hatchling 包配置 + tool_id 占位
│       └── src/truman_director/    src layout 的 Python 包
└── tests/                 pytest 单元 / 协议 / fixture
```

### 2.2 三大运行时通信模型

**正向（Bundle / Skill → Executa）：**
```
anna.tools.invoke({
  tool_id: "<minted tool_id>",
  method:  "world",
  args:    { action: "tick", n: 5 },
})
  ↓ JSON-RPC 2.0 over stdio
truman_director/plugin.py → TOOL_DISPATCH["world"]() → reactor.tick(world, sampling, storage, n=5)
  ↓ 返回
{ results: [{tick, world_time, events}, ...] }
```

**反向（Executa → Anna Host）：**
```
truman_director/decision.py → SamplingClient.create_message(...)
  ↓ 反向 JSON-RPC
anna.llm.sample({ system, messages, response_format })
  ↓ 响应
{ content: "{\"events\":[...]}" }

truman_director/storage.py → StorageClient.set(...)
  ↓ 反向 JSON-RPC
anna.storage.set({ key: "truman:run:world", value: JSON })
```

### 2.3 数据流：tick 是怎么转起来的

```
1. 用户在聊天说 "推进 10 tick"
   ↓
2. Anna LLM 读取 SKILL.md 上下文
   ↓
3. LLM 决定调用 world(action="tick", n=10)
   ↓
4. Anna Tool runtime spawns Executa 子进程（如果尚未启动）
   ↓
5. plugin.py 收到 invoke 请求
   ↓
6. tool_world("tick", n=10) → reactor.tick(world, sampling, storage, n=10)
   ↓
7. reactor 循环 10 次：
   - world.advance_tick()                   # world_time +5min, current_tick++
   - world_view = world.snapshot()
   - events = decision.decide(sampling, world_view)   # ← 唯一决策入口
   - for evt in events:
       world.apply_event(evt)
       world.record_event(evt)
   ↓
8. storage.save(world) → anna.storage.set({key:"truman:run:world", value:JSON})
   ↓
9. 返回 [{tick, world_time, events}, ...]
   ↓
10. Bundle 收到响应 → 更新地图 / 时间线 / agent 详情
   ↓
11. Skill 总结："这 10 tick 里发生了 3 件有意思的事..."
```

---

## 三、项目结构（src layout）

### 3.1 顶层目录树

```
anna-truman-director/                          # 仓库根 = Anna App 根
├── README.md                                  # 项目说明（安装 / 运行 / 截图）
├── MVP.md                                     # 产品 / 范围 / 用户旅程（已存在）
├── TECHNICAL.md                               # 本文档
├── FRAMEWORK.md                               # 工程蓝图（已存在）
├── CHANGELOG.md                               # 版本变更
├── LICENSE                                    # MIT
│
├── .python-version                            # "3.12"
├── .gitignore                                 # Python / UV / PyInstaller / anna-app
├── .pre-commit-config.yaml                    # ruff format → ruff check → pytest
├── .editorconfig                              # UTF-8 / LF / 4-space indent
├── pyproject.toml                             # 仓库根：anna-app CLI 工作区
├── uv.lock                                    # UV 锁文件（自动生成，提交）
│
├── app.json                                   # Anna App 商店元数据 + bundled_executas 映射
├── manifest.json                              # schema:2 manifest（permissions / ui / host_api / dev）
├── package.json                               # pnpm 工作区元数据 + scripts（dev/validate/test）
├── pnpm-workspace.yaml                        # 标识 monorepo（只一个包）
│
├── bundle/                                    # iframe SPA
│   ├── index.html                             # 入口（AnnaAppRuntime.connect 装载点）
│   ├── app.js                                 # SDK 通信 + state + 渲染
│   ├── style.css                              # Anna 品牌色 + CSS Grid 地图
│   ├── icon.svg                               # 任务栏图标
│   └── anna-tool-ids.js                       # 发布期生成（dev 时 404 不影响）
│
├── executas/                                  # 所有 Executa 子目录
│   └── truman-director/                       # 唯一 plugin handle
│       ├── SKILL.md                           # Director 行为剧本
│       ├── executa.json                       # 发布期元数据
│       ├── README.md                          # plugin 单独说明（开发指南）
│       ├── pyproject.toml                     # hatchling 包配置 + tool_id 占位
│       ├── src/
│       │   └── truman_director/               # ★ src layout：包名 = "truman_director"
│       │       ├── __init__.py                # 版本号 / 公开 API
│       │       ├── plugin.py                  # stdio loop + TOOL_DISPATCH + tool_world
│       │       ├── world.py                   # dataclass: World / Agent / Location / Event
│       │       ├── engine.py                  # tick() / init_world() / inject_event()
│       │       ├── decision.py                # decide() — SamplingClient
│       │       ├── scenarios.py               # SCENARIOS["cafe_town"] + build()
│       │       ├── storage.py                 # APS KV 反向 RPC 封装
│       │       └── errors.py                  # 自定义异常 + JSON-RPC error code 映射
│       └── tests/                             # ★ 与 src 平级的 tests（不走 src layout）
│           ├── conftest.py
│           ├── unit/
│           │   ├── test_world.py
│           │   ├── test_engine.py
│           │   ├── test_decision.py           # mock SamplingClient
│           │   └── test_scenarios.py
│           └── protocol/
│               └── test_plugin_contract.py    # JSON-RPC over stdio 端到端
│
├── tests/                                     # 顶层测试（Anna App 级别）
│   ├── conftest.py
│   ├── bundle/
│   │   └── app.spec.ts                        # vitest：UI 渲染 / 交互
│   └── integration/
│       └── test_anna_app.py                   # 用 anna-app validate + fixture verify
│
├── fixtures/                                  # anna-app fixture verify 用
│   ├── happy-path.jsonl
│   ├── tick-10.jsonl
│   └── inject-weather.jsonl
│
├── scripts/                                   # 仓库内工具脚本
│   ├── set-tool-id.py                         # 同步 minted tool_id → 4 个文件
│   ├── build-binary.sh                        # 调 PyInstaller 出 4 平台 tar.gz
│   └── run-plugin.sh                          # 本地 stdio 调试入口
│
└── docs/
    ├── MVP.md                                 # 已存在
    ├── TECHNICAL.md                           # 本文档
    ├── FRAMEWORK.md                           # 已存在
    ├── ARCHITECTURE.md                        # 架构详解（未来）
    └── SCENARIOS.md                           # 场景设计指南（未来）
```

### 3.2 `src/truman_director/` 模块拆分原则

按 **职责单一 + 测试独立** 切：

| 模块 | 行数预算 | 单元测试 | 依赖 |
|------|---------|---------|------|
| `world.py` | ~200 | `test_world.py` | 无 |
| `scenarios.py` | ~80 | `test_scenarios.py` | world |
| `decision.py` | ~60 | `test_decision.py` | SamplingClient |
| `engine.py` | ~120 | `test_engine.py` | world / decision / storage |
| `storage.py` | ~40 | mock Anna stdio 测 | executa_sdk |
| `plugin.py` | ~120 | `test_plugin_contract.py` 端到端 | 上述全部 |
| `errors.py` | ~40 | (错误码对照表) | 无 |

**总预算**：约 700 行 Python（含注释），单测 400 行左右。**比 v0.1 少一半**，因为 heuristic / registry / etag / safe_set 全部删了。

### 3.3 为什么不把测试放进 src？

两个原因：

1. **测试要 import 包外的 fixtures / mocks**，src layout 的包一旦 `from __future__ import absolute_import` 就只能 import `truman_director.*`，无法从 `tests/` 反向注入。
2. **PyInstaller 打包时不希望包含测试代码**。`executas/truman-director/tests/` 平级放在 src 之外，打包脚本直接 `cp -r src dist/`，干净。

---

## 四、开发环境与 UV

### 4.1 一次性安装

```bash
# 1. 安装 uv（如果还没装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. clone 仓库
git clone https://github.com/your-org/anna-truman-director.git
cd anna-truman-director

# 3. 同步环境（自动读 .python-version 创建 .venv）
uv sync

# 4. 安装 pre-commit 钩子
uv run pre-commit install
```

### 4.2 `uv` 常用命令

| 命令 | 用途 |
|------|------|
| `uv sync` | 按 uv.lock 创建 / 更新 `.venv` |
| `uv add <pkg>` | 加运行时依赖（更新 pyproject.toml + uv.lock） |
| `uv add --group dev <pkg>` | 加开发依赖（写入 `[dependency-groups.dev]`） |
| `uv run <cmd>` | 在 `.venv` 里跑命令（自动激活） |
| `uv run pytest -q` | 跑测试 |
| `uv run ruff format .` | 格式化 |
| `uv run ruff check . --fix` | lint 自动修复 |
| `uv run python -m truman_director.plugin` | 本地启 plugin stdio 循环 |
| `uv build` | 出 sdist + wheel |
| `uv tool run pyinstaller ...` | 出多平台二进制（CI 中用） |

### 4.3 `.python-version`

```
3.12
```

锁死解释器版本，避免本地用 3.11 / 3.13 跑出隐式行为差异。`uv sync` 自动读这个文件。

### 4.4 与 `anna-app` CLI 协作

`anna-app` 是 Node 工具，**不进 Python venv**，独立通过 `pnpm` / `npm` 安装：

```bash
# 一次性全局装（也可在仓库根 pnpm install）
pnpm add -g @anna-ai/cli

# 然后在仓库根跑：
anna-app dev                    # 起完整 Anna App 调试器
anna-app validate --strict      # 三层校验（manifest / executa / bundle）
anna-app fixture verify fixtures/*.jsonl
anna-app apps publish           # 发布（首次会 mint tool_id）
anna-app executa dev            # 只跑 plugin（REPL 模式，最快的本地循环）
```

**为什么用 pnpm 而不是 npm？** Focus Flow 模板示例用 pnpm，我们保持一致。

---

## 五、代码风格与 pre-commit

### 5.1 `.pre-commit-config.yaml`（参考 crawl-mcp）

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format .
        language: system
        types: [python]

      - id: ruff-check
        name: ruff check
        entry: uv run ruff check . --fix
        language: system
        types: [python]
        pass_filenames: false

      - id: pytest
        name: pytest
        entry: .venv/bin/python -m pytest -q
        language: system
        types: [python]
        pass_filenames: false
```

**为什么是 local repo 而不是 `pre-commit/pre-commit-hooks`？** 我们用 `uv run` 而不是全局 `python`，且 ruff / pytest 已经 dev-dependency 装在 `.venv` 里——直接调 system 命令更稳。

### 5.2 `pyproject.toml` 的 ruff / pytest 配置

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
src = ["executas/truman-director/src"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "SIM", "RUF"]
ignore = ["E501"]  # line-length 由 formatter 管

[tool.ruff.lint.per-file-ignores]
"executas/truman-director/tests/*" = ["B"]  # 测试允许 assert

[tool.pytest.ini_options]
testpaths = ["executas/truman-director/tests", "tests"]
pythonpath = ["executas/truman-director/src"]
asyncio_mode = "auto"
addopts = "-q --cov=truman_director --cov-report=term-missing"
```

### 5.3 pre-commit 不通过怎么办

| 现象 | 原因 | 处理 |
|------|------|------|
| `ruff format` 改了一堆文件 | 之前没格式化 | `uv run ruff format .` 后重 `git add` |
| `ruff check --fix` 改了一堆文件 | 同上 + import 排序 | 同上 |
| `pytest -q` 失败 | 测试挂了 | 先 `uv run pytest -x` 看第一个错 |
| hook 跑得慢 | pytest 全量跑 | 改成 `pytest -q --co` 只收集用例（见 5.4） |

### 5.4 性能优化（可选）

pre-commit 每次 commit 都跑全量测试，3-5 秒还行，30 秒就难受。可以用 `pytest-xdist`：

```toml
dev = [
    "pytest-xdist>=3.6",
    # ...
]

[tool.pytest.ini_options]
addopts = "-q -n auto --cov=truman_director"
```

---

## 六、模块详解

### 6.1 `world.py` — 数据模型

**职责**：所有 in-memory 状态用 `@dataclass` 表达。不依赖任何外部库（连 `uuid` 都不用，全靠外部注入）。

```python
from dataclasses import dataclass, field
from enum import Enum

class LocationType(str, Enum):
    CAFE = "cafe"
    PARK = "park"
    LIBRARY = "library"
    HOME = "home"
    STREET = "street"

@dataclass
class Location:
    id: str
    name: str
    type: LocationType
    x: int  # 0-100, UI 百分比
    y: int
    capacity: int = 10
    description: str = ""

@dataclass
class Relationship:
    other_agent_id: str
    familiarity: float = 0.0
    trust: float = 0.5
    affinity: float = 0.0
    last_interaction_tick: int = 0

@dataclass
class Memory:
    tick: int
    content: str
    importance: float = 0.5
    memory_type: str = "observation"  # observation/interaction/reflection

@dataclass
class Agent:
    id: str
    name: str
    occupation: str
    home_location_id: str
    current_location_id: str
    personality: dict = field(default_factory=dict)
    memories: list[Memory] = field(default_factory=list)
    relationships: dict[str, Relationship] = field(default_factory=dict)

@dataclass
class Event:
    id: str
    tick: int
    event_type: str  # move/talk/work/rest/director_inject/world_change
    actor_agent_id: str | None
    target_agent_id: str | None = None
    location_id: str | None = None
    description: str = ""
    payload: dict = field(default_factory=dict)
    importance: float = 0.5
    created_at: float = 0.0

@dataclass
class WorldState:
    run_id: str
    scenario: str
    current_tick: int = 0
    world_time: str = "08:00"   # HH:MM
    tick_minutes: int = 5       # 1 tick = 5 模拟分钟
    locations: dict[str, Location] = field(default_factory=dict)
    agents: dict[str, Agent] = field(default_factory=dict)
    events: list[Event] = field(default_factory=list)
    created_at: float = 0.0
    last_tick_at: float = 0.0

    def advance_tick(self) -> None:
        """+1 tick，world_time 推进 tick_minutes 分钟"""
        from datetime import datetime, timedelta
        h, m = map(int, self.world_time.split(":"))
        dt = datetime(2000, 1, 1, h, m) + timedelta(minutes=self.tick_minutes)
        self.world_time = dt.strftime("%H:%M")
        self.current_tick += 1

    def snapshot(self) -> dict:
        """JSON 序列化入口（喂模型 + 存 APS KV 用）"""
        from dataclasses import asdict
        return asdict(self)

    @classmethod
    def from_snapshot(cls, data: dict) -> "WorldState":
        """JSON 反序列化入口（从 APS KV 读出时用）"""
        # ... re-construct from dict
```

**设计要点**：
- `Location.x/y` 是 0-100 整数，UI 用百分比定位，不用 canvas。
- `events` 不在 `world.py` 里做 cap —— bundle 渲染时按 `importance` 排序，模型自己判断哪些进 timeline。`v0.1` 里 `events cap 100` 已删除。
- **没有** `energy` / `social_battery` / `hunger` 这类 magic number 字段 —— 决策完全交给模型，`state` 维度由模型在 prompt 里推理。

### 6.2 `scenarios.py` — 场景预设

```python
from datetime import datetime
from .world import WorldState, Location, Agent

def _cafe_town(start: datetime) -> WorldState:
    return WorldState(
        run_id=f"run_{int(datetime.now().timestamp() * 1000)}",
        scenario="cafe_town",
        world_time="08:00",
        locations={
            "loc_cafe": Location(id="loc_cafe", name="晨光咖啡馆", type="cafe",
                                 x=60, y=40, capacity=8,
                                 description="小镇的社交中心"),
            # ... 完整列表见 MVP §9.1
        },
        agents={
            "agent_alice": Agent(
                id="agent_alice", name="Alice", occupation="咖啡师",
                home_location_id="loc_alice_home",
                current_location_id="loc_alice_home",
                personality={"openness": 0.8, "conscientiousness": 0.7,
                            "extraversion": 0.7, "agreeableness": 0.8},
            ),
            # ... Bob / Truman
        },
    )

SCENARIOS: dict[str, callable] = {
    "cafe_town": _cafe_town,
}

def build(slug: str, start: datetime) -> WorldState:
    if slug not in SCENARIOS:
        raise ValueError(f"unknown scenario: {slug!r}; available: {sorted(SCENARIOS)}")
    return SCENARIOS[slug](start)
```

**改动 vs v0.1**：删了 `list_scenarios()` / `get_scenario()` —— bundle 写死 `["cafe_town"]` select 即可，不需要 plugin 开 action 暴露。删了 `cfg.get("current_goal")` / `cfg.get("personality", {})` —— builder 直接构造 dataclass，缺字段让 builder 报错而不是默认值兜底。

### 6.3 `decision.py` — 决策（唯一：调 SamplingClient）

```python
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

SYSTEM = """You are the director of a small simulated town. Each tick (5 simulated minutes) you receive a JSON snapshot of the world (current_time, locations with occupants and types, agents with occupation/personality/relationships, recent events) and emit a JSON array `events` describing what each agent does.

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

**改动 vs v0.1**：整段 `decide_action()` 启发式 + `pick_talk_target()` 加权打分 + `random.choice` 漫步 + `energy -= 0.01` magic decay 全部删除。决策权 100% 交给模型。

**没有**：heuristic fallback、`on_unsupported: "json_object"` 降级、`Protocol` + `STRATEGIES` registry、`if action not in VALID: raise` 校验。模型返回什么用什么；解析失败让 host 看到错误。

### 6.4 `engine.py` — Tick 编排

```python
from . import decision
from .storage import save

def tick(world, sampling, storage, n: int = 1) -> list[dict]:
    """推进 n 个 tick，返回每个 tick 的结果"""
    results = []
    for _ in range(n):
        world.advance_tick()
        world_view = world.snapshot()
        events = decision.decide(sampling, world_view)
        for evt in events:
            world.apply_event(evt)
            world.record_event(evt)
        save(storage, world.snapshot())
        results.append({
            "tick":       world.current_tick,
            "world_time": world.world_time,
            "events":     events,
        })
    return results

def apply_inject_event(world, event_spec: dict) -> dict:
    """导演注入事件，下一 tick 生效"""
    from uuid import uuid4
    injection_id = f"inj_{uuid4().hex[:8]}"
    world._pending_injections.append({
        "id": injection_id,
        "effective_tick": world.current_tick + 1,
        "spec": event_spec,
    })
    return {
        "injection_id": injection_id,
        "effective_tick": world.current_tick + 1,
        "message": f"已注入事件，将在 tick {world.current_tick + 1} 生效",
    }
```

**改动 vs v0.1**：
- 删 `_pick_highlight()` —— bundle 自己按 `importance` 排序。
- 删 `events cap 100` —— 不在 plugin 侧限制事件流。
- 删 `agent.state["energy"] -= 0.01` 这类 magic number 衰减 —— 模型在 prompt 里自行判断 agent 状态演化。

### 6.5 `storage.py` — APS KV 反向 RPC

```python
from executa_sdk.storage import StorageClient

KEY = "truman:run:world"

def load(storage: StorageClient) -> dict | None:
    r = storage.get(KEY, scope="app")
    return r["value"] if r["exists"] else None

def save(storage: StorageClient, snapshot: dict) -> None:
    storage.set(KEY, snapshot, scope="app")

# Key 命名规范
KEYS = {
    "world":    "truman:run:world",     # ~5KB
    "timeline": "truman:run:timeline",  # ~10KB（如要避免 world 单 key 超限，可分）
    "meta":     "truman:run:meta",      # {created_at, scenario, tick_count, last_inject_id}
}
```

**改动 vs v0.1**：
- 删 `safe_set()`（容错章节已整体删除，§8.3）。
- 删 `Phase 1 兜底：本地开发期（`anna-app executa dev` 不连宿主）用 `~/.anna/truman-director/state.json` —— 直接用 executa_sdk 的 FakeHost 跑测试，`anna-app dev` 就连真 host，不做本地降级。
- 删 `if resp.get("ok")` 链 —— SDK 直接抛异常。
- 删 etag 乐观并发 —— 单一 plugin 实例顺序写入，无并发。

### 6.6 `plugin.py` — Executa stdio 入口

**核心骨架**：

```python
#!/usr/bin/env python3
"""truman-director — Executa stdio tool plugin (single-dispatcher method)"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from typing import Any

from executa_sdk.storage  import StorageClient
from executa_sdk.sampling import SamplingClient
from executa_sdk.rpc      import make_response_router

from .world     import WorldState
from .engine    import tick, apply_inject_event
from .scenarios import build
from .storage   import load as storage_load, save as storage_save
from . import __version__

MANIFEST: dict[str, Any] = {
    "display_name": "Truman Director",
    "version": __version__,
    "description": "LLM-directed tick-based town simulator.",
    "tools": [{
        "name": "world",
        "description": (
            "Manage Truman Town simulation. Use 'action' to select operation: "
            "init | tick | inject_event."
        ),
        "parameters": [
            {"name": "action",     "type": "string",  "required": True},
            {"name": "scenario",   "type": "string",  "required": False},
            {"name": "n",          "type": "integer", "required": False},
            {"name": "event",      "type": "object",  "required": False},
        ],
    }],
    "runtime": {"type": "uv", "min_version": "0.1.0"},
}


_state: dict[str, Any] = {"world": None, "sampling": None, "storage": None}


def tool_world(action: str, **kwargs) -> dict:
    """单 dispatcher：按 action 分发到 3 个具体实现"""
    if action == "init":
        scenario = kwargs["scenario"]
        start = _now()
        world = build(scenario, start)
        storage_save(_state["storage"], world.snapshot())
        _state["world"] = world
        return {"scenario": scenario, "tick": 0}

    world = _state["world"]
    if world is None:
        raise RuntimeError("world not initialized; call action='init' first")

    if action == "tick":
        n = kwargs.get("n", 1)
        return {"results": tick(world, _state["sampling"], _state["storage"], n)}

    if action == "inject_event":
        return apply_inject_event(world, kwargs["event"])

    raise ValueError(f"unknown action: {action!r}")


TOOL_DISPATCH = {"world": tool_world}


# --- JSON-RPC handlers ---

def handle_initialize(_params):
    return {
        "protocolVersion": "2.0",
        "serverInfo":      {"name": MANIFEST["display_name"], "version": MANIFEST["version"]},
        "capabilities":    {
            "storage":  {"kv": True, "files": True},
            "sampling": {"enabled": True},
        },
    }

def handle_describe(_params): return MANIFEST

def handle_invoke(params):
    tool, args = params["tool"], params.get("arguments") or {}
    payload = TOOL_DISPATCH[tool](**args)
    return {"success": True, "data": payload}

def handle_health(_params):
    return {"status": "ok", "version": __version__}

METHOD_DISPATCH = {
    "initialize": handle_initialize,
    "describe":   handle_describe,
    "invoke":     handle_invoke,
    "health":     handle_health,
}


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> None:
    print(f"[truman-director] v{__version__} ready", file=sys.stderr)
    _state["sampling"] = SamplingClient.from_stdio()
    _state["storage"]  = StorageClient.from_stdio()
    router = make_response_router(SamplingClient, StorageClient)

    for line in sys.stdin:
        line = line.strip()
        if not line: continue
        req = json.loads(line)
        req_id, method, params = req.get("id"), req.get("method"), req.get("params") or {}
        handler = METHOD_DISPATCH.get(method)
        if not handler:
            send({"jsonrpc":"2.0","id":req_id,"error":{"code":-32601,"message":f"unknown method: {method}"}})
            continue
        result = handler(params)
        send({"jsonrpc":"2.0","id":req_id,"result":result})


def _now():
    from datetime import datetime
    return datetime.now()


if __name__ == "__main__":
    main()
```

**改动 vs v0.1**：
- 8 个 action → 3 个：`init` / `tick` / `inject_event`。删 `get_state` / `get_agent` / `get_timeline` / `reset` / `list_scenarios` —— bundle 直接 `anna.storage.get("truman:run:world")` 读。
- `handle_invoke` 去掉 `try/except Exception` —— 异常上抛走 JSON-RPC `error` 响应。
- `main()` 去掉 `try/except json.JSONDecodeError: send(error); continue` —— host 给的非法 JSON 直接 raise，让 host 重启 plugin。
- MANIFEST parameters 去掉所有 `default: ...` —— 模型调用时显式给值。
- `Make response_router` 多 client 复用 —— SamplingClient + StorageClient 都要 reverse RPC，reader 必须共享。

---

## 七、Executa 协议

### 7.1 JSON-RPC 2.0 over stdio

```
宿主 (Anna)                              插件 (truman-director)
   │                                          │
   │─── {"jsonrpc":"2.0","id":1,            ──>│
   │      "method":"initialize"}               │
   │                                          │
   │<── {"jsonrpc":"2.0","id":1,            ───│
   │      "result":{protocolVersion,           │
   │                capabilities}}             │
   │                                          │
   │─── {"jsonrpc":"2.0","id":2,            ──>│
   │      "method":"describe"}                 │
   │                                          │
   │<── {"jsonrpc":"2.0","id":2,            ───│
   │      "result":<MANIFEST>}                 │
   │                                          │
   │─── {"jsonrpc":"2.0","id":3,            ──>│
   │      "method":"invoke",                  │
   │      "params":{"tool":"world",           │
   │               "arguments":{              │
   │                 "action":"init",          │
   │                 "scenario":"cafe_town"}}  │
   │                                          │
   │<── {"jsonrpc":"2.0","id":3,            ───│
   │      "result":{                          │
   │        "success":true,                   │
   │        "data":<WorldSnapshot>}}          │
```

### 7.2 四种 method

| method | params | 返回 | 何时调用 |
|--------|--------|------|----------|
| `initialize` | `{}` | `{protocolVersion, serverInfo, capabilities}` | 插件启动时（一次） |
| `describe` | `{}` | `MANIFEST` 完整 dict | 插件启动时（一次） |
| `invoke` | `{"tool": "world", "arguments": {...}}` | `{"success": bool, "data": ..., "error"?: ...}` | 每次工具调用 |
| `health` | `{}` | `{"status": "ok", ...}` | 宿主健康检查（可选） |

### 7.3 `MANIFEST` 关键字段

```python
{
    "display_name": "Truman Director",       # UI 显示名
    "version": "0.1.0",                       # semver
    "description": "...",                     # 一句话描述
    "author": "Anna Hackathon Team",
    "homepage": "https://github.com/...",
    "license": "MIT",
    "tags": ["simulation", "social", "director"],
    "tools": [{
        "name": "world",                      # ★ 与 TOOL_DISPATCH key 一致
        "description": "...",
        "parameters": [...]                   # LLM 看这个决定怎么调用
    }],
    "runtime": {"type": "uv", "min_version": "0.1.0"},
}
```

**关键约束**：`tools` 列表里**只能有一个 tool**（单 dispatcher 模式），否则 Anna UI Runtime 会为每个 tool 分配一行 Executa。

### 7.4 错误码

JSON-RPC 2.0 预定义 + Anna 扩展。**Plugin 主动抛的只剩 3 个**，其余让 SDK / host 自然抛出：

| Code | 含义 | 何时抛 |
|------|------|--------|
| `-32700` | Parse error | stdio 收到非法 JSON（plugin 不会捕获，让 host 重启） |
| `-32601` | Method not found | host 调了 plugin 不认识的方法 |
| `-32000` | Server error | tool 抛未捕获异常（plugin 不捕获，让 traceback 上 host） |
| `-32001` | World not initialized | 调 tick / inject_event 但从未 init |

`v0.1` 的 `-32002`（agent_id 找不到）/ `-32003`（scenario 非法）/ `-32004`（event_type 非法）/ `-32005`（world 已存在）全部删除 —— 模型直接生成正确的 agent_id / scenario / event_type，不需要 plugin 校验。

---

## 八、Anna Storage（APS KV）反向 RPC

### 8.1 协议形态

Plugin 不写 reverse RPC 模板，直接用 `executa_sdk.storage.StorageClient`：

```python
from executa_sdk.storage import StorageClient

storage = StorageClient.from_stdio()       # SDK 自己负责 Initialize 握手 + token mint
r = storage.get("truman:run:world", scope="app")
storage.set("truman:run:world", snapshot, scope="app")
```

**改动 vs v0.1**：删 `_ANNA_HOST_AVAILABLE` 分支 + `_local_storage_handler` —— 没有"本地 fallback"，`anna-app dev` 就连真 host，测试用 `executa_sdk` 的 `FakeHost`。

### 8.2 Key 命名规范

```
truman:run:world      → WorldState JSON
truman:run:timeline   → 单独存事件流（如要避免 world 单 key 超限，可分）
truman:run:meta       → {created_at, scenario, tick_count, last_inject_id}
```

**命名原则**：
- 前缀 `truman:` 避免与其它 App 冲突
- `run:<run_id>:` 分 run（虽然 MVP 不支持多 run，但预留）
- 单 key 不超过 ~20KB（APS 软限制）；bundle 渲染时按 importance 排序 + 截断，不在 plugin 侧 cap 100。

### 8.3 （已删除）容错策略

~~`safe_set()` 吞 APS 错误 → 不让 tick 失败~~

**v0.2 立场**：持久化失败 = 数据丢失，下次 reload 恢复不出来。tick 应该 fail loud，让 host 知道，触发重试或重置。`storage.set()` 直接抛异常，由 SDK / host 处理。

---

## 九、构建与分发

### 9.1 本地开发（uv run）

```bash
cd executas/truman-director
uv run python -m truman_director.plugin
# 调试时手动喂请求
echo '{"jsonrpc":"2.0","id":1,"method":"describe"}' | uv run python -m truman_director.plugin
```

### 9.2 Source Distribution（uv build）

```bash
cd executas/truman-director
uv build
# 产物：
#   dist/tool_DEV_truman_director_xxxxxxxx-0.1.0.tar.gz
#   dist/tool_DEV_truman_director_xxxxxxxx-0.1.0-py3-none-any.whl
```

发布到 PyPI（可选）：`uv publish`

### 9.3 Binary Distribution（PyInstaller）

**为什么需要 binary？** Anna 平台最终用户机器上不一定有 Python；PyInstaller 把 Python 解释器 + 依赖 + 我们的代码打包成单文件 / 单目录可执行。

```bash
cd executas/truman-director
uv tool run pyinstaller --name tool-DEV-truman-director-xxxxxxxx \
    --onefile --noconfirm \
    src/truman_director/plugin.py
```

**多平台**：PyInstaller 不交叉编译，必须在每个目标平台跑一次。CI 用 GitHub Actions matrix：

```yaml
# .github/workflows/build-binary.yml
strategy:
  matrix:
    include:
      - os: macos-14
        target: darwin-arm64
      - os: macos-13
        target: darwin-x86_64
      - os: ubuntu-22.04
        target: linux-x86_64
      - os: windows-2022
        target: windows-x86_64
```

### 9.4 `scripts/build-binary.sh`

```bash
#!/usr/bin/env bash
# 一键构建当前平台的 binary
set -euo pipefail

cd "$(dirname "$0")/../executas/truman-director"

TOOL_ID=$(grep '^name = ' pyproject.toml | head -1 | cut -d'"' -f2)
echo "Building binary for tool_id: $TOOL_ID"

uv tool run pyinstaller \
    --name "$TOOL_ID" \
    --onefile --noconfirm --clean \
    src/truman_director/plugin.py

mkdir -p ../../dist
mv "dist/$TOOL_ID" "../../dist/"
echo "Built: ../../dist/$TOOL_ID"
```

---

## 十、测试策略

### 10.1 测试金字塔

```
        ┌──────────┐
        │  E2E     │   anna-app fixture verify（最少、最慢）
        ├──────────┤
        │Protocol  │   JSON-RPC over stdio 端到端（中等数量）
        ├──────────┤
        │  Unit    │   world / engine / decision / scenarios（最多、最快）
        └──────────┘
```

### 10.2 单元测试（`executas/truman-director/tests/unit/`）

```python
# test_world.py
def test_world_advance_tick():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="08:00", tick_minutes=5)
    world.advance_tick()
    assert world.current_tick == 1
    assert world.world_time == "08:05"

def test_world_advance_tick_crosses_hour():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="08:58", tick_minutes=5)
    world.advance_tick()
    assert world.world_time == "09:03"

def test_world_snapshot_roundtrip():
    world = WorldState(run_id="r1", scenario="cafe_town", world_time="08:00")
    snapshot = world.snapshot()
    restored = WorldState.from_snapshot(snapshot)
    assert restored.world_time == "08:00"
    assert restored.run_id == "r1"
```

```python
# test_decision.py
from unittest.mock import MagicMock
from truman_director.decision import decide

def test_decide_parses_model_response():
    sampling = MagicMock()
    sampling.create_message.return_value.content = '{"events": [{"agent_id":"alice","action":"rest","target":null,"reason":"sleep"}]}'
    events = decide(sampling, {"clock": {"hour": 3}, "agents": {"alice": {}}})
    assert events == [{"agent_id":"alice","action":"rest","target":null,"reason":"sleep"}]
```

**改动 vs v0.1**：删 `test_world_events_cap_at_100` —— plugin 不再 cap events。

### 10.3 协议契约测试（`tests/protocol/`）

```python
# test_plugin_contract.py
import subprocess
import json

def run_plugin_rpc(request: dict) -> dict:
    proc = subprocess.run(
        ["uv", "run", "python", "-m", "truman_director.plugin"],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return json.loads(proc.stdout.strip().split("\n")[0])

def test_describe_returns_manifest():
    resp = run_plugin_rpc({"jsonrpc": "2.0", "id": 1, "method": "describe"})
    assert resp["result"]["tools"][0]["name"] == "world"

def test_init_then_tick():
    init_resp = run_plugin_rpc({
        "jsonrpc": "2.0", "id": 2, "method": "invoke",
        "params": {"tool": "world", "arguments": {"action": "init", "scenario": "cafe_town"}}
    })
    assert init_resp["result"]["success"]

    tick_resp = run_plugin_rpc({
        "jsonrpc": "2.0", "id": 3, "method": "invoke",
        "params": {"tool": "world", "arguments": {"action": "tick", "n": 5}}
    })
    assert tick_resp["result"]["success"]
    assert len(tick_resp["result"]["data"]["results"]) == 5

def test_invalid_scenario_returns_error():
    resp = run_plugin_rpc({
        "jsonrpc": "2.0", "id": 4, "method": "invoke",
        "params": {"tool": "world", "arguments": {"action": "init", "scenario": "no_such"}}
    })
    assert resp["result"]["success"] is False
    assert "scenario" in resp["result"]["error"]
```

### 10.4 Fixture 测试（`fixtures/*.jsonl`）

每行一个 JSON-RPC 请求/响应对：

```jsonl
{"req":{"jsonrpc":"2.0","id":1,"method":"invoke","params":{"tool":"world","arguments":{"action":"init","scenario":"cafe_town"}}},"resp":{"success":true,"data":{...}}}
{"req":{...},"resp":{...}}
```

验证：

```bash
anna-app fixture verify fixtures/happy-path.jsonl
```

### 10.5 Bundle 测试（`tests/bundle/app.spec.ts`）

用 vitest + jsdom 测 bundle 渲染：

```typescript
import { describe, it, expect } from "vitest";
import { mountApp } from "./helpers";

describe("Truman Director bundle", () => {
    it("renders empty state when no world", async () => {
        const { getByText } = await mountApp();
        expect(getByText("还没有世界")).toBeInTheDocument();
    });

    it("renders 6 locations after init", async () => {
        const { getAllByTestId } = await mountApp({ mockState: mockWorld() });
        expect(getAllByTestId("location")).toHaveLength(6);
    });
});
```

---

## 十一、CI/CD

### 11.1 `ci.yml`（PR 检查）

```yaml
name: CI
on:
  pull_request:
    branches: [main]

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: uv sync
      - run: uv run ruff format --check .
      - run: uv run ruff check .
      - run: uv run pytest -q
```

### 11.2 `publish.yml`（发布期多平台构建）

```yaml
name: Publish
on:
  push:
    tags: ["truman-director-v*"]

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: macos-14    ; target: darwin-arm64 ;   ext: tar.gz
          - os: macos-13    ; target: darwin-x86_64 ;  ext: tar.gz
          - os: ubuntu-22.04; target: linux-x86_64 ;   ext: tar.gz
          - os: windows-2022; target: windows-x86_64 ; ext: zip
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: curl -LsSf https://astral.sh/uv/install.sh | sh
      - run: uv sync
      - name: Build binary
        run: ./scripts/build-binary.sh ${{ matrix.target }} ${{ matrix.ext }}
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/*
```

---

## 十二、Tool ID 生命周期

### 12.1 三种状态

| 状态 | tool_id 形态 | 出现在哪里 | 何时 |
|------|-------------|----------|------|
| **开发** | `tool-DEV-truman-director-xxxxxxxx` | 4 个文件 | 本地 `anna-app dev` |
| **已 mint** | `tool-<yourhandle>-truman-director-<hash>` | 4 个文件 + bundle | `anna-app apps publish` 后 |
| **运行时** | 同上 | 平台服务端分发 | 用户打开 App |

### 12.2 涉及的文件

1. `executas/truman-director/pyproject.toml` → `name = "..."` 和 `[project.scripts] "..." = "truman_director.plugin:main"`
2. `executas/truman-director/src/truman_director/plugin.py` → 注释
3. `executas/truman-director/executa.json` → `tool_id` 字段（dev 期）
4. `bundle/anna-tool-ids.js` → 发布期生成（dev 期 404 即可）
5. `bundle/app.js` → 从 `window.__ANNA_TOOL_IDS__` 读

### 12.3 `scripts/set-tool-id.py`

```python
#!/usr/bin/env python3
"""把 mint 后的 tool_id 同步到 4 个文件"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOOL_ID_PATTERN = re.compile(r"tool-[A-Za-z0-9_-]+")

FILES = {
    "pyproject.toml": [
        (r'^name = ".*"$', f'name = "{{tool_id}}"'),
        (r'^"tool-[^"]+" = "truman_director.plugin:main"$', f'"{{tool_id}}" = "truman_director.plugin:main"'),
    ],
    "executa.json": [
        (r'"tool_id":\s*"[^"]+"', f'"tool_id": "{{tool_id}}"'),
    ],
    "plugin.py": [
        (r'# tool_id: tool-[a-zA-Z0-9_-]+', f'# tool_id: {{tool_id}}'),
    ],
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool_id")
    args = parser.parse_args()
    for fname, patterns in FILES.items():
        path = ROOT / "executas/truman-director" / fname
        text = path.read_text()
        for pat, repl in patterns:
            text = re.sub(pat, repl.format(tool_id=args.tool_id), text, flags=re.M)
        path.write_text(text)
        print(f"updated: {path}")

if __name__ == "__main__":
    main()
```

**注意**：发布期 `anna-app apps publish` 会**自动调用**这个脚本的逻辑，不需要手动跑；只有想手动同步时才用。

**改动 vs v0.1**：删 "dev 期用占位符 fallback" 注释 —— 占位符不是 fallback，是开发期临时 id，发布期会被替换。

---

## 十三、调试与故障排查

### 13.1 插件显示 "Stopped"

常见原因（按概率排序）：

| 症状 | 排查 |
|------|------|
| 启动后立即退出 | 看 stderr，常见：`ModuleNotFoundError`（依赖没装）/ `pyproject.toml` 里 `name` 与 tool_id 不一致 |
| 启动成功但 invoke 失败 | 看 stderr，应该是 `ValueError`（入参校验）；检查 bundle/app.js 传的 args |
| 启动慢 | 首次启动会 `uv sync`，缓存后秒开；CI 环境要注意预热 |
| `tool_id mismatch` | `scripts/set-tool-id.py apply --tool <正确 id>` 重新同步 |

### 13.2 Bundle CSP 失败

`script-src 'self'` 拦截了：
- 内联 `<script>...</script>` → 改用 `<script src="..."></script>`
- `eval()` → 改写逻辑
- CDN 外链 → 全部 inline 到本地文件

`anna-app validate --strict` 会自动检测并报错。

### 13.3 APS KV 权限拒绝

```json
{
  "code": -32010,
  "message": "storage.set denied: missing 'storage.write' permission"
}
```

解决：检查 `manifest.json` 的 `permissions` 是否包含 `"storage.write"`，且 `host_api.storage` 包含 `"set"`。

### 13.4 单次 invoke 超时

Anna Tool runtime 默认 invoke 超时 ~5 秒。如果一次 `tick(n=50)` 卡住：

- 拆分：bundle 端用 `setInterval` 多次调 `tick(n=5)`
- 优化：`engine.py` 里跳过不必要的 dataclass 拷贝

**改动 vs v0.1**：删"兜底：MVP 内 `n > 20` 时直接拒绝（返回错误）" —— 信任 bundle 端自行控制 n 大小，plugin 不该限制合法调用。

---

## 十四、参考

### 14.1 官方文档

- [Anna Executa Protocol](https://anna.partners/developers/reference/executa-protocol)
- [Anna App Manifest](https://anna.partners/developers/reference/anna-app-manifest)
- [Anna Storage (APS)](https://anna.partners/developers/reference/executa-persistent-storage)
- [Anna Sampling](https://anna.partners/developers/reference/executa-sampling)
- [`@anna-ai/app-cli` 参考](https://anna.partners/developers/reference/cli)

### 14.2 参考项目

- [`anna-executa-examples/anna-app-focus-flow`](https://github.com/whtcjdtc2007/anna-executa-examples) — Anna App 骨架
- [`anna-executa-examples/sdk/python/executa_sdk/`](https://github.com/whtcjdtc2007/anna-executa-examples) — StorageClient + SamplingClient + RPC
- [`TrumanWorld/backend`](https://github.com/your-org/truman-world) — 模拟引擎原型（内部仓库）
- [`gqy20/crawl-mcp`](https://github.com/gqy20/crawl-mcp) — 工程基线（pre-commit / uv / hatchling / src layout）

### 14.3 工具链

- [UV 文档](https://docs.astral.sh/uv/)
- [Ruff 文档](https://docs.astral.sh/ruff/)
- [Hatchling 构建](https://hatch.pypa.io/latest/config/build/)
- [PyInstaller 手册](https://pyinstaller.org/en/stable/)

---

## 附录 A：与 crawl-mcp 工程基线的差异表

| 维度 | crawl-mcp | truman-director |
|------|-----------|-----------------|
| Python 版本 | 3.12 | 3.12（一致） |
| 包管理器 | uv | uv（一致） |
| 布局 | `src/crawl4ai_mcp/` | `executas/truman-director/src/truman_director/`（嵌套，因 Anna App 单仓多包） |
| 构建后端 | hatchling | hatchling（一致） |
| 构建产物 | MCP server stdio | Executa stdio + PyInstaller binary |
| pre-commit | ruff format + check + pytest | ruff format + check + pytest（一致） |
| 测试 | pytest + pytest-asyncio | pytest + pytest-asyncio + pytest-cov（多了 coverage） |
| CI | ci.yml + publish.yml | ci.yml + publish.yml（一致） |
| 分发 | PyPI（optional）| PyPI + GitHub Release binary（双轨）|

## 附录 B：术语对照表

| 本文术语 | Anna 文档 | 说明 |
|---------|----------|------|
| Plugin / Executa | Executa plugin | Python stdio 进程 |
| Bundle | App Bundle | iframe SPA |
| Skill | Skill | Markdown 行为剧本 |
| Manifest | Anna App Manifest | 平台配置文件 |
| Tool ID | tool_id | 平台分配的唯一 ID |
| APS KV | Anna Persistent Storage | 平台托管的 KV |
| Host API | host_api | bundle 可调用的平台 API 白名单 |
| Executa handle | — | manifest 里引用的本地代号（开发期占位）|

---

## 附录 C：v0.1 → v0.2 清理清单

13 条防御模式已删：

1. `agents.py` heuristic 决策 → `decision.py` SamplingClient
2. `DecisionStrategy` Protocol + `STRATEGIES` registry → 单函数 `decide()`
3. `ScenarioRegistry` 装饰器 → 简单 dict
4. `dev_runtime.py` + `FakeStorage` + `_ANNA_HOST_AVAILABLE` 分支 → 整个 dev-mode fallback 层
5. etag 乐观并发 + `APSKeyValue.if_match` → 单 key 直接 set
6. `safe_set()` 吞 APS 错误 → SDK 抛异常
7. `handle_invoke` 全 catch → 不 catch，让异常走 JSON-RPC `error`
8. `main()` `except json.JSONDecodeError` → 不 catch，让 host 重启 plugin
9. 8 个 action → 3 个（删 get_state / get_agent / get_timeline / reset / list_scenarios）
10. MANIFEST parameters 所有 `default: ...` → 删，让模型显式给值
11. `events cap 100` → 删，bundle 按 importance 排序
12. phase gating（`llm.sample (Phase 2 才需要)` 等）→ 全开
13. `on_unsupported: "json_object"` → 删

代码量减少：~1300 行 → ~700 行（少 46%）。

---

> **文档状态**: v0.2 (清理完成)
> **下一步**: 按 FRAMEWORK.md §13 的 checklist 初始化仓库
> **Owner**: Anna Hackathon Team