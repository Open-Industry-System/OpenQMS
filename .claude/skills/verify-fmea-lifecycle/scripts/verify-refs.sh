#!/usr/bin/env bash
# Verify sub-skill references in the verify-fmea-lifecycle epic skill.
# Checks: epic SKILL.md exists, frontmatter valid, and every
# verify-fmea-lifecycle-* slug referenced under the spec directory
# (docs/user-stories/US-E2E-02-fmea-lifecycle/) has a matching
# .claude/skills/<slug>/SKILL.md. Exit non-zero and print any missing.
#
# NOTE: until the 19 sub-skills are authored (Task 2), this script is
# expected to report them as MISSING — that is correct behavior: it proves
# the validator works.
set -uo pipefail
SKILL=".claude/skills/verify-fmea-lifecycle/SKILL.md"
SPEC_DIR="docs/user-stories/US-E2E-02-fmea-lifecycle"
[ -f "$SKILL" ] || { echo "FAIL: $SKILL not found"; exit 1; }
[ -d "$SPEC_DIR" ] || { echo "FAIL: $SPEC_DIR not found"; exit 1; }

# 1. frontmatter
head -20 "$SKILL" | grep -q '^name: verify-fmea-lifecycle' || { echo "FAIL: missing/wrong name frontmatter"; exit 1; }
head -20 "$SKILL" | grep -q '^description: Use when' || { echo "FAIL: missing/bad description frontmatter"; exit 1; }

# 2. every verify-fmea-lifecycle-* slug referenced in the spec dir must have a skill dir
status=0
for slug in $(grep -rhoE 'verify-fmea-lifecycle-[a-z0-9-]+' "$SPEC_DIR" | sort -u); do
  if [ ! -f ".claude/skills/$slug/SKILL.md" ]; then
    echo "MISSING skill: .claude/skills/$slug/SKILL.md"
    status=1
  fi
done
exit $status
