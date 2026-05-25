# SachinTaxCare — Field Manifest
*Single source of truth for all intake fields*
*Version: 1.4 | Engine: V17.1 | Last updated: 2026-05-24*
*Rule: Any session that adds a field to the engine MUST add a row here and add the field to the UI.*

---

## How to use this file

| Column | Meaning |
|---|---|
| **Field label** | Human-readable name shown in UI |
| **UI id pattern** | HTML `id` attribute. `foo-${id}` = repeating row; `foo` = singleton |
| **Engine field** | Python dataclass field in `sachintaxcare_engine.py` |
| **Routes to** | IRS form line where value is used |
| **IRS source** | Authoritative PDF from `irs.gov/pub/irs-pdf/` |
| **Status** | ✅ In UI · ⚠ Captured but not computed · ❌ Missing from UI |

---

## 1 — Taxpayer & Filing Status

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| First name | `tp-first` | `TaxpayerSchema.first` | 1040 p1 header | f1040.pdf | ✅ |
| Last name | `tp-last` | `TaxpayerSchema.last` | 1040 p1 header | f1040.pdf | ✅ |
| SSN | `tp-ssn` | `TaxpayerSchema.ssn` | 1040 p1 header | f1040.pdf | ✅ |
| Date of birth | `tp-dob` | `TaxpayerSchema.dob` | Age calculations | f1040.pdf | ✅ |
| Occupation | `tp-occ` | `TaxpayerSchema.occupation` | 1040 p1 header | f1040.pdf | ✅ |
| Address | `tp-addr` | `TaxpayerSchema.address` | 1040 p1 header | f1040.pdf | ✅ |
| Blind (taxpayer) | `tp-blind` | `TaxpayerSchema.taxpayer_is_blind` | Std ded +$1,950 | f1040.pdf | ✅ |
| Claimed as dependent | `tp-dep-of` | `TaxpayerSchema.is_dependent_of_another` | Std ded cap | IRC §63(c)(5) | ✅ |
| Dependent earned income | `tp-dep-ei` | `TaxpayerSchema.dependent_earned_income` | Std ded cap | IRC §63(c)(5) | ✅ |
| Full-time student | `tp-student` | `TaxpayerSchema.care_spouse_is_student` *(see §2441 fields)* | Form 8880 bar | f8880.pdf | ✅ |
| Filing status | `fs` (hidden) | `TaxpayerSchema.filing_status` | All brackets | f1040.pdf | ✅ |

### 1a — Qualifying Surviving Spouse

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Deceased spouse name | `ds-name` | `DeceasedSpouse.name` | 1040 header | f1040.pdf | ✅ |
| Deceased spouse SSN | `ds-ssn` | `DeceasedSpouse.ssn` | 1040 header | f1040.pdf | ✅ |
| Date of death | `ds-dod` | `DeceasedSpouse.date_of_death` | QSS eligibility | f1040.pdf | ✅ |

### 1b — Spouse (MFJ/MFS)

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Spouse first name | `sp-first` | `TaxpayerSchema.spouse.first` | 1040 header | f1040.pdf | ✅ |
| Spouse last name | `sp-last` | `TaxpayerSchema.spouse.last` | 1040 header | f1040.pdf | ✅ |
| Spouse SSN | `sp-ssn` | `TaxpayerSchema.spouse.ssn` | 1040 header | f1040.pdf | ✅ |
| Spouse DOB | `sp-dob` | `TaxpayerSchema.spouse.dob` | Age calcs | f1040.pdf | ✅ |
| Spouse blind | `sp-blind` | `TaxpayerSchema.spouse.is_blind` | Std ded +$1,550 | f1040.pdf | ✅ |
| Spouse W-2 Box 13 retirement | *(auto-derived from spouse W-2s)* | `spouse.w2_box13_ret_plan` | IRA phase-out | p590a.pdf | ✅ |

---

## 2 — Dependents

*One row per dependent. Repeating id pattern: `dep-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| First name | `dep-first-${id}` | `Dependent.first` | 1040 p1 dependents | f1040.pdf | ✅ |
| Last name | `dep-last-${id}` | `Dependent.last` | 1040 p1 dependents | f1040.pdf | ✅ |
| SSN | `dep-ssn-${id}` | `Dependent.ssn` | 1040 p1 dependents | f1040.pdf | ✅ |
| Date of birth | `dep-dob-${id}` | `Dependent.dob` | Age → CTC/ODC | f1040.pdf | ✅ |
| Relationship | `dep-rel-${id}` | `Dependent.relationship` | Qualifying tests | f1040.pdf | ✅ |
| CTC eligible (override) | `dep-ctc-${id}` | `Dependent.ctc_eligible` | L19 CTC $2,000 | IRC §24 | ✅ |
| ODC eligible (auto-computed) | `dep-odc-${id}` (hidden) | `Dependent.odc_eligible` | Schedule 8812 $500 | IRC §24(h)(4) | ✅ |
| Unearned income (Kiddie Tax) | `dep-unearned-${id}` | `Form8615Data.unearned_income` | Form 8615 L1 | f8615.pdf | ✅ |
| Earned income | `dep-earned-${id}` | `Form8615Data.earned_income` | Form 8615 | f8615.pdf | ✅ |
| Full-time student (age 19–23) | `dep-student-${id}` | `Form8615Data.child_is_full_time_student` | Form 8615 kiddie tax | f8615.pdf | ✅ |

---

## 3 — W-2 Wages

*One row per employer. Repeating id pattern: `w2-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Employer name | `w2-emp-${id}` | `W2.employer` | 1040 header | iw2w3.pdf | ✅ |
| EIN (Box b) | `w2-ein-${id}` | `W2.ein` | Identification | iw2w3.pdf | ✅ |
| For spouse? | `w2-spouse-${id}` | `W2.for_spouse` | MFJ income tests | f2441.pdf | ✅ |
| Box 1 — Wages | `w2-box1-${id}` | `W2.box1_wages` | 1040 Line 1z | iw2w3.pdf | ✅ |
| Box 2 — Fed WH | `w2-box2-${id}` | `W2.box2_fed_wh` | 1040 Line 25a | iw2w3.pdf | ✅ |
| Box 3 — SS wages | `w2-box3-${id}` | `W2.box3_ss_wages` | SE SS cap | iw2w3.pdf | ✅ |
| Box 4 — SS WH | `w2-box4-${id}` | `W2.box4_ss_wh` | Excess SS WH | iw2w3.pdf | ✅ |
| Box 5 — Medicare wages | `w2-box5-${id}` | `W2.box5_med_wages` | Form 8959 Addl Medicare | iw2w3.pdf | ✅ |
| Box 6 — Medicare WH | `w2-box6-${id}` | `W2.box6_med_wh` | Form 8959 | iw2w3.pdf | ✅ |
| Box 7 — SS tips | `w2-box7-${id}` | `W2.box7_ss_tips` | 1040 Line 1b | iw2w3.pdf | ✅ |
| Box 8 — Allocated tips | `w2-box8-${id}` | `W2.box8_allocated_tips` | Sch 1 Line 8 | iw2w3.pdf | ✅ |
| Box 10 — Dep care benefits | `w2-box10-${id}` | `W2.box10_dependent_care` | Form 2441 L12 | iw2w3.pdf | ✅ |
| Box 11 — Nonqual deferred comp | `w2-box11-${id}` | `W2.box11_nonqual_def_comp` | 1040 Line 1 | iw2w3.pdf | ✅ |
| Box 12a (code + amount) | `w2-b12a-${id}` | `W2.box12a_code / box12a_amt` | HSA/401k/GTL | iw2w3.pdf | ✅ |
| Box 12b (code + amount) | `w2-b12b-${id}` | `W2.box12b_code / box12b_amt` | HSA/401k/GTL | iw2w3.pdf | ✅ |
| Box 12c (code + amount) | `w2-b12c-${id}` | `W2.box12c_code / box12c_amt` | HSA/401k/GTL | iw2w3.pdf | ✅ |
| Box 12d (code + amount) | `w2-b12d-${id}` | `W2.box12d_code / box12d_amt` | HSA/401k/GTL | iw2w3.pdf | ✅ |
| Box 13 — Retirement plan | `w2-box13-${id}` | `W2.box13_retirement_plan` | IRA deduction phase-out | p590a.pdf | ✅ |
| Box 14 — Other (SDI, union) | `w2-box14-${id}` | `W2.box14_other` | CA SDI credit | iw2w3.pdf | ✅ |
| Box 15 — State | `w2-state-${id}` | `W2.box15_state` | State return | iw2w3.pdf | ✅ |
| Box 16 — State wages | `w2-statew-${id}` | `W2.box16_state_wages` | State return | iw2w3.pdf | ✅ |
| Box 17 — State WH | `w2-statewh-${id}` | `W2.box17_state_wh` | State return | iw2w3.pdf | ✅ |
| Box 18 — Local wages | `w2-locw-${id}` | `W2.box18_local_wages` | Local return | iw2w3.pdf | ✅ |
| Box 19 — Local WH | `w2-locwh-${id}` | `W2.box19_local_wh` | Local return | iw2w3.pdf | ✅ |
| Box 20 — Locality name | `w2-locname-${id}` | `W2.box20_locality_name` | Local return | iw2w3.pdf | ✅ |

---

## 4 — 1099-INT Interest Income

*One row per payer. Repeating id pattern: `int-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `int-payer-${id}` | `Form1099INT.payer` | Schedule B | f1099int.pdf | ✅ |
| Payer EIN | `int-ein-${id}` | `Form1099INT.payer_ein` | Schedule B | f1099int.pdf | ✅ |
| Box 1 — Interest | `int-box1-${id}` | `Form1099INT.box1_interest` | Sch B → Line 2b | f1099int.pdf | ✅ |
| Box 2 — Early withdrawal penalty | `int-box2-${id}` | `Form1099INT.box2_early_withdrawal_penalty` | Sch 1 Line 18 | f1099int.pdf | ✅ |
| Box 3 — US savings bond interest | `int-box3-${id}` | `Form1099INT.box3_us_savings_bond` | Line 2b (state-exempt) | f1099int.pdf | ✅ |
| Box 4 — Federal backup WH | `int-box4-${id}` | `Form1099INT.box4_fed_wh` | Line 25b | f1099int.pdf | ✅ |
| Box 6 — Foreign tax paid | `int-box6-${id}` | `Form1099INT.box6_foreign_tax` | Form 1116 | f1099int.pdf | ✅ |
| Box 7 — Foreign country | `int-box7-${id}` | `Form1099INT.box7_foreign_country` | Form 1116 | f1099int.pdf | ✅ |
| Box 8 — Tax-exempt interest | `int-box8-${id}` | `Form1099INT.box8_tax_exempt_interest` | Line 2a + SS prov. income | f1099int.pdf | ✅ |
| Box 9 — Private activity bond | *(not in UI)* | `Form1099INT.box9_private_activity_bond` | Form 6251 L3 | f1099int.pdf | ❌ |
| Box 10 — Market discount | *(not in UI)* | `Form1099INT.box10_market_discount` | Sch B ordinary income | f1099int.pdf | ❌ |
| Box 11 — Bond premium | *(not in UI)* | `Form1099INT.box11_bond_premium` | Offsets Box 1 on Sch B | f1099int.pdf | ❌ |
| Box 15 — State WH | *(not in UI)* | `Form1099INT.box15_state_wh` | State return | f1099int.pdf | ❌ |

---

## 5 — 1099-DIV Dividends & Distributions

*One row per payer. Repeating id pattern: `div-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `div-payer-${id}` | `Form1099DIV.payer` | Schedule B | f1099div.pdf | ✅ |
| Box 1a — Ordinary dividends | `div-b1a-${id}` | `Form1099DIV.box1a_ordinary_div` | Line 3b via Sch B | f1099div.pdf | ✅ |
| Box 1b — Qualified dividends | `div-b1b-${id}` | `Form1099DIV.box1b_qualified_div` | Line 3a QDCGT | f1099div.pdf | ✅ |
| Box 2a — Cap gain distributions | `div-b2a-${id}` | `Form1099DIV.box2a_cap_gain_dist` | Sch D Line 13 | f1099div.pdf | ✅ |
| Box 2b — Unrec §1250 gain | `div-b2b-${id}` | `Form1099DIV.box2b_unrec_1250` | QDCGT 25% rate | f1099div.pdf | ⚠ |
| Box 2d — Collectibles gain | `div-b2d-${id}` | `Form1099DIV.box2d_collectibles` | QDCGT 28% rate | f1099div.pdf | ⚠ |
| Box 3 — Nondividend distributions | `div-b3-${id}` | `Form1099DIV.box3_nondiv_dist` | Return of capital | f1099div.pdf | ✅ |
| Box 4 — Federal backup WH | `div-b4-${id}` | `Form1099DIV.box4_fed_wh` | Line 25b | f1099div.pdf | ✅ |
| Box 5 — §199A dividends | `div-b5-${id}` | `Form1099DIV.box5_sec199a_div` | Form 8995 QBI | f1099div.pdf | ✅ |
| Box 7 — Foreign tax paid | `div-b7-${id}` | `Form1099DIV.box7_foreign_tax` | Form 1116 / Sch 3 L1 | f1099div.pdf | ✅ |
| Box 9 — Cash liquidation dist. | `div-b9-${id}` | `Form1099DIV.box3_nondiv_dist` | Return of capital | f1099div.pdf | ✅ |
| Box 11 — Exempt-interest divs | `div-b11-${id}` | `Form1099DIV.box11_exempt_interest` | Line 2a + SS prov. income | f1099div.pdf | ✅ |
| Box 12 — Private activity bond | `div-b12-${id}` | `Form1099DIV.box12_private_activity` | Form 6251 Line 3 | f1099div.pdf | ✅ |
| Box 15 — State WH | `div-b15-${id}` | `Form1099DIV.box15_state_wh` | State return | f1099div.pdf | ✅ |
| Box 2c — §1202 gain | *(not in UI)* | `Form1099DIV.box2c_sec1202` | 28% rate | f1099div.pdf | ❌ |
| Box 6 — Investment expenses | *(not in UI)* | `Form1099DIV.box6_invest_expense` | Sch A Line 9 | f1099div.pdf | ❌ |

---

## 6 — 1099-R Pension, Annuity & IRA Distributions

*One row per payer. Repeating id pattern: `r-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `r-payer-${id}` | `Form1099R.payer` | 1040 Lines 4a/5a | f1099r.pdf | ✅ |
| Payer EIN | `r-ein-${id}` | `Form1099R.payer_tin` | Identification | f1099r.pdf | ✅ |
| Account number | `r-acct-${id}` | `Form1099R.account_number` | Identification | f1099r.pdf | ✅ |
| Box 1 — Gross distribution | `r-box1-${id}` | `Form1099R.box1_gross` | Lines 4a/5a | f1099r.pdf | ✅ |
| Box 2a — Taxable amount | `r-box2a-${id}` | `Form1099R.box2a_taxable` | Lines 4b/5b | f1099r.pdf | ✅ |
| Box 2b — Checkboxes | `r-box2b-${id}` | `Form1099R.box2b_not_determined` | Taxability flag | f1099r.pdf | ✅ |
| Box 3 — Capital gain | `r-box3-${id}` | `Form1099R.box3_capital_gain` | Form 4972 | f1099r.pdf | ✅ |
| Box 4 — Fed WH | `r-box4-${id}` | `Form1099R.box4_fed_wh` | Line 25b | f1099r.pdf | ✅ |
| Box 5 — Employee contributions | `r-box5-${id}` | `Form1099R.box5_employee_contrib` | Cost basis | f1099r.pdf | ✅ |
| Box 6 — NUA | `r-box6-${id}` | `Form1099R.box6_nua` | Excludes from ordinary | f1099r.pdf | ✅ |
| Box 7 — Distribution code | `r-code-${id}` | `Form1099R.box7_code` | Penalty / routing | f1099r.pdf | ✅ |
| Box 7 — Second code | `r-code2-${id}` | `Form1099R.box7_code2` | Combined codes | f1099r.pdf | ✅ |
| Box 7 — IRA/SEP/SIMPLE checkbox | `r-ira-${id}` | `Form1099R.box7_ira_sep_simple` | Lines 4a/4b vs 5a/5b | f1099r.pdf | ✅ |
| Box 9a — % of total distribution | `r-box9a-${id}` | `Form1099R.box9a_pct_total_dist` | Proration | f1099r.pdf | ✅ |
| Box 9b — Employee contributions | `r-box9b-${id}` | `Form1099R.box9b_employee_contribs` | Simplified Method trigger | p575.pdf | ✅ |
| Box 10 — IRR within 5 years | `r-box10-${id}` | `Form1099R.box10_irr_within_5yrs` | Roth ordering | f1099r.pdf | ✅ |
| Box 11 — First year Roth | `r-box11-${id}` | `Form1099R.box11_roth_first_year` | Roth 5-yr clock | f1099r.pdf | ✅ |
| Box 12 — FATCA | `r-box12-${id}` | `Form1099R.box12_fatca` | Form 8938 flag | f1099r.pdf | ✅ |
| Box 13 — Date of payment | `r-box13-${id}` | `Form1099R.box13_date_of_payment` | §6050Y death benefits | f1099r.pdf | ✅ |
| Box 14 — State WH | `r-statewh-${id}` | `Form1099R.box14_state_wh` | State return | f1099r.pdf | ✅ |
| Box 15 — State / payer no. | `r-state-${id}` | `Form1099R.box15_state_payer_number` | State return | f1099r.pdf | ✅ |
| Box 16 — State distribution | `r-stated-${id}` | `Form1099R.box16_state_dist` | State return | f1099r.pdf | ✅ |
| Box 17 — Local WH | `r-locwh-${id}` | `Form1099R.box17_local_wh` | Local return | f1099r.pdf | ✅ |
| Box 18 — Locality name | `r-locname-${id}` | `Form1099R.box18_locality_name` | Local return | f1099r.pdf | ✅ |
| Box 19 — Local distribution | `r-locd-${id}` | `Form1099R.box19_local_dist` | Local return | f1099r.pdf | ✅ |
| Simplified Method — use? | `r-sm-${id}` | `SimplifiedMethodData.use_simplified_method` | Tax-free portion | p575.pdf | ✅ |
| Simplified Method — annuity type | `r-smtype-${id}` | `SimplifiedMethodData.annuity_type` | Expected payments table | p575.pdf | ✅ |
| Simplified Method — age at start | `r-smage-${id}` | `SimplifiedMethodData.age_at_annuity_start` | Table 1 lookup | p575.pdf | ✅ |
| Simplified Method — joint age | `r-smagej-${id}` | `SimplifiedMethodData.joint_age_at_annuity_start` | Table 2 lookup | p575.pdf | ✅ |
| Simplified Method — fixed months | `r-smfixed-${id}` | `SimplifiedMethodData.fixed_period_months` | Fixed period | p575.pdf | ✅ |
| Simplified Method — prior recovered | `r-smprior-${id}` | `SimplifiedMethodData.prior_year_tax_free_recovered` | L6 Wk A | p575.pdf | ✅ |
| Simplified Method — start date | `r-smstart-${id}` | `SimplifiedMethodData.annuity_start_after_nov_18_1996` | Table version | p575.pdf | ✅ |

---

## 7 — SSA-1099 Social Security Benefits

*Singleton fields (one per return)*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
⚠ **Bridge note**: UI sends `box6_vol_wh`; engine field is `box6_voluntary_wh`. Without the bridge, SSA voluntary WH is silently zero and refund is understated by the WH amount.

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Recipient (taxpayer/spouse) | `ss-recipient` | *(routing flag)* | Attribution | f1099ssa.pdf | ✅ |
| Box 3 — Gross benefits | `ss-gross` | `FormSSA1099.box3_gross_benefits` | Line 6a | p915.pdf | ✅ |
| Box 4 — Repayments | `ss-rep` | `FormSSA1099.box4_repayments` | Net benefit calc | p915.pdf | ✅ |
| Box 5 — Net benefits | `ss-net` | `FormSSA1099.box5_net_benefits` | Line 6a | p915.pdf | ✅ |
| Box 6 — Voluntary WH | `ss-wh` | `FormSSA1099.box6_voluntary_wh` *(schema sends: `box6_vol_wh`)* | Line 25b | p915.pdf | ✅ |
| Medicare Part B premiums | `ss-medicare-b` | *(informational)* | IRMAA / Sch A | SSA notice | ✅ |
| Medicare Part D premiums | `ss-medicare-d` | *(informational)* | IRMAA | SSA notice | ✅ |
| Medicare Part C premiums | `ss-medicare-c` | *(informational)* | IRMAA | SSA notice | ✅ |
| MFS lived apart all year | `ss-mfs-apart` | `FormSSA1099.mfs_lived_apart_all_year` | Base $25k vs $0 | p915.pdf | ✅ |
| Lump-sum election? | `ss-lump-yn` | *(triggers lump_sum_prior_years list)* | Line 6c checkbox | p915.pdf | ✅ |

### 7a — SSA Lump-Sum Prior Years

*One row per prior year. Repeating id pattern: `lump-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Prior year | `lump-yr-${id}` | `SSALumpSumPriorYear.prior_year` | Worksheet 2 | p915.pdf | ✅ |
| Amount in Box 3 for this year | `lump-amt-${id}` | `SSALumpSumPriorYear.lump_sum_amount_for_this_year` | Worksheet 2 L1 | p915.pdf | ✅ |
| Prior-year net SS benefits | `lump-ss-${id}` | `SSALumpSumPriorYear.prior_year_net_ss_benefits` | Worksheet 2 L1 | p915.pdf | ✅ |
| Prior-year AGI | `lump-agi-${id}` | `SSALumpSumPriorYear.prior_year_agi` | Worksheet 2 L3 | p915.pdf | ✅ |
| Prior-year tax-exempt interest | `lump-tei-${id}` | `SSALumpSumPriorYear.prior_year_tax_exempt_interest` | Worksheet 2 L5 | p915.pdf | ✅ |
| Prior-year taxable SS already reported | `lump-tax-${id}` | `SSALumpSumPriorYear.prior_year_taxable_ss_already_reported` | Worksheet 2 L20 | p915.pdf | ✅ |
| Pre-1994 year? | `lump-pre-${id}` | `SSALumpSumPriorYear.is_pre_1994` | Worksheet 3 flag | p915.pdf | ✅ |

---

## 8 — Self-Employment (Schedule C)

### 8a — 1099-NEC (SE page)

*One row per payer. Repeating id pattern: `necse-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `necse-payer-${id}` | `Form1099NEC.payer` | Sch C gross | f1099nec.pdf | ✅ |
| Payer EIN | `necse-ein-${id}` | `Form1099NEC.payer_ein` | Identification | f1099nec.pdf | ✅ |
| Box 1 — Nonemployee comp | `necse-box1-${id}` | `Form1099NEC.box1_nonemployee_comp` | Sch C gross → Line 3 | f1099nec.pdf | ✅ |
| Box 4 — Federal backup WH | `necse-box4-${id}` | `Form1099NEC.box4_fed_wh` | Line 25b | f1099nec.pdf | ✅ |
| Box 5 — State WH | `necse-box5-${id}` | `Form1099NEC.box5_state_wh` | State return | f1099nec.pdf | ✅ |
| Box 6 — State ID | `necse-box6-${id}` | `Form1099NEC.box6_state_id` | State return | f1099nec.pdf | ✅ |
| Box 7 — State income | `necse-box7-${id}` | `Form1099NEC.box7_state_income` | State return | f1099nec.pdf | ✅ |

### 8b — Schedule C Business

*One row per business. Repeating id pattern: `sc-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Business name | `sc-name-${id}` | `ScheduleC.business_name` | Sch C header | f1040sc.pdf | ✅ |
| Principal product/service | `sc-prod-${id}` | `ScheduleC.principal_product_service` | Sch C header | f1040sc.pdf | ✅ |
| For spouse? | `sc-spouse-${id}` | `ScheduleC.for_spouse` | MFJ SE income split | f1040sc.pdf | ✅ |
| Gross receipts (L1) | `sc-receipts-${id}` | `ScheduleC.gross_receipts` | Sch C Part I | f1040sc.pdf | ✅ |
| Returns & allowances (L2) | `sc-returns-${id}` | `ScheduleC.returns_allowances` | Sch C Part I | f1040sc.pdf | ✅ |
| Other income (L6) | `sc-other-inc-${id}` | `ScheduleC.other_income` | Sch C Part I | f1040sc.pdf | ✅ |
| Advertising (L8) | `sc-adv-${id}` | `ScheduleC.advertising` | Sch C Part II | f1040sc.pdf | ✅ |
| Car & truck (L9) | `sc-car-${id}` | `ScheduleC.car_truck_expenses` | Sch C Part II | f1040sc.pdf | ✅ |
| Commissions & fees (L10) | `sc-comm-${id}` | `ScheduleC.commissions_fees` | Sch C Part II | f1040sc.pdf | ✅ |
| Contract labor (L11) | `sc-cont-${id}` | `ScheduleC.contract_labor` | Sch C Part II | f1040sc.pdf | ✅ |
| Depletion (L12) | `sc-depl-${id}` | `ScheduleC.depletion` | Sch C Part II | f1040sc.pdf | ✅ |
| Depreciation (L13) | `sc-dep-${id}` | `ScheduleC.depreciation` | Sch C Part II | f1040sc.pdf | ✅ |
| Employee benefits (L14) | *(not in UI)* | `ScheduleC.employee_benefit_programs` | Sch C Part II | f1040sc.pdf | ❌ |
| Insurance (L15) | `sc-ins-${id}` | `ScheduleC.insurance` | Sch C Part II | f1040sc.pdf | ✅ |
| Mortgage interest (L16a) | *(not in UI)* | `ScheduleC.mortgage_interest` | Sch C Part II | f1040sc.pdf | ❌ |
| Other interest (L16b) | *(not in UI)* | `ScheduleC.other_interest` | Sch C Part II | f1040sc.pdf | ❌ |
| Legal & professional (L17) | `sc-legal-${id}` | `ScheduleC.legal_professional` | Sch C Part II | f1040sc.pdf | ✅ |
| Office expense (L18) | `sc-off-${id}` | `ScheduleC.office_expense` | Sch C Part II | f1040sc.pdf | ✅ |
| Pension & profit-sharing (L19) | `sc-pens-${id}` | `ScheduleC.pension_profit_sharing` | Sch C Part II | f1040sc.pdf | ✅ |
| Rent/lease — vehicles (L20a) | `sc-rentv-${id}` | `ScheduleC.rent_lease_vehicles` | Sch C Part II | f1040sc.pdf | ✅ |
| Rent/lease — other (L20b) | `sc-rent-${id}` | `ScheduleC.rent_lease_other` | Sch C Part II | f1040sc.pdf | ✅ |
| Repairs & maintenance (L21) | `sc-rep-${id}` | `ScheduleC.repairs_maintenance` | Sch C Part II | f1040sc.pdf | ✅ |
| Supplies (L22) | `sc-sup-${id}` | `ScheduleC.supplies` | Sch C Part II | f1040sc.pdf | ✅ |
| Taxes & licenses (L23) | `sc-tax-${id}` | `ScheduleC.taxes_licenses` | Sch C Part II | f1040sc.pdf | ✅ |
| Travel (L24a) | `sc-trav-${id}` | `ScheduleC.travel` | Sch C Part II | f1040sc.pdf | ✅ |
| Meals (L24b — enter full; 50% applied) | `sc-meals-${id}` | `ScheduleC.meals` | Sch C Part II × 50% | f1040sc.pdf | ✅ |
| Utilities (L25) | `sc-util-${id}` | `ScheduleC.utilities` | Sch C Part II | f1040sc.pdf | ✅ |
| Wages to employees (L26) | `sc-wages-${id}` | `ScheduleC.wages` | Sch C Part II | f1040sc.pdf | ✅ |
| Other expenses Part V (L27a) | `sc-othexp-${id}` | `ScheduleC.other_expenses` | Sch C Part II | f1040sc.pdf | ✅ |
| Home office sq ft | `sc-sqft-${id}` | `ScheduleC.home_office_sq_ft` | $5/sqft max 300 | f8829.pdf | ✅ |
| Use simplified home office | `sc-homeoff-${id}` | `ScheduleC.use_home_office_simplified` | Rev. Proc. 2013-13 | f8829.pdf | ✅ |
| COGS — Inventory beginning (L35) | `sc-invbeg-${id}` | `ScheduleC.inventory_beginning` | Sch C Part III | f1040sc.pdf | ✅ |
| COGS — Purchases (L36) | `sc-purch-${id}` | `ScheduleC.purchases` | Sch C Part III | f1040sc.pdf | ✅ |
| COGS — Cost of labor (L37) | `sc-labor-${id}` | `ScheduleC.cost_of_labor` | Sch C Part III | f1040sc.pdf | ✅ |
| COGS — Materials & supplies (L38) | `sc-mats-${id}` | `ScheduleC.materials_supplies_cogs` | Sch C Part III | f1040sc.pdf | ✅ |
| COGS — Other costs (L39) | `sc-othcogs-${id}` | `ScheduleC.other_cogs` | Sch C Part III | f1040sc.pdf | ✅ |
| COGS — Inventory ending (L41) | `sc-invend-${id}` | `ScheduleC.inventory_ending` | Sch C Part III | f1040sc.pdf | ✅ |
| W-2 wages (for Form 8995-A) | `sc-w2wages-${id}` | `ScheduleC.w2_wages` | Form 8995-A above threshold | f8995a.pdf | ✅ |
| UBIA qualified property | `sc-ubia-${id}` | `ScheduleC.ubia_qualified_property` | Form 8995-A | f8995a.pdf | ✅ |
| SSTB? | `sc-sstb-${id}` | `ScheduleC.is_sstb` | §199A SSTB phase-out | f8995.pdf | ✅ |

---

## 9 — Schedule E Rental Real Estate

*One row per property. Repeating id pattern: `sche-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Property address | `sche-addr-${id}` | `ScheduleE.address` | Sch E header | f1040se.pdf | ✅ |
| Days rented at fair market rate | `sche-dr-${id}` | `ScheduleE.days_rented` | §280A vacation rules | f1040se.pdf | ✅ |
| Days personal use | `sche-dp-${id}` | `ScheduleE.days_personal_use` | §280A vacation rules | f1040se.pdf | ✅ |
| Rents received (L3) | `sche-rents-${id}` | `ScheduleE.rents_received` | Sch 1 Line 5 | f1040se.pdf | ✅ |
| Insurance (L9) | `sche-ins-${id}` | `ScheduleE.insurance` | Sch E Part I | f1040se.pdf | ✅ |
| Management fees (L11) | `sche-mgt-${id}` | `ScheduleE.management_fees` | Sch E Part I | f1040se.pdf | ✅ |
| Mortgage interest (L12) | `sche-mort-${id}` | `ScheduleE.mortgage_interest` | Sch E Part I | f1040se.pdf | ✅ |
| Repairs (L14) | `sche-rep-${id}` | `ScheduleE.repairs` | Sch E Part I | f1040se.pdf | ✅ |
| Real estate taxes (L16) | `sche-tax-${id}` | `ScheduleE.taxes` | Sch E Part I | f1040se.pdf | ✅ |
| Utilities (L17) | `sche-util-${id}` | `ScheduleE.utilities` | Sch E Part I | f1040se.pdf | ✅ |
| Depreciation (L18) | `sche-dep-${id}` | `ScheduleE.depreciation` | Sch E Part I | f1040se.pdf | ✅ |
| Other expenses (L19) | `sche-oth-${id}` | `ScheduleE.other_expenses` | Sch E Part I | f1040se.pdf | ✅ |
| Participation type | `sche-part-${id}` | `ScheduleE.active_participation / is_real_estate_professional` | Form 8582 passive rules | f8582.pdf | ✅ |
| Prior year unallowed losses | `sche-prior-loss` | `Form8582Data.prior_year_unallowed_losses` | Form 8582 Wk 7 | f8582.pdf | ✅ |
| MFS lived apart (8582) | `sche-mfs-apart` | `Form8582Data.mfs_lived_apart` | $50k/$12.5k threshold | f8582.pdf | ✅ |
| Advertising (L5) | *(not in UI)* | `ScheduleE.advertising` | Sch E Part I | f1040se.pdf | ❌ |
| Auto & travel (L6) | *(not in UI)* | `ScheduleE.auto_travel` | Sch E Part I | f1040se.pdf | ❌ |
| Cleaning & maintenance (L7) | *(not in UI)* | `ScheduleE.cleaning_maintenance` | Sch E Part I | f1040se.pdf | ❌ |
| Commissions (L8) | *(not in UI)* | `ScheduleE.commissions` | Sch E Part I | f1040se.pdf | ❌ |
| Legal & professional (L10) | *(not in UI)* | `ScheduleE.legal_professional` | Sch E Part I | f1040se.pdf | ❌ |
| Other interest (L13) | *(not in UI)* | `ScheduleE.other_interest` | Sch E Part I | f1040se.pdf | ❌ |
| Supplies (L15) | *(not in UI)* | `ScheduleE.supplies` | Sch E Part I | f1040se.pdf | ❌ |

---

## 10 — Schedule K-1 Pass-Through Income

*One row per entity. Repeating id pattern: `k1-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Entity name | `k1-nm-${id}` | `ScheduleK1.entity_name` | Sch E Part II | f1065sk1.pdf | ✅ |
| Entity type | `k1-type-${id}` | `ScheduleK1.entity_type` | Routing rules | f1065sk1.pdf | ✅ |
| Participation | `k1-part-${id}` | `ScheduleK1.material_participation` | Form 8582 | f1065sk1.pdf | ✅ |
| Box 1 — Ordinary income (loss) | `k1-b1-${id}` | `ScheduleK1.box1_ordinary_income` | Sch E Part II | f1065sk1.pdf | ✅ |
| Box 2 — Net rental income (loss) | `k1-b2-${id}` | `ScheduleK1.box2_net_rental` | Sch E Part I equivalent | f1065sk1.pdf | ✅ |
| Box 5 — Interest | `k1-b5-${id}` | `ScheduleK1.box5_interest` | Sch B → Line 2b | f1065sk1.pdf | ✅ |
| Box 6a — Ordinary dividends | `k1-b6a-${id}` | `ScheduleK1.box6a_ordinary_div` | Sch B → Line 3b | f1065sk1.pdf | ✅ |
| Box 6b — Qualified dividends | `k1-b6b-${id}` | `ScheduleK1.box6b_qualified_div` | Line 3a QDCGT | f1065sk1.pdf | ✅ |
| Box 7 — Royalties | `k1-b7-${id}` | `ScheduleK1.box7_royalties` | Sch E Part II | f1065sk1.pdf | ✅ |
| Box 8 — Short-term cap gain | `k1-b8-${id}` | `ScheduleK1.box8_stcg` | Sch D | f1065sk1.pdf | ✅ |
| Box 9a — Long-term cap gain | `k1-b9a-${id}` | `ScheduleK1.box9_ltcg` | Sch D | f1065sk1.pdf | ✅ |
| Box 10 — §1231 gain (loss) | `k1-b10-${id}` | `ScheduleK1.box9a_sec1231` | Form 4797 | f1065sk1.pdf | ✅ |
| Box 11 — Other income | `k1-b11-${id}` | `ScheduleK1.box10_other_income` | Sch 1 Line 8z | f1065sk1.pdf | ✅ |
| Box 13 — Other deductions | `k1-b13-${id}` | `ScheduleK1.box13_other_deductions` | Various | f1065sk1.pdf | ✅ |
| Box 14a — SE earnings | `k1-b14-${id}` | `ScheduleK1.box14a_se_income` | Sch SE | f1065sk1.pdf | ✅ |
| Box 17 — AMT items | `k1-b17-${id}` | *(AMT preference)* | Form 6251 | f1065sk1.pdf | ✅ |
| Box 20Z — §199A income | `k1-b20z-${id}` | `ScheduleK1.box17_sec199a` | Form 8995 | f1065sk1.pdf | ✅ |
| Box 20W — §199A W-2 wages | `k1-b20w-${id}` | `ScheduleK1.box17_w2_wages` | Form 8995-A | f1065sk1.pdf | ✅ |
| Box 3 — Other net rental | *(not in UI)* | `ScheduleK1.box3_other_net_rental` | Sch E | f1065sk1.pdf | ❌ |
| Box 12 — §179 deduction | *(not in UI)* | `ScheduleK1.box12_sec179` | Form 4562 | f1065sk1.pdf | ❌ |
| Box 17 — UBIA | *(not in UI)* | `ScheduleK1.box17_ubia` | Form 8995-A | f1065sk1.pdf | ❌ |

---

## 11 — Capital Gains (Schedule D / Form 8949)

*One row per sale. Repeating id pattern: `sale-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Description | `sale-desc-${id}` | `Form1099B.description` | Form 8949 Col (a) | f8949.pdf | ✅ |
| Date info | `sale-dates-${id}` | `Form1099B.date_acquired / date_sold` | Form 8949 Col (b)(c) | f8949.pdf | ✅ |
| Proceeds | `sale-proc-${id}` | `Form1099B.proceeds` | Form 8949 Col (d) | f8949.pdf | ✅ |
| Cost basis | `sale-basis-${id}` | `Form1099B.cost_basis` | Form 8949 Col (e) | f8949.pdf | ✅ |
| Accrued market discount (Box 1f) | `sale-amd-${id}` | `Form1099B.accrued_discount` | Form 8949 adj Code D | f8949.pdf | ✅ |
| Wash sale disallowed (Box 1g) | `sale-wash-${id}` | `Form1099B.wash_sale_loss_disallowed` | Form 8949 adj Code W | f8949.pdf | ✅ |
| Term (long/short) | `sale-term-${id}` | `Form1099B.is_long_term` | Sch D L1b/L8b | f8949.pdf | ✅ |
| Basis reported to IRS | `sale-covered-${id}` | `Form1099B.basis_reported_to_irs` | Box A/B/C/D | f8949.pdf | ✅ |
| Prior year cap loss carryover | `cap-carryover` | `TaxpayerSchema.capital_loss_carryover_prior` | Sch D Line 6 | f1040sd.pdf | ✅ |

### 11a — Form 4797 Sales of Business Property

*One row per sale. Repeating id pattern: `f4797-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Property description | `f4797-desc-${id}` | `Form4797SaleData.description` | Form 4797 Line 19 | f4797.pdf | ✅ |
| Property type | `f4797-type-${id}` | `Form4797SaleData.property_type` | §1245/§1250 rules | f4797.pdf | ✅ |
| Held over 1 year? | `f4797-held-${id}` | `Form4797SaleData.held_over_one_year` | Part I vs II | f4797.pdf | ✅ |
| Gross proceeds | `f4797-proc-${id}` | `Form4797SaleData.gross_proceeds` | Form 4797 Line 20 | f4797.pdf | ✅ |
| Original cost | `f4797-cost-${id}` | `Form4797SaleData.original_cost` | Adjusted basis | f4797.pdf | ✅ |
| Depreciation taken | `f4797-depr-${id}` | `Form4797SaleData.depreciation_taken` | §1250 recapture | f4797.pdf | ✅ |
| Prior §1231 losses 5-yr | `f4797-prior1231-${id}` | `Form4797SaleData.prior_sec1231_losses_5yr` | §1231(c) lookback | f4797.pdf p544.pdf | ✅ |
| Date acquired | *(not in UI)* | `Form4797SaleData.date_acquired` | Holding period | f4797.pdf | ❌ |
| Date sold | *(not in UI)* | `Form4797SaleData.date_sold` | Holding period | f4797.pdf | ❌ |
| Suspended passive losses | *(not in UI)* | `Form4797SaleData.suspended_passive_losses` | §469(g) release | f4797.pdf f8582.pdf | ❌ |

---

## 12 — Other Income

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Unemployment (1099-G Box 1) | `unemp` | `Form1099G.box1_unemployment` | Sch 1 Line 7 | f1099g.pdf | ✅ |
| State tax refund (1099-G Box 2) | `state-refund` | `Form1099G.box2_state_refund` | Sch 1 Line 1 (if prior itemized) | f1099g.pdf | ✅ |
| Fed WH 1099-G (Box 4) | `unemp-wh` | `Form1099G.box4_fed_wh` | Line 25b | f1099g.pdf | ✅ |
| State WH 1099-G (Box 10a/11) | `unemp-state-wh` | `Form1099G.box11_state_wh` | State return | f1099g.pdf | ✅ |
| Prior year itemized? | `prior-yr-itemized` | `Form1099G.prior_year_itemized` | Tax benefit rule IRC §111 | f1099g.pdf | ✅ |
| Prize / award (1099-MISC Box 3) | `prize` | `Form1099MISC_Prize.box3_other_income` | Sch 1 Line 8b | f1099msc.pdf | ✅ |
| Other income | `other-adj` | `TaxpayerSchema.other_adjustments` | Sch 1 Line 8z | f1040s1.pdf | ✅ |
| Alimony received (pre-2019) | `alimony-rec` | `AlimonyData.alimony_received` | Sch 1 Line 2a | f1040s1.pdf | ✅ |
| Alimony paid (pre-2019) | `alimony-paid` | `AlimonyData.alimony_paid` | Sch 1 Line 19a | f1040s1.pdf | ✅ |
| Alimony payee SSN | `alimony-ssn` | `AlimonyData.recipient_ssn` | Sch 1 Line 19b | f1040s1.pdf | ✅ |
| Alimony era (pre-2019 / post-2018) | `alimony-era` | `AlimonyData.decree_pre_2019` | TCJA cut-off | IRC §71 | ✅ |

### 12a — W-2G Gambling Winnings

*One row per payer. Repeating id pattern: `w2g-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer | `w2g-payer-${id}` | `FormW2G.payer` | Sch 1 Line 8b | fw2g.pdf | ✅ |
| Box 1 — Winnings | `w2g-box1-${id}` | `FormW2G.box1_winnings` | Sch 1 Line 8b | fw2g.pdf | ✅ |
| Box 4 — Fed WH | `w2g-box4-${id}` | `FormW2G.box4_fed_wh` | Line 25b | fw2g.pdf | ✅ |
| Box 15 — State WH | `w2g-box15-${id}` | *(not in engine — field removed)* | State return | fw2g.pdf | ✅ |
| Box 16 — State ID | `w2g-box16-${id}` | *(not in engine — field removed)* | State return | fw2g.pdf | ✅ |
| Box 17 — Local WH | `w2g-box17-${id}` | *(not in engine — field removed)* | Local return | fw2g.pdf | ✅ |
| Gambling losses | `gambling-losses` | `TaxpayerSchema.gambling_losses` | Sch A Line 16 | IRC §165(d) | ✅ |

### 12b — 1099-C Cancellation of Debt

*One row per creditor. Repeating id pattern: `cod-xxx-${id}`*

⚠ **Bridge note**: UI sends `box2_discharged` + `exclusion_applies`; engine reads `box2_amount_discharged` + `is_excluded`. Bridge in `deserialize_schema()` translates both.

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Creditor name | `cod-cred-${id}` | `Form1099C.creditor` | Sch 1 Line 8c | f1099c.pdf | ✅ |
| Creditor EIN | `cod-ein-${id}` | `Form1099C.creditor_ein` | Identification | f1099c.pdf | ✅ |
| Recipient (taxpayer/spouse) | `cod-recipient-${id}` | *(routing flag)* | Attribution | f1099c.pdf | ✅ |
| Box 1 — Date of event | `cod-date-${id}` | `Form1099C.box1_date_of_event` | Record | f1099c.pdf | ✅ |
| Box 2 — Amount discharged | `cod-amt-${id}` | `Form1099C.box2_amount_discharged` *(schema: `box2_discharged`)* | Sch 1 Line 8c | f1099c.pdf | ✅ |
| Box 3 — Interest included | `cod-int-${id}` | `Form1099C.box3_interest` | Ordinary income | f1099c.pdf | ✅ |
| Box 4 — Debt description | `cod-desc-${id}` | `Form1099C.box4_debt_description` | Record | f1099c.pdf | ✅ |
| Box 5 — Personally liable? | `cod-recourse-${id}` | `Form1099C.box5_personally_liable` *(schema: `exclusion_applies` maps differently)* | Recourse vs non-recourse | f1099c.pdf | ✅ |
| Box 6 — Event code (A–H) | `cod-code-${id}` | `Form1099C.box6_event_code` | Discharge type | f1099c.pdf | ✅ |
| Box 7 — FMV of property | `cod-fmv-${id}` | `Form1099C.box7_fmv` | Non-recourse basis | f1099c.pdf | ✅ |
| Exclusion applies? | `cod-excl-${id}` | `Form1099C.is_excluded` *(schema: `exclusion_applies`)* | Form 982 flag | f982.pdf | ✅ |

### 12c — 1099-MISC (Other Income / Prize / Royalties)

*One row per payer. Repeating id pattern: `misc-xxx-${id}`*
*Box 3 Other Income (prizes, awards, taxable damages) → Sch 1 Line 8b via Form1099MISC_Prize bridge.*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `misc-payer-${id}` | bridge → `Form1099MISC_Prize.payer` | Sch 1 Line 8b | f1099msc.pdf | ✅ |
| Payer EIN | `misc-ein-${id}` | *(passthrough)* | Identification | f1099msc.pdf | ✅ |
| Recipient | `misc-recipient-${id}` | *(routing flag)* | Attribution | f1099msc.pdf | ✅ |
| Box 1 — Rents | `misc-b1-${id}` | *(→ Sch E if rental)* | Sch E Part I | f1099msc.pdf | ✅ |
| Box 2 — Royalties | `misc-b2-${id}` | *(→ Sch E royalties)* | Sch E Part I | f1099msc.pdf | ✅ |
| Box 3 — Other income (prizes) | `misc-b3-${id}` | `Form1099MISC_Prize.box3_other_income` | Sch 1 Line 8b | f1099msc.pdf | ✅ |
| Box 4 — Federal WH | `misc-b4-${id}` | *(→ Line 25b)* | Line 25b | f1099msc.pdf | ✅ |
| Box 5 — Fishing proceeds | `misc-b5-${id}` | *(informational)* | Sch C | f1099msc.pdf | ✅ |
| Box 6 — Medical payments | `misc-b6-${id}` | *(informational)* | Sch C | f1099msc.pdf | ✅ |
| Box 7 — Direct sales | `misc-b7-${id}` | *(checkbox)* | Informational | f1099msc.pdf | ✅ |
| Box 8 — Substitute payments | `misc-b8-${id}` | *(→ Sch B)* | Sch B | f1099msc.pdf | ✅ |
| Box 9 — Crop insurance | `misc-b9-${id}` | *(informational)* | Sch F | f1099msc.pdf | ✅ |
| Box 10 — Attorney proceeds | `misc-b10-${id}` | *(informational)* | Sch 1 Line 8z | f1099msc.pdf | ✅ |
| Box 11 — Fish purchased | `misc-b11-${id}` | *(informational)* | Sch C | f1099msc.pdf | ✅ |
| Box 12 — §409A deferrals | `misc-b12-${id}` | *(informational)* | W-2 Box 12 | f1099msc.pdf | ✅ |
| Box 13 — Golden parachute | `misc-b13-${id}` | *(informational)* | Excise tax | f1099msc.pdf | ✅ |
| Box 14 — NQDC | `misc-b14-${id}` | *(informational)* | Compensation | f1099msc.pdf | ✅ |
| Box 15a — State WH | `misc-b15a-${id}` | *(→ state return)* | State | f1099msc.pdf | ✅ |
| Box 15b — State payer ID | `misc-b15b-${id}` | *(informational)* | State | f1099msc.pdf | ✅ |
| Box 16 — State income | `misc-b16-${id}` | *(→ state return)* | State | f1099msc.pdf | ✅ |

### 12d — 1099-NEC (Other Income page)

*One row per payer where no Schedule C exists. Repeating id pattern: `nec-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Payer name | `nec-payer-${id}` | `Form1099NEC.payer` | Sch C gross | f1099nec.pdf | ✅ |
| Payer EIN | `nec-ein-${id}` | `Form1099NEC.payer_ein` | Identification | f1099nec.pdf | ✅ |
| Box 1 — Nonemployee comp | `nec-box1-${id}` | `Form1099NEC.box1_nonemployee_comp` | Sch C gross → Line 3 | f1099nec.pdf | ✅ |
| Box 4 — Backup WH | `nec-box4-${id}` | `Form1099NEC.box4_fed_wh` | Line 25b | f1099nec.pdf | ✅ |

---

## 13 — Above-Line Adjustments (Schedule 1 Part II)

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Teacher / educator expense | `adj-teacher` | `TaxpayerSchema.teacher_expense` | Sch 1 Line 11 (max $300) | f1040s1.pdf | ✅ |
| Student loan interest | `adj-student-loan` | `TaxpayerSchema.student_loan_interest` | Sch 1 Line 21 | f1040s1.pdf | ✅ |
| Early CD withdrawal penalty | `adj-early-wdwl` | *(derived from 1099-INT box2_early_withdrawal_penalty)* | Sch 1 Line 18 | f1040s1.pdf | ✅ |
| SE health insurance premiums | `adj-se-health` | `TaxpayerSchema.se_health_insurance_premiums` | Sch 1 Line 17 | f1040s1.pdf IRC §162(l) | ✅ |
| Other above-line adjustments | `adj-other` | `TaxpayerSchema.other_adjustments` | Sch 1 Line 24z | f1040s1.pdf | ✅ |
| NOL carryforward from prior year | `nol-carryforward` | `TaxpayerSchema.nol_carryforward_prior_year` | Sch 1 Line 8a (80% TI limit) | p536.pdf IRC §172 | ✅ |
| QBI loss carryforward | `qbi-loss-cf` | `TaxpayerSchema.qbi_loss_carryforward` | Form 8995 Line 11 | f8995.pdf | ✅ |

### 13a — SE Retirement (Schedule 1 Line 16)

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| SE retirement contributions | `se-ret-contrib` | `TaxpayerSchema.se_retirement_contributions` | Sch 1 Line 16 | f1040s1.pdf p560.pdf | ✅ |
| SE retirement plan type | `se-ret-type` | `TaxpayerSchema.se_retirement_plan_type` | SEP/Solo401k/SIMPLE limits | p560.pdf | ✅ |

### 13b — Estimated Tax Payments (Form 1040-ES)

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Q1 — due Apr 15 | `est-q1` | `EstimatedTaxPayments.q1` | Line 26 | f1040es.pdf | ✅ |
| Q2 — due Jun 16 | `est-q2` | `EstimatedTaxPayments.q2` | Line 26 | f1040es.pdf | ✅ |
| Q3 — due Sep 15 | `est-q3` | `EstimatedTaxPayments.q3` | Line 26 | f1040es.pdf | ✅ |
| Q4 — due Jan 15, 2026 | `est-q4` | `EstimatedTaxPayments.q4` | Line 26 | f1040es.pdf | ✅ |
| Prior-year overpayment applied | `est-prior` | `EstimatedTaxPayments.prior_year_overpayment_applied` | Line 26 | f1040es.pdf | ✅ |

### 13c — Form 2210 Underpayment Safe Harbor

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Prior year (2024) total tax | `py-tax` | `Form2210Data.prior_year_tax` | Safe harbor test (b) | f2210.pdf | ✅ |
| Prior year (2024) AGI | `py-agi` | `Form2210Data.prior_year_agi` | 110% test threshold | f2210.pdf | ✅ |

---

## 14 — Schedule A Itemized Deductions

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Use itemized deductions? | `use-itemized` | `TaxpayerSchema.use_itemized` | Std vs itemized | f1040sa.pdf | ✅ |
| Medical & dental total | `sa-medical` | `ScheduleAData.medical_dental_total` | L1 (7.5% AGI floor) | f1040sa.pdf | ✅ |
| SALT method (income vs sales tax) | `sa-salt-method` | *(routing flag)* | L5a choice | f1040sa.pdf IRC §164 | ✅ |
| State/local income or sales tax | `sa-state-inc` | `ScheduleAData.state_income_tax` | L5a ($10k cap) | f1040sa.pdf | ✅ |
| Real estate taxes | `sa-re-tax` | `ScheduleAData.real_estate_tax` | L5b ($10k cap) | f1040sa.pdf | ✅ |
| Personal property taxes | `sa-pp-tax` | `ScheduleAData.personal_property_tax` | L5c ($10k cap) | f1040sa.pdf | ✅ |
| Form 1098 mortgage interest | `sa-mort-int` | `ScheduleAData.mortgage_interest_1098` | L8a | f1040sa.pdf f1098.pdf | ✅ |
| Outstanding mortgage balance | `sa-mort-bal` | *(limit enforcement)* | $750k / $1M cap | IRS Pub 936 | ✅ |
| Grandfathered pre-12/16/2017? | `sa-grandfathered` | *(limit flag)* | $1M limit | IRS Pub 936 | ✅ |
| Points not on Form 1098 | `sa-points` | `ScheduleAData.mortgage_points` | L8c | f1040sa.pdf | ✅ |
| PMI / MIP (EXPIRED 2025) | `sa-pmi` (disabled) | `ScheduleAData.mortgage_insurance_premiums` | L8d ($0 for 2025) | IRS Pub 936 (2025) | ✅ |
| Investment interest | `sa-invest-int` | `ScheduleAData.investment_interest` | L9 | f1040sa.pdf | ✅ |
| Cash / check contributions | `sa-cash-char` | `ScheduleAData.cash_charitable` | L11 | f1040sa.pdf | ✅ |
| Non-cash contributions | `sa-noncash` | `ScheduleAData.noncash_charitable` | L12 (Form 8283 if >$500) | f1040sa.pdf | ✅ |
| Charitable carryover | `sa-char-co` | `ScheduleAData.carryover_charitable` | L13 | f1040sa.pdf | ✅ |
| Casualty / theft loss | `sa-casualty` | `ScheduleAData.casualty_theft_loss` | L15 (disaster area only) | f4684.pdf | ✅ |
| Other miscellaneous | `sa-other` | `ScheduleAData.other_misc` | L16 | f1040sa.pdf | ✅ |

---

## 15 — Credits

### 15a — Form 2441 Child & Dependent Care

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Employer dep. care benefits (W-2 Box 10 total) | `emp-dep-care` | *(derived from W-2 box10_dependent_care)* | Form 2441 L12 §129 exclusion | f2441.pdf | ✅ |

*Care providers — Repeating id pattern: `care-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Provider name | `care-name-${id}` | `Form2441Provider.name` | Form 2441 | f2441.pdf | ✅ |
| Provider EIN | `care-ein-${id}` | `Form2441Provider.ein` | Form 2441 | f2441.pdf | ✅ |
| Qualified expenses paid | `care-exp-${id}` | `Form2441Provider.expenses` | Form 2441 L3 | f2441.pdf | ✅ |

### 15b — Form 8863 Education Credits

*One row per student. Repeating id pattern: `t-xxx-${id}`*

⚠ **Bridge note**: export writes `institution`, `student_is`, `box8_at_least_half_time`, `out_of_pocket_books/supplies/other`; import reads both old and new key names. Always use the current keys below.

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Institution name | `t-inst-${id}` | `Form1098T.institution` | Form 8863 | f8863.pdf | ✅ |
| Box 1 — Payments received | `t-box1-${id}` | `Form1098T.box1_payments` | Form 8863 net expenses | f1098t.pdf | ✅ |
| Box 5 — Scholarships / grants | `t-box5-${id}` | `Form1098T.box5_scholarships` | Reduces qualified expenses | f1098t.pdf | ✅ |
| Student name | `t-student-${id}` | `Form1098T.student_name` | Form 8863 | f8863.pdf | ✅ |
| Student is (taxpayer/spouse/dep) | `t-who-${id}` | `Form1098T.student_who` *(also: `student_who`)* | Credit attribution | f8863.pdf | ✅ |
| Credit type (AOC / LLC) | `t-type-${id}` | `Form1098T.credit_type` | AOC → L29 refundable; LLC → Sch 3 | f8863.pdf | ✅ |
| AOC prior years claimed | `t-aoc-prior-${id}` | `Form1098T.aoc_years_claimed_prior` | First 4 years only | f8863.pdf | ✅ |
| Books & required materials | `t-books-${id}` | `Form1098T.out_of_pocket_books` | Qualified expenses | f8863.pdf | ✅ |
| Required supplies & equipment | `t-supplies-${id}` | `Form1098T.out_of_pocket_supplies` | Qualified expenses | f8863.pdf | ✅ |
| Other qualified expenses | `t-other-qee-${id}` | `Form1098T.out_of_pocket_other` | Qualified expenses | f8863.pdf | ✅ |
| Box 8 — At least half-time | `t-halftime-${id}` | `Form1098T.box8_half_time` | AOC eligibility | f1098t.pdf | ✅ |
| Box 9 — Graduate student | `t-grad-${id}` | `Form1098T.box9_graduate` | LLC only (no AOC for grad) | f1098t.pdf | ✅ |

### 15c — Form 8880 Retirement Savings Credit

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| IRA contributions (L1) | `f8880-ira` | `Form8880Data.ira_contributions` | Form 8880 L1 | f8880.pdf | ✅ |
| Elective deferrals 401k/403b (L2) | `f8880-deferrals` | `Form8880Data.elective_deferrals` | Form 8880 L2 | f8880.pdf | ✅ |
| Disqualifying distributions (L4) | `f8880-dist` | `Form8880Data.disqualifying_dist` | Form 8880 L4 | f8880.pdf | ✅ |

### 15d — Form 8962 Premium Tax Credit (ACA)

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Household size | `aca-size` | `TaxpayerSchema.aca_household_size` | Form 8962 L1 | f8962.pdf | ✅ |
| Coverage method (annual/monthly) | `aca-method` | *(routing flag)* | Lines 11 vs 12–23 | f8962.pdf | ✅ |
| 1095-A Col A — Annual premium | `aca-cola` | `Form1095A.col_a_annual` | Form 8962 L11a | f1095a.pdf | ✅ |
| 1095-A Col B — SLCSP annual | `aca-colb` | `Form1095A.col_b_annual` | Form 8962 L11b | f1095a.pdf | ✅ |
| 1095-A Col C — APTC paid | `aca-colc` | `Form1095A.col_c_annual` | Form 8962 L11c | f1095a.pdf | ✅ |

### 15e — EITC

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Exact EITC from IRS table | `exact-eitc` | `TaxpayerSchema.exact_eitc_from_table` | Line 27a override | p596.pdf EIC Table | ✅ |

---

## 16 — IRA · HSA · SE Retirement · Form 8606 · Form 5329

### 16a — Traditional IRA

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| IRA contribution | `ira-contrib` | `TaxpayerSchema.ira_contribution_traditional` | Sch 1 Line 20 (auto phase-out) | p590a.pdf | ✅ |
| Taxpayer age at Dec 31 | `ira-age` | `TaxpayerSchema.ira_taxpayer_age` | Catch-up limit $8k if 50+ | p590a.pdf | ✅ |
| Covered by workplace plan? | `ira-covered` | *(derived from W-2 Box 13)* | Phase-out $79k–$89k single | p590a.pdf | ✅ |

### 16b — Form 8606 Nondeductible IRA & Roth

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| L1 — Nondeductible contributions | `f8606-contrib` | `Form8606Data.nonded_contrib_this_year` | Form 8606 Part I | f8606.pdf | ✅ |
| L2 — Prior basis | `f8606-prior-basis` | `Form8606Data.basis_prior_year` | Form 8606 L2 | f8606.pdf | ✅ |
| L6 — FMV all IRAs Dec 31 | `f8606-ira-val` | `Form8606Data.trad_ira_value_dec31` | Form 8606 L6 (aggregation rule) | f8606.pdf | ✅ |
| L7 — Total IRA distributions | `f8606-dist` | `Form8606Data.trad_ira_distributions` | Form 8606 L7 | f8606.pdf | ✅ |
| Roth conversion amount (L16) | `f8606-conversion` | `Form8606Data.conversion_amount` | Form 8606 Part II | f8606.pdf | ✅ |
| L19 — Roth distributions | `f8606-roth-dist` | `Form8606Data.roth_distributions` | Form 8606 Part III | f8606.pdf | ✅ |
| L22 — Roth basis | `f8606-roth-basis` | `Form8606Data.roth_basis_contributions` | Form 8606 L22 | f8606.pdf | ✅ |
| Roth 5-year period met? | `f8606-5yr` | `Form8606Data.roth_account_5yr_old` | Qualified distribution test | f8606.pdf | ✅ |
| Age 59½ or older? | `f8606-age` | `Form8606Data.over_59_5` | Qualified distribution test | f8606.pdf | ✅ |
| Inherited IRA? | `f8606-inh` | `Form8606Data.is_inherited` | Inherited basis rules | f8606.pdf | ✅ |
| Inherited IRA basis | `f8606-inh-basis` | `Form8606Data.inherited_basis` | Decedent's basis allocated | f8606.pdf | ✅ |

### 16c — Form 8889 HSA

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Employee HSA contributions | `hsa-contrib` | `Form8889Data.contributions_taxpayer` | Sch 1 Line 13 | f8889.pdf | ✅ |
| Coverage type (self / family) | `hsa-type` | `Form8889Data.coverage_type` | Contribution limit | f8889.pdf | ✅ |
| Taxpayer age at Dec 31 | `hsa-age` | `Form8889Data.taxpayer_age` | Catch-up $1k if 55+ | f8889.pdf | ✅ |
| Non-medical distributions | `hsa-nonmed` | `Form8889Data.total_distributions` | Taxable + 20% penalty | f8889.pdf | ✅ |
| Employer HSA (W-2 Box 12 Code W) | *(auto from W-2 Box 12)* | `Form8889Data.employer_contrib_w2_code_w` | Reduces limit | iw2w3.pdf | ✅ |

### 16d — Form 5329 Exception Codes

*One row per exception. Repeating id pattern: `f5329-xxx-${id}`*

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Exception code | `f5329-code-${id}` | `Form5329Exception.exception_code` | Reduces 10% penalty | f5329.pdf | ✅ |
| Amount qualifying for exception | `f5329-amt-${id}` | `Form5329Exception.distribution_amount` | Form 5329 Part I | f5329.pdf | ✅ |
| IRA or employer plan? | `f5329-acct-${id}` | `Form5329Exception.plan_type` | Exception applicability | f5329.pdf | ✅ |
| Excess IRA contribution penalty | `f5329-excess` | *(6% excise)* | Form 5329 Part III | f5329.pdf | ✅ |

---

## 17 — Form 6251 AMT · Form 4972 Lump-Sum

### 17a — Form 6251 AMT

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Line 2j — ISO bargain element | `amt-iso` | `Form6251Data.iso_bargain_element` | Form 6251 L2j | f6251.pdf | ✅ |
| Line 2i — NOL addback | `amt-nol` | `Form6251Data.net_operating_loss_ded` | Form 6251 L2i | f6251.pdf | ✅ |
| Excess depletion | `amt-dep` | `Form6251Data.depletion_excess` | Form 6251 L2h | f6251.pdf | ✅ |
| Other AMT adjustments | `amt-other` | `Form6251Data.other_adjustments` | Form 6251 L2o | f6251.pdf | ✅ |

### 17b — Form 4972 Lump-Sum Distribution

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Born before Jan 2, 1936? | `f4972-elig` | `Form4972Data` (eligibility gate) | Form 4972 eligibility | f4972.pdf | ✅ |
| 1099-R Code A? | `f4972-code` | `Form4972Data` (eligibility gate) | Code A required | f4972.pdf | ✅ |
| Ordinary income portion | `f4972-ordinary` | `Form4972Data.ordinary_income` | Form 4972 L6 | f4972.pdf | ✅ |
| Capital gain portion | `f4972-capgain` | `Form4972Data.capital_gain` | Form 4972 L3 | f4972.pdf | ✅ |
| Elect 20% capital gain tax? | `f4972-20pct` | `Form4972Data.elect_20pct_capital_gain` | Form 4972 Part II | f4972.pdf | ✅ |
| Elect 10-year averaging? | `f4972-10yr` | `Form4972Data.elect_10yr_option` | Form 4972 Part III | f4972.pdf | ✅ |
| Employer / plan name | `f4972-plan` | `Form4972Data.employer_plan_name` | Form 4972 header | f4972.pdf | ✅ |

---

## 18 — California Form 540

| Field label | UI id pattern | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| CA SDI withheld | `ca-sdi` | `CaliforniaData.ca_sdi_withheld` | CA credit against tax | 2025-540.pdf (ftb) | ✅ |
| Renter's credit | `ca-renter` | `CaliforniaData.paid_rent_over_half_year` | $60/$120 CA credit | 2025-540.pdf (ftb) | ✅ |
| Other CA subtractions | `ca-sub` | `CaliforniaData.ca_other_subtractions` | CA AGI | 2025-540.pdf (ftb) | ✅ |
| CA itemized total override | `ca-itemized` | `CaliforniaData.ca_itemized_total` | CA Sch A (no SALT cap) | 2025-540-ca.pdf (ftb) | ✅ |

---

## 19 — Known Gaps Summary

Fields in the engine that are NOT yet in the UI. Add to manifest and UI when implemented.

| Form | Engine field | Why not in UI | Priority |
|---|---|---|---|
| 1099-INT Box 9 | `box9_private_activity_bond` | AMT item from INT (rare) | 🟡 Medium |
| 1099-INT Box 10 | `box10_market_discount` | Accrual election needed | 🟡 Medium |
| 1099-INT Box 11 | `box11_bond_premium` | Reduces Box 1 on Sch B | 🟡 Medium |
| 1099-INT Box 15 | `box15_state_wh` | State return only | 🟢 Low |
| 1099-DIV Box 2c | `box2c_sec1202` | §1202 very rare | 🟢 Low |
| 1099-DIV Box 6 | `box6_invest_expense` | Non-RIC only (rare) | 🟢 Low |
| Sch C L14 employee benefits | `employee_benefit_programs` | Uncommon | 🟢 Low |
| Sch C L16a mortgage interest | `mortgage_interest` | Usually in L20b other rent | 🟢 Low |
| Sch C L16b other interest | `other_interest` | Uncommon | 🟢 Low |
| Sch E L5 advertising | `ScheduleE.advertising` | Less common rental expense | 🟢 Low |
| Sch E L6 auto & travel | `ScheduleE.auto_travel` | Less common | 🟢 Low |
| Sch E L7 cleaning | `ScheduleE.cleaning_maintenance` | Less common | 🟢 Low |
| Sch E L8 commissions | `ScheduleE.commissions` | Less common | 🟢 Low |
| Sch E L10 legal/prof | `ScheduleE.legal_professional` | Less common | 🟢 Low |
| Sch E L13 other interest | `ScheduleE.other_interest` | Less common | 🟢 Low |
| Sch E L15 supplies | `ScheduleE.supplies` | Less common | 🟢 Low |
| K-1 Box 3 other rental | `box3_other_net_rental` | Uncommon | 🟢 Low |
| K-1 Box 12 §179 | `box12_sec179` | At-risk basis not computed | 🟡 Medium |
| K-1 Box 17 UBIA | `box17_ubia` | Form 8995-A threshold | 🟡 Medium |
| Form 4797 dates | `date_acquired / date_sold` | Holding period verification | 🟡 Medium |
| Form 4797 suspended losses | `suspended_passive_losses` | §469(g) release at sale | 🔴 High |
| Form 1116 (FTC) | `Form1116Data` | Full panel not built | 🔴 High |
| Form 8615 parent income | `Form8615Data.parent_taxable_income` | Requires parent return | 🔴 High |
| HSA spouse contributions | `contributions_spouse` | Separate spouse HSA | 🟡 Medium |
| HSA Archer MSA | `archer_msa_contrib` | Very rare | 🟢 Low |
| CA Form 540 other additions | `ca_other_additions` | HSA addback auto-applied | 🟢 Low |

---

## 20 — Manifest Maintenance Rules

**Import/Export Roundtrip Rule**: Whenever a field is added to `buildSchema()` (export), an identical entry must be added to `populateFromSchema()` (import) using the same JSON key name. If the UI field id and JSON key name differ from the engine field name, document the bridge in Page 2A of TaxReturn_PlanningReference.md and add the bridge to `sachintaxcare_server.py`'s `deserialize_schema()`. Run `python3 sachintaxcare_test.py` to verify roundtrip.


1. **Every engine session**: If a field is added to any `@dataclass` in `sachintaxcare_engine.py`, add a row to the relevant section of this manifest with Status = ❌ before writing any UI code.
2. **Every UI session**: When a ❌ field is added to the intake, change its Status to ✅.
3. **Test script**: Run `test_ui_fields.js` against `sachintaxcare_intake.html` after every UI change. All ✅ rows must pass. ❌ rows are expected failures — do not add them to the passing set.
4. **IRS source column**: Always cite the exact PDF filename from `irs.gov/pub/irs-pdf/`. Never cite secondary sources (TurboTax, Kiplinger, etc.).
5. **New forms**: Add a new section (e.g., `## 19 — Form 8824 Like-Kind Exchange`) before adding fields to it.

---

## 21 — OBBBA TY 2025 New Fields (P.L. 119-21, signed July 4, 2025)

*Source: Rev. Proc. 2025-32; irs.gov/newsroom/one-big-beautiful-bill-provisions*
*All fields added to `TaxpayerSchema` in engine and wired in `sachintaxcare_pro.html`*

### 21a — Standard Deduction Updates (OBBBA §70102)
No new intake fields — constants updated in `PARAMS_2025`. Verified by Section 32 tests.

| Filing Status | Old Amount (Rev. Proc. 2024-40) | New Amount (OBBBA) | Engine key |
|---|---|---|---|
| Single / MFS | $15,000 | **$15,750** | `std_deduction.single` |
| MFJ / QSS | $30,000 | **$31,500** | `std_deduction.mfj` |
| HOH | $22,500 | **$23,625** | `std_deduction.hoh` |

### 21b — Child Tax Credit Update (OBBBA §70104)
No new intake fields — constant updated in `PARAMS_2025`.

| Item | Old | New | Engine key |
|---|---|---|---|
| CTC per child | $2,000 | **$2,200** | `ctc_per_child` |
| ACTC refundable cap | $1,700 | $1,700 (unchanged 2025) | `actc_cap_per_child` |

### 21c — SALT Cap Update (OBBBA §70106)
No new intake fields — `ScheduleAData` unchanged; SALT cap logic updated in `compute_schedule_a()`.

| Item | Old | New |
|---|---|---|
| SALT cap (default) | $10,000 | **$40,000** |
| SALT cap (MFS) | $5,000 | **$20,000** |
| Phase-down threshold | n/a | AGI > $500,000 |
| Phase-down rate | n/a | $50 per $1,000 AGI above threshold |
| Floor | $10,000 | $10,000 |

### 21d — Senior Bonus Deduction (OBBBA §70103 — TY 2025–2028)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Taxpayer age at Dec 31, 2025 | `tp-age-senior` | `TaxpayerSchema.taxpayer_age_for_senior_ded` | OBBBA Senior Deduction | one-big-beautiful-bill-provisions | ✅ |
| Spouse age at Dec 31, 2025 (MFJ) | `sp-age-senior` | `TaxpayerSchema.spouse_age_for_senior_ded` | OBBBA Senior Deduction (spouse) | one-big-beautiful-bill-provisions | ✅ |

*Auto-populated: entering DOB in taxpayer/spouse panels calls `autoSeniorAge()` which computes age from MM-DD-YYYY and fills the age field. Manual override allowed.*

Engine function: `compute_senior_deduction()`. Amount: $6,000/qualifying person. Phase-out: MAGI > $75k single / $150k MFJ. MFS ineligible.

### 21e — Tip Income Deduction (OBBBA §70201 — TY 2025–2028)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Qualified tip income ($) | `qualified-tips` | `TaxpayerSchema.qualified_tips` | Sch 1 above-line | one-big-beautiful-bill-provisions | ✅ |

Engine function: `compute_tip_deduction()`. Cap $25,000. Phase-out: MAGI > $150k single / $300k MFJ.

### 21f — Overtime Pay Deduction (OBBBA §70202 — TY 2025–2028)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| FLSA qualifying overtime pay ($) | `overtime-pay` | `TaxpayerSchema.overtime_pay_qualifying` | Sch 1 above-line | one-big-beautiful-bill-provisions | ✅ |

Engine function: `compute_overtime_deduction()`. Cap $12,500 single / $25,000 MFJ. MFS ineligible. Phase-out: MAGI > $150k single / $300k MFJ.

### 21g — Auto Loan Interest Deduction (OBBBA §70301 — TY 2025–2028)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Auto loan interest ($) | `auto-loan-interest` | `TaxpayerSchema.auto_loan_interest` | Sch 1 above-line | one-big-beautiful-bill-provisions | ✅ |
| Loan originated after 12/31/2024? | `auto-loan-post2024` | `TaxpayerSchema.auto_loan_originated_after_2024` | Eligibility gate | one-big-beautiful-bill-provisions | ✅ |
| Vehicle new and US-assembled? | `auto-loan-us-vehicle` | `TaxpayerSchema.auto_loan_vehicle_new_us_assembled` | Eligibility gate | one-big-beautiful-bill-provisions | ✅ |

Engine function: `compute_auto_loan_deduction()`. Cap $10,000/yr. Phase-out: MAGI > $100k single / $200k MFJ.

### 21h — Charitable Floor Update (OBBBA — itemizers)
No new intake fields — `ScheduleAData.cash_charitable` unchanged; floor logic added in `compute_schedule_a()`.
0.5% AGI floor applies before 60% cap for itemizers. `PARAMS_2025["charitable_agi_floor_pct"] = 0.005`.

---

## 22 — v12 New Fields (P0–P6 Session, 2026-05-11)

### 22a — SE Retirement Plan Type (P1)
| Field label | UI id | Engine field | Notes | Status |
|---|---|---|---|---|
| Retirement plan type | `se-ret-type` | `TaxpayerSchema.se_retirement_plan_type` | "sep" / "solo401k" / "simple" | f1040sc.pdf | ✅ |

### 22b — Capital Loss Carryover (P1)
| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Capital loss carryover from prior year ($) | `cap-carryover` | `TaxpayerSchema.capital_loss_carryover_prior` | Schedule D Lines 6/14 | f1040sd.pdf; IRC §1212(b) | ✅ |

### 22c — ScheduleC 8995-A Fields (P3)
| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| W-2 wages paid by business ($) | `sc-w2wages-${id}` | `ScheduleC.w2_wages` | Form 8995-A Part II Line 12 | f8995a.pdf | ✅ |
| UBIA of qualified property ($) | `sc-ubia-${id}` | `ScheduleC.ubia_qualified_property` | Form 8995-A Part II Line 13 | f8995a.pdf; IRC §199A(b)(6) | ✅ |
| Is SSTB (law/health/consult/etc.)? | `sc-sstb-${id}` | `ScheduleC.is_sstb` | Form 8995-A Part III | f8995a.pdf; IRC §199A(d) | ✅ |

### 22d — CalEITC / YCTC / FYTC (P2)
| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Qualifying child under age 6? | `ca-young-child` | `CaliforniaData.has_young_child_under6` | FTB 3514 Part VI YCTC | ftb.ca.gov/forms/2025/2025-3514.pdf | ✅ |
| Taxpayer in CA foster care (age 18-25)? | `ca-foster-tp` | `CaliforniaData.foster_youth_taxpayer` | FTB 3514 Part IX FYTC | ftb.ca.gov/forms/2025/2025-3514.pdf | ✅ |
| Spouse in CA foster care (age 18-25)? | `ca-foster-sp` | `CaliforniaData.foster_youth_spouse` | FTB 3514 Part IX FYTC | ftb.ca.gov/forms/2025/2025-3514.pdf | ✅ |
| CA taxpayer age | `ca-tp-age` | `CaliforniaData.ca_taxpayer_age` | CalEITC age gate (18+) | FTB 3514 Step 1 | ✅ |
| CA investment income (CalEITC) ($) | `ca-invest-caleitc` | `CaliforniaData.ca_investment_income_caleitc` | FTB 3514 Worksheet 1 (≤ $4,814) | ftb.ca.gov/forms/2025/2025-3514-booklet.html | ✅ |

### 22e — TY 2026 Support (P5)
Engine auto-selects PARAMS_2026 when `tax_year=2026`. No new UI fields required — tax_year field already in UI.

---

---

## 23 — Fields Added Since v12 (Engine V13–V17.1)

*Added to engine after the last manifest update. All verified against V17.1 dataclasses.*

### 23a — TaxpayerSchema additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Tip occupation (IRS Notice 2025-65) | `tip-occupation` | `TaxpayerSchema.tip_occupation` | OBBBA tip deduction gate | Notice 2025-65 | ✅ |
| FLSA overtime confirmed | `overtime-flsa` | `TaxpayerSchema.overtime_flsa_confirmed` | OBBBA OT deduction gate | P.L. 119-21 §70202 | ✅ |
| Care spouse is student | `care-sp-student` | `TaxpayerSchema.care_spouse_is_student` | Form 2441 Line 6 deemed income | f2441.pdf | ✅ |
| Care spouse is disabled | `care-sp-disabled` | `TaxpayerSchema.care_spouse_is_disabled` | Form 2441 Line 6 deemed income | f2441.pdf | ✅ |
| Care spouse months qualified | `care-sp-months` | `TaxpayerSchema.care_spouse_months_qualified` | Form 2441 Line 6 deemed income | f2441.pdf | ✅ |
| CA foster youth taxpayer | `ca-foster-tp` | `TaxpayerSchema.ca_foster_youth_taxpayer` | CA FYTC (FTB 3514 Part IX) | ftb.ca.gov/forms/2025/2025-3514.pdf | ✅ |
| CA foster youth spouse | `ca-foster-sp` | `TaxpayerSchema.ca_foster_youth_spouse` | CA FYTC (FTB 3514 Part IX) | ftb.ca.gov/forms/2025/2025-3514.pdf | ✅ |
| QBI loss carryforward | `qbi-loss-cf` | `TaxpayerSchema.qbi_loss_carryforward` | Form 8995 Line 2 | f8995.pdf | ⚠ captured not computed |
| ACA household size override | `aca-household` | `TaxpayerSchema.aca_household_size` | Form 8962 Line 1 | f8962.pdf | ⚠ captured not computed |
| Prior §1231 losses 5yr | `f4797-1231-prior` | `TaxpayerSchema.prior_sec1231_losses_5yr` | Form 4797 §1231 lookback | f4797.pdf; IRC §1231(c) | ⚠ captured not computed |

### 23b — CaliforniaData additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Use CA itemized deductions | `ca-use-itemized` | `CaliforniaData.use_ca_itemized` | CA Form 540 deduction | FTB 540 | ✅ |
| CA itemized total | `ca-itemized-total` | `CaliforniaData.ca_itemized_total` | CA Form 540 Line 18 | FTB 540 | ✅ |
| CA OBBBA addback override | `ca-obbba-override` | `CaliforniaData.ca_obbba_addback_override` | CA non-conformity override | FTB Announcement 2025-4 | ⚠ mapped via ca_other_additions |
| CA bonus depreciation addback | `ca-bonus-dep` | `CaliforniaData.ca_bonus_depreciation_addback` | CA Schedule CA addback | FTB 3885 | ✅ |
| CA military pay exclusion | `ca-military-pay` | `CaliforniaData.ca_military_pay_exclusion` | CA Mil & Vet Code §402 | FTB 3504 | ✅ |
| CA loan forgiveness excluded | `ca-loan-forgive` | `CaliforniaData.ca_loan_forgiveness_excluded` | CA AB 1577 exclusion | FTB guidance | ✅ |
| CA lottery winnings | `ca-lottery` | `CaliforniaData.ca_lottery_winnings` | CA Form 540 Schedule CA | R&TC §17154 | ✅ |

### 23c — AlimonyData addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Decree modified after 12/31/2018 | `al-modified` | `AlimonyData.decree_modified_after_2018` | Post-2018 = no deduction/income | IRC §11051(c); Pub 504 | ✅ |

### 23d — Form1099R additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| IRA/SEP/SIMPLE flag | `r-is-ira-${id}` | `Form1099R.is_ira` | Routes to Lines 4b vs 5b | f1099r.pdf | ❌ UI uses box7_ira_sep_simple instead — ⚠ bridge maps both |
| Payer TIN | `r-payer-tin-${id}` | `Form1099R.payer_tin` | Identification | f1099r.pdf | ⚠ captured not displayed |
| Recipient TIN | `r-recip-tin-${id}` | `Form1099R.recipient_tin` | Identification | f1099r.pdf | ⚠ captured not displayed |

### 23e — Form1098T additions (all gates)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| At least half-time student | `1098t-half-time-${id}` | `Form1098T.box8_half_time` | AOC hard gate (1 of 3) | f8863.pdf; IRC §25A(b)(3) | ✅ |
| No drug conviction | `1098t-drug-${id}` | `Form1098T.aoc_drug_conviction` | AOC hard gate (2 of 3) | f8863.pdf; IRC §25A(b)(2) | ✅ |
| First four years | `1098t-4yr-${id}` | `Form1098T.first_four_years` | AOC eligibility (3 of 3) | f8863.pdf; IRC §25A(b)(2) | ✅ |
| Graduate student | `1098t-grad-${id}` | `Form1098T.box9_graduate` | LLC eligibility (not AOC) | f8863.pdf | ✅ |
| Future period box 7 | `1098t-fut-${id}` | `Form1098T.box7_future_period` | Timing adjustment | f1098t.pdf | ⚠ captured not computed |
| Student relationship | `1098t-who-${id}` | `Form1098T.student_who` | Taxpayer/spouse/dep routing | f8863.pdf | ✅ |

### 23f — ScheduleC additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Business code (NAICS) | `sc-code-${id}` | `ScheduleC.business_code` | Schedule C header | f1040sc.pdf | ✅ |
| Business miles | `sc-miles-${id}` | `ScheduleC.business_miles` | Car/truck expenses | f1040sc.pdf; Pub 463 | ✅ |
| NEC income in gross receipts? | `sc-nec-${id}` | `ScheduleC.nec_included_in_gross` | Prevents double-count | f1040sc.pdf | ✅ |
| For spouse? | `sc-spouse-${id}` | `ScheduleC.for_spouse` | MFJ SE allocation | f1040sc.pdf | ✅ |
| W-2 wages paid (Form 8995-A) | `sc-w2wages-${id}` | `ScheduleC.w2_wages` | Form 8995-A Part II L12 | f8995a.pdf | ✅ |
| UBIA qualified property | `sc-ubia-${id}` | `ScheduleC.ubia_qualified_property` | Form 8995-A Part II L13 | f8995a.pdf; IRC §199A(b)(6) | ✅ |
| Is SSTB? | `sc-sstb-${id}` | `ScheduleC.is_sstb` | Form 8995-A Part III | f8995a.pdf; IRC §199A(d) | ✅ |
| Accounting method | `sc-acctg-${id}` | `ScheduleC.accounting_method` | Schedule C header | f1040sc.pdf | ⚠ captured not computed |

### 23g — Form 8606 addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Backdoor Roth conversion | `f8606-backdoor` | `Form8606Data.is_backdoor_roth` | Form 8606 Part II warning | f8606.pdf; Notice 2014-54 | ✅ |

### 23h — Form 4797 addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Additional §1250 recapture | `f4797-1250r-${id}` | `Form4797SaleData.additional_section_1250_recapture` | Form 4797 Line 26g | f4797.pdf; IRC §1250 | ✅ |

### 23i — Form 982 (new form since v12)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Bankruptcy Title 11 | `cod-982-type-${id}` | `Form982Data.bankruptcy_title11` | Form 982 Line 1a | f982.pdf; IRC §108(a)(1)(A) | ✅ (via 1099-C exclusion type) |
| Total liabilities before | `cod-liab-${id}` | `Form982Data.total_liabilities_before` | Insolvency test | f982.pdf | ✅ (via 1099-C section) |
| Total assets FMV before | `cod-assets-${id}` | `Form982Data.total_assets_fmv_before` | Insolvency test | f982.pdf | ✅ (via 1099-C section) |
| Discharged amount override | `f982-override` | `Form982Data.discharged_amount_override` | Form 982 Line 2 | f982.pdf | ⚠ bridge-only — no UI field yet |

### 23j — W-2 additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Box 13 — Statutory employee | `w2-box13-${id}` (select val=statutory) | `W2.box13_statutory_employee` | Schedule C routing | iw2w3.pdf | ✅ (shared select with retirement/sick) |
| Box 13 — Third-party sick pay | `w2-box13-${id}` (select val=sick) | `W2.box13_third_party_sick` | Line 1d | iw2w3.pdf | ✅ (shared select with retirement/statutory) |
| State employer ID (Box 15b) | `w2-state-${id}` | `W2.box15_state_employer_id` | State return | iw2w3.pdf | ✅ (shared with box15_state) |
| Employee SSN | `w2-empssn-${id}` | `W2.employee_ssn` | Identification | iw2w3.pdf | ⚠ captured not displayed |

### 23k — Form 1116 (all fields — form added since v12)

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Passive foreign taxes paid | `f1116-pass-tax` | `Form1116Data.passive_foreign_taxes_paid` | Form 1116 Part II | f1116.pdf | ✅ |
| Passive foreign income | `f1116-pass-inc` | `Form1116Data.passive_foreign_income` | Form 1116 Part I | f1116.pdf | ✅ |
| Passive foreign expenses | `f1116-pass-exp` | `Form1116Data.passive_foreign_expenses` | Form 1116 Part I | f1116.pdf | ✅ |
| General basket foreign taxes | `f1116-gen-tax` | `Form1116Data.general_foreign_taxes_paid` | Form 1116 Part II | f1116.pdf | ✅ |
| General basket income | `f1116-gen-inc` | `Form1116Data.general_foreign_income` | Form 1116 Part I | f1116.pdf | ✅ |
| General basket expenses | `f1116-gen-exp` | `Form1116Data.general_foreign_expenses` | Form 1116 Part I | f1116.pdf | ✅ |
| Passive carryover | `f1116-pass-cf` | `Form1116Data.passive_carryover` | Form 1116 Line 10 | f1116.pdf | ⚠ captured not computed |
| General carryover | `f1116-gen-cf` | `Form1116Data.general_carryover` | Form 1116 Line 10 | f1116.pdf | ⚠ captured not computed |
| Cash basis | `f1116-cash` | `Form1116Data.cash_basis` | Form 1116 election | f1116.pdf | ⚠ captured not computed |
| AMT applies | `f1116-amt` | `Form1116Data.amt_applies` | AMT FTC | f1116.pdf | ⚠ captured not computed |

### 23l — ScheduleE addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Enforce §280A vacation home rules | `sche-280a-${id}` | `ScheduleE.enforce_280a` | Personal use day proration | IRC §280A; f1040se.pdf | ✅ |

### 23m — Form 5329 addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Account type | `5329-acct-${id}` | `Form5329Exception.account_type` | IRA vs plan routing | f5329.pdf | ✅ |

### 23n — SSA-1099 additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Lump sum election | `ssa-lump-elect` | `FormSSA1099.lump_sum_election` | Pub 915 Worksheet 2 | p915.pdf | ✅ |
| Lump sum years | `ssa-lump-yrs` | `FormSSA1099.lump_sum_years` | Pub 915 Worksheet 2 | p915.pdf | ✅ |
| Medicare Part B premiums | `ssa-mcare-b` | `FormSSA1099.medicare_part_b_premiums` | Schedule A medical | p915.pdf | ⚠ captured not computed |
| Medicare Part C premiums | `ssa-mcare-c` | `FormSSA1099.medicare_part_c_premiums` | Schedule A medical | p915.pdf | ⚠ captured not computed |
| Medicare Part D premiums | `ssa-mcare-d` | `FormSSA1099.medicare_part_d_premiums` | Schedule A medical | p915.pdf | ⚠ captured not computed |

### 23o — ScheduleA additions

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Mortgage balance outstanding | `sa-mort-bal` | `ScheduleAData.mortgage_balance_outstanding` | $750k limit calc | f1040sa.pdf; IRC §163(h)(3); Pub 936 | ✅ |
| Mortgage is pre-12/16/2017 (grandfathered) | `sa-mort-grand` | `ScheduleAData.mortgage_is_grandfathered` | $1M limit if grandfathered | f1040sa.pdf; IRC §163(h)(3)(F) | ✅ |
| Other state/local taxes | `sa-other-tax` | `ScheduleAData.other_state_local_tax` | SALT pool (within $40k cap) | f1040sa.pdf | ✅ |

### 23p — Dependent addition

| Field label | UI id | Engine field | Routes to | IRS source | Status |
|---|---|---|---|---|---|
| Lived with taxpayer all year | `dep-lived-${id}` | `Dependent.lived_all_year` | HOH / QSS eligibility | f1040.pdf; IRC §2(b) | ⚠ captured not fully computed |

### 23q — Manifest totals (V17.1)

| Category | Count |
|---|---|
| Total engine fields | **555** |
| Documented in manifest (v1.4) | **~450** |
| Status ✅ (in UI and computed) | ~370 |
| Status ⚠ (captured, not computed or displayed) | ~25 |
| Status ❌ (missing from UI — pending) | ~55 |
| Stale manifest entries fixed this session | **10** |
| New entries added this session (§23a–23p) | **58** |

---

*End of manifest · v1.4 · V17.1 · 2026-05-24*
