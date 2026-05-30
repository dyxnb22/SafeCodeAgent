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
plan_dir="docs/version-plans"
plan_file="${plan_dir}/${version}-${short_name}.md"
note_file="docs/version-notes/${version}-${short_name}.md"

if [ -e "$plan_file" ]; then
  echo "Refusing to overwrite existing $plan_file" >&2
  exit 1
fi

mkdir -p "$plan_dir" docs/version-notes

sed \
  -e "s/VERSION/${version}/g" \
  -e "s/PREVIOUS_VERSION/${previous}/g" \
  -e "s/short-feature-name/${short_name}/g" \
  "${plan_dir}/_template.md" > "$plan_file"

cat >> "$plan_file" <<EOF

## Generated
- Created by: \`scripts/new-version-plan.sh\`
EOF

if [ ! -e "$note_file" ]; then
  cat > "$note_file" <<EOF
# ${version}: ${short_name}

## Base
- Depends on: \`${previous}\`
- Plan: \`${plan_file}\`

## Completion Notes
- TBD

## Tests
- TBD

## Tag
- TBD
EOF
fi

echo "Created $plan_file"
echo "Created or kept $note_file"
