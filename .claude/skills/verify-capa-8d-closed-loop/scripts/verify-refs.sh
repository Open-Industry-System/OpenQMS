#!/usr/bin/env bash
# Verify selector / API / audit contracts across all verify-capa-8d-* skills.
# Exit non-zero on any problem.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$ROOT" || exit 1

SKILL_DIRS=(.claude/skills/verify-capa-8d-*/)
status=0

echo "== frontmatter =="
for dir in "${SKILL_DIRS[@]}"; do
  skill="${dir}SKILL.md"
  [ -f "$skill" ] || { echo "FAIL: $skill not found"; status=1; continue; }
  name="$(basename "$dir")"
  if ! head -20 "$skill" | grep -q "^name: ${name}$"; then
    echo "FAIL: $skill missing/wrong name frontmatter (expected name: $name)"
    status=1
  fi
  if ! head -20 "$skill" | grep -q '^description: Use when'; then
    echo "FAIL: $skill missing/bad description frontmatter (must start with 'Use when')"
    status=1
  fi
done

selector_in_src() {
  local sel="$1"
  grep -rqs "data-e2e=\"$sel\"" frontend/src && return 0
  grep -rqs "data-e2e={\`$sel\`}" frontend/src && return 0
  # Ant Design okButtonProps / object form: "data-e2e": "sel"
  grep -rqs "\"data-e2e\": \"$sel\"" frontend/src && return 0
  grep -rqs "'data-e2e': '$sel'" frontend/src && return 0
  return 1
}

echo "== sub-report contract =="
for dir in "${SKILL_DIRS[@]}"; do
  [ "$(basename "$dir")" = "verify-capa-8d-closed-loop" ] && continue
  skill="${dir}SKILL.md"
  [ -f "$skill" ] || { echo "FAIL: $skill not found"; status=1; continue; }
  if ! grep -q '^## 子报告输出' "$skill"; then
    echo "FAIL: $skill missing '## 子报告输出' section (orchestrator contract)"
    status=1
  fi
  # One walk = one dated folder: US-E2E-01-<date>/01.<n>/report.md
  if ! grep -qE 'docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01\.[0-9]+/report\.md' "$skill"; then
    echo "FAIL: $skill missing/incorrect report.md path (expected docs/e2e/reports/US-E2E-01-<YYYY-MM-DD>/01.<n>/report.md)"
    status=1
  fi
done

echo "== selectors =="
while IFS= read -r sel; do
  # Angle-bracket templates: lateral-hit-<type> → require prefix
  if [[ "$sel" == *"<"*">"* ]]; then
    prefix="${sel%%<*}"
    if ! grep -rqs "data-e2e={\`$prefix" frontend/src && ! grep -rqs "$prefix" frontend/src; then
      echo "MISSING template-prefix selector in frontend/src: $sel (prefix=$prefix)"
      status=1
    fi
    continue
  fi
  # Indexed / dynamic suffixes documented as prefix only
  case "$sel" in
    rec-dag-stage-*|rec-source-*|rec-item-stage-*|d3-advice-type-*|related-capa-source-*|lateral-hit-*|row-*|verify-pass-*|verify-fail-*)
      base="${sel%\*}"
      if ! grep -rqs "data-e2e={\`$base" frontend/src && ! grep -rqs "$base" frontend/src; then
        echo "MISSING prefix selector in frontend/src: $sel"
        status=1
      fi
      continue
      ;;
  esac
  if ! selector_in_src "$sel"; then
    echo "MISSING selector in frontend/src: $sel"
    status=1
  fi
done < <(
  for dir in "${SKILL_DIRS[@]}"; do
    skill="${dir}SKILL.md"
    [ -f "$skill" ] || continue
    grep -oE 'data-e2e="[^"]+"' "$skill" 2>/dev/null | sed -E 's/data-e2e="([^"]+)"/\1/'
  done | sort -u
)

echo "== API paths =="
while IFS= read -r path; do
  last_seg="$(echo "$path" | sed -E 's#/+$##; s#\{[^}]+\}##g; s#//+#/#g' | awk -F/ '{print $NF}')"
  [ -z "$last_seg" ] && continue
  case "$last_seg" in
    api|e2e|seed-state|admin|logs|audit) continue ;;
  esac
  if ! grep -rqs --include='*.py' "$last_seg" backend/app/api; then
    echo "MISSING API path fragment in backend/app/api: $path (last=$last_seg)"
    status=1
  fi
done < <(
  for dir in "${SKILL_DIRS[@]}"; do
    skill="${dir}SKILL.md"
    [ -f "$skill" ] || continue
    grep -oE '/api/[A-Za-z0-9_./{}-]+' "$skill" 2>/dev/null
  done | sort -u
)

echo "== audit actions =="
while IFS= read -r action; do
  case "$action" in
    TRANSITION|CREATE|UPDATE|EDIT|APPROVE|GET|POST|PUT|PATCH|DELETE) continue ;;
  esac
  if ! grep -rqs --include='*.py' -E "action=[\"']${action}[\"']" backend/app; then
    echo "MISSING audit action in backend/app: $action"
    status=1
  fi
done < <(
  for dir in "${SKILL_DIRS[@]}"; do
    skill="${dir}SKILL.md"
    [ -f "$skill" ] || continue
    grep -oE 'action=[A-Z][A-Z0-9_]+' "$skill" 2>/dev/null | sed 's/action=//'
  done | sort -u
)

echo "== PPT review_status enum =="
ppt_skill=".claude/skills/verify-capa-8d-ppt-output/SKILL.md"
# Skill must document passed|needs_review|skipped and must NOT list 'failed' inside the enum set.
if grep -qE 'X-PPT-Review-Status[^。]*\{[^}]*`failed`' "$ppt_skill"; then
  echo "FAIL: $ppt_skill lists 'failed' inside the review_status enum set (should be passed|needs_review|skipped)"
  status=1
else
  echo "ok: PPT review_status enum excludes 'failed'"
fi

if [ "$status" -eq 0 ]; then
  echo "OK: all selector / API-fragment / audit-action contracts present (fragment-level match only; not a full behavioral test)"
else
  echo "FAIL: one or more contract checks failed"
fi
exit $status
