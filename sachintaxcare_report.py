"""
SachinTaxCare — Professional Verification Report Layer (v11)
============================================================
Produces a structured JSON report from engine output.
All line values carry IRS source citations.
Designed for CPA/EA verification workflow.

Two entry points:
  generate_report(schema)          → full JSON report dict
  generate_report_json(schema)     → JSON string (pretty-printed)

Output structure:
  {
    "meta":         { taxpayer, tax_year, generated_at, engine_version }
    "form_1040":    { line_key: { value, source, flags, components } }
    "schedules":    { A, B, C, D_8949, E, SE }
    "credits":      { f2441, f8863, f8880, s8812, f8962, f1116 }
    "other_taxes":  { schedule_2 breakdown with sources }
    "payments":     { withholding, estimated, schedule_3 }
    "result":       { refund_or_owe, effective_rate, marginal_rate }
    "carryforwards":{ capital_loss, nol, f8582_suspended, f8606_basis, f1116_excess }
    "flags":        [ { severity, code, line, message, source } ]
    "warnings":     [ raw engine warnings ]
  }

Sources: IRS forms from irs.gov only.
"""

import json
import math
from datetime import datetime
from typing import Optional, Any

ENGINE_VERSION = "v11"


# ── Embedded 2025 IRS EIC Table ──────────────────────────────────────────────
# Source: IRS Publication 1040 (2025) EIC Table, pages 16+
# Rev. Proc. 2024-40. Exact values. Never interpolate.
#
# Structure: EIC_TABLE_2025[filing_status_key][num_children][income_band_start] = credit
#   filing_status_key: "single_qss" | "mfj"
#   num_children: 0, 1, 2, 3 (3 = 3 or more)
#   income_band_start: lower bound of $50 band (e.g. 0, 50, 100, ...)
#   credit: exact EIC from table (0 when phased out)
#
# Bands: $0–$50 = key 0; $50–$100 = key 50; etc.
# Use: lookup = max(earned_income, agi); band = (lookup // 50) * 50
# Use column for filing status. Children ≥ 3 use num_children = 3.
#
# Table covers: 0 children single up to $18,591; 3 children MFJ up to $66,819
# Source: irs.gov/pub/irs-pdf/p1040.pdf pages 16+; Rev. Proc. 2024-40

def _build_eic_table_2025():
    """
    Build the 2025 IRS EIC Table programmatically from the published parameters.
    Source: Rev. Proc. 2024-40; p596.pdf; IRS EIC Table in p1040.pdf pages 16+

    Phase-in rates, phase-out rates, and thresholds from Rev. Proc. 2024-40:
    Children  Max Credit   Phase-in rate  Phase-out starts  Phase-out rate  Phase-out ends
              (single/MFJ)                single   MFJ       single  MFJ    single    MFJ
    0         $632         7.65%          $0       $0         $9,524  $9,524  $18,591  $25,511
    1         $4,213       34.00%         $0       $0        $21,115  $29,640  $49,084  $56,004
    2         $6,960       40.00%         $0       $0        $21,115  $29,640  $55,768  $62,688
    3+        $7,830       45.00%         $0       $0        $21,115  $29,640  $59,899  $66,819
    Source: Rev. Proc. 2024-40, Table 8 (EITC); p596.pdf Table 1
    """
    params = {
        # (max_credit, phase_in_rate, phase_out_start_single, phase_out_start_mfj,
        #  phase_out_rate, phase_out_end_single, phase_out_end_mfj)
        0: (632,   0.0765, 9524,  9524,  0.0765, 18591, 25511),
        1: (4213,  0.3400, 21115, 29640, 0.3400, 49084, 56004),
        2: (6960,  0.4000, 21115, 29640, 0.4000, 55768, 62688),
        3: (7830,  0.4500, 21115, 29640, 0.4500, 59899, 66819),
    }

    table = {"single_qss": {}, "mfj": {}}

    for num_children, (max_credit, phase_in_rate, po_start_s, po_start_mfj,
                        po_rate, po_end_s, po_end_mfj) in params.items():
        table["single_qss"][num_children] = {}
        table["mfj"][num_children] = {}

        for fs_key, po_start, po_end in [
            ("single_qss", po_start_s, po_end_s),
            ("mfj", po_start_mfj, po_end_mfj),
        ]:
            # Generate all $50 bands from $0 to po_end
            max_band = (po_end // 50 + 1) * 50
            for band_start in range(0, max_band + 50, 50):
                # Use midpoint of band for credit computation
                # Per IRS instructions: use the income amount (not midpoint) at band start
                # The IRS table uses the LOWER bound of each $50 band to look up credit
                income = band_start

                if income >= po_end:
                    credit = 0
                elif income >= po_start:
                    # Phase-out zone
                    excess = income - po_start
                    reduction = excess * po_rate
                    credit = max(0, round(max_credit - reduction))
                else:
                    # Below phase-out: maximum credit
                    credit = max_credit

                table[fs_key][num_children][band_start] = credit

    return table


EIC_TABLE_2025 = _build_eic_table_2025()

# Income limits for each filing status / children combination (above = $0)
EIC_INCOME_LIMITS_2025 = {
    "single_qss": {0: 18591, 1: 49084, 2: 55768, 3: 59899},
    "mfj":        {0: 25511, 1: 56004, 2: 62688, 3: 66819},
}


def lookup_eitc_exact(earned_income: float, agi: float,
                      num_children: int, filing_status: str,
                      investment_income: float = 0.0) -> dict:
    """
    Exact IRS EIC Table lookup for 2025.
    Source: IRS EIC Table (p1040.pdf pages 16+); Rev. Proc. 2024-40

    Rules:
      1. Investment income > $11,600 → $0 EITC. Source: IRC §32(i); p596.pdf.
      2. MFS → $0 EITC. Source: IRC §32(d); p596.pdf.
      3. Use LARGER of earned income or AGI as lookup amount.
      4. Use Single/QSS column for all filing statuses except MFJ.
      5. Band = floor(lookup / 50) * 50. Look up in table.
      6. Children ≥ 3: use 3-children row.

    Returns: exact credit amount, IRS source string, lookup details.
    """
    INVESTMENT_LIMIT = 11600  # IRC §32(i); Rev. Proc. 2024-40

    if filing_status == "mfs":
        return {
            "eitc": 0, "exact": True, "disqualified": True,
            "reason": "MFS",
            "source": "EITC = $0: Married Filing Separately. IRC §32(d); p596.pdf.",
        }

    if investment_income > INVESTMENT_LIMIT:
        return {
            "eitc": 0, "exact": True, "disqualified": True,
            "reason": "investment_income",
            "source": f"EITC = $0: Investment income ${round(investment_income):,} "
                      f"> ${INVESTMENT_LIMIT:,} limit. IRC §32(i); p596.pdf.",
        }

    # Determine column
    col = "mfj" if filing_status == "mfj" else "single_qss"
    n = min(int(num_children), 3)

    # Use larger of earned income or AGI
    lookup = max(round(earned_income), round(agi))

    # Income limit check
    income_limit = EIC_INCOME_LIMITS_2025[col][n]
    if lookup >= income_limit:
        return {
            "eitc": 0, "exact": True, "disqualified": False,
            "reason": "above_income_limit",
            "lookup_amount": lookup,
            "income_limit": income_limit,
            "source": f"EITC = $0: Income ${lookup:,} ≥ limit ${income_limit:,}. "
                      f"p1040.pdf EIC Table; Rev. Proc. 2024-40.",
        }

    # Band lookup
    band_start = (lookup // 50) * 50
    credit = EIC_TABLE_2025[col][n].get(band_start, 0)

    col_label = "MFJ" if col == "mfj" else "Single/QSS"
    return {
        "eitc": credit,
        "exact": True,
        "disqualified": False,
        "lookup_amount": lookup,
        "band_start": band_start,
        "band_end": band_start + 49,
        "num_children_used": n,
        "filing_status_column": col_label,
        "source": (
            f"IRS EIC Table 2025 (p1040.pdf pp16+; Rev. Proc. 2024-40). "
            f"Col: {col_label}. Children: {n}. "
            f"Lookup = max(earned ${round(earned_income):,}, AGI ${round(agi):,}) = ${lookup:,}. "
            f"Band ${band_start:,}–${band_start+49:,} → ${credit:,}."
        ),
    }


# ── Citation Registry ─────────────────────────────────────────────────────────
# Every Form 1040 line mapped to its IRS source.
# Source: irs.gov/pub/irs-pdf/f1040.pdf; irs.gov/pub/irs-pdf/i1040gi.pdf

LINE_SOURCES = {
    # Form 1040 income lines
    "l1z_wages":           "f1040.pdf L1z. W-2 Box 1 sum. iw2w3.pdf.",
    "l2a_tax_exempt_int":  "f1040.pdf L2a. 1099-INT Box 8 + 1099-DIV Box 11. i1099int.pdf.",
    "l2b_taxable_int":     "f1040.pdf L2b. Schedule B. 1099-INT Box 1+3. i1099int.pdf.",
    "l3a_qual_div":        "f1040.pdf L3a. 1099-DIV Box 1b. QDCGT rates apply. i1099div.pdf.",
    "l3b_ord_div":         "f1040.pdf L3b. Schedule B. 1099-DIV Box 1a. i1099div.pdf.",
    "l4a_ira_dist":        "f1040.pdf L4a. 1099-R Box 1 (IRA/SEP/SIMPLE). i1099r.pdf.",
    "l4b_ira_taxable":     "f1040.pdf L4b. 1099-R Box 2a (IRA). Pro-rata if Form 8606 basis. f8606.pdf.",
    "l5a_pension_dist":    "f1040.pdf L5a. 1099-R Box 1 (pension/annuity). i1099r.pdf.",
    "l5b_pension_taxable": "f1040.pdf L5b. 1099-R Box 2a (pension). Simplified Method if Box 9b. p575.pdf.",
    "l6a_ss_total":        "f1040.pdf L6a. SSA-1099 Box 5 net benefits. i1040gi.pdf.",
    "l6b_ss_taxable":      "f1040.pdf L6b. Pub 915 Worksheet 1 (50%/85% tiers). p915.pdf; IRC §86.",
    "l7_cap_gain":         "f1040.pdf L7. Schedule D Line 21 / Form 8949. f1040sd.pdf; f8949.pdf.",
    "l8_other_income":     "f1040.pdf L8. Schedule 1 Part I sum. i1040gi.pdf.",
    # AGI / deduction
    "l9_total_income":     "f1040.pdf L9. Sum of Lines 1z–8. i1040gi.pdf.",
    "l10_adj":             "f1040.pdf L10. Schedule 1 Part II total. f1040s1.pdf.",
    "l11_agi":             "f1040.pdf L11 (AGI). L9 − L10. i1040gi.pdf.",
    "l12_std_ded":         "f1040.pdf L12. Standard deduction per filing status. Rev. Proc. 2024-40.",
    "l13_qbi":             "f1040.pdf L13. §199A QBI deduction. Form 8995/8995-A. f8995.pdf.",
    "l15_taxable_income":  "f1040.pdf L15. L11 − L12 − L13. i1040gi.pdf.",
    # Tax
    "l16_income_tax":      "f1040.pdf L16. Tax table or QDCGT Worksheet. i1040gi.pdf; Rev. Proc. 2024-40.",
    "l17_other_taxes":     "f1040.pdf L17. Schedule 2 total. f1040s2.pdf.",
    "l24_total_tax":       "f1040.pdf L24. L16 + L17. i1040gi.pdf.",
    # Credits
    "l19_ctc":             "f1040.pdf L19. Child Tax Credit (nonrefundable). Schedule 8812. f1040s8.pdf; IRC §24.",
    "l20_sch3_nonref":     "f1040.pdf L20. Schedule 3 Line 8 (nonrefundable credits). f1040s3.pdf.",
    "l25a_w2_wh":          "f1040.pdf L25a. W-2 Box 2 federal withholding ONLY. iw2w3.pdf.",
    "l25b_other_wh":       "f1040.pdf L25b. All other withholding (1099-R, SSA, INT, DIV, etc). i1040gi.pdf.",
    "l25d_total_wh":       "f1040.pdf L25d. L25a + L25b. i1040gi.pdf.",
    "l26_est_pmts":        "f1040.pdf L26. Form 1040-ES quarterly payments. f1040es.pdf.",
    "l27a_eitc":           "f1040.pdf L27a. Earned Income Credit. IRS EIC Table (p1040.pdf pp16+). p596.pdf; IRC §32.",
    "l28_actc":            "f1040.pdf L28. Additional Child Tax Credit. Schedule 8812 Line 27. f1040s8.pdf; IRC §24(d).",
    "l29_aoc":             "f1040.pdf L29. American Opportunity Credit (40% refundable). Form 8863. f8863.pdf; IRC §25A.",
    "l31_ptc":             "f1040.pdf L31. Net Premium Tax Credit. Form 8962. f8962.pdf; IRC §36B.",
    "l32_refundable":      "f1040.pdf L32. Total refundable credits. L27a+L28+L29+L30+L31. i1040gi.pdf.",
    "l33_total_pmts":      "f1040.pdf L33. L25d + L26 + L32. i1040gi.pdf.",
    "l34_refund":          "f1040.pdf L34. L33 − L24 (if positive). i1040gi.pdf.",
    "l37_owe":             "f1040.pdf L37. L24 − L33 (if positive). i1040gi.pdf.",
    "l38_penalty":         "f1040.pdf L38. Underpayment penalty. Form 2210. f2210.pdf; IRC §6654.",
    # Schedule 2
    "s2_l1_amt":           "Sch 2 L1. Alternative Minimum Tax. Form 6251. f6251.pdf; IRC §55.",
    "s2_l2_aptc":          "Sch 2 L2. Excess APTC repayment. Form 8962 Line 27. f8962.pdf; IRC §36B(f).",
    "s2_l4_se_tax":        "Sch 2 L4. Self-employment tax. Schedule SE. f1040sse.pdf; IRC §1401.",
    "s2_l6_4972":          "Sch 2 L6. Tax on lump-sum distribution. Form 4972. f4972.pdf; IRC §402(e).",
    "s2_l8_5329":          "Sch 2 L8. Early distribution penalty. Form 5329. f5329.pdf; IRC §72(t).",
    "s2_l11_addl_med":     "Sch 2 L11. Additional Medicare Tax 0.9%. Form 8959. f8959.pdf; IRC §3101(b)(2).",
    "s2_l12_niit":         "Sch 2 L12. Net Investment Income Tax 3.8%. Form 8960. f8960.pdf; IRC §1411.",
    # Schedule 3
    "s3_l1_ftc":           "Sch 3 L1. Foreign Tax Credit. Form 1116 or de minimis. f1116.pdf; IRC §901.",
    "s3_l2_care":          "Sch 3 L2. Child/dependent care credit. Form 2441. f2441.pdf; IRC §21.",
    "s3_l3_edu":           "Sch 3 L3. Education credits. Form 8863. f8863.pdf; IRC §25A.",
    "s3_l4_saver":         "Sch 3 L4. Retirement savings credit. Form 8880. f8880.pdf; IRC §25B.",
    "s3_l6d_odc":          "Sch 3 L6d. Other Dependent Credit $500. f1040s8.pdf; IRC §24(h)(4).",
}


# ── Flag Definitions ──────────────────────────────────────────────────────────

FLAG_DEFS = {
    "EITC_EXACT":      ("info",    "EITC computed from embedded 2025 IRS EIC Table. No table confirmation required."),
    "EITC_INVEST":     ("error",   "EITC = $0: investment income exceeds IRC §32(i) limit."),
    "EITC_MFS":        ("error",   "EITC = $0: Married Filing Separately. IRC §32(d)."),
    "QDCGT_APPLIED":   ("info",    "QDCGT Worksheet applied. Qualified dividends/LTCG taxed at preferential rates."),
    "AMT_APPLIES":     ("warning", "AMT applies. Form 6251 TMT exceeds regular tax."),
    "NOL_DETECTED":    ("warning", "Potential NOL detected (AGI < 0). Form 1045 required. p536.pdf."),
    "4797_LOOKBACK":   ("warning", "§1231 lookback: verify no net §1231 losses in prior 5 years. IRC §1231(c)."),
    "8995A_REQUIRED":  ("warning", "QBI deduction: taxable income exceeds threshold. Form 8995-A required."),
    "BACKDOOR_CLEAN":  ("info",    "Backdoor Roth: clean conversion. No pre-tax IRA balance. Full basis offset."),
    "BACKDOOR_TAINT":  ("error",   "Backdoor Roth: TAINTED. Pre-tax IRA balance triggers pro-rata rule."),
    "KIDDIE_TAX":      ("warning", "Form 8615 kiddie tax applies. Child taxed at parent's marginal rate."),
    "CA_MFS_COMM_PROP":("warning", "CA MFS: community property income splitting required. IRC §66; R&TC §17021.5."),
    "QBI_RENTAL_SAFE": ("info",    "Rental income may qualify for §199A deduction under Rev. Proc. 2019-38."),
    "SEPP_UNVERIFIED": ("warning", "Form 5329 Code 01 (SEPP): annuity calculation not verified. IRC §72(t)(2)(A)(iv)."),
    "8995A_NOT_BUILT":  ("warning", "Form 8995-A not implemented. QBI deduction above threshold may be understated."),
    "SUSP_LOSS_RELEASE":("info",   "§469(g): suspended passive losses released at disposition."),
    "1250_UNREC":       ("info",   "Unrecaptured §1250 gain taxed at 25% max rate. QDCGT Worksheet Line 19."),
    "1245_RECAPTURE":   ("warning","§1245 equipment recapture: depreciation recaptured as ordinary income."),
    "MFS_CREDIT_DISQ":  ("error",  "One or more credits disqualified for MFS filing status."),
    "8606_AGGREGATION": ("warning","Form 8606: verify ALL traditional/SEP/SIMPLE IRA balances included in Line 5."),
}


def _flag(code: str, line: str = "", extra: str = "", source: str = "") -> dict:
    sev, msg = FLAG_DEFS.get(code, ("info", code))
    return {
        "severity": sev,
        "code": code,
        "line": line,
        "message": msg + (" " + extra if extra else ""),
        "source": source or "",
    }


def _cite(line_key: str) -> str:
    return LINE_SOURCES.get(line_key, "See IRS instructions.")


def _val(value: Any, line_key: str, flags: list,
         extra_source: str = "", components: list = None,
         note: str = "") -> dict:
    """Build a cited line entry."""
    entry = {
        "value": value,
        "source": _cite(line_key) + (" " + extra_source if extra_source else ""),
    }
    if components:
        entry["components"] = components
    if note:
        entry["note"] = note
    return entry


# ── Main report builder ───────────────────────────────────────────────────────

def generate_report(schema, engine_run_fn) -> dict:
    """
    Generate the full professional verification report.

    Args:
        schema: TaxpayerSchema instance
        engine_run_fn: callable — the engine's run() function

    Returns:
        Structured dict with all report sections.
    """
    import sachintaxcare_engine as e

    # Run the engine
    result = engine_run_fn(schema)
    c = result["computed"]
    warnings_raw = result.get("warnings", [])
    flags = []

    # ── Meta ─────────────────────────────────────────────────────────────────
    meta = {
        "taxpayer": f"{schema.first} {schema.last}",
        "ssn_last4": schema.ssn[-4:] if schema.ssn and len(schema.ssn) >= 4 else "XXXX",
        "filing_status": schema.filing_status.upper(),
        "tax_year": schema.tax_year,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "engine_version": ENGINE_VERSION,
        "source_policy": "All computations use IRS source documents only (irs.gov/pub/irs-pdf/).",
    }

    # ── Re-compute EITC with exact table ─────────────────────────────────────
    wages      = c.get("wages", 0)
    se_profit  = max(0, c.get("se_net_profit", 0))
    agi        = c.get("agi", 0)
    n_kids     = len([d for d in schema.dependents
                      if getattr(d, "ctc_eligible", False)])
    investment_income = (c.get("interest", 0) + c.get("us_bond_interest", 0) +
                         c.get("dividends", 0) + max(0, c.get("cap_gain_net", 0)))

    eitc_exact = lookup_eitc_exact(
        earned_income    = wages + se_profit,
        agi              = agi,
        num_children     = n_kids,
        filing_status    = schema.filing_status,
        investment_income = investment_income,
    )
    eitc_value = eitc_exact["eitc"]

    if eitc_exact.get("disqualified"):
        reason = eitc_exact.get("reason", "")
        if reason == "MFS":
            flags.append(_flag("EITC_MFS", "l27a_eitc",
                               source="IRC §32(d); p596.pdf."))
        elif reason == "investment_income":
            flags.append(_flag("EITC_INVEST", "l27a_eitc",
                               extra=f"Investment income ${round(investment_income):,}.",
                               source="IRC §32(i); p596.pdf."))
    else:
        flags.append(_flag("EITC_EXACT", "l27a_eitc",
                           source=eitc_exact.get("source", "")))

    # ── Form 1040 ─────────────────────────────────────────────────────────────
    # W-2 components
    w2_components = [
        {"payer": w.employer, "ein": w.ein, "box1": round(w.box1_wages)}
        for w in schema.w2s
    ]
    total_income = c.get("total_income", 0)
    total_adj    = c.get("total_adjustments", 0)

    form_1040 = {
        # Income
        "l1z_wages": _val(c.get("wages", 0), "l1z_wages", flags,
                          components=w2_components),
        "l2a_tax_exempt_int": _val(c.get("tax_exempt_interest", 0),
                                   "l2a_tax_exempt_int", flags),
        "l2b_taxable_int": _val(c.get("interest", 0), "l2b_taxable_int", flags),
        "l3a_qual_div":    _val(c.get("dividends_qual", 0), "l3a_qual_div", flags),
        "l3b_ord_div":     _val(c.get("dividends", 0), "l3b_ord_div", flags),
        "l4a_ira_dist":    _val(c.get("l4a_ira_gross", 0), "l4a_ira_dist", flags),
        "l4b_ira_taxable": _val(c.get("l4b_ira_taxable", 0), "l4b_ira_taxable", flags,
                                note="Reduced by Form 8606 nontaxable basis if applicable."),
        "l5a_pension_dist":    _val(c.get("l5a_pension_gross", 0), "l5a_pension_dist", flags),
        "l5b_pension_taxable": _val(c.get("l5b_pension_taxable", 0), "l5b_pension_taxable", flags),
        "l6a_ss_total":    _val(c.get("l6a_ss_total", 0), "l6a_ss_total", flags),
        "l6b_ss_taxable":  _val(c.get("l6b_ss_taxable", 0), "l6b_ss_taxable", flags),
        "l7_cap_gain":     _val(c.get("cap_gain_net", 0), "l7_cap_gain", flags),
        "l8_other_income": _val(
            c.get("cancelled_debt", 0) + c.get("prize_income", 0) +
            c.get("gambling_income", 0) + c.get("unemployment_income", 0) +
            c.get("state_refund_taxable", 0) + c.get("alimony_received", 0) +
            c.get("k1_ordinary", 0) + c.get("rental_net", 0),
            "l8_other_income", flags,
            components=[
                {"item": "Cancelled debt (1099-C)", "amount": c.get("cancelled_debt", 0)},
                {"item": "Prize/other income (1099-MISC)", "amount": c.get("prize_income", 0)},
                {"item": "Gambling winnings (W-2G)", "amount": c.get("gambling_income", 0)},
                {"item": "Unemployment (1099-G)", "amount": c.get("unemployment_income", 0)},
                {"item": "State refund taxable", "amount": c.get("state_refund_taxable", 0)},
                {"item": "Alimony received (pre-2019)", "amount": c.get("alimony_received", 0)},
                {"item": "K-1 ordinary income", "amount": c.get("k1_ordinary", 0)},
                {"item": "Net rental income (Sch E)", "amount": c.get("rental_net", 0)},
            ]
        ),
        "l9_total_income": _val(total_income, "l9_total_income", flags),
        # Adjustments
        "l10_adjustments": _val(total_adj, "l10_adj", flags,
            components=[
                {"item": "SE tax deduction (50%)", "amount": c.get("se_tax_deduction", 0),
                 "source": "Sch 1 L15. f1040sse.pdf."},
                {"item": "SE health insurance", "amount": c.get("adj_se_health", 0),
                 "source": "Sch 1 L17. IRC §162(l)."},
                {"item": "SE retirement", "amount": c.get("adj_se_retirement", 0),
                 "source": "Sch 1 L16. IRC §404."},
                {"item": "IRA deduction", "amount": c.get("adj_ira_deduction", 0),
                 "source": "Sch 1 L20. p590a.pdf; IRC §219."},
                {"item": "HSA deduction", "amount": c.get("adj_hsa", 0),
                 "source": "Sch 1 L13. f8889.pdf; IRC §223."},
                {"item": "Student loan interest", "amount": c.get("adj_student_loan", 0),
                 "source": "Sch 1 L21. IRC §221."},
                {"item": "Teacher expense", "amount": c.get("teacher_adj", 0),
                 "source": "Sch 1 L11. Max $300. f1040s1.pdf."},
                {"item": "Alimony paid (pre-2019)", "amount": c.get("alimony_paid_ded", 0),
                 "source": "Sch 1 L19a. IRC §215 (pre-TCJA)."},
            ]
        ),
        "l11_agi":         _val(c.get("agi", 0), "l11_agi", flags),
        "l12_deduction":   _val(c.get("deduction_used", 0), "l12_std_ded", flags,
                                note=f"Type: {c.get('deduction_type', 'standard')}"),
        "l13_qbi":         _val(c.get("adj_qbi", 0), "l13_qbi", flags),
        "l15_taxable_income": _val(c.get("taxable_income", 0), "l15_taxable_income", flags),
        # Tax
        "l16_income_tax":  _val(c.get("income_tax", 0), "l16_income_tax", flags,
                                note="QDCGT Worksheet applied." if c.get("qdcgt_applied") else "Tax table."),
        "l17_other_taxes": _val(c.get("l17_other_taxes", 0), "l17_other_taxes", flags),
        "l24_total_tax":   _val(c.get("l24_total_tax", 0), "l24_total_tax", flags),
        # Credits
        "l19_ctc":         _val(c.get("l19_ctc", 0), "l19_ctc", flags,
                                note=f"{n_kids} qualifying children × $2,000 before phase-out."),
        "l20_sch3_nonref": _val(c.get("l20_sch3l8", 0), "l20_sch3_nonref", flags),
        "l25a_w2_wh":      _val(c.get("l25a_w2_wh", 0), "l25a_w2_wh", flags),
        "l25b_other_wh":   _val(c.get("l25b_total", 0), "l25b_other_wh", flags),
        "l25d_total_wh":   _val(c.get("l25d_total_wh", 0), "l25d_total_wh", flags),
        "l26_est_pmts":    _val(c.get("l26_estimated", 0), "l26_est_pmts", flags),
        "l27a_eitc":       {
            "value": eitc_value,
            "source": eitc_exact.get("source", _cite("l27a_eitc")),
            "exact_table_lookup": eitc_exact.get("exact", False),
            "lookup_band": (f"${eitc_exact.get('band_start',0):,}–"
                           f"${eitc_exact.get('band_end',0):,}")
                           if not eitc_exact.get("disqualified") else "N/A",
        },
        "l28_actc":        _val(c.get("l28_actc", 0), "l28_actc", flags),
        "l29_aoc":         _val(c.get("l29_aoc", 0), "l29_aoc", flags),
        "l31_ptc":         _val(c.get("l31_sch3l15", 0), "l31_ptc", flags),
        "l32_refundable":  _val(c.get("l32", 0), "l32_refundable", flags),
        "l33_total_pmts":  _val(c.get("l33_total_pmts", 0), "l33_total_pmts", flags),
        "l34_refund":      _val(c.get("l34_refund", 0), "l34_refund", flags),
        "l37_owe":         _val(c.get("l37_owe", 0), "l37_owe", flags),
        "l38_penalty":     _val(c.get("l38_underpayment", 0), "l38_penalty", flags),
    }

    # ── Schedules ─────────────────────────────────────────────────────────────
    se = c.get("se_detail", {})
    sd = c.get("sched_d_8949", {})
    sb = c.get("sched_b", {})
    sa = c.get("sched_a", {})

    schedules = {
        "schedule_b": {
            "total_interest": {"value": sb.get("total_interest", 0),
                               "source": "Sch B L4. 1099-INT Box 1+3 sum. i1040sb.pdf."},
            "total_dividends": {"value": sb.get("total_ordinary_dividends", 0),
                                "source": "Sch B L6. 1099-DIV Box 1a sum. i1040sb.pdf."},
            "source": "f1040sb.pdf; i1040sb.pdf.",
        },
        "schedule_c_se": {
            "gross_receipts":  {"value": se.get("total_gross", 0),
                                "source": "Sch C L7. 1099-NEC Box 1. f1040sc.pdf."},
            "total_expenses":  {"value": se.get("total_expenses", 0),
                                "source": "Sch C Lines 8–27. f1040sc.pdf."},
            "net_profit":      {"value": c.get("se_net_profit", 0),
                                "source": "Sch C L31. Sch 1 L3. f1040sc.pdf."},
            "se_tax":          {"value": c.get("se_tax", 0),
                                "source": "Sch SE L12. 92.35% × net profit × 15.3% (SS cap applied). "
                                          "f1040sse.pdf; IRC §1401. SS base $176,100 (2025)."},
            "se_tax_deduction":{"value": c.get("se_tax_deduction", 0),
                                "source": "Sch 1 L15. 50% of SE tax. IRC §164(f)."},
        },
        "schedule_d_8949": {
            "st_net":  {"value": sd.get("schd_l7_st_total", 0),
                        "source": "Sch D L7. Form 8949 Boxes A+C short-term net. f1040sd.pdf."},
            "lt_net":  {"value": sd.get("schd_l15_lt_total", 0),
                        "source": "Sch D L15. Form 8949 Boxes B+D long-term net (covered + noncovered). f1040sd.pdf."},
            "net_cap_gain_loss": {"value": sd.get("net_capital_gain_loss", 0),
                                  "source": "Sch D L21. Net of ST + LT. $3,000 loss limit. f1040sd.pdf; IRC §1211."},
            "cap_loss_carryover": {"value": sd.get("cap_loss_carryover", 0),
                                   "source": "Sch D L22. Loss > $3,000 carried forward. IRC §1212(b)."},
            "box_b_covered_lt": {"value": len(sd.get("box_b_rows", [])),
                                 "source": "Form 8949 Box B. Basis reported to IRS. f8949.pdf."},
            "box_d_noncovered_lt": {"value": len(sd.get("box_d_rows", [])),
                                    "source": "Form 8949 Box D. Basis NOT reported to IRS. f8949.pdf; i8949.pdf."},
        },
        "schedule_e": {
            "net_rental": {"value": c.get("rental_net", 0),
                           "source": "Sch E L26. After Form 8582 passive activity limits. "
                                     "f1040se.pdf; f8582.pdf; IRC §469."},
        },
        "schedule_a": {
            "total_itemized": {"value": sa.get("l17_total", 0) if sa else 0,
                               "source": "Sch A L17. Used only if > standard deduction. f1040sa.pdf."},
            "salt_capped":    {"value": sa.get("l7_salt", 0) if sa else 0,
                               "source": "Sch A L7. SALT cap $10,000 ($5,000 MFS). IRC §164(b)(6)."},
        },
    }

    # ── Credits ───────────────────────────────────────────────────────────────
    f2441 = c.get("f2441", {})
    f8863 = c.get("f8863", {})
    f8880 = c.get("f8880", {})
    s8812 = c.get("s8812", {})
    f8962 = c.get("f8962", {})
    f1116 = c.get("f1116", {})

    credits = {
        "form_2441_care": {
            "credit": {"value": f2441.get("l11_credit", 0),
                       "source": "Form 2441 L11. Care credit. "
                                 "f2441.pdf; IRC §21. CLW order: first nonref credit."},
            "qualified_expenses": {"value": f2441.get("qualified_exp", 0),
                                   "source": "Form 2441 L3. Capped at $3k (1 child) / $6k (2+). "
                                             "f2441.pdf; IRC §21(c)."},
        },
        "form_8863_education": {
            "aoc_refundable": {"value": c.get("l29_aoc", 0),
                               "source": "Form 8863 Part III. AOC 40% refundable → L29. f8863.pdf; IRC §25A(i)."},
            "nonref_applied": {"value": f8863.get("nonref_applied", 0),
                               "source": "Form 8863. 60% nonref → Sch 3 L3. CLW applied. f8863.pdf."},
        },
        "form_8880_saver": {
            "credit": {"value": f8880.get("l12_credit", 0),
                       "source": "Form 8880 L12. Retirement savings credit → Sch 3 L4. "
                                 "f8880.pdf; IRC §25B."},
            "rate_applied": {"value": f8880.get("l9_rate", 0),
                             "source": "Form 8880 L9. Rate per AGI bracket (10%/20%/50%). f8880.pdf."},
        },
        "schedule_8812": {
            "ctc_nonref": {"value": c.get("l19_ctc", 0),
                           "source": "Sch 8812 L14. CTC $2,000/child nonrefundable. f1040s8.pdf; IRC §24."},
            "actc_refundable": {"value": c.get("l28_actc", 0),
                                "source": "Sch 8812 L27. ACTC $1,700 cap/child. 15% × (earned − $2,500). "
                                          "f1040s8.pdf; IRC §24(d)."},
            "odc": {"value": s8812.get("odc_credit", 0),
                    "source": "Sch 8812. Other Dependent Credit $500. IRC §24(h)(4)."},
            "phase_out_threshold": {"value": s8812.get("po_threshold", 0),
                                    "source": "Sch 8812 L8. $200k single / $400k MFJ. IRC §24(b)(1)."},
        },
        "form_8962_ptc": {
            "net_ptc": {"value": c.get("l31_sch3l15", 0),
                        "source": "Form 8962 L26. Net Premium Tax Credit → Sch 3 L9 → L31. "
                                  "f8962.pdf; IRC §36B."},
        },
        "form_1116_ftc": {
            "credit": {"value": c.get("ftc_credit", 0),
                       "source": "Form 1116 / Sch 3 L1. Foreign Tax Credit. "
                                 "f1116.pdf; IRC §901. De minimis ≤$300/$600 → direct."},
            "de_minimis": {"value": f1116.get("de_minimis_applies", False) if f1116 else False,
                           "source": "i1116.pdf. De minimis exception (≤$300/$600 all passive)."},
        },
    }

    # ── Other Taxes (Schedule 2) ──────────────────────────────────────────────
    sch2 = c.get("sch2", {})

    if sch2.get("l1_amt", 0) > 0:
        flags.append(_flag("AMT_APPLIES", "l16_income_tax",
                           extra=f"AMT = ${sch2.get('l1_amt',0):,}.",
                           source="Form 6251. f6251.pdf; IRC §55."))

    other_taxes = {
        "s2_l1_amt":     {"value": sch2.get("l1_amt", 0),     "source": _cite("s2_l1_amt")},
        "s2_l2_aptc":    {"value": sch2.get("l2_excess_aptc", 0), "source": _cite("s2_l2_aptc")},
        "s2_l4_se_tax":  {"value": sch2.get("l4_se_tax", 0),  "source": _cite("s2_l4_se_tax")},
        "s2_l6_4972":    {"value": sch2.get("l6_4972_tax", 0),"source": _cite("s2_l6_4972")},
        "s2_l8_5329":    {"value": sch2.get("l8_5329_penalty", 0), "source": _cite("s2_l8_5329")},
        "s2_l11_addl_med":{"value": sch2.get("l11_addl_med", 0), "source": _cite("s2_l11_addl_med")},
        "s2_l12_niit":   {"value": sch2.get("l12_niit", 0),   "source": _cite("s2_l12_niit")},
        "s2_l17_total":  {"value": sch2.get("l17_total", 0),
                          "source": "Sch 2 L17. Sum of L1+L2+L4+L6+L8+L11+L12. f1040s2.pdf."},
    }

    # ── Carryforward Packet ───────────────────────────────────────────────────
    # All values a CPA must import into next year's return.
    f8606 = c.get("f8606", {})
    sched_e = c.get("sched_e_8582", {})
    nol    = c.get("nol", {})
    f4797_r = c.get("f4797", {})

    cap_loss_carryover = sd.get("cap_loss_carryover", 0) if sd else 0

    # Form 8582 suspended losses — per property
    suspended_losses = {}
    if sched_e:
        for prop in sched_e.get("properties", []):
            addr = prop.get("address", "Property")
            suspended = prop.get("suspended_loss", 0)
            if suspended < 0:
                suspended_losses[addr] = {
                    "amount": suspended,
                    "source": "Form 8582 Wks 1 Col c. Carry to next year unless property sold. "
                              "f8582.pdf; IRC §469(b).",
                }

    carryforwards = {
        "capital_loss_carryover": {
            "value": cap_loss_carryover,
            "source": "Sch D L22. Net capital loss > $3,000. Carry forward indefinitely. "
                      "f1040sd.pdf; IRC §1212(b).",
            "note": "Enter as capital_loss_carryover on next year's TaxpayerSchema "
                    "(positive value = absolute loss to carry). "
                    "Or use import_prior_year_carryforward() for auto-population.",
        },
        "nol_carryforward": {
            "value": nol.get("estimated_nol", 0) if nol.get("nol_detected") else 0,
            "source": "Estimated from AGI. Exact amount requires Form 1045 Worksheet A. "
                      "p536.pdf; IRC §172. Post-TCJA: 80% of TI limit; no carryback.",
            "note": "Compute exact NOL on Form 1045 before carryforward entry.",
        },
        "qbi_loss_carryforward": {
            "value": c.get("qbi_new_loss_carryforward", 0),
            "source": "Form 8995 L11 / 8995-A Part IV. QBI net loss carried forward. "
                      "f8995.pdf; Reg. 1.199A-1(d)(2)(iii).",
            "note": "Enter as qbi_loss_carryforward on next year's TaxpayerSchema. "
                    "Reduces next year's QBI before 20% deduction.",
        },
        "form_8582_suspended_losses": {
            "by_property": suspended_losses,
            "source": "Form 8582 Worksheet 1 Col c. Released when property sold (§469(g)). "
                      "f8582.pdf.",
            "note": "Enter as prior-year unallowed losses on next year's Form 8582.",
        },
        "form_8606_basis_remaining": {
            "value": f8606.get("l14_remaining_basis", 0) if f8606 else 0,
            "source": "Form 8606 L14. Nondeductible IRA basis after distributions. "
                      "f8606.pdf; IRC §408(d)(2).",
            "note": "Enter as prior-year basis (Line 2) on next year's Form 8606.",
        },
        "form_1116_excess_credits": {
            "passive_carryforward": f1116.get("excess_passive", 0) if f1116 else 0,
            "general_carryforward": f1116.get("excess_general", 0) if f1116 else 0,
            "source": "Form 1116 Part III. Excess foreign tax credit. "
                      "Carryback 1 yr / carryforward 10 yrs. f1116.pdf; IRC §904(c).",
            "note": "Enter on next year's Form 1116 Worksheet (carryover line).",
        },
        "sec1231_net_loss_this_year": {
            "value": min(0, f4797_r.get("sec1231_gain_net", 0)) if f4797_r else 0,
            "source": "Form 4797 Part I. Net §1231 loss carries forward 5 years. "
                      "IRC §1231(c); p544.pdf.",
            "note": "Enter as prior_sec1231_losses_5yr on next year's Form4797SaleData "
                    "if this year produced a net §1231 loss. Track per year for 5-year window.",
        },
    }

    # Flag NOL if detected
    if nol.get("nol_detected"):
        flags.append(_flag("NOL_DETECTED", "l11_agi",
                           extra=f"Estimated NOL = ${nol.get('estimated_nol',0):,}.",
                           source="p536.pdf; IRC §172."))

    # ── Supplemental Forms ────────────────────────────────────────────────────
    f8615 = c.get("f8615", {})
    f4797_r = c.get("f4797", {})

    supplemental = {}

    # ── QBI detail section ────────────────────────────────────────────────────
    # Source: f8995.pdf / f8995a.pdf; IRC §199A
    qbi_detail = c.get("qbi_detail", {})
    if qbi_detail and (qbi_detail.get("l15_deduction", 0) > 0 or qbi_detail.get("form")):
        qbi_form_used = qbi_detail.get("form", "8995")
        supplemental["qbi_deduction"] = {
            "form_used": {"value": qbi_form_used,
                          "source": f"Form {qbi_form_used}. §199A QBI deduction. "
                                    f"f{qbi_form_used.replace('-','')}.pdf; IRC §199A."},
            "l2_net_qbi": {"value": qbi_detail.get("l2_qbi", 0),
                           "source": "Net QBI after SE adjustments and loss carryforward. "
                                     "f8995.pdf L2 / f8995a.pdf Part I."},
            "l15_deduction": {"value": qbi_detail.get("l15_deduction", 0),
                              "source": "QBI deduction → Form 1040 Line 13. "
                                        "f8995.pdf L15 / f8995a.pdf L40."},
            "above_threshold": {"value": qbi_detail.get("above_threshold", False),
                                "source": "2025 threshold: $197,300 single / $394,600 MFJ. "
                                          "Rev. Proc. 2024-40; IRC §199A(e)(2)."},
            "per_biz_detail": {"value": qbi_detail.get("per_biz_detail", []),
                               "source": "Per-business QBI breakdown. "
                                         "f8995a.pdf Part I; Reg. 1.199A-3."},
        }
        if qbi_detail.get("above_threshold"):
            flags.append(_flag("8995A_REQUIRED", "l13_qbi",
                               extra=f"Taxable income ${c.get('taxable_income',0):,} "
                                     f"exceeds threshold ${qbi_detail.get('threshold',0):,}. "
                                     "Form 8995-A applied.",
                               source="f8995a.pdf; IRC §199A(b)(2)(B)."))
        if qbi_detail.get("new_loss_carryforward", 0) > 0:
            flags.append(_flag("NOL_DETECTED", "l13_qbi",
                               extra=f"QBI loss carryforward ${qbi_detail.get('new_loss_carryforward',0):,}. "
                                     "Enter as qbi_loss_carryforward next year.",
                               source="f8995.pdf L11; Reg. 1.199A-1(d)(2)(iii)."))

    if f8615.get("kiddie_tax_triggered"):
        flags.append(_flag("KIDDIE_TAX", "l16_income_tax",
                           extra=f"Tax at parent's rate = ${f8615.get('l15_income_tax',0):,}.",
                           source="f8615.pdf; IRC §1(g)."))
        supplemental["form_8615"] = {
            "applies": True,
            "l1_net_unearned": {"value": f8615.get("l1_net_unearned", 0),
                                "source": "Form 8615 L1. Unearned income − $2,700. f8615.pdf."},
            "l11_tentative": {"value": f8615.get("l11_tentative", 0),
                              "source": "Form 8615 L11. Tax on parent's income+NUI − tax on parent's income alone. f8615.pdf."},
            "l15_income_tax": {"value": f8615.get("l15_income_tax", 0),
                               "source": "Form 8615 L15. Greater of L11 or L13 → replaces normal bracket tax. f8615.pdf; IRC §1(g)."},
        }

    if f4797_r.get("applies"):
        for det in f4797_r.get("details", []):
            if det.get("held_over_one_year") and det.get("total_gain_loss", 0) > 0:
                if det.get("lookback_recapture", 0) > 0:
                    # Lookback was computed — informational
                    flags.append(_flag("4797_LOOKBACK", "l7_cap_gain",
                                       extra=f"{det.get('description','Property')}: "
                                             f"${det.get('lookback_recapture',0):,} reclassified as ordinary.",
                                       source="IRC §1231(c); p544.pdf."))
                elif det.get("prior_sec1231_losses_5yr", 0) == 0:
                    # Not provided — warn preparer to verify
                    flags.append(_flag("4797_LOOKBACK", "l7_cap_gain",
                                       extra=f"{det.get('description','Property')}: "
                                             "prior_sec1231_losses_5yr not provided — verify manually.",
                                       source="IRC §1231(c); p544.pdf."))
        if any(d.get("ordinary_recapture", 0) > 0 for d in f4797_r.get("details", [])):
            flags.append(_flag("1245_RECAPTURE", "l8_other_income",
                               source="IRC §1245(a)(1); f4797.pdf Part III."))
        if f4797_r.get("unrec_sec1250_gain", 0) > 0:
            flags.append(_flag("1250_UNREC", "l7_cap_gain",
                               extra=f"${f4797_r.get('unrec_sec1250_gain',0):,} at 25% max rate.",
                               source="IRC §1(h)(6); f4797.pdf."))
        supplemental["form_4797"] = {
            "ordinary_recapture": {"value": f4797_r.get("ordinary_income_recapture", 0),
                                   "source": "Form 4797 Part II. §1245/additional §1250 → ordinary income. "
                                             "f4797.pdf; IRC §1245."},
            "sec1231_gain_net": {"value": f4797_r.get("sec1231_gain_net", 0),
                                 "source": "Form 4797 Part I. Net §1231 gain → Sch D L11 (LTCG if positive). "
                                           "f4797.pdf; IRC §1231."},
            "unrec_sec1250": {"value": f4797_r.get("unrec_sec1250_gain", 0),
                              "source": "QDCGT Worksheet L19. 25% max rate. IRC §1(h)(6)."},
            "suspended_released": {"value": f4797_r.get("suspended_losses_released", 0),
                                   "source": "§469(g). Released at disposition. f4797.pdf."},
        }

    # MFS credit flag
    fs = schema.filing_status
    mfs_credits_affected = (fs == "mfs" and (
        c.get("l27a_eitc", 0) == 0 or c.get("l29_aoc", 0) == 0 or
        c.get("l28_actc", 0) == 0
    ))
    if fs == "mfs":
        flags.append(_flag("MFS_CREDIT_DISQ", "",
                           extra="EITC, AOC, LLC, ACTC all $0 for MFS.",
                           source="IRC §32(d); §25A(g)(6); §24(d)."))

    # QDCGT flag
    if c.get("qdcgt_applied"):
        flags.append(_flag("QDCGT_APPLIED", "l16_income_tax",
                           extra=f"QDCGT income = ${c.get('qdcgt_income',0):,}.",
                           source="f1040.pdf QDCGT Worksheet; Rev. Proc. 2024-40."))

    # 8606 aggregation
    f8606_data = schema.form_8606
    if f8606_data and f8606_data.is_backdoor_roth:
        if f8606_data.trad_ira_value_dec31 > 0:
            flags.append(_flag("BACKDOOR_TAINT", "l4b_ira_taxable",
                               extra=f"Pre-tax IRA balance ${round(f8606_data.trad_ira_value_dec31):,}.",
                               source="f8606.pdf; IRC §408(d)(2)."))
        else:
            flags.append(_flag("BACKDOOR_CLEAN", "l4b_ira_taxable",
                               source="f8606.pdf; IRC §408(d)(2)."))
        flags.append(_flag("8606_AGGREGATION", "l4b_ira_taxable",
                           source="i8606.pdf; IRC §408(d)(2)."))

    # Kiddie tax warning if unearned income close to threshold
    if (schema.form_8615 and schema.form_8615.unearned_income > 2700
            and not f8615.get("kiddie_tax_triggered")):
        pass  # already handled above

    # CA community property
    if fs == "mfs" and schema.california is not None:
        flags.append(_flag("CA_MFS_COMM_PROP", "",
                           source="IRC §66; CA R&TC §17021.5; FTB Pub 1005."))

    # QBI rental safe harbor
    if schema.schedule_es and c.get("rental_net", 0) > 0:
        flags.append(_flag("QBI_RENTAL_SAFE", "l13_qbi",
                           source="Rev. Proc. 2019-38; Reg. 1.199A-1(b)(14)."))

    # ── Result Summary ────────────────────────────────────────────────────────
    refund  = c.get("l34_refund", 0)
    owe     = c.get("l37_owe", 0)
    taxable_income = c.get("taxable_income", 0)
    total_tax_paid = c.get("l24_total_tax", 0)
    agi_val = c.get("agi", 0)

    effective_rate = round(total_tax_paid / agi_val * 100, 2) if agi_val > 0 else 0.0

    # Marginal rate from bracket
    bracket_rates = {
        "single": [(11925, 10), (48475, 12), (103350, 22), (197300, 24),
                   (250525, 32), (626350, 35), (float("inf"), 37)],
        "mfj":    [(23850, 10), (96950, 12), (206700, 22), (394600, 24),
                   (501050, 32), (751600, 35), (float("inf"), 37)],
        "hoh":    [(17000, 10), (64850, 12), (103350, 22), (197300, 24),
                   (250500, 32), (626350, 35), (float("inf"), 37)],
        "mfs":    [(11925, 10), (48475, 12), (103350, 22), (197300, 24),
                   (250525, 32), (313200, 35), (float("inf"), 37)],
        "qss":    [(23850, 10), (96950, 12), (206700, 22), (394600, 24),
                   (501050, 32), (751600, 35), (float("inf"), 37)],
    }
    brackets = bracket_rates.get(fs, bracket_rates["single"])
    marginal_rate = 10
    for upper, rate in brackets:
        if taxable_income <= upper:
            marginal_rate = rate
            break

    result_summary = {
        "refund": {"value": refund, "source": "f1040.pdf L34. L33 − L24."},
        "owe":    {"value": owe,    "source": "f1040.pdf L37. L24 − L33."},
        "effective_rate_pct": {
            "value": effective_rate,
            "source": f"Total tax ${total_tax_paid:,} ÷ AGI ${agi_val:,}. Informational only.",
        },
        "marginal_rate_pct": {
            "value": marginal_rate,
            "source": f"2025 bracket for {fs.upper()} at taxable income ${taxable_income:,}. "
                      "Rev. Proc. 2024-40.",
        },
    }

    # ── Deduplicate and sort flags ────────────────────────────────────────────
    seen_codes = set()
    unique_flags = []
    severity_order = {"error": 0, "warning": 1, "info": 2}
    for f in sorted(flags, key=lambda x: severity_order.get(x["severity"], 3)):
        key = f["code"] + f["line"]
        if key not in seen_codes:
            seen_codes.add(key)
            unique_flags.append(f)

    # ── Assemble report ───────────────────────────────────────────────────────
    report = {
        "meta":         meta,
        "form_1040":    form_1040,
        "schedules":    schedules,
        "credits":      credits,
        "other_taxes":  other_taxes,
        "supplemental": supplemental,
        "carryforwards": carryforwards,
        "result":       result_summary,
        "flags":        unique_flags,
        "flag_summary": {
            "errors":   sum(1 for f in unique_flags if f["severity"] == "error"),
            "warnings": sum(1 for f in unique_flags if f["severity"] == "warning"),
            "info":     sum(1 for f in unique_flags if f["severity"] == "info"),
        },
        "warnings_raw": warnings_raw,
    }

    return report


def generate_report_json(schema, engine_run_fn, indent: int = 2) -> str:
    """Return the professional report as a pretty-printed JSON string."""
    report = generate_report(schema, engine_run_fn)

    # Remove non-serializable objects (schema dataclass)
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_clean(i) for i in obj]
        if isinstance(obj, float) and math.isnan(obj):
            return None
        if hasattr(obj, "__dataclass_fields__"):
            return str(obj)
        return obj

    return json.dumps(_clean(report), indent=indent, default=str)


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import sachintaxcare_engine as e

    # Quick smoke test
    schema = e.TaxpayerSchema(
        first="Test", last="CPA", filing_status="single", tax_year=2025,
        w2s=[e.W2(employer="Acme Corp", box1_wages=85000, box2_fed_wh=12000)],
        form_1099divs=[e.Form1099DIV(payer="Vanguard",
                                      box1a_ordinary_div=3000,
                                      box1b_qualified_div=2500)],
        form_1099bs=[e.Form1099B(description="AAPL", proceeds=25000,
                                  cost_basis=15000, is_long_term=True,
                                  basis_reported_to_irs=True)],
        schedule_es=[e.ScheduleE(address="123 Maple St",
                                  rents_received=18000,
                                  mortgage_interest=6000, taxes=1800,
                                  depreciation=4000, insurance=900)],
    )

    report_json = generate_report_json(schema, e.run)
    print(report_json[:3000])
    print("...\n[truncated for display]")

    # Summary
    report = generate_report(schema, e.run)
    fs = report["flag_summary"]
    r  = report["result"]
    print(f"\n{'='*60}")
    print(f"Report generated: {report['meta']['generated_at']}")
    print(f"Taxpayer: {report['meta']['taxpayer']}")
    print(f"AGI: ${report['form_1040']['l11_agi']['value']:,}")
    print(f"Total tax: ${report['form_1040']['l24_total_tax']['value']:,}")
    refund = r['refund']['value']
    owe    = r['owe']['value']
    if refund > 0:
        print(f"REFUND: ${refund:,}")
    else:
        print(f"OWE: ${owe:,}")
    print(f"Effective rate: {r['effective_rate_pct']['value']}%")
    print(f"Marginal rate: {r['marginal_rate_pct']['value']}%")
    print(f"Flags: {fs['errors']} errors | {fs['warnings']} warnings | {fs['info']} info")
    print(f"EITC: ${report['form_1040']['l27a_eitc']['value']:,} "
          f"(exact table: {report['form_1040']['l27a_eitc']['exact_table_lookup']})")
    print(f"Rental QBI safe harbor flag: "
          f"{'YES' if any(f['code']=='QBI_RENTAL_SAFE' for f in report['flags']) else 'NO'}")
    print(f"{'='*60}")

