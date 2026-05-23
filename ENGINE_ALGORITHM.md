# SachinTaxCare — Engine Algorithm & Code Flow
*Authoritative description of how the engine computes a 2025/2026 federal + CA return*
*Tax years 2025 & 2026 · Engine v12-fork · 145/145 tests passing · Updated 2026-05-11*

---

## ⚠ OBBBA TY 2025 Algorithm Changes (P.L. 119-21, signed July 4, 2025)

The One Big Beautiful Bill Act changed the following computation parameters and added new steps:

| Change | Old value | New value | Engine location |
|---|---|---|---|
| Std ded single/MFS | $15,000 | **$15,750** | `PARAMS_2025["std_deduction"]` |
| Std ded HOH | $22,500 | **$23,625** | `PARAMS_2025["std_deduction"]` |
| Std ded MFJ/QSS | $30,000 | **$31,500** | `PARAMS_2025["std_deduction"]` |
| CTC per child | $2,000 | **$2,200** | `PARAMS_2025["ctc_per_child"]` |
| SALT cap (default) | $10,000 | **$40,000** | `PARAMS_2025["salt_cap_default"]` |
| SALT cap (MFS) | $5,000 | **$20,000** | `PARAMS_2025["salt_cap_mfs"]` |
| Charitable floor | 0% | **0.5% AGI** (itemizers) | `PARAMS_2025["charitable_agi_floor_pct"]` |

New above-line deductions (all in `OBBBA Above-Line Deductions` block, between NOL and Step 4):

| Deduction | Cap | Phase-out threshold | Engine function |
|---|---|---|---|
| Senior Bonus ($6k/person, age 65+) | $6k per person | MAGI $75k/$150k | `compute_senior_deduction()` |
| Qualified tips | $25,000 | MAGI $150k/$300k | `compute_tip_deduction()` |
| FLSA overtime | $12,500 / $25,000 MFJ | MAGI $150k/$300k | `compute_overtime_deduction()` |
| Auto loan interest (new US vehicle) | $10,000 | MAGI $100k/$200k | `compute_auto_loan_deduction()` |

Source: Rev. Proc. 2025-32; irs.gov/newsroom/one-big-beautiful-bill-provisions

---

## Overview

The entire computation is a single pure function:

```python
result = sachintaxcare_engine.run(schema: TaxpayerSchema) -> dict
```

- Input: one `TaxpayerSchema` dataclass instance (42 nested dataclasses)
- Output: one dict with keys `computed`, `warnings`, `steps`, `schema`
- No side effects, no database, no network calls
- Same input always produces same output

`result["computed"]` contains every Form 1040 line value. `result["warnings"]` contains every IRS-sourced advisory message. The caller (Flask `/compute` route) serializes `result["computed"]` as JSON and returns it to the browser.

---

## The 14-step computation order

The order is mandated by the IRS Credit Limit Worksheet (CLW) circular dependency. It cannot be changed without breaking credit calculations. Each step feeds values into later steps.

```
Step 1:  Income aggregation
Step 2:  Above-line adjustments (partial)
Step 3:  AGI · SS taxability
Step 4:  Deduction (standard vs itemized)
Step 5:  QBI deduction · Income tax · AMT · Kiddie Tax
Step 6:  Form 2441 — child/dep care (FIRST — sets CLW baseline)
Step 7:  Form 8863 — education credits (SECOND)
Step 8:  Form 8880 — saver's credit (THIRD)
Step 9:  Schedule 8812 — CTC/ACTC/ODC (FOURTH)
Step 10: Schedule 3 Part I — FTC, care, education, saver, ODC
Step 11: EITC
Step 12: Form 8962 — Premium Tax Credit
Step 13: Form 5329 · Schedule 2 · Schedule 3 Part II
Step 14: Form 1040 totals
```

---

## Step 1 — Income aggregation

**Source**: `f1040.pdf` Lines 1–8; all 1099 instructions

The engine aggregates every income source into variables. All values are rounded after each operation using `rnd() = round()`.

### W-2 wages

```
wages          = Σ(w2.box1_wages for all W-2s)             → Line 1z
fed_wh         = Σ(w2.box2_fed_wh)                         → Line 25a ONLY
allocated_tips = Σ(w2.box8_allocated_tips)                  → Schedule 1 Line 8
employer_dep_care = Σ(w2.box10_dependent_care)              → Form 2441 Line 12
covered_by_ret_plan = ANY(w2.box13_retirement_plan)         → IRA deduction phase-out test
```

### 1099-INT interest

```
interest         = Σ(box1_interest)                         → Schedule B → Line 2b
early_wdwl       = Σ(box2_early_withdrawal)                 → Schedule 1 Line 18 (NOT Line 8)
us_bond_interest = Σ(box3_us_savings_bond)                  → Line 2b (state-exempt)
int_backup_wh    = Σ(box4_fed_wh)                           → Line 25b (backup WH)
tax_exempt_int   = Σ(box8_tax_exempt_interest)              → Line 2a + SS provisional income
```

### 1099-DIV dividends

If per-payer `form_1099divs` list is populated, it takes precedence over legacy flat fields:

```
dividends         = Σ(box1a_ordinary_div)                   → Schedule B → Line 3b
dividends_qual    = Σ(box1b_qualified_div)                  → Line 3a (QDCGT rates)
div_cap_gain_dist = Σ(box2a_cap_gain_dist)                  → Schedule D Line 13
div_backup_wh     = Σ(box4_fed_wh)                          → Line 25b
div_exempt_int    = Σ(box11_exempt_interest)                 → Line 2a + SS provisional income
tax_exempt_int   += div_exempt_int                           (added to INT tax-exempt total)
```

### 1099-NEC + Schedule C

1099-NEC Box 1 is NOT prize income — it routes directly to Schedule C gross income.

```
nec_backup_wh = Σ(form_1099necs.box4_fed_wh)               → Line 25b

compute_schedule_c_se(schedule_cs, PARAMS_2025, w2_ss_wages):
  for each ScheduleC:
    cogs = inventory_beginning + purchases + cost_of_labor +
           materials_supplies_cogs + other_cogs − inventory_ending
    meals_deductible = meals × 0.50                          (50% limitation)
    home_office = min(home_office_sq_ft, 300) × 5           (Rev. Proc. 2013-13)
    net_profit = gross_receipts − returns − cogs − all_expenses − home_office
    net_earnings_se = net_profit × 0.9235                   (Schedule SE)
    available_ss_base = max(0, ss_wage_base_2025 − w2_ss_wages)  ← CRITICAL CAP
    se_ss_taxable = min(net_earnings_se, available_ss_base)
    se_tax = se_ss_taxable × 0.124 + net_earnings_se × 0.029
  se_tax_deduction = se_tax × 0.50                           → Schedule 1 Line 15
  se_net_profit = Σ(all_net_profits)                         → Schedule 1 Line 3
```

### 1099-R pension / IRA distributions

The IRA/SEP/SIMPLE checkbox on Box 7 is the authoritative routing determinant — not the Box 7 code:

```
for each Form1099R:
  if box7_code in ("G", "H"):  SKIP (direct rollover — not taxable)
  if box7_code == "Q":          SKIP (qualified Roth — not taxable)

  taxable = box2a_taxable  (if box2b_not_determined: taxable = 0, issue warning)
  taxable -= box6_nua      (NUA excluded from ordinary income → LTCG when sold)
  box3_cap_gain_total += box3_capital_gain  (for Form 4972)

  # ⚠ GATE: simplified method only applies when box9b_employee_contribs > 0
  # If schema sends box9b_employee_contrib (no trailing 's'), bridge must map it.
  # Without this, gate fails silently and full gross amount is taxable.
  if simplified_method and box9b_employee_contribs > 0:
    taxable = compute_simplified_method(sm, taxable)
    [Pub 575 Worksheet A — exact age/combined-age table row]

  if box7_code == "1":  penalty_1099r += taxable × 0.10   (Code 1 = early dist)
  if box7_code == "S":  penalty_1099r += taxable × 0.25   (Code S = SIMPLE < 2yr)

  if box7_ira_sep_simple:  f1099r_taxable_ira     += taxable → Line 4b
  else:                     f1099r_taxable_pension  += taxable → Line 5b

l4a = f1099r_gross_ira    l4b = f1099r_taxable_ira      → Lines 4a/4b
l5a = f1099r_gross_pension l5b = f1099r_taxable_pension  → Lines 5a/5b
```

### Form 8606 — nondeductible IRA basis

Adjusts l4b to remove the nontaxable portion of IRA distributions:

```
compute_form_8606(f8606, f1099r_taxable_ira):
  l3 = nonded_contrib_this_year + basis_prior_year
  l6_total = trad_ira_value_dec31 + trad_ira_distributions
  l8_nontaxable = l3 / l6_total × trad_ira_distributions   (pro-rata)
  l14_new_basis = l3 − l8_nontaxable + nonded_contrib_this_year
  if conversion_amount > 0:
    l18_conv_taxable = conversion_amount × (1 − l8_nontaxable / trad_ira_distributions)
  l4b = max(0, l4b − l8_nontaxable + l18_conv_taxable + roth_taxable)
```

### SSA-1099 (computed after pre-SS AGI is known — see Step 3)

```
ss_net    = form_ssa1099.box5_net_benefits → Line 6a (always shown)
ss_box6_wh = form_ssa1099.box6_voluntary_wh → Line 25b
```

### Capital gains — Form 8949 / Schedule D

```
compute_form_8949_schd(form_1099bs):
  for each Form1099B:
    gain = proceeds − cost_basis + accrued_discount − wash_sale_loss_disallowed
    route to: short-term (Box A/B) or long-term (Box D/E/F)
  net_lt = Σ(long-term gains) − Σ(long-term losses)
  net_st = Σ(short-term gains) − Σ(short-term losses)
  cap_loss_deductible = max(−3000, min(0, net_lt + net_st))  → Line 7
  cap_gain_taxable = max(0, net_lt + net_st)                  → Line 7
```

### Form 4797 — Sales of business property

```
compute_form_4797(form_4797s):
  for each Form4797SaleData:
    total_gain = gross_proceeds − (original_cost − depreciation_taken)
    if 1250_residential:
      ordinary_recapture = 0                    (MACRS straight-line → no §1250 recapture)
      unrec_1250 = min(depreciation_taken, total_gain)  (25% rate via QDCGT worksheet)
    if 1245_equipment:
      ordinary_recapture = min(depreciation_taken, total_gain)  (all depr = ordinary)
    sec1231_gain = total_gain − ordinary_recapture
    if prior_sec1231_losses_5yr > 0:
      reclassify up to prior_sec1231_losses_5yr as ordinary (lookback rule IRC §1231(c))

  ordinary_income_recapture → Schedule 1 Line 4 (ordinary income)
  sec1231_gain_net > 0 → added to cap_gain_income (LTCG treatment)
  sec1231_gain_net < 0 → ordinary deduction
  unrec_sec1250_gain    → QDCGT worksheet Line 19 (25% rate)
```

### Schedule E Part I + Form 8582 — rental real estate

Run twice: once with AGI=0 (placeholder before AGI known), then again with final AGI.

```
compute_schedule_e_8582(schedule_es, agi, filing_status, form_8582_override):
  for each ScheduleE:
    if days_personal_use > max(14, 0.10 × days_rented):  §280A vacation rules
      allocate_expenses by (days_rented / total_days)
      loss FULLY disallowed even if active participant
    net_income = rents_received − Σ(all expenses including depreciation)

  passive_losses = Σ(net_income where net_income < 0 and not real_estate_pro)
  passive_incomes = Σ(net_income where net_income > 0)
  prior_unallowed = form_8582.prior_year_unallowed_losses (Worksheet 7)

  if is_real_estate_professional:  losses are non-passive (bypasses §469)
  else if active_participant:
    phase_out_start = 100000 (50000 if mfs_lived_apart)
    max_allowance   = 25000  (12500 if mfs_lived_apart)
    allowance = max(0, max_allowance − 0.50 × max(0, agi − phase_out_start))
    allowed_loss = min(total_passive_loss + prior_unallowed, allowance)
  else:
    allowed_loss = min(passive_losses, passive_incomes)  (only offset passive income)

  net_rental = passive_incomes − allowed_loss              → Schedule 1 Line 5
```

### Schedule K-1 pass-through income

```
compute_k1_income(schedule_k1s):
  for each ScheduleK1:
    if material_participation:  ordinary = non-passive (not Form 8582 limited)
    else:                       ordinary = passive (Form 8582 applies)
    k1_ordinary  += box1_ordinary_income    → Schedule E Part II
    k1_rental    += box2_net_rental         → Schedule E Part I (passive)
    k1_interest  += box5_interest           → Schedule B → Line 2b
    k1_ord_div   += box6a_ordinary_div      → Schedule B → Line 3b
    k1_qual_div  += box6b_qualified_div     → QDCGT
    k1_stcg      += box8_stcg              → Schedule D
    k1_ltcg      += box9_ltcg             → Schedule D
    k1_se        += box14a_se_income        → Schedule SE
    k1_sec199a   += box17_sec199a           → Form 8995
```

### Other income items

```
gambling_income = Σ(w2g.box1_winnings)                      → Schedule 1 Line 8b
gambling_wh     = Σ(w2g.box4_fed_wh)                        → Line 25b
unemployment    = Σ(f1099g.box1_unemployment)               → Schedule 1 Line 7 (CA-exempt)
state_refund_taxable = Σ(f1099g.box2_state_refund           → Schedule 1 Line 1
                         where f1099g.prior_year_itemized)   (tax benefit rule IRC §111)
cancelled_debt  = Σ(f1099c.box2 where not is_excluded)       → Schedule 1 Line 8c
prize_income    = Σ(f1099misc_prize.box3_other_income)       → Schedule 1 Line 8b
alimony_received = al.alimony_received (if decree_pre_2019)  → Schedule 1 Line 2a
alimony_paid     = al.alimony_paid     (if decree_pre_2019)  → Schedule 1 Line 19a (adj)
```

### Total income assembled

```
additional_income = l4b + l5b + cancelled_debt + prize_income + se_net_profit +
                    rental_net + gambling_income + unemployment + state_refund_taxable +
                    alimony_received + k1_ordinary + k1_rental + k1_se + f4797_ordinary_recapture

interest       += k1_interest         (K-1 interest joins Schedule B)
dividends      += k1_ord_div
dividends_qual += k1_qual_div

qdcgt_income = dividends_qual + max(0, net_ltcg_with_k1) +
               max(0, div_cap_gain_dist) + f4797_unrec_1250

total_income_pre_ss = wages + interest + us_bond_interest + dividends +
                       additional_income + net_cap_gain
```

---

## Step 2 — Above-line adjustments (partial — before SS)

```
teacher_adj     = min(teacher_expense, 300)           → Schedule 1 Line 11
adj_early_wdwl  = early_wdwl                          → Schedule 1 Line 18
adj_other       = other_adjustments                   → Schedule 1 Line 24z

compute_se_retirement(contributions, se_net_profit, se_tax_deduction):
  ceiling per plan type:
    SEP-IRA:    min(contributions, 0.25 × net_SE, 70000)   → Schedule 1 Line 16
    SIMPLE IRA: min(contributions, net_SE, 16500+employer)
    Solo 401k:  elective + 25% employer, ≤ 70000
  adj_se_retirement = capped amount

compute_se_health_insurance(premiums, se_net_profit, se_tax_ded, adj_se_retirement):
  ceiling = net_SE_profit − se_tax_deduction − adj_se_retirement
  adj_se_health = min(premiums, ceiling)               → Schedule 1 Line 17

compute_ira_deduction(contrib, age, magi, filing_status, covered_by_plan, spouse_covered):
  limit = 7000 if age < 50 else 8000
  if not covered_by_plan and not spouse_covered:
    deductible = min(contrib, limit)                   (no phase-out)
  elif covered_by_plan:
    phase_out_range by filing_status:
      single:  79000–89000 · mfj-covered: 126000–146000
    deductible = min(contrib, limit) × phase_out_factor
  elif not covered but spouse_covered:
    phase_out: 236000–246000 mfj
  adj_ira_deduction = deductible                       → Schedule 1 Line 20

compute_form_8889(hsa, filing_status, w2_code_w):
  limit = 4300 (self) or 8550 (family) + 1000 if age ≥ 55
  limit -= employer_contrib_from_w2_code_w
  deductible = min(contributions_taxpayer, limit)      → Schedule 1 Line 13
  if total_distributions > qualified_medical:
    taxable = total_distributions − qualified_medical  → Schedule 1 Line 8f
    if not age_65_or_disabled: penalty = taxable × 0.20  → Schedule 2 Line 17c

compute_student_loan_deduction(interest_paid, magi, filing_status):
  limit = 2500
  phase_out_range: 75000–90000 single / 155000–185000 mfj
  (mfs: disallowed entirely)
  deduction = min(interest_paid, limit) × phase_out_factor  → Schedule 1 Line 21

total_adjustments_before_sl = teacher_adj + adj_early_wdwl + adj_other +
                               se_tax_deduction + adj_se_retirement +
                               adj_se_health + adj_ira_deduction + adj_hsa + adj_alimony_paid
total_adjustments = total_adjustments_before_sl + adj_student_loan
```

---

## Step 3 — AGI and SS taxability

```
agi_pre_ss = total_income_pre_ss − total_adjustments

# SS taxability — Pub 915 Worksheet 1
compute_ss_taxable(net_benefits, agi_before_ss, filing_status,
                   tax_exempt_interest, mfs_lived_apart):
  combined_income = agi_before_ss + tax_exempt_interest + net_benefits × 0.50
  base_amount:
    single/hoh/qss: 25000   upper: 34000
    mfj:            32000   upper: 44000
    mfs (apart):    25000   upper: 34000   ← MFS lived-apart exception
    mfs (together):     0   upper:  0  (85% always taxable)
  if combined_income ≤ base:       l6b = 0
  elif combined_income ≤ upper:    l6b = min(0.50 × (combined − base), 0.50 × net_benefits)
  else:                            l6b = min(0.85 × net_benefits,
                                             0.85 × (combined − upper) + 0.50 × (upper − base))
  l6b = rnd(l6b)

# Lump-sum election — Pub 915 Worksheets 2 & 4 (if box3 includes prior years)
compute_ss_lump_sum_election(net_benefits_2025, ..., prior_years):
  w1_taxable = compute_ss_taxable(...)   ← standard method
  for each prior year in lump_sum_prior_years:
    recompute taxable SS as if lump-sum amount had been received in that prior year
    additional_taxable_for_that_year = Worksheet 2 result
  w4_total = Σ(additional_taxable per prior year) + current_year_portion
  final_taxable_ss = min(w1_taxable, w4_total)  ← use whichever is lower
  if election_beneficial: check Form 1040 Line 6c

total_income = total_income_pre_ss + l6b
agi = total_income − total_adjustments

# Form 8582 re-run with final AGI (rental passive phase-out needs actual AGI)
if schedule_es:
  sched_e_result = compute_schedule_e_8582(schedule_es, agi=agi, ...)
  adjust total_income and agi by delta
```

---

## Step 3B — OBBBA Above-Line Deductions (NEW — P.L. 119-21)

Applied after AGI is finalized (Step 3), before deduction step (Step 4). MAGI = AGI at this point.

```
# Senior Bonus Deduction — OBBBA §70103 (TY 2025–2028)
compute_senior_deduction(taxpayer_age, spouse_age, magi, filing_status):
  if filing_status == "mfs": return 0   # ineligible
  threshold = 75000 (single/hoh/qss) or 150000 (mfj)
  qualifying = 6000 × (1 if taxpayer_age ≥ 65 else 0)
             + 6000 × (1 if mfj and spouse_age ≥ 65 else 0)
  return max(0, qualifying − max(0, magi − threshold))   # $1 : $1 phase-out

# Qualified Tip Deduction — OBBBA §70201 (TY 2025–2028)
compute_tip_deduction(qualified_tips, magi, filing_status):
  threshold = 150000 (single/hoh/qss) or 300000 (mfj)
  capped = min(qualified_tips, 25000)
  return max(0, capped − max(0, magi − threshold))       # $1 : $1 phase-out

# Overtime Pay Deduction — OBBBA §70202 (TY 2025–2028)
compute_overtime_deduction(overtime_pay, magi, filing_status):
  if filing_status == "mfs": return 0   # ineligible
  max_cap = 12500 (single/hoh/qss) or 25000 (mfj)
  threshold = 150000 (single/hoh/qss) or 300000 (mfj)
  capped = min(overtime_pay, max_cap)
  return max(0, capped − max(0, magi − threshold))       # $1 : $1 phase-out

# Auto Loan Interest Deduction — OBBBA §70301 (TY 2025–2028)
compute_auto_loan_deduction(interest_paid, magi, filing_status,
                             loan_originated_after_2024, vehicle_new_us_assembled):
  if not loan_originated_after_2024 or not vehicle_new_us_assembled: return 0
  threshold = 100000 (single/hoh/qss) or 200000 (mfj)
  capped = min(interest_paid, 10000)
  return max(0, capped − max(0, magi − threshold))       # $1 : $1 phase-out

obbba_total = adj_senior + adj_tips + adj_overtime + adj_auto
agi = agi − obbba_total
```

Source: Rev. Proc. 2025-32; irs.gov/newsroom/one-big-beautiful-bill-provisions

---

## Steps 4–5 — Deduction, QBI, and income tax

### Step 4 — Deduction

```
std_deduction = PARAMS_2025["std_deduction"][filing_status]
  # OBBBA §70102 amounts (updated from Rev. Proc. 2024-40):
  single/mfs: $15,750   mfj/qss: $31,500   hoh: $23,625

blind_addon = 2000 (single/hoh age 65+ or blind) or 1600 (mfj/mfs per qualifying person)
std_deduction += Σ(blind/65+ add-ons)

compute_schedule_a(sched_a, agi, filing_status):
  medical_floor    = max(0, medical_dental_total − agi × 0.075)  → Line 4

  # SALT — OBBBA §70106 (NEW: $40k cap, phase-down above $500k AGI)
  salt_raw         = state_income_tax + real_estate_tax + personal_property_tax
  salt_cap_base    = 40000 (default) or 20000 (MFS)
  phasedown_thresh = 500000 (default) or 250000 (MFS)
  if agi > phasedown_thresh:
    salt_cap = max(10000, salt_cap_base − ceil((agi − thresh) / 1000) × 50)
  else:
    salt_cap = salt_cap_base
  salt_deductible  = min(salt_raw, salt_cap)                    → Line 5e

  # Mortgage interest — OBBBA makes $750k limit permanent
  mortgage_limit   = 1000000 if grandfathered else 750000
  mort_deductible  = mortgage_interest × min(1, mortgage_limit / outstanding_balance)

  # Charitable — OBBBA: 0.5% AGI floor before 60% cap (itemizers)
  charitable_floor = agi × 0.005                                # OBBBA new
  cash_above_floor = max(0, cash_charitable − charitable_floor)
  charitable_limit = 0.60 × agi (cash), 0.50 × agi (non-cash)
  itemized_total   = medical_floor + salt_deductible + mort_deductible +
                     mortgage_points + investment_interest +
                     min(cash_above_floor + noncash_charitable + carryover, limit) +
                     casualty_theft_loss + other_misc                → Line 17
  # Misc itemized deductions: permanently disallowed per OBBBA §70501

deduction_used = max(std_deduction, itemized_total if use_itemized else std_deduction)
taxable = max(0, agi − deduction_used)
```

### Step 5 — QBI deduction, income tax, AMT, Kiddie Tax

```
# QBI §199A — Form 8995 simplified method (below threshold)
compute_qbi_deduction(schedule_cs, se_tax_ded, se_health_ded, se_retirement_ded,
                      taxable_income, qdcgt_income, filing_status):
  threshold = 197300 (single) / 394600 (mfj)  [WARN: Form 8995-A needed above threshold]
  ordinary_ti = taxable_income − qdcgt_income
  for each ScheduleC:
    qbi = net_profit − se_tax_ded − se_health_ded − se_retirement_ded
    if sstb and agi > threshold: qbi = 0 (full SSTB phase-out above threshold)
  total_qbi = Σ(max(0, qbi) for all SCs)
  l12 = min(total_qbi × 0.20, ordinary_ti × 0.20)    → Line 13
  taxable = max(0, taxable − adj_qbi)

# Income tax — always uses QDCGT worksheet if qualified div or LTCG > 0
compute_qdcgt_tax(taxable, qdcgt_income, filing_status):
  if qdcgt_income == 0:
    return compute_tax(taxable, filing_status)   ← regular brackets
  ordinary_ti = max(0, taxable − qdcgt_income)
  tax_on_ordinary = compute_tax(ordinary_ti, filing_status)
  # QDCGT threshold amounts (2025):
  rate0_threshold:  single=47025  mfj/qss=94050  hoh=63000  mfs=47025   [TY 2025 PARAMS_2025]
  rate15_threshold: single=518900 mfj/qss=583750 hoh=551350 mfs=518900   [TY 2025 PARAMS_2025]
  qdcgt_in_0pct_band  = max(0, min(taxable, rate0_threshold) − ordinary_ti)
  qdcgt_in_15pct_band = max(0, min(taxable, rate15_threshold) − max(ordinary_ti, rate0_threshold))
  qdcgt_in_20pct_band = max(0, qdcgt_income − qdcgt_in_0pct_band − qdcgt_in_15pct_band)
  qdcgt_tax = qdcgt_in_0pct_band × 0 + qdcgt_in_15pct_band × 0.15 +
              qdcgt_in_20pct_band × 0.20
  income_tax = rnd(tax_on_ordinary + qdcgt_tax)

# HOH uses distinct brackets — not same as single
compute_tax(taxable, filing_status):
  brackets = PARAMS_2025["tax_brackets_" + {mfj:mfj, qss:mfj, single:single,
                                             mfs:single, hoh:hoh}[filing_status]]
  tax = 0; prev = 0
  for (ceiling, rate) in brackets:
    band = min(taxable, ceiling) − prev
    tax += max(0, band) × rate
    if taxable ≤ ceiling: break
    prev = ceiling
  return rnd(tax)

# Form 6251 — AMT
compute_form_6251(taxable, agi, regular_tax, qdcgt_income, filing_status,
                  deduction_type, salt_itemized, form_6251_data, ...):
  l1   = taxable
  l2a  = std_deduction if deduction_type == "standard" else 0    (addback)
  l2b  = salt_itemized if deduction_type == "itemized" else 0     (SALT addback)
  l2j  = form_6251_data.iso_bargain_element if form_6251_data else 0
  l3   = Σ(box12_private_activity for all 1099-DIVs and 1099-INTs)  (AMT pref item)
  amti = l1 + l2a + l2b + l2j + l3 + other_adjustments
  exemption = {single: 88100, mfj/qss: 137000, mfs: 68500, hoh: 88100}[fs]
  phase_out_start = {single: 626350, mfj: 1252700, mfs: 626350, hoh: 626350}[fs]
  exemption = max(0, exemption − 0.25 × max(0, amti − phase_out_start))
  amti_after_exemption = max(0, amti − exemption)
  tmt = 26% × min(amti_after_exemption, 232600) + 28% × max(0, amti_after_exemption − 232600)
  [QDCGT §55(b)(3) rates applied on AMTI same as regular QDCGT computation]
  l9_amt = max(0, tmt − regular_tax)                             → Schedule 2 Line 1

# Form 8615 — Kiddie Tax (if child with unearned income)
compute_form_8615(f8615, child_taxable_income, child_qdcgt_income):
  applies = (unearned_income > 2700 and
            (child_age < 18 or
             (child_age in [18,19,20,21,22,23] and child_is_full_time_student)))
  if not applies: return (no kiddie tax)
  net_unearned = max(0, unearned_income − 2700)
  l6_child_taxable = child_taxable_income
  l7_parent_taxable = f8615.parent_taxable_income
  l8 = l7_parent_taxable + net_unearned
  l9 = compute_tax(l8, parent_filing_status)
  l10 = compute_tax(l7_parent_taxable, parent_filing_status)
  l11 = l9 − l10   (parent's marginal rate on child's NUI)
  l13 = compute_qdcgt_tax(child_taxable_income, child_qdcgt_income, child's_fs)
  income_tax = max(l11, l13)   (replaces normal bracket calc for the child)
```

---

## Steps 6–9 — Credits (CLW order, mandatory)

The Credit Limit Worksheet (CLW) is a running subtraction:

```
CLW baseline = income_tax   ← only regular tax, not SE/AMT/penalty

Step 6 — Form 2441 (FIRST):
  care_cap = 3000 (1 qualifying child) or 6000 (2+)
  care_exp = min(Σ(care_providers.expenses), care_cap)
  care_exp -= min(employer_dep_care, 5000)   (§129 exclusion)
  care_exp = min(care_exp, earned_income_taxpayer)  (earned income test)
  f2441_decimal = get_f2441_decimal(agi)    ← lookup table f2441.pdf Line 8
  care_credit = min(care_exp × f2441_decimal, CLW_remaining)
  CLW_remaining -= care_credit             → Schedule 3 Line 2

Step 7 — Form 8863 (SECOND):
  for each Form1098T:
    net_exp = max(0, box1_payments − box5_scholarships)
    if credit_type == "aoc" and first_four_years:
      aoc = 100% × first_2000 + 25% × next_2000  → max $2,500
      aoc_refundable  = aoc × 0.40               → Line 29 (NEVER into CLW)
      aoc_nonref      = aoc × 0.60               → Schedule 3 Line 3
      apply MAGI phase-out: $80k–$90k single / $160k–$180k mfj
    else (llc):
      llc = 20% × min(net_exp, 10000)  → max $2,000, non-refundable
      apply MAGI phase-out: same ranges as AOC
  edu_nonref_applied = min(Σ(aoc_nonref + llc), CLW_remaining)
  CLW_remaining -= edu_nonref_applied       → Schedule 3 Line 3

Step 8 — Form 8880 (THIRD):
  saver_l3 = IRA_contributions + elective_deferrals
  saver_l5 = max(0, saver_l3 − disqualifying_dist)
  saver_l6 = min(saver_l5, 2000)
  saver_rate = get_saver_rate(agi, filing_status)  ← 3-column table f8880.pdf
  saver_l10 = saver_l6 × saver_rate
  *** saver_l4 = 0 (CLW circular dependency — Form 8880 L4 not yet known) ***
  saver_l12 = min(saver_l10, CLW_remaining)
  CLW_remaining -= saver_l12               → Schedule 3 Line 4

Step 9 — Schedule 8812 (FOURTH):
  ctc_total = num_ctc_kids × 2000
  odc_total = num_odc_deps × 500
  po_threshold = 400000 (mfj) or 200000 (all others)
  po_reduction = ceil((agi − po_threshold) / 1000) × 50 if agi > threshold
  l12 = max(0, ctc_total − po_reduction)
  l14_ctc = min(l12, CLW_remaining)        → Line 19 (non-refundable CTC)
  odc_credit = min(odc_total, CLW_remaining − l14_ctc)  → Schedule 3 Line 6d

  # ACTC — refundable, after non-refundable CTC
  l16a = l12 − l14_ctc
  l16b = num_ctc_kids × 1700
  l17 = min(l16a, l16b)
  earned_for_actc = wages + max(0, se_net_profit) + allocated_tips
  l20 = max(0, earned_for_actc − 2500) × 0.15
  actc = min(l17, l20)                     → Line 28 (refundable)
  [actc = 0 if mfs and lived_with_spouse]
```

---

## Step 10 — Schedule 3 Part I and Form 1116 (Foreign Tax Credit)

```
compute_f1116(form_1116, agi, us_tax_before_credit, qdcgt_income, filing_status, amt_tax):
  # Passive basket (most common — 1099-DIV Box 7 / 1099-INT Box 6)
  limitation = (passive_foreign_income / agi) × us_tax_before_credit
  allowable_passive = min(passive_foreign_taxes_paid, limitation)

  # De minimis exception (no Form 1116 needed):
  if total_foreign_taxes ≤ 300 (single) or 600 (mfj):
    ftc_credit = total_foreign_taxes  → Schedule 3 Line 1 directly

sch3_l1  = ftc_credit                          (FTC or de minimis)
sch3_l2  = care_credit                         (Form 2441)
sch3_l3  = edu_nonref_applied                  (Form 8863)
sch3_l4  = saver_l12                           (Form 8880)
sch3_l6d = odc_credit                          (ODC)
sch3_l8  = sch3_l1 + sch3_l2 + sch3_l3 + sch3_l4 + sch3_l6d  → Line 20
tax_after = max(0, income_tax − l14_ctc − sch3_l8)
```

---

## Step 11 — EITC

```
compute_eitc(earned_income, agi, num_children, filing_status,
             investment_income, exact_eitc_from_table):
  if exact_eitc_from_table > 0: return exact_eitc_from_table   (user-confirmed IRS table value)
  if investment_income > 11600: return 0                         (IRC §32(i) disqualification)
  if filing_status == "mfs":    return 0                         (mfs always disqualified)
  income_for_eitc = max(earned_income, agi)   ← use LARGER per IRS instructions
  *** QSS uses single/qss column ($23,350 phaseout) — NOT mfj column ***
  params = PARAMS_2025["eitc"][fs_key][num_children]  (capped at 3 children)
  if income_for_eitc ≤ params["phaseout_start"]:
    eitc = min(income_for_eitc × phase_in_rate, params["max"])
  else:
    eitc = max(0, params["max"] − (income_for_eitc − params["phaseout_start"]) × params["phaseout_rate"])
  WARNING: "Verify with exact IRS EIC Table — engine formula approximates"
```

---

## Step 12 — Form 8962 Premium Tax Credit

```
compute_f8962(agi, family_size, form_1095a):
  fpl = PARAMS_2025["fpl_2024"][family_size]
  magi_pct = agi / fpl × 100

  if monthly data uniform (all 12 months same): use Line 11 annual method
  else: use Lines 12–23 monthly method
    for each month with coverage:
      slcsp_month = col_b
      fpl_pct = agi / (fpl / 12) — monthly FPL
      contribution_rate = Table 2 row lookup [TRUNCATE FPL% to whole number, exact row]
      contribution_amount = agi/12 × contribution_rate
      premium = col_a_month; slcsp = col_b_month; aptc = col_c_month
      monthly_ptc = max(0, slcsp − contribution_amount)
      monthly_net = monthly_ptc − aptc
    l26_net_ptc  = max(0, Σ(monthly_net))   → Schedule 3 Line 9 → Line 31
    l27_excess_aptc = max(0, −Σ(monthly_net)) → Schedule 2 Line 2
```

---

## Step 13 — Form 5329, Schedule 2, Schedule 3 Part II

```
# Form 5329 exception codes override raw penalty
compute_f5329_exceptions(form_1099rs, form_5329_exceptions, agi):
  for each exception claim:
    validate plan_type vs exception_code:
      code 02 (age 55): employer plans ONLY — not IRA
      code 06 (QDRO): employer plans ONLY — not IRA
      codes 07/08/09: IRA only — not employer plans
      code 09: cap at $10,000 lifetime
      code 11: cap at $5,000 per child
    exception_amount = min(claimed, validated_amount)
  l4_penalty = max(0, total_taxable_early_dist − Σ(exception_amounts)) × rate

# Schedule 2 assembly
sch2_l1_amt           = amt_tax               (Form 6251)
sch2_l2_excess_aptc   = excess_aptc           (Form 8962 Line 27) ← NOT Line 8
sch2_l4_se_tax        = se_tax                (Schedule SE)
sch2_l6_4972_tax      = form_4972_additional_tax  (lump-sum)
sch2_l8_5329_penalty  = penalty_1099r         (after exceptions)
sch2_l11_addl_med     = addl_med_tax          (Form 8959)
sch2_l12_niit         = niit_tax              (Form 8960)
sch2_l17_total = Σ(all above)                 → Line 17

# NIIT — Form 8960
compute_niit(agi, nii, filing_status):
  threshold = {single/hoh/mfs: 200000, mfj/qss: 250000}[fs]
  nii = interest + dividends + max(0, rental_net) + max(0, k1_rental) + max(0, net_cap_gain)
  niit = 0.038 × min(nii, max(0, agi − threshold))

# Additional Medicare Tax — Form 8959
compute_additional_medicare_tax(total_wages_se, agi, filing_status, employer_wh):
  threshold = {single/hoh/mfs: 200000, mfj/qss: 250000}[fs]
  tax = 0.009 × max(0, agi − threshold)
  net = max(0, tax − employer_wh)              → Schedule 2 Line 11

# Schedule 3 Part II
sch3_l9  = ptc_net     (Form 8962 net PTC)    → Line 31
```

---

## Step 14 — Form 1040 totals

```
# Withholding — CRITICAL ASSIGNMENT
l25a_w2_wh    = Σ(w2.box2_fed_wh)               ← W-2 Box 2 ONLY — nothing else here
l25b_total    = f1099r_wh                ← 1099-R Box 4 fed WH
              + ss_box6_wh                 ← SSA-1099 Box 6 voluntary WH (box6_voluntary_wh, NOT box6_vol_wh)
              + int_backup_wh + div_backup_wh
              + 1099b_backup_wh + nec_backup_wh + gambling_wh + unemp_wh
l25d_total_wh = l25a_w2_wh + l25b_total

# Estimated payments
l26 = q1 + q2 + q3 + q4 + prior_year_overpayment

# Refundable credits
l27a = eitc             (Schedule EIC)
l28  = actc             (Schedule 8812 refundable)
l29  = edu_ref_aoc      (AOC 40% refundable — NOT in l32)
l31  = sch3_l9          (net PTC)

# Line 32 = EXACTLY these items — nothing else
l32 = l27a + l28 + l29 + l31   ← (l29_aoc separate, already in sum; l27a, l28, l31 only)

l33_total_pmts = l25d_total_wh + l26 + l32
l24_total_tax  = tax_after + sch2_l17_total    ← tax_after already has CLW credits applied
l34_refund = max(0, l33_total_pmts − l24_total_tax)
l37_owe    = max(0, l24_total_tax − l33_total_pmts)

# Form 2210 underpayment penalty — Line 38 NOT in Line 24
compute_form_2210_safe_harbor(l24_total_tax, l33_total_pmts, prior_year_tax, prior_year_agi):
  safe_harbor_multiplier = 1.10 if prior_year_agi > 150000 else 1.00
  safe_harbor_amount = prior_year_tax × safe_harbor_multiplier
  safe_harbor_met = (l33_total_pmts ≥ safe_harbor_amount or
                     l33_total_pmts ≥ l24_total_tax × 0.90 or
                     l24_total_tax − l33_total_pmts < 1000)
  if not safe_harbor_met:
    underpay_penalty = (l24_total_tax − l33_total_pmts) × 0.08  (annual rate approx)
l38_underpayment = underpay_penalty               → Line 38 (separate from Line 24)
effective_owe    = l37_owe + l38_underpayment
effective_refund = max(0, l34_refund − l38_underpayment)

# California Form 540
compute_california_540(fed_agi, filing_status, ...):
  ca_agi = fed_agi
  ca_agi -= ss_benefits           (R&TC §17083 — CA-exempt)
  ca_agi -= unemployment_income   (R&TC §17083 — CA-exempt)
  ca_agi += hsa_deduction         (CA does not conform to IRC §223 — addback required)
  ca_agi -= ca_other_subtractions
  ca_std = {single/mfs: 5540, mfj/hoh/qss: 11080}[fs]
  ca_deduction = max(ca_std, ca_itemized_total if use_ca_itemized else 0)
  ca_taxable = max(0, ca_agi − ca_deduction − personal_exemption_credits)
  ca_tax = ca_brackets(ca_taxable, fs)
  if ca_taxable > 1000000: ca_tax += (ca_taxable − 1000000) × 0.01  (Prop 63 surtax)
  ca_credits = SDI_credit + renter_credit(60 or 120 if paid_rent_over_half_year)
  ca_net_tax = max(0, ca_tax − ca_credits)
```

---

## UI code flow

### Mode A — Engine mode

```
User fills intake panels
  → clicks "⚙ Compute Return"
  → go('compute') called
  → buildPreComputeSummary() renders input review card

User clicks "Run Engine"
  → computeReturn() called
  → buildSchema() runs:
       for each intake panel, read every DOM input by id
       construct TaxpayerSchema-equivalent JSON object
       S.w2s.map(id => { box1: n('w2-box1-'+id), ... })
       S.scs.map(id => { gross_receipts: n('sc-receipts-'+id), ... })
       ... (all 325 fields)
  → fetch('POST /compute', JSON.stringify(schema))
  → Flask: engine.run(TaxpayerSchema(**data))
  → result["computed"] returned as JSON
  → renderResult(schema, result) called:
       renders summary grid (AGI, taxable income, tax, refund/owe)
       renders Form 1040 line table
       renders warnings list

Export/Import JSON:
  → exportJSON() → buildSchema() → JSON.stringify → browser download
  → importJSON() → FileReader → populateFromSchema(sc):
       clears all dynamic rows and resets all index counters
       calls addW2(), addDep(), etc. for each item in array
       sets each UI field via sv(id, value)
       bridges schema key names to UI field ids (e.g. institution → t-inst-)
```

### Server bridge layer (sachintaxcare_server.py)

`safe_init()` maps JSON keys → engine dataclass fields by exact name match. Any key with a different name is **silently discarded**. The bridge layer in `deserialize_schema()` translates all known mismatches before `safe_init()` runs:

```
Schema/UI key              → Engine field              → Dataclass
box2_discharged            → box2_amount_discharged    → Form1099C
exclusion_applies          → is_excluded               → Form1099C
box6_vol_wh                → box6_voluntary_wh         → FormSSA1099
age_at_start               → age_at_annuity_start      → SimplifiedMethodData
joint_age_at_start         → joint_age_at_annuity_start → SimplifiedMethodData
prior_tax_free_recovered   → prior_year_tax_free_recovered → SimplifiedMethodData
start_after_nov_1996       → annuity_start_after_nov_18_1996 → SimplifiedMethodData
box9b_employee_contrib     → box9b_employee_contribs   → Form1099R
form_1099miscs[].box3      → Form1099MISC_Prize        → list (new bridge)
```

Startup: `python3 sachintaxcare_server.py` runs `sachintaxcare_test.py` (77 assertions) before Flask binds.

### Mode B — Claude mode

```
User fills intake panels
  → clicks "✦ Generate Return"
  → sendToClaude() called
  → buildPrompt() runs:
       same DOM traversal as buildSchema()
       serializes every field to human-readable text lines:
         "W2#0: Employer=Acme EIN=12-3456789 Box1=85000 Box2=14200 ..."
         "SchedC#0: Name=Consulting GrossReceipts=65000 Meals=2000(50%limit) ..."
       assembles 20 sections × standing rules header = ~3,000 word prompt
  → sendPrompt(prompt)   ← global function injected by claude.ai host
  → Claude AI receives prompt, fetches IRS PDFs, computes return, generates output
```

---

## Data flow summary

```
TaxpayerSchema (42 dataclasses, 325 fields)
    ↓
run(schema) → 14 sequential computation steps
    ↓
result["computed"] = {
    "agi":              85000,
    "taxable_income":   54500,
    "income_tax":       6120,
    "sch2":             {"l1_amt": 0, "l4_se_tax": 4200, ...},
    "sch3":             {"l2_care": 0, "l3_edu": 0, "l8_total": 800},
    "l19_ctc":          2000,
    "l27a_eitc":        0,
    "l28_actc":         1700,
    "l29_aoc":          0,
    "l24_total_tax":    10320,
    "l25d_wh":          14200,
    "l26_estimated":    0,
    "l33_total_pmts":   14200,
    "l34_refund":       3880,
    "l37_owe":          0,
    "l38_underpay":     0,
    "ca_computed":      {"ca_agi": 80000, "ca_tax": 3200, ...}
}

result["warnings"] = [
    "EITC formula approximation — verify with IRS EIC Table p1040.pdf",
    "SSA-1099: $12,600 of $22,000 SS benefits taxable. Source: Pub 915 Wk 1.",
    ...
]
```

---

## Rounding rule

Every arithmetic result is immediately rounded using `rnd() = round()`. Rounding cascades: each step produces whole-dollar inputs to the next step. Never accumulate fractions and round at the end.

```python
def rnd(v): return round(v)

# Correct:
wages = rnd(sum(w.box1_wages for w in schema.w2s))
se_tax = rnd(se_ss_taxable * 0.124 + net_earnings_se * 0.029)

# Wrong — do not do this:
wages = sum(w.box1_wages for w in schema.w2s)  # fractions accumulate
```

Source: IRC §6102; IRS rounding convention throughout all form instructions.

---

*End of algorithm document · Engine v12-fork · Updated 2026-05-16*
*Run `python3 sachintaxcare_test.py` (77 PASS) and `python3 test_vita_irs.py` (145 PASS) to verify.*
