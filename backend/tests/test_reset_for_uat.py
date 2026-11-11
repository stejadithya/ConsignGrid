"""The UAT clean-up keeps dealers, SKUs, prices and users, and empties everything else safely."""

from scripts.reset_for_uat import KEEP, plan


def test_plan_keeps_master_data_and_never_breaks_references():
    keep, wipe = plan()   # exits if a kept table points at one that would be emptied
    # 1.11: copies of signed agreements are dealer master data and are kept too (D8).
    assert set(keep) == KEEP == {"users", "resellers", "locations", "consignment_agreements",
                                 "consignment_agreement_files", "customer_prices", "products", "tax_rates", "app_settings"}
    for t in ("stock_requests", "replenishment_requests", "deliveries", "transfers", "consignment_sales", "invoices",
              "stocktakes", "inventory_transactions", "stock_balances", "consignment_allocations", "notifications",
              "number_sequences"):
        assert t in wipe
