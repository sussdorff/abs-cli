#!/usr/bin/env bash
# Repository pre-push preflight. The global pre-push hook runs this script
# with the hook arguments (remote name and URL); they are not needed here.
# A non-zero exit fails the push.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

python3 .agents/standards/toolchains/scripts/check_toolchain_versions.py
