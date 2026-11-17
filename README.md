# MWP-APT

Signed APT repository for My Weird Prompts Linux packages, built from the `.deb` assets on
their GitHub releases. Static files on Cloudflare R2, published on demand. Created 2026-11-17,
cloned from the pattern of `danielrosehill/APT-Public-Repo` (same scripts, different bucket,
key and arch list).

**Add it (Ubuntu / Debian, amd64 or arm64 incl. Raspberry Pi):**

```bash
curl -fsSL https://cdn.myweirdprompts.com/apt/setup.sh | sudo sh
# or add and install in one step:
curl -fsSL https://cdn.myweirdprompts.com/apt/setup.sh | sudo sh -s -- mwp-announcer
```

Landing page / package list: <https://cdn.myweirdprompts.com/apt/>.

| | |
|---|---|
| Repo URL | `https://cdn.myweirdprompts.com/apt`, suite `stable`, component `main`, archs `amd64` and `arm64` |
| Signing key | "My Weird Prompts APT <show@myweirdprompts.com>", RSA 4096, no expiry, no passphrase. Fingerprint `500A7BDACD658CA3A0414E1FAB59AE3CED26BB79`. Public: `key.gpg` (binary), `key.asc` |
| Bucket | R2 `mwppublic` (account `81ee9810726226b99b56e4d84ffac020`), custom domain `cdn.myweirdprompts.com`, prefix `apt/` only. Sibling: `fdroid/` in the same bucket (`My-Weird-Prompts/MWP-FDroid`), never touched here |
| Local paths | install keyring `/etc/apt/keyrings/myweirdprompts-archive-keyring.gpg`, source `/etc/apt/sources.list.d/myweirdprompts.sources` (deb822) |

## How it works

```
app repo: tag v* -> workflow builds .deb, creates a GitHub release, sends repository_dispatch `publish`
this repo: scripts/sync_releases.py  adds any release .deb the pool lacks, prunes to 3 versions
           scripts/build.sh          pulls pool from R2, apt-ftparchive per arch, signs, syncs to R2
```

- `packages.yml` lists GitHub repos (`repo`, optional `tag_prefix`). The newest non-draft release
  whose tag starts with the prefix and that has a `.deb` is added to
  `pool/main/<p>/<Package>/<Package>_<Version>_<Arch>.deb`. The pool in R2 is the only state.
- `Architecture: all` packages are indexed in both `binary-amd64/Packages` and
  `binary-arm64/Packages` (`apt-ftparchive --arch X packages` includes `all`); `Release` lists
  `Architectures: amd64 arm64`. A package built for one arch only appears under that arch.
  `setup.sh` accepts amd64 and arm64 hosts only.
- Three versions per package kept; removing an entry from `packages.yml` deletes the package.
- Upload order: new `.deb`s, `dists/` (60 s cache), key/`setup.sh`/landing page, then pruning.
  The landing page is uploaded as `apt/index.html` and as the key `apt/` (R2 serves no directory index).

## Publish triggers

| Event | Effect |
|---|---|
| `repository_dispatch` type `publish` | rebuild (sent by MWP-Announcer's `desktop-release.yml` if secret `MWP_APT_DISPATCH_TOKEN` is set there) |
| `gh workflow run publish.yml -R My-Weird-Prompts/MWP-APT` | rebuild (manual) |
| push to `packages.yml`, `key.*`, `scripts/**`, `site/**`, the workflow | rebuild |

No schedule. **Manual step outstanding:** no fine-grained PAT for dispatch existed in 1Password,
so `MWP_APT_DISPATCH_TOKEN` is NOT set on MWP-Announcer. Until it is, after each `v*` release run
the `gh workflow run` line above. To automate: create a fine-grained PAT scoped to
`My-Weird-Prompts/MWP-APT` with Contents read+write (needed for the dispatches endpoint) and set
it with `gh secret set MWP_APT_DISPATCH_TOKEN -R My-Weird-Prompts/MWP-Announcer`.

## Adding a package

1. The app repo releases a `.deb` asset (public repo; for a private one set `RELEASES_READ_TOKEN`
   here, and think first: the `.deb` becomes public).
2. Add `- repo: My-Weird-Prompts/<Repo>` (plus `tag_prefix: v` if the repo also tags Android
   builds such as `android-v*`) to `packages.yml`, push. The push publishes.
3. `Version` in the control file must rise every release; `Package` names must be unique.

`My-Weird-Prompts/MWP-FM-Linux` (Package `mwp-fm`, `mwp-fm_1.0-1_all.deb` on v1.0) was private; Daniel had it
made public on 2026-11-17 and it is listed.

## Secrets (GitHub, this repo)

| Name | What |
|---|---|
| secret `APT_SIGNING_KEY` | ASCII-armoured private key. Master copy: 1Password vault Development, document "APT signing key - My Weird Prompts" |
| secret `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` | the R2 token MWP-FDroid uses (`CF_R2_KEY_ID` / `CF_R2_ACCESS_KEY` in `My-Weird-Prompts/.env.production`), write access to `mwppublic` (verified: lists the bucket) |
| variable `R2_ACCOUNT_ID`, `R2_BUCKET` | account ID above; `mwppublic` |
| secret `RELEASES_READ_TOKEN` (optional) | not set; `github.token` reads public repos |

**Losing the key means every user must replace the keyring by hand.** Never commit it.

## Running locally

```bash
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=... R2_ACCOUNT_ID=... R2_BUCKET=mwppublic
export GH_TOKEN=$(gh auth token) APT_SIGNING_KEY="$(op document get 'APT signing key - My Weird Prompts' --vault Development)"
FORCE=1 scripts/build.sh
```

Needs `apt-ftparchive` (`apt-utils`), `dpkg-deb`, `gpg`, `aws`, `gh`, `python3-yaml`.

## History

- 2026-11-17: created; first package `mwp-announcer` 2.0 from `MWP-Announcer` tag `v2.0`.
