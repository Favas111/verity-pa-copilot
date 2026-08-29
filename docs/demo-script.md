# Demo video script — Verity

**Target: 3 minutes.** Two apps: the **Streamlit console** and the **Cortex Agent**.
Skip the SQL, the repo and the deck — judges read those separately, and screen-recording
code is dead air.

Record in **Incognito**, full screen, bookmarks hidden.

---

## Before you press record

1. Open the console and **click all three patients**, then **run one search** with
   `M00003612`. This wakes the warehouse. A cold start takes ~10 seconds and looks broken.
2. Open the agent in a second tab so you are not navigating menus on camera.
3. Decide now whether you are doing the **3-minute version** (with the live search) or the
   **safe 2½-minute version** (without). Both are marked below.

> **Record the safe version first and save it.** Then re-record with the search if you have
> time. Do not risk your only take on a live 40-second wait.

---

## 0:00 – 0:25 · The problem

*Screen: `data/policies/MHP-PA-0142.pdf`, scrolled to §4.1*

> "This is a medical policy. It decides whether a patient gets an expensive diabetes drug.
>
> To apply it, a nurse needs the patient's lab results, their prescription history, and
> whatever a doctor typed into a consultation note two years ago. Those live in completely
> different systems.
>
> So patients get refused because the evidence was never *found* — not because it didn't
> exist."

---

## 0:25 – 0:45 · What we built

*Screen: the console, landing on Elena Vasquez*

> "Verity reads that policy, turns it into twenty-one checkable rules, and tests every rule
> against every source — database records and typed notes together.
>
> Two outcomes only: approve, or hand it to a human clinician. There is no code path in
> this system that denies a patient."

---

## 0:45 – 1:40 · The moment that matters

*Elena Vasquez, Criteria trail tab, green "Approved" banner*

> "Elena needs this drug. The policy says she must have tried metformin for three
> consecutive months first."

*Scroll to §4.1. Expand the evidence.*

> "Under her current insurance she has **zero** metformin prescriptions. A conventional
> system stops here and refuses her.
>
> Ours found **5.9 months of continuous metformin** — sourced from Northstar Mutual Health,
> her *previous* insurer."

*Point at the citation.*

> "That's not a trick. Section 2.3 of the policy says therapy under prior coverage counts.
> The rule was always there. Conventional tools just never look."

*Scroll to §4.2. Show the two amber NO EVIDENCE rows, then the green group below them.*

> "Same pattern here. No prescription records for either second-line drug — both structured
> checks fail. But a consultation note from an out-of-network specialist documents that she
> can't tolerate either one. The system reads it, and the criterion passes."

*Expand that evidence to show the empagliflozin sentence.*

> "Every green tick has a receipt."

---

## 1:40 – 2:05 · It doesn't just say yes

*Click Marcus Thorne.*

> "Marcus routes to a clinician — and the system says exactly why: his most recent HbA1c is
> 210 days old, and the policy needs one within ninety. Not 'denied.' Just: here's the one
> thing missing."

*Click Priya Nakamura. Expand §5.1.*

> "Priya passes every single criterion. But buried in a consultation note is a family
> history of medullary thyroid carcinoma — a contraindication for this drug class. The
> system catches it and stops.
>
> That's the safety case. It found something that would have been missed."

---

## 2:05 – 2:30 · It runs on anyone *(skip for the safe version)*

*Sidebar → "Look up any member" → type `M00003612` → Run review*

> "Those three are pre-computed so we don't wait on camera. But this runs against the whole
> population — five thousand members. Let me review someone at random."

*Talk over the ~40-second spinner.*

> "It's reading her claims, pulling her lab history, searching her notes, and applying all
> twenty-one criteria — right now."

*Result: Ashley Dawson, routed to clinician.*

> "Routed for review. And look at the exclusions — they say **NO EVIDENCE**, not 'passed'.
> This member has no clinical notes on file, so the system says *I cannot verify this*
> rather than assuming she's clear.
>
> That distinction matters when the thing you can't verify is a contraindication."

**Do not skip that last line.** A screen full of amber looks like a broken app unless you
explain that it is the system refusing to guess.

---

## 2:30 – 2:50 · The guardrail, proven live

*Second tab: Snowsight → AI & ML → Agents → VERITY_AGENT → Preview*

> "We also built a conversational agent over the same data. Watch what happens when I ask
> it to make the call itself."

*Type: `Should member M09000003 be approved?`*

> "It refuses. It reports what the recorded determination says, and won't improvise a
> coverage decision. That isn't a prompt asking it nicely — approvals are computed by
> deterministic SQL. The model never gets a vote."

---

## 2:50 – 3:00 · Close

*Back to Elena's approved determination*

> "Forty-three seconds per decision. Every determination fully cited — three hundred and
> fifteen audit records, each traceable to its source. Two hundred forty-five thousand rows
> of synthetic data. Seven dollars of Snowflake credit to build all of it.
>
> All synthetic. The insurer is fictional. Nothing here touches real patients."

---

## If something breaks on camera

| Symptom | What to do |
|---|---|
| Console slow to load | Warehouse suspended. **Wait** — do not reload, that re-queries and looks worse |
| Search returns an error | Member ids are `M` + 8 digits. `M00003612` is known-good |
| Agent returns nothing | Use the Snowsight **Preview** tab, not the CLI — the CLI returns empty regardless of cause |
| Evidence panel empty | You clicked a group row, not a leaf. Pick one with an "evidence" expander |

## What NOT to say

- **Don't invent an industry comparison** ("this normally takes 14 days"). We have no
  sourced figure for that. Stick to what we measured: 43 seconds, 100% cited, $7.
- **Don't call the data realistic** beyond "synthetic and clinically plausible."
- **Don't say the system denies anything.** It approves, or it routes.

## After recording — reset the queue

A live search leaves a real request in the database. Before the next take or a screenshot,
clear it so the sidebar shows only the three demo cases:

```sql
DELETE FROM VERITY.AUDIT.DETERMINATION_NODE WHERE determination_id IN
  (SELECT determination_id FROM VERITY.AUDIT.DETERMINATION WHERE pa_id LIKE 'PA-LIVE-%');
DELETE FROM VERITY.AUDIT.DETERMINATION WHERE pa_id LIKE 'PA-LIVE-%';
DELETE FROM VERITY.CORE.PA_REQUEST WHERE pa_id LIKE 'PA-LIVE-%';
```
