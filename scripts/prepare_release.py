# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Package a release of the HuMeta Instrument Library for archiving.

Each release is deposited in the HuMeta Instrument Library sub-collection of the STEMEd+ Commons
Library, which keeps it permanently and gives it a DOI (one DOI for the library as a whole, and one
for each version). This writes everything the deposit needs:

  humeta-library-<version>.tar.gz   the library's records and schemas (the same archive the website
                                    publishes for the same files)
  humeta-library-<version>.json     manifest: version, date, commit, SHA-256 checksum, counts
  CITATION.cff                      how to cite this version
  deposit.md                        what to fill in on the deposit form
  notes.md                          release notes: counts and changes since the last release

Usage:
  python scripts/prepare_release.py --version 2026.11.18 --out _release

Versions are dates (YYYY.MM.DD, with .2, .3 ... for a second release the same day). The Release
workflow runs this when a tag v<version> is pushed and attaches the files to a GitHub release.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from library_archive import build_archive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^(\d{4})\.(\d{2})\.(\d{2})(\.\d+)?$")
REPO_URL = "https://github.com/JLib271/humeta-library"
SITE_URL = "https://jlib271.github.io/humeta-library/"
COLLECTION_URL = "https://works.hcommons.org/collections/humetainstrumentlibrary/"
PERSISTENT_BASE = "https://w3id.org/humeta/"


def check_version(version: str) -> str:
    """'v2026.11.18' or '2026.11.18' -> '2026.11.18'; anything else is an error."""
    version = version.strip().removeprefix("v")
    m = VERSION_RE.match(version)
    if not m:
        raise ValueError(f"Version {version!r} is not a date version like 2026.11.18 (or 2026.11.18.2).")
    try:
        dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        raise ValueError(f"Version {version!r} is not a real date.") from None
    return version


def counts(root: Path) -> dict[str, int]:
    def records(name: str, key: str) -> int:
        doc = json.loads((root / name).read_text(encoding="utf-8"))
        return len(doc.get(key, []) if isinstance(doc, dict) else doc)

    return {"instruments": len(list((root / "instruments").glob("*.json"))),
            "constructs": records("constructs.json", "constructs"),
            "frameworks": records("frameworks.json", "frameworks"),
            "evidence_records": len(list((root / "evidence").rglob("*.json"))),
            "item_files": len(list((root / "items").rglob("*.json")))}


def git(*args: str, root: Path = ROOT) -> str:
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def changes(root: Path, version: str) -> list[str]:
    """Commit subjects since the previous release tag (all commits if there is none)."""
    tags = [t for t in git("tag", "--list", "v*", "--sort=-creatordate", root=root).splitlines()
            if VERSION_RE.match(t.removeprefix("v")) and t.removeprefix("v") != version]
    span = [f"{tags[0]}..HEAD"] if tags else []
    return [s for s in git("log", "--no-merges", "--format=%s", *span, root=root).splitlines() if s]


def citation(root: Path, version: str, released: str) -> dict:
    cff = yaml.safe_load((root / "CITATION.cff").read_text(encoding="utf-8"))
    return {**cff, "version": version, "date-released": released}


def creators(cff: dict) -> list[str]:
    out = []
    for a in cff.get("authors", []):
        name = a.get("name") or f"{a.get('family-names', '')}, {a.get('given-names', '')}".strip(", ")
        out.append(name + (f" ({a['affiliation']})" if a.get("affiliation") else ""))
    return out


def prepare(root: Path, version: str, out: Path, released: str | None = None, commit: str | None = None) -> dict:
    """Write the release files to ``out``; return the manifest."""
    version = check_version(version)
    released = released or dt.date.today().isoformat()
    commit = commit if commit is not None else git("rev-parse", "HEAD", root=root)
    out.mkdir(parents=True, exist_ok=True)
    name = f"humeta-library-{version}"
    packed, n_files = build_archive(root)
    (out / f"{name}.tar.gz").write_bytes(packed)
    n = counts(root)
    manifest = {"format": "humeta-library-release", "title": "HuMeta Instrument Library", "version": version,
                "released": released, "commit": commit, "source": REPO_URL, "archive": f"{name}.tar.gz",
                "sha256": hashlib.sha256(packed).hexdigest(), "files": n_files, "counts": n,
                "license": "CC-BY-SA-4.0", "identifiers": PERSISTENT_BASE + "<instrument|construct|framework>/<pid>", "identifier_policy": REPO_URL + "/blob/main/IDENTIFIERS.md"}
    (out / f"{name}.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    cff = citation(root, version, released)
    (out / "CITATION.cff").write_text(yaml.safe_dump(cff, sort_keys=False, allow_unicode=True), encoding="utf-8")
    log = changes(root, version)
    summary = (f"{n['instruments']} instruments, {n['constructs']} shared constructs, {n['frameworks']} theories "
               f"and frameworks, {n['evidence_records']} evidence records, and {n['item_files']} item files")
    description = (
        f"Version {version} of the HuMeta Instrument Library: {summary}. The library describes research instruments "
        "used in education, social science, and humanities research: what each part measures (linked to a shared "
        "construct vocabulary), its versions and items, its reliability and validity evidence, and its terms of use. "
        "Records are JSON, with JSON Schemas, under CC BY-SA 4.0. Every instrument, instrument version, item, "
        f"construct, and theory has a persistent identifier ({PERSISTENT_BASE}...). The archive holds the records "
        f"and schemas; the manifest gives its SHA-256 checksum ({manifest['sha256']}).")
    (out / "notes.md").write_text(
        f"HuMeta Instrument Library {version}: {summary}.\n\n"
        f"Archive SHA-256: `{manifest['sha256']}`\n\n"
        + ("Changes since the last release:\n\n" + "\n".join(f"- {s}" for s in log) + "\n" if log else ""),
        encoding="utf-8")
    keywords = [*cff.get("keywords", []), "HuMeta", "metadata", "FAIR"]
    (out / "deposit.md").write_text(f"""# Deposit: HuMeta Instrument Library {version}

**Where:** the HuMeta Instrument Library sub-collection of the STEMEd+ Commons Library
({COLLECTION_URL}).

- **First release:** start a new upload and add it to the HuMeta Instrument Library collection.
- **Every later release:** open the library's existing record and choose **New version**, so the record
  keeps one DOI for the library as a whole and gets a new DOI for this version.

**Files:** `{name}.tar.gz`, `{name}.json`, `CITATION.cff`

| Field | Value |
|---|---|
| Resource type | Dataset |
| Title | HuMeta Instrument Library |
| Version | {version} |
| Publication date | {released} |
| Creators | {"; ".join(creators(cff))} |
| Description | {description} |
| Keywords | {"; ".join(keywords)} |
| License | Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0) |
| Related works | Is documented by: {SITE_URL} (URL) · Is supplemented by: {REPO_URL} (URL) · Is documented by: {PERSISTENT_BASE}metadata-code (URL) |

**After depositing:** add the library's DOI (the one for all versions) to `CITATION.cff` as `doi:`, so
later releases carry it.
""", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Package a HuMeta Instrument Library release for archiving.")
    ap.add_argument("--version", required=True, help="Date version, e.g. 2026.11.18 (a leading v is allowed)")
    ap.add_argument("--out", default="_release", type=Path)
    ap.add_argument("--library", default=ROOT, type=Path)
    args = ap.parse_args(argv)
    try:
        manifest = prepare(args.library, args.version, args.out)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"Release {manifest['version']}: {manifest['files']} files, sha256 {manifest['sha256']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
