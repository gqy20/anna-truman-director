# 发布状态与环境核对

最后核对：2026-09-20。这里区分线上回读、历史记录和待验证事项。
发布步骤仅维护在 [PUBLISH.md](PUBLISH.md)，历史功能证据见 [REVIEW-FEEDBACK.md](REVIEW-FEEDBACK.md)。

## 当前结论

GitHub代码基线为 v0.4.8（7b68e4e），本次工作树修正尚未提交到Git。9月20日已将App修正push到工作草稿r11并cut为App0.4.9（835），未提审或正式上架；冻结工具仍为未改动的0.4.8（478）。
GitHub 四平台资产完整不等于 Marketplace 上架完成。

| 项目 | 证据与边界 |
| --- | --- |
| GitHub | 9 月 20 日 API 确认 main 为 7b68e4e；v0.4.8 有四平台归档及 SHA256，构建 run 34798269907 成功 |
| 提审 | 9 月 14 日本地台账记录 v0.4.8 pending_review；不是今天的后台回读 |
| Windows Local | 9 月 14 日记录 Agent 安装/加载 Executa 0.4.8；不替代当前候选完整 E2E |
| 最新审核 | 9 月 16 日 Anna Dev 邮件：前端可打开，Cloud Agent 开镇报目标 Executa 未部署。未提供实际 App/Executa 版本 |
| 平台实时状态 | 9 月 20 日重新授权后 CLI 回读：status=rejected，is_published=false，review_candidate_version=null；latest_version 仍为 v0.3.3 (327) |
| App / Executa v0.4.8 | AppVersion 758 存在，published_at=null、is_latest=false；ExecutaVersion 478 存在，工具本体 is_published=true，但 in_published_app=false。列表回读尚不证明 App 758 的具体冻结映射 |
| 正式上架 | 尚无审核批准、release 成功和用户侧安装验收证据 |

原始邮件仅保存在仓库外 mail/anna/inbox-4129.eml；不把私人邮件纳入 git。

## 工具链核对

| 组件 | 本次发现 | 处理 |
| --- | --- | --- |
| 项目 CLI | 0.1.52；npm latest 为 0.1.53 | 升级到精确 0.1.53，并更新 pnpm lockfile |
| 全局 CLI | 0.1.52 | 同步升级到 0.1.53；发布仍用 pnpm exec |
| Windows Agent | PATH 中旧 Anna.exe 为 1.1.0-beta.35 | 已独立安装并启动官方 beta.39，文件/运行进程/平台心跳三者核对一致；旧 PATH 安装保留，直接运行旧路径仍会启动 beta.35。Cloud #580 为 beta.39 在线 |
| 平台 | 官方 9 月 18 日公告覆盖 beta.160–166 | 平台版本与 Agent 版本独立，不能混用；公告不证明某次请求命中的服务器版本 |
| SDK | 本地源码 81bc6a5b35a4154bb1481cc7857d8df2d586f46f，Python 包号 0.1.0 | CI 固定相同提交，不能仅以包号判定源码一致 |
| 打包依赖 | v0.4.8 CI 实装 PyInstaller 6.22.3 / hooks 2026.7 / PyYAML 6.0.3 | 固定这三个直接构建依赖，完整依赖树和 runner 仍不是完全锁定 |

来源：[npm](https://www.npmjs.com/package/@anna-ai/cli)、
[Agent 官方下载](https://anna.partners/download)、
[9 月 18 日官方更新](https://forum.anna.partners/t/327)、
[成功构建](https://github.com/gqy20/anna-truman-director/actions/runs/34798269907)。
CLI 0.1.53 官方声明为兼容升级；最新公告包含 Cloud 唤醒、权限保存、invoke 数据截断修复，
但没有证明本项目 9 月 16 日的部署错误已解决。

## 本次修正

- 开镇和初始连接的工具未部署错误提供中英文操作指引，保留原始诊断；失败信封保留错误 code/message。
- 修正 dev 启动器对 pnpm 透传 `--` 的处理。
- 修正 README 配置职责、工具 action 列表，删除产品描述中“纯云版在 main”的失实说明。
- 统一流程为冻结工具 → cut → 安装目标 cut 验收 → 提审 → 批准 → release。
- 同步审核证据边界和环境核对要求，旧截图仍引用 v0.4.5，不删除被引用资产。

## 剩余门禁

1. Anna 登录已恢复，app 82 当前 rejected、无审核候选；继续核对 AppVersion 758 的实际冻结依赖和目标 Agent 部署，不从两个版本号相同推断绑定关系。
2. 本机 Agent beta.39 已启动并核对心跳；本机和 Cloud 均被同一旧冻结引用阻塞，需修复引用后分别验收。
3. 在审核目标 Agent 上安装**同一 immutable cut**，记录实际 AppVersion、ExecutaVersion、tool_id、Agent ID、deploy_status/install_error。确认 Linux 资产不等于部署成功。
4. 在目标 cut 上验证 init、连续 tick、事件干预、真实 APS 保存、关闭重开恢复，以及 TC-01～TC-05 / Security。
5. 本次 bundle/manifest 的修改需要新 App cut 才会进入审核；正式发布前确定新版本并运行版本门禁，不覆盖已冻结 v0.4.8。是否重建 Executa 由引擎/SDK/二进制内容变更决定。
6. 草稿安装、旧 pin、更新 confirm 卡死和 dev-aps 注册问题尚无新的关闭证据。BYOK 原 provider 矩阵/论坛沟通闭环仍待完成。

本地单测、lint、schema 校验和模拟宿主测试只能证明对应本地行为，不能替代以上平台门禁。

## 本次本地验证

- Python：112 tests passed；Ruff lint / format 检查通过。
- 前端：2 项 Node 回归测试通过，覆盖两种语言、字符串/结构化失败信封和正常结果解包。
- CLI 0.1.53：manifest validate 通过；lockfile 的离线 frozen 安装通过。
- 发布脚本：Bash 语法检查、四平台 workflow YAML 解析通过。本次没有运行四平台构建或平台 E2E。

## 登录恢复记录（2026-09-20）

浏览器确认 Device authorized，官方 CLI 登录函数确认凭证已保存（约 90 天），后续 apps status/versions、executa status/versions 均成功。
原始 CLI 遇一次网络错误即退出；本次使用系统现有代理，并仅在临时进程中给官方登录函数增加网络失败重试，未修改 CLI 安装、未在项目保存凭证。
该阶段仅恢复登录和查询；后续安装/权限修正记录见文末。未重新提审、release 或修改默认 Agent。

## Cloud 部署初次只读核对（2026-09-20，后续结果见下节）

- 当前安装为 `0.0.0-draft`，部署 degraded，目标工具 unavailable；部署错误记录指向 v0.3.0 Linux 归档，本次 HEAD 确认404。
- Cloud beta.39 在线，但目标工具 install_status=failed、agent_loaded=false、agent_running=false；元数据 version=0.4.8 不能代表 Agent 已加载0.4.8。
- 当前 Executa 元数据的 v0.4.8 Linux CDN 对象 HEAD=200（23092705字节），四平台可见；这不是冻结版本映射或运行测试。
- 权限检查 satisfied=false，缺项 `Truman Director · Sampling`，尚未修改授权。
- 控制台保留历史 `0.0.0-draft` (#200，6月创建/发布)，目前显示与 r10 同样的清单；应核对其旧冻结引用。App758 的精确冻结 ExecutaVersion 映射在本次可用只读接口/UI中未暴露。
- 当前控制台主列表安装按钮仍为 v0.3.3；没有据此安装旧版或通过 Publish 绕过验收。

直接部署失败证据已找到，历史引用是重点调查方向；未发起新安装，旧错误记录不证明当前重新安装必然复现。原始核对记录在仓库外 `mail/2026-09-20-cloud-deployment-audit.md`。这是作者自己的 Cloud 环境，不能冒充审核团队日志。

## Cloud 修正与重新验证（2026-09-20）

用户要求继续修正后，明确指定自己的 Cloud Agent 执行重装，结果确认旧冻结引用仍在生效：

- `POST /api/v1/agents/agent_624becf6cf414ff5a46953a1021efcb7/plugins/reinstall`，body 仅含 `user_executa_id=11978`。
- 09:55:50 UTC 返回失败：`resolved_from=frozen_snapshot`、`resolved_version=0.1.1`、`executa_version_id=119`、`pinned_by_app=anna-truman-director-local@0.0.0-draft`。
- 该快照下载 v0.3.0 Linux GitHub 归档，返回404。当前工具元数据0.4.8并未决定实际部署版本。
- 执行官方 `POST /api/v1/developer/apps/82/working/install` 返回 success=true、installed_version=0.0.0-draft，但 deployment=null；随后重装仍在09:57:46 UTC返回完全相同旧 pin。草稿重装没有修复引用。
- 已最小化修正目标工具的 `custom_config.sampling_grant.enabled=true`，保留其他配置。PUT 返回200；权限回读 `satisfied=true`、`missing=[]`。原有 `llm_grant.complete` 不能代替 Sampling 授权。
- 权限修正后 Cloud 仍在线，但工具 `install_status=failed`、`agent_loaded=false`、`agent_running=false`。尚不能运行 init/tick/APS恢复验收。

尚未取得 App758 的精确冻结映射或受支持的目标 cut 安装入口。下一步需平台确认草稿旧 pin 的迁移/修复方法，以及未发布 cut 的测试方式；不删除世界数据或旧版本，不以发布绕过安装问题。
平台跟进草稿在仓库外 `mail/2026-09-20-cloud-pin-followup-draft.md`，尚未发送。本地代码修改仍未提交/推送，未提审/发布。

## Windows Agent 升级及独立复现（2026-09-20）

- 官方下载 API `/api/v1/downloads/latest` 返回 Windows production beta.39，归档131467641字节；本地 SHA-256 与官方一致：`526dfafc39af6b45f3abe9d1ab5cc70ef34c3d5b806c0ccbbf63ad2a318d2b75`。
- 新安装位于 `~/.local/share/anna-versions/1.1.0-beta.39/Anna/Anna.exe`；旧版及其共享 `_internal` 未覆盖。已从新路径启动，沿用原账号配置。
- `/api/v1/agents` 回读本机 `agent_e5dccaa14b884f7098a9b8ca1143a61b`：is_online=true、is_cloud=false、Windows/AMD64、metadata.version=1.1.0-beta.39，last_seen_at=2026-09-20T12:57:32.338841Z。
- 12:58:43 UTC 指定此 Windows Agent 重装目标工具，返回 `No binary available for platform 'windows-x86_64'`，可用平台仅darwin-arm64、linux-x86_64。解析仍为 frozen_snapshot / v0.1.1 / ExecutaVersion119 / pinned_by_app=anna-truman-director-local@0.0.0-draft。
- 这次是本机独立重装证据，不是误读共用 Cloud install_error。升级 Agent 没有解除服务端旧 pin。原始响应保存在仓库外 `mail/2026-09-20-local-agent-reinstall.json`。
- 本轮开始时项目 node_modules 缺失，已使用现有 lockfile 执行 `pnpm install --frozen-lockfile`，恢复CLI0.1.53，无依赖版本变更。

## 官方 QA 复核后的下一步修正（2026-09-20）

[官方对本项目的回复](https://forum.anna.partners/t/280/2) 已给出 cut→Developer Console安装cut→目标Agent重装的路径，无须先正式上架。[9月20日官方新答复](https://forum.anna.partners/t/326/2)进一步说明Console安装只登记账号关系，工具需显式部署，且部署遵循已安装App的pin。

因此不能断言只能等待平台修复。我们已显式部署，但账号安装仍为旧草稿；下一项是核对普通自安装的版本选择及历史草稿安装引用，验证能否切换到目标cut。9月14日本地台账曾记录移除草稿安装/重建UE后运行到0.4.8，需核对具体步骤及数据保留后才可复用；那次记录仍不能替代当前Cloud和目标cut验收。

其他开发者在[同日后续回复](https://forum.anna.partners/t/326/3)也报告显式重装后疑似仍运行旧代码，尚未见官方最终根因；不可推断所有其他项目发布正常。完整来源与证据边界见仓库外 `mail/2026-09-20-official-release-qa-findings.md`。

## 新 cut 与安装实验（2026-09-20）

用户要求cut新版本并测试，已执行：

- App版本升为0.4.9，manifest依赖明确固定Executa0.4.8（min_version同为0.4.8）。引擎源码未变，复用已冻结版本，不新增引擎发布。
- schema校验、前端2项测试通过。官方CLI命令入口在Windows/Node24.16.0退出时触发UV_HANDLE_CLOSING断言；改用安装包导出的官方runAppsPush/runAppsCut函数，未修改CLI安装。
- push成功：工作草稿r11，5文件61611字节，bundle ready；cut成功：AppVersion835/v0.4.9，明确冻结到ExecutaVersion478/v0.4.8，bundle791。原始结果在仓库外mail/2026-09-20-v049-push.json及v049-cut.json。
- 按官方建议POST `/developer/apps/82/install`返回success=true，但installed_version=0.3.3、deployment=null；随后权限接口再次确认安装为0.3.3。普通自安装并未选中新cut。
- 已通过working/install恢复测试前的0.0.0-draft安装模式，权限仍satisfied=true。恢复后的草稿投影对应当前r11，不宣称已安装或验收835。
- 首次Cloud重装请求遇到HTTP524超时；随后发现Cloud已suspended。这次超时不是旧pin复现证据，需唤醒后另行确认。
- 已通过官方Cloud start接口唤醒580，并回读agent_online=true；13:13:18 UTC重新部署得到确定失败：仍解析frozen_snapshot / Executa119 v0.1.1 / pinned_by_app=anna-truman-director-local@0.0.0-draft，下载旧v0.3.0 Linux归档404。证据在mail/2026-09-20-v049-cloud-test.json。新cut没有自动改变账号安装引用或旧草稿pin。

新cut未提审、未release，也未提交/推送Git。尚不能宣布v0.4.9功能验收通过。

## 安装关系隔离实验（2026-09-20，最终状态13:25:58 UTC）

用户要求进一步操作测试后，完成以下对照；未删除任何App定义、AppVersion、ExecutaVersion、Cloud Agent或存储数据。

| 条件 | 同一Cloud580上的实际结果 |
| --- | --- |
| 普通owner install选中App0.3.3，再显式重装 | 二进制安装成功，但loaded=false；不能把success=true当作工具运行成功 |
| 备份世界/权限后，仅移除当前账号App安装关系，再重装同一UE11978 | installed=true、loaded=true、version=0.4.8；状态回读running=true、1个world工具 |
| 恢复working draft安装后再次显式重装 | 13:25:08 UTC又解析draft→Executa119/v0.1.1，旧Linux地址404 |
| 再移除账号App安装关系、重装工具、恢复draft | 再次加载0.4.8成功；最终draft已安装、Cloud工具0.4.8正在运行 |

结论：当前Linux二进制能够在Cloud加载，App安装关系的pin是可重复的控制变量；历史版本数量不是已证实原因。解除账号安装关系可临时绕过，但恢复draft后重装仍会选旧pin，不能视为平台问题永久修复，也不证明App835已安装。

数据保护：世界快照和权限备份在用户目录 `.local/share/anna-test-backups/`，没有保存到应用仓库。结束时逐项回读确认：世界value与ETag均未变，App grants和工具custom_config均与备份一致，permissions.satisfied=true。恢复阶段尝试PATCH全部历史dev grants被400拒绝（未声明image）；随后回读证实working/install已恢复相同dev defaults，无需扩大manifest授权。

证据：仓库外mail中的 `2026-09-20-install-selection-experiment.json`、`2026-09-20-no-app-pin-deploy.json`、`2026-09-20-restored-draft-reinstall.json`、`2026-09-20-install-experiment-final-state.json`。

尚未执行init/tick或世界写入。浏览器Anna登录已过期，已打开并保留登录页面；后续可在恢复登录后验证当前草稿UI与Cloud0.4.8的临时组合，但仍不能冒充immutable App0.4.9验收。不要在该临时状态随意执行Repair/reinstall，否则会重新命中旧pin。

## Cloud 实际界面 smoke（2026-09-20，后续测试）

- 浏览器已登录；将默认Agent从本机切到Cloud580，管理页确认Ask/auto选择Cloud。本轮保留Cloud为默认，供继续测试。
- 本轮开始时App82安装记录已不存在（API permissions返回404、installed列表没有82；原因未查明），恢复working/install后列表显示0.0.0-draft、deploy_status=ready、工具available、权限satisfied=true。不能把这个缺失直接归因于平台自动卸载。
- 存在另一款旧同名App60（World Director、打开v0.2.2）。识别后关闭，未操作其开镇或tick；后续使用World Director (Local)，窗口确认App82草稿路径。
- Cloud工具回读loaded=true、running=true、agent_version=0.4.8。当前测试是草稿与0.4.8工具的临时组合，非App835不可变cut。
- 快照读取成功：第1天08:00/t000、三个居民。关闭窗口再打开后恢复同一场景和时间；爱丽丝档案查询成功。
- 界面执行一次tick，返回JSON-RPC -32003、SAMPLING_PROVIDER_ERROR、sampling HTTP502，detail为上游HTML错误页面。重开窗口后再试一次，仍同样失败。没有出现executa_not_deployed。
- 未reset或覆盖现有世界，未进行连续tick、注入或午夜叙事；真实模型推进和写后恢复未通过。模型路由/供应商根因尚未定位，不能仅凭502判定平台或某供应商单方故障。
- 本次结构化结果在仓库外 `mail/2026-09-20-cloud-runtime-smoke.json`；对外记录不保存窗口JWT或认证信息。

## 采样502隔离测试（2026-09-20）

使用官方CLI的dev/session/mint获取App82短期会话，仅在内存使用凭证；直接调用官方 `/api/v1/copilot/app/complete`，不经过Cloud、不读取或发送世界内容。

| 探针 | 结果 |
| --- | --- |
| 默认路由、短文本请求、无response_format | HTTP502，Cloudflare HTML标题anna.partners / Bad gateway |
| 默认路由、相同短提示、json_object | 同样HTTP502 |
| 匿名空POST | 403 Not authenticated |
| 已鉴权空POST | 422，缺少messages字段 |
| GET同一路由 | 405 Method Not Allowed |
| 指定model_hint=byok:minimax/MiniMax-M3 | HTTP502，Ray a3e143758f519913-SJC |
| 指定model_hint=byok:deepseek/deepseek-v4-flash | HTTP502，Ray a3e1438b28e55655-SJC |
| 指定平台模型minimax/minimax-m2.7 | HTTP502，Ray a3e14437f8dc4f1c-SJC |

模型名称来自当前available接口，两个BYOK条目均active且provider verified。没有修改默认模型、BYOK开关或供应商配置。失败响应没有返回实际模型，model_hint是请求提示，不足以证明请求被路由至不同供应商；“verified”也不能代替当下生成健康检查。

结论：合法生成请求在Anna采样执行链路失败，鉴权/参数校验仍可用；Cloud与本地直接调用都能复现，所以不是仅Cloud工具部署或json_schema特有错误。仍无法仅凭502定位Anna内部服务、代理或实际供应商的具体责任；需要平台按Ray和服务器日志定位。未继续反复tick、未改世界数据。证据在mail/2026-09-20-sampling-*.json。

## 采样定位更新：流式接口透出上游额度错误（2026-09-20 13:55 UTC）

这部分更新上一节“根因未定位”的结论，保留原始测试供追溯。

- 官方 CLI 0.1.53 的 server 模块明确使用 `/api/v1/copilot/app/complete/stream`。同一 App82、同种 complete 会话、相同短文本及 max_tokens=512 对照：普通 complete 返回 Cloudflare 502；stream HTTP200，但 SSE 是 `event=error / code=APP_PROVIDER_ERROR`，并未生成成功。
- 流式错误明确透出 `RateLimitError / HTTP429 / rate_limit_error`，消息为“已达到 Token Plan 用量上限：请升级 Token Plan 套餐或购买积分补充用量。 (2056)”。默认请求 Ray `a3e1539fe8d13e8e-SJC`，上游 request_id `06ff18c488f5be409c94e49e8624208b`。
- 流式请求指定 DeepSeek、GLM、平台 MiniMax M2.7 三个 model_hint，仍是相同额度错误，各有独立 request_id。不能据此认定三个供应商均额度耗尽。
- 浏览器 `/llm` 确认主模型 MiniMax-M3，且“App / 插件默认使用我的 API Key”已开启。官方页面明确说明该开关为最高优先级，盖过 App 请求的模型偏好。这解释了 model_hint 对照为何不能证明跨供应商路由。
- MiniMax 提供商的官方“测试”按钮执行后仍显示“已验证”；这种验证不能证明真实生成有剩余额度。未获取或显示完整供应商密钥，未改变主模型、BYOK 开关或专用模型设置。
- 当前最强解释：默认 MiniMax BYOK 生成遭遇 Token Plan 用量限制；普通接口没有提供同样清晰的错误，表现为502。实际 selected model 元数据及普通接口如何转成502仍需服务端日志确认，不应继续表述为“所有 BYOK 又坏了”或“平台全站模型不可用”。
- 官方 Token Plan 页面说明额度受5小时和周窗口控制；当前尚未查询该账户的额度窗口/恢复时间，也未充值。下一步应在用户选择后切换实际主模型做对照，或待原模型额度恢复后重测；只改 model_hint 或重新cut无助于验证。

证据：仓库外 `mail/2026-09-20-sampling-stream-controls.json`、`mail/2026-09-20-sampling-stream-models.json`。未进行新的世界tick或写入，Cloud端到端验收仍未通过。

## DeepSeek 实际主模型对照与 Cloud 写后恢复（2026-09-20 14:01–14:04 UTC）

- 用户继续授权后，将 `/llm` 实际主模型临时切换为 DeepSeek，保留 BYOK 第三方默认开关。普通 complete 立即 HTTP200 / OK，响应明确 `model=byok:deepseek/deepseek-v4-flash`、`provider=byok:deepseek`，共51 tokens，平台quotaConsumed=0。这是实际路由证据，区别于此前无效的model_hint对照。
- 先备份APS完整记录至用户目录 `.local/share/anna-test-backups/app82-before-deepseek-tick.json`。初始APS为t000/08:00。
- 浏览器默认Agent明确为Cloud580，工具状态回读0.4.8、loaded/running均true。连续两次单tick成功生成居民动作；APS最终t004/08:20，ETag变为 `e365fcc5fee55eb19a9d6879f0d3bcdc`，事件包含t3和t4各三个动作。完整刷新Dashboard后窗口恢复同一t004、人物位置及两轮事件，完成真实生成→保存→界面重建读取验证；没有重启Cloud进程。
- **新发现本地缺陷**：首次成功点击从已保存t0跳到t3。与此前两次采样失败对应；engine.tick先对共享world执行advance_tick及排空注入，再await decide，异常没有回滚。因此失败已改变内存却未写APS，下一次成功会把漂移状态保存。代码确认问题位于engine.tick（advance_tick到save区间）和plugin长期缓存_world。此缺陷尚未修复，应增加失败后状态/注入不丢失及重试无跳号的回归测试；日终第二次save的失败语义也应纳入设计。
- 成功范围仅为App82 working draft与临时加载Executa0.4.8，不是不可变App835验收；旧安装pin仍可能在Repair/reinstall时回退。未进行午夜叙事、Cloud冷启动恢复或正式发布。

证据：仓库外 `mail/2026-09-20-deepseek-main-control.json`、`mail/2026-09-20-deepseek-cloud-ticks.json`。世界保留本次测试产生的t004，未reset或回写旧备份。

结束时已恢复原主模型MiniMax-M3，刷新LLM页面确认保存成功，BYOK第三方开关仍开启。恢复后相同短文本流式请求再次返回429/2056（`mail/2026-09-20-minimax-restored-control.json`），形成MiniMax失败→DeepSeek成功→MiniMax失败的对照。因此保留原配置时仍会遇到额度限制；需要继续使用DeepSeek或等原额度恢复。

## tick 失败状态修复（2026-09-21，本地未发布）

- engine.tick 改为每 tick 深拷贝完整运行态，在临时副本完成时钟、注入、模型决策与午夜叙事，一次save成功后才发布内存状态。未使用snapshot往返复制，避免截断完整历史或丢失待执行注入。
- plugin语言切换随tick一起提交，失败保持原语言；午夜不再先保存跨天再请求故事，避免叙事失败后无法补生成。多tick调用保留已成功的前序tick。
- 新增6项回归用例：决策失败、叙事失败、存储拒绝、取消、真实plugin入口连续两次失败后重试不跳号及重建恢复、多tick后续失败保留前序提交。验证包含注入/完整历史/语言保留、午夜只写一次且带故事。
- 验证：全量118项pytest通过；ruff check通过，修改的Python文件已格式化。
- 范围：修复仅在本地源代码；未提交、推送、重建发行二进制或部署Cloud。现有Cloud0.4.8仍含旧缺陷，当前APS的t004未回写修改；App旧pin问题未解决。
- 限制：若APS写入成功但响应丢失，远程结果不确定，当前修复不承诺分布式exactly-once；需要另行设计幂等确认，不能把本地状态隔离当成网络事务保证。
