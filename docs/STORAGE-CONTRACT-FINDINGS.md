# APS owner contract investigation — 2026-09-07

## Official contract

Source: https://anna.partners/developers/tools/executa-storage.md (live Markdown
retrieved 2026-09-07), plus the cloned official Python SDK storage.py and
examples/python/storage-notebook/storage_notebook.py.

- Plugin KV requires v2 negotiation, aps.kv and a user storage grant.
- Documented storage/get parameters are key and scope. The tool-scope examples
  do not supply owner_id. The Python StorageClient.get API exposes no owner arg.
- Tool storage is isolated by user and Executa. User storage is visible to other
  plugins the user grants. A key prefix is namespacing, not access control.
- The runnable official notebook defaults to user scope. It explicitly suggests
  tool scope for a private notebook; it is not an unchanged tool-scope control.

## Observed production behavior

### Original App82 comparison

Read-only inspection of the original developer page confirms latest frozen
version0.4.6 (unpublished), no0.4.7 App version, working revision8, and store
latest0.3.3. Account installation is0.0.0-draft. App82 and App261 both pass the
permissions check and reference Executa1013/UserExecuta10649; permissions API
manifest_cache still says0.4.6, while the live local binary is diagnostic0.4.7.

Opened the already-installed original App82 without reinstalling/updating it.
Verified iframe slug anna-truman-director-local and version0.0.0-draft, window
534d0ccb-083a-41f9-ae0a-d1c0be509d7d. The UI shows STANDBY / Start because its
refresh function still reads via anna.storage.get (App scope), not get_snapshot.
This does not establish that init/tick/save work; none was invoked.

- Original App list_scenarios: success (RPC mtr7qdqw-fgt72ey9).
- Original App get_snapshot against the currently running diagnostic plugin:
  -32029 / HTTP403 / forbidden_scope / scope=tool requires owner_id
  (RPC mtr7qlc7-g7k738hf).

The tool-scope failure therefore reproduces under the original App identity,
not only diagnostic App261. This is a mixed-version diagnostic comparison,
NOT acceptance of an immutable original-App release or its old binary.
No App82 manifest, install version, grants, review state or world data changed.

The installed diagnostic App's get_snapshot reaches the plugin and receives
403 forbidden_scope: scope=tool requires owner_id. The plugin returns the error
to the App. No missing-data fallback is appropriate. list_scenarios succeeds.
The previous shared 92-second dispatch timeout is no longer reproduced by that
successful control; its original cause has not been established.

The CLI storage bridge reproduces the same tool403. Adding owner_id=tool ID or
owner=our numeric Executa ID1013 to a read request did not resolve it. These are
diagnostic probes, not documented fixes. No upstream repositories were changed.

A read of our own new namespaced diagnostic key with scope=user returned
404 not_found instead of403. This demonstrates read authorization, not successful
write/read roundtrip or end-to-end App acceptance. The CLI bridge does not
normalize that404; official Agent documentation says the Agent should do so.

## Resolution boundary

## Additional source verification

The installed beta.34 Agent's Cython source comments reconstruct the relevant
`src/executa/storage.py` path: lines169–178 obtain/refresh the storage token;
lines189–203 select scope and forward the remaining parameters; lines193 and
208–213 send the Bearer token and query/body to Nexus. There is no owner resolver
in this handler. This establishes forwarding behavior, not that adding such a
resolver here would be correct.

Read-only GET probes with our own numeric Executa ID1013 as owner_id also return
the identical403 (in addition to the earlier string-owner and owner probes).
Do not turn these unsuccessful guesses into production parameters.

The latest official documentation commit for this page is
133e1c8b62943557ef6ba10b4fff29af19854ae3 (PR3). Official forum reply248/2 confirms
plugin tokens support tool/user scopes; it does not document an owner_id fix.
The accessible official organization and author repositories expose docs/examples,
not the Nexus storage authorization implementation. No server-source patch can
be verified with the current available source/access.

Required next evidence from the platform: trace RPC mtr3ws2f-n1jbj4il and inspect
the authenticated tool identity -> storage owner resolution. A correct fix must
derive/validate the owner against the authenticated Executa and retain user ×
Executa isolation; it must not trust arbitrary plugin-supplied owner IDs or
relax scope authorization. Exact function/line and patch remain unverified.

Retaining tool isolation requires a corrected platform/Agent ownership contract;
the available public documentation does not specify an additional plugin field.
Do not invent one, expand grants, or silently fall back to user storage.

Using the officially supported user scope is a possible compatibility change,
but requires explicit acceptance of its broader visibility and a new namespaced
key. Existing tool-scope data must be preserved; do not interpret a403 as absence
or silently initialize over inaccessible data. No scope change or migration has
been performed. Regression tests preserve the original error for reads/writes.

## CLI upgrade and live manifest correction (2026-09-07)

Upgraded the project CLI from 0.1.49 to pinned 0.1.51. The latter adds protocol
manifest synchronization. Explicit `executa.json.manifest_file` now points to
`executa-manifest.json`, generated from the plugin's describe result, rather than
the unrelated App `manifest.json`. All 108 tests passed.

On Windows Node 24.16.0, the CLI entrypoint's publish dry-run crashed with
`UV_HANDLE_CLOSING`. Calling the same official `runExecutaPublish` function with
`dryRun:true` and setting `process.exitCode` instead of forcing `process.exit`
completed with code 0. This isolates the observed failure to the entrypoint/exit
path; the underlying Node/libuv cause is not established. No node_modules patch
or runtime protocol fallback was introduced.

Using the official CLI API client, updated ONLY `manifest_cache` on original
Executa 1013 (identity and version checked before mutation). Readback confirmed:

- Tool version remains 0.4.7; manifest cache changed from 0.4.6 to 0.4.7.
- Capabilities are now `aps.kv`, `llm.sample`; old App-scope capabilities removed.
- Tool descriptions now include `get_snapshot`.
- Binary URLs unchanged; binary_source remains `mirror` (not changed here).
- No new ExecutaVersion, App cut, review submission or release was performed.

Original App82 `get_snapshot` still returned -32029 / HTTP403 / forbidden_scope /
`scope=tool requires owner_id`, both in the existing window and after closing and
reopening the original app. New window ID:
`6465818e-f28c-46c8-a48c-889848c16548`; iframe path remains
`/anna-apps/qingyu_ge/anna-truman-director-local/0.0.0-draft/index.html`.
No world writes were made. Thus stale current-tool metadata was real, but fixing
it alone did not resolve storage access. This does not establish that immutable
dependency snapshots or every server-side cache have also been refreshed.

### Original App identity, fresh direct storage token

Subsequent GET `/api/v1/apps/82/permissions` confirms that the original App's
permission view now sees manifest 0.4.7, Executa1013/UserExecuta10649,
`storage_grant.enabled=true`, `allowedScopes=[user,tool]`, `satisfied=true`,
and `missing=[]`. Working revision8 still has top-level host_capabilities=[],
and latest immutable App version remains 0.4.6. Version-list GET responses do
not expose immutable dependency mappings; do not claim those were inspected.

Using the same request shape as official CLI0.1.51 storage bridge, minted a fresh
60-second dev storage token for ORIGINAL slug `anna-truman-director-local`,
the original tool_id and allowed_scopes=[tool]. No harness app was registered.
Selected decoded claims: app_id=82, executa_tool_id matches the original tool,
allowed_scopes=[tool]; owner_id, executa_version_id and version_id absent.
The credential and token were neither logged nor persisted.

Immediately GET `/api/v1/storage/kv?scope=tool&key=truman:run:world` with that
token returned HTTP403, forbidden_scope, `scope=tool requires owner_id`.
This reproduces the same failure without browser window, local Agent, plugin
binary or an explicit frozen-version identifier in the dev request/token.
The absence of owner_id in the token does NOT establish that the documented
contract requires such a claim: the backend may resolve owner from tool identity.
The isolated failing boundary is now fresh storage token issuance/consumption
for the original App/tool identity, not merely an outdated installed binary.
No storage writes, App edits, cut, release or review submission were made.

## 2026-09-11 平台修复后复测（beta.153–159 + CLI 0.1.52）

背景：hunter 周报官宣 beta.154 修复 scope=tool 存储 403（#280），beta.153 增加 install 诊断；CLI 0.1.52 dev harness 加入生产同款 manifest 能力门禁与存储上限门禁。

本轮事实：

1. 协议级真 LLM E2E（`local_e2e.py`，自研 host 替身 + 真 staging sampling）：全链路通过。首跑 narrate 因 MiniMax-M3 think 块输出形状不符 retry_exhausted（与 09-07 记录同签名，模型行为抖动而非稳定阻塞）；二跑 init → 2 ticks → 跨午夜 narrate → get/get_story/snapshot 一致性全部通过。storage.set 全程成功。
2. dev harness（bridge → 真 staging LLM、legacy in-memory 存储）：
   - 新门禁：未声明能力时 init 报 `[-32603] manifest does not declare 'aps.scope.tool.write'`——即周报所称"未注册工具给可操作错误代替神秘 403"。
   - 修复：`manifest.json#host_capabilities` 增加 `aps.scope.tool.read` + `aps.scope.tool.write`，`anna-app validate` 通过。
   - 通过：init（cafe_town, zh）→ pickOpening(lost_grinder) 注入 world_change(0.95) → tick 1–3 真实 LLM 决策、关系熟悉度 0.1→0.15 演化，runtime_state_synced 事件可见完整世界状态；`truman.storage save size=6303B` 成功。
   - **新发现（平台侧 bug）**：同一插件、同一 key、同一 scope，`storage.set` 成功后 `storage.get` 立即返回 `exists:false`（插件取证 `load miss`，UI refresh 拿到 `{"value":null}` 舞台空）。写读命名空间不一致，位于 runtime `anna-app-runtime-local@0.2.0a23`（PyPI 最新即此版）的 legacy in-memory 后端，疑似本 beta 周期生产同款 owner 解析在 dev 路径的回归。SDK（本地 sdk/python，f26d2b5）get/set 参数对称，无嫌疑。
3. 结论：平台侧 403 是否真修好，dev harness 无法回答（其存储是内存替身）；权威复测仍需发布 v0.4.7（含 manifest 能力声明）后在真实 Windows Agent + 真实 APS 上开镇/tick。dev harness 的 tool-scope 读丢失需另行反馈平台（按台账规则，未获用户明确要求前不自动发帖）。

## 2026-09-11 深夜追加：dev 读丢失根因（本地源码级证据）与修复

**根因（已证实，本地源码）**：dev harness legacy 存储后端的 `storage/get` 不返回 `exists` 字段——
`anna_app_core/dispatcher.py::_h_storage_get` 返回裸 `{"value": ...}`（0.9.0/0.18.1/0.20.0 三代一致，
非新回归）；而生产 APS 与 SDK 文档契约是 `{value, etag, exists}`。我们的 `storage.load()` 严格执行
`r.get("exists")`，于是 dev 里**每次读都判 miss**：写成功（set 走 `window.runtime_state` 并发
`runtime_state_synced`）但 bundle `refresh()` 永远拿到 `{"value":null}` → 舞台空。同一 tab 内的
恢复读取其实从项目第一天起就没在 dev 里成功过；此前"重启/新 tab = 空世界"的认知被 session 隔离
现象掩盖了这一层。

**修复（本项目侧，已完成并回归通过）**：`storage.load()` 双形状容错——`exists` 缺失时以
`value is not None` 判命中（快照恒为 dict，非 None 即命中，可靠）。生产契约不变；owner 合约错误
照旧响亮冒泡（test_owner_contract_error… 仍过）。新增
`test_load_tolerates_legacy_dev_backend_without_exists_flag`；109 单测全过，ruff 干净。
回归：legacy harness 开镇 → pickOpening → t003/08:15/3 居民/10 字幕全部渲染，
`save 5454B → load 5454B` 成对命中。

**dev-aps 复测（`node scripts/dev.mjs --storage aps` → 真 `/api/v1/storage/kv`）**：
- beta.154 owner 解析已生效：403 文案从 `scope=tool requires owner_id` 变为可操作错误
  `executa 'dev-anna-truman-director' is not registered — … register a dev profile`。
- 按提示注册：`anna-app executa register --tool-id tool-qingyu_ge-…-sxah66uc --slug dev-anna-truman-director`
  → 平台确认 `✓ registered (app_id=274, kind=executa)`；重启 harness（强制重铸 600s TTL 的
  storage_token）后 owner 解析**仍报 not registered**。dev-registration 兜底疑似未接上 mint 链路，
  平台侧新问题，待反馈。
- 注：`pnpm dev -- --storage aps` 无效——pnpm 未吞 `--`，dev.mjs 原样转发导致旗标被当位置参数；
  正确姿势 `node scripts/dev.mjs --storage aps`（或修 dev.mjs 过滤 "--"）。
- 真实发布链路（已发布 ExecutaVersion + 真实 Agent）不依赖 dev slug 解析，不受此影响。

**遗留**：① 论坛反馈两条（legacy get 缺 `exists` 的契约缺口；dev-aps 注册后仍 403）——草稿待写，
未发布；② `dev-anna-truman-director`(274) 与 `executa-tool-…`(101) 两条 DRAFT 注册记录在平台上，
是否清理待定。
