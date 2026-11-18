# Governance: construct names

The HuMeta governance committee decides the official name of each shared construct
(`constructs.json`). It works asynchronously, in GitHub issues: one issue per construct, with the
evidence for the proposed name, the committee's votes and discussion, and a tally that updates itself.

## The naming rule

1. An ERIC Thesaurus descriptor with exactly the same meaning, written as ERIC writes it; else
2. an ICPSR Subject Thesaurus term with exactly the same meaning; else
3. the name as first published, anchored to that publication.

Exact meaning only, never a broader term. Ids never change; other names are kept as synonyms.

## For committee members

You need a free GitHub account, listed in [`committee.yml`](committee.yml).

1. Open the issues labeled **name-review**. The **Construct name review: progress** issue lists them
   all with their status.
2. Read the evidence in the issue: the proposed name, its source and year, and notes on what to check.
3. Vote by commenting with one of these. Your latest vote counts, so you can change it at any time
   before the decision is applied. Discuss freely in other comments.

| Vote | Comment | Means |
|---|---|---|
| Confirm | `/vote confirm` | The proposed name stands. |
| Rename | `/vote rename` and, on the next lines, `name:`, `rule:` (eric, icpsr or first_use), `source:`, `link:`, `year:` | Another name, with its source. One member gives the details; others agreeing can just write `/vote rename` with the same `name:`. |
| Reject | `/vote reject`, optionally `replaced_by: <construct id>` | Take the construct off the shared list. It is retired, not deleted, because studies may already use it; `replaced_by` says what to use instead. |
| Research more | `/vote research_more` | Not ready to decide; say what to look for. |

## How a decision is reached (lazy consensus)

- Each issue has a **deadline**, normally two weeks. A chair can extend it by editing the
  `**Deadline:**` line in the issue.
- **At the deadline**, the outcome is the one that every vote cast agrees on. With no votes, a
  proposed name stands: silence is consent. A construct with no proposed name needs at least one
  member to propose one with `/vote rename`.
- **Disagreement or a `research_more` vote** keeps the issue open as *needs discussion* until the
  votes agree.
- **Early consensus:** if every member has voted and all agree, the decision does not wait for the
  deadline.
- **Approval:** a chair comments `/approve` on an issue that has reached consensus. The chair then
  runs the **Apply construct-name decisions** workflow (Actions tab), which writes every approved
  decision, with each member's vote, into `governance/construct-names/<id>.yml` and `constructs.json`,
  and opens a pull request. Merging it closes the issues.

The tally in each issue, and its label (*awaiting votes*, *needs discussion*, *consensus*,
*approved*, *applied*), update whenever someone comments and once a day.

## Emails

- **Weekly digest, every Monday morning** (about 8:30 Eastern): one comment on the progress issue
  that mentions every member, listing the constructs each still needs to vote on, those that need
  discussion, and those waiting for a chair's approval. Nothing is sent when no round is open.
- **Reminder 3 days before a deadline**, on that construct's issue, mentioning only the members
  who have not voted on it.

GitHub emails you when you are mentioned. Keep email notifications on in your GitHub settings
(Settings → Notifications; on by default). Replying to the email posts a comment on the issue, so
you can vote by email: reply with `/vote confirm` (or another vote) as the first line.

## For the chair

- **Start a round:** Actions → **Open a construct-name review round** → give the deadline
  (YYYY-MM-DD) and, optionally, the construct ids to include (default: every construct not yet
  decided and not already under review). One issue is opened per construct.
- **Add or remove members:** on GitHub, open `committee.yml`, click the pencil, add two lines under
  `members:` (`- name: Full Name` and `  github: username`), and commit through a pull request. Their
  votes count from then on, on open issues too, and they get the next weekly digest.
- **Send the digest now:** Actions → **Name review weekly digest** → Run workflow.
- **Apply decisions:** comment `/approve` on each issue with consensus, then run **Apply
  construct-name decisions**. Review and merge its pull request. If a pull request is closed without
  merging, remove the *applied* label from its issues.
- The repository setting *Allow GitHub Actions to create and approve pull requests* (Settings →
  Actions → General) must be on for the apply workflow.

## Files

- `committee.yml`: who votes, and who chairs.
- `construct-names/<construct id>.yml`: the evidence for each proposed name and, once decided, the
  decision and every member's vote. Made by `python scripts/naming_review.py create`.
- `python scripts/naming_review.py status` lists what is decided and what is left.
