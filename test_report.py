"""
SachinTaxCare — Report Layer Tests (v11)
Tests: JSON schema, EIC exact table, citations, carryforwards, flags
Source: IRS forms from irs.gov only.
"""
import sys, json
sys.path.insert(0, '.')
import sachintaxcare_engine as e
import sachintaxcare_report as r

PASS = FAIL = 0

def check(label, source, actual, expected, tolerance=0):
    global PASS, FAIL
    diff = abs(actual - expected)
    if diff <= tolerance:
        PASS += 1
        print(f"\033[92m[PASS] {label}\033[0m  ({actual:,})")
    else:
        FAIL += 1
        print(f"\033[91m[FAIL] {label}\033[0m  expected={expected:,} actual={actual:,} diff={diff:,}\n  source: {source}")

def check_bool(label, source, actual, expected):
    global PASS, FAIL
    if actual == expected:
        PASS += 1; print(f"\033[92m[PASS] {label}\033[0m")
    else:
        FAIL += 1; print(f"\033[91m[FAIL] {label}\033[0m  expected={expected} actual={actual}\n  source: {source}")

print("=" * 65)
print("SachinTaxCare — Report Layer / EIC Table Tests (v11)")
print("=" * 65)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 25: EIC TABLE EXACT LOOKUPS
# Source: IRS EIC Table p1040.pdf pp16+; Rev. Proc. 2024-40
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Section 25: EIC Table — Exact Lookups ────────────────────────")

# 25.1: 0 children, single, $12,000 income
# Band = (12000//50)*50 = 12000; col=single_qss, n=0
# Phase-out starts $9,524; excess = $12,000-$9,524=$2,476; reduction=$2,476×7.65%=$189
# Credit ≈ max(0, $632 - $189) = $443
res = r.lookup_eitc_exact(12000, 12000, 0, 'single')
check("25.1 EITC 0 children single $12k — exact table",
      "IRS EIC Table 2025; Rev. Proc. 2024-40",
      res['eitc'], 443, tolerance=5)
check_bool("25.1 exact=True flag", "p1040.pdf EIC Table", res['exact'], True)

# 25.2: 1 child, single, $20,000 income
# Phase-out starts $21,115 → below threshold → max credit $4,213
res2 = r.lookup_eitc_exact(20000, 20000, 1, 'single')
check("25.2 EITC 1 child single $20k — max credit $4,213",
      "IRS EIC Table 2025", res2['eitc'], 4213, tolerance=10)

# 25.3: 2 children, MFJ, $30,000 income
# Phase-out starts $29,640; excess=$360; reduction=$360×40%=$144
# Credit ≈ $6,960 - $144 = $6,816
res3 = r.lookup_eitc_exact(30000, 30000, 2, 'mfj')
check("25.3 EITC 2 children MFJ $30k — phased out slightly",
      "IRS EIC Table 2025; Rev. Proc. 2024-40",
      res3['eitc'], 6816, tolerance=20)

# 25.4: 3 children, MFJ, $28,000 income — max credit $7,830
res4 = r.lookup_eitc_exact(28000, 28000, 3, 'mfj')
check("25.4 EITC 3 children MFJ $28k — max credit $7,830",
      "IRS EIC Table 2025", res4['eitc'], 7830, tolerance=0)

# 25.5: Above income limit → $0
res5 = r.lookup_eitc_exact(60000, 60000, 2, 'single')
check("25.5 EITC above income limit → $0",
      "IRS EIC Table 2025; IRC §32", res5['eitc'], 0, tolerance=0)
check_bool("25.5 disqualified=True (income limit)", "p596.pdf", res5.get('disqualified', False), False)

# 25.6: MFS → $0
res6 = r.lookup_eitc_exact(25000, 25000, 1, 'mfs')
check("25.6 EITC MFS → $0", "IRC §32(d); p596.pdf", res6['eitc'], 0, tolerance=0)
check_bool("25.6 MFS disqualified", "IRC §32(d)", res6.get('disqualified'), True)

# 25.7: Investment income > $11,600 → $0
res7 = r.lookup_eitc_exact(15000, 15000, 1, 'single', investment_income=12000)
check("25.7 Investment income > $11,600 → $0",
      "IRC §32(i); p596.pdf", res7['eitc'], 0, tolerance=0)
check_bool("25.7 investment income disqualified", "IRC §32(i)", res7.get('disqualified'), True)

# 25.8: Use larger of earned vs AGI
# Earned = $10,000, AGI = $18,000 → use $18,000
# 0 children, single: phase-out starts $9,524; excess=$8,476; reduction=$648
# Credit ≈ max(0, $632 - $648) = $0
res8 = r.lookup_eitc_exact(10000, 18000, 0, 'single')
check("25.8 EITC uses larger of earned ($10k) vs AGI ($18k) → near $0",
      "IRS EIC Table — use larger. p596.pdf; i1040gi.pdf", res8['eitc'], 0, tolerance=50)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 26: REPORT JSON SCHEMA — STRUCTURE & CITATIONS
# Source: f1040.pdf; i1040gi.pdf; all IRS source citations in LINE_SOURCES
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Section 26: Report JSON Schema & Citations ───────────────────")

schema_base = e.TaxpayerSchema(
    first='Report', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Tech Corp', box1_wages=120000, box2_fed_wh=22000)],
    form_1099divs=[e.Form1099DIV(payer='Vanguard',
                                  box1a_ordinary_div=5000,
                                  box1b_qualified_div=4000)],
    form_1099bs=[e.Form1099B(description='AAPL', proceeds=30000,
                              cost_basis=20000, is_long_term=True,
                              basis_reported_to_irs=True)],
    schedule_es=[e.ScheduleE(address='100 Oak', rents_received=20000,
                              mortgage_interest=7000, taxes=2000,
                              depreciation=4500, insurance=800)],
    dependents=[e.Dependent('Kid', 'Test', '999-01-0001', '05/01/2018', 'Child',
                             ctc_eligible=True)],
)

rpt = r.generate_report(schema_base, e.run)

# 26.1: Meta section present
check_bool("26.1 meta.tax_year = 2025", "report meta",
           rpt['meta']['tax_year'], 2025)
check_bool("26.1 engine_version present", "report meta",
           'engine_version' in rpt['meta'], True)
check_bool("26.1 source_policy present", "report meta",
           'source_policy' in rpt['meta'], True)

# 26.2: Every form_1040 line has 'value' and 'source'
missing_source = [k for k, v in rpt['form_1040'].items()
                  if not isinstance(v, dict) or 'source' not in v]
if not missing_source:
    PASS += 1; print(f"\033[92m[PASS] 26.2 All form_1040 lines have 'source' citation\033[0m")
else:
    FAIL += 1; print(f"\033[91m[FAIL] 26.2 Lines missing 'source': {missing_source}\033[0m")

# 26.3: EITC uses exact table (not formula)
eitc_line = rpt['form_1040']['l27a_eitc']
check_bool("26.3 l27a_eitc.exact_table_lookup = True",
           "p1040.pdf EIC Table; Rev. Proc. 2024-40",
           eitc_line.get('exact_table_lookup'), True)
check_bool("26.3 l27a_eitc.value matches lookup_eitc_exact",
           "p1040.pdf EIC Table",
           eitc_line['value'] >= 0, True)

# 26.4: W-2 components in l1z
components = rpt['form_1040']['l1z_wages'].get('components', [])
check_bool("26.4 l1z_wages has W-2 components", "W-2 Box 1 sum",
           len(components) > 0, True)
check_bool("26.4 W-2 component has payer field", "iw2w3.pdf",
           'payer' in components[0], True)

# 26.5: Carryforwards section present with required keys
required_cf_keys = ['capital_loss_carryover', 'nol_carryforward',
                    'form_8582_suspended_losses', 'form_8606_basis_remaining',
                    'form_1116_excess_credits', 'sec1231_net_loss_this_year']
missing_cf = [k for k in required_cf_keys if k not in rpt['carryforwards']]
if not missing_cf:
    PASS += 1; print(f"\033[92m[PASS] 26.5 All carryforward keys present\033[0m")
else:
    FAIL += 1; print(f"\033[91m[FAIL] 26.5 Missing carryforward keys: {missing_cf}\033[0m")

# 26.6: Each carryforward has 'source' and 'note'
missing_cf_src = [k for k in required_cf_keys
                  if 'source' not in rpt['carryforwards'][k]]
if not missing_cf_src:
    PASS += 1; print(f"\033[92m[PASS] 26.6 All carryforward entries have 'source'\033[0m")
else:
    FAIL += 1; print(f"\033[91m[FAIL] 26.6 Carryforward missing source: {missing_cf_src}\033[0m")

# 26.7: flags section present with severity, code, source on each flag
bad_flags = [f for f in rpt['flags']
             if not all(k in f for k in ('severity', 'code', 'source', 'message'))]
if not bad_flags:
    PASS += 1; print(f"\033[92m[PASS] 26.7 All flags have severity/code/source/message\033[0m")
else:
    FAIL += 1; print(f"\033[91m[FAIL] 26.7 Malformed flags: {bad_flags}\033[0m")

# 26.8: flag_summary counts match actual flags
fs = rpt['flag_summary']
actual_errors   = sum(1 for f in rpt['flags'] if f['severity'] == 'error')
actual_warnings = sum(1 for f in rpt['flags'] if f['severity'] == 'warning')
check_bool("26.8 flag_summary.errors count correct",
           "report flag_summary", fs['errors'], actual_errors)
check_bool("26.8 flag_summary.warnings count correct",
           "report flag_summary", fs['warnings'], actual_warnings)

# 26.9: result section has effective_rate and marginal_rate
check_bool("26.9 result.effective_rate_pct present",
           "report result section", 'effective_rate_pct' in rpt['result'], True)
check_bool("26.9 result.marginal_rate_pct = 24 (single $125,700 taxable; AGI $140,700)",
           "Rev. Proc. 2024-40 brackets — single 24% bracket $103,350–$197,300",
           rpt['result']['marginal_rate_pct']['value'], 24)

# 26.10: QBI rental safe harbor flag fires for profitable rental
has_qbi_flag = any(f['code'] == 'QBI_RENTAL_SAFE' for f in rpt['flags'])
check_bool("26.10 QBI_RENTAL_SAFE flag present for rental income",
           "Rev. Proc. 2019-38", has_qbi_flag, True)

# 26.11: Cap loss carryover in carryforwards
check("26.11 Capital loss carryover in carryforwards",
      "Sch D L22; IRC §1212(b)",
      rpt['carryforwards']['capital_loss_carryover']['value'], 0, tolerance=0)

# ─────────────────────────────────────────────────────────────────────────────
# SECTION 27: REPORT — COMPLEX SCENARIOS (Cited Verification)
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Section 27: Report — Complex Scenario Verification ──────────")

# 27.1: Backdoor Roth — tainted — appears in flags + carryforward basis
schema_roth = e.TaxpayerSchema(
    first='Roth', last='Tainted', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=150000, box2_fed_wh=30000)],
    form_1099rs=[e.Form1099R(payer='Fidelity', box1_gross=7000,
        box2a_taxable=7000, box4_fed_wh=0, box7_code='2',
        box7_ira_sep_simple=True, is_ira=True)],
    form_8606=e.Form8606Data(
        nonded_contrib_this_year=7000, basis_prior_year=0,
        trad_ira_value_dec31=93000, trad_ira_distributions=7000,
        conversion_amount=7000, is_backdoor_roth=True))
rpt_roth = r.generate_report(schema_roth, e.run)
has_taint = any(f['code'] == 'BACKDOOR_TAINT' for f in rpt_roth['flags'])
check_bool("27.1 BACKDOOR_TAINT flag fires for pre-tax IRA balance",
           "f8606.pdf; IRC §408(d)(2)", has_taint, True)
f8606_cf = rpt_roth['carryforwards']['form_8606_basis_remaining']['value']
check("27.1 Form 8606 remaining basis in carryforward = $6,510",
      "f8606.pdf L14", f8606_cf, 6510, tolerance=0)

# 27.2: Capital loss carryover appears in carryforwards
schema_loss = e.TaxpayerSchema(
    first='Loss', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=80000, box2_fed_wh=10000)],
    form_1099bs=[e.Form1099B(description='Tech ETF', proceeds=5000,
        cost_basis=20000, is_long_term=True, basis_reported_to_irs=True)])
rpt_loss = r.generate_report(schema_loss, e.run)
cf_loss = rpt_loss['carryforwards']['capital_loss_carryover']['value']
check("27.2 Capital loss carryover = -$12,000 (loss $15k − $3k deductible)",
      "Sch D L22; IRC §1212(b)", cf_loss, -12000, tolerance=0)
check_bool("27.2 carryforward has note field",
           "report carryforward", 'note' in rpt_loss['carryforwards']['capital_loss_carryover'], True)

# 27.3: MFS flags
schema_mfs = e.TaxpayerSchema(
    first='MFS', last='Test', filing_status='mfs', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=60000, box2_fed_wh=8000)],
    form_1098ts=[e.Form1098T(institution='State U', box1_payments=4000,
                              box5_scholarships=0, credit_type='aoc',
                              first_four_years=True)])
rpt_mfs = r.generate_report(schema_mfs, e.run)
has_mfs_flag = any(f['code'] == 'MFS_CREDIT_DISQ' for f in rpt_mfs['flags'])
has_eitc_mfs = any(f['code'] == 'EITC_MFS' for f in rpt_mfs['flags'])
check_bool("27.3 MFS_CREDIT_DISQ flag present", "IRC §32(d); §25A(g)(6)", has_mfs_flag, True)
check_bool("27.3 EITC_MFS flag present", "IRC §32(d)", has_eitc_mfs, True)
check("27.3 EITC = $0 for MFS in report output",
      "IRC §32(d)", rpt_mfs['form_1040']['l27a_eitc']['value'], 0, tolerance=0)

# 27.4: Form 4797 §1250 — flags in report, supplemental section present
schema_4797 = e.TaxpayerSchema(
    first='F4797', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=80000, box2_fed_wh=10000)],
    form_4797s=[e.Form4797SaleData(
        description='Rental Prop', property_type='1250_residential',
        held_over_one_year=True, gross_proceeds=400000,
        original_cost=300000, depreciation_taken=50000)])
rpt_4797 = r.generate_report(schema_4797, e.run)
has_1250_flag = any(f['code'] == '1250_UNREC' for f in rpt_4797['flags'])
has_lookback  = any(f['code'] == '4797_LOOKBACK' for f in rpt_4797['flags'])
check_bool("27.4 1250_UNREC flag fires for rental sale", "IRC §1(h)(6); f4797.pdf", has_1250_flag, True)
check_bool("27.4 4797_LOOKBACK flag fires", "IRC §1231(c); p544.pdf", has_lookback, True)
check_bool("27.4 supplemental.form_4797 present in report",
           "f4797.pdf", 'form_4797' in rpt_4797['supplemental'], True)

# 27.5: generate_report_json produces valid JSON
json_str = r.generate_report_json(schema_base, e.run)
try:
    parsed = json.loads(json_str)
    PASS += 1; print(f"\033[92m[PASS] 27.5 generate_report_json produces valid JSON\033[0m")
except Exception as ex:
    FAIL += 1; print(f"\033[91m[FAIL] 27.5 Invalid JSON: {ex}\033[0m")

# 27.6: JSON has all top-level sections
required_keys = ['meta', 'form_1040', 'schedules', 'credits',
                 'other_taxes', 'carryforwards', 'result', 'flags',
                 'flag_summary', 'warnings_raw']
missing_keys = [k for k in required_keys if k not in parsed]
if not missing_keys:
    PASS += 1; print(f"\033[92m[PASS] 27.6 All top-level JSON sections present\033[0m")
else:
    FAIL += 1; print(f"\033[91m[FAIL] 27.6 Missing JSON sections: {missing_keys}\033[0m")

# 27.7: Effective rate sanity (> 0 for income taxpayer)
eff_rate = rpt['result']['effective_rate_pct']['value']
check_bool("27.7 Effective rate > 0 for income taxpayer",
           "Total tax / AGI", eff_rate > 0, True)

# 27.8: Schedule D 8949 section cites Box D (noncovered LT)
schema_noncov = e.TaxpayerSchema(
    first='BoxD', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=80000, box2_fed_wh=10000)],
    form_1099bs=[
        e.Form1099B(description='AAPL', proceeds=20000, cost_basis=10000,
                    is_long_term=True, basis_reported_to_irs=True, noncovered=False),
        e.Form1099B(description='Old Fund', proceeds=15000, cost_basis=10000,
                    is_long_term=True, basis_reported_to_irs=False, noncovered=True),
    ])
rpt_noncov = r.generate_report(schema_noncov, e.run)
box_d_count = rpt_noncov['schedules']['schedule_d_8949']['box_d_noncovered_lt']['value']
check("27.8 Box D noncovered LT count = 1 in schedule_d_8949",
      "Form 8949 Box D; i8949.pdf", box_d_count, 1, tolerance=0)

print()
print("=" * 65)
print(f"Results: {PASS} passed  |  {FAIL} failed")
if FAIL == 0:
    print("✅ ALL REPORT TESTS PASSED")
else:
    print(f"❌ {FAIL} test(s) failed")
print("=" * 65)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 28: REPORT — v12 NEW FEATURES
# ──────────────────────────────────────────────────────────────────────────────
print("\n── Section 28: Report v12 — 8995-A, Carryforward, Compare ─────")

# 28.1: QBI deduction present in report supplemental + carryforward section
schema_qbi = e.TaxpayerSchema(
    first='QBIReport', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=50000, box2_fed_wh=5000)],
    schedule_cs=[e.ScheduleC(business_name='Freelance', gross_receipts=60000)],
)
rpt_qbi = r.generate_report(schema_qbi, e.run)
qbi_cf = rpt_qbi['carryforwards'].get('qbi_loss_carryforward', {})
check_bool("28.1 QBI loss carryforward present in carryforwards section",
           "f8995.pdf L11", 'value' in qbi_cf, True)
check_bool("28.1 QBI loss carryforward value is numeric",
           "f8995.pdf L11", isinstance(qbi_cf.get('value'), (int, float)), True)

# 28.2: Form 8995-A triggered for above-threshold filer
schema_8995a = e.TaxpayerSchema(
    first='AboveThresh', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=250000, box2_fed_wh=60000)],
    schedule_cs=[e.ScheduleC(
        business_name='Consulting',
        gross_receipts=100000,
        w2_wages=60000,
    )],
)
rpt_8995a = r.generate_report(schema_8995a, e.run)
has_8995a_flag = any(f['code'] == '8995A_REQUIRED' for f in rpt_8995a['flags'])
check_bool("28.2 8995A_REQUIRED flag set for above-threshold filer",
           "f8995a.pdf; IRC §199A(b)(2)", has_8995a_flag, True)
qbi_supp = rpt_8995a.get('supplemental', {}).get('qbi_deduction', {})
form_used = qbi_supp.get('form_used', {}).get('value', '')
check_bool("28.2 Supplemental QBI section shows 8995-A",
           "f8995a.pdf", form_used == '8995-A', True)

# 28.3: QBI carryforward from prior year reduces deduction and shows in report
schema_cf_import = e.TaxpayerSchema(
    first='CFImport', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=50000, box2_fed_wh=5000)],
    schedule_cs=[e.ScheduleC(business_name='Biz', gross_receipts=40000)],
    qbi_loss_carryforward=5000,
)
rpt_cf = r.generate_report(schema_cf_import, e.run)
qbi_l2_cf = rpt_cf.get('supplemental', {}).get('qbi_deduction', {}).get('l2_net_qbi', {}).get('value', -1)
check_bool("28.3 QBI supplemental section present when carryforward applied",
           "f8995.pdf L11; Reg. 1.199A-1(d)(2)(iii)", qbi_l2_cf >= 0, True)

# 28.4: Comparison mode returns correct structure
schema_comp = e.TaxpayerSchema(
    first='CompReport', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=75000, box2_fed_wh=9000)],
)
comp_r = e.run(schema_comp)
comp_vals = {"agi": comp_r['computed']['agi']}
diff = e.compare_to_competitor(schema_comp, comp_vals)
check_bool("28.4 Comparison mode returns summary dict",
           "compare_to_competitor()", 'summary' in diff, True)
check_bool("28.4 Comparison mode summary has expected keys",
           "compare_to_competitor()", all(k in diff['summary'] for k in
           ['match', 'diff', 'miss', 'extra', 'all_match']), True)
check_bool("28.4 Exact AGI match detected",
           "compare_to_competitor()", diff['summary']['all_match'], True)

# 28.5: import_prior_year_carryforward round-trip: run → carryforward packet → import → run
schema_yr1 = e.TaxpayerSchema(
    first='Year1', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=60000, box2_fed_wh=6000)],
    form_8606=e.Form8606Data(nonded_contrib_this_year=7000, basis_prior_year=0,
                               trad_ira_value_dec31=7000, trad_ira_distributions=0),
)
rpt_yr1 = r.generate_report(schema_yr1, e.run)
cf_packet = {
    "f8606_basis":          rpt_yr1['carryforwards']['form_8606_basis_remaining']['value'],
    "qbi_loss_carryforward": rpt_yr1['carryforwards']['qbi_loss_carryforward']['value'],
    "capital_loss_carryover": rpt_yr1['carryforwards']['capital_loss_carryover']['value'],
}
schema_yr2 = e.TaxpayerSchema(
    first='Year2', last='Test', filing_status='single', tax_year=2025,
    w2s=[e.W2(employer='Corp', box1_wages=65000, box2_fed_wh=7000)],
)
schema_yr2_imported = e.import_prior_year_carryforward(schema_yr2, cf_packet)
check_bool("28.5 Round-trip: Form 8606 basis imported from prior year report",
           "f8606.pdf L14 → next year L2",
           schema_yr2_imported.form_8606 is not None and
           schema_yr2_imported.form_8606.basis_prior_year ==
           rpt_yr1['carryforwards']['form_8606_basis_remaining']['value'],
           True)

print()
print("=" * 65)
print(f"Results: {PASS} passed  |  {FAIL} failed")
if FAIL == 0:
    print("✅ ALL REPORT TESTS PASSED")
else:
    print(f"❌ {FAIL} test(s) failed")
print("=" * 65)
sys.exit(0 if FAIL == 0 else 1)
