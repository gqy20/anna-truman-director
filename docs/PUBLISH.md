# 发布流程(World Director / Local)

实战沉淀:v0.4.3 提交审核被拒一次,定位 manifest host_api 根因后修复,cut v0.4.3 重新提审(2026-08)。下面的步骤按本次实际跑通过的顺序整理。

## 0. 发布前自检

| 项 | 命令 | 通过条件 |
|---|---|---|
| manifest 校验 | `pnpm exec anna-app validate` | `validate passed` |
| 格式 / lint | `uv run ruff format --check . && uv run ruff check .` | 全部通过 |
| 单元测试 | `uv run pytest -q` | 全绿 |
| 协议 E2E | `MOCK=1 uv run python scripts/local_e2e.py` | init → tick → 跨午夜 narrate → get_story 全链路通过 |
| harness smoke | `pwsh -File scripts/review_smoke_opencli.ps1` | 自动完成开镇 / 戏剧开场 3 tick / 注入后 1 tick / 居民档案 / 中英切换；`result.json` 为 PASS，RPC 无 error/failed |
| 截图齐备 | 见 §3 | 至少 4 张(空舞台 / 居民点亮 / 章节卡 / 日终故事)|

> 真机截图脚本化的好处是排障「前端不可用」时,可一眼看出到底是 bundle 坏了还是 harness 坏了。本次就是只动 manifest + harness 就能跑通,排除了「前端 broken」的嫌疑。

## 1. 引擎二进制 → GitHub Release

引擎任何改动(纯云版/本地 Executa 切换/算法调整)必须走二进制;bundle 改动则不需要。

```bash
# 1. 同步版本号(四处必对齐),并提前把 binary_artifacts.path 改为
#    dist-release/v0.4.X+1/<tool_id>-<platform>.tar.gz。
uv lock
sed -i 's/"version": "0\.4\.X"/"version": "0.4.X+1"/' executa.json app.json
sed -i 's/__version__ = "0\.4\.X"/__version__ = "0.4.X+1"/' src/truman_director/__init__.py
sed -i 's/^version = "0\.4\.X"/version = "0.4.X+1"/' pyproject.toml
sed -i 's|dist-release/v0\.4\.X/|dist-release/v0.4.X+1/|g' executa.json

# 2. 提交并推送上述版本/URL变更,再从同一 commit 打 tag。
git add app.json executa.json pyproject.toml uv.lock src/truman_director/__init__.py
git commit -m "chore(release): prepare v0.4.X+1"
git push
git tag truman-director-v0.4.X+1
git push origin truman-director-v0.4.X+1

# 3. 等 Actions 完成。release job 自带四平台完整性/entrypoint 门禁。
gh run watch <run-id> --exit-status

# 4. 再从 GitHub API 验证 4 tar.gz + 4 sha256 已挂到同一个 Release。
gh release view truman-director-v0.4.X+1 --json assets --jq '.assets[] | .name'

# 5. 下载四个归档到 executa.json 声明的本地路径，并让 CLI 校验上传计划。
mkdir -p dist-release/v0.4.X+1
gh release download truman-director-v0.4.X+1 \
  --pattern 'tool-*.tar.gz' --dir dist-release/v0.4.X+1
pnpm exec anna-app executa upload-binaries --dry-run --json
# 必须看到四个平台；Windows entrypoint 必须带 .exe。此时仍不要 cut App。
```

Release 资产本身就是公网 URL(`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`)。从下一版开始，**Executa binaries、SHA256 和 Marketplace screenshots 共用同一个版本 Release**，但截图只在 binary workflow 完成后追加，见 §3。

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

# 2. 直传四个平台并冻结 ExecutaVersion。此刻本地四个 artifact 必须存在。
pnpm exec anna-app executa publish

# 3. 硬门禁:回读版本,并在真实 Windows Agent 上安装+调用。
pnpm exec anna-app executa status tool-qingyu_ge-anna-truman-director-sxah66uc
pnpm exec anna-app executa versions tool-qingyu_ge-anna-truman-director-sxah66uc
# Executa Hub → My Tools → Truman Director → Install
# 然后 Developer Console 安装 working draft,完成开镇 + 1 tick。
# 若 deploy_status!=ready / executa_not_deployed / No binary available,立即停止。

# 4. 只有 Windows 真机门禁通过后,才冻结 App 版本并锁 ExecutaVersion。
pnpm exec anna-app apps cut 0.4.X+1 --changelog "<简明变更说明>"

# 5. 若是 archived 状态:先 unarchive 再 submit-review
pnpm exec anna-app apps unarchive anna-truman-director-local --yes
pnpm exec anna-app apps submit-review

# 6. 审核通过后,跑一条上架命令
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

### Marketplace Screenshots Release 的作用与保留规则

GitHub Release 在这里充当**稳定的公网静态文件托管**。Anna Marketplace 保存的是 `cover_url` / `screenshots[]` URL，不会把 PNG 复制进平台；所以只要元数据仍引用某个 Release Asset，那个 Release 就是线上依赖，不能删除。

当前 `Marketplace Screenshots — v0.4.4` (`truman-director-screenshots-v0.4.4`) 仍被 app 82 的线上平台元数据和正在进行的 v0.4.4 审核引用；v0.4.5 工作树虽已准备迁移 URL，但在新资产上传并执行 `sync-meta` 前尚未生效。**现在删除仍会导致线上封面和四张截图全部 404**。

从 v0.4.5 起不再单独创建 screenshots Release。等 binary workflow 完成后，把干净截图追加到同一个版本 Release：

```bash
gh release upload truman-director-v0.4.X+1 \
  02-first-act.png 03-town-overview.png 06-english-view.png 07-day-story.png

# 更新 app.json 中 cover/screenshots 为这个 tag 的 URL,再同步平台元数据。
pnpm exec anna-app apps sync-meta --dry-run --json
pnpm exec anna-app apps sync-meta --json
```

URL 形态仍是:`https://github.com/<owner>/<repo>/releases/download/<tag>/<file>`。

旧 screenshots Release 的删除条件（缺一不可）：

1. 新截图已上传到新的版本 Release，四个 URL 均返回 200；
2. `app.json` 已改为新 URL并提交；
3. `apps sync-meta --json` 成功，Developer Console/平台 API 回读不再出现旧 tag；
4. 新审核候选已指向新版本，最好等新版本批准/上架后再删旧 Release。

满足后才可执行：

```bash
gh release delete truman-director-screenshots-v0.4.4 --cleanup-tag --yes
```

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
| `apps submit-review` 报 `App 状态不允许提交审核: pending_review` | 上一轮审核未结束 | 不要重复 submit。2026-09-01 实测：在 pending_review 下成功 cut 新版本后，服务器自动把现有审核指针更新到新 cut；必须用 `apps status` 回读确认 |
| Developer Console 报 `Save failed: manifest does not declare agent.session.auto` | manifest host_api 写法错误(数组而非嵌套对象),缺 agent.session.auto: true | 见 §2 |
| `desc:` 时 dev harness 跑一会挂 / `Object has no member 'ref'` | bundle SDK 在 harness 进程里调 agent.session.refresh 被拒 | 修了上面之后正常 |
| Windows Agent 安装报 `No binary available for platform 'windows-x86_64'` | immutable ExecutaVersion 冻结时没有 Windows map；当前 Executa 记录后来补齐也不会修旧快照 | 禁止 App cut/release；补齐四平台后发布新的 Executa patch 版本，Windows 真机安装通过再 cut App |
| `binary_urls` 当前记录有四平台，但 frozen version 只剩 macOS ARM + Linux | 平台 pull-mirror 冻结路径丢失 Intel macOS/Windows（v0.4.4、首次 v0.4.5 均复现） | 改用 `binary_artifacts`，下载 GitHub Release 四归档后由 CLI 直传；坏快照若未被 AppVersion 引用可 yank 后重建 |
| Executa Hub Install 明明默认 Local 却请求 Cloud Agent | 页面 `window.defaultAgentClientId` 为空时错误回退 `agents[0]` | 从 Network 核对 `/agents/<client_id>/plugins/reinstall` 的目标；平台修复前不要把按钮提示当成部署成功证据 |
| BYOK 探针:开关 ON 时 500,OFF 时正常 JSON 错误 | 平台 app/complete 路径的 BYOK 转发 bug(2026-08 实测,3 家供应商 × 含/不含思考模型 × 开关两态全 500) | 官方论坛 2026-08-27 确认修复于 `v1.1.0-beta.144`；升级后重跑原矩阵并在 topic 256 回帖确认 |

## 5. 检查清单(checklist)

每次发布过一遍:

- [ ] `pnpm exec anna-app validate` 通过
- [ ] `uv run ruff format --check . && uv run ruff check .` 通过
- [ ] `uv run pytest -q` 全绿
- [ ] Windows 默认环境（不依赖手动 `PYTHONUTF8=1`）下 mock E2E 通过
- [ ] `pwsh -File scripts/review_smoke_opencli.ps1` 真实 LLM smoke 输出 PASS、5 张截图且 `rpcErrors=0`
- [ ] `manifest.json#ui.host_api` 是嵌套对象,含 `agent.session.auto: true`
- [ ] 版本号四处对齐(executa.json / app.json / pyproject.toml / __init__.py)
- [ ] `executa.json#binary_artifacts` 声明四个平台，`dist-release/v<version>/` 四归档已下载
- [ ] `executa upload-binaries --dry-run --json` 显示四个平台和正确 Windows `.exe` entrypoint
- [ ] GitHub Release 4 tar.gz + 4 sha256 齐全
- [ ] 冻结后的 ExecutaVersion 已在真实 Windows Agent 安装成功（不能只检查当前 Executa 记录）
- [ ] Developer working draft 的 `deploy_status=ready`，开镇 + 1 tick 不报 `executa_not_deployed`
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

- 历史 v0.4.3 已 cut(version_id=521,锁定 executable v0.4.2)
- v0.4.4 已 cut(version_id=623)，冻结 executa_version=427(v0.4.4)
- 平台状态仍为 `pending_review`，但 `in review` 已由服务器自动更新为 v0.4.4；线上 latest 仍是 v0.3.3
- 仓库已提交:`fix(manifest): host_api 嵌套对象 + agent.session.auto: true` (38a3435),`docs: PRIVACY.md + ignore` (af9ae25)
- Developer Console「基本信息」表单已保存(homepage/support/privacy/cover/screenshot URL 全部填好)
- v0.4.4 源码已提交并推送；tag `truman-director-v0.4.4` 的四平台 binary + SHA256 Release 已成功
- `executa.json#binary_urls` 已切换到 v0.4.4 Release
- 截图 Release `truman-director-screenshots-v0.4.4` 已发布 4 张 PNG；app 82 的 cover/homepage/support/privacy/screenshots 已 PATCH 并 GET 回读确认
- 2026-09-01 本地验证：90 tests、Ruff、manifest、Windows UTF-8 mock E2E 全绿；harness 完成真实 LLM 开镇、事件注入、定向居民事件、XSS inert-markup、3 tick 与中英切换
- TC-01～TC-05 + Security 本地证据已补齐
- `apps push` 已更新 working draft rev 6；`executa publish` 与 `apps cut 0.4.4` 均成功
- 2026-09-01 真机复核发现 v0.4.4 immutable ExecutaVersion 在 Windows 安装时报 `No binary available for platform 'windows-x86_64'`，尽管当前 Executa 记录和 GitHub Release 已有四平台；working draft 因此 `deploy_status=degraded` / `executa_not_deployed`
- Executa Hub Install 还存在默认 Local 却请求 Cloud Agent 的前端选路 bug；Network 证据显示请求落到 Cloud client_id
- 下一步：发布 v0.4.5 Executa（四平台先写入并冻结）→ Windows 真机安装/调用 → 再 cut App v0.4.5。v0.4.4 不得 release
