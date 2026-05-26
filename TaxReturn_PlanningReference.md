# SachinTaxCare — Tax Return Planning Reference
*Last updated: 2026-05-26 · **Version V17.4** · All dollar values from `PARAMS_2025` / `PARAMS_2026` in engine.*
*IRS source authority: irs.gov only (per Rules 12+15+16).*

---

## How to use this document

Single source of truth for every tax constant, rule, bridge mapping, test gate, and session protocol.
**Before any session:** run all six gates in 9A. Zero failures required before any changes.

---

## Page 1 — File Registry

| File | Lines | Version | Role |
|---|---|---|---|
| `sachintaxcare_engine.py` | **8,908** | V17.3 — qualified_dividends alias, DIV box2b unrec§1250→QDCGT, FTC alias | Computation engine (TY 2025 + TY 2026) |
| `sachintaxcare_pro.html` | **4,821** | v9 — FLSA restore, care spouse restore, standalone div fields, div aliases | Primary UI — intake + results |
| `sachintaxcare_server.py` | **835** | v18 — safe_init None guard, Windows UTF-8 startup fix, SM buildSchema field names | Flask server + bridge |
| `sachintaxcare_workpaper.html` | **1,670** | v8 — 18 pages, try/catch, pre-declared sub-dicts, QBI L13a, Sch C summary | CPA workpaper |
| `sachintaxcare_test.py` | **2,527** | v4.2 — **593 PASS · 0 FAIL · 0 WARN** | Regression suite |
| `test_vita_irs.py` | **2,486** | v12.3 — **218/218 PASS**; Section 35 P1/P2/P3; Section 36 DIV routing regression | VITA known-answer tests |
| `test_ui_fields.js` | **815** | v2.0 — 64 round-trip keys — **404 PASS · 0 FAIL** | UI field completeness |
| `sachintaxcare_pdf.py` | **367** | v1.0 | PDF output (reportlab) |
| `sachintaxcare_report.py` | **965** | v11 | JSON verification report |
| `test_report.py` | **415** | v1 | Report verification tests |
| `sachintaxcare_field_manifest.md` | **1,021** | v1.4 — 0 ❌ remaining | Field registry |
| `IMPLEMENTATION_GUIDE.md` | **330** | V17.1 | How to rebuild from scratch |
| `ENGINE_ALGORITHM.md` | **604** | V17.1 | Engine computation flow |
| `sachintaxcare_schema_2025.json` | **31** | v1 | JSON schema reference |

**Session start gate:** `python3 sachintaxcare_test.py` → **593 PASS · 0 FAIL · 0 WARN**

---

## Page 1A — Changelog (most recent first)

### Session 2026-05-26 — **V17.4** — Filing rules expanded + Windows server fix + Willis null crash

**Gate results (no test changes — documentation and bug fixes only):**
- sachintaxcare_test.py: **593 PASS · 0 FAIL · 0 WARN**
- test_vita_irs.py: **218/218 PASS**
- test_ui_fields.js: **404 PASS · 0 FAIL**

| Fix | Severity | Item | What changed |
|---|---|---|---|
| Windows UTF-8 crash | CRIT | `subprocess.run(text=True)` used cp1252 on Windows → UnicodeDecodeError on startup | Removed `text=True`; decode bytes manually with `utf-8 errors=replace`; added `PYTHONIOENCODING=utf-8` to env |
| None + str crash | HIGH | `result.stdout + result.stderr` crashed when stdout=None after encoding failure | Guarded with `if result.stdout else ''` |
| Willis null crash | CRIT | `ca_itemized_total: null` from JSON → `safe_init()` passed None → `None > 0` TypeError | `_safe_init()` now replaces JSON null with field default for all scalar typed fields |
| ca_itemized_total guard | MED | `if cd.ca_itemized_total > 0` in engine — no None guard | Added `is not None and` guard (defense-in-depth) |
| SM buildSchema keys | HIGH | `buildSchema` sent old SM key names (`age_at_start` etc.) → dropped by safe_init() → wrong pension taxable | buildSchema now sends exact engine names: `age_at_annuity_start`, `joint_age_at_annuity_start`, `prior_year_tax_free_recovered`, `annuity_start_after_nov_18_1996` |
| Startup banner | LOW | Banner said "Engine v15 · 180/180 tests" (stale) | Updated to "Engine V17.3 · 593 tests · 218 VITA tests" |
| Rules 17–25 added | DOC | 9 new filing rules documenting existing engine behavior | See Page 5 Rules 17–25 (renumbered; former Rules 25/26/27 → 26/27/28) |

### Session 2026-05-26 — **V17.3** — 1099-DIV routing fixes + Import/Export round-trip gaps

**Gate results after this session:**
- sachintaxcare_test.py: **593 PASS · 0 FAIL · 0 WARN**
- test_vita_irs.py: **218/218 PASS** (was 212; +6 Section 36 DIV regression tests)
- test_ui_fields.js: **404 PASS · 0 FAIL**

| Fix | Severity | Item | What changed |
|---|---|---|---|
| DIV box1b qualified_div | HIGH | `qualified_dividends` missing from result dict — result panel showed $0 for Line 3a | Added `"qualified_dividends": dividends_qual` alias to computed dict |
| DIV box2b unrec §1250 | HIGH | 1099-DIV Box 2b not added to QDCGT 25% pool; only Form 4797 sourced | `div_unrec_1250 = sum(box2b_unrec_1250)` added to `total_unrec_1250`; passed to `compute_qdcgt_tax()` |
| FTC alias | LOW | `foreign_tax_credit` key missing (engine used `ftc_credit`); UI expected `foreign_tax_credit` | Added `"foreign_tax_credit": ftc_credit` alias to computed dict |
| Import: FLSA checkbox | MEDIUM | `overtime_flsa_confirmed` exported but not restored on import — checkbox always reset unchecked | `populateFromSchema`: `_flsaEl.checked = sc.overtime_flsa_confirmed` |
| Import: care spouse status | MEDIUM | `care_spouse_is_student/disabled/months_qualified` exported but not restored — deemed income calc lost on re-import | `populateFromSchema`: restores `care-spouse-status` select and `care-spouse-months` |
| Standalone dividend fields | NEW | No UI path to enter dividends without individual 1099-DIV rows | Added `div-ordinary-total` / `div-qualified-total` fields below 1099-DIV list; wired to `dividends_ordinary` / `dividends_qualified` in buildSchema + populateFromSchema |
| File sync | LOW | `sachintaxcare_pdf.py`, `sachintaxcare_report.py`, `test_report.py` missing from outputs | Copied to /mnt/user-data/outputs/ |

### Session 2026-05-25 — **V17.2** — CA P1, Form 2210 quarterly, income routing

**Gate results after this session:**
- sachintaxcare_test.py: **593 PASS · 0 FAIL · 0 WARN** (was 584/0/4)
- test_vita_irs.py: **212/212** PASS (was 145/145; +17 new Section 35 tests)
- test_ui_fields.js: **404 PASS · 0 FAIL**

| Fix | Severity | Item | What changed |
|---|---|---|---|
| P1 CA std ded | CRIT | $5,540/$11,080 (2024 values) → **$5,706/$11,412** (2025) | ftb.ca.gov/forms/2025/2025-540.pdf Line 18; FETCH_VERIFIED |
| P1 CA HOH bracket | CRIT | Schedule Z entirely missing; engine used single brackets for HOH | `ca_brackets_hoh_2025` added; HOH now routes to Schedule Z |
| P1 CA 2025 brackets | CRIT | 2024 breakpoints in Schedule X and Y throughout | All updated: X[0]=$11,079; Y[0]=$22,158 |
| P1 Military $20k cap | HIGH | CA military pay exclusion uncapped | `min(ca_military_pay_exclusion, 20000)` per R&TC §17132.9 |
| P1 Alimony addback | HIGH | TY 2025 CA transition rule missing | `ca_alimony_addback` field + warning; R&TC §17076 |
| P1 NOL suspension | HIGH | 2024–2026 CA NOL suspension addback missing | `ca_nol_addback` field + warning; R&TC §17276.24 |
| P2 EITC | INFO | Already filing-grade — band algorithm confirmed correct | No change; approximation language removed from docs |
| P3 Form 2210 quarterly | MEDIUM | Annual rate estimate → per-installment quarterly penalty | i2210.pdf Part III; Q1–Q4 dates; daily rate 8%/365 |
| Unemployment bridge | CRIT | Flat `unemployment_income` scalar silently dropped by safe_init() | Server bridge synthesizes Form1099G; WH flows to Line 25b |
| Jury duty | HIGH | No field, no compute, no Sch 1 Line 8h | `jury_duty_income` field + compute + UI card; f1040s1.pdf L8h |
| 1099-DIV key names | HIGH | buildSchema sent stale field names; all 16 DIV boxes dropped | All 16 boxes use exact engine names; Box 2c + Box 6 added |
| W-2G/1099-G WH | HIGH | Not routed to Line 25b | `l25b_w2g_wh` + `l25b_1099g_wh` added to L25b total |
| Form 2441 age-13 | HIGH | CTC-eligible dependents age ≥13 incorrectly counted for care credit | `care_qualifying = [d for d in ctc_children if d.age < 13]`; IRC §21(b)(1)(A) |
| MFS mortgage limit | MEDIUM | $750k used for MFS filers | MFS → $375k; grandfathered MFS → $500k; IRC §163(h)(3)(B)(ii) |
| EstimatedTaxPayments | HIGH | Nested dict passed as raw dict → AttributeError on `.q1` | Added `EstimatedTaxPayments` to `_SCALAR_NESTED` in server |
| Schema import compat | HIGH | 15 renamed fields, 3 structural changes in old schemas | UI `populateFromSchema` now accepts old \|\| new names for all renamed fields |
| MFS cap loss $1,500 | KNOWN GAP | Engine uses $3k cap for MFS | IRC §1211(b)(1) — not yet implemented |
| IRC §63(c)(5) dep std ded | KNOWN GAP | Engine uses regular std ded for dependents | Not yet implemented |
| IRC §25B(c)(1) student | KNOWN GAP | Saver's credit not disqualified for students | Not yet implemented |
| QSS stale death year | KNOWN GAP | 2-year window check not enforced | Not yet implemented |

### Session 2026-05-24 — **V17.1** — Session-start divergence fixes

| Fix | Item | What changed |
|---|---|---|
| Test 14.3 | Code `02` (SEPP) incorrectly asserted IRA-invalid | Changed to `'01'` (age-55 separation, plan-only per i5329.pdf). Code 02 valid for both IRAs and plans. IRC §72(t)(2)(A)(iv)/(v) |
| Test 4.4 | ODC tested on `sch3['l6d_odc']` (always 0 per Rule 2) | Fixed to `s8812['odc_total']`. Rule 2: ODC routes through Sch 8812. f1040s8.pdf; IRC §24(h)(4) |
| Tests 32.2b/32.4b/32.13b | OBBBA deductions tested as AGI reductions (V16 behavior) | Updated to test `taxable_income` — OBBBA is L13b below-the-line. Expected: 32.2b→$36,250; 32.4b→$44,250; 32.13b→$59,250 |
| `qbi_min` alias | `PARAMS_2026['qbi_min']` KeyError | Added `"qbi_min": 400` alias alongside `qbi_min_deduction` in PARAMS_2026 |
| File registry | Page 1 line counts off by −1 on 5 files; citation count stale | Corrected all counts |

### Session 2026-05-24 — **V17** — IRS compliance, Form 8995 REIT, QBI routing, 1040 L16–L24

**Engine metrics after this session:**
- Compute functions: 42 · Dataclasses: 40 · Schema fields: 515+
- IRS citations: 1,521 · FETCH_VERIFIED annotations: 13 · Round-trip keys: 64

| Fix | Severity | Item | What changed |
|---|---|---|---|
| Mileage rate | CRIT | 67¢ → **70¢/mile** | IRS Notice 2025-5; Pub 463 (2025); FETCH_VERIFIED |
| QBI on L13a | CRIT | QBI was reducing AGI (wrong) | Moved to below-the-line L13a. f1040.pdf L13a; IRC §199A |
| l4b routing | CRIT | IRA/pension in Sch1 L10 (wrong) | Moved to Lines 4b/5b directly. f1040.pdf Lines 4b, 5b, 8 |
| Form 8995 L6 | CRIT | REIT/PTP component entirely missing | 1099-DIV Box 5 §199A divs × 20%. f8995.pdf Lines 6–9; FETCH_VERIFIED |
| QBI base | CRIT | compute_qbi_deduction re-derived net profit from schema, missing mileage + NEC | Now accepts `se_net_profit` from `run()` directly |
| qdcgt double-count | HIGH | div_cap_gain_dist double-counted in QDCGT worksheet | `qdcgt = qual_div + max(0, net_ltcg)`. f1040.pdf QDCGT Worksheet |
| 1040 L21-L24 labels | HIGH | L21 was "Tax after credits" (wrong) | Correct IRS form order: L21=Add L19+L20; L22=L18−L21; L23=Other taxes; L24=L22+L23 |
| Education credit order | HIGH | Credits shown after L24 (wrong form order) | Credits (L19, L20) now before L24 |
| 1099-B import | HIGH | cost_basis → wrong field; is_long_term used wrong key | Fixed in populateFromSchema |
| 1098-E import | HIGH | No restore loop — 1098-E entries not importable | Restore loop added |
| Workpaper loading | MED | TypeError on undefined sub-dicts → forever loading | Six sub-dicts pre-declared; render() wrapped in try/catch |
| Round-trip | MED | 47 → 64 keys | schedule_cs, form_1099ints, form_5329_exceptions, form_1099divs added |

### Session 2026-05-22/23 — Schedule D, sch1/sch2/sch3 export, workpaper expansion

| Fix | Item |
|---|---|
| Schedule D double-count | Box C (ST noncovered) was in both `box_c_rows` AND ST accumulators |
| 1099-DIV box2a alias | `box2a_total_cap_gain` JSON vs `box2a_cap_gain_dist` engine — alias added |
| Form 5329 amount/account_type | Alias fields added to Form5329Exception |
| LLC fallback from AOC | All three AOC denial gates now fall through to LLC |
| Workpaper Pages A–G | W-2 summary, Schedule B, D/8949, C detail, 1099-R/5329, Form 8962, Form 2441 |

### Session 2026-05-18 — C2, M1–M6, EA audit critical/high fixes

| Fix | Item | What changed |
|---|---|---|
| C1 | EITC exact table | Rewritten — IRS $50-band algorithm; `requires_table_lookup` always False |
| C2 | Form 2441 deemed earned income | `care_spouse_is_student/disabled/months_qualified`; f2441.pdf Line 6 logic |
| C3 | OBBBA tips occupation | 30-occupation dropdown (IRS Notice 2025-65); mandatory service charges excluded |
| H1 | Cap gains §1250/28% | `unrecaptured_sec1250` and `collectibles_gain` params reduce the 0%/15%/20% pool |
| H4a | AOTC half-time gate | Hard gate: `box8_half_time=False` → AOTC = $0 |
| H4b | AOTC drug conviction | Hard gate: `aoc_drug_conviction=True` → AOTC = $0 |
| H6 | HOH hard gate | `selFS('hoh')` blocked if `S.deps.length === 0` |
| M1/M6 | OBBBA overtime FLSA | `overtime_flsa_confirmed: bool`; ⚠ warning when False |
| M3 | CA Schedule CA | `obbba_total_federal` auto-addback; military pay; loan forgiveness; CaliforniaData expanded |
| M4 | §1231 5-year lookback | `prior_sec1231_losses_5yr: float`; warning emitted; passed to `compute_form_4797` |

### Session 2026-05-17 — Willis workpaper bugs (5 fixed)

| Bug | Root cause | Fix |
|---|---|---|
| L25b missing SSA WH | `l25b_ssa_wh` stored but not summed | Workpaper shows breakdown: "1099-R: $X + SSA Box 6: $Y" |
| ODC on Sch 3 L6d (wrong) | ODC routed to `sch3_l6d` | `l12_8812 = ctc_total + odc_total`; `sch3_l6d = 0` always |
| Sch 8812 L19 / 1040 L32 missing | Computed correctly; not displayed | L19 added to Sch 8812 workpaper; L32 added to Form 1040 Page 2 |
| Sch 8812 page missing for ODC-only | `has8812` only checked CTC/ACTC | Condition now includes `odc_total > 0 \|\| l14_ctc > 0` |

---

## Page 2 — Architecture

### Data flow
```
Browser UI (sachintaxcare_pro.html)
  → buildSchema()
  → POST /compute
  → deserialize_schema() + safe_init()
  → engine.run(TaxpayerSchema)
  → dict(computed) [155+ keys, all auto]
  → map_result() [dict(c) pass-through + aliases]
  → renderResult()
  → CPA workpaper (18 pages) / exportJSON
```

### 1040 Structure — Lines 11–15 (critical — AGI vs taxable income)

```
L8   Additional income = Schedule 1 Part I total
     IRA/pension (L4b/L5b) → directly into total_income — NOT through Sch 1
L11  AGI = total_income − total_adjustments
     total_adjustments = Schedule 1 Part II (above-the-line only):
     SE deduction + student loan + IRA + teacher + SE health + HSA
     QBI is NOT in total_adjustments. OBBBA is NOT in total_adjustments.
L12  Standard deduction (or itemized)
L13a QBI §199A deduction (Form 8995 L15) — below-the-line, does NOT reduce AGI
L13b OBBBA Schedule 1-A (tips, overtime, auto, senior) — below-the-line, does NOT reduce AGI
L14  = L12 + L13a + L13b
L15  Taxable income = L11 − L14
```

### Form 8995 Structure — QBI Deduction

```
L1   QBI from each business (net profit − ½SE tax − SE health − SE retirement)
L2   Total QBI (= L1 + carryforward)
L3   QBI component = 20% × L2
L4   Net capital gain
L5   Ordinary taxable income = TI − L4
L6   Qualified REIT dividends (1099-DIV Box 5 §199A) + qualified PTP income
L8   Total REIT/PTP = L6 + carryforward
L9   REIT/PTP component = 20% × L8
L10  Combined = L3 + L9
L11  TI limit = 20% × L5
L15  QBID = min(L10, L11) → 1040 Line 13a
Source: f8995.pdf; i8995.pdf; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24
```

### map_result() architecture rule (permanent — Rule 3/24)
`map_result()` starts with `dict(c)` — every engine key is automatically in the output. Only add derived values (`effective_rate`, `marginal_rate`) and legacy aliases. Never enumerate individual keys. Adding a new engine key requires zero changes to the server.

### safe_init() field name mismatch table
Any field name mismatch between UI JSON and engine dataclass is silently dropped. Run bridge audit (Page 9F) at every session start.

| UI/JSON key | Engine field | Dataclass | Discovered |
|---|---|---|---|
| `box2_discharged` | `box2_amount_discharged` | Form1099C | 2026-05-16 |
| `exclusion_applies` | `is_excluded` | Form1099C | 2026-05-16 |
| `box6_vol_wh` | `box6_voluntary_wh` | FormSSA1099 | 2026-05-16 |
| `box9b_employee_contrib` | `box9b_employee_contribs` | Form1099R | 2026-05-16 |
| `box5_medicare_wages` | `box5_med_wages` | W2 | 2026-05-16 |
| `box6_medicare_wh` | `box6_med_wh` | W2 | 2026-05-25 |
| `box10_dep_care` | `box10_dependent_care` | W2 | 2026-05-25 |
| `box8_at_least_half_time` | `box8_half_time` | Form1098T | 2026-05-17 |
| `spouse{ssn,first,last,dob}` | `spouse_ssn/first/last/dob` | TaxpayerSchema | 2026-05-17 |
| `age_at_start` | `age_at_annuity_start` | SimplifiedMethodData | 2026-05-16 |
| `prior_tax_free_recovered` | `prior_year_tax_free_recovered` | SimplifiedMethodData | 2026-05-16 |
| `start_after_nov_1996` | `annuity_start_after_nov_18_1996` | SimplifiedMethodData | 2026-05-16 |
| `box2a_total_cap_gain` | `box2a_cap_gain_dist` | Form1099DIV | 2026-05-22 |
| `amount` | `distribution_amount` | Form5329Exception | 2026-05-21 |
| `account_type` | `plan_type` | Form5329Exception | 2026-05-21 |
| `cost_basis` → `sale-cost-` (wrong UI field) | → `sale-basis-` | UI 1099-B import | 2026-05-24 |
| `is_long_term` → `b.term` (wrong key) | → `b.is_long_term` | UI 1099-B import | 2026-05-24 |
| `basis_reported_to_irs` → `b.basis_reported` | → `b.basis_reported_to_irs` | UI 1099-B import | 2026-05-24 |
| `unemployment_income` (flat scalar) | Form1099G (synthesized by server bridge) | server bridge | 2026-05-25 |
| `jury_duty_income` (flat scalar) | TaxpayerSchema.jury_duty_income | direct | 2026-05-25 |
| `estimated_tax_payments` (raw dict) | EstimatedTaxPayments dataclass | _SCALAR_NESTED | 2026-05-25 |
| `box6_foreign_tax_paid` | `box6_foreign_tax` | Form1099INT | 2026-05-25 |
| `sdi_withheld` | `ca_sdi_withheld` | CaliforniaData | 2026-05-16 |
| `other_subtractions` | `ca_other_subtractions` | CaliforniaData | 2026-05-16 |
| `form_1099miscs[].box3` | Form1099MISC_Prize list | (constructed) | 2026-05-16 |
| `prize_income` (legacy flat) | Form1099MISC_Prize list | (constructed) | 2026-05-16 |

### Engine internals (V17.2)
- **Compute functions:** 40 / 40 cited
- **Dataclasses:** 40 · **Schema fields:** 556
- **Computed keys emitted:** 155+ (all via dict(c) pass-through)
- **IRS citations:** 1,623 · **FETCH_VERIFIED annotations:** 13
- **PARAMS_2025 constants:** 128 · **PARAMS_2026:** 153
- **Round-trip keys tested:** 64
- **TY 2025 + TY 2026 fully parametrized** — every constant keyed by year

---

## Page 3 — Tax Year Constants (TY 2025)

*Source: Rev. Proc. 2024-40 · OBBBA P.L. 119-21 · IRS Notice 2025-5*

### Standard Deductions (IRC §63)
| Status | Amount | Age-65/blind add-on |
|---|---|---|
| Single / MFS | $15,750 | +$2,000/condition |
| MFJ / QSS | $31,500 | +$1,600/qualifying spouse |
| HOH | $23,625 | +$2,000/condition |

### CA Standard Deductions (FETCH_VERIFIED 2026-05-24 — ftb.ca.gov/forms/2025/2025-540.pdf Line 18)
| Status | Amount |
|---|---|
| Single / MFS | **$5,706** |
| MFJ / HOH / QSS | **$11,412** |

### Mileage Rates (TY 2025)
| Purpose | Rate | Source |
|---|---|---|
| **Business** | **70¢/mile** | IRS Notice 2025-5; IRS Pub 463 (2025); FETCH_VERIFIED 2026-05-24 |
| Medical / moving | 21¢/mile | IRS Notice 2025-5 |
| Charitable | 14¢/mile | IRC §170(i) |

> **TY 2026:** 72.5¢/mile business (IR-2025-128, effective Jan 1, 2026)

### OBBBA Deductions (→ Form 1040 Line 13b; below-the-line; do NOT reduce AGI)
| Provision | OBBBA § | Cap | Phase-out MAGI starts |
|---|---|---|---|
| Senior Bonus Deduction (age ≥65) | §70103 | $6,000/person | $75k single / $150k MFJ |
| Qualified tips | §70201 | $25,000 | $150k single / $300k MFJ |
| FLSA overtime pay (§207) | §70202 | $12,500 single / $25,000 MFJ | $150k / $300k; MFS ineligible |
| Auto loan interest (new US vehicle) | §70301 | $10,000/yr | $100k single / $200k MFJ |
| SALT cap | §70106 | $40,000 (MFJ) / $20,000 (MFS) | Phase-down above $500k AGI |

All four OBBBA deductions flow through **Schedule 1-A → Form 1040 Line 13b**. They reduce **taxable income, NOT AGI**. CA did NOT conform — engine auto-adds back `obbba_total_federal` to CA income. Source: f1040s1a.pdf; IR-2026-28; CA FTB Announcement 2025-4.

### Child and Education Credits
| Credit | Amount | Notes |
|---|---|---|
| CTC per qualifying child | $2,200 | OBBBA §70104; phase-out $200k single / $400k MFJ |
| ACTC refundable cap | $1,700/child | 15% × (earned − $2,500) |
| ODC (other dependents) | $500/dep | IRC §24(h)(4); always through Sch 8812 L4b |
| AOTC max | $2,500 | 40% refundable ($1,000); first 4 years; half-time required; no drug conviction |
| Saver's credit (Form 8880) | Up to $1,000 | 50%/20%/10% tiers based on AGI |
| Charitable AGI floor (itemizers) | 0.5% of AGI | New per OBBBA; IRC §170 as amended |

### Education Credits
| Credit | Amount | Key rules |
|---|---|---|
| AOTC | $2,500 max | 40% refundable ($1,000 max); first 4 years only; half-time required; no drug conviction |
| LLC | 20% × up to $10,000 | No year limit; no enrollment requirement; nonrefundable only |
| LLC AGI phase-out | $85k–$105k single / $170k–$190k MFJ | Fully eliminated above top of range |

### Form 5329 Part I Line 2 Exception Codes
**FETCH_VERIFIED: irs.gov/pub/irs-pdf/i5329.pdf | Part I Line 2 | 2026-05-21**

| Code | Exception | Applies to |
|---|---|---|
| 01 | Separation from service age 55+ | Plans only — NOT IRAs |
| 02 | SEPP / Substantially equal periodic payments | IRA + Plans |
| 03 | Total and permanent disability | IRA + Plans |
| 04 | Death | IRA + Plans |
| 05 | Medical expenses > 7.5% AGI | IRA + Plans |
| 06 | QDRO (alternate payee) | Plans only |
| 07 | Health insurance while unemployed | IRA only |
| 08 | Higher education expenses | IRA only |
| 09 | First-home purchase, $10k lifetime | IRA only |
| 10 | Qualified reservist distributions | IRA + Plans |
| 11 | Qualified birth or adoption, $5k/child | IRA + Plans |
| 12 | Other / multiple (attach statement) | IRA + Plans |

### Retirement Accounts (TY 2025)
| Account | Limit | Catch-up (50+) |
|---|---|---|
| IRA (traditional/Roth) | $7,000 | +$1,000 |
| SEP-IRA | $70,000 | — |
| Solo 401(k) elective | $23,500 | +$7,500 |
| SIMPLE IRA | $16,500 | +$3,500 |
| HSA self-only | $4,300 | +$1,000 (55+) |
| HSA family | $8,550 | +$1,000 (55+) |

### Income Thresholds (TY 2025)
| Threshold | Single | MFJ |
|---|---|---|
| AMT exemption | $88,100 | $137,000 |
| AMT phaseout starts | $626,350 | $1,252,700 |
| QDCGT 0% ceiling | $47,025 | $94,050 |
| QDCGT 15% ceiling | $518,900 | $583,750 |
| QBI threshold | $197,300 | $394,600 |
| EITC invest income limit | $11,600 | — |
| IRA phaseout (covered) | $79k–$89k | $126k–$146k |
| IRA phaseout (noncovered MFJ) | — | $236k–$246k |

---

## Page 4 — Tax Year Constants (TY 2026)

*Source: Rev. Proc. 2025-32 · IR-2025-103 · OBBBA P.L. 119-21*

### Changes from TY 2025 → TY 2026

| Item | TY 2025 | TY 2026 | Note |
|---|---|---|---|
| Std ded — Single | $15,750 | $16,100 | |
| Std ded — MFJ | $31,500 | $32,200 | |
| Std ded — HOH | $23,625 | $24,150 | |
| Age-65 add-on — MFJ | $1,600 | $1,650 | |
| CTC per child | $2,200 | $2,300 | |
| ACTC cap | $1,700 | $1,800 | |
| Business mileage | 70¢/mile | 72.5¢/mile | IR-2025-128 |
| IRA limit | $7,000 | $7,500 | |
| IRA catch-up (50+) | +$1,000 | +$1,100 | |
| HSA self-only | $4,300 | $4,400 | |
| HSA family | $8,550 | $8,750 | |
| AMT phaseout — single | $626,350 | $500,000 | ⚠ lower |
| AMT phaseout — MFJ | $1,252,700 | $1,000,000 | ⚠ lower |
| QBI phase-in range — single | $50,000 | $75,000 | |
| QBI minimum deduction | $0 | $400 | new |
| EITC max (3+ children) | $8,046 | $8,231 | |

⚠ AMT phaseout is significantly lower in TY 2026 — more taxpayers may owe AMT.

---

## Page 5 — Filing Rules

### Rule 1 — OBBBA deductions are Form 1040 Line 13b (below-the-line; reduce taxable income, NOT AGI)
All four OBBBA deductions (senior, tips, OT, auto) flow through **Schedule 1-A → Form 1040 Line 13b**. `taxable = max(0, taxable − l13b_schedule1a)`. Do NOT add to `total_adjustments`. AGI is unaffected. CA does not conform — `obbba_total_federal` is added back in `compute_california_540()`. Source: f1040s1a.pdf; P.L. 119-21 §70103–70301; IR-2026-28; CA FTB Announcement 2025-4.

### Rule 1A — QBI §199A deduction is 1040 Line 13a (NOT Schedule 1; does NOT reduce AGI)
QBI goes on 1040 **Line 13a** — a below-the-line deduction that reduces taxable income via Line 14.
```
L11  AGI = total_income − Schedule 1 Part II adjustments
L12  Standard / itemized deduction
L13a QBI §199A (Form 8995 Line 15) — does NOT affect AGI
L14  = L12 + L13a + L13b (OBBBA)
L15  Taxable income = L11 − L14
```
Source: f1040.pdf Lines 11–15; f8995.pdf; IRC §199A.

### Rule 1B — IRA/pension distributions go on 1040 Lines 4b/5b (NOT Schedule 1)
`l4b` (IRA taxable) and `l5b` (pension taxable) go directly into `total_income`. They are NOT Schedule 1 Part I items and must NOT appear in `additional_income` (Line 8). Source: f1040.pdf Lines 4b, 5b, 8.

### Rule 1C — Form 1040 Lines 21-24 (exact per f1040.pdf)
```
L18  Add lines 16 and 17
L19  Child tax credit / ODC — Schedule 8812
L20  Schedule 3, line 8 (nonrefundable credits incl. education)
L21  Add lines 19 and 20
L22  Subtract line 21 from line 18 (if zero or less, enter -0-)
L23  Other taxes — Schedule 2, line 21 (SE tax, 5329, NIIT, etc.)
L24  Add lines 22 and 23 — This is your total tax
```
FETCH_VERIFIED: irs.gov/pub/irs-pdf/f1040.pdf | Page 2 Lines 18–24 | 2026-05-24

### Rule 1D — Form 8995 includes REIT/PTP component (Lines 6–9)
QBID = (20% × QBI component) + (20% × REIT/PTP component). L6 = qualified REIT dividends (1099-DIV Box 5 §199A) + qualified PTP income (K-1 §199A). L9 = 20% × L8. L10 = L3 + L9. L15 = min(L10, 20% × ordinary TI) → 1040 Line 13a. Do NOT skip Lines 6–9. Source: f8995.pdf; i8995.pdf Line 6; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24.

### Rule 2 — ODC routes through Sch 8812, never Sch 3
All dependents — qualifying children AND other qualifying dependents — route through Schedule 8812. L4a = children × CTC; L4b = other deps × $500 (ODC); L4c = pooled. L14 → 1040 L19. `sch3_l6d = 0` always. Source: f1040s8.pdf (2025); IRC §24(h)(4).

### Rule 3 — map_result() is a pass-through (never a translator)
`map_result()` starts with `dict(c)`. Every engine key is automatically in the output. Only add derived values and legacy aliases. Never enumerate individual engine keys.

### Rule 4 — EITC uses IRS $50-band table algorithm (not formula)
The IRS EIC Table uses discrete $50 bands. Credit is computed at `band = (int(lookup) // 50) * 50`. Formula approximations differ by $1–$100 per return. `requires_table_lookup` is always False — the band algorithm is filing-grade. Source: p1040.pdf pp.16+; IRC §32; Rev. Proc. 2024-40 §3.07.

### Rule 5 — safe_init() silently drops field name mismatches
Any field name difference between UI JSON and engine dataclass is dropped without error. The bridge audit (Page 9F) is the only safeguard. Every new form field must match the exact engine dataclass field name.

### Rule 6 — Form 2441 Line 6 deemed earned income
When MFJ spouse has $0 earned income but is a full-time student OR disabled, deemed income = $250/month (1 qualifying person) or $500/month (2+ persons) × months qualified. Source: f2441.pdf Line 6; IRC §21(d)(2).

### Rule 7 — AOTC eligibility gates (all three required)
(1) `box8_half_time=True` — at least half-time enrollment (hard gate). (2) `aoc_drug_conviction=False` — no federal/state drug conviction (hard gate). (3) `first_four_years=True` — cannot exceed 4 tax years total. Source: IRC §25A(b); i8863.pdf.

### Rule 8 — OBBBA tips occupation required (IRS Notice 2025-65)
Tip deduction requires a qualifying occupation from the IRS Notice 2025-65 list. Mandatory service charges are explicitly excluded (they are wages, not tips). Source: IRC §3121; Rev. Rul. 2012-18; Notice 2025-65.

### Rule 9 — OBBBA overtime must be FLSA-qualifying
Only time-and-a-half overtime qualifying under FLSA §207 counts. Bonuses, shift differentials, and exempt-employee extra pay do not qualify. Source: P.L. 119-21 §70202; FLSA §207(a)(1).

### Rule 10 — Capital gains special rates: §1250 (25%) and collectibles (28%)
Unrecaptured §1250 gain is taxed at max 25%. Collectibles gain is taxed at max 28%. Both reduce the pool subject to 0%/15%/20% rates. Source: IRC §1(h)(1)(D),(4); i1040sd.pdf Lines 18–19.

### Rule 11 — CA does not conform to OBBBA
CA Schedule CA must add back all four OBBBA deductions when computing CA AGI. Engine auto-computes: `obbba_total_federal` passed to `compute_california_540()`. Source: CA FTB Announcement 2025-4.

### Rule 12 — IRS-first before any calculation (EA audit requirement)
Before coding any new formula, limit, or rate: look it up on irs.gov first. Add `# Source: <form>.pdf <line>; <IRC §>` on the formula line. Never rely on training data for dollar amounts. See 9A and 9G.

**IRS source tiers (always prefer higher tier):**
| Tier | Source |
|---|---|
| 1 | IRS form/instruction PDF · IRS Pub · IRC § · Rev. Proc. · OBBBA § |
| 2 | IRS Notice / newsroom |
| ❌ | Training data memory — never for amounts/rates |

### Rule 13 — HOH requires a qualifying person (hard gate in UI)
`selFS('hoh')` is blocked when `S.deps.length === 0`. Alert shown. Engine also warns via soft gate for API mode. Source: IRC §2(b); Pub 501.

### Rule 14 — IRA spouse covered_by_plan from W-2 Box 13
`sp_covered = any(w.box13_retirement_plan for w in schema.w2s if w.for_spouse)`. Never hardcode False. When noncovered taxpayer / covered spouse: phaseout $236k–$246k (2025). Source: Pub 590-A WS 1-2; IRC §219(g)(7).

### Rule 15 — All IRS forms from irs.gov/forms-instructions only
No secondary sources (TurboTax, tax blogs, cached PDFs). Forms and instructions from https://www.irs.gov/forms-instructions only.

### Rule 16 — No taxpayer data to web without express approval
No taxpayer data (names, SSNs, income, etc.) sent to any external service without explicit user approval per session.

### Rule 17 — OBBBA senior deduction auto-populate
Enter taxpayer DOB in Taxpayer panel; UI auto-fills `tp-age-senior`. Engine applies $6,000 deduction per person ≥ 65 at year-end. MFS ineligible. MAGI phaseout: $75k single / $150k MFJ. Source: P.L. 119-21 §70103; OBBBA §70103; PARAMS_2025[`senior_deduction_amount`].

### Rule 18 — Cancelled debt (Form 1099-C)
`box2_discharged` → bridge → `box2_amount_discharged`. `is_excluded=False` → taxable on Sch 1 Line 8c. Form 982 required if insolvency/bankruptcy exclusion applies. Source: IRC §61(a)(12); IRC §108; i1099c.pdf.

### Rule 19 — SSA withholding → Line 25b
SSA-1099 `box6_vol_wh` → bridge → `box6_voluntary_wh` → `l25b_ssa_wh`. Never put SSA withholding on Line 25a (W-2 only). Source: f1040.pdf Line 25b; i1040.pdf.

### Rule 20 — Import/export round-trip integrity; spouse SSN dual-path
`buildSchema()` (export) and `populateFromSchema()` (import) must use identical key names. Verified by `test_ui_fields.js` 64-key round-trip. Spouse SSN stored in `schema.spouse.ssn` AND `schema.spouse_ssn` (top-level) for backward compatibility; travels as `TaxpayerSchema.spouse_ssn` through the engine, emits in `computed`, passes through `map_result()`, available to workpaper as `r.spouse_ssn`. *(Consolidates former Rule 23.)* 

### Rule 21 — EITC investment income limit (IRC §32(i))
Investment income for the §32(i) limit includes: interest + ordinary dividends + net capital gains + net positive rental income + passive K-1 ordinary income. 2025 limit: $11,600. Exceeding this limit disqualifies the entire EITC. Source: IRC §32(i)(1); p596.pdf.

### Rule 22 — Form 8606 separate per spouse
IRS requires a SEPARATE Form 8606 per spouse. Each spouse's pro-rata is computed independently on their OWN IRA balances. Never aggregate both spouses into one Form 8606. Source: i8606.pdf "Who Must File"; IRC §408(d)(2).

### Rule 23 — Alimony decree modification
Pre-2019 decree modified after 12/31/2018 WITH explicit §71 inapplicability clause → treated as post-2018 (no deduction, no income). Modification date controls, not original decree date. Source: IRC §11051(c); IRS Pub 504.

### Rule 24 — Home office simplified method cap
Simplified method ($5/sqft, max 300 sqft) cannot exceed gross income from business use of home. Cannot create a loss — any excess is carried forward. Source: Rev. Proc. 2013-13 §4.07; IRC §280A(c)(5).

### Rule 25 — NOL carryforward 80% limit
Post-TCJA NOL carryforward limited to 80% of taxable income per year. Indefinite carryforward. No carryback except farming losses. Field: `nol_carryforward_prior_year`. Source: IRC §172(a)(2); IRS Pub 536.

### Rule 26 — Every nested object must be in _SCALAR_NESTED
Any nested dataclass object passed in JSON must be registered in `_SCALAR_NESTED` in server.py, otherwise safe_init() receives a raw dict and crashes with AttributeError on first field access.

### Rule 27 — Always patch HTML with str_replace; never rewrite full file
Python `open/write` converts CRLF → LF across the entire file. Chromium v141 fails to parse template literals in LF-only files in some cases. Always use the `str_replace` tool for targeted HTML patches.

### Rule 28 — Always modify TaxReturn_PlanningReference.md; never create from scratch
Open the existing file and use str_replace for targeted updates. Creating from scratch silently drops the full changelog history, all rules, all patterns, and all bridge entries accumulated across sessions.

---

## Page 5A — Schedule C Rules

### Income placement
| Item | Line |
|---|---|
| All gross receipts (delivery, cash, tips, 1099-NEC Box 1) | **L1** |
| Returns and allowances | L2 |
| Cost of Goods Sold | L4 (Part III) |
| Other income (gasoline tax refund, §199A cooperative payments) | **L6** |
| Net profit → Schedule 1 L3 → 1040 L8 | L31 |

### Car expense
- Standard mileage: **70¢/mile** (TY 2025, IRS Notice 2025-5; Pub 463)
- Cannot combine standard rate + actual for same vehicle same year
- Requires contemporaneous mileage log (date, destination, business purpose, miles)
- Business travel (airfare, lodging) → Line 24a — separate from mileage

### 1099-NEC handling
- `nec_included_in_gross: true` (default) — preparer included NEC in gross receipts on L1
- `nec_included_in_gross: false` — engine auto-adds all 1099-NEC Box 1 to gross receipts
- Engine always emits verification warning when 1099-NEC income exists
- Do NOT enter NEC in both SE panel and Other Income panel (double-count)

### QBI §199A (Form 8995)
- **L1 QBI** = net profit − ½ SE tax − SE health insurance − SE retirement contributions
- **L6 REIT/PTP** = 1099-DIV Box 5 (§199A dividends) + K-1 §199A income
- **L9** = 20% × L8 REIT/PTP
- **L10** = L3 (QBI component) + L9 (REIT/PTP component)
- **L15 QBID** = min(L10, TI limit) → 1040 **Line 13a** (NOT Schedule 1; does NOT reduce AGI)
- Source: f8995.pdf; i8995.pdf; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24

---

## Page 6 — Forms Implemented

### Fully implemented ✅ (38 forms/schedules — updated V17.2)
Form 1040 all lines · Schedule 1 Part I+II (incl. L8h jury duty) · Schedule 1-A OBBBA · Schedule A · Schedule B · Schedule C · Schedule D/8949 · Schedule E/8582 · Schedule K-1 · Schedule SE · Schedule 8812 CTC/ACTC/ODC · Form 2441 (incl. Line 6 deemed income + age-13 gate) · Form 2210 (quarterly per-installment) · Form 4797 §1231/§1245/§1250 · Form 5329 (all codes) · Form 6251 AMT · Form 8606 (pro-rata, TP+SP, backdoor Roth) · Form 8615 Kiddie tax · Form 8863 AOTC+LLC · Form 8880 Saver's · Form 8889 HSA · Form 8959 Add'l Medicare · Form 8960 NIIT · Form 8962 PTC (incl. repayment cap) · Form 8995 QBI (incl. REIT L6–9) · Form 8995-A (above threshold scaffold) · Form 982 CoD exclusion · Form 1116 FTC · Pub 915 WS1 SS taxability · Pub 575 Simplified Method · OBBBA §70103–70301 · CA 540 (partial — see ⬜) · CalEITC/YCTC/FYTC · TY 2026 full PARAMS · EITC $50-band table · Cap gains 25%/28% rates · QCD §408(d)(8) · Form 8582 PAL §469

### Not yet implemented ⬜
| # | Priority | Item | Notes |
|---|---|---|---|
| 1 | HIGH | CA Schedule CA full line-by-line | Community property MFS, Form 3885 detail not done; use with caution |
| 2 | MEDIUM | CalEITC using W-2 Box 16/17 CA wages | Currently uses CA AGI proxy |
| 3 | MEDIUM | IRC §63(c)(5) dependent std ded limitation | $1,350 min / earned+$450 cap |
| 4 | MEDIUM | IRC §1211(b)(1) MFS capital loss $1,500 limit | Engine uses $3k for all statuses |
| 5 | MEDIUM | Form 8995-A above-threshold W-2 wage / SSTB detail | Scaffolded only |
| 6 | LOW | IRC §25B(c)(1) full-time student saver's credit disqualification | Known gap |
| 7 | LOW | QSS stale death year validation (2-year window) | Known gap |
| 8 | LOW | Sch 1 Line 24a jury pay deduction (when remitted to employer) | Known gap |
| 9 | LOW | K-1 outside basis computation | Warnings issued; basis not tracked multi-year |
| 10 | LOW | Form 8829 home office | Not implemented |
| 11 | LOW | AMT ISO/NQSO | Stock option AMT beyond $0 input |
| 12 | LOW | Non-CA state returns | Only CA 540 |
| 13 | LOW | §1231 5-year lookback auto-computation | Warning issued; reclassification not auto-applied |

---

## Page 7 — Known Structural Risks

| Severity | Risk | Mitigation |
|---|---|---|
| HIGH | CA Schedule CA incomplete | P1 partial: brackets/std ded/HOH/alimony/NOL/military fixed. Community property MFS, Form 3885 not done. Flag for all CA filers. |
| MEDIUM | safe_init() silent drops | Bridge audit (Page 9F) every session; _SCALAR_NESTED required for all nested objects |
| LOW | MFS cap loss $1,500 limit | Engine uses $3k single limit for MFS. IRC §1211(b)(1) known gap. |
| LOW | Dependent std ded limitation | IRC §63(c)(5) not implemented. Engine uses regular std ded. |
| LOW | Form 8995-A above threshold | Scaffolded; W-2 wage limit not complete for SSTB |
| LOW | K-1 basis/at-risk not enforced | ⚠ warnings issued on all losses; Form 6198 verification required |
| LOW | EITC band algorithm vs pre-computed table | Band algorithm matches table to within $1–$3 on most returns; acceptable for filing |

---

## Page 8 — Recurring Bug Patterns

### Pattern 1 — safe_init() silent drop
**Examples:** CoD always $0 · SSA WH $0 · Simplified Method never applied · books missing from AOTC · spouse fields dropped · unemployment flat scalar dropped · estimated_tax_payments raw dict crash
**Prevention:** Bridge audit (Page 9F) every session. Every nested object must be in `_SCALAR_NESTED`.

### Pattern 2 — Local var not in computed dict
**Examples:** `additional_income` $0 · `obbba_senior_deduction` not in result
**Prevention:** Every new computed value must be stored in `result["computed"]`. `map_result()` uses `dict(c)` — all keys automatic.

### Pattern 3 — UI import overwrites auto-computed value
**Examples:** Senior age blanked · spouse SSN lost on re-import
**Prevention:** `populateFromSchema()` only overrides if schema value is non-zero/non-null. `buildSchema()` derives from DOB if field blank.

### Pattern 4 — map_result() manual drift
**Example:** Engine keys missing from result → renderResult showed $0 for correct values
**Prevention:** `map_result()` now starts with `dict(c)`. Can never drift.

### Pattern 5 — Test helper uses __import__ inline
**Example:** `__import__('dataclasses').fields` inside function body → field not found
**Prevention:** Always use a module-level `si()` helper with `import dataclasses as _dc` at top of test block.

### Pattern 6 — Independent re-computation diverges from engine
**Example:** `compute_qbi_deduction()` re-derived net profit from raw schema, missing mileage ($1,750) and NEC ($1,000) already applied by `compute_schedule_c_se()`.
**Rule:** Never re-derive a value that another function already computed. Pass computed results as parameters.

### Pattern 7 — Template literal TypeError silently aborts innerHTML
**Example:** `r.qbi_detail.per_biz.map(...)` — if `r.qbi_detail` is undefined, TypeError aborts the entire innerHTML assignment. UI stays on "Loading result…" forever.
**Rule:** Pre-declare all sub-dicts at top of render(): `const _qbi = r.qbi_detail || {}`. Wrap render() in try/catch.

### Pattern 8 — localStorage cross-origin isolation
**Example:** Workpaper opened as `file://` never has data set by `localhost:5000`. localStorage is per-origin.
**Prevention:** Use embedded standalone workpaper or pass data via URL parameter / postMessage.

### Pattern 9 — qdcgt double-count of cap gain distributions
**Example:** `div_cap_gain_dist` was added to `qdcgt_income` separately despite already being in `net_ltcg_with_k1` (via Schedule D Line 13). When Schedule D net is negative, adding it back artificially reduces ordinary income taxed at bracket rates.
**Rule:** `qdcgt_income = qual_div + max(0, net_ltcg)`. Never add `div_cap_gain_dist` separately.

### Pattern 10 — Wrong 1040 line routing
**Examples:** IRA/pension in Sch1 instead of L4b/5b; QBI in Sch1 instead of L13a; OBBBA in AGI instead of L13b.
**Prevention:** Always look up the exact 1040 line in f1040.pdf before routing. Cite the line number in the code.

### Pattern 11 — Variable shadowing in template literals
**Example:** `map(r =>)` inside template literal shadows outer `r` → TypeError aborts innerHTML.
**Prevention:** Use distinct variable names. Pre-declare all computed values outside the template.

### Pattern 12 — Line ending conversion kills browser JS parse
**Example:** Python `open/write` converts CRLF → LF; Chromium v141 fails to parse template literals in the entire script block.
**Prevention:** Always patch HTML using `str_replace` tool. Never rewrite the full file via Python `f.write(html)`.

### Pattern 13 — Partial form implementation
**Example:** Form 8995 Lines 1–7 computed, Lines 6–9 (REIT/PTP) skipped entirely.
**Prevention:** Always implement all form lines. Check against the actual IRS form PDF.

### Pattern 14 — Planning Reference blank-page regression
**Example:** Writing TaxReturn_PlanningReference.md from scratch for a new version loses all prior content (full changelog history, all rules, all patterns, bridge table, priority list).
**Prevention:** Always open the existing file and use str_replace for targeted updates. Never create from scratch (Rule 27).

---

## Page 9 — Session Protocol

### 9A — Session start (required — all 6 steps before any work)

```
1. python3 sachintaxcare_test.py       → 593 PASS · 0 FAIL · 0 WARN
2. python3 test_vita_irs.py            → 212 PASS · 0 FAIL
3. Sync audit (9C)                     → 0 divergences
4. node test_ui_fields.js sachintaxcare_pro.html  → 404 PASS · 0 FAIL
5. IRS Citation Audit (9G)             → 40/40 cited · 0 uncited
6. Then begin work
```

**STOP GATE before writing any new calculation code:**
> Before coding any new tax rule, formula, or limit — look it up on irs.gov first.
> Primary sources only: IRS form PDFs, instructions, publications, Rev. Proc., IRC sections, OBBBA §.
> Add the citation as `# Source: <form>.pdf <line>; IRC §X` on the formula line.
> Never rely on training data for dollar amounts — they change annually.

**IRS source tiers (always prefer higher tier):**
| Tier | Source |
|---|---|
| 1 | IRS form/instruction PDF · IRS Pub · IRC § · Rev. Proc. · OBBBA § |
| 2 | IRS Notice / newsroom |
| ❌ | Training data memory — never for amounts/rates |

### 9B — Session end (required)
1. Run `python3 sachintaxcare_test.py` → 0 failures
2. Run `python3 test_vita_irs.py` → 0 failures
3. Run `node test_ui_fields.js sachintaxcare_pro.html` → 0 failures
4. Update Page 1 file registry with new line counts and version notes
5. Add entry to Page 1A changelog (what changed and why)
6. Update Page 6 ⬜ list if any gaps resolved or added
7. Update Page 10 priorities (mark completed, add new)
8. Copy all changed files to /mnt/user-data/outputs/
9. Update this document via str_replace — never rewrite from scratch (Rule 27)

### 9C — Sync Audit (paste into python3)

```python
import sachintaxcare_engine as e

p25 = e.PARAMS_2025; p26 = e.PARAMS_2026
checks = [
    # TY 2025 key values
    ("P25 std_ded MFJ",        p25["std_deduction"]["mfj"],              31500),
    ("P25 std_ded single",     p25["std_deduction"]["single"],           15750),
    ("P25 ctc_per_child",      p25["ctc_per_child"],                     2200),
    ("P25 actc_cap",           p25["actc_cap_per_child"],                1700),
    ("P25 senior_ded",         p25["senior_deduction_amount"],           6000),
    ("P25 tip_max",            p25["tip_deduction_max"],                 25000),
    ("P25 ot_max_mfj",         p25["overtime_deduction_max_mfj"],        25000),
    ("P25 ira_limit",          p25["ira_contribution_limit_2025"],       7000),
    ("P25 hsa_self",           p25["hsa_limit_self_only_2025"],          4300),
    ("P25 amt_ex_single",      p25["amt_exemption_single"],              88100),
    ("P25 amt_po_single",      p25["amt_phaseout_single"],               626350),
    ("P25 qbi_threshold_mfj",  p25["qbi_threshold_mfj"],                394600),
    ("P25 eitc_invest_limit",  p25["eitc_investment_income_limit"],      11600),
    ("P25 ca_std_single",      p25["ca_std_ded_single"],                 5706),
    ("P25 ca_std_mfj",         p25["ca_std_ded_mfj"],                   11412),
    ("P25 mileage_biz",        p25["mileage_rate_business"],             0.70),
    # TY 2026 key values
    ("P26 std_ded MFJ",        p26["std_deduction"]["mfj"],              32200),
    ("P26 ctc_per_child",      p26["ctc_per_child"],                     2300),
    ("P26 ira_limit",          p26["ira_limit_2026"],                    7500),
    ("P26 hsa_self",           p26["hsa_self_only_2026"],                4400),
    ("P26 amt_po_single",      p26["amt_phaseout_single"],               500000),
    ("P26 qbi_min",            p26["qbi_min_deduction"],                 400),
]
ok = True
for label, got, exp in checks:
    if got != exp:
        print(f"  DIVERGE {label}: got={got} expected={exp}")
        ok = False
if ok:
    print(f"  ✅ All {len(checks)} PARAMS checks pass — 0 divergences")
```

### 9D — Adding a new engine field (checklist)
1. Add field to the appropriate dataclass with type annotation and default value
2. Add `# Source: <IRS form/IRC>` comment inline
3. If a nested object: add to `_SCALAR_NESTED` in sachintaxcare_server.py (Rule 25)
4. Add field to UI HTML with correct `id`
5. Wire field in `buildSchema()` using `v()` or `n()`
6. Wire field in `populateFromSchema()` for import
7. If field name differs between UI and dataclass, add to bridge table (server.py + Page 2)
8. Add test assertion in test suite
9. Run 9A gates — 0 failures required
10. Update Page 1 registry and Page 1A changelog

### 9E — Adding a new compute function (checklist)
1. Define `compute_X()` with `# Source: <IRS form>` in docstring
2. Add at least one IRS citation inside the function body on every formula line
3. Call from `run()` with appropriate params at correct position in 14-step order
4. Store result in `result["computed"]` (or sub-dict)
5. Add test assertions — both unit (Layer 3) and pipeline (Layer 2)
6. Run 9G citation audit → 0 uncited
7. Run 9A gates → 0 failures

### 9F — Bridge Audit Protocol (run at session start — step 5 of 9A)

```python
import sachintaxcare_engine as e, dataclasses as dc

BRIDGE_TARGETS = [
    (e.Form1099C,            "box2_amount_discharged"),
    (e.Form1099C,            "is_excluded"),
    (e.FormSSA1099,          "box6_voluntary_wh"),
    (e.Form1099R,            "box9b_employee_contribs"),
    (e.W2,                   "box5_med_wages"),
    (e.Form1098T,            "box8_half_time"),
    (e.Form1098T,            "aoc_drug_conviction"),
    (e.Form1098T,            "box9_graduate"),
    (e.TaxpayerSchema,       "spouse_ssn"),
    (e.TaxpayerSchema,       "spouse_first"),
    (e.TaxpayerSchema,       "spouse_last"),
    (e.TaxpayerSchema,       "spouse_dob"),
    (e.TaxpayerSchema,       "tip_occupation"),
    (e.TaxpayerSchema,       "overtime_flsa_confirmed"),
    (e.TaxpayerSchema,       "care_spouse_is_student"),
    (e.TaxpayerSchema,       "care_spouse_is_disabled"),
    (e.TaxpayerSchema,       "care_spouse_months_qualified"),
    (e.TaxpayerSchema,       "prior_sec1231_losses_5yr"),
    (e.TaxpayerSchema,       "jury_duty_income"),
    (e.TaxpayerSchema,       "prize_award_income"),
    (e.CaliforniaData,       "ca_alimony_addback"),
    (e.CaliforniaData,       "ca_nol_addback"),
    (e.EstimatedTaxPayments, "q1"),
    (e.SimplifiedMethodData, "age_at_annuity_start"),
    (e.SimplifiedMethodData, "prior_year_tax_free_recovered"),
    (e.SimplifiedMethodData, "annuity_start_after_nov_18_1996"),
    (e.Form1099DIV,          "box2a_cap_gain_dist"),
    (e.Form5329Exception,    "distribution_amount"),
    (e.Form1099INT,          "box6_foreign_tax"),
    (e.ScheduleC,            "nec_included_in_gross"),
    (e.ScheduleC,            "business_code"),
    (e.ScheduleC,            "business_miles"),
    (e.Form1099INT,          "payer_ein"),
]
all_ok = True
for cls, field in BRIDGE_TARGETS:
    fields = {f.name for f in dc.fields(cls)}
    if field not in fields:
        print(f"  ❌ BRIDGE MISSING: {cls.__name__}.{field}")
        all_ok = False
if all_ok:
    print(f"  ✅ All {len(BRIDGE_TARGETS)} bridge target fields present")
```

### 9G — IRS Citation Audit (run at session start — step 5 of 9A)

```python
import re

engine = open('sachintaxcare_engine.py').read()
lines  = engine.split('\n')

SOURCE_PATTERN = re.compile(
    r'(irs\.gov|IRC\s*§|Rev\.\s*Proc\.|P\.L\.\s*\d+|f\d{4}|i\d{4}|pub\d+|'
    r'Pub\.\s*\d+|f1040|i8863|i1040|OBBBA\s*§|Notice\s*\d{4}|IR-\d{4}|ftb\.ca\.gov)',
    re.IGNORECASE)
COMPUTE_FN = re.compile(r'^def (compute_\w+)\(')

fns = {}; current = None; body_start = None
for i, line in enumerate(lines):
    m = COMPUTE_FN.match(line)
    if m:
        if current and body_start is not None:
            body = '\n'.join(lines[body_start:i])
            fns[current] = len(SOURCE_PATTERN.findall(body))
        current = m.group(1); body_start = i
if current and body_start is not None:
    fns[current] = len(SOURCE_PATTERN.findall('\n'.join(lines[body_start:])))

uncited     = [fn for fn, n in fns.items() if n == 0]
total_fns   = len(fns); cited_fns = total_fns - len(uncited)
params_blks = re.findall(r'PARAMS_\d{4}\s*=\s*\{[^}]{200,}?\}', engine, re.DOTALL)
params_src  = sum(1 for b in params_blks if SOURCE_PATTERN.search(b))
total_cites = len(SOURCE_PATTERN.findall(engine))

print(f'\n{"="*60}')
print(f'  9G IRS CITATION AUDIT')
print(f'{"="*60}')
print(f'  Total IRS citations:            {total_cites:>5}')
print(f'  Compute functions with source:  {cited_fns:>3}/{total_fns}')
print(f'  PARAMS blocks sourced:          {params_src:>3}/{len(params_blks)}')
if uncited:
    print(f'\n  ❌ Uncited functions:')
    for fn in uncited: print(f'     {fn}()')
else:
    print(f'\n  ✅ All compute functions have IRS citations')
print(f'{"="*60}')
```

---

## Page 10 — Session Priorities

| # | Status | Priority | Item | Notes |
|---|---|---|---|---|
| 1 | ✅ V17.2 | — | CA Schedule CA brackets/HOH/alimony/NOL | ftb.ca.gov/forms/2025/2025-540.pdf FETCH_VERIFIED |
| 2 | ✅ V17.2 | — | Form 2210 quarterly per-installment | i2210.pdf Part III |
| 3 | ✅ V17.2 | — | Jury duty income Sch 1 Line 8h | f1040s1.pdf L8h |
| 4 | ✅ V17 | — | EITC $50-band table algorithm | Filing-grade confirmed |
| 5 | ✅ V17 | — | Form 2210 annual rate | Replaced by quarterly in V17.2 |
| 6 | 🔲 | HIGH | CA Schedule CA full line-by-line | Community property MFS, Form 3885 |
| 7 | 🔲 | MEDIUM | CalEITC using W-2 Box 16/17 CA wages | Currently uses CA AGI proxy |
| 8 | 🔲 | MEDIUM | IRC §63(c)(5) dependent std ded limitation | $1,350 min / earned+$450 |
| 9 | 🔲 | MEDIUM | IRC §1211(b)(1) MFS capital loss $1,500 | Engine uses $3k |
| 10 | 🔲 | MEDIUM | Form 8995-A above-threshold SSTB W-2 | Scaffolded only |
| 11 | 🔲 | LOW | IRC §25B(c)(1) student saver's credit | Known gap |
| 12 | 🔲 | LOW | QSS stale death year validation | 2-year window |
| 13 | 🔲 | LOW | Sch 1 Line 24a jury pay deduction | When remitted to employer |
| 14 | 🔲 | LOW | §1231 5-year lookback auto-computation | Warning issued; reclassification not applied |
| 15 | 🔲 | LOW | Form 2441 Line 6 workpaper display | Deemed income calc not shown on workpaper |
| 16 | 🔲 | LOW | K-1 outside basis multi-year | Warnings issued; tracking not implemented |
| 17 | 🔲 | LOW | Form 8829 home office actual-expense | Not implemented |
| 18 | 🔲 | LOW | 1099-INT Box 9 PAB → AMT verify | Low impact |
| 19 | 🔲 | LOW | Schedule B Line 3 Treasury bond premium | Display only |
| 20 | 🔲 | LOW | Schedule C Part III COGS workpaper display | Product-based businesses |

---

## Appendix A — Why Calculation Mistakes Happen

1. **safe_init() silent drop** — field name mismatch between UI JSON and dataclass → silently $0
2. **Local var not in computed dict** — engine computes correctly but value not stored in result
3. **UI import overwrites auto-compute** — `populateFromSchema()` overwrites a value the engine derives
4. **map_result() manual drift** — manually listed keys diverge from engine; fixed permanently by `dict(c)` pass-through
5. **Test helper inline __import__** — `__import__('dataclasses').fields` inside function → field not found
6. **Round-trip not tested** — new field in buildSchema but not ROUND_TRIP_CHECKS → import breaks silently
7. **Wrong layer diagnosis** — "not in export" interpreted as result dict missing, not populateFromSchema missing
8. **Wrong IRS rate from memory** — FETCH_VERIFIED protocol prevents this
9. **Wrong 1040 line routing** — IRA/pension in Sch1 instead of L4b; QBI in Sch1 instead of L13a; OBBBA reducing AGI instead of L13b
10. **Variable shadowing** — `map(r =>)` inside template literal shadows outer `r` → TypeError aborts innerHTML
11. **localStorage cross-origin** — workpaper as file:// never has data from localhost:5000
12. **Independent re-computation** — `compute_qbi_deduction()` re-derived net profit from schema, missing mileage/NEC. Fixed: pass computed value from run()
13. **Partial form implementation** — Form 8995 Lines 1–7 computed, Lines 6–9 (REIT/PTP) skipped. Always implement all form lines
14. **Planning Reference blank-page regression** — creating from scratch loses full changelog, all rules, all patterns. Always modify existing file (Rule 27)

---

*Updated: 2026-05-26 · Version V17.4*
*IRS sources: irs.gov/pub/irs-pdf/ · IRS Pub 463 (2025) · IRS Notice 2025-5 · IRS Notice 2025-65 · IRS Notice 2025-67 · Rev. Proc. 2024-40 · Rev. Proc. 2025-32 · IR-2025-103 · IR-2025-128 · IR-2026-28 · P.L. 119-21 (OBBBA) · f8995.pdf · i8995.pdf · i5329.pdf · i2210.pdf · f1040.pdf · f1040s1.pdf · f1040s1a.pdf · f982.pdf · ftb.ca.gov/forms/2025/ · IRC §21, §24, §25A, §32, §63, §85, §86, §108, §163, §164, §170, §199A, §219, §221, §408(d)(8), §465, §469, §704, §1211, §1231, §1250, §1401 · IRS Pub 463, 503, 575, 596, 915, 939, 1001*
