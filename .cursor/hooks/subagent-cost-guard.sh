#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode_file="$script_dir/../subagent-mode"
mode="standard"

if [ -f "$mode_file" ]; then
  mode=$(tr -d '[:space:]' < "$mode_file")
fi

case "$mode" in
  standard)
    printf '%s\n' '{"permission":"allow"}'
    ;;
  blocked)
    printf '%s\n' '{"permission":"deny","user_message":"Sub-agent blocked by .cursor/subagent-mode to prevent unintended Composer Fast usage. Continue the work sequentially in the current main agent; do not retry Task or sub-agent calls."}'
    ;;
  *)
    printf '%s\n' '{"permission":"deny","user_message":"Sub-agent blocked because .cursor/subagent-mode is invalid. Set it to standard or blocked."}'
    ;;
esac

