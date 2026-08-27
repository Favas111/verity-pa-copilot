# CoCo CLI transcript — blind criteria extraction

**Skill:** `policy-criteria-extractor` (custom, `.cortex/skills/`)
**Run label:** `run2-blind`
**Policy:** `MHP-PA-0142` — GLP-1 receptor agonists for T2DM
**Result:** 21/21 structural match · 0/21 identical labels · **2 nodes the human tree lacked**

---

## Run 1 — discarded (contaminated)

The first attempt scored 19/19, 100% — and was worthless. All 19 labels came back
byte-identical to the hand-authored tree, including invented node-id conventions
(`C4.1a`, `G4.1`, `S3`) that appear nowhere in the policy PDF.

The answer key was sitting in `POLICY.POLICY_CRITERIA`, the same table the extractor was
told to write to. It read the key rather than deriving from the document, measuring
"can it copy" instead of "can it extract".

This was an eval-design fault, not a model failure. Corrected by moving the key to a
held-out `EVAL` schema, scoring structurally rather than by node id, and adding a
contamination detector to `scripts/score_extraction.py`.

---

## Run 2 — blind, valid

Inputs restricted to `VERITY.DOCS.POLICY_PARSED`. CoCo used its own naming convention
(`L3.1`, `G4.2int`, `L4.2c`) and did not score its own work.

### Extracted tree — 21 nodes (8 GROUP, 13 LEAF)

```
ROOT [GROUP ALL_OF §3] — Initial Authorization
├── G3 [GROUP ALL_OF §3] — Coverage Criteria
│   ├── L3.1  [LEAF STRUCTURED §3.1]  — Age >= 18
│   ├── G3.2  [GROUP ANY_OF §3.2]     — Diagnosis of T2DM
│   │   ├── L3.2s [LEAF STRUCTURED]   — E11.* on claim within 12 months
│   │   └── L3.2u [LEAF UNSTRUCTURED] — T2DM in medical record
│   └── L3.3  [LEAF STRUCTURED §3.3]  — HbA1c >= 7.0% within 90 days
├── G4 [GROUP ALL_OF §4] — Step Therapy
│   ├── G4.1  [GROUP ANY_OF §4.1]     — Metformin
│   │   ├── L4.1s [LEAF STRUCTURED]   — Adequate trial (3+ months rx claims)
│   │   └── L4.1u [LEAF UNSTRUCTURED] — Intolerance/contraindication documented
│   └── G4.2  [GROUP ANY_OF §4.2]     — Second-Line Agent
│       ├── L4.2a [LEAF STRUCTURED]   — SGLT2i adequate trial
│       ├── L4.2b [LEAF STRUCTURED]   — Sulfonylurea adequate trial
│       └── G4.2int [GROUP ALL_OF]    — Intolerance to BOTH classes
│           ├── L4.2c [LEAF UNSTRUCTURED] — SGLT2i intolerance
│           └── L4.2d [LEAF UNSTRUCTURED] — Sulfonylurea intolerance
└── G5 [GROUP NONE_OF §5] — Exclusions
    ├── L5.1 [LEAF UNSTRUCTURED §5.1] — MTC/MEN2 history
    ├── L5.2 [LEAF UNSTRUCTURED §5.2] — Pregnancy/intent to conceive
    └── L5.3 [LEAF UNSTRUCTURED §5.3] — Prior GLP-1 hypersensitivity
```

### Judgement calls, in CoCo's own words

Reproduced because they are a genuine account of where the policy language is ambiguous —
useful for the architecture slide and for anyone extending this to a second policy.

> **1. §3.2 split into two leaves vs one.** The policy says "ICD-10 … on at least one claim
> … OR documented in the medical record." I read "or" as offering two independent evidence
> routes — one checkable via claims data, one via notes — so I modeled it as an ANY_OF group
> with a STRUCTURED and an UNSTRUCTURED leaf. A reasonable alternative would be a single
> STRUCTURED leaf (since most payers operationally rely on claims codes and treat
> "documented in medical record" as the override pathway, not a first-class route). I chose
> the split because the single-source rule says a criterion offering two routes should be
> decomposed.
>
> **2. §3.3 as purely STRUCTURED.** HbA1c is a lab value. The policy doesn't explicitly
> offer a medical-record-narrative alternative. I kept it as one STRUCTURED leaf. An
> argument could be made that a clinician's note quoting an external lab should count — but
> the policy says "laboratory result," which I read as the structured lab feed.
>
> **3. §4.2 intolerance sub-group.** The policy says "a documented intolerance or
> contraindication to both classes." This means a single intolerance note (covering only
> SGLT2i but not sulfonylureas) doesn't satisfy the escape. I modeled this as an ALL_OF
> group requiring documentation for each class independently. The alternative — a single
> UNSTRUCTURED leaf whose test_expr demands both — is functionally equivalent but loses
> granularity in the evidence packet.
>
> **4. §5.2 as one UNSTRUCTURED leaf.** Pregnancy could be detected structurally (ICD-10
> Z33/O-codes on claims). But "documented intent to conceive" is purely narrative, and the
> policy phrases them as a single disjunctive condition. I kept it as one UNSTRUCTURED leaf.
> A more aggressive decomposition would split pregnancy (STRUCTURED) from intent-to-conceive
> (UNSTRUCTURED) under an ANY_OF. I chose not to because the policy treats them as a single
> exclusion criterion and the operational expectation is clinical-note review.
>
> **5. §5.1 as one leaf.** "Personal or family history of MTC" and "personal history of
> MEN2" are combined in a single sentence. I read these as facets of one exclusion (thyroid
> malignancy risk) rather than two independent exclusions. They share the same clinical
> concern and would always be reviewed together.
>
> **6. ROOT section_ref = '3'.** The preamble "All criteria in Section 3 AND all criteria in
> Section 4…" appears under the §3 heading. Strictly the root spans §3–§5. I assigned
> section_ref = '3' because that's where the combining sentence lives. This is cosmetic —
> the rollup doesn't depend on the root's section_ref.

---

## Adjudication — judgement call 3 was right, and the human tree was wrong

Call 3 identified a genuine defect in the hand-authored key. Verified against
`POLICY.LEAF_EVIDENCE` for member `M09000001`:

| Retrieved chunk | Single-leaf verdict |
|---|---|
| "Empagliflozin … discontinued due to recurrent urinary tract infections" | `False` — covers one class |
| "Glipizide … discontinued after recurrent symptomatic hypoglycemia" | `False` — covers one class |
| "documented intolerance to **both** sulfonylurea and SGLT2 inhibitor classes" | `True` |

Under the single-leaf design, **only the summarising sentence satisfied the criterion**.
Both passages carrying the actual clinical detail were rejected. The hero demo passed only
because that note happens to summarise itself; a realistically-written note documenting
each intolerance separately would have returned `NOT_MET` and routed an approvable member
to a clinician.

Decomposition adopted into `POLICY_CRITERIA`, `policy_defs.py`, and `LEAF_RESOLVER`.
Re-verified: `C4.2c` is now affirmed by the detailed empagliflozin passage rather than the
summary. Answer key corrected to 21 nodes.

Scoring is run by the project owner, never the extractor:

```bash
python3 scripts/score_extraction.py run2-blind
```
