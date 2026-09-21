# 发布流程(World Director / Local)

> 当前证据以 [RELEASE-STATUS.md](RELEASE-STATUS.md) 为准。本文维护操作流程，不把历史草稿、GitHub Release 或已提审写成正式上架。

> **2026-09-21 流程纠正（优先于本文较早的安装门禁表述）**：本地及实际Agent运行验证、冻结绑定与bundle核验通过后，应推进submit-review。开发者owner install选旧latest，不单独作为无限期阻止提审的条件；需如实保留安装与测试边界。官方submit-review会对最新cut执行预检并固定审核候选，审核方按候选安装。App0.4.10已通过提交预检并进入pending_review，绑定Executa0.4.9。只有APPROVED/PUBLISHED才执行正式release；提审成功不等于上架成功。
>
> 顺序：四平台构建 → apps push → executa publish → 回读冻结快照 → apps cut → 安装目标 cut 并验收 → submit-review → 审核批准 → release。cut 用于生成安装引用，不代表通过运行门禁。门禁失败时停止提审/上架。

## 0. 发布前自检

### CLI 与工具协议清单

项目 CLI 固定为 `@anna-ai/cli@0.1.53`，使用 `pnpm install --frozen-lockfile` 安装。
0.1.49 不在发布时同步工具 `manifest_cache`；0.1.51 支持该同步，但默认寻找
`executa.json` 同目录的 `manifest.json`。本项目该文件是 **App 清单**，不可用于工具。
因此 `executa.json.manifest_file` 显式指向独立的 `executa-manifest.json`。

工具清单从插件的 `MANIFEST`（即 `describe` 返回值）生成，禁止手动维护第二份协议：

```bash
uv run python scripts/export_executa_manifest.py
uv run python scripts/export_executa_manifest.py --check
pnpm exec anna-app executa publish --dry-run --json
```

每次修改工具版本、参数或能力声明后重新生成并提交工具清单；单元测试检查其与
`describe` 一致。归档里的 `manifest.json` 是二进制启动清单，也不能替代它。
正式同步后回读工具详情，确认 `manifest_cache.version`、`tools` 和
`host_capabilities` 与目标版本一致。CLI 升级与本地校验通过不等于平台缓存已更新，
更不等于 `scope=tool` 的 `owner_id` 403 已解决；仍须原 App 真机验证。

> **2026-09-07 describe 兼容性修复**：v0.4.5 的十个工具参数缺少 `description`，已安装 Anna Agent 的 `ParameterSchema.from_dict` 会抛出 `KeyError('description')`，外层可能只显示 `describe returned no manifest`。源码现已补齐描述，协议测试和二进制打包检查均要求参数描述非空。仅收到 describe JSON 不等于宿主解析通过；还需验证官方解析器、真实 Agent 注册及 App init/tick。该修复不代表平台旧版本安装问题已解决，也不会改变已冻结的 v0.4.5；正式分发必须构建新版本。

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

仅修改 App bundle/说明时，可独立增加 App 版本并复用已冻结的 Executa；例如 App0.4.9固定依赖Executa0.4.8。以下四处版本同步和新二进制构建适用于同时发布引擎的版本，不应为了App-only cut改写旧工具版本。

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
# 必须看到四个平台；Windows entrypoint 必须带 .exe。先发布并核对 Executa 冻结快照，再 cut App。
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

# 3. 回读冻结快照，确认四平台齐全。
pnpm exec anna-app executa status tool-qingyu_ge-anna-truman-director-sxah66uc
pnpm exec anna-app executa versions tool-qingyu_ge-anna-truman-director-sxah66uc
# 4. 冻结 App 版本并锁定已核对的 ExecutaVersion；cut 不是提审/上架。
pnpm exec anna-app apps cut 0.4.X+1 --changelog "<简明变更说明>"

# 安装后回读实际 App/Executa 版本，完成 Windows 真机开镇 + tick。
# Developer Install 若仍选旧版，或 deploy_status!=ready，则停止提审。
# working draft 与 immutable cut 不是同一个版本，不能混用测试结论。

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

当前 `app.json` 的封面与截图引用 `truman-director-v0.4.5`。版本号不同不等于截图失效；只要画面仍准确可以继续使用。清理前必须回读线上元数据和审核候选引用，本地配置不能证明旧资产已无引用。

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
| 审核期间 cut 后候选仍为旧版 | cut 与审核候选是独立指针 | 2026-09-20 官方文档 §2 说明：cut 不自动移动候选；需要切换到已验收的新 cut 时显式 submit-review，然后回读候选。同候选重复提交为幂等操作，预检失败保留原候选；服务器行为不符时记录错误并停止，不套用 9 月 1 日旧经验 |
| Developer Console 报 `Save failed: manifest does not declare agent.session.auto` | manifest host_api 写法错误(数组而非嵌套对象),缺 agent.session.auto: true | 见 §2 |
| `desc:` 时 dev harness 跑一会挂 / `Object has no member 'ref'` | bundle SDK 在 harness 进程里调 agent.session.refresh 被拒 | 修了上面之后正常 |
| Windows Agent 安装报 `No binary available for platform 'windows-x86_64'` | immutable ExecutaVersion 冻结时没有 Windows map；当前 Executa 记录后来补齐也不会修旧快照 | 补齐四平台后发布新的 Executa patch，回读快照后 cut，安装目标 cut 验证；失败时禁止提审/release |
| `binary_urls` 当前记录有四平台，但 frozen version 只剩 macOS ARM + Linux | 平台 pull-mirror 冻结路径丢失 Intel macOS/Windows（v0.4.4、首次 v0.4.5 均复现） | 改用 `binary_artifacts`，下载 GitHub Release 四归档后由 CLI 直传；坏快照若未被 AppVersion 引用可 yank 后重建 |
| Executa Hub Install 明明默认 Local 却请求 Cloud Agent | 页面 `window.defaultAgentClientId` 为空时错误回退 `agents[0]` | 从 Network 核对 `/agents/<client_id>/plugins/reinstall` 的目标；平台修复前不要把按钮提示当成部署成功证据 |
| BYOK 探针:开关 ON 时 500,OFF 时正常 JSON 错误 | 平台 app/complete 路径的 BYOK 转发 bug(2026-08 实测,3 家供应商 × 含/不含思考模型 × 开关两态全 500) | 官方论坛 2026-08-27 确认修复于 `v1.1.0-beta.144`；升级后重跑原矩阵并在 topic 256 回帖确认 |

## 5. 检查清单(checklist)

每次发布过一遍:

- [ ] `pnpm exec anna-app validate` 通过
- [ ] `uv run ruff format --check . && uv run ruff check .` 通过
- [ ] `uv run pytest -q` 全绿
- [ ] `pnpm test:frontend` 通过
- [ ] Windows 默认环境（不依赖手动 `PYTHONUTF8=1`）下 mock E2E 通过
- [ ] `pwsh -File scripts/review_smoke_opencli.ps1` 真实 LLM smoke 输出 PASS、5 张截图且 `rpcErrors=0`
- [ ] `manifest.json#ui.host_api` 是嵌套对象,含 `agent.session.auto: true`
- [ ] 引擎发布时四处版本对齐；App-only cut时记录独立App版本和明确的Executa冻结版本，不重写未改动的引擎版本
- [ ] `executa.json#binary_artifacts` 声明四个平台，`dist-release/v<version>/` 四归档已下载
- [ ] `executa upload-binaries --dry-run --json` 显示四个平台和正确 Windows `.exe` entrypoint
- [ ] GitHub Release 4 tar.gz + 4 sha256 齐全
- [ ] 冻结后的 ExecutaVersion 已在真实 Windows Agent 安装成功（不能只检查当前 Executa 记录）
- [ ] 安装实际目标 immutable cut，回读 AppVersion、ExecutaVersion、Agent ID/类型/版本及部署 ready；开镇 + tick 成功。working draft 不能替代 cut 验收
- [ ] Windows Local 与审核 Cloud 环境分别记录结果；未支持环境明确写入产品说明及审核说明
- [ ] Developer Console「基本信息」表单已填 homepage/support/privacy/cover/screenshot URL
- [ ] `docs/PRIVACY.md` 在仓库里
- [ ] 按 `docs/REVIEW-FEEDBACK.md` 跑完 TC-01～TC-05，并保存工具输入、工具输出和前端结果证据
- [ ] `uv run python scripts/review_acceptance.py` 输出 TC-01～TC-05 + Security 全 PASS
- [ ] 安全复核完成：动态文本转义、CSP、权限最小化、无密钥入库
- [ ] `apps push` + `executa publish` + `apps cut <version>` 顺序正确
- [ ] `apps submit-review` 后回读审核候选；pending_review 下若要切换到已验收的新 cut，显式重新提交并确认候选变化
- [ ] 审核批准后对同一已验收版本执行 release，并回读 Marketplace 最新版本

## 6. 历史审核反馈

2026-08-19 的 v0.3.3 Marketplace 审核把问题分成五类：App frontend 不可访问、Tools 不可执行、Permission 无法保存、产品页/截图缺失，以及 TC-01～TC-05 与安全检查无法验证。历史逐项证据保存在 [`REVIEW-FEEDBACK.md`](REVIEW-FEEDBACK.md)，当前阻塞与剩余门禁见 [`RELEASE-STATUS.md`](RELEASE-STATUS.md)，不要从旧邮件草稿推断当前状态。

## 7. 当前状态与审核环境

见 [RELEASE-STATUS.md](RELEASE-STATUS.md)。旧版本安装故障仅作历史依据，不代表今天的平台状态。

2026-09-20 回读的 [官方发布文档](https://anna.partners/developers/apps/app-publish.md) §2 明确支持 pending_review 下切换候选，§4 限定 APPROVED/PUBLISHED 才能发布；同页状态概览仍含“不允许重复提交”等相冲突旧描述。操作以详细规则为依据并回读服务器结果，不能把文档更新当成本项目已验收。
[版本文档](https://anna.partners/developers/apps/app-versioning.md) 未提供任意历史版本的公开安装入口。目前控制台只有草稿安装和旧 latest 安装可见；目标 cut 的受支持验收入口须向平台确认，不能用 release 绕过审核，也不能以 working draft 测试替代 cut 验收。

## 8. 真实存储验收

0.4.6 真机开镇暴露 `forbidden_scope`：插件不能使用 App 存储范围。
后续补丁使用工具范围持久化和 `get_snapshot` 前端读取；不得覆盖已冻结 0.4.6。
发布前必须验证：空存储展示开镇 → init → get_snapshot → 真模型 tick → 关闭重开恢复同一快照；
还需检查权限拒绝明确显示错误。单元测试和 MOCK E2E 不能替代该平台验证。

## 9. 发布前环境版本核对

- `pnpm exec anna-app --version` 与项目 package.json/lockfile 一致；`npm view @anna-ai/cli version dist-tags --json` 查询官方版本。
- 全局 `anna-app --version` 可能不同；发布统一使用项目 `pnpm exec`。401 必须先恢复登录，升级 CLI 不会刷新 PAT。
- 本机 Agent 的磁盘版本、运行进程版本和平台心跳版本分别记录；从 [官方页面](https://anna.partners/download) 查询同平台正式下载版本。平台 beta 号与 Agent beta 号是两套版本。
- Cloud Agent 是独立环境，升级本机 Agent 不会升级审核方 Cloud Agent。记录其实际版本/平台/依赖冻结版本/安装错误，不能根据本机版本推断。
- CI 将 SDK 固定到确定提交，构建依赖见 `scripts/binary-requirements.txt`（来自 v0.4.8 成功构建）。本地 SDK checkout 必须与 CI 一致；这些约束不意味着不同 OS runner 的产物逐字节一致。
- [官方审核流程](https://forum.anna.partners/t/app-review-timeline-process/318) 要求完整核心流程及所支持 Agent 环境自测。重新提审会进入新的审核周期，不以频繁提交替代验收。
