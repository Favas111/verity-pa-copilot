# Console guide — what to click, what it means

For anyone presenting or recording the Verity console. Every value below was pulled
live from the current database, not written from memory — if the app ever shows
something different, the data changed, not this doc.

---

## The shape of the app, in one paragraph

Open the console and you land on a **patient**. There's a **sidebar** on the left to
pick who you're looking at, and **three tabs** across the top for that one patient:
**Criteria trail** (the decision itself, rule by rule), **Member 360** (their raw
records), and **Policy source** (the actual rulebook text). Nothing on any tab is
computed on the spot — it's all reading back a decision that was already made and
saved, except the sidebar search box, which *does* make a brand new decision live.

---

## The sidebar

**Review queue** — the three prepared patients. Click a name, the whole screen updates.

**Look up any member** — a text box. Type any patient ID from the 5,003 in the
database and click **Run review**; the system builds a brand-new decision for them,
live, in about 40 seconds. Covered in its own section below.

---

## The three tabs, for whichever patient is selected

### Tab 1 — Criteria trail (the important one)

A list of all 21 rules from the policy, indented to show how they group together.
Each rule has a colored tag:

| Tag | Meaning |
|---|---|
| **MET** (green) | This rule is satisfied — proof is attached |
| **NOT MET** (red) | Checked, and it fails |
| **NO EVIDENCE** (amber) | Nothing on file either proves or disproves it |

Rows written in `(structured)` were checked against database records (claims, labs,
prescriptions). Rows written in `(narrative)` were checked by reading typed notes.
Any row with an **"Evidence"** link underneath can be clicked open to show the exact
source sentence.

At the very top, a green **Approved** or amber **Routed to clinical reviewer** banner
gives the bottom line before you scroll through the rules.

### Tab 2 — Member 360

The patient's raw chart: age/plan on the left, an HbA1c chart, a table of every
continuous drug trial the system found (which drug class, how many months, and if it
came from a *different* insurer), recent diagnoses, and a list of their clinical notes.
This is where you'd go to double-check the trail tab isn't making anything up.

### Tab 3 — Policy source

The actual policy text, section by section, exactly as it was read out of the PDF.
Sections referenced by the current decision are marked with a small dot.

---

## Elena Vasquez — `M09000001` — **Approved**

**The story:** two different rules get rescued two different ways.

| Click | What you'll see |
|---|---|
| §4.1 *(structured)* — **MET** | Expand it → *"5.9 months continuous biguanide… source: Northstar Mutual Health"*. Her metformin history exists, just under a **previous insurer's** ID |
| §4.2 *(structured)* rows ×2 — **NO EVIDENCE** | No prescription records for either second-line drug — genuinely nothing there |
| §4.2 *(narrative)* rows ×2 — **MET** | Expand either → an out-of-network specialist's note documenting she can't tolerate either drug class |

**The one sentence to say:** *"Two different rules, rescued two different ways — one by
finding records under her old insurer, one by reading a doctor's note. Neither would
show up in a normal database query."*

---

## Marcus Thorne — `M09000002` — **Routed to clinical reviewer**

**The story:** one missing test, named exactly.

| Click | What you'll see |
|---|---|
| Top banner | *"§3.3 HbA1c ≥ 7.0% within 90 days prior to the request [INSUFFICIENT_EVIDENCE]"* — this is the entire reason |
| §3.3 *(structured)* — **NO EVIDENCE** | His last HbA1c test is 210 days old; the policy needs one from the last 90 |

**The one sentence to say:** *"Everything else about Marcus checks out. He's routed for
exactly one reason, stated in plain language — not 'denied', just 'we need a recent
lab result'."*

---

## Priya Nakamura — `M09000003` — **Routed to clinical reviewer**

**The story:** everything passes, until a dangerous detail turns up in a note.

| Click | What you'll see |
|---|---|
| §5.1 *(narrative)* — **MET** | Expand it → a consult note recording a family history of medullary thyroid carcinoma, a contraindication for this drug |
| Everything above §5 | All green — she otherwise qualifies |

**The one sentence to say:** *"This is the safety catch. She'd have qualified on every
other rule — the system found something buried in a note that changes the outcome."*

---

## The live search — reviewing someone not on the list

Type any of the IDs below into **"Look up any member"** and click **Run review**.
It takes about 40 seconds — say what it's doing while it thinks (reading claims,
checking labs, searching notes, applying all 21 rules).

**Known-good IDs to use on camera** (real patients, confirmed to have diagnosis, lab
and prescription history so the trail isn't empty):

```
M00003612   M00004676   M00004270   M00004349   M00001442   M00004605
```

### What you will see, and why — say this out loud

**Every one of these will come back "Routed to clinical reviewer" — never
"Approved."** That's not random and not a bug: only the three prepared patients have
doctor's notes written for them. Everyone else in the database has real structured
records (claims, labs, prescriptions) but no typed notes at all.

So for a random search, the structured rules (§3.1, §3.2, §3.3, §4.1, §4.2) will show
a genuine mix of MET / NOT MET / NO EVIDENCE depending on that person's real data — and
**every rule that needs a note will read NO EVIDENCE**, including all three exclusion
checks under §5. Since one of the twenty-one rules can't be verified, the honest answer
is "route to a human," not "approve."

**The exact line to say on camera:**

> "Notice the exclusions all say NO EVIDENCE, not 'passed'. This person has no clinical
> notes on file, so the system says *I can't verify this* rather than guessing she's
> safe. That's the system refusing to assume — not a broken screen."

That line is the whole point of showing this at all. Skip it and a wall of amber just
looks like something didn't load.
