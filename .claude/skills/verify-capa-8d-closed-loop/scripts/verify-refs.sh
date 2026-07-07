#!/usr/bin/env bash
# Verify selector references + frontmatter in verify-capa-8d-closed-loop SKILL.md.
# Checks: SKILL.md exists, frontmatter valid, every [data-e2e="X"] in SKILL.md
# appears in frontend/src. Backend /api/... paths are NOT checked here — verify
# them manually against backend/app/api/ (see plan Task 5). Exit non-zero on any problem.
set -uo pipefail
SKILL=".claude/skills/verify-capa-8d-closed-loop/SKILL.md"
[ -f "$SKILL" ] || { echo "FAIL: $SKILL not found"; exit 1; }

# 1. frontmatter
head -20 "$SKILL" | grep -q '^name: verify-capa-8d-closed-loop' || { echo "FAIL: missing/wrong name frontmatter"; exit 1; }
head -20 "$SKILL" | grep -q '^description: Use when' || { echo "FAIL: missing/bad description frontmatter"; exit 1; }

# 2. every [data-e2e="X"] in SKILL.md must appear in frontend/src
status=0
for sel in $(grep -oE 'data-e2e="[^"]+"' "$SKILL" | sed -E 's/data-e2e="([^"]+)"/\1/' | sort -u); do
  # rec-dag-stage-<i> is a JSX template literal (data-e2e={`rec-dag-stage-${i}`}),
  # not a quoted attr — search the bare prefix, not data-e2e="rec-dag-stage-.
  if [[ "$sel" == "rec-dag-stage-"* ]]; then
    if ! grep -rqs 'rec-dag-stage-' frontend/src; then
      echo "MISSING selector in frontend/src: $sel"
      status=1
    fi
    continue
  fi
  if ! grep -rqs "data-e2e=\"$sel\"" frontend/src; then
    echo "MISSING selector in frontend/src: $sel"
    status=1
  fi
done
# 3. prefix-match selectors [data-e2e^="X"] — validate the bare prefix appears in frontend/src
for sel in $(grep -oE 'data-e2e\^="[^"]+"' "$SKILL" | sed -E 's/data-e2e\^="([^"]+)"/\1/' | sort -u); do
  if ! grep -rqs "data-e2e={\`$sel" frontend/src && ! grep -rqs "data-e2e=\"$sel" frontend/src; then
    echo "MISSING prefix selector in frontend/src: $sel"
    status=1
  fi
done
exit $status
