#!/usr/bin/env bash
# Start Langflow for Part 2 on http://localhost:7860 (D16), with the keys from .env.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VENV=${LANGFLOW_VENV:-$ROOT/.venv-langflow}
set -a; source "$ROOT/.env"; set +a
export PYTHONPATH="$ROOT"                                      # the components import eventai
export LANGFLOW_COMPONENTS_PATH="$ROOT/langflow_part2/components"
export LANGFLOW_CONFIG_DIR="$ROOT/langflow_part2/.data"       # gitignored: secret key, API keys, flows
export LANGFLOW_AUTO_LOGIN=true DO_NOT_TRACK=true
export LANGFUSE_BASE_URL="${LANGFUSE_HOST:-}" LANGFUSE_TRACING_ENVIRONMENT=agent
exec "$VENV/bin/langflow" run --host 127.0.0.1 --port 7860 --no-open-browser
