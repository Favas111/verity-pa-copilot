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

import re
import uuid

import streamlit as st
from snowflake.snowpark.context import get_active_session

# Every real member id is "M" + 8 digits (see CORE.MEMBER / build_golden.py).
# The search box is the one place free-typed text reaches SQL, and CALL
# statements through Snowpark's params=[...] binding returned a malformed
# result here (DETERMINATION_ID missing from the row) for reasons not worth
# chasing under time pressure — so this build validates against an
# allowlist and interpolates, rather than trusting parameter binding.
MEMBER_ID_RE = re.compile(r"^M[0-9]{8}$")

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

# The one policy this build supports. A live "look up any member" review has
# nothing else to adjudicate against, so this is what gets requested on
# their behalf. Update if a second policy is ever added.
DEFAULT_POLICY_ID = "MHP-PA-0142"
DEFAULT_NDC = "99999-0401-02"
DEFAULT_DRUG = "Semaglutide 0.5 MG/DOSE"


# ---------------------------------------------------------------------
# Per-member data — fetched live and cached BY MEMBER, rather than bulk-
# loaded for the three demo members up front. This is what lets "look up
# any member" work at all: the other ~5,000 members were never bulk-loaded
# into DATA, so a per-member fetch is the only way to see their chart.
# Cached per member_id, so re-viewing someone costs nothing.
# ---------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_member_snapshot(member_id: str) -> dict:
    # member_id only ever reaches here already validated against
    # MEMBER_ID_RE (see run_live_adjudication) or sourced from our own
    # queue dataframe, but escape defensively regardless of provenance.
    mid = member_id.replace("'", "''")

    def q(sql: str):
        return session.sql(sql).to_pandas()

    return {
        "profile": q(f"""
            SELECT m.member_id, m.first_name, m.last_name, m.date_of_birth,
                   m.sex, m.state,
                   FLOOR(DATEDIFF(day, m.date_of_birth, CURRENT_DATE())/365.25) AS age,
                   e.plan_id, e.lob, e.coverage_start
            FROM VERITY.CORE.MEMBER m
            LEFT JOIN VERITY.CORE.ELIGIBILITY e ON e.member_id = m.member_id
            WHERE m.member_id = '{mid}'
            LIMIT 1
        """),
        "links": q(f"""
            SELECT member_id, prior_member_id, prior_carrier,
                   coverage_start, coverage_end
            FROM VERITY.CORE.MEMBER_LINK WHERE member_id = '{mid}'
        """),
        "labs": q(f"""
            SELECT collected_date, value_num
            FROM VERITY.CORE.LAB_RESULT
            WHERE member_id = '{mid}' AND loinc = '4548-4'
            ORDER BY collected_date
        """),
        "trials": q(f"""
            SELECT drug_class, trial_start, trial_end, trial_months, fill_count,
                   ARRAY_TO_STRING(evidence_sources, ', ') AS source
            FROM VERITY.CORE.V_DRUG_TRIAL
            WHERE member_id = '{mid}'
            ORDER BY drug_class, trial_start
        """),
        "dx": q(f"""
            SELECT c.service_date, d.icd10, p.provider_name, p.network_status
            FROM VERITY.CORE.CLAIM c
            JOIN VERITY.CORE.CLAIM_DIAGNOSIS d ON d.claim_id = c.claim_id
            LEFT JOIN VERITY.CORE.PROVIDER p ON p.provider_id = c.provider_id
            WHERE c.member_id = '{mid}'
            ORDER BY c.service_date DESC
            LIMIT 12
        """),
        "notes": q(f"""
            SELECT note_date, note_type, source_system, network_status
            FROM VERITY.DOCS.CLINICAL_NOTE
            WHERE member_id = '{mid}'
            ORDER BY note_date DESC
        """),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_determination(determination_id: str) -> dict:
    """Fetch one determination + its node trail, not from the bulk DATA
    blob. Used for determinations created by a live search — they will
    not appear in the app-startup snapshot DATA was loaded from.

    determination_id is always a UUID this app minted itself via
    ADJUDICATE, never free-typed input, but it is still escaped below —
    cheap insurance."""
    did = determination_id.replace("'", "''")

    det = session.sql(f"""
        SELECT determination_id, pa_id, member_id, outcome, root_verdict,
               blocking_reasons, policy_id, policy_version, decided_at
        FROM VERITY.AUDIT.DETERMINATION WHERE determination_id = '{did}'
    """).to_pandas()
    nodes = session.sql(f"""
        SELECT determination_id, node_id, parent_id, node_type, combinator,
               section_ref, label, evidence_type, verdict, citation,
               evidence, depth, sort_order
        FROM VERITY.AUDIT.DETERMINATION_NODE
        WHERE determination_id = '{did}'
        ORDER BY sort_order
    """).to_pandas()
    return {"det": det, "nodes": nodes}


def run_live_adjudication(raw_member_id: str) -> dict:
    """
    Review a member who is not already in the demo queue.

    If this member already has a determination against the default policy,
    reuse it rather than paying for a fresh 40-second adjudication — a
    reviewer re-checking the same person a minute later should not
    re-trigger retrieval and LLM calls, and would not expect the answer
    to change on an unchanged record.

    Returns {"ok": True, "pa_id": ..., ...} or {"ok": False, "error": ...}.
    Never raises: search-box input is untrusted, and a stack trace on
    screen is a bad first impression for a live demo.

    NOTE on SQL construction: this validates member_id against a strict
    allowlist (MEMBER_ID_RE) and then interpolates, rather than using
    Snowpark's params=[...] binding. Binding a CALL statement's argument
    that way returned a result missing DETERMINATION_ID in this runtime —
    not worth chasing under time pressure, and the allowlist closes the
    injection risk that binding exists to prevent.
    """
    member_id = (raw_member_id or "").strip().upper()
    if not MEMBER_ID_RE.match(member_id):
        return {"ok": False, "error": "Member ids look like M followed by 8 digits."}

    found = session.sql(
        f"SELECT first_name, last_name FROM VERITY.CORE.MEMBER "
        f"WHERE member_id = '{member_id}'"
    ).to_pandas()
    if found.empty:
        return {"ok": False, "error": f"No member with id {member_id}."}
    member_name = f"{found.iloc[0].FIRST_NAME} {found.iloc[0].LAST_NAME}"

    existing = session.sql(f"""
        SELECT d.determination_id, p.pa_id, p.requested_drug
        FROM VERITY.CORE.PA_REQUEST p
        JOIN VERITY.AUDIT.DETERMINATION d ON d.pa_id = p.pa_id
        WHERE p.member_id = '{member_id}' AND p.policy_id = '{DEFAULT_POLICY_ID}'
        ORDER BY d.decided_at DESC LIMIT 1
    """).to_pandas()
    if not existing.empty:
        row = existing.iloc[0]
        return {
            "ok": True, "reused": True, "pa_id": row.PA_ID,
            "member_id": member_id, "member_name": member_name,
            "requested_drug": row.REQUESTED_DRUG,
            "determination_id": row.DETERMINATION_ID,
        }

    pa_id = "PA-LIVE-" + uuid.uuid4().hex[:12].upper()
    session.sql(f"""
        INSERT INTO VERITY.CORE.PA_REQUEST
            (pa_id, member_id, policy_id, requested_ndc, requested_drug,
             request_date, date_of_service, status)
        SELECT '{pa_id}', '{member_id}', '{DEFAULT_POLICY_ID}', '{DEFAULT_NDC}',
               '{DEFAULT_DRUG}', CURRENT_DATE(), CURRENT_DATE(), 'PENDING'
    """).collect()

    # Fire the adjudication, then read the result back from the audit table
    # rather than from the CALL's own return value.
    #
    # ADJUDICATE returns TABLE(outcome, root_verdict, blocking_reasons,
    # determination_id) and that works fine from the CLI, but in this
    # Snowpark runtime the returned frame does not carry DETERMINATION_ID —
    # neither with params=[...] binding nor with plain interpolation. Since
    # we minted pa_id ourselves, AUDIT.DETERMINATION is an authoritative and
    # completely unambiguous place to look the result up, so the procedure's
    # return shape stops mattering.
    session.sql(f"CALL VERITY.POLICY.ADJUDICATE('{pa_id}')").collect()

    written = session.sql(f"""
        SELECT determination_id
        FROM VERITY.AUDIT.DETERMINATION
        WHERE pa_id = '{pa_id}'
        ORDER BY decided_at DESC
        LIMIT 1
    """).to_pandas()
    if written.empty:
        # Adjudication did not persist anything — drop the orphan request so
        # a failed run does not leave a phantom entry in the review queue.
        session.sql(
            f"DELETE FROM VERITY.CORE.PA_REQUEST WHERE pa_id = '{pa_id}'"
        ).collect()
        return {"ok": False,
                "error": "Adjudication ran but wrote no determination."}
    r = written.iloc[0]
    return {
        "ok": True, "reused": False, "pa_id": pa_id,
        "member_id": member_id, "member_name": member_name,
        "requested_drug": DEFAULT_DRUG,
        "determination_id": r.DETERMINATION_ID,
    }


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
# Queue + live lookup
#
# Only three members arrive with a request already sitting in the queue —
# those are the ones with a hand-written clinical story to find. Everyone
# else in the 5,000-member population can still be reviewed: typing their
# id below runs a REAL adjudication against them, live, right now. It is
# the same ADJUDICATE procedure behind both paths; the three queue cases
# just have their result pre-computed so the demo doesn't wait on them.
# =====================================================================
queue = DATA["queue"]

st.sidebar.markdown("### Review queue")
st.sidebar.caption("Prior authorization requests awaiting determination")

labels = {
    r.PA_ID: f"{r.MEMBER_NAME} — {r.REQUESTED_DRUG.split()[0]}"
    for r in queue.itertuples()
}
queue_choice = st.sidebar.radio(
    "Select a request", list(labels), format_func=lambda k: labels[k],
    label_visibility="collapsed", key="queue_choice",
)

st.sidebar.divider()
st.sidebar.markdown("### Look up any member")
st.sidebar.caption(
    f"Runs a fresh review against policy {DEFAULT_POLICY_ID}. "
    "Takes about 40 seconds for a member with no case on file yet."
)
lookup_id = st.sidebar.text_input(
    "Member id", placeholder="e.g. M00001234", label_visibility="collapsed"
)
if st.sidebar.button("Run review", use_container_width=True):
    with st.sidebar:
        with st.spinner("Reading records, searching notes, applying policy…"):
            result = run_live_adjudication(lookup_id)
    if result["ok"]:
        st.session_state["live_result"] = result
        st.session_state["active_source"] = "live"
    else:
        st.sidebar.error(result["error"])

# Picking a queue case switches back out of "live" mode.
if queue_choice != st.session_state.get("last_queue_choice"):
    st.session_state["active_source"] = "queue"
    st.session_state["last_queue_choice"] = queue_choice

active_source = st.session_state.get("active_source", "queue")

if active_source == "live" and "live_result" in st.session_state:
    live = st.session_state["live_result"]
    pa_id = live["pa_id"]
    member_id = live["member_id"]
    member_name = live["member_name"]
    requested_drug = live["requested_drug"]
    determination_id = live["determination_id"]
    if live.get("reused"):
        st.sidebar.caption("Already reviewed earlier this session — showing that result.")
else:
    pa_id = queue_choice
    row = queue[queue.PA_ID == pa_id].iloc[0]
    member_id = row.MEMBER_ID
    member_name = row.MEMBER_NAME
    requested_drug = row.REQUESTED_DRUG
    determination_id = None  # resolved from DATA["det"] below

st.sidebar.divider()
st.sidebar.markdown(
    f'<div class="kv"><b>Request</b><br><span class="cite">{pa_id}</span></div>'
    f'<div class="kv"><b>Member</b><br><span class="cite">{member_id}</span></div>'
    f'<div class="kv"><b>Drug</b><br>{requested_drug}</div>',
    unsafe_allow_html=True,
)
st.sidebar.divider()
st.sidebar.caption(
    "All data synthetic. Meridian Health Plan is fictional. "
    "This system can approve or route to a clinician — it cannot deny."
)

# =====================================================================
# Determination — from the bulk snapshot for a queue case, or fetched
# live (and cached by determination_id) for a searched-up member.
# =====================================================================
if determination_id is not None:
    live_data = fetch_determination(determination_id)
    det, nodes_full = live_data["det"], live_data["nodes"]
else:
    det = DATA["det"][DATA["det"].PA_ID == pa_id]

st.markdown(f"## {member_name}")
st.caption(f"{requested_drug} · policy {DEFAULT_POLICY_ID}")

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

if determination_id is not None:
    nodes = nodes_full  # already scoped to this one determination
else:
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
# Member 360 — fetched live for whichever member is currently active
# (queue case or a live-searched one). Cached per member_id, so this
# costs a real query only the first time each member is opened.
# ---------------------------------------------------------------------
with tab_360:
    snap = fetch_member_snapshot(member_id)
    c1, c2 = st.columns([1, 1.35])

    with c1:
        st.markdown("#### Member")
        if snap["profile"].empty:
            st.caption("No member profile on file.")
        else:
            prof = snap["profile"].iloc[0]
            st.markdown(
                f'<div class="kv"><b>Age</b> {prof.AGE} · {prof.SEX} · {prof.STATE}</div>'
                f'<div class="kv"><b>Plan</b> {prof.PLAN_ID} ({prof.LOB})</div>'
                f'<div class="kv"><b>Covered since</b> {prof.COVERAGE_START}</div>',
                unsafe_allow_html=True,
            )

        # Prior coverage is what makes step therapy discoverable at all —
        # surface it rather than burying it in a join.
        links = snap["links"]
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
        labs = snap["labs"]
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
        trials = snap["trials"]
        if trials.empty:
            st.caption("No pharmacy claims on file.")
        else:
            # Streamlit in Snowflake predates hide_index (added in 1.23), so
            # promote a meaningful column to the index instead of passing it.
            st.dataframe(trials.set_index("DRUG_CLASS"), use_container_width=True)

        st.markdown("#### Recent diagnoses")
        dx = snap["dx"]
        if dx.empty:
            st.caption("No claims on file.")
        else:
            st.dataframe(dx.set_index("SERVICE_DATE"), use_container_width=True)

        st.markdown("#### Clinical notes")
        notes = snap["notes"]
        if notes.empty:
            st.caption(
                "No clinical notes on file — this member has only structured "
                "records, so any narrative criterion below will read NO EVIDENCE "
                "rather than MET."
            )
        else:
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
