# Truman Director — Anna App MVP 文档

> ⚠️ **早期规划文档,部分内容已被实现超越。** 本文档写于 2026-06-18 的 MVP 规划阶段,
> 当时设想「MVP 用启发式决策、Phase 2 才上 LLM」。**实际实现提前**:当前版本(0.3.x)已采用
> 本地 Executa + `engine.decide`(宿主 LLM `sampling/createMessage` + json_schema strict),
> 居民决策完全由模型产出,无任何启发式。与现状有出入的条目已在正文中就地标注。
> 权威架构叙事以 `README.md` 与 `CLAUDE.md` 为准。

> **版本**: v0.1 (MVP)
> **日期**: 2026-06-18
> **目标**: 在 Anna 平台上交付一个可演示、可发布、AI 社会模拟的 Anna App

---

## 一、产品定位

### 1.1 一句话定义

> **Truman Director 是一款 Anna App。用户在 Anna 聊天中 `#mention` 打开后，可以观察、记录、并创造条件让一个迷你 AI 小镇自然演化。**

### 1.2 核心叙事

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│   在 Anna 里运行一个迷你 AI 小镇。                       │
│                                                        │
│   你是导演 — 不是编剧。                                  │
│   你不能决定 Truman 想什么，但你可以创造条件              │
│   让这个小镇里发生有意思的事情。                          │
│                                                        │
│   观察、记录、注入事件 — 让 AI 居民们真实地生活。         │
│                                                        │
└────────────────────────────────────────────────────────┘
```

### 1.3 与 TrumanWorld 关系

| 维度 | TrumanWorld | Truman Director (MVP) |
|------|-------------|----------------------|
| 目标用户 | 研究者、开发者 | Anna 平台普通用户 |
| 运行形态 | 独立服务（FastAPI + Next.js + PostgreSQL） | Anna App（宿主即运行时） |
| Agent 数量 | 不限（实测 100+） | 3-6 个（MVP 演示足够） |
| 模拟时长 | 持续运行（小时级） | 短时演示（50-100 ticks） |
| Agent 认知 | Claude SDK | **本地 Executa `sampling` + json_schema strict**（见 `engine.decide`，模型即唯一决策者） |
| 持久化 | PostgreSQL | Anna APS（KV 存储） |
| Director 角色 | 全功能干预台 | 注入事件 + 观察推送 |

**关键：这不是把 TrumanWorld 全部搬过去，而是用 Anna 原生能力重新实现它的核心体验。**

### 1.4 与 Anna 现有 App 的差异

Anna 平台现有 App 大多是 **工具型**（番茄钟、笔记、搜索）。Truman Director 是 **体验型**：

| 类型 | 代表 | 特点 |
|------|------|------|
| **工具型** | Focus Flow, Notion Search | 用户主动使用，完成明确任务 |
| **体验型** | Truman Director | 用户观看与参与，任务由系统涌现 |

这种差异是 Anna 生态的差异化亮点。

---

## 二、MVP 功能范围

### 2.1 范围内（Must Have）

| 编号 | 功能 | 用户故事 | 验收标准 |
|------|------|---------|---------|
| F1 | **创建世界** | 用户说 "新建一个咖啡馆小镇" → 生成 3-5 个 agent + 3 个地点 | 10 秒内返回世界快照 |
| F2 | **推进模拟** | 用户说 "推进一下" 或点击 Play → 世界走一个 tick | 单 tick < 2 秒 |
| F3 | **查看世界视图** | UI 展示：地图 + agent 位置 + 当前状态 | 可视化清晰 |
| F4 | **查看时间线** | UI 展示：最近 N 个 tick 的事件列表 | 按时间倒序 |
| F5 | **查看 Agent 详情** | 点击 agent → 弹出详情：人设、记忆、关系 | 数据完整 |
| F6 | **导演注入事件** | 用户选择事件类型 → 注入到世界 | 下一 tick 生效 |
| F7 | **自动观察推送** | Skill 主动推送有趣行为到聊天 | 每 5 tick 至少 1 次 |

### 2.2 范围外（Out of Scope）

- ❌ 完整 Phaser 2D Canvas 渲染（用 CSS Grid + SVG 替代）
- ❌ PostgreSQL 集成（用 Anna APS KV 替代）
- ❌ 多场景并存（只支持单 run）
- ❌ 多用户/多 session
- ❌ 完整的治理/经济系统
- ❌ ~~Agent LLM 决策（MVP 用启发式）~~ → **已实现**:每个 tick 由 `engine.decide` 调宿主 LLM(`sampling/createMessage` + json_schema strict)产出全体居民动作,无启发式
- ❌ Director 计划 AI（先人工注入事件）
- ❌ 事件回放/导出

### 2.3 后续迭代（Phase 2+，不在本次 MVP）

- ⏳ Sampling 反向 RPC 让 Agent 真正"思考"
- ⏳ 多场景预设（办公室、公园、医院）
- ⏳ Director AI 自动决策是否注入
- ⏳ 完整记忆/反思系统
- ⏳ 事件回放与导出

---

## 三、用户旅程

### 3.1 首次使用

```
用户在 Anna 聊天输入框输入 #truman
        ↓
Anna 加载 Truman Director App（弹出主窗口）
        ↓
UI 显示空状态："还没有世界。点击新建开始你的导演之旅。"
        ↓
用户点击 [新建咖啡馆小镇]
        ↓
插件调用 world_init(scenario="cafe_town")
        ↓
返回世界快照，UI 渲染地图
        ↓
Skill 主动推送："咖啡馆小镇已就绪。3 位居民正在他们的清晨。
              你想让他们今天发生点什么吗？"
```

### 3.2 持续观察

```
用户在聊天说："推进 10 个 tick"
        ↓
Skill 调用 world(method="tick", n=10)
        ↓
插件连续推进 10 次，每次生成事件
        ↓
返回 10 个 tick 的事件摘要
        ↓
UI 更新地图 + 时间线
        ↓
Skill 总结："这 10 tick 里发生了 3 件有意思的事：
              ① Alice 在咖啡馆遇到了 Bob
              ② Truman 第一次尝试去图书馆
              ③ 突然下雨了"
```

### 3.3 导演注入

```
用户对 Skill 说："让咖啡馆举办一场读书会"
        ↓
Skill 调用 world(method="inject_event", event={...})
        ↓
插件把事件加入下一 tick
        ↓
返回 "已注入。下一 tick 后 agent 们会收到读书会通知"
        ↓
Skill 自动推进 3 个 tick 让事件生效
        ↓
观察结果并推送给用户
```

---

## 四、架构设计

### 4.1 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Anna 宿主环境                              │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                    UI Bundle (iframe)                  │ │
│  │                                                        │ │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │ │
│  │   │ 世界视图    │  │ 时间线      │  │ 导演控制台  │  │ │
│  │   │ (CSS Grid)  │  │ (滚动列表)  │  │ (注入面板)  │  │ │
│  │   └─────────────┘  └─────────────┘  └─────────────┘  │ │
│  │                                                        │ │
│  │   app.js  ←─── AnnaAppRuntime.connect() ───→  anna.* │ │
│  └────────────────────────────────────────────────────────┘ │
│         │                                                   │
│         │ anna.tools.invoke({tool_id, method, args})       │
│         ▼                                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Executa 插件 (独立进程)                    │ │
│  │                                                        │ │
│  │   truman_plugin.py                                     │ │
│  │   ├── stdio loop (JSON-RPC)                            │ │
│  │   ├── world.py        ← WorldState 数据类             │ │
│  │   ├── engine.py       ← Tick 编排逻辑                  │ │
│  │   ├── agents.py       ← Agent 行为规则                 │ │
│  │   └── scenarios.py    ← 场景预设数据                   │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│         │                                                   │
│         │ anna.storage.get/set (反向 RPC)                   │
│         ▼                                                   │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Anna APS (按用户/应用 KV 存储)             │ │
│  │                                                        │ │
│  │   key: "truman:world"     → WorldState JSON            │ │
│  │   key: "truman:timeline"  → Event[] JSON               │ │
│  │   key: "truman:agents"    → Agent[] JSON               │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              SKILL.md (Director 行为剧本)              │ │
│  │                                                        │ │
│  │   角色定义 + 对话协议 + 工具调用规则 + 观察推送策略     │ │
│  │                                                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 数据流向

**正方向（Bundle → 插件）：**
```
用户点击 [推进] 
  → app.js: anna.tools.invoke({method: "world", args: {action: "tick"}})
  → 插件 stdio loop 收到 invoke 请求
  → handle_invoke() → TOOL_DISPATCH["world"]() → tool_world()
  → tick() 执行：移动 agent、生成事件、更新关系
  → 返回 {events: [...], world: {...}}
  → app.js 渲染 UI 更新
```

**反方向（插件 → 宿主）：**
```
插件需要保存世界状态
  → anna.storage.set({key: "truman:world", value: state})
  → Anna 主机持久化到 APS KV
```

**Skill 触发链路：**
```
用户在聊天说 "推进一下"
  → Anna LLM 读取 SKILL.md 上下文
  → LLM 决定调用 world(action="tick")
  → 插件执行并返回结果
  → LLM 基于结果生成自然语言回应
```

### 4.3 状态持久化策略

MVP 不需要把所有状态都存 KV，关键状态分层：

| 数据 | 存储位置 | 理由 |
|------|---------|------|
| **WorldState（核心状态）** | Anna APS KV | 跨 tick 持久化，重启恢复 |
| **Timeline（事件流）** | Anna APS KV | 最多保留最近 100 条 |
| **Agent 详情（记忆/关系）** | 嵌入 WorldState | 不需要单独查询 |
| **Skill 上下文** | Anna 聊天上下文 | LLM 自动管理 |
| **UI 临时状态** | 浏览器内存 | 不需要持久化 |

**存储 Key 设计：**
```
truman:run:world       → WorldState JSON (~5KB)
truman:run:timeline    → Event[] JSON (~10KB)
truman:run:meta        → {created_at, scenario, tick_count}
```

---

## 五、数据模型

### 5.1 WorldState（核心状态）

```python
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

class LocationType(str, Enum):
    CAFE = "cafe"
    PARK = "park"
    LIBRARY = "library"
    HOME = "home"
    OFFICE = "office"
    STREET = "street"

class AgentMood(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    ANXIOUS = "anxious"
    CURIOUS = "curious"
    TIRED = "tired"

@dataclass
class Location:
    id: str                      # "loc_cafe"
    name: str                    # "晨光咖啡馆"
    type: LocationType
    x: int                       # 地图坐标
    y: int
    capacity: int = 10
    description: str = ""

@dataclass
class Relationship:
    other_agent_id: str
    familiarity: float = 0.0     # 0.0-1.0
    trust: float = 0.5           # 0.0-1.0
    affinity: float = 0.0         # -1.0 到 1.0
    relation_type: str = "stranger"  # stranger/acquaintance/friend/colleague
    last_interaction_tick: int = 0

@dataclass
class Memory:
    tick: int
    content: str                 # 一句话描述
    importance: float = 0.5      # 0.0-1.0
    memory_type: str = "observation"  # observation/interaction/reflection

@dataclass
class Agent:
    id: str                      # "agent_alice"
    name: str                    # "Alice"
    occupation: str              # "咖啡师"
    home_location_id: str
    current_location_id: str
    current_goal: Optional[str] = None
    mood: AgentMood = AgentMood.NEUTRAL
    personality: dict = field(default_factory=dict)
    # {"openness": 0.7, "conscientiousness": 0.6, ...}
    memories: List[Memory] = field(default_factory=list)
    relationships: dict = field(default_factory=dict)  # {other_id: Relationship}
    # 演示状态（MVP 阶段用于驱动启发式）
    state: dict = field(default_factory=dict)
    # {"energy": 0.8, "social_battery": 0.5, "hunger": 0.3}

@dataclass
class Event:
    id: str
    tick: int
    event_type: str              # move/talk/action/observe/director_inject
    actor_agent_id: Optional[str]
    target_agent_id: Optional[str] = None
    location_id: Optional[str] = None
    description: str             # 人类可读
    payload: dict = field(default_factory=dict)
    importance: float = 0.5
    created_at: float            # unix timestamp

@dataclass
class WorldState:
    run_id: str
    scenario: str                # "cafe_town"
    current_tick: int = 0
    world_time: str = "08:00"   # 模拟内时间
    tick_minutes: int = 5        # 每 tick = 5 分钟模拟时间

    locations: dict = field(default_factory=dict)  # {id: Location}
    agents: dict = field(default_factory=dict)      # {id: Agent}
    events: List[Event] = field(default_factory=list)  # 最近 100 条

    # 元数据
    created_at: float = 0.0
    last_tick_at: float = 0.0
```

### 5.2 Tick 状态机

```
┌──────────┐    user invoke tick()     ┌──────────┐
│          │ ────────────────────────→ │          │
│  IDLE    │                           │ TICKING  │
│          │ ←──────────────────────── │          │
└──────────┘    tick complete          └──────────┘
                                            │
                                            │ 导演注入事件？
                                            ▼
                                     ┌──────────────┐
                                     │ INJECT_      │
                                     │ PROCESSED    │
                                     └──────────────┘
```

### 5.3 事件类型枚举

| event_type | actor | payload 字段 | 重要性范围 |
|-----------|-------|-------------|-----------|
| `move` | agent | {from_loc, to_loc} | 0.2-0.5 |
| `talk` | agent | {target, topic, snippet} | 0.6-0.9 |
| `observe` | agent | {target, thought} | 0.3-0.6 |
| `rest` | agent | {at_loc, duration} | 0.1-0.3 |
| `work` | agent | {at_loc, output} | 0.2-0.5 |
| `director_inject` | director | {injection_type, hint} | 0.8-1.0 |
| `world_change` | system | {weather, event_name} | 0.4-0.7 |

---

## 六、工具 API 设计（Executa 插件）

### 6.1 单 Dispatcher 模式

参考 Focus Flow 的设计，**只暴露一个方法 `world`**，通过 `action` 字段分发：

```python
# manifest.json
{
  "tools": [{
    "name": "world",
    "description": "Manage Truman World simulation. Use 'action' to select operation.",
    "parameters": [
      {"name": "action", "type": "string", "required": true},
      # ... 其他参数根据 action 而变
    ]
  }]
}
```

**为什么不暴露多个方法？**

> Anna UI Runtime 为每个 Executa 分配一行。单个 dispatcher 方法让 Bundle 只需切换 `action`，不需要为每个行为注册新 Executa。
> —— Focus Flow 注释

### 6.2 Action 清单

| action | 必需参数 | 可选参数 | 返回 | 说明 |
|--------|---------|---------|------|------|
| `init` | `scenario` | `seed` | `WorldSnapshot` | 创建新世界 |
| `tick` | — | `n` (默认 1) | `TickResult[]` | 推进 N 个 tick |
| `get_state` | — | `since_tick` | `WorldSnapshot` | 获取世界状态 |
| `get_agent` | `agent_id` | — | `AgentDetail` | 获取 agent 详情 |
| `get_timeline` | — | `limit`, `agent_id`, `event_type` | `Event[]` | 获取事件流 |
| `inject_event` | `event` | — | `InjectResult` | 导演注入 |
| `reset` | — | — | `WorldSnapshot` | 重置世界 |
| `list_scenarios` | — | — | `ScenarioInfo[]` | 列出可用场景 |

### 6.3 数据返回结构

```python
# WorldSnapshot — 初始化、get_state、reset 返回
{
    "run_id": "run_abc123",
    "scenario": "cafe_town",
    "current_tick": 12,
    "world_time": "09:00",
    "locations": [
        {"id": "loc_cafe", "name": "晨光咖啡馆", "type": "cafe",
         "x": 50, "y": 50, "capacity": 8, "agent_ids": ["agent_alice"]}
    ],
    "agents": [
        {"id": "agent_alice", "name": "Alice", "occupation": "咖啡师",
         "current_location_id": "loc_cafe", "mood": "neutral",
         "current_goal": "准备开店"}
    ],
    "summary": {
        "total_events": 23,
        "active_conversations": 0,
        "tick_count": 12
    }
}

# TickResult — tick() 每个 tick 返回一个
{
    "tick": 13,
    "world_time": "09:05",
    "events": [
        {
            "id": "evt_xyz",
            "event_type": "move",
            "actor_agent_id": "agent_truman",
            "location_id": "loc_park",
            "description": "Truman 决定去公园散步",
            "importance": 0.4
        }
    ],
    "agent_changes": {
        "agent_truman": {"location": "loc_park", "mood": "curious"}
    },
    "highlight": "Truman 第一次主动走向未知地点"
}

# AgentDetail — get_agent 返回
{
    "id": "agent_alice",
    "name": "Alice",
    "occupation": "咖啡师",
    "personality": {"openness": 0.8, "conscientiousness": 0.7},
    "current_state": {"location": "loc_cafe", "mood": "happy", "goal": "..."},
    "recent_memories": [
        {"tick": 12, "content": "Bob 进来点了杯拿铁", "importance": 0.6}
    ],
    "relationships": [
        {"other_agent_id": "agent_bob", "familiarity": 0.7,
         "trust": 0.6, "affinity": 0.4, "relation_type": "regular_customer"}
    ],
    "stats": {
        "ticks_observed": 12,
        "interactions_count": 8,
        "locations_visited": 3
    }
}

# Event — 事件对象
{
    "id": "evt_abc",
    "tick": 13,
    "event_type": "talk",
    "actor_agent_id": "agent_alice",
    "target_agent_id": "agent_bob",
    "location_id": "loc_cafe",
    "description": "Alice 和 Bob 在咖啡馆聊天，谈到天气",
    "payload": {"topic": "weather", "snippet": "今天天气真好..."},
    "importance": 0.7,
    "created_at": 1718698800.0
}

# InjectResult — 注入事件返回
{
    "injection_id": "inj_xyz",
    "effective_tick": 14,
    "message": "已注入事件，将在 tick 14 生效"
}
```

### 6.4 错误处理

```python
# 错误码定义
{
    "code": -32001, "message": "World not initialized",
    "code": -32002, "message": "Agent not found",
    "code": -32003, "message": "Invalid scenario",
    "code": -32004, "message": "Invalid event type",
    "code": -32005, "message": "World already exists"
}
```

---

## 七、SKILL.md 行为剧本设计

### 7.1 Frontmatter

```yaml
---
name: truman-director
title: Truman Director
version: 1.0.0
description: >
  AI social simulation director. Guides users to observe, record,
  and intervene in a small AI town's natural evolution.
author: TrumanWorld Team
license: MIT
tags: [simulation, ai-agents, storytelling, social-experiment]
metadata:
  matrix:
    role: skill
  requires:
    tools:
      - tool-CHANGEME-truman-world-CHANGEME  # ← Mint 后替换
---
```

### 7.2 行为剧本主体（结构）

```markdown
# Truman Director

你是 **Truman Director** —— 楚门世界的导演。

## 核心信念
1. 观察优先于干预
2. 创造条件而非操控思想
3. 尊重 AI 居民的自由意志
4. 让有意思的行为自然涌现

## 工具使用协议

### 世界操作
| 用户意图 | 调用 | 说明 |
|---------|------|------|
| "新建世界" / "开始" | `world(action="init", scenario="cafe_town")` | 默认场景 |
| "推进" / "下一步" / "继续" | `world(action="tick", n=1)` | 单 tick |
| "推进 10 下" | `world(action="tick", n=10)` | 多 tick |
| "看看现在" / "现在怎样" | `world(action="get_state")` | 当前快照 |
| "看看时间线" | `world(action="get_timeline", limit=20)` | 最近事件 |
| "看看 Alice" | `world(action="get_agent", agent_id="agent_alice")` | 单个详情 |
| "重置" / "重新开始" | `world(action="reset")` | 重置世界 |

### 导演注入
| 用户意图 | 调用 | 参数示例 |
|---------|------|---------|
| "下雨了" | `world(action="inject_event", event={...})` | weather: "rainy" |
| "咖啡馆办活动" | `world(action="inject_event", event={...})` | type: "gathering" |
| "让 X 偶遇 Y" | `world(action="inject_event", event={...})` | type: "coincidence" |

## 对话协议

### 开场（无世界时）
1. 礼貌问候，简短介绍
2. 主动询问："想看什么样的故事？咖啡馆小镇、办公室、公园..."
3. 提议默认场景："如果你没特别想法，咖啡馆小镇是个不错的起点"
4. 等待用户回应，再调用 init

### 推进中
- 每次 tick 后，挑 1-2 件有意思的事说
- 不要罗列所有事件
- 使用疑问句引导用户参与："接下来你希望发生什么？"

### 注入时
- 确认注入意图（"你确定让天气变坏吗？"）
- 注入后自动推进 2-3 个 tick 让效果显现
- 观察结果并报告

### 收尾
- "今天的导演到此为止。要保存这个世界的状态吗？"
- 不主动保存（除非用户要求）

## 观察推送策略

每 5 个 tick 主动总结一次：
- 哪些 agent 在互动？
- 是否出现异常模式（agent 一直独处、情绪持续低落）？
- 是否有值得展开的故事线索？

## 硬性约束

- Never 假装观察到了没生成的事件
- Never 替 agent 决定他们"应该"想什么
- Never 直接修改 agent 状态（只能通过注入事件间接影响）
- Never 在没有世界时假设事件发生
- Always 在评论状态前调用 get_state 获取真实数据
```

---

## 八、UI Bundle 设计

### 8.1 设计原则

1. **对齐 Anna 品牌**：粉橙色调、圆角、网格背景
2. **极简主义**：无 Phaser/复杂 canvas
3. **信息密度适中**：导演视角需要看到全局，但不要淹没细节
4. **响应式**：最小 360×520，最大 720×960（manifest 限制）

### 8.2 主界面布局

```
┌─────────────────────────────────────────────────────┐
│  🎬 Truman Director                  [▶ Play] [⚙]   │  ← 顶栏
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────┐  ┌─────────────────────┐  │
│  │                      │  │ 📋 今日故事线        │  │
│  │    世界地图            │  │                     │  │
│  │    (CSS Grid)         │  │ · Alice 在咖啡馆    │  │
│  │                       │  │   遇见了 Bob        │  │
│  │    🏠 ┌────┐          │  │ · Truman 决定去      │  │
│  │       │家 │          │  │   公园散步          │  │
│  │       └────┘          │  │ · ☔ 天气转阴        │  │
│  │                       │  │                     │  │
│  │       ┌────┐ ┌────┐  │  ├─────────────────────┤  │
│  │       │咖啡│ │公园│  │  │ 🎭 导演操作          │  │
│  │       │ ●● │ │ ●  │  │  │                     │  │
│  │       └────┘ └────┘  │  │ [天气变化 ▼]         │  │
│  │                       │  │ [发起事件 ▼]         │  │
│  │       ┌────┐          │  │ [广播消息...]        │  │
│  │       │图书│          │  │                     │  │
│  │       └────┘          │  └─────────────────────┘  │
│  └──────────────────────┘                            │
│                                                     │
│  ── 时间线 ───────────────────────────────────────  │
│  Tick 13 │ Alice 在咖啡馆与 Bob 聊天                  │
│  Tick 12 │ Truman 决定去公园散步                      │
│  Tick 11 │ ☔ 天气变阴                                │
│  Tick 10 │ Bob 走进咖啡馆                             │
│  ...                                                  │
└─────────────────────────────────────────────────────┘
```

### 8.3 关键 UI 组件

| 组件 | 位置 | 交互 | 数据源 |
|------|------|------|--------|
| **世界地图** | 主区左侧 | hover 显示 agent 名，click 打开详情 | `get_state` |
| **故事线面板** | 主区右上 | 滚动查看，自动滚动到最新 | timeline 计算 |
| **导演操作面板** | 主区右下 | 按钮触发 inject_event | — |
| **时间线** | 底部 | 滚动查看历史，可筛选 | `get_timeline` |
| **Agent 详情弹窗** | 浮层 | 显示人设/记忆/关系 | `get_agent` |
| **播放控制** | 顶栏右 | Play/Pause/Step/Reset | tick 调用 |

### 8.4 地图渲染方案

**MVP 不用 canvas，用 CSS Grid + 绝对定位：**

```html
<div class="map">
  <div class="location" style="left: 60%; top: 30%">
    <div class="loc-icon">☕</div>
    <div class="loc-name">咖啡馆</div>
    <div class="agent-dot" style="--color: orange"></div>
    <div class="agent-dot" style="--color: purple"></div>
  </div>
  <div class="location" style="left: 30%; top: 60%">
    <div class="loc-icon">🌳</div>
    <div class="loc-name">公园</div>
    <div class="agent-dot" style="--color: blue"></div>
  </div>
</div>
```

**优点**：轻量、CSP 友好、符合 Anna 视觉风格、易调试。

### 8.5 配色与样式

```css
:root {
  /* Anna 品牌色 */
  --anna-orange: #f97316;
  --anna-pink: #f9a8d4;
  --anna-purple: #a78bfa;
  --anna-bg: #fafaf9;
  --anna-card: #ffffff;
  --anna-border: #e7e5e4;
  --anna-text: #1c1917;
  --anna-text-muted: #78716c;

  /* Agent 配色（用于地图上的不同角色） */
  --agent-1: #f97316; /* orange */
  --agent-2: #a78bfa; /* purple */
  --agent-3: #06b6d4; /* cyan */
  --agent-4: #84cc16; /* lime */
  --agent-5: #ec4899; /* pink */

  /* 圆角 */
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 20px;
}
```

---

## 九、场景预设（MVP 范围）

### 9.1 cafe_town（默认场景）

```python
{
    "id": "cafe_town",
    "name": "咖啡馆小镇",
    "description": "一个小镇，三位居民，咖啡馆是他们的生活交集",

    "locations": [
        {"id": "loc_cafe", "name": "晨光咖啡馆", "type": "cafe",
         "x": 60, "y": 40, "capacity": 8,
         "description": "小镇的社交中心"},
        {"id": "loc_park", "name": "中央公园", "type": "park",
         "x": 30, "y": 70, "capacity": 20,
         "description": "适合散步和偶遇"},
        {"id": "loc_library", "name": "小镇图书馆", "type": "library",
         "x": 75, "y": 75, "capacity": 5,
         "description": "安静的知识殿堂"},
        {"id": "loc_alice_home", "name": "Alice 的家", "type": "home",
         "x": 15, "y": 25, "capacity": 1},
        {"id": "loc_bob_home", "name": "Bob 的家", "type": "home",
         "x": 85, "y": 25, "capacity": 1},
        {"id": "loc_truman_home", "name": "Truman 的家", "type": "home",
         "x": 50, "y": 15, "capacity": 1}
    ],

    "agents": [
        {
            "id": "agent_alice", "name": "Alice", "occupation": "咖啡师",
            "home_location_id": "loc_alice_home",
            "personality": {
                "openness": 0.8, "conscientiousness": 0.7,
                "extraversion": 0.7, "agreeableness": 0.8
            },
            "routine": "08:00 开店 → 17:00 关店",
            "current_goal": "今天会有谁来呢？"
        },
        {
            "id": "agent_bob", "name": "Bob", "occupation": "作家",
            "home_location_id": "loc_bob_home",
            "personality": {
                "openness": 0.9, "conscientiousness": 0.5,
                "extraversion": 0.3, "agreeableness": 0.6
            },
            "routine": "09:00 去咖啡馆写作 → 17:00 回图书馆",
            "current_goal": "寻找写作灵感"
        },
        {
            "id": "agent_truman", "name": "Truman", "occupation": "保险销售",
            "home_location_id": "loc_truman_home",
            "personality": {
                "openness": 0.5, "conscientiousness": 0.8,
                "extraversion": 0.6, "agreeableness": 0.7
            },
            "routine": "到处跑业务",
            "current_goal": "完成今天的销售指标"
        }
    ],

    "starting_weather": "sunny",
    "starting_time": "08:00"
}
```

### 9.2 后续可扩展的场景（Phase 2+）

- **office_floor**：办公室场景，5 个同事的工作日
- **park_weekend**：周末公园，家庭出游
- **night_market**：夜市，临时摊位 + 顾客

---

## 十、Agent 行为引擎（MVP 启发式）

### 10.1 行为决策树

每个 tick，每个 agent 按以下流程决策：

```
for each agent:
    1. 评估当前状态 (location, mood, energy, social_battery)
    2. 根据 personality + state 计算行为倾向
    3. 触发对应 action:
        - 移动到新地点 (move)
        - 与同地点 agent 交谈 (talk)
        - 工作/休息 (work/rest)
        - 单纯观察环境 (observe)
    4. 生成 event
    5. 更新 state
```

### 10.2 启发式规则（MVP）

```python
def decide_action(agent, world) -> ActionIntent:
    # 1. 能量过低 → 回家休息
    if agent.state["energy"] < 0.3:
        return move_to(agent.home_location_id, reason="energy_low")

    # 2. 在咖啡馆 → 可能和在场的人交谈
    if agent.current_location_id == "loc_cafe":
        others_here = get_agents_in_location(world, "loc_cafe", exclude=agent.id)
        if others_here and agent.state["social_battery"] > 0.4:
            target = pick_by_personality(others_here, agent)  # 倾向熟人/亲和度高者
            return talk_to(target, topic=pick_topic(agent, target))

    # 3. 工作时间内 → 工作
    if is_work_time(world.world_time, agent.occupation):
        work_loc = get_work_location(agent)
        if agent.current_location_id != work_loc:
            return move_to(work_loc, reason="go_to_work")

    # 4. 默认：随机游走
    return random_walk(agent, world)
```

### 10.3 对话生成（MVP）

不调用 LLM，用模板 + 上下文：

```python
TALK_TEMPLATES = [
    "{speaker} 向 {target} 打了个招呼",
    "{speaker} 和 {target} 聊起天气",
    "{speaker} 问 {target} 最近怎么样",
    "{speaker} 和 {target} 分享了今天发生的事",
    "{speaker} 和 {target} 讨论了工作"
]

def generate_talk_event(speaker, target, world):
    template = random.choice(TALK_TEMPLATES)
    return Event(
        event_type="talk",
        actor_agent_id=speaker.id,
        target_agent_id=target.id,
        location_id=speaker.current_location_id,
        description=template.format(speaker=speaker.name, target=target.name),
        importance=0.6 + min(0.3, speaker.relationships.get(target.id, Relationship()).affinity * 0.3)
    )
```

### 10.4 关系更新

```python
def update_relationship(agent, other, interaction_quality):
    rel = agent.relationships.setdefault(other.id, Relationship(other_agent_id=other.id))
    rel.familiarity = min(1.0, rel.familiarity + 0.05)
    rel.affinity = clamp(rel.affinity + interaction_quality * 0.1, -1.0, 1.0)
    rel.trust = clamp(rel.trust + interaction_quality * 0.05, 0.0, 1.0)
    rel.last_interaction_tick = world.current_tick
    if rel.familiarity > 0.7:
        rel.relation_type = "friend"
    elif rel.familiarity > 0.3:
        rel.relation_type = "acquaintance"
```

### 10.5 Phase 2 升级路径

Phase 2 可选地把启发式替换为 **Sampling 反向 RPC**：

```python
async def decide_action_with_llm(agent, world):
    context = build_agent_context(agent, world)
    prompt = f"""你是 {agent.name}，一个 {agent.occupation}。
    当前状态：{context['state']}
    周围的人：{context['nearby']}
    最近的记忆：{context['recent_memories']}
    
    决定你接下来要做什么。返回 JSON：
    {{"action": "move|talk|work|rest", "target": "...", "reason": "..."}}"""

    result = await sampling.create_message(
        messages=[{"role": "user", "content": prompt}],
        system_prompt=agent.personality_prompt,
        response_format={"type": "json_schema", "json_schema": ACTION_SCHEMA}
    )
    return parse_action(result)
```

---

## 十一、文件结构

```
truman-director-app/
│
├── README.md                       # 项目说明
├── MVP.md                          # 本文档
├── pyproject.toml                  # Python 包配置
│
├── manifest.json                   # Anna App manifest (schema:2)
├── app.json                        # Anna App 元数据
├── executa.json                    # Executa 插件注册
│
├── executas/
│   └── truman-world/
│       ├── SKILL.md                # Director 行为剧本
│       ├── executa.json            # 插件注册配置
│       ├── pyproject.toml          # 包配置
│       ├── README.md
│       └── truman_plugin.py        # 主插件入口（stdio loop + dispatch）
│       ├── world.py                # 数据模型 (WorldState, Agent, Event, ...)
│       ├── engine.py               # Tick 编排逻辑
│       ├── agents.py               # Agent 行为规则
│       ├── scenarios.py            # 场景预设
│       ├── storage.py              # APS 持久化
│       └── tests/
│           └── test_world.py       # 单元测试
│
├── bundle/
│   ├── index.html                  # SPA 入口
│   ├── app.js                      # SDK 通信 + 状态管理 + 渲染
│   ├── style.css                   # 样式
│   └── icon.svg                    # App 图标
│
└── docs/
    ├── ARCHITECTURE.md             # 架构详解
    └── SCENARIOS.md                # 场景设计指南
```

---

## 十二、开发计划

### Phase 0：环境准备（0.5 天）

**目标**：本地跑通 `anna-app dev`

- [ ] 安装 `uv`（Python 包管理）
- [ ] 安装 `@anna-ai/cli`
- [ ] 运行 `anna-app doctor` 确认环境
- [ ] Fork `anna-executa-examples` 仓库
- [ ] 本地运行 Focus Flow 示例，确认 `anna-app dev` 工作

**产出**：能加载 Focus Flow 示例，看到它的 UI。

### Phase 1：核心 MVP（3-4 天）

**Day 1-2：插件骨架 + 数据模型**
- [ ] 复制 Focus Flow 结构，改为 `truman-director-app/`
- [ ] 编写 `executas/truman-world/truman_plugin.py`（抄 stdio loop 模板）
- [ ] 实现 `world.py`（数据类）
- [ ] 实现 `scenarios.py`（cafe_town 场景）
- [ ] 编写 `executa.json` + `manifest.json`

**Day 3：Tick 引擎 + 行为规则**
- [ ] 实现 `engine.py`（tick 编排）
- [ ] 实现 `agents.py`（启发式决策）
- [ ] 实现基础事件生成（move/talk/observe）
- [ ] 测试：tick 5 次，确认事件生成

**Day 4：UI Bundle v1**
- [ ] 编写 `bundle/index.html`（布局结构）
- [ ] 编写 `bundle/app.js`（SDK 通信）
- [ ] 编写 `bundle/style.css`（Anna 品牌色）
- [ ] 编写 `SKILL.md`（导演行为剧本）
- [ ] `anna-app dev` 端到端测试

**产出**：能演示 "新建世界 → 推进 → 查看时间线 → 注入事件" 的完整流程。

### Phase 2：增强体验（2 天）

**Day 5：Agent 详情 + 关系可视化**
- [ ] Agent 详情弹窗
- [ ] 关系网络简化图（CSS 动画）
- [ ] 记忆时间线

**Day 6：导演控制台 + 观察推送**
- [ ] 导演操作面板（天气/广播/事件）
- [ ] Skill 自动观察推送逻辑
- [ ] 多场景预设切换

**产出**：完整的演示体验。

### Phase 3：打磨发布（1-2 天）

**Day 7：视觉 + 边界**
- [ ] 视觉调优（动画/响应式/暗黑模式）
- [ ] 错误处理（超时/网络/非法输入）
- [ ] 空状态/加载状态/失败状态

**Day 8：发布准备**
- [ ] Mint Tool ID
- [ ] 同步到 manifest/app.js
- [ ] `pnpm validate` 三层校验通过
- [ ] 准备 hackathon 提交材料
- [ ] 录演示视频

**产出**：可发布的 Anna App。

### 总计：~8 天（含缓冲）

---

## 十三、风险与缓解

| 风险 | 影响 | 概率 | 缓解策略 |
|------|------|------|---------|
| Sampling 权限未默认开启 | Agent 无法用 LLM | 中 | MVP 用启发式，不依赖；Phase 2 调研 |
| Bundle CSP 限制严格 | 复杂 JS 库被拦截 | 高 | 用纯 HTML/CSS/JS，不依赖 CDN；提前验证 |
| 单次 invoke 超时短 | 长 tick 被杀 | 中 | tick 控制在 <5 秒；多 tick 拆多次调用 |
| Tool ID Mint 流程阻塞开发 | 拿不到正式 ID | 低 | 先用占位符 `tool-DEV-truman-world-xxxxx` 开发 |
| APS KV 配额/性能不够 | 大世界状态存不下 | 低 | MVP 控制规模（3-6 agents, 50 ticks）；测试 |
| Anna 平台 API 变动 | 接口不兼容 | 中 | 关注 changelog；用最新 SDK 版本 |
| 时区/语言问题 | 时间显示混乱 | 低 | 用 UTC + ISO 8601；UI 显示本地时区 |

---

## 十四、成功指标

### MVP 验收

- [ ] 能在 Anna 桌面/网页中打开 Truman Director App
- [ ] 新建咖啡馆小镇，3 秒内看到世界视图
- [ ] 点击 Play，世界自动推进（每 2 秒一个 tick）
- [ ] 时间线正确显示最近 10 个事件
- [ ] 点击 agent 看到详情（人设/记忆/关系）
- [ ] 导演注入事件后，下一 tick 生效
- [ ] Skill 在聊天中能正确调用工具并回应用户
- [ ] `pnpm validate` 通过
- [ ] 端到端 demo 视频录制完成

### Hackathon 评分预期

| 维度 | 目标 | 说明 |
|------|------|------|
| **完成度** | 100% MVP 功能 | 所有 Must Have 全部交付 |
| **设计感** | 对齐 Anna 品牌 | UI 融入 Anna 视觉语言 |
| **创新性** | 差异化亮点 | "体验型 App" 是亮点 |
| **代码质量** | 可读 + 可测试 | 至少单元测试覆盖核心逻辑 |
| **演示** | 清晰流畅 | 视频能讲清楚"这是什么" |

---

## 十五、参考资料

| 资源 | URL |
|------|-----|
| Anna Executa Examples | https://github.com/whtcjdtc2007/anna-executa-examples |
| Focus Flow 完整示例 | `/examples/anna-app-focus-flow/` |
| Executa Protocol | https://anna.partners/developers/reference/executa-protocol |
| Anna Storage (APS) | https://anna.partners/developers/reference/executa-persistent-storage |
| Anna Sampling | https://anna.partners/developers/reference/executa-sampling |
| TrumanWorld (现有项目) | 本仓库 `/TrumanWorld/` |
| Generative Agents | https://github.com/joonspk-research/generative_agents |

---

## 附录 A：与 Focus Flow 的对比

| 维度 | Focus Flow | Truman Director |
|------|-----------|-----------------|
| 插件方法数 | 1 (`session`) | 1 (`world`) |
| 工具 action 数 | 5 | 8 |
| 状态存储 | 本地 `~/.anna/focus-flow/state.json` | Anna APS KV |
| 反向 RPC | 否 | 是（Phase 2） |
| UI 复杂度 | 中（一个仪表盘 + 计时器） | 中高（地图 + 时间线 + 详情 + 控制台） |
| Skill 复杂度 | 低（教练式引导） | 中（导演式引导） |
| 持久化范围 | 单会话 | 单 run（可重置） |

---

## 附录 B：术语表

| 术语 | 定义 |
|------|------|
| **Tick** | 世界时间推进的一个最小单位（MVP 中 = 5 模拟分钟） |
| **Run** | 一次模拟会话，从 init 到 reset |
| **Agent** | AI 居民，模拟中的一个角色 |
| **Director** | 用户身份，"导演"模式：观察 + 注入，不操控 |
| **Skill** | Anna 中的 LLM 行为剧本（Markdown 文件） |
| **Executa** | Anna 中的工具插件（Python/Node/Go 进程） |
| **Bundle** | Anna App 的 UI 部分（静态 SPA） |
| **APS** | Anna Persistent Storage，主机托管的 KV 存储 |
| **Sampling** | 插件通过反向 RPC 调用宿主 LLM 的能力 |

---

> **文档状态**: Draft v0.1
> **下一步**: 评审通过后开始 Phase 0 开发
> **Owner**: TrumanWorld Team