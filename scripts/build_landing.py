#!/usr/bin/env python3
"""Write the landing page (apt/index.html) from the built Packages index.

Usage: build_landing.py --packages <Packages> --owners <owners.json> --out <index.html>

One row per Package: every version in the index (newest first), the first line of the
control Description, Homepage if set, and the GitHub repo that ships it (from the owners
map written by sync_releases.py). All package-supplied text is HTML-escaped.
"""
import argparse
import functools
import json
import subprocess
from datetime import datetime, timezone
from html import escape
from pathlib import Path

BASE = "https://cdn.myweirdprompts.com/apt"
FPR = "500A7BDACD658CA3A0414E1FAB59AE3CED26BB79"


def stanzas(text):
    for block in text.strip().split("\n\n"):
        fields, key = {}, None
        for line in block.splitlines():
            if line[:1] in (" ", "\t") and key:
                continue  # continuation line (long Description); only the first line is used
            key, _, value = line.partition(":")
            fields[key] = value.strip()
        if fields.get("Package"):
            yield fields


def vercmp(a, b):
    if a == b:
        return 0
    return -1 if subprocess.call(["dpkg", "--compare-versions", a, "lt", b]) == 0 else 1


def link(url, text=None):
    return f'<a href="{escape(url, quote=True)}">{escape(text or url)}</a>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--packages", required=True)
    ap.add_argument("--owners", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    owners = json.loads(Path(args.owners).read_text())
    pkgs = {}
    for f in stanzas(Path(args.packages).read_text()):
        p = pkgs.setdefault(f["Package"], {"versions": [], "fields": f})
        p["versions"].append(f["Version"])
        newest = max(p["versions"], key=functools.cmp_to_key(vercmp))
        if f["Version"] == newest:
            p["fields"] = f

    rows = []
    for name in sorted(pkgs):
        p = pkgs[name]
        f = p["fields"]
        versions = sorted(p["versions"], key=functools.cmp_to_key(vercmp), reverse=True)
        links = []
        repo = owners.get(name)
        if repo:
            links.append(link(f"https://github.com/{repo}", repo))
        home = f.get("Homepage", "")
        if home and home.rstrip("/") != f"https://github.com/{repo}":
            links.append(link(home, "homepage"))
        rows.append(
            "<tr>"
            f'<td><code>{escape(name)}</code></td>'
            f'<td>{"<br>".join(escape(v) for v in versions)}</td>'
            f'<td>{escape(f.get("Description", ""))}</td>'
            f'<td>{"<br>".join(links)}</td>'
            "</tr>"
        )

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Weird Prompts APT repository</title>
<meta name="description" content="Signed APT repository for My Weird Prompts Linux packages (amd64, arm64).">
<style>
:root {{ --bg:#fff; --fg:#1b1f24; --muted:#59636e; --line:#d1d9e0; --code:#f2f4f7; --accent:#0b5cad; }}
@media (prefers-color-scheme: dark) {{
  :root {{ --bg:#0f1115; --fg:#e6e8eb; --muted:#9aa4af; --line:#2c323a; --code:#1a1e24; --accent:#6cb2ff; }}
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:960px; margin:0 auto; padding:32px 16px 64px; }}
h1 {{ font-size:1.6rem; margin:0 0 4px; }}
h2 {{ font-size:1.15rem; margin:32px 0 8px; }}
p.lede {{ color:var(--muted); margin:0 0 24px; }}
a {{ color:var(--accent); }}
pre, code {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; font-size:.9em; }}
pre {{ background:var(--code); border:1px solid var(--line); border-radius:6px; padding:12px; overflow-x:auto; white-space:pre; }}
.table {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:.95rem; }}
th, td {{ text-align:left; vertical-align:top; padding:8px 10px; border-bottom:1px solid var(--line); }}
th {{ color:var(--muted); font-weight:600; }}
td code {{ white-space:nowrap; }}
.note {{ border-left:3px solid var(--accent); padding:4px 12px; margin:16px 0; }}
footer {{ color:var(--muted); font-size:.85rem; margin-top:40px; }}
</style>
</head>
<body>
<main>
<h1>My Weird Prompts APT repository</h1>
<p class="lede">Signed APT repository for My Weird Prompts Linux packages, built from their GitHub releases. amd64 and arm64 (Raspberry Pi); Ubuntu / Debian.</p>

<h2>Set up</h2>
<pre>curl -fsSL {BASE}/setup.sh | sudo sh</pre>
<p>Add package names to install them in the same step:</p>
<pre>curl -fsSL {BASE}/setup.sh | sudo sh -s -- mwp-announcer</pre>
<p>The script checks the signing key's fingerprint, installs it to <code>/etc/apt/keyrings</code>, writes a deb822 source and runs <code>apt-get update</code>. {link(BASE + "/setup.sh", "Read it first")}.</p>

<h2>Manual setup</h2>
<pre>sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL {BASE}/key.gpg | sudo tee /etc/apt/keyrings/myweirdprompts-archive-keyring.gpg &gt;/dev/null
gpg --show-keys /etc/apt/keyrings/myweirdprompts-archive-keyring.gpg   # fingerprint below
sudo tee /etc/apt/sources.list.d/myweirdprompts.sources &gt;/dev/null &lt;&lt;'EOF'
Types: deb
URIs: {BASE}
Suites: stable
Components: main
Architectures: amd64 arm64
Signed-By: /etc/apt/keyrings/myweirdprompts-archive-keyring.gpg
EOF
sudo apt update</pre>
<p>Signing key (RSA 4096): <code>{FPR}</code><br>{link(BASE + "/key.gpg", "key.gpg")} · {link(BASE + "/key.asc", "key.asc")}</p>

<h2>Packages</h2>
<div class="table"><table>
<thead><tr><th>Package</th><th>Version</th><th>Description</th><th>Source</th></tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody>
</table></div>
<p>Android apps: the {link("https://cdn.myweirdprompts.com/fdroid/repo", "MWP F-Droid repository")}.</p>

<footer>Index built {built}. Source: {link("https://github.com/My-Weird-Prompts/MWP-APT", "My-Weird-Prompts/MWP-APT")} · {link("https://myweirdprompts.com")}</footer>
</main>
</body>
</html>
"""
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(html)


if __name__ == "__main__":
    main()
