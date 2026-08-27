# VERITY — Prior Authorization Evidence Copilot

Snowflake **CoCo CLI Hackathon (GCC Edition)** submission.
Challenge 4 — *Patient & Member 360 / Clinical-Regulatory Copilot* (HCLS).

> **All data in this project is fully synthetic.** No real PHI is ever used.
> The payer, **Meridian Health Plan**, is fictional. Every generated policy
> document carries a synthetic-document watermark. This is a hard requirement
> of the challenge brief, not a nice-to-have.

---

## The concept

A **Utilization Management console** with **prior authorization as the hero workflow**.
Not a generic chatbot over healthcare data.

Prior auth was chosen because it *structurally* requires both halves of the challenge:
a PA decision cannot be made without the **Member 360** (claims, Rx history, labs,
eligibility) **and** the **unstructured corpus** (clinical notes, medical policy PDFs).
The join between them *is* the problem, rather than an artificial pairing.

### Non-negotiable design rule: the AI cannot deny care

The system emits exactly two outcomes:

| Outcome | When |
|---|---|
| `APPROVE` | Every policy criterion is provably met, each with a citation |
| `ROUTE_TO_CLINICIAN` | Anything else — with a complete evidence packet and an explicit list of what is missing |

Denial is **structurally impossible**, enforced in the deterministic rollup, not by prompt
instructions. This is the correct design on the merits (there is active public concern and
litigation around AI systems denying care), and it is also the stronger demo: the AI's job
is to auto-approve clear-cut cases so patients stop waiting, and to hand human reviewers a
finished evidence packet for everything else.

---

## The differentiator: the Criteria Ledger

**The LLM never renders the verdict.**

1. **Offline, once:** `AI_PARSE_DOCUMENT` (LAYOUT mode) over each policy PDF →
   `AI_COMPLETE` with a structured `response_format` → decompose the policy into a
   **criteria tree** in `POLICY.POLICY_CRITERIA`
   (`policy_id, section_ref, criterion_text, logic_op, parent_id, evidence_type`).
2. **At runtime, each criterion resolves independently** to
   `MET` / `NOT_MET` / `INSUFFICIENT_EVIDENCE` **plus its citation** — sourced either from
   SQL over the semantic view (structured) or Cortex Search (unstructured).
3. **The decision is a deterministic SQL rollup** of the tree's AND/OR logic. Not a model call.
4. The LLM is used only for *extraction* and for *explaining a result already computed*.

Why this wins: the verdict is arithmetic over cited leaves, so the system cannot produce an
uncited conclusion. Competing submissions that ask an LLM to judge will hallucinate on stage.

### The moat detail

A determination must be evaluated against **the policy version in effect on the date of
service**, not today's policy. Effective-dated policy tables + Snowflake Time Travel handle
this natively. It is a genuine compliance requirement, roughly 15 lines of SQL, and almost
no competing team will think of it.

---

## Environment (verified working)

| Item | Value |
|---|---|
| Account | set in the `hackathon` CLI connection (locator not committed) |
| Region | `AWS_AP_SOUTHEAST_7` (Jakarta) |
| Auth | Key-pair (`SNOWFLAKE_JWT`), key at `~/.snowflake/keys/hackathon_rsa_key.p8` |
| CLI connection | `hackathon` (`snow sql -c hackathon -q "..."`) |
| CoCo CLI | `cortex` v1.1.66, `~/.local/bin/cortex` |
| Warehouse | `COMPUTE_WH` — X-Small, `AUTO_SUSPEND=60` |
| Trial budget | $400 / 30 days from 2026-08-19 |

### Region caveat — important

Jakarta does not host most Cortex models locally. Everything works **only** because
`CORTEX_ENABLED_CROSS_REGION = 'ANY_REGION'` is set at account level. Do not unset it.

### Capability probes (all passed)

| Capability | Result |
|---|---|
| `AI_COMPLETE('claude-4-sonnet', ...)` | works |
| `AI_FILTER` | works |
| `SNOWFLAKE.CORTEX.EMBED_TEXT_1024` (`snowflake-arctic-embed-l-v2.0`) | works — 0.57 related vs 0.14 unrelated |
| `AI_PARSE_DOCUMENT` LAYOUT mode | works — **returns markdown with `#` headings preserved**, which is what enables §-anchored citations |
| Cortex Search + `ATTRIBUTES` | works — hybrid cosine + reranker + text_match |

**Citation architecture proven end-to-end.** Parsing `MHP-PA-0142.pdf` (3 pages, 5,320 chars)
recovered **20 of 20 headings with correct hierarchy** — `#` for sections 1–8, `##` for every
subsection (2.1–2.3, 3.1–3.3, 4.1–4.2, 5.1–5.3). Chunking on those heading boundaries is what
lets a determination cite "§4.1" rather than "chunk 37".

Gotchas already hit, so nobody re-hits them:

- `ARRAY_SIZE()` on an embedding returns `NULL` — `EMBED_TEXT_1024` returns a `VECTOR`,
  not an array. Verify with `VECTOR_COSINE_SIMILARITY` instead.
- Stages read by `AI_PARSE_DOCUMENT` **must** be created with
  `ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')`.
- A live Cortex Search service **bills continuously**. Drop unused ones on a trial account.
- `snow sql -f <file>` is blocked in this agent harness; run DDL inline via
  `snow sql -c hackathon -q "..."`.

---

## Database layout

`VERITY` database, 8 schemas:

| Schema | Purpose |
|---|---|
| `RAW` | Landing zone for generated synthetic source data |
| `CORE` | Conformed member/claims/clinical model (Member 360 foundation) |
| `DOCS` | Stages, `AI_PARSE_DOCUMENT` output, chunks, Cortex Search services |
| `POLICY` | Policy registry + machine-checkable criteria tree (Criteria Ledger) |
| `SEMANTIC` | Semantic views powering Cortex Analyst |
| `AGENT` | Cortex Agent definitions and tool wiring |
| `AUDIT` | Immutable decision + evidence audit trail |
| `APP` | Streamlit in Snowflake — care coordinator / UM nurse console |

Stages: `DOCS.POLICY_DOCS`, `DOCS.CLINICAL_DOCS` (both SSE-encrypted, directory enabled).
Roles: `VERITY_CLINICAL_REVIEWER` (sees PHI) vs `VERITY_ANALYST` (PHI masked).

> **Caution:** the roles in `00_setup.sql` were not created for a long time. That file's
> execution was blocked early on, the DDL was re-run inline, and only the database,
> schemas and stages made it across — the role statements were silently skipped. It only
> surfaced weeks later when granting a teammate access failed with "role does not exist".
> If a file is ever partially re-run by hand, verify the tail of it, not just the head.

---

## Build status

| Step | State |
|---|---|
| `00_setup.sql` — DB, 8 schemas, stages, warehouse guardrails | done |
| Policy `MHP-PA-0142` authored + PDF rendered | done |
| PDF staged + `AI_PARSE_DOCUMENT` → `DOCS.POLICY_PARSED` | done — 20/20 headings |
| `01_policy_model.sql` — `POLICY_REGISTRY` + `POLICY_CRITERIA` | done |
| Ground-truth criteria tree loaded (19 nodes: 7 GROUP, 12 LEAF) | done |
| `02_core_model.sql` — CORE + `DOCS.CLINICAL_NOTE` (11 tables) | done |
| `03_generate_bulk.sql` — Tier 1 population | done — 240k rows |
| `V_MEMBER_IDENTITY` + `V_DRUG_TRIAL` resolver views | done |
| Golden cohort (3 demo members) — `build_golden.py` | done — verified |
| `POLICY_CHUNK` (section-aware) + `NOTE_CHUNK` | done |
| `POLICY_SEARCH` + `CLINICAL_SEARCH` Cortex Search services | done |
| `04_resolvers.sql` — two-stage unstructured resolver | done — verified 3/3 |
| CoCo set-piece 1 — blind criteria extraction | done — 21/21, 0% overlap |
| `05_rollup.sql` — structured verdicts + `ADJUDICATE` | done — 3/3 correct |
| Streamlit console — `VERITY.APP.VERITY_CONSOLE` | **working end to end** |
| Prototype deck — `docs/verity-prototype.pptx` | drafted, 7 slides |
| `06_semantic.sql` — `SEMANTIC.MEMBER_360` (org bullet 3) | done — verified |
| `07_agent.sql` — `AGENT.VERITY_AGENT` (org bullet 5) | done — all tools + guardrail verified |
| `03b_chunks_search.sql` — chunks + both Search services | done (was missing from the repo) |
| Demo video / walkthrough | next |

### Semantic view

`SEMANTIC.MEMBER_360` — 9 logical tables, 8 relationships, 3 facts, 24 dimensions,
11 metrics. Verified with real cross-table queries (members↔labs, rx↔drugs).

Synonyms are load-bearing, not decoration: they are how a nurse asking about "patients"
reaches a table called `MEMBER`. Cortex Analyst reads the comments to choose joins, so
vague comments produce vague SQL.

**Scope line that must not blur:** the semantic view answers *population* questions
("how many members have HbA1c above 9?"). It does **not** decide prior authorizations —
that is `POLICY.ADJUDICATE` rolling up the Criteria Ledger. Text-to-SQL is right for
exploration and wrong for adjudication, because a determination must be reproducible and
individually cited.

**Syntax gotchas:**
- Clause order is fixed: `TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS`.
  FACTS after DIMENSIONS fails with `unexpected 'FACTS'`.
- Equals form required: `COMMENT = '...'` and `WITH SYNONYMS = (...)`, not the bare form.

### Cortex Agent — created but not proven working

`AGENT.VERITY_AGENT` wires three tools: `member_360` (Analyst over the semantic view),
`policy_lookup` and `clinical_lookup` (the two Search services). Its orchestration
instructions explicitly forbid rendering a coverage conclusion — it reports what
`AUDIT.DETERMINATION` recorded, or says none exists.

**Agent model IDs use a different naming convention than `AI_COMPLETE`.** This is the
trap: `claude-4-sonnet` is valid for `AI_COMPLETE` and *invalid* for Agents, which want
`claude-sonnet-4-5`. Allowed values as reported by the account:

```
claude-haiku-4-5, claude-opus-4-5, claude-opus-4-6, claude-opus-4-7, claude-opus-4-8,
claude-opus-5, claude-sonnet-4-5, claude-sonnet-4-6, claude-sonnet-5,
gemini-3.1-pro, gemini-3.5-flash, openai-gpt-4.1, openai-gpt-5, openai-gpt-5-mini,
openai-gpt-5.1, openai-gpt-5.2, openai-gpt-5.4
```

Now set to `claude-sonnet-4-5`.

**Diagnosis only surfaced in the Snowsight UI.** `cortex agents run` reports
`{"error":"Agent returned an empty response"}` regardless of cause; the UI Preview tab
returned the actual model-allowlist error. When an agent misbehaves, test in Snowsight
first — the CLI swallows the diagnostic.

**A Cortex Analyst tool needs an execution environment.** Without it the tool is invalid
and the *entire agent* fails silently — every question returns empty, including ones that
would only have used the search tools:

```json
"member_360": {
  "semantic_view": "VERITY.SEMANTIC.MEMBER_360",
  "execution_environment": { "type": "warehouse", "warehouse": "COMPUTE_WH" }
}
```

One malformed tool takes down the whole agent, so suspect tool_resources before
orchestration when nothing answers.

**Verified working** (`cortex agents run VERITY.AGENT.VERITY_AGENT "<question>" -c hackathon`):

| Path | Result |
|---|---|
| `policy_lookup` | Quotes §4.1 requirements with contraindications, cites §4.1 and §4 |
| `member_360` | "There are 5,003 members in total" |
| `clinical_lookup` | Both intolerances for `M09000001`, sourced to the 2025-02-18 consult note |
| **Guardrail** | "I cannot make approval decisions" — reports the recorded outcome instead |

### Two bugs the agent surfaced

- **Citations read `$4.1` instead of `§4.1`.** `POLICY_CHUNK` was built inline via
  `snow sql -q` and the shell ate the escaped section sign; the agent faithfully quoted the
  corrupted string. Those objects also existed only in shell history — now captured in
  `03b_chunks_search.sql`, which must run through `run_sql.py` to survive the `§`.
- **`PA_REQUEST.status` never left `PENDING`.** `ADJUDICATE` wrote to
  `AUDIT.DETERMINATION` but not back to the request, so the agent reported "no
  determination has been run" while the audit trail said otherwise. Two sources of truth
  disagreeing about whether a decision exists is worse than either being wrong.
  `ADJUDICATE` now updates `status` and `decision_date`.

### Open items needing the user

- **Team name, team leader, team size** — slide 1 of the deck is `[PLACEHOLDER]`.
  Set them in `TEAM_NAME` / `TEAM_LEADER` / `TEAM_SIZE` at the top of
  `scripts/build_deck.py`, then rebuild.
- **Verify the CMS-0057-F claim on deck slide 2** (decision windows + a specific reason
  per denial) against current rule text, or soften the wording. It has not been checked
  against a primary source in-session, and a healthcare judge may know it precisely.

### The deck

`python3 scripts/build_deck.py` → `docs/verity-prototype.pptx`. Built with python-pptx on
the template's own background art (extracted to `docs/_bg/`), so it carries hackathon
branding while we control content. The three template-required sections — Problem Brief,
Architecture Diagram, Impact Statement — are labelled as kickers so a judge scanning for
them finds them.

Every Impact figure is measured from this build, never quoted from industry sources:
43s adjudication, 100% of determinations cited (315 audit nodes), 21/21 blind extraction,
$6.77 total cost.

**Deck gotchas, all hit:**

- **Slide size is 10 × 5.625in**, not the 13.33in wide layout. Coordinates past 10in are
  written, not clamped — the shape simply is not on the slide.
- **Autoshape text frames default to CENTER.** A centered heading over left-aligned body
  inside one card is the classic careless-deck tell. `para()`/`rich()` now force LEFT
  unless told otherwise.
- **`\n` inside a python-pptx run is not a line break.** Use separate paragraphs.
- Flow arrows in `RULE` grey are invisible against card borders; `ARROW` exists for that.

**Visual QA is mandatory and needs LibreOffice** (installed via `brew install --cask
libreoffice`):

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice --headless --convert-to pdf --outdir <dir> docs/verity-prototype.pptx
pdftoppm -jpeg -r 130 <dir>/verity-prototype.pdf <dir>/deck
```

A programmatic bounds check catches off-slide shapes, but its text-fit heuristic is noisy
(single-line labels in one-line boxes always flag). Look at the renders.
| Semantic view + Cortex Agent (org bullets 3, 5) | not started |
| Bulk filler notes (`AI_COMPLETE`) | optional — cut if time compresses |

> **Standing risk, now reduced.** An end-to-end demo stands: policy PDF → parsed → criteria
> tree → evidence → determination → console. Remaining risk is packaging, not capability.
> Deck before further engineering.

### The console

`snow streamlit deploy -c hackathon --replace` (driven by `snowflake.yml`). Runs as
Streamlit **in** Snowflake — no PHI leaves the perimeter and the reviewer inherits
Snowflake RBAC, which is a real compliance argument worth saying out loud.

It renders determinations, never computes them: everything on screen is read back from
`AUDIT.DETERMINATION_NODE`. Three tabs — criteria trail (outcome banner + indented tree
with per-leaf evidence expanders), Member 360 (prior coverage surfaced deliberately, since
it is what makes step therapy discoverable), and policy source.

Verify a deploy with `EXECUTE STREAMLIT` under an explicit `USE DATABASE` — the
`snow streamlit execute` wrapper fails without a current database.

**Deploy with `./scripts/deploy_app.sh`, never `snow streamlit deploy`.**

`snow streamlit deploy` uploads to versioned storage
(`snow://streamlit/.../versions/live/`) and **every app deployed that way dies at load on
this account** with `Python Interpreter Error: TypeError: bad argument type for built-in
operation` — no traceback, and `snow streamlit logs` is unavailable on this runtime.

Proven not to be application code: a **two-line, pure-ASCII** app failed identically
through the CLI and worked immediately through `ROOT_LOCATION`. The same underlying fault
also surfaced as the CLI's `'live_version_location_uri'` error. The fix is to `PUT` the
file to a plain internal stage and point `ROOT_LOCATION` at it.

Worth remembering as a debugging lesson: the error text (`bad argument type for built-in
operation`) is exactly what `str * Decimal` raises, which sent me chasing a real-but-
unrelated type bug in the app for two deploy cycles. A plausible error message is not
evidence. Bisecting to a minimal app took one deploy and settled it.

**Streamlit-in-Snowflake gotchas, all hit in practice:**

- **Snowflake `NUMBER` arrives as `decimal.Decimal`.** `Decimal` has no sequence-repeat
  protocol, so `"x" * Decimal(3)` raises *"TypeError: bad argument type for built-in
  operation"* — which is what took the console down on first load. Wrap anything used for
  indentation, repetition, or slicing in `as_int()`, and `.astype(float)` any column
  before charting. Cheap to prevent, opaque to diagnose.
- **`EXECUTE STREAMLIT` is a weak check.** It runs the script but does not exercise the
  full render path, and it passed cleanly on the build that failed in the browser. Treat
  it as a syntax check only — a real page load is the only verification that counts.
- **`snow streamlit deploy --replace` can fail with `'live_version_location_uri'`.**
  Same underlying fault as above; use `./scripts/deploy_app.sh`.
- **An app instance has a lifetime cap on queries** — *"Exceeded maximum number of inbound
  queries allowed for this instance: 219"*. A query-per-panel design hits it fast, because
  every widget interaction reruns the whole script. The console therefore loads its entire
  working set in **one cached call** (`load_all()`, `ttl=3600`) and filters per member in
  pandas: 10 queries once, then zero. If it ever trips again, stop and start the app from
  Snowsight to reset the instance.
- **Never mutate a cached DataFrame.** `st.cache_data` hands back the cached object itself,
  so `df["col"] = ...` corrupts every later read. `.copy()` first.
- **Streamlit version here is >= 1.19 but < 1.23.** `st.divider`, `st.tabs`,
  `label_visibility` and `use_container_width` all work; **`hide_index` does not** (added
  1.23) and raises `TypeError: dataframe() got an unexpected keyword argument`. To hide a
  meaningless index, `set_index()` a real column instead. Check any new Streamlit API
  against that window before using it.

### The answer key must be held out — eval hygiene

The first CoCo criteria-extraction run scored **19/19, 100%** — and the score was worthless.

All 19 labels were byte-identical to the hand-authored tree, including invented node-id
conventions (`C4.1a`, `G4.1`, `S3`) that appear nowhere in the policy PDF. Independent
derivation from prose cannot reproduce those. The extractor had read `GROUND_TRUTH`, which
was sitting in the same table it was told to write to.

This was an eval-design fault, not a model failure. Fixed by:

- **`EVAL` schema** — `CRITERIA_ANSWER_KEY` (held out) and `CRITERIA_SUBMISSION`
  (where blind runs land). `POLICY.POLICY_CRITERIA` now holds only the operational tree.
- **Structural scoring** — matches on `(section_ref, node_type, combinator, evidence_type)`,
  never `node_id`, so an extractor loses nothing by using its own naming.
- **Contamination detector** — `scripts/score_extraction.py` reports the share of labels
  byte-identical to the key alongside the score. ≥60% ⇒ discard the run.

Never let an agent write beside the key it is scored against, and never let it score its
own work. A confident meaningless number is worse than no number — especially one headed
for a slide.

**The blind re-run then found a real defect in the hand-authored tree.**

`run2-blind`: **0% label overlap** (independent derivation confirmed), all 19 key nodes
recovered, plus **2 extra** — it decomposed §4.2's "intolerance to both classes" into an
`ALL_OF` over one leaf per drug class, where the key had a single leaf demanding both.

CoCo's reading is correct, and the evidence proves it. Under the single-leaf design, only
one chunk affirmed §4.2c for Member A — the ASSESSMENT paragraph, which happens to contain
a summarising sentence. The two chunks carrying the *actual* clinical detail were both
rejected, each covering only one class:

```
"Empagliflozin ... discontinued due to recurrent urinary tract infections"   -> False
"Glipizide ... discontinued after recurrent symptomatic hypoglycemia"        -> False
"documented intolerance to both sulfonylurea and SGLT2 inhibitor classes"    -> True
```

The hero demo passed **only because the note happened to summarise itself**. Real consult
notes document each intolerance separately, and the leaf would have returned `NOT_MET`.

Adopted the decomposed structure (`G4.2int` ALL_OF over `C4.2c` SGLT2i + `C4.2d`
sulfonylurea) into the operational tree, `policy_defs.py`, and `LEAF_RESOLVER`. Re-verified:
both leaves now MET for Member A, with **C4.2c affirmed by the detailed empagliflozin
passage** rather than the summary. Tree is now 21 nodes (8 GROUP, 13 LEAF); answer key
refreshed; `run2-blind` rescores 21/21 against the corrected key.

A blind eval that merely confirms your own work teaches nothing. This one caught a latent
failure that would have broken the demo on any realistically-written note.

### Deadline

**2026-09-01.** Ordering from here is visible-layer-first: rollup → Streamlit → deck →
semantic view + agent + second CoCo set-piece → demo video → buffer. If time compresses,
cut bulk AI notes, Cortex Analyst NL querying, and any further polish on what already
works. Never cut the console or the deck.

### The rollup engine, and what "blocking reason" actually means

`POLICY.ADJUDICATE(pa_id)` folds the Criteria Ledger bottom-up and writes the full trail to
`AUDIT.DETERMINATION` + `AUDIT.DETERMINATION_NODE`. Recursive CTEs walk top-down, so the
procedure computes node depth once and folds one level at a time from the deepest upward.

Three verdict states, not two. `INSUFFICIENT_EVIDENCE` ("no HbA1c on file") is not
`NOT_MET` ("HbA1c too low") — collapsing them tells a clinician something untrue about
their patient.

**Blocking reasons required a real fix.** The first implementation collected "leaves that
aren't MET under a group that isn't MET". That is wrong twice:

- it blamed leaves under a failed sub-group whose parent `ANY_OF` was satisfied by a
  sibling route — Member B was told §4.2 blocked her when her SGLT2 trial had satisfied it;
- under `NONE_OF` it blamed the wrong leaves entirely. A `MET` child *is* the exclusion that
  fired; `NOT_MET` children are the exclusions that did **not** apply. Member C's real
  blocker (§5.1, MTC history) was filtered out precisely because it was `MET`.

Responsibility is a downward descent from ROOT, by combinator:

| Combinator | Responsible children |
|---|---|
| `ALL_OF` | those not MET |
| `ANY_OF` | all of them (no route succeeded) |
| `NONE_OF` | those that **are** MET — reported as `EXCLUSION APPLIES` |

Verified end-to-end, one actionable reason each:

| PA | Outcome | Reason |
|---|---|---|
| `PA-2026-000001` | `APPROVE` | — |
| `PA-2026-000002` | `ROUTE_TO_CLINICIAN` | §3.3 HbA1c `[INSUFFICIENT_EVIDENCE]` |
| `PA-2026-000003` | `ROUTE_TO_CLINICIAN` | §5.1 MTC history `[EXCLUSION APPLIES]` |

`sort_order` drives console rendering, so patched-in nodes must be reloaded from
`policy_defs.py` rather than hand-numbered — otherwise the tree renders out of order while
still rolling up correctly, which is easy to miss.

### Retrieval alone is unsafe — the two-stage resolver

**The single most important correctness finding in this build.** Semantic search matches
on *topic*, not *polarity*:

```
query: "family history of medullary thyroid carcinoma or MEN2"
  M09000003 -> "Mother was diagnosed with medullary thyroid carcinoma"      (rerank -1.55)
  M09000002 -> "No personal or family history of thyroid malignancy"        (rerank -7.22)
```

Both are strong topical matches and **both are returned**. Treating "retrieval returned a
hit" as "criterion met" would have fired exclusion §5.1 against a member whose record
explicitly *denies* that history — wrongly blocking their care, live on stage.

Reranker scores did separate the two, but a score threshold is arbitrary and drifts with
corpus and phrasing. So:

- **Stage 1 — Cortex Search narrows** to candidate passages, filtered by `member_id` inside
  the request so a retrieval can never surface another member's record.
- **Stage 2 — `AI_FILTER` adjudicates** whether the passage *affirmatively asserts* the
  condition.

Retrieval proposes; adjudication disposes. Config lives in `POLICY.LEAF_RESOLVER`
(one search query + assertion prompt per unstructured leaf); evidence and verdicts land in
`POLICY.LEAF_EVIDENCE` for the audit trail.

Verified across all three golden members:

| Member | Result | Meaning |
|---|---|---|
| A `M09000001` | `C4.2c` **MET** | Out-of-network note rescues §4.2 |
| B `M09000002` | `C5.1` **NOT_MET** | Negated text correctly rejected — no false exclusion |
| C `M09000003` | `C5.1` **MET** | Buried family history correctly fires the exclusion |

Implementation notes:
- `SEARCH_PREVIEW` needs a **constant** second argument, so the resolver loops the config
  with `EXECUTE IMMEDIATE` rather than joining set-wise.
- Cursor fields aren't visible inside a nested `SELECT`; copy them to locals first.
- Stored-procedure bodies need `$$` delimiters, which the shell expands to a PID —
  use `python3 scripts/run_sql.py <file.sql>` for any SQL containing a procedure body.

### Golden cohort — the demo spine

Load order matters: `03_generate_bulk.sql` uses `CREATE OR REPLACE`, so golden rows
must be inserted **after** it. Ids start at `M09000001`, outside the bulk range.

| Member | Outcome | Design |
|---|---|---|
| **A** `M09000001` Elena Vasquez, 54 | `APPROVE` | Two rescues on **different** criteria — §4.1 saved by identity linkage, §4.2 saved by narrative evidence |
| **B** `M09000002` Marcus Thorne, 57 | `ROUTE_TO_CLINICIAN` | Only HbA1c on file is 210 days old. Value *is* elevated, so the failure is purely recency — makes "here is what's missing" crisp |
| **C** `M09000003` Priya Nakamura, 46 | `ROUTE_TO_CLINICIAN` | Every criterion passes; §5.1 exclusion (family history of MTC) is buried in an out-of-network consult note |

**Hero moment, verified live:**

```
naive query (current member_id only)  ->  0 metformin fills   -> would deny
V_DRUG_TRIAL (identity-linked)        ->  5.9 months, 6 fills -> §4.1a MET
                                          source: "Northstar Mutual Health"
```

Structured leaf status confirmed: A = 3.1/3.2a/3.3/4.1a MET, 4.2a+4.2b NOT_MET (note must
carry §4.2c). B = all MET except 3.3. C = all MET (only the exclusion can stop it).

Golden notes are hand-authored, not AI-generated: demo evidence must be exact and stable
across reruns. Bulk filler notes are AI-generated separately.
| Cortex Search services, semantic view, agent | |
| Streamlit console | |
| AI criteria extraction scored vs ground truth (CoCo set-piece) | |

### Data model, derived from the criteria tree

Deriving schema *from* the criteria (rather than the reverse) surfaced two
requirements that a naive claims model would have missed — and would have forced a
full regeneration to fix:

- **`RX_CLAIM.days_supply`** — §2.3 defines an adequate trial as *three consecutive
  months*, so consecutive-fill gap logic is required. Fill dates alone cannot prove it.
- **`MEMBER_LINK`** — §2.3 states trials under a prior member ID or prior carrier count.
  Without this table the hero demo is impossible.

| Table | Serves |
|---|---|
| `CORE.MEMBER` | §3.1 age |
| `CORE.MEMBER_LINK` | §2.3 prior-coverage linkage — **hero enabler** |
| `CORE.ELIGIBILITY` | plan/LOB scoping |
| `CORE.CLAIM` + `CORE.CLAIM_DIAGNOSIS` | §3.2a ICD-10 E11.* |
| `CORE.RX_CLAIM` | §4.1a, §4.2a, §4.2b step therapy |
| `CORE.LAB_RESULT` | §3.3 HbA1c (LOINC 4548-4) |
| `CORE.PROVIDER` | network status (hero note is out-of-network) |
| `CORE.PA_REQUEST` | the request under review |
| `DOCS.CLINICAL_NOTE` | every UNSTRUCTURED leaf |

## Judging rubric — the organizers published their own architecture

The challenge slide lists six capabilities. Treat it as the scoring sheet for
**Solution Completeness**, and name these primitives explicitly in the deck:

1. Generate fully synthetic EHR / claims / lab datasets
2. `AI_PARSE_DOCUMENT` to extract structure from clinical notes and regulatory filings
3. Patient 360 **semantic view** with risk stratification + care gap indicators
4. Cited evidence retrieval agent — every answer traces to a source document
5. Orchestrate: clinical question → evidence retrieval → risk score → recommended action
6. Care coordinator **Streamlit** app with explainable, auditable outputs

### Prototype deck required sections

Per the official template (`Prototype Submission Template _ CoCo CLI Hackathon GCC Edition.pptx`):

1. **Problem Brief** — business problem, target persona, current pain, domain context
2. **Architecture Diagram** — data flow, **which CoCo CLI skills are used and how they
   connect**, structured/unstructured sources, modular composition
3. **Impact Statement** — measurable outcomes, scalability, extension beyond the demo

Slide 1 needs: Team Name, Problem Statement, Team Leader Name, Team Size.

> The "which CoCo CLI **skills**" requirement is the single most-missed item. Author real
> skills in `.cortex/skills/` (`hcls-synthetic-data`, `policy-criteria-extractor`,
> `evidence-audit`) so they appear on the architecture diagram as named, connected
> components.

---

## Working conventions

- Every SQL change lands in `sql/NN_*.sql` first, then is executed — the repo must
  reproduce the whole build from scratch for the GitHub submission.
- Synthetic policy documents use a **fictional payer** and are watermarked as synthetic.
  Never generate a document that could be mistaken for a real insurer's actual policy.
- Impact-slide statistics (CMS-0057-F dates, AMA prior-auth burden figures) must be
  verified against current primary sources before submission. Prefer
  **measured-in-prototype** numbers ("11 days → 8 seconds on our synthetic cohort") over
  cited industry averages — judges trust a number you generated.
- Keep `COMPUTE_WH` at X-Small; drop unused Cortex Search services.

## Layout

```
sql/         00_setup.sql, then numbered build steps
data/
  generators/  deterministic synthetic data generators (seeded, reproducible)
  policies/    synthetic medical policy source + PDF builder
app/         Streamlit in Snowflake console
docs/        architecture diagram, demo script
.cortex/skills/  custom CoCo CLI skills
```
