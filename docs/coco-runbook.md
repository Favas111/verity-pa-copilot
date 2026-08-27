# CoCo CLI runbook

Steps you run yourself in a real Terminal. CoCo needs an interactive terminal, so these
cannot be driven from the agent sandbox — and that is fine, because these are exactly the
steps worth showing CoCo doing.

Keep the transcripts. They are the evidence behind the "which CoCo CLI skills are used and
how they connect" requirement on the prototype submission slide.

---

## Before you start

Open **Terminal** (not the Claude window) and go to the project:

```bash
cd "/Users/shymila/Documents/Coyot Claude Projects/snowflake-coco-hackathon"
```

Check CoCo sees the Snowflake connection:

```bash
cortex connections list
```

Expect `"active_connection": "hackathon"`. If `cortex` is not found, run
`export PATH="$HOME/.local/bin:$PATH"` and retry.

---

## Set-piece 1 — extract the criteria tree

**What it does.** Reads the parsed policy PDF already sitting in Snowflake, converts it
into a tree of checkable rules, writes it back as `AI_EXTRACTED`, then scores itself
against the hand-authored `GROUND_TRUTH` tree.

**Why it matters.** This is the single most judge-visible use of CoCo in the build: a
document goes in, governed structured rules come out, and the accuracy is *measured*
rather than asserted.

Start CoCo in the project directory:

```bash
cortex -c hackathon
```

Then paste this as your first message:

> Use the `policy-criteria-extractor` skill to extract the criteria tree for policy
> `MHP-PA-0142` from `VERITY.DOCS.POLICY_PARSED`. This is a **blind** extraction: do not
> read `VERITY.EVAL.CRITERIA_ANSWER_KEY`, `VERITY.POLICY.POLICY_CRITERIA`, or any existing
> rows in `VERITY.EVAL.CRITERIA_SUBMISSION`. Derive the tree only from the parsed document.
> Use your own node id convention. Insert your tree into `VERITY.EVAL.CRITERIA_SUBMISSION`
> with `run_label = 'run2-blind'`, then show me the tree and tell me which readings were
> judgement calls. Do not score yourself.

**What to expect.** CoCo proposes SQL and asks permission. Approve `SELECT`s against
`DOCS.POLICY_PARSED` and `INSERT`s into `EVAL.CRITERIA_SUBMISSION`.

**Decline** any query against `EVAL.CRITERIA_ANSWER_KEY` or `POLICY.POLICY_CRITERIA` — a
peek at either invalidates the measurement. Also decline any `DELETE` or `UPDATE`; this
step only inserts.

**What good looks like.** Roughly 19 nodes, node ids in CoCo's own naming style, and an
honest account of which readings were uncertain. Node ids matching ours exactly would be
evidence it saw the key.

**Then score it yourself** (the extractor must not score its own work):

```bash
python3 scripts/score_extraction.py run2-blind
```

The scorer matches on structure rather than node names, and reports how many labels are
byte-identical to the key. A high identical-label rate means contamination and the score
must be discarded.

**When it finishes,** copy the transcript into `docs/coco-transcripts/01-criteria-extraction.md`.

### Run history

| Run | Structural | Labels identical | Verdict |
|---|---|---|---|
| `run1-contaminated` | 19/19 (100%) | 19/19 (100%) | **Discarded.** The answer key sat in the same table the extractor was writing to, so it copied rather than derived. Eval-design fault, since corrected by moving the key to `EVAL`. |
| `run2-blind` | 21/21 (100%) | 0/21 (0%) | **Valid, and it improved the system.** Recovered all 19 key nodes independently and added 2 the key was missing: §4.2's "intolerance to both classes" decomposed into one leaf per drug class. The single-leaf design only worked because our hero note happened to summarise itself. Decomposition adopted; answer key corrected to 21 nodes. |

---

## Guardrails while running CoCo

- Approve statements one at a time; read what it is about to run.
- Decline anything that writes outside `VERITY`, or that drops or replaces a `CORE` table —
  the bulk population takes minutes to rebuild and the golden cohort must be reloaded after
  any `CREATE OR REPLACE` on those tables.
- `/sql-readonly on` flips CoCo into read-only mid-session if you want it to explore
  without write access.
- If it stalls or loops, `Ctrl-C` and restart with `cortex -c hackathon --continue`.

---

## Queued set-pieces

| # | Task | Skill | Status |
|---|---|---|---|
| 1 | Criteria tree extraction + scoring | `policy-criteria-extractor` | ready to run |
| 2 | Bulk synthetic clinical notes | `hcls-synthetic-data` | skill not yet written |
| 3 | Semantic view for Cortex Analyst | `agent-studio` (built in) | blocked on Cortex Search |
