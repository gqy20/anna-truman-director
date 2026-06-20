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
git tag truman-director-v0.3.0     # version = executa.json#version
git push origin truman-director-v0.3.0
```

`.github/workflows/release-binary.yml` 在 `darwin-arm64` / `darwin-x86_64` / `linux-x86_64` 三 runner 矩阵上各跑一次 `package_binary.sh`,把每个 `.tar.gz` + `.sha256` 挂到 GitHub Release。

> workflow 同时 checkout `anna-executa-examples` 到 app 旁边,因为 `executa-sdk` 是本地路径依赖(`../anna-executa-examples/sdk/python`),干净 runner 上需要它存在。若从自己的 fork 发布,改 workflow 里那个 `repository:`。

## 在平台配置

`binary_urls` **不**写进 `executa.json`(forum topic 140:推荐在平台 UI 配)。把打包脚本打印的每个平台条目贴进 Anna 平台 Tool 配置页(Multi-platform Binary URLs):

```json
"linux-x86_64": {
  "url": "https://github.com/<owner>/<repo>/releases/download/truman-director-v0.3.0/<tool_id>-linux-x86_64.tar.gz",
  "sha256": "...",
  "size": 23967421,
  "entrypoint": "bin/<tool_id>",
  "format": "tar.gz"
}
```

然后把 Tool 的 distribution 切到 Binary(`local` profile 留作 dev;topic 78 允许两者并排,flip `active`)。

## 前提与代价

- **Matrix Agent 必须在线**:Agent 下载二进制并 spawn,离线则 Executa 不可达。这是本地版相对纯云版的体验代价(见 CLAUDE.md 分支上下文 + `docs/question.md` 方案 B)。
- **发布三阶段**:`apps push`(注册 bundled Tool + 上传 bundle draft)→ `apps cut <version>`(冻 immutable)→ submit-review + publish。
