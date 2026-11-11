# TyreGrow website stock API: guide for the website developer

The customer website's **server** can ask TyreGrow whether a tyre can be sold from the warehouse. The answer is a status band,
never a quantity:

| `status` | Meaning |
|---|---|
| `IN_STOCK` | Plenty in the warehouse |
| `LOW` | Only a few left (1 to 4 by default) |
| `OUT` | None available to sell, or the tyre is no longer stocked |

Only stock the warehouse can sell counts: stock already reserved for a dealer, damaged stock and stock held by dealers is
excluded.

## Getting a key

A TyreGrow Administrator creates a key in **Administration → Website access** and gives it to you.
- It looks like `tg_live_…` and is shown to them only once.
- Keep it in your server's secret settings (an environment variable).
- **Never** put it in browser JavaScript, the website's HTML or a mobile app. Those can be read by anyone.

If a key leaks, ask the Administrator to create a new one, switch your server to it, then have the old one revoked.
Revoking takes effect immediately.

## Calls

Base URL: your TyreGrow address (the same one staff use), for example `https://tyregrow.example.com`. Every request sends
the key in the `X-API-Key` header.

### All tyres

```bash
curl -H "X-API-Key: $TYREGROW_KEY" https://tyregrow.example.com/api/partner/v1/stock
```

```json
{
  "generated_at": "2026-10-22T09:15:02Z",
  "items": [
    { "sku": "103294", "name": "CEAT EcoDrive", "size": "195/65R15 91H", "status": "IN_STOCK" },
    { "sku": "104010", "name": "CEAT SecuraDrive", "size": "205/55R16 91V", "status": "LOW" }
  ],
  "unknown_skus": []
}
```

### Some tyres (up to 100 per call)

```bash
curl -H "X-API-Key: $TYREGROW_KEY" "https://tyregrow.example.com/api/partner/v1/stock?sku=103294&sku=104010"
```

SKUs TyreGrow doesn't know are listed in `unknown_skus`.

### One tyre

```bash
curl -H "X-API-Key: $TYREGROW_KEY" https://tyregrow.example.com/api/partner/v1/stock/103294
```

```json
{ "sku": "103294", "name": "CEAT EcoDrive", "size": "195/65R15 91H", "status": "IN_STOCK" }
```

## Responses and errors

| HTTP | When |
|---|---|
| 200 | OK |
| 401 | Missing, wrong or revoked key (`"code": "invalid_api_key"`) |
| 404 | One-tyre call with an SKU TyreGrow doesn't know |
| 422 | More than 100 SKUs in one call |

Every response has `Cache-Control: private, max-age=60`.

## Recommended use

- Fetch the full list about **once a minute** on your server and keep it in memory, rather than calling TyreGrow on
  every page view. Statuses can change at any time as the warehouse works, so a minute is a good balance.
- Treat the status as guidance for showing availability and limiting orders. The API doesn't reserve stock, so on
  `LOW` items two customers could order the last units at the same moment. TyreGrow staff confirm website orders as today.
- If TyreGrow is unreachable, show the last known status, or "Call to confirm", rather than "In stock".
