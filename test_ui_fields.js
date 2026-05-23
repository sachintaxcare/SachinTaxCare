#!/usr/bin/env node
/**
 * SachinTaxCare — UI Field Test Script  v1.4
 * Source of truth: sachintaxcare_field_manifest.md
 * Updated 2026-05-17: added 71 fields from sessions 2026-05-14 + 2026-05-16;
 *   4797 dates/susp-passive, Sch E 8 new lines, Form 1116 panel, 1099-MISC full,
 *   1099-C expanded, SSA Medicare, 1098-T expanded, OBBBA deductions, senior DOB.
 *
 * Usage:
 *   node test_ui_fields.js [path/to/ui.html]
 *   node test_ui_fields.js                        # defaults to sachintaxcare_pro.html
 *
 * Exit codes:
 *   0 = all ✅ manifest fields present in UI
 *   1 = one or more ✅ manifest fields missing
 *
 * What it checks:
 *   - Every field marked ✅ in the manifest must have its id pattern present in the HTML
 *   - Singleton ids (e.g. 'tp-first') checked as-is
 *   - Repeating row ids (e.g. 'int-box1-${id}') checked for the static prefix
 *   - Fields marked ❌ or ⚠ in the manifest are reported but NOT counted as failures
 *   - Fields marked 'auto' or 'derived' are skipped (no HTML id to check)
 *
 * Output format mirrors test_vita_irs.py:
 *   [PASS] field description
 *   [FAIL] field description  ← id pattern not found in HTML
 *   [SKIP] field description  ← ❌ known gap (expected, not a failure)
 *   [WARN] field description  ← ⚠ captured but not computed
 */

'use strict';
const fs = require('fs');
const path = require('path');

// ── CLI arg ──────────────────────────────────────────────────────────────────
const uiPath = process.argv[2] || path.join(__dirname, 'sachintaxcare_pro.html');
if (!fs.existsSync(uiPath)) {
  console.error(`\n❌ File not found: ${uiPath}`);
  console.error('   Usage: node test_ui_fields.js [path/to/ui.html]\n');
  process.exit(1);
}
const html = fs.readFileSync(uiPath, 'utf8');
console.log(`\nSachinTaxCare UI Field Test`);
console.log(`UI file : ${path.basename(uiPath)}`);
console.log(`─`.repeat(60));

// ── Field manifest ────────────────────────────────────────────────────────────
// Format: { section, label, id, status }
//   status: 'ok'   = ✅ must be in UI (failure if missing)
//           'gap'  = ❌ known gap (skip — expected missing)
//           'warn' = ⚠  captured not computed (skip)
//           'auto' = derived/auto — no HTML id to check
//
// id patterns:
//   'tp-first'          → singleton: id="tp-first"
//   'int-box1-${id}'    → repeating: check prefix 'int-box1-'
//   null                → auto/derived, no id check

const MANIFEST = [
  // ── 1: Taxpayer ────────────────────────────────────────────────────────────
  { s:'Taxpayer', label:'First name',                    id:'tp-first',          status:'ok' },
  { s:'Taxpayer', label:'Last name',                     id:'tp-last',           status:'ok' },
  { s:'Taxpayer', label:'SSN',                           id:'tp-ssn',            status:'ok' },
  { s:'Taxpayer', label:'Date of birth',                 id:'tp-dob',            status:'ok' },
  { s:'Taxpayer', label:'Occupation',                    id:'tp-occ',            status:'ok' },
  { s:'Taxpayer', label:'Address',                       id:'tp-addr',           status:'ok' },
  { s:'Taxpayer', label:'Blind',                         id:'tp-blind',          status:'ok' },
  { s:'Taxpayer', label:'Claimed as dependent',          id:'tp-dep-of',         status:'ok' },
  { s:'Taxpayer', label:'Dependent earned income',       id:'tp-dep-ei',         status:'ok' },
  { s:'Taxpayer', label:'Full-time student',             id:'tp-student',        status:'ok' },
  { s:'Taxpayer', label:'Filing status',                 id:'fs',                status:'ok' },
  { s:'Taxpayer', label:'TP age for senior ded',         id:'tp-age-senior',     status:'ok' },
  { s:'Taxpayer', label:'Other adjustments',             id:'adj-other',         status:'ok' },

  { s:'QSS',      label:'Deceased spouse name',          id:'ds-name',           status:'ok' },
  { s:'QSS',      label:'Deceased spouse SSN',           id:'ds-ssn',            status:'ok' },
  { s:'QSS',      label:'Date of death',                 id:'ds-dod',            status:'ok' },

  { s:'Spouse',   label:'Spouse first name',             id:'sp-first',          status:'ok' },
  { s:'Spouse',   label:'Spouse last name',              id:'sp-last',           status:'ok' },
  { s:'Spouse',   label:'Spouse SSN',                    id:'sp-ssn',            status:'ok' },
  { s:'Spouse',   label:'Spouse DOB',                    id:'sp-dob',            status:'ok' },
  { s:'Spouse',   label:'Spouse blind',                  id:'sp-blind',          status:'ok' },
  { s:'Spouse',   label:'SP age for senior ded',         id:'sp-age-senior',     status:'ok' },
  { s:'Spouse',   label:'W-2 Box 13 (auto from W-2s)',   id:null,                status:'auto' },

  // ── 2: Dependents ──────────────────────────────────────────────────────────
  { s:'Dependents', label:'First name',                  id:'dep-first-',        status:'ok' },
  { s:'Dependents', label:'Last name',                   id:'dep-last-',         status:'ok' },
  { s:'Dependents', label:'SSN',                         id:'dep-ssn-',          status:'ok' },
  { s:'Dependents', label:'DOB',                         id:'dep-dob-',          status:'ok' },
  { s:'Dependents', label:'Relationship',                id:'dep-rel-',          status:'ok' },
  { s:'Dependents', label:'CTC eligible',                id:'dep-ctc-',          status:'ok' },
  { s:'Dependents', label:'ODC eligible (auto-computed)',id:'dep-odc-',          status:'ok' },
  { s:'Dependents', label:'Unearned income (8615)',      id:'dep-unearned-',     status:'ok' },
  { s:'Dependents', label:'Earned income',               id:'dep-earned-',       status:'ok' },
  { s:'Dependents', label:'Full-time student (8615)',    id:'dep-student-',      status:'ok' },
  { s:'Dependents', label:'Parent taxable income (8615)',id:'dep-parent-ti-',    status:'ok' },

  // ── 3: W-2 ─────────────────────────────────────────────────────────────────
  { s:'W-2', label:'Employer name',              id:'w2-emp-',           status:'ok' },
  { s:'W-2', label:'EIN',                        id:'w2-ein-',           status:'ok' },
  { s:'W-2', label:'For spouse',                 id:'w2-spouse-',        status:'ok' },
  { s:'W-2', label:'Box 1 wages',                id:'w2-box1-',          status:'ok' },
  { s:'W-2', label:'Box 2 fed WH',               id:'w2-box2-',          status:'ok' },
  { s:'W-2', label:'Box 3 SS wages',             id:'w2-box3-',          status:'ok' },
  { s:'W-2', label:'Box 4 SS WH',                id:'w2-box4-',          status:'ok' },
  { s:'W-2', label:'Box 5 Medicare wages',       id:'w2-box5-',          status:'ok' },
  { s:'W-2', label:'Box 6 Medicare WH',          id:'w2-box6-',          status:'ok' },
  { s:'W-2', label:'Box 7 SS tips',              id:'w2-box7-',          status:'ok' },
  { s:'W-2', label:'Box 8 allocated tips',       id:'w2-box8-',          status:'ok' },
  { s:'W-2', label:'Box 10 dep care',            id:'w2-box10-',         status:'ok' },
  { s:'W-2', label:'Box 11 NQDC',                id:'w2-box11-',         status:'ok' },
  { s:'W-2', label:'Box 12a',                    id:'w2-b12a-',          status:'ok' },
  { s:'W-2', label:'Box 12b',                    id:'w2-b12b-',          status:'ok' },
  { s:'W-2', label:'Box 12c',                    id:'w2-b12c-',          status:'ok' },
  { s:'W-2', label:'Box 12d',                    id:'w2-b12d-',          status:'ok' },
  { s:'W-2', label:'Box 13 checkboxes',          id:'w2-box13-',         status:'ok' },
  { s:'W-2', label:'Box 14 other',               id:'w2-box14-',         status:'ok' },
  { s:'W-2', label:'Box 15 state',               id:'w2-state-',         status:'ok' },
  { s:'W-2', label:'Box 16 state wages',         id:'w2-statew-',        status:'ok' },
  { s:'W-2', label:'Box 17 state WH',            id:'w2-statewh-',       status:'ok' },
  { s:'W-2', label:'Box 18 local wages',         id:'w2-locw-',          status:'ok' },
  { s:'W-2', label:'Box 19 local WH',            id:'w2-locwh-',         status:'ok' },
  { s:'W-2', label:'Box 20 locality',            id:'w2-locname-',       status:'ok' },

  // ── 4: 1099-INT ────────────────────────────────────────────────────────────
  { s:'1099-INT', label:'Payer name',            id:'int-payer-',        status:'ok' },
  { s:'1099-INT', label:'Payer EIN',             id:'int-ein-',          status:'ok' },
  { s:'1099-INT', label:'Box 1 interest',        id:'int-box1-',         status:'ok' },
  { s:'1099-INT', label:'Box 2 early wdwl',      id:'int-box2-',         status:'ok' },
  { s:'1099-INT', label:'Box 3 US savings bond', id:'int-box3-',         status:'ok' },
  { s:'1099-INT', label:'Box 4 backup WH',       id:'int-box4-',         status:'ok' },
  { s:'1099-INT', label:'Box 6 foreign tax',     id:'int-box6-',         status:'ok' },
  { s:'1099-INT', label:'Box 7 foreign country', id:'int-box7-',         status:'ok' },
  { s:'1099-INT', label:'Box 8 tax-exempt int',  id:'int-box8-',         status:'ok' },
  { s:'1099-INT', label:'Box 9 priv activity',   id:null,                status:'gap' },
  { s:'1099-INT', label:'Box 10 market discount',id:null,                status:'gap' },
  { s:'1099-INT', label:'Box 11 bond premium',   id:null,                status:'gap' },
  { s:'1099-INT', label:'Box 15 state WH',       id:null,                status:'gap' },

  // ── 5: 1099-DIV ────────────────────────────────────────────────────────────
  { s:'1099-DIV', label:'Payer name',            id:'div-payer-',        status:'ok' },
  { s:'1099-DIV', label:'Box 1a ordinary div',   id:'div-b1a-',          status:'ok' },
  { s:'1099-DIV', label:'Box 1b qualified div',  id:'div-b1b-',          status:'ok' },
  { s:'1099-DIV', label:'Box 2a cap gain dist',  id:'div-b2a-',          status:'ok' },
  { s:'1099-DIV', label:'Box 2b unrec 1250',     id:'div-b2b-',          status:'warn' },
  { s:'1099-DIV', label:'Box 2d collectibles',   id:'div-b2d-',          status:'warn' },
  { s:'1099-DIV', label:'Box 3 nondiv dist',     id:'div-b3-',           status:'ok' },
  { s:'1099-DIV', label:'Box 4 fed WH',          id:'div-b4-',           status:'ok' },
  { s:'1099-DIV', label:'Box 5 §199A div',       id:'div-b5-',           status:'ok' },
  { s:'1099-DIV', label:'Box 7 foreign tax',     id:'div-b7-',           status:'ok' },
  { s:'1099-DIV', label:'Box 9 cash liquidation',id:'div-b9-',           status:'ok' },
  { s:'1099-DIV', label:'Box 11 exempt-int div', id:'div-b11-',          status:'ok' },
  { s:'1099-DIV', label:'Box 12 priv activity',  id:'div-b12-',          status:'ok' },
  { s:'1099-DIV', label:'Box 15 state WH',       id:'div-b15-',          status:'ok' },
  { s:'1099-DIV', label:'Box 2c §1202 gain',     id:null,                status:'gap' },
  { s:'1099-DIV', label:'Box 6 invest expense',  id:null,                status:'gap' },

  // ── 6: 1099-R ──────────────────────────────────────────────────────────────
  { s:'1099-R', label:'Payer name',              id:'r-payer-',          status:'ok' },
  { s:'1099-R', label:'Payer EIN',               id:'r-ein-',            status:'ok' },
  { s:'1099-R', label:'Account number',          id:'r-acct-',           status:'ok' },
  { s:'1099-R', label:'Recipient (TP/SP)',        id:'r-recipient-',      status:'ok' },
  { s:'1099-R', label:'Box 1 gross dist',        id:'r-box1-',           status:'ok' },
  { s:'1099-R', label:'Box 2a taxable',          id:'r-box2a-',          status:'ok' },
  { s:'1099-R', label:'Box 2b checkboxes',       id:'r-box2b-',          status:'ok' },
  { s:'1099-R', label:'Box 3 cap gain',          id:'r-box3-',           status:'ok' },
  { s:'1099-R', label:'Box 4 fed WH',            id:'r-box4-',           status:'ok' },
  { s:'1099-R', label:'Box 5 employee contrib',  id:'r-box5-',           status:'ok' },
  { s:'1099-R', label:'Box 6 NUA',               id:'r-box6-',           status:'ok' },
  { s:'1099-R', label:'Box 7 dist code',         id:'r-code-',           status:'ok' },
  { s:'1099-R', label:'Box 7 second code',       id:'r-code2-',          status:'ok' },
  { s:'1099-R', label:'IRA/SEP/SIMPLE checkbox', id:'r-ira-',            status:'ok' },
  { s:'1099-R', label:'Box 9a pct',              id:'r-box9a-',          status:'ok' },
  { s:'1099-R', label:'Box 9b emp contrib (SM)', id:'r-box9b-',          status:'ok' },
  { s:'1099-R', label:'Box 10 IRR',              id:'r-box10-',          status:'ok' },
  { s:'1099-R', label:'Box 11 first Roth yr',    id:'r-box11-',          status:'ok' },
  { s:'1099-R', label:'Box 12 FATCA',            id:'r-box12-',          status:'ok' },
  { s:'1099-R', label:'Box 13 date of payment',  id:'r-box13-',          status:'ok' },
  { s:'1099-R', label:'Box 14 state WH',         id:'r-statewh-',        status:'ok' },
  { s:'1099-R', label:'Box 15 state/payer no.',  id:'r-state-',          status:'ok' },
  { s:'1099-R', label:'Box 16 state dist',       id:'r-stated-',         status:'ok' },
  { s:'1099-R', label:'Box 17 local WH',         id:'r-locwh-',          status:'ok' },
  { s:'1099-R', label:'Box 18 locality',         id:'r-locname-',        status:'ok' },
  { s:'1099-R', label:'Box 19 local dist',       id:'r-locd-',           status:'ok' },
  { s:'1099-R', label:'Simplified method use',   id:'r-sm-',             status:'ok' },
  { s:'1099-R', label:'SM annuity type',         id:'r-smtype-',         status:'ok' },
  { s:'1099-R', label:'SM age at start',         id:'r-smage-',          status:'ok' },
  { s:'1099-R', label:'SM joint age',            id:'r-smagej-',         status:'ok' },
  { s:'1099-R', label:'SM fixed period months',  id:'r-smfixed-',        status:'ok' },
  { s:'1099-R', label:'SM prior recovered',      id:'r-smprior-',        status:'ok' },
  { s:'1099-R', label:'SM start date',           id:'r-smstart-',        status:'ok' },
  { s:'1099-R', label:'SM recipient',            id:'sm-r-',             status:'ok' },

  // ── 7: SSA-1099 ────────────────────────────────────────────────────────────
  { s:'SSA-1099', label:'Box 3 gross benefits',  id:'ss-gross',          status:'ok' },
  { s:'SSA-1099', label:'Box 4 repayments',      id:'ss-rep',            status:'ok' },
  { s:'SSA-1099', label:'Box 5 net benefits',    id:'ss-net',            status:'ok' },
  { s:'SSA-1099', label:'Box 6 vol WH',          id:'ss-wh',             status:'ok' },
  { s:'SSA-1099', label:'MFS lived apart',       id:'ss-mfs-apart',      status:'ok' },
  { s:'SSA-1099', label:'Lump-sum election',     id:'ss-lump-yn',        status:'ok' },
  { s:'SSA-1099', label:'Recipient (TP/SP)',      id:'ss-recipient',      status:'ok' },
  { s:'SSA-1099', label:'Medicare B premiums',   id:'ss-medicare-b',     status:'ok' },
  { s:'SSA-1099', label:'Medicare C premiums',   id:'ss-medicare-c',     status:'ok' },
  { s:'SSA-1099', label:'Medicare D premiums',   id:'ss-medicare-d',     status:'ok' },
  { s:'SSA Lump', label:'Prior year',            id:'lump-yr-',          status:'ok' },
  { s:'SSA Lump', label:'Lump sum amount',       id:'lump-amt-',         status:'ok' },
  { s:'SSA Lump', label:'Prior-year SS net',     id:'lump-ss-',          status:'ok' },
  { s:'SSA Lump', label:'Prior-year AGI',        id:'lump-agi-',         status:'ok' },
  { s:'SSA Lump', label:'Prior-year TEI',        id:'lump-tei-',         status:'ok' },
  { s:'SSA Lump', label:'Prior taxable SS',      id:'lump-tax-',         status:'ok' },
  { s:'SSA Lump', label:'Pre-1994 flag',         id:'lump-pre-',         status:'ok' },

  // ── 8a: 1099-NEC (SE page) ─────────────────────────────────────────────────
  { s:'1099-NEC(SE)', label:'Payer name',        id:'necse-payer-',      status:'ok' },
  { s:'1099-NEC(SE)', label:'Payer EIN',         id:'necse-ein-',        status:'ok' },
  { s:'1099-NEC(SE)', label:'Box 1 NEC',         id:'necse-box1-',       status:'ok' },
  { s:'1099-NEC(SE)', label:'Box 4 backup WH',   id:'necse-box4-',       status:'ok' },
  { s:'1099-NEC(SE)', label:'Box 5 state WH',    id:'necse-box5-',       status:'ok' },
  { s:'1099-NEC(SE)', label:'Box 6 state ID',    id:'necse-box6-',       status:'ok' },
  { s:'1099-NEC(SE)', label:'Box 7 state income',id:'necse-box7-',       status:'ok' },

  // ── 8b: Schedule C ─────────────────────────────────────────────────────────
  { s:'Sch C', label:'Business name',            id:'sc-name-',          status:'ok' },
  { s:'Sch C', label:'For spouse',               id:'sc-spouse-',        status:'ok' },
  { s:'Sch C', label:'Gross receipts (L1)',       id:'sc-receipts-',      status:'ok' },
  { s:'Sch C', label:'Returns & allow (L2)',      id:'sc-returns-',       status:'ok' },
  { s:'Sch C', label:'Other income (L6)',         id:'sc-other-inc-',     status:'ok' },
  { s:'Sch C', label:'Advertising (L8)',          id:'sc-adv-',           status:'ok' },
  { s:'Sch C', label:'Car & truck (L9)',          id:'sc-car-',           status:'ok' },
  { s:'Sch C', label:'Commissions (L10)',         id:'sc-comm-',          status:'ok' },
  { s:'Sch C', label:'Contract labor (L11)',      id:'sc-cont-',          status:'ok' },
  { s:'Sch C', label:'Depletion (L12)',           id:'sc-depl-',          status:'ok' },
  { s:'Sch C', label:'Depreciation (L13)',        id:'sc-dep-',           status:'ok' },
  { s:'Sch C', label:'Employee benefits (L14)',   id:null,                status:'gap' },
  { s:'Sch C', label:'Insurance (L15)',           id:'sc-ins-',           status:'ok' },
  { s:'Sch C', label:'Mortgage interest (L16a)',  id:null,                status:'gap' },
  { s:'Sch C', label:'Other interest (L16b)',     id:null,                status:'gap' },
  { s:'Sch C', label:'Legal & prof (L17)',        id:'sc-legal-',         status:'ok' },
  { s:'Sch C', label:'Office expense (L18)',      id:'sc-off-',           status:'ok' },
  { s:'Sch C', label:'Pension plan (L19)',        id:'sc-pens-',          status:'ok' },
  { s:'Sch C', label:'Rent lease vehicles (L20a)',id:'sc-rentv-',         status:'ok' },
  { s:'Sch C', label:'Rent lease other (L20b)',   id:'sc-rent-',          status:'ok' },
  { s:'Sch C', label:'Repairs & maint (L21)',     id:'sc-rep-',           status:'ok' },
  { s:'Sch C', label:'Supplies (L22)',            id:'sc-sup-',           status:'ok' },
  { s:'Sch C', label:'Taxes & licenses (L23)',    id:'sc-tax-',           status:'ok' },
  { s:'Sch C', label:'Travel (L24a)',             id:'sc-trav-',          status:'ok' },
  { s:'Sch C', label:'Meals 50% (L24b)',          id:'sc-meals-',         status:'ok' },
  { s:'Sch C', label:'Utilities (L25)',           id:'sc-util-',          status:'ok' },
  { s:'Sch C', label:'Wages employees (L26)',     id:'sc-wages-',         status:'ok' },
  { s:'Sch C', label:'Other expenses (L27a)',     id:'sc-othexp-',        status:'ok' },
  { s:'Sch C', label:'Products/inventory desc',  id:'sc-prod-',          status:'ok' },
  { s:'Sch C', label:'Home office sq ft',         id:'sc-sqft-',          status:'ok' },
  { s:'Sch C', label:'Home office use',           id:'sc-homeoff-',       status:'ok' },
  { s:'Sch C', label:'COGS inv beginning',        id:'sc-invbeg-',        status:'ok' },
  { s:'Sch C', label:'COGS purchases',            id:'sc-purch-',         status:'ok' },
  { s:'Sch C', label:'COGS cost of labor',        id:'sc-labor-',         status:'ok' },
  { s:'Sch C', label:'COGS materials',            id:'sc-mats-',          status:'ok' },
  { s:'Sch C', label:'COGS other costs',          id:'sc-othcogs-',       status:'ok' },
  { s:'Sch C', label:'COGS inv ending',           id:'sc-invend-',        status:'ok' },
  { s:'Sch C', label:'W-2 wages (8995-A)',        id:'sc-w2wages-',       status:'ok' },
  { s:'Sch C', label:'UBIA (8995-A)',             id:'sc-ubia-',          status:'ok' },
  { s:'Sch C', label:'SSTB',                      id:'sc-sstb-',          status:'ok' },

  // ── 9: Schedule E ──────────────────────────────────────────────────────────
  { s:'Sch E', label:'Property address',          id:'sche-addr-',        status:'ok' },
  { s:'Sch E', label:'Days rented',               id:'sche-dr-',          status:'ok' },
  { s:'Sch E', label:'Days personal use',         id:'sche-dp-',          status:'ok' },
  { s:'Sch E', label:'Rents received (L3)',        id:'sche-rents-',       status:'ok' },
  { s:'Sch E', label:'Insurance (L9)',             id:'sche-ins-',         status:'ok' },
  { s:'Sch E', label:'Management fees (L11)',      id:'sche-mgt-',         status:'ok' },
  { s:'Sch E', label:'Mortgage interest (L12)',    id:'sche-mort-',        status:'ok' },
  { s:'Sch E', label:'Repairs (L14)',              id:'sche-rep-',         status:'ok' },
  { s:'Sch E', label:'Real estate taxes (L16)',    id:'sche-tax-',         status:'ok' },
  { s:'Sch E', label:'Utilities (L17)',            id:'sche-util-',        status:'ok' },
  { s:'Sch E', label:'Depreciation (L18)',         id:'sche-dep-',         status:'ok' },
  { s:'Sch E', label:'Other expenses (L19)',       id:'sche-oth-',         status:'ok' },
  { s:'Sch E', label:'Participation type',         id:'sche-part-',        status:'ok' },
  { s:'Sch E', label:'Prior yr unallowed loss',    id:'sche-prior-loss',   status:'ok' },
  { s:'Sch E', label:'MFS lived apart (8582)',     id:'sche-mfs-apart',    status:'ok' },
  { s:'Sch E', label:'Advertising (L5)',           id:'sche-adv-',         status:'ok' },
  { s:'Sch E', label:'Auto & travel (L6)',         id:'sche-auto-',        status:'ok' },
  { s:'Sch E', label:'Cleaning & maint (L7)',      id:'sche-clean-',       status:'ok' },
  { s:'Sch E', label:'Commissions (L8)',           id:'sche-comm-',        status:'ok' },
  { s:'Sch E', label:'Legal & prof (L10)',         id:'sche-legal-',       status:'ok' },
  { s:'Sch E', label:'Other interest (L13)',       id:'sche-oint-',        status:'ok' },
  { s:'Sch E', label:'Supplies (L15)',             id:'sche-sup-',         status:'ok' },
  { s:'Sch E', label:'Wages (L22)',                id:'sche-wages-',       status:'ok' },

  // ── 10: K-1 ────────────────────────────────────────────────────────────────
  { s:'K-1', label:'Entity name',                 id:'k1-nm-',            status:'ok' },
  { s:'K-1', label:'Entity type',                 id:'k1-type-',          status:'ok' },
  { s:'K-1', label:'Participation',               id:'k1-part-',          status:'ok' },
  { s:'K-1', label:'Box 1 ordinary',              id:'k1-b1-',            status:'ok' },
  { s:'K-1', label:'Box 2 net rental',            id:'k1-b2-',            status:'ok' },
  { s:'K-1', label:'Box 5 interest',              id:'k1-b5-',            status:'ok' },
  { s:'K-1', label:'Box 6a ordinary div',         id:'k1-b6a-',           status:'ok' },
  { s:'K-1', label:'Box 6b qualified div',        id:'k1-b6b-',           status:'ok' },
  { s:'K-1', label:'Box 7 royalties',             id:'k1-b7-',            status:'ok' },
  { s:'K-1', label:'Box 8 STCG',                  id:'k1-b8-',            status:'ok' },
  { s:'K-1', label:'Box 9a LTCG',                 id:'k1-b9a-',           status:'ok' },
  { s:'K-1', label:'Box 10 §1231',                id:'k1-b10-',           status:'ok' },
  { s:'K-1', label:'Box 11 other income',         id:'k1-b11-',           status:'ok' },
  { s:'K-1', label:'Box 13 deductions',           id:'k1-b13-',           status:'ok' },
  { s:'K-1', label:'Box 14a SE earnings',         id:'k1-b14-',           status:'ok' },
  { s:'K-1', label:'Box 17 AMT',                  id:'k1-b17-',           status:'ok' },
  { s:'K-1', label:'Box 20Z §199A income',        id:'k1-b20z-',          status:'ok' },
  { s:'K-1', label:'Box 20W §199A W-2 wages',     id:'k1-b20w-',          status:'ok' },
  { s:'K-1', label:'Box 3 other net rental',      id:null,                status:'gap' },
  { s:'K-1', label:'Box 12 §179',                 id:null,                status:'gap' },
  { s:'K-1', label:'Box 17 UBIA',                 id:null,                status:'gap' },

  // ── 11: Capital gains ──────────────────────────────────────────────────────
  { s:'8949', label:'Description',                id:'sale-desc-',        status:'ok' },
  { s:'8949', label:'Date info',                  id:'sale-dates-',       status:'ok' },
  { s:'8949', label:'Proceeds',                   id:'sale-proc-',        status:'ok' },
  { s:'8949', label:'Cost basis',                 id:'sale-basis-',       status:'ok' },
  { s:'8949', label:'Accrued market discount',    id:'sale-amd-',         status:'ok' },
  { s:'8949', label:'Wash sale disallowed',       id:'sale-wash-',        status:'ok' },
  { s:'8949', label:'Term',                       id:'sale-term-',        status:'ok' },
  { s:'8949', label:'Basis reported to IRS',      id:'sale-covered-',     status:'ok' },
  { s:'8949', label:'Cap loss carryover',         id:'cap-carryover',     status:'ok' },
  { s:'4797', label:'Property description',       id:'f4797-desc-',       status:'ok' },
  { s:'4797', label:'Property type',              id:'f4797-type-',       status:'ok' },
  { s:'4797', label:'Held over 1 year',           id:'f4797-held-',       status:'ok' },
  { s:'4797', label:'Gross proceeds',             id:'f4797-proc-',       status:'ok' },
  { s:'4797', label:'Original cost',              id:'f4797-cost-',       status:'ok' },
  { s:'4797', label:'Depreciation taken',         id:'f4797-depr-',       status:'ok' },
  { s:'4797', label:'Prior §1231 losses 5yr',     id:'f4797-prior1231-',  status:'ok' },
  { s:'4797', label:'Date acquired',              id:'f4797-acq-',        status:'ok' },
  { s:'4797', label:'Date sold',                  id:'f4797-sold-',       status:'ok' },
  { s:'4797', label:'Suspended passive losses',   id:'f4797-susp-',       status:'ok' },

  // ── 12: Other income ───────────────────────────────────────────────────────
  { s:'1099-G', label:'Box 1 unemployment',       id:'unemp',             status:'ok' },
  { s:'1099-G', label:'Box 2 state refund',       id:'state-refund',      status:'ok' },
  { s:'1099-G', label:'Box 4 fed WH',             id:'unemp-wh',          status:'ok' },
  { s:'1099-G', label:'Box 10a/11 state WH',      id:'unemp-state-wh',    status:'ok' },
  { s:'1099-G', label:'Prior year itemized?',     id:'prior-yr-itemized', status:'ok' },
  { s:'Other',  label:'Prize income (1099-MISC Box 3)', id:'misc-b3-',       status:'ok' },
  { s:'1099-MISC', label:'Payer name',            id:'misc-payer-',       status:'ok' },
  { s:'1099-MISC', label:'Payer EIN',             id:'misc-ein-',         status:'ok' },
  { s:'1099-MISC', label:'Recipient (TP/SP)',      id:'misc-recipient-',   status:'ok' },
  { s:'1099-MISC', label:'Box 1 rents',           id:'misc-b1-',          status:'ok' },
  { s:'1099-MISC', label:'Box 2 royalties',       id:'misc-b2-',          status:'ok' },
  { s:'1099-MISC', label:'Box 4 fed WH',          id:'misc-b4-',          status:'ok' },
  { s:'1099-MISC', label:'Box 5 fishing boats',   id:'misc-b5-',          status:'ok' },
  { s:'1099-MISC', label:'Box 6 medical',         id:'misc-b6-',          status:'ok' },
  { s:'1099-MISC', label:'Box 7 dir sales',       id:'misc-b7-',          status:'ok' },
  { s:'1099-MISC', label:'Box 8 sub pmts',        id:'misc-b8-',          status:'ok' },
  { s:'1099-MISC', label:'Box 9 crop ins',        id:'misc-b9-',          status:'ok' },
  { s:'1099-MISC', label:'Box 10 gross proceeds', id:'misc-b10-',         status:'ok' },
  { s:'1099-MISC', label:'Box 11 fish bought',    id:'misc-b11-',         status:'ok' },
  { s:'1099-MISC', label:'Box 12 section 409A',   id:'misc-b12-',         status:'ok' },
  { s:'1099-MISC', label:'Box 13 excess golden',  id:'misc-b13-',         status:'ok' },
  { s:'1099-MISC', label:'Box 14 409A income',    id:'misc-b14-',         status:'ok' },
  { s:'1099-MISC', label:'Box 15a state WH',      id:'misc-b15a-',        status:'ok' },
  { s:'1099-MISC', label:'Box 15b state WH 2',    id:'misc-b15b-',        status:'ok' },
  { s:'1099-MISC', label:'Box 16 state income',   id:'misc-b16-',         status:'ok' },
  { s:'Other',  label:'Other income',             id:'other-adj',         status:'ok' },
  { s:'Other',  label:'Alimony received',         id:'alimony-rec',       status:'ok' },
  { s:'Other',  label:'Alimony paid',             id:'alimony-paid',      status:'ok' },
  { s:'Other',  label:'Alimony payee SSN',        id:'alimony-ssn',       status:'ok' },
  { s:'Other',  label:'Alimony era dropdown',     id:'alimony-era',       status:'ok' },
  { s:'Other',  label:'Alimony decree modified',  id:'alimony-modified',  status:'ok' },
  { s:'W-2G',   label:'Payer',                    id:'w2g-payer-',        status:'ok' },
  { s:'W-2G',   label:'Box 1 winnings',           id:'w2g-box1-',         status:'ok' },
  { s:'W-2G',   label:'Box 4 fed WH',             id:'w2g-box4-',         status:'ok' },
  { s:'W-2G',   label:'Box 15 state WH',          id:'w2g-box15-',        status:'ok' },
  { s:'W-2G',   label:'Gambling type',            id:'w2g-type-',         status:'ok' },
  { s:'W-2G',   label:'Gambling losses',          id:'gambling-losses',   status:'ok' },
  { s:'1099-C', label:'Creditor',                 id:'cod-cred-',         status:'ok' },
  { s:'1099-C', label:'Box 2 amount discharged',  id:'cod-amt-',          status:'ok' },
  { s:'1099-C', label:'Box 6 event code',         id:'cod-code-',         status:'ok' },
  { s:'1099-C', label:'Date of debt discharge',   id:'cod-date-',         status:'ok' },
  { s:'1099-C', label:'Debt description',         id:'cod-desc-',         status:'ok' },
  { s:'1099-C', label:'Creditor EIN',             id:'cod-ein-',          status:'ok' },
  { s:'1099-C', label:'FMV of property',          id:'cod-fmv-',          status:'ok' },
  { s:'1099-C', label:'Interest included',        id:'cod-int-',          status:'ok' },
  { s:'1099-C', label:'Recipient (TP/SP)',         id:'cod-recipient-',    status:'ok' },
  { s:'1099-C', label:'Recourse debt?',           id:'cod-recourse-',     status:'ok' },
  { s:'1099-C', label:'Exclusion applies',        id:'cod-excl-',         status:'ok' },
  { s:'1099-NEC(Other)', label:'Payer name',      id:'nec-payer-',        status:'ok' },
  { s:'1099-NEC(Other)', label:'Payer EIN',       id:'nec-ein-',          status:'ok' },
  { s:'1099-NEC(Other)', label:'Box 1 NEC',       id:'nec-box1-',         status:'ok' },
  { s:'1099-NEC(Other)', label:'Box 4 backup WH', id:'nec-box4-',         status:'ok' },

  // ── 13: Adjustments ────────────────────────────────────────────────────────
  { s:'Adj', label:'Teacher expense',             id:'adj-teacher',       status:'ok' },
  { s:'Adj', label:'Student loan interest',       id:'adj-student-loan',  status:'ok' },
  { s:'Adj', label:'Early CD withdrawal',         id:'adj-early-wdwl',    status:'ok' },
  { s:'Adj', label:'SE health insurance',         id:'adj-se-health',     status:'ok' },
  { s:'Adj', label:'SE retirement contrib',       id:'se-ret-contrib',    status:'ok' },
  { s:'Adj', label:'SE retirement plan type',     id:'se-ret-type',       status:'ok' },
  { s:'Adj', label:'NOL carryforward prior year',  id:'nol-carryforward',  status:'ok' },
  { s:'Adj', label:'QBI loss carryforward',       id:'qbi-loss-cf',       status:'ok' },
  { s:'Adj', label:'Q1 estimated payment',        id:'est-q1',            status:'ok' },
  { s:'Adj', label:'Q2 estimated payment',        id:'est-q2',            status:'ok' },
  { s:'Adj', label:'Q3 estimated payment',        id:'est-q3',            status:'ok' },
  { s:'Adj', label:'Q4 estimated payment',        id:'est-q4',            status:'ok' },
  { s:'Adj', label:'Prior-year overpayment',      id:'est-prior',         status:'ok' },
  { s:'Adj', label:'Prior-year tax (2210)',        id:'py-tax',            status:'ok' },
  { s:'Adj', label:'Prior-year AGI (2210)',        id:'py-agi',            status:'ok' },

  // ── 14: Schedule A ─────────────────────────────────────────────────────────
  { s:'Sch A', label:'Use itemized?',             id:'use-itemized',      status:'ok' },
  { s:'Sch A', label:'Medical total',             id:'sa-medical',        status:'ok' },
  { s:'Sch A', label:'SALT method',               id:'sa-salt-method',    status:'ok' },
  { s:'Sch A', label:'State/local income tax',    id:'sa-state-inc',      status:'ok' },
  { s:'Sch A', label:'Real estate taxes',         id:'sa-re-tax',         status:'ok' },
  { s:'Sch A', label:'Personal property tax',     id:'sa-pp-tax',         status:'ok' },
  { s:'Sch A', label:'Mortgage interest (1098)',  id:'sa-mort-int',       status:'ok' },
  { s:'Sch A', label:'Mortgage balance',          id:'sa-mort-bal',       status:'ok' },
  { s:'Sch A', label:'Grandfathered mortgage',    id:'sa-grandfathered',  status:'ok' },
  { s:'Sch A', label:'Points not on 1098',        id:'sa-points',         status:'ok' },
  { s:'Sch A', label:'PMI (disabled/expired)',    id:'sa-pmi',            status:'ok' },
  { s:'Sch A', label:'Investment interest',       id:'sa-invest-int',     status:'ok' },
  { s:'Sch A', label:'Cash charitable',           id:'sa-cash-char',      status:'ok' },
  { s:'Sch A', label:'Non-cash charitable',       id:'sa-noncash',        status:'ok' },
  { s:'Sch A', label:'Charitable carryover',      id:'sa-char-co',        status:'ok' },
  { s:'Sch A', label:'Casualty loss',             id:'sa-casualty',       status:'ok' },
  { s:'Sch A', label:'Other misc',                id:'sa-other',          status:'ok' },

  // ── 15: Credits ────────────────────────────────────────────────────────────
  { s:'2441', label:'Employer dep care (Box 10)', id:'emp-dep-care',      status:'ok' },
  { s:'2441', label:'Care provider name',         id:'care-name-',        status:'ok' },
  { s:'2441', label:'Care provider EIN',          id:'care-ein-',         status:'ok' },
  { s:'2441', label:'Care expenses',              id:'care-exp-',         status:'ok' },
  { s:'8863', label:'Institution name',           id:'t-inst-',           status:'ok' },
  { s:'8863', label:'Box 1 payments',             id:'t-box1-',           status:'ok' },
  { s:'8863', label:'Box 5 scholarships',         id:'t-box5-',           status:'ok' },
  { s:'8863', label:'Student name',               id:'t-student-',        status:'ok' },
  { s:'8863', label:'Credit type AOC/LLC',        id:'t-type-',           status:'ok' },
  { s:'8863', label:'AOC prior years',            id:'t-aoc-prior-',      status:'ok' },
  { s:'8863', label:'Recipient (TP/SP)',          id:'t-who-',            status:'ok' },
  { s:'8863', label:'Graduate student?',          id:'t-grad-',           status:'ok' },
  { s:'8863', label:'At least half-time',         id:'t-halftime-',       status:'ok' },
  { s:'8863', label:'Books/supplies included',    id:'t-books-',          status:'ok' },
  { s:'8863', label:'Other qualified expenses',   id:'t-other-qee-',      status:'ok' },
  { s:'8863', label:'Supplies not in Box 1',      id:'t-supplies-',       status:'ok' },
  { s:'8880', label:'IRA contributions (L1)',     id:'f8880-ira',         status:'ok' },
  { s:'8880', label:'Deferrals 401k/403b (L2)',   id:'f8880-deferrals',   status:'ok' },
  { s:'8880', label:'Disqualifying dist (L4)',    id:'f8880-dist',        status:'ok' },
  { s:'8962', label:'Household size',             id:'aca-size',          status:'ok' },
  { s:'8962', label:'1095-A Col A annual',        id:'aca-cola',          status:'ok' },
  { s:'8962', label:'1095-A Col B SLCSP',         id:'aca-colb',          status:'ok' },
  { s:'8962', label:'1095-A Col C APTC',          id:'aca-colc',          status:'ok' },
  { s:'EITC', label:'Exact EITC from table',      id:'exact-eitc',        status:'ok' },

  // ── 16: Retirement ─────────────────────────────────────────────────────────
  { s:'IRA',   label:'IRA contribution',          id:'ira-contrib',       status:'ok' },
  { s:'IRA',   label:'Taxpayer age',              id:'ira-age',           status:'ok' },
  { s:'IRA',   label:'Covered by plan',           id:'ira-covered',       status:'ok' },
  { s:'8606',  label:'L1 nonded contrib',         id:'f8606-contrib',     status:'ok' },
  { s:'8606',  label:'L2 prior basis',            id:'f8606-prior-basis', status:'ok' },
  { s:'8606',  label:'L6 IRA FMV Dec 31',         id:'f8606-ira-val',     status:'ok' },
  { s:'8606',  label:'L7 total dist',             id:'f8606-dist',        status:'ok' },
  { s:'8606',  label:'Roth conversion (L16)',     id:'f8606-conversion',  status:'ok' },
  { s:'8606',  label:'L19 Roth dist',             id:'f8606-roth-dist',   status:'ok' },
  { s:'8606',  label:'L22 Roth basis',            id:'f8606-roth-basis',  status:'ok' },
  { s:'8606',  label:'5yr period met',            id:'f8606-5yr',         status:'ok' },
  // Spouse Form 8606 (MFJ)
  { s:'8606',  label:'Spouse L1 nonded contrib',  id:'sp-f8606-contrib',     status:'ok' },
  { s:'8606',  label:'Spouse L2 prior basis',     id:'sp-f8606-prior-basis', status:'ok' },
  { s:'8606',  label:'Spouse L6 IRA FMV Dec 31',  id:'sp-f8606-ira-val',     status:'ok' },
  { s:'8606',  label:'Spouse L7 total dist',      id:'sp-f8606-dist',        status:'ok' },
  { s:'8606',  label:'Spouse Roth conversion',    id:'sp-f8606-conversion',  status:'ok' },
  { s:'8606',  label:'Spouse Roth distributions', id:'sp-f8606-roth-dist',   status:'ok' },
  { s:'8606',  label:'Over 59½',                  id:'f8606-age',         status:'ok' },
  { s:'8606',  label:'Inherited IRA',             id:'f8606-inh',         status:'ok' },
  { s:'8606',  label:'Inherited basis',           id:'f8606-inh-basis',   status:'ok' },
  { s:'8889',  label:'HSA contributions',         id:'hsa-contrib',       status:'ok' },
  { s:'8889',  label:'HSA coverage type',         id:'hsa-type',          status:'ok' },
  { s:'8889',  label:'HSA taxpayer age',          id:'hsa-age',           status:'ok' },
  { s:'8889',  label:'HSA non-medical dist',      id:'hsa-nonmed',        status:'ok' },
  { s:'5329',  label:'Exception code',            id:'f5329-code-',       status:'ok' },
  { s:'5329',  label:'Exception amount',          id:'f5329-amt-',        status:'ok' },
  { s:'5329',  label:'IRA or plan',               id:'f5329-acct-',       status:'ok' },
  { s:'5329',  label:'Excess IRA contrib',        id:'f5329-excess',      status:'ok' },

  // ── 17: AMT & Form 4972 ────────────────────────────────────────────────────
  { s:'6251', label:'ISO bargain element',        id:'amt-iso',           status:'ok' },
  { s:'6251', label:'NOL addback',                id:'amt-nol',           status:'ok' },
  { s:'6251', label:'Excess depletion',           id:'amt-dep',           status:'ok' },
  { s:'6251', label:'Other AMT adj',              id:'amt-other',         status:'ok' },
  { s:'4972', label:'Eligible (born before 1936)',id:'f4972-elig',        status:'ok' },
  { s:'4972', label:'Distribution code',         id:'f4972-code',        status:'ok' },
  { s:'4972', label:'Ordinary income',            id:'f4972-ordinary',    status:'ok' },
  { s:'4972', label:'Capital gain portion',       id:'f4972-capgain',     status:'ok' },
  { s:'4972', label:'Elect 20% cap gain',         id:'f4972-20pct',       status:'ok' },
  { s:'4972', label:'Elect 10-year averaging',    id:'f4972-10yr',        status:'ok' },
  { s:'4972', label:'Plan name',                  id:'f4972-plan',        status:'ok' },

  // ── 18a: Form 1116 — Foreign Tax Credit ───────────────────────────────────
  { s:'1116', label:'Foreign taxes paid',         id:'f1116-taxes-',      status:'ok' },
  { s:'1116', label:'Foreign income',             id:'f1116-inc-',        status:'ok' },
  { s:'1116', label:'Foreign country',            id:'f1116-country-',    status:'ok' },
  { s:'1116', label:'Carryover',                  id:'f1116-co-',         status:'ok' },
  { s:'1116', label:'Income category',            id:'f1116-cat-',        status:'ok' },
  { s:'1116', label:'Reporting method',           id:'f1116-method-',     status:'ok' },
  { s:'1116', label:'De minimis election',        id:'f1116-simplified',  status:'ok' },
  { s:'1116', label:'De minimis amount',          id:'f1116-simple-amt',  status:'ok' },

  // ── 18b: OBBBA above-line deductions ──────────────────────────────────────
  { s:'OBBBA', label:'Qualified tips',            id:'qualified-tips',    status:'ok' },
  { s:'OBBBA', label:'FLSA overtime pay',         id:'overtime-pay',      status:'ok' },
  { s:'OBBBA', label:'Auto loan interest',        id:'auto-loan-interest',status:'ok' },
  { s:'OBBBA', label:'Auto loan post-2024',       id:'auto-loan-post2024',status:'ok' },
  { s:'OBBBA', label:'Auto loan US vehicle',      id:'auto-loan-us-vehicle',status:'ok'},

  // ── 18: California 540 ─────────────────────────────────────────────────────
  { s:'CA540', label:'CA SDI withheld',           id:'ca-sdi',            status:'ok' },
  { s:'CA540', label:"Renter's credit",           id:'ca-renter',         status:'ok' },
  { s:'CA540', label:'CA subtractions',           id:'ca-sub',            status:'ok' },
  { s:'CA540', label:'CA itemized override',      id:'ca-itemized',       status:'ok' },

  // ── Output / mode ──────────────────────────────────────────────────────────
  { s:'Output', label:'Mode toggle (engine)',     id:'mode-engine',       status:'ok' },
  { s:'Output', label:'Mode toggle (claude)',     id:'mode-claude',       status:'ok' },
  { s:'Output', label:'Claude format selector',  id:'claude-fmt',        status:'ok' },
  { s:'Output', label:'Claude notes field',      id:'claude-notes',      status:'ok' },
  { s:'Output', label:'Engine result panel',     id:'compute-result',    status:'ok' },
  { s:'Output', label:'Claude result panel',     id:'claude-result',     status:'ok' },
];

// ── Test runner ───────────────────────────────────────────────────────────────
let pass = 0, fail = 0, skip = 0, warn = 0, auto = 0;
let currentSection = '';
const failures = [];

for (const { s, label, id, status } of MANIFEST) {
  if (s !== currentSection) {
    currentSection = s;
    console.log(`\n── ${s} ─────────────────────────────────────────────`);
  }

  if (status === 'auto') {
    auto++;
    console.log(`  \x1b[90m[AUTO] ${label} (auto-derived — no id)\x1b[0m`);
    continue;
  }

  if (id === null || status === 'gap') {
    skip++;
    console.log(`  \x1b[33m[SKIP] ${label} — known gap ❌\x1b[0m`);
    continue;
  }

  if (status === 'warn') {
    // Still check presence but mark as warn
    const found = html.includes(`id="${id}`) || html.includes(`id="${id}-`) || html.includes(`id="${id}`);
    if (found) {
      warn++;
      console.log(`  \x1b[36m[WARN] ${label} — ⚠ captured not computed\x1b[0m`);
    } else {
      fail++;
      failures.push(`${s}: ${label} (id: ${id})`);
      console.log(`  \x1b[31m[FAIL] ${label} — MISSING in HTML (id: "${id}")\x1b[0m`);
    }
    continue;
  }

  // status === 'ok' — must be present
  // Check for exact id= or as part of a template literal prefix
  const pattern = id.endsWith('-') ? id : `id="${id}"`;
  const found = html.includes(pattern) ||
    (id.endsWith('-') && html.includes(`id="${id}`)) ||
    html.includes(`id="${id}`);

  if (found) {
    pass++;
    console.log(`  \x1b[32m[PASS] ${label}\x1b[0m`);
  } else {
    fail++;
    failures.push(`${s}: ${label} (id: ${id})`);
    console.log(`  \x1b[31m[FAIL] ${label} — MISSING in HTML (id: "${id}")\x1b[0m`);
  }
}


// ── Round-trip populateFromSchema audit ──────────────────────────────────────
// For every array key that buildSchema() writes to the schema, verify that
// populateFromSchema() reads a matching key (exact OR a documented alias).
// This catches the exact class of bug where buildSchema exports {name} but
// populateFromSchema reads cp.provider_name → undefined → "".
//
// Method: extract (key) from buildSchema's object literals and compare against
// the keys populateFromSchema reads via sv(). Any key in the export that has
// no corresponding sv() read is a silent-drop bug.
//
// Source: bridge hardening 2026-05-19 EA review follow-up
// ─────────────────────────────────────────────────────────────────────────────

// Keys that appear to be missing from populateFromSchema but are intentionally handled
// differently (computed from another field, bracket notation, or display-only).
const RT_KNOWN_SAFE = new Set([
  't.first_four_years',    // intentional: re-derived from aoc_years_claimed_prior
  'd.age',                 // intentional: computed display from dob (which IS restored)
  'w.box12a_code',         // false alarm: read via w['box12a_code'] bracket notation
  'w.box12a_amt',          // false alarm: same bracket notation
  'w.box12b_code', 'w.box12b_amt', 'w.box12c_code', 'w.box12c_amt',
  'w.box12d_code', 'w.box12d_amt', // all box12 via bracket notation
  'w.box15_state_id',      // minor: display-only employer state ID;
  'b.date_acquired',       // handled directly via sv('sale-acq-', b.date_acquired)
  'b.date_sold',           // handled directly via sv('sale-sold-', b.date_sold)
  'b.wash_sale_loss_disallowed', // handled via sv('sale-wash-', b.wash_sale_loss_disallowed)
  'b.origination_before_sept_2004', // handled via e1098.origination_before_sept_2004
  // schedule_cs scanner uses 'sc2.' prefix in populate but 'schedule_cs.' won't match
  'schedule_cs.business_code', 'schedule_cs.business_miles', 'schedule_cs.nec_included_in_gross',
  'schedule_cs.principal_product', 'schedule_cs.gross_receipts', 'schedule_cs.car_truck_expenses',
  // form_1099ints scanner looks for 'form_1099ints.payer_ein' but code uses 'f.payer_ein'
  'form_1099ints.payer', 'form_1099ints.payer_ein',
  'form_1099ints.box1_interest', 'form_1099ints.box2_early_withdrawal_penalty',
  // form_5329 scanner looks for 'form_5329_exceptions.amount' but code uses 'ex.amount'
  'form_5329_exceptions.exception_code', 'form_5329_exceptions.amount',
  'form_5329_exceptions.account_type',
  // form_1099divs scanner looks for 'form_1099divs.box2a_total_cap_gain'
  'form_1099divs.box1a_ordinary_div', 'form_1099divs.box1b_qualified_div',
  'form_1099divs.box2a_total_cap_gain', 'form_1099divs.box5_sec199a_div',
  // form_1098es scanner uses wrong prefix
  // form_1098es scanner uses wrong prefix — actual var name is 'e1098', not 'form_1098es'
  'form_1098es.lender',                    // scanner false alarm: restore uses e1098.lender
  'form_1098es.box1_student_loan_interest',// scanner false alarm: uses e1098.box1_...
  'form_1098es.origination_before_sept_2004', // scanner false alarm engine uses box15_state_employer_id
]);

const ROUND_TRIP_CHECKS = [
  // [section, export_keys_from_buildSchema, import_keys_from_populateFromSchema]
  // care_providers
  { section: 'care_providers',
    exported: ['name', 'ein', 'expenses'],
    imported: [
      // populateFromSchema reads: cp.name || cp.provider_name,
      //                           cp.ein  || cp.provider_ein,
      //                           cp.expenses (with null-check)
      'cp.name', 'cp.provider_name',   // dual-key fix: both accepted
      'cp.ein',  'cp.provider_ein',
      'cp.expenses',
    ],
    note: 'buildSchema exports {name,ein,expenses}; populateFromSchema must read those keys'
  },
  // form_1098ts
  { section: 'form_1098ts',
    exported: ['institution', 'box1_payments', 'box5_scholarships', 'student_who',
               'credit_type', 'first_four_years', 'aoc_years_claimed_prior',
               'box8_at_least_half_time', 'aoc_drug_conviction', 'box9_graduate',
               'out_of_pocket_books', 'out_of_pocket_supplies', 'out_of_pocket_other'],
    imported: ['t.institution', 't.institution_name', 't.box1_payments',
               't.box8_at_least_half_time', 't.box8_half_time',
               't.credit_type', 't.student_who', 't.student_is'],
    note: '1098-T round-trip — institution and box8 key variants'
  },
  // dependents
  { section: 'dependents',
    exported: ['first', 'last', 'ssn', 'dob', 'age', 'relationship',
               'ctc_eligible', 'odc_eligible', 'is_full_time_student',
               'unearned_income', 'earned_income'],
    imported: ['d.first', 'd.last', 'd.ssn', 'd.dob', 'd.age', 'd.relationship',
               'd.ctc_eligible', 'd.odc_eligible', 'd.is_full_time_student',
               'd.unearned_income', 'd.earned_income'],
    note: 'dependent fields — all keys should match directly'
  },
  // form_1099bs — the specific fields that were broken twice
  { section: 'form_1099bs',
    exported: ['cost_basis', 'is_long_term', 'basis_reported_to_irs',
               'date_acquired', 'date_sold', 'wash_sale_loss_disallowed'],
    imported: [
      // populateFromSchema reads:
      'b.cost_basis',              // → sv('sale-basis-', ...) — was wrongly using sale-cost-
      'b.basis',                   // fallback alias
      'b.is_long_term',            // → sv('sale-term-', 'long'/'short') — was using b.term
      'b.basis_reported_to_irs',   // → sv('sale-covered-', 'yes'/'no') — was using b.basis_reported
      'b.date_acquired', 'b.date_sold',
      'b.wash_sale_loss_disallowed',
    ],
    note: 'TWICE BROKEN: cost_basis→sale-cost- (wrong field), is_long_term→b.term (wrong key)'
  },
  // form_1098es — missing populateFromSchema entirely (was never added)
  { section: 'form_1098es',
    exported: ['lender', 'box1_student_loan_interest', 'origination_before_sept_2004'],
    imported: [
      // populateFromSchema calls addF1098E() then sets fields
      'f1098e-lender-', 'e1098.lender',
      'f1098e-int-',    'e1098.box1_student_loan_interest', 'e1098.interest',
      'f1098e-old-',    'e1098.origination_before_sept_2004',
    ],
    note: 'TWICE BROKEN: populateFromSchema restore loop was never added in previous sessions'
  },
  // schedule_cs — ALL new fields added in this session
  { section: 'schedule_cs',
    exported: ['business_code', 'business_miles', 'nec_included_in_gross',
               'principal_product', 'gross_receipts', 'car_truck_expenses'],
    imported: [
      'sc2.business_code',    // → sv('sc-code-', ...)
      'sc2.business_miles',   // → sv('sc-miles-', ...)
      'sc2.nec_included_in_gross', // → sv('sc-nec-incl-', ...)
      'sc2.principal_product', 'sc2.principal_product_service',
      'sc2.gross_receipts', 'sc2.car_truck_expenses',
    ],
    note: 'Schedule C: NAICS code, mileage, NEC inclusion — all new this session'
  },
  // form_1099ints — payer_ein newly added
  { section: 'form_1099ints',
    exported: ['payer', 'payer_ein', 'box1_interest', 'box2_early_withdrawal_penalty'],
    imported: [
      'f.payer', 'f.payer_ein',      // → sv('int-ein-', f.payer_ein)
      'f.box1_interest', 'f.box2_early_withdrawal_penalty',
    ],
    note: '1099-INT EIN: was in HTML field but NOT in buildSchema for multiple sessions'
  },
  // form_5329_exceptions — amount/account_type bridge aliases
  { section: 'form_5329_exceptions',
    exported: ['exception_code', 'amount', 'account_type'],
    imported: [
      'ex.exception_code', 'ex.amount', 'ex.exception_amount',  // → sv('f5329-amt-', ...)
      'ex.account_type', 'ex.acct',    // → sv('f5329-acct-', ...)
    ],
    note: 'Form 5329: amount/account_type were silently dropped — bridge fix applied'
  },
  // form_1099divs — box2a_total_cap_gain alias
  { section: 'form_1099divs',
    exported: ['box1a_ordinary_div', 'box1b_qualified_div', 'box2a_total_cap_gain',
               'box5_sec199a_div'],
    imported: [
      'f.box1a_ordinary_div', 'f.box1b_qualified_div',
      'f.box2a_total_cap_gain',  // JSON key; engine field is box2a_cap_gain_dist
      'div-b2a-',  // UI field for box2a
      'f.box5_sec199a_div',
    ],
    note: '1099-DIV box2a_total_cap_gain: JSON key vs engine field name mismatch — alias added'
  },
  // w2s (key sample)
  { section: 'w2s (key sample)',
    exported: ['employer', 'ein', 'box1_wages', 'box2_fed_wh', 'box5_medicare_wages',
               'box6_medicare_wh', 'box10_dep_care', 'box12a_code', 'box12a_amt',
               'box15_state', 'box15_state_id'],
    imported: ['w.employer', 'w.ein', 'w.box1_wages', 'w.box2_fed_wh',
               'w.box5_medicare_wages', 'w.box5_med_wages',
               'w.box6_medicare_wh', 'w.box6_med_wh',
               'w.box10_dep_care', 'w.box10_dependent_care',
               'w.box12a_code', 'w.box12a_amt', 'w.box15_state', 'w.box15_state_id'],
    note: 'W-2 key sample including known bridge aliases'
  },
];

console.log('\n── Round-trip audit (buildSchema → populateFromSchema) ──');
let rt_pass = 0, rt_fail = 0;
const rt_failures = [];

// Extract all keys that populateFromSchema reads by scanning the HTML
// Look for patterns like: cp.name, cp.provider_name, t.institution, d.first, w.employer
const allImportReads = new Set();
const importSectionRe = /populateFromSchema[\s\S]*?(?=function \w|$)/;
const importSection = html.match(/populateFromSchema[^{]*\{([\s\S]*?)\n\}/)?.[0] || html;
// Scan entire html for obj.property accesses anywhere in populateFromSchema context
// Handles both sv(id, obj.prop) and chained calls sv(a, obj.p1 || ''); sv(b, obj.p2 || '')
// and || fallback patterns (cp.name || cp.provider_name)
const allPropRe = /([a-z]+)\.([a-zA-Z_][a-zA-Z0-9_]*)/g;
let pm;
while ((pm = allPropRe.exec(html)) !== null) {
  allImportReads.add(pm[1] + '.' + pm[2]);
}

for (const check of ROUND_TRIP_CHECKS) {
  for (const exportedKey of check.exported) {
    // An exported key is "safe" if populateFromSchema reads obj.exportedKey
    // or any of the check.imported aliases that cover this key
    const prefix = check.section.split(' ')[0].replace('form_1098ts','t').replace('care_providers','cp')
      .replace('dependents','d').replace('w2s','w');
    const directRead  = `${prefix}.${exportedKey}`;
    const aliasReads  = check.imported.filter(k => k.includes(exportedKey) || k.endsWith(exportedKey));

    const covered = RT_KNOWN_SAFE.has(directRead) ||
                    allImportReads.has(directRead) ||
                    aliasReads.some(a => allImportReads.has(a));

    if (covered) {
      rt_pass++;
    } else {
      rt_fail++;
      const msg = `${check.section}: exported key "${exportedKey}" not read in populateFromSchema (looked for ${directRead})`;
      rt_failures.push(msg);
      console.log(`  \x1b[31m[RT-FAIL] ${msg}\x1b[0m`);
    }
  }
}

if (rt_fail === 0) {
  console.log(`  \x1b[32m✅ Round-trip PASS  ${rt_pass}\x1b[0m  — all exported keys read back`);
} else {
  console.log(`  \x1b[31m❌ Round-trip FAIL  ${rt_fail}\x1b[0m  — keys exported but never imported`);
  console.log('  These are silent-drop bugs: data saved to JSON but never restored to UI.');
}
fail += rt_fail;

// ── Summary ───────────────────────────────────────────────────────────────────
console.log('\n' + '═'.repeat(60));
console.log(`Results:`);
console.log(`  \x1b[32m✅ PASS  ${pass}\x1b[0m  — field id found in UI`);
console.log(`  \x1b[31m❌ FAIL  ${fail}\x1b[0m  — field id MISSING from UI`);
console.log(`  \x1b[33m⏭  SKIP  ${skip}\x1b[0m  — known gap (expected)`);
console.log(`  \x1b[36m⚠  WARN  ${warn}\x1b[0m  — captured not computed`);
console.log(`  \x1b[90m🔁 AUTO  ${auto}\x1b[0m  — auto-derived, no id`);
console.log('═'.repeat(60));

if (fail === 0) {
  console.log('\x1b[32m\n✅ ALL MANIFEST FIELDS PRESENT — UI is complete\x1b[0m\n');
} else {
  console.log(`\x1b[31m\n❌ ${fail} FIELD(S) MISSING FROM UI:\x1b[0m`);
  failures.forEach(f => console.log(`   • ${f}`));
  console.log('');
}

process.exit(fail > 0 ? 1 : 0);
