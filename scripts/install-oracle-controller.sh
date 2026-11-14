#!/usr/bin/env bash
# One-time trusted root bootstrap; never executed from a PR or by workflow credentials.
set +x
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'controller installation requires root' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
exec 9>/run/lock/openqms-deploy.lock
flock -x 9
install -d -m 0755 /usr/local/lib/openqms
controller=$(mktemp -d /usr/local/lib/openqms/.oracle-production.XXXXXXXX)
trap 'if [[ -n "${controller:-}" && -d "$controller" ]]; then rm -rf -- "$controller"; fi' EXIT
install -d -m 0755 "$controller/scripts" "$controller/deploy"
files=(scripts/oracle-production-remote.py scripts/check-release-tree.py docker-compose.prod.yml deploy/preview-edge.override.yml deploy/production-edge-Caddyfile compose.preview.yml scripts/oracle-preview-remote.py scripts/oracle-preview.py scripts/oracle-preview-initialize.py deploy/preview-Caddyfile)
for name in "${files[@]}"; do
  [[ -f "$repo/$name" && ! -L "$repo/$name" ]] || { echo 'trusted controller file unavailable' >&2; exit 1; }
  install -m 0644 "$repo/$name" "$controller/$name"
done
python3 - "$controller" <<'PY'
import hashlib,pathlib,sys
root=pathlib.Path(sys.argv[1])
manifest=''.join(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n' for path in sorted(root.rglob('*')) if path.is_file() and path.name!='controller.sha256')
(root/'controller.sha256').write_text(manifest)
PY
chown -R root:root "$controller"
chmod -R go-w "$controller"
if [[ -e /usr/local/lib/openqms/oracle-production ]]; then
  [[ ! -L /usr/local/lib/openqms/oracle-production ]] || exit 1
  mv /usr/local/lib/openqms/oracle-production "/usr/local/lib/openqms/oracle-production.previous.$(date -u +%Y%m%dT%H%M%SZ).$$"
fi
mv "$controller" /usr/local/lib/openqms/oracle-production
controller=""
install -m 0755 "$repo/scripts/oracle-deploy-receiver.py" /usr/local/sbin/openqms-deploy-receiver
install -m 0755 "$repo/scripts/oracle-backup-current.py" /usr/local/sbin/openqms-backup-current
install -d -m 0755 /usr/local/bin
cat > /usr/local/bin/openqms-deploy-ssh <<'EOF'
#!/bin/sh
[ "$#" = 1 ] || exit 1
case "$1" in production|preview) ;; *) exit 1 ;; esac
exec sudo -n /usr/local/sbin/openqms-deploy-receiver "$1" "$SSH_ORIGINAL_COMMAND"
EOF
chmod 0755 /usr/local/bin/openqms-deploy-ssh
id openqms-deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/sh openqms-deploy
for group in $(id -nG openqms-deploy); do
  case "$group" in root|sudo|docker|admin|wheel)
    echo 'existing deployment account has broad groups; administrator review required' >&2
    exit 1
    ;;
  esac
done
usermod --lock openqms-deploy
# The account is intentionally NOT added to docker or sudo groups.
install -d -m 0755 -o root -g root /home/openqms-deploy/.ssh
touch /home/openqms-deploy/.ssh/authorized_keys
chown root:root /home/openqms-deploy/.ssh/authorized_keys
chmod 0644 /home/openqms-deploy/.ssh/authorized_keys
python3 - /home/openqms-deploy/.ssh/authorized_keys <<'PYKEYS'
from pathlib import Path
import sys
production='restrict,port-forwarding,permitopen="127.0.0.1:5432",command="/usr/local/bin/openqms-deploy-ssh production"'
preview='restrict,port-forwarding,permitopen="127.0.0.1:25432",permitopen="127.0.0.1:25433",command="/usr/local/bin/openqms-deploy-ssh preview"'
for line in Path(sys.argv[1]).read_text().splitlines():
    if not line.strip() or line.lstrip().startswith('#'): continue
    if not any(line.startswith(options + ' ssh-ed25519 ') for options in (production,preview)):
        raise SystemExit('existing deployment key lacks required role/forwarding restrictions')
PYKEYS
install -d -m 0700 -o root -g root /var/lib/openqms-releases /var/lib/openqms-previews
install -d -m 0755 -o root -g root /etc/openqms /etc/openqms/preview-routes
install -m 0644 "$repo/deploy/production-edge-Caddyfile" /etc/openqms/production-edge-Caddyfile
install -m 0644 "$repo/deploy/preview-Caddyfile" /etc/openqms/preview-Caddyfile
cat > /etc/sudoers.d/openqms-deploy <<'EOF'
openqms-deploy ALL=(root) NOPASSWD: /usr/local/sbin/openqms-deploy-receiver *
EOF
chmod 0440 /etc/sudoers.d/openqms-deploy
visudo -cf /etc/sudoers.d/openqms-deploy >/dev/null
cat > /etc/ssh/sshd_config.d/90-openqms-deploy.conf <<'EOF'
Match User openqms-deploy
    AuthenticationMethods publickey
    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitTTY no
    X11Forwarding no
    AllowAgentForwarding no
    AllowTcpForwarding local
    PermitOpen 127.0.0.1:5432 127.0.0.1:25432 127.0.0.1:25433
Match all
EOF
sshd -t
# Reload only after sshd validates; the operator retains their existing admin session.
systemctl reload ssh
if ! docker network inspect openqms-preview-edge >/dev/null 2>&1; then
  docker network create openqms-preview-edge >/dev/null
fi
# Resource-bounded isolated preview builder; no production app resources are reset.
if ! docker buildx inspect openqms-preview-builder >/dev/null 2>&1; then
  docker buildx create --name openqms-preview-builder --driver docker-container --driver-opt memory=2g,cpu-quota=200000 >/dev/null
fi
docker buildx inspect --bootstrap openqms-preview-builder >/dev/null
docker update --cpus 2 --memory 2g --pids-limit 512 buildx_buildkit_openqms-preview-builder0 >/dev/null
printf '%s\n' 'Trusted Oracle controller installed; install separate restricted public keys before enabling workflows.'
