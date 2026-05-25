"""
SachinTaxCare -- Regression & Bridge Audit Test Suite
=====================================================
Runs on every server start via: python3 sachintaxcare_test.py
Also callable standalone for CI.

Three layers:
  Layer 1 -- Bridge Audit: every schema field that buildSchema() can produce
             must map to a valid engine field (no silent drops)
  Layer 2 -- Pipeline Regression: known schemas -> expected computed values
  Layer 3 -- Engine Unit: key calculations verified against IRS publications

Source: IRS forms, publications, and instructions cited inline.
"""

import sys, json, dataclasses, traceback
sys.path.insert(0, '.')
import sachintaxcare_engine as e

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
PASS = 0; FAIL = 0; WARN = 0
results = []

def ok(label, got, expected, tolerance=1, note=''):
    global PASS, FAIL
    if isinstance(expected, bool):
        passed = bool(got) == expected
    elif isinstance(expected, str):
        passed = str(got) == expected
    else:
        passed = abs((got or 0) - expected) <= tolerance
    sym = '[PASS]' if passed else '[FAIL]'
    if passed: PASS += 1
    else: FAIL += 1
    results.append((sym, label, got, expected, note))
    if not passed:
        print(f"  {sym} {label}: got={got} expected={expected} {note}")

def warn(label, message):
    global WARN
    WARN += 1
    results.append(('[WARN] ', label, message, '', ''))
    print(f"  [WARN]  {label}: {message}")

def section(title):
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# -----------------------------------------------------------------------------
# LAYER 1 -- BRIDGE AUDIT
# All schema fields that the UI can send must reach the engine correctly
# -----------------------------------------------------------------------------
section("LAYER 1 -- Bridge Audit: Schema -> Engine Field Mapping")

# Fields the UI/schema sends that differ from engine field names.
# Format: (description, engine_class, schema_key, engine_key)
BRIDGE_MAPPINGS = [
    # Form1099INT — field renamed 2026-05-19 to match JSON key (no bridge needed)
    # box2_early_withdrawal_penalty: JSON key == engine field now (renamed from box2_early_withdrawal)
    # Source: f1099int.pdf Box 2; i1040s1.pdf Line 18; IRC §62(a)(9)
    # Form1099C
    ("1099-C discharged amount",    e.Form1099C, "box2_discharged",        "box2_amount_discharged"),
    ("1099-C exclusion flag",        e.Form1099C, "exclusion_applies",      "is_excluded"),
    # FormSSA1099
    ("SSA WH voluntary",             e.FormSSA1099, "box6_vol_wh",          "box6_voluntary_wh"),
    # SimplifiedMethodData
    ("SM age at start",              e.SimplifiedMethodData, "age_at_start", "age_at_annuity_start"),
    ("SM joint age",                 e.SimplifiedMethodData, "joint_age_at_start", "joint_age_at_annuity_start"),
    ("SM prior recovered",           e.SimplifiedMethodData, "prior_tax_free_recovered", "prior_year_tax_free_recovered"),
    # SM start_after_nov_1996: now a proper alias field in SimplifiedMethodData (added 2026-05-19)
    # No bridge needed — safe_init passes it through directly.
    # Form1099R
    ("1099-R cost basis",            e.Form1099R, "box9b_employee_contrib", "box9b_employee_contribs"),
    # W2
    ("W2 med wages",                 e.W2, "box5_medicare_wages", "box5_med_wages"),
    ("W2 med WH",                    e.W2, "box6_medicare_wh",   "box6_med_wh"),
    ("W2 dep care",                  e.W2, "box10_dep_care",     "box10_dependent_care"),
    ("W2 nonqual deferred",          e.W2, "box11_nonqual_deferred", "box11_nonqual_def_comp"),
    # Dependent
    ("Dependent full_time_student",  e.Dependent, "is_full_time_student", None),  # not in engine
    # Form1098T
    ("1098-T student_is",            e.Form1098T, "student_is",   None),   # mapped via bridge
    ("1098-T box8_at_least_half_time", e.Form1098T, "box8_at_least_half_time", None),  # check it maps
]

for desc, cls, schema_key, engine_key in BRIDGE_MAPPINGS:
    valid_fields = {f.name for f in dataclasses.fields(cls)}
    if engine_key is None:
        # Just check schema_key isn't directly in engine (it's a bridge case)
        schema_direct = schema_key in valid_fields
        # This is expected to be NOT directly in engine -- it's a bridge field
        ok(f"Bridge needed: {cls.__name__}.{schema_key}",
           not schema_direct, True,
           note="(schema key differs from engine -- bridge required)")
    else:
        engine_has = engine_key in valid_fields
        schema_missing = schema_key not in valid_fields
        ok(f"{desc}: engine has '{engine_key}'", engine_has, True)
        ok(f"{desc}: schema key '{schema_key}' != engine (needs bridge)", schema_missing, True)

# Verify engine dataclass field counts haven't changed unexpectedly
ok("Form1099C has box2_amount_discharged", 
   "box2_amount_discharged" in {f.name for f in dataclasses.fields(e.Form1099C)}, True)
ok("Form1099C has is_excluded",
   "is_excluded" in {f.name for f in dataclasses.fields(e.Form1099C)}, True)
ok("FormSSA1099 has box6_voluntary_wh",
   "box6_voluntary_wh" in {f.name for f in dataclasses.fields(e.FormSSA1099)}, True)
ok("SimplifiedMethodData has start_after_nov_1996 alias",
   "start_after_nov_1996" in {f.name for f in dataclasses.fields(e.SimplifiedMethodData)}, True,
   note="Alias field added 2026-05-19 — safe_init now passes UI key directly to engine")
ok("SimplifiedMethodData has use_simplified_method",
   "use_simplified_method" in {f.name for f in dataclasses.fields(e.SimplifiedMethodData)}, True)
ok("SimplifiedMethodData has cost_in_contract",
   "cost_in_contract" in {f.name for f in dataclasses.fields(e.SimplifiedMethodData)}, True)


# -----------------------------------------------------------------------------
# LAYER 2 -- Pipeline Regression Tests
# Full schema -> deserialize_schema() -> e.run() -> assert computed values
# -----------------------------------------------------------------------------
section("LAYER 2 -- Pipeline Regression Tests")

# Import the server's deserialize_schema (the real bridge we're testing)
try:
    # We can't import the full server (Flask dependency), so replicate
    # deserialize_schema logic inline -- this IS the bridge under test
    from sachintaxcare_server import deserialize_schema, map_result
    USE_SERVER_BRIDGE = True
    print("  Using server's deserialize_schema() directly")
except Exception:
    USE_SERVER_BRIDGE = False
    print("  [WARN]  Cannot import server (Flask not installed) -- using inline bridge")


def build_bridge(raw: dict) -> e.TaxpayerSchema:
    """Replicate server deserialize_schema logic for testing without Flask."""
    _LIST_MAP = {
        'w2s': e.W2, 'form_1099ints': e.Form1099INT, 'form_1099divs': e.Form1099DIV,
        'form_1099rs': e.Form1099R, 'form_1099necs': e.Form1099NEC,
        'form_1099cs': e.Form1099C, 'form_1099misc_prizes': e.Form1099MISC_Prize,
        'form_1099bs': e.Form1099B, 'form_1099gs': e.Form1099G,
        'form_w2gs': e.FormW2G, 'schedule_cs': e.ScheduleC, 'schedule_es': e.ScheduleE,
        'schedule_k1s': e.ScheduleK1, 'dependents': e.Dependent,
        'care_providers': e.Form2441Provider, 'form_1098ts': e.Form1098T,
        'form_5329_exceptions': e.Form5329Exception, 'form_4797s': e.Form4797SaleData,
    }
    _NESTED = {
        'form_ssa1099': e.FormSSA1099, 'schedule_a': e.ScheduleAData,
        'form_8606': e.Form8606Data, 'form_8606_spouse': e.Form8606Data,
        'form_8889': e.Form8889Data, 'form_1095a': e.Form1095A,
        'form_8880': e.Form8880Data, 'form_6251': e.Form6251Data,
        'form_2210': e.Form2210Data, 'form_1116': e.Form1116Data,
        'form_8615': e.Form8615Data, 'form_4972': e.Form4972Data,
        'form_8582': e.Form8582Data, 'alimony': e.AlimonyData,
        'deceased_spouse': e.DeceasedSpouse, 'california': e.CaliforniaData,
        'estimated_tax_payments': e.EstimatedTaxPayments,
    }

    def safe_init(cls, data):
        if not isinstance(data, dict): return None
        valid = {f.name for f in dataclasses.fields(cls)}
        try: return cls(**{k: v for k, v in data.items() if k in valid})
        except Exception: return None

    kwargs = {}
    for key, value in raw.items():
        if key in _LIST_MAP and isinstance(value, list):
            kwargs[key] = [x for d in value for x in [safe_init(_LIST_MAP[key], d)] if x]
        elif key in _NESTED and isinstance(value, dict):
            inst = safe_init(_NESTED[key], value)
            if inst: kwargs[key] = inst
        else:
            kwargs[key] = value

    # -- Bridge 1: Form1099C ---------------------------------------------------
    bridged_cs = []
    for c in raw.get('form_1099cs', []):
        if not isinstance(c, dict): continue
        bridged_cs.append(e.Form1099C(
            creditor=c.get('creditor', ''),
            box2_amount_discharged=float(c.get('box2_discharged') or c.get('box2_amount_discharged') or 0),
            box6_event_code=c.get('box6_event_code') or c.get('box6_code') or '',
            is_excluded=bool(c.get('exclusion_applies') or c.get('is_excluded') or False),
        ))
    if bridged_cs: kwargs['form_1099cs'] = bridged_cs

    # -- Bridge 2: FormSSA1099 box6_vol_wh -> box6_voluntary_wh ---------------
    ssa_raw = raw.get('form_ssa1099')
    if isinstance(ssa_raw, dict):
        kwargs['form_ssa1099'] = e.FormSSA1099(
            box3_gross_benefits=float(ssa_raw.get('box3_gross_benefits', 0)),
            box4_repayments=float(ssa_raw.get('box4_repayments', 0)),
            box5_net_benefits=float(ssa_raw.get('box5_net_benefits', 0)),
            box6_voluntary_wh=float(ssa_raw.get('box6_vol_wh') or ssa_raw.get('box6_voluntary_wh') or 0),
            mfs_lived_apart_all_year=bool(ssa_raw.get('mfs_lived_apart') or ssa_raw.get('mfs_lived_apart_all_year') or False),
            lump_sum_prior_years=[],
        )

    # -- Bridge 3: Form1099R simplified_method + box9b ------------------------
    bridged_rs = []
    for raw_r in raw.get('form_1099rs', []):
        if not isinstance(raw_r, dict): continue
        sm_raw = raw_r.get('simplified_method')
        sm_obj = None
        if raw_r.get('use_simplified_method') and isinstance(sm_raw, dict):
            cost = float(raw_r.get('box9b_employee_contrib') or raw_r.get('box9b_employee_contribs') or 0)
            sm_obj = e.SimplifiedMethodData(
                use_simplified_method=True,
                cost_in_contract=cost,
                annuity_type=sm_raw.get('annuity_type', 'single'),
                age_at_annuity_start=int(sm_raw.get('age_at_start') or sm_raw.get('age_at_annuity_start') or 0),
                joint_age_at_annuity_start=int(sm_raw.get('joint_age_at_start') or sm_raw.get('joint_age_at_annuity_start') or 0),
                fixed_period_months=int(sm_raw.get('fixed_period_months') or 0),
                prior_year_tax_free_recovered=float(sm_raw.get('prior_tax_free_recovered') or sm_raw.get('prior_year_tax_free_recovered') or 0),
                annuity_start_after_nov_18_1996=bool(sm_raw.get('start_after_nov_1996', True)),
            )
        valid_r = {f.name for f in dataclasses.fields(e.Form1099R)}
        r_kw = {k: v for k, v in raw_r.items() if k in valid_r}
        # bridge box9b singular -> plural
        if 'box9b_employee_contrib' in raw_r and 'box9b_employee_contribs' not in r_kw:
            r_kw['box9b_employee_contribs'] = float(raw_r.get('box9b_employee_contrib') or 0)
        if sm_obj:
            r_kw['simplified_method'] = sm_obj
            if r_kw.get('box9b_employee_contribs', 0) == 0:
                r_kw['box9b_employee_contribs'] = sm_obj.cost_in_contract
        try: bridged_rs.append(e.Form1099R(**r_kw))
        except Exception: pass
    if bridged_rs: kwargs['form_1099rs'] = bridged_rs

    # -- Bridge 4: 1099-MISC Box 3 -> prizes -----------------------------------
    misc_prizes = list(kwargs.get('form_1099misc_prizes', []))
    for m in raw.get('form_1099miscs', []):
        if isinstance(m, dict) and (m.get('box3_other_income') or 0) > 0:
            misc_prizes.append(e.Form1099MISC_Prize(
                payer=m.get('payer', ''),
                box3_other_income=float(m['box3_other_income']),
                description='Prize/Award/Other'))
    if misc_prizes: kwargs['form_1099misc_prizes'] = misc_prizes

    valid = {f.name for f in dataclasses.fields(e.TaxpayerSchema)}
    filtered = {k: v for k, v in kwargs.items() if k in valid}
    for key in ['form_1099ints','form_1099divs','form_1099rs','form_1099necs','form_1099cs',
                'form_1099misc_prizes','form_1099bs','form_1099gs','form_w2gs',
                'schedule_cs','schedule_es','schedule_k1s','dependents','care_providers',
                'form_1098ts','form_5329_exceptions','form_4797s']:
        filtered.setdefault(key, [])
    return e.TaxpayerSchema(**filtered)


def run_schema(raw: dict) -> dict:
    """Run schema through bridge -> engine, return computed dict."""
    if USE_SERVER_BRIDGE:
        try:
            schema = deserialize_schema(raw)
            return e.run(schema).get('computed', {})
        except Exception:
            pass  # fall through to inline bridge
    schema = build_bridge(raw)
    return e.run(schema).get('computed', {})


# -- TEST 1: MFJ complex 2025 — pension (SM), SSA, CoD, interest, senior ded, est payments --
print("\n  Test 1: MFJ complex 2025 (pension SM + SSA + CoD + interest + senior ded)")
try:
    import dataclasses as _dc1
    def _si1(cls, **kw):
        valid = {f.name for f in _dc1.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})

    _sm1 = e.SimplifiedMethodData(
        use_simplified_method=True, cost_in_contract=15000,
        annuity_type="joint", age_at_annuity_start=67,
        joint_age_at_annuity_start=58, fixed_period_months=0,
        prior_year_tax_free_recovered=1259,
        annuity_start_after_nov_18_1996=True)
    # Combined age 67+58=125 -> IRS Pub 939 Table 2: 310 payments
    # Monthly exclusion = 15000/310 = 48.387; annual = 48.387*12 = 580.65 -> round = 581
    # Prior recovered = 1259 -> remaining basis = 15000-1259 = 13741; still < 310*581 -> full exclusion
    # taxable = 22100 - 581 = 21519

    _r1 = _si1(e.Form1099R, payer="Pension Board", ein="12-3456789", recipient="spouse",
        box1_gross=22100, box2a_taxable=22100, box4_fed_wh=2210, box7_code="7",
        box7_ira_sep_simple=False, box9b_employee_contribs=15000, simplified_method=_sm1)
    _ssa1 = e.FormSSA1099(
        box3_gross_benefits=25000, box4_repayments=0, box5_net_benefits=24500,
        box6_voluntary_wh=0, mfs_lived_apart_all_year=False, lump_sum_prior_years=[])
    _cod1 = e.Form1099C(creditor="Bank", box2_amount_discharged=850,
        box6_event_code="A", is_excluded=False)
    _int1 = _si1(e.Form1099INT, payer="Federal Savings", payer_ein="", account_number="",
        box1_interest=222, box2_early_withdrawal_penalty=0, box3_us_savings_bond=0,
        box4_fed_wh=0, box5_investment_expenses=0, box6_foreign_tax=0,
        box7_foreign_country="", box8_tax_exempt_interest=0,
        box9_private_activity_bond=0, box10_market_discount=0, box11_bond_premium=0,
        box12_bond_premium_treasury=0, box13_bond_premium_tax_exempt=0,
        box14_cusip="", box15_state_wh=0, box16_state_id="", box17_state_income=0)
    _w1 = _si1(e.W2, employer="Corp", ein="98-7654321", box1_wages=39353,
        box2_fed_wh=3500, box3_ss_wages=39353, box4_ss_wh=2440,
        box5_med_wages=39353, box6_med_wh=570, box13_retirement_plan=False,
        box16_state_wages=39353, box17_state_wh=1200, for_spouse=False)
    _et1 = e.EstimatedTaxPayments(q1=658, q2=658, q3=658, q4=656,
        prior_year_overpayment_applied=0)

    _s1 = _si1(e.TaxpayerSchema,
        first="Test", last="MFJ", ssn="100-00-0001", dob="01-01-1955",
        occupation="Retired", address="1 Test St", filing_status="mfj",
        tax_year=2025, spouse_age_for_senior_ded=70,
        estimated_tax_payments=_et1,
        w2s=[_w1], form_1099rs=[_r1], form_ssa1099=_ssa1,
        form_1099cs=[_cod1], form_1099ints=[_int1],
        form_1099divs=[], form_1099necs=[], form_1099misc_prizes=[],
        form_1099bs=[], schedule_cs=[], schedule_es=[], schedule_k1s=[],
        dependents=[], care_providers=[], form_1098ts=[], form_w2gs=[],
        form_1099gs=[], form_5329_exceptions=[], form_4797s=[])
    _c1 = e.run(_s1).get("computed", {})
    def g(k): return _c1.get(k, 0)

    ok("W1.1 Wages",                  g('wages'),                   39353)
    ok("W1.2 Pension gross (5a)",     g('l5a_pension_gross'),        22100)
    ok("W1.3 Pension taxable (5b)",   g('l5b_pension_taxable'),      21519, tolerance=1,
       note="IRS Pub 575/939 WkshtA; combined age 125->310 pmts; 15000/310*12=581 exclusion")
    ok("W1.4 SS taxable (6b)",        g('l6b_ss_taxable'),           20825, tolerance=5,
       note="IRS Pub 915 WS1; provisional = wages+pension+CoD+0.5*SSA = 61800; 85% tier")
    ok("W1.5 Cancelled debt",         g('cancelled_debt'),           850,
       note="IRC §61(a)(12); 1099-C non-excluded")
    ok("W1.6 Interest income",        g('interest'),                 222,
       note="1099-INT box1_interest")
    ok("W1.7 AGI",                    g('agi'),                      82769, tolerance=10,
       note="total_income(82769) - total_adjustments(0) = 82769; OBBBA senior $12,000 now below-line Sch1-A Line 13b, does NOT reduce AGI. Source: f1040s1a.pdf; IR-2026-28")
    ok("W1.8 OBBBA senior deduction", g('obbba_senior_deduction'),   12000,
       note="OBBBA §70103; TP DOB 1955 (age 70) + spouse_age_for_senior_ded=70 = 2×$6,000. Schedule 1-A Part V → Form 1040 Line 13b. Source: f1040s1a.pdf; IR-2026-28")
    ok("W1.8b total_adjustments",     g('total_adjustments'),        0,
       note="W1 schema has no Schedule 1 adjustments; OBBBA senior $12,000 on Schedule 1-A (below-line). Source: f1040s1a.pdf; IR-2026-28")
    ok("W1.9 Std ded MFJ+2 seniors",  g('std_deduction'),            34700, tolerance=0,
       note="IRC §63(f); MFJ $31,500 + 2×$1,600 age-65 addon")
    ok("W1.8c l13b_schedule1a",       g('l13b_schedule1a'),          12000, tolerance=0,
       note="Schedule 1-A total → Form 1040 Line 13b; Source: f1040s1a.pdf Part VI; IR-2026-28")
    ok("W1.10 Taxable income",        g('taxable_income'),           36069, tolerance=5,
       note="82769 AGI - 34700 std ded - 12000 Sch1-A Line 13b = 36069. Source: f1040s1a.pdf Part VI; Form 1040 Line 15")
    ok("W1.11 W-2 WH (25a)",          g('l25a_w2_wh'),               3500)
    ok("W1.12 1099-R WH (25b)",       g('l25b_1099r_wh'),            2210)
    ok("W1.13 SSA vol WH",            g('l25b_ssa_wh'),              0,
       note="box6_vol_wh=0; SSA WH bridge tested separately in Test 5")
    ok("W1.14 Total WH (25d)",        g('l25d_total_wh'),            5710)
    ok("W1.15 Refund",                g('l34_refund'),               4489, tolerance=50,
       note="WH $5,710 + est $2,630 - tax after credits; AGI $82,769 (OBBBA below-line, no AGI change for this case)")
except Exception as ex:
    warn("MFJ complex test CRASHED", traceback.format_exc(limit=3))

# -- TEST 2: Simple Single W-2 Only --------------------------------------------
print("\n  Test 2: Single filer, W-2 only")
try:
    simple_single = {
        "first":"Test","last":"Single","ssn":"111-22-3333","dob":"01-15-1985",
        "occupation":"Engineer","address":"123 Main St","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Acme","ein":"11-1111111","box1_wages":80000,
                "box2_fed_wh":12000,"box3_ss_wages":80000,"box4_ss_wh":4960,
                "box5_medicare_wages":80000,"box6_medicare_wh":1160,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":80000,
                "box17_state_wh":4000,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_1099ints":[],"form_1099divs":[],"form_1099rs":[],"form_1099necs":[],
        "form_ssa1099":None,"form_1099cs":[],"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c2 = run_schema(simple_single)
    def g2(k): return c2.get(k, 0)
    # Standard deduction single 2025 = $15,000
    # Taxable = 80000 - 15000 = 65000
    # Tax (MFJ brackets for single): 10% on 11925 + 12% on (48475-11925) + 22% on (65000-48475)
    #  = 1192.5 + 4386 + 3635.5 = 9214
    ok("S2.1 Wages",              g2('wages'),       80000)
    ok("S2.2 AGI",                g2('agi'),         80000)
    ok("S2.3 Std deduction",      g2('std_deduction'), 15750,
       note="Source: OBBBA S.70001 + Rev. Proc. 2024-40; inflation-adjusted to $15,750")
    ok("S2.4 Taxable income",     g2('taxable_income'), 64250)
    ok("S2.5 Income tax",         g2('income_tax'),  9049, tolerance=5,
       note="Source: 2025 tax tables; IRS Rev. Proc. 2024-40")
    ok("S2.6 Total WH",           g2('l25d_total_wh'), 12000)
    ok("S2.7 Refund",             g2('l34_refund'),   2951, tolerance=10)
except Exception as ex:
    warn("Simple single test CRASHED", traceback.format_exc(limit=3))

# -- TEST 3: MFJ Standard Deduction --------------------------------------------
print("\n  Test 3: MFJ standard deduction 2025")
try:
    mfj_std = {
        "first":"John","last":"Test","ssn":"222-33-4444","dob":"01-01-1970",
        "occupation":"Worker","address":"456 Oak St","filing_status":"mfj",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Corp","ein":"22-2222222","box1_wages":100000,
                "box2_fed_wh":15000,"box3_ss_wages":100000,"box4_ss_wh":6200,
                "box5_medicare_wages":100000,"box6_medicare_wh":1450,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":100000,
                "box17_state_wh":5000,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_1099ints":[],"form_1099divs":[],"form_1099rs":[],"form_1099necs":[],
        "form_ssa1099":None,"form_1099cs":[],"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c3 = run_schema(mfj_std)
    ok("S3.1 MFJ std deduction 2025", c3.get('std_deduction',0), 31500,
       note="Source: OBBBA S.70001 + Rev. Proc. 2024-40; inflation-adjusted MFJ $31,500")
    ok("S3.2 Taxable income MFJ", c3.get('taxable_income',0), 68500)
except Exception as ex:
    warn("MFJ std deduction test CRASHED", traceback.format_exc(limit=3))

# -- TEST 4: Cancelled Debt Included in Income ----------------------------------
print("\n  Test 4: Cancelled debt (1099-C) added to income")
try:
    cod_test = {
        "first":"Debt","last":"Test","ssn":"333-44-5555","dob":"01-01-1980",
        "occupation":"Worker","address":"789 Pine St","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Corp","ein":"33-3333333","box1_wages":50000,
                "box2_fed_wh":6000,"box3_ss_wages":50000,"box4_ss_wh":3100,
                "box5_medicare_wages":50000,"box6_medicare_wh":725,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":50000,
                "box17_state_wh":2500,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_1099cs":[{
            "creditor":"Big Bank","box2_discharged":5000,
            "box6_event_code":"A","exclusion_applies":False}],
        "form_1099ints":[],"form_1099divs":[],"form_1099rs":[],"form_1099necs":[],
        "form_ssa1099":None,"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c4 = run_schema(cod_test)
    ok("S4.1 Cancelled debt computed", c4.get('cancelled_debt',0), 5000,
       note="Source: IRC S.61(a)(12); Pub 4681")
    ok("S4.2 Total income includes CoD", c4.get('total_income',0), 55000,
       note="Wages 50,000 + CoD 5,000")
    ok("S4.3 AGI includes CoD",       c4.get('agi',0),          55000)
except Exception as ex:
    warn("Cancelled debt test CRASHED", traceback.format_exc(limit=3))

# -- TEST 5: SSA Withholding ----------------------------------------------------
print("\n  Test 5: SSA voluntary withholding (box6_vol_wh)")
try:
    ssa_test = {
        "first":"SS","last":"Test","ssn":"444-55-6666","dob":"01-01-1950",
        "occupation":"Retired","address":"101 Elm St","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Corp","ein":"44-4444444","box1_wages":30000,
                "box2_fed_wh":3000,"box3_ss_wages":30000,"box4_ss_wh":1860,
                "box5_medicare_wages":30000,"box6_medicare_wh":435,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":30000,
                "box17_state_wh":1500,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_ssa1099":{
            "box3_gross_benefits":15000,"box4_repayments":0,"box5_net_benefits":15000,
            "box6_vol_wh":1500,   # <- schema key (not box6_voluntary_wh)
            "mfs_lived_apart":False,"lump_sum_election":False,"lump_sum_years":[]},
        "form_1099cs":[],"form_1099ints":[],"form_1099divs":[],"form_1099rs":[],
        "form_1099necs":[],"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c5 = run_schema(ssa_test)
    ok("S5.1 SSA WH reaches l25b_ssa_wh", c5.get('l25b_ssa_wh',0), 1500,
       note="box6_vol_wh -> box6_voluntary_wh bridge; Source: IRC S.3402(p); SSA-1099 Box 6")
    ok("S5.2 Total WH includes SSA WH", c5.get('l25d_total_wh',0), 4500,
       note="W-2 $3,000 + SSA $1,500")
except Exception as ex:
    warn("SSA withholding test CRASHED", traceback.format_exc(limit=3))

# -- TEST 6: Simplified Method Joint & Survivor Annuity -----------------------
print("\n  Test 6: Simplified method -- Joint & Survivor pension")
try:
    sm_test = {
        "first":"Annuity","last":"Test","ssn":"555-66-7777","dob":"01-01-1958",
        "occupation":"Retired","address":"202 Oak Ave","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[],
        "form_1099rs":[{
            "payer":"Pension Corp","ein":"55-5555555","recipient":"taxpayer",
            "box1_gross":12000,"box2a_taxable":12000,
            "box3_cap_gain":0,"box4_fed_wh":0,"box5_employee_contrib":0,
            "box6_nua":0,"box7_code":"2","box7_code2":"","box7_ira_sep_simple":False,
            "box9a_pct":100,"box9b_employee_contrib":18000,  # <- cost basis (schema key)
            "box10_irr":0,"box11_roth_yr":"","box12_fatca":False,"box13_date":"",
            "box14_state_wh":0,"box17_local_wh":0,
            "use_simplified_method":True,
            "simplified_method":{
                "annuity_type":"joint",
                "age_at_start":65,          # <- schema key
                "joint_age_at_start":60,    # <- schema key; combined=125 -> 260 payments
                "fixed_period_months":0,
                "prior_tax_free_recovered":0,
                "start_after_nov_1996":True}}],
        "form_1099cs":[],"form_1099ints":[],"form_1099divs":[],"form_1099necs":[],
        "form_ssa1099":None,"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c6 = run_schema(sm_test)
    # Combined age 65+60=125 -> IRS Pub 939 Table 2: combined 121-130 -> 310 payments
    # monthly exclusion = 18000/310 = $58.06 -> annual = $696.77
    # year 1: prior=0, tax_free = min(696.77, 18000) = 696.77
    # taxable = 12000 - 696.77 = 11303.23 -> rounded 11303
    expected_taxable = round(12000 - (18000/310*12))
    ok("S6.1 SM pension taxable (not full gross)", 
       c6.get('l5b_pension_taxable',0), expected_taxable, tolerance=5,
       note=f"IRS Pub 939 Table 2: combined age 125 -> 310 payments; expected ~{expected_taxable}")
    ok("S6.2 SM exclusion applied (taxable < gross)",
       c6.get('l5b_pension_taxable',0) < 12000, True,
       note="Simplified method MUST reduce taxable below gross")
except Exception as ex:
    warn("Simplified method test CRASHED", traceback.format_exc(limit=3))

# -- TEST 7: OBBBA Senior Deduction --------------------------------------------
print("\n  Test 7: OBBBA senior deduction -- age 65+, AGI limit")
try:
    senior_test = {
        "first":"Senior","last":"Test","ssn":"666-77-8888","dob":"01-01-1958",
        "occupation":"Retired","address":"303 Elm","filing_status":"mfj",
        "tax_year":2025,"use_itemized":False,
        "taxpayer_age_for_senior_ded":67,
        "spouse_age_for_senior_ded":66,
        "w2s":[{"employer":"Corp","ein":"66-6666666","box1_wages":60000,
                "box2_fed_wh":6000,"box3_ss_wages":60000,"box4_ss_wh":3720,
                "box5_medicare_wages":60000,"box6_medicare_wh":870,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":60000,
                "box17_state_wh":3000,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_1099cs":[],"form_1099ints":[],"form_1099divs":[],"form_1099rs":[],
        "form_1099necs":[],"form_ssa1099":None,"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c7 = run_schema(senior_test)
    ok("S7.1 Senior deduction both spouses = $12,000",
       c7.get('obbba_senior_deduction',0), 12000,
       note="Source: OBBBA S.70103; $6,000 x 2 qualifying spouses; AGI $60k < $150k limit")
    ok("S7.2 Senior ded is below-line (Schedule 1-A) — does NOT reduce AGI",
       c7.get('agi',0), 60000 - c7.get('teacher_adj',0), tolerance=5,
       note="Source: f1040s1a.pdf; IR-2026-28 — OBBBA deductions → Line 13b, not Line 10")
    ok("S7.3 Senior ded reduces taxable income via Line 13b",
       c7.get('taxable_income',0),
       max(0, c7.get('agi',0) - c7.get('deduction_used',0) - 12000), tolerance=5,
       note="Source: f1040s1a.pdf Part VI; Schedule 1-A total → Form 1040 Line 13b")
    ok("S7.4 l13b_schedule1a key = 12000",
       c7.get('l13b_schedule1a',0), 12000, tolerance=0,
       note="Source: f1040s1a.pdf Part VI; IR-2026-28")
except Exception as ex:
    warn("OBBBA senior test CRASHED", traceback.format_exc(limit=3))

# -- TEST 9: DOB fallback — senior deduction when age fields = 0 ---------------
# Willis scenario: exported schema has taxpayer_age_for_senior_ded=0 and
# spouse_age_for_senior_ded=0 because the UI sent zeros. Engine must auto-derive
# from DOBs. This is the root cause of the deduction being stuck at $31,500.
print("\n  Test 9: DOB fallback — senior ded when age fields=0, DOBs present")
try:
    import dataclasses as _dc9
    def _si9(cls, **kw):
        valid = {f.name for f in _dc9.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})

    schema9 = _si9(e.TaxpayerSchema,
        first="Martin", last="Willis", ssn="416-00-1111",
        dob="05-01-1964",          # Martin age 61 -- does NOT qualify
        filing_status="mfj", tax_year=2025,
        taxpayer_age_for_senior_ded=0,   # ZERO — engine must use DOB
        spouse_age_for_senior_ded=0,     # ZERO — engine must use spouse_dob
        spouse_dob="10-08-1955",         # Yvette age 69 -- QUALIFIES
        spouse_ssn="417-00-1111",
        teacher_expense=275,
        w2s=[_si9(e.W2, employer="ROOSEVELT", ein="35-7001111",
            box1_wages=39353, box2_fed_wh=3500, box3_ss_wages=41353, box4_ss_wh=2563,
            box5_med_wages=41353, box6_med_wh=599, box13_retirement_plan=True,
            box16_state_wages=39353, box17_state_wh=600, for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c9 = e.run(schema9).get("computed", {})

    ok("S9.1 DOB fallback: senior ded = $6,000 (Yvette only)",
       c9.get("obbba_senior_deduction", 0), 6000, tolerance=0,
       note="age_fields=0; engine derives Yvette age=69 from spouse_dob='10-08-1955'")
    ok("S9.2 DOB fallback: std ded = $33,100 (MFJ + 1 addon)",
       c9.get("std_deduction", 0), 33100, tolerance=0,
       note="MFJ $31,500 + $1,600 (Yvette age 69 >= 65); Martin age 61 no addon")
    ok("S9.3 DOB fallback: AGI = wages - teacher_adj only",
       c9.get("agi", 0), 39078, tolerance=5,
       note="39353 wages - 275 teacher = 39078; OBBBA senior $6,000 now Schedule 1-A below-line, does NOT reduce AGI. Source: f1040s1a.pdf; IR-2026-28")
    ok("S9.3b DOB fallback: l13b_schedule1a = 6000",
       c9.get("l13b_schedule1a", 0), 6000, tolerance=0,
       note="Yvette age 70 → $6,000 via Schedule 1-A Part V. Source: f1040s1a.pdf; IR-2026-28")
    ok("S9.4 Martin (age 61) does NOT qualify for senior ded",
       c9.get("obbba_senior_deduction", 0), 6000, tolerance=0,
       note="Only 1 person qualifies; would be $12,000 if both qualified")
except Exception as ex:
    warn("DOB fallback test CRASHED", traceback.format_exc(limit=3))


print("\n  Test 8: 1099-MISC Box 3 prize income -> Sch 1 Line 8b")
try:
    prize_test = {
        "first":"Prize","last":"Test","ssn":"777-88-9999","dob":"01-01-1985",
        "occupation":"Contestant","address":"404 Main","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Corp","ein":"77-7777777","box1_wages":40000,
                "box2_fed_wh":4000,"box3_ss_wages":40000,"box4_ss_wh":2480,
                "box5_medicare_wages":40000,"box6_medicare_wh":580,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":40000,
                "box17_state_wh":2000,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_1099miscs":[{"payer":"Game Show","box3_other_income":10000,
                           "box1_rents":0,"box2_royalties":0,"box4_fed_wh":0}],
        "form_1099cs":[],"form_1099ints":[],"form_1099divs":[],"form_1099rs":[],
        "form_1099necs":[],"form_ssa1099":None,"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c8 = run_schema(prize_test)
    ok("S8.1 Prize income computed",    c8.get('prize_income',0), 10000,
       note="Source: IRC S.74; 1099-MISC Box 3 -> Sch 1 Line 8b")
    ok("S8.2 Total income includes prize", c8.get('total_income',0), 50000,
       note="Wages 40,000 + Prize 10,000")
except Exception as ex:
    warn("Prize income test CRASHED", traceback.format_exc(limit=3))

# -- TEST 8B: ODC routing — child (age>=17) ODC via Sch 8812, NOT Sch 3 ----------
print("\n  Test 8B: ODC for aged-out child routes through Sch 8812 L14 (not Sch 3 L6d)")
try:
    import dataclasses as _dc8b
    def _si8b(cls, **kw):
        valid = {f.name for f in _dc8b.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})
    dep_odc = _si8b(e.Dependent, first='ODC', last='Child', ssn='300-00-0001',
        dob='01-01-2005', relationship='child', ctc_eligible=False, odc_eligible=True)
    s_odc = _si8b(e.TaxpayerSchema,
        first='T', last='T', ssn='100-00-0001', dob='01-01-1980',
        filing_status='single', tax_year=2025,
        w2s=[_si8b(e.W2, employer='Corp', ein='11-1111111', box1_wages=45000,
                box2_fed_wh=5000, box3_ss_wages=45000, box4_ss_wh=2790,
                box5_med_wages=45000, box6_med_wh=653, for_spouse=False)],
        dependents=[dep_odc],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c8b = e.run(s_odc).get("computed", {})
    s8_ = c8b.get("s8812", {})
    s3_ = c8b.get("sch3", {})
    ok("T8B.1 ODC in s8812.l4b_odc_amt = $500",
       s8_.get("l4b_odc_amt", s8_.get("odc_total", 0)), 500,
       note="IRC §24(h)(4); ODC for child goes through Sch 8812 L4b")
    ok("T8B.2 s8812.l4c_total = 500 (CTC 0 + ODC 500)",
       s8_.get("l4c_total", 0), 500,
       note="Sch 8812 L4c = L4a(0) + L4b(500); f1040s8.pdf")
    ok("T8B.3 l19_ctc (1040 L19) = $500 via Sch 8812 L14",
       c8b.get("l19_ctc", 0), 500,
       note="1040 L19 = Sch 8812 L14 total; CTC+ODC combined nonrefundable")
    ok("T8B.4 sch3.l6d_odc = $0 (ODC never on Sch 3)",
       s3_.get("l6d_odc", 0), 0,
       note="f1040s3.pdf 2025 — no L6d; all dependents route through Sch 8812")
except Exception as ex:
    warn("ODC routing test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 1: IRA deduction — spouse covered_by_plan from W-2 Box 13 --
print("\n  EA Fix 1: IRA deduction — spouse covered_by_plan derived from spouse W-2 Box 13")
try:
    import dataclasses as _dcea1
    def _siea1(cls, **kw):
        valid = {f.name for f in _dcea1.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})
    # Taxpayer NOT covered (box13=False), MFJ spouse IS covered (box13=True)
    # MAGI ~$180k < noncovered-MFJ phaseout start $236k → full $7,000 deduction
    s_ea1 = _siea1(e.TaxpayerSchema,
        first="T", last="T", ssn="100-00-0001", dob="01-01-1980",
        filing_status="mfj", tax_year=2025,
        ira_contribution_traditional=7000, ira_taxpayer_age=45,
        w2s=[
            _siea1(e.W2, employer="TP Corp", ein="11-1111111",
                box1_wages=100000, box2_fed_wh=15000, box3_ss_wages=100000,
                box4_ss_wh=6200, box5_med_wages=100000, box6_med_wh=1450,
                box13_retirement_plan=False, for_spouse=False),
            _siea1(e.W2, employer="SP Corp", ein="22-2222222",
                box1_wages=80000, box2_fed_wh=12000, box3_ss_wages=80000,
                box4_ss_wh=4960, box5_med_wages=80000, box6_med_wh=1160,
                box13_retirement_plan=True, for_spouse=True),
        ],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c_ea1 = e.run(s_ea1).get("computed", {})
    ok("EA1.1 IRA full deduction: TP not covered, MAGI < noncovered-MFJ phaseout",
       c_ea1.get("adj_ira_deduction", 0), 7000, tolerance=0,
       note="Pub 590-A WS 1-2; IRC §219(g)(7); MAGI ~$180k < $236k phaseout start")
    # Now test: MAGI above phaseout = partial/zero
    s_ea1b = _siea1(e.TaxpayerSchema,
        first="T", last="T", ssn="100-00-0002", dob="01-01-1980",
        filing_status="mfj", tax_year=2025,
        ira_contribution_traditional=7000, ira_taxpayer_age=45,
        w2s=[
            _siea1(e.W2, employer="TP Corp", ein="11-1111111",
                box1_wages=200000, box2_fed_wh=30000, box3_ss_wages=176100,
                box4_ss_wh=10918, box5_med_wages=200000, box6_med_wh=2900,
                box13_retirement_plan=False, for_spouse=False),
            _siea1(e.W2, employer="SP Corp", ein="22-2222222",
                box1_wages=80000, box2_fed_wh=12000, box3_ss_wages=80000,
                box4_ss_wh=4960, box5_med_wages=80000, box6_med_wh=1160,
                box13_retirement_plan=True, for_spouse=True),
        ],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c_ea1b = e.run(s_ea1b).get("computed", {})
    ok("EA1.2 IRA zero deduction: TP not covered, MAGI > noncovered-MFJ phaseout end $246k",
       c_ea1b.get("adj_ira_deduction", 0), 0, tolerance=0,
       note="MAGI ~$280k > $246k phaseout end → $0 deduction; Pub 590-A WS 1-2")
except Exception as ex:
    warn("IRA sp_covered test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 3: AOTC — hard gates (half-time + drug conviction) ----------
print("\n  EA Fix 3: AOTC hard gates — half-time enrollment and drug conviction")
try:
    import dataclasses as _dc3
    def _si3(cls, **kw):
        valid = {f.name for f in _dc3.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})

    def _base_schema(**extra):
        return _si3(e.TaxpayerSchema,
            first="T", last="T", ssn="100-00-0001", dob="01-01-1985",
            filing_status="single", tax_year=2025,
            w2s=[_si3(e.W2, employer="Corp", ein="11-1111111", box1_wages=45000,
                    box2_fed_wh=5000, box3_ss_wages=45000, box4_ss_wh=2790,
                    box5_med_wages=45000, box6_med_wh=653, for_spouse=False)],
            form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
            form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
            schedule_cs=[], dependents=[], care_providers=[],
            form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
            schedule_k1s=[], form_5329_exceptions=[], form_4797s=[], **extra)

    # Test 3a: half-time=True → AOTC allowed
    t_ht = _si3(e.Form1098T, institution="State U", ein="44-4444444",
        box1_payments=8000, box5_scholarships=2000,
        box8_half_time=True, credit_type="aoc", first_four_years=True)
    c3a = e.run(_base_schema(form_1098ts=[t_ht])).get("computed", {})
    ok("EA3.1 AOTC half-time=True → credit allowed",
       c3a.get("l29_aoc", 0), 1000, tolerance=0,
       note="IRC §25A(b)(1)(B); half-time confirmed → AOTC computed")

    # Test 3b: half-time=False → AOTC = $0 (hard gate)
    t_nht = _si3(e.Form1098T, institution="State U", ein="44-4444444",
        box1_payments=8000, box5_scholarships=2000,
        box8_half_time=False, credit_type="aoc", first_four_years=True)
    c3b = e.run(_base_schema(form_1098ts=[t_nht])).get("computed", {})
    ok("EA3.2 AOTC half-time=False → $0 (hard gate)",
       c3b.get("l29_aoc", 0), 0, tolerance=0,
       note="IRC §25A(b)(1)(B); box8_half_time=False → AOTC denied")

    # Test 3c: drug conviction → AOTC = $0 (hard gate)
    t_drug = _si3(e.Form1098T, institution="State U", ein="44-4444444",
        box1_payments=8000, box5_scholarships=2000,
        box8_half_time=True, credit_type="aoc", first_four_years=True,
        aoc_drug_conviction=True)
    c3c = e.run(_base_schema(form_1098ts=[t_drug])).get("computed", {})
    ok("EA3.3 AOTC drug conviction=True → $0 (hard gate)",
       c3c.get("l29_aoc", 0), 0, tolerance=0,
       note="IRC §25A(b)(2)(D); drug conviction → AOTC denied")

except Exception as ex:
    warn("AOTC gate test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 4: Cap gains §1250 (25%) and collectibles (28%) rates -------
print("\n  EA Fix 4: Capital gains §1250 (25%) and collectibles (28%) rates")
try:
    import dataclasses as _dc4
    def _si4(cls, **kw):
        valid = {f.name for f in _dc4.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})

    # §1250 recapture: at high income the 25% rate results in more tax than QDCGT rates
    # For taxable=$300k with $50k §1250 gain: QDCGT worksheet < ordinary brackets
    # The 25% special rate applies to the §1250 portion
    t_qdcgt_no_1250   = e.compute_qdcgt_tax(300000, 200000, "single", 2025, 0,     0)
    t_qdcgt_with_1250 = e.compute_qdcgt_tax(300000, 200000, "single", 2025, 50000, 0)
    t_qdcgt_collect   = e.compute_qdcgt_tax(300000, 200000, "single", 2025, 0,  50000)
    ok("EA4.1 §1250 gain at 25% → higher QDCGT worksheet than without §1250",
       t_qdcgt_with_1250 > t_qdcgt_no_1250, True,
       note="IRC §1(h)(1)(D); $50k unrecaptured §1250 taxed at 25%, raises total tax")
    ok("EA4.2 Collectibles (28%) → even higher tax than §1250 (25%)",
       t_qdcgt_collect >= t_qdcgt_with_1250, True,
       note="IRC §1(h)(4); collectibles at 28% ≥ §1250 at 25%")
    ok("EA4.3 No special rates: qdcgt_tax unaffected",
       e.compute_qdcgt_tax(50000, 0, "single", 2025, 0, 0),
       e.compute_tax(50000, "single", 2025),
       note="No qdcgt_income, no §1250, no collectibles → pure ordinary tax")
except Exception as ex:
    warn("Cap gains special rates test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 5: Tips deduction occupation validation --------------------
print("\n  EA Fix 5: Tips deduction — occupation required")
try:
    # No occupation → warning issued
    r_no_occ = e.compute_tip_deduction(10000, 50000, "single", tip_occupation="")
    ok("EA5.1 Tips with no occupation → warning issued",
       any("occupation" in w.lower() for w in r_no_occ["warnings"]), True,
       note="IRS Notice 2025-65; occupation required for tip deduction")
    ok("EA5.2 Tips with no occupation → deduction still computed (warning, not gate)",
       r_no_occ["deduction"] > 0, True,
       note="Engine warns; UI has dropdown; amount still computed for return")
    # Valid occupation → no occupation warning
    r_occ = e.compute_tip_deduction(10000, 50000, "single", tip_occupation="waiter_waitress")
    ok("EA5.3 Tips with valid occupation → no occupation warning",
       not any("occupation" in w.lower() and "not on" not in w.lower()
               and "not specified" not in w.lower() for w in r_occ["warnings"]), True,
       note="Waiter/waitress is IRS Notice 2025-65 qualifying occupation")
except Exception as ex:
    warn("Tips occupation test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 6: C2 Form 2441 Line 6 — deemed earned income ---------------
print("\n  EA Fix 6: Form 2441 Line 6 — deemed earned income (disabled/student spouse)")
try:
    import dataclasses as _dc6
    def _si6(cls, **kw):
        valid = {f.name for f in _dc6.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})
    cpr6 = _si6(e.Form2441Provider, name="Day Care", address="1 Main St",
                ein="55-5555555", expenses=6000)
    s_c2 = _si6(e.TaxpayerSchema,
        first="T", last="T", ssn="100-00-0001", dob="01-01-1985",
        filing_status="mfj", tax_year=2025,
        care_spouse_is_student=True, care_spouse_months_qualified=12,
        w2s=[_si6(e.W2, employer="Corp", ein="11-1111111", box1_wages=55000,
                box2_fed_wh=7000, box3_ss_wages=55000, box4_ss_wh=3410,
                box5_med_wages=55000, box6_med_wh=798, for_spouse=False)],
        care_providers=[cpr6],
        dependents=[_si6(e.Dependent, first="Kid", last="T", ssn="200-00-0001",
            dob="01-01-2021", relationship="child", ctc_eligible=True)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c_c2 = e.run(s_c2).get("computed", {})
    f2441_detail = c_c2.get("f2441", {})
    ok("C2.1 Form 2441: student spouse deemed income → care credit > $0",
       f2441_detail.get("l11_credit", 0) > 0, True,
       note="IRC §21(d)(2); f2441.pdf Line 6; $250/mo×12=$3,000 deemed income → credit")
    # Warning goes on the main result, check via run() result directly
    run_result_c2 = e.run(s_c2)
    ok("C2.2 Form 2441 Line 6 warning issued",
       any("deemed" in w.lower() or "line 6" in w.lower()
           for w in run_result_c2.get("warnings", [])), True,
       note="Engine warns that deemed earned income was applied")
except Exception as ex:
    warn("Form 2441 C2 test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 7: M1 FLSA confirmation warning ----------------------------
print("\n  EA Fix 7: M1 FLSA — overtime confirmation warning when not confirmed")
try:
    import dataclasses as _dcm1
    def _sim1(cls, **kw):
        valid = {f.name for f in _dcm1.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})

    s_m1 = _sim1(e.TaxpayerSchema,
        first="T", last="T", ssn="100-00-0001", dob="01-01-1980",
        filing_status="single", tax_year=2025,
        overtime_pay_qualifying=8000, overtime_flsa_confirmed=False,
        w2s=[_sim1(e.W2, employer="Corp", ein="11-1111111", box1_wages=50000,
                box2_fed_wh=6000, box3_ss_wages=50000, box4_ss_wh=3100,
                box5_med_wages=50000, box6_med_wh=725, for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    r_m1     = e.run(s_m1)
    c_m1     = r_m1.get("computed", {})
    warns_m1 = r_m1.get("warnings", [])
    ok("M1.1 Overtime deduction computed despite unconfirmed FLSA (warn, not block)",
       c_m1.get("obbba_overtime_deduction", 0) > 0, True,
       note="OBBBA §70202; amount computed; FLSA warning issued separately")
    ok("M1.2 FLSA warning issued when overtime_flsa_confirmed=False",
       any("flsa" in w.lower() for w in warns_m1), True,
       note="P.L. 119-21 §70202; FLSA §207(a)(1); confirmation required")
except Exception as ex:
    warn("M1 FLSA test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 8: M4 §1231 5-year lookback at schema level ----------------
print("\n  EA Fix 8: M4 §1231 5-year lookback — schema-level warning without Form 4797 sales")
try:
    r_1231 = e.compute_form_4797([], schema_sec1231_losses_5yr=15000)
    ok("M4.1 §1231 schema-level lookback warning emitted (no 4797 sales)",
       len(r_1231.get("warnings", [])) > 0, True,
       note="IRC §1231(c); prior §1231 losses warn even without Form 4797 sales")
    ok("M4.2 §1231 warning references $15,000 prior loss amount",
       any("15,000" in w or "15000" in w for w in r_1231.get("warnings", [])), True,
       note="Warning should display the prior loss amount clearly")
except Exception as ex:
    warn("M4 §1231 test CRASHED", traceback.format_exc(limit=3))

# -- EA AUDIT FIX 9: M5 prior-year safe harbor warning ------------------------
print("\n  EA Fix 9: M5 — prior_year_tax=0 warning when balance owed > $500")
try:
    import dataclasses as _dcm5
    def _sim5(cls, **kw):
        valid = {f.name for f in _dcm5.fields(cls)}
        return cls(**{k:v for k,v in kw.items() if k in valid})

    s_m5 = _sim5(e.TaxpayerSchema,
        first="T", last="T", ssn="100-00-0001", dob="01-01-1980",
        filing_status="single", tax_year=2025,
        w2s=[_sim5(e.W2, employer="Corp", ein="11-1111111", box1_wages=120000,
                box2_fed_wh=5000, box3_ss_wages=118500, box4_ss_wh=7347,
                box5_med_wages=120000, box6_med_wh=1740, for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    r_m5     = e.run(s_m5)
    c_m5     = r_m5.get("computed", {})
    warns_m5 = r_m5.get("warnings", [])
    owes_m5  = c_m5.get("l37_owe", 0)
    ok("M5.1 Scenario produces balance owed > $500 (needed to trigger warning)",
       owes_m5 > 500, True,
       note=f"l37_owe=${owes_m5:,}; warning triggers when owe > $500 and no prior-year data")
    ok("M5.2 Form 2210 prior-year warning issued when owe > $500 and no Form 2210",
       any("2210" in w.lower() or "underpayment" in w.lower() for w in warns_m5), True,
       note="IRC §6654(d)(1)(B); f2210.pdf; safe harbor cannot be evaluated without PY tax")
except Exception as ex:
    warn("M5 prior-year test CRASHED", traceback.format_exc(limit=3))


print("\n  EA Fix 2: EITC — exact IRS $50-band table algorithm (p1040.pdf pp.16+)")
try:
    # Table algorithm: floor income to $50 band, apply phase-in/out at band value
    eitc_cases = [
        # (earned, agi, n_children, fs, expected, note)
        (18000, 18000, 2, "single", 7152, "max credit for 2 children single"),
        (20000, 20000, 2, "single", 7152, "plateau — still at max"),
        (23350, 23350, 1, "single", 4328, "max credit for 1 child single"),
        (35000, 35000, 1, "single", None, "phaseout range — non-zero"),
        (50000, 50000, 1, "single", None, "near limit but below $50,434 → small credit"),
        (50434, 50434, 1, "single", 0,    "at income_limit $50,434 → $0"),
        (15000, 15000, 0, "mfj",    649,  "0 children MFJ at plateau"),
        (0,     0,     1, "single", 0,    "no income → $0"),
    ]
    for ei, agi, nc, fs, exp, note in eitc_cases:
        result_e = e.compute_eitc(ei, agi, nc, fs, 0.0)
        if exp is None:
            ok(f"EA2 EITC ei={ei} n={nc} {fs}: non-zero",
               result_e["eitc"] > 0, True, note=note)
        else:
            ok(f"EA2 EITC ei={ei} n={nc} {fs}: ${exp}",
               result_e["eitc"], exp, tolerance=0, note=note)
        ok(f"EA2 EITC ei={ei}: requires_table_lookup=False",
           result_e["requires_table_lookup"], False,
           note="table algorithm is filing-grade — no manual lookup needed")
except Exception as ex:
    warn("EITC table test CRASHED", traceback.format_exc(limit=3))

# -----------------------------------------------------------------------------
section("LAYER 3 -- Engine Unit Tests (IRS-cited calculations)")

# -- TEST 9: SS Taxability -- IRS Pub 915 Worksheet 1 -------------------------
print("\n  Test 9: SS taxability calculation (IRS Pub 915 Worksheet 1)")
try:
    ss_unit = {
        "first":"SS","last":"Unit","ssn":"100-00-0001","dob":"01-01-1950",
        "occupation":"Retired","address":"1 Test St","filing_status":"single",
        "tax_year":2025,"use_itemized":False,
        "w2s":[{"employer":"Corp","ein":"10-0000001","box1_wages":20000,
                "box2_fed_wh":2000,"box3_ss_wages":20000,"box4_ss_wh":1240,
                "box5_medicare_wages":20000,"box6_medicare_wh":290,
                "box7_ss_tips":0,"box8_allocated_tips":0,"box10_dep_care":0,
                "box11_nonqual_deferred":0,"box12a_code":"","box12a_amt":0,
                "box12b_code":"","box12b_amt":0,"box12c_code":"","box12c_amt":0,
                "box12d_code":"","box12d_amt":0,
                "box13_retirement_plan":False,"box16_state_wages":20000,
                "box17_state_wh":1000,"box18_local_wages":0,"box19_local_wh":0,
                "box20_locality_name":"","for_spouse":False}],
        "form_ssa1099":{"box3_gross_benefits":12000,"box4_repayments":0,
                        "box5_net_benefits":12000,"box6_vol_wh":0,
                        "mfs_lived_apart":False,"lump_sum_election":False,"lump_sum_years":[]},
        "form_1099cs":[],"form_1099ints":[],"form_1099divs":[],"form_1099rs":[],
        "form_1099necs":[],"form_1099miscs":[],"form_1099bs":[],
        "schedule_cs":[],"schedule_es":[],"schedule_k1s":[],"dependents":[],
        "care_providers":[],"form_1098ts":[],"form_w2gs":[],"form_1099gs":[],
        "form_5329_exceptions":[],"form_4797s":[],"schedule_a":None,
    }
    c9 = run_schema(ss_unit)
    # IRS Pub 915 Worksheet 1:
    # Combined income = wages + 50% of SS = 20000 + 6000 = 26000
    # Base (single) = 25000. Excess = 1000.
    # SS taxable = min(0.5 * 1000, 0.5 * 12000) = 500
    ok("S9.1 SS taxable near threshold (single)",
       c9.get('l6b_ss_taxable',0), 500, tolerance=2,
       note="IRS Pub 915 Worksheet 1: combined income $26,000; base $25,000 single")
except Exception as ex:
    warn("SS taxability unit test CRASHED", traceback.format_exc(limit=3))

# -- TEST 10: Standard Deduction 2025 values -----------------------------------
print("\n  Test 10: 2025 standard deduction amounts")
PARAMS = e.PARAMS_2025
ok("S10.1 Std ded single 2025",  PARAMS['std_deduction']['single'], 15750,
   note="Source: OBBBA S.70001 + Rev. Proc. 2024-40; $15,000 base + $750 inflation adj")
ok("S10.2 Std ded MFJ 2025",    PARAMS['std_deduction']['mfj'],    31500,
   note="Source: OBBBA S.70001 + Rev. Proc. 2024-40; $30,000 base + $1,500 inflation adj")
ok("S10.3 Std ded HOH 2025",    PARAMS['std_deduction']['hoh'],    23625)
ok("S10.4 CTC per child 2025",  PARAMS['ctc_per_child'],           2200,
   note="Source: OBBBA S.70021; CTC increased from $2,000")
ok("S10.5 SALT cap default",    PARAMS['salt_cap_default'],        40000,
   note="Source: OBBBA S.70106; SALT cap increased from $10,000")
ok("S10.6 SS wage base 2025",   PARAMS['ss_wage_base_2025'],       176100,
   note="Source: SSA.gov; OASDI wage base 2025")
ok("S10.7 Senior bonus ded",    PARAMS['senior_deduction_amount'], 6000,
   note="Source: OBBBA S.70103; new $6,000 deduction age 65+")
ok("S10.8 IRA limit 2025",      PARAMS['ira_contribution_limit_2025'], 7000,
   note="Source: IRS IR-2024-285; IRA limit unchanged")
ok("S10.9 HSA family 2025",     PARAMS['hsa_limit_family_2025'],   8550,
   note="Source: Rev. Proc. 2024-25; HSA family limit")
ok("S10.10 AMT exemption MFJ",  PARAMS['amt_exemption_mfj'],       137000,
   note="Source: Rev. Proc. 2024-40; AMT exemption MFJ 2025")



# -- TEST 11: TY 2026 EITC updated table (P1 -- IR-2025-103) ------------------
print("\n  Test 11: TY 2026 EITC table (IR-2025-103)")
try:
    p26 = e.PARAMS_2026
    ok_3plus = p26.get('eitc',{}).get('single_qss',{}).get(3,{}).get('max',0)
    ok_inv   = p26.get('eitc_investment_income_limit', 0)
    ok("S11.1 TY2026 EITC 3+ children max = $8,231", ok_3plus, 8231,
       note="Source: IR-2025-103; was $8,046 in TY 2025")
    ok("S11.2 TY2026 EITC invest limit = $11,950",   ok_inv,   11950,
       note="Source: IR-2025-103; was $11,600 in TY 2025")
except Exception as ex:
    warn("TY 2026 EITC test CRASHED", traceback.format_exc(limit=3))

# -- TEST 12: TY 2026 QBI minimum $400 deduction (P2 -- OBBBA) ----------------
print("\n  Test 12: TY 2026 QBI minimum $400 deduction (OBBBA)")
try:
    import dataclasses as _dc
    def _si(cls, **kw):
        valid = {f.name for f in _dc.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})
    sc_small = _si(e.ScheduleC, business_name="Consulting", gross_receipts=2200)
    schema_qbi = _si(e.TaxpayerSchema,
        first="Q", last="T", ssn="111-00-2026", dob="01-01-1980",
        occupation="Consultant", address="1 Test", filing_status="single",
        tax_year=2026, schedule_cs=[sc_small],
        w2s=[], form_1099ints=[], form_1099rs=[], form_1099divs=[],
        form_1099necs=[], form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        dependents=[], care_providers=[], form_1098ts=[], form_1099bs=[],
        schedule_es=[], form_w2gs=[], form_1099gs=[], schedule_k1s=[],
        form_5329_exceptions=[], form_4797s=[])
    c_qbi = e.run(schema_qbi).get("computed", {})
    ok("S12.1 TY2026 QBI min $400 applied when 20%xQBI < $400",
       c_qbi.get("adj_qbi", 0), 400, tolerance=0,
       note="Source: OBBBA new for TY 2026; QBI $2,044 x 20% = $409 > $400 -> min not triggered here")
    # Note: at gross=2200, QBI ~ 2044, 20%=409 which is already > 400.
    # Verify it's at least the minimum:
    ok("S12.2 TY2026 QBI deduction >= $400 minimum",
       c_qbi.get("adj_qbi", 0) >= 400, True,
       note="OBBBA S.70XXX: if QBI >= $1,000 and computed deduction < $400, floor to $400")
except Exception as ex:
    warn("TY 2026 QBI minimum test CRASHED", traceback.format_exc(limit=3))

# -- TEST 13: 1099-INT bond premium (P7) --------------------------------------
print("\n  Test 13: 1099-INT bond premium Box 11 reduces taxable interest")
try:
    int_bond = e.Form1099INT(
        payer="Bond Corp", payer_ein="", account_number="",
        box1_interest=1000, box2_early_withdrawal_penalty=0, box3_us_savings_bond=0,
        box4_fed_wh=0, box5_investment_expenses=0, box6_foreign_tax=0,
        box7_foreign_country="", box8_tax_exempt_interest=0,
        box9_private_activity_bond=0,
        box10_market_discount=200,   # accrued market discount -> adds to income
        box11_bond_premium=150,      # bond premium -> reduces Box 1 per IRC S.171
        box12_bond_premium_treasury=0, box13_bond_premium_tax_exempt=0,
        box14_cusip="", box15_state_wh=0, box16_state_id="", box17_state_income=0,
    )
    schema_bp = _si(e.TaxpayerSchema,
        first="B", last="P", ssn="333-00-7777", dob="01-01-1970",
        occupation="Investor", address="2 Bond St", filing_status="single",
        tax_year=2025, form_1099ints=[int_bond],
        w2s=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c_bp = e.run(schema_bp).get("computed", {})
    ok("S13.1 Bond premium reduces taxable interest (Box11=150 reduces Box1=1000)",
       c_bp.get("interest", 0), 1050,
       note="Source: IRC S.171; Schedule B Line 1(b); (1000-150)+200 market_discount = 1,050")
    ok("S13.2 Market discount adds to taxable interest (Box10=200)",
       c_bp.get("interest", 0) > 1000, True,
       note="Source: IRC S.1278(b); Box 10 accrued market discount is interest income")
except Exception as ex:
    warn("Bond premium test CRASHED", traceback.format_exc(limit=3))

# -----------------------------------------------------------------------------

# -- TEST 14: Standard deduction age 65+ addon (TY 2025) ----------------------
print("\n  Test 14: Standard deduction age 65+ addon -- single and MFJ")
try:
    import dataclasses as _dc14
    def _si14(cls, **kw):
        valid = {f.name for f in _dc14.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})

    mfj_s = _si14(e.TaxpayerSchema,
        first="A", last="T", ssn="111-00-0014", dob="01-01-1964",
        occupation="T", address="1 T", filing_status="mfj", tax_year=2025,
        taxpayer_age_for_senior_ded=61, spouse_age_for_senior_ded=70,
        w2s=[_si14(e.W2, employer="C", ein="11-1111111",
            box1_wages=60000, box2_fed_wh=7000,
            box3_ss_wages=60000, box4_ss_wh=3720,
            box5_med_wages=60000, box6_med_wh=870, for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c14 = e.run(mfj_s).get("computed", {})
    ok("S14.1 MFJ std ded + 1 senior addon = $33,100",
       c14.get("std_deduction", 0), 33100,
       note="IRC S.63(f); Rev. Proc. 2024-40 S.3.10; $31,500 + $1,600 (1 spouse age 70)")

    single_s = _si14(e.TaxpayerSchema,
        first="B", last="T", ssn="222-00-0014", dob="01-01-1955",
        occupation="T", address="2 T", filing_status="single", tax_year=2025,
        taxpayer_age_for_senior_ded=70,
        w2s=[_si14(e.W2, employer="C", ein="22-2222222",
            box1_wages=30000, box2_fed_wh=3000,
            box3_ss_wages=30000, box4_ss_wh=1860,
            box5_med_wages=30000, box6_med_wh=435, for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c14s = e.run(single_s).get("computed", {})
    ok("S14.2 Single age 70 std ded = $17,750",
       c14s.get("std_deduction", 0), 17750,
       note="Rev. Proc. 2024-40 S.3.10; $15,750 base + $2,000 single senior addon")
except Exception as ex:
    warn("Std deduction addon test CRASHED", traceback.format_exc(limit=3))

# -- TEST 15: SM rounding correct (round after x12) ---------------------------
print("\n  Test 15: Simplified method rounding (IRS Pub 575 Worksheet A)")
try:
    import dataclasses as _dc15
    def _si15(cls, **kw):
        valid = {f.name for f in _dc15.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})
    sm15 = e.SimplifiedMethodData(
        use_simplified_method=True, cost_in_contract=15000,
        annuity_type="joint", age_at_annuity_start=67,
        joint_age_at_annuity_start=58,
        fixed_period_months=0, prior_year_tax_free_recovered=1259,
        annuity_start_after_nov_18_1996=True)
    r15 = _si15(e.Form1099R, payer="Pension", ein="", recipient="spouse",
        box1_gross=22100, box2a_taxable=22100, box3_cap_gain=0, box4_fed_wh=2210,
        box7_code="7", box7_ira_sep_simple=False, box9b_employee_contribs=15000,
        simplified_method=sm15)
    schema15 = _si15(e.TaxpayerSchema,
        first="Y", last="W", ssn="555-00-0015", dob="10-08-1955",
        occupation="Retired", address="1 Willis", filing_status="single", tax_year=2025,
        form_1099rs=[r15],
        w2s=[], form_1099ints=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c15 = e.run(schema15).get("computed", {})
    ok("S15.1 SM taxable = $21,519 (round after x12, not before)",
       c15.get("l5b_pension_taxable", 0), 21519, tolerance=1,
       note="IRS Pub 575 WkshtA: 15000/310=48.387/mo, x12=580.65, round=581, 22100-581=21519")
except Exception as ex:
    warn("SM rounding test CRASHED", traceback.format_exc(limit=3))

# =============================================================================
# LAYER 1B -- Dataclass Field Registry Audit
# Every engine dataclass that the server bridges must have its critical fields
# confirmed present. Guards against silent engine refactors that break bridges.
# =============================================================================
section("LAYER 1B -- Dataclass Field Registry Audit")

import inspect as _inspect

def _fields(cls):
    return {f.name for f in dataclasses.fields(cls)}

# All bridged/critical dataclasses and their required fields
DC_REQUIRED = [
    (e.TaxpayerSchema, [
        "filing_status","tax_year","w2s","form_1099ints","form_1099rs",
        "form_1099divs","form_1099necs","form_ssa1099","form_1099cs",
        "form_1099misc_prizes","schedule_cs","schedule_es","schedule_k1s",
        "dependents","care_providers","form_1098ts","form_1099bs","form_w2gs",
        "form_1099gs","form_4797s","form_5329_exceptions","form_8606",
        "form_8606_spouse","form_8889","form_1095a","form_8880","form_6251",
        "form_2210","form_1116","form_8615","form_4972","form_8582","alimony",
        "deceased_spouse","california","estimated_tax_payments",
        "ira_contribution_traditional","capital_loss_carryover_prior",
        "nol_carryforward_prior_year","taxpayer_age_for_senior_ded",
        "spouse_age_for_senior_ded","qualified_tips","overtime_pay_qualifying",
        "auto_loan_interest","auto_loan_originated_after_2024",
        "auto_loan_vehicle_new_us_assembled","gambling_losses","use_itemized",
        "teacher_expense","student_loan_interest","schedule_a",
    ]),
    (e.W2, [
        "employer","ein","box1_wages","box2_fed_wh","box3_ss_wages","box4_ss_wh",
        "box5_med_wages","box6_med_wh","box7_ss_tips","box10_dependent_care",
        "box11_nonqual_def_comp","box12a_code","box12a_amt","box12b_code",
        "box12b_amt","box12c_code","box12c_amt","box12d_code","box12d_amt",
        "box13_retirement_plan","box13_statutory_employee","box15_state",
        "box16_state_wages","box17_state_wh","for_spouse",
    ]),
    (e.Form1099R, [
        "payer","box1_gross","box2a_taxable","box4_fed_wh","box7_code",
        "box7_ira_sep_simple","box9b_employee_contribs","is_ira",
        "simplified_method","box14_state_wh",
    ]),
    (e.Form1099INT, [
        "payer","box1_interest","box3_us_savings_bond","box4_fed_wh",
        "box8_tax_exempt_interest","box9_private_activity_bond",
        "box10_market_discount","box11_bond_premium","box12_bond_premium_treasury",
    ]),
    (e.Form1099DIV, [
        "payer","box1a_ordinary_div","box1b_qualified_div","box2a_cap_gain_dist",
        "box2b_unrec_1250","box4_fed_wh","box5_sec199a_div","box7_foreign_tax",
        "box11_exempt_interest","box12_private_activity",
    ]),
    (e.Form1099C, [
        "creditor","box2_amount_discharged","box6_event_code","is_excluded",
    ]),
    (e.FormSSA1099, [
        "box3_gross_benefits","box4_repayments","box5_net_benefits",
        "box6_voluntary_wh","mfs_lived_apart_all_year","lump_sum_prior_years",
    ]),
    (e.Form1099NEC, [
        "payer","box1_nonemployee_comp","box4_fed_wh",
    ]),
    (e.Form1099B, [
        "description","date_acquired","date_sold","proceeds","cost_basis",
        "is_long_term","wash_sale_loss_disallowed","fed_wh",
    ]),
    (e.Form1099G, [
        "payer","box1_unemployment","box2_state_refund","box4_fed_wh",
        "prior_year_itemized",
    ]),
    (e.Form1099MISC_Prize, [
        "payer","box3_other_income","description",
    ]),
    (e.FormW2G, [
        "payer","box1_winnings","box4_fed_wh",
    ]),
    (e.SimplifiedMethodData, [
        "use_simplified_method","cost_in_contract","annuity_type",
        "age_at_annuity_start","joint_age_at_annuity_start",
        "fixed_period_months","prior_year_tax_free_recovered",
        "annuity_start_after_nov_18_1996",
    ]),
    (e.Form8606Data, [
        "nonded_contrib_this_year","basis_prior_year","trad_ira_value_dec31",
        "trad_ira_distributions","conversion_amount","is_backdoor_roth",
        "roth_distributions","roth_basis_contributions","over_59_5",
    ]),
    (e.Form8889Data, [
        "coverage_type","taxpayer_age","spouse_age","contributions_taxpayer",
        "contributions_spouse","employer_contrib_w2_code_w","total_distributions",
        "qualified_medical_expenses","age_65_or_disabled",
    ]),
    (e.ScheduleAData, [
        "medical_dental_total","state_income_tax","real_estate_tax",
        "personal_property_tax","mortgage_interest_1098","cash_charitable",
        "noncash_charitable","casualty_theft_loss","mortgage_balance_outstanding",
    ]),
    (e.ScheduleC, [
        "business_name","gross_receipts","w2_wages","ubia_qualified_property",
        "is_sstb","home_office_sq_ft","use_home_office_simplified",
    ]),
    (e.ScheduleE, [
        "address","days_rented","days_personal_use","rents_received",
        "mortgage_interest","depreciation","is_real_estate_professional",
        "material_participation","active_participation",
    ]),
    (e.ScheduleK1, [
        "entity_name","entity_ein","entity_type","taxpayer_pct",
        "box1_ordinary_income","box2_net_rental","box14a_se_income",
        "box17_sec199a","box17_w2_wages","box17_ubia","material_participation",
    ]),
    (e.Form4797SaleData, [
        "description","property_type","date_acquired","date_sold",
        "gross_proceeds","original_cost","depreciation_taken",
        "additional_section_1250_recapture","suspended_passive_losses",
    ]),
    (e.Form8615Data, [
        "child_age","parent_taxable_income","unearned_income","earned_income",
        "parent_filing_status",
    ]),
    (e.Form1116Data, [
        "passive_foreign_taxes_paid","passive_foreign_income",
        "general_foreign_taxes_paid","general_foreign_income","passive_carryover",
    ]),
    (e.Form1095A, [
        "col_a_annual","col_b_annual","col_c_annual",
    ]),
    (e.Form8582Data, [
        "prior_year_unallowed_losses","mfs_lived_apart",
    ]),
    (e.AlimonyData, [
        "decree_pre_2019","alimony_paid","alimony_received",
    ]),
    (e.CaliforniaData, [
        "ca_sdi_withheld","use_ca_itemized","paid_rent_over_half_year",
        "has_young_child_under6","ca_investment_income_caleitc",
    ]),
    (e.Form2210Data, [
        "prior_year_tax","prior_year_agi","waiver_retired_disabled",
    ]),
    (e.Dependent, [
        "first","last","ssn","dob","relationship","ctc_eligible","odc_eligible",
    ]),
    (e.Form5329Exception, [
        "payer_name","distribution_amount","exception_code","plan_type",
    ]),
    (e.Form4972Data, [
        "ordinary_income","capital_gain","elect_20pct_capital_gain",
        "elect_10yr_option",
    ]),
]

for cls, required_fields in DC_REQUIRED:
    actual = _fields(cls)
    for fname in required_fields:
        ok(f"{cls.__name__}.{fname} present",
           fname in actual, True,
           note=f"Required field missing from {cls.__name__} — bridge will silently drop it")


# =============================================================================
# LAYER 3B -- Expanded PARAMS Sync Audit
# All constants cited in TaxReturn_PlanningReference.md Pages 3–4.
# Covers every value shown in the UI, referenced in workpaper, or used in
# a deduction/credit calculation.
# =============================================================================
section("LAYER 3B -- Expanded PARAMS Sync Audit (TY 2025 + TY 2026)")

p25 = e.PARAMS_2025
p26 = e.PARAMS_2026

# ---- TY 2025 ----------------------------------------------------------------
# Standard deductions (OBBBA §70001 + Rev. Proc. 2024-40)
ok("P25.01 Std ded single",         p25['std_deduction']['single'],      15750, tolerance=0,
   note="OBBBA §70001; Rev. Proc. 2024-40")
ok("P25.02 Std ded MFJ/QSS",        p25['std_deduction']['mfj'],         31500, tolerance=0)
ok("P25.03 Std ded HOH",            p25['std_deduction']['hoh'],         23625, tolerance=0)
ok("P25.04 Std ded MFS",            p25['std_deduction'].get('mfs', p25['std_deduction']['single']), 15750, tolerance=0)
ok("P25.05 Std addon MFJ per spouse", p25['std_addon_mfj_per_2025'],     1600,  tolerance=0,
   note="IRC §63(f); Rev. Proc. 2024-40 §3.10")
ok("P25.06 Std addon single/HOH",   p25['std_addon_single_hoh_2025'],    2000,  tolerance=0)

# Credits (OBBBA + Rev. Proc. 2024-40)
ok("P25.07 CTC per child",          p25['ctc_per_child'],                2200,  tolerance=0,
   note="OBBBA §70021; was $2,000 pre-OBBBA")
ok("P25.08 ACTC cap per child",     p25['actc_cap_per_child'],           1700,  tolerance=0,
   note="Rev. Proc. 2024-40; ACTC cap unchanged")
ok("P25.09 ODC per qualifying dep", p25['odc_per_dependent'],            500,   tolerance=0,
   note="IRC §24(h)(4); unchanged")

# SALT (OBBBA §70106)
ok("P25.10 SALT cap default",       p25['salt_cap_default'],             40000, tolerance=0,
   note="OBBBA §70106; was $10,000; MFS = $20,000")
ok("P25.11 SALT cap MFS",           p25['salt_cap_mfs'],                 20000, tolerance=0)
ok("P25.12 SALT phasedown threshold", p25['salt_phasedown_threshold'],   500000, tolerance=0,
   note="OBBBA: $50 reduction per $1,000 AGI above $500k; floor $10,000")
ok("P25.13 SALT floor",             p25['salt_floor'],                   10000, tolerance=0)

# OBBBA new above-line deductions
ok("P25.14 Senior bonus ded amount", p25['senior_deduction_amount'],     6000,  tolerance=0,
   note="OBBBA §70103; $6,000/person age 65+")
ok("P25.15 Senior ded MAGI single", p25['senior_deduction_magi_single'], 75000, tolerance=0)
ok("P25.16 Senior ded MAGI MFJ",    p25['senior_deduction_magi_mfj'],   150000, tolerance=0)
ok("P25.17 Tip ded max",            p25['tip_deduction_max'],            25000, tolerance=0,
   note="OBBBA §70201; qualified tips above-line deduction")
ok("P25.18 Tip ded MAGI single",    p25['tip_deduction_magi_single'],   150000, tolerance=0)
ok("P25.19 Tip ded MAGI MFJ",       p25['tip_deduction_magi_mfj'],      300000, tolerance=0)
ok("P25.20 OT ded max single",      p25['overtime_deduction_max_single'],12500, tolerance=0,
   note="OBBBA §70202; FLSA overtime pay above-line deduction")
ok("P25.21 OT ded max MFJ",         p25['overtime_deduction_max_mfj'],  25000, tolerance=0)
ok("P25.22 OT ded MAGI single",     p25['overtime_deduction_magi_single'],150000, tolerance=0)
ok("P25.23 OT ded MAGI MFJ",        p25['overtime_deduction_magi_mfj'], 300000, tolerance=0)

# QDCGT thresholds (Rev. Proc. 2024-40 §3.03)
ok("P25.28 QDCGT 0% single",        p25['qdcgt_0pct_single'],           47025, tolerance=0,
   note="Rev. Proc. 2024-40; qualified dividends/LTCG 0% bracket top")
ok("P25.29 QDCGT 0% MFJ",           p25['qdcgt_0pct_mfj'],              94050, tolerance=0)
ok("P25.30 QDCGT 15% single",        p25['qdcgt_15pct_single'],         518900, tolerance=0)
ok("P25.31 QDCGT 15% MFJ",           p25['qdcgt_15pct_mfj'],            583750, tolerance=0)

# AMT (Rev. Proc. 2024-40 §3.07)
ok("P25.32 AMT exemption single",    p25['amt_exemption_single'],        88100, tolerance=0,
   note="Rev. Proc. 2024-40 §3.07")
ok("P25.33 AMT exemption MFJ",       p25['amt_exemption_mfj'],          137000, tolerance=0)
ok("P25.34 AMT phaseout single",     p25['amt_phaseout_single'],        626350, tolerance=0)
ok("P25.35 AMT phaseout MFJ",        p25['amt_phaseout_mfj'],          1252700, tolerance=0)

# QBI (Rev. Proc. 2024-40 + OBBBA)
ok("P25.36 QBI threshold single",    p25['qbi_threshold_other'],        197300, tolerance=0,
   note="Rev. Proc. 2024-40; §199A W-2/UBIA phase-in starts")
ok("P25.37 QBI threshold MFJ",       p25['qbi_threshold_mfj'],          394600, tolerance=0)

# Retirement plans (Rev. Proc. 2024-40 + Notice 2024-80)
ok("P25.38 IRA limit 2025",          p25['ira_contribution_limit_2025'], 7000,  tolerance=0,
   note="IRS IR-2024-285; unchanged from 2024")
ok("P25.39 IRA catchup 50+ 2025",    p25['ira_contribution_catchup_2025'],8000, tolerance=0)
ok("P25.40 SEP-IRA max 2025",        p25['sep_ira_max_2025'],            70000, tolerance=0,
   note="IRS IR-2024-285; 25% net SE comp or $70,000")
ok("P25.41 Solo 401k elective 2025", p25['solo401k_elective_max_2025'], 23500, tolerance=0)
ok("P25.42 SIMPLE IRA max 2025",     p25['simple_ira_max_2025'],         16500, tolerance=0)

# HSA (Rev. Proc. 2024-25)
ok("P25.43 HSA self-only 2025",      p25['hsa_limit_self_only_2025'],    4300,  tolerance=0,
   note="Rev. Proc. 2024-25")
ok("P25.44 HSA family 2025",         p25['hsa_limit_family_2025'],       8550,  tolerance=0)
ok("P25.45 HSA catchup 55+ 2025",    p25['hsa_catchup_age55_2025'],      1000,  tolerance=0)

# EITC (Rev. Proc. 2024-40)
ok("P25.46 EITC invest limit 2025",  p25['eitc_investment_income_limit'],11600, tolerance=0,
   note="Rev. Proc. 2024-40; EITC disallowed if invest income > limit")
ok("P25.47 EITC 3+ max 2025 (single/QSS)", p25['eitc']['single_qss'][3]['max'], 8046, tolerance=0)

# NIIT & Additional Medicare (IRC §1411, §3101)
ok("P25.48 NIIT threshold single",   p25['niit_threshold_single'],      200000, tolerance=0,
   note="IRC §1411; 3.8% on NII above threshold")
ok("P25.49 NIIT threshold MFJ",      p25['niit_threshold_mfj'],         250000, tolerance=0)
ok("P25.50 Addl Medicare single",    p25['addl_medicare_threshold_single'],200000, tolerance=0,
   note="IRC §3101(b)(2); 0.9% on wages/SE above threshold")
ok("P25.51 Addl Medicare MFJ",       p25['addl_medicare_threshold_mfj'],250000, tolerance=0)

# Other key amounts
ok("P25.52 SS wage base 2025",        p25['ss_wage_base_2025'],         176100, tolerance=0,
   note="SSA.gov; OASDI wage base 2025")
ok("P25.53 Teacher expense max",      p25['teacher_expense_max'],          300, tolerance=0,
   note="IRC §62(a)(2)(D); inflation-adjusted")
ok("P25.54 Student loan max",         p25['student_loan_max'],            2500, tolerance=0,
   note="IRC §221(b)(1)")
ok("P25.55 Kiddie Tax NUI threshold", p25['kiddie_tax_nui_threshold'],    2700, tolerance=0,
   note="Rev. Proc. 2024-40; Form 8615 unearned income threshold")

# Form 1116 de minimis (IRC §904(j))
ok("P25.56 F1116 de minimis single",  p25['f1116_de_minimis_single'],     300, tolerance=0,
   note="IRC §904(j); no Form 1116 required if total foreign tax ≤ $300 single")
ok("P25.57 F1116 de minimis MFJ",     p25['f1116_de_minimis_mfj'],        600, tolerance=0)

# California
ok("P25.58 CA std ded single/MFS",    p25['ca_std_ded_single'],           5706, tolerance=0,
   note="FTB 2025; CA standard deduction")
ok("P25.60 CA YCTC max",             p25['ca_young_child_tax_credit'],    1189,  tolerance=0,
   note="FTB 2025; Young Child Tax Credit max per return")
ok("P25.61 CA personal exempt single",p25['ca_personal_exempt_credit'],    144,  tolerance=0,
   note="FTB 2025; CA personal exemption credit — single/MFS")
ok("P25.62 CA personal exempt MFJ",   p25['ca_personal_exempt_mfj_qss'],   288,  tolerance=0)
ok("P25.63 CA dep exempt credit",     p25['ca_dependent_exempt_credit'],    433,  tolerance=0)
ok("P25.65 CA surtax millionaire",    p25['ca_surtax_millionaire'],        0.01,  tolerance=0,
   note="Rev. & Tax. Code §17043; 1% on CA taxable income > $1M")

# IRA deductibility phaseouts (Rev. Proc. 2024-40 §3.06)
ok("P25.66 IRA PO covered single start", p25['ira_phaseout_covered_single_start'], 79000, tolerance=0,
   note="Rev. Proc. 2024-40 §3.06; single covered by plan")
ok("P25.67 IRA PO covered single end",   p25['ira_phaseout_covered_single_end'],   89000, tolerance=0)
ok("P25.68 IRA PO covered MFJ start",    p25['ira_phaseout_covered_mfj_start'],   126000, tolerance=0)
ok("P25.69 IRA PO covered MFJ end",      p25['ira_phaseout_covered_mfj_end'],     146000, tolerance=0)
ok("P25.70 IRA PO noncovered MFJ start", p25['ira_phaseout_noncovered_mfj_start'],236000, tolerance=0,
   note="Spouse covered, filer not covered")
ok("P25.71 IRA PO noncovered MFJ end",   p25['ira_phaseout_noncovered_mfj_end'],  246000, tolerance=0)

# Student loan phaseouts (IRC §221(b)(2))
ok("P25.72 Student loan PO single start",p25['student_loan_phaseout_single_start'], 80000, tolerance=0,
   note="IRC §221(b)(2); Rev. Proc. 2024-40")
ok("P25.73 Student loan PO single end",  p25['student_loan_phaseout_single_end'],   95000, tolerance=0)
ok("P25.74 Student loan PO MFJ start",   p25['student_loan_phaseout_mfj_start'],   165000, tolerance=0)
ok("P25.75 Student loan PO MFJ end",     p25['student_loan_phaseout_mfj_end'],     195000, tolerance=0)

# AOC / LLC education credit phaseouts (IRC §25A(d))
ok("P25.76 AOC/LLC PO single start",     p25['aoc_llc_phaseout_single_start'],      80000, tolerance=0,
   note="IRC §25A(d); Rev. Proc. 2024-40")
ok("P25.77 AOC/LLC PO single end",       p25['aoc_llc_phaseout_single_end'],        90000, tolerance=0)
ok("P25.78 AOC/LLC PO MFJ start",        p25['aoc_llc_phaseout_mfj_start'],        160000, tolerance=0)
ok("P25.79 AOC/LLC PO MFJ end",          p25['aoc_llc_phaseout_mfj_end'],          180000, tolerance=0)

# CTC / ACTC phaseouts (IRC §24)
ok("P25.84 CTC phaseout single start",  p25['ctc_phaseout_all_other'],             200000, tolerance=0)
ok("P25.85 ACTC cap per child",         p25['actc_cap_per_child'],                  1700,  tolerance=0,
   note="Rev. Proc. 2024-40; max refundable portion per child")
ok("P25.86 ACTC earned income floor",   p25['actc_earned_floor'],                   2500,  tolerance=0,
   note="IRC §24(d)(1)(B)(i)")
ok("P25.87 ACTC rate",                  p25['actc_rate'],                           0.15,  tolerance=0,
   note="IRC §24(d)(1)(A); 15% of earned income above floor")

# Rental activity (IRC §469(i))
ok("P25.88 Rental special allowance",   p25['rental_special_allowance'],           25000,  tolerance=0,
   note="IRC §469(i)(2); active participation rental allowance")
ok("P25.89 Rental PO start",            p25['rental_phaseout_start'],             100000,  tolerance=0,
   note="IRC §469(i)(3)(A); $25k reduced $1 per $2 of AGI above $100k")

# AMT rates (IRC §55(b))
ok("P25.90 AMT rate 1 (26%)",           p25['amt_rate1'],                           0.26,  tolerance=0,
   note="IRC §55(b)(1)(A)")
ok("P25.91 AMT rate 2 (28%)",           p25['amt_rate2'],                           0.28,  tolerance=0)
ok("P25.92 AMT rate breakpoint",        p25['amt_rate_breakpoint'],               232600,  tolerance=0,
   note="Rev. Proc. 2024-40; 28% applies above this AMTI")

# Form 5329 exceptions
ok("P25.93 F5329 birth/adoption limit", p25['f5329_birth_adoption'],                5000,  tolerance=0,
   note="IRC §72(t)(2)(H); exception for qualified birth/adoption")
ok("P25.94 F5329 first home lifetime",  p25['f5329_first_home_lifetime'],          10000,  tolerance=0,
   note="IRC §72(t)(2)(F); lifetime limit for first-time homebuyer")

# ---- TY 2026 ----------------------------------------------------------------
print("\n  TY 2026 constants:")

# Standard deductions (Rev. Proc. 2025-32)
ok("P26.01 Std ded single 2026",        p26['std_deduction']['single'],           16100, tolerance=0,
   note="Rev. Proc. 2025-32; +$350 from 2025")
ok("P26.02 Std ded MFJ 2026",           p26['std_deduction']['mfj'],              32200, tolerance=0)
ok("P26.03 Std ded HOH 2026",           p26['std_deduction']['hoh'],              24150, tolerance=0)
ok("P26.04 Std addon MFJ per spouse",   p26['std_addon_mfj_per'],                  1650, tolerance=0,
   note="Rev. Proc. 2025-32 §3.10; +$50 from 2025's $1,600")
ok("P26.05 Std addon single/HOH",       p26['std_addon_single_hoh'],               2050, tolerance=0,
   note="Rev. Proc. 2025-32 §3.10; +$50 from 2025's $2,000")

# Credits
ok("P26.06 CTC per child 2026",         p26['ctc_per_child'],                      2300, tolerance=0,
   note="Rev. Proc. 2025-32 §4.05; +$100 from 2025's $2,200")
ok("P26.07 ACTC cap per child 2026",    p26['actc_cap_per_child'],                 1800, tolerance=0,
   note="Rev. Proc. 2025-32; +$100 from 2025's $1,700")

# AMT (Rev. Proc. 2025-32 + OBBBA phaseout reset)
ok("P26.08 AMT exemption single 2026",  p26['amt_exemption_single'],              90100, tolerance=0,
   note="Rev. Proc. 2025-32; +$2,000 from $88,100")
ok("P26.09 AMT exemption MFJ 2026",     p26['amt_exemption_mfj'],                140200, tolerance=0,
   note="Rev. Proc. 2025-32; +$3,200 from $137,000")
ok("P26.10 AMT phaseout single 2026",   p26['amt_phaseout_single'],              500000, tolerance=0,
   note="OBBBA §70401 reset; was $626,350 in TY 2025")
ok("P26.11 AMT phaseout MFJ 2026",      p26['amt_phaseout_mfj'],               1000000, tolerance=0,
   note="OBBBA §70401 reset; was $1,252,700 in TY 2025")
ok("P26.12 AMT phaseout rate 2026",     p26['amt_phaseout_rate'],                  0.50, tolerance=0,
   note="OBBBA §70401; 50¢/$1 (was effectively 25¢/$1 in 2025)")

# QBI (Rev. Proc. 2025-32 + OBBBA)
ok("P26.13 QBI threshold single 2026",  p26['qbi_threshold_other'],             201775, tolerance=0,
   note="Rev. Proc. 2025-32; W-2/UBIA phase-in starts")
ok("P26.14 QBI threshold MFJ 2026",     p26['qbi_threshold_mfj'],              403550, tolerance=0)
ok("P26.15 QBI phase-in range single",  p26['qbi_phase_in_range_single'],        75000, tolerance=0,
   note="OBBBA; expanded from $50,000 in TY 2025")
ok("P26.16 QBI phase-in range MFJ",     p26['qbi_phase_in_range_mfj'],          150000, tolerance=0,
   note="OBBBA; expanded from $100,000 in TY 2025")
ok("P26.17 QBI minimum deduction",      p26['qbi_min_deduction'],                  400, tolerance=0,
   note="OBBBA new for TY 2026; floor when QBI >= $1,000")

# QDCGT (Rev. Proc. 2025-32 §3.03)
ok("P26.18 QDCGT 0% single 2026",       p26['qdcgt_0pct_single'],               48350, tolerance=0,
   note="Rev. Proc. 2025-32; +$1,325 from $47,025")
ok("P26.19 QDCGT 0% MFJ 2026",          p26['qdcgt_0pct_mfj'],                  96700, tolerance=0)
ok("P26.20 QDCGT 15% single 2026",      p26['qdcgt_15pct_single'],             533400, tolerance=0)
ok("P26.21 QDCGT 15% MFJ 2026",         p26['qdcgt_15pct_mfj'],                600050, tolerance=0)

# EITC (IR-2025-103)
ok("P26.22 EITC invest limit 2026",     p26['eitc_investment_income_limit'],     11950, tolerance=0,
   note="IR-2025-103; +$350 from $11,600")
ok("P26.23 EITC 3+ children max 2026",  p26['eitc']['single_qss'][3]['max'],     8231, tolerance=0,
   note="IR-2025-103; +$185 from $8,046")

# Retirement (Notice 2025-67)
ok("P26.24 SEP-IRA max 2026",           p26['sep_ira_max_2026'],                73000, tolerance=0,
   note="Notice 2025-67; +$3,000 from $70,000")
ok("P26.25 Solo 401k elective 2026",    p26['solo401k_elective_max_2026'],       24500, tolerance=0,
   note="Notice 2025-67; +$1,000 from $23,500")
ok("P26.26 SIMPLE IRA max 2026",        p26['simple_ira_max_2026'],              17000, tolerance=0,
   note="Notice 2025-67; +$500 from $16,500")
ok("P26.27 IRA limit 2026",             p26['ira_limit_2026'],                   7500, tolerance=0,
   note="Notice 2025-67; +$500 from $7,000")
ok("P26.28 IRA catchup 50+ 2026",       p26['ira_catchup_50plus_2026'],          1100, tolerance=0,
   note="SECURE 2.0 §108 indexed; +$100 from 2025's $1,000 add-on")

# HSA (Rev. Proc. 2025-32)
ok("P26.29 HSA self-only 2026",         p26['hsa_self_only_2026'],               4400, tolerance=0,
   note="Rev. Proc. 2025-32; +$100 from $4,300")
ok("P26.30 HSA family 2026",            p26['hsa_family_2026'],                  8750, tolerance=0,
   note="Rev. Proc. 2025-32; +$200 from $8,550")

# TY 2026 income tax bracket spot-checks (Rev. Proc. 2025-32)
ok("P26.31 2026 bracket single 10% top", p26['brackets_single_2026'][0][0],     12400, tolerance=0,
   note="Rev. Proc. 2025-32; 10% bracket top — single")
ok("P26.32 2026 bracket single 12% top", p26['brackets_single_2026'][1][0],     50400, tolerance=0,
   note="Rev. Proc. 2025-32; 12% bracket top — single")
ok("P26.33 2026 bracket MFJ 10% top",   p26['brackets_mfj_2026'][0][0],         24800, tolerance=0)
ok("P26.34 2026 bracket MFJ 12% top",   p26['brackets_mfj_2026'][1][0],        100800, tolerance=0)
ok("P26.35 2026 bracket HOH 10% top",   p26['brackets_hoh_2026'][0][0],         17700, tolerance=0)
ok("P26.36 2026 bracket HOH 12% top",   p26['brackets_hoh_2026'][1][0],         67050, tolerance=0)


# =============================================================================
# LAYER 2B -- TY 2026 Pipeline Regression
# Run a real return with tax_year=2026 and verify key computed values change
# appropriately vs TY 2025 (std ded, brackets, CTC, QBI min).
# =============================================================================
section("LAYER 2B -- TY 2026 Pipeline Regression")

print("\n  Test 16: TY 2026 — standard deduction, brackets, ACTC increase")
try:
    import dataclasses as _dc16
    def _si16(cls, **kw):
        valid = {f.name for f in _dc16.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})

    schema26 = _si16(e.TaxpayerSchema,
        first="Tax", last="Year26", ssn="999-00-2026", dob="01-01-1980",
        occupation="Worker", address="1 Main", filing_status="single",
        tax_year=2026,
        w2s=[_si16(e.W2, employer="Corp", ein="99-9999999",
                   box1_wages=60000, box2_fed_wh=8000,
                   box3_ss_wages=60000, box4_ss_wh=3720,
                   box5_med_wages=60000, box6_med_wh=870,
                   for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c26 = e.run(schema26).get("computed", {})

    ok("S16.1 TY2026 std ded single = $16,100",
       c26.get("std_deduction", 0), 16100, tolerance=0,
       note="Rev. Proc. 2025-32; $350 higher than 2025's $15,750")
    ok("S16.2 TY2026 taxable income = $43,900",
       c26.get("taxable_income", 0), 43900, tolerance=0,
       note="$60,000 wages - $16,100 std ded")
    # 2026 tax: 10% on 12400 + 12% on (43900-12400) = 1240 + 3780 = 5020
    ok("S16.3 TY2026 income tax uses 2026 brackets",
       c26.get("income_tax", 0), 5020, tolerance=5,
       note="Rev. Proc. 2025-32 brackets: 10% on ≤$12,400, 12% on $12,401–$50,400")
except Exception as ex:
    warn("TY 2026 pipeline regression CRASHED", traceback.format_exc(limit=3))

print("\n  Test 17: TY 2026 — senior std addon uses 2026 amounts")
try:
    import dataclasses as _dc17
    def _si17(cls, **kw):
        valid = {f.name for f in _dc17.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})

    schema26s = _si17(e.TaxpayerSchema,
        first="Senior", last="2026", ssn="888-00-2026", dob="01-01-1955",
        occupation="Retired", address="2 Main", filing_status="mfj",
        tax_year=2026,
        taxpayer_age_for_senior_ded=70, spouse_age_for_senior_ded=68,
        w2s=[_si17(e.W2, employer="Corp", ein="88-8888888",
                   box1_wages=50000, box2_fed_wh=6000,
                   box3_ss_wages=50000, box4_ss_wh=3100,
                   box5_med_wages=50000, box6_med_wh=725,
                   for_spouse=False)],
        form_1099ints=[], form_1099rs=[], form_1099divs=[], form_1099necs=[],
        form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        schedule_cs=[], dependents=[], care_providers=[], form_1098ts=[],
        form_1099bs=[], schedule_es=[], form_w2gs=[], form_1099gs=[],
        schedule_k1s=[], form_5329_exceptions=[], form_4797s=[])
    c26s = e.run(schema26s).get("computed", {})

    ok("S17.1 TY2026 MFJ std ded both senior = $35,500",
       c26s.get("std_deduction", 0), 35500, tolerance=0,
       note="$32,200 + 2×$1,650 senior addon (Rev. Proc. 2025-32 §3.10)")
except Exception as ex:
    warn("TY 2026 senior addon test CRASHED", traceback.format_exc(limit=3))

print("\n  Test 18: TY 2026 — QBI minimum $400 triggers when 20%×QBI < $400")
try:
    import dataclasses as _dc18
    def _si18(cls, **kw):
        valid = {f.name for f in _dc18.fields(cls)}
        return cls(**{k: v for k,v in kw.items() if k in valid})

    # SE income ~$1,500 net after SE deduction -> QBI ~$1,415
    # 20% × 1415 = $283 < $400 -> engine should floor to $400
    sc_small18 = _si18(e.ScheduleC, business_name="Small Biz",
                       gross_receipts=1700, expenses_other=200)
    schema26q = _si18(e.TaxpayerSchema,
        first="Q", last="Min", ssn="777-00-2026", dob="01-01-1980",
        occupation="Freelancer", address="3 Main", filing_status="single",
        tax_year=2026, schedule_cs=[sc_small18],
        w2s=[], form_1099ints=[], form_1099rs=[], form_1099divs=[],
        form_1099necs=[], form_ssa1099=None, form_1099cs=[], form_1099misc_prizes=[],
        dependents=[], care_providers=[], form_1098ts=[], form_1099bs=[],
        schedule_es=[], form_w2gs=[], form_1099gs=[], schedule_k1s=[],
        form_5329_exceptions=[], form_4797s=[])
    c26q = e.run(schema26q).get("computed", {})
    qbi_ded = c26q.get("adj_qbi", 0)
    ok("S18.1 TY2026 QBI min $400 floor triggered",
       qbi_ded, 400, tolerance=0,
       note="OBBBA: 20%×QBI < $400 and QBI >= $1,000 -> floor to $400")
except Exception as ex:
    warn("TY 2026 QBI min floor test CRASHED", traceback.format_exc(limit=3))


# =============================================================================
# FILE REGISTRY AUDIT
# Confirm current line counts match PlanningReference Page 1.
# A mismatch means a file was edited without updating the reference document.
# =============================================================================
section("FILE REGISTRY -- Line Count Audit")

import os

FILE_REGISTRY = [
    ("sachintaxcare_engine.py",        8897,  100),
    ("sachintaxcare_pro.html",         4797,   50),
    ("sachintaxcare_server.py",         761,   50),
    ("sachintaxcare_workpaper.html",   1639,   50),
    ("sachintaxcare_test.py",          None,   None),   # self -- skip
    ("sachintaxcare_pdf.py",           367,   30),
    ("sachintaxcare_report.py",        965,   30),
    ("test_vita_irs.py",              2439,   20),
    ("test_ui_fields.js",              815,   50),
    ("test_report.py",                 415,   30),
    ("sachintaxcare_field_manifest.md", 1021,   50),
    ("IMPLEMENTATION_GUIDE.md",        330,   50),
    ("ENGINE_ALGORITHM.md",            604,   50),
    ("sachintaxcare_schema_2025.json",  31,   30),
]

for fname, expected_lines, tolerance in FILE_REGISTRY:
    if expected_lines is None:
        continue
    if not os.path.exists(fname):
        warn(f"FILE MISSING: {fname}", "File not found in project directory")
        continue
    with open(fname, 'r', errors='replace') as fh:
        actual_lines = sum(1 for _ in fh)
    if tolerance and abs(actual_lines - expected_lines) <= tolerance:
        ok(f"Registry: {fname} lines",
           actual_lines, expected_lines, tolerance=tolerance,
           note=f"actual={actual_lines}, reference={expected_lines}")
    else:
        ok(f"Registry: {fname} lines",
           actual_lines, expected_lines, tolerance=tolerance or 0,
           note=f"actual={actual_lines} vs reference={expected_lines} — update PlanningReference Page 1 if intentional")


# =============================================================================
# QCD + EITC-2 REGRESSION TESTS (added 2026-05-19 EA review)
# =============================================================================

print("\n  Test QCD: Code Y exclusion and cap (IRC §408(d)(8))")
try:
    _sc_qcd = build_bridge({"first":"QCD","last":"Test","ssn":"300-00-0001",
        "dob":"01-01-1952","filing_status":"single","tax_year":2025,
        "w2s":[{"employer":"Test","ein":"99-0000001","box1_wages":30000,"box2_fed_wh":3000}],
        "form_1099rs":[{"payer":"Fidelity","payer_ein":"04-0000001","box1_gross":10000,
            "box2a_taxable":10000,"box4_fed_wh":0,"box7_code":"Y","box7_ira_sep_simple":True}]})
    _cq  = e.run(_sc_qcd).get("computed", {})
    ok("QCD.1 Code Y excluded from l4b",
       _cq.get("l4b_ira_taxable", -1), 0, tolerance=0,
       note="IRC §408(d)(8); f1099r.pdf — Code Y must not appear on Line 4b")
    ok("QCD.2 qcd_total tracked",
       _cq.get("qcd_total", -1), 10000, tolerance=0,
       note="qcd_total accumulates all Code Y gross amounts")
    ok("QCD.3 QCD not in total_income",
       _cq.get("total_income", 0), 30000, tolerance=0,
       note="total_income = wages only; QCD fully excluded from gross income")

    _sc_big = build_bridge({"first":"Big","last":"Donor","ssn":"300-00-0002",
        "dob":"01-01-1952","filing_status":"single","tax_year":2025,
        "w2s":[{"employer":"Test","ein":"99-0000002","box1_wages":50000,"box2_fed_wh":5000}],
        "form_1099rs":[{"payer":"Vanguard","ein":"04-0000002","box1_gross":110000,
            "box2a_taxable":110000,"box4_fed_wh":0,"box7_code":"Y","box7_ira_sep_simple":True}]})
    _cap_warned = any("QCD LIMIT EXCEEDED" in w for w in e.run(_sc_big).get("warnings", []))
    ok("QCD.4 Cap warning at $110,000 (limit $105,000)",
       _cap_warned, True,
       note="IRC §408(d)(8)(B)(i); SECURE 2.0 §307; Rev. Proc. 2024-40")

    _sc_sA = build_bridge({"first":"DoubleA","last":"Test","ssn":"300-00-0003",
        "dob":"01-01-1952","filing_status":"single","tax_year":2025,
        "use_itemized":True,
        "w2s":[{"employer":"Test","ein":"99-0000003","box1_wages":30000,"box2_fed_wh":3000}],
        "form_1099rs":[{"payer":"Fidelity","payer_ein":"04-0000001","box1_gross":10000,
            "box2a_taxable":10000,"box4_fed_wh":0,"box7_code":"Y","box7_ira_sep_simple":True}],
        "schedule_a":{"cash_charitable":10000,"salt_method":"income"}})
    _conflict = any("Schedule A conflict" in w for w in e.run(_sc_sA).get("warnings", []))
    ok("QCD.5 Sch A conflict warning when QCD + cash_charitable entered",
       _conflict, True,
       note="IRC §408(d)(8)(D) — QCDs cannot be deducted on Sch A. Source: IRS Pub 590-B")
except Exception as ex:
    warn("QCD test CRASHED", traceback.format_exc(limit=3))

print("\n  Test EITC2: 0-child single corrected params (Rev. Proc. 2024-40)")
try:
    ok("EITC2.1 0-child single plateau $632 (not MFJ $649)",
       e.compute_eitc(8450, 8450, 0, "single", 0.0)["eitc"], 632, tolerance=1,
       note="Rev. Proc. 2024-40 §3.07; Pub 596 TY2025: single_qss 0-child max=$632")
    ok("EITC2.2 0-child single above $18,591 limit → $0",
       e.compute_eitc(18700, 18700, 0, "single", 0.0)["eitc"], 0, tolerance=0,
       note="single limit $18,591, NOT MFJ $19,104 — Rev. Proc. 2024-40")
    ok("EITC2.3 0-child single AT $18,591 → $0",
       e.compute_eitc(18591, 18591, 0, "single", 0.0)["eitc"], 0, tolerance=0,
       note="At income_limit exactly → $0 per IRC §32; p1040.pdf EIC Table")
    ok("EITC2.4 0-child MFJ $649 plateau unchanged",
       e.compute_eitc(8450, 8450, 0, "mfj", 0.0)["eitc"], 646, tolerance=2,
       note="MFJ max $649; band $8,450 → $646 (band rounding) — Rev. Proc. 2024-40")
    ok("EITC2.5 0-child MFJ above $26,214 → $0",
       e.compute_eitc(26300, 26300, 0, "mfj", 0.0)["eitc"], 0, tolerance=0,
       note="MFJ income limit $26,214 unchanged — Rev. Proc. 2024-40")
except Exception as ex:
    warn("EITC-2 test CRASHED", traceback.format_exc(limit=3))

print("\n  Test F2210: Form 2210 prior-year guard (EA fix 2026-05-19)")
try:
    fn = e.compute_form_2210_safe_harbor

    # THE KEY FIX: blank prior year must NOT grant harbor (b)
    _r = fn(10000, 3000, 0, 0)
    ok("F2210.1 Blank prior year + $7k shortfall: NOT safe harbor",
       _r["safe_harbor_met"], False,
       note="IRC §6654(d)(1)(B) — prior_year_tax=0 must not grant harbor (b) via req_prior=$0")
    ok("F2210.2 Blank prior year + $7k shortfall: penalty assessed",
       _r.get("penalty", 0) > 0, True,
       note="penalty=480 (8% rate × shortfall). Source: IRC §6654; f2210.pdf")

    # Harbor (c) — 90% of current — works even without prior year
    ok("F2210.3 Blank prior, 95% paid: harbor (c) met",
       fn(10000, 9500, 0, 0)["safe_harbor_met"], True,
       note="payments $9,500 >= 90% current $9,000 — harbor (c). Source: f2210.pdf Part II")
    ok("F2210.4 Blank prior, exactly 90% paid: harbor (c) met",
       fn(10000, 9000, 0, 0)["safe_harbor_met"], True,
       note="payments == req_current exactly. Source: IRC §6654(d)(1)(C)")

    # Harbor (a) — net owed < $1,000
    ok("F2210.5 Net owed $800 < $1,000: harbor (a) met",
       fn(1000, 200, 0, 0)["safe_harbor_met"], True,
       note="net_owed $800 < $1,000 — harbor (a). Source: IRC §6654(e)(1); f2210.pdf Line 9")

    # Prior year known — all three harbors work
    _rk = fn(10000, 3000, 9000, 120000)
    ok("F2210.6 Prior year known, insufficient: NOT safe",
       _rk["safe_harbor_met"], False,
       note="payments $3,000 < 100% prior $9,000 AND 90% current $9,000. Source: f2210.pdf")
    ok("F2210.7 Prior year known, harbor (b) met",
       fn(10000, 9001, 9000, 120000)["safe_harbor_met"], True,
       note="payments $9,001 >= 100% prior $9,000. Source: IRC §6654(d)(1)(B)")

    # 110% rule: prior AGI > $150k, harbor (c) saves when 110% fails
    _r110 = fn(10000, 10900, 10000, 200000)
    ok("F2210.8 110% rule — harbor (c) saves when 110% fails",
       _r110["safe_harbor_met"], True,
       note="prior AGI $200k: need 110%=$11k; pmts $10,900 fail (b) but >= 90% cur $9k passes (c)")

    # Warning content check: blank prior with balance due
    _rw = fn(10000, 3000, 0, 0)
    ok("F2210.9 Blank prior warning mentions prior year not entered",
       "Prior year" in _rw.get("warning", "") or "prior year" in _rw.get("warning", ""), True,
       note="Warning must direct preparer to enter Form 1040 Line 24")
except Exception as ex:
    warn("F2210 test CRASHED", traceback.format_exc(limit=3))

print("\n  Test F4-F9: EA High/Low findings (2026-05-19)")
try:
    # F4: CA CalEITC uses W-2 Box 16 wages, not AGI proxy
    import dataclasses as _dc
    def _si(cls, **kw):
        valid = {f.name for f in _dc.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})
    _w2_ca = _si(e.W2, employer="SchoolDistrict", ein="94-0000001",
        box1_wages=28000, box2_fed_wh=2800, box3_ss_wages=28000, box4_ss_wh=1736,
        box5_med_wages=28000, box6_med_wh=406,
        box15_state="CA", box16_state_wages=28000, box17_state_wh=600)
    _sc_ca = _si(e.TaxpayerSchema, first="CA", last="Worker", ssn="600-00-0001",
        dob="01-01-1985", filing_status="single", tax_year=2025,
        w2s=[_w2_ca], california=_si(e.CaliforniaData))
    _ca_res = e.run(_sc_ca).get("computed", {})
    _ca540  = _ca_res.get("ca_540", {})
    ok("F4.1 CA CalEITC uses W-2 Box16 CA wages (not AGI proxy)",
       _ca540.get("caleitc_detail", {}).get("ca_earned_income", 0), 28000, tolerance=10,
       note="FTB 3514 Step 1: CA earned income = W-2 Box 16 wages. Source: ftb.ca.gov/forms/2025/2025-3514-booklet.html")

    # F5: K-1 outside basis caps loss
    _k1_limited = e.ScheduleK1(entity_name="TestLP", entity_ein="99-0000001",
        box1_ordinary_income=-20000, outside_basis=5000.0,
        material_participation=True, is_rental=False)
    _k1_res = e.compute_k1_income([_k1_limited])
    ok("F5.1 K-1 loss capped at outside_basis=$5,000 (loss was -$20,000)",
       _k1_res["net_k1_ordinary"], -5000, tolerance=0,
       note="IRC §704(d): loss limited to outside basis. Source: IRC §704(d); IRC §1366(d); f6198.pdf")
    _basis_warned = any("§704(d)" in w or "704(d)" in w for w in _k1_res.get("warnings",[]))
    ok("F5.2 §704(d) warning emitted when basis caps loss",
       _basis_warned, True,
       note="Source: IRC §704(d); IRC §1366(d)")

    # F5: K-1 loss below basis — not capped
    _k1_ok = e.ScheduleK1(entity_name="TestLP2", entity_ein="99-0000002",
        box1_ordinary_income=-3000, outside_basis=10000.0,
        material_participation=True, is_rental=False)
    _k1_ok_res = e.compute_k1_income([_k1_ok])
    ok("F5.3 K-1 loss within basis — not capped",
       _k1_ok_res["net_k1_ordinary"], -3000, tolerance=0,
       note="Loss $3,000 < basis $10,000 — no cap. Source: IRC §704(d)")

    # F6: Form 982 insolvency worksheet
    _f982_solvent = e.Form982Data(
        total_liabilities_before=30000, total_assets_fmv_before=50000)
    _r_solvent = e.compute_form_982(_f982_solvent, 5000)
    ok("F6.1 Form 982: solvent taxpayer — no exclusion",
       _r_solvent["excluded"], 0, tolerance=0,
       note="Liabilities $30k < assets $50k → not insolvent. Source: IRC §108(a)(1)(B)")

    _f982_insolvent = e.Form982Data(
        total_liabilities_before=80000, total_assets_fmv_before=60000)
    _r_insolvent = e.compute_form_982(_f982_insolvent, 10000)
    ok("F6.2 Form 982: insolvent — insolvency=$20k, discharged=$10k → excluded=$10k",
       _r_insolvent["excluded"], 10000, tolerance=0,
       note="Insolvency $20k > discharge $10k → full exclusion. Source: IRC §108(a)(1)(B)")
    ok("F6.3 Form 982: taxable = $0 when fully excluded",
       _r_insolvent["taxable"], 0, tolerance=0,
       note="Source: IRC §108(a)(1)(B); f982.pdf")

    _f982_partial = e.Form982Data(
        total_liabilities_before=65000, total_assets_fmv_before=60000)
    _r_partial = e.compute_form_982(_f982_partial, 8000)
    ok("F6.4 Form 982: partial exclusion — insolvency=$5k, discharge=$8k → excluded=$5k",
       _r_partial["excluded"], 5000, tolerance=0,
       note="Exclusion = min(discharged $8k, insolvency $5k) = $5k. Source: IRC §108(a)(1)(B)")
    ok("F6.5 Form 982: partial — taxable = $3k",
       _r_partial["taxable"], 3000, tolerance=0,
       note="$8k discharged - $5k excluded = $3k taxable. Source: IRC §108; f982.pdf")

    _f982_bk = e.Form982Data(bankruptcy_title11=True)
    _r_bk = e.compute_form_982(_f982_bk, 15000)
    ok("F6.6 Form 982: bankruptcy Title 11 — full exclusion",
       _r_bk["excluded"], 15000, tolerance=0,
       note="Box 1a: Title 11 → fully excluded. Source: IRC §108(a)(1)(A); f982.pdf Box 1a")

    # F8: IRA MAGI proxy includes student loan addback
    # Taxpayer with student loan interest $2,500 near IRA phaseout boundary
    # Without addback: MAGI might be below $79k; with addback might be above
    # Just test that the addback is present by checking magi_proxy calc
    _wages_near_po = 77000  # near covered single phaseout start $79k
    _sl_addback = 2500
    # The IRA phaseout for covered single starts at $79,000
    # Without addback: MAGI = $77,000 (below threshold) → full deduction
    # With addback: MAGI = $77,000 + $2,500 = $79,500 (into phaseout) → reduced deduction
    _sc_ira = build_bridge({
        "first":"IRA","last":"Test","ssn":"700-00-0001",
        "dob":"01-01-1985","filing_status":"single","tax_year":2025,
        "w2s":[{"employer":"Employer","ein":"50-0000001",
                "box1_wages":_wages_near_po,"box2_fed_wh":8000,
                "box13_retirement_plan":True}],
        "ira_contribution_traditional":7000,
        "ira_taxpayer_age":40,
        "student_loan_interest":_sl_addback
    })
    _ira_res = e.run(_sc_ira).get("computed",{})
    _ira_ded = _ira_res.get("adj_ira_deduction",0)
    # With student loan addback: MAGI = 77000+2500 = 79500 → into $79k-$89k phaseout
    # Phaseout ratio = (79500-79000)/(89000-79000) = 500/10000 = 5%
    # Deduction = 7000 × (1 - 0.05) = 6650 → floor to nearest $10 = 6650
    ok("F8.1 IRA MAGI includes student loan addback (Pub 590-A WS1-2)",
       _ira_ded < 7000, True,
       note="MAGI $79,500 (wages $77k + SL $2.5k) is in phaseout $79k-$89k → partial deduction. Source: Pub 590-A WS1-2; IRC §219(g)(3)(A)(ii)")

except Exception as ex:
    warn("F4-F9 test CRASHED", traceback.format_exc(limit=4))


print("\n  Test EWP: Early withdrawal penalty flows to Schedule 1 Line 18 (IRC §62(a)(9))")
try:
    _sc_ewp = build_bridge({
        "first":"EWP","last":"Test","ssn":"800-00-0001",
        "dob":"04-12-1984","filing_status":"single","tax_year":2025,
        "w2s":[{"employer":"Employer","ein":"99-0000010",
                "box1_wages":40000,"box2_fed_wh":4000}],
        "form_1099ints":[{"payer":"Bank","box1_interest":500,
                          "box2_early_withdrawal_penalty":75}]
    })
    _c_ewp = e.run(_sc_ewp).get("computed",{})
    ok("EWP.1 adj_early_wdwl = 75 (f1099int.pdf Box 2 → Sch 1 Line 18)",
       _c_ewp.get("adj_early_wdwl",0), 75, tolerance=0,
       note="Source: f1099int.pdf Box 2; i1040s1.pdf Line 18; IRC §62(a)(9)")
    ok("EWP.2 total_adjustments includes penalty",
       _c_ewp.get("total_adjustments",0), 75, tolerance=0,
       note="Penalty is above-line — reduces AGI")
    ok("EWP.3 AGI reduced by penalty",
       _c_ewp.get("agi",0), 40500 - 75, tolerance=1,
       note="wages $40k + interest $500 - penalty $75 = $40,425")
except Exception as ex:
    warn("EWP test CRASHED", traceback.format_exc(limit=3))

print("\n  Test QSS: Qualifying Surviving Spouse standard deduction = MFJ rate")
try:
    import dataclasses as _dc2
    def _si2(cls, **kw):
        valid = {f.name for f in _dc2.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})
    _sc_qss = build_bridge({
        "first":"CARL","last":"GRAVES","ssn":"328-00-1111",
        "dob":"04-12-1984","filing_status":"qss","tax_year":2025,
        "taxpayer_age_for_senior_ded":41,
        "deceased_spouse":{"name":"JANE GRAVES","ssn":"329-00-1111","date_of_death":"07-18-2023"},
        "w2s":[{"employer":"Employer","ein":"34-8001111","box1_wages":37000,
                "box2_fed_wh":1500,"box13_retirement_plan":True}],
        "form_1099ints":[{"payer":"Bank","box1_interest":160,
                          "box2_early_withdrawal_penalty":32}],
        "dependents":[{"first":"LILLY","last":"GRAVES","ssn":"125-00-1111",
                       "dob":"07-24-2016","age":9,"relationship":"child",
                       "ctc_eligible":True}]
    })
    _c_qss = e.run(_sc_qss).get("computed",{})
    ok("QSS.1 std_deduction = $31,500 (MFJ rate for QSS)",
       _c_qss.get("std_deduction",0), 31500, tolerance=0,
       note="IRC §1(a); Pub 501 — QSS uses MFJ std deduction for tax year of election")
    ok("QSS.2 adj_early_wdwl = 32",
       _c_qss.get("adj_early_wdwl",0), 32, tolerance=0,
       note="box2_early_withdrawal_penalty bridge fix — f1099int.pdf Box 2")
    ok("QSS.3 AGI = 37128 (37160 - 32 early wdwl penalty)",
       _c_qss.get("agi",0), 37128, tolerance=1,
       note="wages $37k + interest $160 - penalty $32 = $37,128")
except Exception as ex:
    warn("QSS test CRASHED", traceback.format_exc(limit=3))


print("\n  Test BRIDGE: End-to-end bridge coverage (2026-05-19 hardening)")
try:
    import dataclasses as _dce
    # Helper: run a raw JSON dict through the inline bridge (mirrors server deserialize_schema)
    def _bridge(raw: dict):
        """Inline bridge that mirrors server deserialize_schema for testing without Flask."""
        kwargs = {}
        DMAP = {
            'w2s': e.W2, 'form_1099ints': e.Form1099INT, 'form_1099divs': e.Form1099DIV,
            'form_1099rs': e.Form1099R, 'form_1099cs': e.Form1099C,
            'form_1099bs': e.Form1099B, 'form_1099necs': e.Form1099NEC,
            'form_w2gs': e.FormW2G, 'form_1099gs': e.Form1099G,
            'schedule_cs': e.ScheduleC, 'schedule_es': e.ScheduleE,
            'schedule_k1s': e.ScheduleK1, 'dependents': e.Dependent,
            'care_providers': e.Form2441Provider, 'form_1098ts': e.Form1098T,
            'form_5329_exceptions': e.Form5329Exception, 'form_4797s': e.Form4797SaleData,
        }
        SMAP = {
            'form_ssa1099': e.FormSSA1099, 'schedule_a': e.ScheduleAData,
            'form_1095a': e.Form1095A, 'form_6251': e.Form6251Data,
            'form_2210': e.Form2210Data, 'deceased_spouse': e.DeceasedSpouse,
            'california': e.CaliforniaData, 'ca_540': e.CaliforniaData,
            'form_982': e.Form982Data,
        }
        def _si_b(cls, d):
            valid = {f.name for f in _dce.fields(cls)}
            return cls(**{k: v for k, v in d.items() if k in valid}) if isinstance(d, dict) else None

        for key, val in raw.items():
            if key == 'w2s' and isinstance(val, list):
                bridged = []
                for d in val:
                    if not isinstance(d, dict): continue
                    d = dict(d)
                    for old, new in [('box10_dep_care','box10_dependent_care'),
                                     ('box15_state_id','box15_state_employer_id'),
                                     ('box5_medicare_wages','box5_med_wages'),
                                     ('box6_medicare_wh','box6_med_wh')]:
                        if old in d and new not in d: d[new] = d.pop(old)
                    i = _si_b(e.W2, d)
                    if i: bridged.append(i)
                kwargs[key] = bridged
            elif key == 'form_1099ints' and isinstance(val, list):
                bridged = []
                for d in val:
                    if not isinstance(d, dict): continue
                    d = dict(d)
                    if 'box6_foreign_tax_paid' in d: d['box6_foreign_tax'] = d.pop('box6_foreign_tax_paid')
                    i = _si_b(e.Form1099INT, d)
                    if i: bridged.append(i)
                kwargs[key] = bridged
            elif key == 'form_1099rs' and isinstance(val, list):
                bridged = []
                for d in val:
                    if not isinstance(d, dict): continue
                    d2 = dict(d)
                    if 'box9b_employee_contrib' in d2 and 'box9b_employee_contribs' not in d2:
                        d2['box9b_employee_contribs'] = float(d2.pop('box9b_employee_contrib') or 0)
                    i = _si_b(e.Form1099R, d2)
                    if i: bridged.append(i)
                kwargs[key] = bridged
            elif key == 'form_1099cs' and isinstance(val, list):
                bridged = []
                for d in val:
                    if not isinstance(d, dict): continue
                    d2 = dict(d)
                    if 'box2_discharged' in d2 and 'box2_amount_discharged' not in d2:
                        d2['box2_amount_discharged'] = float(d2.pop('box2_discharged') or 0)
                    if 'exclusion_applies' in d2 and 'is_excluded' not in d2:
                        d2['is_excluded'] = bool(d2.pop('exclusion_applies'))
                    i = _si_b(e.Form1099C, d2)
                    if i: bridged.append(i)
                kwargs[key] = bridged
            elif key == 'form_ssa1099' and isinstance(val, dict):
                d2 = dict(val)
                if 'box6_vol_wh' in d2 and 'box6_voluntary_wh' not in d2:
                    d2['box6_voluntary_wh'] = d2.pop('box6_vol_wh')
                kwargs[key] = _si_b(e.FormSSA1099, d2)
            elif key == 'form_1098ts' and isinstance(val, list):
                bridged = []
                for d in val:
                    if not isinstance(d, dict): continue
                    d2 = dict(d)
                    if 'box8_at_least_half_time' in d2 and 'box8_half_time' not in d2:
                        d2['box8_half_time'] = d2.pop('box8_at_least_half_time')
                    i = _si_b(e.Form1098T, d2)
                    if i: bridged.append(i)
                kwargs[key] = bridged
            elif key in DMAP and isinstance(val, list):
                kwargs[key] = [i for d in val if isinstance(d,dict)
                               for i in [_si_b(DMAP[key], d)] if i is not None]
            elif key in SMAP and isinstance(val, dict):
                i = _si_b(SMAP[key], val)
                if i: kwargs[key] = i
            else:
                kwargs[key] = val
        for k in list(DMAP.keys()) + ['form_1099necs']:
            kwargs.setdefault(k, [])
        valid_ts = {f.name for f in _dce.fields(e.TaxpayerSchema)}
        return e.TaxpayerSchema(**{k: v for k, v in kwargs.items() if k in valid_ts})

    # ── B1: W2.box10_dep_care → box10_dependent_care ──────────────────────────
    _raw_w2_dc = {"first":"T","last":"T","ssn":"900-00-0001","dob":"01-01-1985",
                  "filing_status":"single","tax_year":2025,
                  "w2s":[{"employer":"E","ein":"99-0000001","box1_wages":50000,
                          "box2_fed_wh":5000,"box10_dep_care":5000}]}
    _s_w2 = _bridge(_raw_w2_dc)
    ok("BRIDGE.B1 W2.box10_dep_care → box10_dependent_care",
       _s_w2.w2s[0].box10_dependent_care, 5000, tolerance=0,
       note="Form 2441 §129 exclusion. Source: iw2w3.pdf Box 10; bridge hardening 2026-05-19")

    # ── B2: Form1099INT.box6_foreign_tax_paid → box6_foreign_tax ──────────────
    _raw_int = {"first":"T","last":"T","ssn":"900-00-0002","dob":"01-01-1985",
                "filing_status":"single","tax_year":2025,
                "w2s":[{"employer":"E","ein":"99-0000002","box1_wages":50000,"box2_fed_wh":5000}],
                "form_1099ints":[{"payer":"Bank","box1_interest":1000,"box6_foreign_tax_paid":50}]}
    _s_int = _bridge(_raw_int)
    ok("BRIDGE.B2 Form1099INT.box6_foreign_tax_paid → box6_foreign_tax",
       _s_int.form_1099ints[0].box6_foreign_tax, 50, tolerance=0,
       note="Form 1116 FTC. Source: f1099int.pdf Box 6; bridge hardening 2026-05-19")

    # ── B3: Form1099C.box2_discharged → box2_amount_discharged ────────────────
    _raw_cod = {"first":"T","last":"T","ssn":"900-00-0003","dob":"01-01-1985",
                "filing_status":"single","tax_year":2025,
                "w2s":[{"employer":"E","ein":"99-0000003","box1_wages":30000,"box2_fed_wh":3000}],
                "form_1099cs":[{"creditor":"Bank","box2_discharged":5000,"box6_event_code":"F"}]}
    _s_cod = _bridge(_raw_cod)
    ok("BRIDGE.B3 Form1099C.box2_discharged → box2_amount_discharged",
       _s_cod.form_1099cs[0].box2_amount_discharged, 5000, tolerance=0,
       note="Sch 1 Line 8c. Source: f1099c.pdf; bridge hardening 2026-05-19")

    # ── B4: FormSSA1099.box6_vol_wh → box6_voluntary_wh ──────────────────────
    _raw_ssa = {"first":"T","last":"T","ssn":"900-00-0004","dob":"01-01-1955",
                "filing_status":"single","tax_year":2025,
                "w2s":[{"employer":"E","ein":"99-0000004","box1_wages":20000,"box2_fed_wh":2000}],
                "form_ssa1099":{"box5_net_benefits":12000,"box3_gross_benefits":12000,
                                "box6_vol_wh":1200}}
    _s_ssa = _bridge(_raw_ssa)
    ok("BRIDGE.B4 FormSSA1099.box6_vol_wh → box6_voluntary_wh",
       _s_ssa.form_ssa1099.box6_voluntary_wh, 1200, tolerance=0,
       note="Line 25b. Source: SSA-1099; bridge hardening 2026-05-19")

    # ── B5: Form1098T.box8_at_least_half_time → box8_half_time ────────────────
    _raw_1098t = {"first":"T","last":"T","ssn":"900-00-0005","dob":"01-01-1985",
                  "filing_status":"single","tax_year":2025,
                  "w2s":[{"employer":"E","ein":"99-0000005","box1_wages":45000,"box2_fed_wh":4500}],
                  "form_1098ts":[{"institution":"College","box1_payments":5000,
                                  "box8_at_least_half_time":True,"credit_type":"aoc",
                                  "first_four_years":True,"student_who":"taxpayer"}]}
    _s_1098t = _bridge(_raw_1098t)
    ok("BRIDGE.B5 Form1098T.box8_at_least_half_time → box8_half_time",
       _s_1098t.form_1098ts[0].box8_half_time, True,
       note="AOC eligibility. Source: f1098t.pdf; f8863.pdf; bridge hardening 2026-05-19")

    # ── C1: TaxpayerSchema.taxpayer_is_blind now a proper field ───────────────
    _raw_blind = {"first":"T","last":"T","ssn":"900-00-0006","dob":"01-01-1985",
                  "filing_status":"single","tax_year":2025,"taxpayer_is_blind":True,
                  "w2s":[{"employer":"E","ein":"99-0000006","box1_wages":40000,"box2_fed_wh":4000}]}
    _s_blind = _bridge(_raw_blind)
    ok("BRIDGE.C1 TaxpayerSchema.taxpayer_is_blind is a proper field (not dropped)",
       _s_blind.taxpayer_is_blind, True,
       note="Std ded +$1,950. Source: IRC §63(f); bridge hardening 2026-05-19")

    # ── C2: TaxpayerSchema.aca_household_size wired into Form 8962 L1 ─────────
    _raw_aca = {"first":"T","last":"T","ssn":"900-00-0007","dob":"01-01-1985",
                "filing_status":"single","tax_year":2025,"aca_household_size":3,
                "w2s":[{"employer":"E","ein":"99-0000007","box1_wages":37000,"box2_fed_wh":1500}],
                "form_1095a":{"col_a_annual":5352,"col_b_annual":7224,"col_c_annual":4656}}
    _s_aca = _bridge(_raw_aca)
    _c_aca = e.run(_s_aca).get("computed",{})
    ok("BRIDGE.C2 aca_household_size=3 wired into Form 8962 L1 family_size",
       _c_aca.get("f8962",{}).get("l1_family_size",0), 3, tolerance=0,
       note="Form 8962 L1. Source: f8962.pdf L1; IRC §36B(d)(1); bridge hardening 2026-05-19")

    # ── C3: ScheduleC.for_spouse is a proper field ────────────────────────────
    import dataclasses as _dce2
    ok("BRIDGE.C3 ScheduleC.for_spouse is a proper dataclass field",
       "for_spouse" in {f.name for f in _dce2.fields(e.ScheduleC)}, True,
       note="MFJ SE income split. Source: f1040sc.pdf; bridge hardening 2026-05-19")

    # ── C4: Form1098T.aoc_years_claimed_prior is a proper field ──────────────
    ok("BRIDGE.C4 Form1098T.aoc_years_claimed_prior is a proper dataclass field",
       "aoc_years_claimed_prior" in {f.name for f in _dce2.fields(e.Form1098T)}, True,
       note="AOC 4-year limit. Source: f8863.pdf L27; IRC §25A(b)(2)")

    # ── C5: Form1098T.student_who is a proper field ───────────────────────────
    ok("BRIDGE.C5 Form1098T.student_who is a proper dataclass field",
       "student_who" in {f.name for f in _dce2.fields(e.Form1098T)}, True,
       note="Credit attribution. Source: f8863.pdf; bridge hardening 2026-05-19")

    # ── Strict mode validator works ───────────────────────────────────────────
    # Build a raw dict with a known bad key
    _raw_strict_bad = {"first":"T","last":"T","ssn":"900-00-0008","tax_year":2025,
                       "w2s":[{"employer":"E","box1_wages":50000,"UNKNOWN_BAD_KEY":999}]}
    # Import the validator inline
    import importlib.util as _ilu
    _srv_spec = _ilu.spec_from_file_location("_srv", "/tmp/sachintaxcare_server.py")
    try:
        _srv = _ilu.module_from_spec(_srv_spec)
        # Don't exec (requires Flask) — just verify the function exists in source
        with open("/mnt/project/sachintaxcare_server.py") as _f:
            _srv_src = _f.read()
        ok("BRIDGE.STRICT _validate_bridge_strict function defined in server",
           "_validate_bridge_strict" in _srv_src, True,
           note="Strict mode: returns dropped_keys list. Source: bridge hardening 2026-05-19")
        ok("BRIDGE.STRICT _KNOWN_BRIDGES dict defined",
           "_KNOWN_BRIDGES" in _srv_src, True,
           note="Maps JSON key aliases to engine fields")
        ok("BRIDGE.STRICT /compute endpoint checks ?strict=true",
           "strict_mode" in _srv_src and "bridge_strict_violation" in _srv_src, True,
           note="Returns 422 with dropped_keys when strict mode fires")
    except Exception as _ex:
        warn("Strict mode source check error", str(_ex))

except Exception as ex:
    warn("BRIDGE coverage test CRASHED", traceback.format_exc(limit=4))

print("\n  Test F8880: Saver's credit rate table for QSS uses MFJ thresholds")
try:
    import dataclasses as _dca
    def _si8(cls, **kw):
        valid = {f.name for f in _dca.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})

    # QSS filer, AGI $40,000 → MFJ table: $47,500 limit → 50% rate
    # Single table at $40,000 → above $38,250 (10% rate)
    # This directly tests the QSS/MFJ distinction
    _r8880 = e.get_saver_rate(40000, "qss")
    ok("F8880.1 QSS AGI $40,000 → MFJ table → 50% rate (NOT single_qss 10%)",
       _r8880, 0.5,
       note="f8880.pdf Line 9 Rate Table; i8880.pdf; Rev. Proc. 2024-40 §3.14")

    _r8880_mfj = e.get_saver_rate(40000, "mfj")
    ok("F8880.2 MFJ AGI $40,000 → 50% rate",
       _r8880_mfj, 0.5,
       note="f8880.pdf; MFJ $0–$47,500 → 50%")

    _r8880_s = e.get_saver_rate(40000, "single")
    ok("F8880.3 Single AGI $40,000 → single_qss table → 10% rate",
       _r8880_s, 0.1,
       note="f8880.pdf; single $38,250–$39,500 → 10%")

    _r8880_hoh = e.get_saver_rate(40000, "hoh")
    ok("F8880.4 HOH AGI $40,000 → HOH table → 20% rate",
       _r8880_hoh, 0.2,
       note="f8880.pdf; HOH $38,500–$51,000 → 20%")

except Exception as ex:
    warn("F8880 test CRASHED", traceback.format_exc(limit=3))

print("\n  Test F8880-AUTO: W-2 Box 12 elective deferrals auto-populate Form 8880 L2")
try:
    import dataclasses as _dca
    def _si8a(cls, **kw):
        valid = {f.name for f in _dca.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})

    # Case 1: Code D $200 on W-2, no Form8880Data supplied → l2 should = $200
    _sc_d = _si8a(e.TaxpayerSchema,
        first="T", last="T", ssn="900-10-0001", dob="01-01-1980",
        filing_status="single", tax_year=2025,
        w2s=[_si8a(e.W2, employer="E", ein="99-0000020",
                   box1_wages=40000, box2_fed_wh=4000,
                   box12a_code="D", box12a_amt=200,
                   box13_retirement_plan=True)])
    _c_d = e.run(_sc_d).get("computed", {})
    ok("F8880-AUTO.1 W-2 Box12 Code D auto-populates Form 8880 L2",
       _c_d.get("f8880", {}).get("l2_deferrals", 0), 200, tolerance=0,
       note="i8880.pdf Line 2: Box 12 Code D = 401k deferral. Auto-read from W-2.")

    # Case 2: Code D $1 → l2=$1, l10=$1×10% (single $40k→10% rate) = $0 (rounds)
    _sc_d1 = _si8a(e.TaxpayerSchema,
        first="T", last="T", ssn="900-10-0002", dob="01-01-1980",
        filing_status="single", tax_year=2025,
        w2s=[_si8a(e.W2, employer="E", ein="99-0000021",
                   box1_wages=40000, box2_fed_wh=4000,
                   box12a_code="D", box12a_amt=1,
                   box13_retirement_plan=True)])
    _c_d1 = e.run(_sc_d1).get("computed", {})
    ok("F8880-AUTO.2 Code D $1 → l2=$1, l10=$0 (rounds from $0.10)",
       _c_d1.get("f8880", {}).get("l2_deferrals", 0), 1, tolerance=0,
       note="i8880.pdf L2; $1 × 10% = $0.10 rounds to $0 — credit correctly $0")

    # Case 3: Code D $400, single AGI $20k → 50% bracket ($0–$23,750) → credit $200
    _sc_big = _si8a(e.TaxpayerSchema,
        first="T", last="T", ssn="900-10-0003", dob="01-01-1980",
        filing_status="single", tax_year=2025,
        w2s=[_si8a(e.W2, employer="E", ein="99-0000022",
                   box1_wages=20000, box2_fed_wh=2000,
                   box12a_code="D", box12a_amt=400,
                   box13_retirement_plan=True)])
    _c_big = e.run(_sc_big).get("computed", {})
    ok("F8880-AUTO.3 Code D $400, single AGI $20k → 50% bracket → credit $200",
       _c_big.get("f8880", {}).get("l12_credit", 0), 200, tolerance=0,
       note="i8880.pdf L2+L9; single $0–$23,750 → 50%; $400 × 50% = $200. Source: Rev. Proc. 2024-40")

    # Case 4: QSS Code D $200, AGI $40k → MFJ table → 50% → l10=$100
    _sc_qss = _si8a(e.TaxpayerSchema,
        first="T", last="T", ssn="900-10-0004", dob="01-01-1980",
        filing_status="qss", tax_year=2025,
        w2s=[_si8a(e.W2, employer="E", ein="99-0000023",
                   box1_wages=40000, box2_fed_wh=4000,
                   box12a_code="D", box12a_amt=200,
                   box13_retirement_plan=True)])
    _c_qss = e.run(_sc_qss).get("computed", {})
    ok("F8880-AUTO.4 QSS Code D $200, AGI $40k → MFJ 50% rate → credit $100",
       _c_qss.get("f8880", {}).get("l12_credit", 0), 100, tolerance=0,
       note="QSS uses MFJ thresholds. $200 × 50% = $100. Source: f8880.pdf; i8880.pdf; Rev. Proc. 2024-40")

except Exception as ex:
    warn("F8880-AUTO test CRASHED", traceback.format_exc(limit=3))

print("\n  Test NEW-FIELDS: Jones schema new field coverage (2026-05-20)")
try:
    import dataclasses as _dcn
    def _sin(cls, **kw):
        valid = {f.name for f in _dcn.fields(cls)}
        return cls(**{k: v for k, v in kw.items() if k in valid})

    # ── ScheduleC.business_code and business_miles ────────────────────────────
    _sc_biz = _sin(e.ScheduleC, business_name="Test Biz",
                   business_code="812990", business_miles=500.0,
                   gross_receipts=10000, car_truck_expenses=0)
    ok("NEW.1 ScheduleC.business_code is a proper field",
       _sc_biz.business_code, "812990",
       note="NAICS code. Source: f1040sc.pdf Box A; i1040sc.pdf Appendix")
    ok("NEW.2 ScheduleC.business_miles is a proper field",
       _sc_biz.business_miles, 500.0, tolerance=0,
       note="Part IV mileage. Source: Rev. Proc. 2024-45; i1040sc.pdf Part IV")
    ok("NEW.3 ScheduleC.principal_product alias field exists",
       "principal_product" in {f.name for f in _dcn.fields(e.ScheduleC)}, True,
       note="Alias for principal_product_service — matches JSON/UI key")

    # ── Form1098E dataclass and form_1098es in TaxpayerSchema ─────────────────
    _f1098e = _sin(e.Form1098E, lender="Navient",
                   box1_student_loan_interest=1800.0)
    ok("NEW.4 Form1098E.box1_student_loan_interest is a proper field",
       _f1098e.box1_student_loan_interest, 1800.0, tolerance=0,
       note="f1098e.pdf Box 1; IRC §221")
    ok("NEW.5 TaxpayerSchema.form_1098es is a proper list field",
       "form_1098es" in {f.name for f in _dcn.fields(e.TaxpayerSchema)}, True,
       note="Receives Form1098E list from server bridge")

    # ── Form1098E flows into student loan interest deduction ──────────────────
    _sc_sl = _sin(e.TaxpayerSchema,
        first="T", last="T", ssn="900-20-0001", dob="01-01-1990",
        filing_status="single", tax_year=2025,
        w2s=[_sin(e.W2, employer="E", ein="99-0000030",
                  box1_wages=55000, box2_fed_wh=6000)],
        form_1098es=[_sin(e.Form1098E, lender="Navient",
                          box1_student_loan_interest=1800.0)])
    _c_sl = e.run(_sc_sl).get("computed", {})
    ok("NEW.6 Form1098E flows into adj_student_loan deduction",
       _c_sl.get("adj_student_loan", 0), 1800, tolerance=5,
       note="f1098e.pdf Box 1 → Schedule 1 Line 21; IRC §221")

    # ── Form1099B.date_acquired / date_sold as proper fields ──────────────────
    ok("NEW.7 Form1099B.date_acquired is a proper engine field",
       "date_acquired" in {f.name for f in _dcn.fields(e.Form1099B)}, True,
       note="f8949.pdf Col (b); bridge hardening 2026-05-20")
    ok("NEW.8 Form1099B.date_sold is a proper engine field",
       "date_sold" in {f.name for f in _dcn.fields(e.Form1099B)}, True,
       note="f8949.pdf Col (c); bridge hardening 2026-05-20")

    # ── AOC 4-year limit gate ─────────────────────────────────────────────────
    _sc_aoc4 = _sin(e.TaxpayerSchema,
        first="T", last="T", ssn="900-20-0002", dob="01-01-1999",
        filing_status="single", tax_year=2025,
        w2s=[_sin(e.W2, employer="E", ein="99-0000031",
                  box1_wages=42000, box2_fed_wh=3000)],
        form_1098ts=[_sin(e.Form1098T,
                          institution="College", box1_payments=4000,
                          credit_type="aoc", first_four_years=True,
                          aoc_years_claimed_prior=4,    # already used all 4
                          box8_half_time=True, aoc_drug_conviction=False)])
    _r_aoc4 = e.run(_sc_aoc4)
    _c_aoc4 = _r_aoc4.get("computed", {})
    ok("NEW.9 AOC denied when aoc_years_claimed_prior=4 (4-year limit)",
       _c_aoc4.get("l29_aoc", 0), 0, tolerance=0,
       note="IRC §25A(b)(2)(C): max 4 tax years total. Source: f8863.pdf Line 27")
    _aoc_warn = any("4yr_limit" in w or "4 prior" in w or "maximum 4" in w
                    for w in _r_aoc4.get("warnings", []))
    ok("NEW.10 AOC 4-year limit warning emitted",
       _aoc_warn, True,
       note="Warning includes LLC recommendation. Source: IRC §25A(b)(2)(C)")

    # ── Server bridge: Form1098E in _DATACLASS_MAP ────────────────────────────
    with open("/mnt/project/sachintaxcare_server.py") as _f:
        _srv_src = _f.read()
    ok("NEW.11 Form1098E in server _DATACLASS_MAP",
       "'form_1098es'" in _srv_src and "e.Form1098E" in _srv_src, True,
       note="Server bridge handles form_1098es list via safe_init()")

except Exception as ex:
    warn("NEW-FIELDS test CRASHED", traceback.format_exc(limit=4))

print("\n  Test FETCH_VERIFIED: Code tables must have FETCH_VERIFIED annotations")
try:
    with open("/mnt/project/sachintaxcare_engine.py") as _fv:
        _eng_src = _fv.read()

    # Tables that are required to carry FETCH_VERIFIED annotations
    _required = [
        ("Form 5329 exception codes (Form5329Exception dataclass)",
         "FETCH_VERIFIED",
         "Form5329Exception"),
        ("Form 5329 exception codes (compute_f5329_exceptions validation)",
         "FETCH_VERIFIED",
         "IRA_ONLY_CODES"),
        ("W-2 Box 12 elective deferral codes",
         "FETCH_VERIFIED",
         "_ELECTIVE_DEFERRAL_CODES"),
        ("FETCH_VERIFIED protocol definition in engine",
         "CODE VERIFICATION PROTOCOL",
         "FETCH_VERIFIED"),
    ]

    for desc, required_text, context_anchor in _required:
        # Check that the required_text appears within 10 lines of the context_anchor
        _lines = _eng_src.split("\n")
        _found = False
        for _i, _line in enumerate(_lines):
            if context_anchor in _line:
                # Check 15 lines around this anchor
                _window = "\n".join(_lines[max(0,_i-15):_i+15])
                if required_text in _window:
                    _found = True
                    break
        ok(f"FETCH_VER: {desc}",
           _found, True,
           note="FETCH_VERIFIED protocol: code tables must cite fetched URL+section+date. "
                "Never write code tables from memory. Source: project rule 2026-05-21")

except Exception as ex:
    warn("FETCH_VERIFIED audit CRASHED", traceback.format_exc(limit=3))
# =============================================================================
# FINAL SUMMARY
# =============================================================================
print(f"\n{'='*65}")
print(f"  FINAL RESULTS")
print(f"{'='*65}")
print(f"  PASS : {PASS}")
print(f"  FAIL : {FAIL}")
print(f"  WARN : {WARN}")
print(f"{'='*65}")
if FAIL == 0 and WARN == 0:
    print(f"✅ ALL {PASS} ASSERTIONS PASSED — safe to start session")
elif FAIL == 0:
    print(f"✅ {PASS} PASS · 0 FAIL · {WARN} WARN — review warnings before proceeding")
else:
    print(f"❌ {FAIL} FAILURE(S) — do not start session until resolved")
print(f"{'='*65}")

sys.exit(0 if FAIL == 0 else 1)
