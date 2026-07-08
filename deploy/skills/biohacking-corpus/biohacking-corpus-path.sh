#!/usr/bin/env bash
# Default corpus path for biohacking-corpus skill
BASE="${BIOHACKING_CORPUS_PATH:-/opt/medbot-corpus/structured_database}"
if [[ "$BASE" == *$'\n'* ]] || [[ ! "$BASE" =~ ^[a-zA-Z0-9/_.-]+$ ]] || [[ "$BASE" == *".."* ]]; then
  echo "ERROR: invalid BIOHACKING_CORPUS_PATH" >&2
  exit 1
fi
echo "$BASE"
