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

浏览器 smoke 已整理为可复现脚本：

```powershell
pwsh -File scripts/review_smoke_opencli.ps1 -Port 5181
```

脚本按以下顺序执行：

1. 检查 `pnpm`、`opencli` 和目标端口，并运行 `opencli doctor`。
2. 启动 `anna-app dev --executa dir=.`，等待 harness 监听。
3. 通过 `window.__truman` 审核钩子初始化小镇，选择戏剧开场并等待 3 个真实 LLM tick。
4. 从 UI 注入导演事件，再推进 1 tick，断言事件出现在字幕中。
5. 打开居民档案、切换英文 UI，断言英文时间码生效。
6. 输出带 harness 的技术证据、960×880 干净截图、`result.json`、stdout/stderr 日志。
7. 默认关闭 OpenCLI lease 并终止本次启动的 harness 进程树。

默认输出目录：`../review/opencli-smoke-<timestamp>/`。常用参数：

```powershell
# 自定义事件、开场（0～2）和居民
pwsh -File scripts/review_smoke_opencli.ps1 `
  -OpeningIndex 1 `
  -InjectedEvent "暴雨突然来临，咖啡馆成为临时避雨点。" `
  -ResidentId alice

# 调试失败：保留 harness 与浏览器
pwsh -File scripts/review_smoke_opencli.ps1 -KeepHarness -KeepBrowser

# 使用确定性 LLM fixture（路径相对仓库根；如已有 fixture）
pwsh -File scripts/review_smoke_opencli.ps1 -MockLlmFixture path/to/fixture.jsonl
```

该脚本只覆盖本地 developer harness，不修改 Anna 账号默认 Agent、线上 working draft 或审核状态。
Developer Console 的“安装测试”仍需使用已登录的 Anna 页面单独验证；当前平台的 qualified app ref
解析和 bundled Executa 自动部署问题也应独立留证，不能被 harness 通过所替代。

2026-09-01 在 Windows + 真实 LLM 模式完整实跑通过：`lost_grinder` 开场推进到 t3，暴雨事件在
t4 生效，居民档案与英文时间码正常，生成 5 张截图，`rpcErrors=0`；退出后 5181 端口已释放。

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

- 发布 v0.4.5 ExecutaVersion，并在真实 Windows Matrix Agent 验证安装、`world init`、1 tick 与 APS backend。
- 将新版 Marketplace 图片追加到 v0.4.5 版本 Release，sync-meta 回读后再决定旧 screenshots Release 的删除时间。
- 按 GLM / MiniMax / DeepSeek 原矩阵复测 BYOK，并在论坛 topic 256 回帖。
- cut App v0.4.5，并确认现有 `pending_review` 的候选指针已更新到 v0.4.5。
