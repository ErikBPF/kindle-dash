#!/usr/bin/env python3
"""Update the single immutable kindle-dash image pin in Servarr."""

import argparse
import re
from pathlib import Path

PIN = re.compile(
    r"(?m)^(?P<prefix>\s*image: "
    r"harbor\.homelab\.pastelariadev\.com/library/kindle-dash:)"
    r"v?\d+\.\d+\.\d+@sha256:[0-9a-f]{64}$"
)
VERSION = re.compile(r"v\d+\.\d+\.\d+")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def update_pin(path: Path, version: str, digest: str) -> None:
    if not VERSION.fullmatch(version):
        raise ValueError(f"invalid version: {version}")
    if not DIGEST.fullmatch(digest):
        raise ValueError(f"invalid digest: {digest}")

    original = path.read_text()
    updated, count = PIN.subn(rf"\g<prefix>{version}@{digest}", original)
    if count != 1:
        raise ValueError(f"expected one kindle-dash image pin, found {count}")
    if updated == original:
        raise ValueError("kindle-dash image pin is already current")
    path.write_text(updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("version")
    parser.add_argument("digest")
    args = parser.parse_args()
    update_pin(args.path, args.version, args.digest)


if __name__ == "__main__":
    main()
