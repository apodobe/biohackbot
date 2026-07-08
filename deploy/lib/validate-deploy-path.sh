#!/usr/bin/env bash
# Reject shell metacharacters in deploy paths/hosts (SSH injection guard).
validate_deploy_value() {
  local label="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    echo "ERROR: $label is empty" >&2
    return 1
  fi
  if [[ "$value" == *$'\n'* ]] || [[ "$value" == *$'\r'* ]]; then
    echo "ERROR: $label contains newline" >&2
    return 1
  fi
  if [[ ! "$value" =~ ^[a-zA-Z0-9@._:/-]+$ ]]; then
    echo "ERROR: $label contains unsafe characters: $value" >&2
    return 1
  fi
  if [[ "$value" == *".."* ]]; then
    echo "ERROR: $label must not contain .." >&2
    return 1
  fi
}
