# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The committee's construct-name review: votes in issue comments, lazy consensus, approval, apply."""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import naming_review as NR  # noqa: E402
import naming_votes as V  # noqa: E402

TODAY = dt.date(2026, 12, 1)
DEADLINE = dt.date(2026, 12, 10)
AFTER = dt.date(2026, 12, 11)


def test_votes_are_read_from_comments():
    assert V.parse_vote("I agree.\n/vote confirm") == {"choice": "confirm"}
    assert V.parse_vote("/vote Research more\nCheck the 1989 report.") == {"choice": "research_more"}
    v = V.parse_vote("/vote rename\nname: Self-efficacy\nrule: First use\nsource: Bandura (1977)\nyear: 1977")
    assert v == {"choice": "rename", "name": "Self-efficacy", "rule": "first_use", "source": "Bandura (1977)",
                 "year": "1977"}
    assert V.parse_vote('/vote rename "Science identity"')["name"] == "Science identity"
    assert V.parse_vote("/vote reject\nreplaced_by: interest") == {"choice": "reject", "replaced_by": "interest"}
    assert V.parse_vote("/vote confirm\n...later...\n/vote reject")["choice"] == "reject"  # the last one counts
    assert V.parse_vote("no vote here") is None and V.parse_vote("I'd /vote confirm") is None


MEMBERS = {"ana", "raj", "lee"}


def test_lazy_consensus():
    t = V.tally
    assert t({}, MEMBERS, True, DEADLINE, TODAY)["state"] == "open"
    assert t({}, MEMBERS, True, DEADLINE, AFTER)["outcome"] == {"decision": "confirm"}  # silence is consent
    assert t({}, MEMBERS, False, DEADLINE, AFTER)["state"] == "no_proposal"
    one = {"ana": {"choice": "confirm"}}
    assert t(one, MEMBERS, True, DEADLINE, TODAY)["state"] == "open"  # agreeing so far
    assert t(one, MEMBERS, True, DEADLINE, AFTER)["state"] == "consensus"
    allc = {m: {"choice": "confirm"} for m in MEMBERS}
    assert t(allc, MEMBERS, True, DEADLINE, TODAY)["state"] == "consensus"  # everyone voted: early
    split = {"ana": {"choice": "confirm"}, "raj": {"choice": "reject"}}
    assert t(split, MEMBERS, True, DEADLINE, AFTER)["state"] == "needs_discussion"
    research = {"ana": {"choice": "confirm"}, "raj": {"choice": "research_more"}}
    assert t(research, MEMBERS, True, DEADLINE, AFTER)["state"] == "needs_discussion"
    outsider = {"zed": {"choice": "reject"}}  # not on the committee: not counted
    assert t(outsider, MEMBERS, True, DEADLINE, AFTER)["outcome"] == {"decision": "confirm"}
    rename = {"ana": {"choice": "rename", "name": "Self-efficacy", "rule": "first_use",
                      "source": "Bandura (1977)", "year": "1977"},
              "raj": {"choice": "rename", "name": "self-efficacy"}}
    r = t(rename, MEMBERS, True, DEADLINE, AFTER)
    assert r["state"] == "consensus" and r["outcome"]["name"] == "Self-efficacy" and r["outcome"]["year"] == "1977"
    no_source = {"ana": {"choice": "rename", "name": "X", "rule": "eric"}}
    assert "source" in t(no_source, MEMBERS, True, DEADLINE, AFTER)["reason"]
    assert t({"ana": {"choice": "confirm"}}, MEMBERS, False, DEADLINE, AFTER)["state"] == "needs_discussion"
    rej = t({"ana": {"choice": "reject", "replaced_by": "interest"}}, MEMBERS, True, DEADLINE, AFTER)
    assert rej["outcome"] == {"decision": "reject", "replaced_by": "interest"}


class FakeGitHub:
    """Issues and comments in memory, as the GitHub API returns them."""

    def __init__(self):
        self.issue_list, self.comment_list, self.labels = [], {}, set()

    def issues(self, label, state="open"):
        return [i for i in self.issue_list if label in {x["name"] for x in i["labels"]}
                and (state == "all" or i["state"] == state)]

    def comments(self, number):
        return self.comment_list.get(number, [])

    def ensure_label(self, name, color=""):
        self.labels.add(name)

    def create_issue(self, title, body, labels):
        n = len(self.issue_list) + 1
        issue = {"number": n, "title": title, "body": body, "state": "open", "html_url": f"https://x/issues/{n}",
                 "labels": [{"name": x} for x in labels]}
        self.issue_list.append(issue)
        return issue

    def update_issue(self, number, **fields):
        issue = next(i for i in self.issue_list if i["number"] == number)
        if "body" in fields:
            issue["body"] = fields["body"]
        if "labels" in fields:
            issue["labels"] = [{"name": x} for x in fields["labels"]]
        return issue

    def comment(self, number, login, body):
        lst = self.comment_list.setdefault(number, [])
        lst.append({"user": {"login": login}, "body": body, "created_at": f"2026-12-01T00:00:{len(lst):02d}Z",
                    "html_url": f"https://x/issues/{number}#c{len(lst)}"})


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "library"
    shutil.copytree(ROOT, root, ignore=shutil.ignore_patterns(".git", ".humeta", "_site", "__pycache__", "_release"))
    (root / "governance" / "committee.yml").write_text(yaml.safe_dump({
        "chair": [{"name": "Chair Person", "github": "Chair"}],
        "members": [{"name": "Ana", "github": "ana"}, {"name": "Raj", "github": "raj"}]}), encoding="utf-8")
    return root


def number_of(gh, cid):
    return next(i["number"] for i in gh.issue_list if f"<!-- construct: {cid} -->" in i["body"])


def test_a_round_from_opening_to_applying(library):
    gh = FakeGitHub()
    made = V.open_round(gh, library, DEADLINE, ["self_efficacy", "epistemological_beliefs", "interest", "anxiety"])
    assert len(made) == 4 and V.open_round(gh, library, DEADLINE) and len(gh.issue_list) == 32  # no duplicates
    se, eb, it = number_of(gh, "self_efficacy"), number_of(gh, "epistemological_beliefs"), number_of(gh, "interest")
    issue = gh.issue_list[se - 1]
    assert "**Deadline:** 2026-12-10" in issue["body"] and "Self Efficacy" in issue["body"]
    # Self Efficacy: everyone confirms early. Epistemological beliefs: renamed. Interest: rejected.
    for who in ("chair", "ana", "raj"):
        gh.comment(se, who, "/vote confirm")
    gh.comment(eb, "ana", "/vote rename\nname: Epistemic beliefs\nrule: first_use\n"
                          "source: Schommer, M. (1989). Students' beliefs about knowledge.\nyear: 1989")
    gh.comment(it, "raj", "/vote reject\nreplaced_by: engagement")
    gh.comment(it, "stranger", "/vote confirm")  # not a member: ignored
    rows = {r["construct"]: r for r in V.update_all(gh, library, TODAY)}
    assert rows["self_efficacy"]["state"] == "consensus" and rows["epistemological_beliefs"]["state"] == "awaiting votes"
    assert "Status: consensus" in gh.issue_list[se - 1]["body"] and "3 of 3 members have voted" in gh.issue_list[se - 1]["body"]
    progress = gh.issues(V.PROGRESS_LABEL)[0]["body"]
    assert "32 under review now" in progress and "Self Efficacy" in progress
    # After the deadline: the other two reach consensus; the chair approves three of them.
    for n in (se, eb, it):
        gh.comment(n, "chair", "/approve")
    gh.comment(number_of(gh, "anxiety"), "ana", "/approve")  # a member is not a chair: no effect
    rows = {r["construct"]: r for r in V.update_all(gh, library, AFTER)}
    assert all(rows[c]["approved"] for c in ("self_efficacy", "epistemological_beliefs", "interest"))
    assert not rows["anxiety"]["approved"]
    applied = V.apply_approved(gh, library, AFTER)
    assert sorted(a["construct"] for a in applied) == ["epistemological_beliefs", "interest", "self_efficacy"]
    cons = {c["id"]: c for c in json.loads((library / "constructs.json").read_text())["constructs"]}
    assert cons["self_efficacy"]["naming"]["status"] == "verified" and cons["self_efficacy"]["naming"]["reviewed_by"] == "Chair Person"
    eb_c = cons["epistemological_beliefs"]
    assert eb_c["label"] == "Epistemic beliefs" and "Epistemological beliefs" in eb_c["synonyms"]
    assert eb_c["naming"]["year"] == 1989 and eb_c["naming"]["authority"] == "first_use"
    assert cons["interest"]["retired"]["replaced_by"] == "engagement"
    record = yaml.safe_load((library / "governance" / "construct-names" / "interest.yml").read_text())
    assert record["decision"] == "reject" and [v["github"] for v in record["votes"]] == ["raj"]
    assert record["proposed"]["construct_id"] == "interest"  # the evidence is kept
    assert NR.problems(library) == []
    assert V.apply_approved(gh, library, AFTER) == []  # applied once only


def test_review_files_are_checked(library):
    path = library / "governance" / "construct-names" / "anxiety.yml"
    text = path.read_text()
    path.write_text(text.replace("decision:        #", "decision: confirm #", 1))
    assert any("no proposed name to confirm" in p for p in NR.problems(library))
    path.write_text(text.replace("decision:        #", "decision: maybe #", 1))
    assert any("decision must be one of" in p for p in NR.problems(library))
    path.write_text("decision: [unclosed")
    assert any("not valid YAML" in p for p in NR.problems(library))


def test_every_construct_has_a_review_file():
    ids = {c["id"] for c in json.loads((ROOT / "constructs.json").read_text())["constructs"]}
    files = {p.stem for p in (ROOT / "governance" / "construct-names").glob("*.yml")}
    assert files == ids
    for p in (ROOT / "governance" / "construct-names").glob("*.yml"):
        assert yaml.safe_load(p.read_text())["proposed"]["construct_id"] == p.stem
