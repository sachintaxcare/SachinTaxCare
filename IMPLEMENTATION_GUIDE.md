# SachinTaxCare — Implementation Guide
*How to rebuild this project from scratch in one focused effort*
*Current state: Engine v12-fork · UI v1.0+OBBBA · 145/145 tests passing · TY 2025 + TY 2026*
*Last updated: 2026-05-16*

---

## ⚠ OBBBA Update (P.L. 119-21, signed July 4, 2025)

**Critical**: The One Big Beautiful Bill Act changed TY 2025 tax parameters. All six project files were updated 2026-05-10. Key changes:

1. **Standard deductions**: Single $15,750 / HOH $23,625 / MFJ $31,500 (engine `PARAMS_2025`)
2. **CTC**: $2,200/child (up from $2,000; engine `PARAMS_2025["ctc_per_child"]`)
3. **SALT cap**: $40,000 (up from $10,000; phase-down above $500k AGI; `compute_schedule_a()`)
4. **Four new above-line deductions**: Senior Bonus ($6k/person age 65+), Tip ($25k cap), Overtime ($12.5k/$25k cap), Auto Loan Interest ($10k cap) — all in `TaxpayerSchema` + new compute functions
5. **Charitable floor**: 0.5% AGI floor before 60% cap for itemizers (`compute_schedule_a()`)
6. **Tests**: 18 new OBBBA tests in Section 32 of `test_vita_irs.py`; all prior tests updated

Source: Rev. Proc. 2025-32; irs.gov/newsroom/one-big-beautiful-bill-provisions

---

## What this document is

This is a complete blueprint for rebuilding SachinTaxCare without reading any prior session history. It covers architecture, every file, every design decision already made, the exact IRS rules the engine enforces, known limitations, and what to build next. A competent engineer reading this document plus the five source files listed below should be able to fully understand, extend, and maintain the project.

---

## The five files

| File | Lines | Role |
|---|---|---|
| `sachintaxcare_engine.py` | 7,513 | Python computation engine — TY 2025 + TY 2026 |
| `sachintaxcare_pro.html` | **3,911** | Single-file web UI — intake form + dual output modes + import/export |
| `sachintaxcare_server.py` | **563** | Flask server + bridge layer + startup test runner |
| `sachintaxcare_workpaper.html` | **896** | IRS Form 1040-faithful CPA workpaper (4-page layout) |
| `sachintaxcare_test.py` | **632** | Regression + bridge audit test suite — **77/77 PASS** |
| `sachintaxcare_pdf.py` | 367 | PDF output layer — reportlab Form 1040 summary |
| `sachintaxcare_report.py` | 965 | JSON report layer — CPA/EA verification workpaper |
| `test_vita_irs.py` | 2,547 | IRS/VITA known-answer test harness — **145/145 cases**, 0 failures |
| `test_ui_fields.js` | **588** | UI field completeness test — **388 PASS · 0 FAIL · 15 SKIP** |
| `sachintaxcare_field_manifest.md` | **851** | Single source of truth for every form field |

The project has no database, no user accounts, no external API dependencies (beyond optional Anthropic API for Claude mode), and no build step. Everything runs locally.

---

## Architecture

```
Browser (sachintaxcare_pro.html)
    │
    ├── Mode A: Engine mode
    │       └── POST /compute  ──→  Flask server (your app.py)
    │                                    └── sachintaxcare_engine.run(TaxpayerSchema)
    │                                             └── returns dict with computed lines
    │
    └── Mode B: Claude mode
            └── buildPrompt()  ──→  sendPrompt()  ──→  Claude AI (chat window)
                                    (only works inside claude.ai)
```

**Flask server** (`sachintaxcare_server.py`, 563 lines): serves the UI and bridges schema JSON to the engine.

Routes: `GET /` → `sachintaxcare_pro.html` · `GET /workpaper` → `sachintaxcare_workpaper.html` · `POST /compute` → engine.

**Bridge layer** (`deserialize_schema()`): `safe_init()` maps JSON keys → engine dataclass fields by exact name. Any mismatched key is silently dropped. The bridge explicitly translates all known mismatches:
```
box2_discharged → Form1099C.box2_amount_discharged
exclusion_applies → Form1099C.is_excluded  
box6_vol_wh → FormSSA1099.box6_voluntary_wh
age_at_start → SimplifiedMethodData.age_at_annuity_start
box9b_employee_contrib → Form1099R.box9b_employee_contribs
form_1099miscs[].box3 → Form1099MISC_Prize (new list)
```

**Startup tests**: `python3 sachintaxcare_server.py` runs `sachintaxcare_test.py` (77 assertions) before Flask binds. Any bridge or regression failure prints immediately.

**Key constraint**: `sachintaxcare_engine.py` is pure Python with no Flask import. It takes a `TaxpayerSchema` dataclass and returns a plain dict. Keep it that way — it makes testing trivial and the engine reusable in any context.

---

## Export / Import JSON (session persistence)

The topbar has **Export JSON** and **Import JSON** buttons:

- **Export**: `exportJSON()` → calls `buildSchema()` → downloads `sachintaxcare_schema_2025.json`
- **Import**: `importJSON(event)` → reads file → calls `populateFromSchema(sc)`:
  - Clears all dynamic rows and resets all index counters to zero
  - For each array (W-2s, dependents, 1099s, etc.) calls the corresponding `addXxx()` function then sets field values
  - Bridges schema key names to UI field ids (e.g., `institution` → `t-inst-`, `student_is` → `t-who-`)
  - Calls `go('taxpayer')` to navigate to first panel

**Roundtrip guarantee**: every field in `buildSchema()` must have a corresponding entry in `populateFromSchema()` using the same JSON key. Any divergence causes silent data loss. The `sachintaxcare_test.py` Layer 1 bridge audit checks this.

## Regression and bridge tests (sachintaxcare_test.py)

```
python3 sachintaxcare_test.py    # 77 PASS · 0 FAIL
```

Three layers:
1. **Bridge Audit** — asserts each schema↔engine field-name mismatch is documented as a bridge case; verifies engine dataclass fields still exist
2. **Pipeline Regression** — 8 known-schema scenarios run through full bridge→engine→computed pipeline; asserts specific dollar values
3. **Engine Unit** — PARAMS_2025 constants verified against IRS publication values

Add a test whenever: (a) a new bridge mapping is added to the server, (b) a real return reveals a miscalculation, or (c) a new field is added to the engine.

## Workpaper (sachintaxcare_workpaper.html)

IRS Form 1040-faithful 4-page layout:
- Page 1: Taxpayer info, filing status checkboxes, dependents, income lines
- Page 2: Tax, credits, payments, refund/owe, rate summary, signature block  
- Page 3: Schedule 1, Schedule SE, QBI, Schedule A
- Page 4: CPA/EA warnings, pre-filing checklist

Reads `localStorage['sachintaxcare_result']` written by the compute flow. Opened via `GET /workpaper` Flask route. Print/save via browser print (`@page { size: letter }`).

## Engine architecture


### Design principles
1. **No side effects** — `run()` is a pure function. Same input always gives same output.
2. **IRS source on every line** — every computation cites the exact PDF from `irs.gov/pub/irs-pdf/`.
3. **Never interpolate lookup tables** — always read the exact IRS table row.
4. **Whole-dollar rounding at each step** — `rnd()` wraps `round()`, applied after every arithmetic operation, not just at output.
5. **Data classes for every form** — 42 `@dataclass` classes, one per IRS form or schedule. Each field maps to a specific IRS box number documented in the class docstring.

### Computation order (enforced — do not reorder)

The 14-step order is mandated by IRS credit-limit worksheet (CLW) circular dependency rules:

```
Step 1:  Income aggregation
         W-2 Box 1 → Line 1z
         1099-INT Box 1 → Schedule B → Line 2b
         1099-DIV → Schedule B → Lines 3a/3b
         1099-R → Lines 4a/4b (IRA) or 5a/5b (pension)
         SSA-1099 → Lines 6a/6b (Pub 915 Worksheet 1 or lump-sum election)
         Schedule C → Schedule SE → Schedule 1 Line 3
         Schedule E Part I → Form 8582 → Schedule 1 Line 5
         Schedule E Part II (K-1) → Schedule 1 Line 5
         1099-G → Schedule 1 Lines 1/7
         Gambling, prizes, alimony → Schedule 1 Line 8
         Capital gains → Schedule D → Line 7

Step 2:  Above-line adjustments (Schedule 1 Part II)
         SE tax deduction (50%) → Line 15
         SE health insurance → Line 17
         SE retirement → Line 16
         HSA → Line 13
         IRA deduction (with phase-out) → Line 20
         Student loan interest → Line 21
         Teacher expense (max $300) → Line 11

Step 3:  AGI = Line 9

Step 3B: OBBBA Above-Line Deductions (NEW — P.L. 119-21)
         Senior Bonus ($6k/person age 65+), Tip ($25k cap), Overtime ($12.5k/$25k),
         Auto Loan Interest ($10k). All phase out above MAGI thresholds.
         Applied after AGI finalized; further reduce AGI before Step 4.

Step 4:  Deduction — greater of standard or Schedule A
         Standard (OBBBA): $15,750 single/MFS / $31,500 MFJ/QSS / $23,625 HOH
         Add-on: $2,000 blind/65+ (single/HOH) / $1,600 (MFJ/MFS per person)
         SALT cap (OBBBA): $40,000 default / $20,000 MFS; phase-down above $500k AGI
         Charitable (OBBBA): 0.5% AGI floor before 60% cap (itemizers)

Step 5:  QBI deduction → Line 13 (Form 8995)
         min(20% × QBI per business, 20% × ordinary taxable income)
         *** Above $197,300/$394,600: Form 8995-A needed — engine warns, does not compute ***

Step 6:  Taxable income → income tax
         Regular brackets OR QDCGT Worksheet (when qualified div or LTCG > 0)
         HOH uses distinct brackets — NOT same as single

Step 7:  Form 2441 (FIRST credit — sets CLW baseline)
         Employer dep care (W-2 Box 10) reduces qualified expense base
         Earned income test: limited to lower-earning spouse
         Schedule 3 Line 2

Step 8:  Form 8863 (SECOND — education credits)
         AOC: 100% first $2,000 + 25% next $2,000 = max $2,500; 40% refundable → Line 29
         LLC: 20% of up to $10,000 = max $2,000; non-refundable → Schedule 3 Line 3
         MAGI phase-out: $80k–$90k single / $160k–$180k MFJ
         Schedule 3 Line 3 (also adds to CLW for steps 9–10)

Step 9:  Form 8880 (THIRD — saver's credit)
         L4 = 0 (circular dependency: CLW result not yet known)
         Three-column table: Single/MFS/QSS vs HOH vs MFJ
         Schedule 3 Line 4

Step 10: Schedule 8812 / CTC (FOURTH)
         CTC: $2,200 per qualifying child under 17 (OBBBA §70104; valid SSN required)
         Phase-out: $200,000 single / $400,000 MFJ (permanent per OBBBA)
         ACTC refundable: 15% × (earned income − $2,500), cap $1,700/child → Line 28
         CLW uses Schedule 3 total through step 9
         Line 19 (non-refundable) + Line 28 (refundable ACTC)

Step 11: EITC (Schedule EIC)
         *** Engine formula approximates — exact IRS EIC Table required before filing ***
         Use LARGER of earned income or AGI
         Investment income disqualifies if > $11,600
         QSS uses Single/QSS column (not MFJ column)

Step 12: Form 8962 Premium Tax Credit (ACA)
         Monthly method (Lines 12–23) if mid-year coverage change
         Annual method (Line 11) if same plan all 12 months
         Excess APTC repayment → Schedule 2 Line 2
         Net PTC → Schedule 3 Line 9 → Line 31

Step 13: Additional taxes (Schedule 2)
         AMT (Form 6251) → Schedule 2 Line 1
         SE tax → Schedule 2 Line 4
         Form 5329 early distribution penalty → Schedule 2 Line 8
         Additional Medicare 0.9% → Schedule 2 Line 11
         NIIT 3.8% → Schedule 2 Line 12

Step 14: Totals
         Line 24 = income tax + Schedule 2 Line 17
         Line 25a = W-2 Box 2 ONLY
         Line 25b = all other withholding (1099-R, SSA, INT, DIV, NEC, W-2G, G)
         Line 25d = Line 25a + Line 25b
         Line 26 = estimated payments + prior-year overpayment
         Line 32 = Lines 27a+28+29+30+31 ONLY (no other items)
         Line 33 = Line 25d + Line 26 + Line 32
         Line 37 = amount owed (if Line 24 > Line 33)
         Line 34 = refund (if Line 33 > Line 24)
         Line 38 = Form 2210 underpayment penalty (SEPARATE — not in Line 24)
```

### Critical rules that have caused bugs before

These rules were discovered through test failures and must be preserved:

**Withholding line assignment**
```
Line 25a = W-2 Box 2 ONLY — never mix in any other form
Line 25b = 1099-R Box 4 + SSA Box 6 + 1099-INT Box 4 + 1099-DIV Box 4
           + 1099-NEC Box 4 + W-2G Box 4 + 1099-G Box 4
```
Source: `f1040.pdf` Lines 25a–25b; `i1040gi.pdf`

**QSS is not uniformly MFJ** — QSS uses MFJ rates for tax table and standard deduction, but uses Single/QSS column for EITC ($23,350 phaseout vs $30,470 MFJ), Schedule 8812 Line 9 ($200k vs $400k), Form 8880, SS base ($25k vs $32k), NIIT ($200k vs $250k), and Additional Medicare ($200k vs $250k).

**HOH uses distinct tax brackets** — not same as Single. HOH 10% band: $0–$17,000. HOH 12% band: $17,001–$64,850. Source: Rev. Proc. 2024-40.

**SE SS wage base cap** — when taxpayer has both W-2 wages and SE income, available SS base for SE = max(0, $176,100 − W-2 Box 3 wages). Without this, taxpayer double-pays SS on combined wages above $176,100. Source: `f1040sse.pdf` Line 8a.

**Line 38 is not Line 24** — Form 2210 underpayment penalty goes to Line 38, not into Line 24 (total tax). These are separate lines.

**SSA-1099 MFS lived-apart** — MFS taxpayer who lived apart from spouse all year uses $25,000 base (same as single), not $0 (which is the MFS default). Source: `p915.pdf` base amount table.

**1099-R routing** — the IRA/SEP/SIMPLE checkbox on Box 7 (not the Box 7 code) is the authoritative determinant of whether the distribution goes to Lines 4a/4b (IRA) or Lines 5a/5b (pension). Code G/H = direct rollover = not taxable regardless of checkbox.

**CLW circular dependency** — Form 8880 Line 4 must be 0 during computation because the Schedule 3 total it references hasn't been computed yet at that step. This is not a bug; it matches the IRS circular worksheet design.

---

## UI architecture

### Single file, no build step

`sachintaxcare_pro.html` is a self-contained 2,837-line file. No npm, no webpack, no React. Plain HTML/CSS/JS with IBM Plex fonts from Google Fonts.

### Layout

```
┌─────────────────┬──────────────────────────────────────┐
│ Sidebar (260px) │ Topbar (52px sticky)                 │
│                 ├──────────────────────────────────────┤
│  Mode toggle    │ Content panel (active panel shown)   │
│  Nav items      │                                      │
│  (17 sections)  │  Each panel = one tax topic          │
│                 │  One panel visible at a time         │
│  Sidebar rules  │  Panels are divs with display:none   │
└─────────────────┴──────────────────────────────────────┘
```

### Dual output modes

The mode toggle (sidebar, topbar badge) switches between:

**Engine mode** — calls `buildSchema()` → serializes all form data to a JSON object → `POST /compute` → Flask → `engine.run()` → renders result table in the same page. Does not leave the page.

**Claude mode** — calls `buildPrompt()` → builds a ~3,000 word natural-language tax prompt using all form data → `sendPrompt()` → sends to Claude AI in the enclosing claude.ai chat window. Only works when the HTML is served as an artifact inside claude.ai. Falls back gracefully (shows prompt for copy) when run standalone.

### State management

```javascript
const S = {
  fs: 'single',                    // filing status string
  deps: [],                         // dependent row IDs
  w2s: [], ints: [], divs: [],     // 1099 row IDs
  rs: [], scs: [], sales: [],
  cares: [], t1098s: [], sches: [], k1s: [], lumps: [],
  currentPanel: 'taxpayer',
  lastResult: null,
};
```

All repeating rows (W-2s, 1099s, etc.) are added as DOM elements with ids like `w2-box1-0`, `w2-box1-1`. `buildSchema()` and `buildPrompt()` both collect them via `S.w2s.map(id => ...)` or `document.querySelectorAll('[id^="necse-row-"]')`. The state arrays track which row IDs exist so they can be iterated; the actual data lives in the DOM inputs.

### Navigation

`go(panelId)` hides all panels, shows the target panel, updates the nav active state, updates topbar title and progress bar, and calls `buildPreComputeSummary()` when navigating to the compute panel.

17 panels in order:
`taxpayer` → `spouse` → `dependents` → `w2` → `1099s` → `se` → `rental` → `k1` → `capgains` → `other-inc` → `adj` → `scheda` → `credits` → `retirement` → `advanced` → `ca540` → `compute`

---

## Field manifest and test script

### The contract

`sachintaxcare_field_manifest.md` is the single source of truth for every field in the project. It maps:
- Every IRS form box → HTML element id → engine dataclass field → IRS form line → source PDF

**The rule**: any session that adds a field to the engine **must** add a row to the manifest before touching the UI. Any session that adds the UI field changes the status from ❌ to ✅.

Current counts: 325 ✅ (in UI) · 26 ❌ (known gaps, not in UI) · 3 ⚠ (captured, not computed)

### Running tests

```bash
# Engine tests (Python)
python3 test_vita_irs.py
# Expected: 59 PASS, 0 FAIL

# UI field tests (Node.js)
node test_ui_fields.js sachintaxcare_pro.html
# Expected: 325 PASS, 0 FAIL, 22 SKIP (known gaps), 2 WARN
```

Both tests must pass before any session is considered complete.

---

## Known limitations (as of v11-fork + OBBBA, 2026-05-10)

These are documented limitations in the current engine, not bugs:

| Item | Impact | Fix complexity |
|---|---|---|
| EITC uses formula approximation | Off by $0–$100 for most cases | Medium — embed exact IRS EIC table |
| Form 8995-A not built | QBI deduction wrong for income > $197k single / $394k MFJ | High — per-business W-2 wages + UBIA calculation |
| K-1 basis / at-risk limits not enforced | K-1 losses may be overstated | High — Form 6198, §704(d) outside basis |
| Form 2210 uses annual rate | Penalty estimate may be higher than actual | Medium — quarter-by-quarter calculation |
| IRA MAGI proxy | Off by small amount when student loan or SE income present | Low — add back student loan + ½ SE tax |
| 1099-DIV Box 2b §1250 / Box 2d collectibles captured not computed | Rate capped at 25%/28% not enforced | Medium |
| CA Schedule CA partial | CalEITC, Young Child Tax Credit, community property not built | High |
| Form 5329 SEPP Code 01 not validated | Engine accepts claimed amount without computing annuity | Medium |

---

## What to build next (priority order)

### P1 — PDF output layer (🔴 High — user-facing)

All computed values exist in `result["computed"]`. Need a rendering layer.

**Recommended path**: reportlab (Python) generating IRS-look-alike PDFs.

```python
# Engine already returns this structure:
result["computed"] = {
    "agi": 85000,
    "taxable_income": 54000,
    "income_tax": 6120,
    "l19_ctc": 4000,
    "l34_refund": 1240,
    # ... all 1040 lines
}
```

Build `sachintaxcare_pdf.py` (file already exists in project, check current state) that takes `result["computed"]` and generates a formatted PDF. One session.

### P2 — JSON export (🔴 High)

Serialize `result["computed"]` to structured JSON:

```json
{
  "federal": {
    "form_1040": { "line_1z": 85000, "line_11": 85000, "line_34": 1240 },
    "schedule_c": [{ "business": "Consulting", "net_profit": 45000 }],
    "schedule_a": { "mortgage_interest": 12000, "state_taxes": 8500 }
  },
  "state": { "ca_540": { "ca_taxable_income": 80000, "ca_tax": 3200 } },
  "warnings": ["EITC formula approximation — verify with IRS EIC Table"]
}
```

Add a Flask route `/export` and a download button in the UI. One session.

### P3 — Form 8995-A (🔴 High — affects high-income SE filers)

Triggered when taxable income > $197,300 single / $394,600 MFJ.

What needs to be built in the engine:
- Per-business W-2 wages (already captured in `ScheduleC.w2_wages`)
- Per-business UBIA (already captured in `ScheduleC.ubia_qualified_property`)
- W-2 wage limitation: min(50% of W-2 wages, QBI deduction) or (25% W-2 wages + 2.5% UBIA)
- SSTB phase-out for specified service trades (law, accounting, health, consulting, etc.)

Source: `f8995a.pdf`; Reg. §1.199A-1 through -6.

### P4 — CA Schedule CA + CalEITC (🔴 High — CA-specific)

What needs to be built:
- `compute_caleitc()` — separate from federal, much lower income thresholds
- Young Child Tax Credit: $1,117 per child under 6 for CalEITC-eligible filers
- CA Schedule CA full line-by-line income adjustments (conformity differences from federal)
- Community property rules: MFS filers in CA must split community income 50/50

Sources: `ftb.ca.gov/forms/2025/2025-3514.pdf` (CalEITC); `ftb.ca.gov/forms/2025/2025-540-ca.pdf`

### P5 — EITC exact table (🟡 Medium)

Replace the formula approximation with the exact IRS EIC Table lookup. The table is in `p1040.pdf` pages 16+. Embed as a Python dict keyed by (filing_status, num_children, income_band). Engine already has a flag `exact_eitc_from_table` that overrides the formula when the user provides the confirmed value from the IRS table.

### P6 — Multi-state skeleton (🟠 Lower)

After CA is complete, build a generic state return framework that handles income routing and bracket calculation. NY, FL (no income tax — trivial), WA (no income tax — trivial), NJ. Each state gets a `compute_state_xxx()` function following the CA pattern.

### P7 — UI panel completion tracking (🟢 Deferred)

CSS is already written (`.nav-item.done` with gold checkmark `::after`). Add completion logic to `go()`:

```javascript
function isPanelComplete(panelId) {
  // Check required fields for each panel
  // Return true when minimum required fields are filled
}
// In go():
if (isPanelComplete(S.currentPanel)) {
  document.getElementById('nav-' + S.currentPanel).classList.add('done');
}
```

---

## IRS source document index

Always fetch from `irs.gov/pub/irs-pdf/` — never use secondary sources.

| Document | URL fragment | Used for |
|---|---|---|
| Form 1040 | `f1040.pdf` | Main return line numbers |
| Form 1040 Instructions | `i1040gi.pdf` | Line-by-line guidance, tax table |
| Schedule 1 | `f1040s1.pdf` | Additional income and adjustments |
| Schedule 2 | `f1040s2.pdf` | Additional taxes |
| Schedule 3 | `f1040s3.pdf` | Additional credits |
| Schedule A | `f1040sa.pdf` + `i1040sa.pdf` | Itemized deductions |
| Schedule B | `f1040sb.pdf` | Interest and dividends |
| Schedule C | `f1040sc.pdf` + `i1040sc.pdf` | Business profit/loss |
| Schedule D | `f1040sd.pdf` | Capital gains |
| Schedule E | `f1040se.pdf` + `i1040se.pdf` | Supplemental income |
| Schedule SE | `f1040sse.pdf` | SE tax |
| Form 8949 | `f8949.pdf` | Capital asset sales |
| Form 2441 | `f2441.pdf` + `i2441.pdf` | Child/dep care credit |
| Form 8863 | `f8863.pdf` + `i8863.pdf` | Education credits |
| Form 8880 | `f8880.pdf` | Saver's credit |
| Schedule 8812 | `f1040s8.pdf` | CTC/ACTC |
| Form 8962 | `f8962.pdf` + `i8962.pdf` | Premium tax credit |
| Form 8995 | `f8995.pdf` | QBI deduction (below threshold) |
| Form 8995-A | `f8995a.pdf` | QBI deduction (above threshold) — not yet built |
| Form 6251 | `f6251.pdf` + `i6251.pdf` | AMT |
| Form 8606 | `f8606.pdf` + `i8606.pdf` | Nondeductible IRA / Roth |
| Form 8889 | `f8889.pdf` + `i8889.pdf` | HSA |
| Form 8582 | `f8582.pdf` + `i8582.pdf` | Passive activity losses |
| Form 5329 | `f5329.pdf` + `i5329.pdf` | Early distributions |
| Form 1116 | `f1116.pdf` + `i1116.pdf` | Foreign tax credit |
| Form 4797 | `f4797.pdf` + `i4797.pdf` | Sale of business property |
| Form 4972 | `f4972.pdf` + `i4972.pdf` | Lump-sum distribution |
| Form 8615 | `f8615.pdf` + `i8615.pdf` | Kiddie tax |
| Form 8960 | `f8960.pdf` | NIIT |
| Form 8959 | `f8959.pdf` | Additional Medicare Tax |
| Form 2210 | `f2210.pdf` + `i2210.pdf` | Underpayment penalty |
| Form W-2 | `fw2.pdf` + `iw2w3.pdf` | Wages |
| Form 1099-INT | `f1099int.pdf` + `i1099int.pdf` | Interest |
| Form 1099-DIV | `f1099div.pdf` + `i1099div.pdf` | Dividends |
| Form 1099-R | `f1099r.pdf` + `i1099r.pdf` | Retirement distributions |
| Form 1099-NEC | `f1099nec.pdf` + `i1099nec.pdf` | Nonemployee comp |
| Form 1099-B | `f1099b.pdf` | Broker transactions |
| Form 1099-G | `f1099g.pdf` + `i1099g.pdf` | Government payments |
| Form 1099-C | `f1099c.pdf` | Cancellation of debt |
| Form W-2G | `fw2g.pdf` + `iw2g.pdf` | Gambling winnings |
| Pub 590-A | `p590a.pdf` | IRA contributions |
| Pub 575 | `p575.pdf` | Simplified Method (annuities) |
| Pub 915 | `p915.pdf` | Social Security taxability |
| Rev. Proc. 2024-40 | IRS website | 2025 inflation adjustments |
| CA Form 540 | `ftb.ca.gov/forms/2025/2025-540.pdf` | California return |

---

## Session workflow for new features

Every new feature session follows this checklist:

```
1. Read sachintaxcare_field_manifest.md — understand current field coverage
2. Fetch the relevant IRS PDF from irs.gov/pub/irs-pdf/ before writing any code
3. Add new @dataclass fields to engine.py with IRS source citations in the docstring
4. Add new rows to sachintaxcare_field_manifest.md with status ❌
5. Write the compute_xxx() function in engine.py
6. Wire the compute function into run() at the correct step in the 14-step order
7. Add test cases to test_vita_irs.py with exact expected values from IRS publications
8. Run python3 test_vita_irs.py — must show 0 FAIL before proceeding to UI
9. Add the UI fields to sachintaxcare_pro.html
10. Update manifest status from ❌ to ✅
11. Run node test_ui_fields.js sachintaxcare_pro.html — must show 0 FAIL
12. Update TaxReturn_PlanningReference.md with the session summary
```

**Hard rule**: no field goes into the engine without a test case. No test case uses secondary sources — only IRS publications with page and example citations.

---

## 2025 tax parameters quick reference

*Updated 2026-05-10 with OBBBA (P.L. 119-21) changes. Source: Rev. Proc. 2025-32.*

| Parameter | Value | Source |
|---|---|---|
| Standard deduction single/MFS | **$15,750** (was $15,000) | Rev. Proc. 2025-32; OBBBA §70102 |
| Standard deduction MFJ/QSS | **$31,500** | Rev. Proc. 2025-32; OBBBA §70102 |
| Standard deduction HOH | **$23,625** (was $22,500) | Rev. Proc. 2025-32; OBBBA §70102 |
| Blind/65+ add-on (single/HOH) | $2,000 | Rev. Proc. 2024-40 |
| Blind/65+ add-on (MFJ per person) | $1,600 | Rev. Proc. 2024-40 |
| CTC per qualifying child | **$2,200** (was $2,000) | OBBBA §70104; IRC §24(h)(2) as amended |
| ACTC cap per child | $1,700 | Rev. Proc. 2024-40 (unchanged 2025) |
| ACTC refundable rate | 15% × (earned − $2,500) | IRC §24(d) |
| CTC phase-out (single) | Starts at $200,000 | IRC §24(b); permanent per OBBBA |
| CTC phase-out (MFJ) | Starts at $400,000 | IRC §24(b); permanent per OBBBA |
| ODC (other dependent credit) | $500 | IRC §24(h)(4); permanent per OBBBA |
| SALT cap (default) | **$40,000** (was $10,000) | OBBBA §70106; IRC §164(b)(6) as amended |
| SALT cap (MFS) | **$20,000** (was $5,000) | OBBBA §70106 |
| SALT phase-down threshold | AGI $500,000 | OBBBA §70106 |
| SALT phase-down rate | $50 per $1,000 AGI above threshold | OBBBA §70106 |
| SALT floor (minimum cap) | $10,000 | OBBBA §70106 |
| Charitable AGI floor (itemizers) | **0.5% of AGI** (new) | OBBBA; IRC §170 as amended |
| Senior Bonus Deduction | **$6,000/qualifying person age 65+** (new) | OBBBA §70103 |
| Senior Bonus phase-out | MAGI > $75k single / $150k MFJ | OBBBA §70103 |
| Tip income deduction cap | **$25,000** (new) | OBBBA §70201 |
| Tip income phase-out | MAGI > $150k single / $300k MFJ | OBBBA §70201 |
| Overtime pay deduction cap | **$12,500 single / $25,000 MFJ** (new) | OBBBA §70202 |
| Overtime phase-out | MAGI > $150k single / $300k MFJ | OBBBA §70202 |
| Auto loan interest deduction cap | **$10,000/yr** (new) | OBBBA §70301 |
| Auto loan phase-out | MAGI > $100k single / $200k MFJ | OBBBA §70301 |
| SS wage base | $176,100 | SSA 2025 |
| SE tax rate | 15.3% × 92.35% of net profit | IRC §1401 |
| Additional Medicare threshold (single) | $200,000 | IRC §3103 |
| Additional Medicare threshold (MFJ) | $250,000 | IRC §3103 |
| NIIT threshold (single) | $200,000 | IRC §1411 |
| NIIT threshold (MFJ) | $250,000 | IRC §1411 |
| NIIT rate | 3.8% | IRC §1411 |
| AMT exemption (single) | $88,100 | Rev. Proc. 2024-40; permanent per OBBBA §70107 |
| AMT exemption (MFJ) | $137,000 | Rev. Proc. 2024-40; permanent per OBBBA §70107 |
| AMT phase-out starts (single) | $626,350 | Rev. Proc. 2024-40 |
| AMT phase-out starts (MFJ) | $1,252,700 | Rev. Proc. 2024-40 |
| QBI threshold (single) | $197,300 | Rev. Proc. 2024-40; permanent per OBBBA |
| QBI threshold (MFJ) | $394,600 | Rev. Proc. 2024-40; permanent per OBBBA |
| EITC investment income limit | $11,600 | Rev. Proc. 2024-40 |
| HSA limit (self-only) | $4,300 | Rev. Proc. 2024-40 |
| HSA limit (family) | $8,550 | Rev. Proc. 2024-40 |
| HSA catch-up (55+) | $1,000 | IRC §223(b)(3) |
| 401(k) elective deferral limit | $23,500 | IRS IR-2024-285 |
| IRA contribution limit | $7,000 ($8,000 if 50+) | IRC §219(b)(5) |
| SEP-IRA limit | min(25% net SE, $70,000) | IRC §404(h) |
| Teacher expense max | $300 | IRC §62(a)(2)(D) |
| CA standard deduction (single) | $5,540 | FTB 2025 |
| CA standard deduction (MFJ) | $11,080 | FTB 2025 |
| CA Mental Health surtax | 1% on CA taxable income > $1M | Prop 63 |

---

## Common implementation mistakes to avoid

These mistakes have been made in this project and corrected — don't repeat them:

1. **Putting W-2 Box 13 on the Spouse panel** — it belongs on the W-2 form itself. The engine derives `w2_box13_ret_plan` by scanning all spouse-tagged W-2 entries.

2. **Using a single `total-expenses` field for Schedule C** — Schedule C has 20 individual expense lines, each with different tax treatment (meals at 50%, home office via Rev. Proc. 2013-13, etc.). A single field loses all of this.

3. **Hardcoding `decree_pre_2019: True` for alimony** — post-2018 divorce agreements produce zero deduction/income. The UI must have an era dropdown.

4. **Computing ODC as a manual dropdown** — ODC is deterministic from DOB + CTC status. If age ≥ 17 and not CTC-eligible, ODC = yes. Auto-compute it and show the result.

5. **Two files tracking the same data** — the widget and intake were built independently and drifted apart over 9 sessions. This is why the field manifest exists. One UI file, one manifest, one test script.

6. **Not running the test harness after engine changes** — the 59 test cases catch regressions in credit ordering, withholding routing, and QSS/HOH distinctions that are easy to break.

7. **Using secondary tax sources** — TurboTax help pages and tax blogs sometimes contain errors or use simplified explanations. Every number must trace back to an IRS publication with a page number.

---

*End of implementation guide · v1.0 · 2025-05-10*
*For current test status: `python3 test_vita_irs.py` and `node test_ui_fields.js sachintaxcare_pro.html`*
