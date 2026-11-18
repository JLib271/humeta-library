# Copyright (C) 2026 Julie C. Libarkin
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Construct-name review by the governance committee, in GitHub issues.

Each construct under review has one issue (label ``name-review``) that shows the evidence for its
proposed name. Committee members (governance/committee.yml) vote by commenting:

  /vote confirm                  keep the proposed name
  /vote rename                   another name; add lines  name: ...  rule: eric|icpsr|first_use
                                 source: ...  link: ...  year: ...
  /vote reject                   take the construct off the shared list; optionally  replaced_by: <id>
  /vote research_more            not ready to decide; say what to look for

A member's latest vote counts. Consensus is lazy: at the issue's deadline, the outcome is the one that
every vote cast agrees on (with no votes, a proposed name stands); a research_more vote or any
disagreement keeps the issue open for discussion. If every member has voted and all agree, consensus
comes before the deadline. A chair then comments /approve, and the Apply workflow writes the decision
into governance/construct-names/<id>.yml and constructs.json in a pull request.

  python scripts/naming_votes.py open --deadline 2026-12-15 [--constructs id ...]
  python scripts/naming_votes.py tally
  python scripts/naming_votes.py remind      # 3 days before a deadline: mention members who have not voted
  python scripts/naming_votes.py digest      # weekly: one comment on the progress issue mentioning every member
  python scripts/naming_votes.py apply

GitHub emails people when a comment mentions them, so the digest and reminders reach members by email
(with GitHub's default notification settings).

open, tally and apply call the GitHub API with GITHUB_TOKEN for GITHUB_REPOSITORY.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import naming_review as NR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
COMMITTEE = Path("governance") / "committee.yml"
LABEL = "name-review"
PROGRESS_LABEL = "name-review-progress"
STATE_LABELS = {"open": "awaiting votes", "needs_discussion": "needs discussion", "consensus": "consensus",
                "no_proposal": "needs a proposal"}
APPROVED_LABEL, APPLIED_LABEL = "approved", "applied"
CHOICES = ("confirm", "rename", "reject", "research_more")
VOTE_RE = re.compile(r"^\s*/vote\s+(confirm|rename|reject|research[ _-]?more)\b[ \t:]*(.*)$", re.I | re.M)
FIELD_RE = re.compile(r"^\s*(name|rule|source|link|year|replaced_by)\s*:\s*(.+?)\s*$", re.I)
APPROVE_RE = re.compile(r"^\s*/approve\b", re.I | re.M)
DEADLINE_RE = re.compile(r"^\*\*Deadline:\*\*\s*(\d{4}-\d{2}-\d{2})", re.M)
CONSTRUCT_RE = re.compile(r"<!-- construct: ([a-z0-9_]+) -->")
TALLY_START, TALLY_END = "<!-- humeta-tally -->", "<!-- /humeta-tally -->"
REMINDER_MARK, DIGEST_MARK = "<!-- humeta-reminder -->", "<!-- humeta-digest -->"
REMIND_DAYS = 3


# ---------------------------------------------------------------- votes and consensus
def parse_vote(text: str) -> dict | None:
    """The last /vote in a comment, with its fields; None if the comment has no vote."""
    matches = list(VOTE_RE.finditer(text or ""))
    if not matches:
        return None
    m = matches[-1]
    choice = re.sub(r"[ _-]", "_", m.group(1).lower())
    choice = "research_more" if choice.startswith("research") else choice
    vote: dict = {"choice": choice}
    rest = m.group(2).strip()
    if choice == "rename" and rest:
        vote["name"] = rest.strip('"“”')
    for line in (text or "")[m.end():].splitlines()[1:]:
        if line.strip().startswith("/"):
            break
        f = FIELD_RE.match(line)
        if f:
            vote[f.group(1).lower()] = f.group(2).strip().strip('"“”')
    if vote.get("rule"):
        vote["rule"] = vote["rule"].lower().replace(" ", "_").replace("-", "_")
    return vote


def _key(vote: dict) -> tuple:
    if vote["choice"] == "rename":
        return ("rename", (vote.get("name") or "").strip().lower())
    if vote["choice"] == "reject":
        return ("reject", (vote.get("replaced_by") or "").strip().lower())
    return (vote["choice"],)


def tally(votes: dict[str, dict], members: set[str], proposed: bool, deadline: dt.date | None,
          today: dt.date) -> dict:
    """Lazy consensus over committee members' latest votes.

    Returns state (open | needs_discussion | consensus | no_proposal), outcome (for consensus: a
    decision with its fields), and a one-line reason.
    """
    counted = {m: v for m, v in votes.items() if m in members}
    passed = deadline is not None and today > deadline
    keys = {_key(v) for v in counted.values()}
    if any(v["choice"] == "research_more" for v in counted.values()):
        return {"state": "needs_discussion", "outcome": None,
                "reason": "A member asked for more research; discuss, then change votes."}
    if len(keys) > 1:
        return {"state": "needs_discussion", "outcome": None,
                "reason": "Votes differ; discuss until they agree (a member's latest vote counts)."}
    if not counted:
        if passed and proposed:
            return {"state": "consensus", "outcome": {"decision": "confirm"},
                    "reason": "No objection by the deadline: the proposed name stands."}
        if passed:
            return {"state": "no_proposal", "outcome": None,
                    "reason": "No proposed name and no votes: a member needs to propose one (/vote rename)."}
        return {"state": "open", "outcome": None, "reason": "Waiting for votes."}
    if not (passed or members <= set(counted)):
        return {"state": "open", "outcome": None,
                "reason": "Votes agree so far; consensus at the deadline unless someone objects."}
    choice = next(iter(counted.values()))["choice"]
    outcome: dict = {"decision": choice}
    if choice == "confirm" and not proposed:
        return {"state": "needs_discussion", "outcome": None,
                "reason": "There is no proposed name to confirm: propose one with /vote rename, or reject."}
    if choice == "rename":
        for field in ("name", "rule", "source", "link", "year"):
            outcome[field] = next((v[field] for v in counted.values() if v.get(field)), None)
        missing = [f for f in ("name", "rule", "source") if not outcome.get(f)]
        if outcome.get("rule") not in NR.RULES:
            missing.append("rule (eric, icpsr, or first_use)")
        if outcome.get("rule") == "first_use" and not str(outcome.get("year") or "").isdigit():
            missing.append("year")
        if missing:
            return {"state": "needs_discussion", "outcome": None,
                    "reason": "The rename needs " + ", ".join(dict.fromkeys(missing)) + "."}
    if choice == "reject":
        outcome["replaced_by"] = next((v["replaced_by"] for v in counted.values() if v.get("replaced_by")), None)
    return {"state": "consensus", "outcome": outcome,
            "reason": "Every vote agrees" + (" and the deadline has passed." if passed else ", and every member voted.")}


def describe(outcome: dict | None) -> str:
    if not outcome:
        return ""
    d = outcome["decision"]
    if d == "rename":
        return f'rename to "{outcome["name"]}" ({outcome["rule"]}: {outcome["source"]})'
    if d == "reject":
        return "reject" + (f" (replaced by {outcome['replaced_by']})" if outcome.get("replaced_by") else "")
    return "confirm the proposed name"


# ---------------------------------------------------------------- committee and issues
def load_committee(root: Path) -> dict:
    doc = yaml.safe_load((root / COMMITTEE).read_text(encoding="utf-8")) or {}
    people = {}
    for role in ("chair", "members"):
        for p in doc.get(role) or []:
            people[str(p["github"]).lower()] = {"name": p.get("name") or p["github"], "chair": role == "chair"}
    return people


def issue_body(review: dict, deadline: dt.date) -> str:
    """A new review issue: the evidence, how to vote, the deadline, and room for the tally."""
    p = review["proposed"]
    proposed = p.get("status") == "proposed"
    rows = [("Construct id", f"`{p['construct_id']}`"), ("Proposed name", p["name"] if proposed else "none yet"),
            ("Naming rule", p.get("rule") or ""), ("Source", p.get("source") or ""), ("Year", str(p.get("year") or "")),
            ("Link", p.get("link") or ""), ("Notes for reviewers", p.get("notes_for_reviewers") or ""),
            ("Other names", p.get("other_names") or ""), ("Definition", p.get("definition") or "")]
    table = "\n".join(f"| {k} | {str(v).replace('|', '/')} |" for k, v in rows if v)
    return f"""<!-- construct: {p['construct_id']} -->
**Deadline:** {deadline.isoformat()}

The governance committee is reviewing the official name of this shared construct. The naming rule: (1) an ERIC Thesaurus descriptor with exactly the same meaning, written as ERIC writes it; else (2) an ICPSR Subject Thesaurus term with exactly the same meaning; else (3) the name as first published. Exact meaning only.

| | |
|---|---|
{table}

### How to vote

Committee members: comment with one of these (your latest vote counts; discuss freely in other comments).

```
/vote confirm
```
```
/vote rename
name: Self-efficacy
rule: first_use
source: Bandura, A. (1977). Self-efficacy: Toward a unifying theory of behavioral change. Psychological Review, 84(2), 191-215.
link: https://doi.org/10.1037/0033-295X.84.2.191
year: 1977
```
```
/vote reject
replaced_by: another_construct_id
```
```
/vote research_more
```

**Consensus (lazy):** at the deadline, the outcome is the one every vote agrees on; with no votes, a proposed name stands. A `research_more` vote or any disagreement keeps this open for discussion. If every member votes and all agree, consensus comes early. A chair then comments `/approve`, and the decision goes into the library in a pull request.

{TALLY_START}
_The tally appears here._
{TALLY_END}
"""


def tally_block(status: dict, votes: dict[str, dict], people: dict, deadline: dt.date | None,
                approved_by: list[str], links: dict[str, str]) -> str:
    members = {k: v for k, v in people.items()}
    rows = []
    for login, person in sorted(members.items(), key=lambda kv: kv[1]["name"].lower()):
        v = votes.get(login)
        what = "—" if not v else (v["choice"].replace("_", " ") + (f": {v['name']}" if v.get("name") else "")
                                   + (f" → {v['replaced_by']}" if v.get("replaced_by") else ""))
        rows.append(f"| {person['name']} (@{login}){' (chair)' if person['chair'] else ''} | {what} |"
                    + (f" [comment]({links[login]}) |" if login in links else " |"))
    state = STATE_LABELS[status["state"]]
    head = f"**Status: {state}.** {status['reason']}"
    if status["state"] == "consensus":
        head += f"\n\n**Outcome:** {describe(status['outcome'])}." + (
            f" Approved by {', '.join(approved_by)}." if approved_by else " Waiting for a chair to comment `/approve`.")
    return (f"{TALLY_START}\n### Tally (updated {dt.date.today().isoformat()})\n\n{head}\n\n"
            f"{len([m for m in members if m in votes])} of {len(members)} members have voted"
            + (f"; deadline {deadline.isoformat()}" if deadline else "") + ".\n\n"
            "| Member | Latest vote | |\n|---|---|---|\n" + "\n".join(rows) + f"\n{TALLY_END}")


def replace_tally(body: str, block: str) -> str:
    if TALLY_START in body and TALLY_END in body:
        return body[:body.index(TALLY_START)] + block + body[body.index(TALLY_END) + len(TALLY_END):]
    return body.rstrip() + "\n\n" + block + "\n"


def read_issue(issue: dict, comments: list[dict], people: dict, today: dt.date, proposed: bool) -> dict:
    """Votes, approvals, and the tally of one review issue."""
    body = issue.get("body") or ""
    m = DEADLINE_RE.search(body)
    deadline = dt.date.fromisoformat(m.group(1)) if m else None
    votes, links, approvals = {}, {}, []
    for c in sorted(comments, key=lambda c: c.get("created_at") or ""):
        login = ((c.get("user") or {}).get("login") or "").lower()
        if login not in people:
            continue
        vote = parse_vote(c.get("body") or "")
        if vote:
            votes[login], links[login] = vote, c.get("html_url", "")
        if people[login]["chair"] and APPROVE_RE.search(c.get("body") or ""):
            approvals.append(people[login]["name"])
    status = tally(votes, set(people), proposed, deadline, today)
    approved = status["state"] == "consensus" and bool(approvals)
    return {"deadline": deadline, "votes": votes, "links": links, "status": status,
            "approved_by": sorted(set(approvals)) if approved else []}


# ---------------------------------------------------------------- GitHub
class GitHub:
    def __init__(self, repo: str, token: str):
        self.base, self.token = f"https://api.github.com/repos/{repo}", token

    def call(self, method: str, path: str, payload: dict | None = None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
            "User-Agent": "humeta-library-name-review", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return json.load(resp) if resp.status != 204 else None

    def pages(self, path: str) -> list:
        out, page = [], 1
        while True:
            sep = "&" if "?" in path else "?"
            batch = self.call("GET", f"{path}{sep}per_page=100&page={page}")
            out += batch
            if len(batch) < 100:
                return out
            page += 1

    def issues(self, label: str, state: str = "open") -> list[dict]:
        return [i for i in self.pages(f"/issues?labels={urllib.parse.quote(label)}&state={state}")
                if "pull_request" not in i]

    def comments(self, number: int) -> list[dict]:
        return self.pages(f"/issues/{number}/comments")

    def ensure_label(self, name: str, color: str = "c5def5") -> None:
        try:
            self.call("POST", "/labels", {"name": name, "color": color})
        except urllib.error.HTTPError as e:
            if e.code != 422:  # 422: it exists
                raise

    def create_issue(self, title: str, body: str, labels: list[str]) -> dict:
        return self.call("POST", "/issues", {"title": title, "body": body, "labels": labels})

    def update_issue(self, number: int, **fields) -> dict:
        return self.call("PATCH", f"/issues/{number}", fields)

    def add_comment(self, number: int, body: str) -> dict:
        return self.call("POST", f"/issues/{number}/comments", {"body": body})


def _labels(issue: dict) -> set[str]:
    return {lbl["name"] for lbl in issue.get("labels") or []}


# ---------------------------------------------------------------- commands
def open_round(gh, root: Path, deadline: dt.date, construct_ids: list[str] | None = None) -> list[str]:
    """One review issue for each construct not yet decided and not already under review."""
    reviews = NR.load_reviews(root)
    open_ids = {m.group(1) for i in gh.issues(LABEL, "all") if (m := CONSTRUCT_RE.search(i.get("body") or ""))
                and (i.get("state") == "open" or APPLIED_LABEL in _labels(i))}
    for name in [LABEL, *STATE_LABELS.values(), APPROVED_LABEL, APPLIED_LABEL]:
        gh.ensure_label(name)
    made = []
    for cid, review in sorted(reviews.items()):
        if construct_ids and cid not in construct_ids:
            continue
        if cid in open_ids or review.get("decision") in ("confirm", "rename", "reject"):
            continue
        p = review["proposed"]
        issue = gh.create_issue(f"Name review: {p['name']} ({cid})", issue_body(review, deadline),
                                [LABEL, STATE_LABELS["open"]])
        made.append(f"#{issue.get('number')} {cid}")
    return made


def update_all(gh, root: Path, today: dt.date) -> list[dict]:
    """Recount every open review issue, update its tally and labels, and the progress issue."""
    people = load_committee(root)
    reviews = NR.load_reviews(root)
    rows = []
    for issue in gh.issues(LABEL):
        m = CONSTRUCT_RE.search(issue.get("body") or "")
        if not m or m.group(1) not in reviews:
            continue
        cid = m.group(1)
        proposed = reviews[cid]["proposed"].get("status") == "proposed"
        info = read_issue(issue, gh.comments(issue["number"]), people, today, proposed)
        body = replace_tally(issue["body"], tally_block(info["status"], info["votes"], people, info["deadline"],
                                                        info["approved_by"], info["links"]))
        keep = {lbl for lbl in _labels(issue) if lbl not in STATE_LABELS.values() and lbl != APPROVED_LABEL}
        labels = sorted(keep | {STATE_LABELS[info["status"]["state"]]} | ({APPROVED_LABEL} if info["approved_by"] else set()))
        if body != issue["body"] or set(labels) != _labels(issue):
            gh.update_issue(issue["number"], body=body, labels=labels)
        rows.append({"number": issue["number"], "construct": cid, "name": reviews[cid]["proposed"]["name"],
                     "state": STATE_LABELS[info["status"]["state"]], "outcome": describe(info["status"]["outcome"]),
                     "approved": bool(info["approved_by"]), "deadline": info["deadline"],
                     "voted": len(info["votes"]), "members": len(people)})
    progress_issue(gh, rows, reviews)
    return rows


def progress_issue(gh, rows: list[dict], reviews: dict) -> None:
    decided = sum(1 for r in reviews.values() if r.get("decision") in ("confirm", "rename", "reject"))
    lines = [f"**{decided} of {len(reviews)} construct names decided** (applied to the library). "
             f"{len(rows)} under review now.", "",
             "| Issue | Construct | Status | Votes | Deadline | Outcome |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: r["name"].lower()):
        lines.append(f"| #{r['number']} | {r['name']} | {r['state']}{' (approved)' if r['approved'] else ''} | "
                     f"{r['voted']} of {r['members']} | {r['deadline'] or ''} | {r['outcome']} |")
    body = "\n".join(lines) + f"\n\n_Updated {dt.date.today().isoformat()} by the Name review workflow._"
    existing = gh.issues(PROGRESS_LABEL)
    if existing:
        if existing[0].get("body") != body:
            gh.update_issue(existing[0]["number"], body=body)
    else:
        gh.ensure_label(PROGRESS_LABEL)
        gh.create_issue("Construct name review: progress", body, [PROGRESS_LABEL])


def review_states(gh, root: Path, today: dt.date) -> list[dict]:
    """Every open review issue with its construct, deadline, votes, and tally."""
    people = load_committee(root)
    reviews = NR.load_reviews(root)
    out = []
    for issue in gh.issues(LABEL):
        m = CONSTRUCT_RE.search(issue.get("body") or "")
        if not m or m.group(1) not in reviews or APPLIED_LABEL in _labels(issue):
            continue
        cid = m.group(1)
        proposed = reviews[cid]["proposed"].get("status") == "proposed"
        comments = gh.comments(issue["number"])
        info = read_issue(issue, comments, people, today, proposed)
        out.append({"issue": issue, "construct": cid, "name": reviews[cid]["proposed"]["name"],
                    "comments": comments, **info})
    return out


def _link(r: dict) -> str:
    return f"[{r['name']}]({r['issue'].get('html_url', '')}) (#{r['issue']['number']})"


def remind(gh, root: Path, today: dt.date) -> list[str]:
    """3 days before an issue's deadline, mention the members who have not voted on it (once per deadline)."""
    people = load_committee(root)
    sent = []
    for r in review_states(gh, root, today):
        if not r["deadline"] or (r["deadline"] - today).days != REMIND_DAYS:
            continue
        if r["status"]["state"] == "consensus" and set(people) <= set(r["votes"]):
            continue
        mark = f"{REMINDER_MARK[:-4]} {r['deadline'].isoformat()} -->"
        if any(mark in (c.get("body") or "") for c in r["comments"]):
            continue
        missing = sorted(login for login in people if login not in r["votes"])
        if not missing:
            continue
        gh.add_comment(r["issue"]["number"], f"{mark}\n**Reminder:** voting on this construct name closes on "
                       f"{r['deadline'].isoformat()} ({REMIND_DAYS} days). Not voted yet: "
                       + ", ".join(f"@{login}" for login in missing)
                       + ". Comment `/vote confirm`, `/vote rename`, `/vote reject`, or `/vote research_more` "
                       "(how: the top of this issue). With no objection by the deadline, the proposed name stands.")
        sent.append(f"#{r['issue']['number']}")
    return sent


def digest_text(states: list[dict], people: dict, today: dt.date) -> str | None:
    """The weekly digest: what each member still needs to vote on, what needs discussion, what awaits approval."""
    if not states:
        return None
    pending = {login: [r for r in states if login not in r["votes"] and r["status"]["state"] != "consensus"]
               for login in people}
    discuss = [r for r in states if r["status"]["state"] in ("needs_discussion", "no_proposal")]
    to_approve = [r for r in states if r["status"]["state"] == "consensus" and not r["approved_by"]]
    chairs = [f"@{login}" for login, p in people.items() if p["chair"]]
    lines = [DIGEST_MARK, f"## Construct name review: week of {today.isoformat()}", "",
             f"{len(states)} under review · {len(discuss)} need discussion · {len(to_approve)} waiting for approval.", "",
             "### Your votes"]
    for login, person in sorted(people.items(), key=lambda kv: kv[1]["name"].lower()):
        items = sorted(pending[login], key=lambda r: (r["deadline"] or dt.date.max, r["name"].lower()))
        if items:
            lines.append(f"- @{login}: please vote on " + "; ".join(
                _link(r) + (f", by {r['deadline'].isoformat()}" if r["deadline"] else "") for r in items))
        else:
            lines.append(f"- @{login}: all caught up, thank you.")
    if discuss:
        lines += ["", "### Needs discussion"] + [f"- {_link(r)}: {r['status']['reason']}" for r in discuss]
    if to_approve:
        lines += ["", f"### Waiting for a chair's `/approve` ({', '.join(chairs)})"] + [
            f"- {_link(r)}: {describe(r['status']['outcome'])}" for r in to_approve]
    lines += ["", "With no objection by an issue's deadline, its proposed name stands. How to vote: "
              "governance/README.md in the library repository."]
    return "\n".join(lines)


def digest(gh, root: Path, today: dt.date) -> bool:
    """Post the weekly digest on the progress issue (one comment that mentions every member)."""
    people = load_committee(root)
    text = digest_text(review_states(gh, root, today), people, today)
    progress = gh.issues(PROGRESS_LABEL)
    if not text or not progress:
        return False
    gh.add_comment(progress[0]["number"], text)
    return True


def apply_approved(gh, root: Path, today: dt.date) -> list[dict]:
    """Write approved decisions into the review files and constructs.json; return what was applied."""
    people = load_committee(root)
    reviews = NR.load_reviews(root)
    applied = []
    for issue in gh.issues(LABEL):
        m = CONSTRUCT_RE.search(issue.get("body") or "")
        if not m or m.group(1) not in reviews or APPLIED_LABEL in _labels(issue):
            continue
        cid = m.group(1)
        proposed = reviews[cid]["proposed"].get("status") == "proposed"
        info = read_issue(issue, gh.comments(issue["number"]), people, today, proposed)
        if not info["approved_by"]:
            continue
        o = info["status"]["outcome"]
        record = [{"member": people[login]["name"], "github": login, "vote": v["choice"],
                   **{k: v[k] for k in ("name", "rule", "source", "link", "year", "replaced_by") if v.get(k)},
                   "comment": info["links"].get(login, "")} for login, v in sorted(info["votes"].items())]
        NR.write_decision(root, cid, {
            "decision": o["decision"], "reviewer": ", ".join(info["approved_by"]), "reviewed_on": today.isoformat(),
            "comments": f"Committee consensus in {issue.get('html_url', '')}: {describe(o)}.",
            "agreed_name": o.get("name") or "", "agreed_rule": o.get("rule") or None,
            "agreed_source": o.get("source") or "", "agreed_link": o.get("link") or "",
            "agreed_year": int(o["year"]) if str(o.get("year") or "").isdigit() else None,
            "replaced_by": o.get("replaced_by") or None, "issue": issue.get("html_url", ""), "votes": record})
        applied.append({"number": issue["number"], "construct": cid, "outcome": describe(o)})
    if applied:
        problems = NR.problems(root)
        if problems:
            raise SystemExit("The decisions do not pass the checks:\n" + "\n".join(problems))
        NR.apply(root)
        gh.ensure_label(APPLIED_LABEL)
        for a in applied:
            issue = next(i for i in gh.issues(LABEL) if i["number"] == a["number"])
            gh.update_issue(a["number"], labels=sorted(_labels(issue) | {APPLIED_LABEL}))
    return applied


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Construct-name review by the governance committee, in GitHub issues.")
    ap.add_argument("command", choices=["open", "tally", "remind", "digest", "apply"])
    ap.add_argument("--deadline", help="open: last day for votes, YYYY-MM-DD")
    ap.add_argument("--constructs", nargs="*", help="open: only these construct ids")
    ap.add_argument("--library", type=Path, default=ROOT)
    ap.add_argument("--summary", type=Path, help="apply: write a pull-request description here")
    args = ap.parse_args(argv)
    gh = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    today = dt.date.today()
    if args.command == "open":
        try:
            deadline = dt.date.fromisoformat((args.deadline or "").strip())
        except ValueError:
            print("Give --deadline as YYYY-MM-DD.", file=sys.stderr)
            return 1
        if deadline <= today:
            print("The deadline must be after today.", file=sys.stderr)
            return 1
        ids = [c for c in " ".join(args.constructs or []).replace(",", " ").split() if c]
        made = open_round(gh, args.library, deadline, ids or None)
        print("Opened: " + (", ".join(made) if made else "nothing (all decided or already under review)"))
        return 0
    if args.command == "tally":
        rows = update_all(gh, args.library, today)
        print(f"Updated {len(rows)} review issue(s).")
        return 0
    if args.command == "remind":
        sent = remind(gh, args.library, today)
        print("Reminders: " + (", ".join(sent) if sent else "none due"))
        return 0
    if args.command == "digest":
        print("Digest posted." if digest(gh, args.library, today) else "Nothing under review: no digest.")
        return 0
    applied = apply_approved(gh, args.library, today)
    if args.summary:
        args.summary.write_text(
            "Construct-name decisions approved by the governance committee chair.\n\n"
            + "\n".join(f"- {a['construct']}: {a['outcome']} (closes #{a['number']})" for a in applied) + "\n",
            encoding="utf-8")
    print(f"Applied {len(applied)} decision(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
