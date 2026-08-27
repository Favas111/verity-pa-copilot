"""
Golden cohort — the three demo members, with every piece of evidence
deliberately planted.

    python3 data/generators/build_golden.py <outdir>

MUST run AFTER 03_generate_bulk.sql. The bulk script uses CREATE OR REPLACE
on CORE tables, so golden rows inserted first would be destroyed.

Member ids start at M09000001, outside the bulk range (M00000000-M00004999),
so the two populations never collide.

------------------------------------------------------------------------
The three demo beats
------------------------------------------------------------------------
A  M09000001  APPROVE
   Two independent rescues, on two different criteria:
     4.1  Six months of metformin exist, but ONLY under a PRIOR member id
          from a previous carrier. A step-therapy query scoped to the
          current member_id returns nothing. MEMBER_LINK + policy 2.3
          recover it -> MET.
     4.2  No SGLT2 or sulfonylurea fills exist at all, so both structured
          leaves genuinely fail. An OUT-OF-NETWORK consult note documents
          intolerance to both classes -> 4.2c MET.
   Naive system: deny twice. Verity: approve, with citations.

B  M09000002  ROUTE_TO_CLINICIAN
   Everything passes except 3.3 - the only HbA1c on file is 210 days old,
   outside the 90-day window. Proves the system does not rubber-stamp, and
   names precisely what is missing.

C  M09000003  ROUTE_TO_CLINICIAN
   Every coverage and step-therapy criterion passes. A consult note records
   a family history of medullary thyroid carcinoma, firing exclusion 5.1.
   Proves buried contraindications are caught before auto-approval.

Golden notes are hand-authored rather than AI_COMPLETE-generated: demo
evidence must be exact and stable across reruns. Bulk filler notes are
AI-generated separately (Tier 3).
"""

import json
import os
import sys
from datetime import date, timedelta

TODAY = date(2026, 8, 26)


def d(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


def monthly_fills(member_id, ndc, drug_name, prescriber, first_days_ago, n, tag):
    """n consecutive 30-day fills, oldest first."""
    out = []
    for k in range(n):
        out.append({
            "rx_claim_id": f"RXG-{tag}-{k:02d}",
            "member_id": member_id,
            "ndc": ndc,
            "fill_date": d(first_days_ago - k * 30),
            "days_supply": 30,
            "quantity": 30,
            "dose_text": drug_name,
            "prescriber_id": prescriber,
        })
    return out


# ======================================================================
# Members
# ======================================================================
MEMBERS = [
    {"member_id": "M09000001", "first_name": "Elena", "last_name": "Vasquez",
     "date_of_birth": "1972-03-14", "sex": "F", "state": "MN", "zip3": "554", "is_golden": True},
    {"member_id": "M09000002", "first_name": "Marcus", "last_name": "Thorne",
     "date_of_birth": "1968-09-02", "sex": "M", "state": "TX", "zip3": "770", "is_golden": True},
    {"member_id": "M09000003", "first_name": "Priya", "last_name": "Nakamura",
     "date_of_birth": "1979-11-21", "sex": "F", "state": "CA", "zip3": "941", "is_golden": True},
]

# Member A's prior identity under a previous carrier. Without this row the
# hero scenario cannot be evaluated at all.
MEMBER_LINKS = [
    {"member_id": "M09000001", "prior_member_id": "M08500001",
     "prior_carrier": "Northstar Mutual Health", "link_type": "CARRIER_CHANGE",
     "coverage_start": "2023-01-01", "coverage_end": "2025-03-31"},
]

ELIGIBILITY = [
    {"member_id": "M09000001", "plan_id": "PLAN-002", "lob": "Commercial",
     "coverage_start": "2025-04-01", "coverage_end": None},
    {"member_id": "M09000002", "plan_id": "PLAN-004", "lob": "Commercial",
     "coverage_start": "2024-01-01", "coverage_end": None},
    {"member_id": "M09000003", "plan_id": "PLAN-001", "lob": "Commercial",
     "coverage_start": "2023-06-01", "coverage_end": None},
]

# ======================================================================
# Providers — P90001 is deliberately OUT_OF_NETWORK. Its notes are the
# evidence that never reached structured claims.
# ======================================================================
PROVIDERS = [
    {"provider_id": "P900001", "npi": "9987650001",
     "provider_name": "Cedar Ridge Endocrine Associates", "specialty": "Endocrinology",
     "network_status": "OUT_OF_NETWORK"},
    {"provider_id": "P900002", "npi": "9987650002",
     "provider_name": "Lakeside Family Practice", "specialty": "Family Medicine",
     "network_status": "IN_NETWORK"},
    {"provider_id": "P900003", "npi": "9987650003",
     "provider_name": "Summit Internal Medicine", "specialty": "Internal Medicine",
     "network_status": "IN_NETWORK"},
]

# ======================================================================
# Claims — establish the E11.* diagnosis history for section 3.2a
# ======================================================================
CLAIMS, CLAIM_DX = [], []


def add_claim(cid, member, provider, days_ago, icd_list, billed):
    CLAIMS.append({
        "claim_id": cid, "member_id": member, "provider_id": provider,
        "service_date": d(days_ago), "claim_type": "PROFESSIONAL",
        "billed_amount": billed, "allowed_amount": round(billed * 0.52, 2),
    })
    for i, code in enumerate(icd_list, start=1):
        CLAIM_DX.append({"claim_id": cid, "seq": i, "icd10": code})


# Member A — regular T2DM management, in network
add_claim("CG-A-001", "M09000001", "P900002", 75, ["E11.9", "I10"], 245.00)
add_claim("CG-A-002", "M09000001", "P900002", 204, ["E11.9", "E78.5"], 198.00)
add_claim("CG-A-003", "M09000001", "P900002", 379, ["E11.65"], 312.00)
# The out-of-network endocrine consult. Present as a claim, but its clinical
# CONTENT lives only in the note.
add_claim("CG-A-004", "M09000001", "P900001", 554, ["E11.9"], 640.00)

# Member B
add_claim("CG-B-001", "M09000002", "P900003", 62, ["E11.65", "I10"], 267.00)
add_claim("CG-B-002", "M09000002", "P900003", 246, ["E11.65"], 221.00)
add_claim("CG-B-003", "M09000002", "P900003", 428, ["E11.9", "E66.9"], 289.00)

# Member C
add_claim("CG-C-001", "M09000003", "P900002", 41, ["E11.9"], 232.00)
add_claim("CG-C-002", "M09000003", "P900001", 104, ["E11.9", "E04.9"], 585.00)
add_claim("CG-C-003", "M09000003", "P900002", 287, ["E11.9", "E78.5"], 210.00)

# ======================================================================
# Pharmacy claims
# ======================================================================
RX = []

# --- Member A: metformin ONLY under the PRIOR member id -----------------
# Six consecutive 30-day fills. Oldest fill 730 days ago, newest 580 days
# ago -> a ~6.9 month continuous run, comfortably over the 3-month bar.
# Note member_id here is M08500001, NOT M09000001.
RX += monthly_fills("M08500001", "99999-0101-03", "Metformin HCl 1000 MG",
                    "P900001", first_days_ago=730, n=6, tag="A-MET")
# Member A has NO SGLT2 and NO sulfonylurea fills anywhere. Both structured
# leaves under 4.2 must genuinely fail so the note is what carries it.

# --- Member B: adequate metformin AND adequate SGLT2 --------------------
RX += monthly_fills("M09000002", "99999-0101-02", "Metformin HCl 850 MG",
                    "P900003", first_days_ago=442, n=8, tag="B-MET")
RX += monthly_fills("M09000002", "99999-0201-01", "Empagliflozin 10 MG",
                    "P900003", first_days_ago=359, n=5, tag="B-SGLT2")

# --- Member C: adequate metformin AND adequate sulfonylurea -------------
RX += monthly_fills("M09000003", "99999-0101-03", "Metformin HCl 1000 MG",
                    "P900002", first_days_ago=398, n=7, tag="C-MET")
RX += monthly_fills("M09000003", "99999-0301-02", "Glipizide 10 MG",
                    "P900002", first_days_ago=308, n=4, tag="C-SU")

# ======================================================================
# Labs — section 3.3 requires HbA1c >= 7.0 within 90 days
# ======================================================================
LABS = [
    # A: 34 days old -> inside the window. MET.
    {"lab_id": "LG-A-001", "member_id": "M09000001", "loinc": "4548-4",
     "test_name": "Hemoglobin A1c", "value_num": 8.4, "unit": "%",
     "collected_date": d(34), "abnormal_flag": "H"},
    {"lab_id": "LG-A-002", "member_id": "M09000001", "loinc": "4548-4",
     "test_name": "Hemoglobin A1c", "value_num": 8.1, "unit": "%",
     "collected_date": d(224), "abnormal_flag": "H"},

    # B: only result is 210 days old -> OUTSIDE the window. NOT_MET.
    # Value is elevated, so the failure is purely recency, which makes the
    # "here is exactly what is missing" message crisp.
    {"lab_id": "LG-B-001", "member_id": "M09000002", "loinc": "4548-4",
     "test_name": "Hemoglobin A1c", "value_num": 8.1, "unit": "%",
     "collected_date": d(210), "abnormal_flag": "H"},

    # C: 27 days old -> MET. Everything passes until exclusion 5.1 fires.
    {"lab_id": "LG-C-001", "member_id": "M09000003", "loinc": "4548-4",
     "test_name": "Hemoglobin A1c", "value_num": 9.2, "unit": "%",
     "collected_date": d(27), "abnormal_flag": "H"},
    {"lab_id": "LG-C-002", "member_id": "M09000003", "loinc": "4548-4",
     "test_name": "Hemoglobin A1c", "value_num": 8.8, "unit": "%",
     "collected_date": d(209), "abnormal_flag": "H"},
]

# ======================================================================
# Clinical notes
# ======================================================================
NOTES = [
    # ---- Member A: THE hero document -----------------------------------
    # Out-of-network endocrine consult. Documents intolerance to BOTH
    # second-line classes, satisfying 4.2c. Also corroborates the metformin
    # history that structured data only holds under the prior member id.
    {
        "note_id": "NG-A-001", "member_id": "M09000001", "provider_id": "P900001",
        "note_type": "CONSULT_NOTE", "note_date": d(554),
        "source_system": "CEDAR_RIDGE_EMR", "network_status": "OUT_OF_NETWORK",
        "note_text": (
            "ENDOCRINOLOGY CONSULTATION\n\n"
            "REASON FOR REFERRAL: Type 2 diabetes mellitus with inadequate glycemic "
            "control despite multiple oral agents.\n\n"
            "HISTORY OF PRESENT ILLNESS: 53-year-old woman with type 2 diabetes "
            "mellitus diagnosed approximately six years ago. She completed an extended "
            "course of metformin, titrated to 1000 mg twice daily, which she continued "
            "for roughly six months under her previous insurance coverage. Glycemic "
            "response was partial and she remained above target.\n\n"
            "MEDICATION TRIAL HISTORY:\n"
            "1. Metformin 1000 mg BID - completed approximately six months of continuous "
            "therapy at maximum tolerated dose. Discontinued when coverage lapsed during "
            "her carrier transition.\n"
            "2. Glipizide 10 mg daily - trial discontinued after the patient experienced "
            "recurrent symptomatic hypoglycemia, including two episodes requiring "
            "assistance and one documented capillary glucose of 48 mg/dL. Sulfonylurea "
            "therapy is not tolerated and should not be re-attempted.\n"
            "3. Empagliflozin 10 mg daily - trial discontinued due to recurrent urinary "
            "tract infections, three culture-positive episodes within four months, with "
            "one requiring intravenous antibiotics. SGLT2 inhibitor therapy is not "
            "tolerated in this patient.\n\n"
            "ASSESSMENT: Type 2 diabetes mellitus, suboptimally controlled. The patient "
            "has documented intolerance to both sulfonylurea and SGLT2 inhibitor "
            "classes. She has completed an adequate trial of metformin.\n\n"
            "PLAN: Given documented intolerance to both second-line oral classes, "
            "recommend proceeding to GLP-1 receptor agonist therapy. Will initiate prior "
            "authorization. No personal or family history of medullary thyroid carcinoma "
            "or multiple endocrine neoplasia. Patient is post-menopausal and not "
            "pregnant."
        ),
    },
    {
        "note_id": "NG-A-002", "member_id": "M09000001", "provider_id": "P900002",
        "note_type": "PROGRESS_NOTE", "note_date": d(75),
        "source_system": "MERIDIAN_EMR", "network_status": "IN_NETWORK",
        "note_text": (
            "PROGRESS NOTE - Diabetes follow-up\n\n"
            "SUBJECTIVE: Patient reports adherence to diet and exercise. No hypoglycemic "
            "episodes since discontinuing glipizide. No urinary symptoms.\n\n"
            "OBJECTIVE: BP 128/78. BMI 31.2. Recent HbA1c 8.4%.\n\n"
            "ASSESSMENT: Type 2 diabetes mellitus, above target.\n\n"
            "PLAN: Endocrinology has recommended GLP-1 receptor agonist. Prior "
            "authorization submitted. Continue lifestyle measures."
        ),
    },

    # ---- Member B: unremarkable. Nothing rescues the stale lab. ---------
    {
        "note_id": "NG-B-001", "member_id": "M09000002", "provider_id": "P900003",
        "note_type": "PROGRESS_NOTE", "note_date": d(62),
        "source_system": "MERIDIAN_EMR", "network_status": "IN_NETWORK",
        "note_text": (
            "PROGRESS NOTE - Routine diabetes management\n\n"
            "SUBJECTIVE: Patient reports good tolerance of current regimen. Taking "
            "metformin 850 mg twice daily and empagliflozin 10 mg daily. No adverse "
            "effects reported. No hypoglycemia. No genitourinary symptoms.\n\n"
            "OBJECTIVE: BP 134/82. Weight stable. Laboratory studies not repeated at "
            "this visit.\n\n"
            "ASSESSMENT: Type 2 diabetes mellitus. Glycemic status not currently "
            "documented; last HbA1c predates this visit by several months.\n\n"
            "PLAN: Order HbA1c prior to next visit. Discussed escalation to GLP-1 "
            "receptor agonist if remains above target. No personal or family history of "
            "thyroid malignancy."
        ),
    },

    # ---- Member C: the exclusion, buried in narrative -------------------
    {
        "note_id": "NG-C-001", "member_id": "M09000003", "provider_id": "P900001",
        "note_type": "CONSULT_NOTE", "note_date": d(104),
        "source_system": "CEDAR_RIDGE_EMR", "network_status": "OUT_OF_NETWORK",
        "note_text": (
            "ENDOCRINOLOGY CONSULTATION\n\n"
            "REASON FOR REFERRAL: Type 2 diabetes mellitus, evaluation for treatment "
            "intensification. Incidental thyroid nodule on prior imaging.\n\n"
            "HISTORY OF PRESENT ILLNESS: 46-year-old woman with type 2 diabetes "
            "mellitus. Currently on metformin 1000 mg twice daily with partial response. "
            "Previously completed a four-month trial of glipizide 10 mg daily.\n\n"
            "FAMILY HISTORY: Mother was diagnosed with medullary thyroid carcinoma at "
            "age 52 and underwent total thyroidectomy. Maternal grandmother had thyroid "
            "disease of unspecified type. Father has type 2 diabetes and hypertension. "
            "No known family history of multiple endocrine neoplasia syndrome, though "
            "formal genetic testing has not been performed.\n\n"
            "OBJECTIVE: Thyroid examination reveals a small right-sided nodule, "
            "approximately 8 mm, non-tender. Serum calcitonin pending.\n\n"
            "ASSESSMENT: Type 2 diabetes mellitus, suboptimally controlled. Thyroid "
            "nodule with a significant family history of medullary thyroid carcinoma.\n\n"
            "PLAN: Obtain calcitonin and thyroid ultrasound. Consider genetic counselling "
            "regarding RET mutation testing. Given the family history of medullary "
            "thyroid carcinoma, GLP-1 receptor agonist therapy warrants careful "
            "specialist review before initiation."
        ),
    },
    {
        "note_id": "NG-C-002", "member_id": "M09000003", "provider_id": "P900002",
        "note_type": "PROGRESS_NOTE", "note_date": d(41),
        "source_system": "MERIDIAN_EMR", "network_status": "IN_NETWORK",
        "note_text": (
            "PROGRESS NOTE - Diabetes follow-up\n\n"
            "SUBJECTIVE: Patient reports fatigue and increased thirst. Adherent to "
            "metformin.\n\n"
            "OBJECTIVE: HbA1c 9.2%. BP 126/80.\n\n"
            "ASSESSMENT: Type 2 diabetes mellitus, above target despite dual oral "
            "therapy.\n\n"
            "PLAN: Requesting prior authorization for GLP-1 receptor agonist. Awaiting "
            "endocrinology workup of thyroid nodule."
        ),
    },
]

# ======================================================================
# Prior authorization requests — all PENDING, awaiting adjudication
# ======================================================================
PA_REQUESTS = [
    {"pa_id": "PA-2026-000001", "member_id": "M09000001", "policy_id": "MHP-PA-0142",
     "requested_ndc": "99999-0401-02", "requested_drug": "Semaglutide 0.5 MG/DOSE",
     "request_date": d(6), "date_of_service": d(6), "prescriber_id": "P900001",
     "status": "PENDING", "decision_date": None},
    {"pa_id": "PA-2026-000002", "member_id": "M09000002", "policy_id": "MHP-PA-0142",
     "requested_ndc": "99999-0401-01", "requested_drug": "Semaglutide 0.25 MG/DOSE",
     "request_date": d(4), "date_of_service": d(4), "prescriber_id": "P900003",
     "status": "PENDING", "decision_date": None},
    {"pa_id": "PA-2026-000003", "member_id": "M09000003", "policy_id": "MHP-PA-0142",
     "requested_ndc": "99999-0402-01", "requested_drug": "Dulaglutide 0.75 MG/0.5ML",
     "request_date": d(3), "date_of_service": d(3), "prescriber_id": "P900002",
     "status": "PENDING", "decision_date": None},
]

TABLES = {
    "golden_member": MEMBERS,
    "golden_member_link": MEMBER_LINKS,
    "golden_eligibility": ELIGIBILITY,
    "golden_provider": PROVIDERS,
    "golden_claim": CLAIMS,
    "golden_claim_diagnosis": CLAIM_DX,
    "golden_rx_claim": RX,
    "golden_lab_result": LABS,
    "golden_clinical_note": NOTES,
    "golden_pa_request": PA_REQUESTS,
}


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    for name, rows in TABLES.items():
        path = os.path.join(outdir, f"{name}.ndjson")
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
