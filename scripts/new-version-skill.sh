#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 <new-version> <previous-version> [short-name]" >&2
  echo "Example: $0 v1.8.0 v1.7.9 real-sandbox-execution" >&2
  exit 2
fi

version="$1"
previous="$2"
short_name="${3:-planned-version}"
skill_dir=".claude/skills/${version}"
skill_file="${skill_dir}/SKILL.md"

if [ -e "$skill_file" ]; then
  echo "Refusing to overwrite existing $skill_file" >&2
  exit 1
fi

mkdir -p "$skill_dir"
sed \
  -e "s/VERSION/${version}/g" \
  -e "s/PREVIOUS_VERSION/${previous}/g" \
  .claude/skills/_template/SKILL.md > "$skill_file"

note_file="docs/version-notes/${version}-${short_name}.md"
if [ ! -e "$note_file" ]; then
  cat > "$note_file" <<EOF
# ${version}: ${short_name}

## Base
- Depends on: \`${previous}\`
- Skill: \`${skill_file}\`

## Goals
- TBD

## Acceptance
- TBD

## Completion Notes
- TBD
EOF
fi

echo "Created $skill_file"
echo "Created or kept $note_file"
