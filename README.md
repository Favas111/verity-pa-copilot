# Verity — Prior Authorization Evidence Copilot

**Snowflake CoCo CLI Hackathon · GCC Edition**
Challenge 4 — *Patient & Member 360 / Clinical-Regulatory Copilot* (HCLS)

> **All data here is synthetic.** No real PHI is used anywhere. The payer,
> *Meridian Health Plan*, is fictional, and every generated policy document carries a
> synthetic-document watermark.

---

## What it does

A utilization-management reviewer decides whether a requested drug meets the plan's
published medical policy. The evidence needed to make that call is split in half:
eligibility, claims, labs and pharmacy fills sit in tables; trial history, intolerances
and contraindications sit in narrative notes. The policy itself is a PDF.

Nothing joins them but a person reading — so requests get refused because the evidence
was never *found*, not because it didn't exist.

Verity turns a medical policy PDF into a tree of individually checkable criteria, resolves
each one against whichever source can answer it, and rolls the results up into a
determination where **every leaf carries a citation**.

### The system cannot deny care

Two outcomes exist:

| Outcome | Meaning |
|---|---|
| `APPROVE` | Every criterion provably met, each with a citation |
| `ROUTE_TO_CLINICIAN` | Anything else — with the evidence packet assembled and the missing item named |

There is no code path that emits a denial. That is a structural property of
[`sql/05_rollup.sql`](sql/05_rollup.sql), not an instruction to a model that could be
ignored. The agent refuses to render coverage conclusions for the same reason.

---

## The demo, in one screenshot's worth of words

Member `M09000001` needs a GLP-1. Policy §4.1 requires three consecutive months of
metformin. Hers sits under a **previous carrier's member id**.

```
conventional query  (WHERE member_id = 'M09000001')   ->  0 fills      -> refused
Verity              (identity-linked, per policy §2.3) ->  5.9 months  -> §4.1 MET
                                                           source: Northstar Mutual Health
```

This is the policy applied correctly, not a loophole: §2.3 states that a trial completed
under a prior member identifier or prior carrier **shall** count toward step therapy.
Conventional tooling simply never looks there.

Three demo members exercise three different paths:

| Member | Outcome | What it proves |
|---|---|---|
| Elena Vasquez | `APPROVE` | §4.1 rescued by identity linkage; §4.2 by an out-of-network note documenting intolerance to both second-line classes |
| Marcus Thorne | `ROUTE_TO_CLINICIAN` | Only HbA1c on file is 210 days old — the system names exactly what is missing rather than refusing |
| Priya Nakamura | `ROUTE_TO_CLINICIAN` | Every criterion passes, but a family history of medullary thyroid carcinoma is buried in a consult note. §5.1 fires |

---

## Architecture

```
                     ┌─ AI_PARSE_DOCUMENT (layout) ─┐
  policy PDF ───────►│  headings preserved → §refs   │──► POLICY_CHUNK ──┐
                     └───────────────────────────────┘                    │
                                                    CoCo CLI skill:       │
                                          policy-criteria-extractor       │
                                                          │               │
                                                          ▼               ▼
                                                  ┌──────────────────────────┐
  claims · labs · Rx ──► V_DRUG_TRIAL ──────────► │     CRITERIA LEDGER      │
       (structured leaves, identity-linked)       │   21 nodes, GROUP/LEAF   │
                                                  └──────────────────────────┘
  clinical notes ──► Cortex Search ──► AI_FILTER   │
       (retrieve)                     (adjudicate) │
                                                   ▼
                                    ┌─────────────────────────────┐
                                    │   DETERMINISTIC ROLLUP      │
                                    │ ALL_OF / ANY_OF / NONE_OF   │
                                    │   SQL — not a model call    │
                                    └─────────────────────────────┘
                                                   │
                        ┌──────────────────────────┼──────────────────────────┐
                        ▼                          ▼                          ▼
                  AUDIT trail            Streamlit console            Cortex Agent
             (every node + source)      (reviewer surface)        (ask questions;
                                                                   never decides)
```

Everything executes inside Snowflake. No PHI leaves the perimeter and reviewers inherit
Snowflake's own RBAC.

### Two design decisions worth naming

**Retrieval alone is unsafe for criterion evaluation.** Semantic search matches on *topic*,
not polarity. Searching two members for a history of medullary thyroid carcinoma returns a
confident hit for both — one says *"Mother was diagnosed with medullary thyroid carcinoma"*,
the other says *"**No** personal or family history of thyroid malignancy."* Treating a
retrieval hit as a met criterion would have blocked care for the second member.

So resolution is two-stage: **Cortex Search narrows** to candidate passages, then
**`AI_FILTER` adjudicates** whether the passage affirmatively asserts the condition.
Retrieval proposes; adjudication disposes.

**Text-to-SQL is the wrong tool for adjudication.** The semantic view answers population
questions ("how many members have an HbA1c above 9?"). It does not decide prior
authorizations — that is the Criteria Ledger, because a coverage decision has to be
reproducible and individually cited.

---

## What's in here

| Path | |
|---|---|
| `sql/00_setup.sql` | Database, 8 schemas, stages, cost guardrails |
| `sql/01_policy_model.sql` | Policy registry (effective-dated) + Criteria Ledger tables |
| `sql/02_core_model.sql` | Member 360 tables — every column traced to the criterion it serves |
| `sql/03_generate_bulk.sql` | 5,000 synthetic members, ~245k rows, fully deterministic |
| `sql/03b_chunks_search.sql` | Section-aware policy chunks + both Cortex Search services |
| `sql/04_resolvers.sql` | Two-stage unstructured leaf resolution |
| `sql/05_rollup.sql` | Structured verdicts + `ADJUDICATE` — the deterministic rollup |
| `sql/06_semantic.sql` | `MEMBER_360` semantic view for Cortex Analyst |
| `sql/07_agent.sql` | Cortex Agent wiring the semantic view + both search services |
| `app/streamlit_app.py` | The reviewer console (Streamlit in Snowflake) |
| `data/policies/` | Synthetic policy definitions + PDF renderer + ground-truth criteria tree |
| `data/generators/build_golden.py` | The three demo members, evidence deliberately planted |
| `.cortex/skills/` | Custom CoCo CLI skills |
| `docs/coco-runbook.md` | How the CoCo set-pieces were run, and their scored results |
| `docs/verity-prototype.pptx` | Prototype submission deck |
| `ENGINEERING_NOTES.md` | Full engineering notes — every gotcha hit, and why each decision was made |

---

## Running it

Requires the [Snowflake CLI](https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation)
with a connection configured, plus Python 3.11+ (`reportlab`, `python-pptx`).

```bash
# 1. Infrastructure
python3 scripts/run_sql.py sql/00_setup.sql

# 2. Policy: render the PDF, stage it, parse it, load the criteria tree
python3 data/policies/build_policies.py data/policies
python3 scripts/run_sql.py sql/01_policy_model.sql
python3 data/policies/load_criteria.py /tmp/verity     # then PUT + COPY, see ENGINEERING_NOTES.md

# 3. Member 360 — bulk population, then the golden cohort (order matters:
#    step 3 uses CREATE OR REPLACE and would wipe golden rows inserted first)
python3 scripts/run_sql.py sql/02_core_model.sql
python3 scripts/run_sql.py sql/03_generate_bulk.sql
python3 data/generators/build_golden.py /tmp/verity/golden

# 4. Retrieval, resolution, rollup
python3 scripts/run_sql.py sql/03b_chunks_search.sql
python3 scripts/run_sql.py sql/04_resolvers.sql
python3 scripts/run_sql.py sql/05_rollup.sql

# 5. Natural-language layer
python3 scripts/run_sql.py sql/06_semantic.sql
python3 scripts/run_sql.py sql/07_agent.sql

# 6. The console
./scripts/deploy_app.sh
```

Adjudicate a request:

```sql
CALL VERITY.POLICY.ADJUDICATE('PA-2026-000001');
```

Ask the agent something:

```bash
cortex agents run VERITY.AGENT.VERITY_AGENT "What does the policy require for metformin step therapy?" -c hackathon
```

> `scripts/run_sql.py` exists because stored-procedure bodies use `$$` delimiters, which
> the shell expands to a PID. It passes SQL to `snow sql -q` as a single argv element so
> quotes and `$$` survive intact.

---

## CoCo CLI usage

Custom skills live in [`.cortex/skills/`](.cortex/skills/).

**`policy-criteria-extractor`** converts parsed policy prose into the Criteria Ledger, and
is scored blind against a held-out answer key. Full transcript and results:
[`docs/coco-transcripts/01-criteria-extraction.md`](docs/coco-transcripts/01-criteria-extraction.md).

| Run | Structural match | Labels identical | |
|---|---|---|---|
| `run1` | 19/19 | **19/19** | **Discarded** — the answer key sat in the table the extractor was writing to, so it copied rather than derived. Our eval-design fault, fixed by moving the key to a held-out schema |
| `run2-blind` | 21/21 | 0/21 | **Valid — and it improved the system.** Recovered every key node independently *and* added two the hand-authored key was missing |

That second run is the interesting one. CoCo decomposed §4.2's "intolerance to both
classes" into one leaf per drug class, arguing that a single note covering only one class
should not satisfy the criterion. It was right: under our original single-leaf design, only
a passage summarising *both* intolerances could satisfy §4.2 — a realistically-written note
documenting each separately would have returned `NOT_MET` and wrongly routed an approvable
member to a clinician. The decomposition was adopted and the answer key corrected.

CoCo's contribution here is narrow and specific: it read the parsed policy and produced
the criteria tree, blind, and its reading was better than ours. That is the whole claim —
the rest of the build is ordinary SQL and Python in this repo.

---

## Measured results

Every figure is measured from this build, not quoted from industry sources.

| | |
|---|---|
| **43s** | end-to-end adjudication — 21 criteria, 6 retrievals, 20 adjudication calls |
| **100%** | of determinations fully cited — 315 audit nodes, each with its source |
| **21/21** | blind criteria extraction, 0% label overlap with the key |
| **245,291** | rows of synthetic data, deterministic and reproducible |
| **~$7** | total Snowflake spend to build the whole thing |

---

## License / provenance

Synthetic data, fictional payer, fake NPIs and NDC codes (labeler `99999`). The medical
policy is authored for this demonstration and reflects no real insurer's coverage criteria.
Drug names are real generic names used factually.
