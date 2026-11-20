#!/bin/bash
# Writes the local config of mytool once per checkout; an apply runs it every time (post-apply).
set -eu
config="$AGENT_READY_PROJECT_ROOT/.mytool/config.json"
if [ -f "$config" ]; then
  exit 0
fi
mkdir -p "$(dirname "$config")"
printf '{\n  "strict": true\n}\n' > "$config"
echo "wrote $config"
