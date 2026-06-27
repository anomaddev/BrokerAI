#!/usr/bin/env fish
# Load BrokerAI .env into fish (fish cannot source bash KEY=value files).
#
# Usage (from repo root):
#   source scripts/load-env.fish
#
# Note: ./venv/bin/brokerai and ./scripts/dev.sh load .env automatically —
# you only need this when exporting vars into your fish session manually.

set -l root (status dirname)/..
set -l env_file "$root/.env"

if not test -f "$env_file"
    echo "No .env at $env_file — run ./scripts/dev.sh --setup first" >&2
    return 1
end

set -l loaded 0
for line in (grep -v '^\s*#' "$env_file" | grep -v '^\s*$')
    set -l kv (string split -m 1 '=' -- $line)
    if test (count $kv) -eq 2
        set -gx $kv[1] $kv[2]
        set loaded (math $loaded + 1)
    end
end

echo "Loaded $loaded variables from $env_file"
