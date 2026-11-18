# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The validator accepts the library and rejects terms that aren't current HuMeta terms."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import validate_library  # noqa: E402


def _vocabularies() -> str:
    """The HuMeta profile vocabularies from the HuMeta checkout the site builder uses."""
    import build_site
    path = build_site.HUMETA / "standard" / "humeta" / "vocabularies.json"
    if not path.is_file():
        pytest.skip("no HuMeta checkout with the profile")
    return str(path)


def _copy(tmp_path) -> Path:
    root = tmp_path / "library"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".humeta", "_site", "__pycache__"))
    return root


def test_library_is_valid():
    assert validate_library.main(ROOT, _vocabularies()) == 0


def test_validator_rejects_library_only_and_deprecated_terms(tmp_path):
    root = _copy(tmp_path)
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["disciplines"] = ["geoscience"]          # deprecated
    rec["education_levels"] = ["undergraduate"]  # the library's old term
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1


def test_unreadable_vocabularies_fail_when_named(tmp_path):
    assert validate_library.main(ROOT, str(tmp_path / "missing.json")) == 1


def test_instrument_metadata_codes_are_unique(tmp_path, capsys):
    root = _copy(tmp_path)
    path = root / "instruments" / "gci.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["metadata_code"] = "Pintrich1991"  # already the MSLQ's code
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1
    assert "metadata_code 'Pintrich1991'" in capsys.readouterr().out


def test_psyctests_ids_must_be_dois(tmp_path):
    root = _copy(tmp_path)
    path = root / "instruments" / "mslq.json"
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["identifiers"]["records"].append({"registry": "psyctests", "id": "9999-22083-000",
                                          "url": "https://doi.org/10.1037/t22083-000"})
    path.write_text(json.dumps(rec), encoding="utf-8")
    assert validate_library.main(root, _vocabularies()) == 1
