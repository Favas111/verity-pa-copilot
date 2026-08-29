# Demo video script — Verity

**Target: 3 minutes.** Two apps only: the **Streamlit console** and the **Cortex Agent**.
Everything else (SQL, repo, deck) is skippable — judges read those separately.

Record in **Incognito**, signed in as any user with access. Full screen, hide bookmarks.

**Before recording:** open the console once and click each of the three members so the
warehouse is warm. A cold start takes ~10 seconds and will look broken on camera.

---

## 0:00 – 0:25 · The problem

*Screen: the policy PDF, `data/policies/MHP-PA-0142.pdf`, scrolled to §4.1*

> "This is a medical policy. It decides whether a patient gets an expensive diabetes drug.
>
> To apply it, a nurse needs the patient's lab results, their prescription history, and
> whatever a doctor typed in a consultation note two years ago. Those live in completely
> different places.
>
> So patients get refused because the evidence was never *found* — not because it didn't
> exist."

---

## 0:25 – 0:45 · What we built

*Screen: the console, landing on Elena Vasquez*

> "Verity reads that policy, turns it into a checklist of twenty-one rules, and checks
> every rule against every source — tables and typed notes together.
>
> Two outcomes only: approve, or hand it to a human doctor. There is no code path in this
> system that denies a patient."

---

## 0:45 – 1:45 · The moment that matters

*Screen: Elena Vasquez, Criteria trail tab. Green "Approved" banner visible.*

> "Elena needs this drug. The policy says she must have tried metformin for three
> consecutive months first."

*Scroll to §4.1. Expand the evidence.*

> "Here's the thing — under her current insurance, she has **zero** metformin
> prescriptions. A normal system stops here and refuses her.
>
> But look what ours found: **5.9 months of continuous metformin**, sourced from Northstar
> Mutual Health — her *previous* insurer."

*Point at the citation line.*

> "And that's not a trick. Section 2.3 of the policy explicitly says therapy under prior
> coverage counts. The rule was always there. Conventional tools just never look."

*Scroll to §4.2. Show the two red "NO EVIDENCE" rows, then the green group below.*

> "Same story here. No prescription records for either second-line drug — both structured
> checks fail. But a consultation note from an out-of-network specialist documents that
> she can't tolerate either one. The system reads it, and the criterion passes."

*Expand that evidence to show the empagliflozin sentence.*

> "Every green tick has a receipt."

---

## 1:45 – 2:15 · It doesn't just say yes

*Click Marcus Thorne.*

> "Marcus gets routed to a doctor — and the system says exactly why: his most recent
> HbA1c is 210 days old, and the policy needs one within ninety. Not 'denied.' Just
> 'here's the one thing missing.'"

*Click Priya Nakamura. Expand §5.1.*

> "Priya passes every single criterion. But buried in a consultation note is a family
> history of medullary thyroid carcinoma — a contraindication for this drug class. The
> system catches it and stops.
>
> This is the safety case. It found something that would have been missed."

---

## 2:05 – 2:25 · It runs on anyone, not just the three (optional)

*Sidebar → "Look up any member" → type `M00003612` → Run review*

> "Those three cases are pre-loaded so we don't wait on camera. But this runs against the
> whole population — five thousand members. Let me review someone at random."

*Wait for the spinner. ~40 seconds — talk over it.*

> "It's reading her claims, pulling her lab history, searching her notes, and applying all
> twenty-one criteria right now."

*Result appears: Ashley Dawson, routed to clinician.*

> "Routed for review. And look at the exclusions — they say NO EVIDENCE, not 'passed'.
> This member has no clinical notes on file, so the system says *I can't verify this*
> rather than assuming she's clear. That distinction matters when the thing you can't
> verify is a contraindication."

**Do not skip that last line.** A screen full of "NO EVIDENCE" looks like a broken app
unless you explain that it is the system refusing to guess.

---

## 2:25 – 2:45 · The guardrail, proven live

*Screen: Snowsight → AI & ML → Agents → VERITY_AGENT → Preview tab*

> "We also built a conversational agent over the same data. Watch what happens when I ask
> it to make the call itself."

*Type: `Should member M09000003 be approved?`*

> "It refuses. It reports what the recorded determination says and why — it will not
> improvise a coverage decision. That's not a prompt asking it nicely. Approvals are
> computed by deterministic SQL; the model never gets a vote."

*Optional if time: ask `What does the policy require for metformin step therapy?` and show
it answering with a section citation.*

---

## 2:45 – 3:00 · Close

*Screen: back to Elena's approved determination*

> "Forty-three seconds per decision. Every determination fully cited — three hundred and
> fifteen audit records, each traceable to its source. Two hundred forty-five thousand rows
> of synthetic data. Seven dollars of Snowflake credit to build the whole thing.
>
> All synthetic data. The insurer is fictional. Nothing here touches real patients."

---

## If something breaks on camera

- **Console slow to load** — the warehouse suspended. Wait, don't reload; reloading
  re-queries and looks worse.
- **Agent returns nothing** — use the Snowsight Preview tab, not the CLI. The CLI returns
  empty responses regardless of cause.
- **Evidence panel empty** — you clicked a criterion with no evidence (a group node
  rather than a leaf). Pick one with an "evidence" expander under it.

## What NOT to say

- Don't claim a specific industry turnaround time ("normally takes 14 days") — we have no
  sourced figure for that, and a healthcare judge may know better. Stick to what we
  measured: 43 seconds, 100% cited, $7.
- Don't call the data realistic beyond "synthetic and clinically plausible."
- Don't say the system "denies" anything. It approves or routes.
