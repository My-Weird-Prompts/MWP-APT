#!/bin/sh
# Add My Weird Prompts APT repository (amd64, arm64), optionally installing packages.
#   curl -fsSL https://cdn.myweirdprompts.com/apt/setup.sh | sudo sh
#   curl -fsSL https://cdn.myweirdprompts.com/apt/setup.sh | sudo sh -s -- mwp-announcer
# Package list: https://cdn.myweirdprompts.com/apt/
# Source: https://github.com/My-Weird-Prompts/MWP-APT/blob/main/site/setup.sh
set -eu
FPR=500A7BDACD658CA3A0414E1FAB59AE3CED26BB79
BASE=https://cdn.myweirdprompts.com/apt
KEYRING=/etc/apt/keyrings/myweirdprompts-archive-keyring.gpg
SOURCES=/etc/apt/sources.list.d/myweirdprompts.sources
[ "$(id -u)" = 0 ] || { echo "Run as root: curl -fsSL $BASE/setup.sh | sudo sh" >&2; exit 1; }
case "$(dpkg --print-architecture)" in amd64|arm64) ;; *) echo "This repository serves amd64 and arm64 only." >&2; exit 1;; esac
command -v curl >/dev/null || { apt-get update -q && apt-get install -y -q curl; }
command -v gpg >/dev/null || { apt-get update -q && apt-get install -y -q gpg; }
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
curl -fsSL "$BASE/key.gpg" -o "$tmp"
gpg --show-keys --with-colons "$tmp" | grep -q "^fpr:*$FPR:" || { echo "Key fingerprint mismatch; not installing." >&2; exit 1; }
install -d -m 0755 /etc/apt/keyrings
install -m 0644 "$tmp" "$KEYRING"
cat > "$SOURCES" <<SRC
Types: deb
URIs: $BASE
Suites: stable
Components: main
Architectures: amd64 arm64
Signed-By: $KEYRING
SRC
apt-get update -q
if [ "$#" -gt 0 ]; then
    apt-get install -y "$@"
fi
echo "Repository added. Install packages with: sudo apt install <name>  (list: $BASE/)"
