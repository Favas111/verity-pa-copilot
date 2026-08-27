#!/usr/bin/env python3
"""
Score a blind criteria-extraction run against the held-out answer key.

    python3 scripts/score_extraction.py run2-blind

Run by the project owner, never by the agent being scored.

------------------------------------------------------------------------
Structural matching
------------------------------------------------------------------------
Nodes are matched on (section_ref, node_type, combinator, evidence_type),
NOT on node_id. Node names are arbitrary: an extractor that names a leaf
`leaf_4_1_a` is not wrong, and one that reproduces our exact `C4.1a`
convention has almost certainly seen the key rather than derived it.

------------------------------------------------------------------------
Contamination check
------------------------------------------------------------------------
Independent derivation from prose does not reproduce another author's
labels word for word. So the score is reported alongside the proportion of
labels that are byte-identical to the key. A high identical-label rate
means the run was contaminated and its score must be discarded.

This check exists because run 1 scored 19/19 with all 19 labels identical
and our exact node-id convention — it had read the key, which at the time
sat in the same table it was writing to.
"""

import json
import subprocess
import sys

CONN = "hackathon"


def q(sql):
    p = subprocess.run(
        ["snow", "sql", "-c", CONN, "-q", sql, "--format", "json"],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        sys.exit(f"query failed:\n{p.stdout}\n{p.stderr}")
    out = p.stdout.strip()
    start = out.find("[")
    if start == -1:
        return []
    return json.loads(out[start:])


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: score_extraction.py <run_label>")
    run = sys.argv[1].replace("'", "''")

    key = q("""SELECT node_type, combinator, section_ref, evidence_type, label
               FROM VERITY.EVAL.CRITERIA_ANSWER_KEY""")
    sub = q(f"""SELECT node_type, combinator, section_ref, evidence_type, label
                FROM VERITY.EVAL.CRITERIA_SUBMISSION WHERE run_label = '{run}'""")

    if not sub:
        sys.exit(f"no submission rows found for run_label '{sys.argv[1]}'")

    def sig(r):
        return (
            (r.get("SECTION_REF") or "").strip(),
            (r.get("NODE_TYPE") or "").strip(),
            (r.get("COMBINATOR") or "-").strip(),
            (r.get("EVIDENCE_TYPE") or "-").strip(),
        )

    key_sigs, sub_sigs = [sig(r) for r in key], [sig(r) for r in sub]
    remaining = list(key_sigs)
    matched = 0
    for s in sub_sigs:
        if s in remaining:
            remaining.remove(s)
            matched += 1

    missed = len(key_sigs) - matched
    extra = len(sub_sigs) - matched
    pct = 100.0 * matched / len(key_sigs) if key_sigs else 0.0

    key_labels = {(r.get("LABEL") or "").strip() for r in key}
    identical = sum(1 for r in sub if (r.get("LABEL") or "").strip() in key_labels)
    ident_pct = 100.0 * identical / len(sub)

    print(f"\nRun: {sys.argv[1]}")
    print(f"  answer key nodes : {len(key_sigs)}")
    print(f"  submitted nodes  : {len(sub_sigs)}")
    print(f"  structural match : {matched}/{len(key_sigs)}  ({pct:.0f}%)")
    print(f"  missed           : {missed}")
    print(f"  extra            : {extra}")
    print(f"\n  labels identical to key : {identical}/{len(sub)} ({ident_pct:.0f}%)")

    if ident_pct >= 60:
        print("\n  ** CONTAMINATED — discard this score. **")
        print("  Independent derivation does not reproduce another author's wording")
        print("  at this rate. The run almost certainly read the answer key.")
    elif ident_pct >= 25:
        print("\n  ! Elevated label overlap — inspect before trusting the score.")
    else:
        print("\n  Label overlap is low: consistent with independent derivation.")

    if missed or extra:
        print("\n  Unmatched signatures (section, type, combinator, evidence):")
        for s in remaining:
            print(f"    MISSED  {s}")
        used = list(key_sigs)
        for s in sub_sigs:
            if s in used:
                used.remove(s)
            else:
                print(f"    EXTRA   {s}")


if __name__ == "__main__":
    main()
