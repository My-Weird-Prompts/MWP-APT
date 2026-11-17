#!/usr/bin/env bash
# Rebuild and publish the APT repo. Runs in CI (.github/workflows/publish.yml) and locally
# the same way. Nothing schedules it: run it when a package has a new release.
#
# Env: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (R2 token with write access to mwppublic; only the apt/ prefix is touched),
#      R2_ACCOUNT_ID, GH_TOKEN, APT_SIGNING_KEY (ASCII-armoured secret key, no passphrase).
#      FORCE=1 rebuilds the index even when no new release was found.
#      R2_BUCKET overrides the bucket (default mwppublic); the prefix is always apt/.
set -euo pipefail
cd "$(dirname "$0")/.."

R2_BUCKET=${R2_BUCKET:-mwppublic}
BUCKET=s3://$R2_BUCKET/apt
SUITE=stable
export AWS_DEFAULT_REGION=auto
ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
S3=(aws s3 --endpoint-url "$ENDPOINT" --only-show-errors)

rm -rf tmp dists && mkdir -p tmp pool

# 1. Pull the published pool. It is the only state.
"${S3[@]}" sync "$BUCKET/pool/" pool/ --delete

# 2. Stage new releases, prune old versions, drop packages no longer in packages.yml.
GITHUB_OUTPUT=tmp/out python3 scripts/sync_releases.py --pool pool --owners tmp/owners.json
staged=$(sed -n 's/^staged=//p' tmp/out)
removed=$(sed -n 's/^removed=//p' tmp/out)
if [[ "$staged" == 0 && "$removed" == 0 && "${FORCE:-0}" != 1 ]]; then
  echo "Nothing new; index left as is."
  exit 0
fi

# 3. Index. Architecture: all packages are listed under binary-amd64 and binary-arm64.
ARCHES="amd64 arm64"
for a in $ARCHES; do
  mkdir -p "dists/$SUITE/main/binary-$a"
  apt-ftparchive --arch "$a" packages pool > "dists/$SUITE/main/binary-$a/Packages"
  gzip -9kf "dists/$SUITE/main/binary-$a/Packages"
done
apt-ftparchive \
  -o APT::FTPArchive::Release::Origin="My Weird Prompts" \
  -o APT::FTPArchive::Release::Label="My Weird Prompts" \
  -o APT::FTPArchive::Release::Suite="$SUITE" \
  -o APT::FTPArchive::Release::Codename="$SUITE" \
  -o APT::FTPArchive::Release::Architectures="$ARCHES" \
  -o APT::FTPArchive::Release::Components="main" \
  -o APT::FTPArchive::Release::Description="Linux packages for the My Weird Prompts podcast, built from their GitHub releases" \
  release "dists/$SUITE" > tmp/Release
mv tmp/Release "dists/$SUITE/Release"

# 4. Sign (InRelease for current apt, Release.gpg for old clients).
export GNUPGHOME=$(mktemp -d)
trap 'rm -rf "$GNUPGHOME"' EXIT
gpg --batch --quiet --import <<< "$APT_SIGNING_KEY"
gpg --batch --yes --clearsign -o "dists/$SUITE/InRelease" "dists/$SUITE/Release"
gpg --batch --yes --armor --detach-sign -o "dists/$SUITE/Release.gpg" "dists/$SUITE/Release"

# 4b. Landing page (apt/index.html) from the index just built.
python3 scripts/build_landing.py --packages "dists/$SUITE/main/binary-amd64/Packages" \
  --owners tmp/owners.json --out tmp/site/index.html

# 5. Publish: new .debs first, index next, pruned .debs last, so a client never sees an
#    index entry whose file is missing. Index files get a 60 s Cache-Control: the same
#    Cloudflare edge-cache mismatch that broke the F-Droid repo (signed file cached,
#    index not) would make apt reject the Packages hash.
"${S3[@]}" sync pool/ "$BUCKET/pool/" --cache-control 'public, max-age=31536000, immutable'
"${S3[@]}" sync dists/ "$BUCKET/dists/" --delete --cache-control 'public, max-age=60' --exact-timestamps
"${S3[@]}" cp key.gpg "$BUCKET/key.gpg"
"${S3[@]}" cp key.asc "$BUCKET/key.asc"
# Landing page and setup script: short cache, like dists/. The page goes up twice: as
# apt/index.html and as the object keyed "apt/", because R2's custom domain serves no
# directory index; a key ending in "/" is what answers https://cdn.myweirdprompts.com/apt/
# (verified 2026-10-21 with a probe key).
SHORT='public, max-age=60'
"${S3[@]}" cp site/setup.sh "$BUCKET/setup.sh" --cache-control "$SHORT" --content-type 'text/x-shellscript; charset=utf-8'
"${S3[@]}" cp tmp/site/index.html "$BUCKET/index.html" --cache-control "$SHORT" --content-type 'text/html; charset=utf-8'
aws s3api put-object --endpoint-url "$ENDPOINT" --bucket "$R2_BUCKET" --key apt/ \
  --body tmp/site/index.html --content-type 'text/html; charset=utf-8' --cache-control "$SHORT" >/dev/null
"${S3[@]}" sync pool/ "$BUCKET/pool/" --delete
echo "Published $staged new package(s), removed $removed file(s)."
