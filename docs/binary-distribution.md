# Binary distribution(local-executa 分支)

> 本分支(local-executa)的 `truman-director` Executa 以**平台特定的 PyInstaller 二进制**分发:Anna Agent 按用户 OS/arch 下载对应包,解压后作为 stdio JSON-RPC 子进程 spawn。依据 forum topic 140(Don't Just Run Locally)+ topic 78(distribution profile 模型)。

## 本地打包(单平台)

```bash
bash scripts/package_binary.sh     # → dist-anna/<tool_id>-<platform>.tar.gz
```

PyInstaller 不能交叉编译,只打**当前主机**的平台。输出归档内:`bin/<tool_id>` + `manifest.json`(entrypoint = `bin/<tool_id>`),约 24 MB 单文件。已本地验证:打出的二进制响应 stdio `describe` 返回完整 MANIFEST。

打包入口是 `src/_entry.py`(绝对 import shim)——plugin.py 是包内模块(相对 import),直接当 PyInstaller 入口会丢包上下文;shim 让 module graph 从绝对 import 生根,`--collect-submodules truman_director executa_sdk` + `--collect-data truman_director`(收 `prompts.yaml`)确保不漏。

## 全平台构建(CI)

```bash
git tag truman-director-v0.4.5     # version = executa.json#version
git push origin truman-director-v0.4.5
```

`.github/workflows/release-binary.yml` 在 `darwin-arm64` / `darwin-x86_64` / `linux-x86_64` / `windows-x86_64` 四个 runner 上各跑一次 `package_binary.sh`。release job 会先验证四个归档都存在，且包含正确的 `bin/<tool_id>[.exe]` 与 `manifest.json`，然后生成四个 `.sha256` 并统一挂到同一个 GitHub Release。任何平台缺失都会阻止 release job。

> workflow 同时 checkout `anna-executa-examples` 到 app 旁边,因为 `executa-sdk` 是本地路径依赖(`../anna-executa-examples/sdk/python`),干净 runner 上需要它存在。若从自己的 fork 发布,改 workflow 里那个 `repository:`。

## 在平台配置

`binary_urls` 必须在 `anna-app executa publish` **之前**写进 `executa.json#distribution.profiles.binary.binary_urls`。Release URL 是确定的，可以在 tag 创建前按目标版本填写；等 CI 生成资产后逐个验证 URL，再执行 publish。publish 会把当时的四平台映射冻结进不可变 ExecutaVersion，之后修改 Executa Hub 当前记录不会反向修补旧快照。

```json
"linux-x86_64": {
    "url": "https://github.com/<owner>/<repo>/releases/download/truman-director-v0.4.5/<tool_id>-linux-x86_64.tar.gz",
  "sha256": "...",
  "size": 23967421,
  "entrypoint": "bin/<tool_id>",
  "format": "tar.gz"
}
```

四个平台都要声明：`darwin-arm64`、`darwin-x86_64`、`linux-x86_64`、`windows-x86_64`；Windows entrypoint 必须带 `.exe`。`local` profile 继续保留作 dev，发布时 `active` 使用 `binary`。

冻结后的硬门禁：在真实 Windows Agent 上从 Executa Hub 安装该版本并成功调用 `describe`/`world init`。如果安装 API 报 `No binary available for platform 'windows-x86_64'`，说明 immutable snapshot 不完整；此时禁止 `apps cut`，必须修正后发布新的 Executa patch 版本。

## 前提与代价

- **Matrix Agent 必须在线**:Agent 下载二进制并 spawn,离线则 Executa 不可达。这是本地版相对纯云版的体验代价(见 CLAUDE.md 分支上下文 + `docs/question.md` 方案 B)。
- **发布顺序**:`apps push`(上传 working draft)→ `executa publish`(冻结四平台 ExecutaVersion)→ Windows Agent 安装/调用验证 → `apps cut <version>`(锁定已验证的 ExecutaVersion)→ submit-review + release。
