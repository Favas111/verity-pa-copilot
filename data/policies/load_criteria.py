"""
Emit the ground-truth criteria tree + policy registry as NDJSON for loading
into Snowflake.

    python3 data/policies/load_criteria.py <outdir>

Writes:
    <outdir>/policy_registry.ndjson
    <outdir>/policy_criteria.ndjson

We go via NDJSON + PUT + COPY INTO rather than generating INSERT statements
because policy text contains apostrophes, percent signs and parentheses that
are painful to escape through the shell into `snow sql -q`. Semi-structured
loading sidesteps quoting entirely and is how this would be done for real.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from policy_defs import ALL_POLICIES, ALL_TREES  # noqa: E402


def registry_rows():
    for p in ALL_POLICIES:
        # Current version: in force from its effective date, no end date.
        yield {
            "policy_id": p["policy_id"],
            "policy_version": p["version"],
            "title": p["title"],
            "payer": p["payer"],
            "lob": p["lob"],
            "effective_date": p["effective_date"],
            "end_date": None,
            "supersedes_version": p["supersedes_version"],
            "source_file": f"{p['policy_id']}.pdf",
        }
        # Superseded version: ended the day the current version took effect.
        # Present so a date-of-service in 2025 resolves to v2.4, which is what
        # makes the effective-dated join demonstrable rather than theoretical.
        if p.get("supersedes_version"):
            yield {
                "policy_id": p["policy_id"],
                "policy_version": p["supersedes_version"],
                "title": p["title"],
                "payer": p["payer"],
                "lob": p["lob"],
                "effective_date": p["supersedes_effective_date"],
                "end_date": p["effective_date"],
                "supersedes_version": None,
                "source_file": None,
            }


def criteria_rows():
    for tree in ALL_TREES:
        for i, n in enumerate(tree["nodes"]):
            yield {
                "policy_id": tree["policy_id"],
                "policy_version": tree["policy_version"],
                "node_id": n["node_id"],
                "parent_id": n.get("parent_id"),
                "node_type": n["node_type"],
                "combinator": n.get("combinator"),
                "section_ref": n["section_ref"],
                "label": n["label"],
                "evidence_type": n.get("evidence_type"),
                "test_expr": n.get("test_expr"),
                "sort_order": i,
                "source": "GROUND_TRUTH",
            }


def write(path, rows):
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    print(f"wrote {path} ({n} rows)")
    return n


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "."
    os.makedirs(outdir, exist_ok=True)
    write(os.path.join(outdir, "policy_registry.ndjson"), registry_rows())
    write(os.path.join(outdir, "policy_criteria.ndjson"), criteria_rows())


if __name__ == "__main__":
    main()
