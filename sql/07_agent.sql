-- =====================================================================
-- VERITY — 07_agent.sql
-- Cortex Agent: one natural-language surface over three governed tools.
--
-- Run with: python3 scripts/run_sql.py sql/07_agent.sql
--
-- ---------------------------------------------------------------------
-- The line this agent must not cross
-- ---------------------------------------------------------------------
-- The agent ANSWERS QUESTIONS. It does not decide prior authorizations.
--
-- A determination is produced by POLICY.ADJUDICATE — a deterministic
-- rollup of the Criteria Ledger — because a coverage decision has to be
-- reproducible, individually cited, and incapable of denying care. An
-- agent that could improvise a verdict would destroy all three
-- properties.
--
-- So the orchestration instructions below are explicit: for "should this
-- be approved" questions, the agent reports what the recorded
-- determination says and why, or states that none exists. It never
-- reasons its way to a coverage conclusion.
--
-- Tools:
--   member_360      Cortex Analyst over the semantic view  (structured)
--   policy_lookup   Cortex Search over policy sections     (rules)
--   clinical_lookup Cortex Search over clinical notes      (narrative)
-- =====================================================================

USE DATABASE VERITY;
USE SCHEMA AGENT;

CREATE OR REPLACE AGENT VERITY_AGENT
WITH PROFILE = '{"display_name": "Verity — Utilization Management Assistant"}'
COMMENT = 'Natural-language access to the Member 360, medical policy text, and clinical notes. Answers questions; never renders coverage determinations.'
FROM SPECIFICATION
$$
{
  "models": { "orchestration": "claude-sonnet-4-5" },

  "instructions": {
    "response": "You support utilization-management staff at a health plan. Be concise and factual. Always name your source: a policy section reference such as section 4.1, a member id, or a note type and date. Never state a coverage conclusion of your own — approvals and referrals are computed by the Criteria Ledger, not by you. All data is synthetic and the payer is fictional; say so if asked whether this is real patient data.",

    "orchestration": "Choose tools by the kind of question.\n\n1. Counts, totals, averages, cohort filters, anything about the member population or claims and labs -> member_360.\n2. What the policy requires, criteria wording, exclusions, definitions -> policy_lookup. Quote the section reference.\n3. What a specific member's chart says — intolerances, family history, narrative detail -> clinical_lookup. Always scope by member id.\n\nQuestions of the form 'should this be approved' or 'does this member qualify' are NOT yours to answer. Report what the recorded determination in AUDIT.DETERMINATION says, together with the blocking reason, or say that no determination has been run. Do not evaluate criteria yourself and do not predict an outcome.\n\nWhen a question spans structured and narrative evidence, use both tools and keep the two kinds of evidence clearly labelled.",

    "sample_questions": [
      { "question": "How many members have an average HbA1c above 9?" },
      { "question": "What does the policy require for metformin step therapy?" },
      { "question": "Which second-line drug classes are most prescribed?" },
      { "question": "Does member M09000001 have any documented drug intolerance?" },
      { "question": "How many prior authorization requests are pending?" }
    ]
  },

  "tools": [
    { "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "member_360",
        "description": "Query the Member 360: members, coverage, claims, diagnoses, pharmacy fills, labs, providers and prior authorization requests. Use for counts, averages, trends and cohort questions."
    }},
    { "tool_spec": {
        "type": "cortex_search",
        "name": "policy_lookup",
        "description": "Search medical policy MHP-PA-0142 by section. Use for what the plan requires, coverage criteria, step therapy rules, exclusions and definitions. Returns the section reference to cite."
    }},
    { "tool_spec": {
        "type": "cortex_search",
        "name": "clinical_lookup",
        "description": "Search synthetic clinical notes. Use for narrative detail about a specific member such as documented intolerances, family history or prior therapy. Always filter by member_id."
    }}
  ],

  "tool_resources": {
    "member_360": {
      "semantic_view": "VERITY.SEMANTIC.MEMBER_360",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "COMPUTE_WH"
      }
    },
    "policy_lookup": {
      "name": "VERITY.DOCS.POLICY_SEARCH",
      "id_column": "SECTION_REF",
      "title_column": "CITATION",
      "max_results": 4
    },
    "clinical_lookup": {
      "name": "VERITY.DOCS.CLINICAL_SEARCH",
      "id_column": "NOTE_ID",
      "title_column": "CITATION",
      "max_results": 4
    }
  }
}
$$;

SHOW AGENTS IN SCHEMA VERITY.AGENT;
