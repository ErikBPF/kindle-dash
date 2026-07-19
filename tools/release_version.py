#!/usr/bin/env python3
"""Fail-closed release-label and SemVer calculation."""
import argparse
import re


LABELS = {
    "release:major": "major",
    "release:minor": "minor",
    "release:patch": "patch",
    "release:none": "none",
}
VERSION = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def release_kind(labels):
    selected = sorted(set(labels) & LABELS.keys())
    if len(selected) > 1:
        raise ValueError(f"conflicting release labels: {', '.join(selected)}")
    return LABELS[selected[0]] if selected else "minor"


def latest_version(tags):
    versions = [
        tuple(int(part) for part in match.groups())
        for tag in tags
        if (match := VERSION.fullmatch(tag))
    ]
    return max(versions, default=(0, 0, 0))


def next_version(tags, labels):
    kind = release_kind(labels)
    if kind == "none":
        return None
    major, minor, patch = latest_version(tags)
    if kind == "major":
        return f"v{major + 1}.0.0"
    if kind == "minor":
        return f"v{major}.{minor + 1}.0"
    return f"v{major}.{minor}.{patch + 1}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", action="append", default=[])
    parser.add_argument("--label", action="append", default=[])
    args = parser.parse_args()
    result = next_version(args.tag, args.label)
    print(result or "none")


if __name__ == "__main__":
    main()
