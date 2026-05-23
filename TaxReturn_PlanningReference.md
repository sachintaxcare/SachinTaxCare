# SachinTaxCare — Tax Return Planning Reference
*Last updated: 2026-05-24 · Engine v17 · All dollar values from `PARAMS_2025` / `PARAMS_2026` in engine.*
*IRS source authority: irs.gov only (per Rules 27, 9A, 9G).*

---

## How to use this document

Single source of truth for every tax constant, rule, bridge mapping, test gate, and session protocol.
**Before any session:** run all four gates in 9A. Zero failures required before any changes.

---

## Page 1 — File Registry

| File | Lines | Version | Role |
|---|---|---|---|
| `sachintaxcare_engine.py` | **8,735** | v17 — mileage 70¢, QBI L13a+L6 REIT, l4b routing, workpaper fix | Computation engine (TY 2025 + TY 2026) |
| `sachintaxcare_pro.html` | **4,625** | v7 — NEC inclusion, 1098-T Box9, int-ein, 1098-E restore | Primary UI — intake + results |
| `sachintaxcare_server.py` | **761** | v16 — map_result() pass-through | Flask server + bridge |
| `sachintaxcare_workpaper.html` | **1,670** | v8 — 18 pages, try/catch, pre-declared sub-dicts | CPA workpaper |
| `sachintaxcare_test.py` | **2,527** | v4.1 — **586 PASS · 0 FAIL · 7 WARN** | Regression suite |
| `test_ui_fields.js` | **815** | v2.0 — 64 round-trip keys | UI field completeness |

**Session start gate:** `python3 sachintaxcare_test.py` → **586 PASS · 0 FAIL**

---

## Page 1A — Changelog (most recent first)

### Session 2026-05-24 (afternoon) — Form 8995 REIT/PTP Line 6 fix + QBI base fix

| Fix | Item | Source |
|---|---|---|
| **Form 8995 L6 REIT/PTP** | Engine computed Lines 1–7 (QBI) but skipped Lines 6–9 (REIT/PTP component). 1099-DIV Box 5 §199A dividends ($32) × 20% = $6 → QBID was $1,334, now **$1,340**. | f8995.pdf Lines 6-9; i8995.pdf Line 6; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24 |
| **QBI wrong base** | `compute_qbi_deduction()` re-derived net profit from raw schema fields, missing mileage deduction ($1,750) and NEC auto-add ($1,000). Now accepts `se_net_profit` from `run()` directly. | f8995.pdf Line 1; Reg. §1.199A-3(b) |
| **QBI on 1040 L13a** | QBI was in `total_adjustments` (reducing AGI) — wrong. Removed from `total_adjustments_before_sl`; now applied to `taxable_income` via `taxable = taxable - adj_qbi`. | f1040.pdf Line 13a; IRC §199A |
| **l4b routing** | IRA/pension distributions were in `additional_income` (Sch1 L10/Line 8) — wrong. Removed from `additional_income`; added directly to `total_income_pre_ss`. Line 8 was $12,250, now **$7,250**. | f1040.pdf Lines 4b, 5b, 8 |
| **Mileage rate 67¢→70¢** | Engine had 2024 rate. Corrected to 70¢/mile for TY 2025. | IRS Pub 463 (2025); IRS Notice 2025-5; FETCH_VERIFIED 2026-05-24 |
| **Workpaper loading** | Template literals threw TypeError on undefined sub-dicts → "Loading result…" forever. Pre-declared 6 sub-dicts; render() wrapped in try/catch. | — |
| **Round-trip 64 keys** | schedule_cs, form_1099ints, form_5329_exceptions, form_1099divs sections added to ROUND_TRIP_CHECKS. | — |
| **1099-B import** | cost_basis → wrong field (`sale-cost-` not `sale-basis-`); is_long_term, basis_reported_to_irs used wrong JSON keys. | — |
| **1098-E import** | populateFromSchema had zero code to restore 1098-E entries. Restore loop added. | — |

### Session 2026-05-24 (morning) — Three IRS-compliance corrections

| Fix | What changed |
|---|---|
| Mileage 67¢→70¢ | IRS Pub 463 (2025); IRS Notice 2025-5 |
| QBI on L13a not Sch1 | QBI removed from AGI; applies below-the-line per f1040.pdf L13a |
| l4b in total_income directly | IRA/pension no longer routes through Sch1 additional_income |

### Session 2026-05-23 — Workpaper expansion, bridge fixes, Schedule D corrections

| Fix | Item |
|---|---|
| Schedule D double-count | Box C (ST noncovered) was in both box_c_rows AND ST accumulators |
| 1099-DIV box2a alias | `box2a_total_cap_gain` JSON key vs `box2a_cap_gain_dist` engine field |
| Form 5329 amount/account_type | Alias fields added to Form5329Exception |
| Workpaper Pages A–G | W-2, Schedule B, Schedule D/8949, Schedule C, 1099-R/5329, Form 8962, Form 2441 |
| Education credit on L20 | Credits shown BEFORE total tax per 1040 L18→L19→L20→L21 |

### Session 2026-05-22 — Schedule D dates, LLC fallback, sch1/sch2/sch3 export

| Fix | Item |
|---|---|
| ST/LT from actual dates | date_acquired/date_sold → holding period; is_long_term = fallback only |
| 1099-DIV Box 2a → Sched D L13 | Cap gain distributions now in Schedule D net |
| sch1/sch2/sch3 sub-dicts | Added to computed dict |
| LLC fallback from AOC | All three AOC denial gates fall through to LLC |

### Session 2026-05-18 — EA audit critical/high fixes (prior session)

*(EITC table, Form 2441 deemed income, AOTC gates, HOH gate, CA Schedule CA, §1231 lookback, etc.)*

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
`map_result()` starts with `dict(c)` — every engine key automatically in output. Only add derived values and legacy aliases. Adding a new engine key requires zero server changes.

### safe_init() field name mismatch table

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
| `cost_basis`→`sale-cost-` (wrong field) | →`sale-basis-` | UI 1099-B | 2026-05-24 |
| `is_long_term`→`b.term` (wrong key) | →`b.is_long_term` | UI 1099-B | 2026-05-24 |
| `basis_reported_to_irs`→`b.basis_reported` | →`b.basis_reported_to_irs` | UI 1099-B | 2026-05-24 |

### Engine internals (2026-05-24)
- **Compute functions:** 41
- **Dataclasses:** 38 · **Schema fields:** 515+
- **Computed keys:** 155+
- **IRS citations:** 1,350+
- **PARAMS_2025:** 131 scalar · **PARAMS_2026:** 149 scalar
- **Round-trip keys tested:** 64
- **TY 2025 + TY 2026 fully parametrized**

---

## Page 3 — Tax Year Constants (TY 2025)

Source: Rev. Proc. 2024-40 · OBBBA P.L. 119-21 · IRS Notice 2025-5

### Standard Deductions (IRC §63)
| Status | Amount | Age-65/blind add-on |
|---|---|---|
| Single / MFS | $15,750 | +$2,000/condition |
| MFJ / QSS | $31,500 | +$1,600/qualifying spouse |
| HOH | $23,625 | +$2,000/condition |

### Mileage Rates (TY 2025)
| Purpose | Rate | Source |
|---|---|---|
| **Business** | **70¢/mile** | IRS Notice 2025-5; IRS Pub 463 (2025); **FETCH_VERIFIED 2026-05-24** |
| Medical / moving | 21¢/mile | IRS Notice 2025-5 |
| Charitable | 14¢/mile | IRC §170(i) |

> **TY 2026:** 72.5¢/mile business (IR-2025-128, effective Jan 1, 2026)

### OBBBA Above-Line Deductions (Sch 1 Part II → reduce AGI; TY 2025–2028)
| Provision | Cap | Phaseout starts |
|---|---|---|
| Senior bonus §70103 (age ≥65) | $6,000/person | $75k single / $150k MFJ |
| Qualified tips §70201 | $25,000 | $150k single / $300k MFJ |
| FLSA overtime §70202 | $12,500 single / $25,000 MFJ | $150k / $300k |
| Auto loan interest §70301 | $10,000 | $100k single / $200k MFJ |
| SALT cap §70106 | $40,000 (MFJ) | Phase-down above $500k AGI |

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

---

## Page 4 — Schedule C Rules

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

## Page 9 — Session Gates

### 9A — Mandatory pre-session (run before ANY changes)
```bash
python3 sachintaxcare_test.py          # 586 PASS · 0 FAIL
python3 test_vita_irs.py               # 145 PASS · 0 FAIL
node test_ui_fields.js sachintaxcare_pro.html  # Round-trip PASS 64
# FETCH_VERIFIED audit built into Gate 1
```

### 9D — Adding a new engine field (checklist)
1. Add to dataclass with type annotation, default, `# Source:` comment
2. Add `# FETCH_VERIFIED: <URL> | <section> | <date>` for code tables/rates
3. Add UI HTML field with correct `id`
4. Wire in `buildSchema()` and `populateFromSchema()`
5. **Add to `ROUND_TRIP_CHECKS` in `test_ui_fields.js`** — mandatory same session
6. Add to bridge table (Page 2) if JSON key ≠ dataclass field name
7. Run 9A gates — 0 failures required

### 9F — Bridge Audit Protocol
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
    (e.Form1099DIV,       "box2a_total_cap_gain"),
    (e.Form5329Exception, "amount"),
    (e.Form5329Exception, "account_type"),
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
    print(f"  ✅ All {len(BRIDGE_TARGETS)} bridge targets present")
```

---

## Page 10 — Next Session Priorities

| # | Priority | Item |
|---|---|---|
| 1 | HIGH | CA Schedule CA full line-by-line (military pay, community property, bonus depreciation) |
| 2 | MEDIUM | CalEITC using CA wages (Box 16/17) — currently uses CA AGI proxy |
| 3 | MEDIUM | Form 982 insolvency worksheet — CoD exclusion |
| 4 | LOW | §1231 5-year lookback auto-computation — warning issued, not auto-applied |
| 5 | LOW | Form 2210 quarterly penalty rate |
| 6 | LOW | Schedule C Part III COGS workpaper display |

---

## Appendix A — Why Calculation Mistakes Happen

1. **safe_init() silent drop** — field name mismatch → silently $0. Run 9F bridge audit.
2. **Round-trip not tested** — new field in buildSchema but not ROUND_TRIP_CHECKS → import breaks silently.
3. **Wrong layer diagnosis** — "not in export" interpreted as result dict missing, not populateFromSchema missing.
4. **Wrong IRS rate from memory** — FETCH_VERIFIED protocol prevents this.
5. **Wrong 1040 line routing** — IRA/pension in Sch1 instead of L4b; QBI in Sch1 instead of L13a.
6. **Variable shadowing** — `map(r =>)` inside template literal shadows outer `r` → TypeError aborts innerHTML.
7. **localStorage cross-origin** — workpaper as file:// never has data from localhost:5000. Use embedded standalone.
8. **Independent re-computation** — `compute_qbi_deduction()` re-derived net profit from schema, missing mileage/NEC. Fixed: pass computed value from run().
9. **Partial form implementation** — Form 8995 Lines 1–7 computed, Lines 6–9 (REIT/PTP) skipped. Always implement all form lines.

---

*Updated: 2026-05-24 · Engine v17*
*IRS sources: IRS Pub 463 (2025) · IRS Notice 2025-5 · f8995.pdf · i8995.pdf · i5329.pdf · f1040.pdf · f1040sc.pdf · Rev. Proc. 2024-40 · Rev. Proc. 2025-32 · IR-2025-103 · IR-2025-128 · Notice 2025-65 · Notice 2025-67 · P.L. 119-21 (OBBBA) · IRC §21, §24, §25A, §32, §63, §86, §165, §199A, §219, §221, §465, §704, §1231, §1250, §1401 · IRS Pub 463, 503, 575, 596, 915, 939, 1001*
