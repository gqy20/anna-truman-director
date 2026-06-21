#!/usr/bin/env bash
# Pack the truman-director Executa into a platform-specific .tar.gz binary
# distribution that Anna Agent can download + install.
#
# Archive layout follows the forum topic 140 guide's recommended form:
#
#   <tool_id>-<platform>.tar.gz
#   ├── bin/<tool_id>[.exe]   # PyInstaller --onefile 产物
#   └── manifest.json         # runtime.binary.entrypoint.default + permissions
#
# The Agent reads manifest.json to locate the entrypoint (no guessing). The
# multi-platform binary_urls themselves live on the Anna platform Tool config
# page — NOT in executa.json (forum topic 140).
#
# PyInstaller cannot cross-compile → builds only for the current host; the
# GitHub Actions matrix runs this per runner (topic 140: macos-14 → darwin-arm64,
# macos-15-intel → darwin-x86_64, ubuntu-latest → linux-x86_64).
#
# Windows note: CI runs under git-bsh. `python3` is usually absent (only
# `python`), `shasum`/`sha256sum` may be missing, AND PyInstaller appends `.exe`
# — so the binary name, manifest entrypoint and post-build exec all carry
# EXE_EXT (".exe" on windows-*, "" elsewhere). Pick the Python command and
# compute sha256 via Python (cross-platform).

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

EXECUTA_JSON="executa.json"
ENTRY_FILE="src/_entry.py"   # PyInstaller shim (absolute import → package graph)
SRC_DIR="src"
OUT_DIR="dist-anna"

[ -f "$EXECUTA_JSON" ] || { echo "ERROR: $EXECUTA_JSON not found" >&2; exit 1; }
[ -f "$ENTRY_FILE" ]   || { echo "ERROR: $ENTRY_FILE not found" >&2; exit 1; }
command -v pyinstaller >/dev/null 2>&1 || command -v uv >/dev/null 2>&1 || { echo "ERROR: need pyinstaller (CI) or uv (local dev)" >&2; exit 1; }

PY="$(command -v python3 >/dev/null 2>&1 && echo python3 || echo python)"

eval "$($PY - "$EXECUTA_JSON" <<'PYEOF'
import json, sys, shlex
d = json.load(open(sys.argv[1], encoding="utf-8"))
for k, default in [("tool_id", ""), ("version", "0.0.0"), ("name", ""), ("description", "")]:
    print(f"{k.upper()}={shlex.quote(str(d.get(k) or default))}")
PYEOF
)"
[ -n "$TOOL_ID" ] || { echo "ERROR: executa.json has no tool_id" >&2; exit 1; }

if [ -z "${PLATFORM:-}" ]; then
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  ARCH="$(uname -m)"
  case "$ARCH" in x86_64|amd64) ARCH=x86_64;; arm64|aarch64) ARCH=arm64;; esac
  case "$OS" in
    darwin)               PLATFORM="darwin-$ARCH" ;;
    linux)                PLATFORM="linux-$ARCH" ;;
    mingw*|msys*|cygwin*) PLATFORM="windows-x86_64" ;;
    *) echo "ERROR: unsupported platform: $OS-$ARCH (set PLATFORM env on CI)" >&2; exit 1 ;;
  esac
fi

# Windows binaries are PE executables with a .exe suffix; macOS/Linux are not.
# The archive's bin/ entry, manifest entrypoint, and post-build exec must all
# agree on this (a .exe stripped of its suffix is not launchable on Windows).
EXE_EXT=""
case "$PLATFORM" in windows-*) EXE_EXT=".exe" ;; esac

echo "Tool ID:  $TOOL_ID"
echo "Version:  $VERSION"
echo "Platform: $PLATFORM"
echo

# ── Pre-packaging check (forum topic 140, Ch3) ─────────────────────────
# Source-mode describe/health must both answer before we freeze the plugin
# into a binary — a broken source plugin only produces a broken binary.
# Skipped when the anna-app CLI isn't reachable (e.g. CI runners that only
# install pyinstaller) or when ANNA_SKIP_PRECHECK is set.
ANNAPP=""
if command -v anna-app >/dev/null 2>&1; then
  ANNAPP="anna-app"
elif command -v pnpm >/dev/null 2>&1 && pnpm exec anna-app --version >/dev/null 2>&1; then
  ANNAPP="pnpm exec anna-app"
fi
if [ -z "${ANNA_SKIP_PRECHECK:-}" ] && [ -n "$ANNAPP" ]; then
  echo "==> Pre-check: executa dev --describe / --health (topic 140 Ch3)"
  $ANNAPP executa dev --describe >/dev/null 2>&1 \
    || { echo "ERROR: '$ANNAPP executa dev --describe' failed — source plugin broken, aborting (set ANNA_SKIP_PRECHECK=1 to bypass)" >&2; exit 1; }
  $ANNAPP executa dev --health >/dev/null 2>&1 \
    || { echo "ERROR: '$ANNAPP executa dev --health' failed — source plugin broken, aborting (set ANNA_SKIP_PRECHECK=1 to bypass)" >&2; exit 1; }
  echo "    ✓ source-mode describe/health OK"
  echo
else
  echo "==> Pre-check skipped (anna-app CLI not reachable or ANNA_SKIP_PRECHECK set)"
  echo
fi

rm -rf build dist "$OUT_DIR/$TOOL_ID-$PLATFORM.tar.gz" "$OUT_DIR/stage-$PLATFORM"
mkdir -p "$OUT_DIR"

echo "==> Building single-file executable with PyInstaller"
# Prefer `uv run` so PyInstaller runs inside the project .venv, which has the
# local-path executa_sdk dep. A globally-installed pyinstaller (e.g. conda base)
# usually LACKS executa_sdk → ModuleNotFoundError in the frozen binary. CI has
# no uv but pip-installs pyinstaller + executa_sdk into one interpreter, so the
# bare `pyinstaller` fallback is correct there.
run_pyinstaller() {
  if command -v uv >/dev/null 2>&1; then
    uv run --with pyinstaller python -m PyInstaller "$@"
  else
    pyinstaller "$@"
  fi
}
# --collect-data skips prompts.yaml ("truman_director not a package" under the
# src-layout), so add it explicitly — engine._load_prompts() reads it at import
# and would FileNotFoundError inside the frozen binary. PyInstaller's --add-data
# separator is ';' on Windows, ':' elsewhere.
DATA_SEP=":"
[ -n "$EXE_EXT" ] && DATA_SEP=";"
run_pyinstaller \
  --onefile --clean --noupx \
  --name "$TOOL_ID" \
  --paths "$SRC_DIR" \
  --collect-submodules truman_director \
  --collect-submodules executa_sdk \
  --hidden-import executa_sdk \
  --add-data "src/truman_director/prompts.yaml${DATA_SEP}truman_director" \
  "$ENTRY_FILE"

BINARY="dist/$TOOL_ID$EXE_EXT"
[ -f "$BINARY" ] || { echo "ERROR: PyInstaller did not produce $BINARY" >&2; exit 1; }

if [ "$(uname -s)" = "Darwin" ]; then
  codesign --force --sign - "$BINARY" 2>/dev/null || true
fi

# ── Stage the archive: bin/<tool_id>[.exe] + manifest.json (topic 140) ──
STAGE="$OUT_DIR/stage-$PLATFORM"
mkdir -p "$STAGE/bin"
cp "$BINARY" "$STAGE/bin/$TOOL_ID$EXE_EXT"
chmod 0755 "$STAGE/bin/$TOOL_ID$EXE_EXT"

# manifest.json tells the Agent the entrypoint and marks the binary executable
# (forum topic 140: runtime.binary.entrypoint.default + permissions["bin/.."]).
$PY - "$STAGE/manifest.json" "$TOOL_ID" "$EXE_EXT" <<'PYEOF'
import json, sys
path, tool_id, ext = sys.argv[1], sys.argv[2], sys.argv[3]
entry = f"bin/{tool_id}{ext}"
json.dump(
    {
        "runtime": {"binary": {"entrypoint": {"default": entry}}},
        "permissions": {entry: "0o755"},
    },
    open(path, "w", encoding="utf-8"),
    indent=2,
)
PYEOF

ARCHIVE="$OUT_DIR/$TOOL_ID-$PLATFORM.tar.gz"
echo "==> Creating archive: $ARCHIVE (bin/<tool_id>$EXE_EXT + manifest.json)"
( cd "$STAGE" && tar czf "../$(basename "$ARCHIVE")" bin manifest.json )

# ── Post-build self-check (topic 140 FAQ): binary must answer describe ──
echo "==> Post-build check: binary answers describe (topic 140 FAQ)"
DESC="$(printf '{"jsonrpc":"2.0","method":"describe","id":1}' | "$STAGE/bin/$TOOL_ID$EXE_EXT" 2>/dev/null || true)"
$PY - "$DESC" <<'PYEOF' 2>/dev/null || { echo "ERROR: built binary did not answer describe — not a valid Executa" >&2; exit 1; }
import json, sys
d = json.loads(sys.argv[1])
r = d.get("result")
assert isinstance(r, dict) and (r.get("display_name") or r.get("name") or r.get("tools")), \
    "describe returned no manifest"
PYEOF
echo "    ✓ binary describe OK"

SHA256="$($PY -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ARCHIVE")"
SIZE="$(wc -c < "$ARCHIVE" | tr -d ' ')"

echo
echo "Built: $ARCHIVE ($SIZE bytes)"
echo "SHA-256: $SHA256"
echo "Layout:"; tar tzf "$ARCHIVE"
echo
echo "entrypoint = bin/$TOOL_ID$EXE_EXT  (declared in archive manifest.json; set the"
echo "  same on the platform Tool config page binary_urls.entrypoint — NOT in executa.json)"
