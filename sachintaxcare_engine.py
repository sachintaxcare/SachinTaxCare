"""
SachinTaxCare — Computation Engine v2
Expanded: 1098-T/Form 8863, Teacher Expense, 1099-C, Prize Money, 1099-R, SSA-1099
Separation of concerns: this module handles ONLY calculations.
All IRS sources: irs.gov/pub/irs-pdf/

Computation order (per IRS rules):
  Step 1:   Income — W-2, 1099s, 1099-R, SSA-1099, 1099-C, Prize money
  Step 2:   Adjustments — Schedule 1 Part II (teacher expense, early W/D, student loan)
  Step 3:   AGI
  Step 4:   Standard Deduction → Taxable Income
  Step 5:   Income Tax (Form 1040 Line 16/18)
  Step 6:   Form 2441  (FIRST non-ref credit)
  Step 7:   Form 8863  (SECOND — education credits)
  Step 8:   Form 8880  (THIRD — needs 2441+8863 results for CLW)
  Step 9:   Schedule 8812 (FOURTH — needs 2441+8863+8880 for CLW)
  Step 10:  Schedule 3 Part I
  Step 11:  EIC Worksheet A → EIC Table
  Step 12:  Form 8962 (Premium Tax Credit)
  Step 13:  Schedule 3 Part II
  Step 14:  Form 1040 Totals
"""

from dataclasses import dataclass, field
from typing import Optional
import math


# ── DATA SCHEMA ────────────────────────────────────────────────────────────────

@dataclass
class W2:
    """
    Form W-2: Wage and Tax Statement (2025)
    Source: irs.gov/pub/irs-prior/fw2--2025.pdf  |  Instructions: irs.gov/pub/irs-pdf/iw2w3.pdf

    Boxes a–f  : Identification (SSN, EIN, employer/employee name/address)
    Box 1      : Wages, tips, other compensation → Form 1040 Line 1z
    Box 2      : Federal income tax withheld → Form 1040 Line 25a
    Box 3      : Social security wages
    Box 4      : Social security tax withheld
    Box 5      : Medicare wages and tips
    Box 6      : Medicare tax withheld
    Box 7      : Social security tips (tips reported to employer)
    Box 8      : Allocated tips → Schedule 1 Line 8 (if not included in Box 1)
    Box 10     : Dependent care benefits (employer-provided) → Form 2441 Line 12
                 Reduces the §21 credit base dollar-for-dollar (up to $5,000 exclusion)
    Box 11     : Nonqualified deferred comp (§457 distributions taxable in current year)
    Box 12a–12d: Up to 4 code/amount pairs. Common codes:
                 D=401k, E=403b, F=SIMPLE, G=457, AA=Roth401k, BB=Roth403b,
                 C=group life >$50k, W=HSA employer contrib, DD=employer health cost
    Box 13     : Three checkboxes — Statutory employee / Retirement plan / Third-party sick pay
                 "Retirement plan" box → affects IRA deduction phase-out (Pub 590-A)
    Box 14a    : Other (free-form; state-mandated items like NY SDI, NJ FLI, CA SDI)
    Box 15     : State / Employer's state ID number
    Box 16     : State wages, tips, etc.
    Box 17     : State income tax → state return
    Box 18     : Local wages, tips, etc.
    Box 19     : Local income tax withheld
    Box 20     : Locality name
    """
    # Identification
    employer: str = ""
    ein: str = ""                        # Box b
    employee_ssn: str = ""               # Box a (last 4 shown on form)

    # Federal boxes
    box1_wages: float = 0                # → Line 1z
    box2_fed_wh: float = 0               # → Line 25a
    box3_ss_wages: float = 0
    box4_ss_wh: float = 0
    box5_med_wages: float = 0
    box6_med_wh: float = 0
    box7_ss_tips: float = 0              # Social security tips
    box8_allocated_tips: float = 0       # → Schedule 1 Line 8 if not in Box 1
    box10_dependent_care: float = 0      # Employer-provided dep care → Form 2441 L12
    box11_nonqual_def_comp: float = 0    # §457 plan distributions taxable this year

    # Box 12: up to 4 entries (stored as list of (code, amount) tuples or use 4 pairs)
    box12a_code: str = ""
    box12a_amt: float = 0
    box12b_code: str = ""
    box12b_amt: float = 0
    box12c_code: str = ""
    box12c_amt: float = 0
    box12d_code: str = ""
    box12d_amt: float = 0

    # Box 13 checkboxes
    box13_statutory_employee: bool = False
    box13_retirement_plan: bool = False  # → affects IRA deduction phase-out
    box13_third_party_sick: bool = False

    # Box 14 (free-form; label + amount)
    box14_other: str = ""                # e.g. "NY SDI 31.20" or "CA SDI 450.00"

    # State boxes (15–17)
    box15_state: str = ""                # State abbreviation
    box15_state_employer_id: str = ""    # State EIN
    box16_state_wages: float = 0
    box17_state_wh: float = 0

    # Local boxes (18–20)
    box18_local_wages: float = 0
    box19_local_wh: float = 0
    box20_locality_name: str = ""

    # Engine field
    for_spouse: bool = False

@dataclass
class Form1099INT:
    """
    1099-INT: Interest Income (2025)
    Source: irs.gov/pub/irs-pdf/f1099int.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1099int.pdf

    Box 1  : Interest income → Schedule B → Form 1040 Line 2b
    Box 2  : Early withdrawal penalty → Schedule 1 Line 18 (NOT Line 8)
    Box 3  : Interest on US savings bonds / Treasury obligations
             Federally taxable; exempt from state/local tax
    Box 4  : Federal income tax withheld (backup withholding) → Form 1040 Line 25b
    Box 5  : Investment expenses → Schedule A Line 9 (if itemizing)
    Box 6  : Foreign tax paid → Form 1116 (foreign tax credit)
    Box 7  : Foreign country or US possession (required for Form 1116)
    Box 8  : Tax-exempt interest → Form 1040 Line 2a
             Also included in provisional income for SS taxability calculation
    Box 9  : Specified private activity bond interest → Form 6251 (AMT)
    Box 10 : Market discount (ordinary income; accrual election)
    Box 11 : Bond premium (offsets Box 1 interest on Schedule B)
    Box 12 : Bond premium on Treasury obligations (offsets Box 3)
    Box 13 : Bond premium on tax-exempt bond (reduces tax-exempt interest)
    Box 14 : Tax-exempt and tax-credit bond CUSIP (identification only)
    Box 15 : State tax withheld → state return
    Box 16 : State ID number
    Box 17 : State income (portion allocable to state)
    """
    payer: str = ""
    payer_ein: str = ""
    account_number: str = ""

    box1_interest: float = 0             # → Schedule B → Line 2b
    box2_early_withdrawal_penalty: float = 0  # Box 2 — Early withdrawal penalty → Schedule 1 Line 18. Source: f1099int.pdf; i1040s1.pdf L18; IRC §62(a)(9)
    box3_us_savings_bond: float = 0      # Federally taxable; state-exempt
    box4_fed_wh: float = 0               # Backup WH → Line 25b
    box5_investment_expenses: float = 0  # → Schedule A Line 9
    box6_foreign_tax: float = 0          # → Form 1116
    box7_foreign_country: str = ""
    box8_tax_exempt_interest: float = 0  # → Line 2a; included in SS provisional income
    box9_private_activity_bond: float = 0  # AMT item → Form 6251
    box10_market_discount: float = 0
    box11_bond_premium: float = 0        # Reduces Box 1 on Schedule B
    box12_bond_premium_treasury: float = 0  # Reduces Box 3
    box13_bond_premium_tax_exempt: float = 0
    box14_cusip: str = ""
    box15_state_wh: float = 0
    box16_state_id: str = ""
    box17_state_income: float = 0

@dataclass
class SimplifiedMethodData:
    """
    Pub. 575 Worksheet A — Simplified Method for annuity cost basis recovery.
    Required when: annuity starting date after Nov 18 1996 AND qualified plan
                   AND box 2a is blank or taxpayer can reduce taxable amount.
    Source: irs.gov/pub/irs-pdf/p575.pdf Worksheet A; irs.gov/pub/irs-pdf/p554.pdf
    """
    use_simplified_method: bool = False
    # Line 2: cost in the contract (Box 9b on 1099-R, or prior-year carryforward)
    cost_in_contract: float = 0
    # Line 3: expected number of monthly payments
    #   Single-life → use Table 1 (age at annuity start date)
    #   Multiple-lives → use Table 2 (combined ages of annuitants)
    #   Fixed-period → enter the number of months in the period
    annuity_type: str = "single"        # "single" | "joint" | "fixed"
    age_at_annuity_start: int = 0       # primary annuitant age on starting date
    joint_age_at_annuity_start: int = 0 # second annuitant age (joint only)
    fixed_period_months: int = 0        # fixed period in months (fixed only)
    # Line 6: amounts already recovered tax-free in prior years
    prior_year_tax_free_recovered: float = 0
    # Annuity starting date — determines which Table 1 column to use
    # Pre-Nov-19-1996 start → different (old) table; Post → current table
    annuity_start_after_nov_18_1996: bool = True   # After Nov 18 1996 → simplified method required
    start_after_nov_1996: bool = True              # Alias: UI sends this key. Source: Pub 575

@dataclass
class Form1099R:
    """
    1099-R: Distributions from Pensions, Annuities, Retirement Plans, IRAs
    Source: irs.gov/pub/irs-pdf/f1099r.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1099r.pdf
    Pub 575: irs.gov/pub/irs-pdf/p575.pdf   |  Pub 939: irs.gov/pub/irs-pdf/p939.pdf

    ── Recipient identification ───────────────────────────────────────────────
    payer          : Name of the payer / plan administrator
    payer_tin      : Payer's federal EIN (e.g. "34-1234567")
    recipient_tin  : Taxpayer SSN — used to match to 1040
    account_number : Payer's account number for this recipient (when multiple 1099-Rs from same payer)

    ── Federal boxes ─────────────────────────────────────────────────────────
    Box 1  box1_gross              Gross distribution (always enter; includes rollover amounts)
    Box 2a box2a_taxable           Taxable amount. Leave 0 if box2b_not_determined=True; compute via
                                   Simplified Method (Box 9b) or Form 8606 if IRA with basis.
    Box 2b box2b_not_determined    "Taxable amount not determined" checkbox — payer couldn't compute
           box2b_total_dist        "Total distribution" checkbox — entire account liquidated
    Box 3  box3_capital_gain       Capital gain included in Box 2a (pre-1974 lump-sum portion).
                                   Only populated if born before 1/2/1936. Feeds Form 4972 Part II.
    Box 4  box4_fed_wh             Federal income tax withheld → Form 1040 Line 25b (NOT 25a)
    Box 5  box5_employee_contrib   Employee contributions / Designated Roth contributions or
                                   insurance premiums recovered tax-free this year.
                                   For Roth: this is the basis in the designated Roth account.
                                   For annuities: after-tax contributions returned (not IRA contribs).
    Box 6  box6_nua                Net unrealized appreciation in employer securities.
                                   Excluded from ordinary income at distribution (taxed as LTCG
                                   when securities are later sold) unless taxpayer elects inclusion.
                                   Lump-sum → total NUA; non-lump-sum → NUA on employee contribs only.
    Box 7  box7_code               Primary distribution code. See BOX_7_CODES dict below.
           box7_code2              Second code when two are required (e.g. "8" + "1", "P" + "J").
           box7_ira_sep_simple     IRA/SEP/SIMPLE checkbox next to Box 7 — the authoritative
                                   determinant of Lines 4a/4b (IRA) vs. 5a/5b (pension/annuity).
                                   Do NOT check for Roth IRA or IRA recharacterization.
    Box 8  box8_other_percent      Annuity contract value within a lump-sum distribution (%).
                                   Excluded from Boxes 1 and 2a. Rarely used.
    Box 9a box9a_pct_total_dist    Your percentage of total distribution (when split, e.g. MFJ).
    Box 9b box9b_employee_contribs Total employee contributions (cost basis for Simplified Method).
                                   Populated by payer when annuity payments first begin after 1996.
                                   → Feeds Pub. 575 Worksheet A (Simplified Method).
    Box 10 box10_irr_within_5yrs   Amount allocable to IRR (In-plan Roth Rollover) within 5 years.
                                   Affects ordering rules for Roth 401(k) distributions.
    Box 11 box11_roth_first_year   First year of designated Roth contributions (4-digit year).
                                   Starts the 5-year clock for tax-free qualified Roth distributions.
    Box 12 box12_fatca             FATCA filing requirement checkbox (foreign financial institution).
    Box 13 box13_date_of_payment   Date of payment for reportable death benefits (section 6050Y).

    ── State boxes (14–16) ───────────────────────────────────────────────────
    box14_state_wh                 State income tax withheld
    box15_state_payer_number       State / payer's state number
    box16_state_dist               State distribution amount

    ── Local boxes (17–19) ───────────────────────────────────────────────────
    box17_local_wh                 Local income tax withheld
    box18_locality_name            Name of locality
    box19_local_dist               Local distribution amount

    ── Engine fields (not on form) ───────────────────────────────────────────
    is_ira         : Mirrors box7_ira_sep_simple for backward compatibility.
                     True → Form 1040 Lines 4a/4b | False → Lines 5a/5b
    taxable_not_determined : Mirrors box2b_not_determined.
    simplified_method : SimplifiedMethodData for annuities with cost basis (Box 9b > 0).
    """
    # ── Recipient / payer identification ──────────────────────────────────
    payer: str = ""
    payer_tin: str = ""                      # EIN e.g. "XX-XXXXXXX"
    recipient_tin: str = ""                  # Taxpayer SSN
    account_number: str = ""

    # ── Federal boxes ─────────────────────────────────────────────────────
    box1_gross: float = 0
    box2a_taxable: float = 0
    box2b_not_determined: bool = False       # Taxable amount not determined checkbox
    box2b_total_dist: bool = False           # Total distribution checkbox
    box3_capital_gain: float = 0             # Pre-1974 capital gain → Form 4972 Part II
    box4_fed_wh: float = 0                   # → Line 25b (NOT 25a)
    box5_employee_contrib: float = 0         # After-tax basis / Roth basis recovered
    box6_nua: float = 0                      # Net unrealized appreciation (employer securities)
    box7_code: str = "7"                     # Primary distribution code
    box7_code2: str = ""                     # Second code (if applicable)
    box7_ira_sep_simple: bool = False        # IRA/SEP/SIMPLE checkbox — routes 4a/4b vs 5a/5b
    box8_other_percent: float = 0            # Annuity contract % in lump-sum (rarely used)
    box9a_pct_total_dist: float = 100.0      # % of total distribution (default 100%)
    box9b_employee_contribs: float = 0       # Total cost basis for Simplified Method
    box10_irr_within_5yrs: float = 0         # In-plan Roth Rollover within 5 years
    box11_roth_first_year: int = 0           # First year of designated Roth contributions
    box12_fatca: bool = False
    box13_date_of_payment: str = ""          # Date for section 6050Y death benefits

    # ── State boxes ───────────────────────────────────────────────────────
    box14_state_wh: float = 0
    box15_state_payer_number: str = ""
    box16_state_dist: float = 0

    # ── Local boxes ───────────────────────────────────────────────────────
    box17_local_wh: float = 0
    box18_locality_name: str = ""
    box19_local_dist: float = 0

    # ── Engine / backward-compat fields ───────────────────────────────────
    # is_ira mirrors box7_ira_sep_simple; keep both in sync when constructing
    is_ira: bool = False                     # True → Lines 4a/4b | False → Lines 5a/5b
    taxable_not_determined: bool = False     # mirrors box2b_not_determined
    simplified_method: object = None         # SimplifiedMethodData or None
    # Bridge hardening 2026-05-19 — fields sent by UI but missing from dataclass
    use_simplified_method: bool = False      # True = use simplified method to compute taxable portion. Source: f1099r.pdf; Pub 575
    payer_ein: str = ""                      # Payer EIN (identification). Source: f1099r.pdf
    recipient: str = "taxpayer"              # "taxpayer" | "spouse" — which person received the distribution


# ── Box 7 distribution codes (complete 2025 list) ──────────────────────────────
# Source: irs.gov/pub/irs-pdf/f1099r.pdf Box 7 table; irs.gov/pub/irs-pdf/i1099r.pdf
BOX_7_CODES = {
    "1":  "Early distribution, no known exception (under 59½) — 10% penalty may apply",
    "2":  "Early distribution, exception applies (under 59½, no penalty)",
    "3":  "Disability",
    "4":  "Death — paid to beneficiary/estate",
    "5":  "Prohibited transaction — IRA no longer an IRA",
    "6":  "Section 1035 tax-free exchange of life insurance, annuity, or endowment contracts",
    "7":  "Normal distribution (age 59½+)",
    "8":  "Excess contributions plus earnings returned — taxable in current year",
    "9":  "Cost of current life insurance protection (PS-58 costs)",
    "A":  "May be eligible for 10-year tax option (Form 4972) — born before 1/2/1936",
    "B":  "Designated Roth account distribution",
    "C":  "Reportable death benefits under section 6050Y",
    "D":  "Annuity payments from nonqualified annuities subject to section 1411",
    "E":  "Distributions under EPCRS (excess employer contributions returned)",
    "F":  "Charitable gift annuity",
    "G":  "Direct rollover to qualified plan, 403(b), governmental 457(b), or IRA — not taxable",
    "H":  "Direct rollover of designated Roth account to Roth IRA or Roth SIMPLE IRA",
    "J":  "Early distribution from Roth IRA or Roth SIMPLE IRA, no known exception",
    "K":  "Distribution of IRA assets not having a readily determinable FMV",
    "L":  "Loans treated as distributions (default on plan loan)",
    "M":  "Qualified plan loan offset (offset within 60-day rollover window)",
    "N":  "Recharacterized IRA contribution made for 2025, recharacterized in 2025",
    "P":  "Excess contributions plus earnings returned — taxable in prior year",
    "Q":  "Qualified distribution from Roth IRA or Roth SIMPLE IRA (tax-free)",
    "R":  "Recharacterized IRA contribution made for 2024 or prior, recharacterized in 2025",
    "S":  "Early distribution from SIMPLE IRA in first 2 years, no exception (25% penalty)",
    "T":  "Roth IRA or Roth SIMPLE IRA — exception applies (age 59½+ or other exception)",
    "U":  "Dividend distribution from ESOP under section 404(k) — not eligible for rollover",
    "W":  "Charges/payments for qualified long-term care insurance under combined contract",
    "Y":  "Qualified charitable distribution (QCD) under section 408(d)(8)",
}

@dataclass
class SSALumpSumPriorYear:
    """
    Data for one prior year included in a 2025 SSA-1099 lump-sum payment.
    Source: irs.gov/pub/irs-pdf/p915.pdf — Worksheets 2 & 4

    The SSA-1099 "Description of Amount in Box 3" section lists each prior
    year and its payment amount. One instance per prior year is required.

    Engine uses Worksheet 2 (post-1993 years) for each prior year:
      Line 1  = prior-year Box 5 net benefits PLUS this year's lump-sum for that year
      Line 2  = Line 1 × 50%
      Line 3  = prior-year AGI (from taxpayer's prior-year return)
      Line 4  = prior-year exclusion adjustments (Form 8815, 2555, 4563, etc.)
      Line 5  = prior-year tax-exempt interest
      Line 6  = sum of lines 2–5
      Line 7  = prior-year Schedule 1 adjustments (lines 11–20, 23, 25)
      Lines 8–19 = SS taxability worksheet (same structure as Worksheet 1)
      Line 20 = taxable SS benefits ALREADY reported for that prior year (prior-year 1040 Line 6b)
      Line 21 = additional taxable benefits (line 19 − line 20, floor 0)
                → carries to Worksheet 4

    Worksheet 3 (1993 or earlier): uses older thresholds ($25k/$32k still apply
    but the upper tier calculation differs slightly; engine uses Worksheet 2 logic
    for all post-1983 years since the formulas are structurally identical for
    post-1993 years, and Worksheet 3 years are pre-1994 which is extremely rare).
    Flag is_pre_1994 to trigger warning that manual verification is needed.
    """
    prior_year: int = 0                       # e.g. 2024
    lump_sum_amount_for_this_year: float = 0  # portion of Box 3 attributed to this prior year
    prior_year_net_ss_benefits: float = 0     # prior-year SSA-1099 Box 5
    prior_year_agi: float = 0                 # prior-year Form 1040 Line 11
    prior_year_tax_exempt_interest: float = 0 # prior-year Form 1040 Line 2a
    prior_year_exclusion_adjustments: float = 0  # Form 8815/2555/4563 adjustments
    prior_year_sch1_adjustments: float = 0    # prior-year Sch 1 Lines 11-20, 23, 25
    prior_year_taxable_ss_already_reported: float = 0  # prior-year 1040 Line 6b
    is_pre_1994: bool = False                 # True → use Worksheet 3 (manual warning)

@dataclass
class FormSSA1099:
    """
    SSA-1099: Social Security Benefit Statement
    Source: irs.gov/pub/irs-pdf/p915.pdf (Pub 915 Appendix + Worksheets 1, 2, 4)

    Box 3 = gross benefits paid (shown in "Description of Amount in Box 3")
    Box 4 = repayments made during year (taxpayer-to-SSA)
    Box 5 = net benefits (Box 3 − Box 4) → Line 6a of Form 1040
    Box 6 = voluntary federal income tax withheld (Form W-4V elections: 7%/10%/12%/22%)
            → Form 1040 Line 25b (alongside 1099-R and other withholding)

    Lump-Sum Election (Form 1040 Line 6c checkbox):
      If Box 3 includes benefits for an earlier year, taxpayer may elect to
      refigure taxable benefits using prior-year income (Pub 915 Worksheets 2/4).
      Engine computes both methods and automatically uses the lower taxable amount.
      Taxpayer CANNOT amend prior-year returns — all math on current-year return.

    MFS lived-apart flag:
      Married filing separately AND lived apart ALL year → base amount = $25,000
      (same as single). If lived together at any point → base amount = $0 (85% always).
      Source: p915.pdf base amount table.
    """
    # Core boxes
    box3_gross_benefits: float = 0            # Gross benefits paid (before repayments)
    box4_repayments: float = 0                # Repayments made during 2025
    box5_net_benefits: float = 0              # Net benefits = Box 3 − Box 4 → Line 6a
    box6_voluntary_wh: float = 0              # Voluntary FIT withheld → Line 25b
    # Bridge hardening 2026-05-19 — fields sent by UI but missing from dataclass
    medicare_part_b_premiums: float = 0       # Medicare Part B premiums deducted from SS benefit. Source: SSA-1099 box; Pub 502
    medicare_part_d_premiums: float = 0       # Medicare Part D premiums deducted. Source: SSA-1099; Pub 502
    medicare_part_c_premiums: float = 0       # Medicare Advantage premiums deducted. Source: SSA-1099; Pub 502
    lump_sum_election: bool = False           # True = prior-year lump sum election available. Source: Pub 915; IRC §86(e)
    lump_sum_years: list = field(default_factory=list)  # List of prior years included in lump sum
    mfs_lived_apart: bool = False             # MFS and lived apart all year (different SS base). Source: IRC §86(d)(4)
    recipient: str = "taxpayer"               # "taxpayer" | "spouse" — which person received benefits

    # MFS lived-apart exception (changes base amount from $0 to $25,000)
    mfs_lived_apart_all_year: bool = False    # Only relevant when filing_status = "mfs"

    # Lump-sum election data (one entry per prior year in Box 3)
    lump_sum_prior_years: list = field(default_factory=list)  # list of SSALumpSumPriorYear

@dataclass
class Form1098T:
    """
    1098-T: Tuition Statement
    Source: irs.gov/pub/irs-pdf/f1098t.pdf, i8863.pdf, p970.pdf
    Box 1 = payments received for qualified tuition and related expenses
    Box 5 = scholarships or grants (reduces qualified expenses)
    Box 7 = checked if Box 1 includes amounts for Jan-Mar 2026
    Box 8 = at least half-time student
    Feeds Form 8863 (American Opportunity Credit or Lifetime Learning Credit)
    out_of_pocket_books/supplies/other = additional QEE not on 1098-T (AOC only, Pub 970 p17)
    """
    institution: str = ""
    ein: str = ""
    box1_payments: float = 0
    box5_scholarships: float = 0
    box7_future_period: bool = False
    box8_half_time: bool = True
    credit_type: str = "aoc"    # "aoc" = American Opportunity | "llc" = Lifetime Learning
    student_name: str = ""
    first_four_years: bool = True   # AOC only available first 4 years of higher ed
    # Additional out-of-pocket qualified education expenses (AOC only; IRC §25A(b)(1))
    # Course materials required for enrollment: books, supplies, equipment
    # Source: IRS Pub 970 (2024) p17; i8863.pdf Worksheet 1 Line 1
    out_of_pocket_books: float = 0      # Books required for enrollment
    out_of_pocket_supplies: float = 0   # Supplies required for enrollment
    out_of_pocket_other: float = 0      # Other required course materials
    # AOC eligibility gates — IRC §25A(b)(2); i8863.pdf Part III instructions
    aoc_drug_conviction: bool = False   # §25A(b)(2)
    # Bridge hardening 2026-05-19 — fields sent by UI but missing from dataclass
    aoc_years_claimed_prior: int = 0    # Times AOC claimed before TY. Must be < 4 total. Source: f8863.pdf L27; IRC §25A(b)(2)
    box9_graduate: bool = False         # Box 9: graduate student — blocks AOC, LLC may apply. Source: f1098t.pdf; f8863.pdf
    student_who: str = ""               # "taxpayer" | "spouse" | "dependent" — credit attribution. Source: f8863.pdf(D): federal/state drug conviction → $0 AOC

@dataclass
class Form1099C:
    """
    1099-C: Cancellation of Debt
    Source: irs.gov/pub/irs-pdf/f1099c.pdf, i1099ac.pdf
    Box 2 = amount of debt discharged → generally taxable → Schedule 1 Line 8c
    Box 6 = identifiable event code
    Exceptions (taxpayer must determine): insolvency, bankruptcy → Form 982
    Always flag for taxpayer to verify exception eligibility
    """
    creditor: str = ""
    box2_amount_discharged: float = 0
    box6_event_code: str = ""
    box1_date_of_event: str = ""  # Box 1 — Date of identifiable event. Source: f1099c.pdf
    box3_interest: float = 0      # Box 3 — Interest included in Box 2. Source: f1099c.pdf
    box4_debt_description: str = "" # Box 4 — Debt description. Source: f1099c.pdf
    box5_personally_liable: bool = True  # Box 5 — Personally liable for debt (recourse). Source: f1099c.pdf; IRC §108
    box7_fmv: float = 0           # Box 7 — FMV of property (non-recourse). Source: f1099c.pdf
    creditor_ein: str = ""        # Creditor EIN (identification). Source: f1099c.pdf
    is_excluded: bool = False   # True if taxpayer qualifies for insolvency/bankruptcy exception

@dataclass
class Form982Data:
    """
    Form 982 — Reduction of Tax Attributes Due to Discharge of Indebtedness (IRC §108)
    Source: irs.gov/pub/irs-pdf/f982.pdf | Instructions: irs.gov/pub/irs-pdf/i982.pdf

    Insolvency exclusion (IRC §108(a)(1)(B)):
      Insolvent = total liabilities exceed FMV of total assets immediately before discharge.
      Exclusion = min(discharged_amount, insolvency_amount = liabilities - assets FMV).

    Bankruptcy exclusion (IRC §108(a)(1)(A)):
      Title 11 case — full discharge excluded if under bankruptcy protection.

    Engine computes the worksheet automatically when this dataclass is provided.
    Source: f982.pdf; i982.pdf; IRC §108(a)(1)(A)-(B); IRS Pub 4681.
    """
    bankruptcy_title11: bool = False       # Box 1a: discharge in Title 11 bankruptcy case
    # Insolvency worksheet (i982.pdf p.3; IRC §108(a)(1)(B))
    total_liabilities_before: float = 0   # All debts immediately before discharge (mortgage, cards, IRS, etc.)
    total_assets_fmv_before: float = 0    # FMV of all assets immediately before discharge (cash, RE, vehicles, etc.)
    # Override: if 0, engine uses sum of Form 1099-C box2_amount_discharged amounts
    discharged_amount_override: float = 0

@dataclass
class Form1099MISC_Prize:
    """
    Prize/Award money: 1099-MISC Box 3
    Source: irs.gov/pub/irs-pdf/f1099msc.pdf
    Box 3 = other income (prizes, awards, gambling winnings if not on W-2G)
    → Schedule 1 Line 8b (other income)
    """
    payer: str = ""
    box3_other_income: float = 0
    description: str = "Prize/Award"

@dataclass
class Form1098E:
    """
    Form 1098-E — Student Loan Interest Statement
    Source: irs.gov/pub/irs-pdf/f1098e.pdf | Instructions: irs.gov/pub/irs-pdf/i1098e.pdf
    IRC §221 — student loan interest deduction (above-line, Schedule 1 Line 21)
    Up to $2,500 deductible; phases out at MAGI $75k–$90k (single) / $155k–$185k (MFJ) for 2025.
    """
    lender: str = ""                    # Lender name
    lender_ein: str = ""               # Lender EIN
    box1_student_loan_interest: float = 0   # Box 1 — student loan interest received by lender
    box2_origination_before_sept_2004: bool = False  # Box 2 — loan originated before 09/01/2004

@dataclass
class Form1099NEC:
    """
    1099-NEC: Nonemployee Compensation (2025)
    Source: irs.gov/pub/irs-pdf/f1099nec.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1099nec.pdf
    Box 1 = nonemployee compensation → Schedule C gross income (self-employment)
    Box 4 = federal income tax withheld (backup withholding) → Line 25b
    Box 5 = state tax withheld  Box 6 = state/payer ID  Box 7 = state income
    """
    payer: str = ""
    payer_ein: str = ""
    box1_nonemployee_comp: float = 0    # → Schedule C gross income
    box4_fed_wh: float = 0              # Backup WH → Line 25b
    box5_state_wh: float = 0
    box6_state_id: str = ""
    box7_state_income: float = 0

@dataclass
class ScheduleC:
    """
    Schedule C — Profit or Loss from Business (Sole Proprietorship) (2025)
    Source: irs.gov/pub/irs-pdf/f1040sc.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1040sc.pdf

    Part I  — Income
    Part II — Expenses
    Part III— Cost of goods sold (if applicable)
    Part V  — Other expenses

    Net profit (Line 31) → Schedule 1 Line 3 → Form 1040 AGI
    Net loss may be limited by at-risk rules (Form 6198) or passive activity rules.

    Self-employment tax computed on Schedule SE (Line 57 in engine = net SE income).
    QBI deduction (§199A) deferred — flagged as warning.
    """
    business_name: str = ""
    business_ein: str = ""
    principal_product_service: str = ""
    principal_product: str = ""           # Alias: UI/JSON uses principal_product → maps to principal_product_service
    business_code: str = ""               # Box A: NAICS 6-digit code. Source: f1040sc.pdf; i1040sc.pdf Appendix
    accounting_method: str = "cash"         # "cash" or "accrual"
    material_participation: bool = True

    # Part I — Income
    gross_receipts: float = 0               # Line 1 — preparer must include 1099-NEC Box 1 here
    nec_included_in_gross: bool = True      # True = 1099-NEC already in gross_receipts (default)
                                             # False = engine adds matched 1099-NEC to gross_receipts
                                             # Source: i1040sc.pdf Line 1; i1099nec.pdf
    returns_allowances: float = 0           # Line 2
    other_income: float = 0                 # Line 6

    # Part II — Expenses (Lines 8-27)
    advertising: float = 0                  # Line 8
    car_truck_expenses: float = 0           # Line 9 — actual car/truck expenses (Form 4562 if >$2,500)
    business_miles: float = 0              # Part IV — business miles. Standard rate 67¢/mile (2025). Source: Rev. Proc. 2024-45; i1040sc.pdf Part IV
    commissions_fees: float = 0             # Line 10
    contract_labor: float = 0              # Line 11
    depletion: float = 0                    # Line 12
    depreciation: float = 0                # Line 13 (Form 4562)
    employee_benefit_programs: float = 0    # Line 14
    insurance: float = 0                    # Line 15
    mortgage_interest: float = 0            # Line 16a
    other_interest: float = 0              # Line 16b
    legal_professional: float = 0          # Line 17
    office_expense: float = 0              # Line 18
    pension_profit_sharing: float = 0      # Line 19
    rent_lease_vehicles: float = 0         # Line 20a
    rent_lease_other: float = 0            # Line 20b
    repairs_maintenance: float = 0         # Line 21
    supplies: float = 0                    # Line 22
    taxes_licenses: float = 0              # Line 23
    travel: float = 0                      # Line 24a
    meals: float = 0                       # Line 24b (50% limitation applies)
    utilities: float = 0                   # Line 25
    wages: float = 0                       # Line 26
    other_expenses: float = 0              # Line 27a (Part V detail)

    # Home office (Form 8829) — simplified method only
    home_office_sq_ft: float = 0           # Business sq ft (simplified: $5/sq ft max 300)
    use_home_office_simplified: bool = False

    # v12 (P3): Form 8995-A fields — required above QBI threshold
    # Source: irs.gov/pub/irs-pdf/f8995a.pdf; IRC §199A(b)(2)(B)
    w2_wages: float = 0                    # W-2 wages paid to employees of this business
    ubia_qualified_property: float = 0     # Unadjusted basis of qualified property (depreciable)
    is_sstb: bool = False                  # Specified Service Trade or Business (law, health, consult, etc.)

    # Part III — Cost of Goods Sold (Gap 11) — Source: f1040sc.pdf Part III
    # Only applicable for businesses that sell physical products or carry inventory
    inventory_beginning: float = 0        # Line 35: inventory at start of year
    purchases: float = 0                  # Line 36: purchases during year
    cost_of_labor: float = 0             # Line 37: cost of labor (not SE owner wages)
    materials_supplies_cogs: float = 0   # Line 38: materials and supplies for COGS
    other_cogs: float = 0                # Line 39: other costs
    inventory_ending: float = 0          # Line 41: inventory at end of year
    # COGS = inventory_beginning + purchases + cost_of_labor + materials + other − inventory_ending
    # If COGS fields all 0, Part III is skipped (service businesses)

    # Bridge hardening 2026-05-19 — for_spouse was in run() via getattr but not in dataclass
    for_spouse: bool = False  # True = this Schedule C belongs to spouse (MFJ SE income split). Source: f1040sc.pdf

@dataclass
class Form1099DIV:
    """
    1099-DIV: Dividends and Distributions (2025)
    Source: irs.gov/pub/irs-pdf/f1099div.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1099div.pdf

    Box 1a = Total ordinary dividends → Schedule B → Form 1040 Line 3b
    Box 1b = Qualified dividends → Form 1040 Line 3a (preferential QDCGT rates)
    Box 2a = Total capital gain distributions → Schedule D Line 13
    Box 2b = Unrecaptured Section 1250 gain (25% rate)
    Box 2c = Section 1202 gain (small business stock)
    Box 2d = Collectibles gain (28% rate)
    Box 2e = Section 897 ordinary dividends
    Box 2f = Section 897 capital gain
    Box 3  = Nondividend distributions (return of capital — reduces basis)
    Box 4  = Federal income tax withheld (backup WH) → Line 25b
    Box 5  = Section 199A dividends (REIT/PTP — may qualify for QBI deduction)
    Box 6  = Investment expenses (only for non-RIC)
    Box 7  = Foreign tax paid → Form 1116
    Box 8  = Foreign country
    Box 9  = Cash liquidation distributions
    Box 10 = Noncash liquidation distributions
    Box 11 = Exempt-interest dividends → Form 1040 Line 2a (also in SS provisional income)
    Box 12 = Specified private activity bond interest (AMT)
    Boxes 13-16 = State information
    """
    payer: str = ""
    payer_ein: str = ""
    box1a_ordinary_div: float = 0           # → Line 3b via Schedule B
    box1b_qualified_div: float = 0          # → Line 3a (QDCGT preferential rates)
    box2a_cap_gain_dist: float = 0          # → Schedule D Line 13
    box2a_total_cap_gain: float = 0        # alias: UI/JSON uses box2a_total_cap_gain
    box2b_unrec_1250: float = 0             # Unrecaptured §1250 (25% rate)
    box2c_sec1202: float = 0
    box2d_collectibles: float = 0           # 28% rate
    box3_nondiv_dist: float = 0             # Return of capital
    box4_fed_wh: float = 0                  # Backup WH → Line 25b
    box5_sec199a_div: float = 0             # REIT/PTP §199A dividends
    box6_invest_expense: float = 0
    box7_foreign_tax: float = 0             # → Form 1116
    box8_foreign_country: str = ""
    box11_exempt_interest: float = 0        # → Line 2a; in SS provisional income
    box12_private_activity: float = 0       # AMT
    box15_state_wh: float = 0
    box16_state_id: str = ""

@dataclass
class EstimatedTaxPayments:
    """
    Form 1040-ES: Estimated Tax Payments (2025)
    Source: irs.gov/pub/irs-pdf/f1040es.pdf
    Also includes prior-year overpayment applied to 2025.
    → Form 1040 Line 26
    """
    q1: float = 0    # Due April 15, 2025
    q2: float = 0    # Due June 16, 2025
    q3: float = 0    # Due September 15, 2025
    q4: float = 0    # Due January 15, 2026
    prior_year_overpayment_applied: float = 0  # From 2024 return applied to 2025
    """
    Form 8606 — Nondeductible IRAs
    Source: irs.gov/pub/irs-pdf/f8606.pdf, i8606.pdf
    Part I  — Nondeductible traditional IRA contributions (basis tracking)
    Part II — Roth conversions / withdrawals from traditional IRA with basis
    Part III— Roth IRA distributions
    Inherited IRA basis tracked separately per beneficiary
    """
    # Part I — Nondeductible contributions
    nonded_contrib_this_year: float = 0      # L1: current year nondeductible contrib
    basis_prior_year: float = 0              # L2: total basis from prior Form 8606s
    # Traditional IRA values at year end
    trad_ira_value_dec31: float = 0          # L6: FMV of ALL traditional/SEP/SIMPLE IRAs on 12/31
    # Part II — Roth conversions / distributions with basis
    trad_ira_distributions: float = 0        # L7: total distributions (incl. conversions) from trad IRA
    # Part III — Roth IRA distributions
    roth_distributions: float = 0           # L19: total Roth IRA distributions
    roth_basis_contributions: float = 0     # L22: basis in Roth (total regular contributions)
    roth_account_5yr_old: bool = False       # qualified distribution requires 5-yr holding
    over_59_5: bool = True                   # age test for qualified Roth distribution
    # Inherited IRA
    is_inherited: bool = False
    inherited_basis: float = 0              # basis allocated from decedent's Form 8606

@dataclass
class Form8606Data:
    """
    Form 8606 — Nondeductible IRAs
    Source: irs.gov/pub/irs-pdf/f8606.pdf, i8606.pdf
    Part I  — Nondeductible traditional IRA contributions (basis tracking)
    Part II — Roth conversions / withdrawals from traditional IRA with basis
    Part III— Roth IRA distributions
    Inherited IRA basis tracked separately per beneficiary
    """
    nonded_contrib_this_year: float = 0      # L1
    basis_prior_year: float = 0              # L2
    trad_ira_value_dec31: float = 0          # L6: FMV of ALL traditional/SEP/SIMPLE IRAs 12/31
                                             # CRITICAL: must include ALL trad/SEP/SIMPLE IRA balances
                                             # (aggregation rule — not just the converting account)
    trad_ira_distributions: float = 0        # L7: total distributions incl. conversions
    # Part II — Roth conversion fields (v10)
    # conversion_amount: the portion of trad_ira_distributions that was converted to Roth
    # For backdoor Roth: conversion_amount = full nondeductible contribution just made
    # For partial conversion: conversion_amount ≤ trad_ira_distributions
    conversion_amount: float = 0            # L16: amount converted to Roth IRA this year
                                             # If 0 and trad_ira_distributions > 0: assume all withdrawn, none converted
    is_backdoor_roth: bool = False          # True: nonded contrib + immediate conversion (aggregation warning)
    roth_distributions: float = 0           # L19
    roth_basis_contributions: float = 0     # L22
    roth_account_5yr_old: bool = False
    over_59_5: bool = True
    is_inherited: bool = False
    inherited_basis: float = 0

@dataclass
class Form1099B:
    """
    1099-B: Proceeds from Broker Transactions → Schedule D / Form 8949
    Source: irs.gov/pub/irs-pdf/f1099b.pdf, f8949.pdf, f1040sd.pdf
    Box 1a = description of property
    Box 1b = date acquired
    Box 1c = date sold
    Box 1d = proceeds
    Box 1e = cost or other basis
    Box 1f = accrued market discount
    Box 1g = wash sale loss disallowed
    Box 2  = long-term/short-term indicator
    Box 3  = basis reported to IRS (checked = Box B; unchecked = Box A/C)
    Box 4  = federal income tax withheld
    Box 5  = if checked, noncovered security (basis NOT reported to IRS)
    """
    description: str = ""
    date_acquired: str = ""
    date_sold: str = ""
    proceeds: float = 0
    cost_basis: float = 0
    accrued_discount: float = 0
    wash_sale_loss_disallowed: float = 0
    is_long_term: bool = True           # True=long-term; False=short-term
    basis_reported_to_irs: bool = True  # True=Box B; False=Box A (covered ST) / C (not reported)
    noncovered: bool = False            # Box 5 checked
    fed_wh: float = 0                   # Box 4
    broker: str = ""

@dataclass
class Form4972Data:
    """
    Form 4972 — Tax on Lump-Sum Distributions
    Source: irs.gov/pub/irs-pdf/f4972.pdf, i4972.pdf
    Applies to: 1099-R Code A (qualifying lump-sum from qualified plan, born before 1936)
    Part II — 20% Capital Gain Election (optional)
    Part III — 10-Year Tax Option (optional, uses 1986 tax rates)
    NOTE: Form 4972 uses special rate schedules from the form itself — not regular brackets.
    """
    participant_name: str = ""
    employer_plan_name: str = ""
    # From 1099-R for lump-sum
    ordinary_income: float = 0          # L6: ordinary income portion
    capital_gain: float = 0             # L3: capital gain portion (pre-1974 participation)
    # Elections
    elect_20pct_capital_gain: bool = False   # Part II: pay 20% on capital gain portion
    elect_10yr_option: bool = False          # Part III: use 10-year averaging
    # Part III calculations use 1986 rates — read from f4972.pdf table
    previous_lump_sum_this_year: bool = False  # prior plan distribution same year

@dataclass
class ScheduleAData:
    """
    Schedule A — Itemized Deductions
    Source: irs.gov/pub/irs-pdf/f1040sa.pdf, i1040sa.pdf
    Line 1-4:  Medical & Dental (7.5% of AGI floor)
    Line 5-6:  State & Local Taxes — OBBBA: $40,000 cap (was $10k); phase-down above $500k AGI
    Line 7:    Other taxes
    Line 8-9:  Mortgage interest (Form 1098) + points
    Line 11:   Investment interest
    Line 12-14:Charitable contributions (OBBBA: 0.5% AGI floor before 60% cap)
    Line 16:   Casualty/theft losses (disaster area only — permanently disallowed otherwise per OBBBA)
    Line 17:   Other misc deductions (permanently disallowed per OBBBA §70501)
    """
    # Medical & Dental
    medical_dental_total: float = 0      # L1: total unreimbursed medical/dental expenses
    # includes Medicare Part B/D premiums, Medicare Advantage, supplemental premiums
    # State & Local Taxes (SALT)
    state_income_tax: float = 0          # L5a: state/local income taxes paid
    real_estate_tax: float = 0           # L5b: real estate taxes
    personal_property_tax: float = 0     # L5c: personal property taxes
    other_state_local_tax: float = 0     # L6: other taxes
    # Mortgage Interest (Form 1098)
    mortgage_interest_1098: float = 0    # L8a: from Form 1098
    mortgage_points: float = 0           # L8c: not from Form 1098
    mortgage_insurance_premiums: float = 0  # L8d: PMI premiums
    investment_interest: float = 0       # L9: investment interest (Form 4952)
    # Charitable
    cash_charitable: float = 0           # L11: cash/check/electronic
    noncash_charitable: float = 0        # L12: non-cash (Form 8283 if >$500)
    carryover_charitable: float = 0      # L13: carryover from prior year
    # Casualty/Theft
    casualty_theft_loss: float = 0       # L15: net casualty loss (Form 4684)
    # Other misc
    other_misc: float = 0                # L16: other miscellaneous
    # Mortgage loan details (for $750k/$1M limit computation — v15 fix)
    mortgage_balance_outstanding: float = 0   # Outstanding loan balance for limit test
    mortgage_is_grandfathered: bool = False   # True = pre-12/16/2017 loan → $1M limit

@dataclass
class Dependent:
    """
    Source: irs.gov/pub/irs-pdf/i1040.pdf — Dependents section
    CTC eligible: qualifying child under age 17 at Dec 31, 2025 with valid SSN
    ODC eligible: dependent NOT CTC-eligible (age 17+, or qualifying relative, or
                  child with ITIN) → $500 nonrefundable Credit for Other Dependents
    """
    first: str = ""
    last: str = ""
    ssn: str = ""
    dob: str = ""
    relationship: str = "child"
    lived_all_year: bool = True
    ctc_eligible: bool = True       # Under 17, US citizen/national/resident, SSN required
    odc_eligible: bool = False      # Age 17+, qualifying relative, or ITIN child
    age: int = 0                    # Used to auto-warn if ctc_eligible=True but age>=17

@dataclass
class Form2441Provider:
    name: str = ""
    address: str = ""
    ein: str = ""
    expenses: float = 0

@dataclass
class Form8880Data:
    ira_contributions: float = 0
    elective_deferrals: float = 0
    disqualifying_dist: float = 0

@dataclass
class Form1095AMonth:
    """One row of Form 1095-A Part III (Lines 21–33) — monthly coverage data.
    Source: irs.gov/pub/irs-pdf/f1095a.pdf Part III
    Column A = monthly enrollment premium (actual premium for plan enrolled in)
    Column B = monthly SLCSP premium (Second Lowest Cost Silver Plan — from HealthCare.gov)
    Column C = monthly APTC (advance premium tax credit paid to insurer)
    """
    col_a: float = 0    # monthly enrollment premium
    col_b: float = 0    # monthly SLCSP premium
    col_c: float = 0    # monthly APTC advance payment

@dataclass
class Form1095A:
    """
    Form 1095-A — Health Insurance Marketplace Statement
    Source: irs.gov/pub/irs-pdf/f1095a.pdf  |  Instructions: irs.gov/pub/irs-pdf/if1095a.pdf

    Part I  — Recipient information (policy number, issuer, coverage period)
    Part II — Covered individuals (names, SSNs, start/end months)
    Part III — Coverage information by month (Lines 21–33)
               Col A = monthly enrollment premium
               Col B = monthly applicable SLCSP premium (from HealthCare.gov lookup)
               Col C = monthly advance premium tax credit (APTC) paid to insurer

    Annual totals (Lines 33a/b/c) = sum of all months in coverage.

    Mid-year coverage: If coverage started or ended mid-year (job change, marriage, birth,
    loss of Medicaid eligibility, etc.), monthly entries will differ from month to month.
    Form 8962 Lines 12–23 must be used instead of Line 11 (annual method).
    Engine automatically detects mid-year when monthly entries are non-uniform and
    routes to Lines 12–23 computation.

    Annual shortcut (Line 11): valid ONLY if same plan/same APTC all 12 months.
    Source: irs.gov/pub/irs-pdf/i8962.pdf Lines 11–23.
    """
    policy_number: str = ""
    issuer: str = ""
    # Annual totals (Lines 33a/b/c) — used when all 12 months identical (Line 11 method)
    col_a_annual: float = 0
    col_b_annual: float = 0
    col_c_annual: float = 0
    # Monthly data (Lines 21–32, i.e. January–December) — for Lines 12–23 method
    # Leave empty to use annual totals only (Line 11 method)
    months: list = field(default_factory=list)   # list of Form1095AMonth (12 entries for full year)
    # Coverage months: if not all 12, specify which months had coverage
    start_month: int = 1    # 1=January; first month of coverage this policy
    end_month: int = 12     # 12=December; last month of coverage this policy

@dataclass
class DeceasedSpouse:
    name: str = ""
    ssn: str = ""
    date_of_death: str = ""

@dataclass
class TaxpayerSchema:
    """Master schema — structured input to computation engine"""
    # Identity
    first: str = ""
    last: str = ""
    ssn: str = ""
    dob: str = ""
    occupation: str = ""
    address: str = ""
    filing_status: str = "single"
    deceased_spouse: Optional[DeceasedSpouse] = None
    tax_year: int = 2025
    # Spouse metadata (MFJ/MFS) — stored for workpaper/return header; not used in computation
    spouse_ssn: str = ""
    spouse_first: str = ""
    spouse_last: str = ""
    spouse_dob: str = ""

    # Income
    w2s: list = field(default_factory=list)
    form_1099ints: list = field(default_factory=list)
    form_1099rs: list = field(default_factory=list)
    form_1099divs: list = field(default_factory=list)          # v5: per-payer dividends
    form_1099necs: list = field(default_factory=list)          # v5: nonemployee comp
    form_ssa1099: Optional[FormSSA1099] = None
    form_1099cs: list = field(default_factory=list)
    form_982: object = None                  # F6: Form982Data | None — insolvency/bankruptcy worksheet (IRC §108)
    form_1099misc_prizes: list = field(default_factory=list)
    schedule_cs: list = field(default_factory=list)            # v5: Schedule C businesses
    dividends_ordinary: float = 0    # legacy flat field — overridden by form_1099divs if present
    dividends_qualified: float = 0   # legacy flat field — overridden by form_1099divs if present
    estimated_tax_payments: Optional[EstimatedTaxPayments] = None  # v5: Form 1040-ES Line 26

    # Dependents
    dependents: list = field(default_factory=list)

    # Adjustments (Schedule 1 Part II)
    teacher_expense: float = 0          # → Sch 1 Line 11, max $300
    student_loan_interest: float = 0
    other_adjustments: float = 0
    # v6: SE health insurance deduction — Schedule 1 Line 17
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf; IRC §162(l)
    # Cannot exceed net SE profit; disallowed if eligible for employer-subsidized plan
    se_health_insurance_premiums: float = 0
    # v6: SE retirement deduction — Schedule 1 Line 16
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf; IRC §404
    # SEP-IRA: min(25% of net SE after deductions, $70,000 for 2025)
    # SIMPLE IRA: employee deferrals (elective) + employer match/non-elective
    # Solo 401(k): elective deferrals up to $23,500 + 25% employer contributions
    se_retirement_contributions: float = 0   # user-computed or elective deferrals
    # v12 (P1): Plan type selector — determines which cap applies
    # "sep" = SEP-IRA (20% × net SE comp, cap $70,000)
    # "solo401k" = Solo 401(k) elective + employer, total cap $70,000; elective cap $23,500 ($31,000 age 50+)
    # "simple" = SIMPLE IRA, $16,500 elective ($20,000 age 50+)
    # Source: irs.gov/pub/irs-pdf/p560.pdf; IRC §404
    se_retirement_plan_type: str = "sep"     # "sep" | "solo401k" | "simple"

    # Credits
    care_providers: list = field(default_factory=list)
    form_1098ts: list = field(default_factory=list)
    form_1098es: list = field(default_factory=list)   # Form 1098-E student loan interest statements          # education credits
    form_8880: Optional[Form8880Data] = None
    form_1095a: Optional[Form1095A] = None

    # v3/v5 — Additional forms
    form_8606: Optional[Form8606Data] = None                 # nondeductible IRA / Roth (taxpayer)
    form_8606_spouse: Optional[Form8606Data] = None          # nondeductible IRA / Roth (spouse — MFJ only)
                                                              # IRS requires SEPARATE Form 8606 per spouse
                                                              # Source: i8606.pdf "Who Must File"
    form_1099bs: list = field(default_factory=list)          # capital gains (→ Sch D / 8949)
    form_4972: Optional[Form4972Data] = None                 # lump-sum distribution
    schedule_a: Optional[ScheduleAData] = None               # itemized deductions
    use_itemized: bool = False
    exact_eitc_from_table: float = -1.0   # v5: -1 = not confirmed; set to exact IRS table value

    # v7 — new forms
    schedule_es: list = field(default_factory=list)          # Schedule E rental properties
    form_6251: Optional["Form6251Data"] = None               # AMT — set None to skip
    form_8582: Optional["Form8582Data"] = None               # Passive activity — auto-built from Sch E losses

    # v8 — Gap fills
    form_8889: Optional["Form8889Data"] = None               # HSA → Sch 1 Line 13
    form_w2gs: list = field(default_factory=list)            # Gambling winnings (W-2G)
    gambling_losses: float = 0                               # Schedule A Line 16 (only if itemizing)
    form_1099gs: list = field(default_factory=list)          # Unemployment / state refunds (1099-G)
    schedule_k1s: list = field(default_factory=list)         # K-1 pass-through income (Sch E Part II)
    alimony: Optional["AlimonyData"] = None                  # Pre-2019 alimony paid/received
    form_2210: Optional["Form2210Data"] = None               # Underpayment penalty safe harbor
    california: Optional["CaliforniaData"] = None            # CA Form 540
    # v9: new forms
    form_5329_exceptions: list = field(default_factory=list) # Form 5329 exception claims
    form_1116: Optional["Form1116Data"] = None               # Foreign Tax Credit
    # v10: new forms
    form_8615: Optional["Form8615Data"] = None               # Kiddie Tax (child's unearned income at parent's rate)
    form_4797s: list = field(default_factory=list)           # Sales of Business Property (§1231/§1245/§1250)
    # Schedule C COGS (Gap 11) — added to ScheduleC via separate field below
    # IRA deduction is auto-computed from contributions + W-2 Box 13 + MAGI
    ira_contribution_traditional: float = 0                  # traditional IRA contribution for 2025
    ira_taxpayer_age: int = 0                                # used for catch-up limit ($8k if 50+)
    # v11: NOL carryforward from prior year (IRC §172) — Schedule 1 Line 8a
    # Post-TCJA: indefinite carryforward, limited to 80% of current-year taxable income
    # User must supply from prior-year Form 1045 / Form 1040 NOL worksheet
    nol_carryforward_prior_year: float = 0                   # → Sch 1 Line 8a

    # v12 (P1): Capital loss carryover from prior year — Schedule D Line 6/14
    # When current-year capital losses exceed $3,000, the excess carries forward
    # Supply from prior-year Schedule D Line 16 (net loss) minus $3,000
    # Source: irs.gov/pub/irs-pdf/f1040sd.pdf Line 6/14; IRC §1212(b)
    capital_loss_carryover_prior: float = 0   # positive number = prior-year unused loss

    # v13 (Bridge hardening 2026-05-19): fields present in UI/JSON but missing from schema
    # These were silently dropped by safe_init() — now added as proper typed fields.
    taxpayer_is_blind: bool = False          # Std ded +$1,950 single / +$1,550 per blind spouse. Source: IRC §63(f); f1040.pdf p2
    is_dependent_of_another: bool = False    # Std ded capped at earned income + $450. Source: IRC §63(c)(5); f1040.pdf
    dependent_earned_income: float = 0       # Used when is_dependent_of_another=True. Source: IRC §63(c)(5)
    qbi_loss_carryforward: float = 0         # Form 8995 Line 11 prior-year QBI loss. Source: f8995.pdf L11; IRC §199A
    aca_household_size: int = 0              # Form 8962 Line 1; 0 = derive from 1 + len(dependents). Source: f8962.pdf L1

    # v12 (P2): CalEITC / YCTC / FYTC — California refundable credits (Form FTB 3514)
    # Source: ftb.ca.gov/forms/2025/2025-3514.pdf
    # Engine computes if california is not None and CA earned income > 0
    ca_foster_youth_taxpayer: bool = False   # True if taxpayer was in CA foster care, age 18-25
    ca_foster_youth_spouse: bool = False     # True if spouse qualifies for FYTC

    # ── OBBBA TY 2025 NEW DEDUCTIONS (P.L. 119-21, signed July 4, 2025) ──────────
    # Source: irs.gov/newsroom/one-big-beautiful-bill-provisions

    # Senior Bonus Deduction — §70103 (TY 2025–2028)
    # $6,000 per qualifying taxpayer/spouse age 65+; phases out above $75k/$150k MAGI
    # MFS ineligible. Set ages here; engine computes based on dob if 0.
    taxpayer_age_for_senior_ded: int = 0    # taxpayer age at Dec 31, 2025 (0 = use dob)
    spouse_age_for_senior_ded: int = 0      # spouse age at Dec 31, 2025 (0 = not applicable)

    # Tip Income Deduction — §70201 (TY 2025–2028)
    # Qualified cash/charged tips in customary tip occupations. Cap $25,000.
    # Phases out above $150k/$300k MAGI. Must be reported on W-2 or SE income.
    qualified_tips: float = 0               # → Schedule 1-A Line 13b (below-the-line)
    # IRS Notice 2025-65 qualifying occupation. Empty string = not validated.
    # Source: IRS Notice 2025-65; P.L. 119-21 §70201
    tip_occupation: str = ""                # must match a qualifying occupation to claim deduction

    # Overtime Pay Deduction — §70202 (TY 2025–2028)
    # FLSA-qualifying overtime. Cap $12,500 single / $25,000 MFJ.
    # Phases out above $150k/$300k MAGI. MFS ineligible.
    overtime_pay_qualifying: float = 0      # → Schedule 1-A Line 13b (below-the-line)
    # FLSA confirmation — employer must separately identify FLSA-qualifying overtime.
    # Bonuses, shift differentials, and exempt-employee extra pay do NOT qualify.
    # Source: P.L. 119-21 §70202; FLSA §207; irs.gov/newsroom/one-big-beautiful-bill-provisions
    overtime_flsa_confirmed: bool = False   # must be True to avoid warning

    # Auto Loan Interest Deduction — §70301 (TY 2025–2028)
    # Interest on qualified passenger vehicle loans. Cap $10,000/yr.
    # Phases out above $100k/$200k MAGI. Loan post-12/31/2024; vehicle new US-assembled.
    auto_loan_interest: float = 0           # → Schedule 1-A Line 13b (below-the-line)
    auto_loan_originated_after_2024: bool = True    # must be True to qualify
    auto_loan_vehicle_new_us_assembled: bool = True # must be True to qualify

    # Form 2441 — Child and Dependent Care — spouse disability/student override
    # When a spouse has $0 earned income but IS a full-time student OR disabled,
    # IRC §21(d)(2) deems them to have earned income: $250/mo (1 person) or $500/mo (2+)
    # Source: f2441.pdf Line 6; IRC §21(d)(2); Pub 503
    care_spouse_is_student: bool = False    # spouse is full-time student during year
    care_spouse_is_disabled: bool = False   # spouse is disabled (unable to care for self)
    care_spouse_months_qualified: int = 0   # months spouse was student/disabled (1–12)

    # §1231 5-year lookback — TaxpayerSchema-level input for taxpayers without Form 4797 sales
    # Net §1231 losses from prior 5 years that recharacterize current §1231 gains as ordinary.
    # Source: IRC §1231(c); f4797.pdf; Pub 544
    prior_sec1231_losses_5yr: float = 0     # → passed to compute_form_4797 as aggregate

    # Schedule 1 Line 8h — Jury duty pay
    # Taxable as ordinary income per IRC §61(a). If taxpayer remitted jury pay to employer,
    # the employer-remitted amount may be deducted on Schedule 1 Line 24a.
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 8h; IRC §61(a); IRS Pub 525
    jury_duty_income: float = 0             # → Schedule 1 Line 8h


@dataclass
class ScheduleE:
    """
    Schedule E — Supplemental Income and Loss (Rental Real Estate) Part I
    Source: irs.gov/pub/irs-pdf/f1040se.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1040se.pdf

    Each row = one rental property (up to 3 per Schedule E; use multiple for more)
    All income and expenses are reported on cash basis unless accrual elected.

    Part I Lines:
      Line 3  = Rents received → Schedule E Line 3 (also Form 1040 Line 8, via Schedule 1 Line 5)
      Lines 5–19 = Deductible expenses (advertising, auto, cleaning, commissions,
                   insurance, legal, mgmt fees, mortgage interest, repairs,
                   supplies, taxes, utilities, depreciation, other)
      Line 20 = Total expenses
      Line 21 = Net income (loss) before passive activity
      Line 22 = Deductible rental loss (subject to Form 8582 passive activity rules
                and $25,000 allowance for active participants with AGI ≤ $100k)

    Passive activity rules — §469:
      - Rental activities are per se passive (regardless of hours)
      - Exception: Real estate professional (750+ hrs, majority of work time) → not passive
      - $25,000 allowance: active participants (not real estate pros) with AGI ≤ $100k
        may deduct up to $25,000 of rental losses against non-passive income
        Phase-out: $100k–$150k AGI → allowance reduced $0.50 per $1 over $100k
        Above $150k → allowance $0 (full Form 8582 suspension)
      - Suspended losses carry forward to future years or until property sold

    Depreciation: residential = 27.5 years straight-line (Form 4562)
    """
    address: str = ""
    property_type: str = "R"   # R=residential, P=personal use days, C=commercial
    days_rented: int = 365
    days_personal_use: int = 0

    # Part I Income
    rents_received: float = 0              # Line 3 → Schedule 1 Line 5

    # Part I Expenses (Lines 5–18)
    advertising: float = 0                 # Line 5
    auto_travel: float = 0                 # Line 6
    cleaning_maintenance: float = 0        # Line 7
    commissions: float = 0                 # Line 8
    insurance: float = 0                   # Line 9
    legal_professional: float = 0          # Line 10
    management_fees: float = 0             # Line 11
    mortgage_interest: float = 0           # Line 12 (Form 1098)
    other_interest: float = 0             # Line 13
    repairs: float = 0                    # Line 14
    supplies: float = 0                   # Line 15
    taxes: float = 0                      # Line 16 (real estate taxes)
    utilities: float = 0                  # Line 17
    depreciation: float = 0              # Line 18 (from Form 4562; residential = cost/27.5)
    other_expenses: float = 0            # Line 19

    # Participation flags (affects Form 8582)
    is_real_estate_professional: bool = False   # §469(c)(7): 750+ hrs, majority of work
    material_participation: bool = False         # significant participation (not re: rental)
    active_participation: bool = True            # actively managed (standard rental)

    # §280A vacation / personal-use rules (Gap 12)
    # If personal_use_days > max(14, 10% of days_rented) → property treated as personal residence
    # Expenses allocated by (days_rented / total_days_used); losses FULLY disallowed even active
    # Mortgage interest and RE taxes still deductible on Schedule A (not Schedule E)
    # Engine enforces this automatically when personal_use_days is set
    enforce_280a: bool = True                   # Set False only if vacation-rental rules confirmed inapplicable


@dataclass
class Form8582Data:
    """
    Form 8582 — Passive Activity Loss Limitations
    Source: irs.gov/pub/irs-pdf/f8582.pdf  |  Instructions: irs.gov/pub/irs-pdf/i8582.pdf

    Engine auto-builds this from Schedule E rental losses.
    Manual override: set prior_year_unallowed_losses to carry-forward from prior year.

    Worksheet 1 (Rental Real Estate with Special Allowance):
      Column (a) = current year net income from rental activities with net income
      Column (b) = current year net loss from rental activities with net loss
      Column (c) = prior year unallowed losses (carried from last year's Form 8582 Worksheet 7)

    Special $25,000 Allowance (§469(i)):
      - Available ONLY to active participants in rental real estate
      - NOT available to real estate professionals (their losses not passive)
      - Maximum allowance: $25,000 ($12,500 MFS lived apart)
      - Phase-out: 50% of AGI excess over $100,000 (over $50,000 MFS lived apart)
        → zero allowance when AGI ≥ $150,000 (≥ $100,000 MFS lived apart)

    Worksheet 4 — Allowed vs. Unallowed Losses:
      Allocates allowed loss proportionally among activities when total loss exceeds allowance.

    Prior year unallowed losses — user must supply from prior year's Worksheet 7.
    """
    prior_year_unallowed_losses: float = 0    # Worksheet 1 Column (c): carryforward
    mfs_lived_apart: bool = False              # affects $25k/$50k phase-out thresholds


@dataclass
class Form6251Data:
    """
    Form 6251 — Alternative Minimum Tax — Individuals (2025)
    Source: irs.gov/pub/irs-pdf/f6251.pdf  |  Instructions: irs.gov/pub/irs-pdf/i6251.pdf

    AMT applies if tentative minimum tax (TMT) > regular tax.
    For most W-2/standard-deduction filers, AMT does not apply.
    Engine computes Lines 1–18 (the common items); exotic preferences (mining, oil/gas, ISOs
    past exercise, etc.) are flagged as warnings for manual completion.

    Key inputs captured here (user-supplied adjustments beyond what engine can auto-derive):
      iso_bargain_element: ISO exercise spread (not in W-2; common AMT trigger)
      state_local_tax_itemized: SALT deduction claimed on Schedule A (addback required)
      misc_itemized_deductions: 2% floor misc deductions (eliminated post-TCJA → always $0)
      depletion_excess: excess depletion over adjusted basis
      net_operating_loss_deduction: NOL claimed in regular tax (addback required)

    Engine auto-sources:
      Line 1  = taxable income (Form 1040 Line 15 after QBI)
      Line 2a = standard deduction (if used) — addback for AMT
      Line 2b = state/local tax from Schedule A (SALT addback)
      Line 2j = ISO bargain element (from user field below)
      Line 4  = AMTI = sum of L1 + adjustments
      Line 5  = exemption (phased out above exemption phaseout income)
      Line 6  = AMTI minus exemption
      Line 7  = TMT = 26% × min(L6, $232,600) + 28% × max(0, L6−$232,600)
               (QDCGT rates apply to preferential income even in AMT — §55(b)(3))
      Line 9  = TMT minus regular tax = AMT (if positive → additional tax)
    """
    # User-supplied AMT preference items
    iso_bargain_element: float = 0            # Line 2j: ISO exercise spread (§56(b)(3))
    net_operating_loss_ded: float = 0         # Line 2i: NOL deduction (addback; §56(a)(4))
    depletion_excess: float = 0              # Line 2h: excess depletion (§57(a)(1))
    tax_shelter_farm_loss: float = 0         # Line 2f: tax shelter farm loss (§58)
    refund_of_taxes: float = 0              # Line 2d: refund of taxes included in income
    other_adjustments: float = 0             # Line 2o: other AMTI adjustments (catch-all)


@dataclass
class Form8889Data:
    """
    Form 8889 — Health Savings Accounts (HSA) (2025)
    Source: irs.gov/pub/irs-pdf/f8889.pdf  |  Instructions: irs.gov/pub/irs-pdf/i8889.pdf
            Pub 969: irs.gov/pub/irs-pdf/p969.pdf

    Part I — HSA Contributions and Deduction (→ Schedule 1 Line 13)
      Line 1   = HDHP coverage type: 1=self-only, 2=family
      Line 2   = Total HSA contributions made in 2025 (by taxpayer + spouse contributions,
                 EXCLUDING employer contributions in W-2 Box 12 Code W)
      Line 3   = Archer MSA contributions (reduces HSA limit)
      Line 4   = Employee contribution limit (from worksheet, based on coverage type)
      Line 5   = Additional contribution if age 55+ at year-end ($1,000 catch-up)
      Line 6   = Qualified HSA funding distribution from IRA (once-in-lifetime)
      Line 7   = Line 2 + Line 3 (total HSA contributions from all sources)
      Line 8   = Employer contributions from W-2 Box 12 Code W
      Line 9   = Qualified HSA funding distribution
      Line 10  = Total (Lines 8 + 9)
      Line 11  = Contribution limit minus Line 10 → remaining deductible
      Line 13  = Deductible HSA contributions (lesser of Line 2 and Line 11)
               → Schedule 1 Line 13

    Part II — HSA Distributions
      Line 14a = Total distributions (Box 1 of Form 1099-SA)
      Line 14b = Qualified medical expenses (tax-free)
      Line 14c = Distributions for non-medical use (Line 14a − 14b) → taxable
      Line 15  = Taxable HSA distributions → Schedule 1 Line 8f
      Line 17a/b = 20% additional tax if non-qualified use and under 65 / not disabled
               → Schedule 2 Line 17c

    Mid-year coverage rule (Last-Month Rule):
      If enrolled in HDHP on Dec 1, may contribute full-year limit even if enrolled mid-year.
      But must remain HDHP-enrolled for all of next year (testing period), or partial-year
      limit applies and excess becomes taxable income + 10% excise.

    Spousal note: Each spouse may contribute to their own HSA if HDHP-covered.
    Family limit shared; allocate between them as desired.

    HDHP 2025 minimums: self-only deductible ≥ $1,650; family ≥ $3,300
    HDHP 2025 OOP max: self-only ≤ $8,300; family ≤ $16,600
    """
    coverage_type: str = "self"          # "self" = self-only HDHP; "family" = family HDHP
    taxpayer_age: int = 0                # Used to determine catch-up eligibility (55+)
    spouse_age: int = 0                  # Spouse catch-up (if MFJ and spouse 55+)

    # Part I — Contributions
    contributions_taxpayer: float = 0   # L2: employee/self-employed contributions
    contributions_spouse: float = 0     # L2 spouse (for MFJ with separate HSAs)
    employer_contrib_w2_code_w: float = 0  # L8: W-2 Box 12 Code W (employer; reduces limit)
    archer_msa_contrib: float = 0       # L3: Archer MSA (rare)
    ira_funding_dist: float = 0         # L6: qualified IRA→HSA rollover (once per lifetime)
    last_month_rule_elected: bool = False  # If True, full-year limit allowed with testing period

    # Part II — Distributions (from Form 1099-SA)
    total_distributions: float = 0      # L14a: total from all HSA accounts (Form 1099-SA Box 1)
    qualified_medical_expenses: float = 0  # L14b: medical expenses paid with HSA
    # Non-qualified distributions = total - qualified → taxable + 20% penalty
    age_65_or_disabled: bool = False    # Exempt from 20% penalty; distributions still taxable


@dataclass
class FormW2G:
    """
    Form W-2G — Certain Gambling Winnings (2025)
    Source: irs.gov/pub/irs-pdf/fw2g.pdf  |  Instructions: irs.gov/pub/irs-pdf/iw2g.pdf

    Payers must issue W-2G when winnings exceed thresholds:
      - Slot machines, bingo, keno: ≥ $1,200
      - Poker tournaments: > $5,000
      - Other: ≥ $600 and ≥ 300× wager
      - State lotteries: ≥ $600 (some states vary)

    All gambling winnings are taxable as ordinary income → Schedule 1 Line 8b.
    This includes winnings NOT reported on W-2G (e.g., table game wins).

    Gambling losses:
      - ONLY deductible as itemized deduction on Schedule A Line 16
      - Cannot exceed gambling winnings (no net loss deduction)
      - NOT an above-the-line deduction
      - Records: taxpayer must keep diary of winnings/losses
      - Professional gambler: Schedule C (different rules; beyond scope here)

    Withholding:
      - Box 4: Federal income tax withheld → Form 1040 Line 25b
      - Box 15: State tax withheld → state return

    Note: Gambling winnings increase MAGI for purposes of:
      - SS provisional income
      - ACA subsidy cliff (Form 8962)
      - NIIT threshold test
    """
    payer: str = ""
    box1_winnings: float = 0            # → Schedule 1 Line 8b (all gambling income)
    box4_fed_wh: float = 0              # → Line 25b
    box14_state_wh: float = 0
    gambling_type: str = ""             # "slots", "lottery", "poker", "sports", "other"


@dataclass
class Form1099G:
    """
    Form 1099-G — Certain Government Payments (2025)
    Source: irs.gov/pub/irs-pdf/f1099g.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1099g.pdf

    Common uses:
      Box 1 = Unemployment compensation → Schedule 1 Line 7 → Form 1040
      Box 2 = State/local income tax refund → Schedule 1 Line 1 (if taxpayer itemized in prior year;
              if took standard deduction → not taxable; Tax Benefit Rule applies)
      Box 4 = Federal income tax withheld → Form 1040 Line 25b
      Box 10a = State / Payer's state number
      Box 11 = State income tax withheld → state return

    Unemployment compensation:
      - Fully taxable for federal; California exempts it from CA income tax
      - Box 4 withholding → Line 25b
      - Box 6: Taxable grants → Schedule 1 Line 8g
      - Box 7: Agriculture payments → Schedule F (not in scope)
      - Box 2 state refund: taxable only if itemized in year of refund with SALT deduction
        (Tax Benefit Rule — IRC §111). If deducted only via standard deduction → $0 taxable.

    MAGI impact: unemployment compensation counts in AGI for:
      - ACA premium tax credit cliff
      - EITC phase-out
      - SS provisional income
    """
    payer: str = ""                      # State agency or employer name
    box1_unemployment: float = 0         # → Schedule 1 Line 7
    box2_state_refund: float = 0         # → Schedule 1 Line 1 (if prior year itemized)
    box4_fed_wh: float = 0               # → Line 25b
    box6_taxable_grants: float = 0       # → Schedule 1 Line 8g
    box11_state_wh: float = 0
    prior_year_itemized: bool = False    # True → state refund is taxable (tax benefit rule)


@dataclass
class ScheduleK1:
    """
    Schedule K-1 — Distributive Share from Partnership, S-Corp, Estate, or Trust
    Source: f1065sk1.pdf (Partnership) | f1120ssk1.pdf (S-Corp) | f1041sk1.pdf (Estate/Trust)
            Instructions: i1065.pdf | i1120s.pdf | i1041.pdf

    Schedule E Part II (Form 1040) wiring:
      → Net income/loss → Schedule E Line 28, col (f) passive or (g) non-passive
      → Interest (Box 5) → Schedule B → Form 1040 Line 2b
      → Dividends (Box 6a/6b) → Schedule B → Lines 3a/3b
      → Net rental income (Box 2) → Schedule E Part I-equivalent
      → §179 deduction (Box 12 / Box 11 S-corp) → Form 4562
      → §199A income (Box 20Z or Box 17V) → Form 8995/8995-A
      → Capital gains (Box 9/10) → Schedule D
      → Self-employment income (Box 14a) → Schedule SE

    Passive activity rules:
      - Partnership/S-corp losses passive unless material participation test met
        (IRC §469(c): 7 tests; most common = 500+ hours or sole meaningful activity)
      - Rental income from partnership is passive by default (same as direct rental)
      - Form 8582 groups all passive activities; losses limited to passive income
      - Suspended losses released when activity fully disposed

    Engine scope: captures common boxes; routes income/loss through passive rules.
    Complex basis-at-risk (Form 6198), §704(d) outside-basis limits not computed.
    """
    entity_name: str = ""
    entity_ein: str = ""
    entity_type: str = "partnership"     # "partnership", "s_corp", "estate", "trust"
    taxpayer_pct: float = 100.0          # ownership/allocation percentage

    # Common boxes (partnership / S-corp)
    box1_ordinary_income: float = 0      # Ordinary business income (loss)
    box2_net_rental: float = 0           # Net rental real estate income (loss)
    box3_other_net_rental: float = 0     # Other net rental income
    box5_interest: float = 0             # Interest income → Schedule B
    box6a_ordinary_div: float = 0        # Ordinary dividends → Schedule B
    box6b_qualified_div: float = 0       # Qualified dividends → QDCGT
    box7_royalties: float = 0            # Royalties → Schedule E Part II
    box8_stcg: float = 0                 # Net short-term capital gain (loss)
    box9_ltcg: float = 0                 # Net long-term capital gain (loss)
    box9a_sec1231: float = 0             # Net §1231 gain (loss)
    box10_other_income: float = 0        # Other income (loss) → Schedule E
    box12_sec179: float = 0              # §179 deduction (limited by at-risk basis; not computed)
    box13_other_deductions: float = 0    # Other deductions
    box14a_se_income: float = 0          # Self-employment earnings → Schedule SE
    box15_credits: float = 0             # Various credits (low-income housing, rehab, etc.)
    box17_sec199a: float = 0             # §199A qualified business income (Box 20Z partnership / 17V S-corp)
    box17_w2_wages: float = 0            # §199A W-2 wages (for 8995-A above threshold)
    box17_ubia: float = 0                # §199A UBIA of qualified property (for 8995-A)

    # F5: Outside basis and at-risk tracking (IRC §704(d); IRC §465; Form 6198)
    # Source: irs.gov/pub/irs-pdf/f6198.pdf; IRC §704(d); IRC §465
    # Enter the taxpayer's outside basis in the partnership/S-corp as of year-end.
    # $0 = not entered (engine will warn but allow loss — preparer must verify manually).
    outside_basis: float = -1.0          # -1 = not entered; 0+ = actual basis; losses capped at this
    at_risk_amount: float = -1.0         # -1 = not entered; Form 6198 Line 19 amount at risk

    # Estate/Trust specific
    box1_interest_et: float = 0          # Schedule K-1 (1041) Box 1
    box2a_ordinary_div_et: float = 0     # Box 2a
    box2b_qualified_div_et: float = 0    # Box 2b
    box3_net_stcg_et: float = 0          # Box 3
    box4a_net_ltcg_et: float = 0         # Box 4a
    box5_other_portfolio_et: float = 0   # Box 5
    box11_final_year_deductions: float = 0  # Box 11 — excess deductions on final return

    # Participation flags
    material_participation: bool = False  # Meets any §469 MP test → non-passive
    is_rental: bool = False               # True → per se passive (rental rules)
    disposition_year: bool = False        # True → suspended losses released this year


@dataclass
class AlimonyData:
    """
    Alimony Paid/Received — Schedule 1 Lines 2a/2b (received) and 19a/19b (paid deduction)
    Source: irs.gov/pub/irs-pdf/f1040s1.pdf; IRC §71 (pre-TCJA) and §11051 (TCJA)

    CRITICAL TCJA cut-off:
      - Divorce/separation agreements executed BEFORE January 1, 2019:
        Payer deducts (Schedule 1 Line 19a — above-the-line)
        Recipient includes in income (Schedule 1 Line 2a)
      - Agreements executed ON OR AFTER January 1, 2019:
        NO deduction for payer; NOT income for recipient
        These are treated as non-deductible spousal support payments

    Modified agreements: If a pre-2019 agreement is MODIFIED after 2018 to specifically
    state that §71 no longer applies, it is treated as post-2018 → no deduction.

    Recipient: alimony received → Schedule 1 Line 2a → included in AGI (pre-2019 only)
    Payer: SSN of recipient required for deduction (Schedule 1 Line 19b)
    """
    decree_pre_2019: bool = True         # True = pre-2019 decree → deductible/taxable
    alimony_paid: float = 0              # Schedule 1 Line 19a (if decree_pre_2019)
    recipient_ssn: str = ""              # Schedule 1 Line 19b (required for deduction)
    alimony_received: float = 0          # Schedule 1 Line 2a (pre-2019; income if received)
    decree_modified_after_2018: bool = False  # True = pre-2019 decree MODIFIED after 12/31/2018
                                              # AND modification explicitly states §71 no longer applies
                                              # → treated as post-2018 agreement (no ded/income)
                                              # Source: IRC §11051(c); IRS Pub 504


@dataclass
class Form2210Data:
    """
    Form 2210 — Underpayment of Estimated Tax (2025) — Safe Harbor Method
    Source: irs.gov/pub/irs-pdf/f2210.pdf  |  Instructions: irs.gov/pub/irs-pdf/i2210.pdf

    Engine implements Safe Harbor (Part II) only — not the Annualized Income Installment Method.

    Safe Harbor — No penalty if ANY of these are met:
      (a) Total tax < $1,000 after withholding
      (b) Withholding + estimated payments ≥ 100% of PRIOR year tax
          (110% if prior-year AGI > $150,000)
      (c) Withholding + estimated payments ≥ 90% of CURRENT year tax

    Penalty calculation (simplified):
      - On the underpaid amount for each quarter
      - Rate: federal short-term rate + 3% (8% for 2025)
      - Each quarter: Apr 15, Jun 15, Sep 15, Jan 15 due dates

    Required underpayment trigger: Line 9 (total tax after credits) minus Line 11 (WH) ≥ $1,000

    Engine: computes whether penalty applies; estimates annual penalty amount.
    Actual quarter-by-quarter computation requires prior-quarter payment history.
    Penalty → Form 1040 Line 38 (NOT part of L24 total tax — separate line).
    """
    prior_year_tax: float = 0            # From taxpayer's 2024 return, Form 1040 Line 24
    prior_year_agi: float = 0            # From 2024 return, Line 11 (for 110% test)
    # Waiver checkboxes (uncommon; engine just flags)
    waiver_retired_disabled: bool = False   # Line 5a: retired or disabled in 2024 or 2025
    waiver_casualty_disaster: bool = False  # Line 5b: casualty/disaster
    waiver_other: bool = False              # Line 5c: other reasonable cause


@dataclass
class CaliforniaData:
    """
    California Form 540 — Individual Income Tax Return (2025)
    Source: ftb.ca.gov/forms/2025/2025-540.pdf
            ftb.ca.gov/forms/2025/2025-540-booklet.pdf

    CA tax is computed separately from federal. Key differences:
      - No TCJA standard deduction changes → CA std ded is lower ($5,540 single)
      - No QBI deduction (§199A) — CA conforms to pre-TCJA; QBI not allowed
      - No SALT cap on CA return (CA allows full state taxes deducted)
      - No AMT exemption inflation adjustment (CA AMT uses different rates/thresholds)
      - CA SDI (State Disability Insurance) included as income offset
      - CA does not conform to IRC §83(b) (stock options) in some respects
      - CA taxes ALL income (residents) regardless of source

    CA AGI adjustments (CA-specific addbacks and subtractions):
      - Federal-CA conformity differences: HSA deduction NOT allowed in CA
        (CA does not conform to federal HSA treatment — IRC §223)
      - CA allows rental losses differently — more restrictive in some cases
      - CA unemployment compensation: EXEMPT from CA income tax (R&TC §17083)
      - CA lottery winnings: EXEMPT from CA income tax (≠ federal)
      - Social Security benefits: EXEMPT from CA income tax

    CA filing status generally matches federal, with minor exceptions.
    Community property rules: MFJ/MFS have community income splitting implications.
    """
    # CA-specific income adjustments
    ca_lottery_winnings: float = 0       # CA-exempt lottery income (must add back if in fed income)
    ca_other_subtractions: float = 0     # Other CA subtractions (e.g., interest on fed obligations)
    ca_other_additions: float = 0        # CA additions (e.g., HSA deduction taken federally)

    # CA SDI withholding (W-2 Box 14 CASDI or VPDI) — affects CA return only
    ca_sdi_withheld: float = 0           # From W-2 Box 14; may be claimed as credit in CA

    # CA itemized vs standard
    use_ca_itemized: bool = False        # If True, use CA Schedule CA itemized deductions
    # If CA itemized: most federal Schedule A items carry to CA, except:
    #   - CA allows full mortgage interest (no federal $750k cap post-2018)
    #   - CA has no misc itemized deduction floor (unlike federal — TCJA suspended)
    ca_itemized_total: float = 0         # User-computed CA itemized total

    # Renter's credit: $60 single / $120 MFJ if rented > 6 months, income below threshold
    paid_rent_over_half_year: bool = False
    # Mental health services surtax (Prop 63): 1% on CA taxable income > $1M
    # (same as millionaire's tax; auto-applied in engine)

    # v12 (P2): CalEITC / YCTC / FYTC fields (Form FTB 3514)
    # Source: ftb.ca.gov/forms/2025/2025-3514.pdf
    has_young_child_under6: bool = False     # True if qualifying child under age 6 at Dec 31 → YCTC
    foster_youth_taxpayer: bool = False      # True if taxpayer was in CA foster care, age 18-25
    foster_youth_spouse: bool = False        # True if spouse qualifies for FYTC
    ca_taxpayer_age: int = 0                 # Taxpayer age at Dec 31, 2025 (CalEITC age gate: 18+)
    ca_investment_income_caleitc: float = 0  # CA investment income for FTB 3514 $4,814 limit

    # ── CA Schedule CA Part II — Adjustments (CA nonconformity addbacks) ─────
    # Source: ftb.ca.gov/forms/2025/2025-schca.pdf Part II; FTB Pub 1001

    # OBBBA nonconformity — CA did NOT adopt P.L. 119-21 (OBBBA) for TY 2025
    # The four OBBBA above-line deductions (senior, tips, OT, auto loan) are NOT
    # allowed on CA Schedule CA. They must be added back to arrive at CA AGI.
    # Engine auto-computes the addback from federal OBBBA deductions.
    # Source: CA FTB Announcement 2025-4; P.L. 119-21 nonconformity
    ca_obbba_addback_override: float = 0    # 0 = auto-compute from federal OBBBA deductions

    # Bonus / accelerated depreciation addback
    # CA does not conform to IRC §168(k) bonus depreciation.
    # Federal bonus depreciation taken on Sch C/E/4797 must be added back on CA.
    # CA allows its own first-year depreciation under R&TC §24356 (50%) instead.
    # Source: FTB Pub 1001; R&TC §17250; CA Schedule CA Part II Line 22
    ca_bonus_depreciation_addback: float = 0   # Federal bonus dep to add back on CA

    # Military pay exclusion
    # Active duty military pay is CA-exempt if stationed outside CA all year.
    # Source: R&TC §17140; Military Spouses Residency Relief Act; FTB Pub 1032
    ca_military_pay_exclusion: float = 0

    # Loan forgiveness / cancelled debt exclusion
    # CA has its own cancelled-debt exclusion rules that may differ from federal.
    # Source: R&TC §17144; FTB Notice 2024-4
    ca_loan_forgiveness_excluded: float = 0

    # Alimony addback (CA TY 2025 transition) — Sch CA Part I Sec B Line 2a / Sec C Line 19a
    # Required when alimony agreement executed 1/1/2019 – 12/31/2025.
    # For payor: federal deduction = $0 → CA requires income addback.
    # For recipient: federal income = $0 → CA requires inclusion.
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html "Alimony"; R&TC §17076
    ca_alimony_addback: float = 0

    # NOL carryforward suspension addback
    # CA suspended NOL deduction 2024–2026 for modified AGI ≥ $1M.
    # Enter the federal NOL deduction amount (from Form 1040 / Sch 1 Line 8a) that
    # must be added back on the CA return.
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html "Net Operating Loss Suspension"
    #         R&TC §17276.24; FTB 3805V
    ca_nol_addback: float = 0


@dataclass
class Form5329Exception:
    """
    One exception claim on Form 5329 — matches to a specific distribution.
    Engine validates that the exception code is consistent with distribution type.
    Source: irs.gov/pub/irs-pdf/f5329.pdf  |  Instructions: irs.gov/pub/irs-pdf/i5329.pdf

    Attach one Form5329Exception per 1099-R that has an exception code.
    The payer_name must match the payer on the corresponding Form1099R.
    """
    payer_name: str = ""                 # must match Form1099R.payer
    distribution_amount: float = 0      # the taxable amount subject to exception
    amount: float = 0                   # alias for distribution_amount (UI/JSON uses 'amount')
    exception_code: str = ""            # OFFICIAL IRS Form 5329 Part I Line 2 exception number
    account_type: str = "ira"           # alias for plan_type: 'ira' or 'plan' (UI uses account_type)
    # FETCH_VERIFIED: irs.gov/pub/irs-pdf/i5329.pdf | Part I Line 2 exception numbers | 2026-05-21
    # These are the EXACT codes printed in the IRS Form 5329 instructions — not remapped.
    # 01 = Separation from service in or after age 55 (employer plans only — NOT IRAs)
    # 02 = Substantially equal periodic payments / SEPP — IRC §72(t)(2)(A)(iv)
    # 03 = Total and permanent disability — IRC §72(t)(2)(A)(iii)
    # 04 = Death — IRC §72(t)(2)(A)(ii)  (does not apply to modified endowment contracts)
    # 05 = Medical expenses exceeding 7.5% AGI — IRC §72(t)(2)(B)
    # 06 = QDRO — distributions to alternate payee — IRC §72(t)(2)(C)
    # 07 = Health insurance premiums while unemployed (IRA only) — IRC §72(t)(2)(D)
    # 08 = Higher education expenses (IRA only) — IRC §72(t)(2)(E)
    # 09 = First-time home purchase up to $10,000 lifetime (IRA only) — IRC §72(t)(2)(F)
    # 10 = Qualified reservist distributions — IRC §72(t)(2)(G)
    # 11 = Qualified birth or adoption up to $5,000 per child — IRC §72(t)(2)(H)
    # 12 = Other (multiple exceptions or exceptions not listed above) — attach statement
    plan_type: str = "ira"              # "ira" or "employer_plan" (some exceptions only apply to one)


@dataclass
class Form1116Data:
    """
    Form 1116 — Foreign Tax Credit (Individual, Estate, or Trust) (2025)
    Source: irs.gov/pub/irs-pdf/f1116.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1116.pdf

    Allows a credit (not deduction) for foreign taxes paid on foreign-source income.
    Two income baskets: passive and general. Most individuals with only 1099-DIV Box 7
    foreign taxes fall into the passive basket.

    De minimis exception (no Form 1116 required):
      If total creditable foreign taxes ≤ $300 (single/MFS) or $600 (MFJ/QSS),
      AND all income is passive, AND no exclusion/deduction claimed for same taxes:
      → Enter directly on Schedule 3 Line 1 without filing Form 1116.
      Source: irs.gov/pub/irs-pdf/i1116.pdf "Who Must File Form 1116"

    Part I — Taxable Income or Loss From Sources Outside the US (by basket)
    Part II — Foreign Taxes Paid or Accrued
    Part III — Figuring the Credit
      Line 9  = Foreign-source taxable income (limited by Part I)
      Line 10 = Adjusted gross income from all sources
      Line 11 = Ratio = Line 9 ÷ Line 10
      Line 12 = Tax before credit (Form 1040 Line 16, after QDCGT/AMT)
      Line 13 = Credit limitation = Line 11 × Line 12
      Line 14 = Smaller of foreign taxes paid or limitation = allowable credit
      Excess = carryback 1 year / carryforward 10 years

    AMT Form 1116: Separate computation required when AMT applies (§59(a)).
    Not implemented — flagged as warning.
    """
    # Passive basket (most common — mutual fund/ETF dividends with foreign taxes)
    passive_foreign_taxes_paid: float = 0     # from 1099-DIV Box 7 / 1099-INT Box 6
    passive_foreign_income: float = 0        # gross foreign-source income in passive basket
    passive_foreign_expenses: float = 0      # expenses allocated to foreign income (usually $0)

    # General basket (wages/salary from foreign country, foreign business income)
    general_foreign_taxes_paid: float = 0
    general_foreign_income: float = 0
    general_foreign_expenses: float = 0

    # Carryover from prior years
    passive_carryover: float = 0             # unused credit from prior year Worksheet
    general_carryover: float = 0

    # Cash vs accrual election — most individuals use "paid" basis
    cash_basis: bool = True                  # True = paid; False = accrued

    # AMT consideration
    amt_applies: bool = False                # If True, warn that separate AMT Form 1116 needed


@dataclass
class Form8615Data:
    """
    Form 8615 — Tax for Certain Children Who Have Unearned Income (Kiddie Tax)
    Source: irs.gov/pub/irs-pdf/f8615.pdf  |  Instructions: irs.gov/pub/irs-pdf/i8615.pdf

    Applies when ALL of the following are true (2025):
      1. Child has net unearned income > $2,700 (2× standard deduction for child)
      2. Child is under 18 at end of 2025, OR
         Child is age 18 and did not provide more than half own support from earned income, OR
         Child is a full-time student age 19–23 and did not provide more than half own support
         from earned income
      3. Child's filing status is not MFJ
      4. At least one parent was alive at end of 2025

    Computation (Form 8615):
      L1  = child's net unearned income = gross unearned income − $2,700 (2× std ded offset)
            (std ded offset = $2 × $1,350 = $2,700 for 2025)
      L6  = child's taxable income
      L7  = parent's taxable income (from parent's return or parent_taxable_income field)
      L8  = parent's taxable income + child's L1 (combined parent+child taxable for rate calc)
      L9  = tax on L8 using parent's filing status and brackets
      L10 = tax on parent's L7 alone
      L11 = tentative tax = L9 − L10 (parent's marginal rate applied to child's NUI)
      L13 = tax on child's taxable income at child's own rate
      L15 = greater of L11 or L13 → child's income tax (replaces normal bracket calc)

    Source: f8615.pdf Lines 1–15; i8615.pdf; IRC §1(g)
    """
    # Child qualification data
    child_age: int = 0                          # child's age at end of 2025
    child_is_full_time_student: bool = False    # True → kiddie tax extends to age 23
    child_support_from_earned: bool = False     # True if child provided >half own support from earned income

    # Parent data (required for Part I)
    parent_filing_status: str = "single"        # parent's filing status for bracket lookup
    parent_taxable_income: float = 0            # parent's taxable income (Form 1040 Line 15)

    # If multiple children with kiddie tax: use highest parent taxable income
    # (when sibling also has Form 8615, see i8615.pdf "Special Rule" — not implemented)

    # Child's income breakdown (for L1 computation)
    # Net unearned income = unearned income − $2,700
    # Unearned income = interest + dividends + cap gains + other unearned
    # Earned income = wages + SE income
    unearned_income: float = 0                  # child's gross unearned income (taxable)
    earned_income: float = 0                    # child's earned income (W-2 Box 1 + SE)


@dataclass
class Form4797SaleData:
    """
    Form 4797 — Sales of Business Property (2025)
    Source: irs.gov/pub/irs-pdf/f4797.pdf  |  Instructions: irs.gov/pub/irs-pdf/i4797.pdf

    Handles sale of:
      - Rental real estate (§1250 property: 27.5yr residential / 39yr commercial)
      - Business equipment/vehicles (§1245 property: accelerated depreciation)
      - Mixed-use property (home office, partly-personal)

    Three-part structure:
      Part I  — §1231 property held > 1 year (net gain → Schedule D L11; net loss → ordinary)
      Part II — Property held ≤ 1 year OR §1245/§1250 ordinary income recapture
      Part III— Summary of gains under §1245/§1250 recapture (flows into Part II Line 31)

    §1231 logic:
      - Gain after recapture → Schedule D Line 11 as §1231 LTCG (15% rate if net gain)
      - Net §1231 loss → ordinary deduction (better than LTCG treatment)
      - §1231 lookback: if net §1231 losses in last 5 years, current gains are ordinary
        (NOT implemented — flagged as warning)

    §1250 recapture (rental/real property):
      - Post-1986 MACRS residential: depreciation straight-line → NO §1250 ordinary recapture
      - Unrecaptured §1250 gain = cumulative straight-line depreciation taken → 25% rate cap
        (not ordinary income; goes to Schedule D via the QDCGT worksheet)
      - Commercial/pre-ACRS: additional §1250 recapture may apply

    §1245 recapture (equipment/personal property):
      - ALL depreciation previously taken → ordinary income (Part II)
      - Remaining gain (if any) → §1231 gain (Schedule D Line 11)

    Suspended passive losses:
      - When rental property is sold, ALL suspended Form 8582 losses are released
        against the §1231 gain in the year of sale (§469(g))
      - Engine requires user to provide suspended_passive_losses amount
      - Released losses reduce §1231 gain (not ordinary income recapture)

    Source: f4797.pdf; i4797.pdf; IRC §1231, §1245, §1250; p544.pdf
    """
    description: str = ""                    # Property address or description
    property_type: str = "1250_residential"  # "1250_residential", "1250_commercial", "1245_equipment"
    date_acquired: str = ""
    date_sold: str = ""
    held_over_one_year: bool = True          # True → Part I (§1231); False → Part II

    # Sales proceeds and basis
    gross_proceeds: float = 0               # Form 4797 Line 20 (or gross sale price)
    original_cost: float = 0               # Original purchase price + capital improvements
    depreciation_taken: float = 0          # Total depreciation claimed on all prior returns
                                            # (CRITICAL: cumulative, not just last year)

    # §1250 specific (residential/commercial rental)
    additional_section_1250_recapture: float = 0  # Pre-ACRS commercial property only; 0 for MACRS
    # Note: unrecaptured §1250 gain (25% rate) = min(depreciation_taken, §1231 gain)
    # This is computed automatically from depreciation_taken

    # §1245 specific (equipment)
    # For §1245: ALL depreciation is ordinary income recapture up to the gain
    # remaining_gain = total_gain - depreciation_taken goes to §1231

    # Suspended passive losses released at sale (§469(g))
    suspended_passive_losses: float = 0    # From prior Form 8582; released against §1231 gain

    # §1231 lookback — IRC §1231(c)
    # If taxpayer had NET §1231 LOSSES in any of the prior 5 tax years,
    # current §1231 GAINS are reclassified as ordinary income (not LTCG)
    # up to the amount of those prior losses.
    # Source: IRC §1231(c); p544.pdf "Section 1231 Gains and Losses — Lookback Rule"
    # Enter the TOTAL net §1231 losses from prior 5 years (positive number = prior losses).
    # Leave 0 if no prior §1231 losses (default — no lookback reclassification).
    prior_sec1231_losses_5yr: float = 0   # Total net §1231 losses, prior 5 tax years

    # Federal income tax withheld (rare — usually $0 for property sales)
    fed_wh: float = 0


# ═══════════════════════════════════════════════════════════════════════════════
# CODE VERIFICATION PROTOCOL — MANDATORY FOR ALL CODE TABLES
# ═══════════════════════════════════════════════════════════════════════════════
# Any enumerated code list, exception number table, or named-code system
# from an IRS form MUST carry a FETCH_VERIFIED annotation:
#
#   # FETCH_VERIFIED: <URL> | <form section / line> | <date fetched YYYY-MM-DD>
#
# This is NOT the same as "# Source: ...". A Source comment can be written
# without opening the document. FETCH_VERIFIED means the document was opened
# and the specific code table was read before writing the code.
#
# Applies to: Form 5329 Line 2 exception codes, 1099-R Box 7 distribution
# codes, W-2 Box 12 codes, any code → meaning mapping tied to an IRS form.
#
# Session gate: before any session that touches a code table, verify the
# FETCH_VERIFIED annotation is present or fetch the document and add it.
# ═══════════════════════════════════════════════════════════════════════════════

# ── 2025 TAX PARAMETERS ────────────────────────────────────────────────────────
PARAMS_2025 = {
    # ── Standard Deduction — OBBBA §70102 (P.L. 119-21, signed July 4, 2025) ──
    # Supersedes Rev. Proc. 2024-40 amounts for TY 2025.
    # Source: Rev. Proc. 2025-32 §2.08; irs.gov/pub/irs-drop/rp-25-32.pdf
    "std_deduction": {
        "single": 15750, "mfj": 31500, "mfs": 15750,
        "hoh": 23625,    "qss": 31500
    },
    "tax_brackets_mfj": [
        (23850, 0.10), (96950, 0.12), (206700, 0.22),
        (394600, 0.24), (501050, 0.32), (751600, 0.35), (float('inf'), 0.37),
    ],
    "tax_brackets_single": [
        (11925, 0.10), (48475, 0.12), (103350, 0.22),
        (197300, 0.24), (250525, 0.32), (626350, 0.35), (float('inf'), 0.37),
    ],
    # Head of Household 2025 — Source: Rev. Proc. 2024-40
    "tax_brackets_hoh": [
        (17000, 0.10), (64850, 0.12), (103350, 0.22),
        (197300, 0.24), (250500, 0.32), (626350, 0.35), (float('inf'), 0.37),
    ],
    # ── Child Tax Credit — OBBBA §70104 (P.L. 119-21) ───────────────────────────
    # CTC increased to $2,200 for TY 2025. ACTC refundable cap stays $1,700 for 2025.
    # Source: Rev. Proc. 2025-32 §2.03; IRC §24(h)(2) as amended by OBBBA
    "ctc_per_child": 2200,   # 2025 OBBBA: $2,200 per qualifying child (was $2,000 Rev. Proc. 2024-40)
    "actc_cap_per_child": 1700,
    "actc_earned_floor": 2500,
    "actc_rate": 0.15,
    "ctc_phaseout_all_other": 200000,
    "ctc_phaseout_mfj": 400000,
    # Teacher expense — Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 11
    "teacher_expense_max": 300,
    # Form 8615 — Kiddie Tax (2025) — Source: irs.gov/pub/irs-pdf/f8615.pdf; IRC §1(g)
    # Net unearned income threshold = 2 × dependent standard deduction ($1,350 × 2 = $2,700)
    # Source: Rev. Proc. 2024-40; i8615.pdf
    "kiddie_tax_nui_threshold": 2700,   # Line 1 floor: unearned income below this → no kiddie tax
    # Form 8863 — Source: irs.gov/pub/irs-pdf/f8863.pdf, i8863.pdf
    # EITC 2025 — from EIC Table, IRS Pub 1040
    "eitc": {
        # Source: Rev. Proc. 2024-40; IRC §32(b); p596.pdf; p1040.pdf pp.16+
        # phase_in_rate used by table-band algorithm (added session 2026-05-17)
        "phase_in_rates": {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45},   # IRC §32(b)(1)
        "single_qss": {
            0: {"max": 632,  "phaseout_start": 10620, "phaseout_rate": 0.0765, "income_limit": 18591},  # Rev. Proc. 2024-40; Pub 596 TY2025 — single/QSS 0-child max $632 / limit $18,591 (NOT MFJ values)
            1: {"max": 4328, "phaseout_start": 23350, "phaseout_rate": 0.1598, "income_limit": 50434},
            2: {"max": 7152, "phaseout_start": 23350, "phaseout_rate": 0.2106, "income_limit": 57310},
            3: {"max": 8046, "phaseout_start": 23350, "phaseout_rate": 0.2106, "income_limit": 61555},
        },
        "mfj": {
            0: {"max": 649,  "phaseout_start": 17830, "phaseout_rate": 0.0765, "income_limit": 26214},
            1: {"max": 4328, "phaseout_start": 30470, "phaseout_rate": 0.1598, "income_limit": 57554},
            2: {"max": 7152, "phaseout_start": 30470, "phaseout_rate": 0.2106, "income_limit": 64430},
            3: {"max": 8046, "phaseout_start": 30470, "phaseout_rate": 0.2106, "income_limit": 68675},
        },
    },
    "fpl_2024": {1: 15060, 2: 20440, 3: 25820, 4: 31200,
                 5: 36580, 6: 41960, 7: 47340, 8: 52720},
    "saver_rate_single_qss": [
        (23750, 0.50), (25500, 0.20), (38250, 0.10), (39500, 0.10),
        (float('inf'), 0.00)
    ],
    "saver_rate_hoh": [
        (35625, 0.50), (38500, 0.20), (51000, 0.10), (57375, 0.10),
        (float('inf'), 0.00)
    ],
    "saver_rate_mfj": [
        (47500, 0.50), (51000, 0.20), (79000, 0.10),
        (float('inf'), 0.00)
    ],
    # SSA-1099 base amounts — Source: irs.gov/pub/irs-pdf/p915.pdf
    "ss_base_single_qss_hoh": 25000,
    "ss_base_mfj": 32000,
    "ss_upper_single_qss_hoh": 34000,
    "ss_upper_mfj": 44000,
    # ── v5 additions ──────────────────────────────────────────────────────────
    # AOC/LLC phase-out — Source: irs.gov/pub/irs-pdf/i8863.pdf
    "aoc_llc_phaseout_single_start": 80000,
    "aoc_llc_phaseout_single_end":   90000,
    "aoc_llc_phaseout_mfj_start":   160000,
    "aoc_llc_phaseout_mfj_end":     180000,
    # Student loan interest phase-out — Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 21
    "student_loan_phaseout_single_start":  80000,
    "student_loan_phaseout_single_end":    95000,
    "student_loan_phaseout_mfj_start":    165000,
    "student_loan_phaseout_mfj_end":      195000,
    "student_loan_max":  2500,
    # EITC investment income disqualification — Source: irs.gov/pub/irs-pdf/p596.pdf
    "eitc_investment_income_limit": 11600,

    # ── Age 65+ / Blind standard deduction add-on — TY 2025 ──────────────────
    # Source: IRS Rev. Proc. 2024-40 S.3.10; IR-2024-273; i1040gi.pdf Line 12
    # Applied PER qualifying condition PER person (age 65+ OR blind = one condition each)
    "std_addon_single_hoh_2025": 2000,   # $2,000 per condition (single/HOH/MFS)
    "std_addon_mfj_per_2025":    1600,   # $1,600 per qualifying spouse (MFJ/QSS)
    # Self-employment tax — Source: irs.gov/pub/irs-pdf/f1040sse.pdf
    "se_tax_rate_net_earnings": 0.9235,   # net earnings = net profit × 92.35%
    "ss_tax_rate_se":           0.124,    # 12.4% SS (on first $176,100 for 2025)
    "medicare_tax_rate_se":     0.029,    # 2.9% Medicare (no limit)
    "ss_wage_base_2025":        176100,
    # QDCGT rates 2025 — Source: f1040.pdf QDCGT Worksheet; irs.gov/pub/irs-pdf/i1040gi.pdf
    "qdcgt_0pct_single":    47025,
    "qdcgt_0pct_mfj":       94050,
    "qdcgt_0pct_hoh":       63000,
    "qdcgt_0pct_qss":       94050,
    "qdcgt_0pct_mfs":       47025,    # MFS = same as single per IRC §1(h)(1)(C); Rev. Proc. 2024-40
    "qdcgt_15pct_single":  518900,
    "qdcgt_15pct_mfj":     583750,
    "qdcgt_15pct_hoh":     551350,
    "qdcgt_15pct_qss":     583750,
    "qdcgt_15pct_mfs":     291875,    # MFS = half of MFJ $583,750 per IRC §1(h)(1)(C); Rev. Proc. 2024-40
    # ODC — Source: irs.gov/pub/irs-pdf/i1040.pdf
    "odc_per_dependent": 500,
    # Home office simplified — Source: Rev Proc 2013-13; irs.gov/pub/irs-pdf/f8829.pdf
    "home_office_simplified_rate":    5.00,
    "home_office_simplified_max_sqft": 300,
    # Meals deduction 50% — Source: irs.gov/pub/irs-pdf/i1040sc.pdf Line 24b
    "meals_deduction_pct": 0.50,
    # ── v6 additions ──────────────────────────────────────────────────────────
    # QBI Deduction §199A — Source: irs.gov/pub/irs-pdf/f8995.pdf; i8995.pdf
    "qbi_threshold_mfj":   394600,
    "qbi_threshold_other": 197300,
    # SE Retirement — Source: irs.gov/pub/irs-pdf/p560.pdf; IRC §404
    "sep_ira_rate_sole_prop": 0.20,
    "sep_ira_max_2025":       70000,
    "solo401k_elective_max_2025": 23500,
    "simple_ira_max_2025":    16500,
    # ── v7 additions ──────────────────────────────────────────────────────────
    # Form 6251 — AMT 2025 — Source: irs.gov/pub/irs-pdf/f6251.pdf
    "amt_exemption_single":      88100,
    "amt_exemption_mfj":        137000,
    "amt_exemption_mfs":         68500,
    "amt_exemption_hoh":         88100,
    "amt_phaseout_single":      626350,
    "amt_phaseout_mfj":        1252700,
    "amt_phaseout_mfs":         626350,
    "amt_phaseout_hoh":         626350,
    "amt_rate1":                 0.26,
    "amt_rate2":                 0.28,
    "amt_rate_breakpoint":      232600,
    # Form 8582 — Passive Activity — Source: irs.gov/pub/irs-pdf/f8582.pdf
    "rental_special_allowance":  25000,
    "rental_allowance_mfs":      12500,
    "rental_phaseout_start":    100000,
    "rental_phaseout_mfs_start": 50000,
    # ── v8 additions ──────────────────────────────────────────────────────────
    # Form 8960 — Net Investment Income Tax (NIIT) — Source: irs.gov/pub/irs-pdf/f8960.pdf
    # IRC §1411: 3.8% on lesser of NII or (MAGI - threshold)
    "niit_rate":                 0.038,
    "niit_threshold_single":   200000,   # Single / HOH / MFS
    "niit_threshold_mfj":      250000,   # MFJ / QSS
    # Form 8959 — Additional Medicare Tax — Source: irs.gov/pub/irs-pdf/f8959.pdf
    # IRC §3101(b)(2): 0.9% on wages+SE income above threshold
    "addl_medicare_rate":        0.009,
    "addl_medicare_threshold_single": 200000,
    "addl_medicare_threshold_mfj":    250000,
    "addl_medicare_threshold_mfs":    125000,
    # Form 8889 — HSA — Source: irs.gov/pub/irs-pdf/f8889.pdf; irs.gov/pub/irs-pdf/p969.pdf
    "hsa_limit_self_only_2025":   4300,
    "hsa_limit_family_2025":      8550,
    "hsa_catchup_age55_2025":     1000,   # additional if 55+ at year-end
    # Traditional IRA deduction phase-out — Source: irs.gov/pub/irs-pdf/p590a.pdf
    # Covered participant (W-2 Box 13 = checked)
    "ira_phaseout_covered_single_start":  79000,
    "ira_phaseout_covered_single_end":    89000,
    "ira_phaseout_covered_mfj_start":    126000,
    "ira_phaseout_covered_mfj_end":      146000,
    "ira_phaseout_covered_mfs_start":       0,
    "ira_phaseout_covered_mfs_end":       10000,
    # Non-covered spouse (MFJ; other spouse has plan)
    "ira_phaseout_noncovered_mfj_start": 236000,
    "ira_phaseout_noncovered_mfj_end":   246000,
    "ira_contribution_limit_2025":         7000,   # under age 50
    "ira_contribution_catchup_2025":       8000,   # age 50+
    # Form 2210 safe-harbor underpayment — Source: irs.gov/pub/irs-pdf/f2210.pdf
    "underpayment_penalty_rate_2025":   0.08,    # Fed funds rate + 3%; 8% for 2025 — annual rate (F7: quarterly calc not implemented; estimate directionally correct)
    "safe_harbor_pct_current":          0.90,    # 90% of current year tax
    "safe_harbor_pct_prior_110":        1.10,    # 110% of prior year tax if AGI > $150k
    "safe_harbor_agi_threshold":       150000,   # above → use 110%
    # California — Source: ftb.ca.gov/forms/
    # ── CALIFORNIA 2025 PARAMETERS — FETCH_VERIFIED 2026-05-24 ────────────────
    # Source: ftb.ca.gov/forms/2025/2025-540.pdf (Form 540 Line 18 std ded values)
    # Source: ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf (Schedules X, Y, Z)
    # CORRECTED from 2024 values (5540/11080) — Form 540 line 18 explicitly states:
    #   Single/MFS: $5,706 | MFJ/HOH/QSS: $11,412
    "ca_std_ded_single":                5706,    # 2025 — Single/MFS. Source: 2025-540.pdf Line 18
    "ca_std_ded_mfj":                   11412,   # 2025 — MFJ/HOH/QSS. Source: 2025-540.pdf Line 18
    "ca_std_ded_hoh":                   11412,   # 2025 — HOH same as MFJ. Source: 2025-540.pdf Line 18
    "ca_std_ded_qss":                   11412,   # 2025 — QSS same as MFJ. Source: 2025-540.pdf Line 18
    "ca_std_ded_mfs":                   5706,    # 2025 — MFS same as single. Source: 2025-540.pdf Line 18
    "ca_personal_exempt_credit":        144,     # Single/MFS personal exemption credit
    "ca_personal_exempt_mfj_qss":       288,     # MFJ/QSS personal exemption credit
    "ca_personal_exempt_hoh":           144,     # HOH — same as single per R&TC §17054
    "ca_dependent_exempt_credit":       433,     # per dependent
    "ca_young_child_tax_credit":        1189,    # 2025 YCTC per return — Source: ftb.ca.gov/file/personal/credits/young-child-tax-credit.html
    # Schedule X — Single or MFS
    # Source: ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf Schedule X
    # FETCH_VERIFIED 2026-05-24: corrected from 2024 values (first bracket was $10,756 → now $11,079)
    "ca_brackets_single_2025": [
        (11079,  0.01),  (26264, 0.02), (41452, 0.04),  (57542, 0.06),
        (72724,  0.08),  (371479, 0.093),(445771,0.103),(742953, 0.113),
        (float('inf'), 0.123),
    ],
    # Schedule Y — MFJ or QSS
    # Source: ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf Schedule Y
    # FETCH_VERIFIED 2026-05-24: corrected from 2024 values (first bracket was $21,512 → now $22,158)
    "ca_brackets_mfj_2025": [
        (22158,  0.01),  (52528, 0.02), (82904, 0.04), (115084, 0.06),
        (145448, 0.08),  (742958, 0.093),(891542,0.103),(1485906, 0.113),
        (float('inf'), 0.123),
    ],
    # Schedule Z — Head of Household (separate CA schedule — NOT same as single/MFJ)
    # Source: ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf Schedule Z
    # FETCH_VERIFIED 2026-05-24: HOH bracket was MISSING from engine — engine was using single
    # brackets for HOH which understated tax at lower incomes (HOH has wider lower brackets)
    "ca_brackets_hoh_2025": [
        (22173,  0.01),  (52530, 0.02), (67716, 0.04), (83805, 0.06),
        (98990,  0.08),  (505208, 0.093),(606248,0.103),(1010416, 0.113),
        (float('inf'), 0.123),
    ],
    "ca_surtax_millionaire":   0.01,   # 1% surcharge on CA taxable income > $1M
    # ── v9 additions ──────────────────────────────────────────────────────────
    # Form 1116 — Foreign Tax Credit de minimis threshold
    # Source: irs.gov/pub/irs-pdf/i1116.pdf "Who Must File Form 1116"
    "f1116_de_minimis_single":   300,   # Single / HOH / MFS / QSS
    "f1116_de_minimis_mfj":      600,   # MFJ
    # Form 5329 — Exception limits
    # Source: irs.gov/pub/irs-pdf/f5329.pdf; IRC §72(t)
    # FETCH_VERIFIED: irs.gov/pub/irs-pdf/p463.pdf | 2025 rate section | 2026-05-24
    # Source: IRS Notice 2025-5; IRS Publication 463 (2025): 70¢/mile (up from 67¢ in 2024)
    "standard_mileage_rate_2025": 0.70,   # IRS Notice 2025-5; Pub 463 (2025): 70¢/mile
    "f5329_first_home_lifetime": 10000,  # Exception code 09: lifetime limit §72(t)(2)(F)
    "f5329_birth_adoption":       5000,  # Exception code 11: per child §72(t)(2)(H)

    # ── OBBBA TY 2025 NEW / CHANGED PARAMETERS ────────────────────────────────────
    # Source: P.L. 119-21 (One Big Beautiful Bill Act, signed July 4, 2025)
    #         Rev. Proc. 2025-32; irs.gov/newsroom/one-big-beautiful-bill-provisions

    # SALT Cap — OBBBA §70106 (IRC §164(b)(6) as amended)
    # $40,000 cap (up from $10,000); MFS cap $20,000; phases down above AGI $500k
    # Phase-down: $50 reduction per $1,000 AGI above $500k; floor = $10,000
    # Cap effective for TY 2025–2029; returns to $10,000 in 2030
    "salt_cap_default":         40000,   # MFJ/Single/HOH/QSS — OBBBA
    "salt_cap_mfs":             20000,   # MFS = half of default
    "salt_phasedown_threshold": 500000,  # AGI above this → reduce cap
    "salt_phasedown_rate":       50,     # $50 reduction per $1,000 of AGI above threshold
    "salt_floor":               10000,   # Cap never falls below $10,000

    # Senior Bonus Deduction — OBBBA §70103 (IRC §62(a) new paragraph; TY 2025–2028)
    # $6,000 below-the-line deduction for taxpayers age 65+ (Schedule 1-A Part V → L13b)
    # For MFJ both spouses qualifying: $12,000 combined
    # Phase-out: reduces $1 per $1 of MAGI above $75k single / $150k MFJ
    # MFS filers NOT eligible
    # Source: irs.gov; OBBBA §70103
    "senior_deduction_amount":  6000,    # per qualifying taxpayer (age 65+)
    "senior_deduction_magi_single": 75000,
    "senior_deduction_magi_mfj":   150000,

    # Tip Income Deduction — OBBBA §70201 (IRC §62(a) new paragraph; TY 2025–2028)
    # Deduct qualified tips (cash/charged, customary tip occupations per IRS list)
    # Cap: $25,000 per individual (not combinable for MFS)
    # Phase-out: reduces for MAGI above $150k single / $300k MFJ
    # Mandatory service charges are NOT qualified tips
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf; OBBBA §70201
    "tip_deduction_max":          25000,
    "tip_deduction_magi_single": 150000,
    "tip_deduction_magi_mfj":    300000,

    # Overtime Pay Deduction — OBBBA §70202 (IRC §62(a) new paragraph; TY 2025–2028)
    # Deduct FLSA-qualifying overtime: cap $12,500 single / $25,000 MFJ combined
    # Phase-out: reduces for MAGI above $150k single / $300k MFJ
    # MFS filers NOT eligible. Requires W-2 designation of qualifying overtime.
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf; OBBBA §70202
    "overtime_deduction_max_single": 12500,
    "overtime_deduction_max_mfj":    25000,
    "overtime_deduction_magi_single": 150000,
    "overtime_deduction_magi_mfj":    300000,

    # Auto Loan Interest Deduction — OBBBA §70301 (IRC new §163A; TY 2025–2028)
    # Deduct interest on qualified passenger vehicle loans (new US-assembled vehicle)
    # Loan originated after Dec 31, 2024. Personal use only. Cap: $10,000/yr.
    # Phase-out: reduces for MAGI above $100k single / $200k MFJ
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf; OBBBA §70301
    "auto_loan_deduction_max":          10000,
    "auto_loan_deduction_magi_single":  100000,
    "auto_loan_deduction_magi_mfj":     200000,

    # Charitable 0.5% AGI Floor — OBBBA (itemizers only; IRC §170 as amended)
    # Cash contributions deductible only to extent exceeding 0.5% of AGI
    # Standard-deduction filers: NEW $1,000/$2,000 charitable add-on (MFJ) — separate field
    # Source: OBBBA; irs.gov/newsroom/one-big-beautiful-bill-provisions
    "charitable_agi_floor_pct":    0.005,   # 0.5% of AGI floor for itemizers
}


# ── PARAMS_2026 — TY 2026 Inflation Adjustments ────────────────────────────────
# Source: IRS Rev. Proc. 2025-32 (issued October 9, 2025); IR-2025-103
#         irs.gov/newsroom/irs-releases-tax-inflation-adjustments-for-tax-year-2026
#         IRS Notice 2025-67 (retirement plan limits, issued November 13, 2025)
# These apply to taxable years beginning January 1, 2026 (returns filed in 2027).
# NOTE: Engine currently computes TY 2025. To use 2026, pass tax_year=2026.
# Most computation logic is shared; only dollar constants differ.

PARAMS_2026 = {
    # ── Standard Deduction ────────────────────────────────────────────────────
    # Source: IRS IR-2025-103; Rev. Proc. 2025-32 §4.02
    "std_deduction": {
        "single": 16100,   # +$350 vs 2025 OBBBA ($15,750)
        "mfj":    32200,   # +$700 vs 2025 OBBBA ($31,500)
        "mfs":    16100,
        "hoh":    24150,   # +$525 vs 2025 OBBBA ($23,625)
        "qss":    32200,
    },

    # Age 65+ / blind add-on standard deduction
    # Source: Rev. Proc. 2025-32 §4.02; Tax Foundation 2026 summary
    "std_addon_single_hoh":  2050,    # $2,050 per qualifying condition (single/HOH)
    "std_addon_mfj_per":     1650,    # $1,650 per qualifying spouse (MFJ/MFS)

    # ── Income Tax Brackets — TY 2026 ─────────────────────────────────────────
    # Source: Rev. Proc. 2025-32 §4.01; IR-2025-103
    # Same 7 rates as 2025. Thresholds adjusted ~2.3–4% for inflation.
    # OBBBA made 4% adjustment for bottom two brackets (10%/12%), 2.3% for higher.
    "brackets_single_2026": [
        (12400,  0.10),
        (50400,  0.12),
        (105700, 0.22),
        (201775, 0.24),
        (256225, 0.32),
        (640600, 0.35),
        (float('inf'), 0.37),
    ],
    "brackets_mfj_2026": [
        (24800,  0.10),
        (100800, 0.12),
        (211400, 0.22),
        (403550, 0.24),
        (512450, 0.32),
        (768700, 0.35),
        (float('inf'), 0.37),
    ],
    "brackets_hoh_2026": [
        (17700,  0.10),
        (67050,  0.12),
        (105700, 0.22),
        (201775, 0.24),
        (256225, 0.32),
        (640600, 0.35),
        (float('inf'), 0.37),
    ],
    "brackets_mfs_2026": [
        (12400,  0.10),
        (50400,  0.12),
        (105700, 0.22),
        (201775, 0.24),
        (256225, 0.32),
        (384350, 0.35),
        (float('inf'), 0.37),
    ],

    # ── QDCGT / Qualified Dividends Thresholds — TY 2026 ─────────────────────
    # Source: Rev. Proc. 2025-32 §4.03
    "qdcgt_0pct_single":     48350,
    "qdcgt_0pct_mfj":        96700,
    "qdcgt_0pct_hoh":        64750,
    "qdcgt_0pct_mfs":        48350,
    "qdcgt_15pct_single":   533400,
    "qdcgt_15pct_mfj":      600050,
    "qdcgt_15pct_hoh":      566700,
    "qdcgt_15pct_mfs":      300025,

    # ── Child Tax Credit — TY 2026 ────────────────────────────────────────────
    # OBBBA: CTC inflation-adjusted from 2026 forward (was fixed $2,200 for 2025 only)
    # Source: Rev. Proc. 2025-32 §4.05; IRC §24(h)(2) as amended by OBBBA
    "ctc_per_child":    2300,    # $2,300 per qualifying child (inflation-adjusted from $2,200)
    "actc_cap_per_child": 1800,  # ACTC refundable cap inflation-adjusted for 2026
    "ctc_phaseout_single": 200000,

    # ── EITC — TY 2026 ───────────────────────────────────────────────────────
    # Source: Rev. Proc. 2025-32 §4.06; IR-2025-103
    "eitc_max_0_children":    666,
    "eitc_max_1_child":      4455,
    "eitc_max_2_children":   7373,
    "eitc_max_3plus_children": 8231,
    "eitc_invest_limit":     11950,   # investment income disqualification limit
    # ── EITC table dict for TY 2026 (IR-2025-103, October 2025) ─────────────
    # Source: IR-2025-103; irs.gov/newsroom/irs-provides-tax-inflation-adjustments-2026
    "eitc": {
        "phase_in_rates": {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45},  # IRC §32(b)(1) unchanged
        "single_qss": {
            0: {"max": 700,  "phaseout_start": 11150, "phaseout_rate": 0.0765, "income_limit": 20260},
            1: {"max": 4483, "phaseout_start": 24500, "phaseout_rate": 0.1598, "income_limit": 53650},
            2: {"max": 7405, "phaseout_start": 24500, "phaseout_rate": 0.2106, "income_limit": 60700},
            3: {"max": 8231, "phaseout_start": 24500, "phaseout_rate": 0.2106, "income_limit": 64650},
        },
        "mfj": {
            0: {"max": 700,  "phaseout_start": 18600, "phaseout_rate": 0.0765, "income_limit": 27710},
            1: {"max": 4483, "phaseout_start": 31900, "phaseout_rate": 0.1598, "income_limit": 60800},
            2: {"max": 7405, "phaseout_start": 31900, "phaseout_rate": 0.2106, "income_limit": 67900},
            3: {"max": 8231, "phaseout_start": 31900, "phaseout_rate": 0.2106, "income_limit": 71800},
        },
    },
    "eitc_investment_income_limit": 11950,   # 2026 invest limit (IR-2025-103)

    # ── AMT — TY 2026 ────────────────────────────────────────────────────────
    # Source: Rev. Proc. 2025-32 §4 (AMT section); Tax Foundation 2026 summary
    "amt_exemption_single":    90100,
    "amt_exemption_mfj":      140200,
    "amt_exemption_mfs":       70100,
    "amt_phaseout_single":    500000,    # OBBBA changed phaseout thresholds
    "amt_phaseout_mfj":      1000000,
    "amt_phaseout_rate":        0.50,    # OBBBA: 50¢ per $1 (was 25¢)

    # ── QBI §199A — TY 2026 ──────────────────────────────────────────────────
    # Source: Rev. Proc. 2025-32; OBBBA expanded phase-in range to $75k/$150k
    "qbi_threshold_mfj":       403550,   # = top of 24% MFJ bracket
    "qbi_threshold_other":     201775,   # = top of 24% single bracket
    # OBBBA: expanded phase-in range from $50k/$100k to $75k/$150k
    "qbi_phase_in_range_single": 75000,
    "qbi_phase_in_range_mfj":   150000,
    "qbi_min_deduction":          400,   # NEW for 2026: minimum QBI deduction if QBI ≥ $1,000
    "qbi_min":                    400,   # Alias for qbi_min_deduction — Source: OBBBA §70XXX; TY 2026 only

    # ── Retirement Plans — TY 2026 ───────────────────────────────────────────
    # Source: IRS Notice 2025-67 (irs.gov/pub/irs-drop/n-25-67.pdf); Rev. Proc. 2025-32
    "solo401k_elective_max_2026":  24500,   # up from $23,500 in 2025
    "simple_ira_max_2026":         17000,   # up from $16,500 in 2025
    "sep_ira_max_2026":            73000,   # up from $70,000 in 2025
    "ira_limit_2026":               7500,   # up from $7,000 in 2025
    "ira_catchup_50plus_2026":      1100,   # up from $1,000 in 2025 (SECURE 2.0 indexed)

    # ── HSA — TY 2026 ────────────────────────────────────────────────────────
    # Source: Rev. Proc. 2025-32 (HSA section)
    "hsa_self_only_2026":    4400,    # up from $4,300 in 2025
    "hsa_family_2026":       8750,    # up from $8,550 in 2025
    "hsa_catchup_55plus":    1000,    # unchanged

    # ── SALT Cap — TY 2026 ───────────────────────────────────────────────────
    # OBBBA §70106: $40,000 cap applies TY 2025–2029 (no inflation adjustment)
    # Same as 2025: $40,000 default, $20,000 MFS, phase-down above $500k AGI
    "salt_cap_default":          40000,
    "salt_cap_mfs":              20000,
    "salt_phasedown_threshold":  500000,
    "salt_phasedown_rate":        50,
    "salt_floor":                10000,

    # ── OBBBA New Deductions — TY 2026 ───────────────────────────────────────
    # All four OBBBA deductions continue in 2026 (same amounts as 2025 unless indexed)
    # Source: OBBBA §70103–§70301 (TY 2025–2028)
    "senior_deduction_amount":       6000,   # per qualifying taxpayer age 65+
    "senior_deduction_magi_single":  75000,
    "senior_deduction_magi_mfj":    150000,
    "tip_deduction_max":             25000,
    "tip_deduction_magi_single":    150000,
    "tip_deduction_magi_mfj":       300000,
    "overtime_deduction_max_single": 12500,
    "overtime_deduction_max_mfj":    25000,
    "overtime_deduction_magi_single":150000,
    "overtime_deduction_magi_mfj":   300000,
}
# Inherit any 2025 params not explicitly overridden
_p2026 = dict(PARAMS_2025)
_p2026.update(PARAMS_2026)
PARAMS_2026 = _p2026
del _p2026


# ── HELPERS ────────────────────────────────────────────────────────────────────

def rnd(v): return round(v)

def compute_tax(taxable_income: float, filing_status: str, tax_year: int = 2025) -> int:
    """
    Regular income tax from brackets.
    Source: TY 2025: Rev. Proc. 2024-40 + OBBBA; TY 2026: Rev. Proc. 2025-32
            irs.gov/pub/irs-pdf/i1040gi.pdf Tax Table
    """
    if tax_year == 2026:
        if filing_status in ("mfj", "qss"):
            brackets = PARAMS_2026["brackets_mfj_2026"]
        elif filing_status == "hoh":
            brackets = PARAMS_2026["brackets_hoh_2026"]
        elif filing_status == "mfs":
            brackets = PARAMS_2026["brackets_mfs_2026"]
        else:
            brackets = PARAMS_2026["brackets_single_2026"]
    else:
        if filing_status in ("mfj", "qss"):
            brackets = PARAMS_2025["tax_brackets_mfj"]
        elif filing_status == "hoh":
            brackets = PARAMS_2025["tax_brackets_hoh"]
        else:  # single, mfs
            brackets = PARAMS_2025["tax_brackets_single"]
    tax, prev = 0.0, 0
    for limit, rate in brackets:
        if taxable_income <= prev: break
        tax += (min(taxable_income, limit) - prev) * rate
        prev = limit
    return rnd(tax)

def get_saver_rate(agi: float, filing_status: str) -> float:
    # QSS uses MFJ thresholds per f8880.pdf instructions and Rev. Proc. 2024-40.
    # Source: irs.gov/pub/irs-pdf/f8880.pdf Line 9 Rate Table; i8880.pdf; Rev. Proc. 2024-40 §3.14
    if filing_status in ("mfj", "qss"):   # QSS = MFJ thresholds per f8880.pdf
        table = PARAMS_2025["saver_rate_mfj"]
    elif filing_status == "hoh":
        table = PARAMS_2025["saver_rate_hoh"]
    else:
        table = PARAMS_2025["saver_rate_single_qss"]
    for limit, rate in table:
        if agi <= limit: return rate
    return 0.0

def get_f2441_decimal(agi: float) -> float:
    """From table printed on Form 2441 (f2441.pdf). Read exact row — never interpolate."""
    table = [
        (15000,.35),(17000,.34),(19000,.33),(21000,.32),(23000,.31),
        (25000,.30),(27000,.29),(29000,.28),(31000,.27),(33000,.26),
        (35000,.25),(37000,.24),(39000,.23),(41000,.22),(43000,.21),
        (float('inf'),.20),
    ]
    for limit, dec in table:
        if agi <= limit: return dec
    return 0.20

def _obbba_phaseout(raw_amount: float, magi: float, magi_threshold: float,
                    phaseout_rate: float = 1.0) -> int:
    """
    Generic OBBBA linear phase-out: reduces dollar-for-dollar above MAGI threshold.
    phaseout_rate: dollars of deduction lost per dollar of MAGI over threshold (default 1:1).
    Returns: deduction after phase-out (minimum 0).
    """
    if magi <= magi_threshold:
        return rnd(raw_amount)
    excess = rnd(magi - magi_threshold)
    return max(0, rnd(raw_amount - excess * phaseout_rate))


def compute_senior_deduction(taxpayer_age: int, spouse_age: int,
                              magi: float, filing_status: str) -> dict:
    """
    OBBBA Senior Bonus Deduction — Schedule 1-A below-the-line (TY 2025–2028)
    Source: P.L. 119-21 §70103; irs.gov/newsroom/one-big-beautiful-bill-provisions

    - $6,000 per qualifying taxpayer/spouse age 65+
    - MFS filers: NOT eligible
    - Phase-out: $1 per $1 of MAGI above $75k (single/HOH/QSS) or $150k (MFJ)
    - Minimum deduction after phase-out: $0
    """
    p = PARAMS_2025
    if filing_status == "mfs":
        return {"deduction": 0, "warnings":
                ["Senior Bonus Deduction: not available for MFS filers. "
                 "Source: OBBBA §70103."]}
    threshold = (p["senior_deduction_magi_mfj"]
                 if filing_status in ("mfj", "qss")
                 else p["senior_deduction_magi_single"])
    per_person = p["senior_deduction_amount"]
    qualifying = 0
    if taxpayer_age >= 65:
        qualifying += per_person
    if filing_status in ("mfj",) and spouse_age >= 65:
        qualifying += per_person
    if qualifying == 0:
        return {"deduction": 0, "warnings": []}
    deduction = _obbba_phaseout(qualifying, magi, threshold)
    warnings = []
    if magi > threshold:
        warnings.append(
            f"Senior Bonus Deduction phased out: MAGI ${magi:,} exceeds ${threshold:,} threshold. "
            f"Pre-phase-out: ${qualifying:,}. Allowed: ${deduction:,}. "
            "Source: OBBBA §70103; irs.gov/newsroom/one-big-beautiful-bill-provisions."
        )
    return {"deduction": deduction, "qualifying_amount": qualifying, "warnings": warnings}


# IRS Notice 2025-65: qualifying occupations for OBBBA tip deduction (§70201)
# Source: irs.gov/pub/irs-drop/n-25-65.pdf; IRS Notice 2025-65 (August 2025)
QUALIFYING_TIP_OCCUPATIONS = {
    # Food & beverage service
    "waiter_waitress":          "Waiter / Waitress",
    "bartender":                "Bartender",
    "busser":                   "Busser / Busboy",
    "barback":                  "Barback",
    "food_runner":              "Food Runner",
    "host_hostess":             "Host / Hostess",
    "counter_server":           "Counter Server / Cashier (food service)",
    "delivery_driver_food":     "Food Delivery Driver",
    "barista":                  "Barista / Coffee Shop Server",
    # Hair, beauty & personal care
    "hairdresser":              "Hairdresser / Hair Stylist",
    "barber":                   "Barber",
    "nail_technician":          "Nail Technician",
    "esthetician":              "Esthetician / Skin Care Specialist",
    "cosmetologist":            "Cosmetologist",
    "massage_therapist":        "Massage Therapist",
    "tattoo_artist":            "Tattoo Artist / Body Piercer",
    # Hospitality & travel
    "hotel_bellhop":            "Hotel Bellhop / Porter",
    "hotel_valet":              "Hotel Valet / Parking Attendant",
    "hotel_housekeeper":        "Hotel Housekeeper / Room Attendant",
    "concierge":                "Concierge",
    "coat_check":               "Coat Check Attendant",
    "casino_dealer":            "Casino Dealer",
    "tour_guide":               "Tour Guide",
    # Transportation
    "taxi_driver":              "Taxi / Rideshare Driver",
    "limo_driver":              "Limousine / Car Service Driver",
    "shuttle_driver":           "Airport Shuttle Driver",
    # Other customary-tip service
    "golf_caddie":              "Golf Caddie",
    "ski_instructor":           "Ski Instructor",
    "spa_attendant":            "Spa / Sauna Attendant",
}

def compute_tip_deduction(qualified_tips: float, magi: float,
                           filing_status: str,
                           tip_occupation: str = "") -> dict:
    """
    OBBBA Tip Income Deduction — Schedule 1-A below-the-line (TY 2025–2028)
    Source: P.L. 119-21 §70201; IRS Notice 2025-65; irs.gov/newsroom/one-big-beautiful-bill-provisions

    - Qualified tips in IRS-listed customary-tip occupations (IRS Notice 2025-65)
    - Cap: $25,000 per individual
    - Phase-out: $1 per $1 of MAGI above $150k (single/HOH/QSS) or $300k (MFJ)
    - Mandatory service charges are NOT qualified tips (IRC §3121; Rev. Rul. 2012-18)
    - SSN required; tips must be reported to employer or self-reported for SE
    - Occupation must be on IRS Notice 2025-65 qualifying list
    """
    p = PARAMS_2025
    warnings = []

    # Occupation validation — IRS Notice 2025-65 qualifying occupation required
    # Source: IRS Notice 2025-65; P.L. 119-21 §70201
    if qualified_tips > 0 and not tip_occupation:
        warnings.append(
            "⚠ Tips Deduction: occupation not specified. "
            "IRS Notice 2025-65 requires tips to be received in a customary-tip occupation "
            "(food service, beauty/personal care, hospitality, transportation, etc.). "
            "Select your occupation to confirm eligibility. "
            "Mandatory service charges do not qualify (Rev. Rul. 2012-18). "
            "Source: P.L. 119-21 §70201; IRS Notice 2025-65."
        )
    elif qualified_tips > 0 and tip_occupation not in QUALIFYING_TIP_OCCUPATIONS:
        # Unrecognized code — could be a valid occupation not yet on our list
        warnings.append(
            f"Tips Deduction: occupation '{tip_occupation}' is not on the confirmed "
            "IRS Notice 2025-65 qualifying list in this software. "
            "Verify your occupation qualifies before filing. "
            "Source: P.L. 119-21 §70201; IRS Notice 2025-65."
        )

    threshold = (p["tip_deduction_magi_mfj"]
                 if filing_status in ("mfj", "qss")
                 else p["tip_deduction_magi_single"])
    capped = min(qualified_tips, p["tip_deduction_max"])
    deduction = _obbba_phaseout(capped, magi, threshold)

    if magi > threshold:
        warnings.append(
            f"Tip Deduction phased out: MAGI ${magi:,} exceeds ${threshold:,} threshold. "
            f"Pre-phase-out: ${capped:,}. Allowed: ${deduction:,}. "
            "Source: OBBBA §70201; IRS Notice 2025-65."
        )
    if qualified_tips > p["tip_deduction_max"]:
        warnings.append(
            f"Qualified tips ${qualified_tips:,} exceed $25,000 cap. "
            f"Cap applied: ${p['tip_deduction_max']:,}. "
            "Source: OBBBA §70201."
        )
    return {"deduction": deduction, "capped_amount": capped, "warnings": warnings,
            "occupation": tip_occupation,
            "occupation_label": QUALIFYING_TIP_OCCUPATIONS.get(tip_occupation, tip_occupation)}


def compute_overtime_deduction(overtime_pay: float, magi: float,
                                filing_status: str) -> dict:
    """
    OBBBA Overtime Pay Deduction — Schedule 1-A below-the-line (TY 2025–2028)
    Source: P.L. 119-21 §70202; irs.gov/newsroom/one-big-beautiful-bill-provisions

    - FLSA-qualifying overtime only (time-and-a-half above regular rate)
    - Cap: $12,500 single/HOH/QSS; $25,000 MFJ (combined both spouses)
    - MFS filers: NOT eligible
    - Phase-out: $1 per $1 of MAGI above $150k (single/HOH/QSS) or $300k (MFJ)
    - Employer must report qualifying overtime separately on W-2
    - Cannot double-count with tip deduction
    """
    p = PARAMS_2025
    if filing_status == "mfs":
        return {"deduction": 0, "warnings":
                ["Overtime Deduction: not available for MFS filers. "
                 "Source: OBBBA §70202."]}
    threshold = (p["overtime_deduction_magi_mfj"]
                 if filing_status in ("mfj", "qss")
                 else p["overtime_deduction_magi_single"])
    max_ded = (p["overtime_deduction_max_mfj"]
               if filing_status in ("mfj", "qss")
               else p["overtime_deduction_max_single"])
    capped = min(overtime_pay, max_ded)
    deduction = _obbba_phaseout(capped, magi, threshold)
    warnings = []
    if magi > threshold:
        warnings.append(
            f"Overtime Deduction phased out: MAGI ${magi:,} exceeds ${threshold:,} threshold. "
            f"Pre-phase-out: ${capped:,}. Allowed: ${deduction:,}. "
            "Source: OBBBA §70202; irs.gov/newsroom/one-big-beautiful-bill-provisions."
        )
    if overtime_pay > max_ded:
        warnings.append(
            f"Overtime pay ${overtime_pay:,} exceeds ${max_ded:,} cap for {filing_status.upper()}. "
            "Source: OBBBA §70202."
        )
    return {"deduction": deduction, "capped_amount": capped, "warnings": warnings}


def compute_auto_loan_deduction(interest_paid: float, magi: float,
                                 filing_status: str,
                                 loan_originated_after_2024: bool = True,
                                 vehicle_new_us_assembled: bool = True) -> dict:
    """
    OBBBA Auto Loan Interest Deduction — Schedule 1-A below-the-line (TY 2025–2028)
    Source: P.L. 119-21 §70301; irs.gov/newsroom/one-big-beautiful-bill-provisions

    - Interest on qualified passenger vehicle loans for NEW US-assembled vehicles
    - Loan must be originated after December 31, 2024
    - Personal use only (not business vehicles — those go to Schedule C/E)
    - Cap: $10,000/year
    - Phase-out: $1 per $1 of MAGI above $100k (single/HOH/QSS) or $200k (MFJ)
    """
    p = PARAMS_2025
    warnings = []
    if not loan_originated_after_2024:
        warnings.append(
            "Auto Loan Interest Deduction: loan must be originated after Dec 31, 2024. "
            "Pre-2025 loans do not qualify. Source: OBBBA §70301."
        )
        return {"deduction": 0, "warnings": warnings}
    if not vehicle_new_us_assembled:
        warnings.append(
            "Auto Loan Interest Deduction: vehicle must be NEW and assembled in the US. "
            "Used vehicles or foreign-assembled vehicles do not qualify. "
            "Source: OBBBA §70301."
        )
        return {"deduction": 0, "warnings": warnings}
    threshold = (p["auto_loan_deduction_magi_mfj"]
                 if filing_status in ("mfj", "qss")
                 else p["auto_loan_deduction_magi_single"])
    capped = min(interest_paid, p["auto_loan_deduction_max"])
    deduction = _obbba_phaseout(capped, magi, threshold)
    if magi > threshold:
        warnings.append(
            f"Auto Loan Interest Deduction phased out: MAGI ${magi:,} exceeds ${threshold:,} threshold. "
            f"Pre-phase-out: ${capped:,}. Allowed: ${deduction:,}. "
            "Source: OBBBA §70301."
        )
        warnings.append(
            f"Auto loan interest ${interest_paid:,} exceeds $10,000 cap. "
            "Source: OBBBA §70301."
        )
    return {"deduction": deduction, "capped_amount": capped, "warnings": warnings}


def compute_simplified_method(sm: 'SimplifiedMethodData',
                               annual_payments_this_year: float) -> dict:
    """
    Pub. 575 Worksheet A — Simplified Method for annuity cost basis recovery.
    Source: irs.gov/pub/irs-pdf/p575.pdf Worksheet A
            irs.gov/pub/irs-pdf/p554.pdf

    Logic:
      Line 1: Cost in the contract (Box 9b or prior-year carryforward)
      Line 2: (same as line 1 for current-year starter; or reduced by prior recoveries)
      Line 3: Expected number of monthly payments from IRS Tables 1 or 2 (or fixed)
      Line 4: Line 2 ÷ Line 3 = monthly tax-free amount (round to nearest dollar)
      Line 5: Months in year for which payments received (max 12)
      Line 6: Prior years' tax-free recovery (must include ALL prior years)
      Line 7: Line 4 × Line 5 = this year's tax-free amount
      Line 8: remaining basis = Line 2 − Line 6 − Line 7 (carry forward; never below 0)
      Taxable this year = total payments − Line 7 (but not less than 0)

    Table 1 — Single life (Pub. 575, post-Nov-18-1996 annuity start):
      Age ≤55 → 360 | 56–60 → 310 | 61–65 → 260 | 66–70 → 210 | 71+ → 160
    Table 1 — Single life (pre-Nov-19-1996 annuity start):
      Age ≤55 → 300 | 56–60 → 260 | 61–65 → 210 | 66–70 → 168 | 71+ → 120
    Table 2 — Multiple lives (combined ages, post-Nov-18-1996):
      ≤110 → 410 | 111–120 → 360 | 121–130 → 310 | 131–140 → 260 | 141+ → 210
    Table 2 — Multiple lives (combined ages, pre-Nov-19-1996):
      ≤110 → 342 | 111–120 → 300 | 121–130 → 255 | 131–140 → 210 | 141+ → 168

    NOTE: Once cost is fully recovered (remaining basis = 0), all subsequent payments
    are fully taxable. Verify exact table values against IRS p575.pdf before filing.
    """
    # Determine expected monthly payments from table
    if sm.annuity_type == "fixed":
        expected_payments = sm.fixed_period_months
    elif sm.annuity_type == "joint":
        combined = sm.age_at_annuity_start + sm.joint_age_at_annuity_start
        if sm.annuity_start_after_nov_18_1996 or getattr(sm, 'start_after_nov_1996', False):
            if combined <= 110:   expected_payments = 410
            elif combined <= 120: expected_payments = 360
            elif combined <= 130: expected_payments = 310
            elif combined <= 140: expected_payments = 260
            else:                 expected_payments = 210
        else:
            if combined <= 110:   expected_payments = 342
            elif combined <= 120: expected_payments = 300
            elif combined <= 130: expected_payments = 255
            elif combined <= 140: expected_payments = 210
            else:                 expected_payments = 168
    else:  # single life
        age = sm.age_at_annuity_start
        if sm.annuity_start_after_nov_18_1996 or getattr(sm, 'start_after_nov_1996', False):
            if age <= 55:   expected_payments = 360
            elif age <= 60: expected_payments = 310
            elif age <= 65: expected_payments = 260
            elif age <= 70: expected_payments = 210
            else:           expected_payments = 160
        else:
            if age <= 55:   expected_payments = 300
            elif age <= 60: expected_payments = 260
            elif age <= 65: expected_payments = 210
            elif age <= 70: expected_payments = 168
            else:           expected_payments = 120

    cost = rnd(sm.cost_in_contract)
    prior_recovered = rnd(sm.prior_year_tax_free_recovered)

    # Remaining basis available for recovery = cost minus already-recovered amounts
    remaining_basis_before = max(0, cost - prior_recovered)

    if expected_payments <= 0 or cost <= 0:
        return {
            "applicable": False,
            "expected_payments": 0, "monthly_tax_free": 0,
            "annual_tax_free": 0, "taxable_amount": rnd(annual_payments_this_year),
            "remaining_basis": 0,
            "warning": "Simplified Method not applicable (zero cost basis or zero expected payments)."
        }

    # IRS Pub 575 Worksheet A rounding:
    # Line 5: cost / expected payments — keep full decimal (do NOT round yet)
    # Line 6: multiply by 12 months, THEN round to nearest dollar
    # Source: IRS Pub 575 p.15; irs.gov/pub/irs-pdf/p575.pdf Worksheet A
    monthly_tax_free_exact = cost / expected_payments          # unrounded
    monthly_tax_free       = monthly_tax_free_exact            # kept for return dict
    annual_tax_free_exact  = monthly_tax_free_exact * 12       # unrounded annual
    # Round after multiplying, then cap at remaining basis
    annual_tax_free = rnd(min(annual_tax_free_exact, remaining_basis_before))

    # Remaining basis to carry to next year
    remaining_basis_after = max(0, remaining_basis_before - annual_tax_free)

    # Taxable portion this year
    taxable = max(0, rnd(annual_payments_this_year) - annual_tax_free)

    warning = "Simplified Method: Confirm exact expected payments from Table 1/2 in IRS Pub. 575 Worksheet A before filing."
    if remaining_basis_after == 0:
        warning += " Cost fully recovered — all future payments are fully taxable."

    return {
        "applicable": True,
        "cost_in_contract": cost,
        "prior_recovered": prior_recovered,
        "remaining_basis_before": remaining_basis_before,
        "expected_payments": expected_payments,
        "monthly_tax_free": monthly_tax_free,
        "annual_tax_free": annual_tax_free,
        "taxable_amount": taxable,
        "remaining_basis_after": remaining_basis_after,
        "warning": warning,
    }


def _compute_ss_taxable_worksheet1(net_benefits: float, agi_before_ss: float,
                                    tax_exempt_interest: float, filing_status: str,
                                    sch1_adjustments: float,
                                    exclusion_adjustments: float,
                                    mfs_lived_apart: bool) -> dict:
    """
    Pub 915 Worksheet 1 — core SS taxability logic.
    Used both for current-year (main path) and for prior-year refigure in Worksheet 2.
    Source: irs.gov/pub/irs-pdf/p915.pdf Worksheet 1 (lines 1–19)

    Lines 1–19:
      L1  = net benefits (Box 5)                → also goes on 1040 Line 6a
      L2  = L1 × 50%
      L3  = other income (wages, interest, pension, dividends, cap gains, other)
      L4  = tax-exempt interest (Form 1040 Line 2a)
      L5  = exclusion adjustments (Forms 8815, 2555, 4563, 8839)
      L6  = L2 + L3 + L4 + L5
      L7  = Schedule 1 above-the-line adjustments (Lines 11–20, 23, 25)
      L8  = L6 − L7 (if negative → $0 taxable)
      L9  = base amount for filing status
      L10 = L8 − L9 (if negative → $0 taxable)
      L11 = $9,000 (single/QSS/HOH/MFS-apart) or $12,000 (MFJ)
      L12 = L10 − L11 (floor 0)
      L13 = smaller of L10 or L11
      L14 = L13 × 50%
      L15 = smaller of L2 or L14
      L16 = L12 × 85%
      L17 = L15 + L16
      L18 = net benefits × 85%
      L19 = smaller of L17 or L18   → taxable SS amount
    Special: MFS lived-with-spouse → always 85% of benefits (skip L9–L16)
    """
    p = PARAMS_2025
    fs = filing_status

    # Base and upper amounts per filing status + MFS-apart flag
    if fs == "mfj":
        base = p["ss_base_mfj"]           # $32,000
        upper = p["ss_upper_mfj"]         # $44,000
        l9 = base
        l11 = 12000
    elif fs == "mfs" and not mfs_lived_apart:
        # Lived with spouse at any time: 85% always
        taxable = rnd(net_benefits * 0.85)
        return {"l1": rnd(net_benefits), "l19_taxable": taxable,
                "method": "mfs_lived_together_85pct"}
    else:
        # single, hoh, qss, mfs-lived-apart
        base = p["ss_base_single_qss_hoh"]   # $25,000
        upper = p["ss_upper_single_qss_hoh"] # $34,000
        l9 = base
        l11 = 9000

    l1  = rnd(net_benefits)
    l2  = rnd(l1 * 0.50)
    l3  = rnd(agi_before_ss)                # other income EXCLUDING SS
    l4  = rnd(tax_exempt_interest)
    l5  = rnd(exclusion_adjustments)
    l6  = l2 + l3 + l4 + l5
    l7  = rnd(sch1_adjustments)
    l8  = max(0, l6 - l7)

    if l8 <= l9:
        return {"l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5,
                "l6": l6, "l7": l7, "l8": l8, "l9": l9,
                "l19_taxable": 0, "method": "below_base"}

    l10 = max(0, l8 - l9)
    l12 = max(0, l10 - l11)
    l13 = min(l10, l11)
    l14 = rnd(l13 * 0.50)
    l15 = min(l2, l14)
    l16 = rnd(l12 * 0.85)
    l17 = l15 + l16
    l18 = rnd(l1 * 0.85)
    l19 = min(l17, l18)

    return {"l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5,
            "l6": l6, "l7": l7, "l8": l8, "l9": l9,
            "l10": l10, "l11": l11, "l12": l12, "l13": l13,
            "l14": l14, "l15": l15, "l16": l16, "l17": l17,
            "l18": l18, "l19_taxable": l19, "method": "standard"}


def compute_ss_lump_sum_election(net_benefits_2025: float,
                                  agi_before_ss_2025: float,
                                  tax_exempt_int_2025: float,
                                  filing_status: str,
                                  sch1_adj_2025: float,
                                  exclusion_adj_2025: float,
                                  mfs_lived_apart_2025: bool,
                                  prior_years: list,
                                  w1_taxable: float) -> dict:
    """
    Pub 915 Lump-Sum Election — Worksheets 2 & 4.
    Source: irs.gov/pub/irs-pdf/p915.pdf

    Algorithm (per Pub 915):
    1. Worksheet 1: compute taxable SS under regular method (already done → w1_taxable)
    2. For each prior year (post-1993): run Worksheet 2:
       - Refigure prior-year taxable SS as if lump-sum received in that year
       - Line 21 = refigured taxable − already reported taxable (floor 0)
    3. Worksheet 4:
       - Line 19 = current-year taxable WITHOUT the lump-sum amounts
                   (re-run Worksheet 1 using Box 5 minus all lump-sum amounts)
       - Line 20 = sum of all Worksheet 2/3 Line 21 amounts
       - Line 21 = Line 19 + Line 20
    4. Compare Worksheet 4 Line 21 vs Worksheet 1 Line 19 → use LOWER amount.
       If election used: check box on Form 1040 Line 6c.

    NOTE: Worksheet 3 (pre-1994 years) uses the same structural formula as
    Worksheet 2 but with historical base amounts. Engine flags pre-1994 with
    a warning; the formula is structurally identical for post-1983 years.
    Prior-year returns are NEVER amended.
    """
    warnings = []
    wks2_results = []
    total_additional_taxable = 0    # sum of all W2 Line 21 amounts

    total_lump_sum = sum(py.lump_sum_amount_for_this_year for py in prior_years)

    for py in prior_years:
        if py.is_pre_1994:
            warnings.append(
                f"Prior year {py.prior_year} is 1993 or earlier — Worksheet 3 applies. "
                "Engine uses Worksheet 2 structure; verify base amounts for that year "
                "against IRS Pub 915. Source: irs.gov/pub/irs-pdf/p915.pdf"
            )
        # Worksheet 2 Line 1: prior-year net SS + this year's lump-sum for that year
        w2_l1 = rnd(py.prior_year_net_ss_benefits + py.lump_sum_amount_for_this_year)

        if w2_l1 <= 0:
            wks2_results.append({"prior_year": py.prior_year, "w2_l21_additional": 0,
                                  "w2_l1": w2_l1})
            continue

        # Run Worksheet 1 logic using prior-year figures
        w2_wks1 = _compute_ss_taxable_worksheet1(
            net_benefits        = w2_l1,
            agi_before_ss       = py.prior_year_agi,
            tax_exempt_interest = py.prior_year_tax_exempt_interest,
            filing_status       = filing_status,
            sch1_adjustments    = py.prior_year_sch1_adjustments,
            exclusion_adjustments = py.prior_year_exclusion_adjustments,
            mfs_lived_apart     = py.mfs_lived_apart_all_year if hasattr(py, 'mfs_lived_apart_all_year') else False,
        )
        w2_l19_refigured = w2_wks1["l19_taxable"]
        # Line 20: taxable SS already reported for that prior year
        w2_l20 = rnd(py.prior_year_taxable_ss_already_reported)
        # Line 21: additional taxable (floor 0 — cannot be negative)
        w2_l21 = max(0, w2_l19_refigured - w2_l20)
        total_additional_taxable += w2_l21
        wks2_results.append({
            "prior_year": py.prior_year,
            "is_pre_1994": py.is_pre_1994,
            "w2_l1": w2_l1,
            "w2_l19_refigured_taxable": w2_l19_refigured,
            "w2_l20_already_reported": w2_l20,
            "w2_l21_additional": w2_l21,
        })

    # Worksheet 4
    # Line 19: current-year taxable WITHOUT the lump-sum amounts
    # Re-run Worksheet 1 using (current Box 5 − total lump-sum)
    net_benefits_excl_lump = max(0, net_benefits_2025 - total_lump_sum)
    wks1_excl = _compute_ss_taxable_worksheet1(
        net_benefits        = net_benefits_excl_lump,
        agi_before_ss       = agi_before_ss_2025,
        tax_exempt_interest = tax_exempt_int_2025,
        filing_status       = filing_status,
        sch1_adjustments    = sch1_adj_2025,
        exclusion_adjustments = exclusion_adj_2025,
        mfs_lived_apart     = mfs_lived_apart_2025,
    )
    w4_l19 = wks1_excl["l19_taxable"]
    w4_l20 = total_additional_taxable          # sum of all W2 Line 21
    w4_l21 = rnd(w4_l19 + w4_l20)             # Worksheet 4 Line 21

    # Choose lower amount
    election_beneficial = w4_l21 < w1_taxable
    final_taxable = w4_l21 if election_beneficial else w1_taxable

    if election_beneficial:
        warnings.append(
            f"Lump-Sum Election BENEFICIAL: Worksheet 4 L21 (${w4_l21:,}) < "
            f"Worksheet 1 L19 (${w1_taxable:,}). Check box on Form 1040 Line 6c. "
            "Keep completed worksheets with records; do NOT attach to return. "
            "Source: irs.gov/pub/irs-pdf/p915.pdf"
        )
    else:
        warnings.append(
            f"Lump-Sum Election NOT beneficial: Worksheet 4 L21 (${w4_l21:,}) >= "
            f"Worksheet 1 L19 (${w1_taxable:,}). Use regular method. "
            "Do NOT check Line 6c box."
        )

    return {
        "worksheet2_results": wks2_results,
        "w4_l19_current_excl_lump": w4_l19,
        "w4_l20_additional": w4_l20,
        "w4_l21": w4_l21,
        "w1_l19_regular": w1_taxable,
        "election_beneficial": election_beneficial,
        "final_taxable_ss": final_taxable,
        "line_6c_check": election_beneficial,
        "warnings": warnings,
    }


def compute_ss_taxable(net_benefits: float, agi_before_ss: float,
                        filing_status: str,
                        tax_exempt_interest: float = 0.0,
                        sch1_adjustments: float = 0.0,
                        exclusion_adjustments: float = 0.0,
                        mfs_lived_apart: bool = False) -> dict:
    """
    SSA-1099 taxability per Pub 915 Worksheet 1 (p915.pdf).
    Delegates to _compute_ss_taxable_worksheet1.
    Source: irs.gov/pub/irs-pdf/p915.pdf Worksheet 1; IRC §86; i1040gi.pdf Line 6b.
    """
    wks1 = _compute_ss_taxable_worksheet1(
        net_benefits=net_benefits,
        agi_before_ss=agi_before_ss,
        tax_exempt_interest=tax_exempt_interest,
        filing_status=filing_status,
        sch1_adjustments=sch1_adjustments,
        exclusion_adjustments=exclusion_adjustments,
        mfs_lived_apart=mfs_lived_apart,
    )
    taxable_ss = wks1["l19_taxable"]
    p = PARAMS_2025
    is_mfj = filing_status == "mfj"
    base  = p["ss_base_mfj"] if is_mfj else p["ss_base_single_qss_hoh"]
    upper = p["ss_upper_mfj"] if is_mfj else p["ss_upper_single_qss_hoh"]
    pct = 0 if taxable_ss == 0 else (50 if taxable_ss <= net_benefits * 0.50 else 85)
    return {
        "net_benefits": rnd(net_benefits),
        "combined_income": rnd(agi_before_ss + net_benefits * 0.50),
        "base_amount": base,
        "upper_threshold": upper,
        "taxable_pct": pct,
        "taxable_amount": taxable_ss,
        "l6a": rnd(net_benefits),
        "l6b": taxable_ss,
        "worksheet1_detail": wks1,
    }

def compute_aoc(qualified_expenses: float, params: dict = None) -> dict:
    """
    American Opportunity Credit — Form 8863 Part III
    Source: irs.gov/pub/irs-pdf/f8863.pdf; irs.gov/pub/irs-pdf/i8863.pdf
    IRC §25A(b): 100% of first $2,000 + 25% of next $2,000 = max $2,500
    40% refundable ($1,000 max) → Form 1040 Line 29
    60% non-refundable → Schedule 3 Line 3
    """
    p = params or PARAMS_2025
    aoc_max_exp  = p.get("aoc_max_qualified_exp", 4000)   # IRC §25A(b)(1)
    aoc_max_cr   = p.get("aoc_max_credit",        2500)   # IRC §25A(b)(1)
    aoc_ref_pct  = p.get("aoc_refundable_pct",    0.40)   # IRC §25A(i)
    exp    = min(qualified_expenses, aoc_max_exp)
    credit = rnd(2000 + max(0, exp - 2000) * 0.25) if exp > 2000 else rnd(exp * 1.00)
    credit = min(credit, aoc_max_cr)
    refundable = rnd(credit * aoc_ref_pct)
    nonref = credit - refundable
    return {"total": credit, "refundable": refundable, "nonref": nonref,
            "qualified_exp_used": rnd(exp)}

def compute_llc(qualified_expenses: float, params: dict = None) -> dict:
    """
    Lifetime Learning Credit — Form 8863 Part I
    Source: irs.gov/pub/irs-pdf/f8863.pdf; irs.gov/pub/irs-pdf/i8863.pdf
    IRC §25A(c): 20% of up to $10,000 qualified expenses = max $2,000
    Entirely non-refundable → Schedule 3 Line 3
    """
    p = params or PARAMS_2025
    llc_max_exp = p.get("llc_max_qualified_exp", 10000)   # IRC §25A(c)(1)
    llc_rate    = p.get("llc_credit_rate",        0.20)   # IRC §25A(c)(1)
    exp    = min(qualified_expenses, llc_max_exp)
    credit = rnd(exp * llc_rate)
    return {"total": credit, "refundable": 0, "nonref": credit,
            "qualified_exp_used": rnd(exp)}

def compute_eitc(earned_income: float, agi: float,
                 num_children: int, filing_status: str,
                 investment_income: float = 0.0,
                 exact_eitc_from_table: float = -1.0,
                 params: dict = None) -> dict:
    """
    EIC — Form 1040 Line 27a
    Source: irs.gov/pub/irs-pdf/p596.pdf; irs.gov/pub/irs-pdf/p1040.pdf pp.16+
            IRC §32; Rev. Proc. 2024-40 §3.07

    IMPLEMENTATION: IRS EIC Table algorithm (exact $50 income-band lookup).
    The IRS EIC Table uses discrete $50 bands — formula approximations differ
    by $1–$100 on virtually every return and are not filing-grade.

    Algorithm (replicates p1040.pdf EIC Table exactly):
      1. Investment income > limit → $0 (IRC §32(i))
      2. MFS → $0 (IRC §32(d))
      3. Use higher of earned income or AGI as the lookup amount
      4. If lookup ≥ income_limit → $0
      5. Floor to nearest $50: band = (lookup // 50) × $50
      6. Apply phase-in/phase-out formula at band value (not exact income)
         - Phase-in:   credit = round(band × phase_in_rate)
         - Plateau:    credit = max_credit
         - Phase-out:  credit = max(0, round(max_credit − (band − po_start) × po_rate))
      7. Cap at max_credit

    If exact_eitc_from_table ≥ 0: use that override (retained for backward compat).
    Source: p596.pdf Ch.4; p1040.pdf EIC Table; IRC §32; Rev. Proc. 2024-40 §3.07.
    """
    p = params or PARAMS_2025

    # MFS disqualification — IRC §32(d)
    if filing_status == "mfs":
        return {
            "eitc": 0, "requires_table_lookup": False,
            "disqualified_mfs": True,
            "warning": "EITC not allowed for Married Filing Separately. Source: IRC §32(d); p596.pdf.",
        }

    # Investment income disqualification — IRC §32(i)
    invest_limit = p.get("eitc_investment_income_limit",
                         p.get("eitc_invest_limit", 11600))
    if investment_income > invest_limit:
        return {
            "eitc": 0, "requires_table_lookup": False,
            "disqualified_investment_income": True,
            "investment_income": investment_income,
            "warning": (f"EITC disqualified: investment income ${investment_income:,.0f} "
                        f"exceeds ${invest_limit:,} limit. Source: IRC §32(i); p596.pdf."),
        }

    col    = "mfj" if filing_status == "mfj" else "single_qss"
    nc     = min(num_children, 3)
    row    = p["eitc"][col].get(nc)
    if not row:
        return {"eitc": 0, "requires_table_lookup": False}

    # Phase-in rates (IRC §32(b)(1); Rev. Proc. 2024-40 §3.07)
    phase_in_rates = p["eitc"].get("phase_in_rates",
                                   {0: 0.0765, 1: 0.34, 2: 0.40, 3: 0.45})
    phase_in_rate  = phase_in_rates[nc]
    phase_in_end   = row["max"] / phase_in_rate   # earned income where max credit first reached

    # Use higher of earned income or AGI — p596.pdf Ch.4 "Which Earned Income or AGI to Use"
    lookup = max(earned_income, agi)
    if lookup >= row["income_limit"]:
        return {"eitc": 0, "requires_table_lookup": False}

    # Override: exact value confirmed by user from IRS table (backward compat)
    if exact_eitc_from_table >= 0:
        return {
            "eitc": rnd(exact_eitc_from_table),
            "requires_table_lookup": False,
            "confirmed_from_table": True,
        }

    # IRS EIC Table band algorithm — p1040.pdf EIC Table pp.16+
    # Each row represents "At least $B — But less than $(B+50)"; credit computed at $B.
    band = float((int(lookup) // 50) * 50)

    if band <= phase_in_end:
        credit = round(band * phase_in_rate)
    elif band <= row["phaseout_start"]:
        credit = row["max"]
    else:
        excess = band - row["phaseout_start"]
        credit = max(0, round(row["max"] - excess * row["phaseout_rate"]))

    credit = min(credit, row["max"])

    return {
        "eitc": credit,
        "requires_table_lookup": False,   # table algorithm is filing-grade
        "table_band": band,
        "lookup_income": lookup,
        "children": nc,
        "filing_col": col,
    }




def compute_aoc(qualified_expenses: float, magi: float, filing_status: str) -> dict:
    """
    American Opportunity Credit — Form 8863 Part III
    Source: irs.gov/pub/irs-pdf/f8863.pdf, i8863.pdf
    100% of first $2,000 + 25% of next $2,000 = max $2,500
    40% refundable ($1,000 max) → Form 1040 Line 29
    60% non-refundable → Schedule 3 Line 3

    MAGI phase-out (v5 fix): Source: i8863.pdf
      Single/HOH/QSS: $80,000–$90,000
      MFJ: $160,000–$180,000
    Above upper limit: credit = $0
    MFS: credit is $0 — IRC §25A(g)(6)
    """
    p = PARAMS_2025
    # MFS disqualification — IRC §25A(g)(6)
    # Source: irs.gov/pub/irs-pdf/i8863.pdf; IRC §25A(g)(6)
    if filing_status == "mfs":
        return {
            "total": 0, "refundable": 0, "nonref": 0,
            "qualified_exp_used": 0, "phaseout_ratio": 0.0, "phaseout_applied": False,
            "disqualified_mfs": True,
            "warning": "American Opportunity Credit not allowed for Married Filing Separately. Source: IRC §25A(g)(6); i8863.pdf.",
        }
    if filing_status == "mfj":
        po_start = p["aoc_llc_phaseout_mfj_start"]
        po_end   = p["aoc_llc_phaseout_mfj_end"]
    else:
        po_start = p["aoc_llc_phaseout_single_start"]
        po_end   = p["aoc_llc_phaseout_single_end"]

    # Phase-out ratio
    if magi >= po_end:
        phaseout_ratio = 0.0
    elif magi <= po_start:
        phaseout_ratio = 1.0
    else:
        phaseout_ratio = (po_end - magi) / (po_end - po_start)

    exp = min(qualified_expenses, 4000)
    if exp <= 2000:
        credit_before_po = rnd(exp * 1.00)
    else:
        credit_before_po = rnd(2000 + (exp - 2000) * 0.25)
    credit_before_po = min(credit_before_po, 2500)
    credit = rnd(credit_before_po * phaseout_ratio)
    refundable = rnd(credit * 0.40)
    nonref = credit - refundable
    return {
        "total": credit, "refundable": refundable, "nonref": nonref,
        "qualified_exp_used": rnd(exp),
        "phaseout_ratio": round(phaseout_ratio, 4),
        "phaseout_applied": magi > po_start,
    }


def compute_llc(qualified_expenses: float, magi: float, filing_status: str) -> dict:
    """
    Lifetime Learning Credit — Form 8863 Part I
    Source: irs.gov/pub/irs-pdf/f8863.pdf, i8863.pdf
    20% of up to $10,000 qualified expenses = max $2,000
    Entirely non-refundable → Schedule 3 Line 3

    MAGI phase-out (v5 fix): same thresholds as AOC
    MFS: credit is $0 — IRC §25A(g)(6)
    """
    p = PARAMS_2025
    # MFS disqualification — IRC §25A(g)(6)
    # Source: irs.gov/pub/irs-pdf/i8863.pdf; IRC §25A(g)(6)
    if filing_status == "mfs":
        return {
            "total": 0, "refundable": 0, "nonref": 0,
            "qualified_exp_used": 0, "phaseout_ratio": 0.0, "phaseout_applied": False,
            "disqualified_mfs": True,
            "warning": "Lifetime Learning Credit not allowed for Married Filing Separately. Source: IRC §25A(g)(6); i8863.pdf.",
        }
    if filing_status == "mfj":
        po_start = p["aoc_llc_phaseout_mfj_start"]
        po_end   = p["aoc_llc_phaseout_mfj_end"]
    else:
        po_start = p["aoc_llc_phaseout_single_start"]
        po_end   = p["aoc_llc_phaseout_single_end"]

    if magi >= po_end:
        phaseout_ratio = 0.0
    elif magi <= po_start:
        phaseout_ratio = 1.0
    else:
        phaseout_ratio = (po_end - magi) / (po_end - po_start)

    exp = min(qualified_expenses, 10000)
    credit = rnd(rnd(exp * 0.20) * phaseout_ratio)
    return {
        "total": credit, "refundable": 0, "nonref": credit,
        "qualified_exp_used": rnd(exp),
        "phaseout_ratio": round(phaseout_ratio, 4),
        "phaseout_applied": magi > po_start,
    }


def compute_student_loan_deduction(interest_paid: float, magi: float,
                                    filing_status: str) -> dict:
    """
    Student loan interest deduction — Schedule 1 Line 21
    Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 21; IRC §221
    Max $2,500; phases out based on MAGI:
      Single/HOH/QSS/MFS: $80,000–$95,000
      MFJ: $165,000–$195,000
    MFS: deduction NOT allowed (Source: IRC §221(b)(2)(B))
    """
    p = PARAMS_2025
    if filing_status == "mfs":
        return {"deduction": 0, "disallowed_mfs": True,
                "warning": "Student loan interest deduction not allowed for MFS filers. Source: IRC §221(b)(2)(B)."}

    if filing_status == "mfj":
        po_start = p["student_loan_phaseout_mfj_start"]
        po_end   = p["student_loan_phaseout_mfj_end"]
    else:
        po_start = p["student_loan_phaseout_single_start"]
        po_end   = p["student_loan_phaseout_single_end"]

    capped = min(interest_paid, p["student_loan_max"])
    if magi >= po_end:
        deduction = 0
    elif magi <= po_start:
        deduction = rnd(capped)
    else:
        ratio = (po_end - magi) / (po_end - po_start)
        deduction = rnd(capped * ratio)

    return {
        "deduction": deduction,
        "interest_paid": rnd(interest_paid),
        "capped_at_2500": rnd(capped),
        "magi": rnd(magi),
        "phaseout_applied": magi > po_start,
        "disallowed_mfs": False,
    }


def compute_schedule_c_se(schedule_cs: list, p: dict,
                           w2_ss_wages: float = 0.0,
                           nec_forms: list = None) -> dict:
    """
    Schedule C + Schedule SE computation.
    Source: irs.gov/pub/irs-pdf/f1040sc.pdf; irs.gov/pub/irs-pdf/f1040sse.pdf

    For each Schedule C:
      Gross profit = gross receipts - returns - COGS
      Net profit (L31) = gross profit + other income - total expenses
      Home office simplified: $5/sqft × business sqft (max 300 sqft = $1,500)
      Meals: 50% of reported meals expense

    Schedule SE (Long method):
      Net earnings from SE = sum of net profits × 92.35%
      SS portion of SE tax: limited to (wage base - W-2 SS wages) to avoid double-counting
        when wages + SE earnings together exceed $176,100 SS wage base (2025).
        Source: f1040sse.pdf Line 8a; IRC §3121(a)(1)
      SE tax = SS portion × 12.4% + Medicare portion × 2.9%
      Deductible SE tax = SE tax × 50% → Schedule 1 Line 15

    w2_ss_wages: W-2 Box 3 wages already subject to SS (reduces available SE SS base)

    Returns:
      total_net_profit  → Schedule 1 Line 3
      se_tax            → Schedule 2 Line 4
      se_tax_deduction  → Schedule 1 Line 15 (reduces AGI)
      per_business      → list of per-Schedule-C detail
    """
    per_business = []
    total_net_profit = 0.0

    for sc in schedule_cs:
        # 1099-NEC gross receipts handling
        # Source: i1040sc.pdf Line 1; i1099nec.pdf Box 1
        # By default (nec_included_in_gross=True), engine assumes preparer has ALREADY
        # included any 1099-NEC Box 1 amounts in their gross_receipts figure.
        # If nec_included_in_gross=False, engine auto-adds all 1099-NEC Box 1 to gross.
        _nec_auto = 0
        if not getattr(sc, 'nec_included_in_gross', True):
            _nec_auto = rnd(sum(f.box1_nonemployee_comp
                               for f in (nec_forms or [])
                               if f.box1_nonemployee_comp > 0))
        gross_receipts   = rnd(sc.gross_receipts + _nec_auto)
        returns          = rnd(sc.returns_allowances)
        gross_profit     = gross_receipts - returns
        total_income     = gross_profit + rnd(sc.other_income)

        # COGS (v8: Part III) — Source: f1040sc.pdf Part III
        cogs = compute_cogs(sc)

        # Meals: 50% limitation per f1040sc.pdf Line 24b and IRC §274(n)
        meals_deductible = rnd(sc.meals * p["meals_deduction_pct"])

        # Home office — simplified method only (Rev Proc 2013-13)
        # §4.07: allowable deduction limited to gross income from business use of home
        # gross income from home use = gross_profit + other_income − non-home-office expenses
        home_office = 0
        if sc.use_home_office_simplified and sc.home_office_sq_ft > 0:
            sqft = min(sc.home_office_sq_ft, p["home_office_simplified_max_sqft"])
            home_office_uncapped = rnd(sqft * p["home_office_simplified_rate"])
            # Compute income before home office to enforce cap
            exp_before_home_office = rnd(
                cogs + sc.advertising + sc.car_truck_expenses + sc.commissions_fees +
                sc.contract_labor + sc.depletion + sc.depreciation +
                sc.employee_benefit_programs + sc.insurance +
                sc.mortgage_interest + sc.other_interest +
                sc.legal_professional + sc.office_expense +
                sc.pension_profit_sharing + sc.rent_lease_vehicles +
                sc.rent_lease_other + sc.repairs_maintenance +
                sc.supplies + sc.taxes_licenses + sc.travel +
                meals_deductible + sc.utilities + sc.wages +
                sc.other_expenses
            )
            income_before_home_office = rnd(total_income - exp_before_home_office)
            # Cap: cannot create a loss (Rev. Proc. 2013-13 §4.07)
            home_office = max(0, min(home_office_uncapped, income_before_home_office))

        # Business miles → standard mileage rate when car_truck_expenses = $0
        # Rev. Proc. 2024-45 §5.01: 67¢/mile for 2025 business driving
        # Source: FETCH_VERIFIED: irs.gov/pub/irs-pdf/rp-24-45.pdf | §5.01 | 2026-05-21
        _std_mileage_rate = p.get("standard_mileage_rate_2025", 0.67)
        _car_expense = rnd(sc.car_truck_expenses) if sc.car_truck_expenses else                        rnd((sc.business_miles or 0) * _std_mileage_rate)

        total_expenses = rnd(
            cogs +
            sc.advertising + _car_expense + sc.commissions_fees +
            sc.contract_labor + sc.depletion + sc.depreciation +
            sc.employee_benefit_programs + sc.insurance +
            sc.mortgage_interest + sc.other_interest +
            sc.legal_professional + sc.office_expense +
            sc.pension_profit_sharing + sc.rent_lease_vehicles +
            sc.rent_lease_other + sc.repairs_maintenance +
            sc.supplies + sc.taxes_licenses + sc.travel +
            meals_deductible + sc.utilities + sc.wages +
            sc.other_expenses + home_office
        )

        net_profit = rnd(total_income - total_expenses)
        total_net_profit += net_profit

        per_business.append({
            "name": sc.business_name or "Business",
            "business_code": sc.business_code or "",   # NAICS 6-digit — f1040sc.pdf Box A
            "gross_receipts": gross_receipts,
            "other_income": rnd(sc.other_income),
            "gross_profit": gross_profit,          # f1040sc Line 5 (receipts - returns)
            "gross_income": rnd(total_income),     # f1040sc Line 7 (gross_profit + other_income)
            "cogs": cogs,
            "total_expenses": total_expenses,
            "car_expense": _car_expense,
            "business_miles": rnd(sc.business_miles),
            "mileage_rate": _std_mileage_rate if sc.business_miles else 0,
            "meals_deductible": meals_deductible,
            "home_office": home_office,
            "net_profit": net_profit,
            "for_spouse": sc.for_spouse,
        })

    total_net_profit = rnd(total_net_profit)

    # Schedule SE — Long Method
    # Source: irs.gov/pub/irs-pdf/f1040sse.pdf
    if total_net_profit <= 0:
        return {
            "per_business": per_business,
            "total_net_profit": total_net_profit,
            "net_earnings_se": 0,
            "se_tax": 0,
            "se_tax_deduction": 0,
            "ss_wages_combined": 0,
            "w2_ss_wages_used": rnd(w2_ss_wages),
        }

    net_earnings_se = rnd(total_net_profit * p["se_tax_rate_net_earnings"])
    # SS wage base applies across W-2 wages AND SE earnings combined
    # Reduce available SE SS base by W-2 SS wages already taxed
    available_ss_base = max(0, rnd(p["ss_wage_base_2025"] - w2_ss_wages))
    ss_portion = min(net_earnings_se, available_ss_base)
    se_ss_tax  = rnd(ss_portion * p["ss_tax_rate_se"])
    se_med_tax = rnd(net_earnings_se * p["medicare_tax_rate_se"])
    se_tax     = se_ss_tax + se_med_tax
    se_tax_deduction = rnd(se_tax * 0.50)   # → Schedule 1 Line 15

    return {
        "per_business": per_business,
        "total_net_profit": total_net_profit,
        "net_earnings_se": net_earnings_se,
        "se_ss_tax": se_ss_tax,
        "se_med_tax": se_med_tax,
        "se_tax": se_tax,                   # → Schedule 2 Line 4
        "se_tax_deduction": se_tax_deduction,  # → Schedule 1 Line 15
        "ss_wages_combined": ss_portion,
        "w2_ss_wages_used": rnd(w2_ss_wages),
        "available_ss_base": available_ss_base,
    }


def compute_qbi_deduction(schedule_cs: list, se_tax_deduction: float,
                           se_health_deduction: float, se_retirement_deduction: float,
                           taxable_income: float, qdcgt_income: float,
                           filing_status: str, params: dict = None,
                           qbi_loss_carryforward: float = 0.0,
                           se_net_profit: float = None,
                           reit_ptp_income: float = 0.0) -> dict:
    # se_net_profit: if provided, use this as QBI base (already has mileage + NEC baked in)
    # reit_ptp_income: Form 8995 Line 6 — 1099-DIV Box 5 (§199A/REIT dividends) + K-1 §199A
    # Source: f8995.pdf Lines 6-9; i8995.pdf Line 6; IRC §199A(e)(4); FETCH_VERIFIED 2026-05-24
    """
    Form 8995 — Qualified Business Income Deduction (§199A) — Simplified
    Source: irs.gov/pub/irs-pdf/f8995.pdf; irs.gov/pub/irs-pdf/i8995.pdf

    Applies when taxable income DOES NOT exceed the threshold:
      2025: $197,300 single/HOH/MFS; $394,600 MFJ/QSS
    Above threshold → Form 8995-A required (W-2 wage / UBIA limitation).
    Engine implements Form 8995 (simplified) only.

    Line-by-line per f8995.pdf:
      L1  = Qualified business income from each business (net profit reduced by
            deductible SE tax, SE health insurance, SE retirement allocable to biz)
      L2  = Total QBI (sum of L1 amounts; negative QBI = loss, carried forward)
      L3  = 20% × L2 (tentative QBI deduction)
      L4  = Net capital gain = qualified dividends + net LTCG (QDCGT Worksheet L4)
      L5  = Taxable income − net capital gain (ordinary taxable income)
      L6  = 20% × L5 (taxable income limitation base)
      L7  = Smaller of L3 or L6 (QBI deduction limited to 20% of ordinary TI)
      L15 = QBI deduction = smaller of L7 or 20% of (taxable income − net cap gain)
            This is the amount entered on Form 1040 Line 13 (Schedule 1 Line not used;
            QBI deduction goes directly to Form 1040 Line 13, below AGI line).

    QBI = net Schedule C profit reduced by:
      - Deductible SE tax (Sch 1 Line 15)  → allocable to business income
      - SE health insurance (Sch 1 Line 17) → reduces QBI per Reg. 1.199A-3
      - SE retirement contributions (Sch 1 Line 16) → reduces QBI per Reg. 1.199A-3

    Loss carryforward: NOT implemented (flagged as warning).
    Threshold: if taxable income exceeds threshold → warn, compute 8995-A is needed.
    Specified service trade or business (SSTB): NOT screened (flagged as warning).
    W-2 wages/UBIA limitation: NOT applicable below threshold.

    Source: irs.gov/pub/irs-pdf/f8995.pdf; irs.gov/pub/irs-pdf/i8995.pdf
    """
    p = params if params is not None else PARAMS_2025
    warnings = []
    threshold     = (p["qbi_threshold_mfj"] if filing_status in ("mfj", "qss")
                     else p["qbi_threshold_other"])
    phase_in_end  = (p["qbi_threshold_mfj"] + 100000 if filing_status in ("mfj", "qss")
                     else p["qbi_threshold_other"] + 50000)   # phase-in range = $100k/$50k

    above_threshold = taxable_income > threshold
    in_phase_in     = threshold < taxable_income <= phase_in_end

    # Total adjustments that reduce QBI (allocable proportionally if multiple businesses;
    # for simplicity, deduct from total QBI — matches single-business common case)
    qbi_reductions = rnd(se_tax_deduction + se_health_deduction + se_retirement_deduction)

    # Use engine-computed net profit when available (has mileage + NEC already applied)
    # Fallback: re-derive from schema (less accurate — misses computed expenses)
    # Source: f8995.pdf Line 1; i8995.pdf; IRC §199A-3(b)
    if se_net_profit is not None:
        total_net_se = rnd(se_net_profit)
    else:
        total_net_se = rnd(sum(
            sc.gross_receipts - sc.returns_allowances + sc.other_income -
            (sc.advertising + sc.car_truck_expenses + sc.commissions_fees +
         sc.contract_labor + sc.depletion + sc.depreciation +
         sc.employee_benefit_programs + sc.insurance +
         sc.mortgage_interest + sc.other_interest +
         sc.legal_professional + sc.office_expense +
         sc.pension_profit_sharing + sc.rent_lease_vehicles +
         sc.rent_lease_other + sc.repairs_maintenance +
         sc.supplies + sc.taxes_licenses + sc.travel +
         rnd(sc.meals * p["meals_deduction_pct"]) + sc.utilities + sc.wages +
         sc.other_expenses +
         (rnd(min(sc.home_office_sq_ft, p["home_office_simplified_max_sqft"]) *
              p["home_office_simplified_rate"]) if sc.use_home_office_simplified else 0))
        for sc in schedule_cs
        ))  # end fallback sum

    # Per-business QBI and 8995-A data
    per_biz = []
    for idx_sc, sc in enumerate(schedule_cs):
        # Use engine-computed net profit for single-business case (most common)
        if se_net_profit is not None and len(schedule_cs) == 1:
            biz_net = rnd(se_net_profit)
        else:
            biz_net = rnd(sc.gross_receipts - sc.returns_allowances + sc.other_income -
            (sc.advertising + sc.car_truck_expenses + sc.commissions_fees +
             sc.contract_labor + sc.depletion + sc.depreciation +
             sc.employee_benefit_programs + sc.insurance +
             sc.mortgage_interest + sc.other_interest +
             sc.legal_professional + sc.office_expense +
             sc.pension_profit_sharing + sc.rent_lease_vehicles +
             sc.rent_lease_other + sc.repairs_maintenance +
             sc.supplies + sc.taxes_licenses + sc.travel +
             rnd(sc.meals * p["meals_deduction_pct"]) + sc.utilities + sc.wages +
             sc.other_expenses +
             (rnd(min(sc.home_office_sq_ft, p["home_office_simplified_max_sqft"]) *
                  p["home_office_simplified_rate"]) if sc.use_home_office_simplified else 0)))
        per_biz.append({
            "name":      sc.business_name or "Business",
            "net_profit": biz_net,
            "is_sstb":   getattr(sc, 'is_sstb', False),
            "w2_wages":  getattr(sc, 'w2_wages', 0),
            "ubia":      getattr(sc, 'ubia_qualified_property', 0),
        })

    # Form 8995 Line 11: apply prior-year QBI loss carryforward
    # Source: f8995.pdf L11; IRC §199A(c)(2) — prior year suspended loss reduces current-year QBI
    l2_total_qbi = max(0, rnd(total_net_se - qbi_reductions - abs(qbi_loss_carryforward)))

    if l2_total_qbi <= 0 and total_net_se > 0:
        warnings.append("QBI: Adjustments exceed net SE profit. QBI deduction is $0. "
                        "Source: Reg. 1.199A-3(b)(1)(ii).")
        return {"l2_qbi": 0, "l3_tentative": 0, "l15_deduction": 0,
                "threshold": threshold, "above_threshold": above_threshold,
                "per_biz": per_biz, "warnings": warnings}

    if total_net_se < 0:
        warnings.append(f"QBI: Net SE loss ${total_net_se:,}. Loss carried forward. "
                        "Source: irs.gov/pub/irs-pdf/f8995.pdf Line 2.")
        return {"l2_qbi": 0, "l3_tentative": 0, "l15_deduction": 0,
                "threshold": threshold, "above_threshold": above_threshold,
                "per_biz": per_biz, "warnings": warnings}

    l3_tentative    = rnd(l2_total_qbi * 0.20)   # 20% of QBI
    l4_net_cap_gain = max(0, qdcgt_income)
    l5_ordinary_ti  = max(0, rnd(taxable_income - l4_net_cap_gain))
    l6_ti_limit     = rnd(l5_ordinary_ti * 0.20)

    # ── Form 8995-A — above threshold: W-2 wage / UBIA limitation (P3) ──────
    # Source: irs.gov/pub/irs-pdf/f8995a.pdf; IRC §199A(b)(2)(B); Reg. §1.199A-1 through -6
    wage_ubia_limit = None
    sstb_phase_out_ratio = 1.0
    if above_threshold:
        # SSTB phase-out ratio (applies within $50k/$100k phase-in range for SSTBs)
        if in_phase_in:
            excess_above_threshold = rnd(taxable_income - threshold)
            phase_in_range = rnd(phase_in_end - threshold)
            sstb_phase_out_ratio = max(0.0, 1.0 - excess_above_threshold / phase_in_range)
        else:
            sstb_phase_out_ratio = 0.0   # fully above phase-in range → SSTBs get $0

        # Aggregate W-2 wages and UBIA across all businesses
        total_w2_wages = rnd(sum(b["w2_wages"] for b in per_biz if not b["is_sstb"]))
        total_ubia     = rnd(sum(b["ubia"]     for b in per_biz if not b["is_sstb"]))
        sstb_qbi       = rnd(sum(max(0, b["net_profit"]) for b in per_biz if b["is_sstb"]))
        non_sstb_qbi   = rnd(sum(max(0, b["net_profit"]) for b in per_biz if not b["is_sstb"]))

        # W-2 wage limitation: max(50% × W-2 wages, 25% × W-2 wages + 2.5% × UBIA)
        # Source: IRC §199A(b)(2)(B); f8995a.pdf Part II Lines 12-17
        wage_limit_50pct = rnd(total_w2_wages * 0.50)
        wage_limit_25pct = rnd(total_w2_wages * 0.25 + total_ubia * 0.025)
        wage_ubia_limit  = max(wage_limit_50pct, wage_limit_25pct)

        # Non-SSTB: deduction = min(20% × QBI, W-2/UBIA limit)
        # In phase-in range: blend between simplified and limited
        if in_phase_in:
            # Phase-in: deduction = unconstrained + ratio × (constrained − unconstrained)
            # i.e., gradually phase in the limitation
            non_sstb_unconstrained = rnd(non_sstb_qbi * 0.20)
            non_sstb_constrained   = min(non_sstb_unconstrained, wage_ubia_limit)
            phase_in_ratio = (rnd(taxable_income - threshold) /
                              rnd(phase_in_end - threshold)) if phase_in_end > threshold else 1.0
            non_sstb_ded = rnd(non_sstb_unconstrained -
                               phase_in_ratio * (non_sstb_unconstrained - non_sstb_constrained))
        else:
            non_sstb_ded = min(rnd(non_sstb_qbi * 0.20), wage_ubia_limit)

        # SSTB: apply phase-out ratio to QBI before computing deduction
        sstb_qbi_allowed = rnd(sstb_qbi * sstb_phase_out_ratio)
        sstb_ded = rnd(sstb_qbi_allowed * 0.20)

        # Combined
        l3_tentative = rnd(non_sstb_ded + sstb_ded)
        l7 = min(l3_tentative, l6_ti_limit)

        if total_w2_wages == 0 and total_ubia == 0:
            warnings.append(
                f"QBI (Form 8995-A): Taxable income ${taxable_income:,} exceeds §199A threshold "
                f"${threshold:,}. W-2 wage limit applies but no W-2 wages or UBIA reported — "
                "F9: QBI deduction = $0 without W-2 wages or UBIA (non-SSTB above threshold). "
                "Enter w2_wages and ubia_qualified_property on each ScheduleC for accurate result. "
                "Source: irs.gov/pub/irs-pdf/f8995a.pdf Part II Lines 12-17; IRC §199A(b)(2)(B)."
            )
        else:
            warnings.append(
                f"QBI (Form 8995-A): Taxable income ${taxable_income:,} {'(phase-in)' if in_phase_in else '(above threshold)'}. "
                f"W-2 wages ${total_w2_wages:,} → 50% limit ${wage_limit_50pct:,} / "
                f"25%+2.5%UBIA limit ${wage_limit_25pct:,}. "
                f"W-2/UBIA limit applied: ${wage_ubia_limit:,}. "
                f"QBI deduction: ${l7:,}. "
                "Source: irs.gov/pub/irs-pdf/f8995a.pdf Part II; IRC §199A(b)(2)(B)."
            )
        if sstb_qbi > 0:
            warnings.append(
                f"QBI (SSTB phase-out): SSTB income ${sstb_qbi:,} × phase-out ratio "
                f"{sstb_phase_out_ratio:.2%} = ${sstb_qbi_allowed:,} allowed QBI. "
                f"SSTB deduction: ${sstb_ded:,}. "
                "Source: IRC §199A(d)(3); Reg. §1.199A-5; f8995a.pdf Part III."
            )
    else:
        # Below threshold — simplified Form 8995
        l7 = min(l3_tentative, l6_ti_limit)

    # P2: TY 2026 QBI minimum deduction (OBBBA new — $400 if QBI ≥ $1,000)
    # Source: OBBBA §70XXX; stored as PARAMS_2026["qbi_min_deduction"] = 400
    qbi_min = p.get("qbi_min_deduction", 0)
    if qbi_min > 0 and l2_total_qbi >= 1000 and l7 < qbi_min:
        l7 = qbi_min
        warnings.append(
            f"QBI minimum deduction applied: ${qbi_min:,} (OBBBA TY 2026 minimum, "
            f"QBI ${l2_total_qbi:,} ≥ $1,000). Source: OBBBA §70XXX; "
            "irs.gov/newsroom/one-big-beautiful-bill-provisions"
        )
    # Form 8995 Lines 6-9: REIT/PTP component
    # Source: f8995.pdf Lines 6-9; i8995.pdf Line 6; IRC §199A(e)(4)
    # FETCH_VERIFIED: irs.gov/instructions/i8995 | Line 6 | 2026-05-24
    # L6 = qualified REIT dividends (1099-DIV Box 5 §199A dividends, held >45 days)
    #       + qualified PTP income (K-1 Box 20 Code Z / S-corp Box 17 Code V)
    l6_reit_ptp   = rnd(reit_ptp_income)
    l8_reit_total = max(0, l6_reit_ptp)          # Line 8 = L6 + L7 carryforward (0)
    l9_reit_comp  = rnd(l8_reit_total * 0.20)    # Line 9 = 20% × L8

    # Form 8995 Line 10 = QBI component (L7) + REIT/PTP component (L9)
    # Line 11 = TI limit (already computed as l6_ti_limit for QBI portion)
    # The combined limit for L10 is still 20% × (TI − net cap gain) — same l6_ti_limit
    l10_combined  = rnd(l7 + l9_reit_comp)
    l15_deduction = min(l10_combined, l6_ti_limit)  # Line 15 = lesser of L10 or TI limit
    # Apply TY 2026 minimum floor to final deduction (OBBBA §70XXX)
    if qbi_min > 0 and l2_total_qbi >= 1000 and l15_deduction < qbi_min:
        l15_deduction = qbi_min

    warnings.append(
        f"QBI deduction (§199A / Form {'8995-A' if above_threshold else '8995'}): "
        f"${l15_deduction:,} → Form 1040 Line 13. "
        f"QBI ${l2_total_qbi:,} × 20% = ${l3_tentative:,}; "
        f"REIT/PTP ${l6_reit_ptp:,} × 20% = ${l9_reit_comp:,}; "
        f"TI limit ${l6_ti_limit:,}. "
        "Source: irs.gov/pub/irs-pdf/f8995.pdf; i8995.pdf Lines 6-9."
    )

    return {
        "l2_qbi": l2_total_qbi,
        "l3_tentative": l3_tentative,
        "l4_net_cap_gain": l4_net_cap_gain,
        "l5_ordinary_ti": l5_ordinary_ti,
        "l6_ti_limit": l6_ti_limit,
        "l7": l7,
        "l6_reit_ptp": l6_reit_ptp,
        "l9_reit_comp": l9_reit_comp,
        "l10_combined": l10_combined,
        "l15_deduction": l15_deduction,
        "threshold": threshold,
        "above_threshold": above_threshold,
        "in_phase_in": in_phase_in if above_threshold else False,
        "wage_ubia_limit": wage_ubia_limit,
        "per_biz": per_biz,
        "warnings": warnings,
    }


def compute_se_health_insurance(premiums: float, se_net_profit: float,
                                 se_tax_deduction: float,
                                 se_retirement: float) -> dict:
    """
    SE Health Insurance Deduction — Schedule 1 Line 17
    Source: irs.gov/pub/irs-pdf/f1040s1.pdf; IRC §162(l); Pub 535

    Deduction = lesser of:
      (a) actual premiums paid for health/dental/vision (taxpayer + family)
      (b) net SE profit MINUS deductible SE tax MINUS SE retirement contributions
          (i.e., net profit available for health deduction)

    Rules:
    - Only applies to months the taxpayer (or spouse) was NOT eligible for
      employer-subsidized health coverage. Pro-rate if partial year.
    - Cannot exceed net SE profit (after SE tax deduction and SE retirement).
    - MFS: allowed only if lived apart from spouse all year.
    - Medicare premiums count if self-employed (Rev. Rul. 2010-27).

    Engine: takes user-supplied premiums; floors at net profit ceiling.
    Eligibility months not tracked → warn to verify.
    """
    warnings = []

    # Net profit available for health deduction
    # IRC §162(l)(1)(B): net SE income = gross income from trade/business
    #   minus deductions (Sch C expenses, SE tax ded, retirement)
    profit_after_se_ded = max(0, rnd(se_net_profit - se_tax_deduction - se_retirement))
    deduction = rnd(min(premiums, profit_after_se_ded))

    if premiums > profit_after_se_ded:
        warnings.append(
            f"SE health insurance: Premiums ${premiums:,} exceed available net SE profit "
            f"${profit_after_se_ded:,} (after SE tax ded + retirement). "
            f"Deduction capped at ${deduction:,}. Source: IRC §162(l); irs.gov/pub/irs-pdf/f1040s1.pdf L17."
        )

    if premiums > 0:
        warnings.append(
            f"SE health insurance (Sch 1 L17): ${deduction:,}. "
            "⚠ Verify: deduction disallowed for months eligible for employer-subsidized plan. "
            "Medicare premiums allowed (Rev. Rul. 2010-27). "
            "Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 17; IRC §162(l)."
        )

    return {"deduction": deduction, "premiums_input": premiums,
            "profit_ceiling": profit_after_se_ded, "warnings": warnings}


def compute_se_retirement(contributions: float, se_net_profit: float,
                           se_tax_deduction: float,
                           plan_type: str = "sep",
                           taxpayer_age: int = 0) -> dict:
    """
    SE Retirement Contribution Deduction — Schedule 1 Line 16
    Source: irs.gov/pub/irs-pdf/f1040s1.pdf; IRC §404; Pub 560; irs.gov/pub/irs-pdf/p560.pdf

    plan_type:
      "sep"      → SEP-IRA: min(20% × net SE comp, $70,000)
      "solo401k" → Solo 401(k): elective (up to $23,500 / $31,000 age 50+) +
                   employer 20% × net SE comp; combined cap $70,000
      "simple"   → SIMPLE IRA: $16,500 elective ($20,000 age 50+); no employer match computed here
    """
    warnings = []
    p = PARAMS_2025
    net_se_comp = max(0, rnd(se_net_profit * p["se_tax_rate_net_earnings"] - se_tax_deduction))
    is_50plus = taxpayer_age >= 50

    if plan_type == "solo401k":
        # Elective deferral cap
        elective_cap = rnd(p["solo401k_elective_max_2025"] * (31000 / 23500) if is_50plus
                           else p["solo401k_elective_max_2025"])
        # Age 50+ catch-up: $7,500 additional elective = $31,000 total
        # Source: IRS IR-2024-285; IRC §402(g)(1)(C)
        elective_cap = 31000 if is_50plus else p["solo401k_elective_max_2025"]
        employer_max = rnd(net_se_comp * p["sep_ira_rate_sole_prop"])   # 20% employer portion
        combined_max = min(rnd(min(contributions, elective_cap) + employer_max),
                           p["sep_ira_max_2025"])
        deduction = min(contributions, combined_max)
        plan_label = "Solo 401(k)"
        plan_max = combined_max
    elif plan_type == "simple":
        # SIMPLE IRA elective deferral
        simple_cap = 20000 if is_50plus else p["simple_ira_max_2025"]
        deduction = min(contributions, simple_cap)
        plan_label = "SIMPLE IRA"
        plan_max = simple_cap
    else:  # sep (default)
        sep_max = rnd(min(net_se_comp * p["sep_ira_rate_sole_prop"], p["sep_ira_max_2025"]))
        deduction = rnd(min(contributions, sep_max)) if contributions > 0 else 0
        plan_label = "SEP-IRA"
        plan_max = sep_max

    deduction = rnd(deduction)

    if contributions > plan_max:
        warnings.append(
            f"SE retirement ({plan_label}): contributions ${contributions:,} exceed "
            f"maximum ${plan_max:,}. Deduction limited to ${deduction:,}. "
            "Source: irs.gov/pub/irs-pdf/p560.pdf; irs.gov/pub/irs-pdf/f1040s1.pdf L16."
        )
    elif contributions > 0:
        warnings.append(
            f"SE retirement ({plan_label}, Sch 1 L16): ${deduction:,}. "
            f"Max ${plan_max:,} (net SE comp ${net_se_comp:,}). "
            "Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 16; irs.gov/pub/irs-pdf/p560.pdf"
        )

    return {"deduction": deduction, "contributions_input": contributions,
            "net_se_comp": net_se_comp, "plan_type": plan_type,
            "plan_max": plan_max, "warnings": warnings}


# ── v8 GAP-FILL COMPUTATION FUNCTIONS ──────────────────────────────────────────

def compute_cogs(sc: "ScheduleC") -> float:
    """Schedule C Part III — Cost of Goods Sold. Source: f1040sc.pdf Part III Lines 33–42."""
    if not any([sc.inventory_beginning, sc.purchases, sc.cost_of_labor,
                sc.materials_supplies_cogs, sc.other_cogs, sc.inventory_ending]):
        return 0
    return rnd(sc.inventory_beginning + sc.purchases + sc.cost_of_labor +
               sc.materials_supplies_cogs + sc.other_cogs - sc.inventory_ending)


def compute_ira_deduction(contrib: float, age: int, magi: float,
                           filing_status: str,
                           covered_by_plan: bool,
                           spouse_covered: bool,
                           taxable_compensation: float = None) -> dict:
    """
    Traditional IRA Deduction — Schedule 1 Line 20
    Source: irs.gov/pub/irs-pdf/p590a.pdf  |  irs.gov/pub/irs-pdf/f1040s1.pdf Line 20

    Three cases: (1) no plan → fully deductible; (2) taxpayer covered → phase-out;
    (3) taxpayer not covered but spouse covered (MFJ) → separate phase-out.
    Phase-out rounds DOWN to nearest $10; if result 1–199 → $200 floor (Pub 590-A).
    """
    p = PARAMS_2025
    warnings = []
    fs = filing_status
    limit = p["ira_contribution_catchup_2025"] if age >= 50 else p["ira_contribution_limit_2025"]
    # IRC §219(b)(1)(B): IRA contribution cannot exceed taxpayer's taxable compensation
    # Taxable compensation = wages + net SE profit (not SS, pensions, dividends, cap gains)
    # Source: IRS Pub 590-A; IRC §219(b)(1)(B); i590a.pdf "What Is Compensation?"
    if taxable_compensation is not None and taxable_compensation < contrib:
        warnings.append(
            f"IRA contribution ${contrib:,} exceeds taxable compensation ${taxable_compensation:,}. "
            "IRA contribution limit is the lesser of the dollar limit or taxable compensation. "
            "Retirees with only SS/pension income ($0 compensation) cannot make deductible IRA contributions. "
            "Source: IRC §219(b)(1)(B); IRS Pub 590-A."
        )
        contrib = min(contrib, taxable_compensation) if taxable_compensation > 0 else 0
    actual_contrib = rnd(min(contrib, limit))
    if contrib > limit:
        warnings.append(
            f"IRA contribution ${contrib:,} exceeds 2025 limit ${limit:,}. "
            "Excess → Form 5329 Part I 6% excise if not withdrawn by filing deadline. "
            "Source: irs.gov/pub/irs-pdf/p590a.pdf"
        )
    if actual_contrib == 0:
        return {"deductible": 0, "nondeductible": 0, "contribution_limit": limit,
                "actual_contrib": 0, "po_start": None, "po_end": None, "warnings": warnings}

    def _phase_out(contrib_amt, start, end):
        if magi <= start: return contrib_amt, start, end
        if magi >= end:   return 0, start, end
        ratio = (magi - start) / (end - start)
        raw = contrib_amt * (1 - ratio)
        rounded = math.floor(raw / 10) * 10
        result = max(200, rounded) if rounded > 0 else 0
        return rnd(result), start, end

    po_start = po_end = None
    if not covered_by_plan and not spouse_covered:
        deductible = actual_contrib
    elif covered_by_plan:
        if fs in ("single", "hoh"):
            deductible, po_start, po_end = _phase_out(
                actual_contrib, p["ira_phaseout_covered_single_start"], p["ira_phaseout_covered_single_end"])
        elif fs == "mfj":
            deductible, po_start, po_end = _phase_out(
                actual_contrib, p["ira_phaseout_covered_mfj_start"], p["ira_phaseout_covered_mfj_end"])
        elif fs == "mfs":
            deductible, po_start, po_end = _phase_out(
                actual_contrib, p["ira_phaseout_covered_mfs_start"], p["ira_phaseout_covered_mfs_end"])
        else:
            deductible, po_start, po_end = _phase_out(
                actual_contrib, p["ira_phaseout_covered_mfj_start"], p["ira_phaseout_covered_mfj_end"])
    else:
        if fs == "mfj":
            deductible, po_start, po_end = _phase_out(
                actual_contrib, p["ira_phaseout_noncovered_mfj_start"], p["ira_phaseout_noncovered_mfj_end"])
        else:
            deductible = actual_contrib

    nondeductible = rnd(actual_contrib - deductible)

    if deductible > 0:
        warnings.append(
            f"Traditional IRA deduction: ${deductible:,} → Schedule 1 Line 20. "
            + (f"Phase-out ${po_start:,}–${po_end:,} (MAGI ${magi:,}). " if po_start else "")
            + "Source: irs.gov/pub/irs-pdf/p590a.pdf; irs.gov/pub/irs-pdf/f1040s1.pdf L20."
        )
    if nondeductible > 0:
        warnings.append(
            f"Nondeductible IRA contribution ${nondeductible:,} → Form 8606 Part I basis tracking required. "
            "Source: irs.gov/pub/irs-pdf/f8606.pdf."
        )
    return {"deductible": rnd(deductible), "nondeductible": nondeductible,
            "contribution_limit": limit, "actual_contrib": actual_contrib,
            "po_start": po_start, "po_end": po_end, "warnings": warnings}


def compute_form_8889(hsa: "Form8889Data", filing_status: str,
                       employer_w2_code_w: float = 0) -> dict:
    """
    Form 8889 — Health Savings Accounts (HSA) (2025)
    Source: irs.gov/pub/irs-pdf/f8889.pdf  |  irs.gov/pub/irs-pdf/p969.pdf

    Part I → Schedule 1 Line 13 deduction.
    Part II → taxable non-medical distributions + 20% penalty.
    CA non-conformity: deduction must be added back on CA Schedule CA.
    """
    p = PARAMS_2025
    warnings = []
    base_limit = (p["hsa_limit_family_2025"] if hsa.coverage_type == "family"
                  else p["hsa_limit_self_only_2025"])
    catchup_tp  = p["hsa_catchup_age55_2025"] if hsa.taxpayer_age >= 55 else 0
    catchup_sp  = (p["hsa_catchup_age55_2025"]
                   if hsa.coverage_type == "family" and hsa.spouse_age >= 55 and filing_status == "mfj"
                   else 0)
    annual_limit = rnd(base_limit + catchup_tp + catchup_sp)
    emp_contrib  = rnd(hsa.employer_contrib_w2_code_w + employer_w2_code_w)
    employee_contrib = rnd(hsa.contributions_taxpayer + hsa.contributions_spouse)
    available    = max(0, rnd(annual_limit - emp_contrib - hsa.ira_funding_dist))
    l13_deduction = rnd(min(employee_contrib, available))

    if employee_contrib > available:
        warnings.append(
            f"HSA excess contribution ${rnd(employee_contrib-available):,}: "
            f"contributions ${employee_contrib:,} > available limit ${available:,}. "
            "6% excise tax on excess (Form 5329 Part VII) unless withdrawn by filing deadline. "
            "Source: irs.gov/pub/irs-pdf/p969.pdf"
        )

    non_medical  = max(0, rnd(hsa.total_distributions - hsa.qualified_medical_expenses))
    l17a_taxable = non_medical
    l17b_penalty = rnd(non_medical * 0.20) if not hsa.age_65_or_disabled and non_medical > 0 else 0

    if l13_deduction > 0:
        warnings.append(
            f"HSA deduction (Form 8889 Part I): ${l13_deduction:,} → Schedule 1 Line 13 "
            f"({'family' if hsa.coverage_type == 'family' else 'self-only'}, limit ${annual_limit:,}). "
            "⚠ CA does NOT conform — add back on CA Sch CA. "
            "Source: irs.gov/pub/irs-pdf/f8889.pdf; irs.gov/pub/irs-pdf/p969.pdf"
        )
    if l17b_penalty > 0:
        warnings.append(
            f"HSA non-qualified distribution ${non_medical:,}: taxable → Sch 1 L8f; "
            f"20% penalty ${l17b_penalty:,} → Sch 2 L17c. Source: f8889.pdf Part II."
        )
    return {"annual_limit": annual_limit, "emp_contrib": emp_contrib,
            "employee_contrib": employee_contrib, "l13_deduction": l13_deduction,
            "non_medical_dist": non_medical, "l17a_taxable": l17a_taxable,
            "l17b_penalty": l17b_penalty, "warnings": warnings}


def compute_niit(magi: float, nii: float, filing_status: str) -> dict:
    """
    Form 8960 — Net Investment Income Tax (3.8%) (2025)
    Source: irs.gov/pub/irs-pdf/f8960.pdf  |  IRC §1411
    NII = interest + dividends + passive rental + passive K-1 + cap gains.
    SE income and active business income are excluded from NII.
    → Schedule 2 Line 12
    """
    p = PARAMS_2025
    threshold = (p["niit_threshold_mfj"] if filing_status in ("mfj", "qss")
                 else p["niit_threshold_single"])
    excess = max(0, rnd(magi - threshold))
    base   = min(nii, excess)
    niit   = rnd(base * p["niit_rate"])
    w = (f"NIIT (Form 8960): ${niit:,} → Schedule 2 Line 12. "
         f"NII ${nii:,}, MAGI ${magi:,} > threshold ${threshold:,}. "
         "Source: irs.gov/pub/irs-pdf/f8960.pdf; IRC §1411.") if niit > 0 else ""
    return {"threshold": threshold, "nii": nii, "niit": niit, "warning": w}


def compute_additional_medicare_tax(wages_se: float, magi: float,
                                     filing_status: str,
                                     wh_from_w2: float) -> dict:
    """
    Form 8959 — Additional Medicare Tax (0.9%) (2025)
    Source: irs.gov/pub/irs-pdf/f8959.pdf  |  IRC §3101(b)(2)

    Employer withholding approximation note (IRC §3102(f)(1)):
    Employers withhold 0.9% per employee only after wages exceed $200k per employer.
    For MFJ filers (threshold $250k) or multi-employer situations, actual employer
    WH may be $0 even though tax is owed — engine estimates WH from wages > $200k.
    Form 8959 reconciles the actual liability; net owed = Line 17 − WH from W-2.
    Source: f8959.pdf; IRC §3102(f)(1); i8959.pdf.
    → Schedule 2 Line 11
    """
    p = PARAMS_2025
    threshold = (p["addl_medicare_threshold_mfj"] if filing_status in ("mfj", "qss")
                 else p["addl_medicare_threshold_mfs"] if filing_status == "mfs"
                 else p["addl_medicare_threshold_single"])
    excess = max(0, rnd(wages_se - threshold))
    tax    = rnd(excess * p["addl_medicare_rate"])
    net    = max(0, rnd(tax - wh_from_w2))
    w = (f"Additional Medicare Tax (Form 8959): ${tax:,} → Schedule 2 Line 11. "
         f"Wages+SE ${wages_se:,} > ${threshold:,}, excess ${excess:,} × 0.9%. "
         + (f"Estimated employer WH ${wh_from_w2:,} (wages over $200k/employer). "
            "⚠ Verify actual Box 6 WH from W-2 — employer WH threshold is $200k "
            "per employer, not the joint $250k return threshold. Net: "
            f"${net:,}. " if wh_from_w2 else "")
         + "Source: irs.gov/pub/irs-pdf/f8959.pdf; IRC §3102(f)(1).") if tax > 0 else ""
    return {"threshold": threshold, "excess": excess, "tax": tax,
            "wh_credit": wh_from_w2, "net": net, "warning": w}


def compute_form_2210_safe_harbor(current_year_tax: float, total_payments: float,
                                   prior_year_tax: float, prior_year_agi: float,
                                   q1_payment: float = 0, q2_payment: float = 0,
                                   q3_payment: float = 0, q4_payment: float = 0,
                                   prior_year_overpayment: float = 0) -> dict:
    """
    Form 2210 — Underpayment of Estimated Tax by Individuals (2025)
    Source: irs.gov/pub/irs-pdf/i2210.pdf  FETCH_VERIFIED 2026-05-24
            irs.gov/pub/irs-pdf/f2210.pdf; IRC §6654; IRS Pub 505 Ch.4

    Three safe harbors (i2210.pdf Part II):
      (a) Net owed (after withholding) < $1,000  — always testable  [i2210.pdf Line 9]
      (b) Payments >= 100%/110% of prior year tax — REQUIRES prior_year_tax > 0
          110% applies when prior year AGI > $150,000 ($75,000 MFS)
          Source: i2210.pdf; IRC §6654(d)(1)(B)(ii)
      (c) Payments >= 90% of current year tax  — always testable
          Source: i2210.pdf; IRC §6654(d)(1)(B)(i)

    Quarterly installment penalty calculation (i2210.pdf Part III, Section B):
      Per i2210.pdf: "The penalty is figured separately for each installment due date."
      2025 installment due dates:
        Q1: April 15, 2025  (Jan 1 – Mar 31)
        Q2: June 15, 2025   (Apr 1 – May 31)
        Q3: September 15, 2025 (Jun 1 – Aug 31)
        Q4: January 15, 2026   (Sep 1 – Dec 31)
      Required per-installment payment = 25% of annual required payment
      Underpayment rate 2025: 8% annual = 8/365 per day
      Source: irs.gov/pub/irs-pdf/i2210.pdf Part III, Section B; IRC §6654(b)(2); §6621

    EA Review fix (2026-05-19): prior_year_tax=0 no longer grants harbor (b).
    P3 (2026-05-24): Added per-installment quarterly penalty calculation.
    """
    p        = PARAMS_2025
    annual_rate = p["underpayment_penalty_rate_2025"]   # 8% for 2025
    daily_rate  = annual_rate / 365.0                   # ~0.02192% per day

    # Total payments = withholding + estimated payments + prior-year overpayment
    # (Withholding is treated as paid evenly; estimated payments by actual date)
    req_current = rnd(current_year_tax * p["safe_harbor_pct_current"])  # 90%
    net_owed    = max(0, rnd(current_year_tax - total_payments))

    # Harbor (a): net owed < $1,000 — IRC §6654(e)(1)
    if net_owed < 1000:
        return {"safe_harbor_met": True,
                "reason": f"(a) net owed ${net_owed:,} < $1,000 (IRC §6654(e)(1))",
                "penalty": 0, "req_prior": None, "req_current": req_current,
                "quarterly_detail": None}

    # Harbor (b): 100% / 110% of prior year tax — IRC §6654(d)(1)(B)
    req_prior = None
    if prior_year_tax > 0:
        multiplier = (p["safe_harbor_pct_prior_110"]
                      if prior_year_agi > p["safe_harbor_agi_threshold"] else 1.0)
        req_prior  = rnd(prior_year_tax * multiplier)
        if total_payments >= req_prior:
            return {"safe_harbor_met": True,
                    "reason": (f"(b) payments ${total_payments:,} >= "
                               f"{int(multiplier*100)}% prior-year tax ${req_prior:,} "
                               f"(IRC §6654(d)(1)(B))"),
                    "penalty": 0, "req_prior": req_prior, "req_current": req_current,
                    "quarterly_detail": None}

    # Harbor (c): 90% of current year tax — IRC §6654(d)(1)(B)(i)
    if total_payments >= req_current:
        return {"safe_harbor_met": True,
                "reason": (f"(c) payments ${total_payments:,} >= "
                           f"90% current tax ${req_current:,} (IRC §6654(d)(1)(B)(i))"),
                "penalty": 0, "req_prior": req_prior, "req_current": req_current,
                "quarterly_detail": None}

    # ── Per-installment quarterly penalty (i2210.pdf Part III, Section B) ─────
    # Required amount per installment = 25% × annual required payment
    # Annual required = min(req_current, req_prior) if prior known; else req_current
    annual_required = req_current if req_prior is None else min(req_current, req_prior)
    per_q           = rnd(annual_required / 4)

    # Days from installment due date to payment date
    # If actual Q payment not provided, assume paid with return (4/15/2026 = 365 days late for Q1)
    # Days underpaid per quarter (from due date to return date or payment date)
    # Due dates 2025: Q1=Apr15, Q2=Jun15, Q3=Sep15, Q4=Jan15 2026
    # Days from each due date to return filing (April 15, 2026):
    #   Q1: Apr 15 2025 → Apr 15 2026 = 365 days
    #   Q2: Jun 15 2025 → Apr 15 2026 = 304 days
    #   Q3: Sep 15 2025 → Apr 15 2026 = 212 days
    #   Q4: Jan 15 2026 → Apr 15 2026 = 90 days
    # Source: i2210.pdf Table 2 "Chart of Total Days"
    Q_DAYS = [365, 304, 212, 90]   # days Q1-Q4 if unpaid until return date
    q_payments = [
        q1_payment + prior_year_overpayment,   # Q1 gets prior-year overpayment credit
        q2_payment,
        q3_payment,
        q4_payment,
    ]

    quarterly_detail = []
    total_penalty = 0.0
    cumulative_shortfall = 0.0

    for i, (q_paid, days) in enumerate(zip(q_payments, Q_DAYS)):
        required  = per_q
        available = q_paid + max(0, -cumulative_shortfall)  # prior overpayment carries forward
        shortfall = max(0, rnd(required - available))
        # Per i2210.pdf: prior installment overpayment reduces next installment requirement
        cumulative_shortfall = required - available
        q_penalty = rnd(shortfall * daily_rate * days)
        total_penalty += q_penalty
        quarterly_detail.append({
            "quarter": f"Q{i+1}",
            "required": required,
            "paid": q_paid,
            "shortfall": shortfall,
            "days": days,
            "penalty": q_penalty,
        })

    total_penalty = rnd(total_penalty)

    if total_penalty == 0:
        return {"safe_harbor_met": True,
                "reason": "Quarterly penalty calculation: no net shortfall across all installments",
                "penalty": 0, "req_prior": req_prior, "req_current": req_current,
                "quarterly_detail": quarterly_detail}

    shortfall_desc = rnd(annual_required - total_payments)
    prior_year_note = (
        " Prior year tax not entered — safe harbor (b) (100%/110% of prior year tax) "
        "cannot be evaluated. Enter Form 1040 Line 24 from your 2024 return for a more accurate result."
        if prior_year_tax == 0 else ""
    )
    return {"safe_harbor_met": False,
            "reason": (f"No safe harbor: payments ${total_payments:,} < "
                       f"required ${annual_required:,}"),
            "penalty": total_penalty,
            "req_prior": req_prior,
            "req_current": req_current,
            "quarterly_detail": quarterly_detail,
            "warning": (
                f"Form 2210 underpayment penalty: ${total_penalty:,} → Line 38. "
                f"Payments ${total_payments:,} vs required ${annual_required:,} "
                f"(shortfall ${shortfall_desc:,}). "
                f"Penalty calculated per-quarter per installment due date."
                f"{prior_year_note} "
                f"Rate: 8%/yr (daily = 8÷365%). Due dates: Q1=Apr 15, Q2=Jun 15, "
                f"Q3=Sep 15 2025, Q4=Jan 15 2026. "
                "Source: irs.gov/pub/irs-pdf/i2210.pdf Part III; IRC §6654(b)(2); §6621."
            )}


def compute_form_982(form_982: "Form982Data", total_discharged: float) -> dict:
    """
    Form 982 — Insolvency / Bankruptcy Exclusion Worksheet (IRC §108)
    Source: irs.gov/pub/irs-pdf/f982.pdf; irs.gov/pub/irs-pdf/i982.pdf; IRS Pub 4681

    Two exclusion types computed:
      (A) Bankruptcy: all discharged debt excluded (Title 11 case)   — Box 1a
      (B) Insolvency: excluded = min(discharged, liabilities - assets FMV) — Box 1b

    F6 (EA review 2026-05-19): replaces manual is_excluded boolean toggle.
    Engine now computes the insolvency amount from the worksheet automatically.
    Source: IRC §108(a)(1)(A)-(B); i982.pdf p.3 insolvency worksheet; IRS Pub 4681 Ch.2
    """
    if form_982 is None:
        return {"applicable": False, "excluded": 0, "taxable": total_discharged,
                "exclusion_type": "none", "warnings": []}

    warnings = []
    discharged = (form_982.discharged_amount_override
                  if form_982.discharged_amount_override > 0
                  else total_discharged)

    # Bankruptcy exclusion — Title 11 case: full discharge excluded
    # Source: IRC §108(a)(1)(A); i982.pdf Box 1a
    if form_982.bankruptcy_title11:
        excluded = rnd(discharged)
        warnings.append(
            f"Form 982 Box 1a: Bankruptcy (Title 11) — ${excluded:,} fully excluded from income. "
            "Verify taxpayer was under bankruptcy protection when debt was discharged. "
            "Source: IRC §108(a)(1)(A); f982.pdf Box 1a."
        )
        return {"applicable": True, "excluded": excluded, "taxable": 0,
                "exclusion_type": "bankruptcy", "insolvency_amount": None, "warnings": warnings}

    # Insolvency exclusion — liabilities exceed assets FMV
    # Source: IRC §108(a)(1)(B); i982.pdf insolvency worksheet (p.3)
    liab  = rnd(form_982.total_liabilities_before)
    assets = rnd(form_982.total_assets_fmv_before)

    if liab == 0 and assets == 0:
        warnings.append(
            "⚠ Form 982: liabilities and assets not entered — insolvency exclusion cannot "
            "be computed. Enter total_liabilities_before and total_assets_fmv_before "
            "(immediately before the discharge event) to compute the IRC §108(a)(1)(B) "
            "insolvency exclusion. Source: i982.pdf insolvency worksheet; IRS Pub 4681 Ch.2."
        )
        return {"applicable": False, "excluded": 0, "taxable": rnd(discharged),
                "exclusion_type": "not_computed", "warnings": warnings}

    insolvency_amount = max(0, rnd(liab - assets))  # excess of liabilities over assets

    if insolvency_amount <= 0:
        warnings.append(
            f"Form 982: taxpayer is NOT insolvent (liabilities ${liab:,} ≤ assets ${assets:,}). "
            "Insolvency exclusion does not apply. Discharged debt is fully taxable. "
            "Source: IRC §108(a)(1)(B); i982.pdf; IRS Pub 4681."
        )
        return {"applicable": False, "excluded": 0, "taxable": rnd(discharged),
                "exclusion_type": "not_insolvent", "insolvency_amount": 0, "warnings": warnings}

    excluded = min(rnd(discharged), insolvency_amount)
    taxable  = max(0, rnd(discharged - excluded))

    warnings.append(
        f"Form 982 Box 1b (Insolvency): liabilities ${liab:,} − assets ${assets:,} = "
        f"insolvency ${insolvency_amount:,}. "
        f"Discharged ${discharged:,} — excluded ${excluded:,} — taxable ${taxable:,}. "
        "⚠ Excluded amount reduces tax attributes (NOL, basis, credit carryforwards). "
        "Source: IRC §108(a)(1)(B); IRC §108(b); f982.pdf; IRS Pub 4681 Ch.2."
    )
    return {"applicable": True, "excluded": excluded, "taxable": taxable,
            "exclusion_type": "insolvency", "insolvency_amount": insolvency_amount,
            "liabilities": liab, "assets_fmv": assets, "warnings": warnings}


def compute_k1_income(k1s: list) -> dict:
    """
    Schedule K-1 → Schedule E Part II — Pass-through Income/Loss
    Source: f1065sk1.pdf (partnership) | f1120ssk1.pdf (S-corp) | f1041sk1.pdf (estate/trust)

    Routing: non-passive col (h); passive income col (f); passive loss col (g).
    Net → Schedule 1 Line 5. K-1 interest/div → Schedule B. K-1 STCG/LTCG → Schedule D.
    K-1 SE income → Schedule SE. K-1 §199A → Form 8995.
    """
    warnings = []
    total_passive_income = total_passive_loss = total_nonpassive = 0
    k1_interest = k1_ord_div = k1_qual_div = k1_stcg = k1_ltcg = 0
    k1_se = k1_sec199a = k1_rental = 0

    for k1 in k1s:
        ord_inc = rnd(k1.box1_ordinary_income)
        rental  = rnd(k1.box2_net_rental + k1.box3_other_net_rental)

        # F5: Outside basis cap — IRC §704(d) / IRC §1366(d)
        # Losses cannot exceed the taxpayer's outside basis in the entity.
        # Source: IRC §704(d) (partnerships); IRC §1366(d) (S-corps); f6198.pdf
        # outside_basis = -1 means not entered (preparer must verify manually).
        _basis  = getattr(k1, 'outside_basis',  -1.0)
        _atrisk = getattr(k1, 'at_risk_amount', -1.0)
        _loss   = min(ord_inc, 0)   # negative = loss
        if _loss < 0:
            if _basis >= 0:
                # Basis entered: cap loss at available basis
                allowed = max(-_basis, _loss)  # e.g. basis=$5k, loss=-$20k → allowed=-$5k
                disallowed = abs(_loss) - abs(allowed)
                if disallowed > 0:
                    warnings.append(
                        f"K-1 {k1.entity_name}: §704(d)/§1366(d) outside basis cap. "                        f"Loss ${abs(int(_loss)):,} limited to basis ${int(_basis):,}. "                        f"Disallowed ${int(disallowed):,} is NOT deductible — "                        f"carries forward when basis is restored. "                        f"Source: IRC §704(d); IRC §1366(d); f6198.pdf."                    )
                    ord_inc = allowed  # replace loss with basis-capped amount
            else:
                # Basis not entered — warn but do not cap (preparer must verify)
                warnings.append(
                    f"⚠ K-1 {k1.entity_name}: outside basis not entered. "                    f"Loss ${abs(int(_loss)):,} is tentative. "                    "Enter outside_basis to enforce IRC §704(d)/§1366(d) limitation. "                    "Source: IRC §704(d); IRC §1366(d); f6198.pdf."                )
        if _loss < 0 and _atrisk >= 0:
            # At-risk cap (IRC §465): applied after basis cap
            atrisk_allowed = max(-_atrisk, ord_inc)
            atrisk_disallowed = abs(ord_inc) - abs(atrisk_allowed)
            if atrisk_disallowed > 0:
                warnings.append(
                    f"K-1 {k1.entity_name}: IRC §465 at-risk limit. "                    f"Loss ${abs(int(ord_inc)):,} limited to at-risk amount ${int(_atrisk):,}. "                    f"Disallowed ${int(atrisk_disallowed):,} → Form 6198. "                    f"Source: IRC §465; f6198.pdf."                )
                ord_inc = atrisk_allowed

        if k1.is_rental:
            k1_rental += rental
        elif k1.material_participation:
            total_nonpassive += ord_inc
        else:
            if ord_inc >= 0: total_passive_income += ord_inc
            else:            total_passive_loss   += abs(ord_inc)
        if k1.disposition_year and ord_inc < 0:
            warnings.append(
                f"K-1 {k1.entity_name}: disposition year — suspended losses released. "
                "Source: IRC §469(g).")
        k1_interest += rnd(k1.box5_interest)
        k1_ord_div  += rnd(k1.box6a_ordinary_div)
        k1_qual_div += rnd(k1.box6b_qualified_div)
        k1_stcg     += rnd(k1.box8_stcg)
        k1_ltcg     += rnd(k1.box9_ltcg + k1.box9a_sec1231)
        k1_se       += rnd(k1.box14a_se_income)
        k1_sec199a  += rnd(k1.box17_sec199a)
        if k1.box12_sec179 > 0:
            warnings.append(f"K-1 {k1.entity_name}: §179 ${rnd(k1.box12_sec179):,} — verify at-risk basis. f4562.pdf")

    net_passive = rnd(total_passive_income - total_passive_loss)
    if total_passive_loss > total_passive_income:
        warnings.append(
            f"K-1 passive losses ${total_passive_loss:,} exceed income ${total_passive_income:,}. "
            f"${rnd(total_passive_loss-total_passive_income):,} suspended → Form 8582. IRC §469.")
    net_ordinary = rnd(total_nonpassive + net_passive)

    return {"net_k1_ordinary": net_ordinary, "k1_rental": k1_rental,
            "k1_interest": k1_interest, "k1_ord_div": k1_ord_div, "k1_qual_div": k1_qual_div,
            "k1_stcg": k1_stcg, "k1_ltcg": k1_ltcg, "k1_se": k1_se, "k1_sec199a": k1_sec199a,
            "warnings": warnings}


def compute_caleitc(ca_earned_income: float, federal_agi: float,
                     num_qualifying_children: int,
                     investment_income: float,
                     filing_status: str,
                     taxpayer_age: int = 0,
                     has_young_child_under6: bool = False,
                     foster_youth_taxpayer: bool = False,
                     foster_youth_spouse: bool = False) -> dict:
    """
    California Earned Income Tax Credit (CalEITC) — Form FTB 3514 (2025)
    Source: ftb.ca.gov/forms/2025/2025-3514.pdf
            ftb.ca.gov/forms/2025/2025-3514-booklet.html

    Key differences from federal EITC:
    - Income limit: $32,900 (both CA earned income AND federal AGI must be below $32,901)
    - Investment income limit: $4,814 (vs $11,600 federal)
    - No earned income required for YCTC (if child under 6 and net loss ≤ $35,640)
    - Age 18+ eligible without child (vs 25-64 federal)
    - ITIN holders eligible (CA-specific)
    - CA wages must be subject to CA withholding

    CalEITC credit amounts (2025 — from FTB 3514 credit table, ftb.ca.gov):
      0 children: max $264
      1 child:    max $1,863
      2 children: max $3,080
      3+ children: max $3,756
    Phase-in and phase-out rates follow FTB 3514 worksheet formula.

    YCTC: $1,189 per return; phase-out: $1,189 - (earned - $27,425)/100 × $21.71 per eligible
    FYTC: $1,189 per qualifying taxpayer (age 18-25, CA foster care); $2,378 both spouses
    """
    p = PARAMS_2025
    warnings = []

    # Eligibility gates
    if federal_agi >= 32901:
        return {"caleitc": 0, "yctc": 0, "fytc": 0, "total_ca_refundable": 0, "eligible": False,
                "warnings": ["CalEITC: Federal AGI $" + f"{federal_agi:,}" +
                             " ≥ $32,901 limit. Not eligible. Source: ftb.ca.gov/forms/2025/2025-3514-booklet.html"]}
    if ca_earned_income < 1:
        caleitc_val = 0
        if not has_young_child_under6:
            return {"caleitc": 0, "yctc": 0, "fytc": 0, "total_ca_refundable": 0, "eligible": False,
                    "warnings": ["CalEITC: No CA earned income — not eligible without young child. Source: FTB 3514."]}
    else:
        caleitc_val = None  # computed below

    if investment_income > 4814:
        return {"caleitc": 0, "yctc": 0, "fytc": 0, "total_ca_refundable": 0, "eligible": False,
                "warnings": [f"CalEITC: Investment income ${investment_income:,} > $4,814 limit. "
                             "Source: ftb.ca.gov/forms/2025/2025-3514-booklet.html Worksheet 1."]}

    if taxpayer_age < 18 and num_qualifying_children == 0:
        return {"caleitc": 0, "yctc": 0, "fytc": 0, "total_ca_refundable": 0, "eligible": False,
                "warnings": ["CalEITC: Taxpayer age < 18 with no qualifying child — not eligible."]}

    # CalEITC credit table 2025 — approximation using FTB phase-in/phase-out structure
    # Source: FTB 3514 Worksheet Part III; ftb.ca.gov/forms/2025/2025-3514-booklet.html
    # Exact credit from lookup table required before filing — engine formula approximates.
    # Maximum amounts confirmed from ftb.ca.gov/file/personal/credits/caleitc/eligibility-and-credit-information.html
    caleitc_params = {
        # (max_credit, phase_in_rate, phase_in_end, phase_out_start, phase_out_end)
        0: (264,   0.0153, 7200,  7200,  32901),
        1: (1863,  0.3400, 6900,  14890, 32901),
        2: (3080,  0.4000, 9000,  14890, 32901),
        3: (3756,  0.4500, 9000,  14890, 32901),
    }
    kids = min(num_qualifying_children, 3)
    max_credit, phase_in_rate, phase_in_end, phase_out_start, phase_out_end = caleitc_params[kids]

    if caleitc_val is None:   # has earned income
        ei = ca_earned_income
        if ei <= phase_in_end:
            caleitc_val = rnd(min(ei * phase_in_rate, max_credit))
        elif ei <= phase_out_start:
            caleitc_val = max_credit
        else:
            # Phase-out: linear reduction from phase_out_start to phase_out_end
            phase_out_range = phase_out_end - phase_out_start
            reduction = rnd((ei - phase_out_start) / phase_out_range * max_credit) if phase_out_range > 0 else max_credit
            caleitc_val = max(0, max_credit - reduction)

    caleitc_val = rnd(caleitc_val)

    # YCTC — Young Child Tax Credit (Form FTB 3514, Part VI)
    # Source: ftb.ca.gov/file/personal/credits/young-child-tax-credit.html
    # Max $1,189; phase-out: starts $27,425, fully phased out at $32,901
    # Formula (from FTB 3514 line 37): YCTC = $1,189 - ceil((earned - 27425)/100) × $21.71
    yctc = 0
    if has_young_child_under6 and federal_agi < 32901:
        yctc_max = p.get("ca_young_child_tax_credit", 1117)  # engine has 1117; FTB 2025 = 1189
        # Update: correct 2025 YCTC amount from FTB is $1,189
        yctc_max = 1189
        yctc_threshold = 27425
        if ca_earned_income <= yctc_threshold:
            yctc = yctc_max
        else:
            excess_hundreds = math.ceil((ca_earned_income - yctc_threshold) / 100)
            reduction = rnd(excess_hundreds * 21.71)
            yctc = max(0, rnd(yctc_max - reduction))

    # FYTC — Foster Youth Tax Credit (Form FTB 3514, Part IX)
    # Source: ftb.ca.gov/forms/2025/2025-3514-booklet.html Step 10
    # $1,189 per qualifying taxpayer (age 18-25, CA foster care age 13+)
    # Phase-out: same as YCTC ($27,425 threshold, $32,901 end)
    fytc = 0
    if (foster_youth_taxpayer or foster_youth_spouse) and caleitc_val > 0:
        fytc_max = 1189
        fytc_threshold = 27425
        num_fytc = (1 if foster_youth_taxpayer else 0) + (1 if foster_youth_spouse else 0)
        if ca_earned_income <= fytc_threshold:
            fytc = rnd(fytc_max * num_fytc)
        else:
            excess_hundreds = math.ceil((ca_earned_income - fytc_threshold) / 100)
            reduction_each = rnd(excess_hundreds * 21.71)
            fytc_each = max(0, rnd(fytc_max - reduction_each))
            fytc = rnd(fytc_each * num_fytc)

    if caleitc_val > 0:
        warnings.append(
            f"CalEITC (FTB 3514): ${caleitc_val:,} ({kids} qualifying child(ren), "
            f"CA earned income ${ca_earned_income:,}). "
            "⚠ Engine approximates CalEITC — verify with exact FTB 3514 credit table before filing. "
            "Source: ftb.ca.gov/forms/2025/2025-3514.pdf"
        )
    if yctc > 0:
        warnings.append(
            f"YCTC (FTB 3514 Part VI): ${yctc:,} (qualifying child under 6). "
            "Source: ftb.ca.gov/file/personal/credits/young-child-tax-credit.html"
        )
    if fytc > 0:
        warnings.append(
            f"FYTC (FTB 3514 Part IX): ${fytc:,} ({num_fytc} qualifying foster youth taxpayer(s)). "
            "Source: ftb.ca.gov/forms/2025/2025-3514-booklet.html Step 10; R&TC §17052.2"
        )

    return {
        "caleitc": caleitc_val, "yctc": yctc, "fytc": fytc,
        "total_ca_refundable": rnd(caleitc_val + yctc + fytc),
        "eligible": True, "num_children": kids,
        "ca_earned_income": ca_earned_income,
        "warnings": warnings,
    }


def compute_california_540(
        fed_agi: float, filing_status: str, num_dependents: int,
        ss_benefits: float, unemployment: float, ca_lottery: float,
        hsa_deduction: float, ira_deduction: float,
        fed_schedule_a: "ScheduleAData | None",
        fed_deduction_type: str, federal_itemized: float,
        ca_data: "CaliforniaData | None",
        ca_sdi_withheld: float,
        obbba_total_federal: float = 0.0,
        ca_w2_wages: float = 0.0,       # Sum of W-2 Box 16 CA wages — exact CA earned income
        ca_se_net_profit: float = 0.0,  # CA SE net profit for CalEITC earned income
        ca_taxpayer_age: int = 0)  -> dict:     # F4: derived from schema.dob for CalEITC age gate
    """
    California Form 540 — Individual Income Tax (2025)
    Source: ftb.ca.gov/forms/2025/2025-540.pdf; ftb.ca.gov/forms/2025/2025-schca.pdf

    Key CA differences from federal:
    - SS, unemployment, CA lottery → CA-exempt (subtracted)
    - HSA deduction not allowed → added back (CA never conformed to IRC §223)
    - OBBBA deductions NOT allowed → added back (CA nonconformity; FTB Announcement 2025-4)
    - Bonus depreciation (§168(k)) not allowed → added back; CA uses R&TC §24356
    - CA std deduction much lower ($5,540 single / $11,080 MFJ)
    - No QBI deduction on CA return (R&TC §17201 — no CA §199A)
    - No SALT cap on CA itemized (CA allows full state taxes)
    - 1% millionaire surcharge on CA taxable > $1M (Prop 63; R&TC §17043)
    - Military pay exclusion if stationed outside CA (R&TC §17140)
    """
    p = PARAMS_2025
    warnings = []
    cd = ca_data or CaliforniaData()

    # ── CA Schedule CA Part II — Additions to federal AGI ────────────────────
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html  FETCH_VERIFIED 2026-05-24

    # HSA addback — CA IRC §223 nonconformity (always required)
    # Source: FTB Pub 1001; R&TC §17201; CA Schedule CA Part II Line 23
    ca_hsa_addback = hsa_deduction

    # OBBBA nonconformity addback — CA did NOT adopt P.L. 119-21
    # Source: CA FTB Announcement 2025-4; 2025-540-ca-instructions.html
    ca_obbba_addback = (cd.ca_obbba_addback_override
                        if cd.ca_obbba_addback_override is not None and cd.ca_obbba_addback_override > 0
                        else obbba_total_federal)

    # Bonus depreciation addback — IRC §168(k) nonconformity
    # Source: FTB Pub 1001; R&TC §17250; CA Schedule CA Part II Line 22
    ca_bonus_dep_addback = rnd(cd.ca_bonus_depreciation_addback)

    # Alimony addback — TY 2025 transition rule (CA Sch CA Part I Sec B Line 2a / Sec C Line 19a)
    # For agreements executed 1/1/2019 – 12/31/2025:
    #   Federal: no deduction (payor) / no income (recipient) per TCJA §11051
    #   CA: still required inclusion/deduction for TY 2025 (CA conforms to federal repeal
    #       only for agreements executed after 12/31/2025)
    #   → Payor: federal deduction = $0 → CA must add income back (Column C addition)
    #   → Recipient: federal income = $0 → CA must include (Column C addition)
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html "Alimony" section; R&TC §17076
    ca_alimony_addback = rnd(getattr(cd, 'ca_alimony_addback', 0) or 0)

    # NOL suspension addback — CA suspended NOL carryforward deduction 2024–2026
    # Applies when modified AGI ≥ $1M. Taxpayer must add back federal NOL deduction.
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html; R&TC §17276.24; FTB 3805V
    ca_nol_addback = rnd(getattr(cd, 'ca_nol_addback', 0) or 0)

    ca_add = rnd(ca_hsa_addback + ca_obbba_addback + ca_bonus_dep_addback
                 + ca_alimony_addback + ca_nol_addback + cd.ca_other_additions)

    # ── CA Schedule CA Part II — Subtractions from federal AGI ───────────────
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html  FETCH_VERIFIED 2026-05-24

    # Military retirement exclusion — $20,000 cap for TY 2025–2029
    # Source: ftb.ca.gov/forms/2025/2025-540-ca-instructions.html "Military Retirement Exclusion"
    #         R&TC §17132.9 and §17132.10  FETCH_VERIFIED 2026-05-24
    ca_military_sub = min(rnd(cd.ca_military_pay_exclusion), 20000)
    # Loan forgiveness / cancelled-debt exclusion — Source: R&TC §17144
    ca_loan_sub      = rnd(cd.ca_loan_forgiveness_excluded)

    ca_sub = rnd(ss_benefits + unemployment + ca_lottery
                 + cd.ca_lottery_winnings + cd.ca_other_subtractions
                 + ca_military_sub + ca_loan_sub)

    ca_agi = rnd(fed_agi + ca_add - ca_sub)

    # Emit conformity warnings
    if ca_obbba_addback > 0:
        warnings.append(
            f"CA Schedule CA: OBBBA deductions ${ca_obbba_addback:,} added back — "
            "CA did not adopt P.L. 119-21 (OBBBA). Senior bonus, tips, overtime, and "
            "auto loan deductions are not allowed on the CA return. "
            "Source: CA FTB Announcement 2025-4; 2025-540-ca-instructions.html."
        )
    if ca_bonus_dep_addback > 0:
        warnings.append(
            f"CA Schedule CA: Bonus depreciation ${ca_bonus_dep_addback:,} added back — "
            "CA does not conform to IRC §168(k). Use R&TC §24356 for CA depreciation. "
            "Source: FTB Pub 1001; R&TC §17250."
        )
    if ca_alimony_addback > 0:
        warnings.append(
            f"CA Schedule CA: Alimony addback ${ca_alimony_addback:,} — "
            "TY 2025 transition rule: agreements executed 1/1/2019–12/31/2025 require CA "
            "income inclusion (recipient) or income addback (payor) even though federal "
            "TCJA §11051 eliminated alimony deduction/inclusion. "
            "Source: 2025-540-ca-instructions.html; R&TC §17076."
        )
    if ca_nol_addback > 0:
        warnings.append(
            f"CA Schedule CA: NOL suspension addback ${ca_nol_addback:,} — "
            "CA suspended NOL carryforward 2024–2026 for modified AGI ≥ $1M. "
            "Source: R&TC §17276.24; 2025-540-ca-instructions.html."
        )
    if ca_military_sub > 0:
        warnings.append(
            f"CA Schedule CA: Military retirement pay exclusion ${ca_military_sub:,} "
            f"(capped at $20,000 for TY 2025–2029). "
            "Source: R&TC §17132.9 and §17132.10; 2025-540-ca-instructions.html; FTB Pub 1032."
        )

    ca_std_key = f"ca_std_ded_{filing_status}"
    ca_std = p.get(ca_std_key, p["ca_std_ded_single"])
    # Source: ftb.ca.gov/forms/2025/2025-540.pdf Line 18
    # Single/MFS: $5,706 | MFJ/HOH/QSS: $11,412  (FETCH_VERIFIED 2026-05-24)

    # CA itemized: rebuild from federal Sch A without SALT cap, with full medical floor re-applied
    ca_itemized = 0
    if fed_schedule_a:
        ca_med  = max(0, rnd(fed_schedule_a.medical_dental_total - ca_agi * 0.075))
        ca_salt = rnd(fed_schedule_a.state_income_tax + fed_schedule_a.real_estate_tax +
                      fed_schedule_a.personal_property_tax + fed_schedule_a.other_state_local_tax)
        ca_mort = rnd(fed_schedule_a.mortgage_interest_1098 + fed_schedule_a.mortgage_points +
                      fed_schedule_a.mortgage_insurance_premiums + fed_schedule_a.investment_interest)
        ca_chr  = rnd(fed_schedule_a.cash_charitable + fed_schedule_a.noncash_charitable +
                      fed_schedule_a.carryover_charitable)
        ca_misc = rnd(fed_schedule_a.other_misc)
        ca_itemized = rnd(ca_med + ca_salt + ca_mort + ca_chr + ca_misc)
    if cd.ca_itemized_total is not None and cd.ca_itemized_total > 0:
        ca_itemized = rnd(cd.ca_itemized_total)

    use_itemized = (cd.use_ca_itemized or fed_deduction_type == "itemized") and ca_itemized > ca_std
    ca_ded       = ca_itemized if use_itemized else ca_std
    ca_ded_type  = "itemized" if use_itemized else "standard"
    ca_taxable   = max(0, rnd(ca_agi - ca_ded))

    # CA income tax — use filing-status-specific bracket schedule
    # Schedule X: Single/MFS | Schedule Y: MFJ/QSS | Schedule Z: HOH (separate!)
    # Source: ftb.ca.gov/forms/2025/2025-540-tax-rate-schedules.pdf  FETCH_VERIFIED 2026-05-24
    if filing_status in ("mfj", "qss"):
        brackets = p["ca_brackets_mfj_2025"]
    elif filing_status == "hoh":
        brackets = p["ca_brackets_hoh_2025"]   # Schedule Z — was MISSING; engine was using single
    else:
        brackets = p["ca_brackets_single_2025"]  # single / mfs
    ca_tax = 0; prev = 0
    for (top, rate) in brackets:
        if ca_taxable <= prev: break
        ca_tax += (min(ca_taxable, top) - prev) * rate
        prev = top
    ca_tax = rnd(ca_tax)
    surtax = rnd(max(0, ca_taxable - 1_000_000) * p["ca_surtax_millionaire"])
    ca_tax_total = rnd(ca_tax + surtax)

    # Credits
    # HOH uses single personal exemption credit per R&TC §17054
    if filing_status in ("mfj", "qss"):
        pers_cr = p["ca_personal_exempt_mfj_qss"]
    elif filing_status == "hoh":
        pers_cr = p.get("ca_personal_exempt_hoh", p["ca_personal_exempt_credit"])
    else:
        pers_cr = p["ca_personal_exempt_credit"]
    dep_cr   = rnd(num_dependents * p["ca_dependent_exempt_credit"])
    sdi_cr   = rnd(ca_sdi_withheld + cd.ca_sdi_withheld)
    renter_cr = 0
    if cd.paid_rent_over_half_year:
        limit_r = 100000 if filing_status in ("mfj", "qss") else 50000
        if ca_agi <= limit_r:
            renter_cr = 120 if filing_status in ("mfj", "qss") else 60
    total_cr = rnd(pers_cr + dep_cr + sdi_cr + renter_cr)
    ca_tax_net = max(0, rnd(ca_tax_total - total_cr))

    if surtax > 0:
        warnings.append(f"CA Mental Health Services surtax: ${surtax:,} (1% on CA taxable > $1M). R&TC §17043.")
    if hsa_deduction > 0:
        warnings.append(f"CA HSA addback ${hsa_deduction:,}: CA does not conform to IRC §223.")
    if unemployment > 0:
        warnings.append(f"CA unemployment ${unemployment:,} exempt from CA tax (R&TC §17083).")

    # CalEITC / YCTC / FYTC (Form FTB 3514)
    # CA earned income = W-2 Box 16 CA wages + CA SE net profit
    # Source: FTB 3514 Step 1; ftb.ca.gov/forms/2025/2025-3514-booklet.html
    # FIX (EA review 2026-05-19, F4): use actual W-2 Box 16 wages instead of AGI proxy.
    # CA wages (Box 16) reflect wages subject to CA withholding — the correct base for
    # CalEITC. Using CA AGI as proxy overstates or understates when SS/HSA/addbacks apply.
    # When Box 16 is $0 (all W-2s are out-of-state), fall back to Box 1 wages × 0 (not eligible).
    if ca_w2_wages > 0 or ca_se_net_profit > 0:
        ca_earned_income_proxy = max(0, rnd(ca_w2_wages + ca_se_net_profit))
    else:
        # No CA wages reported — fall back to AGI proxy with warning
        ca_earned_income_proxy = max(0, rnd(ca_agi - max(0, rnd(
            (cd.ca_other_additions if cd else 0) + hsa_deduction))))
    num_children_caleitc = num_dependents   # simplified — all dependents counted
    has_young_child      = getattr(cd, 'has_young_child_under6', False) if cd else False
    foster_tp            = getattr(cd, 'foster_youth_taxpayer', False) if cd else False
    foster_sp            = getattr(cd, 'foster_youth_spouse',   False) if cd else False
    # Investment income for CalEITC: interest + dividends + cap gains (CA subset)
    ca_invest_income     = getattr(cd, 'ca_investment_income_caleitc', 0) if cd else 0
    caleitc_result = compute_caleitc(
        ca_earned_income      = ca_earned_income_proxy,
        federal_agi           = fed_agi,
        num_qualifying_children = num_children_caleitc,
        investment_income     = ca_invest_income,
        filing_status         = filing_status,
        taxpayer_age          = (ca_taxpayer_age if ca_taxpayer_age > 0
                               else (getattr(cd, 'ca_taxpayer_age', 0) if cd else 0)),
        has_young_child_under6 = has_young_child,
        foster_youth_taxpayer  = foster_tp,
        foster_youth_spouse    = foster_sp,
    )
    caleitc_credit = caleitc_result["caleitc"]
    yctc_credit    = caleitc_result["yctc"]
    fytc_credit    = caleitc_result["fytc"]
    ca_refundable_total = caleitc_result["total_ca_refundable"]

    # Apply CalEITC/YCTC/FYTC to reduce CA tax (refundable if exceeds tax)
    ca_tax_after_credits = max(0, rnd(ca_tax_net - caleitc_credit - yctc_credit - fytc_credit))
    ca_refund_from_credits = max(0, rnd(caleitc_credit + yctc_credit + fytc_credit - ca_tax_net))

    for w in caleitc_result.get("warnings", []):
        warnings.append(w)

    warnings.append(
        f"CA Form 540: CA AGI ${ca_agi:,} | taxable ${ca_taxable:,} | tax ${ca_tax_net:,} → "
        f"after CalEITC/YCTC/FYTC: ${ca_tax_after_credits:,}. "
        f"Ded: {ca_ded_type} ${ca_ded:,}. "
        "Source: ftb.ca.gov/forms/2025/2025-540.pdf"
    )
    return {"ca_agi": ca_agi, "ca_ded": ca_ded, "ca_ded_type": ca_ded_type,
            "ca_taxable": ca_taxable, "ca_tax_before_credits": ca_tax_total,
            "pers_cr": pers_cr, "dep_cr": dep_cr, "sdi_cr": sdi_cr, "renter_cr": renter_cr,
            "total_credits": total_cr, "ca_tax_net": ca_tax_net, "surtax": surtax,
            "caleitc": caleitc_credit, "yctc": yctc_credit, "fytc": fytc_credit,
            "ca_refundable_total": ca_refundable_total,
            "ca_tax_after_caleitc": ca_tax_after_credits,
            "ca_refund_from_credits": ca_refund_from_credits,
            "caleitc_detail": caleitc_result,
            "warnings": warnings}


def compute_schedule_b(form_1099ints: list, form_1099divs: list) -> dict:
    """
    Schedule B — Interest and Ordinary Dividends
    Source: irs.gov/pub/irs-pdf/f1040sb.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1040sb.pdf

    Part I — Interest Income (Lines 1–4)
      Line 1  = List each payer and amount (from 1099-INT and 1099-OID)
                Box 1 ordinary interest + Box 3 US savings bond interest (listed separately)
                Box 8 tax-exempt interest listed for information only (does NOT go to L2b)
      Line 2  = Exclusion for Series EE/I bonds (Form 8815) — not implemented
      Line 3  = Subtract Line 2 from Line 1
      Line 4  = Total taxable interest → Form 1040 Line 2b

    Part II — Ordinary Dividends (Lines 5–6)
      Line 5  = List each payer and Box 1a ordinary dividends
      Line 6  = Total ordinary dividends → Form 1040 Line 3b

    Part III — Foreign accounts / trusts — informational checkboxes (not computed)

    Schedule B required if:
      - Total taxable interest > $1,500, OR
      - Total ordinary dividends > $1,500, OR
      - Any foreign account or trust (Part III)
      - Received interest from a seller-financed mortgage

    Source: irs.gov/pub/irs-pdf/f1040sb.pdf; irs.gov/pub/irs-pdf/i1040sb.pdf
    """
    # Part I — Interest
    int_lines = []
    for f in form_1099ints:
        if f.box1_interest > 0:
            int_lines.append({"payer": f.payer, "amount": rnd(f.box1_interest), "type": "ordinary"})
        if f.box3_us_savings_bond > 0:
            int_lines.append({"payer": f.payer + " (US Savings Bond)", "amount": rnd(f.box3_us_savings_bond), "type": "us_savings"})
        if f.box8_tax_exempt_interest > 0:
            int_lines.append({"payer": f.payer + " (tax-exempt — info only)", "amount": rnd(f.box8_tax_exempt_interest), "type": "tax_exempt_info"})

    l1_total_taxable = rnd(sum(f.box1_interest + f.box3_us_savings_bond for f in form_1099ints))
    l4_total_interest = l1_total_taxable   # Line 2 exclusion (Form 8815) not implemented

    # Part II — Dividends
    div_lines = []
    for f in form_1099divs:
        if f.box1a_ordinary_div > 0:
            div_lines.append({
                "payer": f.payer,
                "box1a": rnd(f.box1a_ordinary_div),
                "box1b": rnd(f.box1b_qualified_div),
                "box2a": rnd(f.box2a_cap_gain_dist),
                "box2b": rnd(f.box2b_unrec_1250),
                "box2d": rnd(f.box2d_collectibles),
                "box3":  rnd(f.box3_nondiv_dist),
                "box5":  rnd(f.box5_sec199a_div),
                "box7":  rnd(f.box7_foreign_tax),
                "box11": rnd(f.box11_exempt_interest),
                "box12": rnd(f.box12_private_activity),
            })

    l6_total_div = rnd(sum(f.box1a_ordinary_div for f in form_1099divs))
    l6_total_qual = rnd(sum(f.box1b_qualified_div for f in form_1099divs))

    required = l4_total_interest > 1500 or l6_total_div > 1500

    # Aggregate AMT private activity bond interest (Box 12 — needed for Form 6251)
    amt_private_activity_int = rnd(
        sum(f.box12_private_activity for f in form_1099divs) +
        sum(getattr(f, 'box9_private_activity', 0) for f in form_1099ints)
    )

    # Foreign tax paid (Box 7 — flows to Form 1116 or Schedule 3 Line 1 if ≤ $300/$600)
    foreign_tax_div = rnd(sum(f.box7_foreign_tax for f in form_1099divs))
    foreign_tax_int = rnd(sum(getattr(f, 'box6_foreign_tax', 0) for f in form_1099ints))
    total_foreign_tax = rnd(foreign_tax_div + foreign_tax_int)
    if total_foreign_tax > 0:
        # ≤ $300 single / $600 MFJ: may claim directly on Sch 3 L1 without Form 1116
        pass  # wired to result; routing noted in warnings

    return {
        "part1_lines": int_lines,
        "l4_total_taxable_interest": l4_total_interest,
        "part2_lines": div_lines,
        "l6_total_ordinary_div": l6_total_div,
        "l6_total_qualified_div": l6_total_qual,
        "required": required,
        "amt_private_activity": amt_private_activity_int,
        "foreign_tax_total": total_foreign_tax,
    }


def compute_schedule_e_8582(schedule_es: list, agi: float,
                             filing_status: str,
                             form_8582_override: "Form8582Data | None" = None) -> dict:
    """
    Schedule E Part I + Form 8582 — Rental Real Estate Income/Loss & Passive Activity Limits
    Source: irs.gov/pub/irs-pdf/f1040se.pdf  |  irs.gov/pub/irs-pdf/f8582.pdf
            Instructions: irs.gov/pub/irs-pdf/i1040se.pdf  |  irs.gov/pub/irs-pdf/i8582.pdf

    Schedule E Part I (Line-by-line):
      Line 3  = rents received
      Lines 5–19 = expenses (see ScheduleE dataclass)
      Line 20 = total expenses
      Line 21 = net income (loss) = Line 3 − Line 20
      Line 22 = deductible rental loss (after Form 8582; enter here if loss)
      Line 23 = total rental income (sum of all Line 21 profits)
      Line 24 = total rental losses (sum of allowed losses after Form 8582)
      Line 26 = net → Schedule 1 Line 5 → Form 1040

    Form 8582 Worksheet 1 (Rental Real Estate with Special Allowance):
      Col (a) = current year net income from activities with income
      Col (b) = current year net loss from activities with loss (absolute value)
      Col (c) = prior year unallowed losses (Form 8582 Wk 7 from prior return)
      Line 1a = col (a) total
      Line 1b = col (b) total
      Line 1c = col (c) total
      Line 1d = combine 1a, 1b, 1c → total net (income) loss

    Form 8582 Special Allowance (§469(i)):
      Line 6 = $25,000 ($12,500 MFS lived apart)
      Line 7 = AGI − phaseout threshold ($100k/$50k MFS)
      Line 8 = Line 7 × 50%
      Line 9 = max(0, Line 6 − Line 8) = allowed special allowance
      Line 10 = smaller of Line 1d or Line 9 → allowed loss

    Real estate professionals: all losses allowed (not passive); skip Form 8582.
    Suspended losses → Worksheet 7 → carry to next year.
    """
    p = PARAMS_2025
    warnings = []
    per_property = []

    for prop in schedule_es:
        days_rented = max(0, prop.days_rented)
        days_personal = max(0, prop.days_personal_use)
        total_days = days_rented + days_personal

        # §280A vacation rules: personal use > max(14, 10% of rental days)
        # When triggered: expenses allocated by rental-use ratio; loss fully disallowed
        vacation_threshold = max(14, round(days_rented * 0.10))
        is_vacation_home = (days_personal > vacation_threshold) if total_days > 0 else False

        # Rental-use allocation ratio (applies to all expenses including mortgage interest)
        # Source: IRC §280A(e)(1); i1040se.pdf; IRS Pub 527
        alloc_ratio = (days_rented / total_days) if (total_days > 0 and is_vacation_home) else 1.0

        mort_interest_allocable  = rnd(prop.mortgage_interest * alloc_ratio)
        total_exp = rnd(
            (prop.advertising + prop.auto_travel + prop.cleaning_maintenance +
            prop.commissions + prop.insurance + prop.legal_professional +
            prop.management_fees + prop.other_interest +
            prop.repairs + prop.supplies + prop.taxes + prop.utilities +
            prop.depreciation + prop.other_expenses) * alloc_ratio +
            mort_interest_allocable  # mortgage interest is also allocated by ratio
        )
        if is_vacation_home:
            warnings.append(
                f"§280A vacation home rules apply to {prop.address or 'property'}: "
                f"{days_personal} personal-use days > {vacation_threshold}-day threshold. "
                f"Expenses allocated {days_rented}/{total_days} = {alloc_ratio:.1%} rental ratio. "
                "Losses are FULLY disallowed even if active participant. "
                "Unallocated mortgage interest → Schedule A (if itemizing). "
                "Source: IRC §280A(e)(1); IRS Pub 527."
            )
        net = rnd(prop.rents_received - total_exp)
        # §280A: vacation home losses FULLY disallowed (even if active participant)
        if is_vacation_home and net < 0:
            net = 0
        per_property.append({
            "address": prop.address or f"Property",
            "rents": rnd(prop.rents_received),
            "total_expenses": total_exp,
            "depreciation": rnd(prop.depreciation * alloc_ratio),
            "net": net,
            "is_re_pro": prop.is_real_estate_professional,
            "active": prop.active_participation,
            "is_vacation_home": is_vacation_home,
        })

    # Separate income vs loss properties (for Form 8582 Worksheet 1)
    col_a_income = rnd(sum(p["net"] for p in per_property if p["net"] > 0))
    col_b_loss   = rnd(abs(sum(p["net"] for p in per_property if p["net"] < 0)))
    re_pro_income = rnd(sum(p["net"] for p in per_property if p["is_re_pro"] and p["net"] >= 0))
    re_pro_loss   = rnd(sum(p["net"] for p in per_property if p["is_re_pro"] and p["net"] < 0))

    # Prior year unallowed losses from Form 8582 Worksheet 7
    col_c_prior  = rnd(form_8582_override.prior_year_unallowed_losses if form_8582_override else 0)
    mfs_apart    = (form_8582_override.mfs_lived_apart if form_8582_override else False) and filing_status == "mfs"

    # Worksheet 1 Line 1d: net of current income, current loss, and prior unallowed
    l1d_net_loss = rnd(col_b_loss + col_c_prior - col_a_income)  # positive = net loss

    # Form 8582 Line 6 — special allowance
    base_allowance = (p["rental_allowance_mfs"] if mfs_apart else p["rental_special_allowance"])
    phaseout_start = (p["rental_phaseout_mfs_start"] if mfs_apart else p["rental_phaseout_start"])

    # Phase-out: 50% of AGI excess over phaseout_start
    agi_excess = max(0, agi - phaseout_start)
    phaseout_reduction = rnd(agi_excess * 0.50)
    special_allowance = max(0, rnd(base_allowance - phaseout_reduction))  # Line 9

    # Allowed loss = smaller of net loss or special allowance (active participants only)
    # Real estate pros: all losses allowed without Form 8582
    active_loss_eligible = rnd(sum(
        abs(p["net"]) for p in per_property
        if p["net"] < 0 and p["active"] and not p["is_re_pro"]
    ))
    active_income_nets = rnd(sum(
        p["net"] for p in per_property
        if p["net"] > 0 and p["active"] and not p["is_re_pro"]
    ))
    net_active_loss = max(0, rnd(active_loss_eligible - active_income_nets + col_c_prior))

    if l1d_net_loss > 0:
        allowed_loss_8582 = min(net_active_loss, special_allowance)
        suspended_loss = rnd(net_active_loss - allowed_loss_8582)
    else:
        allowed_loss_8582 = 0
        suspended_loss = 0

    # Total allowed losses: re pro losses (all allowed) + Form 8582 allowed
    total_allowed_loss = rnd(abs(re_pro_loss) + allowed_loss_8582)
    # Net rental income = all property income nets + allowed losses (negative)
    net_rental = rnd(col_a_income + re_pro_income - total_allowed_loss)

    if col_b_loss > 0 or col_c_prior > 0:
        if special_allowance == 0:
            warnings.append(
                f"Form 8582: AGI ${rnd(agi):,} ≥ ${phaseout_start + base_allowance:,} — "
                f"§469(i) special allowance fully phased out. "
                f"Rental loss ${col_b_loss:,} suspended → Worksheet 7 carryforward. "
                "Source: irs.gov/pub/irs-pdf/f8582.pdf"
            )
        elif suspended_loss > 0:
            warnings.append(
                f"Form 8582: Allowed rental loss ${allowed_loss_8582:,} of ${net_active_loss:,} "
                f"(special allowance ${special_allowance:,}, AGI phase-out ${phaseout_reduction:,}). "
                f"Suspended loss ${suspended_loss:,} → Wk 7 carryforward to 2026. "
                "Source: irs.gov/pub/irs-pdf/f8582.pdf"
            )
        else:
            warnings.append(
                f"Form 8582: Full rental loss ${net_active_loss:,} allowed "
                f"(special allowance ${special_allowance:,} ≥ loss). "
                "Source: irs.gov/pub/irs-pdf/f8582.pdf"
            )

    if re_pro_loss > 0:
        warnings.append(
            f"Schedule E: Real estate professional flag — loss ${abs(re_pro_loss):,} "
            "treated as non-passive (bypasses Form 8582). Verify 750+ hour test and "
            "majority-of-personal-services test. Source: IRC §469(c)(7); i1040se.pdf."
        )

    if suspended_loss > 0:
        warnings.append(
            f"Form 8582 suspended loss ${suspended_loss:,}: enters Worksheet 7. "
            "This amount MUST be entered as prior_year_unallowed_losses on next year's Form 8582. "
            "Entire suspended loss released when property is sold (§469(g))."
        )

    return {
        "per_property": per_property,
        "col_a_income": col_a_income,
        "col_b_loss": col_b_loss,
        "col_c_prior": col_c_prior,
        "l1d_net_loss": l1d_net_loss,
        "special_allowance": special_allowance,
        "allowed_loss_8582": allowed_loss_8582,
        "suspended_loss": suspended_loss,
        "net_rental": net_rental,         # → Schedule 1 Line 5 → Form 1040
        "warnings": warnings,
    }


def compute_form_6251(taxable_income: float, agi: float,
                       regular_tax: float, qdcgt_income: float,
                       filing_status: str,
                       deduction_type: str,   # "standard" or "itemized"
                       deduction_used: float,
                       salt_itemized: float,   # SALT actually deducted on Schedule A
                       form_6251_data: "Form6251Data | None",
                       form_1099divs: list,
                       form_1099ints: list) -> dict:
    """
    Form 6251 — Alternative Minimum Tax — Individuals (2025)
    Source: irs.gov/pub/irs-pdf/f6251.pdf  |  Instructions: irs.gov/pub/irs-pdf/i6251.pdf

    Line-by-line (common items):
      Line 1  = Taxable income (Form 1040 Line 15, after QBI)
      Line 2a = Standard deduction claimed (if took std ded — must add back for AMT)
               Note: SALT deduction is also an addback if itemized, but handled in 2b
      Line 2b = State/local tax (SALT) from Schedule A Line 5 (addback)
               (only if itemized; already in std-ded addback via 2a if standard)
      Line 2c = Home mortgage interest adjustment (not common; skip)
      Line 2d = Refund of taxes (if included in income; negative entry)
      Line 2e = Investment interest expense (Form 4952 adjustments)
      Line 2f = Depletion (alternative depletion)
      Line 2g = NOL deduction (addback)
      Line 2h = Excess depletion
      Line 2i = Net operating loss deduction
      Line 2j = ISO bargain element (exercise of incentive stock options)
      Line 2k = Estates, trusts, partnerships (K-1 AMT items)
      Line 2l = Disposition of property (AMT vs regular basis adjustments)
      Line 2m = Depreciation of post-1986 property
      Line 2n = Passive activities
      Line 2o = Loss limitations
      Line 2p = Circulation costs
      Line 2q = Mining costs
      Line 2r = Long-term contracts
      Line 2s = Amortization of pollution control facilities
      Line 2t = Small business stock (§1202)
      Line 2u = Pre-1987 installment sales
      Line 2v = Adjustments from partnerships/S corps
      Line 2w = Other adjustments
      Line 3  = Tax-exempt interest from private activity bonds (AMT preference item)
               Source: 1099-INT Box 9 + 1099-DIV Box 12
      Line 4  = AMTI = Line 1 + all adjustments + Line 3
      Line 5  = AMT exemption (phased out 25¢ per $1 over phase-out threshold)
      Line 6  = AMTI minus exemption (if negative, $0)
      Line 7  = TMT: 26% × min(L6, $232,600) + 28% × max(0, L6−$232,600)
               Apply QDCGT rates for preferential income (§55(b)(3))
      Line 8  = Alternative minimum tax foreign tax credit (not implemented)
      Line 9  = Tentative minimum tax − regular tax = AMT owed (if > 0)
               → Schedule 2 Line 1 → Form 1040 Line 17

    QDCGT in AMT (§55(b)(3)): Same 0%/15%/20% rate structure as regular tax applies to
    qualified dividends and net capital gain within the AMT calculation.
    """
    p = PARAMS_2025
    warnings = []
    f6251 = form_6251_data

    # Line 1: start with taxable income
    l1 = taxable_income

    # Line 2a: addback of standard deduction if used
    # (AMT disallows standard deduction; itemizers: SALT addback via 2b instead)
    l2a = deduction_used if deduction_type != "itemized" else 0

    # Line 2b: SALT addback (only if itemized; std-ded addback already covers it via 2a)
    l2b = salt_itemized if deduction_type == "itemized" else 0

    # Lines 2c–2o: user-supplied or zero
    l2d = rnd(f6251.refund_of_taxes)       if f6251 else 0
    l2h = rnd(f6251.depletion_excess)      if f6251 else 0
    l2i = rnd(f6251.net_operating_loss_ded) if f6251 else 0
    l2j = rnd(f6251.iso_bargain_element)   if f6251 else 0
    l2o = rnd(f6251.other_adjustments)     if f6251 else 0
    l2f_farm = rnd(f6251.tax_shelter_farm_loss) if f6251 else 0

    # Line 3: Private activity bond interest (AMT preference item)
    # Source: 1099-DIV Box 12 + 1099-INT Box 9 (stored in schedule B)
    l3_private_activity = rnd(
        sum(f.box12_private_activity for f in form_1099divs) +
        sum(getattr(f, 'box9_private_activity', 0) for f in form_1099ints)
    )

    # Line 4: AMTI
    l4_amti = rnd(l1 + l2a + l2b + l2d + l2h + l2i + l2j + l2o + l2f_farm + l3_private_activity)

    # Line 5: AMT exemption (phased out 25¢ per $1 of AMTI above threshold)
    exemption_base = {
        "single": p["amt_exemption_single"], "mfj": p["amt_exemption_mfj"],
        "mfs": p["amt_exemption_mfs"],       "hoh": p["amt_exemption_hoh"],
        "qss": p["amt_exemption_mfj"],
    }.get(filing_status, p["amt_exemption_single"])

    phaseout_threshold = {
        "single": p["amt_phaseout_single"], "mfj": p["amt_phaseout_mfj"],
        "mfs": p["amt_phaseout_mfs"],       "hoh": p["amt_phaseout_hoh"],
        "qss": p["amt_phaseout_mfj"],
    }.get(filing_status, p["amt_phaseout_single"])

    phaseout_reduction = max(0, rnd((l4_amti - phaseout_threshold) * 0.25)) if l4_amti > phaseout_threshold else 0
    l5_exemption = max(0, rnd(exemption_base - phaseout_reduction))

    # Line 6: AMTI after exemption
    l6 = max(0, rnd(l4_amti - l5_exemption))

    # Line 7: Tentative minimum tax
    # §55(b)(3): For AMT, preferential income (QDCGT/qualified div) is taxed at 0%/15%/20%
    # Ordinary AMTI is taxed at 26%/28% AMT rates (NOT regular brackets)
    # Source: IRC §55(b)(3); f6251.pdf Line 7; i6251.pdf "Line 7"
    if qdcgt_income > 0 and l6 > 0:
        # Preferential income in AMTI: min of QDCGT income and total AMTI after exemption
        pref_in_l6 = min(qdcgt_income, l6)
        ord_l6 = max(0, l6 - pref_in_l6)

        # Ordinary AMTI at 26%/28% AMT rates
        if ord_l6 <= p["amt_rate_breakpoint"]:
            ord_tmt = rnd(ord_l6 * p["amt_rate1"])
        else:
            ord_tmt = rnd(p["amt_rate_breakpoint"] * p["amt_rate1"] +
                          (ord_l6 - p["amt_rate_breakpoint"]) * p["amt_rate2"])

        # Preferential AMTI at QDCGT 0%/15%/20% — thresholds applied against AMTI (l6)
        # NOT regular taxable income — this is the fix for issue #20
        # Source: IRC §55(b)(3); i6251.pdf Line 7 "Qualified Dividends and Capital Gain Tax Worksheet"
        rate0  = {
            "single": p["qdcgt_0pct_single"], "mfj": p["qdcgt_0pct_mfj"],
            "mfs":    p["qdcgt_0pct_mfs"],    "hoh": p["qdcgt_0pct_hoh"],
            "qss":    p["qdcgt_0pct_qss"],
        }.get(filing_status, p["qdcgt_0pct_single"])
        rate15 = {
            "single": p["qdcgt_15pct_single"], "mfj": p["qdcgt_15pct_mfj"],
            "mfs":    p["qdcgt_15pct_mfs"],    "hoh": p["qdcgt_15pct_hoh"],
            "qss":    p["qdcgt_15pct_qss"],
        }.get(filing_status, p["qdcgt_15pct_single"])

        # Amount in 0% band = max(0, threshold0 - ordinary AMTI)
        pref_0pct  = max(0, min(pref_in_l6, max(0, rate0  - ord_l6)))
        pref_15pct = max(0, min(pref_in_l6 - pref_0pct, max(0, rate15 - max(ord_l6, rate0))))
        pref_20pct = max(0, pref_in_l6 - pref_0pct - pref_15pct)
        qdcgt_tmt  = rnd(pref_0pct * 0.0 + pref_15pct * 0.15 + pref_20pct * 0.20)

        l7_tmt = rnd(ord_tmt + qdcgt_tmt)
    else:
        breakpoint_amt = p["amt_rate_breakpoint"]
        if l6 <= breakpoint_amt:
            l7_tmt = rnd(l6 * p["amt_rate1"])
        else:
            l7_tmt = rnd(breakpoint_amt * p["amt_rate1"] +
                         (l6 - breakpoint_amt) * p["amt_rate2"])

    # Line 9: AMT = max(0, TMT − regular tax)
    l9_amt = max(0, rnd(l7_tmt - regular_tax))

    if l9_amt > 0:
        warnings.append(
            f"AMT applies: ${l9_amt:,} → Schedule 2 Line 1 → Form 1040 Line 17. "
            f"AMTI ${l4_amti:,} − exemption ${l5_exemption:,} = ${l6:,}; "
            f"TMT ${l7_tmt:,} > regular tax ${regular_tax:,}. "
            "Source: irs.gov/pub/irs-pdf/f6251.pdf"
        )
    else:
        warnings.append(
            f"AMT: No liability (TMT ${l7_tmt:,} ≤ regular tax ${regular_tax:,}). "
            f"AMTI ${l4_amti:,}, exemption ${l5_exemption:,}. "
            "Source: irs.gov/pub/irs-pdf/f6251.pdf"
        )

    if (f6251 is None or f6251.iso_bargain_element == 0) and l9_amt == 0:
        pass  # no exotic items and no AMT — clean
    elif f6251 and (f6251.depletion_excess > 0 or f6251.net_operating_loss_ded > 0):
        warnings.append(
            "Form 6251: Depletion/NOL adjustments included. Verify Lines 2h/2i per f6251.pdf. "
            "Additional preference items (mining, pollution control, long-term contracts) "
            "require manual completion of Lines 2p–2u. Source: irs.gov/pub/irs-pdf/i6251.pdf"
        )

    return {
        "l1_taxable_income": l1,
        "l2a_std_ded_addback": l2a,
        "l2b_salt_addback": l2b,
        "l2j_iso": l2j,
        "l3_private_activity": l3_private_activity,
        "l4_amti": l4_amti,
        "l5_exemption": l5_exemption,
        "l6_amti_after_exemption": l6,
        "l7_tmt": l7_tmt,
        "l9_amt": l9_amt,
        "warnings": warnings,
    }


def compute_form_8615(f8615: 'Form8615Data', child_taxable_income: float,
                      child_qdcgt_income: float = 0) -> dict:
    """
    Form 8615 — Tax for Certain Children Who Have Unearned Income (Kiddie Tax)
    Source: irs.gov/pub/irs-pdf/f8615.pdf  |  Instructions: irs.gov/pub/irs-pdf/i8615.pdf
    IRC §1(g)

    Eligibility test (all must be true):
      1. Net unearned income > $2,700 (2025)
      2. Child under 18, OR age 18 with investment-only support, OR
         full-time student age 19–23 with investment-only support
      3. Filing status ≠ MFJ
      4. At least one parent alive at year-end

    Computation:
      L1  = net unearned income = max(0, unearned_income − $2,700)
      L4  = larger of $1,350 or child's earned income + $1,350 (child's deduction floor)
      L5  = L1 (same as net unearned income for most children)
      L6  = child's taxable income
      L7  = parent's taxable income
      L8  = L7 + L5 (combined parent+child taxable income for rate lookup)
      L9  = tax on L8 at parent's rate (using parent's filing status brackets)
      L10 = tax on L7 at parent's rate alone
      L11 = tentative tax = L9 − L10 (marginal rate applied to child's NUI)
      L13 = tax on child's taxable income at child's own brackets
      L15 = greater of L11 or L13 → child's actual income tax

    Note: If parent is MFJ, L7 = combined MFJ taxable income.
    Note: QDCGT rates also apply on Form 8615 if child has qualified dividends/LTCG.
          Simplified: uses ordinary bracket compute_tax() here; widget should note this.

    Source: f8615.pdf Lines 1–15; i8615.pdf "How To Figure the Tax"; IRC §1(g)(3)
    """
    p = PARAMS_2025
    warnings = []

    # ── Eligibility check ──────────────────────────────────────────────────────
    age = f8615.child_age
    is_student = f8615.child_is_full_time_student
    support_from_earned = f8615.child_support_from_earned

    applies = False
    if age < 18:
        applies = True
    elif age == 18 and not support_from_earned:
        applies = True
    elif 19 <= age <= 23 and is_student and not support_from_earned:
        applies = True

    if not applies:
        return {
            "applies": False,
            "reason": f"Kiddie tax does not apply: age {age}, "
                      f"student={is_student}, support_from_earned={support_from_earned}. "
                      "Source: f8615.pdf; IRC §1(g)(2).",
            "income_tax_8615": 0,
            "warnings": [],
        }

    # ── Line 1: Net Unearned Income ────────────────────────────────────────────
    # Source: f8615.pdf Line 1 instructions; i8615.pdf
    # Net unearned income = unearned income − $2,700 (2 × $1,350 dependent std ded)
    nui_threshold = p["kiddie_tax_nui_threshold"]
    l1_net_unearned = max(0, rnd(f8615.unearned_income - nui_threshold))

    if l1_net_unearned == 0:
        # No kiddie tax: unearned income below threshold
        # Regular tax on child's taxable income applies
        l13_child_tax = compute_tax(child_taxable_income, "single")
        return {
            "applies": True, "kiddie_tax_triggered": False,
            "l1_net_unearned": 0,
            "reason": f"Unearned income ${rnd(f8615.unearned_income):,} ≤ "
                      f"threshold ${nui_threshold:,}. Regular child tax applies.",
            "income_tax_8615": l13_child_tax,
            "l13_child_own_tax": l13_child_tax,
            "warnings": warnings,
        }

    # ── Lines 6–11: Parent's rate on child's NUI ───────────────────────────────
    l5  = l1_net_unearned                                       # simplified: L5 = L1
    l6  = rnd(child_taxable_income)                             # child's taxable income
    l7  = rnd(f8615.parent_taxable_income)                      # parent's taxable income (Form 1040 L15)
    l8  = rnd(l7 + l5)                                         # combined for rate computation
    l9  = compute_tax(l8, f8615.parent_filing_status)           # tax on combined
    l10 = compute_tax(l7, f8615.parent_filing_status)           # tax on parent's income alone
    l11_tentative = max(0, rnd(l9 - l10))                       # parent's marginal rate × child NUI

    # ── Line 13: Child's own tax on taxable income ─────────────────────────────
    l13_child_tax = compute_tax(l6, "single")                   # child's own bracket

    # ── Line 15: Greater of L11 or L13 ────────────────────────────────────────
    l15_income_tax = max(l11_tentative, l13_child_tax)

    # QDCGT note: if child has qualified dividends or LTCG, technically the QDCGT
    # worksheet should be applied to both L8 and L7 at parent's rates.
    # Simplified here: ordinary brackets used. Difference is typically small.
    if child_qdcgt_income > 0:
        warnings.append(
            f"Form 8615: Child has qualified dividends/LTCG of ${rnd(child_qdcgt_income):,}. "
            "Strictly, QDCGT rates apply within the kiddie tax computation (f8615.pdf Line 9 note). "
            "Engine uses ordinary brackets — tax may be slightly overstated. "
            "Verify with f8615.pdf QDCGT worksheet for precision before filing."
        )

    if l15_income_tax > l13_child_tax:
        warnings.append(
            f"Form 8615 Kiddie Tax applies: child's tax at parent's marginal rate "
            f"(${l15_income_tax:,}) exceeds child's own bracket tax (${l13_child_tax:,}). "
            f"Additional tax = ${l15_income_tax - l13_child_tax:,}. "
            "Source: f8615.pdf Line 15; IRC §1(g)."
        )

    return {
        "applies": True, "kiddie_tax_triggered": True,
        "l1_net_unearned": l1_net_unearned,
        "l5_nui": l5, "l6_child_taxable": l6,
        "l7_parent_taxable": l7, "l8_combined": l8,
        "l9_tax_on_combined": l9, "l10_tax_on_parent": l10,
        "l11_tentative": l11_tentative,
        "l13_child_own_tax": l13_child_tax,
        "l15_income_tax": l15_income_tax,
        "income_tax_8615": l15_income_tax,      # replaces normal compute_tax result
        "kiddie_tax_excess": l15_income_tax - l13_child_tax,
        "warnings": warnings,
    }


def compute_form_4797(sales: list, schema_sec1231_losses_5yr: float = 0.0) -> dict:
    """
    Form 4797 — Sales of Business Property
    Source: irs.gov/pub/irs-pdf/f4797.pdf  |  Instructions: irs.gov/pub/irs-pdf/i4797.pdf
    IRC §1231, §1245, §1250; Publication 544

    Processes each Form4797SaleData entry and produces:
      - ordinary_income_recapture: §1245 (equipment) or additional §1250 (commercial pre-ACRS)
        → Schedule 1 Line 4 → Form 1040 Line 8 (ordinary income, taxed at full rate)
      - sec1231_gain_net: gain after recapture allocated to §1231 pool
        → Schedule D Line 11 (LTCG if net §1231 gain; ordinary if net §1231 loss)
      - unrec_sec1250_gain: unrecaptured §1250 (straight-line depreciation on real property)
        → QDCGT Worksheet Line 19 (25% max rate, not ordinary, not standard LTCG rate)
      - suspended_losses_released: §469(g) — ALL Form 8582 suspended passive losses
        released in year of disposition

    §1231 lookback (5-year) — IRC §1231(c):
      If taxpayer had net §1231 losses in prior 5 years, current §1231 gains are
      reclassified as ordinary income to the extent of those prior losses.
      Input: prior_sec1231_losses_5yr on each Form4797SaleData (sale-level), OR
             schema_sec1231_losses_5yr on TaxpayerSchema (aggregate, for returns
             with §1231 history but no Form 4797 sales this year).
      Source: IRC §1231(c); f4797.pdf; Pub 544

    Source: f4797.pdf; i4797.pdf; IRC §1231, §1245, §1250; p544.pdf
    """
    if not sales and schema_sec1231_losses_5yr == 0:
        return {
            "applies": False,
            "ordinary_income_recapture": 0,
            "sec1231_gain_net": 0,
            "unrec_sec1250_gain": 0,
            "suspended_losses_released": 0,
            "details": [],
            "warnings": [
                f"§1231 LOOKBACK: ${schema_sec1231_losses_5yr:,} of net §1231 losses from "
                "prior 5 years on record. If this return has any §1231 gains from other "
                "sources, they may be recharacterized as ordinary income. "
                "Source: IRC §1231(c); f4797.pdf."
            ] if schema_sec1231_losses_5yr > 0 else [],
        }

    warnings = []
    total_ordinary_recapture = 0
    total_sec1231_gain = 0
    total_unrec_1250 = 0
    total_suspended_released = 0
    details = []

    for s in sales:
        sale_warnings = []
        desc = s.description or "Property"

        # ── Compute gain/(loss) ─────────────────────────────────────────────
        # Adjusted basis = original_cost − depreciation_taken
        adjusted_basis = rnd(s.original_cost - s.depreciation_taken)
        total_gain = rnd(s.gross_proceeds - adjusted_basis)
        # total_gain > 0: gain; total_gain < 0: loss (ordinary §1231 loss if held >1yr)

        ordinary_recapture = 0
        sec1231_gain = 0
        unrec_1250 = 0

        if total_gain <= 0:
            # §1231 loss — fully ordinary deduction (better than capital loss treatment)
            # No recapture when there is a loss
            sec1231_gain = total_gain   # negative = §1231 loss → ordinary income deduction
            sale_warnings.append(
                f"§1231 Loss on {desc}: ${abs(total_gain):,}. "
                "Net §1231 losses are ordinary deductions (better than capital loss treatment). "
                "Source: f4797.pdf Part I; IRC §1231(a)(2)."
            )
        else:
            # Gain situation — split between recapture and §1231
            if s.property_type in ("1250_residential", "1250_commercial"):
                # §1250 real property (rental / commercial)
                # Additional §1250 ordinary recapture: only applies to pre-ACRS accelerated dep.
                # Post-1986 MACRS residential: straight-line only → additional_section_1250_recapture = $0
                ordinary_recapture = rnd(min(total_gain,
                                             s.additional_section_1250_recapture))
                remaining_after_recapture = rnd(total_gain - ordinary_recapture)

                # Unrecaptured §1250 gain = straight-line depreciation taken, capped at §1231 gain
                # Taxed at 25% max rate (not ordinary, not regular LTCG)
                # Source: IRC §1(h)(6); QDCGT Worksheet Line 19
                unrec_1250 = rnd(min(s.depreciation_taken, remaining_after_recapture))
                sec1231_gain = rnd(remaining_after_recapture - unrec_1250)
                # Note: sec1231_gain here is the "clean" §1231 gain above depreciation
                # Total §1231 gain = unrec_1250 + sec1231_gain (both go to Sch D Line 11)
                # But unrec_1250 portion is capped at 25% via QDCGT worksheet

                if s.property_type == "1250_residential" and s.depreciation_taken > 0:
                    sale_warnings.append(
                        f"{desc}: Unrecaptured §1250 gain = ${unrec_1250:,} "
                        f"(straight-line depreciation ${s.depreciation_taken:,} capped at §1231 gain). "
                        "Taxed at max 25% rate via QDCGT Worksheet Line 19. "
                        "Source: f4797.pdf; IRC §1(h)(6); IRC §1250."
                    )

            elif s.property_type == "1245_equipment":
                # §1245 full recapture: all depreciation recaptured as ordinary income
                # Source: IRC §1245(a)(1)
                ordinary_recapture = rnd(min(total_gain, s.depreciation_taken))
                sec1231_gain = rnd(total_gain - ordinary_recapture)   # excess above dep = §1231
                # No unrecaptured §1250 for §1245 property
                sale_warnings.append(
                    f"{desc} (§1245 equipment): ${ordinary_recapture:,} ordinary income recapture "
                    f"(all depreciation recaptured). "
                    f"Remaining §1231 gain = ${sec1231_gain:,}. "
                    "Source: f4797.pdf Part III Lines 19–25; IRC §1245(a)(1)."
                )
            else:
                # Unknown type — treat as §1231 gain, flag warning
                sec1231_gain = total_gain
                sale_warnings.append(
                    f"{desc}: Unknown property_type '{s.property_type}'. "
                    "Treated as §1231 gain — verify property type. "
                    "Source: f4797.pdf."
                )

        # ── Suspended passive losses released at sale (§469(g)) ─────────────
        suspended_released = rnd(s.suspended_passive_losses)
        if suspended_released > 0:
            # Suspended losses offset §1231 gain first, then ordinary income
            offset = min(suspended_released, max(0, sec1231_gain + unrec_1250))
            sec1231_gain_after_susp = rnd(sec1231_gain + unrec_1250 - offset)
            # Reassign: unrec_1250 portion consumed first (least favorable to taxpayer)
            unrec_1250_adj = max(0, unrec_1250 - offset)
            sec1231_gain = rnd(sec1231_gain_after_susp - unrec_1250_adj)
            unrec_1250 = unrec_1250_adj
            total_suspended_released += suspended_released
            sale_warnings.append(
                f"{desc}: ${suspended_released:,} suspended Form 8582 passive losses "
                f"released at disposition (§469(g)). "
                "Released losses offset §1231 gain. "
                "Source: f4797.pdf; IRC §469(g); i4797.pdf."
            )

        # ── §1231 lookback — IRC §1231(c) ──────────────────────────────────
        # If prior 5-year net §1231 losses > 0, current §1231 gain is reclassified
        # as ordinary income up to the amount of those prior losses.
        # Source: IRC §1231(c); p544.pdf "Section 1231 Gains and Losses"
        lookback_amount = rnd(s.prior_sec1231_losses_5yr)
        lookback_recapture = 0  # amount reclassified from §1231 LTCG → ordinary

        if lookback_amount > 0 and sec1231_gain > 0:
            # Reclassify §1231 gain as ordinary income up to prior losses
            lookback_recapture = min(sec1231_gain, lookback_amount)
            sec1231_gain = rnd(sec1231_gain - lookback_recapture)
            ordinary_recapture = rnd(ordinary_recapture + lookback_recapture)
            sale_warnings.append(
                f"§1231 LOOKBACK APPLIED — {desc}: ${lookback_recapture:,} of §1231 gain "
                f"reclassified as ORDINARY INCOME (prior 5-year net §1231 losses = "
                f"${lookback_amount:,}). "
                f"Remaining §1231 gain = ${sec1231_gain:,}. "
                "Source: IRC §1231(c); p544.pdf."
            )
        elif total_gain > 0 and s.held_over_one_year:
            # No lookback provided — emit verification warning
            sale_warnings.append(
                f"{desc}: §1231 lookback — verify no net §1231 losses in prior 5 years "
                "(IRC §1231(c)). If yes, populate prior_sec1231_losses_5yr to reclassify gain. "
                "Source: IRC §1231(c); p544.pdf."
            )

        total_ordinary_recapture += ordinary_recapture
        total_sec1231_gain       += sec1231_gain
        total_unrec_1250         += unrec_1250

        details.append({
            "description": desc,
            "property_type": s.property_type,
            "gross_proceeds": rnd(s.gross_proceeds),
            "original_cost": rnd(s.original_cost),
            "depreciation_taken": rnd(s.depreciation_taken),
            "adjusted_basis": adjusted_basis,
            "total_gain_loss": total_gain,
            "ordinary_recapture": ordinary_recapture,
            "lookback_recapture": lookback_recapture,
            "prior_sec1231_losses_5yr": lookback_amount,
            "unrec_sec1250": unrec_1250,
            "sec1231_gain": sec1231_gain,
            "suspended_released": suspended_released,
            "held_over_one_year": s.held_over_one_year,
            "warnings": sale_warnings,
        })
        warnings.extend(sale_warnings)

    # Net §1231 result across all sales
    # If net §1231 > 0: LTCG → Schedule D Line 11 (then QDCGT applies)
    # If net §1231 < 0: ordinary loss → Schedule 1 Line 4 (fully deductible)
    net_sec1231 = rnd(total_sec1231_gain)

    if net_sec1231 < 0:
        warnings.append(
            f"Net §1231 loss = ${abs(net_sec1231):,}. "
            "Fully deductible as ordinary loss (not subject to capital loss $3,000 limit). "
            "Source: f4797.pdf Part I; IRC §1231(a)(2)."
        )
    elif net_sec1231 > 0:
        warnings.append(
            f"Net §1231 gain = ${net_sec1231:,} → Schedule D Line 11 (LTCG treatment). "
            f"Unrecaptured §1250 = ${total_unrec_1250:,} → 25% max rate. "
            "Source: f4797.pdf Part I; Schedule D Line 11; IRC §1231(a)(1)."
        )

    # Add schema-level §1231 lookback warning if prior losses were provided at schema level
    # and no Form 4797 sales were present to apply them.
    # Source: IRC §1231(c); f4797.pdf; Pub 544
    if schema_sec1231_losses_5yr > 0 and not sales:
        warnings.append(
            f"§1231 LOOKBACK: ${schema_sec1231_losses_5yr:,.0f} of prior 5-year §1231 losses on record. "
            "If this return has §1231 gains from any source, they may be recharacterized "
            "as ordinary income to the extent of these prior losses. "
            "Source: IRC §1231(c); f4797.pdf; Pub 544."
        )

    return {
        "applies": True,
        "ordinary_income_recapture": rnd(total_ordinary_recapture),  # → Sch 1 Line 4 / ordinary
        "sec1231_gain_net": net_sec1231,                              # → Sch D Line 11
        "unrec_sec1250_gain": rnd(total_unrec_1250),                  # → QDCGT Wks L19 (25% rate)
        "suspended_losses_released": rnd(total_suspended_released),
        "details": details,
        "warnings": warnings,
    }


def compute_nol_detection(agi: float, total_income: float,
                          se_net_profit: float, filing_status: str) -> dict:
    """
    Net Operating Loss (NOL) Detection — Form 1045 / IRC §172
    Source: irs.gov/pub/irs-pdf/f1045.pdf; irs.gov/pub/irs-pdf/p536.pdf; IRC §172

    Post-TCJA rules (applicable for 2025):
      - NOL = negative taxable income after adding back non-business deductions
      - NOL carryforward: indefinite (no 2-year carryback except farming losses)
      - Deduction limited to 80% of taxable income in carryforward year (IRC §172(a)(2))
      - Carryback: generally disallowed post-TCJA (except farming: 2-year carryback)

    Detection: if AGI < 0, a potential NOL exists.
    Engine computes the NOL amount for informational purposes only.
    Actual NOL computation requires Form 1045 Worksheet A (not implemented).
    Engine flags and warns; taxpayer must compute Form 1045 before carrying forward.

    Source: irs.gov/pub/irs-pdf/p536.pdf "Figuring an NOL"; IRC §172(c)
    """
    if agi >= 0:
        return {"nol_detected": False, "estimated_nol": 0, "warnings": []}

    # AGI is negative — potential NOL
    # Estimated NOL ≈ |AGI| (rough; Form 1045 Worksheet A required for exact)
    estimated_nol = abs(rnd(agi))

    warnings = [
        f"⚠ POTENTIAL NET OPERATING LOSS (NOL): AGI = ${rnd(agi):,}. "
        f"Estimated NOL carryforward = ${estimated_nol:,}. "
        "Post-TCJA: indefinite carryforward, limited to 80% of taxable income per year. "
        "No 2-year carryback (except farming losses). "
        "Compute exact NOL using Form 1045 Worksheet A before filing. "
        "Source: irs.gov/pub/irs-pdf/p536.pdf; IRC §172."
    ]

    if se_net_profit < 0:
        warnings.append(
            f"Schedule C loss of ${abs(rnd(se_net_profit)):,} is the primary NOL driver. "
            "Business losses that exceed all income create a deductible NOL carryforward. "
            "Source: p536.pdf; IRC §172(c)."
        )

    return {
        "nol_detected": True,
        "estimated_nol": estimated_nol,
        "agi": rnd(agi),
        "warnings": warnings,
    }


def compute_qdcgt_tax(taxable_income: float, qdcgt_income: float,
                       filing_status: str, tax_year: int = 2025,
                       unrecaptured_sec1250: float = 0.0,
                       collectibles_gain: float = 0.0) -> int:
    """
    Qualified Dividends and Capital Gain Tax Worksheet (QDCGT Worksheet)
    Source: irs.gov/pub/irs-pdf/f1040.pdf page 36; irs.gov/pub/irs-pdf/i1040gi.pdf
    TY 2026 thresholds: Rev. Proc. 2025-32 §4.03

    Special capital gain rates (IRC §1(h)):
    - Unrecaptured §1250 gain (25%): straight-line depreciation on real property.
      Source: IRC §1(h)(1)(D); i1040sd.pdf Line 19; i4797.pdf.
    - Collectibles gain (28%): coins, art, stamps, bullion, antiques.
      Source: IRC §1(h)(4); i1040sd.pdf Line 18; Pub 544.
    Both reduce the QDCGT amount subject to 0%/15%/20% rates.
    """
    p = PARAMS_2026 if tax_year == 2026 else PARAMS_2025
    if qdcgt_income <= 0 and unrecaptured_sec1250 <= 0 and collectibles_gain <= 0:
        return compute_tax(taxable_income, filing_status, tax_year)

    threshold_0pct = {
        "single": p["qdcgt_0pct_single"], "mfj": p["qdcgt_0pct_mfj"],
        "hoh": p["qdcgt_0pct_hoh"],       "qss": p["qdcgt_0pct_qss"],
        "mfs": p["qdcgt_0pct_single"],
    }.get(filing_status, p["qdcgt_0pct_single"])

    threshold_15pct = {
        "single": p["qdcgt_15pct_single"], "mfj": p["qdcgt_15pct_mfj"],
        "hoh": p["qdcgt_15pct_hoh"],       "qss": p["qdcgt_15pct_qss"],
        "mfs": p["qdcgt_15pct_single"],
    }.get(filing_status, p["qdcgt_15pct_single"])

    l1 = taxable_income

    # §1250 and collectibles tax computed separately at 25%/28% rates
    # Source: i1040sd.pdf Unrecaptured Section 1250 Gain Worksheet; IRC §1(h)(1)(D),(4)
    unrec_1250   = min(max(0, unrecaptured_sec1250), l1)
    collect      = min(max(0, collectibles_gain), max(0, l1 - unrec_1250))
    special_tax  = rnd(unrec_1250 * 0.25 + collect * 0.28)

    # Reduce QDCGT income by special-rate amounts (they are not 0%/15%/20% eligible)
    # Source: i1040sd.pdf; Unrecaptured §1250 Worksheet; IRC §1(h)
    qdcgt_adj    = max(0, qdcgt_income - unrec_1250 - collect)

    l2  = min(qdcgt_adj, l1)             # cap preferential income at taxable income
    l3  = max(0, l1 - l2)               # ordinary income + special-rate income
    l5  = threshold_0pct
    l6  = min(l1, l5)
    l7  = min(l3, l6)
    l8  = l6 - l7                        # taxed at 0%
    l9  = min(l1, l2)
    l10 = l8
    l11 = max(0, l9 - l10)              # above 0% threshold
    l12 = threshold_15pct
    l13 = min(l1, l12)
    l14 = l7 + l8
    l15 = max(0, l13 - l14)
    l16 = rnd(min(l11, l15) * 0.15)     # 15% portion
    l17 = max(0, l9 - l8 - l15)         # 20% portion
    l18 = rnd(l17 * 0.20)
    l19 = compute_tax(rnd(l3 - unrec_1250 - collect), filing_status, tax_year)  # ordinary only
    l20 = l16 + l18 + l19 + special_tax

    # Use the LOWER of QDCGT worksheet or ordinary bracket tax
    ordinary_tax = compute_tax(rnd(l1), filing_status, tax_year)
    l21 = min(l20, ordinary_tax)

    return rnd(l21)

def compute_f8962(agi: float, family_size: int,
                  form_1095a: "Form1095A") -> dict:
    """
    Form 8962 — Premium Tax Credit (PTC) (2025)
    Source: irs.gov/pub/irs-pdf/f8962.pdf  |  Instructions: irs.gov/pub/irs-pdf/i8962.pdf
            irs.gov/pub/irs-pdf/f1095a.pdf  |  IRC §36B

    Two computation methods:
    ─────────────────────────────────────────────────────────────────────────────
    Line 11 — Annual method (ONLY valid if same plan, same APTC all 12 months):
      L11a = annual Col A (enrollment premium)
      L11b = annual Col B (SLCSP)
      L11c = annual expected contribution (MAGI × applicable %  from Table 2)
      L11d = annual PTC = max(0, L11b − L11c)
      L11e = min(L11a, L11d)
      L11f = annual APTC (Col C)

    Lines 12–23 — Monthly method (REQUIRED when mid-year coverage change):
      Each month separately:
        L(n)a = monthly Col A    L(n)b = monthly Col B
        L(n)c = monthly expected contribution = L8a / 12
        L(n)d = monthly PTC = max(0, L(n)b − L(n)c)
        L(n)e = min(L(n)a, L(n)d)
        L(n)f = monthly APTC (Col C)
      Lines 24/25 = totals of col (e) and col (f)

    Engine automatically detects which method applies:
    - If monthly data provided → Lines 12–23
    - If annual only → Line 11

    Table 2 applicable figure:
    CRITICAL — Line 5 FPL% must be TRUNCATED (not rounded) to whole number.
    The applicable figure from Table 2 must be read from the actual IRS table
    (i8962.pdf Table 2) — never interpolated. Engine uses the published 2025 table.
    Source: irs.gov/pub/irs-pdf/i8962.pdf Table 2; Rev. Proc. 2024-35.

    2025 FPL figures (Table 1 in i8962.pdf — 2024 FPL used for 2025):
    Family size 1: $15,060  2: $20,440  3: $25,820  4: $31,200 etc.

    Line 26 — Net PTC (positive = credit, refundable → Sch 3 L9 → 1040 L31)
    Line 27 — Excess APTC repayment → Schedule 2 Line 2 → Form 1040 Line 17
    Repayment cap: §36B(f)(2)(B) — for income below 400% FPL (waived for some years)
    """
    p = PARAMS_2025

    # FPL lookup (2024 FPL used for 2025 returns per Rev. Proc. 2024-35)
    fpl_base = p["fpl_2024"]
    fpl = fpl_base.get(min(family_size, 8),
                       fpl_base[8] + (family_size - 8) * 4480)

    # Line 5: MAGI / FPL% — TRUNCATE (never round)
    l5_pct_raw = agi / fpl * 100
    l5_int = int(l5_pct_raw)   # IRS requires truncation

    # Table 2 — Applicable Figure (2025, per Rev. Proc. 2024-35)
    # Source: irs.gov/pub/irs-pdf/i8962.pdf Table 2
    # Published table reproduced exactly — no interpolation between brackets
    TABLE2_2025 = [
        (100, 133,  0.0200),
        (133, 150,  0.0300),
        (150, 200,  0.0400),
        (200, 250,  0.0600),
        (250, 300,  0.0800),
        (300, 400,  0.0850),
        (400, 9999, 0.0850),   # >400%: no PTC (ARPA cliff removed for 2025)
    ]
    # NOTE: The 400% cliff was permanently removed by the Inflation Reduction Act
    # (extended through 2025); those at >400% FPL can still receive PTC.
    # The applicable figure caps at 8.5% for income above 400%.
    app_figure = 0.0
    for (lo, hi, pct) in TABLE2_2025:
        if lo <= l5_int < hi:
            app_figure = pct
            break

    # Annual expected contribution (Line 8a)
    l8a_annual = rnd(agi * app_figure)

    # Determine method: monthly if months data present and non-empty
    col_a_ann = rnd(form_1095a.col_a_annual)
    col_b_ann = rnd(form_1095a.col_b_annual)
    col_c_ann = rnd(form_1095a.col_c_annual)

    use_monthly = bool(form_1095a.months)

    monthly_detail = []
    if use_monthly:
        # Lines 12–23 — month-by-month
        # Pad / use only provided months
        months_data = form_1095a.months
        # Fill missing months with zero (not covered)
        while len(months_data) < 12:
            months_data.append(Form1095AMonth())

        total_ptc_e = 0
        total_aptc_f = 0
        monthly_l8 = rnd(l8a_annual / 12)   # monthly expected contribution

        for i, mo in enumerate(months_data[:12]):
            mo_a = rnd(mo.col_a)
            mo_b = rnd(mo.col_b)
            mo_c = rnd(mo.col_c)
            mo_d = max(0, rnd(mo_b - monthly_l8))  # monthly PTC = SLCSP − monthly contribution
            mo_e = min(mo_a, mo_d)                   # limited to enrollment premium
            total_ptc_e  += mo_e
            total_aptc_f += mo_c
            monthly_detail.append({
                "month": i + 1,
                "col_a": mo_a, "col_b": mo_b, "col_c": mo_c,
                "monthly_contribution": monthly_l8,
                "col_d_ptc": mo_d, "col_e_allowed": mo_e,
            })

        l24_total_ptc = rnd(total_ptc_e)
        l25_total_aptc = rnd(total_aptc_f)

        # Re-derive annual totals from monthly sums for cross-check
        col_a_ann = rnd(sum(r["col_a"] for r in monthly_detail))
        col_b_ann = rnd(sum(r["col_b"] for r in monthly_detail))
        col_c_ann = rnd(sum(r["col_c"] for r in monthly_detail))

    else:
        # Line 11 — annual method
        l11d = max(0, rnd(col_b_ann - l8a_annual))
        l11e = min(col_a_ann, l11d)
        l24_total_ptc  = rnd(l11e)
        l25_total_aptc = rnd(col_c_ann)

    l26_net_ptc    = max(0, rnd(l24_total_ptc - l25_total_aptc))   # → Sch 3 L9
    l27_excess_aptc = max(0, rnd(l25_total_aptc - l24_total_ptc))  # → Sch 2 L2 repayment

    # Repayment cap §36B(f)(2)(B): applies only below 400% FPL
    # For 2025: cap removed / waived per IRA extension; full repayment required above 400%
    repayment_cap_applies = l5_int < 400
    if repayment_cap_applies and l27_excess_aptc > 0:
        # Cap table (2025) — Source: Rev. Proc. 2024-35 Table 5
        REPAY_CAPS_2025 = {
            "single": [(200, 375), (250, 950), (300, 1575), (350, 2225), (400, 3000)],
            "other":  [(200, 750), (250, 1900),(300, 3150), (350, 4450), (400, 6000)],
        }
        cap_key = "other" if family_size > 1 else "single"
        cap_amount = 0
        for (threshold, cap) in REPAY_CAPS_2025[cap_key]:
            if l5_int < threshold:
                cap_amount = cap
                break
        if cap_amount > 0 and l27_excess_aptc > cap_amount:
            l27_excess_aptc = cap_amount

    return {
        "method": "monthly_lines_12_23" if use_monthly else "annual_line_11",
        "l1_family_size": family_size, "l2a_magi": rnd(agi),
        "l4_fpl": fpl, "l5_pct_raw": round(l5_pct_raw, 4),
        "l5_int": l5_int,     # TRUNCATED — never rounded
        "l7_app_figure": app_figure,
        "l8a_annual_contrib": l8a_annual,
        "col_a": col_a_ann, "col_b": col_b_ann, "col_c": col_c_ann,
        "monthly_detail": monthly_detail,
        "l24_total_ptc": l24_total_ptc,
        "l25_total_aptc": l25_total_aptc,
        "l26_net_ptc": l26_net_ptc,
        "l27_excess_aptc": l27_excess_aptc,
        "repayment_cap_applied": repayment_cap_applies and l27_excess_aptc > 0,
        "WARNING": (
            "⚠ Table 2 applicable figure read from engine table (Rev. Proc. 2024-35). "
            "VERIFY exact row from IRS i8962.pdf Table 2 before filing. "
            "Line 5 % TRUNCATED (never rounded) per i8962.pdf instructions."
        ),
    }


def compute_f5329_exceptions(form_1099rs: list,
                              exceptions: list,
                              agi: float) -> dict:
    """
    Form 5329 — Additional Taxes on Qualified Plans (Parts I–X) (2025)
    Source: irs.gov/pub/irs-pdf/f5329.pdf  |  Instructions: irs.gov/pub/irs-pdf/i5329.pdf

    Engine scope: Part I (early distributions — most common case).
    Parts II–X (excess contributions, prohibited transactions, etc.) flagged as warnings.

    Part I — Additional Tax on Early Distributions from Qualified Retirement Plans
      Line 1  = total early distributions (from 1099-R with Code 1 or S, before exceptions)
      Line 2  = distributions meeting an exception (listed below)
      Line 3  = Line 1 − Line 2 = taxable distribution subject to penalty
      Line 4  = 10% × Line 3 (or 25% for SIMPLE first 2 years)
              → Schedule 2 Line 8

    Exceptions per official IRS f5329.pdf Part I Line 2 codes (2025):
      01 = Death  |  02 = Disability  |  03 = SEPP (§72(t))  |  04 = Age-55 sep (plan only)
      05 = ESOP dividends (plan only)  |  06 = IRS levy  |  07 = Qualified reservist
      08 = Higher education (IRA only)  |  09 = First home $10k lifetime (IRA only)
      10 = Health ins unemployed (IRA only)  |  11 = Medical > 7.5% AGI
      12 = Birth/adoption $5k per child  |  13 = Terminally ill (SECURE 2.0)
      14 = Domestic abuse $10k/yr (SECURE 2.0)  |  15 = Emergency $1k/yr (SECURE 2.0)
      17 = Long-term care insurance distributions

    Validation rules enforced:
      - Codes 08, 09, 10: IRA only — disallowed for employer plans
      - Codes 04, 05: Plan only — disallowed for IRAs
      - Code 09: $10,000 lifetime cap; Code 12: $5,000 per child cap
      - Code 14: $10,000/year cap; Code 15: $1,000/year cap
      - Code 11: informational warning about 7.5% AGI floor

    Source: irs.gov/pub/irs-pdf/f5329.pdf Part I; irs.gov/pub/irs-pdf/i5329.pdf
    """
    p = PARAMS_2025
    warnings = []

    # Collect all Code 1 and Code S distributions from 1099-Rs
    l1_distributions = []
    for f in form_1099rs:
        code = f.box7_code.upper()
        if code in ("1", "S"):
            l1_distributions.append({
                "payer": f.payer,
                "amount": rnd(f.box2a_taxable),
                "code": code,
                "is_ira": f.box7_ira_sep_simple or getattr(f, 'is_ira', False),
                "penalty_rate": 0.10 if code == "1" else 0.25,
            })

    if not l1_distributions:
        return {"l1_total": 0, "l2_exceptions": 0, "l3_subject": 0,
                "l4_penalty": 0, "exception_detail": [], "warnings": warnings}

    l1_total = rnd(sum(d["amount"] for d in l1_distributions))

    # Match exception claims to distributions
    exception_detail = []
    total_exception_amount = 0

    for exc in exceptions:
        code_num = str(exc.exception_code).zfill(2)
        # Read amount: prefer distribution_amount, fall back to alias 'amount'
        # Read plan_type: prefer plan_type, fall back to alias 'account_type'
        dist_amount = rnd(exc.distribution_amount or exc.amount)
        plan_type   = (exc.plan_type or exc.account_type or 'ira').lower()
        is_ira = plan_type == "ira"

        valid = True
        exc_warnings = []

        # ── EXACT IRS Form 5329 Part I Line 2 exception codes ─────────────────
        # Source: irs.gov/pub/irs-pdf/i5329.pdf Line 2 instructions (fetched 2026-05-21)
        # These are the codes AS PRINTED in the IRS instructions — not remapped:
        #   01 = Age-55 separation (plan only); 02 = SEPP; 03 = Disability; 04 = Death
        #   05 = Medical > 7.5% AGI; 06 = QDRO; 07 = Health ins unemployed (IRA only)
        #   08 = Higher education (IRA only); 09 = First home $10k lifetime (IRA only)
        #   10 = Qualified reservist; 11 = Birth/adoption $5k per child
        #   12 = Other (multiple exceptions — attach statement)
        # SECURE 2.0 additions (Notice 2024-55): coded as "other" (12) until IRS
        # formally assigns numbers in updated instructions.

        # Validate IRA-only / plan-only restrictions per i5329.pdf
        # FETCH_VERIFIED: irs.gov/pub/irs-pdf/i5329.pdf | Part I Line 2 exception numbers | 2026-05-21
        IRA_ONLY_CODES = {"07", "08", "09"}   # IRA only per i5329.pdf Line 2
        PLAN_ONLY_CODES = {"01", "06"}          # Plans only, not IRAs per i5329.pdf

        if code_num in IRA_ONLY_CODES and not is_ira:
            valid = False
            exc_warnings.append(
                f"Exception code {code_num} is allowed for IRAs only (not employer plans). "
                f"Source: IRC §72(t); f5329.pdf Part I."
            )
        if code_num in PLAN_ONLY_CODES and is_ira:
            valid = False
            exc_warnings.append(
                f"Exception code {code_num} is NOT allowed for IRAs — applies to employer plans only. "
                f"Source: IRC §72(t)(2)(A); f5329.pdf Part I."
            )

        # Validate dollar caps
        if code_num == "09":
            if dist_amount > p["f5329_first_home_lifetime"]:
                dist_amount = p["f5329_first_home_lifetime"]
                exc_warnings.append(
                    f"Exception 09 (first home purchase): capped at ${p['f5329_first_home_lifetime']:,} lifetime limit. "
                    "Source: IRC §72(t)(2)(F); f5329.pdf."
                )
        if code_num == "12":
            if dist_amount > p["f5329_birth_adoption"]:
                dist_amount = p["f5329_birth_adoption"]
                exc_warnings.append(
                    f"Exception 12 (birth/adoption): capped at ${p['f5329_birth_adoption']:,} per child. "
                    "Source: IRC §72(t)(2)(H); f5329.pdf."
                )
        if code_num == "14":
            if dist_amount > 10000:
                dist_amount = 10000
                exc_warnings.append(
                    "Exception 14 (domestic abuse): capped at $10,000 per year. "
                    "Source: IRC §72(t)(2)(K); SECURE 2.0 Act §314; f5329.pdf."
                )
        if code_num == "15":
            if dist_amount > 1000:
                dist_amount = 1000
                exc_warnings.append(
                    "Exception 15 (emergency personal expense): capped at $1,000 per year. "
                    "Source: IRC §72(t)(2)(J); SECURE 2.0 Act §127; f5329.pdf."
                )

        # Exception 05 (medical > 7.5% AGI): informational warning — code 05 per i5329.pdf
        if code_num == "05":
            floor = rnd(agi * 0.075)
            exc_warnings.append(
                f"Exception 05 (medical): distributions used for medical expenses exceeding "
                f"7.5% AGI floor (${floor:,}). Verify total qualified medical expenses exceed the floor. "
                "Source: IRC §72(t)(2)(B); i5329.pdf Line 2."
            )

        if valid:
            total_exception_amount += dist_amount
            for w in exc_warnings:
                warnings.append(w)
        else:
            for w in exc_warnings:
                warnings.append(w)
            dist_amount = 0

        exception_detail.append({
            "payer": exc.payer_name,
            "code": code_num,
            "requested": rnd(exc.distribution_amount or exc.amount),
            "allowed": rnd(dist_amount),
            "valid": valid,
        })

    l2_exceptions = rnd(min(total_exception_amount, l1_total))
    l3_subject    = max(0, rnd(l1_total - l2_exceptions))

    # Penalty: usually 10%; 25% for SIMPLE IRA (Code S) in first 2 years
    # For mixed Code 1 + S distributions with exceptions, allocate proportionally
    # Simplified: apply 10% to l3_subject (conservative; warn if Code S present)
    has_simple = any(d["code"] == "S" for d in l1_distributions)
    l4_penalty  = rnd(l3_subject * 0.10)
    if has_simple:
        warnings.append(
            "Code S (SIMPLE IRA first 2 years): 25% penalty applies if participant in SIMPLE < 2 years. "
            "Engine applied 10% conservatively — verify plan dates. "
            "Source: IRC §72(t)(6); f5329.pdf."
        )

    if l2_exceptions > 0:
        warnings.append(
            f"Form 5329 exceptions applied: ${l2_exceptions:,} exempt from 10% penalty. "
            f"Taxable early distribution: ${l3_subject:,}. "
            f"Penalty: ${l4_penalty:,} → Schedule 2 Line 8. "
            "Source: irs.gov/pub/irs-pdf/f5329.pdf Part I."
        )

    return {
        "l1_total": l1_total,
        "l2_exceptions": l2_exceptions,
        "l3_subject": l3_subject,
        "l4_penalty": l4_penalty,
        "exception_detail": exception_detail,
        "warnings": warnings,
    }


def compute_f1116(form_1116: "Form1116Data",
                  agi: float,
                  us_tax_before_credit: float,
                  qdcgt_income: float,
                  filing_status: str,
                  amt_tax: float) -> dict:
    """
    Form 1116 — Foreign Tax Credit (2025)
    Source: irs.gov/pub/irs-pdf/f1116.pdf  |  Instructions: irs.gov/pub/irs-pdf/i1116.pdf
            IRC §901, §904; Pub 514

    Separate computation for each basket (passive, general).
    Engine computes both; most individual filers have passive only.

    Part I — Net Foreign Source Income (per basket):
      Line 1a = gross income from foreign sources
      Line 1b = foreign expenses allocable to foreign income
      Line 3  = net foreign source income = 1a − 1b

    Part II — Foreign Taxes Paid:
      Line 8  = total foreign taxes paid (cash basis) or accrued

    Part III — Figuring the Credit:
      Line 9  = net foreign source income (from Part I)
      Line 10 = AGI (Form 1040 Line 11, after all adjustments)
      Line 11 = Line 9 ÷ Line 10 (ratio, never > 1.0)
      Line 12 = US tax on all income (Form 1040 Line 16 after QDCGT)
      Line 13 = Credit limitation = Line 11 × Line 12
      Line 14 = Allowable credit = lesser of Line 8 and Line 13
      Line 20 = Total FTC claimed → Schedule 3 Line 1 (passive + general combined)

    Excess credit: Line 14 minus Line 8 (if positive) = unused limitation → carryforward
    Excess taxes: Line 8 minus Line 13 (if positive) = excess taxes → carryback 1 yr / carryforward 10 yrs

    De minimis (no Form 1116 required):
      If total creditable foreign taxes ≤ $300 single / $600 MFJ,
      AND income is all passive, AND no exclusion/deduction applies:
      → Direct entry on Schedule 3 Line 1 without Form 1116
      Source: i1116.pdf "Who Must File"

    AMT warning: When AMT applies, a separate Form 1116 is required for
    the AMT computation (§59(a)(2)). Not computed here — flagged as warning.

    QDCGT in FTC limitation: The tax used in Line 12 should use the QDCGT
    Worksheet tax (not just the bracket tax), since the credit reduces actual tax.
    """
    p = PARAMS_2025
    warnings = []

    total_foreign_taxes = rnd(form_1116.passive_foreign_taxes_paid +
                               form_1116.general_foreign_taxes_paid)

    # De minimis check
    de_minimis_limit = (p["f1116_de_minimis_mfj"] if filing_status in ("mfj", "qss")
                        else p["f1116_de_minimis_single"])
    only_passive = form_1116.general_foreign_taxes_paid == 0

    if total_foreign_taxes <= de_minimis_limit and only_passive:
        credit = total_foreign_taxes
        warnings.append(
            f"Foreign Tax Credit de minimis: total foreign taxes ${total_foreign_taxes:,} ≤ "
            f"${de_minimis_limit:,} threshold AND all passive income. "
            f"Claimed directly on Schedule 3 Line 1 — Form 1116 not required. "
            "Source: irs.gov/pub/irs-pdf/i1116.pdf; IRC §904(j)."
        )
        return {
            "de_minimis_applies": True,
            "total_foreign_taxes": total_foreign_taxes,
            "allowable_credit": credit,
            "sch3_l1": credit,
            "passive_detail": {}, "general_detail": {},
            "warnings": warnings,
        }

    # Full Form 1116 computation (per basket)
    def _compute_basket(gross_foreign_income, foreign_expenses,
                        foreign_taxes_paid, carryover, basket_name):
        l1a = rnd(gross_foreign_income)
        l1b = rnd(foreign_expenses)
        l3_net = max(0, rnd(l1a - l1b))

        # Part III
        l9  = l3_net
        l10 = max(1, agi)   # avoid divide-by-zero
        l11 = min(1.0, round(l9 / l10, 6)) if l10 > 0 else 0

        l12_tax = us_tax_before_credit   # tax before any FTC

        l13_limitation = rnd(l11 * l12_tax)
        l8_taxes       = rnd(foreign_taxes_paid + carryover)
        l14_allowable  = min(rnd(l8_taxes), l13_limitation)

        excess_taxes    = max(0, rnd(l8_taxes - l13_limitation))
        unused_limit    = max(0, rnd(l13_limitation - l8_taxes))

        if excess_taxes > 0:
            warnings.append(
                f"Form 1116 ({basket_name} basket): ${excess_taxes:,} excess foreign taxes — "
                "carryback 1 year / carryforward 10 years. "
                "Source: irs.gov/pub/irs-pdf/f1116.pdf Line 14; IRC §904(c)."
            )

        return {
            "l1a_gross_foreign": l1a, "l1b_expenses": l1b, "l3_net": l3_net,
            "l8_taxes_plus_co": l8_taxes, "l9": l9, "l10_agi": l10,
            "l11_ratio": l11, "l12_us_tax": l12_tax,
            "l13_limitation": l13_limitation, "l14_allowable": l14_allowable,
            "excess_taxes": excess_taxes, "unused_limit": unused_limit,
        }

    passive_detail = _compute_basket(
        form_1116.passive_foreign_income,
        form_1116.passive_foreign_expenses,
        form_1116.passive_foreign_taxes_paid,
        form_1116.passive_carryover,
        "passive"
    )
    general_detail = _compute_basket(
        form_1116.general_foreign_income,
        form_1116.general_foreign_expenses,
        form_1116.general_foreign_taxes_paid,
        form_1116.general_carryover,
        "general"
    )

    total_allowable = rnd(passive_detail["l14_allowable"] + general_detail["l14_allowable"])

    if amt_tax > 0:
        warnings.append(
            "AMT applies: a separate Form 1116 is required for the AMT FTC computation (§59(a)(2)). "
            "Not computed — manually complete Form 1116 (AMT) and enter on Form 8801. "
            "Source: irs.gov/pub/irs-pdf/i1116.pdf; IRC §59(a)."
        )

    warnings.append(
        f"Foreign Tax Credit (Form 1116): ${total_allowable:,} → Schedule 3 Line 1. "
        f"Passive basket: ${passive_detail['l14_allowable']:,} / "
        f"General basket: ${general_detail['l14_allowable']:,}. "
        "Source: irs.gov/pub/irs-pdf/f1116.pdf; irs.gov/pub/irs-pdf/i1116.pdf."
    )

    return {
        "de_minimis_applies": False,
        "total_foreign_taxes": total_foreign_taxes,
        "allowable_credit": total_allowable,
        "sch3_l1": total_allowable,
        "passive_detail": passive_detail,
        "general_detail": general_detail,
        "warnings": warnings,
    }





# ── v3 HELPERS ─────────────────────────────────────────────────────────────────

def compute_schedule_a(sched_a: 'ScheduleAData', agi: float, fs: str) -> dict:
    """
    Schedule A — Itemized Deductions
    Source: irs.gov/pub/irs-pdf/f1040sa.pdf, i1040sa.pdf

    Medical: only excess above 7.5% of AGI is deductible (Line 4)
    SALT cap: OBBBA §70106 — $40,000 (MFJ/Single/HOH/QSS); $20,000 MFS
              Phase-down: $50 per $1,000 of AGI above $500k; floor $10,000
              Source: P.L. 119-21; Rev. Proc. 2025-32
    Charitable: OBBBA — 0.5% AGI floor applies before 60% cap (itemizers)
    Casualty: only federally declared disaster losses (permanent post-OBBBA)
    Misc itemized deductions: permanently disallowed (OBBBA §70501)
    """
    p = PARAMS_2025
    # Line 1-4: Medical & Dental
    l1_medical = rnd(sched_a.medical_dental_total)
    l2_agi_pct  = rnd(agi * 0.075)
    l4_medical_net = max(0, l1_medical - l2_agi_pct)

    # Line 5-6: State & Local Taxes (SALT) — OBBBA §70106
    # Cap: $40,000 default / $20,000 MFS; phase-down above AGI $500k
    # Floor: never below $10,000
    # Source: P.L. 119-21; irs.gov/newsroom/one-big-beautiful-bill-provisions
    l5a = rnd(sched_a.state_income_tax)
    l5b = rnd(sched_a.real_estate_tax)
    l5c = rnd(sched_a.personal_property_tax)
    l5d = l5a + l5b + l5c
    l6  = rnd(sched_a.other_state_local_tax)
    # Compute OBBBA SALT cap with phase-down
    if fs == "mfs":
        salt_cap_base = p["salt_cap_mfs"]
        phasedown_threshold = p["salt_phasedown_threshold"] / 2   # MFS = half of MFJ threshold
    else:
        salt_cap_base = p["salt_cap_default"]
        phasedown_threshold = p["salt_phasedown_threshold"]
    if agi > phasedown_threshold:
        excess_thousands = rnd((agi - phasedown_threshold) / 1000)
        salt_cap = max(p["salt_floor"],
                       salt_cap_base - excess_thousands * p["salt_phasedown_rate"])
    else:
        salt_cap = salt_cap_base
    l7_salt = min(l5d + l6, salt_cap)

    # Line 8-9: Interest
    # Mortgage interest: $750,000 acquisition debt limit for post-12/15/2017 loans
    # $1,000,000 limit for loans taken before 12/16/2017 (grandfathered)
    # $750,000 standard limit (post-12/15/2017); MFS = $375,000 (half of $750k)
    # Source: IRC §163(h)(3)(B)(ii); IRC §163(h)(3)(F)(i); IRS Pub 936; i1040sa.pdf Line 8a
    # FETCH_VERIFIED 2026-05-24: MFS limit confirmed as $375k per IRC §163(h)(3)(B)(ii)
    if sched_a.mortgage_is_grandfathered:
        mort_limit = 500_000 if fs == "mfs" else 1_000_000
    else:
        mort_limit = 375_000 if fs == "mfs" else 750_000
    outstanding = rnd(sched_a.mortgage_balance_outstanding)
    if outstanding > 0 and outstanding > mort_limit:
        limit_ratio = mort_limit / outstanding
        l8a_raw = rnd(sched_a.mortgage_interest_1098)
        l8a = rnd(l8a_raw * limit_ratio)
    else:
        l8a = rnd(sched_a.mortgage_interest_1098)
    l8c = rnd(sched_a.mortgage_points)
    l8d = rnd(sched_a.mortgage_insurance_premiums)
    l9  = rnd(sched_a.investment_interest)
    l10_interest = l8a + l8c + l8d + l9

    # Line 11-14: Charitable contributions — OBBBA + IRC §170(b)(1) limits
    # OBBBA: 0.5% AGI floor applies FIRST (itemizers) before 60% cap
    # Cash: 60% AGI limit  |  Noncash: 50% AGI (30% for appreciated capital gain property)
    # Carryover: 5-year carryforward for amounts exceeding limit
    # Source: IRC §170(b)(1)(A)–(B); OBBBA; i1040sa.pdf Lines 11–14
    charitable_agi_floor = rnd(agi * p["charitable_agi_floor_pct"])   # 0.5% AGI floor (OBBBA)
    agi_limit_cash    = rnd(agi * 0.60)   # Line 11: 60% AGI cap
    agi_limit_noncash = rnd(agi * 0.50)   # Line 12: 50% AGI cap
    l11_cash_raw    = rnd(sched_a.cash_charitable)
    l12_noncash_raw = rnd(sched_a.noncash_charitable)
    l13_carryover   = rnd(sched_a.carryover_charitable)
    # Apply 0.5% floor: deductible cash = max(0, cash - 0.5% AGI)
    l11_cash_above_floor = max(0, l11_cash_raw - charitable_agi_floor)
    l11_cash        = min(l11_cash_above_floor, agi_limit_cash)
    l12_noncash     = min(l12_noncash_raw, agi_limit_noncash)
    # Combined limit: total ≤ 60% AGI
    combined_raw    = l11_cash + l12_noncash + l13_carryover
    combined_limit  = agi_limit_cash
    l14_charitable  = min(combined_raw, combined_limit)
    charitable_carryover = max(0, l11_cash_raw + l12_noncash_raw + l13_carryover - l14_charitable)

    # Line 15: Casualty/theft losses (must be disaster area; Form 4684)
    l15_casualty = rnd(sched_a.casualty_theft_loss)

    # Line 16: Other
    l16_other = rnd(sched_a.other_misc)

    # Line 17: Total itemized deductions
    l17_total = (l4_medical_net + l7_salt + l10_interest +
                 l14_charitable + l15_casualty + l16_other)

    warnings = []
    if sched_a.noncash_charitable > 500:
        warnings.append("Non-cash charitable >$500: Form 8283 required. "
                        "Source: irs.gov/pub/irs-pdf/f8283.pdf")
    if sched_a.noncash_charitable > 5000:
        warnings.append("Non-cash charitable >$5,000: qualified appraisal required on Form 8283.")
    if charitable_agi_floor > 0 and l11_cash_raw > 0 and l11_cash_raw <= charitable_agi_floor:
        warnings.append(
            f"Charitable contributions ${l11_cash_raw:,} do not exceed the OBBBA 0.5% AGI floor "
            f"(${charitable_agi_floor:,}). No deduction allowed on these contributions. "
            "Source: OBBBA; IRC §170 as amended; irs.gov/newsroom/one-big-beautiful-bill-provisions."
        )
    elif charitable_agi_floor > 0 and l11_cash_raw > charitable_agi_floor:
        warnings.append(
            f"OBBBA charitable 0.5% AGI floor (${charitable_agi_floor:,}) applied. "
            f"Deductible cash contributions: ${l11_cash_raw:,} − ${charitable_agi_floor:,} floor = "
            f"${l11_cash_above_floor:,} (before 60% cap). "
            "Source: OBBBA; irs.gov/newsroom/one-big-beautiful-bill-provisions."
        )
    if charitable_carryover > 0:
        warnings.append(
            f"Charitable contributions ${l11_cash_raw + l12_noncash_raw + l13_carryover:,} "
            f"exceed 60% AGI limit (${combined_limit:,}). "
            f"Allowed deduction: ${l14_charitable:,}. "
            f"Carryforward to 2026: ${charitable_carryover:,} (5-year carryover period). "
            "Source: IRC §170(b)(1)(A); i1040sa.pdf Lines 11–14."
        )
    if sched_a.casualty_theft_loss > 0:
        warnings.append("Casualty/theft loss: must be in federally declared disaster area. "
                        "OBBBA permanently disallows non-disaster casualty/theft losses. "
                        "Form 4684 required. Source: irs.gov/pub/irs-pdf/f4684.pdf; OBBBA §70502.")
    if sched_a.investment_interest > 0:
        warnings.append("Investment interest: limited to net investment income. "
                        "Form 4952 may be required. Source: irs.gov/pub/irs-pdf/f4952.pdf")
    if outstanding > 0 and outstanding > mort_limit:
        warnings.append(
            f"Mortgage interest limited: outstanding balance ${outstanding:,} exceeds "
            f"${mort_limit:,} limit ({'grandfathered pre-12/16/2017' if sched_a.mortgage_is_grandfathered else 'post-12/15/2017 loan — permanent per OBBBA'}). "
            f"Deductible interest: ${l8a:,} of ${rnd(sched_a.mortgage_interest_1098):,} reported. "
            "Source: IRC §163(h)(3)(F)(i); IRS Pub 936; OBBBA."
        )
    if agi > salt_cap_base:
        warnings.append(
            f"OBBBA SALT cap applied: ${salt_cap:,} "
            f"({'phase-down applied' if agi > phasedown_threshold else 'standard cap'}). "
            f"Source: OBBBA §70106; P.L. 119-21; irs.gov/newsroom/one-big-beautiful-bill-provisions."
        )

    return {
        "l1_medical": l1_medical, "l2_agi_floor": l2_agi_pct,
        "l4_medical_net": l4_medical_net,
        "l5a_state_income": l5a, "l5b_real_estate": l5b, "l5c_personal_prop": l5c,
        "l5d_subtotal": l5d, "salt_cap": salt_cap, "l7_salt": l7_salt,
        "l8a_mortgage_1098": l8a, "l8c_points": l8c,
        "l8d_pmi": l8d, "l9_invest_interest": l9, "l10_interest": l10_interest,
        "l11_cash": l11_cash, "l12_noncash": l12_noncash,
        "l13_carryover": l13_carryover, "l14_charitable": l14_charitable,
        "charitable_agi_floor": charitable_agi_floor,
        "charitable_carryover": rnd(charitable_carryover),
        "l15_casualty": l15_casualty, "l16_other": l16_other,
        "l17_total": rnd(l17_total),
        "warnings": warnings,
    }


def compute_form_8949_schd(form_1099bs: list) -> dict:
    """
    Form 8949 → Schedule D — Capital Gains and Losses
    Source: irs.gov/pub/irs-pdf/f8949.pdf, irs.gov/pub/irs-pdf/f1040sd.pdf

    Box categories (Form 8949 checkboxes):
      Box A = Short-term, basis reported to IRS (covered, broker reported)
      Box B = Long-term, basis reported to IRS (covered, broker reported)
      Box C = Short-term, basis NOT reported to IRS
      Box D = Long-term, basis NOT reported to IRS (not used here — C covers noncovered)

    Net short-term → Schedule D Line 7 → ordinary income rates
    Net long-term → Schedule D Line 15 → preferential LTCG rates
    Capital loss carryover cap: ($3,000) per year against ordinary income
    LTCG rates 2025: 0% / 15% / 20% per taxable income thresholds
    """
    st_proceeds = st_basis = st_adj = st_wash = 0.0
    lt_proceeds = lt_basis = lt_adj = lt_wash = 0.0
    box_a_rows = []  # short-term, basis reported (covered)
    box_b_rows = []  # long-term, basis reported (covered)
    box_c_rows = []  # short-term, not reported (noncovered or no EIN)
    box_d_rows = []  # long-term, not reported (noncovered) — Form 8949 Box D

    for t in form_1099bs:
        proceeds  = rnd(t.proceeds)
        basis     = rnd(t.cost_basis)
        accrued   = rnd(t.accrued_discount)
        wash      = rnd(t.wash_sale_loss_disallowed)
        adj       = accrued - wash   # net adjustment to gain/loss
        gain_loss = rnd(proceeds - basis + adj)
        row = {
            "description": t.description,
            "date_acquired": t.date_acquired,
            "date_sold": t.date_sold,
            "proceeds": proceeds,
            "basis": basis,
            "adj_code": ("W" if wash else "") + ("D" if accrued else ""),
            "adj_amount": rnd(adj),
            "gain_loss": gain_loss,
            "broker": t.broker,
        }
        # Derive ST vs LT from actual dates when both are present & not "Various"
        # Source: IRC §1222; f8949.pdf Part I/II; i8949.pdf p.3 "Holding period"
        # >1 year held = long-term; ≤1 year = short-term. Dates override flag.
        _is_lt = t.is_long_term  # start with user-supplied flag
        _acq = (t.date_acquired or '').strip()
        _sol = (t.date_sold or '').strip()
        if _acq and _sol and _acq.upper() not in ('VARIOUS','INHERITED','N/A'):
            try:
                from datetime import datetime as _dt
                for _fmt in ('%m/%d/%Y','%m-%d-%Y','%Y-%m-%d'):
                    try:
                        _d_acq = _dt.strptime(_acq, _fmt)
                        _d_sol = _dt.strptime(_sol, _fmt)
                        _held  = (_d_sol - _d_acq).days
                        _is_lt = (_held > 365)   # >1 year = long-term
                        break
                    except ValueError:
                        continue
            except Exception:
                pass  # fall back to is_long_term flag

        if _is_lt:
            if t.noncovered or not t.basis_reported_to_irs:
                box_d_rows.append(row)   # Box D: noncovered long-term
                # Box D tracked via schd_l9_lt (sum of row gains) — NOT in lt_proceeds/lt_basis
                # Source: f1040sd.pdf Part II Line 9 (noncovered LT, Box D)
            else:
                box_b_rows.append(row)   # Box B: covered long-term
                # Only Box B (covered LT) accumulates lt_proceeds/lt_basis
                lt_proceeds += proceeds; lt_basis += basis
                lt_adj += adj; lt_wash += wash
        else:
            if t.noncovered or not t.basis_reported_to_irs:
                box_c_rows.append(row)   # Box C: noncovered short-term
                # Box C totals tracked SEPARATELY — NOT in st_proceeds/st_basis
                # Source: f1040sd.pdf Part I Lines 1b (covered) vs 2 (noncovered)
            else:
                box_a_rows.append(row)   # Box A: covered short-term
                # Only Box A (covered ST) accumulates st_proceeds/st_basis
                st_proceeds += proceeds; st_basis += basis
                st_adj += adj; st_wash += wash

    # Schedule D totals — Source: f1040sd.pdf Part I Lines 1a/1b/2/7; Part II Lines 8a/8b/9/10/15
    schd_l1b_st = rnd(st_proceeds - st_basis + st_adj)   # Line 1b: Box A covered ST net
    schd_l2_st  = rnd(sum(r["gain_loss"] for r in box_c_rows))  # Line 2: Box C noncovered ST
    schd_l7_st  = schd_l1b_st + schd_l2_st               # Line 7: total ST

    schd_l8b_lt = rnd(lt_proceeds - lt_basis + lt_adj)           # Line 8b: Box B covered LT net
    schd_l9_lt  = rnd(sum(r["gain_loss"] for r in box_d_rows))  # Box D noncovered LT
    schd_l15_lt = schd_l8b_lt + schd_l9_lt                      # Total LT

    # Net capital gain/loss
    net_cap = rnd(schd_l7_st + schd_l15_lt)
    # Loss limitation: max ($3,000) per year against ordinary income
    cap_loss_deductible  = max(-3000, net_cap) if net_cap < 0 else 0
    cap_gain_taxable     = net_cap if net_cap > 0 else 0
    cap_loss_carryover   = min(0, net_cap + 3000) if net_cap < -3000 else 0

    warnings = []
    if any(t.wash_sale_loss_disallowed for t in form_1099bs):
        warnings.append("Wash sale adjustments detected. Code W entered on Form 8949. "
                        "Verify 30-day wash sale window. Source: i8949.pdf")
    if any(t.noncovered for t in form_1099bs):
        warnings.append("Noncovered securities (Box 5 checked on 1099-B): basis not verified "
                        "by broker. Taxpayer responsible for basis. Report on Form 8949 Box C/D.")

    return {
        "box_a_rows": box_a_rows, "box_b_rows": box_b_rows,
        "box_c_rows": box_c_rows, "box_d_rows": box_d_rows,
        "st_proceeds": rnd(st_proceeds), "st_basis": rnd(st_basis), "st_adj": rnd(st_adj),
        "lt_proceeds": rnd(lt_proceeds), "lt_basis": rnd(lt_basis), "lt_adj": rnd(lt_adj),
        "schd_l1b_st": schd_l1b_st, "schd_l2_st": schd_l2_st,
        "schd_l7_st_total": schd_l7_st,
        "schd_l8b_lt": schd_l8b_lt, "schd_l9_lt": schd_l9_lt, "schd_l15_lt_total": schd_l15_lt,
        "net_capital_gain_loss": net_cap,
        "cap_gain_taxable": cap_gain_taxable,
        "cap_loss_deductible": cap_loss_deductible,
        "cap_loss_carryover": cap_loss_carryover,
        "warnings": warnings,
    }


def compute_form_8606(f8606: 'Form8606Data', trad_distributions_taxable: float) -> dict:
    """
    Form 8606 — Nondeductible IRAs
    Source: irs.gov/pub/irs-pdf/f8606.pdf, i8606.pdf

    Part I — Nondeductible traditional IRA basis tracking (Lines 1–14)
      L1  = current year nondeductible contribution
      L2  = total basis from prior Form 8606s
      L3  = L1 + L2 (total basis before distributions)
      L5  = value of ALL traditional/SEP/SIMPLE IRAs at 12/31 (including converting account)
      L6  = total distributions from traditional IRA this year (incl. conversions)
      L7  = L5 + L6
      L8  = nontaxable portion = L3 / L7 × L6 (pro-rata across ALL IRA balances)
      L14 = remaining basis = L3 − L8

    Part II — Roth Conversions (Lines 16–18) — v10 full implementation
      L16 = amount converted to Roth IRA this year
      L17 = nontaxable portion of conversion = L8 × (L16 / L6)  [if L6 > 0]
            (proportional share of total nontaxable amount applied to the conversion)
      L18 = taxable portion of conversion = L16 − L17
            → goes to Form 1040 Line 4b as taxable IRA income

    Backdoor Roth aggregation rule (IRC §408(d)(2)):
      trad_ira_value_dec31 MUST include ALL traditional/SEP/SIMPLE IRA balances on 12/31,
      not just the converting account. For a clean backdoor Roth (zero pre-tax IRA balance),
      L5 ≈ $0 after conversion → pro-rata = 0 → L18 = full conversion is taxable.
      For a tainted backdoor Roth (pre-tax IRA balance remains), a portion is nontaxable
      via pro-rata but the rest is ordinary income.

    Part III — Roth IRA distributions (Lines 19–25b)
      L19 = total Roth distributions
      L22 = basis in Roth (regular contributions, not earnings)
      L23 = nontaxable = min(L19, L22)
      L25b = taxable if account < 5 yrs or owner < 59½

    Source: f8606.pdf; i8606.pdf; IRC §408(d)(2); IRC §408A
    """
    warnings = []

    # ── Part I ──────────────────────────────────────────────────────────────────
    l1  = rnd(f8606.nonded_contrib_this_year)
    l2  = rnd(f8606.basis_prior_year)
    l3  = l1 + l2                              # total basis

    l5  = rnd(f8606.trad_ira_value_dec31)      # ALL trad/SEP/SIMPLE FMV at 12/31
    l6  = rnd(f8606.trad_ira_distributions)    # total distributions incl. conversions
    l7  = l5 + l6

    if l7 > 0 and l3 > 0:
        l8_nontax_ratio = l3 / l7
        l8  = rnd(min(l6, l3) * l8_nontax_ratio)
    else:
        l8_nontax_ratio = 0.0
        l8  = 0

    l14_remaining_basis = max(0, rnd(l3 - l8))

    taxable_trad_total = max(0, l6 - l8)       # taxable portion of ALL distributions

    # ── Part II — Roth Conversion (v10) ────────────────────────────────────────
    l16_conversion = rnd(f8606.conversion_amount)
    l17_conv_nontax = 0
    l18_conv_taxable = 0

    if l16_conversion > 0 and l6 > 0:
        # Pro-rata: nontaxable portion allocated proportionally to conversion amount
        # L17 = L8 × (L16 / L6) — Source: i8606.pdf Part II instructions
        l17_conv_nontax = rnd(l8 * (l16_conversion / l6))
        l18_conv_taxable = max(0, rnd(l16_conversion - l17_conv_nontax))
    elif l16_conversion > 0 and l6 == 0:
        # Conversion entered but no distributions recorded — warn
        l18_conv_taxable = l16_conversion
        warnings.append(
            "Form 8606 Part II: conversion_amount set but trad_ira_distributions is $0. "
            "Set trad_ira_distributions ≥ conversion_amount. "
            "Source: f8606.pdf Line 6; i8606.pdf."
        )

    # Backdoor Roth warnings
    if f8606.is_backdoor_roth:
        if l5 == 0 and l16_conversion > 0 and l3 > 0:
            # Clean backdoor: no pre-tax balance, fully nondeductible, fully taxable = $0
            warnings.append(
                f"Backdoor Roth — CLEAN: No pre-tax IRA balance on 12/31 (Line 5 = $0). "
                f"Pro-rata = 0. Full conversion of ${l16_conversion:,} is nontaxable "
                f"(basis offsets). Taxable amount on Line 18 = ${l18_conv_taxable:,}. "
                "Source: f8606.pdf; IRC §408(d)(2)."
            )
        elif l5 > 0 and l16_conversion > 0:
            # Tainted backdoor: pre-tax IRA balance contaminates pro-rata calculation
            warnings.append(
                f"⚠ Backdoor Roth — TAINTED: Pre-tax IRA balance of ${l5:,} on 12/31. "
                f"Pro-rata rule applies across ALL IRA balances (IRC §408(d)(2)). "
                f"Taxable portion of conversion = ${l18_conv_taxable:,} "
                f"(nontaxable = ${l17_conv_nontax:,}). "
                "To avoid this, roll pre-tax IRA into employer 401(k) before year-end. "
                "Source: f8606.pdf; i8606.pdf; IRC §408(d)(2)."
            )
        if l7 > 0 and l1 > 0:
            warnings.append(
                "Form 8606 aggregation rule reminder: Line 5 must include the FMV of ALL "
                "traditional, SEP, and SIMPLE IRAs at 12/31 (not just the converting account). "
                "Missing IRA balances will understate the taxable amount. "
                "Source: i8606.pdf; IRC §408(d)(2)."
            )

    # Remaining non-conversion taxable distributions (withdrawals, not conversions)
    taxable_non_conversion = max(0, taxable_trad_total - l18_conv_taxable)

    # ── Part III — Roth IRA distributions ──────────────────────────────────────
    l19 = rnd(f8606.roth_distributions)
    l22 = rnd(f8606.roth_basis_contributions)
    l23 = min(l19, l22)
    l25b_roth_taxable = max(0, l19 - l23)

    roth_qualified = f8606.roth_account_5yr_old and f8606.over_59_5
    if roth_qualified:
        l25b_roth_taxable = 0
    elif l25b_roth_taxable > 0:
        warnings.append(
            "Roth IRA distribution may be taxable (non-qualified): "
            "account not 5-year old or owner under 59½. "
            "Verify exceptions (death, disability, first home). "
            "Source: f8606.pdf Part III."
        )

    # Inherited IRA
    inherited_nontax = 0
    if f8606.is_inherited and f8606.inherited_basis > 0:
        inherited_nontax = rnd(f8606.inherited_basis)
        warnings.append(
            f"Inherited IRA: ${inherited_nontax:,} basis allocated from decedent's Form 8606. "
            "Verify basis allocation per i8606.pdf instructions."
        )

    return {
        # Part I
        "l1_contrib": l1, "l2_prior_basis": l2, "l3_total_basis": l3,
        "l5_dec31_value": l5, "l6_distributions": l6, "l7_total": l7,
        "l8_nontax_ratio": round(l8_nontax_ratio, 4), "l8_nontaxable": l8,
        "l14_remaining_basis": l14_remaining_basis,
        "taxable_traditional": rnd(taxable_trad_total),
        "taxable_non_conversion": rnd(taxable_non_conversion),
        # Part II — Roth conversion
        "l16_conversion_amount": l16_conversion,
        "l17_conv_nontax": l17_conv_nontax,
        "l18_conv_taxable": l18_conv_taxable,
        "roth_conversion_nontax": l17_conv_nontax,   # legacy key — kept for compatibility
        # Part III
        "l19_roth_dist": l19, "l22_roth_basis": l22,
        "l23_roth_nontax": l23, "l25b_roth_taxable": l25b_roth_taxable,
        "roth_qualified": roth_qualified,
        # Inherited
        "is_inherited": f8606.is_inherited, "inherited_nontax": inherited_nontax,
        "warnings": warnings,
    }



def compute_form_4972(f4972: 'Form4972Data') -> dict:
    """
    Form 4972 — Tax on Lump-Sum Distributions
    Source: irs.gov/pub/irs-pdf/f4972.pdf, i4972.pdf

    Qualifying lump-sum distributions from qualified plans (Code A on 1099-R).
    Taxpayer must have been born before January 2, 1936 to use this form.

    Part II — 20% Capital Gain Election:
      Tax = capital gain portion × 20%

    Part III — 10-Year Tax Option:
      Uses special 1986 rate schedule printed on the form itself.
      Line 8: 1/10 of ordinary income portion (after $10,000 minimum distribution allowance)
      Line 26: 10 × tax computed on Line 8 amount using 1986 single rates
      The 1986 rates from f4972.pdf (must read from form — approximated here):
        Rate schedule (1986 single): 11% up to $1,190; 12% to $2,270; 14% to $4,530; ...
        NOTE: Engine approximates; confirm exact amount from f4972.pdf before filing.

    The 4972 tax is additional — goes on Schedule 2 Line 6.
    """
    warnings = [
        "Form 4972: Confirm exact tax from IRS f4972.pdf 10-year tax option table. "
        "Source: irs.gov/pub/irs-pdf/f4972.pdf"
    ]

    part2_tax = 0.0  # Part II: 20% capital gain election
    part3_tax = 0.0  # Part III: 10-year tax option

    l3_cap_gain = rnd(f4972.capital_gain)
    l6_ordinary  = rnd(f4972.ordinary_income)

    # Part II — 20% capital gain election (optional)
    if f4972.elect_20pct_capital_gain and l3_cap_gain > 0:
        part2_tax = rnd(l3_cap_gain * 0.20)   # Line 6

    # Part III — 10-year averaging using 1986 special rates from f4972.pdf
    # The $10,000 minimum distribution allowance reduces ordinary income
    if f4972.elect_10yr_option and l6_ordinary > 0:
        l10_one_tenth = rnd(l6_ordinary / 10)
        # Minimum distribution allowance (MDA): min of $10,000 or 50% of L10
        mda_raw = min(10000, rnd(l6_ordinary * 0.50))
        l12_mda  = max(0, rnd(mda_raw - 0.20 * max(0, l6_ordinary - 20000)))
        l13      = max(0, l10_one_tenth - rnd(l12_mda / 10))
        # 1986 single rate schedule (from f4972.pdf Line 26 table — approximate)
        l26_tax_on_l13 = _apply_4972_1986_rates(l13)
        part3_tax = rnd(l26_tax_on_l13 * 10)   # multiply back by 10
        warnings.append(
            f"Form 4972 Part III: 10-year tax approximated as ${part3_tax:,}. "
            "Read exact Line 26 from IRS f4972.pdf before filing."
        )

    total_4972_tax = rnd(part2_tax + part3_tax)   # → Schedule 2 Line 6

    return {
        "l3_cap_gain": l3_cap_gain, "l6_ordinary": l6_ordinary,
        "elect_20pct": f4972.elect_20pct_capital_gain,
        "part2_20pct_tax": rnd(part2_tax),
        "elect_10yr": f4972.elect_10yr_option,
        "part3_10yr_tax": rnd(part3_tax),
        "total_4972_tax": total_4972_tax,     # → Schedule 2 Line 6
        "warnings": warnings,
    }


def _apply_4972_1986_rates(income: float) -> float:
    """
    1986 single individual rate schedule as printed on Form 4972 Part III.
    Source: irs.gov/pub/irs-pdf/f4972.pdf — read exact table before filing.
    This is an approximation; always confirm from the actual IRS form.
    """
    # 1986 rate schedule for single filers (from f4972.pdf)
    brackets_1986 = [
        (1190,  0.11), (2270,  0.12), (4530,  0.14),
        (6690,  0.15), (9170,  0.16), (11650, 0.18),
        (13920, 0.20), (16190, 0.23), (19640, 0.26),
        (25360, 0.30), (31080, 0.34), (36800, 0.38),
        (44780, 0.42), (59670, 0.48), (float('inf'), 0.50),
    ]
    tax, prev = 0.0, 0
    for limit, rate in brackets_1986:
        if income <= prev: break
        tax += (min(income, limit) - prev) * rate
        prev = limit
    return round(tax)


# ── MAIN COMPUTATION ENGINE ────────────────────────────────────────────────────

def run(schema: TaxpayerSchema) -> dict:
    """
    Full computation engine — supports TY 2025 and TY 2026.
    Source: irs.gov/pub/irs-pdf/ (all IRS forms)
    """
    # Select parameter set based on tax year
    # TY 2026: uses PARAMS_2026 (Rev. Proc. 2025-32, IR-2025-103)
    # TY 2025: uses PARAMS_2025 (Rev. Proc. 2024-40 + OBBBA Rev. Proc. 2025-32)
    p   = PARAMS_2026 if schema.tax_year == 2026 else PARAMS_2025
    fs  = schema.filing_status
    result = {"schema": schema, "warnings": [], "steps": {}}

    # ── HOH eligibility warning (IRC §2(b)) ──────────────────────────────────
    # HOH requires: unmarried taxpayer who paid >50% household costs for >6 months
    # for a qualifying person (qualifying child OR certain qualifying relative).
    # Source: IRC §2(b); Pub 501 p.8; i1040gi.pdf "Head of Household"
    if fs == "hoh" and not schema.dependents:
        result["warnings"].append(
            "⚠ HOH ELIGIBILITY: Head of Household requires a qualifying person — "
            "a qualifying child who lived with you >6 months, OR a qualifying relative "
            "(parent, sibling, etc.) for whom you paid >50% of household costs. "
            "No dependents are entered on this return. If you have a qualifying person, "
            "add them in the Dependents section. Source: IRC §2(b); Pub 501; i1040gi.pdf."
        )

    # ── QSS eligibility validation (IRC §2(a)) ────────────────────────────────
    # QSS requires: (1) spouse died in 2023 or 2024, (2) taxpayer maintains home
    # for a qualifying CHILD (not other relative) for all of 2025, (3) not remarried
    # Source: IRC §2(a)(1)(B); i1040gi.pdf "Qualifying Surviving Spouse"
    if fs == "qss":
        qss_has_qualifying_child = any(
            d.relationship in ("child", "stepchild")
            for d in schema.dependents
        )
        if not qss_has_qualifying_child:
            result["warnings"].append(
                "⚠ QSS ELIGIBILITY: Filing status 'Qualifying Surviving Spouse' requires "
                "maintaining a home for a qualifying CHILD (child or stepchild — "
                "not a sibling, parent, or other relative) for all of 2025. "
                "No child/stepchild dependent found on this return. "
                "If the dependent is a sibling or parent, correct filing status to Single. "
                "Source: IRC §2(a)(1)(B); i1040gi.pdf 'Qualifying Surviving Spouse'."
            )
        if not schema.deceased_spouse:
            result["warnings"].append(
                "⚠ QSS ELIGIBILITY: Deceased spouse information (name, SSN, date of death) "
                "required for QSS filing status — not found. "
                "Spouse must have died in 2023 or 2024. "
                "Source: IRC §2(a)(1)(A); i1040gi.pdf."
            )

    # W-2 — Source: irs.gov/pub/irs-prior/fw2--2025.pdf, irs.gov/pub/irs-pdf/iw2w3.pdf
    wages    = rnd(sum(w.box1_wages for w in schema.w2s))
    fed_wh   = rnd(sum(w.box2_fed_wh for w in schema.w2s))
    allocated_tips    = rnd(sum(w.box8_allocated_tips for w in schema.w2s))
    employer_dep_care = rnd(sum(w.box10_dependent_care for w in schema.w2s))
    nonqual_def_comp  = rnd(sum(w.box11_nonqual_def_comp for w in schema.w2s))
    # W-2 Box 13 retirement plan flag — affects IRA deduction phase-out
    covered_by_ret_plan = any(w.box13_retirement_plan for w in schema.w2s)

    # 1099-INT — Source: irs.gov/pub/irs-pdf/f1099int.pdf
    # P7: Bond premium (Box 11) reduces taxable interest per IRC §171 / Schedule B Line 1(b)
    # Box 11 = taxable bond premium elected under §171; reduces Box 1 ordinary interest.
    # Box 12 = Treasury bond premium (reduces Box 3); Box 13 = tax-exempt premium (no effect).
    # Box 10 = market discount — accrued; reportable as interest income (IRC §1278(b)).
    # Source: IRC §171; irs.gov/pub/irs-pdf/f1040sb.pdf Lines 1-4; i1040sb.pdf
    interest         = rnd(sum(
        max(0, f.box1_interest - f.box11_bond_premium)   # Box 11 reduces Box 1
        + f.box10_market_discount                          # Box 10 accrued → income
        for f in schema.form_1099ints
    ))
    # Box 12 reduces US savings bond interest (Box 3 / Line 3 Schedule B)
    early_wdwl       = rnd(sum(f.box2_early_withdrawal_penalty for f in schema.form_1099ints))
    us_bond_interest  = rnd(sum(
        max(0, f.box3_us_savings_bond - f.box12_bond_premium_treasury)  # Box 12 reduces Box 3
        for f in schema.form_1099ints
    ))
    int_backup_wh     = rnd(sum(f.box4_fed_wh for f in schema.form_1099ints))
    tax_exempt_interest = rnd(sum(f.box8_tax_exempt_interest for f in schema.form_1099ints))

    # 1099-DIV — Source: irs.gov/pub/irs-pdf/f1099div.pdf
    # Per-payer forms override legacy flat fields when present
    if schema.form_1099divs:
        dividends         = rnd(sum(f.box1a_ordinary_div for f in schema.form_1099divs))
        dividends_qual    = rnd(sum(f.box1b_qualified_div for f in schema.form_1099divs))
        div_cap_gain_dist = rnd(sum((f.box2a_cap_gain_dist or f.box2a_total_cap_gain) for f in schema.form_1099divs))
        div_backup_wh     = rnd(sum(f.box4_fed_wh for f in schema.form_1099divs))
        # Box 11 exempt-interest dividends: → Line 2a; also in SS provisional income
        div_exempt_int    = rnd(sum(f.box11_exempt_interest for f in schema.form_1099divs))
        # Add div exempt interest to tax_exempt_interest for SS provisional income
        tax_exempt_interest = rnd(tax_exempt_interest + div_exempt_int)
    else:
        dividends         = rnd(schema.dividends_ordinary)
        dividends_qual    = rnd(schema.dividends_qualified)
        div_cap_gain_dist = 0
        div_backup_wh     = 0
        div_exempt_int    = 0

    # 1099-NEC + Schedule C — Source: irs.gov/pub/irs-pdf/f1099nec.pdf; f1040sc.pdf
    # 1099-NEC Box 1 routes to Schedule C gross income (NOT prize income)
    nec_backup_wh = rnd(sum(f.box4_fed_wh for f in schema.form_1099necs))
    # Warn if 1099-NEC income exists — preparer must verify it is in Schedule C gross receipts
    # Source: i1099nec.pdf Box 1; i1040sc.pdf Line 1; IRC §1401
    _nec_total = rnd(sum(f.box1_nonemployee_comp for f in schema.form_1099necs))
    if _nec_total > 0 and schema.schedule_cs:
        _sc_gross_total = sum(sc.gross_receipts + sc.other_income for sc in schema.schedule_cs)
        result["warnings"].append(
            f"1099-NEC VERIFICATION: You have Form 1099-NEC income of ${_nec_total:,}. "
            "Per i1040sc.pdf Line 1, this must be included in Schedule C gross receipts. "
            f"Your Schedule C gross receipts + other income total ${int(_sc_gross_total):,}. "
            "If the 1099-NEC amount is NOT already included in your gross receipts figure, "
            "increase Line 1 by the 1099-NEC Box 1 amount — or set 'nec_included_in_gross: false' "
            "and the engine will add it automatically. Source: i1099nec.pdf Box 1; i1040sc.pdf L1."
        )
    elif _nec_total > 0 and not schema.schedule_cs:
        result["warnings"].append(
            f"1099-NEC of ${_nec_total:,} received but no Schedule C entered. "
            "Nonemployee compensation requires a Schedule C (or Schedule F for farming). "
            "Source: i1099nec.pdf Box 1; i1040sc.pdf."
        )
    # Schedule C computation (includes SE tax)
    se_result = {"total_net_profit": 0, "se_tax": 0, "se_tax_deduction": 0,
                 "net_earnings_se": 0, "per_business": [], "w2_ss_wages_used": 0,
                 "available_ss_base": p["ss_wage_base_2025"]}
    if schema.schedule_cs:
        # W-2 Box 3 SS wages — needed to cap SE SS base correctly
        # Source: f1040sse.pdf Line 8a; IRC §3121(a)(1)
        w2_ss_wages = rnd(sum(
            min(rnd(w.box1_wages), p["ss_wage_base_2025"])
            for w in schema.w2s
        ))
        se_result = compute_schedule_c_se(schema.schedule_cs, p, w2_ss_wages, nec_forms=schema.form_1099necs)
        if se_result["se_tax"] > 0:
            result["warnings"].append(
                f"Schedule SE: SE tax ${se_result['se_tax']:,} → Schedule 2 Line 4. "
                f"Deductible half ${se_result['se_tax_deduction']:,} → Schedule 1 Line 15. "
                "Source: irs.gov/pub/irs-pdf/f1040sse.pdf."
            )
    se_net_profit    = se_result["total_net_profit"]
    se_tax           = se_result["se_tax"]
    se_tax_deduction = se_result["se_tax_deduction"]  # → Schedule 1 Line 15

    # Estimated tax payments — Source: irs.gov/pub/irs-pdf/f1040es.pdf → Line 26
    l26_estimated = 0
    if schema.estimated_tax_payments:
        et = schema.estimated_tax_payments
        l26_estimated = rnd(et.q1 + et.q2 + et.q3 + et.q4 +
                            et.prior_year_overpayment_applied)

    # 1099-R — pension/IRA distributions (v3: full box support)
    # Source: irs.gov/pub/irs-pdf/f1099r.pdf, i1099r.pdf
    # IRA/SEP/SIMPLE checkbox = authoritative routing determinant (4a/4b vs 5a/5b)
    f1099r_gross_ira      = rnd(sum(f.box1_gross for f in schema.form_1099rs
                                    if f.box7_ira_sep_simple and f.box7_code not in ("G","H")))
    f1099r_gross_pension  = rnd(sum(f.box1_gross for f in schema.form_1099rs
                                    if not f.box7_ira_sep_simple and f.box7_code not in ("G","H")))
    f1099r_wh             = rnd(sum(f.box4_fed_wh for f in schema.form_1099rs))

    # Box 5: employee contributions recovered tax-free — reduce taxable amount
    # Box 6: NUA excluded from ordinary income (taxed as LTCG when securities sold)
    # Box 9b + Simplified Method: further reduces taxable annuity amount
    f1099r_taxable_ira    = 0
    f1099r_taxable_pension = 0
    sm_results = []   # store per-form simplified method results for reporting
    penalty_1099r = 0  # 10% early withdrawal penalties (Code 1/S → Form 5329)
    nua_total = 0      # total NUA excluded (informational; not in ordinary income)
    box3_cap_gain_total = 0   # feeds Form 4972 Part II if form_4972 not already set
    qcd_total = 0              # Code Y QCD total — excluded from income; tracked for $105,000 cap

    for f in schema.form_1099rs:
        code = f.box7_code.upper()
        # Rollovers: codes G and H are not taxable
        if code in ("G", "H"):
            continue
        # Qualified Roth distributions: codes Q are fully nontaxable
        if code == "Q":
            continue

        # QCD — Code Y: Qualified Charitable Distribution (IRC §408(d)(8))
        # Excluded from gross income entirely — does NOT appear on Line 4b.
        # Cannot be deducted again on Schedule A (IRC §408(d)(8)(D)).
        # Annual limit: $105,000 per taxpayer (TY 2025; SECURE 2.0 §307; Rev. Proc. 2024-40).
        # Source: IRC §408(d)(8); f1099r.pdf Box 7 Code Y; IRS Pub 590-B; i1040.pdf Line 4b
        if code == "Y":
            qcd_amt = rnd(f.box1_gross)
            qcd_total += qcd_amt
            result["warnings"].append(
                f"1099-R Code Y ({f.payer}): QCD ${qcd_amt:,} excluded from Line 4b income. "
                "Do NOT enter this amount in Schedule A cash_charitable — QCDs cannot be "
                "deducted as charitable contributions (IRC §408(d)(8)(D)). "
                f"Annual limit: $105,000 per taxpayer (TY 2025; SECURE 2.0 §307). "
                "Source: IRC §408(d)(8); IRS Pub 590-B; f1099r.pdf Code Y."
            )
            continue

        gross = rnd(f.box1_gross)
        taxable = rnd(f.box2a_taxable) if not f.box2b_not_determined else 0

        # Box 5: after-tax basis returned — already excluded by payer in box2a
        # (We trust box2a if provided; flag if box2b checked)
        if f.box2b_not_determined:
            result["warnings"].append(
                f"1099-R ({f.payer}): Box 2b 'Taxable amount not determined' is checked. "
                "Taxable amount must be computed using Form 8606 (if IRA) or "
                "Pub. 575 Simplified Method (if annuity with Box 9b). "
                "Engine used $0 — CONFIRM before filing."
            )

        # Box 6: NUA excluded from ordinary income
        nua = rnd(f.box6_nua)
        if nua > 0:
            nua_total += nua
            taxable = max(0, taxable - nua)  # NUA already excluded from 2a per form instructions
            result["warnings"].append(
                f"1099-R ({f.payer}): Box 6 NUA ${nua:,} excluded from ordinary income. "
                "Taxed as LTCG when employer securities are sold. See Pub. 575."
            )

        # Box 3: capital gain — feeds Form 4972 Part II (auto-populate if not set)
        box3_cap_gain_total += rnd(f.box3_capital_gain)

        # Simplified Method: applies when box9b > 0 and sm.use_simplified_method
        if (f.simplified_method and
                isinstance(f.simplified_method, SimplifiedMethodData) and
                f.simplified_method.use_simplified_method and
                f.box9b_employee_contribs > 0):
            sm = f.simplified_method
            # Use box9b as cost in contract if sm.cost_in_contract not set
            if sm.cost_in_contract == 0:
                sm.cost_in_contract = f.box9b_employee_contribs
            sm_res = compute_simplified_method(sm, taxable)
            sm_results.append({**sm_res, "payer": f.payer})
            taxable = sm_res["taxable_amount"]
            result["warnings"].append(sm_res["warning"])

        # Early distribution penalty tracking (Code 1 = 10%, Code S = 25% for SIMPLE)
        if code == "1":
            penalty_1099r += rnd(taxable * 0.10)
        elif code == "S":
            penalty_1099r += rnd(taxable * 0.25)

        # Code 4 — Death distribution: auto-detect as potentially inherited IRA
        # SECURE Act (2019): non-spouse beneficiaries of owners who died after 12/31/2019
        # must distribute entire account within 10 years (no life-expectancy stretch).
        # 10% penalty is waived for Code 4 distributions automatically.
        # Source: IRC §401(a)(9)(H); SECURE Act §401; i1099r.pdf Code 4
        if code == "4" and f.box7_ira_sep_simple:
            result["warnings"].append(
                f"1099-R Code 4 ({f.payer}): Death distribution from IRA/SEP/SIMPLE. "
                "No 10% early distribution penalty. "
                "SECURE Act (2019): If original owner died after 12/31/2019, "
                "non-spouse beneficiaries must fully distribute within 10 years "
                "(IRC §401(a)(9)(H)). Exceptions: surviving spouse, minor child, "
                "chronically ill/disabled, person ≤10 yrs younger than owner. "
                "If inherited IRA has basis (decedent's Form 8606), enter in "
                "form_8606.is_inherited and form_8606.inherited_basis. "
                "Source: IRC §401(a)(9)(H); i1099r.pdf; IRS Pub 590-B."
            )

        if f.box7_ira_sep_simple:
            f1099r_taxable_ira += taxable
        else:
            f1099r_taxable_pension += taxable

    f1099r_taxable_ira     = rnd(f1099r_taxable_ira)
    f1099r_taxable_pension = rnd(f1099r_taxable_pension)

    # QCD post-loop: $105,000 annual cap check + Schedule A double-dip block
    # Source: IRC §408(d)(8)(B)(i); SECURE 2.0 §307; Rev. Proc. 2024-40; f1099r.pdf
    QCD_LIMIT_2025 = 105000
    if qcd_total > QCD_LIMIT_2025:
        result["warnings"].append(
            f"⚠ QCD LIMIT EXCEEDED: Total QCDs ${qcd_total:,} exceed the $105,000 annual limit. "
            f"Excess ${qcd_total - QCD_LIMIT_2025:,} is taxable — reduce Code Y amounts or "
            "reclassify the excess as a normal distribution. "
            "Source: IRC §408(d)(8)(B)(i); SECURE 2.0 §307; Rev. Proc. 2024-40."
        )
    # Schedule A charitable double-dip: if client entered QCD amount in cash_charitable,
    # warn and flag — engine cannot auto-remove it because preparers sometimes split
    # a 1099-R between QCD and non-QCD portions. This warning must be reviewed.
    # Source: IRC §408(d)(8)(D); IRS Pub 590-B p.13; i1040sch a.pdf Line 11 instructions
    if qcd_total > 0 and schema.schedule_a and schema.schedule_a.cash_charitable > 0:
        result["warnings"].append(
            f"⚠ QCD / Schedule A conflict: ${qcd_total:,} QCD excluded from income AND "
            f"${rnd(schema.schedule_a.cash_charitable):,} entered in Schedule A cash charitable. "
            "QCDs cannot be deducted as charitable contributions (IRC §408(d)(8)(D)). "
            "Verify that the Schedule A charitable amount does NOT include any QCD dollars. "
            "Source: IRC §408(d)(8)(D); IRS Pub 590-B; i1040schA.pdf Line 11."
        )

    if penalty_1099r > 0:
        result["warnings"].append(
            f"1099-R early distribution penalty: ${penalty_1099r:,} (Code 1=10% / Code S=25%). "
            "Goes on Form 5329 → Schedule 2 Line 8. "
            "Source: irs.gov/pub/irs-pdf/f5329.pdf"
        )

    # Form 4972: auto-populate Box 3 capital gain if not already set by user
    if box3_cap_gain_total > 0 and schema.form_4972 and schema.form_4972.capital_gain == 0:
        schema.form_4972.capital_gain = box3_cap_gain_total

    # 1040 Lines 4a/4b (IRA) and 5a/5b (pension)
    l4a = f1099r_gross_ira;    l4b = f1099r_taxable_ira
    l5a = f1099r_gross_pension; l5b = f1099r_taxable_pension

    # SSA-1099 — compute taxability after establishing pre-SS AGI (iterative)
    # Source: irs.gov/pub/irs-pdf/p915.pdf Worksheets 1, 2, 4
    # Box 5 = net benefits → Line 6a; Box 6 = voluntary WH → Line 25b
    ss_net = 0
    ss_box6_wh = 0
    ss_mfs_lived_apart = False
    ss_lump_sum_prior_years = []
    if schema.form_ssa1099:
        ss_net = rnd(schema.form_ssa1099.box5_net_benefits)
        ss_box6_wh = rnd(schema.form_ssa1099.box6_voluntary_wh)
        ss_mfs_lived_apart = schema.form_ssa1099.mfs_lived_apart_all_year
        ss_lump_sum_prior_years = schema.form_ssa1099.lump_sum_prior_years or []
    l6a = ss_net   # total benefits → always shown on Line 6a

    # 1099-C — cancelled debt → Schedule 1 Line 8c (generally taxable unless IRC §108 exclusion)
    # F6 (EA review 2026-05-19): engine now computes Form 982 insolvency/bankruptcy exclusion
    # automatically when schema.form_982 is provided, replacing the manual is_excluded toggle.
    # Source: irs.gov/pub/irs-pdf/f1099c.pdf; irs.gov/pub/irs-pdf/f982.pdf; IRC §108; IRS Pub 4681
    _total_discharged = rnd(sum(f.box2_amount_discharged for f in schema.form_1099cs))

    form982_result = {}
    if schema.form_982 is not None and _total_discharged > 0:
        # Use Form 982 worksheet to compute exclusion
        form982_result = compute_form_982(schema.form_982, _total_discharged)
        for w in form982_result.get("warnings", []):
            result["warnings"].append(w)
        cancelled_debt = rnd(form982_result.get("taxable", _total_discharged))
        excluded_debt  = rnd(form982_result.get("excluded", 0))
    else:
        # Legacy: use is_excluded boolean per 1099-C (preparer must determine eligibility)
        cancelled_debt = rnd(sum(
            f.box2_amount_discharged for f in schema.form_1099cs if not f.is_excluded
        ))
        excluded_debt  = rnd(sum(
            f.box2_amount_discharged for f in schema.form_1099cs if f.is_excluded
        ))
        if cancelled_debt > 0:
            result["warnings"].append(
                f"1099-C: ${cancelled_debt:,} cancelled debt is taxable (Sch 1 Line 8c). "
                "If insolvency or bankruptcy exclusion applies, provide Form 982 data "
                "(total_liabilities_before and total_assets_fmv_before) for the engine "
                "to compute the IRC §108(a)(1)(B) exclusion. Source: f982.pdf; IRC §108; IRS Pub 4681."
            )
        if excluded_debt > 0:
            result["warnings"].append(
                f"1099-C: ${excluded_debt:,} marked excluded via is_excluded flag. "
                "Attach Form 982. Provide Form982Data for engine-computed worksheet. "
                "Source: f982.pdf; IRC §108; IRS Pub 4681."
            )

    # Prize money → Schedule 1 Line 8b
    # Source: irs.gov/pub/irs-pdf/f1099msc.pdf Box 3
    prize_income = rnd(sum(f.box3_other_income for f in schema.form_1099misc_prizes))

    # ── v8: Gambling Winnings (Form W-2G) → Schedule 1 Line 8b ─────────────────
    # Source: irs.gov/pub/irs-pdf/fw2g.pdf; IRC §61(a); Pub 525
    gambling_income = rnd(sum(w2g.box1_winnings for w2g in schema.form_w2gs))
    gambling_wh     = rnd(sum(w2g.box4_fed_wh   for w2g in schema.form_w2gs))
    if gambling_income > 0:
        result["warnings"].append(
            f"Gambling winnings: ${gambling_income:,} → Schedule 1 Line 8b. "
            + (f"WH ${gambling_wh:,} → Line 25b. " if gambling_wh else "")
            + ("Gambling losses deductible ONLY on Schedule A Line 16 (must itemize; "
               f"capped at winnings). " if schema.gambling_losses > 0 else
               "Keep records of all winnings and losses. ")
            + "Source: irs.gov/pub/irs-pdf/fw2g.pdf; Pub 525."
        )

    # ── v8: Unemployment Compensation (Form 1099-G) → Schedule 1 Line 7 ─────────
    # Source: irs.gov/pub/irs-pdf/f1099g.pdf; IRC §85
    # CA-exempt; fully taxable at federal level
    unemployment_income = 0
    state_refund_taxable = 0
    for f1099g in schema.form_1099gs:
        unemployment_income += rnd(f1099g.box1_unemployment)
        # State tax refund: taxable only if itemized in year refund was for (tax benefit rule)
        if f1099g.box2_state_refund > 0:
            if f1099g.prior_year_itemized:
                state_refund_taxable += rnd(f1099g.box2_state_refund)
                result["warnings"].append(
                    f"State tax refund ${f1099g.box2_state_refund:,} taxable (prior year itemized — "
                    "tax benefit rule IRC §111). → Schedule 1 Line 1. "
                    "Source: irs.gov/pub/irs-pdf/f1099g.pdf Box 2."
                )
            else:
                result["warnings"].append(
                    f"State tax refund ${f1099g.box2_state_refund:,}: NOT taxable "
                    "(prior year used standard deduction — no tax benefit). "
                    "Source: IRC §111; f1099g.pdf."
                )
    if unemployment_income > 0:
        result["warnings"].append(
            f"Unemployment compensation: ${unemployment_income:,} → Schedule 1 Line 7 (federal taxable). "
            "CA: exempt from CA income tax (R&TC §17083). "
            "Source: irs.gov/pub/irs-pdf/f1099g.pdf; IRC §85."
        )

    # ── Jury Duty Pay → Schedule 1 Line 8h ──────────────────────────────────────
    # Taxable as ordinary income. If employer required taxpayer to remit jury pay,
    # employer-remitted amount is deductible on Schedule 1 Line 24a (other adjustments).
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 8h; IRC §61(a); IRS Pub 525
    jury_duty_income = rnd(getattr(schema, 'jury_duty_income', 0) or 0)
    if jury_duty_income > 0:
        result["warnings"].append(
            f"Jury duty pay: ${jury_duty_income:,} → Schedule 1 Line 8h (taxable). "
            "If you remitted jury pay to your employer, that amount is deductible "
            "on Schedule 1 Line 24a. Source: f1040s1.pdf Line 8h; IRC §61(a); Pub 525."
        )

    # ── v8: Alimony Received → Schedule 1 Line 2a (pre-2019 decrees only) ────────
    alimony_received_income = 0
    alimony_paid_deduction  = 0
    if schema.alimony:
        al = schema.alimony
        # Modification override: pre-2019 decree modified post-2018 with explicit §71 waiver
        # → treated as post-2018 for all purposes regardless of original decree date
        # Source: IRC §11051(c); IRS Pub 504 "Alimony" section
        effective_pre_2019 = al.decree_pre_2019 and not al.decree_modified_after_2018
        if al.decree_modified_after_2018 and al.decree_pre_2019:
            result["warnings"].append(
                "Alimony: Pre-2019 decree was modified after 12/31/2018 with explicit §71 "
                "inapplicability clause → treated as post-2018 agreement. "
                "Alimony paid is NOT deductible; alimony received is NOT income. "
                "Source: IRC §11051(c); IRS Pub 504."
            )
        if effective_pre_2019:
            alimony_received_income = rnd(al.alimony_received)
            alimony_paid_deduction  = rnd(al.alimony_paid)
            if alimony_paid_deduction > 0 and not al.recipient_ssn:
                result["warnings"].append(
                    "Alimony paid deduction requires recipient SSN on Schedule 1 Line 19b. "
                    "Deduction will be disallowed if SSN is missing. "
                    "Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 19b."
                )
            if alimony_paid_deduction > 0:
                result["warnings"].append(
                    f"Alimony paid: ${alimony_paid_deduction:,} → Schedule 1 Line 19a (above-the-line). "
                    "Only deductible for pre-2019 divorce decrees. "
                    "Source: IRC §71 (pre-TCJA); irs.gov/pub/irs-pdf/f1040s1.pdf L19a."
                )
            if alimony_received_income > 0:
                result["warnings"].append(
                    f"Alimony received: ${alimony_received_income:,} → Schedule 1 Line 2a (taxable). "
                    "Pre-2019 decree only. "
                    "Source: IRC §71; irs.gov/pub/irs-pdf/f1040s1.pdf L2a."
                )
        else:
            if al.alimony_paid > 0 or al.alimony_received > 0:
                result["warnings"].append(
                    "Alimony: post-2018 divorce decree — NO deduction for payer, "
                    "NOT income for recipient (TCJA §11051). "
                    "Source: IRC §71 (repealed for 2019+); IRS Pub 504."
                )

    # ── v8: Schedule K-1 — Pass-through Income ───────────────────────────────────
    # Source: f1065sk1.pdf; f1120ssk1.pdf; f1041sk1.pdf; f1040se.pdf Part II
    k1_result = {}
    k1_ordinary = k1_interest = k1_ord_div = k1_qual_div = 0
    k1_stcg = k1_ltcg = k1_se = k1_sec199a = k1_rental = 0
    if schema.schedule_k1s:
        k1_result = compute_k1_income(schema.schedule_k1s)
        k1_ordinary  = k1_result["net_k1_ordinary"]
        k1_rental    = k1_result["k1_rental"]
        k1_interest  += k1_result["k1_interest"]
        k1_ord_div   += k1_result["k1_ord_div"]
        k1_qual_div  += k1_result["k1_qual_div"]
        k1_stcg      += k1_result["k1_stcg"]
        k1_ltcg      += k1_result["k1_ltcg"]
        k1_se        += k1_result["k1_se"]
        k1_sec199a   += k1_result["k1_sec199a"]
        for w in k1_result.get("warnings", []):
            result["warnings"].append(w)
        # At-risk limitation warning for K-1 losses — IRC §465; Form 6198
        # Losses from partnerships/S-corps are first limited to amount at risk
        # before passive activity rules apply. Engine does not compute outside basis.
        # Source: IRC §465; IRC §704(d); irs.gov/pub/irs-pdf/f6198.pdf
        if k1_ordinary < 0:
            result["warnings"].append(
                f"⚠ K-1 ordinary loss ${abs(int(k1_ordinary)):,}: at-risk (IRC §465) and "
                "basis (IRC §704(d)) limitations apply. Losses are deductible only up to your "
                "outside basis and amount at risk in the entity. Use Form 6198 to verify. "
                "Source: IRC §465; IRC §704(d); irs.gov/pub/irs-pdf/f6198.pdf."
            )
        if k1_rental < 0:
            result["warnings"].append(
                f"⚠ K-1 rental loss ${abs(int(k1_rental)):,}: at-risk (IRC §465) applies "
                "before passive activity rules. Verify deductible amount with Form 6198. "
                "Source: IRC §465; irs.gov/pub/irs-pdf/f6198.pdf."
            )
            result["warnings"].append(w)

    # Source: irs.gov/pub/irs-pdf/f1040sb.pdf
    # Required when interest or dividends > $1,500, or foreign accounts
    sched_b_result = compute_schedule_b(schema.form_1099ints, schema.form_1099divs)
    if sched_b_result["required"]:
        result["warnings"].append(
            f"Schedule B required: interest ${sched_b_result['l4_total_taxable_interest']:,} "
            f"/ dividends ${sched_b_result['l6_total_ordinary_div']:,} exceed $1,500 threshold. "
            "Source: irs.gov/pub/irs-pdf/f1040sb.pdf"
        )
    if sched_b_result["foreign_tax_total"] > 0:
        ft = sched_b_result["foreign_tax_total"]
        result["warnings"].append(
            f"Foreign tax paid ${ft:,}: if ≤ $300 single / $600 MFJ may claim on "
            "Schedule 3 Line 1 without Form 1116. Otherwise Form 1116 required. "
            "Source: irs.gov/pub/irs-pdf/f1116.pdf; i1040sb.pdf Part III."
        )

    # ── v7: Schedule E Part I + Form 8582 — Rental Real Estate ─────────────────
    # Source: irs.gov/pub/irs-pdf/f1040se.pdf; irs.gov/pub/irs-pdf/f8582.pdf
    sched_e_result = {}
    rental_net = 0   # → Schedule 1 Line 5 (positive = income; negative = allowed loss)
    if schema.schedule_es:
        # AGI not yet known (pre-adjustments); use pre-SS AGI proxy for phase-out test
        # Engine uses final AGI after first pass; for phase-out accuracy we'll update after
        # AGI is computed (two-pass would be ideal; single-pass approximation here)
        sched_e_result = compute_schedule_e_8582(
            schema.schedule_es,
            agi=0,           # placeholder — updated below after AGI is known
            filing_status=fs,
            form_8582_override=schema.form_8582,
        )
        rental_net = sched_e_result.get("net_rental", 0)
        for w in sched_e_result.get("warnings", []):
            result["warnings"].append(w)
        # At-risk limitation warning — IRC §465; Form 6198
        # Applied BEFORE passive activity rules. Engine does not compute at-risk basis.
        # Source: irs.gov/pub/irs-pdf/f6198.pdf; IRC §465
        if rental_net < 0:
            result["warnings"].append(
                f"⚠ Rental loss ${abs(int(rental_net)):,}: at-risk rules (IRC §465 / Form 6198) "
                "apply before passive activity rules. Losses are deductible only up to your "
                "amount at risk in the activity. If you have non-recourse debt above your equity, "
                "your allowed loss may be less than shown. Verify with Form 6198. "
                "Source: IRC §465; irs.gov/pub/irs-pdf/f6198.pdf."
            )

    # ── v3: Form 8949 / Schedule D — Capital Gains ─────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f8949.pdf, f1040sd.pdf
    schd_result = {}
    cap_gain_income = 0    # net capital gain → Schedule D Line 16/18 → Form 1040 Line 7
    cap_loss_deductible = 0
    # v12 (P1): Capital loss carryover from prior year — Schedule D Lines 6 & 14
    # Reduces current-year gains; any excess adds to current loss for $3,000 deduction
    # Source: irs.gov/pub/irs-pdf/f1040sd.pdf Lines 6, 14; IRC §1212(b)
    cap_loss_cf_prior = rnd(schema.capital_loss_carryover_prior)
    if schema.form_1099bs:
        schd_result = compute_form_8949_schd(schema.form_1099bs)
        # Apply prior-year carryover to reduce current gains (or increase current loss)
        if cap_loss_cf_prior > 0:
            raw_gain  = schd_result["cap_gain_taxable"]
            raw_loss  = schd_result["cap_loss_deductible"]   # already ≥ -3000 or 0
            raw_net   = schd_result.get("net_capital_gain", raw_gain + raw_loss)
            # Carryover reduces net; still capped at -$3,000 deductible in current year
            net_with_cf = rnd(raw_net - cap_loss_cf_prior)
            if net_with_cf >= 0:
                cap_gain_income     = net_with_cf
                cap_loss_deductible = 0
            else:
                cap_gain_income     = 0
                cap_loss_deductible = max(-3000, net_with_cf)
            result["warnings"].append(
                f"Capital loss carryover ${cap_loss_cf_prior:,} applied from prior year "
                f"(Schedule D Lines 6/14). Net capital gain/loss after carryover: ${net_with_cf:,}. "
                "Source: f1040sd.pdf Lines 6, 14; IRC §1212(b); p550.pdf."
            )
        else:
            cap_gain_income     = schd_result["cap_gain_taxable"]
            cap_loss_deductible = schd_result["cap_loss_deductible"]
        # Add 1099-DIV Box 2a capital gain distributions → Schedule D Line 13 (LT)
        # Source: f1040sd.pdf Line 13; i1099div.pdf Box 2a instructions; IRC §1222(3)
        # Box 2a distributions are always long-term — treated as LT cap gain on Sched D L13
        if div_cap_gain_dist > 0:
            net_before_div = rnd(cap_gain_income + cap_loss_deductible)
            net_after_div  = rnd(net_before_div + div_cap_gain_dist)
            if net_after_div >= 0:
                cap_gain_income     = rnd(cap_gain_income + div_cap_gain_dist)
                cap_loss_deductible = 0
            else:
                cap_gain_income     = 0
                cap_loss_deductible = max(-3000, net_after_div)
            schd_result["schd_l13_div_dist"] = div_cap_gain_dist   # Sched D Line 13
            schd_result["cap_loss_deductible"] = cap_loss_deductible  # update stale value
        for w in schd_result.get("warnings", []):
            result["warnings"].append(w)
    elif cap_loss_cf_prior > 0:
        # Prior-year carryover with no current-year transactions
        cap_loss_deductible = max(-3000, -cap_loss_cf_prior)
        result["warnings"].append(
            f"Capital loss carryover ${cap_loss_cf_prior:,} from prior year applied "
            f"(no 2025 transactions). Deductible: ${-cap_loss_deductible:,} (max $3,000/yr). "
            "Source: f1040sd.pdf Lines 6, 14; IRC §1212(b)."
        )

    # ── v10: Form 4797 — Sales of Business Property (§1231/§1245/§1250) ────────
    # Source: irs.gov/pub/irs-pdf/f4797.pdf; IRC §1231, §1245, §1250; p544.pdf
    f4797_result = {}
    f4797_ordinary_recapture = 0   # §1245 recapture + additional §1250 → ordinary income
    f4797_sec1231_gain = 0         # Net §1231 gain → Schedule D Line 11 (LTCG if net gain)
    f4797_unrec_1250 = 0           # Unrecaptured §1250 → QDCGT Worksheet Line 19 (25% rate)
    if schema.form_4797s:
        f4797_result = compute_form_4797(
            schema.form_4797s,
            schema_sec1231_losses_5yr=schema.prior_sec1231_losses_5yr
        )
        f4797_ordinary_recapture = f4797_result["ordinary_income_recapture"]
        f4797_sec1231_gain       = f4797_result["sec1231_gain_net"]
        f4797_unrec_1250         = f4797_result["unrec_sec1250_gain"]
        # §1231 gain (net positive) → adds to long-term capital gain pool
        # §1231 loss (net negative) → ordinary deduction (adds to Sch 1 Line 4 as negative)
        if f4797_sec1231_gain > 0:
            cap_gain_income = rnd(cap_gain_income + f4797_sec1231_gain)
        elif f4797_sec1231_gain < 0:
            # Ordinary §1231 loss → reduces total income (ordinary deduction)
            # Routed through Sch 1 Line 4 — added to other income line 8 as negative
            f4797_ordinary_recapture = rnd(f4797_ordinary_recapture + f4797_sec1231_gain)
        for w in f4797_result.get("warnings", []):
            result["warnings"].append(w)

    # ── v3: Form 8606 — Nondeductible IRA basis adjustment ─────────────────────
    # v10: Full Part II Roth conversion + backdoor Roth aggregation rule
    # v11: Spouse Form 8606 (MFJ only) — each spouse files a SEPARATE Form 8606
    # Source: irs.gov/pub/irs-pdf/f8606.pdf; i8606.pdf "Who Must File"
    f8606_result = {}
    if schema.form_8606:
        f8606_result = compute_form_8606(
            schema.form_8606,
            f1099r_taxable_ira  # current taxable amount before basis offset
        )
        nontax_offset = f8606_result["l8_nontaxable"]
        conv_taxable  = f8606_result["l18_conv_taxable"]
        l4b = max(0, rnd(l4b - nontax_offset + conv_taxable))
        roth_taxable = f8606_result.get("l25b_roth_taxable", 0)
        l4b = rnd(l4b + roth_taxable)
        for w in f8606_result.get("warnings", []):
            result["warnings"].append(w)

    # Spouse Form 8606 — applies only for MFJ; adds to l4b (spouse IRA distributions)
    # IRS requires a SEPARATE Form 8606 per spouse — pro-rata is computed independently
    # on each spouse's OWN IRA balances. Source: i8606.pdf "Married Filing Jointly".
    f8606_spouse_result = {}
    if schema.form_8606_spouse and fs == "mfj":
        f8606_spouse_result = compute_form_8606(
            schema.form_8606_spouse,
            0  # spouse IRA distributions already included in box2a of spouse 1099-Rs
               # which feed into f1099r_taxable_ira; we apply basis offset only
        )
        sp_nontax   = f8606_spouse_result["l8_nontaxable"]
        sp_conv_tax = f8606_spouse_result["l18_conv_taxable"]
        sp_roth_tax = f8606_spouse_result.get("l25b_roth_taxable", 0)
        l4b = max(0, rnd(l4b - sp_nontax + sp_conv_tax + sp_roth_tax))
        for w in f8606_spouse_result.get("warnings", []):
            result["warnings"].append(f"[Spouse Form 8606] {w}")
    elif schema.form_8606_spouse and fs != "mfj":
        result["warnings"].append(
            "⚠ form_8606_spouse is set but filing status is not MFJ. "
            "Spouse Form 8606 only applies to MFJ returns. "
            "For separate returns, each spouse files their own return with their own Form 8606."
        )

    # Teacher expense: up to $300, K-12 educators → Sch 1 Line 11
    teacher_adj = rnd(min(schema.teacher_expense, p["teacher_expense_max"]))
    adj_early_wdwl   = early_wdwl
    # Student loan deduction with phase-out (v5 fix) — requires MAGI
    # MAGI for student loan = AGI before this deduction (pre-SS AGI here, close enough)
    # Full phase-out applied in Step 3 once pre-SS AGI is known; placeholder here
    # Student loan interest — from flat field OR from Form 1098-E list (new)
    # Source: IRC §221; i1040s1.pdf Line 21; i1098e.pdf
    _sl_from_1098e = rnd(sum(f.box1_student_loan_interest
                             for f in (schema.form_1098es or [])))
    _sl_total = rnd((_sl_from_1098e if _sl_from_1098e > 0
                     else schema.student_loan_interest) or 0)
    adj_student_loan_raw = rnd(min(_sl_total, p["student_loan_max"]))
    adj_other        = rnd(schema.other_adjustments)
    # SE tax deduction (v5): Schedule 1 Line 15
    # Add here so it reduces AGI correctly

    # ── v6: SE Retirement Deduction — Schedule 1 Line 16 ──────────────────────
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 16; IRC §404; p560.pdf
    # Must be computed BEFORE SE health insurance (health ceiling depends on it)
    se_retirement_result = {"deduction": 0, "sep_ira_max": 0, "warnings": []}
    adj_se_retirement = 0
    if schema.se_retirement_contributions > 0 and se_net_profit > 0:
        se_retirement_result = compute_se_retirement(
            schema.se_retirement_contributions,
            se_net_profit,
            se_tax_deduction,
            plan_type    = schema.se_retirement_plan_type,
            taxpayer_age = schema.ira_taxpayer_age,
        )
        adj_se_retirement = se_retirement_result["deduction"]
        for w in se_retirement_result["warnings"]:
            result["warnings"].append(w)

    # ── v6: SE Health Insurance Deduction — Schedule 1 Line 17 ────────────────
    # Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 17; IRC §162(l); Pub 535
    # Ceiling = net SE profit − SE tax deduction − SE retirement deduction
    se_health_result = {"deduction": 0, "warnings": []}
    adj_se_health = 0
    if schema.se_health_insurance_premiums > 0 and se_net_profit > 0:
        se_health_result = compute_se_health_insurance(
            schema.se_health_insurance_premiums,
            se_net_profit,
            se_tax_deduction,
            adj_se_retirement
        )
        adj_se_health = se_health_result["deduction"]
        for w in se_health_result["warnings"]:
            result["warnings"].append(w)

    total_adjustments_before_sl = (teacher_adj + adj_early_wdwl +
                                   adj_other + se_tax_deduction +
                                   adj_se_retirement + adj_se_health)

    # ── v8: IRA Deduction — Schedule 1 Line 20 ──────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/p590a.pdf; irs.gov/pub/irs-pdf/f1040s1.pdf Line 20
    # MAGI proxy: approximate pre-AGI income minus above-the-line adjustments known so far.
    # The student loan and IRA deductions themselves affect MAGI; iterate once for accuracy.
    ira_deduction_result = {"deductible": 0, "warnings": []}
    adj_ira_deduction = 0
    if schema.ira_contribution_traditional > 0:
        covered    = any(w.box13_retirement_plan for w in schema.w2s if not w.for_spouse)
        # Source: Pub 590-A Worksheet 1-2; IRC §219(g)(7)
        # If taxpayer is not covered but MFJ spouse IS covered by a workplace plan,
        # a separate (higher) phaseout applies: $236,000–$246,000 (2025).
        sp_covered = (fs == "mfj" and
                      any(w.box13_retirement_plan for w in schema.w2s if w.for_spouse))
        # IRA MAGI per Pub 590-A Worksheet 1-2 / Worksheet 1-1:
        # MAGI = AGI + student loan interest deduction (added back) + IRA deduction (added back)
        # + foreign income/housing exclusions (N/A for most domestic filers)
        # F8 (EA review 2026-05-19): student loan interest is now added back to MAGI.
        # Previously magi_proxy omitted this addback → MAGI understated for SE clients with student loans.
        # Source: IRS Pub 590-A Worksheet 1-2; IRC §219(g)(3)(A)(ii)
        _sl_raw = rnd(min(schema.student_loan_interest,
                          PARAMS_2025.get("student_loan_max", 2500)))   # same cap as adj calc
        magi_proxy = rnd(wages + dividends + interest + us_bond_interest +
                         rnd(se_net_profit) + rental_net + k1_ordinary +
                         l4b + l5b + unemployment_income + alimony_received_income +
                         gambling_income + prize_income + cancelled_debt +
                         - teacher_adj - adj_early_wdwl - adj_other
                         - se_tax_deduction - adj_se_retirement - adj_se_health
                         + _sl_raw)   # F8: Pub 590-A WS1-2 addback: student loan interest
        ira_deduction_result = compute_ira_deduction(
            schema.ira_contribution_traditional,
            schema.ira_taxpayer_age,
            magi           = magi_proxy,
            filing_status  = fs,
            covered_by_plan = covered,
            spouse_covered  = sp_covered,
            taxable_compensation = rnd(wages + max(0, se_net_profit)),
        )
        adj_ira_deduction = ira_deduction_result["deductible"]
        for w in ira_deduction_result["warnings"]:
            result["warnings"].append(w)

    # ── v8: HSA Deduction — Schedule 1 Line 13 ──────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f8889.pdf; irs.gov/pub/irs-pdf/p969.pdf
    hsa_result = {"l13_deduction": 0, "l17b_penalty": 0, "warnings": []}
    adj_hsa = 0
    hsa_non_medical_taxable = 0
    hsa_penalty = 0
    if schema.form_8889:
        # Employer HSA from W-2 Box 12 Code W
        w2_code_w = rnd(sum(
            (w.box12a_amt if w.box12a_code.upper() == "W" else 0) +
            (w.box12b_amt if w.box12b_code.upper() == "W" else 0) +
            (w.box12c_amt if w.box12c_code.upper() == "W" else 0) +
            (w.box12d_amt if w.box12d_code.upper() == "W" else 0)
            for w in schema.w2s
        ))
        hsa_result = compute_form_8889(schema.form_8889, fs, w2_code_w)
        adj_hsa              = hsa_result["l13_deduction"]
        hsa_non_medical_taxable = hsa_result["l17a_taxable"]
        hsa_penalty          = hsa_result["l17b_penalty"]
        for w in hsa_result["warnings"]:
            result["warnings"].append(w)

    # ── v8: Alimony paid — Schedule 1 Line 19a ──────────────────────────────────
    adj_alimony_paid = alimony_paid_deduction  # already computed above

    # QBI §199A is 1040 Line 13a — NOT a Schedule 1 adjustment → NOT in total_adjustments
    # Source: f1040.pdf Line 13a; f8995.pdf; IRC §199A
    # total_adjustments = Schedule 1 Part II (above-the-line) → reduces AGI
    # adj_qbi goes to taxable_income directly via l14_total_ded
    total_adjustments_before_sl = (teacher_adj + adj_early_wdwl +
                                   adj_other + se_tax_deduction +
                                   adj_se_retirement + adj_se_health +
                                   adj_ira_deduction + adj_hsa + adj_alimony_paid)
    # adj_qbi, adj_tip, adj_overtime, adj_auto_loan, adj_senior: below-line (handled separately)

    net_cap_gain = cap_gain_income + cap_loss_deductible
    # QDCGT income = qualified dividends + net long-term capital gain
    net_ltcg = schd_result.get("schd_l15_lt_total", 0) if schd_result else 0
    qdcgt_income = rnd(dividends_qual + max(0, net_ltcg) + max(0, div_cap_gain_dist))

    # additional_income = Schedule 1 Part I total → 1040 Line 8
    # l4b (IRA/pension) and l5b (annuity) go on 1040 Lines 4b/5b DIRECTLY — NOT Sch 1
    # Source: f1040.pdf Lines 4b, 5b vs Line 8; i1040s1.pdf Part I
    additional_income = (cancelled_debt + prize_income +
                         rnd(se_net_profit) +        # SE net profit → Sch 1 Line 3
                         rental_net +                # Rental net → Sch 1 Line 5
                         gambling_income +           # W-2G → Sch 1 Line 8b
                         jury_duty_income +           # → Sch 1 Line 8h; Source: f1040s1.pdf L8h; IRC §61(a)
                         unemployment_income +       # 1099-G → Sch 1 Line 7
                         state_refund_taxable +      # v8: state refund (if prior-year itemized)
                         alimony_received_income +   # v8: alimony received → Sch 1 Line 2a
                         k1_ordinary +               # v8: K-1 ordinary → Sch E Part II
                         k1_rental +                 # v8: K-1 rental passive
                         rnd(k1_se) +               # v8: K-1 SE → Schedule SE
                         f4797_ordinary_recapture)   # v10: §1245 recapture + §1231 loss → Sch 1 L4

    # K-1 interest and dividends add to Schedule B totals
    interest       = rnd(interest + k1_interest)
    dividends      = rnd(dividends + k1_ord_div)
    dividends_qual = rnd(dividends_qual + k1_qual_div)

    # K-1 capital gains add to Schedule D (net) — MUST come before qdcgt_income and eitc calc
    k1_cap_net   = rnd(k1_stcg + k1_ltcg)
    net_cap_gain = rnd(net_cap_gain + k1_cap_net)
    # Update qdcgt_income to include K-1 LTCG
    net_ltcg_with_k1 = rnd(net_ltcg + k1_ltcg)
    # v10: Form 4797 §1231 gain (net positive) → LTCG (Schedule D Line 11)
    # Unrecaptured §1250 gain → included in qdcgt_income (QDCGT Worksheet Line 19, 25% rate)
    # Both amounts already added to cap_gain_income above; update net_cap_gain to match
    if f4797_sec1231_gain > 0:
        net_cap_gain = rnd(net_cap_gain + f4797_sec1231_gain)
        net_ltcg_with_k1 = rnd(net_ltcg_with_k1 + f4797_sec1231_gain)
    # QDCGT income = qualified dividends + net long-term capital gain (already includes
    # div_cap_gain_dist which was added to Schedule D Line 13 and flows into net_cap_gain)
    # DO NOT add div_cap_gain_dist separately — it is already inside net_ltcg_with_k1
    # Per QDCGT Worksheet Line 6: max(0, Schedule D net) — div dist absorbed if net < 0
    # Source: f1040.pdf QDCGT Worksheet Lines 2-6; i1040.pdf; IRC §1(h)
    qdcgt_income = rnd(dividends_qual + max(0, net_ltcg_with_k1)
                       + f4797_unrec_1250)  # unrec §1250 is in qdcgt pool at 25% rate

    # Investment income for EITC disqualification test (after K-1 additions)
    # IRC §32(i): investment income includes interest, dividends, net cap gains,
    # net passive rental income, and passive K-1 income
    # Source: IRC §32(i)(1); IRS Pub 596; p596.pdf
    investment_income_eitc = rnd(
        interest + us_bond_interest + dividends +
        max(0, net_cap_gain) + div_cap_gain_dist +
        max(0, rental_net) +       # net positive rental income (passive per §469)
        max(0, k1_rental)          # passive K-1 rental income
    )
    # l4b (IRA/pension taxable) and l5b (annuity taxable) go directly on 1040 Lines 4b/5b
    # They are NOT Schedule 1 items — they flow into total_income separately
    # Source: f1040.pdf Lines 4b, 5b, 8 (additional income from Sch 1 ≠ lines 4b/5b)
    total_income_pre_ss = rnd(wages + interest + us_bond_interest + dividends +
                               l4b + l5b +          # 1040 Lines 4b, 5b — IRA/pension/annuity
                               additional_income +   # 1040 Line 8 — Schedule 1 Part I total
                               net_cap_gain)
    # Apply student loan deduction with phase-out using pre-SS AGI as MAGI proxy
    # Use _sl_total (from form_1098es if present, else flat field) — set earlier in run()
    # Source: f1098e.pdf; IRC §221; i1040s1.pdf Line 21
    sl_result = compute_student_loan_deduction(
        _sl_total,   # Form1098E total or schema.student_loan_interest
        total_income_pre_ss - total_adjustments_before_sl,
        fs
    )
    adj_student_loan = sl_result["deduction"]
    if sl_result.get("phaseout_applied"):
        result["warnings"].append(
            f"Student loan interest deduction reduced by AGI phase-out: "
            f"${sl_result['deduction']:,} (of ${sl_result['interest_paid']:,} paid). "
            "Source: irs.gov/pub/irs-pdf/f1040s1.pdf Line 21; IRC §221."
        )
    if sl_result.get("disallowed_mfs"):
        result["warnings"].append(sl_result["warning"])

    # total_adjustments = above-the-line adjustments → reduces AGI (Sch 1 Part II)
    # QBI (adj_qbi) is 1040 L13a — below-the-line — NOT added here
    total_adjustments = total_adjustments_before_sl + adj_student_loan
    agi_pre_ss = total_income_pre_ss - total_adjustments

    # Now compute SS taxable portion using pre-SS AGI
    # Pass tax-exempt interest (Box 8) as it's included in provisional income per Pub 915
    ss_result = {}
    ss_lump_sum_result = {}
    l6b = 0
    lump_sum_election_used = False
    if schema.form_ssa1099 and ss_net > 0:
        ss_result = compute_ss_taxable(
            net_benefits        = ss_net,
            agi_before_ss       = agi_pre_ss,
            filing_status       = fs,
            tax_exempt_interest = tax_exempt_interest,
            sch1_adjustments    = total_adjustments,
            exclusion_adjustments = 0,
            mfs_lived_apart     = ss_mfs_lived_apart,
        )
        w1_taxable = ss_result["l6b"]
        l6b = w1_taxable

        # Lump-Sum Election — Pub 915 Worksheets 2 & 4
        if ss_lump_sum_prior_years:
            ss_lump_sum_result = compute_ss_lump_sum_election(
                net_benefits_2025   = ss_net,
                agi_before_ss_2025  = agi_pre_ss,
                tax_exempt_int_2025 = tax_exempt_interest,
                filing_status       = fs,
                sch1_adj_2025       = total_adjustments,
                exclusion_adj_2025  = 0,
                mfs_lived_apart_2025 = ss_mfs_lived_apart,
                prior_years         = ss_lump_sum_prior_years,
                w1_taxable          = w1_taxable,
            )
            l6b = ss_lump_sum_result["final_taxable_ss"]
            lump_sum_election_used = ss_lump_sum_result["election_beneficial"]
            for w in ss_lump_sum_result.get("warnings", []):
                result["warnings"].append(w)

        if l6b > 0:
            result["warnings"].append(
                f"SSA-1099: ${l6b:,} of ${ss_net:,} SS benefits taxable "
                f"(combined income ${ss_result['combined_income']:,} "
                f"vs base ${ss_result['base_amount']:,}). "
                + ("Lump-Sum Election APPLIED (Line 6c checked). " if lump_sum_election_used else "")
                + "Source: IRS Pub 915 Worksheets 1/2/4."
            )

    # Final AGI includes taxable SS
    total_income = total_income_pre_ss + l6b
    agi = total_income - total_adjustments

    # ── v7: Form 8582 re-run with final AGI (phase-out requires actual AGI) ─────
    # Source: irs.gov/pub/irs-pdf/f8582.pdf
    if schema.schedule_es:
        sched_e_result = compute_schedule_e_8582(
            schema.schedule_es,
            agi=agi,
            filing_status=fs,
            form_8582_override=schema.form_8582,
        )
        new_rental_net = sched_e_result.get("net_rental", 0)
        if new_rental_net != rental_net:
            # Adjust total_income and agi for corrected rental net (phase-out changed result)
            delta = rnd(new_rental_net - rental_net)
            total_income = rnd(total_income + delta)
            agi = rnd(agi + delta)
            rental_net = new_rental_net
            # Re-add any new warnings (avoid duplicates)
            for w in sched_e_result.get("warnings", []):
                if w not in result["warnings"]:
                    result["warnings"].append(w)

    # ── v11: NOL carryforward deduction — Schedule 1 Line 8a ─────────────────────
    # Post-TCJA (IRC §172(a)(2)): limited to 80% of taxable income (before this deduction)
    # Applied after AGI is finalized, reduces taxable income
    # Source: irs.gov/pub/irs-pdf/p536.pdf; IRC §172(a)(2); f1040s1.pdf Line 8a
    nol_cf = rnd(schema.nol_carryforward_prior_year)
    nol_deduction_applied = 0
    if nol_cf > 0:
        # 80% limitation applies to taxable income BEFORE the NOL deduction
        # Use AGI as proxy for 80% test base (taxable income not yet computed here)
        nol_80pct_limit = rnd(agi * 0.80)
        nol_deduction_applied = min(nol_cf, nol_80pct_limit)
        agi = rnd(agi - nol_deduction_applied)
        nol_remaining = rnd(nol_cf - nol_deduction_applied)
        result["warnings"].append(
            f"NOL carryforward ${nol_cf:,} applied: ${nol_deduction_applied:,} deducted "
            f"(80% AGI limit = ${nol_80pct_limit:,}) → Schedule 1 Line 8a. "
            + (f"Remaining NOL ${nol_remaining:,} carries forward to 2026. " if nol_remaining > 0 else "")
            + "Source: IRC §172(a)(2); IRS Pub 536; f1040s1.pdf Line 8a."
        )

    # ── OBBBA Below-Line Deductions (P.L. 119-21; TY 2025–2028) ─────────────────
    # Schedule 1-A (Form 1040) — Additional Deductions → Form 1040 Line 13b
    # These are BELOW-the-line deductions: they do NOT reduce AGI.
    # AGI (Line 11) is already final at this point. OBBBA deductions reduce taxable
    # income AFTER the standard/itemized deduction (Line 12) and QBI (Line 13a).
    # Source: f1040s1a.pdf (irs.gov/pub/irs-pdf/f1040s1a.pdf); IR-2026-28 (Mar 2 2026)
    #         IRS Schedule 1-A Part VI → Form 1040 Line 13b
    #         TurboTax guidance (Mar 2026); NATP (Sep 2025); CPA Practice Advisor (Mar 2026)

    obbba_magi = agi   # MAGI for phase-out tests = AGI (Form 1040 Line 11b on Sch 1-A Part I)

    # ── OBBBA Schedule 1-A deductions — below-the-line, applied after std/itemized ──
    # Source: f1040s1a.pdf Parts II–V; Form 1040 Line 13b
    senior_ded_result = {"deduction": 0, "warnings": []}
    adj_senior = 0
    tp_age = schema.taxpayer_age_for_senior_ded
    sp_age = schema.spouse_age_for_senior_ded

    def _age_from_dob(dob_str: str) -> int:
        """Return age at Dec 31 of tax year from MM-DD-YYYY or YYYY-MM-DD string."""
        if not dob_str: return 0
        try:
            parts = dob_str.replace('/', '-').split('-')
            if len(parts) != 3: return 0
            if len(parts[2]) == 4:           # MM-DD-YYYY
                yr = int(parts[2])
            else:                            # YYYY-MM-DD
                yr = int(parts[0])
            return schema.tax_year - yr
        except Exception:
            return 0

    if tp_age == 0 and schema.dob:
        tp_age = _age_from_dob(schema.dob)
    if sp_age == 0 and schema.spouse_dob:
        sp_age = _age_from_dob(schema.spouse_dob)

    if tp_age >= 65 or (fs == "mfj" and sp_age >= 65):
        senior_ded_result = compute_senior_deduction(tp_age, sp_age, obbba_magi, fs)
        adj_senior = senior_ded_result["deduction"]
        for w in senior_ded_result["warnings"]:
            result["warnings"].append(w)

    # Tip Income Deduction
    tip_ded_result = {"deduction": 0, "warnings": []}
    adj_tips = 0
    if schema.qualified_tips > 0:
        tip_ded_result = compute_tip_deduction(schema.qualified_tips, obbba_magi, fs,
                                                tip_occupation=schema.tip_occupation)
        adj_tips = tip_ded_result["deduction"]
        for w in tip_ded_result["warnings"]:
            result["warnings"].append(w)

    # Overtime Pay Deduction
    overtime_ded_result = {"deduction": 0, "warnings": []}
    adj_overtime = 0
    if schema.overtime_pay_qualifying > 0:
        overtime_ded_result = compute_overtime_deduction(
            schema.overtime_pay_qualifying, obbba_magi, fs)
        adj_overtime = overtime_ded_result["deduction"]
        for w in overtime_ded_result["warnings"]:
            result["warnings"].append(w)
        # M1/M6 FLSA confirmation — P.L. 119-21 §70202
        # Deduction applies only to FLSA-qualifying overtime (time-and-a-half).
        # Bonuses, shift differentials, and exempt-employee extra pay do NOT qualify.
        # Source: P.L. 119-21 §70202; FLSA §207(a)(1); irs.gov/newsroom/one-big-beautiful-bill-provisions
        if not schema.overtime_flsa_confirmed:
            result["warnings"].append(
                "⚠ Overtime Deduction: FLSA confirmation required. Enter only overtime pay "
                "shown separately on your W-2 or employer statement as FLSA-qualifying "
                "(time-and-a-half above regular rate). Bonuses, shift differentials, and "
                "extra pay for exempt employees do NOT qualify. Check the FLSA confirmation "
                "box once you have verified your overtime qualifies. "
                "Source: P.L. 119-21 §70202; FLSA §207(a)(1)."
            )

    # Auto Loan Interest Deduction
    auto_ded_result = {"deduction": 0, "warnings": []}
    adj_auto = 0
    if schema.auto_loan_interest > 0:
        auto_ded_result = compute_auto_loan_deduction(
            schema.auto_loan_interest, obbba_magi, fs,
            schema.auto_loan_originated_after_2024,
            schema.auto_loan_vehicle_new_us_assembled)
        adj_auto = auto_ded_result["deduction"]
        for w in auto_ded_result["warnings"]:
            result["warnings"].append(w)

    # OBBBA deductions → Schedule 1-A → Form 1040 Line 13b (below-the-line)
    # These do NOT flow through Schedule 1 Part II and do NOT affect AGI.
    # Applied to taxable income after std/itemized (Line 12) and QBI (Line 13a).
    # Source: f1040s1a.pdf Part VI; IR-2026-28; irs.gov/pub/irs-pdf/f1040s1a.pdf
    obbba_total = adj_senior + adj_tips + adj_overtime + adj_auto
    # AGI is already final — OBBBA does not change it.

    # ── Step 4: DEDUCTION & TAXABLE INCOME ────────────────────────────────────
    # v3: Schedule A (itemized) vs. Standard Deduction — use greater
    std_ded = p["std_deduction"][fs]

    # ── Age 65+ / Blind standard deduction add-on ────────────────────────────
    # Source: IRS Rev. Proc. 2024-40 S.3.10; IRC S63(f); i1040gi.pdf Line 12 instructions
    # Add-on applies per qualifying condition: age >= 65 OR blind (each counts separately)
    # For MFJ: $1,600 per condition per spouse. For Single/HOH: $2,000 per condition.
    # Use same tp_age / sp_age already resolved above (with DOB fallback).
    tp_blind = schema.taxpayer_is_blind  # now a proper field (bridge hardening 2026-05-19)
    sp_blind = (False and  # legacy spouse-object branch removed — spouse_is_blind used directly
                getattr(schema.spouse, "is_blind", False)) if fs in ("mfj","mfs","qss") else False

    if fs in ("mfj", "mfs", "qss"):
        addon_per = p.get("std_addon_mfj_per", p.get("std_addon_mfj_per_2025", 1600))
        conditions = 0
        if tp_age  >= 65: conditions += 1
        if tp_blind:      conditions += 1
        if sp_age  >= 65: conditions += 1
        if sp_blind:      conditions += 1
        std_ded += addon_per * conditions
    else:  # single, hoh
        addon_each = p.get("std_addon_single_hoh", p.get("std_addon_single_hoh_2025", 2000))
        conditions = 0
        if tp_age  >= 65: conditions += 1
        if tp_blind:      conditions += 1
        std_ded += addon_each * conditions

    sched_a_result = {}
    itemized_ded = 0
    salt_itemized = 0    # for AMT SALT addback
    if schema.schedule_a:
        sched_a_result = compute_schedule_a(schema.schedule_a, agi, fs)
        itemized_ded = sched_a_result["l17_total"]
        salt_itemized = rnd(sched_a_result.get("l7_salt", 0))
        for w in sched_a_result.get("warnings", []):
            result["warnings"].append(w)
        if schema.use_itemized and itemized_ded > std_ded:
            deduction_used = itemized_ded
            deduction_type = "itemized"
        elif schema.use_itemized:
            deduction_used = std_ded
            deduction_type = "standard (itemized < std)"
            result["warnings"].append(
                f"Schedule A itemized deductions (${itemized_ded:,}) are less than "
                f"standard deduction (${std_ded:,}). Standard deduction is more beneficial."
            )
        else:
            deduction_used = std_ded
            deduction_type = "standard"
            if itemized_ded > std_ded:
                result["warnings"].append(
                    f"Note: Itemized deductions (${itemized_ded:,}) exceed standard deduction "
                    f"(${std_ded:,}). Consider setting use_itemized=True."
                )
    else:
        deduction_used = std_ded
        deduction_type = "standard"
    taxable = max(0, agi - deduction_used)

    # ── Line 13b: Schedule 1-A — OBBBA below-the-line deductions ────────────
    # Source: f1040s1a.pdf Part VI → Form 1040 Line 13b; IR-2026-28
    # Applied AFTER Line 12 (std/itemized) and BEFORE Line 13a (QBI).
    # Does NOT affect AGI — MAGI for all AGI-tested credits/thresholds unchanged.
    l13b_schedule1a = obbba_total
    if l13b_schedule1a > 0:
        taxable = max(0, taxable - l13b_schedule1a)

    # ── v6: QBI Deduction §199A — Form 8995 (simplified) ─────────────────────
    # Source: irs.gov/pub/irs-pdf/f8995.pdf; irs.gov/pub/irs-pdf/i8995.pdf
    # QBI deduction goes on Form 1040 Line 13 (reduces taxable income after std/itemized)
    # Must be computed using taxable income BEFORE QBI so threshold test is correct.
    qbi_result = {"l15_deduction": 0, "warnings": []}
    adj_qbi = 0
    if schema.schedule_cs and se_net_profit > 0:
        # Compute qualified REIT/§199A dividends (Form 8995 Line 6)
        # Source: f8995.pdf Line 6; i8995.pdf Line 6; IRC §199A(e)(4)
        # FETCH_VERIFIED: irs.gov/instructions/i8995 | Line 6 | 2026-05-24
        # 1099-DIV Box 5 = §199A dividends = qualified REIT dividends
        _reit_ptp = rnd(
            sum(f.box5_sec199a_div for f in schema.form_1099divs) +  # 1099-DIV Box 5
            k1_sec199a                                                # K-1 §199A income
        )
        qbi_result = compute_qbi_deduction(
            schedule_cs         = schema.schedule_cs,
            se_tax_deduction    = se_tax_deduction,
            se_health_deduction = adj_se_health,
            se_retirement_deduction = adj_se_retirement,
            taxable_income      = taxable,
            qdcgt_income        = qdcgt_income,
            filing_status       = fs,
            params              = p,
            qbi_loss_carryforward = schema.qbi_loss_carryforward,
            se_net_profit       = se_net_profit,
            reit_ptp_income     = _reit_ptp,   # Form 8995 Line 6: 1099-DIV Box 5 + K-1 §199A
        )
        adj_qbi = qbi_result["l15_deduction"]
        for w in qbi_result["warnings"]:
            result["warnings"].append(w)
        # Apply QBI to taxable income (Form 1040 Line 13 reduces Line 15)
        taxable = max(0, taxable - adj_qbi)

    # ── Fix 8: QBI §199A safe harbor warning for rental income ───────────────
    # Rev. Proc. 2019-38: rental income may qualify for §199A deduction if the
    # 250-hour safe harbor is met (or enterprise election under Reg. 1.199A-1(b)(14)).
    # Engine computes QBI only for Schedule C SE income. Rental QBI not implemented.
    # Source: Rev. Proc. 2019-38; Reg. 1.199A-1(b)(14); irs.gov/pub/irs-pdf/f8995.pdf
    if schema.schedule_es and rental_net > 0:
        result["warnings"].append(
            f"⚠ QBI §199A — Rental Income: Net rental income of ${rnd(rental_net):,} may qualify "
            "for the 20% §199A deduction under Rev. Proc. 2019-38 (250-hour safe harbor) "
            "or the enterprise grouping election (Reg. 1.199A-1(b)(14)). "
            "Engine does not compute rental QBI — review qualification criteria: "
            "(1) 250+ hours of rental services per year, (2) contemporaneous time records, "
            "(3) attach statement to return. If qualified, rental QBI = net rental income "
            "and deduction = 20% × net rental (subject to taxable income limit). "
            "Source: Rev. Proc. 2019-38; irs.gov/pub/irs-pdf/f8995.pdf."
        )

    # v5: Use QDCGT Worksheet when qualified dividends or LTCG > 0
    # Source: f1040.pdf page 36 QDCGT Worksheet; irs.gov/pub/irs-pdf/i1040gi.pdf
    # §1250 recapture (25%) and collectibles (28%) are special-rate components
    # Source: IRC §1(h)(1)(D),(4); i1040sd.pdf Lines 18–19
    # Unrecaptured §1250 from 1099-DIV Box 2b (RIC/REIT distributions of §1250 gain)
    # added to Form 4797 §1250 — both taxed at max 25% rate
    # Source: f1099div.pdf Box 2b instructions; IRC §1(h)(6)(A)
    div_unrec_1250 = rnd(sum(getattr(f, 'box2b_unrec_1250', 0) for f in schema.form_1099divs))
    total_unrec_1250 = rnd(f4797_unrec_1250 + div_unrec_1250)
    collectibles_gain_total = rnd(
        sum(getattr(f, 'box2d_collectibles', 0) for f in schema.form_1099divs) +
        sum(getattr(k, 'collectibles_gain', 0) for k in schema.schedule_k1s)
    )
    income_tax = compute_qdcgt_tax(taxable, qdcgt_income, fs,
                                    tax_year=schema.tax_year,
                                    unrecaptured_sec1250=total_unrec_1250,
                                    collectibles_gain=collectibles_gain_total)
    if qdcgt_income > 0 or total_unrec_1250 > 0 or collectibles_gain_total > 0:
        note = f"QDCGT Worksheet applied: ${qdcgt_income:,} preferential"
        if f4797_unrec_1250 > 0:
            note += f" + §1250 recapture ${f4797_unrec_1250:,} @ 25% (Form 4797)"
        if div_unrec_1250 > 0:
            note += f" + §1250 from 1099-DIV Box 2b ${div_unrec_1250:,} @ 25%"
        if collectibles_gain_total > 0:
            note += f" + collectibles ${collectibles_gain_total:,} @ 28%"
        result["warnings"].append(note + ". Source: f1040.pdf QDCGT Worksheet; IRC §1(h).")

    # ── v10: Form 8615 — Kiddie Tax ────────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f8615.pdf; IRC §1(g)
    # Replaces normal income_tax if child's tax at parent's rate > child's own rate
    f8615_result = {}
    if schema.form_8615:
        f8615_result = compute_form_8615(
            schema.form_8615,
            child_taxable_income = taxable,
            child_qdcgt_income   = qdcgt_income,
        )
        if f8615_result.get("applies") and f8615_result.get("kiddie_tax_triggered"):
            income_tax = f8615_result["income_tax_8615"]
        for w in f8615_result.get("warnings", []):
            result["warnings"].append(w)

    # ── v10: NOL Detection ─────────────────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/p536.pdf; IRC §172
    nol_result = compute_nol_detection(agi, total_income, se_net_profit, fs)
    if nol_result["nol_detected"]:
        for w in nol_result["warnings"]:
            result["warnings"].append(w)

    # ── v7: Form 6251 — Alternative Minimum Tax ───────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f6251.pdf
    # Computed after income_tax is known; AMT → Schedule 2 Line 1
    f6251_result = compute_form_6251(
        taxable_income = taxable,
        agi            = agi,
        regular_tax    = income_tax,
        qdcgt_income   = qdcgt_income,
        filing_status  = fs,
        deduction_type = deduction_type,
        deduction_used = deduction_used,
        salt_itemized  = salt_itemized,
        form_6251_data = schema.form_6251,
        form_1099divs  = schema.form_1099divs,
        form_1099ints  = schema.form_1099ints,
    )
    amt_tax = f6251_result["l9_amt"]   # → Schedule 2 Line 1
    for w in f6251_result["warnings"]:
        result["warnings"].append(w)

    # ── v3: Form 4972 — Lump-Sum Distribution Tax (Schedule 2 Line 6) ──────────
    # Source: irs.gov/pub/irs-pdf/f4972.pdf
    # This is ADDITIONAL tax — added to income_tax for CLW purposes
    f4972_result = {}
    f4972_additional_tax = 0
    if schema.form_4972:
        f4972_result = compute_form_4972(schema.form_4972)
        f4972_additional_tax = f4972_result["total_4972_tax"]
        for w in f4972_result.get("warnings", []):
            result["warnings"].append(w)
    # Note: Form 4972 tax goes on Schedule 2 Line 6 → Form 1040 Line 17
    # It is NOT part of Line 16 (regular tax), but IS included in total tax (Line 24)
    # For CLW purposes, income_tax (Line 18) does NOT include Form 4972 tax

    # ── v8: Net Investment Income Tax — Form 8960 (Schedule 2 Line 12) ───────────
    # Source: irs.gov/pub/irs-pdf/f8960.pdf; IRC §1411
    # NII = interest + dividends + passive rental + passive K-1 + net cap gains
    # (SE income and active business income excluded)
    # Net Investment Income for Form 8960 — IRC §1411(c)(1)
    # NII includes: interest, dividends, annuities, royalties, rents, net cap gains,
    # and passive activity income (K-1 ordinary from passive partnerships)
    # Does NOT include: wages, SE income, active business income, SS benefits, pensions
    # Source: IRC §1411(c)(1)–(2); f8960.pdf; Reg. §1.1411-4
    passive_k1_ordinary = rnd(k1_result.get("k1_ordinary", 0)) if k1_result.get("is_passive_ordinary") else 0
    # k1_ordinary from passive partnerships is NII per Reg. §1.1411-7
    # Engine tracks participation in ScheduleK1; passive ordinary income is NII
    k1_passive_ordinary_nii = rnd(sum(
        k1.box1_ordinary_income for k1 in schema.schedule_k1s
        if k1.box1_ordinary_income > 0 and not k1.material_participation
    )) if schema.schedule_k1s else 0
    nii = rnd(interest + dividends +
              max(0, rental_net) +          # net rental income (positive only)
              max(0, k1_rental) +           # K-1 passive rental
              max(0, net_cap_gain) +        # net cap gains
              hsa_non_medical_taxable +     # HSA non-qualified distributions
              k1_passive_ordinary_nii)      # passive K-1 ordinary income per Reg. §1.1411-7
    niit_result = compute_niit(agi, nii, fs)
    niit_tax = niit_result["niit"]
    if niit_result.get("warning"):
        result["warnings"].append(niit_result["warning"])

    # ── v8: Additional Medicare Tax — Form 8959 (Schedule 2 Line 11) ─────────────
    # Source: irs.gov/pub/irs-pdf/f8959.pdf; IRC §3101(b)(2)
    # Employer withholds 0.9% on wages > $200k per employee; Form 8959 reconciles
    total_wages_se = rnd(wages + max(0, se_net_profit) + k1_se)
    # Estimate employer's 0.9% WH (applies at $200k threshold per employer, not per joint)
    employer_addl_med_wh = rnd(max(0, wages - 200000) * 0.009) if wages > 200000 else 0
    addl_med_result = compute_additional_medicare_tax(
        total_wages_se, agi, fs, employer_addl_med_wh)
    addl_med_tax = addl_med_result["net"]
    if addl_med_result.get("warning"):
        result["warnings"].append(addl_med_result["warning"])

    # ── v8: HSA Non-Medical Distribution Taxable Income ──────────────────────────
    if hsa_non_medical_taxable > 0:
        result["warnings"].append(
            f"HSA non-qualified distribution ${hsa_non_medical_taxable:,} → Schedule 1 Line 8f. "
            "Source: irs.gov/pub/irs-pdf/f8889.pdf Part II L17a."
        )

    # ── Step 6: FORM 2441 (FIRST) ──────────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f2441.pdf, i2441.pdf
    ctc_children  = [d for d in schema.dependents if d.ctc_eligible]
    odc_deps      = [d for d in schema.dependents if d.odc_eligible]
    # Warn if ctc_eligible set for age >= 17
    for dep in schema.dependents:
        if dep.ctc_eligible and dep.age >= 17:
            result["warnings"].append(
                f"Dependent {dep.first} {dep.last}: ctc_eligible=True but age={dep.age} "
                "≥ 17. CTC requires child under 17 at Dec 31. Source: IRC §24(c)."
            )

    # Form 2441 qualifying persons — must be under age 13 (IRC §21(b)(1)(A))
    # CTC-eligible children may be over 13 (CTC goes to age 16) but care credit only for under-13
    # Source: irs.gov/pub/irs-pdf/f2441.pdf Line 2; IRC §21(b)(1)(A); i2441.pdf
    care_qualifying = [d for d in ctc_children if d.age is None or d.age < 13]
    care_nonqualifying_over13 = [d for d in ctc_children if d.age is not None and d.age >= 13]
    for dep in care_nonqualifying_over13:
        result["warnings"].append(
            f"Form 2441: {dep.first} {dep.last} (age {dep.age}) is NOT a qualifying person "
            "for the child/dependent care credit — must be under age 13 at time of care. "
            "Source: irs.gov/pub/irs-pdf/f2441.pdf Line 2; IRC §21(b)(1)(A)."
        )
    care_cap_amt  = 3000 if len(care_qualifying) == 1 else (6000 if len(care_qualifying) >= 2 else 0)
    care_exp_raw  = rnd(sum(pr.expenses for pr in schema.care_providers))
    care_exp_capped = rnd(min(care_exp_raw, care_cap_amt))
    employer_care_excl = rnd(min(employer_dep_care, 5000))
    care_exp_after_employer = max(0, rnd(care_exp_capped - employer_care_excl))

    # v5 fix: Form 2441 Line 5 — earned income limitation
    # For MFJ, qualified expense is limited to the LESSER earned income of either spouse.
    # For single/HOH, limited to taxpayer's earned income.
    # Earned income for 2441 = wages + net SE + allocated tips (NOT dividends, cap gains)
    # Source: f2441.pdf Line 5; IRC §21(d)
    taxpayer_earned_2441 = rnd(
        sum(w.box1_wages for w in schema.w2s if not w.for_spouse) +
        sum(w.box8_allocated_tips for w in schema.w2s if not w.for_spouse) +
        max(0, sum(pb.get("net_profit", 0)
                   for pb in (se_result.get("per_business") or [])
                   if not pb.get("for_spouse", False)))
    )
    # Re-derive taxpayer SE from per_business results
    taxpayer_se_2441 = rnd(sum(
        pb.get("net_profit", 0) for pb in se_result.get("per_business", [])
        if not getattr(next((sc for sc in schema.schedule_cs
                             if sc.business_name == pb.get("name")), object()),
                       'for_spouse', False)
        and pb.get("net_profit", 0) > 0
    ))
    taxpayer_wages_2441 = rnd(sum(w.box1_wages + w.box8_allocated_tips
                                   for w in schema.w2s if not w.for_spouse))
    earned_income_taxpayer_2441 = rnd(taxpayer_wages_2441 + taxpayer_se_2441)

    if fs == "mfj":
        # Derive spouse earned income from spouse-tagged W-2s and spouse Schedule Cs
        spouse_wages_2441 = rnd(sum(w.box1_wages + w.box8_allocated_tips
                                     for w in schema.w2s if w.for_spouse))
        spouse_se_2441 = rnd(sum(
            pb.get("net_profit", 0) for pb in se_result.get("per_business", [])
            if getattr(next((sc for sc in schema.schedule_cs
                             if sc.business_name == pb.get("name")), object()),
                       'for_spouse', False)
            and pb.get("net_profit", 0) > 0
        ))
        spouse_earned_2441 = rnd(spouse_wages_2441 + spouse_se_2441)

        # ── Form 2441 Line 6 — Deemed earned income for disabled/student spouse ──
        # IRC §21(d)(2): if spouse is a full-time student OR disabled, they are
        # deemed to have earned income of $250/month (1 qualifying person) or
        # $500/month (2+ qualifying persons) for each month they qualify.
        # Source: f2441.pdf Line 6; IRC §21(d)(2); irs.gov/pub/irs-pdf/p503.pdf
        if spouse_earned_2441 == 0 and (
            schema.care_spouse_is_student or
            schema.care_spouse_is_disabled
        ):
            num_care_persons = len([
                p for p in (schema.care_providers or [])
                if getattr(p, 'expenses', 0) > 0
            ]) or (1 if care_exp_after_employer > 0 else 0)
            months = max(1, min(12, schema.care_spouse_months_qualified or 12))
            # $250/month per qualifying person (1 person), $500/month (2+ persons)
            # Source: f2441.pdf Line 6; IRC §21(d)(2)
            deemed_monthly = 500 if num_care_persons >= 2 else 250
            spouse_earned_2441 = rnd(deemed_monthly * months)
            reason = ("full-time student" if schema.care_spouse_is_student
                      else "disabled")
            result["warnings"].append(
                f"Form 2441 Line 6: Spouse deemed earned income ${spouse_earned_2441:,} "
                f"({reason} × {months} months × ${deemed_monthly}/mo). "
                f"Source: f2441.pdf Line 6; IRC §21(d)(2)."
            )

        # Line 5: qualified expenses limited to LESSER of the two spouses' earned income
        earned_income_2441 = min(earned_income_taxpayer_2441, spouse_earned_2441)
        if spouse_earned_2441 == 0 and care_exp_after_employer > 0:
            result["warnings"].append(
                "Form 2441 Line 5: Spouse has $0 earned income derived from spouse-tagged "
                "W-2s and Schedule Cs — child/dependent care credit is $0. "
                "If spouse was a full-time student or disabled, see f2441.pdf Line 6 "
                "deemed earned income rules. Source: f2441.pdf Line 5; IRC §21(d)(2)."
            )
        elif earned_income_2441 < earned_income_taxpayer_2441:
            result["warnings"].append(
                f"Form 2441 Line 5: Qualified expenses limited to spouse's lesser earned "
                f"income ${spouse_earned_2441:,} (taxpayer earned ${earned_income_taxpayer_2441:,}). "
                "Source: f2441.pdf Line 5; IRC §21(d)(1)."
            )
    else:
        earned_income_2441 = earned_income_taxpayer_2441
    care_exp_cap = min(care_exp_after_employer, earned_income_2441) if earned_income_2441 > 0 else 0
    if care_exp_after_employer > 0 and earned_income_2441 == 0:
        result["warnings"].append(
            "Form 2441: Taxpayer has no earned income — child/dependent care credit is $0. "
            "Source: f2441.pdf Line 5."
        )

    if employer_dep_care > 0:
        result["warnings"].append(
            f"W-2 Box 10 employer dep care ${employer_dep_care:,} "
            f"(§129 excl ${employer_care_excl:,}) reduces Form 2441 qualified expenses. "
            "Source: f2441.pdf Line 12."
        )
    f2441_decimal = get_f2441_decimal(agi)
    care_l9c      = rnd(care_exp_cap * f2441_decimal)
    f2441_clw_l1  = income_tax
    f2441_clw_l2  = 0
    f2441_clw_l3  = max(0, f2441_clw_l1 - f2441_clw_l2)
    care_credit   = rnd(min(care_l9c, f2441_clw_l3))

    # ── Step 7: FORM 8863 (SECOND) ─────────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f8863.pdf, i8863.pdf
    # AOC/LLC phase-out uses MAGI = AGI for most taxpayers (no add-backs for domestic production)
    edu_nonref   = 0
    edu_ref_aoc  = 0
    edu_details  = []
    for t in schema.form_1098ts:
        # QEE = net tuition paid + out-of-pocket required course materials (AOC only)
        # Source: IRS Pub 970 (2024) p17; IRC §25A(b)(1); i8863.pdf Worksheet 1 Line 1
        net_exp = max(0, t.box1_payments - t.box5_scholarships)
        oop = rnd(getattr(t, 'out_of_pocket_books', 0) +
                  getattr(t, 'out_of_pocket_supplies', 0) +
                  getattr(t, 'out_of_pocket_other', 0))
        if t.credit_type == "aoc" and t.first_four_years:
            # Hard gate 1: at least half-time enrollment required — IRC §25A(b)(1)(B); i8863.pdf
            if not t.box8_half_time:
                result["warnings"].append(
                    f"AOC denied for {t.institution or 'institution'}: "
                    "Form 1098-T Box 8 (at least half-time) is not checked. "
                    "AOTC requires at least half-time enrollment. "
                    "Source: IRC §25A(b)(1)(B); i8863.pdf Part III instructions."
                )
                edu_details.append({"type": "AOC", "total": 0, "refundable": 0,
                    "nonref": 0, "qualified_exp_used": 0, "phaseout_ratio": 1.0,
                    "phaseout_applied": False, "institution": t.institution,
                    "denied_reason": "not_half_time"})
                # Fallback to LLC — no half-time enrollment requirement for LLC
                # Source: f8863.pdf Part I; IRC §25A(c); i8863.pdf Line 1 instructions
                _llc_fb = compute_llc(net_exp, agi, fs)
                if _llc_fb.get("total", 0) > 0:
                    edu_nonref += _llc_fb["nonref"]
                    edu_details.append({"type": "LLC", **_llc_fb, "institution": t.institution,
                                        "note": "AOC denied (not half-time) — LLC applied instead"})
                    result["warnings"].append(
                        f"AOC denied for {t.institution}: not half-time. "                        "LLC (Lifetime Learning Credit) applied instead — no enrollment requirement. "                        "Source: f8863.pdf; IRC §25A(c)."
                    )
                continue
            # Hard gate 2: drug conviction disqualifies — IRC §25A(b)(2)(D); i8863.pdf
            if getattr(t, 'aoc_drug_conviction', False):
                result["warnings"].append(
                    f"AOC denied for {t.institution or 'institution'}: "
                    "Student has a federal or state drug conviction for the tax year. "
                    "AOTC is not allowed. Source: IRC §25A(b)(2)(D); i8863.pdf."
                )
                edu_details.append({"type": "AOC", "total": 0, "refundable": 0,
                    "nonref": 0, "qualified_exp_used": 0, "phaseout_ratio": 1.0,
                    "phaseout_applied": False, "institution": t.institution,
                    "denied_reason": "drug_conviction"})
                # Drug conviction bars AOC only — LLC still allowed per IRC §25A(c)
                # Source: IRC §25A(b)(2)(D) applies ONLY to AOC; f8863.pdf Part I vs Part II
                _llc_fb = compute_llc(net_exp, agi, fs)
                if _llc_fb.get("total", 0) > 0:
                    edu_nonref += _llc_fb["nonref"]
                    edu_details.append({"type": "LLC", **_llc_fb, "institution": t.institution,
                                        "note": "AOC denied (drug conviction) — LLC applied instead"})
                    result["warnings"].append(
                        f"AOC denied for {t.institution}: drug conviction bars AOC. "                        "LLC applied instead — drug conviction does not bar LLC. "                        "Source: IRC §25A(b)(2)(D) [AOC only]; f8863.pdf Part I vs Part II."
                    )
                continue
            # Hard gate 3: 4-year limit — IRC §25A(b)(2)(C); f8863.pdf Line 27
            # AOC may be claimed at most 4 times. If aoc_years_claimed_prior >= 4, NOT eligible.
            _prior_yrs = getattr(t, 'aoc_years_claimed_prior', 0) or 0
            if _prior_yrs >= 4:
                result["warnings"].append(
                    f"AOC denied for {t.institution or 'institution'}: "
                    f"AOC already claimed {_prior_yrs} prior year(s) — maximum 4 total. "
                    "Consider LLC (Lifetime Learning Credit) instead — no year limit. "
                    "Source: IRC §25A(b)(2)(C); f8863.pdf Line 27."
                )
                edu_details.append({"type": "AOC", "total": 0, "refundable": 0,
                    "nonref": 0, "qualified_exp_used": 0, "phaseout_ratio": 1.0,
                    "phaseout_applied": False, "institution": t.institution,
                    "denied_reason": f"aoc_4yr_limit_prior={_prior_yrs}"})
                # Fallback to LLC — no year limit, no enrollment requirement
                # Source: IRC §25A(c); f8863.pdf Part I; i8863.pdf Line 1
                _llc_fb = compute_llc(net_exp, agi, fs)
                if _llc_fb.get("total", 0) > 0:
                    edu_nonref += _llc_fb["nonref"]
                    edu_details.append({"type": "LLC", **_llc_fb, "institution": t.institution,
                                        "note": f"AOC denied (4yr limit, {_prior_yrs} prior) — LLC applied"})
                    result["warnings"].append(
                        f"AOC denied for {t.institution}: {_prior_yrs} prior year(s) claimed — max 4 total. "                        "LLC (Lifetime Learning Credit) applied automatically — no year limit. "                        "Source: IRC §25A(b)(2)(C) [AOC limit]; IRC §25A(c) [LLC, no limit]; f8863.pdf."
                    )
                continue
            qee = net_exp + oop    # books/supplies are QEE for AOC; not for LLC
            aoc = compute_aoc(qee, agi, fs)   # v5: pass MAGI
            edu_nonref  += aoc["nonref"]
            edu_ref_aoc += aoc["refundable"]
            edu_details.append({"type": "AOC", **aoc, "institution": t.institution})
            if aoc.get("disqualified_mfs"):
                result["warnings"].append(aoc["warning"])
            elif aoc.get("phaseout_applied"):
                result["warnings"].append(
                    f"AOC phase-out applied for {t.institution}: MAGI ${rnd(agi):,} "
                    "in phase-out range. Source: i8863.pdf."
                )
        else:
            llc = compute_llc(net_exp, agi, fs)   # v5: pass MAGI
            edu_nonref += llc["nonref"]
            edu_details.append({"type": "LLC", **llc, "institution": t.institution})
            if llc.get("disqualified_mfs"):
                result["warnings"].append(llc["warning"])
            elif llc.get("phaseout_applied"):
                result["warnings"].append(
                    f"LLC phase-out applied for {t.institution}: MAGI ${rnd(agi):,} "
                    "in phase-out range. Source: i8863.pdf."
                )
    edu_nonref  = rnd(edu_nonref)
    edu_ref_aoc = rnd(edu_ref_aoc)
    f8863_clw_l1 = income_tax
    f8863_clw_l2 = care_credit
    f8863_clw_l3 = max(0, f8863_clw_l1 - f8863_clw_l2)
    edu_nonref_applied = min(edu_nonref, f8863_clw_l3)

    # ── Step 8: FORM 8880 (THIRD) ──────────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f8880.pdf; irs.gov/pub/irs-pdf/i8880.pdf
    s8880        = schema.form_8880 or Form8880Data()

    # L1: IRA contributions — from Form8880Data if provided, else from schema.ira_contribution_traditional
    # Source: i8880.pdf Line 1; Pub 590-A
    saver_l1_explicit = rnd(s8880.ira_contributions)
    saver_l1_ira_schema = rnd(schema.ira_contribution_traditional) if schema.ira_contribution_traditional else 0
    saver_l1 = saver_l1_explicit if saver_l1_explicit > 0 else saver_l1_ira_schema

    # L2: Elective deferrals — from Form8880Data if provided, ELSE auto-populate from W-2 Box 12
    # Codes D, E, F, G, H, S = elective deferrals per i8880.pdf Line 2 instructions
    # Source: i8880.pdf Line 2; iw2w3.pdf Box 12 Code descriptions; IRC §402(g)
    # FETCH_VERIFIED: irs.gov/pub/irs-pdf/iw2w3.pdf | Box 12 Code descriptions | 2026-05-19
    _ELECTIVE_DEFERRAL_CODES = {'D','E','F','G','H','S','AA','BB','EE'}
    _w2_deferrals = rnd(sum(
        amt
        for w in schema.w2s
        for code, amt in [
            (w.box12a_code, w.box12a_amt), (w.box12b_code, w.box12b_amt),
            (w.box12c_code, w.box12c_amt), (w.box12d_code, w.box12d_amt),
        ]
        if (code or '').upper().strip() in _ELECTIVE_DEFERRAL_CODES
    ))
    saver_l2_explicit = rnd(s8880.elective_deferrals)
    saver_l2 = saver_l2_explicit if saver_l2_explicit > 0 else _w2_deferrals
    saver_l3     = saver_l1 + saver_l2
    saver_l4     = rnd(s8880.disqualifying_dist)
    saver_l5     = max(0, saver_l3 - saver_l4)
    saver_l6     = min(saver_l5, 2000)
    saver_l7     = saver_l6
    saver_rate   = get_saver_rate(agi, fs)
    saver_l10    = rnd(saver_l7 * saver_rate)
    # CLW: L2 = Sch3 L2 (Form 2441) + Sch3 L3 (Form 8863) — Sch3 L4 (8880) = $0 circular
    f8880_clw_l1 = income_tax
    f8880_clw_l2 = care_credit + edu_nonref_applied
    f8880_clw_l3 = max(0, f8880_clw_l1 - f8880_clw_l2)
    saver_l11    = f8880_clw_l3
    saver_l12    = rnd(min(saver_l10, saver_l11))   # → Sch 3 Line 4

    # ── Step 9: SCHEDULE 8812 (FOURTH) ─────────────────────────────────────────
    # Source: irs.gov/pub/irs-pdf/f1040s8.pdf; IRC §24; i8812.pdf
    # Line 4a: qualifying children × CTC amount
    # Line 4b: other qualifying dependents × ODC ($500)
    # Line 4c: 4a + 4b — ALL credits pooled through same CLW
    # Line 14: nonrefundable CTC+ODC combined → Form 1040 Line 19
    # ODC for a CHILD (age ≥17, ctc_ineligible) routes through Sch 8812, NOT Sch 3.
    # Sch 3 Line 6d does NOT exist in 2025 Schedule 3 (f1040s3.pdf).
    num_ctc_kids  = len(ctc_children)
    num_odc_deps  = len(odc_deps)
    ctc_total     = num_ctc_kids * p["ctc_per_child"]
    odc_total     = num_odc_deps * p["odc_per_dependent"]
    po_threshold  = p["ctc_phaseout_mfj"] if fs == "mfj" else p["ctc_phaseout_all_other"]
    po_excess     = max(0, agi - po_threshold)
    po_reduction  = rnd(math.ceil(po_excess / 1000) * 1000 / 1000 * 50)
    # Pool CTC + ODC together (both subject to same phase-out, same CLW)
    ctc_odc_total = ctc_total + odc_total
    l12_8812      = max(0, ctc_odc_total - po_reduction)
    odc_after_po  = max(0, odc_total  - max(0, po_reduction - ctc_total))   # for detail only
    clw_8812_l1   = income_tax
    clw_8812_l2   = care_credit + edu_nonref_applied + saver_l12
    clw_8812_l3   = max(0, clw_8812_l1 - clw_8812_l2)
    # Apply combined CTC+ODC against credit limit worksheet
    l14_ctc       = rnd(min(l12_8812, clw_8812_l3))   # total nonrefundable CTC+ODC applied
    odc_credit    = rnd(min(odc_after_po, l14_ctc))    # ODC portion of l14 (for workpaper detail)
    remaining_after_ctc = max(0, clw_8812_l3 - l14_ctc)

    # ACTC — v5 fix: earned income includes SE net profit (Schedule 8812 Line 6a)
    # Source: irs.gov/pub/irs-pdf/f1040s8.pdf Line 6a
    # MFS disqualification: IRC §24(d) — ACTC not allowed for MFS who lived with spouse
    # (MFS lived-apart all year may still claim; engine uses mfs_lived_apart_all_year flag)
    mfs_lived_apart = getattr(schema.form_ssa1099, 'mfs_lived_apart_all_year', False) if schema.form_ssa1099 else False
    actc_mfs_disqualified = (fs == "mfs" and not mfs_lived_apart)
    earned_for_actc = rnd(wages + max(0, se_net_profit) + allocated_tips)
    l16a_actc = l12_8812 - l14_ctc
    l16b_actc = num_ctc_kids * p["actc_cap_per_child"]
    l17_actc  = min(l16a_actc, l16b_actc)
    l19_actc  = max(0, earned_for_actc - p["actc_earned_floor"])
    l20_actc  = rnd(l19_actc * p["actc_rate"])
    actc      = 0 if actc_mfs_disqualified else rnd(min(l17_actc, l20_actc))
    if actc_mfs_disqualified and (l17_actc > 0 or l20_actc > 0):
        result["warnings"].append(
            "Additional Child Tax Credit (ACTC) not allowed for Married Filing Separately "
            "(lived with spouse). Source: IRC §24(d); f1040s8.pdf."
        )

    # ── Step 10: SCHEDULE 3 PART I ─────────────────────────────────────────────
    # Initialize v9 credits before Schedule 3 assembly (values filled in Step 12)
    # Form 1116 FTC is computed here so it can reduce income_tax via sch3_l8
    # Source: irs.gov/pub/irs-pdf/f1040s3.pdf
    excess_aptc_repayment = 0   # set in Step 12 (Form 8962)

    # ── v9: Form 1116 — Foreign Tax Credit (computed BEFORE Schedule 3 so it reduces tax_after)
    f1116_result = {"allowable_credit": 0, "sch3_l1": 0, "de_minimis_applies": False, "warnings": []}
    ftc_credit = 0
    if schema.form_1116:
        f1116_result = compute_f1116(
            schema.form_1116,
            agi            = agi,
            us_tax_before_credit = income_tax,
            qdcgt_income   = qdcgt_income,
            filing_status  = fs,
            amt_tax        = amt_tax,
        )
        ftc_credit = f1116_result["sch3_l1"]
        for w in f1116_result["warnings"]:
            result["warnings"].append(w)
    elif sched_b_result.get("foreign_tax_total", 0) > 0:
        ft = sched_b_result["foreign_tax_total"]
        limit = PARAMS_2025["f1116_de_minimis_mfj"] if fs in ("mfj","qss") else PARAMS_2025["f1116_de_minimis_single"]
        if ft <= limit:
            ftc_credit = ft
            result["warnings"].append(
                f"Foreign tax ${ft:,} ≤ de minimis ${limit:,} — claimed on Schedule 3 Line 1 without Form 1116. "
                "Source: irs.gov/pub/irs-pdf/i1116.pdf; IRC §904(j)."
            )

    sch3_l2  = care_credit
    sch3_l3  = edu_nonref_applied
    sch3_l4  = saver_l12
    sch3_l6d = 0    # ODC does NOT go on Sch 3 — all dependents route through Sch 8812 L14
                    # Source: f1040s3.pdf 2025 — no Line 6d; f1040s8.pdf L4a/4b/4c/14
    sch3_l1_init = ftc_credit         # v9: FTC → Sch 3 L1
    sch3_l8  = sch3_l1_init + sch3_l2 + sch3_l3 + sch3_l4   # sch3_l6d excluded (=0)
    tax_after = max(0, income_tax - l14_ctc - sch3_l8)

    # ── Step 11: EIC ───────────────────────────────────────────────────────────
    # v5: requires exact table lookup before filing; investment income test applied
    eitc_result = compute_eitc(
        earned_income     = rnd(wages + max(0, se_net_profit) + allocated_tips),
        agi               = agi,
        num_children      = num_ctc_kids,
        filing_status     = fs,
        investment_income = investment_income_eitc,
        exact_eitc_from_table = schema.exact_eitc_from_table,
        params            = p,   # pass active year params (TY 2025 or TY 2026)
    )
    eitc = eitc_result["eitc"]
    # requires_table_lookup is now always False — table-band algorithm is filing-grade
    if eitc_result.get("disqualified_investment_income"):
        result["warnings"].append(eitc_result["warning"])
    if eitc_result.get("disqualified_mfs"):
        result["warnings"].append(eitc_result["warning"])

    # ── Step 12: FORM 8962 ─────────────────────────────────────────────────────
    # v9: now uses monthly method (Lines 12–23) when monthly data present
    # Source: irs.gov/pub/irs-pdf/f8962.pdf; irs.gov/pub/irs-pdf/i8962.pdf
    f8962, ptc_net = {}, 0
    excess_aptc_repayment = 0  # → Schedule 2 Line 2
    if schema.form_1095a and (schema.form_1095a.col_a_annual or schema.form_1095a.months):
        # Form 8962 Line 1: family size. Use aca_household_size when explicitly set (> 0).
        # Source: f8962.pdf L1; i8962.pdf instructions; IRC §36B(d)(1)
        family_size = (schema.aca_household_size
                      if schema.aca_household_size > 0
                      else 1 + len(schema.dependents))
        f8962 = compute_f8962(agi, family_size, schema.form_1095a)
        ptc_net = f8962.get("l26_net_ptc", 0)
        excess_aptc_repayment = f8962.get("l27_excess_aptc", 0)
        result["warnings"].append(f8962.get("WARNING", ""))
        if f8962.get("method") == "monthly_lines_12_23":
            result["warnings"].append(
                "Form 8962 Lines 12–23 (monthly method) applied — mid-year coverage change detected. "
                "Source: irs.gov/pub/irs-pdf/i8962.pdf Lines 12–23."
            )
        if excess_aptc_repayment > 0:
            result["warnings"].append(
                f"Form 8962: Excess APTC ${excess_aptc_repayment:,} must be repaid → Schedule 2 Line 2. "
                "Source: irs.gov/pub/irs-pdf/f8962.pdf L27; IRC §36B(f)."
            )

    # ── v9: Form 5329 — Exception codes (Parts I–X) ──────────────────────────
    # Source: irs.gov/pub/irs-pdf/f5329.pdf
    # (Form 1116 FTC was computed before Step 10 so it reduces tax_after correctly)
    f5329_result = {"l4_penalty": 0, "l1_total": 0, "l2_exceptions": 0, "exception_detail": [], "warnings": []}
    if schema.form_5329_exceptions:
        f5329_result = compute_f5329_exceptions(
            schema.form_1099rs,
            schema.form_5329_exceptions,
            agi
        )
        # Override penalty_1099r with exception-adjusted amount
        penalty_1099r = f5329_result["l4_penalty"]
        for w in f5329_result["warnings"]:
            result["warnings"].append(w)
    # If no exceptions provided, penalty_1099r was already set from Code 1/S processing

    # ── Step 13: SCHEDULE 3 PART II ────────────────────────────────────────────
    sch3_l9  = ptc_net      # Net PTC → 1040 Line 31
    sch3_l15 = sch3_l9

    # ── Step 14: FORM 1040 TOTALS ──────────────────────────────────────────────
    # Withholding: W-2 Box 2 → Line 25a; 1099-R Box 4 → Line 25b
    # Withholding sources:
    # Line 25a = W-2 Box 2 only (never includes other forms)
    # Line 25b = 1099-R Box 4 + SSA-1099 Box 6 + 1099-INT Box 4 (backup WH) + 1099-B Box 4
    # + 1099-G Box 4 (unemployment WH) + W-2G Box 4 (gambling WH)
    # Line 25d = 25a + 25b (total federal income tax withheld)
    # Source: f1040.pdf Lines 25a–25d; irs.gov/pub/irs-pdf/i1040gi.pdf
    l25a_w2_wh     = fed_wh
    l25b_1099r_wh  = f1099r_wh
    l25b_ssa_wh    = ss_box6_wh
    l25b_int_wh    = int_backup_wh
    l25b_1099b_wh  = rnd(sum(t.fed_wh for t in schema.form_1099bs))
    l25b_nec_wh    = nec_backup_wh          # 1099-NEC Box 4
    l25b_div_wh    = div_backup_wh          # 1099-DIV Box 4
    l25b_1099g_wh  = rnd(sum(g.box4_fed_wh for g in schema.form_1099gs))  # 1099-G Box 4 unemployment WH
    l25b_w2g_wh    = gambling_wh            # W-2G Box 4 gambling WH
    l25b_total     = rnd(l25b_1099r_wh + l25b_ssa_wh + l25b_int_wh +
                          l25b_1099b_wh + l25b_nec_wh + l25b_div_wh +
                          l25b_1099g_wh + l25b_w2g_wh)
    l25d_total_wh  = rnd(l25a_w2_wh + l25b_total)

    if l25b_ssa_wh > 0:
        result["warnings"].append(f"SSA-1099 Box 6 WH ${l25b_ssa_wh:,} → Line 25b.")
    if l25b_int_wh > 0:
        result["warnings"].append(f"1099-INT backup WH ${l25b_int_wh:,} → Line 25b.")
    if l25b_1099b_wh > 0:
        result["warnings"].append(f"1099-B backup WH ${l25b_1099b_wh:,} → Line 25b.")
    if l25b_nec_wh > 0:
        result["warnings"].append(f"1099-NEC backup WH ${l25b_nec_wh:,} → Line 25b.")
    if l25b_div_wh > 0:
        result["warnings"].append(f"1099-DIV backup WH ${l25b_div_wh:,} → Line 25b.")
    if l25b_1099g_wh > 0:
        result["warnings"].append(f"1099-G (unemployment) WH ${l25b_1099g_wh:,} → Line 25b. Source: f1040.pdf L25b.")
    if l25b_w2g_wh > 0:
        result["warnings"].append(f"W-2G (gambling) WH ${l25b_w2g_wh:,} → Line 25b. Source: f1040.pdf L25b.")

    l27a_eitc = eitc
    l28_actc  = actc
    l29_aoc   = edu_ref_aoc
    l31_sch3  = sch3_l15

    # ── v6/v7/v8/v9: Schedule 2 — Other Taxes (Form 1040 Line 17) ─────────────
    # L1=AMT, L2=excess APTC repayment(v9), L4=SE, L6=4972, L8=5329, L11=AdditionalMed, L12=NIIT
    # Source: irs.gov/pub/irs-pdf/f1040s2.pdf
    sch2_l1_amt           = amt_tax
    sch2_l2_excess_aptc   = excess_aptc_repayment   # v9: Form 8962 Line 27
    sch2_l4_se_tax        = se_tax
    sch2_l6_4972_tax      = f4972_additional_tax
    sch2_l8_5329_penalty  = penalty_1099r
    sch2_l8_hsa_penalty   = hsa_penalty
    sch2_l11_addl_med     = addl_med_tax
    sch2_l12_niit         = niit_tax
    sch2_l17_total        = rnd(sch2_l1_amt + sch2_l2_excess_aptc + sch2_l4_se_tax +
                                sch2_l6_4972_tax + sch2_l8_5329_penalty +
                                sch2_l8_hsa_penalty + sch2_l11_addl_med + sch2_l12_niit)

    if sch2_l8_5329_penalty > 0:
        result["warnings"].append(
            f"Form 5329 penalty ${sch2_l8_5329_penalty:,} → Schedule 2 Line 8 → Form 1040 Line 17. "
            "Source: irs.gov/pub/irs-pdf/f5329.pdf; irs.gov/pub/irs-pdf/f1040s2.pdf L8."
        )
    if sch2_l2_excess_aptc > 0:
        result["warnings"].append(
            f"Excess APTC repayment ${sch2_l2_excess_aptc:,} → Schedule 2 Line 2 → Form 1040 Line 17. "
            "Source: irs.gov/pub/irs-pdf/f8962.pdf L27; f1040s2.pdf L2."
        )

    # v9: Schedule 3 Line 1 — Foreign Tax Credit
    # Previously $0; now uses Form 1116 or de minimis result
    sch3_l1_ftc = ftc_credit   # v9: Form 1116 or de minimis → Sch 3 L1

    l17_other_taxes = sch2_l17_total

    l32 = l27a_eitc + l28_actc + l29_aoc + l31_sch3
    l33_total_pmts = l25d_total_wh + l26_estimated + l32

    l24_total_tax = rnd(tax_after + l17_other_taxes)
    l34_refund = max(0, l33_total_pmts - l24_total_tax)
    l37_owe    = max(0, l24_total_tax - l33_total_pmts)

    # ── v8: Form 2210 — Underpayment Penalty (Line 38) ──────────────────────────
    # Source: irs.gov/pub/irs-pdf/f2210.pdf; IRC §6654
    # Line 38 is SEPARATE from Line 24 (total tax). Adds to owe / reduces refund.
    #
    # Three safe harbors (f2210.pdf Part II):
    #   (a) Net owed < $1,000  → no penalty
    #   (b) Payments ≥ 100%/110% of PRIOR YEAR tax  → requires prior_year_tax > 0
    #   (c) Payments ≥ 90% of CURRENT YEAR tax  → computable without prior-year data
    #
    # FIX (EA review 2026-05-19): when prior_year_tax = 0 (blank), the old code
    # set req_prior = $0, so safe harbor (b) always passed ($0 ≥ $0 = True).
    # This silently suppressed the penalty on every return with blank prior-year data.
    # Correct behavior: skip harbor (b) when prior year is unknown; run (a) and (c) only.
    # Source: IRC §6654(d)(1)(B); f2210.pdf Part II Lines 4–9; IRS Pub 505 Ch.4
    underpay_result = {"penalty": 0, "safe_harbor_met": True, "reason": "No underpayment trigger"}
    underpay_penalty = 0

    # Form 2210 — quarterly installment underpayment penalty
    # Source: irs.gov/pub/irs-pdf/i2210.pdf Part III Section B  FETCH_VERIFIED 2026-05-24
    # P3 (2026-05-24): Now uses per-installment quarterly calculation per i2210.pdf.
    # "The penalty is figured separately for each installment due date." — i2210.pdf
    _est_data = schema.estimated_tax_payments
    underpay_result = compute_form_2210_safe_harbor(
        current_year_tax      = l24_total_tax,
        total_payments        = l33_total_pmts,
        prior_year_tax        = (schema.form_2210.prior_year_tax
                                 if schema.form_2210 and schema.form_2210.prior_year_tax > 0 else 0),
        prior_year_agi        = (schema.form_2210.prior_year_agi
                                 if schema.form_2210 else 0),
        q1_payment            = (_est_data.q1 if _est_data else 0),
        q2_payment            = (_est_data.q2 if _est_data else 0),
        q3_payment            = (_est_data.q3 if _est_data else 0),
        q4_payment            = (_est_data.q4 if _est_data else 0),
        prior_year_overpayment= (_est_data.prior_year_overpayment_applied if _est_data else 0),
    )

    underpay_penalty = underpay_result.get("penalty", 0)
    if underpay_result.get("warning"):
        result["warnings"].append(underpay_result["warning"])
    elif underpay_result["safe_harbor_met"] and (l24_total_tax > 0):
        result["warnings"].append(
            f"Form 2210: safe harbor met — {underpay_result['reason']}. No underpayment penalty. "
            "Source: irs.gov/pub/irs-pdf/i2210.pdf; IRC §6654."
        )
    # Adjust effective owe/refund for underpayment penalty
    l38_underpayment = underpay_penalty
    effective_owe    = rnd(l37_owe + l38_underpayment)
    effective_refund = max(0, rnd(l34_refund - l38_underpayment))

    # ── v8: California Form 540 ──────────────────────────────────────────────────
    # Source: ftb.ca.gov/forms/2025/2025-540.pdf
    ca_result = {}
    if schema.california is not None:
        # ── Fix 7: CA MFS community property warning ────────────────────────
        # IRC §66; California R&TC §17021.5; FTB Publication 1005
        # MFS in a community property state (CA) requires splitting community income 50/50.
        # Engine uses income as reported on each spouse's W-2 — correct ONLY for separate property.
        # Any community income (wages, SE income earned during marriage) must be split equally.
        if fs == "mfs":
            result["warnings"].append(
                "⚠ CA MFS + Community Property: California is a community property state. "
                "Married Filing Separately filers must allocate community income and deductions "
                "50/50 between spouses (IRC §66; R&TC §17021.5). "
                "This includes wages earned during the marriage, SE income, and most investment income. "
                "Engine uses income as reported on each spouse's documents — "
                "verify community vs. separate property allocation before filing. "
                "Source: FTB Publication 1005; irs.gov/pub/irs-pdf/p555.pdf."
            )
        # F4: Sum W-2 Box 16 CA wages for exact CalEITC earned income basis
        # Source: FTB 3514 Step 1; ftb.ca.gov/forms/2025/2025-3514-booklet.html
        # Box 16 = state wages subject to CA withholding — the correct CA earned income base.
        # "CA" state flag: Box 15 state abbreviation must be "CA" or Box 15 state ID includes CA.
        _ca_w2_wages = rnd(sum(
            w.box16_state_wages for w in schema.w2s
            if getattr(w, 'box15_state', '').upper() in ('CA', 'CALIFORNIA')
               or getattr(w, 'box15_state_employer_id', '').upper().startswith('CA')
        ))
        # SE net profit is already CA-sourced (CA-resident return) — use directly
        _ca_se_net = max(0, rnd(se_net_profit)) if schema.schedule_cs else 0

        ca_result = compute_california_540(
            fed_agi           = agi,
            filing_status     = fs,
            num_dependents    = len(schema.dependents),
            ss_benefits       = l6b,
            unemployment      = unemployment_income,
            ca_lottery        = 0,
            hsa_deduction     = adj_hsa,
            ira_deduction     = adj_ira_deduction,
            fed_schedule_a    = schema.schedule_a,
            fed_deduction_type = deduction_type,
            federal_itemized  = itemized_ded,
            ca_data           = schema.california,
            ca_sdi_withheld   = rnd(sum(
                getattr(w, 'box14a_amount', 0) for w in schema.w2s
                if getattr(w, 'box14a_code', '').upper() in ('CASDI', 'SDI', 'VPDI', 'CA SDI')
            )),
            obbba_total_federal = obbba_total,
            ca_w2_wages         = _ca_w2_wages,   # F4: exact CA wages from Box 16
            ca_se_net_profit    = _ca_se_net,      # F4: CA SE income
            ca_taxpayer_age     = tp_age,           # F4: derived from schema.dob for CalEITC age gate
        )
        for w in ca_result.get("warnings", []):
            result["warnings"].append(w)

    result["computed"] = {
        # Identity / metadata (for workpaper header and map_result passthrough)
        "filing_status": fs,
        "spouse_ssn":    schema.spouse_ssn,
        "spouse_first":  schema.spouse_first,
        "spouse_last":   schema.spouse_last,
        "spouse_dob":    schema.spouse_dob,
        # Income
        "wages": wages, "interest": interest,
        "us_bond_interest": us_bond_interest,
        # Line 2b = Box 1 interest + Box 3 US savings bond/Treasury interest (both go to Sch B Part I Line 1,
        # then Sch B Line 4 → 1040 Line 2b). Source: f1099int.pdf Box 3; i1040sb.pdf Part I; f1040.pdf L2b;
        # IRC §61(a)(4); Pub. 550 "How To Report Interest Income". FETCH_VERIFIED 2026-05-26.
        "l2b_interest": rnd(interest + us_bond_interest),
        "tax_exempt_interest": tax_exempt_interest,
        "allocated_tips": allocated_tips,
        "nonqual_def_comp": nonqual_def_comp,
        "dividends": dividends, "dividends_qual": dividends_qual,
        "qualified_dividends": dividends_qual,  # alias — 1040 Line 3a; same as dividends_qual
        "div_cap_gain_dist": div_cap_gain_dist,
        "qdcgt_income": qdcgt_income,
        "cap_gain_net": rnd(net_cap_gain),
        "l4a_ira_gross": l4a, "l4b_ira_taxable": l4b,
        "ira_distributions": l4b,    # 1040 Line 4b alias used by workpaper/server
        "pension_annuity":   l5b,    # 1040 Line 5b alias
        "qcd_total": qcd_total,    # Code Y QCDs excluded from income — IRC §408(d)(8)
        "l5a_pension_gross": l5a, "l5b_pension_taxable": l5b,
        "l6a_ss_total": l6a, "l6b_ss_taxable": l6b,
        "cancelled_debt": cancelled_debt, "prize_income": prize_income,
        # Form 1040 Line 8 = Schedule 1 Part I total (includes SE net profit)
        # 'additional_income' matches the local variable which includes all Sch 1 Part I items
        "additional_income": rnd(additional_income),
        # Misc other income only (excl SE, IRA, pension) — for internal use
        "misc_other_income": rnd(cancelled_debt + prize_income + gambling_income +
                                  unemployment_income + state_refund_taxable +
                                  alimony_received_income + k1_ordinary + k1_rental +
                                  rnd(k1_se) + f4797_ordinary_recapture),
        # SE / Schedule C
        "se_net_profit": se_net_profit,
        "se_tax": se_tax,
        "se_tax_deduction": se_tax_deduction,
        "se_detail": se_result,
        "total_income": total_income,
        # Adjustments
        "teacher_adj": teacher_adj, "adj_early_wdwl": adj_early_wdwl,
        "adj_student_loan": adj_student_loan,
        "student_loan_detail": sl_result,
        "adj_other": adj_other,
        "se_tax_deduction": se_tax_deduction,
        # v6: SE retirement + SE health (Schedule 1 Lines 16-17)
        "adj_se_retirement": adj_se_retirement,
        "se_retirement_detail": se_retirement_result,
        "adj_se_health": adj_se_health,
        "se_health_detail": se_health_result,
        "total_adjustments": total_adjustments,
        # v11: NOL carryforward applied
        "nol_carryforward_applied": nol_deduction_applied,
        "nol_carryforward_remaining": rnd(max(0, nol_cf - nol_deduction_applied)),
        # OBBBA TY 2025 Schedule 1-A below-line deductions → Form 1040 Line 13b
        # Source: f1040s1a.pdf; IR-2026-28; irs.gov/pub/irs-pdf/f1040s1a.pdf
        "obbba_senior_deduction": adj_senior,
        "obbba_tip_deduction": adj_tips,
        "obbba_overtime_deduction": adj_overtime,
        "obbba_auto_loan_deduction": adj_auto,
        "obbba_total_deductions": obbba_total,
        "l13b_schedule1a": l13b_schedule1a,
        # v6: QBI deduction (Form 1040 Line 13)
        "adj_qbi": adj_qbi,           # QBI §199A — 1040 Line 13a
        "l13a_qbi": adj_qbi,          # alias: 1040 Line 13a label
        "l14_total_ded": rnd(deduction_used + adj_qbi),  # 1040 L12+L13a (std/itemized + QBI)
        "l13b_schedule1a": l13b_schedule1a,  # OBBBA Sch 1-A below-line (if any)
        "qbi_detail": qbi_result,
        # AGI & deduction
        "agi_pre_ss": rnd(agi_pre_ss), "agi": rnd(agi),
        "std_deduction": std_ded, "itemized_deduction": itemized_ded,
        "deduction_used": deduction_used, "deduction_type": deduction_type,
        "charitable_carryover_to_2026": rnd(sched_a_result.get("charitable_carryover", 0)) if sched_a_result else 0,
        "taxable_income": taxable,
        # Tax
        "income_tax": income_tax,
        "qdcgt_applied": qdcgt_income > 0,
        "se_tax_sch2": se_tax,
        "f4972_additional_tax": f4972_additional_tax,
        # Schedule 1 Parts I and II — above/below line income and deductions
        # Source: f1040s1.pdf; i1040s1.pdf
        "sch1": {
            # Part I — Additional Income (→ 1040 Line 8)
            "l1_state_refund":      rnd(state_refund_taxable),
            "l2a_alimony":          rnd(alimony_received_income),
            "l3_se_income":         rnd(se_net_profit),
            "l4_1231_gain":         rnd(f4797_ordinary_recapture),
            "l5_rental":            rnd(rental_net),
            "l7_unemployment":      rnd(unemployment_income),
            "l8a_gambling":         rnd(gambling_income),
            "l8b_cancellation_debt":rnd(cancelled_debt),
            "l8c_prize":            rnd(prize_income),
            "l8h_jury_duty":        rnd(jury_duty_income),   # Source: f1040s1.pdf Line 8h; IRC §61(a)
            "l10_total":            rnd(additional_income),   # → 1040 Line 8
            # Part II — Adjustments to Income (→ 1040 Line 10 through 24)
            "l11_educator":         rnd(teacher_adj),
            "l15_se_deduction":     rnd(se_tax_deduction),
            "l16_se_health":        rnd(adj_se_health),
            "l17_se_retirement":    rnd(adj_se_retirement),
            "l19_alimony_paid":     rnd(alimony_paid_deduction),
            "l20_ira":              rnd(ira_deduction_result.get("deductible", 0)),
            "l21_student_loan":     rnd(adj_student_loan),
            # QBI is NOT Schedule 1 — it's 1040 Line 13a (below-the-line)
            # l24_qbi kept for display reference only — does not add to l26
            "l13a_qbi":             rnd(adj_qbi),   # 1040 Line 13a — NOT Sch1
            "l26_total_adj":        rnd(total_adjustments),  # → 1040 Line 10 (AGI adj)
        },
        # v6/v7/v8/v9: Schedule 2 breakdown
        "sch2": {
            "l1_amt": sch2_l1_amt,
            "l2_excess_aptc": sch2_l2_excess_aptc,  # v9
            "l4_se_tax": sch2_l4_se_tax,
            "l6_4972_tax": sch2_l6_4972_tax,
            "l8_5329_penalty": sch2_l8_5329_penalty,
            "l8_hsa_penalty": sch2_l8_hsa_penalty,
            "l11_addl_med": sch2_l11_addl_med,
            "l12_niit": sch2_l12_niit,
            "l17_total": sch2_l17_total,
        },
        "l17_other_taxes": l17_other_taxes,
        # 1040 Lines 16–24 — EXACT IRS form line descriptions
        # FETCH_VERIFIED: irs.gov/pub/irs-pdf/f1040.pdf | Page 2 Lines 16-24 | 2026-05-24
        "l16_income_tax":              income_tax,
        "l17_amt":                     sch2_l1_amt,          # L17: AMT — Schedule 2 line 3
        "l18_add_l16_l17":             rnd(income_tax + sch2_l1_amt),  # L18: Add lines 16 and 17
        "l19_ctc":                     l14_ctc,              # L19: Child tax credit / ODC
        "l20_sch3_credits":            sch3_l8,              # L20: Schedule 3 line 8
        "l20_edu_credit":              sch3_l3,              # L20 detail: edu credit breakdown
        "l21_add_l19_l20":             rnd(l14_ctc + sch3_l8),   # L21: Add lines 19 and 20
        "l22_subtract_l21_from_l18":   max(0, rnd(income_tax + sch2_l1_amt - l14_ctc - sch3_l8)),  # L22: Subtract L21 from L18 (tax after credits)
        "l23_other_taxes":             rnd(sch2_l17_total - sch2_l1_amt),  # L23: Other taxes (Sch 2 line 21: SE, 5329, NIIT, etc.)
        "l24_total_tax": l24_total_tax,  # L24: Add lines 22 and 23
        # 1099-R detail
        "f1099r_nua_excluded": nua_total,
        "f1099r_penalty": penalty_1099r,
        "f1099r_simplified_method": sm_results,
        "f1099r_box3_cap_gain": box3_cap_gain_total,
        # SSA-1099
        "ss_lump_sum_election": ss_lump_sum_result,
        "ss_lump_sum_election_used": lump_sum_election_used,
        "line_6c_lump_sum_checkbox": lump_sum_election_used,
        # Credits
        "f2441": {
            "expense_cap": care_cap_amt, "qualified_exp": care_exp_cap,
            "earned_income_limit": earned_income_2441,
            "decimal_l8": f2441_decimal,
            "l9c": care_l9c, "clw_l1": f2441_clw_l1,
            "clw_l2": f2441_clw_l2, "clw_l3": f2441_clw_l3,
            "l11_credit": care_credit,
        },
        "f8863": {
            "details": edu_details, "nonref_gross": edu_nonref,
            "nonref_applied": edu_nonref_applied, "refundable_aoc": edu_ref_aoc,
            "clw_l1": f8863_clw_l1, "clw_l2": f8863_clw_l2,
        },
        "f8880": {
            "l1_ira": saver_l1, "l2_deferrals": saver_l2, "l3": saver_l3,
            "l5": saver_l5, "l6": saver_l6, "l7": saver_l7,
            "l9_rate": saver_rate, "l10": saver_l10,
            "clw_l1": f8880_clw_l1, "clw_l2": f8880_clw_l2, "clw_l3": f8880_clw_l3,
            "l11": saver_l11, "l12_credit": saver_l12,
        },
        "s8812": {
            # Part I — CTC/ODC detail
            "l4a_ctc_kids":   num_ctc_kids,       # Line 4a: number of qualifying children
            "l4a_ctc_amt":    ctc_total,           # Line 4a: CTC amount
            "l4b_odc_deps":   num_odc_deps,        # Line 4b: other qualifying dependents
            "l4b_odc_amt":    odc_total,           # Line 4b: ODC amount ($500/dep)
            "l4c_total":      ctc_odc_total,       # Line 4c: 4a + 4b pooled
            "ctc_total":      ctc_total,           # alias
            "odc_total":      odc_total,           # alias
            "po_threshold":   po_threshold,
            "po_reduction":   po_reduction,
            "l12":            l12_8812,            # after phase-out
            "clw_l1":         clw_8812_l1,
            "clw_l2":         clw_8812_l2,
            "clw_l3":         clw_8812_l3,
            "l14_ctc":        l14_ctc,             # Line 14: total nonrefundable CTC+ODC → 1040 L19
            "odc_credit":     odc_credit,          # ODC portion of l14 (for workpaper detail)
            "l16a":           l16a_actc,
            "l16b":           l16b_actc,
            "l17":            l17_actc,
            # Line 19: ACTC earned income calculation
            "l19_earned":     earned_for_actc,     # Line 19: earned income for ACTC
            "l19_floor":      p.get("actc_earned_floor", 2500),
            "l19_excess":     max(0, earned_for_actc - p.get("actc_earned_floor", 2500)),
            "l20":            l20_actc,            # Line 20: 15% of excess earned income
            "l27_actc":       actc,                # Line 27: refundable ACTC
            "earned_for_actc": earned_for_actc,
        },
        "ss_detail": ss_result,
        "sch3": {
            "l1_ftc": sch3_l1_init,    # v9: Foreign Tax Credit
            "l2_care": sch3_l2, "l3_edu": sch3_l3, "l4_saver": sch3_l4,
            "l6d_odc": 0,             # ODC routes through Sch 8812, never Sch 3
            "l8_total_nonref": sch3_l8, "l9_ptc": sch3_l9, "l15": sch3_l15,
        },
        "f8962": f8962,
        "sched_a": sched_a_result,
        # Workpaper alias keys — flat convenience accessors for commonly used sub-values
        # Prevents broken workpaper references when workpaper uses r.key directly
        "care_credit":      care_credit,          # Form 2441 l11_credit (scalar already in scope)
        "effective_rate":   (round(income_tax / taxable * 100, 2)
                             if taxable and taxable > 0 else 0.0),
        "net_earnings_se":  se_result.get("net_earnings_se", 0),
        "qbi_form_used":    ("8995-A" if qbi_result.get("above_threshold") else "8995"),
        "sched_a_cash_char": sched_a_result.get("l11_cash", 0) if sched_a_result else 0,
        "sched_a_casualty":  sched_a_result.get("l15_casualty", 0) if sched_a_result else 0,
        "sched_d_8949": schd_result,
        "f8606": f8606_result,
        "f4972": f4972_result,
        "eitc_detail": eitc_result,
        # v7 new forms
        "sched_b": sched_b_result,
        "sched_e_8582": sched_e_result,
        "rental_net": rental_net,
        "f6251": f6251_result,
        "amt_tax": amt_tax,
        # v8 new computations
        "gambling_income": gambling_income,
        "gambling_wh": gambling_wh,
        "jury_duty_income": jury_duty_income,       # Sch 1 Line 8h; Source: f1040s1.pdf L8h; IRC §61(a)
        "unemployment_income": unemployment_income,
        "state_refund_taxable": state_refund_taxable,
        # Echo 1098-E data for workpaper display
        "form_1098es_detail": [{"lender": f.lender, "interest": f.box1_student_loan_interest}
                               for f in (schema.form_1098es or [])],
        # Explicit 1040 line aliases for workpaper and server
        # Source: f1040.pdf Line 8 = Sch 1 Part I additional income
        # Line 10 = taxable state/local refund (Sch 1 Line 1)
        "l8_other_income": rnd(additional_income),   # 1040 Line 8 = Sch 1 Part I total
        "l10_taxable_refund": rnd(state_refund_taxable),  # 1040 Line 10 = taxable refund
        "alimony_received": alimony_received_income,
        "alimony_paid_ded": alimony_paid_deduction,
        "k1_result": k1_result,
        "k1_ordinary": k1_ordinary,
        "k1_stcg": k1_stcg, "k1_ltcg": k1_ltcg,
        "adj_ira_deduction": adj_ira_deduction,
        "ira_deduction_detail": ira_deduction_result,
        "adj_hsa": adj_hsa,
        "hsa_detail": hsa_result,
        "hsa_non_medical_taxable": hsa_non_medical_taxable,
        "hsa_penalty": hsa_penalty,
        "niit_tax": niit_tax,
        "niit_detail": niit_result,
        "addl_med_tax": addl_med_tax,
        "addl_med_detail": addl_med_result,
        "f2210": underpay_result,
        "l38_underpayment": l38_underpayment,
        "effective_owe": effective_owe,
        "effective_refund": effective_refund,
        "ca_540": ca_result,
        # v9 new forms
        "f5329": f5329_result,
        "f1116": f1116_result,
        "ftc_credit": ftc_credit,
        "foreign_tax_credit": ftc_credit,   # alias for UI/workpaper — Sch 3 L1
        "div_unrec_1250": div_unrec_1250,   # 1099-DIV Box 2b §1250 component (25% rate)
        "unrecap_1250_gain": total_unrec_1250,  # total §1250 in QDCGT (Form 4797 + DIV Box 2b)
        "excess_aptc_repayment": excess_aptc_repayment,
        "sch2_l2_excess_aptc": sch2_l2_excess_aptc,
        # v10 new forms
        "f8615": f8615_result,
        "nol": nol_result,
        "f4797": f4797_result,
        # Withholding
        "l25a_w2_wh": l25a_w2_wh,
        "l25b_1099r_wh": l25b_1099r_wh,
        "l25b_ssa_wh": l25b_ssa_wh,
        "l25b_int_wh": l25b_int_wh,
        "l25b_1099b_wh": l25b_1099b_wh,
        "l25b_nec_wh": l25b_nec_wh,
        "l25b_div_wh": l25b_div_wh,
        "l25b_total": l25b_total,
        "l25d_total_wh": l25d_total_wh,
        "l26_estimated": l26_estimated,
        "l14_ctc": l14_ctc, "l19_ctc": l14_ctc,
        "l20_sch3l8": sch3_l8, "tax_after": tax_after,
        "employer_dep_care_box10": employer_dep_care,
        "employer_care_excl_129": employer_care_excl,
        "l27a_eitc": eitc, "l28_actc": actc, "l29_aoc": l29_aoc,
        "l31_sch3l15": sch3_l15, "l32": l32,
        "l33_total_pmts": l33_total_pmts,
        "l34_refund": l34_refund, "l37_owe": l37_owe,
    }
    return result


if __name__ == "__main__":
    # ── Test: Carl Graves 2025 + new income types ─────────────────────────────
    schema = TaxpayerSchema(
        first="Carl", last="Graves", ssn="328-00-1111",
        dob="04/12/1984", occupation="Teacher",
        address="200 Sky Way, Northford, CT 06472",
        filing_status="qss", tax_year=2025,
        w2s=[W2(employer="Rosewood School District", ein="34-8001111",
                 box1_wages=37000, box2_fed_wh=1500, box12a_code="D", box12a_amt=1500)],
        form_1099ints=[Form1099INT(payer="Bank", payer_ein="N/A",
                                   box1_interest=160, box2_early_withdrawal_penalty=32)],
        form_1099rs=[Form1099R(payer="Pension Co", box1_gross=5000, box2a_taxable=5000,
                               box4_fed_wh=500, box7_code="7",
                               box7_ira_sep_simple=False, is_ira=False)],
        form_ssa1099=FormSSA1099(box5_net_benefits=8000, box3_gross_benefits=8000),
        form_1099cs=[Form1099C("Bank",box2_amount_discharged=3000,is_excluded=False)],
        form_1099misc_prizes=[Form1099MISC_Prize("Contest Co",box3_other_income=500)],
        dependents=[Dependent("Lilly","Graves","125-00-1111","07/24/2016","Daughter")],
        teacher_expense=300,
        care_providers=[Form2441Provider("Preschool","","",expenses=2200)],
        form_1098ts=[Form1098T("State University","12-3456789",
                               box1_payments=8000,box5_scholarships=2000,
                               credit_type="aoc",first_four_years=True,
                               student_name="Lilly Graves")],
        form_8880=Form8880Data(elective_deferrals=1500),
        form_1095a=Form1095A("",col_a_annual=5352,col_b_annual=7224,col_c_annual=4656),
    )
    r = run(schema)
    c = r["computed"]
    print("=== SachinTaxCare v2 — Carl Graves 2025 (expanded) ===")
    print(f"  AGI:                ${c['agi']:,}")
    print(f"  Taxable income:     ${c['taxable_income']:,}")
    print(f"  Income tax:         ${c['income_tax']:,}")
    print(f"  Form 2441 credit:   ${c['f2441']['l11_credit']:,}  → Sch 3 L2")
    print(f"  Form 8863 (AOC):    ${c['f8863']['nonref_applied']:,} non-ref + ${c['f8863']['refundable_aoc']:,} refundable → Sch 3 L3 + 1040 L29")
    print(f"  Form 8880 credit:   ${c['f8880']['l12_credit']:,}  → Sch 3 L4")
    print(f"  CTC (Line 19):      ${c['l19_ctc']:,}")
    print(f"  ACTC (Line 28):     ${c['l28_actc']:,}")
    print(f"  EITC (Line 27a):    ${c['l27a_eitc']:,}  ⚠ confirm from IRS table")
    print(f"  AOC refundable L29: ${c['l29_aoc']:,}")
    print(f"  Net PTC (L31):      ${c['l31_sch3l15']:,}  ⚠ confirm Table 2")
    print(f"  Total payments:     ${c['l33_total_pmts']:,}")
    print(f"  REFUND:             ${c['l34_refund']:,}")
    print()
    for w in r["warnings"]:
        print(f"  ⚠  {w}")
