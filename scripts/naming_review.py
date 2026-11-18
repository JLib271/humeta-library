# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The governance committee's review of shared construct names.

One file per construct in governance/construct-names/<construct id>.yml: the evidence for the proposed
name (read-only) and the committee's decision (filled in by a reviewer, through a pull request).

  python scripts/naming_review.py create    # write a review file for every construct that has none
  python scripts/naming_review.py status    # how many are decided, and which are left
  python scripts/naming_review.py apply     # write decided reviews into constructs.json

Decisions:
  confirm        the proposed name stands (only for a construct with a proposed name)
  rename         another name, with the rule it follows (eric, icpsr, first_use) and its source
  reject         take the construct off the shared list (it is retired, never deleted, because
                 studies may use its id); replaced_by names the construct to use instead, if any
  research_more  not decided yet; say what to look for in comments

Decisions are normally reached by the committee in GitHub issues (scripts/naming_votes.py), which
writes them here with every member's vote.

Applying marks a confirmed or renamed construct's naming status "verified" and records the reviewer and
date. A renamed construct keeps its old name as a synonym, so studies that used it still match. Construct
ids never change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REVIEW_DIR = Path("governance") / "construct-names"
DECISIONS = ("confirm", "rename", "reject", "research_more")
FINAL = ("confirm", "rename", "reject")
EVIDENCE_MARK = "# The evidence for the name as proposed"
RULES = ("eric", "icpsr", "first_use")
RULE_TEXT = {"eric": "1. ERIC descriptor", "icpsr": "2. ICPSR term", "first_use": "3. First published use"}
DOI_RE = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.I)


def constructs(root: Path) -> list[dict]:
    return json.loads((root / "constructs.json").read_text(encoding="utf-8"))["constructs"]


def _block(key: str, text: str | None, indent: str = "  ") -> str:
    """A YAML folded block, wrapped for reading in a browser."""
    if not text:
        return f'{indent}{key}: ""\n'
    lines = textwrap.wrap(text, 96, break_long_words=False, break_on_hyphens=False)
    return f"{indent}{key}: >-\n" + "".join(f"{indent}  {line}\n" for line in lines)


def review_text(c: dict) -> str:
    """A new review file for one construct."""
    n = c.get("naming") or {}
    proposed = n.get("status") != "unresolved"
    source = (f'ERIC Thesaurus descriptor "{n.get("term")}"' if n.get("authority") == "eric"
              else f'ICPSR Subject Thesaurus term "{n.get("term")}"' if n.get("authority") == "icpsr"
              else n.get("citation") or "")
    link = n.get("url") or (f"https://doi.org/{n['doi']}" if n.get("doi") else "")
    q = json.dumps  # a double-quoted YAML string
    return (
        f"# Governance review of the name of the shared construct \"{c['label']}\" ({c['id']}).\n"
        "# Fill in the decision below and open a pull request. See README.md in this folder.\n"
        "\n"
        "decision:        # confirm, rename, reject, or research_more\n"
        "reviewer:        # your name\n"
        "reviewed_on:     # date, YYYY-MM-DD\n"
        "comments: \"\"\n"
        "\n"
        "# Only for rename:\n"
        "agreed_name: \"\"\n"
        "agreed_rule:     # eric, icpsr, or first_use\n"
        "agreed_source: \"\" # the ERIC or ICPSR term, or the full citation of the first published use\n"
        "agreed_link: \"\"   # the ERIC or ICPSR page, or the first use's DOI or address\n"
        "agreed_year:     # first use only\n"
        "\n"
        "# Only for reject:\n"
        "replaced_by:     # the id of the construct to use instead, if any\n"
        "\n"
        "# The evidence for the name as proposed (do not edit; it comes from constructs.json).\n"
        "proposed:\n"
        f"  construct_id: {c['id']}\n"
        f"  name: {q(c['label'], ensure_ascii=False)}\n"
        f"  status: {'proposed' if proposed else 'unresolved'}\n"
        f"  rule: {q(RULE_TEXT.get(n.get('authority'), '') if proposed else 'not found yet')}\n"
        + _block("source", source)
        + f"  year: {n.get('year') or q('')}\n"
        + f"  link: {q(link)}\n"
        + _block("notes_for_reviewers", n.get("note"))
        + _block("other_names", "; ".join(c.get("synonyms", [])))
        + _block("definition", c.get("definition"))
    )


def load_reviews(root: Path) -> dict[str, dict]:
    out = {}
    for path in sorted((root / REVIEW_DIR).glob("*.yml")):
        out[path.stem] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return out


def _date(value) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def problems(root: Path) -> list[str]:
    """What is wrong in the review files (checked on every pull request)."""
    if not (root / REVIEW_DIR).is_dir():
        return []
    by_id = {c["id"]: c for c in constructs(root)}
    issues = []
    for path in sorted((root / REVIEW_DIR).glob("*.yml")):
        where = f"{REVIEW_DIR.as_posix()}/{path.name}"
        try:
            r = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            issues.append(f"{where}: not valid YAML ({str(e).splitlines()[0]}). Check quotation marks and indentation.")
            continue
        c = by_id.get(path.stem)
        if c is None:
            issues.append(f"{where}: no construct with the id {path.stem!r} in constructs.json")
            continue
        decision = r.get("decision")
        if decision in (None, ""):
            continue
        if decision not in DECISIONS:
            issues.append(f"{where}: decision must be one of {', '.join(DECISIONS)}")
            continue
        if decision == "research_more":
            continue
        if not str(r.get("reviewer") or "").strip():
            issues.append(f"{where}: give the reviewer's name")
        if not _date(r.get("reviewed_on")):
            issues.append(f"{where}: reviewed_on must be a date, YYYY-MM-DD")
        if decision == "confirm" and (c.get("naming") or {}).get("status") == "unresolved":
            issues.append(f"{where}: there is no proposed name to confirm; choose rename (with its source) or research_more")
        if decision == "reject":
            rep = r.get("replaced_by")
            if rep and (rep not in by_id or rep == path.stem):
                issues.append(f"{where}: replaced_by must be the id of another construct in constructs.json")
        if decision == "rename":
            if not str(r.get("agreed_name") or "").strip():
                issues.append(f"{where}: give the agreed name")
            if r.get("agreed_rule") not in RULES:
                issues.append(f"{where}: agreed_rule must be one of {', '.join(RULES)}")
            if not str(r.get("agreed_source") or "").strip():
                issues.append(f"{where}: give the agreed name's source")
            if r.get("agreed_rule") == "first_use" and not str(r.get("agreed_year") or "").isdigit():
                issues.append(f"{where}: give the year of the first published use")
    return issues


def apply(root: Path) -> list[str]:
    """Write confirm and rename decisions into constructs.json. Returns what changed."""
    doc = json.loads((root / "constructs.json").read_text(encoding="utf-8"))
    reviews = load_reviews(root)
    changed = []
    for c in doc["constructs"]:
        r = reviews.get(c["id"]) or {}
        decision = r.get("decision")
        if decision not in FINAL:
            continue
        if decision == "reject":
            retired = {"on": _date(r["reviewed_on"]).isoformat(), "by": str(r["reviewer"]).strip()}
            if r.get("replaced_by"):
                retired["replaced_by"] = r["replaced_by"]
            if r.get("issue"):
                retired["review"] = r["issue"]
            if c.get("retired") != retired:
                c["retired"] = retired
                changed.append(f"{c['id']}: reject" + (f" -> {r['replaced_by']}" if r.get("replaced_by") else ""))
            continue
        naming = dict(c.get("naming") or {})
        if decision == "rename":
            name = str(r["agreed_name"]).strip()
            if name != c["label"]:
                synonyms = c.setdefault("synonyms", [])
                if c["label"] not in synonyms:
                    synonyms.insert(0, c["label"])
                c["label"] = name
            rule = r["agreed_rule"]
            naming = {"authority": rule, "term": name}
            link = str(r.get("agreed_link") or "").strip()
            doi = DOI_RE.match(link)
            if link:
                naming["url"] = f"https://doi.org/{doi.group(1)}" if doi else link
            if rule == "first_use":
                naming["citation"] = str(r["agreed_source"]).strip()
                if doi:
                    naming["doi"] = doi.group(1)
                naming["year"] = int(r["agreed_year"])
        naming.update({"status": "verified", "reviewed_by": str(r["reviewer"]).strip(),
                       "reviewed_on": _date(r["reviewed_on"]).isoformat()})
        if r.get("comments"):
            naming["note"] = str(r["comments"]).strip()
        if naming != c.get("naming"):
            c["naming"] = naming
            changed.append(f"{c['id']}: {decision} -> {c['label']}")
    (root / "constructs.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # A rejected construct keeps its persistent identifier, marked retired in identifiers.csv
    import assign_identifiers
    assign_identifiers.main(root)
    return changed


def write_decision(root: Path, construct_id: str, fields: dict) -> None:
    """Replace the decision part of a review file (everything above the evidence) with ``fields``."""
    path = root / REVIEW_DIR / f"{construct_id}.yml"
    text = path.read_text(encoding="utf-8")
    evidence = text[text.index(EVIDENCE_MARK):] if EVIDENCE_MARK in text else ""
    head = text.splitlines()[0] + "\n# Decided by the governance committee; the votes are recorded below.\n\n"
    body = yaml.safe_dump({k: v for k, v in fields.items() if v not in (None, "")}, sort_keys=False,
                          allow_unicode=True, width=100)
    path.write_text(head + body + "\n" + evidence, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The governance committee's review of shared construct names.")
    ap.add_argument("command", choices=["create", "status", "apply"])
    ap.add_argument("--library", type=Path, default=ROOT)
    args = ap.parse_args(argv)
    root = args.library
    if args.command == "create":
        folder = root / REVIEW_DIR
        folder.mkdir(parents=True, exist_ok=True)
        made = 0
        for c in constructs(root):
            path = folder / f"{c['id']}.yml"
            if not path.exists():
                path.write_text(review_text(c), encoding="utf-8")
                made += 1
        print(f"Wrote {made} review file(s) in {REVIEW_DIR.as_posix()}/")
        return 0
    issues = problems(root)
    if issues:
        print("\n".join(issues))
        return 1
    if args.command == "status":
        reviews = load_reviews(root)
        decided = {k: r["decision"] for k, r in reviews.items() if r.get("decision") in FINAL}
        left = sorted(set(reviews) - set(decided))
        print(f"{len(decided)} of {len(reviews)} decided "
              f"({sum(d == 'confirm' for d in decided.values())} confirmed, "
              f"{sum(d == 'rename' for d in decided.values())} renamed, "
              f"{sum(d == 'reject' for d in decided.values())} rejected).")
        if left:
            print("Left: " + ", ".join(left))
        return 0
    changed = apply(root)
    print("\n".join(changed) if changed else "Nothing to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
