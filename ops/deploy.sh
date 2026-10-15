#!/bin/sh
# Default invocation is a dry run. --apply deploys the committed component only.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source="$repo/custom_components/vaillant_plus/"
target=/var/apps/docker-home-assistantan/shares/home-assistant/config/custom_components/vaillant_plus/
case "${1:---dry-run}" in
  --dry-run) mode=dry-run ;;
  --apply) mode=apply ;;
  *) echo 'Usage: ops/deploy.sh [--dry-run|--apply]' >&2; exit 2 ;;
esac
[ -f "$source/manifest.json" ] && [ -d "$target" ]
[ ! -L "${target%/}" ] && [ ! -e "$target/.git" ]
if [ -n "$(git -C "$repo" status --porcelain)" ]; then
  echo 'Commit or resolve repository changes before deployment.' >&2
  exit 1
fi
if [ "$mode" = dry-run ]; then
  exec rsync -an --delete --itemize-changes --exclude=.git --exclude=__pycache__ --exclude='*.pyc' "$source" "$target"
fi
umask 077
backup="/root/vaillant-deploy-backups/$(date -u +%Y%m%dT%H%M%SZ)-$(git -C "$repo" rev-parse --short HEAD)"
mkdir -p "$backup"
cp -a "${target%/}" "$backup/component"
git -C "$repo" rev-parse HEAD > "$backup/source-commit"
rsync -a --delete --itemize-changes --exclude=.git --exclude=__pycache__ --exclude='*.pyc' "$source" "$target"
python3 "$repo/ops/check_deployment.py" > "$backup/verification.json"
echo "Deployed; verification and prior component: $backup"
echo 'Reload/restart Home Assistant separately when appropriate.'
