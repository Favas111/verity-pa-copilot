"""
Verity — Prior Authorization Evidence Console

Streamlit in Snowflake. Nothing leaves the Snowflake perimeter: no PHI is
exported, no external API is called, and the reviewer's session inherits
Snowflake's own RBAC.

This is a REVIEWER'S WORKING SURFACE, not a dashboard. The question a
utilization-management nurse actually has is "can I act on this, and what
is it based on?" — so the outcome and the single actionable reason lead,
and the full criteria trail sits underneath with its evidence attached.

Every verdict shown here is read back from AUDIT.DETERMINATION_NODE. The
app renders a determination; it never computes one.
"""

import streamlit as st
from snowflake.snowpark.context import get_active_session

st.set_page_config(page_title="Verity — PA Evidence Console", layout="wide")
session = get_active_session()

# ---------------------------------------------------------------------
# Palette — semantic states are deliberately distinct from the accent, so
# "needs attention" never reads as "branded".
# ---------------------------------------------------------------------
MET = "#1B6E45"
GAP = "#8A5A06"
STOP = "#9C3129"
ACCENT = "#0B6E78"

VERDICT_STYLE = {
    "MET": (MET, "#E2F0E8", "MET"),
    "NOT_MET": (STOP, "#F8E7E5", "NOT MET"),
    "INSUFFICIENT_EVIDENCE": (GAP, "#F7EDDA", "NO EVIDENCE"),
}

st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; max-width: 1500px;}
      .vchip {display:inline-block; padding:2px 9px; border-radius:20px;
              font-size:11px; font-weight:700; font-family:ui-monospace,Menlo,monospace;
              white-space:nowrap;}
      .node {font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:13px;}
      .grp  {font-weight:700;}
      .cite {font-family:ui-monospace,Menlo,monospace; font-size:11px; opacity:.75;}
      .banner {border-radius:10px; padding:18px 22px; margin-bottom:6px;}
      .banner h2 {margin:0; font-size:26px; letter-spacing:-.02em;}
      .banner p  {margin:6px 0 0; font-size:14px;}
      .kv {font-size:13px; padding:5px 0; border-bottom:1px solid rgba(128,128,128,.18);}
      .kv b {font-weight:650;}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------
# Data access
#
# Streamlit in Snowflake caps the number of queries an app INSTANCE may
# issue over its lifetime ("Exceeded maximum number of inbound queries
# allowed for this instance"). A query-per-panel design blows through it,
# because every widget interaction reruns the whole script.
#
# So: fetch the entire working set ONCE, cached for an hour, and do all
# per-member filtering in pandas. The dataset is small and static during
# a review session, so there is nothing to gain from re-querying.
# ---------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner="Loading determinations…")
def load_all() -> dict:
    def q(sql: str):
        return session.sql(sql).to_pandas()

    # Latest determination per request.
    det = q("""
        SELECT determination_id, pa_id, member_id, outcome, root_verdict,
               blocking_reasons, policy_id, policy_version, decided_at
        FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY pa_id
                                           ORDER BY decided_at DESC) AS rn
              FROM VERITY.AUDIT.DETERMINATION)
        WHERE rn = 1
    """)

    return {
        "queue": q("""
            SELECT p.pa_id, p.member_id,
                   m.first_name || ' ' || m.last_name AS member_name,
                   p.requested_drug, p.date_of_service, p.policy_id
            FROM VERITY.CORE.PA_REQUEST p
            JOIN VERITY.CORE.MEMBER m ON m.member_id = p.member_id
            ORDER BY p.request_date DESC
        """),
        "det": det,
        "nodes": q("""
            SELECT n.determination_id, n.node_id, n.parent_id, n.node_type,
                   n.combinator, n.section_ref, n.label, n.evidence_type,
                   n.verdict, n.citation, n.evidence, n.depth, n.sort_order
            FROM VERITY.AUDIT.DETERMINATION_NODE n
            JOIN (SELECT determination_id FROM (
                    SELECT determination_id, ROW_NUMBER() OVER (
                        PARTITION BY pa_id ORDER BY decided_at DESC) AS rn
                    FROM VERITY.AUDIT.DETERMINATION) WHERE rn = 1) l
              ON l.determination_id = n.determination_id
            ORDER BY n.sort_order
        """),
        "member": q("""
            SELECT m.member_id, m.date_of_birth, m.sex, m.state,
                   FLOOR(DATEDIFF(day, m.date_of_birth, CURRENT_DATE())/365.25) AS age,
                   e.plan_id, e.lob, e.coverage_start
            FROM VERITY.CORE.MEMBER m
            LEFT JOIN VERITY.CORE.ELIGIBILITY e ON e.member_id = m.member_id
            WHERE m.is_golden
        """),
        "links": q("""
            SELECT member_id, prior_member_id, prior_carrier,
                   coverage_start, coverage_end
            FROM VERITY.CORE.MEMBER_LINK
        """),
        "labs": q("""
            SELECT l.member_id, l.collected_date, l.value_num
            FROM VERITY.CORE.LAB_RESULT l
            JOIN VERITY.CORE.MEMBER m ON m.member_id = l.member_id AND m.is_golden
            WHERE l.loinc = '4548-4'
            ORDER BY l.collected_date
        """),
        "trials": q("""
            SELECT t.member_id, t.drug_class, t.trial_start, t.trial_end,
                   t.trial_months, t.fill_count,
                   ARRAY_TO_STRING(t.evidence_sources, ', ') AS source
            FROM VERITY.CORE.V_DRUG_TRIAL t
            JOIN VERITY.CORE.MEMBER m ON m.member_id = t.member_id AND m.is_golden
            ORDER BY t.drug_class, t.trial_start
        """),
        "dx": q("""
            SELECT c.member_id, c.service_date, d.icd10,
                   p.provider_name, p.network_status
            FROM VERITY.CORE.CLAIM c
            JOIN VERITY.CORE.MEMBER m ON m.member_id = c.member_id AND m.is_golden
            JOIN VERITY.CORE.CLAIM_DIAGNOSIS d ON d.claim_id = c.claim_id
            LEFT JOIN VERITY.CORE.PROVIDER p ON p.provider_id = c.provider_id
            ORDER BY c.service_date DESC
        """),
        "notes": q("""
            SELECT n.member_id, n.note_date, n.note_type,
                   n.source_system, n.network_status
            FROM VERITY.DOCS.CLINICAL_NOTE n
            JOIN VERITY.CORE.MEMBER m ON m.member_id = n.member_id AND m.is_golden
            ORDER BY n.note_date DESC
        """),
        # Sort numerically by major then minor part. Zero-padding the whole
        # string sorts '0002.1' after '000008', which put every subsection
        # below every top-level section (§2.1 appearing after §8).
        "chunks": q("""
            SELECT policy_id, section_ref, section_heading, chunk_text
            FROM VERITY.DOCS.POLICY_CHUNK
            ORDER BY SPLIT_PART(section_ref, '.', 1)::INT,
                     COALESCE(NULLIF(SPLIT_PART(section_ref, '.', 2), ''), '0')::INT
        """),
    }


DATA = load_all()


def chip(verdict: str) -> str:
    fg, bg, label = VERDICT_STYLE.get(verdict, ("#666", "#EEE", verdict or "—"))
    return f'<span class="vchip" style="color:{fg};background:{bg}">{label}</span>'


def as_int(v, default: int = 0) -> int:
    """
    Snowflake NUMBER columns arrive as decimal.Decimal, and Decimal does not
    support the sequence-repeat protocol: "x" * Decimal(3) raises
    "TypeError: bad argument type for built-in operation". Anything used for
    indentation, slicing, or repetition has to be a real int first.
    """
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


# =====================================================================
# Queue
# =====================================================================
queue = DATA["queue"]

st.sidebar.markdown("### Review queue")
st.sidebar.caption("Prior authorization requests awaiting determination")

labels = {
    r.PA_ID: f"{r.MEMBER_NAME} — {r.REQUESTED_DRUG.split()[0]}"
    for r in queue.itertuples()
}
pa_id = st.sidebar.radio(
    "Select a request", list(labels), format_func=lambda k: labels[k], label_visibility="collapsed"
)
row = queue[queue.PA_ID == pa_id].iloc[0]

st.sidebar.divider()
st.sidebar.markdown(
    f'<div class="kv"><b>Request</b><br><span class="cite">{pa_id}</span></div>'
    f'<div class="kv"><b>Member</b><br><span class="cite">{row.MEMBER_ID}</span></div>'
    f'<div class="kv"><b>Drug</b><br>{row.REQUESTED_DRUG}</div>'
    f'<div class="kv"><b>Date of service</b><br>{row.DATE_OF_SERVICE}</div>',
    unsafe_allow_html=True,
)
st.sidebar.divider()
st.sidebar.caption(
    "All data synthetic. Meridian Health Plan is fictional. "
    "This system can approve or route to a clinician — it cannot deny."
)

# =====================================================================
# Determination
# =====================================================================
det = DATA["det"][DATA["det"].PA_ID == pa_id]

st.markdown(f"## {row.MEMBER_NAME}")
st.caption(f"{row.REQUESTED_DRUG} · policy {row.POLICY_ID}")

if det.empty:
    st.warning("No determination on file for this request yet.")
    st.stop()

d = det.iloc[0]
approved = d.OUTCOME == "APPROVE"
fg, bg = (MET, "#E2F0E8") if approved else (GAP, "#F7EDDA")
headline = "Approved" if approved else "Routed to clinical reviewer"
sub = (
    "All policy criteria are satisfied with cited evidence."
    if approved
    else (d.BLOCKING_REASONS or "Requires clinical review.")
)

st.markdown(
    f'<div class="banner" style="background:{bg};border:1px solid {fg}33">'
    f'<h2 style="color:{fg}">{headline}</h2>'
    f'<p style="color:{fg}">{sub}</p></div>',
    unsafe_allow_html=True,
)
st.caption(
    f"Determination {str(d.DETERMINATION_ID)[:8]} · policy version {d.POLICY_VERSION} "
    f"in force on the date of service · decided {str(d.DECIDED_AT)[:16]}"
)

nodes = DATA["nodes"][DATA["nodes"].DETERMINATION_ID == d.DETERMINATION_ID]

tab_trail, tab_360, tab_policy = st.tabs(
    ["Criteria trail", "Member 360", "Policy source"]
)

# ---------------------------------------------------------------------
# Criteria trail — the heart of the console
# ---------------------------------------------------------------------
with tab_trail:
    st.caption(
        "Each criterion resolves independently against its own evidence. "
        "The determination is a deterministic rollup of these leaves — "
        "no model renders the verdict."
    )
    for n in nodes.itertuples():
        indent = "&nbsp;" * (as_int(n.DEPTH) * 6)
        if n.NODE_TYPE == "GROUP":
            st.markdown(
                f'<div class="node grp" style="padding:7px 0">{indent}'
                f'<span style="color:{ACCENT}">[{n.COMBINATOR}]</span> '
                f'§{n.SECTION_REF} {n.LABEL} &nbsp; {chip(n.VERDICT)}</div>',
                unsafe_allow_html=True,
            )
            continue

        src = "structured" if n.EVIDENCE_TYPE == "STRUCTURED" else "narrative"
        st.markdown(
            f'<div class="node" style="padding:5px 0">{indent}'
            f'<span style="opacity:.55">({src})</span> '
            f"§{n.SECTION_REF} {n.LABEL} &nbsp; {chip(n.VERDICT)}</div>",
            unsafe_allow_html=True,
        )
        if n.EVIDENCE:
            with st.expander(f"Evidence — §{n.SECTION_REF}", expanded=False):
                if n.CITATION:
                    st.markdown(f'<span class="cite">Source: {n.CITATION}</span>',
                                unsafe_allow_html=True)
                st.code(n.EVIDENCE, language=None)

# ---------------------------------------------------------------------
# Member 360
# ---------------------------------------------------------------------
with tab_360:
    c1, c2 = st.columns([1, 1.35])

    with c1:
        st.markdown("#### Member")
        prof = DATA["member"][DATA["member"].MEMBER_ID == row.MEMBER_ID].iloc[0]
        st.markdown(
            f'<div class="kv"><b>Age</b> {prof.AGE} · {prof.SEX} · {prof.STATE}</div>'
            f'<div class="kv"><b>Plan</b> {prof.PLAN_ID} ({prof.LOB})</div>'
            f'<div class="kv"><b>Covered since</b> {prof.COVERAGE_START}</div>',
            unsafe_allow_html=True,
        )

        # Prior coverage is what makes step therapy discoverable at all —
        # surface it rather than burying it in a join.
        links = DATA["links"][DATA["links"].MEMBER_ID == row.MEMBER_ID]
        if not links.empty:
            st.markdown("#### Prior coverage")
            st.caption(
                "Policy §2.3 — therapy completed under prior coverage counts "
                "toward step therapy."
            )
            for l in links.itertuples():
                st.markdown(
                    f'<div class="kv"><b>{l.PRIOR_CARRIER}</b><br>'
                    f'<span class="cite">{l.PRIOR_MEMBER_ID} · '
                    f"{l.COVERAGE_START} to {l.COVERAGE_END}</span></div>",
                    unsafe_allow_html=True,
                )

        st.markdown("#### HbA1c")
        labs = DATA["labs"][DATA["labs"].MEMBER_ID == row.MEMBER_ID]
        if labs.empty:
            st.caption("No HbA1c results on file.")
        else:
            # Decimal values do not plot; coerce to float first.
            # .copy() avoids mutating the cached frame — Streamlit hands back
            # the cached object itself, so writing to it corrupts later reads.
            labs = labs.copy()
            labs["VALUE_NUM"] = labs["VALUE_NUM"].astype(float)
            st.line_chart(labs.set_index("COLLECTED_DATE")["VALUE_NUM"], height=170)

    with c2:
        st.markdown("#### Therapy history")
        st.caption("Continuous runs derived by fill-to-fill gap analysis, across all "
                   "member identities.")
        trials = DATA["trials"][DATA["trials"].MEMBER_ID == row.MEMBER_ID].drop(
            columns=["MEMBER_ID"])
        if trials.empty:
            st.caption("No pharmacy claims on file.")
        else:
            # Streamlit in Snowflake predates hide_index (added in 1.23), so
            # promote a meaningful column to the index instead of passing it.
            st.dataframe(trials.set_index("DRUG_CLASS"), use_container_width=True)

        st.markdown("#### Recent diagnoses")
        dx = DATA["dx"][DATA["dx"].MEMBER_ID == row.MEMBER_ID].drop(
            columns=["MEMBER_ID"]).head(12)
        st.dataframe(dx.set_index("SERVICE_DATE"), use_container_width=True)

        st.markdown("#### Clinical notes")
        notes = DATA["notes"][DATA["notes"].MEMBER_ID == row.MEMBER_ID].drop(
            columns=["MEMBER_ID"])
        st.dataframe(notes.set_index("NOTE_DATE"), use_container_width=True)

# ---------------------------------------------------------------------
# Policy source
# ---------------------------------------------------------------------
with tab_policy:
    st.caption(
        f"{d.POLICY_ID} version {d.POLICY_VERSION} — the version in force on this "
        "request's date of service, not necessarily the current one."
    )
    cited = set(nodes[nodes.VERDICT.notna()].SECTION_REF.dropna())
    chunks = DATA["chunks"][DATA["chunks"].POLICY_ID == d.POLICY_ID]
    for c in chunks.itertuples():
        mark = " ·" if c.SECTION_REF in cited else ""
        with st.expander(f"§{c.SECTION_REF} {c.SECTION_HEADING}{mark}"):
            st.text(c.CHUNK_TEXT)
