#!/usr/bin/env bash
# gitleaks over what goes public: `git archive HEAD` of this
# directory — the root of verso-genealogy/verso, or lib/ of a parent repository — unpacked in a temporary
# directory. `.gitleaks.toml` lists the false positives, each with its reason.
#
#   bash tools/secrets_check.sh        # make secrets-check
set -euo pipefail

command -v gitleaks >/dev/null || { echo "gitleaks не найден — brew install gitleaks" >&2; exit 2; }

here=$(cd "$(dirname "$0")/.." && pwd)
top=$(git -C "$here" rev-parse --show-toplevel)
prefix=$(git -C "$here" rev-parse --show-prefix)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git -C "$top" archive "HEAD${prefix:+:$prefix}" | tar -x -C "$tmp"

config=()
if [ -f "$tmp/.gitleaks.toml" ]; then
  config=(--config "$tmp/.gitleaks.toml")
fi
gitleaks dir --verbose --redact --no-banner --exit-code 1 ${config[@]+"${config[@]}"} "$tmp"
