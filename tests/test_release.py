# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A release packages the library reproducibly, with what its deposit needs."""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import library_archive  # noqa: E402
import prepare_release as R  # noqa: E402


def test_versions_are_dates():
    assert R.check_version("v2026.11.18") == "2026.11.18" and R.check_version("2026.11.18.2") == "2026.11.18.2"
    for bad in ("1.0.0", "2026.13.01", "2026.02.30", "v2026.11.18; rm -rf /"):
        with pytest.raises(ValueError):
            R.check_version(bad)


def test_release_files(tmp_path):
    manifest = R.prepare(ROOT, "2026.11.18", tmp_path, released="2026-11-18", commit="abc")
    archive = tmp_path / "humeta-library-2026.11.18.tar.gz"
    assert manifest["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.read_bytes() == library_archive.build_archive(ROOT)[0]  # the website's archive, byte for byte
    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert "library/constructs.json" in names and any(n.startswith("library/instruments/") for n in names)
    assert not any(n.startswith(("library/scripts", "library/tests", "library/site")) for n in names)
    assert json.loads((tmp_path / "humeta-library-2026.11.18.json").read_text())["counts"]["instruments"] >= 6
    cff = yaml.safe_load((tmp_path / "CITATION.cff").read_text())
    assert cff["version"] == "2026.11.18" and cff["date-released"] == "2026-11-18"
    deposit = (tmp_path / "deposit.md").read_text()
    assert "STEMEd+ Commons Library" in deposit and "New version" in deposit and "| Version | 2026.11.18 |" in deposit
    assert "Knowledge Commons" not in deposit
    assert manifest["sha256"] in (tmp_path / "notes.md").read_text()


def test_release_workflow_runs_the_script():
    flow = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    assert "prepare_release.py" in flow and "softwareheritage" in flow and 'tags: ["v*"]' in flow
