#!/usr/bin/env bash
# scripts/gfw-deploy.sh
#
# GFW-safe deployment: bypasses Dokploy's git-clone pipeline entirely.
# Use when the Dokploy host cannot reach github.com via git HTTPS (GFW interference).
#
# How it works:
#   1. Downloads source via GitHub zipball API  (HTTPS REST — far less GFW interference than git)
#   2. Builds each Docker image directly from /tmp on the host
#   3. Updates the Swarm service with `docker service update --image` (zero-downtime rolling update)
#
# Prerequisites:
#   - SSH access to the Dokploy host as root
#   - GitHub PAT with `repo:read` scope
#   - jq installed locally
#
# Usage:
#   export GITHUB_PAT="ghp_..."
#   export DOKPLOY_HOST="root@192.168.x.x"
#   export REPO="owner/my-project"          # e.g. acme/my-app
#   export BRANCH="main"
#   bash scripts/gfw-deploy.sh
#
# To update a single service only, pass its name as first argument:
#   bash scripts/gfw-deploy.sh web

set -euo pipefail

: "${GITHUB_PAT:?GITHUB_PAT is required}"
: "${DOKPLOY_HOST:?DOKPLOY_HOST is required (e.g. root@192.168.1.50)}"
: "${REPO:?REPO is required (e.g. owner/my-project)}"
: "${BRANCH:=main}"

TARGET_SERVICE="${1:-}"   # optional: filter to one service name

# ---------------------------------------------------------------------------
# Configuration — edit these to match your project
# ---------------------------------------------------------------------------
declare -A SERVICES=(
  # service_key → "dockerfile_path|swarm_service_name|image_tag"
  [web]="apps/web/Dockerfile|my-project-stack_web|my-project-web:latest"
  [api]="services/api/Dockerfile|my-project-stack_api|my-project-api:latest"
  [admin]="apps/admin/Dockerfile|my-project-stack_admin|my-project-admin:latest"
)

WORKDIR="/tmp/gfw_deploy_$$"
ZIP_PATH="/tmp/gfw_deploy_$$.zip"

# ---------------------------------------------------------------------------
cleanup() {
  ssh "$DOKPLOY_HOST" "rm -rf $WORKDIR $ZIP_PATH" 2>/dev/null || true
}
trap cleanup EXIT

echo "==> Downloading source: github.com/$REPO@$BRANCH"
ssh "$DOKPLOY_HOST" "
  curl -fsSL --max-time 180 \
    -H 'Authorization: Bearer $GITHUB_PAT' \
    -o $ZIP_PATH \
    'https://api.github.com/repos/$REPO/zipball/$BRANCH'
  mkdir -p $WORKDIR
  cd $WORKDIR && unzip -q $ZIP_PATH
  echo 'unzip done'
"

# Get the directory name GitHub creates inside the zip (e.g. owner-repo-<sha>/)
SRCDIR=$(ssh "$DOKPLOY_HOST" "ls -d $WORKDIR/*/ | head -1")
echo "==> Source dir: $SRCDIR"

# ---------------------------------------------------------------------------
build_and_update() {
  local key="$1"
  IFS='|' read -r dockerfile swarm_name image_tag <<< "${SERVICES[$key]}"

  echo ""
  echo "==> [$key] Building image: $image_tag"
  ssh "$DOKPLOY_HOST" "docker build -t $image_tag -f ${SRCDIR}${dockerfile} $SRCDIR"

  echo "==> [$key] Updating Swarm service: $swarm_name"
  ssh "$DOKPLOY_HOST" "docker service update --image $image_tag $swarm_name"

  echo "==> [$key] Done. Waiting for rollout..."
  ssh "$DOKPLOY_HOST" "docker service ls --filter name=$swarm_name --format '{{.Replicas}}'"
}

# ---------------------------------------------------------------------------
if [[ -n "$TARGET_SERVICE" ]]; then
  if [[ -z "${SERVICES[$TARGET_SERVICE]:-}" ]]; then
    echo "ERROR: unknown service '$TARGET_SERVICE'. Known: ${!SERVICES[*]}"
    exit 1
  fi
  build_and_update "$TARGET_SERVICE"
else
  for key in "${!SERVICES[@]}"; do
    build_and_update "$key"
  done
fi

echo ""
echo "==> All services updated. Verify with:"
echo "    ssh $DOKPLOY_HOST 'docker service ls | grep my-project'"
echo "    curl http://<host>:<web-port>/api/health"
