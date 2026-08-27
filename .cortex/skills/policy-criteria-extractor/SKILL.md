---
name: policy-criteria-extractor
description: >
  Turn a parsed medical policy document into a machine-checkable criteria tree in
  VERITY.POLICY.POLICY_CRITERIA. Use when asked to extract, rebuild, or refresh the
  criteria tree for a policy id such as MHP-PA-0142, or when a new policy PDF has
  been parsed into VERITY.DOCS.POLICY_PARSED and needs to become checkable rules.
---

# Policy criteria extractor

Converts the prose of a medical policy into the **Criteria Ledger** — a tree of
individually checkable nodes that a deterministic rollup can evaluate. The language
model reads the policy and proposes structure; it never renders a coverage decision.

## Why a tree and not a list

A determination is an AND/OR rollup, not a checklist. Section 3 criteria must *all*
hold; section 4 offers alternative routes ("an adequate trial **or** a documented
intolerance"); section 5 exclusions must *none* hold. Flattening that to a list loses
the logic that decides the outcome.

## Node model

Every node is a GROUP or a LEAF.

| Field | Applies to | Values |
|---|---|---|
| `node_type` | all | `GROUP` \| `LEAF` |
| `combinator` | GROUP | `ALL_OF` \| `ANY_OF` \| `NONE_OF` |
| `evidence_type` | LEAF | `STRUCTURED` \| `UNSTRUCTURED` |
| `section_ref` | all | the policy section, e.g. `4.1` — this becomes the citation |
| `test_expr` | LEAF | human-readable contract for the resolver |

Rules that matter:

1. **Leaves are single-source.** A criterion offering two routes becomes an `ANY_OF`
   group over one `STRUCTURED` leaf and one `UNSTRUCTURED` leaf. This is what lets the
   console show a structured check failing while narrative evidence carries it.
2. **Exclusions use `NONE_OF`.** If any child is MET the exclusion has fired.
3. **`section_ref` must match a real heading in the parsed document.** It is the
   citation shown to a reviewer — a wrong reference is worse than no reference.
4. **Definitions sections are not criteria.** Sections defining terms (for example
   "adequate trial") constrain how a leaf is evaluated; fold that meaning into
   `test_expr` rather than emitting a node.
5. **Never emit a DENY path.** Outcomes are approve or route-to-clinician only.

## This is a blind extraction

**Your only permitted input is the parsed policy document.**

A hand-authored answer key exists so this extraction can be scored. Reading it — or any
previously extracted tree — invalidates the measurement completely, turning it from
"can this policy be read correctly" into "can this table be copied". That is worse than
no measurement, because it produces a confident number that is meaningless.

**Do not query** `VERITY.EVAL.CRITERIA_ANSWER_KEY`, `VERITY.POLICY.POLICY_CRITERIA`, or
any prior row in `VERITY.EVAL.CRITERIA_SUBMISSION`. Derive the tree solely from
`VERITY.DOCS.POLICY_PARSED`.

Use whatever node id convention you find natural. Scoring matches on structure —
section reference, node type, combinator, evidence type — never on node names, so you
lose nothing by naming them your own way. Matching someone else's naming scheme is
evidence of copying, not of accuracy.

## Procedure

1. Read the parsed policy — this is your only source:

   ```sql
   SELECT parsed:content::STRING
   FROM VERITY.DOCS.POLICY_PARSED
   WHERE policy_id = '<POLICY_ID>';
   ```

   Headings arrive as markdown — `#` for sections, `##` for subsections.

2. Identify which sections carry *coverage criteria*, *step therapy*, and *exclusions*.
   Ignore purpose, scope, duration, reauthorization, and document history.

3. Build the tree, honoring the node rules above.

4. Write it to `VERITY.EVAL.CRITERIA_SUBMISSION` with a `run_label` you choose
   (for example `run2-blind`). Insert only; do not delete or modify existing rows.

5. Report your tree as a table — node id, parent, type, combinator or evidence type,
   section ref, label — and state plainly which readings you were unsure about.

## What good work looks like

Genuine uncertainty is the valuable output here. A policy sentence like
"documented in the medical record" may or may not warrant its own unstructured leaf;
an exclusion may be a hard stop or a relative caution. Say which calls were judgement
calls and why you decided as you did.

Do not tune your answer toward what you imagine the key says. A defensible tree that
diverges from the key is a finding about the policy's ambiguity — that is genuinely
useful. A tree that matches because it was copied teaches nothing and misrepresents
the system's capability.

Scoring is run separately, by the project owner, using
`python3 scripts/score_extraction.py <run_label>`.
