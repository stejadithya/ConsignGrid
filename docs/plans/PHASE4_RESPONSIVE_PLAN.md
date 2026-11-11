# Phase 4: mobile and touch, responsive plan (for approval, not implemented)

Branch: `feature/mobile-responsive-phase4` (from `main` at `679e586`). Baseline on that `main`: 20 / 20 browser scenarios passed.
Scope: presentation only. No change to business logic, API behaviour, routes, permissions or backend statuses.
UX order on every screen: **attention → action → KPI/context → detail**. Accessibility is never reduced to fit more data.

## 1. What the audit found

The audit measured 47 screen/role combinations on a phone (390 px, touch), tablet portrait (820 px, touch) and tablet landscape
(1180 px, touch). The data came from a disposable database filled by the 20 browser scenarios.

| # | Finding | Evidence |
|---|---|---|
| A | **The whole page scrolls sideways** on Products (851 px on a 390 px phone), Warehouse (1112), stock request detail (1182), Invoices (926), and also on tablets (Warehouse 1384 px at 1180 px wide). | Cause: in a table header with an icon-only last column ("Actions", "Select"), the screen-reader label (`sr-only`, absolutely positioned) is not contained by the table's scroll box, so it lands to the right of the last column and widens the page. **One shared fix in `DataTable`.** |
| B | Transfer detail on a phone is 451 px wide. | The FlowPath route chip is `whitespace-nowrap`, so a long SKU cannot wrap. |
| C | On phones, tables show only their first 2–3 columns; status, quantities and actions are off-screen, with no cue to scroll sideways. | Sales 1962 px of table in a 356 px card (10 columns), Backorders 1488 (12), stock request lists 1300 (10), Movements 1718. |
| D | Controls under 44 px on touch are now almost all **inside tables**: sortable column headers (about 20 px tall), row checkboxes (16 px), ⓘ icons, number links and document links in cells. | 0–29 per screen. Stand-alone buttons and inputs are already 44 px (Phase 2). |
| E | KPI labels wrap on phones by design: each reserves two lines so values line up. | No action needed beyond ordering and count (see rules). |
| F | Muted grey text directly on the off-white page background (4.47:1, just under 4.5:1). | 4 places: Products and Warehouse table footnotes, New transfer step labels. |
| G | No sticky actions anywhere. On New stock request the submit button is 1,316 px down the page on a phone. | 0 sticky bars in the app. |
| H | The notification pop-up covers the page title and the header actions on phones. | Screenshots (phone, all roles). |
| I | Hamburger menu button is about 32 px. | AppShell header. |
| J | Tablet portrait (820 px) uses the phone navigation (hamburger); landscape (1180 px) shows the 256 px sidebar, leaving about 860 px for tables. | Warehouse table needs 1155 px. |

## 2. Responsive rules (proposed)

1. **Breakpoints.** Phone < 640 px. Tablet portrait 640–1023 px (hamburger navigation). Tablet landscape and desktop ≥ 1024 px (sidebar).
2. **The page never scrolls sideways.** Only a table may scroll, inside its card. A scrolling table keeps its first column (the identifier) pinned and shows a fade at the edge, so it is obvious there is more.
3. **Three table modes, chosen per table:**
   - **Cards on phones.** Each row becomes a card. The first line holds the identifier and status badge, then 2–4 key fields as label/value pairs, then the row's main action as a full-width button. Hidden columns stay reachable on the detail page.
   - **Horizontal scroll** (pinned first column), for ledgers, audit trails and dense reports, where every column matters and the screen is mostly used at a desk.
   - **Dense table** on tablet and desktop for operational lists, unchanged except touch hit-areas.
4. **Touch targets.** Stand-alone controls stay at least 44 px. Inside tables, the target is enlarged without enlarging the visual:
   - a sortable header becomes a full 44 px cell;
   - a checkbox's whole cell is its label;
   - an icon button keeps a 32 px look with a 44 px hit area.
   This meets WCAG 2.5.5 without fattening rows. Small row buttons (`sm`) on touch become 36 px visual with a 44 px hit area, replacing today's full 44 px.
5. **Primary action placement.**
   - **Lists:** in the page header (as now).
   - **Forms and workflows on phones:** the one primary action sits in a **sticky bottom bar**, together with Back or Cancel. It respects the iPhone home-indicator safe area. Secondary header actions on phones collapse into a "More" menu.
6. **KPIs on phones.** Two columns, two-line labels reserved (keep). The figure that needs attention goes first. Banners with five figures show all five (no hiding).
7. **Filters and search on phones.**
   - Search is full width.
   - Secondary filters move behind a "Filters (n)" button that opens a bottom sheet.
   - Quick-filter chips become one horizontally scrolling row instead of wrapping onto 2–3 rows of 44 px chips.
8. **Notifications on phones.** The pop-up appears at the bottom (above any sticky bar), one at a time, so it never covers the title or actions.
9. **Contrast.** Muted grey is only used on white surfaces. On the page background, captions use the secondary grey.
10. **Warehouse comfortable density.** No separate mode switch. Warehouse operational tables declare `density="comfortable"`:
    - 52 px rows and 16 px / 600 quantities on touch devices;
    - unchanged 44 px rows with a mouse.
    Applies to Warehouse, Pick & dispatch, Shipments, Receive (Purchasing) and the stock-check count.
11. **Tablet.** Portrait gets dense tables (scroll with pinned first column where needed) and sticky workflow actions like phones. For landscape, an optional icon-only sidebar between 1024 and 1279 px gives about 190 px back to tables (see decision D3).
12. **Header controls.** The hamburger and bell are 44 px on touch.

## 3. Screen-by-screen decisions

Notes for the table below:
- "Phone table" is the phone table mode; tablet and desktop keep the dense table unless stated.
- "Primary action" is where it sits on a phone.
- Touch behaviour follows rule 4 everywhere; navigation follows rule 1 everywhere (hamburger on phone and tablet portrait), so neither is repeated per row.

| Screen | Desktop today | Phone problem | Phone table | Primary action (phone) | KPIs | Filters / search | Warehouse / tablet |
|---|---|---|---|---|---|---|---|
| **Products** | Header with 4 actions; 7-column table | Page 851 px (finding A); 4 header buttons; table cut | Cards: name, size · SKU, warehouse / at dealers / backorder, status, Edit | "Add product" in header; Template / Export / Import in "More" | none | Search + sheet (brand, size, availability, status) | Tablet: table |
| **Warehouse** | 5-figure strip, tabs, chips, 9-column table | Page 1112 px (A); 5 chips wrap to 3 rows; table cut | Cards: tyre, **Available** large, Low/Out badge, reserved · blocked · demand · incoming, actions menu | Header (Receive / Pick & dispatch) | Strip 2 columns; Out of stock and Backordered first when > 0 | Chips in one scroll row; search full width | **Comfortable** on touch; tablet table with pinned tyre column |
| **Consignment** | Strip + 7-column table | Table cut | Cards grouped by dealer → shop: tyre, on hand, available, target | none | Strip 2 columns | Dealer select in sheet | Tablet: table |
| Inventory allocation / movement | Ledger tables (6 columns, 50+ rows) | Table cut (1718 px) | **Scroll**, pinned first column | none | none | As now | Desk use |
| **Stock requests: lists** (pending, approved, shipments, all) | 10-column table | Only Request and Dealer visible | Cards: SRQ no. + status, dealer · shop, units / SKUs, age, next step (button) | Header "Create request" | none | Search + dealer in sheet | Tablet: table |
| **Stock request detail** | Header + 5 actions, timeline, lines table, approve dialog with a raw table | Page 1182 px (A); 5 actions | Lines as cards; approve dialog rows as cards with 44 px qty input and remainder select | **Sticky bar**: the one next action (Approve… / Ship / Confirm delivery); others in "More" | Figures 2 columns | n/a | Tablet: sticky bar too |
| **New stock request** | Long form | Submit is 1,316 px down | n/a (lines as cards) | **Sticky bar**: Submit for approval / Save draft | n/a | Tyre picker full width | — |
| **Replenishment** (list, Pick & dispatch) | Sections with 4-column tables | Tables cut; Dispatch button deep in page | Cards: REP no., dealer, tyre, qty to pick (large), Ready badge | **Sticky bar** on Pick & dispatch: "Dispatch N unit(s)" | none | Section tabs as scroll row | **Comfortable** on touch |
| **Replenishment detail** | Quantity bar, timeline, lines tables | Lines cut | Lines as cards | **Sticky bar**: Approve… / Mark ready / Ship / Confirm | Bar stays | n/a | Comfortable on touch |
| **Backorders** | 12-column table + allocation | Table cut (1488 px) | Cards: tyre, dealer, waiting qty, age, reason, priority badge | **Sticky bar** "Confirm allocations" when proposals exist | none | Chips scroll row | Tablet: table |
| **Transfers: list / detail / new** | 7-column table; detail with route card; 3-step wizard | Detail 451 px (B); table cut | List as cards (TRF no. + status, from → to, tyre, qty) | Detail: **sticky** next action (Approve / Record collection / Confirm). New: sticky "Continue" | none | Chips scroll row | — |
| **Sales** (staff) | Tabs, 10-column table (1962 px) | Table cut | Cards: SAL no. + date, dealer, tyres (2 lines), Invoiced? badge, replacement | Header "Record sale"; the form gets a **sticky** submit | none | "Not invoiced only" as a chip; dealer in sheet | — |
| **My Sales** (dealer) | Period chips, KPIs, by-tyre and sales tables | Chips wrap to 3 rows | By-tyre: compact 2-column table (fits). Sales as cards | Header "Report a sale" | 2 columns | Period chips scroll row; dates in sheet | — |
| **Invoices** | Who-to-invoice (checkbox table), records table | Page 926 px (A); checkboxes 16 px | Who-to-invoice as cards with a whole-card checkbox; records as cards | **Sticky bar**: "Create invoice record (N lines)" while lines are selected | Strip 2 columns | Dealer in sheet | — |
| Invoice record | Document-style summary + table | Table slightly cut (437 px) | **Scroll** (it is a document to print) | Mark as invoiced in Xero: **sticky** | n/a | n/a | — |
| **Stock checks** (new, detail) | Dealer, shop, count table; detail with lines and actions | Detail table cut (837 px) | Count entry as cards with a 44 px numeric input per tyre; detail lines as cards | **Sticky bar**: Submit count; dealer: Ask for a re-check / Raise a dispute / Invoice | Header card stays | Tyre search full width | **Comfortable** on touch (reps count on tablets) |
| **Dealers** (list, detail) | 7-column list; detail tabs with tables | Tables cut | List as cards (name, account ref., rep, status); detail tables as cards | Header "New dealer"; dealer form **sticky** "Create dealer" | Detail strip 2 columns | Search full width | — |
| **Purchasing** | PO and receipts tables, receive form | Tables cut | Cards (PO no. + status, supplier, received / ordered) | Receive form **sticky** "Receive" | none | — | **Comfortable** on touch |
| **Admin** | Tabs; users, audit, feedback tables | Tables cut | Users and feedback as cards; audit log **scroll** | Header "New user" | none | Tabs scroll row | Desk use |
| **Check Stock** | Search panel + results | Fits | Results already compact (keep) | "Search" inline (keep) | Warehouse / dealers figures (keep) | — | — |
| **Role dashboards** (RM, WM, Rep, Dealer, Finance, Admin) | Header, KPI banner, attention / job lists, tables | Fit; inner tables (e.g. rep's 6-column dealer list) cut | Inner tables as cards | Header actions; on phones only the primary stays, the rest go in "More" | Banner 2 columns | — | See decision D1 |

## 4. Shared-component changes

1. **`DataTable`** (`ui.tsx`):
   - make the scroll box `relative` (fixes finding A on every table);
   - new `mobile="cards" | "scroll"`;
   - new per-column `mobile: "title" | "badge" | "field" | "action" | "hidden"` and an optional `mobileLabel`;
   - pinned first column and edge fade in scroll mode;
   - `density="comfortable"`;
   - 44 px sortable headers on touch.
   Cards are the **same DOM restyled with CSS** (no second copy). That keeps one source of truth, no duplicate text for tests and screen readers, and no hydration mismatch; explicit ARIA roles keep table semantics.
2. **`MobileActionBar`** (new, `ui.tsx`): sticky bottom bar on phones and tablet portrait, safe-area padding; renders inline on desktop. Used by forms and workflows.
3. **`PageHeader`**: optional `secondaryActions`, folded into a "More" menu on phones.
4. **`FilterBar` / new `FilterSheet`**: search stays visible; other filters go into a bottom sheet with a count badge.
5. **`QuickFilters` and `Tabs`**: one horizontally scrolling row on phones.
6. **Hit-area helper**: icon and `sm` buttons get a 44 px invisible hit area on touch instead of a 44 px visual.
7. **`NotificationCenter`**: pop-ups at the bottom on phones, one at a time.
8. **`AppShell`**: 44 px hamburger and bell. An optional icon-rail sidebar between 1024 and 1279 px (decision D3).
9. **`FlowPath`**: the route chip wraps (finding B).
10. **Muted-on-canvas**: the 4 page-level captions use the secondary grey.

## 5. Decisions needed

- **D1.** Dashboards on phones: show the attention or job list *above* the KPI banner (follows attention → action → KPI), or keep today's order? Recommendation: move it above, phones only.
- **D2.** Small row buttons on touch: 36 px visual with a 44 px hit area (recommended), or keep today's full 44 px?
- **D3.** Icon-rail sidebar for tablet landscape (1024–1279 px): yes or not now? Recommendation: yes. It is the single biggest win for warehouse tablets.

## 6. Risks

- **Card mode via CSS** must keep tables readable to screen readers: explicit roles plus label text in each cell. Tested with axe and keyboard.
- **Sticky bars** can hide the last form field or a pop-up. Mitigations: bottom padding equal to the bar height, pop-ups placed above the bar, no sticky bar inside dialogs (a dialog's footer is already fixed).
- **Tests.** The 20 browser scenarios run at desktop width, so card mode does not affect them. New phone and tablet smoke tests are needed to prove the result.
- **Scope creep.** About 69 tables need column metadata. Each is mechanical, but it is a broad change; it will be done area by area with screenshots.
- **Print** (pick sheets, invoice summary) must not pick up card styles. Print media keeps the table.
- **Sidebar rail (D3)** touches navigation for every role; it needs a careful check of labels, tooltips and keyboard focus.

## 7. Size

| Area | Files |
|---|---|
| Shared components (`ui.tsx`, `AppShell`, `NotificationCenter`, `flow.tsx`, `globals.css`) | about 5 |
| Screens with tables to tag (37 files, about 69 tables) | about 37 |
| Workflows with a sticky bar (stock request new and detail, replenishment detail and Pick & dispatch, backorders, transfer new and detail, record sale, invoices, stock check new and detail, purchasing receive, new dealer) | about 13, mostly overlapping the 37 |
| New phone and tablet smoke tests | 1–2 |
| **Total** | **about 45–50 files, about 25 screens** |

## 8. Implementation order

1. **4.1 Quick fixes:** the `DataTable` overflow fix, the FlowPath chip, pop-ups at the bottom on phones, 44 px hamburger and bell, muted-on-canvas captions. All page-level sideways scrolling is gone after this step.
2. **4.2 DataTable modes:** cards, scroll with pinned column, comfortable density, touch hit areas, 44 px headers.
3. **4.3 Lists to cards, by area:** stock requests → replenishment → backorders → transfers → sales / My Sales → invoices → dealers → products → warehouse → consignment → purchasing → admin → dashboards. Ledgers and audit stay as scroll.
4. **4.4 Sticky actions:** `MobileActionBar` and the `PageHeader` "More" menu, applied to the workflows above.
5. **4.5 Filters:** `FilterSheet`, single-row chips and tabs.
6. **4.6 Warehouse and tablet:** comfortable density on the warehouse screens; icon rail if D3 is approved.
7. **4.7 Verification:**
   - re-run this audit: zero page overflow at 390 / 820 / 1180 px, and no stand-alone control under 44 px;
   - phone and tablet screenshots;
   - 20 / 20 desktop browser scenarios, plus the new phone and tablet smoke tests;
   - typecheck, lint, unit tests, build.
