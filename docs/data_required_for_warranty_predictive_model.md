# Data Required for a Clustered Warranty Predictive Model

Explanation, requirements, and data audit for replacing "one predictive
model per issue" with "one model per cluster of related issues," which
also classifies predicted issues and ranks them by financial impact for
the Mahindra Warranty & Quality use case.

This document is a plan/requirements reference only — nothing described
here has been implemented. The data-audit sections below were checked
directly against the live `mahindra_ai` database before writing this, so
the "already exists" claims are real, not assumed.

---

## 1. The core idea, in plain English

The pattern used elsewhere in this project (Predictive Early-Warning
Service) is: one model per issue — a separate classifier for "battery
overheating," a separate one for "low voltage," and so on. That works when
there are a handful of well-understood issues with plenty of examples
each. It breaks down badly for Warranty & Quality's real data: the
`warranty_claims` table already has **26 distinct issue categories**, and
most of them have only **1-3 historical claims each**. A model cannot be
trained reliably on 1 example. Building 26+ separate models, most trained
on almost nothing, isn't just expensive to maintain — it's statistically
meaningless for the rare ones.

The fix: instead of "one model per issue," build **one model per cluster
of related issues**, where the model doesn't just answer yes/no for a
single thing — it looks at a vehicle and estimates the probability of
*each issue within that cluster* happening to it. A rare issue borrows
statistical strength from its more common siblings in the same cluster,
because they share a lot of the same underlying causes (same component
family, same supplier, same production-line effects). This is standard
practice in reliability engineering — multi-class classification instead
of a pile of independent binary classifiers.

**The natural clustering key already exists in the data.**
`warranty_claims.supplier_component_category` already groups the 26 issue
categories into 19 sensible clusters — BATTERY, BRAKING_SYSTEM, STEERING,
SUSPENSION, ECU_ELECTRONICS, HVAC, TYRES, and so on. No taxonomy needs to
be invented from scratch; the existing one needs to be adopted and
validated as the modeling boundary.

---

## 2. How it would work for Mahindra Warranty & Quality

1. **Group issues into clusters** using `supplier_component_category` (or
   a refined version of it) — e.g. all steering-related issue codes become
   one "Steering" cluster, all electrical ones become another.
2. **One shared classifier per cluster**, trained on vehicles'
   manufacturing lineage (plant/line/machine/supplier-lot — already in the
   data) plus telematics history plus service history. Output: for each
   vehicle, a probability for *every issue code in that cluster*, not just
   one yes/no.
3. **Attach a financial-impact number** to every predicted issue (§4).
4. **Gate through warranty eligibility** — is this vehicle actually still
   covered, and is this specific part/failure type covered at all (§6).
5. **Rank everything that survives the gate** by expected cost to
   Mahindra, across the whole fleet (§5), producing one unified priority
   list instead of 26 separate, incomparable model outputs.

---

## 3. Data and components required

### Already exists (confirmed directly against the live database)

- **`warranty_claims`** (55 rows total) — `issue_category`, `failure_code`,
  `severity` (HIGH/MEDIUM/LOW), `diagnosis`, `claim_amount_inr`,
  `approved_amount_inr`, `claim_status` (APPROVED/REJECTED/MANUAL_REVIEW),
  `root_cause_domain` (COMPONENT_FAILURE/MULTIPLE_FACTORS/
  SERVICE_DIAGNOSIS/SUPPLIER_QUALITY), full production lineage
  (plant/line/machine/supplier lot), vehicle age/odometer at claim time.
- **`service_events`** (1,116 rows) — much larger than warranty_claims,
  includes non-warranty visits, `complaint_reported`, `repair_required`,
  `warranty_candidate` flags — a good source of *near-miss* signals even
  when no formal claim was filed.
- **`supplier_component_category`** (19 distinct values) — the de facto
  cluster/part taxonomy: ADHESIVES, BATTERY, BRAKING_SYSTEM,
  DRIVETRAIN_COMPONENTS, ECU_ELECTRONICS, ELECTRICAL_WIRING, EXHAUST,
  FASTENERS, FLUIDS, GLASS, HVAC, LIGHTING, PLASTIC_TRIM, RUBBER_SEALS,
  SEATING, STEEL_BODY_PANELS, STEERING, SUSPENSION, TYRES.
- **`issue_category`** (26 distinct values) — e.g. BATTERY_WARNING,
  BODY_ALIGNMENT, BONDING_DEFECT, BRAKE_NOISE, ELECTRICAL_WARNING,
  ELECTRONIC_CONTROL, EXHAUST_NOISE, EXHAUST_WARNING, FASTENER_LOOSENESS,
  FLUID_LEVEL, GLASS_ALIGNMENT, HVAC_NOISE, INTERIOR_RATTLE,
  INTERMITTENT_ELECTRICAL, LIGHTING_FAULT, LIGHT_ALIGNMENT,
  POWER_DELIVERY, RATTLE_NOISE, RIDE_QUALITY, SEAT_NOISE, STEERING_FEEL,
  STEERING_NOISE, TRIM_SEPARATION, TYRE_VIBRATION, TYRE_WEAR,
  WATER_SEALING.
- Manufacturing and telematics tables — leading-indicator features,
  already wired into the causal pipeline elsewhere in this project.

### Missing — would need to be built

- **A reusable cost-per-part-issue reference table.** Cost currently only
  exists as an *outcome* of a claim that already happened
  (`claim_amount_inr`). To estimate the cost of an issue *before* it's
  claimed, a forward-looking reference is needed: typical labor hours ×
  labor rate + parts cost per issue category, ideally with a realistic
  range rather than one number — the existing 55 rows already show huge
  cost variance by category (see §4 for real numbers).
- **A warranty policy reference table** — does not exist yet (§6).
- **A fleet population count** — how many currently-in-service vehicles
  exist per model/batch/region, to scale a per-vehicle probability into a
  fleet-wide rupee figure. Likely derivable from existing
  delivery/vehicle records, but needs to be joined in explicitly for this
  purpose.
- **More historical claims data.** 55 total claims, several categories
  with a single example, is thin for training anything trustworthy. This
  needs either substantially more synthetic claims, or leaning on the
  much larger `service_events` table as a supplementary weak-label source
  (e.g. `repair_required` + `complaint_reported` events that never became
  formal claims) to pad out the training signal.

---

## 4. Estimating the financial impact of each predicted issue

For one vehicle and one predicted issue:

```
expected cost = P(issue occurs)  ×  typical repair/replacement cost  ×  is-warranty-eligible (1 or 0)
```

That produces a real rupee number: "if nothing is done, this vehicle is
expected to cost Mahindra ₹X in warranty liability for this issue." Sum
that across every currently-at-risk vehicle in the fleet to get the total
expected liability for that issue right now — the same expected-value
approach insurers use for reserving, not a guess.

**Real cost variance already visible in the 55 existing claims** (not
hypothetical — confirms per-issue cost modeling is necessary, a flat
average would misrepresent most categories):

| Issue category | Claims | Avg claim amount (₹) | Avg approved (₹) |
|---|---|---|---|
| STEERING_NOISE | 7 | 24,921 | 17,369 |
| RIDE_QUALITY | 3 | 59,774 | 56,335 |
| HVAC_NOISE | 2 | 60,900 | 54,603 |
| INTERIOR_RATTLE | 1 | 83,430 | 78,214 |
| RATTLE_NOISE | 1 | 6,161 | 6,066 |
| INTERMITTENT_ELECTRICAL | 1 | 35,810 | 0 (rejected) |

---

## 5. How to rank predicted issues

**Ranking by individual claim cost alone would be misleading.** A rare but
expensive issue could easily outrank a common issue that actually costs
Mahindra far more in total. The right ranking basis combines everything
asked about:

```
priority = failure probability × cost per claim × number of affected vehicles
         = total expected fleet-wide liability
```

Rank highest to lowest by that combined number.

**One addition worth flagging**: pure rupee ranking can under-rank a
**safety-critical** issue (e.g. a braking or steering fault) that happens
to be cheap to fix but carries real regulatory/recall/reputational risk
beyond its warranty cost. Standard practice is to keep the rupee-based
ranking as the primary sort, but let severity/safety class (already
present as `severity`: HIGH/MEDIUM/LOW) act as an escalation flag that can
pull an issue up the list regardless of its raw rupee rank — not silently
folded into the same number.

---

## 6. Warranty eligibility, driving behavior, and supporting documents

### 6.1 Do we need warranty policy data?

**Yes — this is a real gap, not optional.** Without it, there is no way
to tell whether a predicted issue is actually a liability to Mahindra at
all — a vehicle past its coverage window, or an excluded part, costs
Mahindra nothing even if the failure is real. The existing
`warranty_claims.claim_status` (APPROVED/REJECTED/MANUAL_REVIEW) shows
*outcomes* of past adjudication, but there is no *policy rulebook* to
evaluate a *predicted* (not-yet-filed) issue against.

A structured, queryable policy reference table is still what does the
actual eligibility math (see §6.5-6.6 for why documents alone aren't
enough for that). It would need:

- **Coverage type** per model/variant (standard bumper-to-bumper vs.
  extended powertrain vs. battery-specific — EVs/hybrids typically carry
  a separate, longer battery warranty, and this project already tracks
  battery telemetry closely).
- **Coverage duration** (months from delivery) and **coverage limit**
  (odometer km), with the usual "whichever comes first" rule.
- **Part-level overrides** — wear items (tyres, wipers, brake pads)
  usually get short or no coverage; powertrain/battery often get *longer*
  coverage than the base warranty.
- **Exclusions** — causes not covered (accident damage, unauthorized
  modification, normal wear).
- **Region-specific variation**, if applicable.

### 6.2 Eligibility is not just about the vehicle — it's about how it was driven

The framing above (coverage window + mileage + part) answers "is this
vehicle still in policy," but it does not answer a real and separate
question: **was this specific failure caused by a manufacturing defect,
or by how the vehicle was driven/used?** A vehicle well within its
warranty period can still have a claim denied for one specific component
if the damage was self-inflicted through misuse. This is the same
principle usage-based insurance already applies to driving risk in
general; here it applies to *warranty* eligibility for a *specific
claim*, using telematics Mahindra already collects.

This needs two new things that do not exist in the plan today:

- **A driving-behavior profile per vehicle** — a rolling summary of
  abuse-relevant telematics signals already available (steering-angle
  change rate, lateral/vertical acceleration, sustained vibration,
  harsh-braking frequency, speeding, overloading indicators), tracked
  over time, not a single point-in-time flag. Misuse is a pattern, not
  one bad data point.
- **A driver-to-vehicle mapping, if it matters for this fleet.**
  Telematics today is captured per vehicle unit, not per driver. If a
  vehicle can have multiple distinct drivers (e.g. commercial/fleet use),
  "policy for the user" and "policy for the vehicle" diverge and a
  driver identity would need to be linked in. If vehicles are
  effectively single-owner/single-driver, the vehicle-level profile
  already *is* the driver profile and nothing extra is needed — **this
  needs to be confirmed against how Mahindra's fleet is actually used**
  before building the driver-mapping piece.

### 6.3 Claim-time telematics forensics (defect vs. misuse)

A new investigative step, run whenever a claim is filed (not only when
predicting risk in advance):

1. Pull the telematics window immediately before and around the reported
   failure for the specific vehicle.
2. Check whether the failure pattern is consistent with abuse of *that
   specific component* — e.g. a steering/suspension failure preceded by
   a spike in steering-angle-rate or lateral-g events reads very
   differently from the same failure with a flat, unremarkable telematics
   history.
3. Output one of three findings — `LIKELY_DEFECT`, `LIKELY_MISUSE`, or
   `INCONCLUSIVE` — with the specific telematics evidence attached, so a
   human adjuster can see exactly why, not just trust a black-box label.

This finding becomes a second eligibility gate alongside the
coverage-window check in §6.1: **even a vehicle that passes the coverage
check can still be denied for one claim if this step finds misuse of
that component.**

### 6.4 Financial impact — what changes, what doesn't

The formula from §4 does not change structurally:

```
expected cost = P(issue occurs) × typical repair/replacement cost × is-warranty-eligible (1 or 0)
```

What changes is that `is-warranty-eligible` is no longer a single
coverage-window lookup — it's the combination of §6.1 (still in policy?)
**and** §6.3 (was this misuse, for this specific claim?). A vehicle that
looks high-risk from manufacturing/telematics leading indicators but has
a driving-behavior profile that would flip a future claim to
`LIKELY_MISUSE` should be treated as lower expected *liability* to
Mahindra, even though the failure itself may still be likely to happen —
the cost simply wouldn't fall on Mahindra.

### 6.5 Synthetic document corpus required

Structured tables do the actual eligibility math (§6.1, §6.3), but real
warranty and insurance decisions are also written down as actual policy
documents, and a copilot explaining "why was this claim denied" should
be able to quote real, consistent policy language rather than paraphrase
a database row. This needs a synthetic document corpus:

**Warranty-side**

1. **Master Warranty Policy** (per model/variant) — base bumper-to-bumper
   terms: duration, mileage limit, "whichever comes first," general
   exclusions (accident damage, unauthorized modification,
   non-Mahindra-authorized repair, undeclared commercial use).
2. **Powertrain/Battery Warranty Addendum** (EV/hybrid-specific) —
   separate, usually longer coverage for motor/drivetrain and battery
   (e.g. capacity-retention guarantee).
3. **Component-Level Coverage Schedule** (per model) — one row per
   `supplier_component_category` with its own duration/mileage limit;
   the document form of the structured table in §6.1.
4. **Driving-Behavior Exclusion Clauses** — explicit prose per component
   on what usage voids coverage (e.g. "suspension is not covered where
   telematics indicates sustained harsh-impact/off-road driving beyond
   specified thresholds"). This is what a RAG lookup would retrieve to
   justify a §6.3 misuse-based denial.
5. **Maintenance/Service Compliance Requirements** — warranty conditional
   on following the service schedule; ties directly to the existing
   `service_events` table (`repair_required`, `complaint_reported`,
   `warranty_candidate`).
6. **Claim Adjudication Guidelines** (internal-facing) — the rulebook an
   adjuster follows: how `root_cause_domain` + `severity` + telematics
   evidence map to approve/reject/manual-review.
7. **Regional Warranty Variation Addenda** — only if region-specific
   terms matter for this fleet.

**Insurance-side**

8. **Motor Insurance Policy Certificate** (per vehicle) — policy number,
   sum insured (IDV), premium, deductible, policy period, cover type.
9. **Insurance Terms & Conditions** — covered perils (accident, theft,
   fire, natural calamity) vs. exclusions; critically states that
   mechanical/electrical breakdown is a *warranty* matter, not insurance.
10. **Add-on/Rider Cover Documents** — zero-depreciation, engine
    protection, roadside assistance, return-to-invoice — these change
    the payable amount for the same failure.
11. **Claims History / No-Claim-Bonus Statement** — prior claims and
    NCB% per policy, relevant to the financial-risk profile.
12. **Surveyor/Claim Investigation Report** (synthetic) — the
    natural-language counterpart to §6.3: what a real surveyor writes up
    after inspecting damage, cross-referenced against telematics-derived
    driving-behavior findings.

**Shared**

13. **Warranty-Insurance Boundary Guidelines** — clarifies which
    failures route to warranty vs. insurance (accident/collision →
    insurance; manufacturing defect → warranty; ambiguous → manual
    review), so the financial-impact model never double-counts a
    failure under both.

### 6.6 Document templates — what each one needs before generation can start

Each document type above needs a reusable template: a fixed structure
with placeholders filled in from real/synthetic data, so every generated
instance stays internally consistent and joinable back to the structured
tables (`issue_category`, `supplier_component_category`, `severity`,
vehicle records). "Grain" below means how many instances of that document
type actually need to be generated.

| # | Document | Grain (generated per…) | Template must define | Pulls from |
|---|---|---|---|---|
| 1 | Master Warranty Policy | model + variant | Policy header, coverage duration/mileage statement, general exclusions list, transferability clause | model/variant list |
| 2 | Powertrain/Battery Addendum | model (EV/hybrid only) | Battery duration/mileage, capacity-retention %, motor/drivetrain terms | model list, battery specs |
| 3 | Component-Level Coverage Schedule | model | One row per `supplier_component_category`: duration, mileage, special conditions | `supplier_component_category` (19 values) |
| 4 | Driving-Behavior Exclusion Clauses | component category (shared across models unless tuning differs) | Trigger condition description, matching telematics signal, exclusion text | telematics field list, `supplier_component_category` |
| 5 | Maintenance/Service Compliance | model | Required service intervals (km/months), consequence of missed service, critical-service list | `service_events` schema |
| 6 | Claim Adjudication Guidelines | one document (global) | Decision matrix: `root_cause_domain` × `severity` × telematics evidence → outcome | `root_cause_domain`, `severity`, `claim_status` |
| 7 | Regional Variation Addenda | region (only if needed) | Region name, climate/region-specific clause text | region list, if tracked |
| 8 | Motor Insurance Policy Certificate | vehicle/policy | Policy number, IDV, premium, deductible, policy period, cover type | vehicle records |
| 9 | Insurance Terms & Conditions | one document (shared/global, or per insurer if multiple) | Covered perils list, exclusions list, warranty/insurance boundary note | — (mostly static policy text) |
| 10 | Add-on/Rider Cover | rider type (zero-dep, engine protection, RSA, RTI, …) | Rider name, additional coverage description, premium delta, conditions | rider type list |
| 11 | Claims History / NCB Statement | policy, per renewal cycle | NCB %, past-claims table (date, type, amount) | `warranty_claims`/insurance claim history |
| 12 | Surveyor/Claim Investigation Report | claim | Inspection findings, cause assessment (accident/mechanical/wear), telematics cross-reference notes, recommended payout | claim record + telematics window (§6.3) |
| 13 | Warranty-Insurance Boundary Guidelines | one document (global) | Decision tree: accident → insurance, defect → warranty, ambiguous → manual review, with worked examples per `issue_category` | `issue_category` (26 values) |

Documents 6, 9, and 13 are **global** (one instance each, not generated
per vehicle/model) — they're rulebooks, not per-vehicle paperwork.
Everything else scales with the number of models, components, or actual
vehicles/claims being simulated.

**Status: #1 and #3 are implemented.** A real Mahindra Thar CRDe
Warranty Information & Maintenance Guide (2015) the user supplied was
used to validate structure/clause style/exclusion language (see the
worked comparison earlier in this conversation - not reproduced here),
combined with the user's researched current terms (3 years/120,000 km
base, 5 years/150,000 km extended). Generator code:

- `data/generators/documents/blocks.py` — shared content model
  (Heading/Paragraph/BulletList/Table/PageBreak) so the Markdown and
  PDF outputs are always built from the exact same content, never two
  copies that can drift apart.
- `data/generators/documents/render_markdown.py` /
  `render_pdf.py` (reportlab) — the two renderers.
- `data/generators/documents/warranty_policy_data.py` — the actual
  synthetic policy data: base/extended durations, and all 19
  `supplier_component_category` values classified into
  base-extendable / proprietary / wear-limited / excluded / consumable
  coverage, plus the standard exclusion list (adapted from the real
  Thar document, including the misuse/accident/continued-use clauses
  and a new driving-behavior-exclusion clause referencing §6.2-6.3).
- `data/generators/documents/master_warranty_policy.py` /
  `component_coverage_schedule.py` — the two document builders.
- `data/generators/documents/generate_warranty_policy_docs.py` — runs
  `build_master_warranty_policy()` and `build_component_coverage_schedule()`
  **once each**, both as single global documents ("Master Warranty
  Policy — Mahindra" and "Component-Level Coverage Schedule — Mahindra").
  Both were originally generated per model, but a diff of the per-model
  copies showed them word-for-word identical except for the title, since
  none of the underlying data (durations, exclusion list,
  proprietary-items list, the component coverage table) actually varies
  by model in this project's synthetic data - so both were consolidated.
  The project's real vehicle-model master data is Thar, Scorpio-N,
  XUV700, Bolero, XUV 3XO — all ICE; no EV model exists, so the
  Powertrain/Battery Addendum (document #2) has nothing to generate
  against yet. If a genuine model-specific coverage difference is ever
  introduced, that is the place to reintroduce per-model generation for
  just that difference.

Output: `data/synthetic/documents/warranty/` — one `.md` (RAG-ready)
and one `.pdf` (showcase) each for `master_warranty_policy` and
`component_coverage_schedule`, 4 files total. Run with:
`Causal_Discovery_Service/.venv/bin/python3 -m
data.generators.documents.generate_warranty_policy_docs`. New
third-party dependencies (`reportlab`, `PyYAML` - the latter was
already an undeclared dependency of the pre-existing `data/generators`
package) are pinned in the new `data/requirements.txt`. Table PDFs use a
plain white background/black text style (an earlier dark-header version
was hard to read and was replaced).

**#4 (Driving-Behavior Exclusion Clauses) is also implemented**, as a
single **global** document (not per model - the underlying telematics
misuse physics don't vary by model in this synthetic PoC). Grounded in
the real column names in `data/synthetic/causal/vehicle_telematics_timeseries.csv`
(confirmed against that file, not assumed): 8 of the 19
`supplier_component_category` values get a real clause (Steering,
Suspension, Drivetrain Components, Braking System, Exhaust, ECU
Electronics, Electrical Wiring, Battery), each naming the actual
telematics field(s), the misuse pattern, an illustrative threshold
(explicitly flagged as a synthetic PoC assumption, not a real
engineering spec), and the exclusion clause text. The remaining 11
categories (Adhesives, Fasteners, Fluids, Glass, HVAC, Lighting,
Plastic Trim, Rubber Seals, Seating, Steel Body Panels, Tyres) have no
real telematics fingerprint and explicitly fall back to the Master
Warranty Policy's general misuse/accident exclusions rather than
inventing a false-precision threshold. Code:
`data/generators/documents/driving_behavior_data.py` (the clauses),
`driving_behavior_exclusions.py` (the document builder),
`generate_driving_behavior_doc.py` (the runner) → outputs
`driving_behavior_exclusion_clauses.{md,pdf}` in the same
`data/synthetic/documents/warranty/` directory.

**#5 (Maintenance/Service Compliance) is also implemented**, also as a
**global** document, deliberately deviating from the "grain: model" in
the template table above: this project's real `service_events` data
(`data/generators/auto/service.py`) currently models exactly one
scheduled-maintenance checkpoint (`FIRST_INSPECTION`, 20-45 days after
delivery, with a real 78% measured attendance rate baked into the
generator - i.e. a real ~22% non-compliance population, not invented),
not the fuller multi-visit odometer-based schedule the real Thar PDF
shows. The document says this explicitly rather than fabricating a
schedule the underlying data can't back up. Code:
`data/generators/documents/maintenance_compliance_data.py` (mirrors
`service.py`'s real constants), `maintenance_compliance.py` (builder),
`generate_maintenance_compliance_doc.py` (runner) → outputs
`maintenance_service_compliance.{md,pdf}`.

**#6 (Claim Adjudication Guidelines) is also implemented**, as a single
**global**, internal-facing document. Grounded directly in the real
decision logic already used to generate this project's `warranty_claims`
data (`data/generators/auto/warranty.py`'s `_derive_claim_decision` and
`_derive_root_cause_domain` functions, including their real reference
constants: production-quality reference 0.95, supplier-quality reference
0.90) - this describes the actual rules the synthetic claims data was
generated under, not an invented rulebook, so a copilot citing it to
explain "why was this claim approved/rejected" is citing the real
generator logic. Documents the 5 real `root_cause_domain` values
(SUPPLIER_QUALITY, MANUFACTURING_QUALITY, COMPONENT_FAILURE,
MULTIPLE_FACTORS, SERVICE_DIAGNOSIS), the real evidence factors
(severity, supplier lot quality, production quality, claim amount), and
a plain-English decision guide translating the generator's continuous
evidence-strength scoring into qualitative evidence-pattern → likely-
outcome rows. Code: `data/generators/documents/claim_adjudication_data.py`
(the real thresholds/domains), `claim_adjudication_guidelines.py`
(builder), `generate_claim_adjudication_doc.py` (runner) → outputs
`claim_adjudication_guidelines.{md,pdf}`.

**#13 (Warranty-Insurance Boundary Guidelines) is also implemented**, as
a single **global** document - and it surfaced a real, important gap,
checked directly against the generator code rather than assumed: **none
of this fleet's 26 real `issue_category` values are accident/collision
type** - all 26 are quality/wear/electrical/noise patterns - and
`warranty_claims`/`service_events` have no accident/collision event
source wired into them at all. An accident-history concept
(`accident_history_count`, `major_accident_flag`) does exist elsewhere
in this project's synthetic data, but only in the circularity/
end-of-life-vehicle domain (`data/generators/circularity/elv.py`),
completely unlinked to the warranty/service pipeline. Practical
consequence: every one of the 26 categories defaults to WARRANTY under
this document's 3-step decision tree (collision telematics evidence →
INSURANCE; recognised defect pattern → WARRANTY; mixed/insufficient
evidence → MANUAL_REVIEW, never auto-INSURANCE given the gap above).
**The insurance-side documents (#8-12) will need this gap closed first**
- either by linking the existing ELV accident-history data into the
claims pipeline, or by generating a separate synthetic insurance-claims
data source - before any of them can reference real per-claim data the
way the warranty-side documents do. Code:
`data/generators/documents/boundary_guidelines_data.py` (the real
26-value list, matching section 3's live-database-confirmed list, not
the generator's fuller ~40-value candidate set), `boundary_guidelines.py`
(builder), `generate_boundary_guidelines_doc.py` (runner) → outputs
`warranty_insurance_boundary_guidelines.{md,pdf}`.

**Update:** the accident/insurance data gap this document reported is now
partially closed. `data/generators/auto/service.py` gained
`generate_accident_service_events()` and
`generate_telematics_linked_accident_events()`, and a new
`data/generators/auto/insurance.py` generates real insurance claims from
accident-caused service events (mirroring `warranty.py`'s architecture) -
run via two new scoped refresh scripts,
`data/scripts/refresh_accident_insurance_claims.py` and
`refresh_telematics_correlated_accidents.py`, both deliberately built to
never touch manufacturing/mobility timeseries and to leave every
pre-existing row byte-identical (proven via an explicit base-match
assertion each run). Live result: 24 real accident-caused service
events, 22 real insurance claims, 3 with a genuine correlated telematics
signature (the small 24-vehicle telematics cohort's 7-day-per-vehicle
coverage limits how many can have real matching telematics evidence -
see the Boundary Guidelines document's own "A Note On Scope" section,
which now reads its stats live from the actual data rather than stating
a fixed gap). `data/dataset_manifest.json` updated accordingly
(`synthetic/auto/insurance_claims` registered as a new dataset).
The Boundary Guidelines document (#13) itself was updated to add the
ACCIDENT_DAMAGE routing row and report these live counts, so it no
longer describes a gap that has since been closed.

**#12 (Surveyor/Claim Investigation Report) is also implemented** - the
first document in this corpus generated per **claim** (grain: claim, per
the template table above), not per model or as a single global document.
One report is generated for every real row currently in
`data/synthetic/auto/insurance_claims.csv` (22 today). Each report reads
the real claim/service data and, where the claim's vehicle has telematics
coverage (3 of 22 today - see §13's "A Note On Scope"), pulls the actual
recorded telematics window (speed, impact-g, vertical/lateral
acceleration) around the incident as cited evidence in a table; the
other 19 reports honestly state that no telematics coverage exists for
that vehicle, rather than fabricating a table. Recommended payout is
read directly from the claim's already-decided `claim_status`/
`approved_amount_inr` - the LLM/template layer never invents a payout
number. Code: `data/generators/documents/surveyor_report_data.py`
(joins insurance_claims + service_events + a telematics window lookup),
`surveyor_report.py` (builder), `generate_surveyor_reports_docs.py`
(runner) → outputs `data/synthetic/documents/insurance/surveyor_reports/
surveyor_report_<insurance_claim_id>.{md,pdf}` (44 files for 22 claims).

**#8 (Motor Insurance Policy Certificate) and #11 (Claims History / NCB
Statement) are also implemented**, one of each per insured vehicle. No
policy master data existed anywhere in this project before this - only
claims existed, referencing a bare `policy_number` string with nothing
defining what it actually covers. `data/generators/documents/insurance_policy_data.py`
computes real per-vehicle IDV, premium, and deductible from data already
in this project (each model's real `base_price`, each vehicle's real
delivery date) using the actual IRDAI-published IDV depreciation
schedule and NCB slab schedule (real, citable industry standards - not
invented), with a simplified, explicitly-flagged synthetic premium
rate/deductible tier on top. **Scope**: policies are only generated for
the 22 vehicles that already have a real insurance claim, not the full
~1,349-vehicle fleet - this project has no "is this vehicle insured"
concept at all yet, so generating certificates for the whole fleet would
overstate what the data actually models; claims are where insurance is
genuinely "activated" here. Code: `insurance_policy_data.py` (real
per-vehicle policy + depreciation/NCB math), `insurance_policy_certificate.py`
/ `claims_history_ncb.py` (the two builders), `generate_insurance_policy_docs.py`
(runner) → outputs `data/synthetic/documents/insurance/policy_certificates/`
and `.../claims_history_ncb/` (88 files: 22 policies × 2 documents × 2
formats).

**#9 (Insurance Terms & Conditions) and #10 (Add-on/Rider Cover
Documents) are also implemented**, both single global documents.
Covered perils, standard exclusions, and the six riders (Zero
Depreciation, Engine Protection, Roadside Assistance, Return To
Invoice, Consumables, NCB Protection) reflect real, standard IRDAI-
regulated Indian motor insurance categories - the same real-industry-
standard grounding approach already used for the Master Warranty
Policy, not invented categories. #9 explicitly cross-references the
Warranty-Insurance Boundary Guidelines document (mechanical/electrical
breakdown is excluded from insurance - a warranty matter). Premium-
delta percentages and eligibility conditions in #10 are explicitly
flagged as simplified synthetic PoC assumptions. Code:
`insurance_terms_data.py` / `insurance_terms.py`, `rider_cover_data.py`
/ `rider_cover.py`, `generate_insurance_reference_docs.py` (runner) →
outputs `insurance_terms_and_conditions.{md,pdf}` and
`addon_rider_cover.{md,pdf}` in `data/synthetic/documents/insurance/`.

**This completes all 13 documents in the corpus described in §6.5** -
#2 (Powertrain/Battery Addendum) remains explicitly not generated
(no EV model exists in this project's real vehicle-model master data),
and #7 (Regional Variation Addenda) remains explicitly skipped (no
region-specific policy variation is modeled in this project). Every
other document (1, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13) is implemented,
grounded in real data or real industry-standard references throughout,
and regenerable on demand from the code in `data/generators/documents/`.

### 6.7 Retrieval layer (RAG) on top of the documents

Once the corpus in §6.5 exists, retrieval needs to be scoped so a lookup
for one issue/component returns the *right* clause, not a generic
document dump — e.g. indexed/filterable by `issue_category` and
`supplier_component_category` so a claim about STEERING_NOISE only
retrieves the steering-relevant clauses from the Component-Level
Coverage Schedule and Driving-Behavior Exclusion documents, not the
entire warranty corpus. This follows the same grounding pattern already
used elsewhere in this project: the structured tables (§6.1, §6.3) make
the actual eligibility decision; the RAG layer's only job is to retrieve
and quote the real clause that explains it — it should never be the
thing deciding eligibility itself.

---

## Summary: what's genuinely new vs. what already exists

**Already exists, reusable as-is:**
- Issue taxonomy (`issue_category`, 26 values)
- Cluster/part taxonomy (`supplier_component_category`, 19 values)
- Severity classification (`severity`)
- Root-cause classification (`root_cause_domain`)
- Historical claim outcomes and amounts (`warranty_claims`, `claim_status`)
- A much larger pool of service/complaint signals (`service_events`)
- Manufacturing and telematics feature sources

**Needs to be built:**
- A forward-looking cost-per-issue reference table
- A warranty policy/eligibility reference table (structured, §6.1)
- A driving-behavior profile per vehicle, built from existing telematics
  signals (§6.2) — and a driver-to-vehicle mapping, only if this fleet
  has vehicles with multiple distinct drivers (needs confirming)
- A claim-time telematics forensics step (defect vs. misuse, §6.3)
- A fleet population count for scaling per-vehicle probabilities to
  fleet-wide liability
- More historical claims (or a documented plan to supplement the 55
  existing ones with `service_events`-derived weak labels)
- The clustered multi-class classifier itself (one per
  `supplier_component_category` cluster, or one hierarchical model across
  all clusters)
- The financial-impact + ranking layer described in §4-5
- The remaining 11 documents of the 13-document synthetic corpus
  (warranty + insurance) described in §6.5 — #1 and #3 are implemented,
  see §6.6
- A RAG retrieval layer over that corpus, scoped per issue/component
  (§6.7)
