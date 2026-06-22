# Truman Director

> 观察并记录一座迷你 AI 小镇的自然演化，必要时亲自下场导演。

**Truman Director** 是一个 experience 类型的 [Anna App](https://anna.ai)：一个由 LLM
驱动、基于 tick 的小镇模拟器。用户在 Anna 聊天里打开它，观看少数几位居民生活、互动、演化，
也可以在两个 tick 之间以「导演」身份往世界里投放事件。

核心设计准则只有一条：**模型是唯一的决策者。** 这里没有规则引擎，没有行为树，没有任何启发式。
每个 tick 上每一位智能体的动作，都由宿主 LLM 通过采样（sampling）产出。插件本身只负责推进时钟、
把世界快照交给模型、再原样执行模型返回的事件。

## 仓库内容

一个 Anna App 由三部分组成，本仓库三者俱全：

| 部分 | 文件 | 职责 |
| --- | --- | --- |
| **App 清单** | `manifest.json` | Anna App 元数据（slug、分类、绑定的 executa） |
| **App 配置** | `app.json` | 权限、system prompt 附加说明、UI 视图规格 |
| **Bundle** | `bundle/` | 静态单窗口界面（网格地图 + 时间线 + 导演面板） |
| **Executa** | `src/truman_director/` | Python stdio 工具插件 —— 推进世界、持久化状态 |

Executa 是唯一的真相来源；bundle 只负责渲染它。

## 架构

插件刻意保持**扁平**：一个包、七个模块、零子包。

```
src/truman_director/
├── __init__.py      # 版本号
├── plugin.py        # stdio JSON-RPC 主循环 + 唯一的 `world` 工具分发器
├── engine.py        # 唯一的 LLM 调用点：decide() + tick() + inject
├── state.py         # WorldState 数据模型 —— 单一真相来源
├── scenarios.py     # 世界构建器（cafe_town）
├── storage.py       # APS KV 持久化（反向 RPC）
└── errors.py        # TrumanError 错误体系
```

依赖图（无环、无跨文件间接耦合）：

```
plugin ──▶ engine ──▶ {state, storage}
       ──▶ scenarios ─▶ {state, errors}
       ──▶ {state, storage, errors}
```

### 单一 `world` 工具

只有一个工具，通过 `action` 区分行为：

| action | 效果 |
| --- | --- |
| `init` | 构建一个场景，初始化各地点的居住者，持久化，并作为当前运行保留 |
| `tick` | 推进 N 个 tick：时钟 → 快照 → 决策（LLM）→ 应用事件 → 持久化 |
| `inject_event` | 入队一个导演事件，在下一个 tick 触发 |

### 线程模型

复刻 `executa_sdk` storage-notebook 参考实现：

- asyncio 事件循环跑在**主线程**。
- 一个**守护线程**逐行读取 stdin。
- 宿主的 `invoke` 请求通过 `asyncio.run_coroutine_threadsafe` 调度到循环上。
- *我们发起的*反向 RPC 调用（sampling、storage）的响应，经由 `make_response_router`
  路由回去，永远不会落到方法分发器上。
- stdin 关闭时，读取线程会解除 `_main()` 的阻塞，让进程干净退出。

## 开发

需要 [uv](https://docs.astral.sh/uv/) 与 Python 3.12+。

```bash
uv sync                 # 安装依赖（executa-sdk 是本地路径依赖）
uv run truman-director  # 启动 stdio 插件（stderr 打印 "ready"）
```

### 测试、格式化、lint

```bash
uv run pytest -q        # 41 个测试，asyncio_mode=auto
uv run ruff format .    # 格式化
uv run ruff check .     # lint（E/F/W/I/N/UP/B/SIM/RUF/ASYNC）
```

### Pre-commit 钩子

`.pre-commit-config.yaml` 配置了四个钩子：

| 钩子 | 阶段 | 作用 |
| --- | --- | --- |
| `ruff-format` | pre-commit | 格式化暂存的 Python 文件 |
| `ruff-check` | pre-commit | lint + 自动修复 |
| `pytest` | pre-commit | 跑测试套件 |
| `conventional-pre-commit` | commit-msg | 强制 `type(scope): subject` 提交格式 |

同时安装 pre-commit 与 commit-msg 钩子（commit-msg 需要显式 flag，**默认不会**装上）：

```bash
uv run pre-commit install                            # pre-commit 钩子
uv run pre-commit install --hook-type commit-msg    # commit-msg 钩子
```

提交信息必须符合 Conventional Commits，例如：

```
feat(plugin): add inject_event action
fix(engine): drain pending injections before deciding
docs(readme): document threading model
```

允许的 type：`feat fix docs style refactor perf test build ci chore revert`。

## 设计原则

- **模型是唯一的决策者** —— 没有启发式，没有行为树。LLM 返回结构化事件，引擎原样执行。
- **一个工具，一个分发器** —— `world` 靠 `action` 区分。没有注册表，没有 bind/ctx 间接层。
- **不做静默 fallback** —— sampling/storage 失败会以 JSON-RPC 错误响应抛出，而不是降级到某个默认值。响亮的失败胜过安静的出错。
- **单一真相来源** —— `WorldState` 是唯一可变的世界模型；其余要么是它的纯函数，要么是架在它之上的传输层。
- **不玩并发花样** —— 没有 etag 乐观锁、没有事件上限、没有阶段门控、没有 dev-mode 后门。

## 路线图

- [x] work/rest 决策落地为真实状态（`Agent.current_activity`，地图与时间线可见）。
- [x] 进程重启后从 APS KV 自动恢复世界（`load()` 接通，无需重新 init）。
- [ ] 铸造正式的 `tool_id`，并通过 `anna-app dev` 跑通整个 App 的端到端流程。
- [ ] 在 `cafe_town` 之外补充更多场景。
- [ ] 更丰富的 bundle 渲染（关系、智能体对话）。

## 许可证

MIT。
