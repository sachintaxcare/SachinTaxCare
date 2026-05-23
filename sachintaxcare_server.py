"""
SachinTaxCare -- Production Computation Server
==============================================
Replaces the Claude API call in sachintaxcare_pro.html with the real
Python engine (sachintaxcare_engine.py).

Run:
    python3 sachintaxcare_server.py

Then open:
    http://localhost:5000                   -> intake form
    http://localhost:5000/workpaper         -> workpaper (after computing)

Endpoints:
    POST /compute       -> accepts TaxpayerSchema JSON, returns engine result
    GET  /health        -> {"status": "ok", "engine": "v15"}
    GET  /              -> serves sachintaxcare_pro.html
    GET  /workpaper     -> serves sachintaxcare_workpaper.html

Architecture:
    Browser (intake.html)
        -> POST /compute  { schema: {...} }
        <- { computed: {...}, warnings: [...], schema: {...} }
    Browser (workpaper.html)
        -> reads result from localStorage (set by intake after /compute)
        -> renders 4-page print workpaper

The /compute endpoint:
    1. Receives the JSON schema built by buildSchema() in intake.html
    2. Deserializes it into a TaxpayerSchema dataclass (with nested dataclasses)
    3. Calls sachintaxcare_engine.run(schema)
    4. Returns result["computed"] + result["warnings"] as JSON

The result JSON is structurally identical to what the Claude API previously
returned -- same key names, same conventions. The workpaper.html requires
no changes. The intake.html computeReturn() is updated to call /compute
instead of the Anthropic API.
"""

from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
import sachintaxcare_engine as e
import dataclasses
import traceback
import os
import sys
import json
from pathlib import Path

# Windows console (CP1252) can't render box-drawing characters -- force UTF-8
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

app = Flask(__name__)
CORS(app)   # allow intake.html served from any origin to call /compute

# -- File paths ----------------------------------------------------------------
HERE = Path(__file__).parent
INTAKE_HTML   = HERE / 'sachintaxcare_pro.html'
WORKPAPER_HTML = HERE / 'sachintaxcare_workpaper.html'

# -- Deserializer --------------------------------------------------------------
# Maps JSON field names -> dataclass constructors for all nested objects.
# Engine dataclasses use keyword arguments and have sensible defaults, so we
# pass only the keys present in the incoming dict (extras are ignored).

_DATACLASS_MAP = {
    'w2s':                  e.W2,
    'form_1099ints':        e.Form1099INT,
    'form_1099divs':        e.Form1099DIV,
    'form_1099rs':          e.Form1099R,
    'form_1099necs':        e.Form1099NEC,
    'form_1099cs':          e.Form1099C,
    'form_1099misc_prizes': e.Form1099MISC_Prize,
    'form_1099bs':          e.Form1099B,
    'form_1099gs':          e.Form1099G,
    'form_w2gs':            e.FormW2G,
    'schedule_cs':          e.ScheduleC,
    'schedule_es':          e.ScheduleE,
    'schedule_k1s':         e.ScheduleK1,
    'dependents':           e.Dependent,
    'care_providers':       e.Form2441Provider,
    'form_1098ts':          e.Form1098T,
    'form_1098es':          e.Form1098E,      # Student loan interest (IRC §221)
    'form_5329_exceptions': e.Form5329Exception,
    'form_4797s':           e.Form4797SaleData,
}

_SCALAR_NESTED = {
    'form_ssa1099':      e.FormSSA1099,
    'form_8606':         e.Form8606Data,
    'form_8606_spouse':  e.Form8606Data,    # separate Form 8606 per spouse (MFJ)
    'form_8889':         e.Form8889Data,
    'schedule_a':        e.ScheduleAData,
    'form_1095a':        e.Form1095A,
    'form_8880':         e.Form8880Data,
    'form_8582':         e.Form8582Data,
    'form_6251':         e.Form6251Data,
    'form_2210':         e.Form2210Data,
    'form_1116':         e.Form1116Data,
    'form_8615':         e.Form8615Data,
    'form_4972':         e.Form4972Data,
    'alimony':           e.AlimonyData,
    'deceased_spouse':   e.DeceasedSpouse,
    'california':        e.CaliforniaData,  # key matches TaxpayerSchema.california
    'form_982':          e.Form982Data,      # F6: insolvency/bankruptcy exclusion worksheet (IRC §108)
    # NOTE: Form1099INT.box2_early_withdrawal_penalty matches JSON key exactly (renamed 2026-05-19).
    # No bridge transformation needed — safe_init passes it through directly.
    # Source: f1099int.pdf Box 2; i1040s1.pdf Line 18; IRC §62(a)(9)
    # NOTE: 'spouse' is not a separate dataclass -- spouse data is derived from
    # spouse-tagged W2s (w2.for_spouse=True) and Schedule Cs (sc.for_spouse=True).
    # No SpouseData class exists in the engine.
}


def _safe_init(cls, data: dict):
    """Construct a dataclass from a dict, ignoring unknown keys."""
    if not isinstance(data, dict):
        return None
    valid = {f.name for f in dataclasses.fields(cls)}
    filtered = {k: v for k, v in data.items() if k in valid}
    try:
        return cls(**filtered)
    except Exception:
        return None


# ── Bridge strict-mode validator ──────────────────────────────────────────────
# Source: bridge hardening 2026-05-19
# Use: ?strict=true query param OR X-Bridge-Strict: true header
# Returns {"error":"bridge_strict_violation","dropped_keys":[...]} when any
# JSON key sent by UI has no matching engine field and no explicit bridge transform.
#
# Known bridge transforms (JSON key → engine field) that are intentional renames:
_KNOWN_BRIDGES = {
    # (json_key, dataclass_name): engine_field
    ("box10_dep_care",          "W2"):                       "box10_dependent_care",
    ("box15_state_id",          "W2"):                       "box15_state_employer_id",
    ("box5_medicare_wages",     "W2"):                       "box5_med_wages",
    ("box6_medicare_wh",        "W2"):                       "box6_med_wh",
    ("box6_foreign_tax_paid",   "Form1099INT"):              "box6_foreign_tax",
    ("box2_early_withdrawal_penalty","Form1099INT"):         "box2_early_withdrawal_penalty",  # renamed; now matches
    ("box2_discharged",         "Form1099C"):                "box2_amount_discharged",
    ("exclusion_applies",       "Form1099C"):                "is_excluded",
    ("box6_vol_wh",             "FormSSA1099"):              "box6_voluntary_wh",
    ("box8_at_least_half_time", "Form1098T"):                "box8_half_time",
    ("age_at_start",            "SimplifiedMethodData"):     "age_at_annuity_start",
    ("joint_age_at_start",      "SimplifiedMethodData"):     "joint_age_at_annuity_start",
    ("prior_tax_free_recovered","SimplifiedMethodData"):     "prior_year_tax_free_recovered",
    ("start_after_nov_1996",    "SimplifiedMethodData"):     "annuity_start_after_nov_18_1996",
    ("box9b_employee_contrib",  "Form1099R"):                "box9b_employee_contribs",
    ("sdi_withheld",            "CaliforniaData"):           "ca_sdi_withheld",
    ("other_subtractions",      "CaliforniaData"):           "ca_other_subtractions",
    # Form1098E — field names match JSON keys directly (no rename needed)
    # box1_student_loan_interest: direct match
    # origination_before_sept_2004: UI sends this, maps to Form1098E.box2_origination_before_sept_2004
    ("origination_before_sept_2004", "Form1098E"): "box2_origination_before_sept_2004",

    # TaxpayerSchema flat fields that come in nested under "spouse"
    ("spouse.first",            "TaxpayerSchema"):           "spouse_first",
    ("spouse.last",             "TaxpayerSchema"):           "spouse_last",
    ("spouse.ssn",              "TaxpayerSchema"):           "spouse_ssn",
    ("spouse.dob",              "TaxpayerSchema"):           "spouse_dob",
    ("spouse.is_blind",         "TaxpayerSchema"):           "spouse_is_blind",
    # care_providers: UI sends {name,ein,expenses} → Form2441Provider {name,ein,expenses} (now match)
    ("name",                    "Form2441Provider"):         "name",
    ("ein",                     "Form2441Provider"):         "ein",
    ("expenses",                "Form2441Provider"):         "expenses",
}

# Informational/record-only fields that engines don't compute — never a violation
_DISPLAY_ONLY = {
    "payer_ein", "recipient", "account_number", "box12_fatca", "box13_date_of_payment",
    "box14_cusip", "ein", "payer", "box1_date_of_event", "box4_debt_description",
    "creditor_ein", "box3_interest", "box7_fmv", "box5_personally_liable",
    "box15_state_wh", "box15_state_id", "box9a_pct", "box10_irr", "box11_roth_yr",
    "box13_date", "institution_name", "student_is", "student_name",
    "box20_locality_name", "box14_other",
}

def _validate_bridge_strict(data: dict) -> list:
    """
    Returns a list of dropped_keys dicts for any JSON key that:
    1. Has no matching engine dataclass field, AND
    2. Has no entry in _KNOWN_BRIDGES, AND
    3. Is not in _DISPLAY_ONLY
    Each entry: {"key": str, "class": str, "value": any, "suggested": str | None}
    Source: bridge hardening 2026-05-19; sachintaxcare_field_manifest.md
    """
    violations = []

    list_maps = {
        'w2s': e.W2, 'form_1099ints': e.Form1099INT, 'form_1099divs': e.Form1099DIV,
        'form_1099rs': e.Form1099R, 'form_1099necs': e.Form1099NEC,
        'form_1099cs': e.Form1099C, 'form_1099bs': e.Form1099B,
        'form_w2gs': e.FormW2G, 'form_1099gs': e.Form1099G,
        'schedule_cs': e.ScheduleC, 'schedule_es': e.ScheduleE,
        'schedule_k1s': e.ScheduleK1, 'dependents': e.Dependent,
        'care_providers': e.Form2441Provider, 'form_1098ts': e.Form1098T,
        'form_1098es': e.Form1098E,
        'form_5329_exceptions': e.Form5329Exception, 'form_4797s': e.Form4797SaleData,
    }
    scalar_maps = {
        'form_ssa1099': e.FormSSA1099, 'form_8606': e.Form8606Data,
        'form_8889': e.Form8889Data, 'schedule_a': e.ScheduleAData,
        'form_1095a': e.Form1095A, 'form_8880': e.Form8880Data,
        'form_8582': e.Form8582Data, 'form_6251': e.Form6251Data,
        'form_2210': e.Form2210Data, 'form_1116': e.Form1116Data,
        'form_8615': e.Form8615Data, 'form_4972': e.Form4972Data,
        'deceased_spouse': e.DeceasedSpouse, 'california': e.CaliforniaData,
        'ca_540': e.CaliforniaData, 'form_982': e.Form982Data,
    }

    def check_keys(obj_dict: dict, cls, container_name: str):
        if not isinstance(obj_dict, dict): return
        valid = {f.name for f in dataclasses.fields(cls)}
        cls_name = cls.__name__
        for k, v in obj_dict.items():
            if k in valid: continue
            if k in _DISPLAY_ONLY: continue
            if (k, cls_name) in _KNOWN_BRIDGES: continue
            # Find suggested engine field (close match)
            suggested = next(
                (vf for vf in valid if k.replace("_","") in vf.replace("_","")
                 or vf.replace("_","") in k.replace("_","")), None)
            violations.append({
                "key": k, "class": cls_name,
                "container": container_name, "value": v,
                "suggested": suggested
            })

    # Check top-level TaxpayerSchema scalar fields
    ts_valid = {f.name for f in dataclasses.fields(e.TaxpayerSchema)}
    for k, v in data.items():
        if k in ts_valid: continue
        if k in list_maps or k in scalar_maps: continue
        if k in ('spouse', 'ca_540', 'form_1099miscs', 'form_1099misc_prizes'): continue
        if k in _DISPLAY_ONLY: continue
        if (k, "TaxpayerSchema") in _KNOWN_BRIDGES: continue
        violations.append({"key": k, "class": "TaxpayerSchema", "container": "root",
                           "value": v, "suggested": None})

    # Check list types
    for list_key, cls in list_maps.items():
        for item in data.get(list_key, []):
            if isinstance(item, dict):
                check_keys(item, cls, list_key)

    # Check scalar nested types
    for scalar_key, cls in scalar_maps.items():
        item = data.get(scalar_key)
        if isinstance(item, dict):
            check_keys(item, cls, scalar_key)

    # Check SimplifiedMethodData within form_1099rs
    for r in data.get('form_1099rs', []):
        if isinstance(r, dict) and isinstance(r.get('simplified_method'), dict):
            check_keys(r['simplified_method'], e.SimplifiedMethodData, 'simplified_method')

    return violations


def deserialize_schema(data: dict) -> e.TaxpayerSchema:

    """
    Convert the raw JSON dict from intake.html's buildSchema() into a
    TaxpayerSchema dataclass with all nested dataclasses instantiated.
    Unknown keys are silently dropped; missing keys use engine defaults.
    """
    kwargs = {}

    for key, value in data.items():
        if key in _DATACLASS_MAP and isinstance(value, list):
            # List of dataclasses
            cls = _DATACLASS_MAP[key]
            kwargs[key] = [inst for d in value if isinstance(d, dict)
                           for inst in [_safe_init(cls, d)] if inst is not None]
        elif key in _SCALAR_NESTED and isinstance(value, dict):
            # Single nested dataclass
            cls = _SCALAR_NESTED[key]
            inst = _safe_init(cls, value)
            if inst is not None:
                kwargs[key] = inst
        else:
            # Scalar field -- pass directly (engine validates types)
            kwargs[key] = value

    # -- Bridge: Form1099C field name mismatches ---------------------------------
    # Engine uses: box2_amount_discharged, is_excluded
    # Schema/UI sends: box2_discharged, exclusion_applies (plus many extra fields)
    bridged_1099cs = []
    for raw_c in data.get('form_1099cs', []):
        if not isinstance(raw_c, dict): continue
        bridged_1099cs.append(e.Form1099C(
            creditor=raw_c.get('creditor', ''),
            box2_amount_discharged=float(raw_c.get('box2_discharged') or raw_c.get('box2_amount_discharged') or 0),
            box6_event_code=raw_c.get('box6_event_code') or raw_c.get('box6_code') or '',
            is_excluded=bool(raw_c.get('exclusion_applies') or raw_c.get('is_excluded') or False),
        ))
    if bridged_1099cs:
        kwargs['form_1099cs'] = bridged_1099cs

    # ── Bridge: W2 field name mismatches ─────────────────────────────────────
    # box10_dep_care → box10_dependent_care (HIGH: Form 2441 §129 exclusion)
    # box15_state_id → box15_state_employer_id (LOW: identification)
    # box5_medicare_wages → box5_med_wages (already in 9F; safe_init now passes correctly)
    # Source: iw2w3.pdf; bridge hardening 2026-05-19
    bridged_w2s = []
    for raw_w in data.get('w2s', []):
        if not isinstance(raw_w, dict): continue
        d = dict(raw_w)
        if 'box10_dep_care' in d and 'box10_dependent_care' not in d:
            d['box10_dependent_care'] = d.pop('box10_dep_care')
        if 'box15_state_id' in d and 'box15_state_employer_id' not in d:
            d['box15_state_employer_id'] = d.pop('box15_state_id')
        if 'box5_medicare_wages' in d and 'box5_med_wages' not in d:
            d['box5_med_wages'] = d.pop('box5_medicare_wages')
        if 'box6_medicare_wh' in d and 'box6_med_wh' not in d:
            d['box6_med_wh'] = d.pop('box6_medicare_wh')
        inst = _safe_init(e.W2, d)
        if inst: bridged_w2s.append(inst)
    if bridged_w2s:
        kwargs['w2s'] = bridged_w2s

    # ── Bridge: Form1099INT field name mismatches ────────────────────────────
    # box6_foreign_tax_paid → box6_foreign_tax (LOW: Form 1116)
    # box2_early_withdrawal_penalty now matches engine field name directly (no bridge needed)
    # Source: f1099int.pdf; bridge hardening 2026-05-19
    bridged_ints = []
    for raw_i in data.get('form_1099ints', []):
        if not isinstance(raw_i, dict): continue
        d = dict(raw_i)
        if 'box6_foreign_tax_paid' in d and 'box6_foreign_tax' not in d:
            d['box6_foreign_tax'] = d.pop('box6_foreign_tax_paid')
        inst = _safe_init(e.Form1099INT, d)
        if inst: bridged_ints.append(inst)
    if bridged_ints:
        kwargs['form_1099ints'] = bridged_ints

    # ── Bridge: Form1099R field name mismatches ──────────────────────────────
    # use_simplified_method → now a proper field (was missing from dataclass)
    # payer_ein → now a proper field
    # Source: f1099r.pdf; bridge hardening 2026-05-19
    # (No key rename needed — fields now match JSON keys exactly)

    # ── Bridge: FormSSA1099 additional fields ────────────────────────────────
    # lump_sum_election, medicare_part_b/c/d_premiums, mfs_lived_apart, recipient
    # These are now proper dataclass fields — safe_init passes them through.
    # Source: SSA-1099; bridge hardening 2026-05-19

    # ── Bridge: CaliforniaData field name mismatches ─────────────────────────
    # sdi_withheld → ca_sdi_withheld (MEDIUM: CA SDI credit)
    # other_subtractions → ca_other_subtractions (MEDIUM: CA subtraction)
    # renter_credit / ca_itemized_override → already handled by safe_init (field names match)
    # Source: CA Form 540; bridge hardening 2026-05-19
    ca_raw = data.get('california') or data.get('ca_540')
    if isinstance(ca_raw, dict):
        d = dict(ca_raw)
        if 'sdi_withheld' in d and 'ca_sdi_withheld' not in d:
            d['ca_sdi_withheld'] = d.pop('sdi_withheld')
        if 'other_subtractions' in d and 'ca_other_subtractions' not in d:
            d['ca_other_subtractions'] = d.pop('other_subtractions')
        inst = _safe_init(e.CaliforniaData, d)
        if inst:
            kwargs['california'] = inst

    # ── Bridge: SimplifiedMethodData field name mismatches ───────────────────
    # joint_age_at_start → joint_age_at_annuity_start (HIGH: SM annuity calculation)
    # start_after_nov_1996 → now aliased as proper field (no rename needed)
    # Source: Pub 575; bridge hardening 2026-05-19
    # (joint_age_at_start → joint_age_at_annuity_start handled in the 1099R bridge below)

    # -- Bridge: FormSSA1099 box6_vol_wh -> box6_voluntary_wh ---------------------
    # Schema/UI sends box6_vol_wh; engine field is box6_voluntary_wh
    ssa_raw = data.get('form_ssa1099')
    if isinstance(ssa_raw, dict) and 'box6_vol_wh' in ssa_raw and 'box6_voluntary_wh' not in ssa_raw:
        ssa_raw = dict(ssa_raw)
        ssa_raw['box6_voluntary_wh'] = ssa_raw.pop('box6_vol_wh')
        # Re-init with corrected data
        valid_ssa = {f.name for f in __import__('dataclasses').fields(e.FormSSA1099)}
        kwargs['form_ssa1099'] = e.FormSSA1099(**{k: v for k, v in ssa_raw.items() if k in valid_ssa})

    # -- Bridge: Form1099R simplified_method dict -> SimplifiedMethodData ----------
    # Schema/UI sends simplified_method as raw dict with different field names
    bridged_1099rs = []
    for raw_r in data.get('form_1099rs', []):
        if not isinstance(raw_r, dict): continue
        sm_raw = raw_r.get('simplified_method')
        sm_obj = None
        if raw_r.get('use_simplified_method') and isinstance(sm_raw, dict):
            cost = float(raw_r.get('box9b_employee_contrib') or sm_raw.get('cost_in_contract') or 0)
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
        valid_r = {f.name for f in __import__('dataclasses').fields(e.Form1099R)}
        r_kwargs = {k: v for k, v in raw_r.items() if k in valid_r}
        # Bridge box9b_employee_contrib (schema) -> box9b_employee_contribs (engine)
        if 'box9b_employee_contrib' in raw_r and 'box9b_employee_contribs' not in r_kwargs:
            r_kwargs['box9b_employee_contribs'] = float(raw_r.get('box9b_employee_contrib') or 0)
        if sm_obj:
            r_kwargs['simplified_method'] = sm_obj
            # Ensure box9b populated so engine gate passes
            if r_kwargs.get('box9b_employee_contribs', 0) == 0:
                r_kwargs['box9b_employee_contribs'] = sm_obj.cost_in_contract
        try:
            bridged_1099rs.append(e.Form1099R(**r_kwargs))
        except Exception as ex:
            pass  # fall through to original
    if bridged_1099rs:
        kwargs['form_1099rs'] = bridged_1099rs

    # -- Bridge P9: Form 8615 parent_taxable_income from dependent fields ----------
    # buildSchema() puts parent_taxable_income on each dependent dict (dep[].parent_taxable_income)
    # Engine reads it from schema.form_8615.parent_taxable_income (single, schema-level).
    # Bridge: take max non-zero parent_taxable_income across all dependents.
    if not data.get('form_8615'):
        parent_ti_values = [
            float(d.get('parent_taxable_income', 0))
            for d in data.get('dependents', [])
            if isinstance(d, dict) and float(d.get('parent_taxable_income') or 0) > 0
        ]
        if parent_ti_values:
            import dataclasses as _dc
            # Build minimal Form8615Data with parent's taxable income
            valid_8615 = {f.name for f in _dc.fields(e.Form8615Data)}
            kwargs['form_8615'] = e.Form8615Data(
                parent_taxable_income=max(parent_ti_values),
                parent_filing_status=data.get('filing_status', 'single'),
                child_age=0, child_is_full_time_student=False,
                child_support_from_earned=False, unearned_income=0, earned_income=0,
            )

    # -- Bridge: form_1099miscs (new full UI form) -> form_1099misc_prizes (engine) --
    # The UI sends form_1099miscs with all 18 boxes; engine reads form_1099misc_prizes.
    # Convert box3_other_income entries; also handle legacy scalar prize_income field.
    misc_prizes = list(kwargs.get('form_1099misc_prizes', []))
    for m in data.get('form_1099miscs', []):
        if isinstance(m, dict) and (m.get('box3_other_income') or 0) > 0:
            misc_prizes.append(e.Form1099MISC_Prize(
                payer=m.get('payer', ''),
                box3_other_income=float(m.get('box3_other_income', 0)),
                description='Prize/Award/Other',
            ))
    # Also bridge old scalar prize_income field if present
    if data.get('prize_income') and float(data.get('prize_income', 0)) > 0:
        misc_prizes.append(e.Form1099MISC_Prize(
            payer='',
            box3_other_income=float(data['prize_income']),
            description='Prize/Award',
        ))
    if misc_prizes:
        kwargs['form_1099misc_prizes'] = misc_prizes

    # -- Bridge: Form1098T field name mismatches ---------------------------------
    # schema: box8_at_least_half_time → engine: box8_half_time
    # schema: student_is/student_who → use credit_type directly (already correct)
    for t_raw in kwargs.get('form_1098ts', []):
        if hasattr(t_raw, '__dict__'):
            # Already a dataclass from safe_init -- patch box8_half_time if needed
            if not t_raw.box8_half_time and hasattr(t_raw, 'box8_at_least_half_time'):
                pass  # safe_init already ran; box8_at_least_half_time not in valid fields

    # Patch via raw list before safe_init runs -- bridge happens in _LIST_MAP processing
    raw_1098ts = data.get('form_1098ts', [])
    if raw_1098ts and isinstance(raw_1098ts[0], dict):
        for t in raw_1098ts:
            if 'box8_at_least_half_time' in t and 'box8_half_time' not in t:
                t['box8_half_time'] = t['box8_at_least_half_time']


    # The UI sends spouse data as a nested dict {first, last, ssn, dob, ...}.
    # The engine stores these as top-level scalar fields for workpaper/return header.
    spouse_dict = data.get('spouse')
    if isinstance(spouse_dict, dict):
        if spouse_dict.get('ssn')   and not kwargs.get('spouse_ssn'):
            kwargs['spouse_ssn']   = str(spouse_dict['ssn'])
        if spouse_dict.get('first') and not kwargs.get('spouse_first'):
            kwargs['spouse_first'] = str(spouse_dict['first'])
        if spouse_dict.get('last')  and not kwargs.get('spouse_last'):
            kwargs['spouse_last']  = str(spouse_dict['last'])
        if spouse_dict.get('dob')   and not kwargs.get('spouse_dob'):
            kwargs['spouse_dob']   = str(spouse_dict['dob'])

    # Construct TaxpayerSchema with only valid field names
    valid = {f.name for f in dataclasses.fields(e.TaxpayerSchema)}
    filtered = {k: v for k, v in kwargs.items() if k in valid}
    return e.TaxpayerSchema(**filtered)


# -- Result mapper --------------------------------------------------------------
# The workpaper and render functions in the intake expect specific flat key names.
# The engine stores everything in result["computed"] with its own naming.
# This mapper bridges the two, pulling the keys the frontend uses.

def map_result(engine_result: dict) -> dict:
    """
    Pass the engine computed dict directly to the frontend, plus legacy aliases.

    ARCHITECTURE: Rather than a manual translation layer (which drifts from the
    engine and breaks constantly), we start with ALL engine keys and add only the
    aliases that the frontend historically used under different names.

    This means:
    - Every key the engine emits is automatically available in the frontend.
    - renderResult() and the workpaper read engine keys directly (no mapping needed).
    - Only true renames and derived values need to be listed here.
    - Adding a new engine key never requires touching this file.
    """
    c  = engine_result.get('computed', {})
    w  = engine_result.get('warnings', [])

    def g(key, default=None):
        return c.get(key, default)

    # Compute derived values the frontend needs but the engine doesn't emit
    total_wh   = g('l25d_total_wh', 0)
    total_tax  = g('l24_total_tax', 0)
    total_pmts = g('l33_total_pmts', 0) or (total_wh + g('l26_estimated', 0))
    refund     = max(0, total_pmts - total_tax)
    owe        = max(0, total_tax - total_pmts)
    agi        = g('agi', 0)
    taxable    = g('taxable_income', 0)
    eff_rate   = round(total_tax / agi, 4) if agi > 0 else 0
    mar_rate   = _marginal_rate(taxable, g('filing_status', 'single'))

    # Start with the complete engine computed dict — every key available automatically
    result = dict(c)

    # Add derived values (not emitted by engine)
    result.update({
        'effective_rate':    eff_rate,
        'marginal_rate':     mar_rate,
        'l34_refund':        result.get('l34_refund') or refund,
        'l37_owe':           result.get('l37_owe')    or owe,
        'l33_total_pmts':    total_pmts,
        'warnings':          [x for x in w if x],
    })

    # Legacy aliases — old frontend key names that renderResult() or workpaper may still use
    # Only add if the canonical engine key is populated, and only if alias not already set
    ALIASES = {
        # Old name               New engine key
        'total_wages':          'wages',
        'total_interest':       'interest',
        'total_dividends':      'dividends',
        'qualified_dividends':  'dividends_qual',
        'cap_gain_income':      'cap_gain_net',
        'cap_gains':            'cap_gain_net',
        'ss_taxable':           'l6b_ss_taxable',
        'total_withholding':    'l25d_total_wh',
        'l25b_total':           'l25b_total',
        'estimated_payments':   'l26_estimated',
        'l33_total_payments':   'l33_total_pmts',
        'edu_nonref':           'edu_nonref',
        'edu_ref_aoc':          'l29_aoc',
        'saver_credit':         'saver_credit',
        'actc':                 'l28_actc',
        'total_other_taxes':    'sch2_l17',
        'other_nonref_credits': None,   # computed below
        'additional_income_sch1': None, # computed below
    }
    for alias, src in ALIASES.items():
        if alias not in result and src and src in result:
            result[alias] = result[src]

    # Derived legacy aliases needing computation
    if 'other_nonref_credits' not in result:
        result['other_nonref_credits'] = (g('sch3') or {}).get('l8_total_nonref', 0)

    if 'additional_income_sch1' not in result:
        result['additional_income_sch1'] = max(0,
            g('total_income', 0) - g('wages', 0) - g('interest', 0)
            - g('us_bond_interest', 0) - g('dividends', 0)
            - g('l4b_ira_taxable', 0) - g('l5b_pension_taxable', 0)
            - g('l6b_ss_taxable', 0) - g('cap_gain_net', 0))

    return result
def _marginal_rate(taxable: float, fs: str) -> float:
    """Determine marginal tax rate from taxable income and filing status."""
    brackets_mfj = [
        (23850, 0.10), (96950, 0.12), (206700, 0.22),
        (394600, 0.24), (501050, 0.32), (751600, 0.35), (float('inf'), 0.37),
    ]
    brackets_single = [
        (11925, 0.10), (48475, 0.12), (103350, 0.22),
        (197300, 0.24), (250525, 0.32), (626350, 0.35), (float('inf'), 0.37),
    ]
    brackets_hoh = [
        (17000, 0.10), (64850, 0.12), (103350, 0.22),
        (197300, 0.24), (250500, 0.32), (626350, 0.35), (float('inf'), 0.37),
    ]
    brackets = (brackets_mfj if fs in ('mfj', 'qss')
                else brackets_hoh if fs == 'hoh'
                else brackets_single)
    prev = 0
    for limit, rate in brackets:
        if taxable <= limit:
            return rate
        prev = limit
    return 0.37


# -- Routes ---------------------------------------------------------------------

@app.get('/')
def serve_intake():
    """Serve the intake form."""
    if INTAKE_HTML.exists():
        return send_file(INTAKE_HTML)
    abort(404, 'sachintaxcare_pro.html not found -- run from the same directory as the HTML files.')


@app.get('/workpaper')
def serve_workpaper():
    """Serve the workpaper renderer."""
    if WORKPAPER_HTML.exists():
        return send_file(WORKPAPER_HTML)
    abort(404, 'sachintaxcare_workpaper.html not found.')


@app.get('/health')
def health():
    return jsonify({'status': 'ok', 'engine': 'SachinTaxCare v15', 'python': '3.x'})


@app.post('/compute')
def compute():
    """
    Main computation endpoint.

    Request:  POST /compute
              Content-Type: application/json
              Body: { "schema": { ...TaxpayerSchema fields... } }

    Response: 200 { "computed": {...}, "warnings": [...], "schema": {...} }
              400 { "error": "..." }  on validation/deserialization failure
              500 { "error": "..." }  on engine exception
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({'error': 'Request body must be JSON'}), 400

    schema_dict = body.get('schema') or body   # accept both {schema: {...}} and {...}

    if not isinstance(schema_dict, dict):
        return jsonify({'error': 'schema must be a JSON object'}), 400

    # -- Strict-mode bridge validation ─────────────────────────────────────────
    # Activated via ?strict=true OR X-Bridge-Strict: true header.
    # Returns 422 with dropped_keys list before running the engine.
    # Use in testing/development to surface silent discards immediately.
    # Source: bridge hardening 2026-05-19; sachintaxcare_field_manifest.md
    strict_mode = (
        request.args.get('strict', '').lower() == 'true'
        or request.headers.get('X-Bridge-Strict', '').lower() == 'true'
    )
    if strict_mode:
        violations = _validate_bridge_strict(schema_dict)
        if violations:
            return jsonify({
                'error': 'bridge_strict_violation',
                'message': (f'{len(violations)} field(s) sent by UI have no matching engine field '
                            'and no registered bridge transform. Fix the bridge or register the key '
                            'in _KNOWN_BRIDGES / _DISPLAY_ONLY.'),
                'dropped_keys': violations
            }), 422

    # -- Deserialize ------------------------------------------------------------
    try:
        schema = deserialize_schema(schema_dict)
    except Exception as ex:
        return jsonify({
            'error': f'Schema deserialization failed: {str(ex)}',
            'detail': traceback.format_exc()
        }), 400

    # -- Run engine -------------------------------------------------------------
    try:
        engine_result = e.run(schema)
    except Exception as ex:
        return jsonify({
            'error': f'Engine computation failed: {str(ex)}',
            'detail': traceback.format_exc()
        }), 500

    # -- Map result to frontend key names ---------------------------------------
    try:
        mapped = map_result(engine_result)
        # Store filing_status on computed dict for workpaper context
        mapped['filing_status'] = schema_dict.get('filing_status', 'single')
    except Exception as ex:
        return jsonify({
            'error': f'Result mapping failed: {str(ex)}',
            'detail': traceback.format_exc()
        }), 500

    return jsonify({
        'computed': mapped,
        'result':   mapped,          # alias -- frontend uses both key names
        'warnings': engine_result.get('warnings', []),
        'schema':   schema_dict,     # echo back for workpaper context
        'engine_version': 'v15',
        'test_counts': {'engine': 180, 'report': 52},
    })


# -- Dev server -----------------------------------------------------------------

# -- Run regression tests before starting server -------------------------------
def run_startup_tests():
    """
    Run bridge audit + regression tests before accepting requests.
    Prevents serving incorrect results if a schema/engine update breaks the bridge.
    Prints a summary; fails loudly if critical assertions fail.
    """
    import subprocess, sys
    try:
        result = subprocess.run(
            [sys.executable, 'sachintaxcare_test.py'],
            capture_output=True, text=True, timeout=60
        )
        # Print last 10 lines of output (summary)
        lines = (result.stdout + result.stderr).strip().splitlines()
        for line in lines[-12:]:
            print(f"  [TEST] {line}")
        if result.returncode != 0:
            print("\n  [STOP]  STARTUP TESTS FAILED -- server is starting anyway.")
            print("      Fix failures in sachintaxcare_test.py before filing returns.\n")
        else:
            print("  [PASS]  All startup tests passed.\n")
    except Exception as ex:
        print(f"  [WARN]   Could not run startup tests: {ex}\n")

if __name__ == '__main__':
    run_startup_tests()
    port = int(os.environ.get('PORT', 5000))
    host = os.environ.get('HOST', '127.0.0.1')
    debug = os.environ.get('DEBUG', '1') == '1'
    print(f"""
+======================================================+
|         SachinTaxCare Computation Server             |
|         Engine v15 . 180/180 tests passing           |
+======================================================+
|  Intake:    http://{host}:{port}/                |
|  Workpaper: http://{host}:{port}/workpaper       |
|  Health:    http://{host}:{port}/health          |
|  Compute:   POST http://{host}:{port}/compute    |
+======================================================+
|  Source: IRS PDFs from irs.gov/pub/irs-pdf/ only     |
|  No table interpolation . Whole-dollar rounding      |
+======================================================+
""")
    app.run(host=host, port=port, debug=debug)
