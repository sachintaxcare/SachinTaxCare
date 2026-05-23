"""
SachinTaxCare — PDF Output Layer (v1.0)
=======================================
Generates IRS-style PDF output from engine result["computed"].
Uses reportlab for PDF generation.

Entry points:
  generate_pdf(result_computed, schema_meta, output_path)
  generate_pdf_bytes(result_computed, schema_meta) → bytes

All values pulled directly from result["computed"] — engine is authoritative.
Source: IRS Form 1040 (2025) layout reference; irs.gov/pub/irs-pdf/f1040.pdf

DISCLAIMER: This output is for CPA/EA review only. Not a substitute for
the official IRS Form 1040. Must be reviewed and signed by a licensed preparer.
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                                  Spacer, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from datetime import datetime

# ── Color palette ──────────────────────────────────────────────────────────
IRS_BLUE     = colors.HexColor("#003087")    # IRS official blue
LIGHT_BLUE   = colors.HexColor("#dce6f5")    # header row fill
GOLD         = colors.HexColor("#f0a500")    # warning accent
GREEN        = colors.HexColor("#006400")    # refund positive
RED          = colors.HexColor("#cc0000")    # amount owed
MUTED_GRAY   = colors.HexColor("#666666")    # source citations
LIGHT_GRAY   = colors.HexColor("#f5f5f5")    # alternating row fill
BORDER_GRAY  = colors.HexColor("#cccccc")

def fmt_dollar(v, parentheses_negative=True):
    """Format dollar amount. Negative → (amount) per IRS convention."""
    if v is None: return "—"
    v = round(v)
    if v < 0 and parentheses_negative:
        return f"(${abs(v):,})"
    return f"${v:,}"

def fmt_pct(v):
    if v is None: return "—"
    return f"{v:.2%}"

def generate_pdf_bytes(computed: dict, meta: dict = None) -> bytes:
    """Generate PDF and return as bytes."""
    buf = BytesIO()
    _build_pdf(buf, computed, meta or {})
    return buf.getvalue()

def generate_pdf(computed: dict, meta: dict = None, output_path: str = "tax_return.pdf") -> str:
    """Generate PDF and write to file. Returns path."""
    with open(output_path, "wb") as f:
        f.write(generate_pdf_bytes(computed, meta))
    return output_path

def _build_pdf(buf, computed: dict, meta: dict):
    c = computed
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.5*inch, leftMargin=0.5*inch,
        topMargin=0.6*inch,   bottomMargin=0.6*inch,
        title="SachinTaxCare — Form 1040 Summary (2025)",
    )

    styles = getSampleStyleSheet()
    title_style    = ParagraphStyle("title",    parent=styles["Normal"],
                                    fontSize=15, textColor=IRS_BLUE,
                                    fontName="Helvetica-Bold", spaceAfter=4)
    sub_style      = ParagraphStyle("sub",      parent=styles["Normal"],
                                    fontSize=8,  textColor=MUTED_GRAY, spaceAfter=8)
    section_style  = ParagraphStyle("section",  parent=styles["Normal"],
                                    fontSize=10, textColor=colors.white,
                                    fontName="Helvetica-Bold", spaceBefore=8, spaceAfter=2)
    note_style     = ParagraphStyle("note",     parent=styles["Normal"],
                                    fontSize=7,  textColor=MUTED_GRAY, spaceAfter=6)
    warn_style     = ParagraphStyle("warn",     parent=styles["Normal"],
                                    fontSize=7.5, textColor=colors.HexColor("#7a4000"))

    def section_header(text):
        """Blue header bar for each major section."""
        return Table([[Paragraph(text, section_style)]],
                     colWidths=[7.5*inch],
                     style=TableStyle([
                         ("BACKGROUND", (0,0), (-1,-1), IRS_BLUE),
                         ("LEFTPADDING",  (0,0), (-1,-1), 6),
                         ("TOPPADDING",   (0,0), (-1,-1), 4),
                         ("BOTTOMPADDING",(0,0), (-1,-1), 4),
                     ]))

    def line_table(rows, col_widths=None):
        """Standard two-column line table: label | amount."""
        if not rows: return Spacer(1, 4)
        if col_widths is None:
            col_widths = [5.8*inch, 1.7*inch]
        tbl = Table(rows, colWidths=col_widths,
                    style=TableStyle([
                        ("FONTSIZE",      (0,0), (-1,-1), 8.5),
                        ("FONTNAME",      (0,0), (0,-1),  "Helvetica"),
                        ("FONTNAME",      (1,0), (1,-1),  "Helvetica"),
                        ("ALIGN",         (1,0), (1,-1),  "RIGHT"),
                        ("TEXTCOLOR",     (0,0), (-1,-1), colors.black),
                        ("ROWBACKGROUNDS",(0,0), (-1,-1), [colors.white, LIGHT_GRAY]),
                        ("LINEBELOW",     (0,-1),(-1,-1), 0.5, BORDER_GRAY),
                        ("TOPPADDING",    (0,0), (-1,-1), 2),
                        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
                        ("LEFTPADDING",   (0,0), (-1,-1), 4),
                    ]))
        return tbl

    def total_row(label, value, positive_color=colors.black):
        """Bold total row."""
        color = positive_color
        if isinstance(value, (int, float)):
            color = GREEN if value > 0 else (RED if value < 0 else colors.black)
            disp = fmt_dollar(value)
        else:
            disp = value
        return Table([[Paragraph(f"<b>{label}</b>", styles["Normal"]),
                       Paragraph(f"<b>{disp}</b>", ParagraphStyle(
                           "tr", parent=styles["Normal"],
                           fontSize=9, textColor=color, alignment=TA_RIGHT))]],
                     colWidths=[5.8*inch, 1.7*inch],
                     style=TableStyle([
                         ("BACKGROUND",   (0,0), (-1,-1), LIGHT_BLUE),
                         ("LINEBELOW",    (0,0), (-1,-1), 1.0, IRS_BLUE),
                         ("TOPPADDING",   (0,0), (-1,-1), 3),
                         ("BOTTOMPADDING",(0,0), (-1,-1), 3),
                         ("LEFTPADDING",  (0,0), (-1,-1), 4),
                     ]))

    def row(label, val, indent=False, source=""):
        """Single data row."""
        prefix = "    " if indent else ""
        src    = f" <font color='grey' size='6'>[{source}]</font>" if source else ""
        lbl = Paragraph(f"{prefix}{label}{src}", styles["Normal"])
        amt = fmt_dollar(val) if isinstance(val, (int, float)) else (val or "—")
        return [lbl, amt]

    def skip(n=1): return [Paragraph("&nbsp;", styles["Normal"]), ""] * n

    # ── Build document ──────────────────────────────────────────────────────
    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    taxpayer = meta.get("taxpayer_name", "Taxpayer")
    tax_year = meta.get("tax_year", 2025)
    fs_map   = {"single":"Single","mfj":"Married Filing Jointly","mfs":"Married Filing Separately",
                "hoh":"Head of Household","qss":"Qualifying Surviving Spouse"}
    fs_label = fs_map.get(meta.get("filing_status",""), meta.get("filing_status",""))
    gen_at   = datetime.now().strftime("%Y-%m-%d %H:%M")

    story.append(Paragraph("SachinTaxCare", title_style))
    story.append(Paragraph(
        f"Form 1040 Computation Summary — Tax Year {tax_year} &nbsp;|&nbsp; "
        f"{taxpayer} &nbsp;|&nbsp; {fs_label} &nbsp;|&nbsp; "
        f"Generated {gen_at}",
        sub_style))
    story.append(Paragraph(
        "⚠ CPA/EA REVIEW COPY — Not a filed return. Engine computation only. "
        "Must be reviewed, verified, and signed by a licensed tax preparer before filing. "
        "Source: IRS forms from irs.gov only.",
        ParagraphStyle("disc", parent=styles["Normal"], fontSize=7,
                       textColor=RED, borderColor=GOLD,
                       borderWidth=1, borderPadding=4, spaceAfter=8)))

    # ── INCOME ──────────────────────────────────────────────────────────────
    story.append(section_header("INCOME  (Form 1040 Lines 1–8)"))
    income_rows = [
        row("Line 1z  Wages, salaries, tips",          c.get("wages"),           source="W-2 Box 1"),
        row("Line 2b  Taxable interest",                c.get("interest"),         source="Schedule B"),
        row("Line 3b  Ordinary dividends",              c.get("dividends"),         source="Schedule B"),
        row("Line 3a  Qualified dividends",             c.get("dividends_qual"),    indent=True, source="1099-DIV Box 1b"),
        row("Line 4b  IRA/pension taxable",             (c.get("l4b_ira_taxable",0) or 0) + (c.get("l5b_pension_taxable",0) or 0), source="1099-R Box 2a"),
        row("Line 6b  Social Security taxable",         c.get("l6b_ss_taxable"),   source="Pub 915 Wk 1"),
        row("Line 7   Capital gain or (loss)",          c.get("cap_gain_income"),  source="Schedule D"),
        row("Line 8   Additional income",               c.get("additional_income"),source="Schedule 1"),
    ]
    story.append(line_table([r for r in income_rows if r[1] not in ("—", "$0", None)]))
    story.append(total_row("Total Income", c.get("total_income",
        (c.get("agi",0) or 0) + (c.get("total_adjustments",0) or 0))))
    story.append(Spacer(1, 6))

    # ── ADJUSTMENTS ─────────────────────────────────────────────────────────
    story.append(section_header("ADJUSTMENTS  (Schedule 1 Part II)"))
    adj_rows = []
    if c.get("se_tax_deduction"):       adj_rows.append(row("SE tax deduction (½)",  c["se_tax_deduction"], source="Schedule SE"))
    if c.get("adj_se_health"):          adj_rows.append(row("SE health insurance",    c["adj_se_health"],    source="Sch 1 L17"))
    if c.get("adj_se_retirement"):      adj_rows.append(row("SE retirement",          c["adj_se_retirement"],source="Sch 1 L16"))
    if c.get("adj_ira_deduction"):      adj_rows.append(row("IRA deduction",          c["adj_ira_deduction"],source="Sch 1 L20"))
    if c.get("adj_hsa"):                adj_rows.append(row("HSA deduction",          c["adj_hsa"],          source="Form 8889"))
    if c.get("adj_student_loan"):       adj_rows.append(row("Student loan interest",  c["adj_student_loan"], source="Sch 1 L21"))
    if c.get("teacher_adj"):            adj_rows.append(row("Educator expenses",      c["teacher_adj"],      source="Sch 1 L11"))
    if c.get("adj_other"):              adj_rows.append(row("Other adjustments",      c["adj_other"],        source="Sch 1 L24z"))
    # OBBBA deductions
    if c.get("obbba_senior_deduction"): adj_rows.append(row("Senior Bonus Ded (OBBBA)", c["obbba_senior_deduction"], source="OBBBA §70103"))
    if c.get("obbba_tip_deduction"):    adj_rows.append(row("Tip income ded (OBBBA)",   c["obbba_tip_deduction"],    source="OBBBA §70201"))
    if c.get("obbba_overtime_deduction"):adj_rows.append(row("Overtime ded (OBBBA)",   c["obbba_overtime_deduction"],source="OBBBA §70202"))
    if c.get("obbba_auto_loan_deduction"):adj_rows.append(row("Auto loan int (OBBBA)", c["obbba_auto_loan_deduction"],source="OBBBA §70301"))
    if adj_rows:
        story.append(line_table(adj_rows))
    story.append(total_row("Adjusted Gross Income  (Line 11)", c.get("agi")))
    story.append(Spacer(1, 6))

    # ── DEDUCTION & TAXABLE INCOME ───────────────────────────────────────────
    story.append(section_header("DEDUCTION & TAXABLE INCOME  (Lines 12–15)"))
    ded_type = c.get("deduction_type","standard")
    ded_rows = [
        row(f"Line 12  {ded_type.title()} deduction", -c.get("deduction_used",0)),
        row("Line 13  QBI deduction (§199A)",          -c.get("adj_qbi",0),      source="Form 8995/8995-A"),
    ]
    story.append(line_table([r for r in ded_rows if r[1] != "$0"]))
    story.append(total_row("Taxable Income  (Line 15)", c.get("taxable_income")))
    story.append(Spacer(1, 6))

    # ── TAX ─────────────────────────────────────────────────────────────────
    story.append(section_header("TAX  (Lines 16–24)"))
    tax_rows = [
        row("Line 16  Income tax",                 c.get("income_tax"),          source="Tax Table / QDCGT Worksheet"),
        row("Line 17  Other taxes (Schedule 2)",   c.get("l17_other_taxes"),     source="Schedule 2"),
    ]
    if c.get("sch2"):
        s2 = c["sch2"]
        if s2.get("l1_amt"):      tax_rows.append(row("  AMT (Form 6251)",       s2["l1_amt"],      indent=True, source="Form 6251"))
        if s2.get("l4_se_tax"):   tax_rows.append(row("  SE tax (Schedule SE)",  s2["l4_se_tax"],   indent=True, source="Schedule SE"))
        if s2.get("l11_addl_med"):tax_rows.append(row("  Additional Medicare",   s2["l11_addl_med"],indent=True, source="Form 8959"))
        if s2.get("l12_niit"):    tax_rows.append(row("  Net Investment Income Tax", s2["l12_niit"],indent=True, source="Form 8960"))
    story.append(line_table([r for r in tax_rows if r[1] not in ("—","$0",None)]))
    story.append(total_row("Total Tax  (Line 24)", c.get("l24_total_tax")))
    story.append(Spacer(1, 6))

    # ── CREDITS ─────────────────────────────────────────────────────────────
    story.append(section_header("CREDITS  (Lines 19–31)"))
    cr_rows = []
    if c.get("l14_ctc"):            cr_rows.append(row("Line 19  Child Tax Credit",         c["l14_ctc"],        source="Schedule 8812"))
    if c.get("f2441",{}).get("l11_credit"): cr_rows.append(row("  Child/Dep Care Credit",  c["f2441"]["l11_credit"], indent=True, source="Form 2441"))
    if c.get("f8863",{}).get("nonref_applied"): cr_rows.append(row("  Education Credits",  c["f8863"]["nonref_applied"], indent=True, source="Form 8863"))
    if c.get("f8880",{}).get("l12_credit"): cr_rows.append(row("  Saver's Credit",         c["f8880"]["l12_credit"],    indent=True, source="Form 8880"))
    if c.get("ftc_credit"):         cr_rows.append(row("  Foreign Tax Credit",             c["ftc_credit"],     indent=True, source="Form 1116"))
    if c.get("l27a_eitc"):          cr_rows.append(row("Line 27a EITC",                    c["l27a_eitc"],      source="Schedule EIC"))
    if c.get("l28_actc"):           cr_rows.append(row("Line 28  ACTC (refundable)",       c["l28_actc"],       source="Schedule 8812"))
    if c.get("edu_ref_aoc"):        cr_rows.append(row("Line 29  AOC refundable",          c["edu_ref_aoc"],    source="Form 8863"))
    if c.get("net_ptc"):            cr_rows.append(row("Line 31  Premium Tax Credit",      c["net_ptc"],        source="Form 8962"))
    if cr_rows:
        story.append(line_table(cr_rows))
    else:
        story.append(Paragraph("No credits claimed.", note_style))
    story.append(Spacer(1, 6))

    # ── PAYMENTS ────────────────────────────────────────────────────────────
    story.append(section_header("PAYMENTS  (Lines 25–33)"))
    pay_rows = [
        row("Line 25a  Federal withholding (W-2)",  c.get("l25a_w2_wh"),           source="W-2 Box 2"),
        row("Line 25b  Other WH (1099-R, SSA, etc)",c.get("total_1099_wh"),        source="Various 1099s"),
        row("Line 26   Estimated tax payments",      c.get("estimated_payments"),   source="Form 1040-ES"),
    ]
    story.append(line_table([r for r in pay_rows if r[1] not in ("—","$0",None)]))
    story.append(total_row("Total Payments  (Line 33)", c.get("l33_total_payments")))
    story.append(Spacer(1, 6))

    # ── RESULT ──────────────────────────────────────────────────────────────
    story.append(section_header("RESULT"))
    refund = c.get("l34_refund", 0) or 0
    owed   = c.get("l37_owe", 0)   or 0
    undpay = c.get("l38_underpayment", 0) or 0

    result_rows = []
    if refund > 0:
        result_rows.append(row("Line 34  REFUND", refund))
    if owed > 0:
        result_rows.append(row("Line 37  AMOUNT OWED", owed))
    if undpay > 0:
        result_rows.append(row("Line 38  Underpayment penalty (Form 2210)", undpay, source="Form 2210"))
    if result_rows:
        story.append(line_table(result_rows))

    # Summary box
    eff_rate = c.get("effective_rate") or (
        (c.get("income_tax",0) / c.get("agi",1) * 100) if c.get("agi",0) else 0)
    summary_data = [
        ["Effective tax rate", f"{eff_rate:.1f}%"],
        ["AGI",                fmt_dollar(c.get("agi"))],
        ["Taxable income",     fmt_dollar(c.get("taxable_income"))],
        ["Total tax",          fmt_dollar(c.get("l24_total_tax"))],
        ["Total payments",     fmt_dollar(c.get("l33_total_payments"))],
        ["REFUND" if refund > 0 else "AMOUNT OWED",
         fmt_dollar(refund if refund > 0 else owed)],
    ]
    summary_table = Table(summary_data, colWidths=[3.5*inch, 1.8*inch],
        style=TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), LIGHT_BLUE),
            ("BACKGROUND",   (0,-1),(-1,-1), IRS_BLUE),
            ("TEXTCOLOR",    (0,-1),(-1,-1), colors.white),
            ("FONTNAME",     (0,0), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,-1), 9),
            ("ALIGN",        (1,0), (1,-1),  "RIGHT"),
            ("TOPPADDING",   (0,0), (-1,-1), 4),
            ("BOTTOMPADDING",(0,0), (-1,-1), 4),
            ("LEFTPADDING",  (0,0), (-1,-1), 8),
            ("GRID",         (0,0), (-1,-1), 0.5, colors.white),
        ]))
    story.append(Spacer(1, 8))
    story.append(summary_table)

    # ── CA 540 ──────────────────────────────────────────────────────────────
    ca = c.get("ca_540")
    if ca:
        story.append(Spacer(1, 10))
        story.append(section_header("CALIFORNIA FORM 540"))
        ca_rows = [
            row("CA AGI",                       ca.get("ca_agi"),          source="CA Sch CA"),
            row("CA deduction",                  ca.get("ca_ded"),         source=f"CA {ca.get('ca_ded_type','std')}"),
            row("CA taxable income",             ca.get("ca_taxable")),
            row("CA tax before credits",         ca.get("ca_tax_before_credits")),
            row("CA total credits",             -ca.get("total_credits",0)),
            row("CA tax (net)",                  ca.get("ca_tax_net")),
        ]
        if ca.get("caleitc"):   ca_rows.append(row("CalEITC (FTB 3514)",       ca["caleitc"],          source="FTB 3514"))
        if ca.get("yctc"):      ca_rows.append(row("YCTC (FTB 3514 Part VI)",  ca["yctc"],             source="FTB 3514"))
        if ca.get("fytc"):      ca_rows.append(row("FYTC (FTB 3514 Part IX)",  ca["fytc"],             source="FTB 3514"))
        if ca.get("ca_refundable_total"): ca_rows.append(row("CA refundable credits total", ca["ca_refundable_total"]))
        story.append(line_table([r for r in ca_rows if r[1] not in ("—","$0",None)]))

    # ── WARNINGS ─────────────────────────────────────────────────────────────
    warnings = c.get("warnings") or []
    if warnings:
        story.append(Spacer(1, 10))
        story.append(section_header(f"PREPARER NOTES & WARNINGS  ({len(warnings)} items)"))
        for i, w in enumerate(warnings[:40], 1):    # cap at 40 for space
            story.append(Paragraph(f"{i}. {w}", warn_style))
        if len(warnings) > 40:
            story.append(Paragraph(f"… and {len(warnings)-40} more warnings. "
                                   "See JSON report for full list.", warn_style))

    # ── Footer ──────────────────────────────────────────────────────────────
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=IRS_BLUE))
    story.append(Paragraph(
        "SachinTaxCare — CPA/EA Review Workpaper · Tax Year 2025 · "
        "IRS sources only: irs.gov/pub/irs-pdf/ · Rev. Proc. 2025-32 (OBBBA) · "
        "NOT for filing without preparer review and signature. "
        f"Engine v11-fork+OBBBA · Generated {gen_at}",
        note_style))

    doc.build(story)


if __name__ == "__main__":
    # Quick self-test
    sample = {
        "wages": 85000, "interest": 500, "dividends": 1200, "dividends_qual": 900,
        "agi": 80000, "taxable_income": 64250, "income_tax": 7890,
        "l24_total_tax": 9200, "l25a_w2_wh": 8000, "total_1099_wh": 0,
        "estimated_payments": 0, "l33_total_payments": 8000,
        "l34_refund": 0, "l37_owe": 1200, "deduction_type": "standard",
        "deduction_used": 15750, "adj_qbi": 0, "l17_other_taxes": 1310,
        "warnings": ["Engine self-test warning."],
    }
    path = generate_pdf(sample, {"taxpayer_name": "Test Taxpayer", "tax_year": 2025,
                                  "filing_status": "single"}, "/tmp/test_1040.pdf")
    print(f"Self-test PDF written: {path}")
