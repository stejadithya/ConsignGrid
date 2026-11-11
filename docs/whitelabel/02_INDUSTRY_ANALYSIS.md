# Industry analysis — consignment inventory across verticals

Consignment means the **supplier keeps ownership** of stock held at someone else's site (dealer, hospital, store,
job site) and is paid only when the stock is **sold, used, or found missing**. The same loop appears in every target
industry:

```
Supplier ships stock → partner holds it → sale or use is recorded → invoice and settle → replenish to target
```

What changes per industry is **how an item is identified**, **what has to be tracked per unit**, **what triggers the
invoice** and **who must approve**. These are exactly the parts we make configurable.

## 1. Industry standards the product must meet (common to all verticals)

| Standard practice | Meaning | ConsignGrid today |
|---|---|---|
| **Title stays with supplier until trigger** | Ownership on the supplier's books; the partner holds custodial stock | ✅ ledger locations separate warehouse vs consignment |
| **Signed consignment agreement** per partner | Targets (par levels), consent to transfer, payment terms, liability for loss | ✅ agreement + files + targets; add billing trigger, liability and ageing terms |
| **Par / min-max levels and auto-replenishment** | Keep the agreed quantity on the shelf | ✅ targets + auto-replenish |
| **Periodic physical counts / cycle counts** with variance resolution | Reconcile what the partner should hold vs what is there | ✅ stock checks with find window, recount and dispute |
| **Proof of delivery** | Signed or photographed receipt | ✅ receipt proof photos, delivery notes |
| **Ageing and slow-mover review** | Rotate or recall stock that hasn't moved in N days | ⚠ reports exist; add ageing buckets and rotation suggestions |
| **Full audit trail** | Who moved what, when, why | ✅ audit + ledger |
| **Sell-through / usage reporting** to the partner and supplier | Monthly statements | ⚠ add periodic statements (Phase 2.2) |
| **Integration with accounting / ERP** | Invoice in the finance system | ⚠ manual export + Xero numbers; add live adapters |
| **Barcode scanning** (GS1 GTIN, GS1-128, DataMatrix) | Fast, error-free counts and receipts | ⚠ barcode field exists; add scanning and GS1 parsing |
| **Accounting treatment** (IFRS 15 / ASC 606: revenue at transfer of control) | The trigger date is the revenue date | ✅ sale/usage date on invoice lines |
| **Tax treatment of cross-border consignment** (e.g. EU call-off stock, Article 17a VAT Directive; consignment for unknown customers requires registration in the destination state) | Determines whether a movement is a taxable supply | ⚠ document in tax profiles; flag cross-border transfers |

## 2. Vertical-by-vertical requirements

Priority: **★★★** = target in the first 6 months, **★★** = next, **★** = opportunistic.

### Tyres and wheels ★★★ (reference customer)
- **Identify:** brand, pattern, width/aspect/rim, construction, load index, speed rating, XL/RF/winter/AT flags; EAN.
- **Track:** DOT date code (week/year) — tyres older than ~5–6 years are hard to sell; FIFO by DOT week.
- **Rules:** tyre stewardship / EPR fees (e.g. NZ Tyrewise, AU Tyre Stewardship) shown separately from price;
  transfers between dealers to chase sizes; size search ("205/55R16").
- **Gaps:** DOT-week ageing, stewardship fee line, wheel fitments (PCD/offset) for a wheels pack.

### Auto parts and batteries ★★★
- **Identify:** part number, OEM cross-references and supersessions, make/model/year fitment, brand.
- **Track:** batteries — manufacture date (freshness, recharge cycle), serial for warranty; **core charges /
  deposits** for exchange units (batteries, alternators, starters).
- **Rules:** consignment to workshops and garages; returns of slow movers ("stock rotation"); warranty claims by serial.
- **Gaps:** cross-reference search, core-charge line on sale, battery age alert, serial capture.

### Medical devices and implants ★★★ (highest value per item, strongest need)
- **Identify:** GTIN / **UDI-DI**, manufacturer REF (catalogue number), size; kits and trays.
- **Track:** **lot or serial + expiry on every unit** (from the UDI-PI on the label — GUDID/EUDAMED store only the
  DI, so lot and expiry must be captured at receipt or scan); sterile status.
- **Rules:** hospital **bill-only** and **bill & replace** (invoice raised *after* use, with a hospital PO), usage
  record with **case/procedure reference, surgeon, date, (optionally) patient reference**; FEFO picking; expiry alerts
  60/30/7 days; **recall lookup** by lot/serial; trunk stock (rep's car) as a location; loaner sets.
- **Compliance:** FDA UDI (21 CFR 830), EU MDR UDI/EUDAMED, TGA, ISO 13485 supplier expectations; HIPAA/Privacy Act
  if patient references are stored (keep optional, prefer case numbers).
- **Gaps:** lot/serial/expiry (Phase 2.1), usage-based billing (2.2), GS1 DataMatrix parsing (Phase 4), rep trunk
  locations (exists as a location type in effect).

### Industrial spares, tools and MRO ★★★
- **Identify:** part number, manufacturer, specification attributes (thread, length, material, grade).
- **Track:** serial for tools; calibration due date for gauges; bin/shelf location at the customer site.
- **Rules:** **VMI vending / storeroom consignment** at factories and mines; usage by **cost centre / work order**;
  monthly consumption statement; min/max per bin.
- **Gaps:** bin-level sub-locations, cost-centre field on usage, periodic statements.

### Agricultural inputs and parts ★★
- **Identify:** product, pack size, active ingredient / registration number (agrochemicals), seed variety.
- **Track:** batch + expiry; hazardous class (storage rules); seasonal stock.
- **Rules:** end-of-season **returns** (seed and chemical buy-back); consignment to rural merchants; litres/kg UoM.
- **Gaps:** batch/expiry, units of measure, season-end return workflow.

### Retail and FMCG vendor stock ★★
- **Identify:** GTIN/EAN, variant (size, colour), case pack.
- **Track:** sell-through by store; date codes for food.
- **Rules:** **scan-based trading** (supplier is paid when the item scans at the till), POS feed import, shrink
  allocation per agreement, markdown/returns.
- **Gaps:** POS/CSV sales feed import, case↔each UoM, shrink rules.

### Building materials and tiles ★★
- **Identify:** product, size, finish.
- **Track:** **shade / batch and calibre** — tiles from different batches don't match, so a job must be supplied from
  one batch; boxes ↔ m² conversion.
- **Rules:** consignment to showrooms and builders; job/project reference on usage; breakage allowance.
- **Gaps:** batch tracking with "same batch" allocation, units of measure, project reference.

### Furniture showrooms ★
- **Identify:** model, variant (fabric, finish, configuration).
- **Track:** serial per piece; display vs sellable condition; floor samples.
- **Rules:** showroom floor stock on consignment, sale reported by showroom, delivery direct to the end customer.
- **Gaps:** condition grades (exists partly as "blocked"), variant attributes (Phase 1.4).

## 3. Capability matrix → roadmap

| Capability | Tyres | Auto | Medical | MRO | Agri | FMCG | Tiles | Furniture | Phase |
|---|---|---|---|---|---|---|---|---|---|
| Configurable attributes and labels | ● | ● | ● | ● | ● | ● | ● | ● | 1.4 |
| Vocabulary (dealer/hospital/site…) | ● | ● | ● | ● | ● | ● | ● | ● | 1.2 |
| Lot / batch | ○ | ○ | ● | ○ | ● | ○ | ● | | 2.1 |
| Serial | | ● | ● | ● | | | | ● | 2.1 |
| Expiry / age + FEFO | ○ (DOT) | ● (batteries) | ● | ○ | ● | ● | | | 2.1 |
| Bill on use + reference | | ○ | ● | ● | | | ● | | 2.2 |
| Periodic statement | | ○ | ○ | ● | ● | ● | | | 2.2 |
| Units of measure | | | | ○ | ● | ● | ● | | 4 |
| Core charge / deposits | | ● | | | | | | | 4 |
| POS / sales feed import | | | | | | ● | | ○ | 4 |
| GS1 / UDI scanning | ○ | ○ | ● | ○ | ○ | ● | | | 4 |

● required to sell · ○ nice to have

## 4. Competitive landscape (summary)

- **Horizontal inventory / ERP** (Zoho Inventory, NetSuite, Acumatica, Odoo, Megaventory, Finale, Acctivate): handle
  consignment as a location flag. They lack replenish-to-target from sales, dealer self-service, transfer
  obligations and stock-check find windows. They are *integration partners* more than competitors.
- **Resale consignment POS** (SimpleConsign, Liberty, ConsignPro): consumer resale shops with consignor payouts —
  different market (B2C goods owned by individuals).
- **Medical device field inventory** (Movemedical, GHX, Tecsys, Syft/Omnicell): deep but expensive and US-centric;
  ANZ/India/ME mid-size distributors are underserved. This is our best value-per-customer niche.
- **Positioning:** *"The consignment layer your ERP doesn't have"* — supplier-side, partner-facing, with a ledger
  your auditor trusts, white-labelled under your own brand, live in days.

Sources consulted: AWS Marketplace seller documentation, Avalara VATLive and Vertex on EU call-off stock, CASRAI and
Movemedical material on medical device consignment and UDI, GetApp / The Retail Exec directories for competitor
positioning. Vendor claims are marketing material and need checking in demos.
