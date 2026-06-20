#!/usr/bin/env bash
# Pack the truman-director Executa into a platform-specific .tar.gz binary
# distribution that Anna Agent can download + install. Mirrors the official
# guide (forum topic 140: "Don't Just Run Locally: Packaging Anna Executa as a
# Releasable Binary").
#
# PyInstaller cannot cross-compile, so this builds ONLY for the current host.
# Run it on each target platform, or — the intended path — let the GitHub
# Actions matrix in .github/workflows/release-binary.yml run it per runner.
#
# Output: dist-anna/<tool_id>-<platform>.tar.gz
#   layout: bin/<tool_id>  +  manifest.json   (entrypoint = bin/<tool_id>)
#
# Windows note: CI runs this under git-bash. `python3` is usually absent there
# (only `python`), and `shasum`/`sha256sum` may be missing — so we pick the
# Python command and compute sha256 via Python (cross-platform).

set -euo pipefail

cd "$(dirname "$0")/.."   # repo root

EXECUTA_JSON="executa.json"
ENTRY_FILE="src/_entry.py"   # PyInstaller shim (absolute import → package graph)
SRC_DIR="src"
OUT_DIR="dist-anna"

[ -f "$EXECUTA_JSON" ] || { echo "ERROR: $EXECUTA_JSON not found" >&2; exit 1; }
[ -f "$ENTRY_FILE" ]   || { echo "ERROR: $ENTRY_FILE not found" >&2; exit 1; }
command -v pyinstaller >/dev/null 2>&1 || command -v uv >/dev/null 2>&1 || { echo "ERROR: need pyinstaller (CI) or uv (local dev)" >&2; exit 1; }

# Python interpreter: python3 on mac/linux, python on windows git-bash.
PY="$(command -v python3 >/dev/null 2>&1 && echo python3 || echo python)"

# Read metadata from executa.json (no hard-coding tool_id in the script).
eval "$($PY - "$EXECUTA_JSON" <<'PYEOF'
import json, sys, shlex
d = json.load(open(sys.argv[1], encoding="utf-8"))
for k, default in [("tool_id", ""), ("version", "0.0.0"), ("name", ""), ("description", "")]:
    print(f"{k.upper()}={shlex.quote(str(d.get(k) or default))}")
PYEOF
)"
[ -n "$TOOL_ID" ] || { echo "ERROR: executa.json has no tool_id" >&2; exit 1; }

# Platform key (Anna: darwin-arm64 / darwin-x86_64 / linux-x86_64 / windows-x86_64).
# Prefer $PLATFORM env when set — CI builds on runners whose `uname -m` reports
# the host arch, not the target. Local dev leaves it unset → auto-detect.
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

rm -rf build dist "$OUT_DIR/staging-$PLATFORM"
mkdir -p "$OUT_DIR/staging-$PLATFORM/bin"

echo "==> Building single-file executable with PyInstaller"
# Use a pre-installed pyinstaller if present (CI sets up Python + pyinstaller
# so it can pick a specific arch); fall back to `uv run --with pyinstaller`
# for local dev. --paths src roots the graph in our package; --collect-submodules
# pulls in every submodule of truman_director + executa_sdk so nothing is dropped.
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

# macOS: ad-hoc codesign so the binary isn't immediately flagged by Gatekeeper.
if [ "$(uname -s)" = "Darwin" ]; then
  codesign --force --sign - "$BINARY" 2>/dev/null || true
fi

STAGE="$OUT_DIR/staging-$PLATFORM"
cp "$BINARY" "$STAGE/bin/$TOOL_ID"
chmod 0755 "$STAGE/bin/$TOOL_ID"

echo "==> Writing archive manifest"
$PY - "$STAGE/manifest.json" "$TOOL_ID" "$VERSION" "$NAME" "$DESCRIPTION" <<'PYEOF'
import json, sys
from pathlib import Path
manifest_path, tool_id, version, display_name, description = sys.argv[1:6]
entrypoint = f"bin/{tool_id}"
manifest = {
    "name": tool_id,
    "display_name": display_name,
    "version": version,
    "description": description,
    "runtime": {
        "binary": {
            "entrypoint": {"default": entrypoint},
            "permissions": {entrypoint: "0o755"},
        }
    },
}
Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PYEOF

ARCHIVE="$OUT_DIR/$TOOL_ID-$PLATFORM.tar.gz"
echo "==> Creating archive: $ARCHIVE"
( cd "$STAGE" && tar czf "../$TOOL_ID-$PLATFORM.tar.gz" . )

# sha256 via Python (cross-platform — no shasum/sha256sum on windows git-bash).
SHA256="$($PY -c 'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' "$ARCHIVE")"
SIZE="$(wc -c < "$ARCHIVE" | tr -d ' ')"

echo
echo "Built: $ARCHIVE ($SIZE bytes)"
echo "SHA-256: $SHA256"
echo "Layout:"; tar tzf "$ARCHIVE"
echo
echo "Paste this into the platform Tool config (Multi-platform Binary URLs):"
cat <<JSON
"$PLATFORM": {
  "url": "https://github.com/<owner>/<repo>/releases/download/truman-director-v$VERSION/$TOOL_ID-$PLATFORM.tar.gz",
  "sha256": "$SHA256",
  "size": $SIZE,
  "entrypoint": "bin/$TOOL_ID",
  "format": "tar.gz"
}
JSON
