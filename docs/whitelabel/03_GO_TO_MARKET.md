# Go-to-market: channels, pricing, marketplaces

## 1. Three ways to sell (and what the product must support for each)

| Channel | Buyer | Product requirement | Margin |
|---|---|---|---|
| **Direct SaaS, our brand** | Distributors and suppliers with 5–200 partner sites | Pooled tenancy (Phase 3.1) for Starter; silo for Growth/Enterprise; self-serve trial; demo tenants per vertical | Highest (~80%+) |
| **White-label reseller** | IT firms, ERP consultancies (Zoho, Odoo, Tally, Xero/MYOB partners) who rebrand and sell to their clients | Brand Pack per reseller *and* per end customer, reseller console (3.5), custom domain + email sender, no ConsignGrid name visible anywhere, usage reports for revenue share | Licence + 20–30% revenue share |
| **Marketplaces** | Buyers with committed cloud spend (AWS EDP/MACC) or who browse integration stores | Marketplace integration (3.3), container deployment, security documentation | Marketplace fee 3–20% |

**Rule for white-label:** a reseller's end customer must never see "ConsignGrid": not in page titles, emails,
PDFs, error messages, API docs title, favicon, or `/api/health`. Phase 1.1 makes that a test.

## 2. Pricing (starting points from the strategy, with packaging advice)

| Plan | Price (USD) | Limits | Notes |
|---|---|---|---|
| **Setup** | 500–3,000 one-off | Branding, configuration, data import | Waive for annual Starter; anchor for Enterprise |
| **Starter** | 99–149 / month | 1 warehouse, up to 10 partner sites, 3 staff users, partner logins unlimited | Partners (dealers) should be **free users** — they drive adoption, charging per partner kills it |
| **Growth** | 299–499 / month | 3 warehouses, 50 partner sites, 15 staff users, accounting integration, partner API | Most customers land here |
| **Enterprise** | Custom (from ~1,500 / month) | Multi-country, SSO, dedicated (silo) deployment, region choice, SLA 99.9% | Medical devices sit here |
| **White-label licence** | 5,000–15,000 / year per reseller + 20–30% revenue share | Reseller console, own domain and brand | Minimum commitment of 3 end customers in year 1 |
| **Add-ons** | — | Extra users/sites, lot & expiry module, API access, premium support, custom reports, extra region | Keep gross margin > 70% |

**Value metric:** *partner sites* (dealers/hospitals/stores holding stock) — it scales with the value the customer
gets and is easy to understand. Staff users are the secondary limit.

Regional price points: India and SEA at ~50–60% of USD list (INR pricing, GST invoice), ME at USD list,
ANZ in NZD/AUD at USD list ×1.6.

## 3. Where to list, in order

| When | Listing | Prerequisite |
|---|---|---|
| Month 1 | G2, Capterra / GetApp / Software Advice, SoftwareSuggest (India), Product Hunt (when self-serve trial exists) | Website, screenshots, 3 reviews from pilots |
| Month 2–3 | **AWS Marketplace** — SaaS contract listing; start with private offers for silo customers | Seller registration, SaaS fulfilment integration (ResolveCustomer → customer ID, Entitlement Service for contracts, metering only for usage above entitlement; SNS subscription events), listing review |
| Month 3–4 | **Azure Marketplace** (SaaS offer with Fulfilment API v2), **Google Cloud Marketplace** | Same pattern; landing page + webhook |
| Month 4–6 | **Zoho Marketplace** (Zoho Books/Inventory extension), **Xero App Store**, **QuickBooks App Store**, **Odoo Apps**, **NetSuite SuiteApp** | The corresponding accounting adapter (2.6) |
| Month 6+ | Shopify App Store (only for the FMCG/retail pack with POS feeds), AppSumo lifetime deal (only once pooled tenancy and support capacity exist — LTDs bring support load and low-value users) | Pooled tenancy, plan limits |

## 4. Marketplace and enterprise readiness checklist

- [ ] Container images (backend, frontend), Helm chart or Terraform module for AWS/Azure
- [ ] SaaS fulfilment endpoints (AWS ResolveCustomer/Entitlements/SNS; Azure Fulfilment v2; GCP Procurement)
- [ ] Plan/limit enforcement (sites, users) driven by entitlements
- [ ] Security: pen test report, SOC 2 Type I readiness, vulnerability disclosure policy, data-processing agreement
- [ ] Privacy policy, terms of service, SLA, sub-processor list, data-residency statement per region
- [ ] Support: help centre, status page, onboarding email sequence, in-app feedback (exists as pilot feedback)
- [ ] Brand-neutral API documentation (OpenAPI title from Brand Pack)
- [ ] Demo tenants per vertical with fictional data (sample catalogue generator exists for tyres)

## 5. Legal and commercial pack (before the first sale)

1. **IP and licence confirmation** between Seven Hills Global and the TyreGrow customer: ownership, no exclusivity,
   permission to name them as a reference.
2. **Trademark**: final product name searched and filed (IPONZ, IP Australia, then WIPO Madrid for IN/AE/UK/EU).
3. **White-label reseller agreement**: territory, minimums, revenue share, brand usage, support tiers (L1 reseller,
   L2/L3 us), data-processing responsibilities, termination and data return.
4. **Customer subscription agreement + DPA + SLA**.
5. **Open-source licence review**: all current dependencies are permissive (MIT/BSD/Apache, Inter font under OFL) —
   keep a `THIRD_PARTY_NOTICES` file in the release.
