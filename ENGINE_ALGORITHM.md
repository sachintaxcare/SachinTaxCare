# SachinTaxCare — Engine Algorithm & Code Flow
*Authoritative description of how the engine computes a TY 2025/2026 federal + CA return*
*Engine V17.1 · 42 compute functions · 40 dataclasses · 1,606 IRS citations · Updated 2026-05-24*

---

## Entry point

```python
result = sachintaxcare_engine.run(schema: TaxpayerSchema) -> dict
```

- **Input**: one `TaxpayerSchema` dataclass (40 nested dataclasses, 84 top-level fields, 515+ total fields)
- **Output**: `{"computed": {...155+ keys}, "warnings": [...], "steps": {...}, "schema": {...}}`
- **Pure function**: no side effects, no DB, no network, no global state
- Same input always produces identical output

`result["computed"]` contains every Form 1040 line. `result["warnings"]` contains IRS-sourced advisory messages. The Flask server serializes `result["computed"]` as JSON and returns it to the browser.

---

## Design principles

1. **IRS source on every formula line** — `# Source: f1040.pdf L11; IRC §63`
2. **Whole-dollar rounding at each step** — `rnd() = round()` after every arithmetic operation, never accumulate fractions
3. **Never interpolate lookup tables** — always read the exact IRS table row (EIC, Pub 575 SM, Form 2441 rate table)
4. **40 dataclasses, one per IRS form** — each field maps to a specific IRS box number in the docstring
5. **Computation order is fixed** — mandated by IRS Credit Limit Worksheet circular dependency

```python
def rnd(v): return round(v)
# Correct:  wages = rnd(sum(w.box1_wages for w in schema.w2s))
# Wrong:    wages = sum(w.box1_wages for w in schema.w2s)  # fractions accumulate
```

---

## PARAMS_2025 and PARAMS_2026

All dollar constants and rates are stored in two dicts, never hardcoded in compute functions:

```python
PARAMS_2025 = {
    "std_deduction":   {"single": 15750, "mfj": 31500, "hoh": 23625, "mfs": 15750, "qss": 31500},
    "ctc_per_child":   2200,
    "actc_cap_per_child": 1700,
    "salt_cap_default": 40000,
    "salt_cap_mfs":    20000,
    "ss_wage_base_2025": 176100,
    "standard_mileage_rate_2025": 0.70,
    "eitc": {...},          # per filing status × child count
    "tax_brackets_single": [...],
    "qdcgt_0pct_single": 47025,
    ...  # 128 keys total
}

PARAMS_2026 = {
    "std_deduction":   {"single": 16100, "mfj": 32200, ...},
    "ctc_per_child":   2300,
    "qbi_min_deduction": 400,
    "qbi_min":         400,   # alias — both keys must exist
    ...  # 153 keys total
}
```

The engine selects `p = PARAMS_2025 if schema.tax_year == 2025 else PARAMS_2026` at the start of `run()`.

---

## All 40 dataclasses

| Dataclass | Fields | IRS source |
|---|---|---|
| `TaxpayerSchema` | 84 | Master schema — all forms and top-level fields |
| `W2` | 33 | fw2.pdf — all 20 boxes |
| `Form1099INT` | 20 | f1099int.pdf |
| `Form1099DIV` | 19 | f1099div.pdf — Box 5 §199A divs critical for QBI |
| `Form1099R` | 34 | f1099r.pdf — all 19 boxes + routing flags |
| `Form1099NEC` | 7 | f1099nec.pdf |
| `Form1099B` | 12 | f1099b.pdf |
| `Form1099G` | 7 | f1099g.pdf |
| `Form1099C` | 10 | f1099c.pdf — `box2_amount_discharged`, `is_excluded` |
| `Form1099MISC_Prize` | 3 | f1099misc.pdf Box 3 |
| `FormSSA1099` | 13 | SSA-1099 — `box6_voluntary_wh` critical for L25b |
| `FormW2G` | 5 | fw2g.pdf |
| `SimplifiedMethodData` | 9 | p575.pdf Worksheet A |
| `Form1098T` | 16 | f1098t.pdf — `box8_half_time`, `aoc_drug_conviction` gates |
| `Form1098E` | 4 | f1098e.pdf |
| `Form1095A` | 8 | f1095a.pdf |
| `Form1095AMonth` | 3 | f1095a.pdf monthly rows |
| `Form5329Exception` | 6 | f5329.pdf Part I Line 2 |
| `Form8606Data` | 12 | f8606.pdf — nondeductible IRA basis |
| `Form8889Data` | 12 | f8889.pdf — HSA |
| `Form8880Data` | 3 | f8880.pdf — saver's credit |
| `Form8582Data` | 2 | f8582.pdf — passive activity |
| `Form8615Data` | 7 | f8615.pdf — kiddie tax |
| `Form6251Data` | 6 | f6251.pdf — AMT preferences |
| `Form4972Data` | 7 | f4972.pdf — lump-sum distribution |
| `Form4797SaleData` | 12 | f4797.pdf — §1231/§1245/§1250 |
| `Form1116Data` | 10 | f1116.pdf — foreign tax credit |
| `Form982Data` | 4 | f982.pdf — cancellation of debt |
| `Form2441Provider` | 4 | f2441.pdf — care provider |
| `Form2210Data` | 5 | f2210.pdf — underpayment |
| `ScheduleC` | 47 | f1040sc.pdf — business income/expenses |
| `ScheduleE` | 24 | f1040se.pdf — rental |
| `ScheduleK1` | 34 | f1065sk1.pdf / f1120sk1.pdf |
| `ScheduleAData` | 16 | f1040sa.pdf |
| `CaliforniaData` | 16 | FTB 540 |
| `AlimonyData` | 5 | Pub 504 |
| `EstimatedTaxPayments` | 15 | f1040es.pdf (4 quarters + prior overpayment) |
| `DeceasedSpouse` | 3 | f1040.pdf |
| `SSALumpSumPriorYear` | 9 | p915.pdf Worksheet 2 |
| `Dependent` | 9 | f1040.pdf — CTC/ODC/HOH |

---

## All 42 compute functions

```
compute_tax()                    — income tax via bracket schedule or QDCGT worksheet
compute_qdcgt_tax()              — QDCGT/qualified dividends worksheet; §1250/collectibles rates
compute_senior_deduction()       — OBBBA §70103 ($6k, age 65+, MAGI phase-out)
compute_tip_deduction()          — OBBBA §70201 ($25k cap, occupation required, phase-out)
compute_overtime_deduction()     — OBBBA §70202 ($12.5k/$25k MFJ, FLSA §207 required)
compute_auto_loan_deduction()    — OBBBA §70301 ($10k cap, new US vehicle, phase-out)
compute_simplified_method()      — Pub 575 Worksheet A (Simplified Method for annuities)
compute_ss_lump_sum_election()   — Pub 915 Worksheet 2 (lump-sum prior-year election)
compute_ss_taxable()             — Pub 915 Worksheet 1 (SS provisional income → 0/50/85%)
compute_aoc()                    — Form 8863 AOC ($2,500; 40% refundable; 4-year limit; drug gate)
compute_llc()                    — Form 8863 LLC ($2,000 non-refundable; phase-out)
compute_eitc()                   — §32 EITC ($50-band IRS table algorithm; investment income gate)
compute_student_loan_deduction() — IRC §221 ($2,500; MAGI phase-out)
compute_schedule_c_se()          — Schedule C all 20 expense lines + SE tax; home office cap
compute_qbi_deduction()          — Form 8995 §199A (Lines 1–15 incl. REIT/PTP Lines 6–9)
compute_se_health_insurance()    — Schedule 1 Line 17 (SE health ins. deduction)
compute_se_retirement()          — Schedule 1 Line 16 (SEP/SIMPLE/solo 401k)
compute_cogs()                   — Schedule C Part III COGS
compute_ira_deduction()          — Pub 590-A (deductible IRA; covered/noncovered phase-outs)
compute_form_8889()              — Form 8889 (HSA contribution/distribution)
compute_niit()                   — Form 8960 (3.8% NIIT on NII above threshold)
compute_additional_medicare_tax() — Form 8959 (0.9% AdMedTax on wages/SE above threshold)
compute_form_2210_safe_harbor()  — Form 2210 (underpayment safe harbor; Line 38)
compute_form_982()               — Form 982 (COD exclusion; insolvency/bankruptcy)
compute_k1_income()              — K-1 all income types (ordinary, rental, §179, §199A, cap gain)
compute_caleitc()                — CA CalEITC + YCTC (FTB Schedule EITC)
compute_california_540()         — CA Form 540 (CA-specific conformity, OBBBA addbacks)
compute_schedule_b()             — Schedule B (interest/dividend totals; foreign account flags)
compute_schedule_e_8582()        — Schedule E Part I + Form 8582 (passive activity loss limits)
compute_form_6251()              — Form 6251 AMT (preferences, AMTI, exemption, 26%/28% rates)
compute_form_8615()              — Form 8615 Kiddie Tax (unearned income > threshold)
compute_form_4797()              — Form 4797 (§1231 gain/loss; §1245 recapture; §1250 recapture)
compute_nol_detection()          — IRC §172 NOL detection and 80% carryforward limit
compute_f8962()                  — Form 8962 (ACA PTC; monthly Lines 12–23; APTC reconciliation)
compute_f5329_exceptions()       — Form 5329 Parts I–X (exception codes 01–12; IRA-only/plan-only)
compute_f1116()                  — Form 1116 FTC (de minimis ≤$300; proportionate share limit)
compute_schedule_a()             — Schedule A (SALT $40k cap; mortgage $750k limit; charitable 60%)
compute_form_8949_schd()         — Form 8949/Schedule D (ST/LT; §1250 25%; collectibles 28%)
compute_form_8606()              — Form 8606 Parts I/II (nondeductible IRA pro-rata; Roth conversion)
compute_form_4972()              — Form 4972 (lump-sum; 10-year and 20% capital gain treatments)
```

---

## The 14-step computation order

**This order is fixed.** It is mandated by the IRS Credit Limit Worksheet (CLW) circular dependency. Changing it breaks credit calculations.

```
Step 1:   Income aggregation
          W-2, 1099-INT, 1099-DIV, 1099-NEC, Schedule C/SE,
          1099-R, Form 8606, SSA-1099, Form 8949/Schedule D,
          Form 4797, Schedule B, Schedule E/Form 8582,
          Schedule K-1, Form 4972, Form 982, gambling, unemployment,
          alimony, state refund, allocated tips, cancelled debt

Step 2:   Above-line adjustments (partial — before AGI)
          Teacher ($300), early withdrawal penalty (Sch 1 L18),
          SE tax deduction (½ SE tax → Sch 1 L15),
          SE health insurance (Sch 1 L17),
          SE retirement (Sch 1 L16),
          IRA deduction (Pub 590-A phase-outs),
          HSA (Form 8889),
          Alimony paid (pre-2019 decrees only)

Step 3:   AGI and SS taxability
          student loan deduction (requires pre-SS AGI for phase-out)
          total_adjustments = Σ(above-line items — QBI NOT included)
          agi_pre_ss = total_income_pre_ss − total_adjustments
          SS taxability (Pub 915 Worksheet 1 or lump-sum election)
          NOL deduction (IRC §172 — adjusts agi directly)
          agi = total_income − total_adjustments

          ── OBBBA BELOW-LINE DEDUCTIONS (L13b — do NOT reduce AGI) ──
          MAGI = agi  (used for all OBBBA phase-out tests)
          adj_senior = compute_senior_deduction(...)
          adj_tips   = compute_tip_deduction(...)
          adj_overtime = compute_overtime_deduction(...)
          adj_auto   = compute_auto_loan_deduction(...)
          obbba_total = adj_senior + adj_tips + adj_overtime + adj_auto

Step 4:   Deduction and taxable income
          std_ded = PARAMS[fs] + age/blind add-on
          Schedule A (if itemizing)
          deduction_used = max(std_ded, itemized)
          taxable = max(0, agi − deduction_used)
          taxable = max(0, taxable − obbba_total)    ← Line 13b
          taxable = max(0, taxable − adj_qbi)        ← Line 13a (QBI)

Step 5:   Income tax · AMT · Kiddie Tax
          income_tax = compute_qdcgt_tax(taxable, ...)   ← QDCGT worksheet if qualified income
          Form 6251 AMT (computed against AMTI, not taxable income)
          Form 8615 Kiddie Tax (replaces income_tax if applicable)
          Form 4972 lump-sum additional tax
          NIIT (Form 8960)
          Additional Medicare Tax (Form 8959)

Step 6:   Form 2441 — child/dependent care (FIRST in CLW)
          Care credit reduces income_tax. Sets CLW L2 baseline.
          Form 2441 Line 6 deemed income: disabled/student spouse
          Employer dep care exclusion (W-2 Box 10) reduces cap

Step 7:   Form 8863 — education credits (SECOND in CLW)
          AOC: $2,500 (40% refundable); 3 hard gates
          LLC: $2,000 (non-refundable); phase-out
          Goes to Sch 3 L3 → sch3_l8

Step 8:   Form 8880 — saver's credit (THIRD in CLW)
          Rate table by filing status + AGI
          Goes to Sch 3 L4 → sch3_l8

Step 9:   Schedule 8812 — CTC / ACTC / ODC (FOURTH in CLW)
          CTC: $2,200/child, phase-out at $200k/$400k
          ACTC: 15% × (earned − $2,500), cap $1,700/child
          ODC: $500/other dependent (ALWAYS through 8812, never Sch 3)
          CLW applies credits in order: care → edu → saver → CTC

Step 10:  Schedule 3 Part I — nonrefundable credits
          Form 1116 FTC (computed here — reduces tax_after)
          sch3_l8 = care + edu + saver + ODC + FTC
          tax_after = max(0, income_tax − l14_ctc − sch3_l8)

Step 11:  EITC
          compute_eitc() — $50-band IRS table algorithm
          Investment income gate: >$11,600 disqualifies (Rule 21)
          Goes to Line 27a

Step 12:  Form 8962 — Premium Tax Credit
          ACA marketplace reconciliation
          Net PTC → Sch 3 L9 → L31

Step 13:  Form 5329 · Schedule 2 · Schedule 3 Part II
          Form 5329: early distribution penalty (after exception codes)
          Schedule 2: SE tax + AMT + NIIT + AdMedTax + 5329 + 4972
          sch2_l17 = total other taxes → Line 23

Step 14:  Form 1040 totals
          l24_total_tax = tax_after + sch2_l17
          l25a = W-2 Box 2 ONLY
          l25b = 1099-R + SSA + INT + DIV + NEC + B + W-2G + 1099-G backup WH
          l26  = estimated tax payments + prior year overpayment
          l27a = EITC  l28 = ACTC  l29 = AOC refundable  l31 = net PTC
          l33  = l25d + l26 + l27a + l28 + l29 + l31
          l34_refund = max(0, l33 − l24)
          l37_owe    = max(0, l24 − l33)
          Form 2210 underpayment → Line 38 (NOT part of Line 24)
          California Form 540 (CA does not conform to OBBBA — addbacks required)
```

---

## Step-by-step detail

### Step 1A — W-2

```python
wages             = Σ(w2.box1_wages)                  → Line 1z
fed_wh            = Σ(w2.box2_fed_wh)                 → Line 25a ONLY (nothing else)
allocated_tips    = Σ(w2.box8_allocated_tips)          → Schedule 1 Line 8
employer_dep_care = Σ(w2.box10_dependent_care)         → Form 2441 Line 12
covered_by_plan   = ANY(w2.box13_retirement_plan)      → IRA phase-out test
w2_ss_wages       = Σ(w2.box3_ss_wages)               → SE SS wage base cap
w2_code_w         = Σ(w2.box12_code_w)                → HSA employer contributions
```

### Step 1B — 1099-INT / Schedule B

```python
interest          = Σ(box1_interest)                  → Schedule B → Line 2b
adj_early_wdwl    = Σ(box2_early_withdrawal_penalty)  → Schedule 1 Line 18 (NOT Line 8)
us_bond_interest  = Σ(box3_us_savings_bond)           → included in Line 2b (state-exempt)
int_backup_wh     = Σ(box4_fed_wh)                    → Line 25b (backup WH)
tax_exempt_int    = Σ(box8_tax_exempt_interest)       → Line 2a + SS provisional income
```

### Step 1C — 1099-DIV

```python
dividends         = Σ(box1a_ordinary_div)             → Schedule B → Line 3b
dividends_qual    = Σ(box1b_qualified_div)            → Line 3a (QDCGT 0/15/20% rates)
div_cap_gain_dist = Σ(box2a_total_cap_gain)           → Schedule D Line 13
div_backup_wh     = Σ(box4_fed_wh)                   → Line 25b
sec199a_divs      = Σ(box5_sec199a_div)              → Form 8995 Line 6 (REIT component)
```

### Step 1D — 1099-NEC + Schedule C

```python
# 1099-NEC Box 1 routes to Schedule C gross income (NOT prize income)
compute_schedule_c_se(schedule_cs, PARAMS, w2_ss_wages):
  for each ScheduleC:
    cogs = inventory_beg + purchases + labor + materials − inventory_end
    meals_deductible = meals × 0.50          # 50% limitation IRC §274
    home_office = min(sq_ft, 300) × 5        # Rev. Proc. 2013-13; cannot create loss
    home_office = min(home_office, gross_income_from_business_use)
    net_profit = gross − returns − cogs − expenses − home_office
    if net_profit > 0:
      net_earnings_se = net_profit × 0.9235
      available_ss = max(0, ss_wage_base − w2_ss_wages)  # critical cap
      se_ss_taxable = min(net_earnings_se, available_ss)
      se_tax = se_ss_taxable × 0.124 + net_earnings_se × 0.029
  se_tax_deduction = se_tax × 0.50           → Schedule 1 Line 15
  se_net_profit = Σ(net_profits)             → Schedule 1 Line 3 (Line 8 in some versions)
```

### Step 1E — 1099-R (pension/IRA distributions)

```python
# Routing: box7_ira_sep_simple is authoritative (not box7_code)
for each Form1099R:
  if box7_code in ("G","H"): SKIP  # direct rollover
  if box7_code == "Q":       SKIP  # qualified Roth
  taxable = box2a_taxable  (box2b_not_determined → 0 + warning)
  taxable -= box6_nua              # NUA excluded → LTCG when sold
  if simplified_method and box9b_employee_contribs > 0:
    taxable = compute_simplified_method(sm, taxable)  # Pub 575 Worksheet A
  if box7_code == "1":  penalty += taxable × 0.10  # early dist
  if box7_code == "S":  penalty += taxable × 0.25  # SIMPLE < 2yr
  if box7_ira_sep_simple: l4b += taxable  else: l5b += taxable
```

### Step 1F — Form 8606 (nondeductible IRA basis)

```python
# Per spouse — NEVER aggregate (Rule 22)
l3 = nonded_contrib_this_year + basis_prior_year
l6 = trad_ira_value_dec31 + distributions
l8_nontaxable = l3 / l6 × distributions   # pro-rata rule
l4b = max(0, l4b − l8_nontaxable)         # adjusts Line 4b
```

### Step 1G — SSA-1099

```python
ss_net   = box5_net_benefits               → Line 6a
ss_wh    = box6_voluntary_wh              → Line 25b  (bridge: box6_vol_wh → box6_voluntary_wh)
# SS taxability computed in Step 3 (requires pre-SS AGI first)
```

### Step 1H — Capital gains (Form 8949 / Schedule D)

```python
compute_form_8949_schd(form_1099bs):
  short_term_gain/loss = Σ(proceeds − cost for ST sales)
  long_term_gain/loss  = Σ(proceeds − cost for LT sales)
  sec1250_unrecap_gain  → taxed at max 25%  (unrecaptured §1250 depreciation)
  collectibles_gain     → taxed at max 28%
  net_ltcg = long_term_net + cap_gain_distributions (1099-DIV Box 2a)
  # Both sec1250 and collectibles reduce pool for 0/15/20% QDCGT rates
```

### Step 3 — AGI critical path

```python
# OBBBA positioning is critical — these are NOT adjustments
total_adjustments = teacher + adj_early_wdwl + se_tax_ded +
                    se_health + se_retirement + ira_ded + hsa_ded +
                    alimony_paid + adj_student_loan
# QBI is NOT here. OBBBA is NOT here. Both are below-the-line.

agi = total_income − total_adjustments

# OBBBA MAGI = agi (then apply below-the-line in Step 4)
```

### Step 4 — Taxable income (Form 1040 Lines 11–15)

```
L11  AGI (from Step 3)
L12  Standard deduction (or itemized — whichever is greater)
     Standard add-ons: +$2,000 per 65+/blind if single/HOH; +$1,600 per MFJ
L13a QBI §199A (Form 8995 Line 15) — below-the-line, does NOT affect AGI
L13b OBBBA Schedule 1-A (senior + tips + OT + auto) — below-the-line
L14  = L12 + L13a + L13b
L15  Taxable income = L11 − L14
```

### Form 8995 QBI (Step 4 continuation)

```python
compute_qbi_deduction(se_net_profit, w2_wages, ubia, reit_ptp_income, taxable_income, fs, p):
  # Line 1: QBI = se_net_profit − ½SE tax − SE health − SE retirement
  l2_total_qbi = l1_qbi_from_business + prior_year_carryover
  l3_qbi_component = l2_total_qbi × 0.20
  l6_reit_ptp = sec199a_divs + k1_sec199a_income   # 1099-DIV Box 5 + K-1 §199A
  l9_reit_component = l6_reit_ptp × 0.20
  l10_combined = l3_qbi_component + l9_reit_component
  # TI limit: 20% × ordinary taxable income
  l11_ti_limit = (taxable_income − qdcgt_income) × 0.20
  l15_deduction = min(l10_combined, l11_ti_limit)
  # TY 2026 minimum: if QBI ≥ $1,000 and deduction < $400, floor to $400
  if p.get("qbi_min", 0) > 0 and l2_total_qbi >= 1000 and l15_deduction < p["qbi_min"]:
      l15_deduction = p["qbi_min"]
  # Above-threshold (>$197,300 single / >$394,600 MFJ): W-2 wage limitation applies
```

### Form 5329 exception codes (Step 13)

```python
PLAN_ONLY_CODES = {"01", "06"}   # 01=age-55 separation; 06=QDRO — invalid for IRAs
IRA_ONLY_CODES  = {"07", "08", "09"}  # employer plan exclusions; IRA-only
LIFETIME_CAPS   = {"09": 10000}  # first home $10k lifetime cap

for each Form5329Exception:
  if code in PLAN_ONLY_CODES and is_ira:
      valid = False    # plan-only exception on IRA → penalty applies
  elif code in IRA_ONLY_CODES and not is_ira:
      valid = False    # IRA-only exception on employer plan → penalty applies
  else:
      valid = True
      allowed = min(amount, LIFETIME_CAPS.get(code, amount))
      l2_exceptions += allowed
l3_subject_to_penalty = l1_total − l2_exceptions
l4_penalty = l3_subject_to_penalty × 0.10   # Code 1 standard rate
```

### Schedule 2 — other taxes (Step 14)

```
Sch 2 L4  = SE tax                  (Schedule SE)
Sch 2 L6  = Form 4972 additional    (lump-sum tax)
Sch 2 L8  = Form 5329 penalty       (early distribution after exceptions)
Sch 2 L11 = Additional Medicare Tax (Form 8959)
Sch 2 L12 = NIIT                    (Form 8960)
Sch 2 L17 = total → Form 1040 Line 23 (NOT Line 24 directly)
```

### Form 1040 Lines 16–24 (exact per f1040.pdf)

```
L16  Income tax (from QDCGT worksheet or rate schedule)
L17  AMT (Form 6251 — if applicable)
L18  Add L16 + L17
L19  Child tax credit / ODC — Schedule 8812 Line 14
L20  Schedule 3 Line 8 (nonrefundable: care + edu + saver + FTC)
L21  Add L19 + L20
L22  Subtract L21 from L18 (tax after credits — if zero or less, -0-)
L23  Other taxes — Schedule 2 Line 17 (SE + AMT + NIIT + AdMed + 5329 + 4972)
L24  Add L22 + L23 = Total tax
```

### Withholding routing (Step 14 — critical)

```
L25a = W-2 Box 2 ONLY — nothing else ever goes here
L25b = 1099-R Box 4 + SSA-1099 Box 6 (box6_voluntary_wh) +
       1099-INT Box 4 + 1099-DIV Box 4 + 1099-B Box 4 +
       1099-NEC Box 4 + 1099-G Box 4 + W-2G Box 4
L25d = L25a + L25b
L26  = Q1+Q2+Q3+Q4 estimated + prior year overpayment applied
L27a = EITC
L28  = ACTC (Schedule 8812 refundable)
L29  = AOC 40% refundable (Form 8863) — already inside L32
L31  = Net PTC (Form 8962 Line 26 → Schedule 3 Line 9)
L33  = L25d + L26 + L27a + L28 + L29 + L31
L34  = max(0, L33 − L24)  → refund
L37  = max(0, L24 − L33)  → amount owed
L38  = Form 2210 underpayment penalty (separate — NOT part of L24)
```

### California Form 540 (Step 14 continuation)

```python
compute_california_540(agi, obbba_total_federal, ...):
  ca_agi = agi
  ca_agi -= ss_benefits                    # R&TC §17083 — CA-exempt
  ca_agi -= unemployment_income            # R&TC §17083 — CA-exempt
  ca_agi += hsa_deduction                  # CA does not conform IRC §223
  ca_agi += obbba_total_federal            # CA does NOT conform to OBBBA — addback all 4
  ca_agi -= ca_other_subtractions
  ca_std = {single/mfs: 5540, mfj/hoh/qss: 11080}[fs]
  ca_taxable = max(0, ca_agi − ca_deduction − personal_exemption)
  ca_tax = ca_rate_schedule(ca_taxable, fs)
  if ca_taxable > 1_000_000:
      ca_tax += (ca_taxable − 1_000_000) × 0.01   # Prop 63 surtax
  ca_credits = ca_sdi_credit + renter_credit
  # CalEITC: compute_caleitc() — CA version; lower income limits than federal
```

---

## Data flow summary

```
TaxpayerSchema (40 dataclasses, 515+ fields)
    ↓
run(schema) → 14 sequential steps
    ↓
result["computed"] = {
    # Income
    "wages": 85000,  "interest": 1200,  "dividends": 500,
    "se_net_profit": 42000,  "agi": 98500,

    # 1040 lines
    "taxable_income": 56750,  "income_tax": 7890,
    "l13a_qbi": 6400,  "l13b_obbba": 3200,
    "l19_ctc": 2200,  "l24_total_tax": 9120,

    # Schedules
    "sch2": {"l4_se_tax": 5930, "l8_5329": 200, "l12_niit": 0, "l17_total": 6130},
    "sch3": {"l2_care": 480, "l3_edu": 0, "l4_saver": 0, "l8_total": 480},
    "s8812": {"ctc_total": 2200, "odc_total": 0, "l27_actc": 1700},
    "qbi_detail": {"l3_qbi_comp": 6400, "l6_reit_ptp": 64, "l9_reit_comp": 13, "l15": 6400},
    "f5329": {"l1_total": 2000, "l2_exceptions": 2000, "l4_penalty": 0},

    # Payments and result
    "l25a_w2_wh": 14200,  "l25b_other_wh": 400,  "l27a_eitc": 0,
    "l28_actc": 1700,  "l34_refund": 7180,  "l37_owe": 0,

    # California
    "ca_computed": {"ca_agi": 101700, "ca_taxable": 84450, "ca_tax": 5200, ...},

    # Metadata
    "effective_rate": 0.093,  "marginal_rate": 0.22,
    "obbba_total_deductions": 3200,  "obbba_senior_deduction": 6000,
    ...  # 155+ keys total
}

result["warnings"] = [
    "SS benefits: $14,280 taxable of $25,200 gross. Source: Pub 915 Worksheet 1.",
    "QBI rental safe harbor: 250-hour requirement not confirmed. See Reg. §1.199A-4.",
    ...
]
```

---

## map_result() — pass-through rule

```python
def map_result(engine_result: dict) -> dict:
    c = engine_result.get("computed", {})
    out = dict(c)          # ALL engine keys automatically included
    # Only add: derived values and legacy aliases
    out["effective_rate"] = round(c["income_tax"] / c["agi"], 4) if c["agi"] else 0
    out["l21_add_l19_l20"] = c.get("l19_ctc", 0) + c.get("sch3", {}).get("l8_total", 0)
    # ... other aliases
    return out
# NEVER enumerate individual engine keys in map_result(). dict(c) covers everything.
```

---

## IRS source PDFs (https://www.irs.gov/forms-instructions)

| Form / Pub | IRS URL | Used for |
|---|---|---|
| Form 1040 + Sch 1/2/3 | `f1040.pdf`, `f1040s1.pdf`, `f1040s2.pdf`, `f1040s3.pdf` | Core return lines |
| Schedule A | `f1040sa.pdf` | Itemized deductions |
| Schedule B | `f1040sb.pdf` | Interest and dividends |
| Schedule C | `f1040sc.pdf` | Business income |
| Schedule D | `f1040sd.pdf` | Capital gains |
| Schedule E | `f1040se.pdf` | Rental income |
| Schedule SE | `f1040sse.pdf` | Self-employment tax |
| Schedule 8812 | `f1040s8.pdf` | CTC/ACTC/ODC |
| Form 8863 | `f8863.pdf` | Education credits |
| Form 8880 | `f8880.pdf` | Saver's credit |
| Form 8962 | `f8962.pdf` | Premium tax credit |
| Form 8995 | `f8995.pdf` | QBI (below threshold) |
| Form 6251 | `f6251.pdf` | AMT |
| Form 8606 | `f8606.pdf` | Nondeductible IRA |
| Form 8889 | `f8889.pdf` | HSA |
| Form 8582 | `f8582.pdf` | Passive activity |
| Form 5329 | `f5329.pdf` | Early distributions |
| Form 1116 | `f1116.pdf` | Foreign tax credit |
| Form 4797 | `f4797.pdf` | Sale of business property |
| Form 4972 | `f4972.pdf` | Lump-sum distribution |
| Form 8615 | `f8615.pdf` | Kiddie tax |
| Form 8960 | `f8960.pdf` | NIIT |
| Form 8959 | `f8959.pdf` | Additional Medicare |
| Form 2210 | `f2210.pdf` | Underpayment penalty |
| Form 982 | `f982.pdf` | Cancellation of debt |
| Pub 915 | `p915.pdf` | SS taxability worksheets |
| Pub 575 | `p575.pdf` | Simplified Method table |
| Pub 590-A | `p590a.pdf` | IRA deduction worksheets |
| Pub 596 | `p596.pdf` | EITC investment income |
| Pub 936 | `p936.pdf` | Mortgage interest limit |
| Pub 504 | `p504.pdf` | Alimony TCJA rules |
| Pub 463 | `p463.pdf` | Mileage rates |
| CA Form 540 | `ftb.ca.gov/forms/2025/2025-540.pdf` | California return |

---

*End of Engine Algorithm · V17.1 · 2026-05-24*
*Verify: `python3 sachintaxcare_test.py` (584/584) · `python3 test_vita_irs.py` (145/145)*
