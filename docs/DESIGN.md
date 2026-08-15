# Truman Director — 产品与架构总体设计(Design v0.5)

> **状态**:已评审的设计契约。后续开发以此为准;与 CLAUDE.md 冲突时,以本文的「红线修订」章节为准并回写 CLAUDE.md。
> **基线**:v0.3.3(2026-08-15)。本文取代 MVP.md 成为路线权威(MVP.md 保留为历史文档)。
> **业务窗口**:Anna Founding Builder Program——2026-08 为 Build & Beta;**2026-09-01 起计量 MAU**;资格窗口至 2026-11-30(详见 `../anna-forum-qa/topic-205-founding-builder-program.md`)。

---

## 1. 定位与北极星

MVP 回答了"能不能":居民动作完全由模型产出,红线架构经住考验。深化阶段的产品命题是**留存**:

> **用户为什么明天还打开它?**

资助计划的规则把这一点变成硬指标:MAU 只认 Qualified Run(成功执行主功能的去重用户),月活靠"牵挂感 + 未完待续"。

**北极星**:小镇是一部剧,用户是导演,居民是会记忆、会成长的角色,剧情永远未完待续。

三个情感杠杆:

| 杠杆 | 机制 | 产品载体 |
|---|---|---|
| 牵挂感 | 角色有内心世界(记忆/洞察/目标) | 居民详情、反思 |
| 期待感 | 剧情有线索与悬念(arc、cliffhanger) | 故事视图、张力面板 |
| 错过的代价 | 时间在流逝,回来能补叙 | 时间跳跃、蒙太奇、日终故事 |

### 1.1 两个必须大声说出来的产品真相

这两点是产品文案与 UI 叙事的第一原则,不只是架构内部约定:

1. **「没有脚本」**——居民的每个动作都是模型此刻的实时决定,不是动画、不是规则引擎。这是与一切"假 AI 宠物"产品的本质分界,在 App 介绍、空状态文案、首次体验中明说。
2. **「看不见的导演」**——用户的权力对居民是无形的(你下的雨,他们以为是天气)。这是楚门隐喻的情绪核心:观察者与造物者的伦理张力。产品语气 lean in,不用"模拟器仪表盘"的自我框架。

**30 秒电梯稿**(对外统一口径):「一座真 AI 居住的小镇。他们自己生活、自己记仇、自己坠入爱河——没有剧本,每个动作都是 AI 此刻的决定。你是看不见的导演:下点雨,派个陌生人,看命运怎么转弯。明天,故事继续。」

## 2. 现状基线(v0.3.3)

已在且不动摇的资产:

- `engine.decide`:唯一 LLM 调用点,`sampling/createMessage` + json_schema strict,一次调用决定**全体居民**(群像模式);
- `WorldState` ↔ APS KV `truman:run:world` 单一真相;插件重启自动恢复;
- `world` 单分发器:`init` / `tick` / `inject_event`;`MAX_TICKS_PER_INVOKE = 8`(per-invoke sampling 预算);
- 事件:`move/talk/work/rest/director_inject/world_change`,`current_activity` 落地,关系 familiarity 双向 +0.05;
- 二进制分发 + 多平台 CI;契约测试 48 通过。

已知短板(本设计要解决的):角色是纸片人(无记忆/目标演化)、事件流不成故事、导演只能扔单事件、离开即冻结、无分享。

## 3. 产品设计:五层

### L1 居民内心世界

- 每居民**记忆流**(亲历事件按重要性留存)、**洞察**(反思综合出的高层认知)、**目标**(随反思漂移)。
- **呈现原则:内心世界以行为变化被感知,而不是以数据面板**。依恋来自"看见她变了"——Alice 今天绕开 Bob 走,比她记忆列表里的二十条记录有力一百倍。UI 把行为/关系变化作为**戏点**叙事化推送(时间线高亮);记忆弹窗是给"已经在乎的人"的深读入口,不是依恋的来源。
- 感知边界:居民只知道**自己亲历**的事(记忆按当事人过滤落账),不知道全知视角。

### L2 故事线

- **Arc(剧情线)**是一等公民:有阶段(萌芽/发展/高潮/消解)与张力的多 tick 线索;来源三种——场景内置摩擦种子、导演点燃、叙事中涌现。
- **日终故事**:模拟日跨零点时生成散文体"本日剧情",与原始事件时间线并列。narrate 的 prompt 要求:**当天的导演注入与剧情存在因果关系时,故事必须显式回扣**(「今天,因为你早晨派来的那个陌生人……」)——导演的作者感要在叙事里被承认。
- **Cliffhanger**:日终叙事收在开放线索上——回访钩子。

### L3 导演 2.0

- **意图级注入**(`direct`):说"让 Alice 和 Bob 产生误会",模型展开为 1–3 个跨 tick 注入计划;导演权力不变(仍走注入队列),模型只是起草人。
- **张力面板**:活跃剧情线、张力值、参与者一目了然。**因果被庆祝**:arc 记录 `origin`,UI 剧情线卡片对 `origin: director` 的线索标注「因你而起」——作者感是导演玩法的核心满足,必须可见。
- **戏剧开场**:init 完成后不是让用户"看人喝咖啡",而是弹三选一开场(如「一个陌生人今天到镇上」/「咖啡馆丢了件重要的东西」/「Truman 收到一封信」),一键注入 + 自动跑 3 tick——首分钟就有戏,同时教会用户"导演是做什么的"。
- 跟拍模式(focus):后续迭代,锁定单居民视角推进。

### L4 时间与会话

- **时间跳跃**(`skip_time`)双模式:
  - **细补叙**(离开较短,≤ 补叙上限):逐 tick 补齐推进——"你不在的六小时,小镇也在生活"。
  - **蒙太奇**(离开超过上限):不再假装能补齐每一分钟——采样 3 个代表性时刻推进 + narrate 生成「你不在的这些天」摘要故事。预算:3 decide + 1 narrate = 4 调用 ✓。预算约束不再泄漏为"离开两天只补四小时"的心智破绽。
- 平台限制(Agent 离线则 Executa 停)转化为产品语义:**世界暂停,回来时选择补叙**。
- 日边界是仪式点:反思 → 日终故事 → checkpoint。

### L5 分享与传播

- 日终故事经 `chat.append_artifact` 推进聊天——**官方文档核实:该 API 完整实现但只在 bundle iframe 面**(插件不能调),ACL 要求 `manifest.ui.host_api.chat: ["append_artifact"]`,artifact summary ≤1000 字符。实现路径:bundle 读 `get_story` 后调 `anna.chat.append_artifact(...)`。
- ⚠️ 现有 manifest 授的是 `chat.write_message`(官方 Phase-3 stub,从未可用)→ M1 顺手替换为 `chat.append_artifact`(permissions 与 host_api.chat 两处)。
- 分享"我的小镇今天的故事" → 拉新 → "来导演你自己的小镇"。

### 3.6 呈现层原则与克制清单

**戏点规则**(什么在 UI 里被高亮为"戏"):
- M1:导演注入事件 + 高 importance 事件(importance ≥ 0.8)在时间线高亮——确定性信号,零启发式争议;
- M2 起:narrate 在日终标记当日「转折点」(模型判定),次日与回访时以叙事卡呈现("昨天,Alice 第一次没有赴约")。

**克制清单(明确不做)**:
- ❌ 成就系统 / 徽章 / 收集要素——会把"剧"降格为任务清单,破坏调性;
- ❌ 居民养成数值面板(能量条/心情条之类)——内心状态通过行为与叙事透出,不做成仪表盘;
- ❌ 倒计时/推送式焦虑机制——回访钩子只靠 cliffhanger 本身,不靠红点。
- 用户的"进度感"唯一来源:**我导演出的剧情**(因你而起的 arc、被回扣的注入)。

**首次体验节奏**(首分钟定生死):init → 三选一戏剧开场(§L3)→ 自动 3 tick(注入生效)→ 日终故事预告。空状态文案直说产品真相:「没有脚本——他们的每个动作,都是 AI 此刻的决定。」

> 原「下一步清单」全部归位:补 action → §7;async 进度 → L4 地基;居民详情弹窗 → L1 的 UI;多场景/记忆 → L1/L2。

## 4. 架构红线(不变)与修订

五条红线(CLAUDE.md)是资产——"AI 原生核心"审核维度的天然证明。深化以增量方式发生,仅一处**表述修订**:

> **红线 1 修订**:「engine.decide 是唯一 LLM 调用点」→「engine.decide 是唯一**决策**调用点;**认知类**调用(reflect / narrate / direct_draft)同样集中在 engine.py,同样 json_schema strict,但**不产生居民动作**——它们合成记忆、叙述故事、起草注入,居民做什么永远只由 decide 决定」。

红线 2 落地方式(重要):`snapshot()` 继续是**唯一完整序列化**(写 KV);新增 `world_view()` 作为喂 prompt 的**纯函数投影**(从 snapshot 派生、做 top-k 裁剪)。`world_view` 不持有独立状态、可随时从 snapshot 重算——是投影,不是影子状态。记忆剪枝(重要性 × 新近度)是上下文预算基础设施,不是行为决策,不触红线 1。

## 5. 数据模型变更(字段级)

### 5.1 WorldState 增量

```python
@dataclass
class WorldState:
    # —— 现有字段不动 ——
    run_id: str; scenario: str; current_tick: int; world_time: str; tick_minutes: int
    locations: dict[str, Location]; agents: dict[str, Agent]; events: list[Event]
    _pending_injections: list[dict]
    # —— 新增 ——
    day: int = 1                       # 第几个模拟日;advance_tick 跨 00:00 时 +1
    arcs: list[Arc] = []               # 活跃+已结剧情线(上限 20,超出收最旧 resolved)
    stories: list[DayStory] = []       # 日终故事(保留最近 7 天)
    last_seen_at: str = ""             # 最近一次成功 invoke 的 ISO 时间(skip_time 依据)
```

`advance_tick()` 跨零点时 `day += 1`,由 `tick()` 检测并触发**日边界例程**(§6.2)。

### 5.2 Agent 增量

```python
@dataclass
class Agent:
    # —— 现有字段不动(id/name/occupation/home/current_location/personality/
    #    current_activity/relationships)——
    goal: str = ""                     # 当前目标;初始来自场景 spec,反思可更新
    insights: list[str] = []           # 反思产出(上限 10 条/人,新替旧)
    memories: list[Memory] = []        # 记忆流(上限 50 条/人,§5.4 剪枝)
```

### 5.3 新 dataclass

```python
@dataclass
class Memory:                          # 一条居民记忆
    id: str; tick: int; day: int
    content: str                       # 一句话,第一人称视角
    kind: str                          # observed / interaction / reflection
    importance: float = 0.5            # 落账时定:注入/剧情事件高,日常低

@dataclass
class Arc:                             # 一条剧情线
    id: str; title: str
    participants: list[str]            # agent ids
    stage: str                         # seed / developing / peak / resolving / resolved
    tension: float                     # 0.0–1.0
    origin: str                        # scenario_seed / director / emerged
    last_tick: int; summary: str = ""

@dataclass
class DayStory:                        # 一天的故事
    day: int; tick_from: int; tick_to: int
    story: str                         # 散文体,150–300 字
    cliffhanger: str                   # 开放线索一句话(可为空)
```

### 5.4 喂 prompt 的投影:`world_view()`

| 区块 | 来源 | 裁剪 |
|---|---|---|
| 时间/地点/在位者 | snapshot 同款 | 不裁 |
| 各居民 | goal + insights + **memories top-k**(k=8,按 importance × 新近度衰减) | 全量留 snapshot |
| 事件尾 | events[-20:] | 不变 |
| 活跃剧情线 | arcs 中 stage ≠ resolved(title/stage/participants/summary) | ≤5 条 |
| 昨日故事 | stories[-1] 的 story + cliffhanger | 1 条 |

体积预算:world_view 控制在 ~8KB(现 snapshot ~5KB);完整 snapshot(含全量记忆)估 20–50KB。**APS KV 单值上限 64KB**(官方 storage 参考页现行口径;2026-06 论坛 hunter 曾说 256KB,从紧取 64KB)→ snapshot 必须严格控界,M2 落地时实测;超界的既定后备:把 `stories` 拆到第二个 KV key `truman:run:stories`(红线 2 的受控修订:真相仍是 WorldState,只是序列化分槽),或走 storage files API(hunter 建议的大对象通道,单文件可到 MB 级)。

### 5.5 序列化兼容

`from_snapshot` 对新字段全部 `get(..., 默认)`——**旧存档(0.3.x)加载后可继续跑**,记忆/剧情线从空开始自然生长。`snapshot()` 新字段随旧字段一起序列化。

## 6. LLM 调用体系与预算

### 6.1 调用分类(全部集中在 engine.py)

| 调用 | 类型 | 触发 | 输出 |
|---|---|---|---|
| `decide` | 决策 | 每 tick | `DECISION_SCHEMA`(**不变**——深化不碰决策 schema) |
| `reflect` | 认知 | 日边界 | `REFLECTION_SCHEMA`:每居民新 insights / goal 更新 / 新记忆(reflection 类) |
| `narrate` | 认知 | 日边界(reflect 之后) | `NARRATIVE_SCHEMA`:story + cliffhanger + arc_updates(增/改 stage、tension) |
| `direct_draft` | 认知 | `direct` action | `INJECTION_PLAN_SCHEMA`:1–3 个注入 spec,各带 `delay_ticks`(0–3) |

所有 prompt 文案集中在 `prompts.yaml`(单一来源不变),新增 `reflect` / `narrate` / `direct` 三节。

### 6.2 日边界例程(在触发跨零点的那次 tick 之后,同一 invoke 内)

```
tick 检测 day 滚动 → reflect(当日事件, 各居民记忆) → 落账 insights/goal/memories
                  → narrate(当日事件 + arcs + 昨日故事) → 落账 story/arcs
                  → persist snapshot
```

预算核算(per-invoke max_calls = 8):普通 tick invoke = 1;跨日 tick invoke = 1(decide) + 2(reflect+narrate) = 3 ✓;`direct` = 1。

### 6.3 时间跳跃(`skip_time`)——已按官方文档核实修订

官方预算口径(executa-sampling 参考页):**sampling 调用上限按 `invoke_id` 计,默认 8 次/invoke;累计 token 32K/invoke**。async job 文档未提及豁免 → **单个 job 内跑 48 tick 必然烧穿调用上限**。因此:

- `skip_time(ticks)` 的单次 action 调用**上限 6 tick**(≤6 decide + 1 日边界余量,留在 8 次内);
- **细补叙**(总补叙量 ≤ 48 tick = 4 小时模拟时间):由 **bundle 分批驱动**:循环提交 `invokeAsyncAwait`(每批一个 job,`clientTag: "truman-director"` 支持重载恢复),批间由 bundle 渲染进度;
- **蒙太奇**(离开时长 > 细补叙上限):单次 invoke 完成——3 个采样时刻各跑 1 tick(decide),时刻间用**时间跳跃**(直接设置 `world_time`/`day`,是状态操作非决策,红线安全),最后 1 次 narrate 生成「你不在的这些天」摘要故事并更新 arcs。共 4 次调用 ✓;
- 每批 job 内插件用 `emit_progress("tool_update", {batch, done, total_ticks})` 推细粒度进度(宿主侧 50 事件/s、单事件 ≤8KB、ring 保留 500 条);
- job 超时 `timeoutMs`:async 默认 30 分钟(clamp 60s–24h),时间预算充裕;每批建议 `60s + ticks × 15s`;
- 重载恢复:bundle 启动时 `listJobs({clientTag})` + `getJob` 重新挂载进行中的补叙,进度从 `lastSeq` 续播。

⚠️ M1.0 保留一项实测:dev harness 确认 async invoke 的 sampling 预算确实沿用 8/invoke(若是,维持上述分批方案;若平台给 async 更大口径,可放宽单 job 批量)。

## 7. world 工具 API(action 3 → 10)

单分发器不变(红线 3)。新增:

| action | 参数 | 返回 | 说明 |
|---|---|---|---|
| `reset` | `scenario?`/`spec?` | 同 init | 重开一局(新 run_id,清旧快照) |
| `list_scenarios` | — | 预设列表 | cafe_town + 后续场景包 |
| `get_agent` | `agent_id` | 全量居民详情(含 memories/insights/goal/relationships) | L1 UI / Anna 对话用 |
| `get_timeline` | `limit?`(≤100)/`agent_id?`/`event_type?` | 事件列表 | 从内存 events(尾 500)取 |
| `get_story` | `day?` | stories + 活跃 arcs | L2 UI / Anna 叙事用 |
| `skip_time` | `ticks`(细补叙单次 ≤6)/ `mode:"montage"` | 补叙结果摘要 / 摘要故事 | §6.3 双模式:细补叙 bundle 分批;蒙太奇单 invoke(3 decide + 1 narrate) |
| `direct` | `intent`(自然语言) | 注入计划(1–3 条,含 delay) | §3 L3;落注入队列 |

`manifest.json` 的工具参数表与 `system_prompt_addendum` 随之扩展(Anna 获得叙事级驱动力)。

## 8. bundle 信息架构

三视图 + 导演面板(无构建步骤、ES module 约定不变):

```
┌ 顶栏: 第 N 天 HH:MM [▶ 推进] [⏩ 补叙] ┐
│ [剧场]  地图 + 在位者 + current_activity  │  ← 现有,增强
│         时间线: 戏点高亮(注入/转折)      │  ← 新(§3.6)
│ [故事]  日终故事流 + 活跃剧情线           │  ← 新
│         arc 卡片: origin=director 标      │  ← 新
│         「因你而起」徽章                  │
│ [居民]  卡片墙 → 点开: 目标/洞察/记忆/关系 │  ← 新(L1)
└ 导演面板: 意图输入(direct) + 张力面板 + 事件注入 ┘
```

- **戏剧开场**:init 成功后立即弹三选一开场卡(模板来自 §9 M1.2 场景数据),一键 = `inject_event` + bundle 顺序驱动 3 个单 tick invoke(每 invoke ≤90s 安全余量)。
- **回归提示**:加载时对比 `last_seen_at`——离开 30 分钟~4 小时弹"细补叙"邀请;超过 4 小时弹**蒙太奇**邀请(「你不在的这些天……」);当天已有故事则首屏直接展示 cliffhanger。

## 9. 里程碑

### M1 — 8 月,上架窗口(目标:8 月内过审,9 月整月计量)

| 项 | 内容 | 验收 |
|---|---|---|
| M1.0 | invokeAsync 通道与预算口径实测 | dev harness E2E 报告,确认 §6.3 分批参数(async job 的 sampling 调用是否沿用 8/invoke) |
| M1.1 | 补 `reset`/`list_scenarios`/`get_agent`/`get_timeline` | 契约测试;Anna 对话可"重开/看看 Alice" |
| M1.2 | **场景戏剧种子**:cafe_town 烤入冲突(Alice 暗恋 Bob / Bob 赶稿期限就在本周 / Truman 藏着不敢说的秘密——身份焦虑,呼应楚门);`goal` 字段提前落地(§5.2)并由场景预填;附 3 个戏剧开场注入模板 | 首个 tick 起居民行为就带张力;narrate 有素材可写;种子仅是初始条件,无任何行为规则(红线 1 安全) |
| M1.3 | **戏剧开场 flow**:init → 三选一开场卡 → 一键注入 + 自动 3 tick | 新用户首分钟内看到第一个"戏";开场后引导首个手动 tick |
| M1.4 | 居民详情视图(现有数据:personality/activity/relationships/goal) + 时间线**戏点高亮**(注入 + importance ≥ 0.8) | UI 弹窗 + get_agent;注入事件在时间线视觉可辨 |
| M1.5 | **日终故事 v1**:`day` 计数 + narrate 调用(含导演因果回扣 prompt)+ `get_story` + 故事视图(无记忆/反思,arcs 空转) | 连跑 2 个模拟日,故事视图出散文 + cliffhanger;注入过的当天,故事出现显式回扣 |
| M1.6 | 多 tick async 化:bundle 弃 for 循环,改 `invokeAsyncAwait` + `onProgress`(`clientTag` 固定);插件 `world` 工具 manifest 声明 `timeout`,handler 内 `bind_invoke(params)`(**contextvars 不跨线程——truman 经 run_coroutine_threadsafe 跨线程,绑定必须落在协程内部**);每 tick 后 `emit_progress` | 10+ tick 连跑,进度实时,timeline 增量渲染;iframe 重载后 `listJobs`+`getJob` 恢复进行中任务 |
| M1.7 | 打磨上架:首跑体验(init→tick 稳定)、错误态、空状态文案(§1.1 产品真相)、`chat.write_message`→`chat.append_artifact` 权限替换、golden fixture 提交 + CI verify/replay(§13.4)、**二进制冷启动实测**(官方 pitfall #7:稳态 describe 仅 5s 超时)、`anna-app validate` 进 checklist、版本 0.4.0 | apps publish + 提审;录制基线可回归;冷启动实测报告 |
| M1.8 | **日志地基**(§13 L0–L2):stderr 通道纪律(含 Windows UTF-8)+ logging 框架(`TRUMAN_LOG_LEVEL`)+ §13.2 事件清单 + decide 最近一次 I/O 内存 ring | 契约测试断言关键事件有日志;stdout 无任何非协议输出 |

**M1 有意不含记忆系统**:narrate 只需要当日事件——故事钩子最早落地,记忆/反思留给 M2。戏剧种子与开场保证 M1 版本**从第一分钟起就有戏**,不是等 M2 才有吸引力。

### M2 — 9 月,计量期深化

| 项 | 内容 |
|---|---|
| M2.1 | 记忆流落账(decide 后按当事人过滤写入,importance 规则)+ `world_view()` 投影 |
| M2.2 | reflect 调用 + insights/goal 演化 + 居民详情展示记忆;**戏点升级**:narrate 标记当日转折点,行为变化叙事化呈现(§3.6) |
| M2.3 | Arc 状态机(narrate 输出 arc_updates;场景 spec 支持 `seed_arcs`;UI arc 卡「因你而起」徽章) |
| M2.4 | `skip_time` 双模式落地:细补叙(分批 job)+ **蒙太奇**(§6.3)+ 回归提示分级 UI |
| 验收 | 连续 3 天真实使用:居民目标可观察漂移;≥2 条 arc 走完 seed→resolved;补叙一次成功;**快照 < 60KB**(KV 上限 64KB 留余量);蒙太奇故事可读且 arcs 连续 |

### M3 — 10 月起

`direct` 意图注入、`append_artifact` 日故事分享、场景包(办公室/夜市,内置 seed_arcs)、跟拍模式。

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| **同步 invoke 90s 硬顶**(官方 tools 参考:timeoutMs clamp 1–90s,缺省 65s) | 现状 `tick n=8` 单采样超时 60s,慢模型下理论可超 90s → tool_timeout。M1.4 起 `n>2` 一律走 async job;单/双 tick 保留 sync 路径 |
| **sampling 调用上限 8/invoke_id**(默认;hunter 在 forum #84 表示愿意为 Truman 用例上调) | 所有 invoke 内调用数 ≤8(§6.2/§6.3 已核算);若实测确实受限且 8 不够,向平台申请上调是既定沟通路径 |
| sampling 失败重试策略缺失 | 官方建议(hunter #84):仅 `-32003`(provider)/`-32005`(timeout) 有界重试 ≤2 次,auth/quota 类(-32001/2/6/7)不重试。M2 在 engine 认知调用层引入(decide 保持现状,重试属传输层非降级) |
| 快照膨胀逼近 **KV 单值 64KB** | §5 全部 bound;M2 实测;后备:stories 拆第二 key 或 files API(§5.4) |
| narrate/reflect 文风与质量 | prompts.yaml 迭代;strict schema 保证结构(上限:序列化 ≤32KB/深 ≤8/≤512 节点,新认知 schema 落地时自查);M1 观察真实输出 |
| call API 抹 error code | 已知(message `[code]` 前缀约定不变) |
| 旧存档兼容 | §5.5 全默认值;0.3.x 快照加载即迁移 |
| 红线漂移 | 每次 PR 自查:新代码是否只在 engine 加调用、只在 world 单入口、失败是否冒泡 |

## 11. 北极星指标(对齐资助计划)

| 指标 | 定义 | 目标 |
|---|---|---|
| Qualified Run 转化 | 打开 App → 成功完成 init+首个 tick | M1 后 ≥ 90% |
| 首会话戏剧完成率 | 新用户完成「戏剧开场 + 自动 3 tick」 | ≥ 70%(首分钟定生死) |
| 次周回访 | 首用后 7 天内再次推进世界 | M2 后 ≥ 25% |
| 导演作者感(定性) | 用户注入与后续 arc 存在因果且 UI 可见 | M2 后抽查日志,注入→arc 转化 ≥ 30% |
| 月活(资助口径) | 月内 ≥1 次 Qualified Run 的去重用户 | 11-30 前达 200(Tier E) |

---

## 12. 附录:官方资料核对记录(2026-08-15)

技术路径已逐条对照官方实现与文档核实,来源与结论留档,避免重复考证:

| # | 假设 | 结论 | 来源 |
|---|---|---|---|
| V1 | invokeAsync 通道可用 | ✅ bundle SDK ≥0.15 `invokeAsyncAwait({tool_id,method,args,timeoutMs,clientTag}, {onProgress,signal})`;错误码族 tool_failed/tool_timeout/cancelled/wait_timeout(带 jobId);cancelJob 幂等 | host-api-tools 官方参考 + long-task-demo bundle 实现 |
| V2 | async job 时间预算 | ✅ timeoutMs 为任务级 deadline,缺省 30 分钟,clamp 60s–24h;进度事件 ring 保留 500 条,`listJobs({clientTag})`+`getJob` 重载恢复 | 同上 |
| V3 | sampling 预算口径 | ⚠️ **按 invoke_id 计,默认 8 调用、32K 累计 token/invoke**;async 文档未提豁免 → skip_time 分批(§6.3);M1.0 实测确认 | executa-sampling 官方参考 |
| V4 | 同步 invoke 时限 | ⚠️ timeoutMs clamp 1–90s(缺省 65s,可回退插件 tool_def.timeout);超 90s 必须 async | host-api-tools 官方参考 |
| V5 | progress 事件约束 | ✅ 50 事件/s/invoke、单事件 ≤8KB、只对 async invoke 生效、无需额外 host_capabilities;`bind_invoke` 基于 contextvars——**不跨线程**,truman 的 run_coroutine_threadsafe 模式必须在协程内绑定 | SDK progress.py/context.py 源码 + long-task-demo |
| V6 | APS KV 单值上限 | ⚠️ 现行文档 **64KB**(2026-06 forum #84 hunter 口径 256KB,从紧);`storage/set` 有 ETag 但红线 5 不用锁 | executa-persistent-storage 官方参考 + forum #84 |
| V7 | chat.append_artifact | ✅ 唯一完整实现的 chat API,但**仅 bundle iframe 面**;ACL `ui.host_api.chat`;summary ≤1000 字符;现 manifest 的 `chat.write_message` 是 stub 需替换 | host-api-chat 官方参考 |
| V8 | response_format 约束 | ✅ 序列化 ≤32KB、深度 ≤8、≤512 节点;`_meta.responseFormat.structuredValid` 可查解析结果;重试仅建议 -32003/-32005 | executa-sampling + forum #84 hunter |
| V9 | 平台对项目的态度 | ✅ hunter 明确:"raising sampling budget for your use case is a conversation we're happy to have"——预算/状态上限/长时执行均在"平台升级"谈判桌上;提供提审前设计评审支持 | forum #84 |
| V10 | 大 payload 传输 | ✅ stdio 帧 >512KB 自动切文件传输;invoke 返回建议发增量而非全量(bundle 渲染本就走 storage 读) | forum #84 hunter |
| V11 | 官方测试设施 | ✅ `anna-executa-test`(生产同源 invoker + Hypothesis 契约 fuzz + wire_format 校验);`anna-app dev` 自动录制会话到 `fixtures/` + `fixture verify/summarize/replay` CLI;`mountBundle` vitest | staging.anna.partners/developers/apps/{testing-plugin,recording-replay,testing-bundle} |
| V12 | 官方排障清单 | ✅ 7 条 pitfalls:进程长驻/三名一致/**stderr-only**/parameters 形状/返回形状/包内 manifest/**PyInstaller 冷启动 vs 5s describe**——冷启动与我们 binary 分发直接相关 | staging.anna.partners/developers/tools/executa-pitfalls |
| V13 | **本地 harness 实测(2026-08-15)** | ⚠️ `anna-app dev` 0.1.30 本地 runtime **没有 job 通道**:`tools.listJobs` 报 `unknown_method`(≠ 文档的 `not_implemented`)→ async 路径在本地 harness 无法验证,只能在平台真机验证;bundle 降级已同时兼容两种错误码 | 本机 dev harness RPC log 实录 |
| V14 | **本地 harness 实测(2026-08-15)** | ✅ bundle 真机加载/连接/ACL 全通(含 `chat.append_artifact` 授权生效);🐛 抓到并修复两个真 bug:`[hidden]` 被 `.openings{display:flex}` 覆盖导致遮罩常驻挡死 UI(CSS 已加 `[hidden]{display:none!important}`)、`unknown_method` 不触发 sync 回退(已修) | 本机 dev harness 会话 |
| V15 | **协议级 E2E(2026-08-16)** | ✅ `scripts/local_e2e.py`:真插件 stdio 全链路(initialize v2/describe/init/tick×2 跨午夜→narrate→故事落快照/get_agent/get_story)mock-LLM 模式全过;真 LLM 路径已打通到 complete 端点(PAT→mint 成功),**当前被账号态阻断:APP_QUOTA_EXCEEDED "Subscription expired"**——续费/领积分后去掉 MOCK=1 即可跑真模型。另:平台 API 在 Cloudflare 后,Python/curl 指纹被 1010 拒,须 Node fetch(脚本已内置)。 | 本机执行记录 |

> 官方文档入口(AI 可读,可粘贴给任意编码助手):https://staging.anna.partners/llms.txt

---

## 13. 可观测性与测试

> stdio 插件 + 「模型是唯一决策者」架构的可观测性代价:**stdout 被协议独占,决策不可复现**——所以通道纪律、结构化日志与决策取证是基础设施,不是锦上添花。

### 13.1 通道纪律(L0)

- **stdout 只允许 JSON-RPC 帧**(官方 pitfalls #3:banner/调试打印会污染协议流,Agent 侧报 `Failed to parse JSON-RPC frame`);
- 一切人读输出走 **stderr**;Windows 下启动时 `sys.stderr.reconfigure(encoding="utf-8")`(主开发机即 Windows,GBK 控制台会炸编码);
- PyInstaller 打包后同样只依赖 stderr,不写日志文件。

### 13.2 结构化插件日志(L1)

stdlib `logging` + stderr handler,级别由 `TRUMAN_LOG_LEVEL` 控制(生产默认 INFO,排障 DEBUG)。红线 5 的串行模型保证 stderr 单写者、无锁安全。

| 事件 | 级别 | 记录内容 |
|---|---|---|
| invoke 进出 | INFO | action、参数摘要、耗时、成败/错误码 |
| decide 调用 | INFO(详情 DEBUG) | tick、prompt/响应字节数、解析路径(dict/list)、事件数 |
| storage 读写 | INFO | key、字节数、耗时(**兼作 §5.4 快照体积监控**) |
| 注入队列 | INFO | 入队/生效 tick |
| 日边界例程 | INFO | reflect/narrate 各步耗时与产出规模 |
| dual-parse 容错触发 | WARNING | strict json_schema 偶发裸数组的观测点 |
| 红线级失败 | ERROR | 错误码 + 完整上下文(**既冒泡又留痕,日志永不吞错**) |
| emit_progress 发送 | DEBUG | type、seq(best-effort,失败不记错) |

### 13.3 决策取证(L2,本项目特有)

「Alice 为什么这样做」是必然出现的 bug 报告,而决策不可复现——必须留证:

- decide 每次调用:内存 ring 保留**最近一次完整 prompt/response**(不持久化、不进快照,红线安全);
- M2 可选:dev 用 `world action="get_debug"` 让 Anna 对话直接调取最近一次决策 I/O,支撑对话式排障(不计入 §7 的 10 个正式 action)。

### 13.4 官方测试设施接入(L3,已核实存在)

| 设施 | 用途 | 采纳决策 |
|---|---|---|
| [`anna-executa-test`](https://staging.anna.partners/developers/apps/testing-plugin.md) | 官方 pytest 插件:**与 Anna Agent 生产同源的 stdio 客户端** spawn 插件;`assert_jsonrpc_ok/error`;`wire_format.validate_response`(nexus 契约级信封校验);Hypothesis 对声明参数自动 fuzz;`mock_state_dir` 状态隔离 | M1 评估迁移现有自研 subprocess 契约测试(至少引入 wire_format + 参数 fuzz 两件套) |
| [会话录制回放](https://staging.anna.partners/developers/apps/recording-replay.md) | `anna-app dev` 自动把 RPC 信封录成 JSONL 到 `fixtures/`;`fixture verify`(结构+时序)、`summarize`(调用统计/错误分解)、`replay`(对新 manifest 干跑,暴露 ACL/改名破坏) | M1 起提交 golden 录制进仓库,CI 跑 verify/replay 作回归基线(manifest 已声明 `fixtures/*.jsonl`,机制零配置) |
| `mountBundle`(vitest) | bundle 测试,同款 ACL 门控 + 确定性事件投喂 | M2/M3 按需(bundle 逻辑复杂化后再上) |
| `anna-app validate` | manifest/结构校验 | 进发布 checklist(M1.7) |
| [官方 pitfalls 清单](https://staging.anna.partners/developers/tools/executa-pitfalls.md) | 7 条症状级排障:进程长驻、三名一致(tool_id=describe.name=包内 manifest name)、stderr 纪律、`parameters` 非 MCP `input_schema`、返回形状、包内 manifest.json、**PyInstaller 冷启动 vs 5s describe 超时** | 冷启动实测进 M1.7(我们 `--onefile` 二进制直接暴露在此坑下);其余已在架构中规避 |

### 13.5 分层小结

L0 通道纪律 → L1 结构化日志 → L2 决策取证,三层随 M1 日志地基一次落地;L3 官方设施(golden fixture、契约 fuzz、validate)随 M1 各项推进接入。**日志是红线 4「失败要响亮」的诊断面:错误必须既冒泡又留痕。**

---

> **文档状态**:Design v0.5 · 2026-08-15 · v0.4 技术路径对照官方资料核实(§12);v0.5 增补用户心智修订(§1.1/§3/§3.6/戏剧种子/蒙太奇)与可观测性体系(§13)
