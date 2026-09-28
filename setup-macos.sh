#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
  echo "This installer is for macOS. On Linux, use docker compose up -d --build --wait."
  exit 1
fi
if [[ "$EUID" -eq 0 ]]; then
  echo "Run bash setup-macos.sh as your normal user, without sudo. It asks for admin access when needed."
  exit 1
fi
if [[ ! -f compose.yaml || ! -f backend/requirements.txt ]]; then
  echo "Extract the entire InTrac ZIP first, then run this script inside that folder."
  exit 1
fi

installer_dir=""
installer_mounted=false
cleanup() {
  if [[ "$installer_mounted" == true ]]; then
    hdiutil detach "$installer_dir/mount" -quiet || true
  fi
  if [[ -n "$installer_dir" ]]; then rm -rf "$installer_dir"; fi
}
trap cleanup EXIT

if [[ ! -d /Applications/Docker.app ]]; then
  case "$(uname -m)" in
    arm64) docker_arch=arm64 ;;
    x86_64) docker_arch=amd64 ;;
    *) echo "Unsupported Mac processor."; exit 1 ;;
  esac
  echo "Downloading Docker Desktop for $docker_arch. This can take several minutes."
  installer_dir="$(mktemp -d "${TMPDIR:-/tmp}/intrac-docker.XXXXXX")"
  curl --fail --location --retry 3 \
    "https://desktop.docker.com/mac/main/$docker_arch/Docker.dmg" \
    --output "$installer_dir/Docker.dmg"
  mkdir "$installer_dir/mount"
  hdiutil attach "$installer_dir/Docker.dmg" -mountpoint "$installer_dir/mount" -nobrowse -quiet
  installer_mounted=true
  echo "Installing Docker Desktop. Enter your Mac login password if asked."
  sudo "$installer_dir/mount/Docker.app/Contents/MacOS/install" --user="$(id -un)"
  hdiutil detach "$installer_dir/mount" -quiet
  installer_mounted=false
fi

# Docker Desktop bundles the CLI, Compose, and credential helper; Homebrew is unnecessary.
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
open -a Docker
echo "Finish Docker Desktop's welcome screens and review/accept its terms if you agree."
echo "Use the recommended settings. You can skip Docker account sign-in."
echo "Waiting up to 10 minutes for Docker's engine..."
docker_ready=false
for ((attempt=0; attempt<120; attempt++)); do
  if docker info >/dev/null 2>&1; then docker_ready=true; break; fi
  if ((attempt % 6 == 0)); then echo "Still waiting; check the Docker Desktop window."; fi
  sleep 5
done
if [[ "$docker_ready" != true ]]; then
  echo "Docker did not start. Resolve the message in Docker Desktop, then rerun this script."
  exit 1
fi
if [[ "$(docker info --format '{{.OSType}}')" != linux ]]; then
  echo "InTrac requires Docker's Linux container engine. Select it in Docker Desktop and rerun."
  exit 1
fi
docker compose version

if [[ ! -f .env ]]; then (umask 077; cp .env.example .env); fi
echo "Building and starting InTrac. The first build downloads its software dependencies."
docker compose up -d --build --wait --wait-timeout 180
echo "Choose an administrator password (12-128 characters). Typing is hidden. Save it in your password manager."
docker compose exec api python -m app.create_admin \
  --first-name System --last-name Administrator --username admin --if-missing
docker compose ps
echo "InTrac is ready. Default address: http://localhost (username: admin)."
echo "If you changed .env, use your configured address/port."
echo "For free public HTTPS, follow docs/CLOUDFLARE.md. For local HTTPS, see docs/HTTPS.md."
echo "Keep Docker Desktop running and this Mac awake while people use InTrac."
