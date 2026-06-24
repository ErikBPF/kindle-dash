#!/usr/bin/env python3
"""opencode-capture — pull OpenCode Go dashboard credentials from a logged-in
Chromium-family browser (Brave/Chromium/Chrome/Edge/Vivaldi) on Linux.

OpenCode exposes no usage API, so the kindle-dash `opencode` widget scrapes the
Go dashboard, which needs a workspace id + the site's `auth` session cookie
(see CONFIGURATION.md). That cookie is HttpOnly and rotates every few days, so
re-grabbing it by hand via DevTools gets old fast. This reads it straight from
the browser's encrypted cookie store the way opencode-bar does — re-run it
whenever the widget goes "(stale)".

  python3 tools/opencode-capture.py            # print the two env lines
  python3 tools/opencode-capture.py -o creds.env   # append them to a file

Linux only (Chromium 'v10'/'v11' cookie encryption via the Secret Service).
Needs: cryptography, secret-tool, sqlite3.
"""
import argparse
import glob
import hashlib
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# (config dir, Secret Service "application" attribute) per browser family.
BROWSERS = [
    ("BraveSoftware/Brave-Browser", "brave"),
    ("google-chrome", "chrome"),
    ("chromium", "chromium"),
    ("microsoft-edge", "chrome"),
    ("vivaldi", "chrome"),
]
HOST = "opencode.ai"


def _keyring_secret(app):
    """The browser's 'Safe Storage' password from the Secret Service."""
    try:
        out = subprocess.run(
            ["secret-tool", "lookup", "application", app],
            capture_output=True, timeout=10,
        )
        return out.stdout or None
    except Exception:
        return None


def _decrypt(enc, secret):
    """Decrypt a Chromium v10/v11 cookie value to plaintext, or None."""
    if not enc:
        return None
    prefix, body = enc[:3], enc[3:]
    if prefix not in (b"v10", b"v11"):
        return None  # unencrypted (rare on Linux) — caller handles
    pw = secret if prefix == b"v11" else b"peanuts"  # v10 = no keyring
    if pw is None:
        return None
    key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1, 16)
    try:
        dec = Cipher(algorithms.AES(key), modes.CBC(b" " * 16)).decryptor()
        pt = dec.update(body) + dec.finalize()
        pt = pt[: -pt[-1]]  # strip PKCS7 padding
    except Exception:
        return None
    # Chrome ≥130 prepends a 32-byte SHA256(domain); strip it when the raw
    # plaintext isn't clean UTF-8 but the tail is.
    for cand in (pt, pt[32:]):
        try:
            s = cand.decode("utf-8")
            if s.isprintable():
                return s
        except Exception:
            continue
    return pt.decode("utf-8", "replace")


def _query(db, sql):
    """Read a (browser-locked) sqlite DB by copying it first."""
    if not os.path.exists(db):
        return []
    with tempfile.TemporaryDirectory() as tmp:
        c = os.path.join(tmp, "db")
        shutil.copy2(db, c)
        try:
            con = sqlite3.connect(c)
            rows = con.execute(sql).fetchall()
            con.close()
            return rows
        except Exception:
            return []


def _profiles(base):
    return [os.path.dirname(p) for p in
            glob.glob(os.path.join(base, "*", "Cookies"))]


def capture():
    for sub, app in BROWSERS:
        base = os.path.join(os.path.expanduser("~/.config"), sub)
        if not os.path.isdir(base):
            continue
        for prof in _profiles(base):
            cookies = os.path.join(prof, "Cookies")
            rows = _query(
                cookies,
                f"SELECT encrypted_value FROM cookies "
                f"WHERE host_key LIKE '%{HOST}%' AND name='auth'",
            )
            if not rows:
                continue
            secret = _keyring_secret(app)
            value = _decrypt(rows[0][0], secret)
            if not value:
                print(f"[{app}/{os.path.basename(prof)}] found auth cookie but "
                      f"could not decrypt (keyring locked?)", file=sys.stderr)
                continue
            # workspace id from this profile's browsing history
            ws = None
            for (url,) in _query(
                os.path.join(prof, "History"),
                "SELECT url FROM urls WHERE url LIKE '%/workspace/wrk_%' "
                "ORDER BY last_visit_time DESC LIMIT 50",
            ):
                m = re.search(r"/workspace/(wrk_[A-Za-z0-9]+)", url)
                if m:
                    ws = m.group(1)
                    break
            return app, os.path.basename(prof), ws, value
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", help="append the env lines to this file")
    args = ap.parse_args()

    res = capture()
    if not res:
        print(f"No '{HOST}' auth cookie found in any Chromium-family browser. "
              f"Log in at https://{HOST} (and open the Go dashboard once), then "
              f"re-run.", file=sys.stderr)
        sys.exit(1)

    app, prof, ws, value = res
    print(f":: captured from {app}/{prof}"
          + (f", workspace {ws}" if ws else ", workspace id NOT found in history"),
          file=sys.stderr)
    lines = []
    if ws:
        lines.append(f"KINDLE_DASH_OPENCODE_WORKSPACE_ID={ws}")
    else:
        print("   → open https://opencode.ai/workspace/<id>/go in this browser "
              "once so the id lands in history, or set it by hand.",
              file=sys.stderr)
    lines.append(f"KINDLE_DASH_OPENCODE_AUTH_COOKIE={value}")

    if args.out:
        with open(args.out, "a") as f:
            f.write("\n".join(lines) + "\n")
        print(f":: appended {len(lines)} line(s) to {args.out}", file=sys.stderr)
    else:
        print("\n".join(lines))


if __name__ == "__main__":
    main()
