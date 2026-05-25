# SachinTaxCare — Tax Return Planning Reference
*Last updated: 2026-05-24 · **Version V17** · All dollar values from `PARAMS_2025` / `PARAMS_2026` in engine.*
*IRS source authority: irs.gov/forms-instructions only (per Rules 15, 16, 9A, 9G). No taxpayer data to web without approval (Rule 16). Rules 1–28 on Page 5.*

---

## How to use this document

Single source of truth for every tax constant, rule, bridge mapping, test gate, and session protocol.
**Before any session:** run all four gates in 9A. Zero failures required before any changes.

---

## Page 1 — File Registry

| File | Lines | Version | Role |
|---|---|---|---|
| `sachintaxcare_engine.py` | **8781** | v17 — mileage 70¢, QBI L13a+L6 REIT, l4b routing, qdcgt fix, L21-L24 labels; +qbi_min alias | Computation engine (TY 2025 + TY 2026) |
| `sachintaxcare_pro.html` | **4,800** | v7 — NEC inclusion, nec_included_in_gross, int-ein, 1098-E restore, L16-L24 panel | Primary UI — intake + results |
| `sachintaxcare_server.py` | **761** | v16 — map_result() pass-through | Flask server + bridge |
| `sachintaxcare_workpaper.html` | **1,670** | v8 — 18 pages, try/catch, pre-declared sub-dicts, QBI L13a, Sch C summary | CPA workpaper |
| `sachintaxcare_test.py` | **2,528** | v4.1 — 584 PASS · 0 FAIL · 4 WARN | Regression suite |
| `test_vita_irs.py` | 2,551 | v12-fork + 14.3/4.4/32.2b/32.4b/32.13b fixes | VITA known-answer tests — **145/145** |
| `test_ui_fields.js` | 815 | v2.0 — 64 round-trip keys | UI field completeness — 64 keys |
| `sachintaxcare_pdf.py` | 367 | v1.0 | PDF output (reportlab) |
| `sachintaxcare_report.py` | 965 | v11 | JSON verification report |
| `test_report.py` | 415 | v1 | Report verification tests |
| `sachintaxcare_field_manifest.md` | 1021 | v1.3 | Field registry |
| `IMPLEMENTATION_GUIDE.md` | 330 | V17.1 | How to rebuild from scratch |
| `ENGINE_ALGORITHM.md` | 604 | V17.1 | Engine computation flow |
| `sachintaxcare_schema_2025.json` | 276 | v1 | JSON schema reference |

**Session start gate:** `python3 sachintaxcare_test.py` → **584 PASS · 0 FAIL · 4 WARN**

---

## Page 1A — Changelog (most recent first)

### Session 2026-05-24 — **V17.1** — Session-start divergence fixes (7 items)

| Fix | Item | What changed |
|---|---|---|
| Test 14.3 | `test_vita_irs.py` line 517 — code `02` (SEPP) incorrectly asserted as IRA-invalid | Changed exception_code to `'01'` (age-55 separation, plan-only per i5329.pdf). Code 02 (SEPP §72(t)(2)(A)(iv)) is valid for both IRAs and employer plans. Source: i5329.pdf Line 2; IRC §72(t)(2)(A)(iv)/(v) |
| Test 4.4 | ODC tested on `sch3['l6d_odc']` (always 0 per Rule 2) | Fixed to `s8812['odc_total']`. Rule 2: ODC routes through Sch 8812, never sch3. Source: f1040s8.pdf; IRC §24(h)(4) |
| Tests 32.2b/32.4b/32.13b | OBBBA deductions tested as AGI reductions (V16 behavior) | Updated to test `taxable_income` — OBBBA is L13b below-the-line per V17 Rule 1. Expected values: 32.2b→$36,250; 32.4b→$44,250; 32.13b→$59,250. Each appears twice in file (both fixed). |
| `qbi_min` alias | `PARAMS_2026['qbi_min']` KeyError — key was named `qbi_min_deduction` only | Added `"qbi_min": 400` alias alongside `qbi_min_deduction` in PARAMS_2026 |
| File registry | Page 1 line counts off by −1 on 5 files; Page 2 citation count stale | Corrected all counts; citations 1,521 → 1,606 |

---

### Session 2026-05-24 — **V17** — IRS compliance, Form 8995 REIT, QBI routing, 1040 L16-L24

**Engine metrics after this session:**
- Compute functions: 42 (was 41)
- Dataclasses: 40 · Schema fields: 515+
- IRS citations: 1,521 (was 1,331)
- FETCH_VERIFIED annotations: 13
- Round-trip keys: 64 (was 47)
- Test suite: 586 PASS · 0 FAIL · 7 WARN (was 528 PASS)

| Fix | Severity | Item | What changed |
|---|---|---|---|
| Mileage rate | CRIT | 67¢ → **70¢/mile** | IRS Pub 463 (2025); Notice 2025-5; FETCH_VERIFIED 2026-05-24 |
| QBI on L13a | CRIT | QBI was reducing AGI (wrong) | Removed from `total_adjustments`; applied to `taxable_income` via `taxable − adj_qbi`. Source: f1040.pdf L13a; IRC §199A |
| l4b routing | CRIT | IRA/pension in Sch1 L10 (wrong) | Removed from `additional_income`; added to `total_income_pre_ss`. Line 8: $12,250 → $7,250. Source: f1040.pdf Lines 4b, 5b, 8 |
| Form 8995 L6 | CRIT | REIT/PTP component missing entirely | 1099-DIV Box 5 §199A divs × 20% = $6. QBID: $1,334 → **$1,340**. Source: f8995.pdf Lines 6-9; i8995.pdf Line 6; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24 |
| QBI base | CRIT | compute_qbi_deduction re-derived net profit from raw schema, missing mileage ($1,750) and NEC ($1,000) | Now accepts `se_net_profit` from `run()` directly. QBI base: $7,925 → $7,175 |
| qdcgt double-count | HIGH | div_cap_gain_dist added to qdcgt separately despite already being in Schedule D net | When net cap ≤ 0, distribution is absorbed. `qdcgt = qual_div + max(0, net_ltcg)`. Line 16: $3,866 → $3,908. Source: f1040.pdf QDCGT Worksheet |
| 1040 L21-L24 labels | HIGH | L21 was "Tax after credits" (wrong) | L21=Add L19+L20; L22=Subtract L21 from L18; L23=Other taxes (Sch2 L21); L24=Add L22+L23. Source: f1040.pdf Lines 21-24; FETCH_VERIFIED 2026-05-24 |
| Education credit | HIGH | Credit shown after L24 total tax (wrong per 1040 form order) | Credits (L19, L20) now before L24 in both result panel and workpaper |
| 1099-B import | HIGH | cost_basis → wrong field; is_long_term/basis_reported_to_irs used wrong keys | Fixed in populateFromSchema. Added to bridge table |
| 1098-E import | HIGH | No restore loop — 1098-E entries not importable | Restore loop added: `addF1098E()` per entry |
| Workpaper loading | MED | TypeError on undefined sub-dicts → "Loading result…" forever | Six sub-dicts pre-declared; render() wrapped in try/catch |
| Round-trip | MED | 47 → 64 keys | schedule_cs, form_1099ints, form_5329_exceptions, form_1099divs sections added |
| 1099-B bridge | MED | box2a_total_cap_gain, Form5329Exception amount/account_type silent drops | Alias fields added to bridge table; populateFromSchema fixed |
| Workpaper Sch C | MED | Page D missing net profit calculation summary and mileage detail | Added "Net Profit Calculation Summary" box; mileage detail line |

### Session 2026-05-22/23 — Schedule D, sch1/sch2/sch3 export, workpaper expansion

| Fix | Item |
|---|---|
| Schedule D double-count | Box C (ST noncovered) was in both `box_c_rows` AND ST accumulators; fixed |
| 1099-DIV box2a alias | `box2a_total_cap_gain` JSON key vs `box2a_cap_gain_dist` engine field — alias added |
| Form 5329 amount/account_type | Alias fields added to Form5329Exception |
| sch1/sch2/sch3 sub-dicts | Exported from computed dict; used by workpaper |
| LLC fallback from AOC | All three AOC denial gates (4-year, drug conviction, half-time) now fall through to LLC |
| Workpaper Pages A–G | W-2 summary, Schedule B, Schedule D/8949, Schedule C detail, 1099-R/5329, Form 8962, Form 2441 |
| Education credit on L20 | Credits shown before total tax; workpaper fixed |

### Session 2026-05-18 — C2, M1–M6, EA audit critical/high fixes

**Engine metrics after this session:**
- Compute functions: 41 (was 39)
- Dataclasses: 38 · Schema fields: 510 (was 499)
- IRS citations: 1,331 (was 1,203)
- 9G audit: 39/39 cited · 0 uncited

| Fix | Item | What changed |
|---|---|---|
| C1 | EITC exact table | `compute_eitc()` rewritten — IRS $50-band algorithm; `requires_table_lookup` always False; `phase_in_rates` added to both PARAMS |
| C2 | Form 2441 deemed earned income | `care_spouse_is_student`, `care_spouse_is_disabled`, `care_spouse_months_qualified` on schema; f2441.pdf Line 6 logic; UI dropdown + months field |
| C3 | OBBBA tips occupation | 30-occupation dropdown (IRS Notice 2025-65); `tip_occupation` field; engine validates; mandatory service charges explicitly excluded |
| H1 | Cap gains §1250/28% | `unrecaptured_sec1250` and `collectibles_gain` params added to `compute_qdcgt_tax()`; both reduce the 0%/15%/20% pool |
| H3 | At-risk Form 6198 | ⚠ warnings on rental_net < 0 and k1_ordinary/k1_rental < 0 citing IRC §465 and §704(d) |
| H4a | AOTC half-time gate | Hard gate: `box8_half_time=False` → AOTC = $0 |
| H4b | AOTC drug conviction | Hard gate: `aoc_drug_conviction=True` → AOTC = $0; new field on Form1098T + UI select |
| H6 | HOH hard gate | `selFS('hoh')` blocked with alert if `S.deps.length === 0`; engine soft warning retained for API mode |
| IRA sp_covered | Spouse 401k → IRA phaseout | `sp_covered = any(w.box13_retirement_plan for w in schema.w2s if w.for_spouse)` |
| M1/M6 | OBBBA overtime FLSA | `overtime_flsa_confirmed: bool` on schema; ⚠ warning when False; UI checkbox with disclosure text |
| M3 | CA Schedule CA | `obbba_total_federal` auto-addback; `ca_bonus_depreciation_addback`; military pay exclusion; loan forgiveness; CaliforniaData expanded |
| M4 | §1231 5-year lookback | `prior_sec1231_losses_5yr: float` on TaxpayerSchema; passed to `compute_form_4797`; warning emitted even without Form 4797 sales |
| M5 | Estimated tax prior-year | ⚠ warning when `form_2210.prior_year_tax == 0` and `l37_owe > 500` or estimated payments made |

### Session 2026-05-17 — Willis workpaper bugs (5 fixed)

| Bug | Root cause | Fix |
|---|---|---|
| OBBBA senior ded not in L10 | `agi = agi - obbba_total` was separate post-AGI step | `total_adjustments += obbba_total`; `agi = total_income - total_adjustments` *(superseded by V17: OBBBA moved to L13b below-the-line; now reduces taxable income, not AGI)* |
| L25b missing SSA WH | `l25b_ssa_wh` stored but not summed into `l25b_total` | Workpaper shows breakdown: "1099-R: $X + SSA Box 6: $Y" |
| ODC on Sch 3 L6d (wrong) | ODC routed to `sch3_l6d` instead of Sch 8812 | `l12_8812 = ctc_total + odc_total`; `sch3_l6d = 0` always |
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
L8   Additional income = Schedule 1 Part I total (SE, rental, unemployment…)
    IRA/pension (L4b/L5b) → go directly to total_income — NOT through Sch 1
L11  AGI = total_income − total_adjustments
    total_adjustments = Schedule 1 Part II (above-the-line):
    SE deduction + student loan + IRA + teacher + SE health + HSA
    QBI is NOT in total_adjustments
L12  Standard deduction (or itemized)
L13a QBI §199A deduction (Form 8995 L15) — below-the-line, does NOT reduce AGI
L13b OBBBA Schedule 1-A (tips, overtime, auto loan, senior) — below-the-line
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
L6   Qualified REIT dividends (1099-DIV Box 5 §199A divs) + qualified PTP income
L8   Total REIT/PTP = L6 + carryforward
L9   REIT/PTP component = 20% × L8
L10  Combined = L3 + L9
L11  TI limit = 20% × L5
L15  QBID = min(L10, L11) → 1040 Line 13a
Source: f8995.pdf; i8995.pdf; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24
```

### map_result() architecture rule (permanent — Rule 24)
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
| `box8_at_least_half_time` | `box8_half_time` | Form1098T | 2026-05-17 |
| `spouse{ssn,first,last,dob}` | `spouse_ssn/first/last/dob` | TaxpayerSchema | 2026-05-17 |
| `age_at_start` | `age_at_annuity_start` | SimplifiedMethodData | 2026-05-16 |
| `prior_tax_free_recovered` | `prior_year_tax_free_recovered` | SimplifiedMethodData | 2026-05-16 |
| `box2a_total_cap_gain` | `box2a_cap_gain_dist` | Form1099DIV | 2026-05-22 |
| `amount` | `distribution_amount` | Form5329Exception | 2026-05-21 |
| `account_type` | `plan_type` | Form5329Exception | 2026-05-21 |
| `cost_basis` → `sale-cost-` (wrong UI field) | → `sale-basis-` | UI 1099-B import | 2026-05-24 |
| `is_long_term` → `b.term` (wrong key) | → `b.is_long_term` | UI 1099-B import | 2026-05-24 |
| `basis_reported_to_irs` → `b.basis_reported` | → `b.basis_reported_to_irs` | UI 1099-B import | 2026-05-24 |

### Engine internals (current)
- **Compute functions:** 42
- **Dataclasses:** 40 · **Schema fields:** 515+
- **Computed keys emitted:** 155+ (all via dict(c) pass-through)
- **IRS citations:** 1,606
- **FETCH_VERIFIED annotations:** 13
- **PARAMS_2025 constants:** 131 scalar · **PARAMS_2026:** 150 scalar (incl. `qbi_min` alias)
- **Round-trip keys tested:** 64
- **TY 2025 + TY 2026 fully parametrized** — every constant keyed by year

---

## Page 3 — Tax Year Constants (TY 2025)

Source: Rev. Proc. 2024-40 · OBBBA P.L. 119-21 · IRS Notice 2025-5

### Standard Deductions (IRC §63)
| Status | Amount | Age-65/blind add-on |
|---|---|---|
| Single / MFS | $15,750 | +$2,000/condition |
| MFJ / QSS | $31,500 | +$1,600/qualifying spouse |
| HOH | $23,625 | +$2,000/condition |

Source: Rev. Proc. 2024-40 · OBBBA P.L. 119-21 signed 2025-07-04 · IRS Notice 2025-5 (mileage 70¢)

### Mileage Rates (TY 2025)
| Purpose | Rate | Source |
|---|---|---|
| **Business** | **70¢/mile** | IRS Notice 2025-5; IRS Pub 463 (2025); FETCH_VERIFIED 2026-05-24 |
| Medical / moving | 21¢/mile | IRS Notice 2025-5 |
| Charitable | 14¢/mile | IRC §170(i) |

> **TY 2026:** 72.5¢/mile business (IR-2025-128, effective Jan 1, 2026)

### Standard Deductions (IRC §63)
| Status | Std ded | Age-65 add-on |
|---|---|---|
| Single / MFS | $15,750 | +$2,000/condition |
| MFJ | $31,500 | +$1,600/qualifying spouse |
| HOH | $23,625 | +$2,000/condition |

### OBBBA Above-Line Deductions (Sch 1 Part II; TY 2025–2028)
| Provision | Cap | Phaseout starts |
|---|---|---|
| Senior bonus §70103 (age ≥65) | $6,000/person | $75k single / $150k MFJ |
| Qualified tips §70201 | $25,000 | $150k single / $300k MFJ |
| FLSA overtime §70202 | $12,500 single / $25,000 MFJ | $150k / $300k |
| Auto loan interest §70301 | $10,000 | $100k single / $200k MFJ |
| SALT cap §70106 | $40,000 (MFJ) | Phase-down above $500k AGI |

All four OBBBA deductions are Schedule 1 Part II adjustments → 1040 Line 10 → reduce AGI. CA did NOT conform (see M3).

### Child and Education Credits
| Credit | Amount | Notes |
|---|---|---|
| CTC per qualifying child | $2,200 | OBBBA §70104; phaseout $400k/$200k |
| ACTC refundable cap | $1,700/child | 15% × (earned − $2,500) |
| ODC (other dependents) | $500/dep | IRC §24(h)(4); through Sch 8812 L4b |
| AOTC max | $2,500 | 40% refundable ($1,000); first 4 years; half-time required; no drug conviction |
| Saver's credit | up to $1,000 | 50%/20%/10% based on AGI |

### Education Credits
| Credit | Amount | Key rules |
|---|---|---|
| AOTC | $2,500 max | 40% refundable ($1,000); first 4 years only; half-time required; no drug conviction |
| LLC | 20% × up to $10,000 | **No year limit; no enrollment requirement;** nonrefundable only |
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

Source: Rev. Proc. 2025-32 · IR-2025-103 · OBBBA P.L. 119-21

### Changes from TY 2025 → TY 2026

| Item | TY 2025 | TY 2026 | ⚠ |
|---|---|---|---|
| Std ded — Single | $15,750 | $16,100 | |
| Std ded — MFJ | $31,500 | $32,200 | |
| Age-65 add-on — MFJ | $1,600 | $1,650 | |
| CTC per child | $2,200 | $2,300 | |
| ACTC cap | $1,700 | $1,800 | |
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

### Rule 1 — OBBBA deductions are Form 1040 Line 13b (below-the-line; NOT Schedule 1 Part II)
All four OBBBA deductions (senior, tips, OT, auto) flow through **Schedule 1-A → Form 1040 Line 13b**. They reduce taxable income, NOT AGI. `taxable = max(0, taxable - l13b_schedule1a)`. Do NOT add to `total_adjustments`. AGI is unaffected. V17 fix (2026-05-24): OBBBA removed from `total_adjustments` and applied post-deduction at Line 13b. CA does not conform — see Rule 11. Source: f1040s1a.pdf; P.L. 119-21 §70103–70301; IR-2026-28.

> ⚠ **V16 note (now obsolete):** Rule 1 previously said OBBBA was Schedule 1 Part II above-the-line. That was incorrect. Tests 32.2b/32.4b/32.13b in test_vita_irs.py have been updated to reflect the correct below-the-line behavior.

### Rule 2 — ODC routes through Sch 8812, never Sch 3
All dependents — qualifying children AND other qualifying dependents — route through Schedule 8812. L4a = children × CTC; L4b = other deps × $500 (ODC); L4c = pooled. L14 → 1040 L19. `sch3_l6d = 0` always. Source: f1040s8.pdf (2025); IRC §24(h)(4).

### Rule 1A — QBI §199A deduction is 1040 Line 13a (NOT Schedule 1)
QBI goes on 1040 **Line 13a** — it is a below-the-line deduction. It does NOT reduce AGI. It reduces taxable income via Line 14.
```
L11  AGI = total_income − Schedule 1 Part II adjustments
L12  Standard / itemized deduction
L13a QBI §199A (Form 8995 Line 15) — does NOT affect AGI
L14  = L12 + L13a + L13b (OBBBA below-line)
L15  Taxable income = L11 − L14
```
Source: f1040.pdf Lines 11-15; f8995.pdf; IRC §199A.

### Rule 1B — IRA/pension distributions go on 1040 Lines 4b/5b (NOT Schedule 1)
`l4b` (IRA taxable) and `l5b` (pension taxable) go directly into `total_income`. They are NOT Schedule 1 Part I items and must NOT appear in `additional_income` (Line 8). Source: f1040.pdf Lines 4b, 5b, 8.

### Rule 1C — Form 1040 Lines 21-24 (exact per f1040.pdf)
```
L18  Add lines 16 and 17
L19  Child tax credit / ODC — Schedule 8812
L20  Schedule 3, line 8 (nonrefundable credits incl. education)
L21  Add lines 19 and 20
L22  Subtract line 21 from line 18 (tax after credits — if zero or less, enter -0-)
L23  Other taxes — Schedule 2, line 21 (SE tax, 5329, NIIT, etc.)
L24  Add lines 22 and 23 — This is your total tax
```
FETCH_VERIFIED: irs.gov/pub/irs-pdf/f1040.pdf | Page 2 Lines 18-24 | 2026-05-24

### Rule 1D — Form 8995 includes REIT/PTP component (Lines 6-9)
Form 8995 QBID = (20% × QBI component) + (20% × REIT/PTP component).
- L6 = qualified REIT dividends (1099-DIV Box 5 §199A dividends) + qualified PTP income (K-1 §199A)
- L9 = 20% × L8 REIT/PTP
- L10 = L3 + L9 (combined before TI limit)
- L15 = min(L10, 20% × ordinary TI) → 1040 Line 13a
Do NOT skip Lines 6-9. Source: f8995.pdf; i8995.pdf Line 6; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24.

### Rule 3 — map_result() is a pass-through (never a translator)
`map_result()` starts with `dict(c)`. Every engine key is automatically in the output. Only add: derived values and legacy aliases. Never enumerate individual engine keys.

### Rule 4 — EITC uses IRS $50-band table algorithm (not formula)
The IRS EIC Table uses discrete $50 bands. Credit is computed at `band = (int(lookup) // 50) * 50`, not at exact income. Formula approximations differ by $1–$100 per return. `requires_table_lookup` is always False — the band algorithm is filing-grade. Source: p1040.pdf pp.16+; IRC §32; Rev. Proc. 2024-40 §3.07.

### Rule 5 — safe_init() silently drops field name mismatches; every new field must be in all three places
Any field name difference between UI JSON and engine dataclass is dropped without error. The bridge audit (Page 9F) is the only safeguard. Every new form field must match the exact engine dataclass field name. **Any new UI field must be added simultaneously to:** `buildSchema()`, `populateFromSchema()`, and `safe_init()` bridge — all three, every time. *(Consolidates former Rule 21.)* 

### Rule 6 — Form 2441 Line 6 deemed earned income
When MFJ spouse has $0 earned income but is a full-time student OR disabled, deemed income = $250/month (1 qualifying person) or $500/month (2+ persons) × months qualified. Source: f2441.pdf Line 6; IRC §21(d)(2).

### Rule 7 — AOTC eligibility gates (all three required)
(1) `box8_half_time=True` — at least half-time enrollment required (hard gate). (2) `aoc_drug_conviction=False` — no federal/state drug conviction (hard gate). (3) `first_four_years=True` — cannot exceed 4 tax years total. Source: IRC §25A(b); i8863.pdf.

### Rule 8 — OBBBA tips occupation required (IRS Notice 2025-65)
Tip deduction requires a qualifying occupation from the IRS Notice 2025-65 list. Mandatory service charges are explicitly excluded (they are wages, not tips). Source: IRC §3121; Rev. Rul. 2012-18; Notice 2025-65.

### Rule 9 — OBBBA overtime must be FLSA-qualifying
Only time-and-a-half overtime qualifying under FLSA §207 counts. Bonuses, shift differentials, and exempt-employee extra pay do not qualify. Employer must separately identify FLSA overtime on W-2 or employer statement. Source: P.L. 119-21 §70202; FLSA §207(a)(1).

### Rule 10 — Capital gains special rates: §1250 (25%) and collectibles (28%)
Unrecaptured §1250 gain (straight-line depreciation on real property) is taxed at max 25%. Collectibles gain (coins, art, stamps, bullion) is taxed at max 28%. Both are passed to `compute_qdcgt_tax()` and reduce the pool subject to 0%/15%/20% rates. Source: IRC §1(h)(1)(D),(4); i1040sd.pdf Lines 18–19.

### Rule 11 — CA does not conform to OBBBA
CA Schedule CA must add back all four OBBBA deductions (senior, tips, OT, auto) when computing CA AGI. Engine auto-computes: `obbba_total_federal` passed to `compute_california_540()`. Source: CA FTB Announcement 2025-4.

### Rule 12 — IRS-first before any calculation (EA audit requirement)
Before coding any new formula, limit, or rate: look it up on irs.gov first. Primary sources only. Add `# Source: <form>.pdf <line>; <IRC §>` on the formula line. Never rely on training data for dollar amounts — they change annually and OBBBA made large mid-year changes. See 9A and 9G.

### Rule 13 — HOH requires a qualifying person (hard gate in UI)
`selFS('hoh')` is blocked when `S.deps.length === 0`. Alert shown to user. Engine also warns via soft gate for API mode. Source: IRC §2(b); Pub 501.

### Rule 14 — IRA spouse covered_by_plan from W-2 Box 13
`sp_covered = any(w.box13_retirement_plan for w in schema.w2s if w.for_spouse)`. Never hardcode False. When noncovered taxpayer / covered spouse, phaseout is $236k–$246k (2025). Source: Pub 590-A WS 1-2; IRC §219(g)(7).

### Rule 15 — IRS tax documents from irs.gov/forms-instructions only
All tax forms, instructions, and publications used in this project must come from **https://www.irs.gov/forms-instructions** exclusively. No third-party reproductions, cached copies, or training-data memory substitutes. When fetching a form or instruction for a calculation, cite the direct irs.gov URL. Hard requirement — not a preference.

### Rule 16 — No taxpayer information sent to web without express approval
No data from any TaxpayerSchema, computed result, or intake form may be transmitted to any external URL, API, or web service without the user's explicit approval in the chat. This includes web search queries that could contain PII. All IRS lookups must be read-only fetches of public IRS documents — never POST requests containing taxpayer data.

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
- `nec_included_in_gross: true` (default) — preparer included NEC in gross receipts
- `nec_included_in_gross: false` — engine auto-adds all 1099-NEC Box 1 to gross receipts
- Engine always emits verification warning when 1099-NEC income exists
- Do NOT enter NEC in both SE panel and Other Income panel (double-count)

### QBI §199A (Form 8995)
- **L1 QBI** = net profit − ½ SE tax − SE health insurance − SE retirement contributions
- **L6 REIT/PTP** = 1099-DIV Box 5 (§199A dividends) + K-1 §199A income
- **L9** = 20% × L8 REIT/PTP
- **L10** = L3 (QBI component) + L9 (REIT/PTP component)
- **L15 QBID** = min(L10, TI limit) → 1040 **Line 13a** (NOT Schedule 1)
- Source: f8995.pdf; i8995.pdf; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24

---

## Page 6 — Forms Implemented

### Fully implemented ✅ (33 forms)
Form 1040 all lines · Schedule 1 Part I+II · Schedule A (OBBBA) · Schedule B · Schedule C · Schedule D/8949 · Schedule E/8582 · Schedule K-1 · Schedule SE · Form 2441 (incl. Line 6 deemed) · Form 6251 AMT · Form 8606 (pro-rata) · Form 8863 AOTC+LLC · Form 8880 · Schedule 8812 CTC/ACTC/ODC · Form 8889 HSA · Form 8962 PTC (incl. repayment cap) · Form 1116 FTC · Form 4797 §1231/§1245/§1250 · Form 5329 · Form 8615 Kiddie · Pub 915 WS1 SS · Pub 575 Simplified Method · OBBBA §70103–70301 · CA 540 (partial) · TY 2026 full params · EITC $50-band table · Cap gains 25%/28% rates · QBI Form 8995-A (above threshold with W-2/UBIA) · PTC repayment cap Table 5 · AOTC half-time + drug conviction gates · HOH qualifying person gate

### Not yet implemented ⬜ (10 items)
| # | Priority | Item | Notes |
|---|---|---|---|
| 1 | HIGH | CA Schedule CA line-by-line | Major adjustments (military pay, loan forgiveness, community property) not full; use with caution |
| 2 | MEDIUM | EITC exact embedded table | Current band algorithm is filing-grade but not the pre-computed table |
| 3 | MEDIUM | CalEITC using W-2 Box 16/17 | Currently uses CA AGI proxy |
| 4 | MEDIUM | Form 982 insolvency worksheet | CoD exclusion for insolvency/bankruptcy |
| 5 | LOW | Form 2210 quarterly rate | Uses annual rate; directionally correct |
| 6 | LOW | K-1 outside basis computation | Warnings issued; basis not tracked multi-year |
| 7 | LOW | Form 8829 home office | Not implemented |
| 8 | LOW | AMT ISO/NQSO | Stock option AMT beyond $0 input |
| 9 | LOW | Non-CA state returns | Only CA 540 |
| 10 | LOW | §1231 5-year lookback computation | Warning issued; reclassification not auto-computed |

---

## Page 7 — Known Structural Risks

| Severity | Risk | Mitigation |
|---|---|---|
| MEDIUM | safe_init() silent drops | Bridge audit (Page 9F) every session; Layer 1 tests all bridge targets |
| HIGH | CA Schedule CA incomplete | Add-backs for OBBBA, bonus depreciation, military pay added; full line-by-line still needed; flag for filers |
| LOW | Form 2210 annual rate only | Penalty estimate directionally correct; exact quarterly calc may differ |
| LOW | K-1 basis/at-risk not enforced | ⚠ warnings issued on all losses; Form 6198 verification required |
| LOW | EITC band algorithm vs pre-computed table | Band algorithm matches table to within $1–$3 on most returns; acceptable for filing |

---

## Page 8 — Recurring Bug Patterns

### Pattern 1 — safe_init() silent drop
**Examples:** CoD always $0 · SSA WH $0 · SM never applied · books missing from AOTC · spouse fields dropped
**Prevention:** Bridge audit (Page 9F) every session. Layer 1 tests all bridge target fields.

### Pattern 2 — Local var not in computed dict
**Examples:** `additional_income` $0 · `obbba_senior_deduction` not in result
**Prevention:** Every new computed value must be stored in `result["computed"]`. `map_result()` uses `dict(c)` — all keys automatic.

### Pattern 3 — UI import overwrites auto-computed value
**Examples:** Senior age blanked · spouse SSN lost on re-import
**Prevention:** `populateFromSchema()` only overrides if schema value > 0. `buildSchema()` derives from DOB if field blank. Engine DOB fallback.

### Pattern 4 — map_result() manual drift
**Example:** 86 engine keys missing · renderResult showed $0 for correct values
**Prevention:** `map_result()` now starts with `dict(c)`. Can never drift.

### Pattern 5 — Test helper uses __import__ inline

### Pattern 6 — Independent re-computation diverges from engine
**Example:** `compute_qbi_deduction()` re-derived net profit from raw `sc.*` fields, missing the standard mileage deduction ($1,750) and NEC auto-add ($1,000) that `compute_schedule_c_se()` had already applied. The QBI function used `sc.car_truck_expenses = $0` (schema value) instead of the computed $1,750.
**Rule:** Never re-derive a value that has already been computed by another function. Pass computed results as parameters.

### Pattern 7 — Template literal TypeError silently aborts innerHTML
**Example:** `r.qbi_detail.per_biz.map(...)` inside a template literal — if `r.qbi_detail` is undefined, this throws TypeError, the entire innerHTML assignment fails, and the UI stays on "Loading result…" forever with no visible error.
**Rule:** Pre-declare all sub-dicts at top of render(): `const _qbi = r.qbi_detail || {}`. Wrap render() in try/catch with a visible error display.

### Pattern 8 — localStorage cross-origin isolation
**Example:** Workpaper opened as `file://` never has data set by `localhost:5000`. localStorage is per-origin. The standalone embedded workpaper (bundle injected at build time) is the workaround.

### Pattern 9 — qdcgt double-count of cap gain distributions
**Example:** `div_cap_gain_dist` was added to `qdcgt_income` separately, despite already being included in `net_ltcg_with_k1` (via Schedule D Line 13). When the Schedule D net is negative, the distribution is absorbed — adding it back to qdcgt artificially reduces ordinary income taxed at bracket rates.
**Rule:** `qdcgt_income = qual_div + max(0, net_ltcg)`. Never add `div_cap_gain_dist` separately.
**Example:** M1/M5 tests used `__import__('dataclasses').fields` inside function → field not found
**Prevention:** Always use a module-level `si()` helper with `import dataclasses as _dcN` at top of test block.

---

## Page 9 — Session Protocol

### 9A — Session start (required — all 6 steps)
1. `python3 sachintaxcare_test.py` → **584 PASS · 0 FAIL · 4 WARN**
2. `python3 test_vita_irs.py` → **145 PASS · 0 FAIL**
3. Sync audit (9C) → **0 divergences**
4. `node test_ui_fields.js sachintaxcare_pro.html` → **404 PASS · 0 FAIL**
5. **IRS Citation Audit (9G)** → 40/40 cited · 0 uncited
6. Then begin work

**STOP GATE before writing any new calculation code:**
> Before coding any new tax rule, formula, or limit — look it up on irs.gov first.
> **Rule 15:** Forms and instructions from https://www.irs.gov/forms-instructions ONLY.
> **Rule 16:** Never send taxpayer data to any web service without express user approval.
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
2. Update file registry (Page 1) with new line counts
3. Update this changelog (Page 1A) with what changed and why
4. Update Page 10 remaining priorities

### 9C — Sync Audit (paste into python3)

```python
import sachintaxcare_engine as e, re

p25 = e.PARAMS_2025; p26 = e.PARAMS_2026
checks = [
    # TY 2025 key values
    ("P25 std_ded MFJ",          p25["std_deduction"]["mfj"],         31500),
    ("P25 std_ded single",       p25["std_deduction"]["single"],       15750),
    ("P25 ctc_per_child",        p25["ctc_per_child"],                 2200),
    ("P25 actc_cap",             p25["actc_cap_per_child"],            1700),
    ("P25 senior_ded",           p25["senior_deduction_amount"],       6000),
    ("P25 tip_max",              p25["tip_deduction_max"],             25000),
    ("P25 ot_max_mfj",           p25["overtime_deduction_max_mfj"],    25000),
    ("P25 ira_limit",            p25["ira_contribution_limit_2025"],   7000),
    ("P25 hsa_self",             p25["hsa_limit_self_only_2025"],      4300),
    ("P25 amt_ex_single",        p25["amt_exemption_single"],          88100),
    ("P25 amt_po_single",        p25["amt_phaseout_single"],           626350),
    ("P25 qbi_threshold_mfj",   p25["qbi_threshold_mfj"],             394600),
    ("P25 eitc_invest_limit",    p25["eitc_investment_income_limit"],  11600),
    # TY 2026 key values
    ("P26 std_ded MFJ",          p26["std_deduction"]["mfj"],         32200),
    ("P26 ctc_per_child",        p26["ctc_per_child"],                 2300),
    ("P26 ira_limit",            p26["ira_limit_2026"],                7500),
    ("P26 hsa_self",             p26["hsa_self_only_2026"],            4400),
    ("P26 amt_po_single",        p26["amt_phaseout_single"],           500000),
    ("P26 qbi_min",              p26["qbi_min_deduction"],             400),
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
3. Add field to UI HTML with correct `id`
4. Wire field in `buildSchema()` using `v()` or `n()`
5. Wire field in `populateFromSchema()` for import
6. If field name differs between UI and dataclass, add to bridge table (server.py + Page 2)
7. Add test assertion in test suite (Layer 1B registry check is automatic via `safe_init`)
8. Run 9A gates — 0 failures required

### 9E — Adding a new compute function (checklist)
1. Define `compute_X()` with `# Source: <IRS form>` in docstring
2. Add at least one IRS citation inside the function body
3. Call from `run()` with appropriate params
4. Store result in `result["computed"]` (or sub-dict)
5. Add test assertions — both unit (Layer 3) and pipeline (Layer 2)
6. Run 9G citation audit — 0 uncited
7. Run 9A gates — 0 failures

### 9F — Bridge Audit Protocol (run at session start)

```python
import sachintaxcare_engine as e, dataclasses as dc

BRIDGE_TARGETS = [
    (e.Form1099C,         "box2_amount_discharged"),
    (e.Form1099C,         "is_excluded"),
    (e.FormSSA1099,       "box6_voluntary_wh"),
    (e.Form1099R,         "box9b_employee_contribs"),
    (e.W2,                "box5_med_wages"),
    (e.Form1098T,         "box8_half_time"),
    (e.Form1098T,         "aoc_drug_conviction"),
    (e.Form1098T,         "box9_graduate"),
    (e.TaxpayerSchema,    "spouse_ssn"),
    (e.TaxpayerSchema,    "spouse_first"),
    (e.TaxpayerSchema,    "spouse_last"),
    (e.TaxpayerSchema,    "spouse_dob"),
    (e.TaxpayerSchema,    "tip_occupation"),
    (e.TaxpayerSchema,    "overtime_flsa_confirmed"),
    (e.TaxpayerSchema,    "care_spouse_is_student"),
    (e.TaxpayerSchema,    "care_spouse_is_disabled"),
    (e.TaxpayerSchema,    "care_spouse_months_qualified"),
    (e.TaxpayerSchema,    "prior_sec1231_losses_5yr"),
    (e.SimplifiedMethodData, "age_at_annuity_start"),
    (e.SimplifiedMethodData, "prior_year_tax_free_recovered"),
    # Added 2026-05-22/24
    (e.Form1099DIV,       "box2a_total_cap_gain"),   # alias for box2a_cap_gain_dist
    (e.Form5329Exception, "amount"),                 # alias for distribution_amount
    (e.Form5329Exception, "account_type"),           # alias for plan_type
    (e.Form1098E,         "box1_student_loan_interest"),
    (e.ScheduleC,         "nec_included_in_gross"),
    (e.ScheduleC,         "business_code"),
    (e.ScheduleC,         "business_miles"),
    (e.Form1099INT,       "payer_ein"),
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

## Page 10 — Next Session Priorities

| # | Priority | Item | Notes |
|---|---|---|---|
| 1 | HIGH | CA Schedule CA full line-by-line | Military pay, community property MFS split, loan forgiveness, bonus depreciation recalculation |
| 2 | MEDIUM | CalEITC: use W-2 Box 16/17 CA wages | Currently uses CA AGI proxy; accuracy matters for low-income filers |
| 3 | MEDIUM | Form 982 insolvency worksheet | CoD exclusion for bankruptcy/insolvency; common with cancelled mortgage debt |
| 4 | MEDIUM | Form 2441 Line 6 workpaper display | Deemed income calculation not yet shown on workpaper page |
| 5 | LOW | §1231 5-year lookback auto-computation | Warning issued; actual reclassification not auto-applied |
| 6 | LOW | Form 2210 quarterly rate | Annual rate used; directionally correct |
| 7 | LOW | 1099-INT Box 9 PAB → AMT route verify | Low impact |
| 8 | LOW | Schedule B Line 3 Treasury bond premium | Display only |
| 9 | LOW | Schedule C Part III COGS workpaper display | For product-based businesses |

---

## Appendix A — Why Calculation Mistakes Happen

See Page 8 (Recurring Bug Patterns) for the full list. Summary:

1. **safe_init() silent drop** — field name mismatch between UI JSON and dataclass → silently $0
2. **Local var not in computed dict** — engine computes correctly but value not stored in result
3. **UI import overwrites auto-compute** — `populateFromSchema()` overwrites a value the engine derives
4. **map_result() manual drift** — manually listed keys diverge from engine; fixed permanently by `dict(c)` pass-through
5. **Test helper inline __import__** — `__import__('dataclasses')` inside function body doesn't find new fields
6. **Round-trip not tested** — new field in buildSchema but not ROUND_TRIP_CHECKS → import breaks silently.
7. **Wrong layer diagnosis** — "not in export" interpreted as result dict missing, not populateFromSchema missing.
8. **Wrong IRS rate from memory** — FETCH_VERIFIED protocol prevents this.
9. **Wrong 1040 line routing** — IRA/pension in Sch1 instead of L4b; QBI in Sch1 instead of L13a.
10. **Variable shadowing** — `map(r =>)` inside template literal shadows outer `r` → TypeError aborts innerHTML.
11. **localStorage cross-origin** — workpaper as file:// never has data from localhost:5000. Use embedded standalone.
12. **Independent re-computation** — `compute_qbi_deduction()` re-derived net profit from schema, missing mileage/NEC. Fixed: pass computed value from run().
13. **Partial form implementation** — Form 8995 Lines 1–7 computed, Lines 6–9 (REIT/PTP) skipped. Always implement all form lines.

---

*Updated: 2026-05-24 · Version V17.1 · Rules 15+16 added*
*IRS sources: irs.gov/pub/irs-pdf/ · IRS Pub 463 (2025) · IRS Notice 2025-5 · Rev. Proc. 2024-40 · Rev. Proc. 2025-32 · IR-2025-103 · IR-2025-128 · Notice 2025-65 · Notice 2025-67 · P.L. 119-21 (OBBBA) · f8995.pdf · i8995.pdf · i5329.pdf · f1040.pdf · IRC §21, §24, §25A, §32, §63, §86, §165, §199A, §219, §221, §465, §704, §1231, §1250, §1401 · IRS Pub 463, 503, 575, 596, 915, 939, 1001 · ftb.ca.gov/forms/2025/*
