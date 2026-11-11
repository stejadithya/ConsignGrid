"""Content of the TyreGrow UAT journey maps (plain language for business testers).

Each journey has lanes (who takes part) and numbered steps. Step fields:
  lane   which lane the step sits in on the diagram
  who    roles that may do the step (used for the role editions); "ALL" = every role
  short  label inside the diagram box (keep it short)
  do     what to do, with where to click (bold = menu, button or field name)
  see    what you should see when it works
Markup: <b>…</b> for screen words; write & as &amp; in do/see (not in short).
"""

ROLES = {
    "ADM": {"name": "Administrator", "short": "Admin", "color": "#52525b"},
    "RM": {"name": "Relationship Manager", "short": "RM", "color": "#1d5fbf"},
    "WM": {"name": "Warehouse Manager", "short": "WM", "color": "#b45309"},
    "FM": {"name": "Finance Manager", "short": "FM", "color": "#0f766e"},
    "SR": {"name": "Sales Representative", "short": "Sales Rep", "color": "#15803d"},
    "DLR": {"name": "Dealer", "short": "Dealer", "color": "#7c3aed"},
}
ROLE_ORDER = ["ADM", "RM", "WM", "FM", "SR", "DLR"]

# Lane definitions: key -> (label, colour, roles it stands for)
LANES = {
    "ALL": ("Any user", "#18181b", ["ADM", "RM", "WM", "FM", "SR", "DLR"]),
    "ADM": ("Administrator", ROLES["ADM"]["color"], ["ADM"]),
    "USERS": ("Administrator or Relationship Manager", ROLES["ADM"]["color"], ["ADM", "RM"]),
    "RM": ("Relationship Manager", ROLES["RM"]["color"], ["RM"]),
    "WM": ("Warehouse Manager", ROLES["WM"]["color"], ["WM"]),
    "CT": ("Central Team (RM or WM)", ROLES["RM"]["color"], ["RM", "WM"]),
    "CAT": ("RM or WM", ROLES["RM"]["color"], ["RM", "WM"]),
    "BILL": ("Relationship or Finance Manager", ROLES["FM"]["color"], ["RM", "FM"]),
    "SR": ("Sales Representative", ROLES["SR"]["color"], ["SR"]),
    "DLR": ("Dealer", ROLES["DLR"]["color"], ["DLR"]),
    "DSR": ("Dealer or Sales Rep", ROLES["DLR"]["color"], ["DLR", "SR"]),
    "FIELD": ("WM, RM or Sales Rep", ROLES["WM"]["color"], ["WM", "RM", "SR"]),
    "STAFF": ("Staff (Admin, RM, WM, Sales Rep)", ROLES["RM"]["color"], ["ADM", "RM", "WM", "SR"]),
    "SYS": ("App (automatic)", "#8a8a93", []),
}

ROLE_CARDS = {
    "ADM": {
        "summary": "The super user. Can do everything in the app.",
        "does": ["Creates user logins and sets roles", "Manages warehouses and tax rates",
                 "Sees the change history (audit log) and tester feedback", "Can step in for any other role"],
        "cannot": ["Nothing is blocked; use it carefully during testing"],
    },
    "RM": {
        "summary": "Heads TyreGrow: dealers, orders, invoices, and everything the warehouse does.",
        "does": ["Adds dealers with their shops and login; existing dealers with their stock (Excel)",
                 "Approves stock and replenishment requests, including those sent by the warehouse",
                 "Can also buy, receive, pick and ship like the Warehouse Manager",
                 "Arranges and approves transfers between dealers",
                 "Creates invoice records and marks them invoiced in Xero; sees Xero numbers",
                 "Manages user logins, hand-overs, change history and tester feedback", "Reads reports"],
        "cannot": ["See or set prices in TyreGrow (prices are in Xero)"],
    },
    "WM": {
        "summary": "Runs the warehouse: supplier stock in, dealer stock out.",
        "does": ["Orders from suppliers and receives tyres", "Approves, packs and ships dealer requests and replenishments",
                 "Sends an approval to a Relationship Manager when needed", "Finds tyres from other dealers (transfers)",
                 "Adds, edits, exports and imports tyres; records non-consignment sales"],
        "cannot": ["Create invoice records or see Xero numbers (sees Invoiced ✓ / Not yet)",
                   "Change dealer accounts or agreed levels", "Manage user logins (the Relationship Manager does)"],
    },
    "FM": {
        "summary": "Billing: makes sure every tyre sold is invoiced in Xero.",
        "does": ["Sees what is sold and not yet invoiced, by dealer", "Creates invoice records",
                 "Marks them invoiced in Xero with the Xero number, and corrects it if needed",
                 "Reads sales, dealers and reports"],
        "cannot": ["Do anything with stock: no ordering, picking, shipping or stock checks",
                   "Change dealers or user logins"],
    },
    "SR": {
        "summary": "In the field with the dealers.",
        "does": ["Counts stock at dealers (stock checks) and starts re-counts",
                 "Records sales and stock or replenishment requests for a dealer",
                 "Carries deliveries and transfers to dealers and confirms the hand-over",
                 "Sees invoiced ✓ / not yet on sales (no invoice or Xero numbers)"],
        "cannot": ["Approve requests or transfers", "Ship from the warehouse", "Create invoices"],
    },
    "DLR": {
        "summary": "Sells TyreGrow tyres held on consignment at their shop.",
        "does": ["Reports every tyre sold", "Requests stock, incl. \"Get this tyre for me\"",
                 "Confirms deliveries when tyres arrive",
                 "After a stock check: asks for a re-check, raises a dispute, or has tyres not found invoiced",
                 "Sees own stock, sales, requests and invoice records (not Xero numbers)"],
        "cannot": ["See other dealers or warehouse stock figures", "See prices (they are on the Xero invoice)",
                   "Approve anything"],
    },
}

JOURNEYS = [
    {
        "title": "Signing in and finding your way",
        "purpose": "Every tester starts here: first sign-in, your own password, your menu and notifications.",
        "starts": "You receive your login email and a temporary password.",
        "ends": "You are signed in, see your own dashboard, get pop-up notifications and can sign out safely.",
        "lanes": ["ALL", "SYS"],
        "steps": [
            dict(lane="ALL", who=["ALL"], short="Sign in with temporary password",
                 do="Open the TyreGrow web address. Enter your <b>Email</b> and temporary <b>Password</b>, click <b>Sign in</b>.",
                 see="The screen <b>Choose your own password</b> appears."),
            dict(lane="ALL", who=["ALL"], short="Choose your own password",
                 do="Enter the temporary password, then your new password twice (at least 10 characters). <b>Show password</b> lets you "
                    "check what you typed. Click <b>Save new password</b>.",
                 see="You are taken into the app."),
            dict(lane="SYS", who=["ALL"], short="Your dashboard and menu appear",
                 do="Look at the menu on the left and the dashboard.",
                 see="Only the menu items for your role (see the <b>Who's who</b> page). Dealers see <b>My Dashboard</b>; "
                     "the Finance Manager sees the billing dashboard."),
            dict(lane="SYS", who=["ALL"], short="New notification pops up",
                 do="Leave TyreGrow open while someone does something for you (e.g. a dealer submits a request).",
                 see="Within about 20 seconds a pop-up appears top right with a short sound; the browser tab shows the unread count, "
                     "e.g. <b>(1) TyreGrow</b>. <b>Open</b> goes to it."),
            dict(lane="ALL", who=["ALL"], short="Bell, sound and desktop alerts",
                 do="Click the bell at the top right. Then your name → <b>Notification sound: on</b> to switch the sound off (and on again).",
                 see="Your notifications; clicking one opens the order, delivery or check. The sound setting is remembered."),
            dict(lane="ALL", who=["ALL"], short="Change password again",
                 do="Click your name (top right) → <b>Change password</b>.",
                 see="A roomy dialog <b>Change your password</b>. Saved: \"Password changed\"; next sign-in uses the new password."),
            dict(lane="ALL", who=["ALL"], short="Send tester feedback",
                 do="Your name → <b>Pilot feedback</b>, write a comment, click <b>Send feedback</b>.",
                 see="A thank-you message."),
            dict(lane="ALL", who=["ALL"], short="Sign out",
                 do="Your name → <b>Sign out</b>.",
                 see="Back on the sign-in page. The browser Back button does not show your data."),
        ],
    },
    {
        "title": "Adding a dealer and giving them a login",
        "purpose": "Bring a new dealer on board, or an existing dealer together with the stock they already hold.",
        "starts": "A dealer agrees to sell TyreGrow tyres on consignment.",
        "ends": "The dealer signs in and sees only their own shops and stock.",
        "lanes": ["RM", "USERS", "DLR"],
        "steps": [
            dict(lane="RM", who=["RM", "ADM"], short="Dealers > New dealer",
                 do="<b>Dealers</b> → <b>New dealer</b>. Choose <b>New dealer</b> or <b>Existing TyreGrow dealer</b>.",
                 see="The New dealer form opens. The (i) icons explain each field."),
            dict(lane="RM", who=["RM", "ADM"], short="Fill in details and shops",
                 do="Fill in <b>Business name</b>, <b>Contact name</b>, <b>Email</b>, <b>Phone</b>, <b>Billing address</b> and "
                    "<b>Sales representative</b> (all required). Under <b>Shops</b>, add each shop with its delivery address and city "
                    "(<b>Add another shop</b>).",
                 see="The <b>Account reference</b> is made for you (e.g. AKT-AUC-001) and cannot be typed; each shop gets a code "
                     "(…-01, …-02)."),
            dict(lane="RM", who=["RM", "ADM"], short="Optional: stock, agreement copy",
                 do="Existing dealer: add their stock under <b>Initial stock (backorder)</b>, by <b>Enter tyres</b> or <b>Upload Excel</b> "
                    "(SKU Code, Quantity, Shop code). Attach the <b>Copy of the signed agreement</b> (PDF or photo, up to 5 MB).",
                 see="The tyres and the file are listed on the form."),
            dict(lane="USERS", who=["RM", "ADM"], short="Create dealer with its login",
                 do="Leave <b>Create a login for this dealer</b> ticked → <b>Create dealer</b> (or <b>Create dealer and add stock</b>).",
                 see="<b>Dealer login created</b>: email and temporary password, shown once, with <b>Copy</b>. The dealer page opens; "
                     "existing stock shows as <b>Initial stock (backorder)</b>."),
            dict(lane="USERS", who=["RM", "ADM"], short="Share login privately",
                 do="Give the dealer their email and temporary password (phone or in person, not in a group chat). It is never emailed.",
                 see="The dealer has what they need to sign in."),
            dict(lane="RM", who=["RM", "ADM"], short="Later: Add shop, missing details",
                 do="On the dealer page: <b>Add shop</b> for a new shop; older dealers show <b>Missing details</b> until completed.",
                 see="The new shop gets the next code."),
            dict(lane="DLR", who=["DLR"], short="Dealer signs in (Journey 1)",
                 do="Sign in with the temporary password and choose a new one, as in Journey 1.",
                 see="<b>My Dashboard</b> with the dealer's own name."),
            dict(lane="DLR", who=["DLR"], short="Dealer sees own stock only",
                 do="Open <b>Consignment Stock</b> and <b>My account</b>.",
                 see="Their shops and initial stock (if any). No other dealer's information and no prices anywhere."),
        ],
    },
    {
        "title": "Tyres (SKUs)",
        "purpose": "Make a tyre available to order and sell. Prices are set in Xero, not in TyreGrow.",
        "starts": "A new tyre needs to be sold, or tyre details change.",
        "ends": "The tyre can be picked in requests and sales, shown by model and size with its SKU.",
        "lanes": ["CAT", "DLR"],
        "steps": [
            dict(lane="CAT", who=["RM", "WM", "ADM"], short="Products > Add product",
                 do="<b>Products</b> → <b>Add product</b>. Fill in brand, pattern, size, load and speed rating. Save.",
                 see="The tyre appears in Products with its model and size. No price is asked for."),
            dict(lane="CAT", who=["RM", "WM", "ADM"], short="Export all SKUs to Excel",
                 do="<b>Products</b> → <b>Export all SKUs (Excel)</b>.",
                 see="An Excel file in the import layout with every tyre, and no price columns."),
            dict(lane="CAT", who=["RM", "WM", "ADM"], short="Edit the file, import it again",
                 do="Change or add rows in that file, then <b>Products</b> → <b>Import from Excel</b>, check the preview, confirm.",
                 see="<b>Import complete</b>: only the rows you changed are updated; importing the untouched file changes nothing."),
            dict(lane="CAT", who=["RM", "WM", "ADM"], short="Edit one tyre",
                 do="<b>Products</b> → open a tyre → <b>Edit</b>, change and save.",
                 see="The change is saved and shown."),
            dict(lane="DLR", who=["DLR"], short="Dealer can find the tyre",
                 do="<b>Request Stock</b> → search by SKU, brand or size.",
                 see="The tyre is found, shown with its model and size. No prices are shown anywhere."),
        ],
    },
    {
        "title": "Supplier order and receiving tyres",
        "purpose": "Get tyres from the supplier into the main warehouse.",
        "starts": "The warehouse needs more tyres from a supplier.",
        "ends": "The tyres are in warehouse stock, and waiting backorders are offered the new stock.",
        "lanes": ["WM", "SYS"],
        "steps": [
            dict(lane="WM", who=["WM", "ADM"], short="Create a purchase order",
                 do="<b>Purchasing &amp; Shipments</b> → <b>New purchase order</b>: supplier, tyres, quantities. <b>Create PO</b>.",
                 see="The order is listed under <b>Open purchase orders</b>."),
            dict(lane="WM", who=["WM", "ADM"], short="Goods arrive: Receive > Post receipt",
                 do="When the delivery arrives, click <b>Receive</b> on the order, enter what actually arrived, "
                    "<b>Post receipt</b>. (No order? Use <b>Receive without PO</b>.)",
                 see="The receipt is recorded; the order shows what is still outstanding."),
            dict(lane="SYS", who=["WM", "ADM"], short="Warehouse stock goes up",
                 do="Open <b>Warehouse</b>.",
                 see="On hand and Available have gone up by the received quantities."),
            dict(lane="WM", who=["WM", "ADM"], short="Check where it came from (i)",
                 do="On <b>Warehouse</b>, hover over (or tap) the <b>(i)</b> icon next to the tyre.",
                 see="\"Received from the supplier (GRN-…)\" with the date."),
            dict(lane="WM", who=["WM", "ADM"], short="Give stock to waiting backorders",
                 do="<b>Backorders</b> → check the proposed allocation → <b>Confirm allocations</b>.",
                 see="\"Reserved stock for N request(s)…\". Ship them as in Journey 7, step 3."),
        ],
    },
    {
        "title": "Dealer orders stock: request to delivery",
        "purpose": "The main ordering journey, from a dealer's request to tyres on their shelf.",
        "starts": "A dealer (or a Sales Rep for them) needs tyres.",
        "ends": "The dealer confirms the tyres arrived; the request shows Delivered; a delivery note is available.",
        "lanes": ["DSR", "SYS", "CT", "RM", "WM"],
        "steps": [
            dict(lane="DSR", who=["DLR", "SR", "RM", "WM", "ADM"], short="Create and submit a stock request",
                 do="Dealer: <b>Request Stock</b> (staff: <b>Create Request</b> and choose the dealer location). One line per "
                    "tyre with quantity, priority, required-by date. <b>Submit for approval</b> (or <b>Save draft</b>).",
                 see="Request <b>SRQ-…</b> with status <b>Submitted</b>."),
            dict(lane="SYS", who=["RM", "WM", "ADM"], short="Central Team notified (pop-up)",
                 do="RM / WM: keep TyreGrow open.",
                 see="A pop-up \"SRQ-… is waiting for approval\" with a sound; also in the bell."),
            dict(lane="CT", who=["RM", "WM", "ADM"], short="Review: stock for this request, pick sheet",
                 do="<b>Pending Approval</b> → open the request → <b>Start review</b>. Look at <b>Stock for this request</b>. "
                    "<b>Print pick sheet</b>.",
                 see="Only the tyres on this request: warehouse yes/no and how many, how many this dealer already holds, other dealers. "
                     "The pick sheet shows tyres, quantities and the shop address, no prices."),
            dict(lane="WM", who=["WM", "ADM"], short="Optional: Send to Relationship Manager",
                 do="<b>Send to Relationship Manager</b> → choose the RM, add a <b>Note for the approver</b> → <b>Send for approval</b>.",
                 see="\"Waiting for (RM) to approve\". Only that RM can now approve or reject; the RM gets \"Your approval is needed\"."),
            dict(lane="CT", who=["RM", "WM", "ADM"], short="Approve… with approval details",
                 do="<b>Approve…</b>: approve what the warehouse has (the dialog shows what the dealer already holds), choose "
                    "<b>Backorder</b> or <b>Reject</b> for the rest → <b>Approve and reserve</b>. Then <b>Approval details</b>: how "
                    "(phone, in person, email, text, standard), who you spoke to, comments → <b>Confirm approval</b>.",
                 see="Approved tyres are reserved; the <b>Approval</b> card shows who, how and why (staff only). An RM can instead "
                     "<b>Hand back to warehouse</b>."),
            dict(lane="DSR", who=["DLR", "SR"], short="Anything not supplied: kind message",
                 do="Dealer: open the request (or the <b>Messages from TyreGrow</b> card). Optional: <b>Please call me</b>.",
                 see="\"Sorry, we couldn't deliver your order this time, but we're working on it…\" and \"Not available right now\"; "
                     "never the internal reason. A call-back request reaches the RM and the rep."),
            dict(lane="WM", who=["WM", "RM", "ADM"], short="Pick, pack: Mark ready for shipment",
                 do="<b>Approved Requests</b> → open the request → <b>Mark ready for shipment</b>.",
                 see="Status <b>Ready for shipment</b>."),
            dict(lane="WM", who=["WM", "RM", "ADM"], short="Ship by courier or Sales Rep",
                 do="<b>Ship</b> → choose <b>Courier</b> (carrier, tracking) or <b>Sales representative</b> (pick the rep). Confirm.",
                 see="Status <b>Shipped</b>. A chosen Sales Rep gets \"Please deliver DEL-…\"."),
            dict(lane="DSR", who=["DLR", "SR"], short="Confirm delivery on arrival",
                 do="Open the request → <b>Confirm delivery</b> → quantities received and delivery date. A Sales Rep also fills in "
                    "<b>Received by</b> (name) and <b>Hand-over notes</b>. Optional: <b>Take photo</b>. Confirm.",
                 see="Status <b>Delivered</b>; the tyres are in the dealer's <b>Consignment Stock</b>. If shipped with a Sales Rep, "
                     "WM / RM see \"To be confirmed by the dealer or (rep)\" instead of the button."),
            dict(lane="SYS", who=["DLR", "RM", "WM", "ADM"], short="Delivery note (PDF / email)",
                 do="Click <b>Delivery note (PDF)</b> on the shipment.",
                 see="A delivery note listing the tyres and quantities (no prices), with the 14-day discrepancy notice. Emailed if "
                     "email is set up."),
        ],
    },
    {
        "title": "\"Get this tyre for me\": a tyre from another dealer",
        "purpose": "When the warehouse cannot supply a tyre, the warehouse finds it at another dealer and a rep carries it.",
        "starts": "A dealer orders a tyre the warehouse cannot fully supply.",
        "ends": "The tyre arrives at the dealer from another dealer; the giving dealer is owed a replacement.",
        "lanes": ["DLR", "SYS", "CT", "SR"],
        "steps": [
            dict(lane="DLR", who=["DLR", "SR"], short="Order a tyre the warehouse lacks",
                 do="<b>Request Stock</b> → choose the tyre and quantity.",
                 see="A soft yellow note: <b>Leave this one with us</b>. It never says \"out of stock\"."),
            dict(lane="DLR", who=["DLR", "SR"], short="Click Get this tyre for me, submit",
                 do="Click <b>Get this tyre for me</b>, then <b>Submit for approval</b>.",
                 see="\"Thank you! Our team is on it.\" The request page shows the same warm note."),
            dict(lane="SYS", who=["RM", "WM", "ADM"], short="Warehouse asked to find it",
                 do="WM / RM: check the pop-up, the bell and <b>Stock Transfers</b>.",
                 see="\"Please find (tyre) for (dealer)\" and a transfer request TRF-…. Any rest of the order goes to normal approval (Journey 5)."),
            dict(lane="CT", who=["WM", "RM", "ADM"], short="Approve, choose source, arrange pick-up",
                 do="Open the transfer → <b>Approve &amp; choose source</b>: pick the dealer that holds it, enter the consent reference if asked. "
                    "Under <b>How will it travel?</b> tick <b>Arrange the pick-up now</b> and choose the <b>Sales representative</b> "
                    "(or a courier) → <b>Approve &amp; reserve</b>. Nobody has it? <b>Reject</b> with a reason.",
                 see="Status <b>Approved</b> and a <b>Pick-up arranged</b> step. The rep gets \"Please collect TRF-…\" with both dealers' addresses. "
                     "WM sees \"To be collected by (rep)\". (Can also be done later: <b>Arrange pick-up &amp; delivery</b>.)"),
            dict(lane="SR", who=["SR", "ADM"], short="Rep records the collection",
                 do="Rep: dashboard <b>Hand-overs</b> shows it <b>to collect</b>. Open it → <b>Record collection</b> → <b>Collected from</b> "
                    "(who handed it over), optional photo.",
                 see="Status <b>In transit</b>; \"Handed over by …\". The receiving dealer gets \"Tyres are on their way to you\"; the giving dealer "
                     "gets \"Collected; your replacement has been raised (REP-…)\" and is <b>never invoiced</b> for a transfer."),
            dict(lane="DLR", who=["SR", "DLR"], short="Confirm delivery on arrival",
                 do="Rep: <b>Confirm delivery</b> with <b>Received by</b> and <b>Hand-over notes</b> (or the receiving dealer: <b>Confirm receipt</b>). "
                    "Only the rep or the receiving dealer can confirm.",
                 see="Status <b>Completed</b>; the tyre is in the dealer's <b>Consignment Stock</b>; <b>Delivery note (PDF)</b> appears "
                     "(no prices, the other dealer is not named)."),
            dict(lane="DLR", who=["DLR"], short="Check (i): moved in from another dealer",
                 do="<b>Consignment Stock</b> → the <b>(i)</b> icon next to the tyre.",
                 see="\"Moved in from another dealer (TRF-…)\". The other dealer's name is not shown."),
        ],
        "note": "Staff can also start a transfer themselves: <b>Stock Transfers</b> → <b>New transfer</b> (who needs what → check availability → choose source).",
    },
    {
        "title": "Reporting a sale and getting a replacement",
        "purpose": "Every tyre sold is reported, replaced automatically and later invoiced; the sale shows both tracks.",
        "starts": "The dealer sells tyres to a customer.",
        "ends": "Replacement tyres are delivered; the sale waits for invoicing (Journey 8).",
        "lanes": ["DSR", "SYS", "WM"],
        "steps": [
            dict(lane="DSR", who=["DLR", "SR", "RM", "ADM"], short="Report the sale",
                 do="Dealer: <b>Report Sale</b> → <b>Report a sale</b>: date, tyre(s), quantity → <b>Report sale</b>. "
                    "Staff: <b>Sales &amp; Stocktakes</b> → <b>Record sale</b> and choose the dealer.",
                 see="Dealer: \"Thanks, your replacement tyres are being arranged (REP-…). TyreGrow will invoice you through Xero.\" "
                     "The dealer's stock goes down."),
            dict(lane="SYS", who=["WM", "RM", "SR", "ADM"], short="Replacement raised automatically",
                 do="WM / RM / Sales Rep: check the pop-up and <b>Replenishment</b>.",
                 see="A replacement request for the same quantity, reason <b>Sale</b>, shown as <b>Approved automatically</b> "
                     "(replacement for SAL-…) when stock was reserved; otherwise on <b>Backorders</b>."),
            dict(lane="WM", who=["WM", "RM", "ADM"], short="Ready and ship from the request",
                 do="Open the replenishment request → <b>Print pick sheet</b> → <b>Mark ready for shipment</b> → <b>Ship</b> "
                    "(courier or sales rep). (Or in bulk: <b>Warehouse</b> → <b>Pick &amp; dispatch</b>, which shows <b>Ready</b>.)",
                 see="A delivery <b>DEL-…</b> <b>In transit</b>; the request timeline shows Raised → Approved → Ready → Shipped."),
            dict(lane="DSR", who=["DLR", "SR"], short="Confirm delivery",
                 do="On the request (or <b>Deliveries</b>): <b>Confirm delivery</b> (quantities). Sales Rep carrying it: plus <b>Received by</b>, "
                    "<b>Hand-over notes</b> and optional <b>Take photo</b>.",
                 see="The request shows <b>Delivered</b>; stock is back up; the delivery note is available."),
            dict(lane="DSR", who=["DLR", "SR", "RM", "WM", "FM", "ADM"], short="Open the sale: two tracks",
                 do="<b>Sales</b> (dealer: <b>My Sales</b>) → open the sale.",
                 see="<b>Stock</b>: Sale recorded → Replacement raised → shipped → delivered. <b>Billing</b>: Sold, not invoiced → "
                     "Invoice record created → Invoiced in Xero (WM and reps see only <b>Invoiced ✓</b> / <b>Not yet invoiced</b>). "
                     "A <b>Next step</b> line says what you should do."),
            dict(lane="DSR", who=["DLR"], short="Check My Sales and (i)",
                 do="<b>My Sales</b> → choose a period. Then the <b>(i)</b> icon on the tyre in <b>Consignment Stock</b>.",
                 see="The sale counted in tyres sold; the (i) icon says \"Replacement for your sale SAL-…\". No prices."),
        ],
        "note": "A wrong sale can be reversed before it is invoiced: <b>Sales &amp; Stocktakes</b> → open the sale → <b>Reverse</b> (RM, with a reason).",
    },
    {
        "title": "Invoicing sold tyres and non-consignment sales",
        "purpose": "Every tyre sold is invoiced in Xero, and TyreGrow records the Xero number.",
        "starts": "Confirmed sales are waiting to be invoiced, or a customer buys at the warehouse.",
        "ends": "The invoice record is marked invoiced in Xero; each role sees what it should.",
        "lanes": ["BILL", "CAT", "WM", "DLR"],
        "steps": [
            dict(lane="BILL", who=["RM", "FM", "ADM"], short="Who to invoice > Select lines",
                 do="<b>Invoices</b> → <b>Who to invoice</b> (tyres sold, in units, per dealer) → <b>Select N lines</b> for one dealer.",
                 see="That dealer's sold, not-yet-invoiced tyres are selected."),
            dict(lane="BILL", who=["RM", "FM", "ADM"], short="Create the invoice record",
                 do="Click <b>Create invoice record (N lines)</b>.",
                 see="The <b>Invoice summary for Xero</b>: dealer, account ref., and SKU, tyre, quantity, sale no., sale date and shop. "
                     "Status <b>Draft</b>. <b>Print</b> it if useful."),
            dict(lane="BILL", who=["RM", "FM", "ADM"], short="Create it in Xero, mark as invoiced",
                 do="Create the invoice in Xero. Back in TyreGrow: <b>Mark as invoiced in Xero</b> → <b>Xero invoice number</b> "
                    "(required) → <b>Mark as invoiced</b>.",
                 see="Status <b>Invoiced in Xero</b> with the Xero number, who recorded it and when. <b>Correct Xero number</b> fixes a typo "
                     "(the change is recorded)."),
            dict(lane="BILL", who=["RM", "FM", "ADM"], short="Sales list: Invoiced? and Xero no.",
                 do="<b>Sales</b> → tick <b>Not invoiced only</b>; then untick it.",
                 see="Columns <b>Invoiced?</b> (Yes / Draft / Not yet), <b>Xero no.</b> and <b>Replacement</b>."),
            dict(lane="WM", who=["WM", "SR"], short="Warehouse sees only Invoiced ✓",
                 do="WM or Sales Rep: <b>Sales</b> → open the same sale.",
                 see="<b>Invoiced ✓</b>, but no invoice or Xero number anywhere."),
            dict(lane="DLR", who=["DLR"], short="Dealer sees the invoice record",
                 do="<b>Invoices</b>.",
                 see="Their own invoice records and status; no Xero number and no prices (prices are on the Xero invoice)."),
            dict(lane="CAT", who=["RM", "WM", "ADM"], short="Non-consignment sale (from warehouse)",
                 do="<b>Sales &amp; Stocktakes</b> → <b>Record sale</b> → Dealer: <b>Non-consignment sale (from warehouse)</b>. "
                    "Customer name and phone, tyres → <b>Record sale</b>.",
                 see="\"Non-consignment sale from the warehouse; invoice record created…\". Stock leaves the warehouse; nothing is "
                     "replaced. Complete its record in Xero as in step 3."),
            dict(lane="BILL", who=["RM", "FM", "ADM"], short="If wrong: Void with reason",
                 do="Open an invoice record → <b>Void</b> → give a reason → <b>Void invoice</b>.",
                 see="Status <b>Void</b>; the reason is recorded and the sold tyres are back under Who to invoice."),
        ],
        "note": "Deliveries and transfers never create invoices. Tyres not found at a stock check are invoiced as sold on an ordinary invoice record (Journey 9).",
    },
    {
        "title": "Stock check at a dealer",
        "purpose": "Count the tyres at a dealer; tyres not found are found again, or invoiced after 5 days.",
        "starts": "A Sales Rep visits a dealer to count stock.",
        "ends": "The count is posted; tyres not found are re-counted, or invoiced as sold and replaced.",
        "lanes": ["SR", "SYS", "DLR", "CT"],
        "steps": [
            dict(lane="SR", who=["SR", "RM", "WM", "ADM"], short="New stocktake: dealer, then shop",
                 do="<b>Sales &amp; Stocktakes</b> → <b>New stocktake</b> → choose the <b>Dealer</b> (name or account ref.), then the "
                    "<b>Shop</b> → enter the counted quantity for each tyre → <b>Save draft</b>.",
                 see="A card with the dealer, account ref., shop, address, city and rep. Stocktake <b>STK-…</b> in Draft."),
            dict(lane="SR", who=["SR", "RM", "WM", "ADM"], short="Submit count",
                 do="Click <b>Submit count</b>.",
                 see="No shortage: posted straight away. Tyres not found: they are held, and the dealer has 5 days."),
            dict(lane="SYS", who=["DLR", "SR", "WM", "RM", "ADM"], short="Dealer told: 5 days to find them",
                 do="Dealer: check the pop-up and the dashboard.",
                 see="\"N tyre(s) weren't found at today's stock check. You have 5 days to find them…\" and "
                     "<b>Action needed: tyres not found at a stock check</b>. A <b>Questions? Contact us</b> card lists the warehouse, "
                     "the RM and the rep with email and phone."),
            dict(lane="DLR", who=["DLR"], short="Found them: ask for a re-check",
                 do="Open the stock check → <b>I found them, please re-check</b> → optional note → <b>Ask for a re-check</b>.",
                 see="<b>Re-check requested</b>; nothing is invoiced meanwhile. The rep and the warehouse are told."),
            dict(lane="SR", who=["SR", "RM", "WM", "ADM"], short="Start re-count",
                 do="Open the stock check → <b>Start re-count</b> → confirm. Count again → <b>Submit count</b>.",
                 see="A new draft \"This is a re-count of STK-…\" for the same shop; the original shows <b>Re-counted in STK-…</b> "
                     "and its tyres are free again."),
            dict(lane="DLR", who=["DLR"], short="Or: Raise a dispute",
                 do="<b>Raise a dispute</b> → say what is wrong → <b>Send dispute</b>.",
                 see="<b>Disputed</b>; the WM and RM are told; nothing is invoiced meanwhile."),
            dict(lane="DLR", who=["DLR"], short="Or: Not found, invoice them now",
                 do="<b>Not found, invoice them now</b>.",
                 see="\"The tyres not found were invoiced as sold: invoice record INV-…\"; a sale and a replacement are raised."),
            dict(lane="CT", who=["RM", "WM", "ADM"], short="Staff: invoice the shortage",
                 do="For a dispute or on request: <b>Invoice the shortage</b>, with a reason.",
                 see="Same result as step 7; the reason is recorded."),
            dict(lane="SYS", who=["DLR", "SR", "RM", "ADM"], short="After 5 days: invoiced automatically",
                 do="Leave a check with no re-check or dispute until the date shown.",
                 see="Daily reminders meanwhile; then \"Stock check STK-…: tyres invoiced\" (Automatically invoiced: not found within 5 days). "
                     "The invoice record is completed in Xero as usual (Journey 8)."),
        ],
        "note": "Nothing is written off as \"missing\": in consignment, tyres that aren't found are re-checked or invoiced.",
    },
    {
        "title": "Agreed stock levels and backorders",
        "purpose": "Keep each dealer at an agreed level per tyre, and supply waiting orders when stock arrives.",
        "starts": "A stock level is agreed with a dealer, or orders cannot be supplied yet.",
        "ends": "Shortfalls are requested, supplied from new stock and dispatched.",
        "lanes": ["RM", "SYS", "CT", "WM"],
        "steps": [
            dict(lane="RM", who=["RM", "ADM"], short="Add SKU target (agreed level)",
                 do="<b>Dealers</b> → open the dealer → <b>Consignment stock by SKU</b> → <b>Add SKU target</b>: location, "
                    "tyre, target, auto-replenish on/off, reason → <b>Save target</b>.",
                 see="The row shows Target, On hand, Open replenishment and Unmet."),
            dict(lane="CT", who=["RM", "WM", "ADM"], short="Generate target shortfalls",
                 do="<b>Replenishment</b> → <b>Generate target shortfalls</b>.",
                 see="Requests raised for tyres below their agreed level (reason <b>Target shortfall</b>)."),
            dict(lane="SYS", who=["RM", "WM", "ADM"], short="Sales replaced up to the level",
                 do="Report a sale at that dealer (Journey 7).",
                 see="The replacement tops up to the agreed level only; with auto-replenish off, none is raised."),
            dict(lane="CT", who=["RM", "WM", "SR", "ADM"], short="Review Backorders",
                 do="<b>Backorders</b>.",
                 see="Waiting demand, highest priority first, then oldest; overdue and urgent ones stand out."),
            dict(lane="WM", who=["WM", "ADM"], short="New stock: Confirm allocations",
                 do="After receiving (Journey 4): <b>Backorders</b> → <b>Confirm allocations</b>.",
                 see="Stock is reserved for those requests."),
            dict(lane="WM", who=["WM", "ADM"], short="Pick & dispatch",
                 do="<b>Warehouse</b> → <b>Pick &amp; dispatch</b> → <b>Dispatch</b> (as in Journey 7).",
                 see="Deliveries <b>In transit</b> to the dealers."),
            dict(lane="CT", who=["RM", "WM", "ADM"], short="Cancel a backorder (if needed)",
                 do="<b>Replenishment</b> → open the request → <b>Cancel quantity</b>, with a reason.",
                 see="The outstanding quantity goes down; the history shows who and why."),
        ],
    },
    {
        "title": "Checking stock, history and reports",
        "purpose": "Everyone can see what they need, and only what they are allowed to see.",
        "starts": "You want to know where stock is, where it came from, or how things stand.",
        "ends": "You found the answer, and dealers saw only their own information.",
        "lanes": ["STAFF", "DLR"],
        "steps": [
            dict(lane="STAFF", who=["ADM", "RM", "WM", "SR"], short="Stock Overview",
                 do="<b>Stock Overview</b>.",
                 see="Per tyre: total, available, reserved, shipped, blocked, delivered."),
            dict(lane="STAFF", who=["ADM", "RM", "WM"], short="Click a number to see why",
                 do="On <b>Warehouse</b>, <b>Stock Overview</b>, <b>Consignment Stock</b> or a dealer's stock tab, click a number, "
                    "e.g. <b>Reserved</b> or <b>Demand</b> next to a tyre.",
                 see="The screen that explains it, filtered to that tyre. <b>Show all</b> removes the filter."),
            dict(lane="STAFF", who=["ADM", "RM", "WM", "SR"], short="Check Stock: search, then results",
                 do="<b>Check Stock</b> (menu, or the <b>Check stock</b> button). The box starts empty: type a SKU or size, click <b>Search</b>.",
                 see="Nothing loads until you click Search. Then the warehouse quantity and every dealer holding it. Dealers never see this."),
            dict(lane="STAFF", who=["ADM", "RM", "WM"], short="On a request: only its own tyres",
                 do="Open a stock request or replenishment request → <b>Stock for this request</b>.",
                 see="Only the tyres on that request: warehouse yes/no and how many, this dealer's own stock, other dealers."),
            dict(lane="STAFF", who=["RM", "ADM"], short="Settings: photo archiving",
                 do="<b>Settings</b> → <b>Archive photos after</b> (e.g. 6 months) → <b>Save</b>. Optionally <b>Run clean-up now</b>.",
                 see="The figures update. Archived photos are listed with the date they will be deleted (90 days after archiving)."),
            dict(lane="STAFF", who=["ADM", "RM", "WM"], short="Stock Movement and Allocation",
                 do="<b>Stock Movement</b>, then <b>Stock Allocation</b>.",
                 see="Every stock movement with date and reference; stock reserved for each dealer."),
            dict(lane="STAFF", who=["ADM", "RM", "WM", "SR"], short="(i) where it came from",
                 do="Hover over (or tap) the <b>(i)</b> icon next to a tyre on <b>Consignment Stock</b>, <b>Warehouse</b> or a dealer page.",
                 see="A two-line summary, e.g. \"2 tyres received on (date) · DEL-… Replacement for sale SAL-…\"."),
            dict(lane="STAFF", who=["ADM", "RM", "WM", "FM"], short="Reports: By dealer by SKU",
                 do="<b>Reports</b> → <b>By dealer by SKU</b> → choose a dealer and the period → <b>Download Excel</b>.",
                 see="Per shop and tyre: on hand, available, held, on the way, waiting, sold, invoiced, not yet invoiced, with dealer totals. "
                     "Units only. The Excel has the same numbers."),
            dict(lane="STAFF", who=["ADM", "RM", "WM", "FM"], short="Other reports",
                 do="<b>Reports</b>: dealer history, warehouse availability, demand, sold not invoiced, ageing, stock-check differences.",
                 see="Each report loads with current figures and no prices."),
            dict(lane="DLR", who=["DLR"], short="Dealer: own stock, reports and (i)",
                 do="<b>Consignment Stock</b> → the <b>(i)</b> icon; then <b>Reports</b> → <b>By dealer by SKU</b>.",
                 see="Where each tyre came from, in plain words, and only their own shops; never another dealer's name."),
            dict(lane="DLR", who=["DLR"], short="Dealer: own tracking only",
                 do="<b>My Requests</b>, <b>Backorders</b>, <b>Deliveries</b>, <b>Stock Transfers</b>, <b>My account</b>.",
                 see="Only this dealer's records. No warehouse stock figures anywhere."),
        ],
    },
    {
        "title": "Managing users, access and hand-overs",
        "purpose": "Give the right people the right access, and hand work over when someone leaves.",
        "starts": "Someone new needs access, someone's access must change, or someone leaves.",
        "ends": "Each person can do exactly what their role allows; no dealer is left without a rep; leavers cannot sign in.",
        "lanes": ["USERS", "ALL", "ADM"],
        "steps": [
            dict(lane="USERS", who=["ADM", "RM"], short="Administration > Users > New user",
                 do="<b>Administration</b> → <b>Users</b> → <b>New user</b>: email, full name, <b>Phone</b> (optional; dealers see it), "
                    "role (incl. <b>Finance Manager</b>; and the dealer for a Dealer login), temporary password → <b>Save</b>.",
                 see="The user is listed as <b>Active</b>; reps show \"Looks after N dealers\"."),
            dict(lane="USERS", who=["ADM", "RM"], short="New rep replacing someone",
                 do="On <b>New user</b>, tick <b>Is this person replacing someone?</b> → choose who → <b>Take over everything</b> "
                    "(the other person is leaving) or <b>Work alongside</b> and tick the dealers to share → <b>Save</b>.",
                 see="The dealers (and their deliveries and approvals) now belong to the new person; with Take over, the other login is "
                     "<b>Inactive</b>. The dealers are told who their new rep is."),
            dict(lane="ALL", who=["ALL"], short="New user signs in (Journey 1)",
                 do="The new user signs in and chooses their own password.",
                 see="Their dashboard and the menu for their role; a new rep sees \"You now look after N dealer(s)\"."),
            dict(lane="USERS", who=["ADM", "RM"], short="Change role or reset password",
                 do="Open the user → change <b>Role</b>, or type a new password (blank keeps the current one) → <b>Save</b>.",
                 see="Saved; the user's menu changes at next sign-in."),
            dict(lane="USERS", who=["ADM", "RM"], short="Leaver: Hand over…, then deactivate",
                 do="Open the user → <b>Status</b>: <b>Inactive</b> → <b>Save</b>. If refused, <b>Hand over…</b> → choose a colleague "
                    "with the same role → <b>Everything</b> (tick \"is leaving: deactivate their login\") → reason → <b>Hand over</b>.",
                 see="Deactivating someone who still has dealers or hand-overs says \"… Hand them over first\". After the hand-over, "
                     "the summary lists what moved and the leaver can no longer sign in."),
            dict(lane="ALL", who=["ALL"], short="Check each role's menu",
                 do="Sign in as each role and compare the menu with the <b>Who's who</b> page. A dealer types /warehouse in the address bar.",
                 see="Menus match. The dealer is not allowed to see warehouse pages."),
            dict(lane="ADM", who=["ADM", "RM"], short="Audit log and feedback",
                 do="<b>Administration</b> → <b>Audit log</b>, then <b>Pilot feedback</b>.",
                 see="Who did what and when (including hand-overs); feedback sent by testers."),
        ],
    },
]

# Big picture: boxes (id, label, journeys) and arrows.
BIG_PICTURE = {
    "boxes": [
        ("setup", "Set up\nDealers, tyres, prices, logins", "2 · 3 · 12"),
        ("supplier", "Supplier tyres into\nthe warehouse", "4"),
        ("order", "Dealer orders stock\nand it is delivered", "5 · 10"),
        ("find", "\"Get this tyre for me\"\nfrom another dealer", "6"),
        ("sell", "Dealer sells, reports it,\ngets a replacement", "7"),
        ("check", "Stock check at\nthe dealer", "9"),
        ("invoice", "Invoices and\nnon-consignment sales", "8"),
        ("see", "Check stock, history,\nreports, notifications", "1 · 11"),
    ],
}
