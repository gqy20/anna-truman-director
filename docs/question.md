# World Director:架构三难与平台卡点

> 给 Anna 平台团队(Hunter)/ 内部存档。
> 核心:**纯云 + 对话驱动 + 单 Anna** 三个目标在当前平台**不可同时满足**,需要平台级升级才能打破。

---

## 1. 背景

World Director 是 experience 类型 Anna App(tick 驱动的迷你 AI 小镇)。

- **P1 纯云迁移(已完成,0.2.2 published)**:tick 引擎从 Python Executa 搬到 `bundle/world.js`,只用平台原生 host API(`anna.llm.complete` + `anna.storage`),**零本地依赖** —— 去 Executa、去 Matrix Agent。用户打开即用。
- **目标体验**:experience 对话驱动 —— 用户和**平台 Anna**(主对话)说"推进时间 / 来场暴雨",Anna 控制 bundle 显示台(地图/timeline),bundle 闭嘴只显示。

## 2. 三难

| 目标 | 当前状态 |
|---|---|
| 纯云(零本地依赖) | ✅ 已实现(P1) |
| 对话驱动(平台 Anna 控制 bundle) | ❌ 卡住 |
| 单 Anna(无双 Anna 冲突) | ⚠ P1-v2 试过 bundle 内 Anna,导致双 Anna 冲突 |

三者**在当前平台不可同时满足**。任一方案只能取其二。

## 3. 卡点(实测 + 官方资料查证)

### 卡点 1:平台 Anna 不能写 storage

设想:平台 Anna 写指令 → bundle 轮询读执行。实测(`anna.partners` 主对话,让 Anna 调 `anna.storage.set({key:"truman:test"})` + 读回):

- Anna **无工具调用 UI**,回应是幻觉("我这就测试…执行结果:"但结果为空)
- 即平台 Anna 工具集**没有可靠的 `anna.storage.set`**

官方查证:5 个 `system_prompt_addendum` 示例(llm-demo / focus-flow / aps-files / visual-brand / embed)**无一让 Anna 写 storage**;`host_api.storage` 是 **bundle iframe 专用 ACL**(forum:3074),不是平台 Anna(对话智能体)的入口。

### 卡点 2:chat.read_history 是 stub

模式 C(Anna→bundle 推送)需要 bundle 监听平台对话消息。但:

- `chat.read_history` 和 `write_message` 都是 **Phase-3 stub**(forum:3078 官方:"so you know not to depend on persistence yet"),只有 `append_artifact` 完全实现
- bundle SDK 虽有 `anna.on(kind, fn)` 事件框架,但**没有 chat 消息 event 被推送**(已知 event 仅 `auth.refresh` / `rpc.stream` / `entry_payload`)

### 卡点 3:无云端 Executa

若走官方推荐的 Executa(focus-flow 模式),核实(forum + anna-executa-examples):

- Executa 是 **stdio JSON-RPC**,天生是本地子进程(anna-executa-examples README:9)
- distribution 的 `local` / `binary` / `uv` / `npm` / `pipx` **全部是"把可执行物送到用户本地 Agent"**,不是"上传平台云端跑"
  - `binary` = PyInstaller 二进制,平台 mirror 到 R2 做 **CDN 下载分发**,**Agent 下载到本地后 spawn**(forum:1306:"the Anna Agent can automatically download and install")
- **Matrix Agent 必须在线**,否则 Executa 不可调:
  - MacBook 合盖 → Agent offline → 所有本地 Executa 能力断(forum:9194)
  - end-user 零本地工具 → 模型"假装"执行(forum:4712)
- 官方架构定性 **"local execution + cloud intelligence"**(forum:8310),local execution = Executa,是设计原则
- forum 全文搜 cloud / hosted / managed / headless / without-agent,**没有任何"云端 Executa"功能或先例**

## 4. 三个方案(权衡)

| 方案 | 纯云 | 对话驱动 | 单 Anna | 代价 |
|---|---|---|---|---|
| **A. 官方架构**(bundle 驱动 + Anna 只读顾问) | ✅ | ❌(用户手动点按钮) | ✅ | 放弃对话驱动 |
| **B. Executa 回归**(focus-flow 模式) | ❌(需 Matrix Agent) | ✅ | ✅ | 用户装 Agent,破纯云 |
| **C. P1-v2**(bundle 内 Anna 对话) | ✅ | ✅ | ❌(双 Anna) | 平台 Anna + bundle Anna 冲突 |

## 5. 给官方的请求(platform-side changes)

官方在论坛 #84 承诺过(line 8683):

> "we really want Truman World on Anna, and we'll be hands-on in getting it there — design review before submission, debugging during the hackathon, and **platform-side changes where the sim genuinely needs them** (sampling budgets, state limits, longer-horizon execution — all on the table)."

World Director 当前卡在以下三点,**任一平台升级即可打破三难**,请求优先级:

1. **云端 Executa 托管** —— 平台直接跑 Executa 代码,用户零本地依赖。最彻底,彻底解决"纯云 + 自定义代码执行"。
2. **平台 Anna 写 storage 能力** —— 让 host LLM(对话智能体)工具集含 `anna.storage.set`;我们即可实现"Anna 写指令 → bundle 轮询执行"。
3. **chat.read_history 出 stub + 推送** —— bundle 能监听平台对话(模式 C push),无需轮询。

## 6. 官方依据(论坛行号)

- **forum #84**(Truman World 移植讨论,Hunter 回复):
  - Q8(8614):one invoke per tick,内部 per-agent loop,≤8 sampling calls
  - Q9(8622):"**drive the loop from the bundle, not the plugin**" — no cron,plugin work 不 survive beyond invoke
  - 8620:`agent.session` for the **director chat layer**(叙事/建议),tick 用 invoke 保持确定性
  - 8654:最接近样板 = **Focus Flow**(bundle panel + bundled Python executa + KV + chat 次要)
  - 8683:"platform-side changes where the sim genuinely needs them"
- forum:3078 —— `chat.read_history` / `write_message` 是 Phase-3 stub
- forum:3074 —— dispatcher 只 gate `manifest.ui.host_api.<namespace>`(bundle 专用)
- forum:8310 —— "Anna combines local execution with cloud intelligence"
- forum:9188 —— 官方拒绝 "fully local mode"(但未提任何 "fully cloud executa")
- forum:9194-9233 —— Agent offline 全断(本地 Executa 铁证)
- forum:1306 —— binary 由 Agent download + install 到本地

---

## 附:当前已落地(P1-v2,0.2.2)

作为权宜,bundle 内嵌了一个"导演 Anna"(`anna.llm.complete` 驱动,非平台主对话 Anna):用户在 bundle 内对话 → Anna 叙事 + JSON actions → bundle tick → 显示。

- ✅ 纯云 + 对话驱动
- ❌ 双 Anna 冲突(bundle Anna vs 平台主对话 Anna)
- ❌ 平台主对话 Anna 被晾成只读顾问

这是三难下的折中。要彻底解决,需第 5 节的平台升级。
