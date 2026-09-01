# 发布流程(World Director / Local)

实战沉淀:v0.4.3 提交审核被拒一次,定位 manifest host_api 根因后修复,cut v0.4.3 重新提审(2026-08)。下面的步骤按本次实际跑通过的顺序整理。

## 0. 发布前自检

| 项 | 命令 | 通过条件 |
|---|---|---|
| manifest 校验 | `pnpm exec anna-app validate` | `validate passed` |
| 格式 / lint | `uv run ruff format --check . && uv run ruff check .` | 全部通过 |
| 单元测试 | `uv run pytest -q` | 全绿 |
| 协议 E2E | `MOCK=1 uv run python scripts/local_e2e.py` | init → tick → 跨午夜 narrate → get_story 全链路通过 |
| harness smoke | `pnpm exec anna-app dev --executa dir=.` 起 harness,在 iframe 里完成开镇 / 注入 / 3 tick / 中英切换 | 不再报 APP_QUOTA_EXCEEDED / agent.session.auto / 502；工具与真实 LLM 均有成功返回 |
| 截图齐备 | 见 §3 | 至少 4 张(空舞台 / 居民点亮 / 章节卡 / 日终故事)|

> 真机截图脚本化的好处是排障「前端不可用」时,可一眼看出到底是 bundle 坏了还是 harness 坏了。本次就是只动 manifest + harness 就能跑通,排除了「前端 broken」的嫌疑。

## 1. 引擎二进制 → GitHub Release

引擎任何改动(纯云版/本地 Executa 切换/算法调整)必须走二进制;bundle 改动则不需要。

```bash
# 1. 同步版本号(四处必对齐)
uv lock
sed -i 's/"version": "0\.4\.X"/"version": "0.4.X+1"/' executa.json app.json
sed -i 's/__version__ = "0\.4\.X"/__version__ = "0.4.X+1"/' src/truman_director/__init__.py
sed -i 's/^version = "0\.4\.X"/version = "0.4.X+1"/' pyproject.toml

# 2. 推 tag,触发 Actions 四平台构建
git tag truman-director-v0.4.X+1
git push origin truman-director-v0.4.X+1

# 3. 等 Actions 完成(darwin-arm64/x86_64, linux-x86_64, windows-x86_64)
gh run watch <run-id> --exit-status

# 4. 验证 4 tar.gz + 4 sha256 已挂到 Release
gh release view truman-director-v0.4.X+1 --json assets --jq '.assets[] | .name'

# 5. 更新 executa.json 的 binary_urls(批量替换 v0.4.X tag 为 v0.4.X+1)
sed -i 's|releases/download/truman-director-v0\.4\.X/|releases/download/truman-director-v0.4.X+1/|g' executa.json

# 6. 提交 binary_urls 更新
git add executa.json && git commit -m "chore(executa): binary_urls → v0.4.X+1 Release"
git push
```

Release 资产本身就是公网 URL(`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`)——**Marketplace 截图也走这个机制**(见 §3)。

## 2. App bundle + manifest → Anna Platform

注意:**`host_api` 在 schema 0.10.0 必须是嵌套对象,不是顶层数组**——这是审核被拒的两个 Needs Fix 的根因。

正确形态(片段):

```jsonc
"ui": {
  "host_api": {
    "storage": ["get", "set", "list", "delete"],
    "tools":   ["required:bundled:truman-director"],
    "chat":    ["append_artifact"],
    "llm":     ["complete"],
    "window":  ["set_title"],
    "agent":   {
      // bundle SDK 默认会静默续 token (session.refresh),
      // 平台需要这个 opt-in,否则 Permission 保存失败,
      // QA harness 整个 App 启动失败。
      "session": { "auto": true },
      "tools":   []
    }
  },
  "csp_overrides": { ... }
}
```

反例(早期版本踩过):

```jsonc
"host_api": [
  "tools.invoke", "storage.read", "storage.write",
  "chat.append_artifact", "llm.complete", "window.set_title"
]
```

→ QA 阶段报「Save failed: manifest does not declare agent.session.auto」,并连锁导致 App frontend / Tools 全部「could not be opened」。

发布步骤:

```bash
# 1. 推工作草稿(manifest + bundle)
pnpm exec anna-app apps push

# 2. ⚠️ 必须单独推 executa 版本(apps push 是 no-freeze,cut 时会报
#    "Version X.Y.Z already published with different content")
pnpm exec anna-app executa publish

# 3. 冻结 App 版本(锁 executa 依赖)
pnpm exec anna-app apps cut 0.4.X+1 --changelog "<简明变更说明>"

# 4. 若是 archived 状态(我们的 case):先 unarchive 再 submit-review
pnpm exec anna-app apps unarchive anna-truman-director-local --yes
pnpm exec anna-app apps submit-review

# 5. 审核通过后,跑一条上架命令
pnpm exec anna-app apps release 0.4.X+1
```

## 3. Marketplace 列表字段

`@anna-ai/cli` 0.1.49 已支持从 `app.json` 同步列表字段。把 `homepage_url`、`support_url`、`privacy_url`、`cover_url` 和 `screenshots` 写入 git，然后执行：

```bash
pnpm exec anna-app apps sync-meta --dry-run --json
pnpm exec anna-app apps sync-meta --json
```

dry-run 必须先确认 app_id、slug 和全部 URL 正确。Developer Console 表单只作为 CLI PATCH 失败时的回退路径。

| 字段 | 我们的填法 | 备注 |
|---|---|---|
| homepage_url | `https://github.com/<owner>/<repo>` | |
| support_url | `https://github.com/<owner>/<repo>/issues` | |
| privacy_url | `https://github.com/<owner>/<repo>/blob/main/docs/PRIVACY.md` | docs/PRIVACY.md 必须在仓库里有 |
| cover_url | 一个截图URL | |
| 截图 URL | 一行一个 | |

### 截图发到公网的最快路径:GitHub Release

```bash
gh release create <screenshots-tag> \
  shot1.png shot2.png shot3.png shot4.png \
  --title "App Screenshots — v0.4.X+1" --notes-file notes.md

# 注意:GitHub 对同名资产重复上传会自动加 default. 前缀,
# URL 仍然有效,但 Marketplace 截图里文件名会带 default.
# 第一次上传就用正确文件名即可。
```

URL 形态:`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`

### Developer Console 回退

旧的 `/developer?app=82&tab=basic` 路由已在 2026-09 重定向；优先使用上面的 `apps sync-meta`。如果新版 Console 重新提供表单，字段名仍是 `homepage_url`(不是 home_url)、`cover_url`、`screenshots`。

```bash
opencli browser truman tab new "https://anna.partners/developer?app=82&tab=basic"
# 用 eval 注入值,触发 input/change 事件让 React 状态机识别
# 然后 click 保存按钮,等待 "Saved." toast
```

### 当前截图工作区

- OpenCLI 原图（含 harness 外框）：`../review/marketplace-screenshots-current/*.png`
- Marketplace 干净候选图：`../review/marketplace-screenshots-current/clean/*.png`
- 建议 cover：`02-first-act.png`
- 建议首批截图：`03-town-overview.png`、`06-english-view.png`、`07-day-story.png`
- `04-targeted-intervention.png` / `05-continued-evolution.png` 保留为 QA 证据；本次真实模型把“获得 500 元”误写成“输了 500 元”，不要直接上传为商品图，应用稳定 fixture 重拍

## 4. 常见陷阱与排障

| 症状 | 根因 | 解决 |
|---|---|---|
| `apps cut` 报 `Version X.Y.Z already published with different content` | `apps push` 对 bundled executa 是 no-freeze | 先跑 `executa publish` 显式冻结工具版本 |
| `apps release` 报 `app status is archived` | App 在归档状态 | `apps unarchive <slug> --yes` |
| `apps release` 报 `app status is draft` | App 从未过审 | `apps submit-review` |
| `apps submit-review` 报 `App 状态不允许提交审核: pending_review` | 上一轮审核未结束 | **必须等审核员走完一轮**(reject/approve),平台不允许覆盖提交 |
| Developer Console 报 `Save failed: manifest does not declare agent.session.auto` | manifest host_api 写法错误(数组而非嵌套对象),缺 agent.session.auto: true | 见 §2 |
| `desc:` 时 dev harness 跑一会挂 / `Object has no member 'ref'` | bundle SDK 在 harness 进程里调 agent.session.refresh 被拒 | 修了上面之后正常 |
| BYOK 探针:开关 ON 时 500,OFF 时正常 JSON 错误 | 平台 app/complete 路径的 BYOK 转发 bug(2026-08 实测,3 家供应商 × 含/不含思考模型 × 开关两态全 500) | 官方论坛 2026-08-27 确认修复于 `v1.1.0-beta.144`；升级后重跑原矩阵并在 topic 256 回帖确认 |

## 5. 检查清单(checklist)

每次发布过一遍:

- [ ] `pnpm exec anna-app validate` 通过
- [ ] `uv run ruff format --check . && uv run ruff check .` 通过
- [ ] `uv run pytest -q` 全绿
- [ ] Windows 默认环境（不依赖手动 `PYTHONUTF8=1`）下 mock E2E 通过
- [ ] `manifest.json#ui.host_api` 是嵌套对象,含 `agent.session.auto: true`
- [ ] 版本号四处对齐(executa.json / app.json / pyproject.toml / __init__.py)
- [ ] `executa.json#binary_urls` 指向最新 tag
- [ ] GitHub Release 4 tar.gz + 4 sha256 齐全
- [ ] Developer Console「基本信息」表单已填 homepage/support/privacy/cover/screenshot URL
- [ ] `docs/PRIVACY.md` 在仓库里
- [ ] 按 `docs/REVIEW-FEEDBACK.md` 跑完 TC-01～TC-05，并保存工具输入、工具输出和前端结果证据
- [ ] `uv run python scripts/review_acceptance.py` 输出 TC-01～TC-05 + Security 全 PASS
- [ ] 安全复核完成：动态文本转义、CSP、权限最小化、无密钥入库
- [ ] `apps push` + `executa publish` + `apps cut <version>` 顺序正确
- [ ] `apps submit-review` 已发(或等上轮结束)

## 6. 历史审核反馈

2026-08-19 的 v0.3.3 Marketplace 审核把问题分成五类：App frontend 不可访问、Tools 不可执行、Permission 无法保存、产品页/截图缺失，以及 TC-01～TC-05 与安全检查无法验证。逐项闭环状态、证据和剩余缺口统一维护在 [`REVIEW-FEEDBACK.md`](REVIEW-FEEDBACK.md)，不要再从旧邮件草稿推断当前状态。

## 7. 当前进度(2026-09-01)

- v0.4.3 已 cut(version_id=521,锁定 executable v0.4.2)
- 平台状态仍为 `pending_review`；线上 latest 是 v0.3.3，不能用当前 `main` 覆盖审核快照
- 仓库已提交:`fix(manifest): host_api 嵌套对象 + agent.session.auto: true` (38a3435),`docs: PRIVACY.md + ignore` (af9ae25)
- Developer Console「基本信息」表单已保存(homepage/support/privacy/cover/screenshot URL 全部填好)
- v0.4.4 源码已提交并推送；tag `truman-director-v0.4.4` 的四平台 binary + SHA256 Release 已成功
- `executa.json#binary_urls` 已切换到 v0.4.4 Release
- 截图 Release `truman-director-screenshots-v0.4.4` 已发布 4 张 PNG；app 82 的 cover/homepage/support/privacy/screenshots 已 PATCH 并 GET 回读确认
- 2026-09-01 本地验证：90 tests、Ruff、manifest、Windows UTF-8 mock E2E 全绿；harness 完成真实 LLM 开镇、事件注入、定向居民事件、XSS inert-markup、3 tick 与中英切换
- TC-01～TC-05 + Security 本地证据已补齐
- 下一步：`apps push` → `executa publish` → `apps cut 0.4.4`；等 v0.4.3 审核结束后再 `submit-review`
