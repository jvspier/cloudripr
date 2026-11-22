#!/bin/bash
set -euo pipefail

# Map env vars to cloudripr CLI flags. Only flags that actually exist
# on the current CLI are forwarded. Anything unset is omitted so the CLI
# falls back to its built-in defaults.
#
# Also recognized directly by the CLI (no mapping needed):
#   CLOUDRIPR_PASSWORD_HASH
#   CLOUDRIPR_SESSION_SECRET

args=()
[[ -n "${HOST:-}" ]]            && args+=(--host "$HOST")
[[ -n "${PORT:-}" ]]            && args+=(--port "$PORT")
[[ -n "${DATA_DIR:-}" ]]        && args+=(--data-dir "$DATA_DIR")
[[ -n "${CACHE_DIR:-}" ]]       && args+=(--cache-dir "$CACHE_DIR")
[[ "${HTTPS_ONLY:-}" == "1" ]]  && args+=(--https-only)
[[ -n "${PASSWORD_HASH:-}" ]]   && args+=(--password-hash "$PASSWORD_HASH")
[[ -n "${SESSION_SECRET:-}" ]]  && args+=(--session-secret "$SESSION_SECRET")

# With arguments (e.g. `verify-2fa-hook --apple-id ...`) run that CLI command
# instead of the web server.
if [[ $# -gt 0 ]]; then
  [[ "$1" == "cloudripr" ]] && shift
  exec cloudripr "$@"
fi

exec cloudripr "${args[@]}"
