#!/usr/bin/env bash
# Install the reviewed test-only service package on the approved Linux preview host.
set -euo pipefail
[[ $(id -u) == 0 ]]
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
destination=/usr/local/lib/openqms/d4-acceptance
exec 9>/run/lock/openqms-deploy.lock
flock -x 9
if ! getent passwd openqms-d4-portal >/dev/null; then
  useradd --system --user-group --no-create-home --shell /usr/sbin/nologin openqms-d4-portal
fi
for group in $(id -nG openqms-d4-portal); do
  [[ "$group" == openqms-d4-portal ]]
done
[[ $(id -u openqms-d4-portal) != 0 && $(id -gn openqms-d4-portal) == openqms-d4-portal ]]
install -d -o root -g root -m 0755 "$destination"
for name in allocate.py browser.py cases.py cleanup.py executor.py issue.py portal_issue.py prepare_preview.py provision.py revoke_runtime.py revoke_wire.py runtime_launch.py witness.py; do
  [[ -f "$source_dir/$name" && ! -L "$source_dir/$name" ]]
  install -o root -g root -m 0644 "$source_dir/$name" "$destination/$name"
done
for service in executor portal; do
  name="openqms-d4-acceptance-${service}@.service"
  install -o root -g root -m 0644 "$source_dir/$name" "/etc/systemd/system/$name"
done
install -o root -g root -m 0644 "$source_dir/openqms-d4-acceptance.conf" /etc/tmpfiles.d/openqms-d4-acceptance.conf
systemd-tmpfiles --create /etc/tmpfiles.d/openqms-d4-acceptance.conf
systemctl daemon-reload
