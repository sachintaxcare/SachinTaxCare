# SachinTaxCare — Implementation Guide
*How to rebuild this project from scratch in one focused effort*
*Engine V17.1 · TY 2025 + TY 2026 · 584/584 tests · 145/145 VITA · Updated 2026-05-24*

---

## What this document is

Complete blueprint for rebuilding SachinTaxCare without reading any prior session history. Covers every file, every architectural decision, the IRS rules the engine enforces, and every known pitfall. A competent engineer reading this document plus the source files listed below should be able to fully understand, extend, and maintain the project.

---

## ⚠ OBBBA (P.L. 119-21, signed July 4, 2025)

Critical mid-year law change. All parameters updated. Key changes for TY 2025:

| Item | Old | New | Engine location |
|---|---|---|---|
| Std ded single/MFS | $15,000 | **$15,750** | `PARAMS_2025["std_deduction"]` |
| Std ded HOH | $22,500 | **$23,625** | `PARAMS_2025["std_deduction"]` |
| Std ded MFJ/QSS | $30,000 | **$31,500** | `PARAMS_2025["std_deduction"]` |
| CTC per child | $2,000 | **$2,200** | `PARAMS_2025["ctc_per_child"]` |
| SALT cap | $10,000 | **$40,000** | `PARAMS_2025["salt_cap_default"]` |
| SALT cap MFS | $5,000 | **$20,000** | `PARAMS_2025["salt_cap_mfs"]` |
| Charitable floor | 0% | **0.5% AGI** | `PARAMS_2025["charitable_agi_floor_pct"]` |
| AMT exemption | sunsets | **permanent** | `PARAMS_2025` |
| QBI threshold | sunsets | **permanent** | `PARAMS_2025` |

New OBBBA Schedule 1-A deductions (Form 1040 Line 13b — **below-the-line, do NOT reduce AGI**):

| Deduction | Cap | Phase-out MAGI | Engine function |
|---|---|---|---|
| Senior Bonus ($6k/person age 65+) | $6k/person | $75k single / $150k MFJ | `compute_senior_deduction()` |
| Qualified tips | $25,000 | $150k single / $300k MFJ | `compute_tip_deduction()` |
| FLSA overtime (§207) | $12,500 / $25,000 MFJ | $150k single / $300k MFJ | `compute_overtime_deduction()` |
| Auto loan interest (new US vehicle) | $10,000 | $100k single / $200k MFJ | `compute_auto_loan_deduction()` |

Source: P.L. 119-21 §70102–70301; Rev. Proc. 2025-32; IRS IR-2026-28.

---

## File registry

| File | Lines | Version | Role |
|---|---|---|---|
| `sachintaxcare_engine.py` | **8,752** | V17.1 | Python computation engine — TY 2025 + TY 2026 |
| `sachintaxcare_pro.html` | **4,629** | v7 | Single-file web UI — 18 panels, dual modes, import/export |
| `sachintaxcare_server.py` | **761** | v16 | Flask server + bridge layer |
| `sachintaxcare_workpaper.html` | **1,670** | v8 | 18-page CPA workpaper |
| `sachintaxcare_test.py` | **2,527** | v4.1 | Regression suite — **584 PASS · 0 FAIL · 4 WARN** |
| `test_vita_irs.py` | **2,551** | v12.1 | IRS/VITA known-answer tests — **145/145** |
| `test_ui_fields.js` | **815** | v2.0 | UI field completeness — **404 PASS · 0 FAIL** |
| `sachintaxcare_pdf.py` | **367** | v1.0 | PDF output (reportlab) |
| `sachintaxcare_report.py` | **965** | v11 | JSON verification report |
| `test_report.py` | **415** | v1 | Report verification tests |
| `sachintaxcare_field_manifest.md` | **855** | v1.3 | Field registry — every form field |
| `ENGINE_ALGORITHM.md` | — | V17.1 | Engine computation flow (this session) |
| `IMPLEMENTATION_GUIDE.md` | — | V17.1 | This document |
| `README_server.md` | **122** | v1 | Server setup and API reference |
| `requirements.txt` | 2 | — | `flask>=3.0.0`, `flask-cors>=4.0.0` |

**No database. No user accounts. No build step. No external API required.** Everything runs locally with `pip install -r requirements.txt`.

---

## Architecture

```
Browser (sachintaxcare_pro.html)
    │
    ├── Mode A: Engine mode (default)
    │       └── buildSchema() → POST /compute
    │                               └── sachintaxcare_server.py
    │                                       └── deserialize_schema(json)
    │                                               └── sachintaxcare_engine.run(TaxpayerSchema)
    │                                                       └── returns dict[computed + warnings]
    │                               └── map_result(engine_result) → flat JSON → renderResult()
    │
    └── Mode B: Claude mode (claude.ai only)
            └── buildPrompt() → sendPrompt() → Claude AI chat window
```

**Key constraint**: `sachintaxcare_engine.py` is pure Python with zero Flask imports. Input = `TaxpayerSchema` dataclass. Output = plain dict. Never change this — it keeps the engine trivially testable and reusable in any context.

---

## 18 UI intake panels

| Panel id | Content |
|---|---|
| `taxpayer` | Name, SSN, DOB, address, filing status, occupation |
| `spouse` | Spouse name, SSN, DOB |
| `dependents` | Dependent array — name, DOB, relationship, CTC/ODC |
| `w2` | W-2 array — all 20 box fields per employer |
| `1099s` | 1099-INT, 1099-DIV, 1099-R, SSA-1099, 1099-NEC, 1099-C, 1099-B, W-2G, 1099-G, 1099-MISC |
| `se` | Schedule C array — gross, expenses, home office, mileage |
| `rental` | Schedule E array — rental properties |
| `k1` | Schedule K-1 array — pass-through entities |
| `capgains` | Form 8949 / Schedule D |
| `adj` | Above-line adjustments — IRA, teacher, student loan, alimony, OBBBA |
| `scheda` | Schedule A — itemized deductions |
| `credits` | Education (Form 8863), care (Form 2441), retirement savings (Form 8880), HSA (Form 8889) |
| `f1116` | Foreign tax credit (Form 1116) |
| `retirement` | IRA/pension — Form 8606, simplified method, Form 5329 exceptions |
| `advanced` | AMT (Form 6251), NIIT, additional Medicare, Form 4972, Form 4797, Form 8615 |
| `ca540` | California Form 540 |
| `taxref` | Estimated tax payments, Form 8962 / ACA, prior year data |
| `compute` | Review + compute button |

---

## Flask server routes

| Route | Handler |
|---|---|
| `GET /` | Serves `sachintaxcare_pro.html` |
| `GET /workpaper` | Serves `sachintaxcare_workpaper.html` |
| `POST /compute` | `deserialize_schema(json)` → `engine.run()` → `map_result()` → JSON |
| `GET /health` | `{"status": "ok", "engine": "V17.1"}` |

---

## Bridge layer (`deserialize_schema` in sachintaxcare_server.py)

`_safe_init()` maps JSON keys → engine dataclass fields by **exact name match**. Any mismatched key is **silently discarded** — this is a constant source of bugs. The bridge explicitly translates all known mismatches before `_safe_init()` runs:

| UI / schema key | Engine dataclass field | Dataclass |
|---|---|---|
| `box2_discharged` | `box2_amount_discharged` | `Form1099C` |
| `exclusion_applies` | `is_excluded` | `Form1099C` |
| `box6_vol_wh` | `box6_voluntary_wh` | `FormSSA1099` |
| `box9b_employee_contrib` | `box9b_employee_contribs` | `Form1099R` |
| `age_at_start` | `age_at_annuity_start` | `SimplifiedMethodData` |
| `joint_age_at_start` | `joint_age_at_annuity_start` | `SimplifiedMethodData` |
| `prior_tax_free_recovered` | `prior_year_tax_free_recovered` | `SimplifiedMethodData` |
| `start_after_nov_1996` | `annuity_start_after_nov_18_1996` | `SimplifiedMethodData` |
| `box10_dep_care` | `box10_dependent_care` | `W2` |
| `box15_state_id` | `box15_state_employer_id` | `W2` |
| `box5_medicare_wages` | `box5_med_wages` | `W2` |
| `box6_medicare_wh` | `box6_med_wh` | `W2` |
| `box6_foreign_tax_paid` | `box6_foreign_tax` | `Form1099INT` |
| `sdi_withheld` | `ca_sdi_withheld` | `CaliforniaData` |
| `other_subtractions` | `ca_other_subtractions` | `CaliforniaData` |
| `form_1099miscs[].box3` | `Form1099MISC_Prize` list | (constructed) |
| `prize_income` (legacy flat) | `Form1099MISC_Prize` list | (constructed) |
| `spouse.ssn/first/last/dob` | `spouse_ssn/first/last/dob` | `TaxpayerSchema` |
| `box8_at_least_half_time` | `box8_half_time` | `Form1098T` |

**Rule**: every new UI field must be verified in `test_ui_fields.js` and every new bridge mapping must appear in the bridge audit section of `sachintaxcare_test.py`.

---

## Export / Import JSON

- **Export**: `exportJSON()` → `buildSchema()` → downloads `sachintaxcare_schema_2025.json`
- **Import**: `importJSON()` → `FileReader` → `populateFromSchema(sc)`:
  - Clears all dynamic rows, resets all index counters to zero
  - Calls `addW2()`, `addDep()`, etc. for each array item, then sets field values
  - Bridges schema key names to UI field ids
  - Calls `go('taxpayer')` to navigate to first panel

**Round-trip rule**: every field in `buildSchema()` must appear identically in `populateFromSchema()`. Verified by `test_ui_fields.js` 64-key round-trip audit.

---

## Workpaper (`sachintaxcare_workpaper.html`)

18-page IRS Form 1040-faithful CPA workpaper:

| Pages | Content |
|---|---|
| 1–2 | Form 1040 — Taxpayer info, income, AGI |
| 3–4 | Form 1040 — Tax, credits, payments, refund/owe |
| 5 | Schedule 1 — Additional income and adjustments |
| 6 | Schedule 2 — Other taxes (SE, AMT, 5329, NIIT) |
| 7 | Schedule 3 — Credits (education, care, FTC, saver) |
| 8 | Schedule A — Itemized deductions |
| 9 | Schedule B — Interest and dividends |
| 10 | Schedule C — Business income |
| 11 | Schedule SE — Self-employment tax |
| 12 | Schedule D — Capital gains |
| 13 | Schedule E — Rental income |
| 14 | Form 8995 — QBI deduction |
| 15 | Schedule 8812 — CTC/ACTC/ODC |
| 16 | Form 5329 — Early distributions |
| 17 | California Form 540 |
| 18 | CPA warnings + pre-filing checklist |

Reads result from `localStorage['sachintaxcare_result']` (written by `renderResult()` after `/compute`). Opened via `GET /workpaper`. Print → `window.print()` → browser PDF.

---

## Test suite architecture

```
python3 sachintaxcare_test.py    → 584 PASS · 0 FAIL · 4 WARN
python3 test_vita_irs.py         → 145/145 PASS
node test_ui_fields.js sachintaxcare_pro.html  → 404 PASS · 0 FAIL
```

### `sachintaxcare_test.py` layers

| Layer | What it tests |
|---|---|
| LAYER 1 — Bridge Audit | Schema↔engine field-name mapping; all known bridge cases documented |
| LAYER 1B — Dataclass Registry | Every engine dataclass field exists in the manifest |
| LAYER 2 — Pipeline Regression | 8+ known-schema scenarios through full bridge→engine→result; asserts dollar values |
| LAYER 2B — TY 2026 Pipeline | Same scenarios with `tax_year=2026` parameters |
| LAYER 3 — Engine Unit | PARAMS_2025 constants verified against IRS publication values |
| LAYER 3B — PARAMS Sync | PARAMS_2025 + PARAMS_2026 vs TaxReturn_PlanningReference.md Page 3 |
| FILE REGISTRY | Line counts of all source files vs registered values |
| QCD Regression | QCD (IRC §408(d)(8)) Code Y exclusion and cap |

### `test_vita_irs.py` sections (145 known-answer cases)

Sections 1–25 cover W-2 only through complex multi-form returns. Section 32 covers all OBBBA deductions. Section 33 covers OBBBA phase-outs. Section 34 covers CA CalEITC/YCTC. Every assertion cites the exact IRS source (`f1040.pdf`, `i8863.pdf`, etc.).

### `test_ui_fields.js`

Runs against the live HTML file. For every field id in `sachintaxcare_field_manifest.md`:
- Confirms the id exists in the HTML DOM
- Runs a 64-key `buildSchema()` → `populateFromSchema()` round-trip
- Reports PASS / FAIL / SKIP (known gaps) / WARN (captured not computed)

---

## Session workflow for new features

```
1.  Run all 6 session-start gates (Page 9A of TaxReturn_PlanningReference.md)
2.  Fetch the relevant IRS PDF from https://www.irs.gov/forms-instructions (Rule 15)
3.  Add new @dataclass fields to engine.py with IRS source citations in docstring
4.  Add new rows to sachintaxcare_field_manifest.md (status ❌)
5.  Write compute_xxx() in engine.py with # Source: citation on every formula line
6.  Wire into run() at correct position in the 14-step order
7.  Add test cases to test_vita_irs.py with exact IRS-cited expected values
8.  python3 test_vita_irs.py → must be 0 FAIL before touching UI
9.  Add UI fields to sachintaxcare_pro.html (all 3: buildSchema + populateFromSchema + bridge)
10. Update manifest status ❌ → ✅
11. node test_ui_fields.js sachintaxcare_pro.html → must be 0 FAIL
12. python3 sachintaxcare_test.py → must be 0 FAIL
13. Update TaxReturn_PlanningReference.md (changelog + file registry)
```

**Hard rules**: no engine field without a test case. No test case uses secondary sources. Every formula cites the IRS form PDF and IRC section. No taxpayer data sent to web (Rule 16).

---

## 2025 tax parameter quick reference

| Parameter | Value | Source |
|---|---|---|
| Std ded single/MFS | **$15,750** | OBBBA §70102; Rev. Proc. 2025-32 |
| Std ded MFJ/QSS | **$31,500** | OBBBA §70102 |
| Std ded HOH | **$23,625** | OBBBA §70102 |
| 65+/blind add-on (single/HOH) | $2,000 | Rev. Proc. 2024-40 |
| 65+/blind add-on (MFJ per person) | $1,600 | Rev. Proc. 2024-40 |
| CTC per qualifying child | **$2,200** | OBBBA §70104; IRC §24(h)(2) |
| ACTC cap per child | $1,700 | Rev. Proc. 2024-40 |
| ACTC rate | 15% × (earned − $2,500) | IRC §24(d) |
| CTC phase-out single | $200,000 | IRC §24(b) |
| CTC phase-out MFJ | $400,000 | IRC §24(b) |
| ODC per other dependent | $500 | IRC §24(h)(4) |
| SALT cap (default) | **$40,000** | OBBBA §70106 |
| SALT cap MFS | **$20,000** | OBBBA §70106 |
| SALT phase-down above | $500,000 AGI | OBBBA §70106 |
| Charitable AGI floor | **0.5% AGI** | OBBBA; IRC §170 |
| Senior Bonus Deduction | **$6,000/person ≥ 65** | OBBBA §70103 |
| Tip deduction cap | **$25,000** | OBBBA §70201 |
| Overtime deduction cap | **$12,500 / $25,000 MFJ** | OBBBA §70202 |
| Auto loan interest cap | **$10,000/yr** | OBBBA §70301 |
| SS wage base | $176,100 | SSA 2025 |
| SE tax rate | 15.3% × 92.35% | IRC §1401 |
| Standard mileage (business) | **70¢/mile** | IRS Notice 2025-5 |
| Additional Medicare threshold single | $200,000 | IRC §3103 |
| Additional Medicare threshold MFJ | $250,000 | IRC §3103 |
| NIIT threshold single | $200,000 | IRC §1411 |
| NIIT threshold MFJ | $250,000 | IRC §1411 |
| NIIT rate | 3.8% | IRC §1411 |
| AMT exemption single | $88,100 | Rev. Proc. 2024-40; OBBBA §70107 |
| AMT exemption MFJ | $137,000 | Rev. Proc. 2024-40; OBBBA §70107 |
| QBI threshold single | $197,300 | Rev. Proc. 2024-40; OBBBA |
| QBI threshold MFJ | $394,600 | Rev. Proc. 2024-40; OBBBA |
| QBI minimum (TY 2026 only) | $400 | OBBBA §70XXX |
| EITC investment income limit | $11,600 | Rev. Proc. 2024-40 |
| HSA limit self-only | $4,300 | Rev. Proc. 2024-40 |
| HSA limit family | $8,550 | Rev. Proc. 2024-40 |
| HSA catch-up (55+) | $1,000 | IRC §223(b)(3) |
| IRA contribution limit | $7,000 ($8,000 if 50+) | IRC §219(b)(5) |
| 401(k) elective deferral | $23,500 | IRS IR-2024-285 |
| SEP-IRA | min(25% net SE, $70,000) | IRC §404(h) |
| Teacher expense | $300 | IRC §62(a)(2)(D) |
| Student loan int phase-out single | $80k–$95k | IRC §221 |
| Student loan int phase-out MFJ | $165k–$195k | IRC §221 |
| CA standard ded single | $5,540 | FTB 2025 |
| CA standard ded MFJ | $11,080 | FTB 2025 |
| CA Mental Health surtax | 1% on CA TI > $1M | Prop 63 |

---

## Common mistakes — do not repeat

1. **OBBBA deductions reduce taxable income, not AGI.** They are Line 13b (below-the-line). Never add them to `total_adjustments`. Tests 32.2b/32.4b/32.13b verify this.

2. **ODC never goes on Schedule 3 Line 6d.** ODC always routes through Schedule 8812 (`s8812.odc_total`). `sch3['l6d_odc']` is always $0. Rule 2.

3. **QBI (§199A) never goes on Schedule 1.** It is Form 1040 Line 13a, below-the-line. Never add to `total_adjustments`. Rule 1A.

4. **IRA/pension distributions go on 1040 Lines 4b/5b, not Schedule 1.** Rule 1B.

5. **Form 5329 exception code 02 (SEPP) is valid for both IRAs and employer plans.** Code 01 (age-55 separation) is plan-only. Code 06 (QDRO) is plan-only. Codes 07/08/09 are IRA-only. See `PLAN_ONLY_CODES` and `IRA_ONLY_CODES` in engine.

6. **`qbi_min` alias required in PARAMS_2026.** The engine uses `qbi_min_deduction`; tests and 9C audit use `qbi_min`. Both keys must exist.

7. **Every new UI field must go into buildSchema + populateFromSchema + bridge simultaneously.** `_safe_init()` silently drops mismatched names — no error. Rule 5.

8. **W-2 Box 13 belongs on the W-2 form, not the Spouse panel.** The engine derives `covered_by_ret_plan` by scanning all W-2s.

9. **SSA withholding goes on Line 25b, never 25a.** Line 25a is W-2 Box 2 only. Rule 19.

10. **Schedule C has 20 individual expense lines.** Never use a single `total-expenses` field — meals (50%), home office (simplified method cap), and COGS each have distinct rules.

11. **Home office simplified method cannot create a loss.** Cap = gross income from business use. `min(sq_ft, 300) × $5` but further limited to gross income. Rule 24.

12. **Never use secondary tax sources.** TurboTax, tax blogs, cached PDFs. Forms and instructions from `https://www.irs.gov/forms-instructions` only. Rule 15.

---

*End of Implementation Guide · V17.1 · 2026-05-24*
*Gates: `python3 sachintaxcare_test.py` (584/584) · `python3 test_vita_irs.py` (145/145) · `node test_ui_fields.js sachintaxcare_pro.html` (404/404)*
