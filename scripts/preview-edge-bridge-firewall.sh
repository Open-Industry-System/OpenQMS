#!/usr/bin/env bash
# Administrator prerequisite, never invoked from a candidate PR or workflow key.
set -euo pipefail
[[ $(id -u) == 0 ]]
rules=/etc/openqms/preview-edge-bridge.nft
[[ -f "$rules" && ! -L "$rules" ]]
[[ $(stat -c '%u:%g:%a' "$rules") == 0:0:644 ]]
exec 9>/run/lock/openqms-preview-edge-bridge.lock
flock -x 9
transaction() {
    if nft list table bridge openqms_preview_edge >/dev/null 2>&1; then
        printf 'delete table bridge openqms_preview_edge\n'
    fi
    cat "$rules"
}
# Atomic replacement of this dedicated table; never flush the global ruleset.
transaction | nft --check --file -
transaction | nft --file -
