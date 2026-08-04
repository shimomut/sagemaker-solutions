# SageMaker / HyperPod Knowledge Docs

This directory holds the **technical mental model** for SageMaker HyperPod and
the mechanism for keeping it accurate over time.

## Layout

```
docs/
├── README.md                          # this file — the maintenance process
├── hyperpod-mental-model.md           # THE main curated doc (stable, deduplicated)
├── mental-model/                      # dedicated supplemental docs, linked from the main doc
│   └── hyperpod-<topic>.md            #   e.g. hyperpod-ssm.md, hyperpod-events.md
└── knowledge-updates/                 # staging area for new, not-yet-merged findings
    ├── TEMPLATE.md                    # copy this to start a new findings file
    ├── hyperpod-new-knowledge-YYYY-MM-DD.md   # dated raw findings (the inbox)
    └── merged/                        # findings that have been folded into the main docs (archive)
```

### The three tiers

1. **Main doc** — [`hyperpod-mental-model.md`](hyperpod-mental-model.md). The
   single source of truth. Broad, curated, deduplicated. Every claim here has
   been validated or clearly hedged. Readers who want "the answer" read only
   this (plus its supplemental docs).

2. **Supplemental docs** — [`mental-model/`](mental-model/). When a topic grows
   too large or self-contained for the main doc (e.g. SSM access patterns, the
   event surfaces, deep-health checks), it gets its own file here and is linked
   from the main doc's supplemental-docs list. Same quality bar as the main doc.

3. **Knowledge updates** — [`knowledge-updates/`](knowledge-updates/). The
   **inbox**. Dated, append-friendly files where raw findings land as they're
   discovered — from live cluster testing, debugging, docs, or a work session.
   Low friction to write; NOT the source of truth. Content lives here only until
   it's merged upward.

## Why the staging tier exists

Writing straight into the main doc during active work causes two problems:
findings get recorded before they're validated, and the main doc churns/bloats
with half-formed notes. The staging tier lets you **capture fast, curate
deliberately**. This is exactly how `hyperpod-mental-model-new-findings-2026-08-03.md`
(now in [`knowledge-updates/`](knowledge-updates/)) came to be — but the merge
step is now a defined process, not ad hoc.

---

## The lifecycle

### 1. Capture — write a dated findings file

When you learn something new (validated a claim, found a gotcha, hit an API
quirk), record it in a dated file. One file per working session/topic-burst:

```
docs/knowledge-updates/hyperpod-new-knowledge-2026-08-15.md
```

Start by copying [`knowledge-updates/TEMPLATE.md`](knowledge-updates/TEMPLATE.md).
Each finding is classified as one of:

- **Confirmation** — a claim in the main doc held under test. Cite where.
- **Proposed edit** — a gap/correction to fold into the main doc. Say *where*
  it goes (section / line) and give proposed wording.
- **New topic** — a subject the main doc doesn't cover yet (candidate for a new
  supplemental doc).
- **Not yet verified** — flagged honestly so no one over-reads it.
- **Open question** — something still unclear.

Rules for the inbox:
- **Always date-stamp** findings (the repo has no reliable "now" — use the
  current date).
- Cite evidence: the API call, the response shape, the region/account/cluster,
  the doc line, the SSM session. Keep it reproducible.
- **Read-only / least-privilege first.** Prefer `describe*` / `list*` and
  read-only SSM over anything mutating; never inject faults or mutate a cluster
  you can't confirm is non-production.
- It's fine to be rough here. Curation happens at merge time.

### 2. Merge — fold findings into the curated docs

Periodically (e.g. when a findings file feels "done", or on a cadence), run a
**merge pass**. For each finding:

| Finding type | Action |
|---|---|
| Confirmation | If it adds nuance, tighten the main-doc wording; else just note it validated and drop it. |
| Proposed edit | Apply the edit to the main doc (or supplemental doc) at the cited location. |
| New topic | Add to the relevant section; if large/self-contained, create a new `mental-model/hyperpod-<topic>.md` and link it from the main doc's supplemental-docs list. |
| Not yet verified | Leave in staging (carry forward) OR move to "Things still unclear" in the main doc. Do NOT assert it as fact. |
| Open question | Add to "Things still unclear / under investigation" in the main doc. |

Merge discipline:
- **Deduplicate.** If a finding restates something already in the main doc,
  don't add a second copy — strengthen or hedge the existing line instead.
- **Preserve honesty.** Keep hedges ("verified on EKS only", "not yet tested",
  orchestrator tags). Never upgrade a "not yet verified" note into a flat
  assertion during merge.
- **Prune the main doc** while you're there: resolve open questions that newer
  findings answer, delete claims newer findings contradict.
- The person/agent doing the merge is the **curator**; the findings file author
  just needs to be clear, not polished.

### 3. Archive — retire the merged findings file

Once every finding in a dated file has been merged, carried forward, or dropped,
move the file to [`knowledge-updates/merged/`](knowledge-updates/merged/) and add
a one-line entry to the merge log below. This keeps the inbox showing only
un-merged work.

If only *some* findings merged, split: move the merged ones to an archived file
and leave the rest in a fresh dated inbox file.

---

## Merge log

Newest first. One line per merge pass: date, source findings file, summary.

<!-- MERGE-LOG:START -->
- _(no merges yet — `hyperpod-mental-model-new-findings-2026-08-03.md` is in the
  inbox awaiting its first merge pass)_
<!-- MERGE-LOG:END -->

---

## Quick reference for an AI assistant

- **Answering a question about HyperPod?** Read `hyperpod-mental-model.md` (+ its
  supplemental docs). Don't rely on training-data assumptions ("basically EC2 +
  Slurm/EKS" is the trap).
- **Learned something new this session?** Append it to today's
  `knowledge-updates/hyperpod-new-knowledge-<date>.md` (create from `TEMPLATE.md`
  if none exists). Classify it. Don't edit the main doc mid-discovery.
- **Asked to curate / "brush up the docs"?** Run a merge pass (step 2), then
  archive (step 3), then update the merge log.
