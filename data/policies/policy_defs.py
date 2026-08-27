"""
Synthetic medical policy definitions for VERITY.

IMPORTANT: Meridian Health Plan is a FICTIONAL payer. These documents are
synthetic and exist solely to demonstrate document parsing and criteria
extraction. They are watermarked as such and must never be presented as,
or mistaken for, a real insurer's medical policy.

This module holds TWO things per policy:

  SECTIONS  - the prose, used to render the policy PDF (build_policies.py).
              That PDF is what AI_PARSE_DOCUMENT consumes.

  TREE      - the GROUND TRUTH criteria tree. After the pipeline extracts
              criteria from the parsed PDF, we score that extraction against
              this tree, producing a real accuracy number for the
              "Technical Execution" judging criterion instead of a vibe.

Single source of truth: the tree is defined ONLY here. Do not duplicate
criterion metadata into SECTIONS, or the two will drift.

------------------------------------------------------------------------
Tree model
------------------------------------------------------------------------
Every node is either a GROUP or a LEAF.

  GROUP  combinator = ALL_OF   -> every child must be MET
                      ANY_OF   -> at least one child must be MET
                      NONE_OF  -> no child may be MET (exclusions)

  LEAF   evidence_type = STRUCTURED    -> SQL over the semantic view
                         UNSTRUCTURED  -> Cortex Search over clinical notes

Note that leaves are deliberately single-source. Where a policy criterion
admits two routes ("an adequate trial ... OR a documented intolerance"),
it becomes an ANY_OF group over one STRUCTURED and one UNSTRUCTURED leaf.
That is what lets the console show the structured check failing and the
unstructured check satisfying it - the structured/unstructured join made
visible, which is the core of the demo.

`test_expr` is the human-readable contract for the resolver that will
evaluate the leaf. It is not executed directly.
"""

WATERMARK = "SYNTHETIC DOCUMENT - FICTIONAL PAYER - HACKATHON DEMONSTRATION ONLY"

# ======================================================================
# MHP-PA-0142 - GLP-1 receptor agonists for T2DM
# ======================================================================

MHP_PA_0142 = {
    "policy_id": "MHP-PA-0142",
    "title": "Glucagon-Like Peptide-1 (GLP-1) Receptor Agonists for Type 2 Diabetes Mellitus",
    "payer": "Meridian Health Plan",
    "version": "3.0",
    "effective_date": "2026-01-15",
    "supersedes_version": "2.4",
    "supersedes_effective_date": "2025-01-01",
    "review_date": "2027-01-15",
    "lob": "Commercial",
    "sections": [
        {
            "ref": "1",
            "heading": "PURPOSE AND SCOPE",
            "body": [
                "This policy establishes the medical necessity criteria applied by Meridian "
                "Health Plan when reviewing prior authorization requests for glucagon-like "
                "peptide-1 (GLP-1) receptor agonists prescribed for the treatment of Type 2 "
                "Diabetes Mellitus (T2DM).",
                "This policy applies to Commercial lines of business. Requests for GLP-1 "
                "receptor agonists prescribed for weight management are governed by a "
                "separate policy and are outside the scope of this document.",
                "Determinations under this policy must be made against the policy version in "
                "effect on the date of service, not the version in effect on the date of review.",
            ],
        },
        {
            "ref": "2",
            "heading": "DEFINITIONS",
            "body": [],
            "subsections": [
                {
                    "ref": "2.1",
                    "heading": "Maximum Tolerated Dose",
                    "body": [
                        "The highest dose of a medication that the member is able to take "
                        "without experiencing adverse effects that materially interfere with "
                        "daily functioning, as documented by the prescribing provider."
                    ],
                },
                {
                    "ref": "2.2",
                    "heading": "Documented Intolerance",
                    "body": [
                        "A clinically significant adverse reaction to a medication that is "
                        "recorded in the member's medical record by a licensed provider. "
                        "Documented intolerance includes, but is not limited to, persistent "
                        "gastrointestinal intolerance, lactic acidosis, or hypersensitivity "
                        "reaction. A provider attestation in a progress note, discharge "
                        "summary, or consultation note constitutes acceptable documentation."
                    ],
                },
                {
                    "ref": "2.3",
                    "heading": "Adequate Trial",
                    "body": [
                        "A continuous course of therapy lasting at least three (3) consecutive "
                        "months at the maximum tolerated dose.",
                        "A trial completed under a prior Meridian Health Plan product, under a "
                        "prior member identifier, or under prior coverage from another carrier "
                        "SHALL count toward this requirement, provided that documentation of "
                        "the trial is available in the member's claims history or medical record.",
                        "Trials need not have occurred within the current plan year.",
                    ],
                },
            ],
        },
        {
            "ref": "3",
            "heading": "COVERAGE CRITERIA - INITIAL AUTHORIZATION",
            "body": [
                "All criteria in Section 3 AND all criteria in Section 4 must be met, and no "
                "exclusion in Section 5 may apply."
            ],
            "subsections": [
                {
                    "ref": "3.1",
                    "heading": "Age",
                    "body": [
                        "The member is eighteen (18) years of age or older on the date of service."
                    ],
                },
                {
                    "ref": "3.2",
                    "heading": "Diagnosis",
                    "body": [
                        "The member has a documented diagnosis of Type 2 Diabetes Mellitus, "
                        "evidenced by an ICD-10-CM code in the E11 category submitted on at "
                        "least one (1) claim within the preceding twelve (12) months, or "
                        "documented in the medical record."
                    ],
                },
                {
                    "ref": "3.3",
                    "heading": "Glycemic Control",
                    "body": [
                        "A hemoglobin A1c (HbA1c) laboratory result of greater than or equal to "
                        "7.0% obtained within ninety (90) days prior to the date of the request."
                    ],
                },
            ],
        },
        {
            "ref": "4",
            "heading": "STEP THERAPY REQUIREMENTS",
            "body": [
                "The member must have completed an adequate trial, as defined in Section 2.3, "
                "of the agents specified below, OR have a documented intolerance or "
                "contraindication to each."
            ],
            "subsections": [
                {
                    "ref": "4.1",
                    "heading": "First-Line Agent - Metformin",
                    "body": [
                        "An adequate trial of metformin at the maximum tolerated dose, OR a "
                        "documented intolerance or contraindication to metformin as defined in "
                        "Section 2.2.",
                        "Contraindications to metformin include eGFR below 30 mL/min/1.73m2, "
                        "acute or chronic metabolic acidosis, and known hypersensitivity.",
                    ],
                },
                {
                    "ref": "4.2",
                    "heading": "Second-Line Agent",
                    "body": [
                        "An adequate trial of EITHER a sodium-glucose cotransporter-2 (SGLT2) "
                        "inhibitor OR a sulfonylurea, OR a documented intolerance or "
                        "contraindication to both classes."
                    ],
                },
            ],
        },
        {
            "ref": "5",
            "heading": "EXCLUSIONS",
            "body": [
                "Authorization SHALL NOT be issued under this policy, and the request must be "
                "referred to a clinical reviewer, if any of the following apply."
            ],
            "subsections": [
                {
                    "ref": "5.1",
                    "heading": "Thyroid Malignancy Risk",
                    "body": [
                        "A personal or family history of medullary thyroid carcinoma (MTC), or a "
                        "personal history of Multiple Endocrine Neoplasia syndrome type 2 (MEN2). "
                        "Family history documented in a clinical note is sufficient to trigger "
                        "this exclusion."
                    ],
                },
                {
                    "ref": "5.2",
                    "heading": "Pregnancy",
                    "body": [
                        "The member is currently pregnant, or has documented intent to conceive "
                        "within the authorization period."
                    ],
                },
                {
                    "ref": "5.3",
                    "heading": "Prior Hypersensitivity",
                    "body": [
                        "A documented history of severe hypersensitivity reaction to any GLP-1 "
                        "receptor agonist."
                    ],
                },
            ],
        },
        {
            "ref": "6",
            "heading": "AUTHORIZATION DURATION",
            "body": [
                "Initial authorizations approved under this policy are granted for a period of "
                "twelve (12) months from the date of approval."
            ],
        },
        {
            "ref": "7",
            "heading": "REAUTHORIZATION CRITERIA",
            "body": [
                "Continuation of therapy requires documentation of a reduction in HbA1c of at "
                "least 0.5 percentage points from the pre-treatment baseline, OR attainment of "
                "an HbA1c below 7.0%, together with confirmation of ongoing treatment adherence."
            ],
        },
        {
            "ref": "8",
            "heading": "DOCUMENT HISTORY",
            "body": [
                "Version 3.0, effective 2026-01-15. Revised Section 2.3 to clarify that trials "
                "completed under prior coverage count toward step therapy requirements. Revised "
                "Section 4.2 to permit SGLT2 inhibitors as an alternative to sulfonylureas.",
                "Version 2.4, effective 2025-01-01. Superseded.",
            ],
        },
    ],
}

# ----------------------------------------------------------------------
# Ground truth criteria tree
# ----------------------------------------------------------------------
# node_id is unique within the policy. Children are evaluated bottom-up and
# rolled up by the GROUP combinator. ROOT's verdict is the determination.

MHP_PA_0142_TREE = {
    "policy_id": "MHP-PA-0142",
    "policy_version": "3.0",
    "nodes": [
        {
            "node_id": "ROOT", "parent_id": None, "node_type": "GROUP",
            "combinator": "ALL_OF", "section_ref": "3",
            "label": "Medical necessity established for GLP-1 receptor agonist",
        },

        # --- Section 3: coverage criteria -----------------------------
        {
            "node_id": "S3", "parent_id": "ROOT", "node_type": "GROUP",
            "combinator": "ALL_OF", "section_ref": "3",
            "label": "Coverage criteria - initial authorization",
        },
        {
            "node_id": "C3.1", "parent_id": "S3", "node_type": "LEAF",
            "section_ref": "3.1", "evidence_type": "STRUCTURED",
            "label": "Member is 18 years or older on the date of service",
            "test_expr": "member_age_on_dos >= 18",
        },
        {
            "node_id": "G3.2", "parent_id": "S3", "node_type": "GROUP",
            "combinator": "ANY_OF", "section_ref": "3.2",
            "label": "Documented diagnosis of Type 2 Diabetes Mellitus",
        },
        {
            "node_id": "C3.2a", "parent_id": "G3.2", "node_type": "LEAF",
            "section_ref": "3.2", "evidence_type": "STRUCTURED",
            "label": "ICD-10 E11.* on a claim within the preceding 12 months",
            "test_expr": "EXISTS claim_diagnosis WHERE icd10 LIKE 'E11%' AND svc_date >= DATEADD(month,-12,dos)",
        },
        {
            "node_id": "C3.2b", "parent_id": "G3.2", "node_type": "LEAF",
            "section_ref": "3.2", "evidence_type": "UNSTRUCTURED",
            "label": "T2DM diagnosis documented in the medical record",
            "test_expr": "clinical_note asserts diagnosis of type 2 diabetes mellitus",
        },
        {
            "node_id": "C3.3", "parent_id": "S3", "node_type": "LEAF",
            "section_ref": "3.3", "evidence_type": "STRUCTURED",
            "label": "HbA1c >= 7.0% within 90 days prior to the request",
            "test_expr": "MAX(lab_result WHERE loinc='4548-4' AND collected >= DATEADD(day,-90,request_date)) >= 7.0",
        },

        # --- Section 4: step therapy ----------------------------------
        {
            "node_id": "S4", "parent_id": "ROOT", "node_type": "GROUP",
            "combinator": "ALL_OF", "section_ref": "4",
            "label": "Step therapy requirements",
        },
        {
            "node_id": "G4.1", "parent_id": "S4", "node_type": "GROUP",
            "combinator": "ANY_OF", "section_ref": "4.1",
            "label": "First-line agent: metformin trial or documented intolerance",
        },
        {
            # THE HERO CRITERION. Per section 2.3 the trial may fall in a prior
            # plan year or under a prior member id, so the resolver must search
            # the member's full linked Rx history - not the current plan year.
            "node_id": "C4.1a", "parent_id": "G4.1", "node_type": "LEAF",
            "section_ref": "4.1", "evidence_type": "STRUCTURED",
            "label": "Adequate trial of metformin (>= 3 consecutive months, any coverage period)",
            "test_expr": "max_consecutive_months(rx_fills WHERE drug_class='BIGUANIDE') >= 3 ACROSS ALL linked_member_ids",
        },
        {
            "node_id": "C4.1b", "parent_id": "G4.1", "node_type": "LEAF",
            "section_ref": "4.1", "evidence_type": "UNSTRUCTURED",
            "label": "Documented metformin intolerance or contraindication",
            "test_expr": "clinical_note documents intolerance/contraindication to metformin per section 2.2",
        },
        {
            "node_id": "G4.2", "parent_id": "S4", "node_type": "GROUP",
            "combinator": "ANY_OF", "section_ref": "4.2",
            "label": "Second-line agent: SGLT2i or sulfonylurea trial, or intolerance to both",
        },
        {
            "node_id": "C4.2a", "parent_id": "G4.2", "node_type": "LEAF",
            "section_ref": "4.2", "evidence_type": "STRUCTURED",
            "label": "Adequate trial of an SGLT2 inhibitor (>= 3 consecutive months)",
            "test_expr": "max_consecutive_months(rx_fills WHERE drug_class='SGLT2_INHIBITOR') >= 3",
        },
        {
            "node_id": "C4.2b", "parent_id": "G4.2", "node_type": "LEAF",
            "section_ref": "4.2", "evidence_type": "STRUCTURED",
            "label": "Adequate trial of a sulfonylurea (>= 3 consecutive months)",
            "test_expr": "max_consecutive_months(rx_fills WHERE drug_class='SULFONYLUREA') >= 3",
        },
        # Decomposed per drug class rather than a single "intolerance to both"
        # leaf. Discovered via the blind extraction run (run2-blind): a single
        # leaf can only be satisfied by one chunk asserting BOTH classes, so it
        # silently fails whenever a note documents each class in separate
        # paragraphs — which is how real consult notes read. Our own hero note
        # passed only because it happened to contain a summarising sentence.
        # Splitting per class and combining with ALL_OF is robust to evidence
        # spread across chunks or across different notes.
        {
            "node_id": "G4.2int", "parent_id": "G4.2", "node_type": "GROUP",
            "combinator": "ALL_OF", "section_ref": "4.2",
            "label": "Documented intolerance to BOTH second-line classes",
        },
        {
            "node_id": "C4.2c", "parent_id": "G4.2int", "node_type": "LEAF",
            "section_ref": "4.2", "evidence_type": "UNSTRUCTURED",
            "label": "Documented intolerance or contraindication to SGLT2 inhibitors",
            "test_expr": "clinical_note documents intolerance/contraindication to SGLT2 inhibitors",
        },
        {
            "node_id": "C4.2d", "parent_id": "G4.2int", "node_type": "LEAF",
            "section_ref": "4.2", "evidence_type": "UNSTRUCTURED",
            "label": "Documented intolerance or contraindication to sulfonylureas",
            "test_expr": "clinical_note documents intolerance/contraindication to sulfonylureas",
        },

        # --- Section 5: exclusions ------------------------------------
        # NONE_OF: if any child is MET, the exclusion fires and the request
        # is routed to a clinician. Never auto-denied.
        {
            "node_id": "S5", "parent_id": "ROOT", "node_type": "GROUP",
            "combinator": "NONE_OF", "section_ref": "5",
            "label": "No exclusion applies",
        },
        {
            "node_id": "C5.1", "parent_id": "S5", "node_type": "LEAF",
            "section_ref": "5.1", "evidence_type": "UNSTRUCTURED",
            "label": "Personal or family history of medullary thyroid carcinoma or MEN2",
            "test_expr": "clinical_note documents personal OR family history of MTC or MEN2",
        },
        {
            "node_id": "C5.2", "parent_id": "S5", "node_type": "LEAF",
            "section_ref": "5.2", "evidence_type": "UNSTRUCTURED",
            "label": "Current pregnancy or documented intent to conceive",
            "test_expr": "clinical_note or claim documents pregnancy or intent to conceive",
        },
        {
            "node_id": "C5.3", "parent_id": "S5", "node_type": "LEAF",
            "section_ref": "5.3", "evidence_type": "UNSTRUCTURED",
            "label": "Prior severe hypersensitivity to any GLP-1 receptor agonist",
            "test_expr": "clinical_note documents severe hypersensitivity reaction to a GLP-1 RA",
        },
    ],
}

ALL_POLICIES = [MHP_PA_0142]
ALL_TREES = [MHP_PA_0142_TREE]
