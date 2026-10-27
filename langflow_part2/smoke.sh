#!/usr/bin/env bash
# Smoke test of the Event AI components in the Langflow venv, with no LLM call.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
VENV=${LANGFLOW_VENV:-$ROOT/.venv-langflow}
set -a; source "$ROOT/.env"; set +a
export PYTHONPATH="$ROOT:$ROOT/langflow_part2/components" LANGFUSE_TRACING_ENABLED=false
export SMOKE_OUT=$(mktemp -d)
"$VENV/bin/lfx" run "$ROOT/langflow_part2/smoke_graph.py" "partnersummit2026" --format text
"$VENV/bin/python" "$ROOT/langflow_part2/smoke_tools.py"
"$VENV/bin/python" "$ROOT/eval/run_part2.py" --outputs "$SMOKE_OUT" --no-save | grep -v "miss:"
