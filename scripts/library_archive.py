# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The library's own files as one reproducible archive.

Used by the website (data/library.tar.gz, which the HuMeta Portal reads) and by releases
(scripts/prepare_release.py), so a release archive is byte-for-byte the archive the website
published for the same files. Needs only the standard library.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from pathlib import Path

#: What the archive holds: the records and schemas, not scripts, tests, or the website
DATA_DIRS = ("instruments", "items", "evidence", "schema")
DATA_FILES = ("constructs.json", "frameworks.json", "identifiers.csv", "scales.json", "standard_variables.json",
              "evidence_rubric.json", "LICENSE.md")


def archive_paths(root: Path) -> list[Path]:
    """The library files that go into the archive, sorted."""
    paths = [root / name for name in DATA_FILES if (root / name).is_file()]
    for folder in DATA_DIRS:
        paths += [p for p in (root / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def build_archive(root: Path) -> tuple[bytes, int]:
    """(gzipped tar of the library's files under library/, number of files).

    The same files always give the same bytes: sorted, no times or owners, gzip without a timestamp.
    """
    paths = archive_paths(root)
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for path in paths:
            info = tarfile.TarInfo("library/" + path.relative_to(root).as_posix())
            content = path.read_bytes()
            info.size, info.mode, info.mtime = len(content), 0o644, 0
            tar.addfile(info, io.BytesIO(content))
    return gzip.compress(raw.getvalue(), mtime=0), len(paths)
