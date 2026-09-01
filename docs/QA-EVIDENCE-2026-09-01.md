# Marketplace QA Evidence — 2026-09-01

> 本文记录本地 release-candidate 证据，不代表 Anna Marketplace 已批准。平台当前仍在审核 v0.4.3 冻结快照。

## 1. 可复跑命令

```powershell
uv run python scripts/review_acceptance.py
uv run pytest -q tests/test_marketplace_review.py
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
pnpm exec anna-app validate
```

浏览器 smoke 使用独立 harness：

```powershell
pnpm exec anna-app dev --port 5181 --executa dir=.
```

## 2. 协议 acceptance 结果

`scripts/review_acceptance.py` 启动真实 Python stdio 插件，以确定性模型响应服务 sampling 反向 RPC，并让两个插件进程共享同一 APS-like KV。

```text
TC-01 PASS — current town and resident dossier are readable
TC-02 PASS — autonomous interaction changed Alice↔Bob relationship state
TC-03 PASS — town-wide event entered the shared world and persisted
TC-04 PASS — individual intervention is attributed to Alice and visible downstream
TC-05 PASS — consequences survived plugin restart and evolution continued
SECURITY PASS — invalid events fail loudly; markup remains inert event data
```

## 3. TC-04 — 定向居民干预

输入：

```json
{
  "action": "inject_event",
  "event": {
    "agent_id": "alice",
    "action": "world_change",
    "reason": "爱丽丝意外获得500元机会基金，这笔钱将影响她和咖啡馆接下来的决定。",
    "importance": 0.95
  }
}
```

真实 harness 结果：

- 注入 ack：事件在下一 tick 生效。
- 持久事件：`event_type=world_change`、`actor_agent_id=alice`、`importance=0.95`。
- 真实 LLM 同 tick 后续动作：Alice `move → loc_cafe`。
- 模型理由：`刚刮彩票中了500块,兴奋地想去咖啡馆张罗请大家喝一杯庆祝`。
- Alice 居民档案的“近事”同时显示导演事件和模型后续动作。

这证明定向事件不仅写入时间线，也进入同 tick 模型上下文并产生可见下游变化。

## 4. TC-05 — 持续后果与重启恢复

Acceptance runner 执行：

1. 初始化世界并建立 Alice↔Bob 关系。
2. 注入 Alice 的 500 元机会事件。
3. 连续推进多个 tick。
4. 保存 `run_id`、关系 familiarity 和事件历史。
5. 正常关闭插件进程。
6. 启动新插件进程，并复用同一 KV 快照。
7. `get_agent alice` 恢复原 run、关系值和定向事件。
8. 再推进一个 tick，`current_tick` 继续增长。

单元测试同时覆盖 `WorldState.snapshot()` → `from_snapshot()` → 继续 tick。

## 5. Security

### 5.1 无效导演事件

新增 `InvalidEventSpecError`（JSON-RPC `-32006`），拒绝：

- 未知 action，例如 `teleport`；
- move 到不存在的地点；
- talk 到不存在的居民；
- 不存在的 `agent_id`；
- 空 reason；
- 非法 importance。

浏览器实测 `teleport` 返回：

```text
[-32006] event.action must be one of ['move', 'rest', 'talk', 'work', 'world_change'], got 'teleport'
```

### 5.2 动态文本 XSS

输入：

```html
<img src=x onerror="window.__qa_xss=1"> SECURITY_MARKER
```

真实浏览器 DOM 检查：

```json
{
  "executed": null,
  "injectedImages": 0,
  "markerText": true,
  "timecode": "第 1 天 · 08:10 · t002"
}
```

结论：payload 作为纯文本显示，未创建攻击图片，未执行事件处理器。

## 6. 本地截图

截图位于仓库外：`../review/evidence-2026-09-01/`。

- `01-empty-stage.png` — frontend 可访问、host scopes 和空舞台。
- `02-town-initialized.png` — 世界初始化、地点和居民渲染。
- `03-targeted-intervention.png` — Alice 档案显示 500 元定向事件及下游动作。
- `04-security-inert-markup.png` — 恶意 HTML 以纯文本显示。

这些图片带 harness 与 RPC log，适合作为 QA 技术证据；不应直接用作 Marketplace 商品截图。

正式 Marketplace 候选图位于 `../review/marketplace-screenshots-current/clean/`，由 Anna CLI developer harness + OpenCLI 驱动生成，再按 App iframe 的实际像素边界确定性裁切；原始 OpenCLI 截图保存在其上级目录。当前包含空舞台、第一幕、镇景、定向干预、持续演化、英文界面和日终故事 7 张。

## 7. 尚未完成

- 在真实 Matrix Agent + APS backend 上复跑重启恢复。
- 生成不带 harness/RPC 外框的新版 Marketplace 图片。
- 按 GLM / MiniMax / DeepSeek 原矩阵复测 BYOK，并在论坛 topic 256 回帖。
- 等平台结束 v0.4.3 `pending_review` 后，以新版本提交上述证据。
