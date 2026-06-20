#!/usr/bin/env bash
# Pack the truman-director Executa into a platform-specific .tar.gz binary
# distribution that Anna Agent can download + install.
#
# Archive layout MATCHES anna-executa-examples (the authoritative reference,
# not the older forum topic 140 guide): a SINGLE binary at the tar ROOT — no
# bin/ directory, no manifest.json. The entrypoint in executa.json binary_urls
# is the bare tool_id, and the platform infers the rest.
#
# PyInstaller cannot cross-compile → builds only for the current host; the
# GitHub Actions matrix runs this per runner.
#
# Windows note: CI runs under git-bash. `python3` is usually absent (only
# `python`), and `shasum`/`sha256sum` may be missing — pick the Python command
# and compute sha256 via Python (cross-platform).

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
  case "$OS-$ARCH" in
    darwin-arm64|darwin-x86_64|linux-x86_64) PLATFORM="$OS-$ARCH" ;;
    *) echo "ERROR: unsupported platform: $OS-$ARCH (set PLATFORM env on CI)" >&2; exit 1 ;;
  esac
fi

echo "Tool ID:  $TOOL_ID"
echo "Version:  $VERSION"
echo "Platform: $PLATFORM"
echo

rm -rf build dist "$OUT_DIR/$TOOL_ID-$PLATFORM.tar.gz"
mkdir -p "$OUT_DIR"

echo "==> Building single-file executable with PyInstaller"
run_pyinstaller() {
  if command -v pyinstaller >/dev/null 2>&1; then
    pyinstaller "$@"
  else
    uv run --with pyinstaller python -m PyInstaller "$@"
  fi
}
run_pyinstaller \
  --onefile --clean --noupx \
  --name "$TOOL_ID" \
  --paths "$SRC_DIR" \
  --collect-submodules truman_director \
  --collect-data truman_director \
  --collect-submodules executa_sdk \
  --hidden-import executa_sdk \
  "$ENTRY_FILE"

BINARY="dist/$TOOL_ID"
[ -f "$BINARY" ] || { echo "ERROR: PyInstaller did not produce $BINARY" >&2; exit 1; }

if [ "$(uname -s)" = "Darwin" ]; then
  codesign --force --sign - "$BINARY" 2>/dev/null || true
fi

# Archive = SINGLE binary at tar root (matches anna-executa-examples; no bin/,
# no manifest.json). entrypoint in binary_urls = bare tool_id.
ARCHIVE="$OUT_DIR/$TOOL_ID-$PLATFORM.tar.gz"
echo "==> Creating archive: $ARCHIVE (single binary at root)"
( cd dist && tar czf "../$ARCHIVE" "$TOOL_ID" )

SHA256="$($PY -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ARCHIVE")"
SIZE="$(wc -c < "$ARCHIVE" | tr -d ' ')"

echo
echo "Built: $ARCHIVE ($SIZE bytes)"
echo "SHA-256: $SHA256"
echo "Layout:"; tar tzf "$ARCHIVE"
echo
echo "(executa.json binary_urls only needs url + entrypoint + format — no sha256/size)"
echo "entrypoint = $TOOL_ID  (bare, at tar root)"
