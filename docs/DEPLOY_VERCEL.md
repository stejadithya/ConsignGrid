# Deploying TyreGrow to Vercel — step by step

What you will end up with:

```
Users ──https──> TyreGrow web app (Vercel project 1, folder frontend/)
                      │  /api/* is forwarded to
                      ▼
                 TyreGrow API (Vercel project 2, folder backend/, Python)
                      │
                      ▼
                 Neon Postgres database (created from Vercel Storage)
```

Accounts you need (all have free tiers): **GitHub** (the repo `stejadithya/tyreworld`) and **Vercel** (sign in with GitHub). Neon is created from inside Vercel. Set `DEFAULT_CURRENCY=NZD` on the API project; the dealer price list is in NZD.

Time needed: about 30–45 minutes.

---

## Step 1 — Get the code onto `main`

1. On GitHub, open the repo → **Pull requests → New pull request**.
2. Base: `main`, compare: `claude/blissful-cray-nq8382` → **Create pull request** → **Merge**.

(Alternatively, deploy the branch directly: in steps 5 and 6, set the branch under each Vercel project's **Settings → Environments → Production → Branch Tracking**.)

## Step 2 — Create the database

1. Go to <https://vercel.com/dashboard> → **Storage** tab → **Create Database**.
2. Choose **Neon** (Serverless Postgres) → **Continue**. Accept the Neon terms (an account is created for you).
3. Pick a **region** close to your users (and remember it; use the same region for the API in step 5). Plan: Free. Name: `tyregrow-db` → **Create**.
4. Open the new database → **.env.local** (or **Quickstart**) tab → **Show secret**. Copy and save two values somewhere safe:
   - `DATABASE_URL` — the **pooled** connection (host name contains `-pooler`). Used by the API.
   - `DATABASE_URL_UNPOOLED` — the **direct** connection. Used for setting up tables.

Keep these secret. Anyone with them can read or change all data.

## Step 3 — Create the tables and the pilot accounts

There is **no demo data**. The database starts empty and the business enters real transactions.

### A. Using GitHub Actions (recommended)
1. GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
   Name: `DATABASE_URL_UNPOOLED`, Value: the unpooled URL from step 2 → **Add secret**.
2. Add the pilot account secrets listed in **[PILOT_USERS.md §5](PILOT_USERS.md#5-one-time-reset-to-the-clean-pilot-state)** (`PILOT_RM_EMAIL`, `PILOT_RM_PASSWORD`, …).
3. GitHub repo → **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
4. Click **Database setup** → **Run workflow** → branch `main` → type `RESET-PILOT` in **pilot_reset** → **Run workflow**.
   This **deletes all data** and creates the four pilot accounts. Run it once at the start of the pilot only.
5. Wait for the green tick. The log lists the counts after the reset: every business count is 0, users is 4.

For later updates (new migrations), run the same workflow with **pilot_reset left empty**. That only migrates and never deletes data.

**Clean up for UAT** (keeps people, dealers and SKUs; removes all test activity):
1. **Actions → Database setup → Run workflow**, branch `main`, type `PREVIEW` in **uat_reset**. The log lists what is kept and what would be deleted. Nothing changes.
2. Run again with `CLEAN-FOR-UAT` in **uat_reset**. It **keeps** user logins, dealers (accounts, locations, agreements), dealer-specific prices, SKUs and tax rates. It **deletes** all stock and stock movements, stock requests, replenishment requests and backorders, deliveries, transfers, sales (including cash sales), invoices, stocktakes, purchase orders, dealer agreed stock levels, notifications, change history and feedback. Document numbers restart at 000001. It then puts **10 of every active SKU** in the main warehouse. All of this runs as one step: either everything is done or nothing changes.

### B. From your computer (needs Python 3.11+)
```bash
git clone https://github.com/stejadithya/tyreworld.git && cd tyreworld/backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export DATABASE_URL='<UNPOOLED URL>' # Windows PowerShell: $env:DATABASE_URL='<UNPOOLED URL>'
alembic upgrade head
# then the one-time reset described in docs/PILOT_USERS.md §5B
```

## Step 4 — Generate a secret key

Create one long random string (keep it secret, never commit it). Use any of these:
- <https://generate-secret.vercel.app/48>, or
- `python -c "import secrets; print(secrets.token_urlsafe(48))"`, or
- `openssl rand -base64 48`

## Step 5 — Deploy the API (Vercel project 1 of 2)

1. Vercel dashboard → **Add New… → Project** → find `tyreworld` → **Import**.
2. **Project Name**: `tyregrow-api`.
3. **Root Directory** → **Edit** → select `backend` → **Continue**.
4. **Framework Preset**: **FastAPI** (Vercel detects it; "Other" also works). Leave Build/Output/Install commands empty.
   Vercel uses `backend/app/main.py` (the `app` object) as the entrypoint and installs the dependencies listed in `backend/pyproject.toml`.
5. Open **Environment Variables** and add:

   | Key | Value |
   |---|---|
   | `DATABASE_URL` | the **pooled** URL from step 2 |
   | `DB_DISABLE_POOL` | `true` |
   | `DB_DISABLE_PREPARED_STATEMENTS` | `true` |
   | `APP_ENV` | `staging` |
   | `JWT_SECRET` | the secret from step 4 |
   | `AUTH_COOKIE_SECURE` | `true` |
   | `APP_DISPLAY_NAME` | `TyreGrow` |
   | `INVOICE_ISSUER_NAME` | `TyreGrow` |
   | `INVOICE_ISSUER_DETAILS` | your address / tax number line, e.g. `1 Warehouse Road, City · Tax no. …` |
   | `DEFAULT_CURRENCY` | e.g. `AUD`, `INR`, `NZD`, `GBP` |

   Optional, to email delivery notes to resellers. Leave these out and the PDF can still be downloaded; nothing is emailed until they are set:

   | Key | Value |
   |---|---|
   | `SMTP_HOST` | your mail server, e.g. `smtp.gmail.com` (Google Workspace) or `smtp.office365.com` (Microsoft 365) |
   | `SMTP_PORT` | `587` |
   | `SMTP_USERNAME` | the sending mailbox, e.g. `deliveries@yourdomain` |
   | `SMTP_PASSWORD` | that mailbox's app password (never commit it) |
   | `SMTP_FROM` | e.g. `TyreGrow <deliveries@yourdomain>` |
   | `DELIVERY_NOTE_REPLY_TO` | optional: where reseller replies go |
   | `BUSINESS_TIMEZONE` | default `Pacific/Auckland` (times on delivery notes) |

6. **Deploy**. When finished, click **Continue to Dashboard**, and note the domain, e.g. `https://tyregrow-api.vercel.app`.
7. **Settings → Functions → Function Region**: choose the same region as the database → Save → **Deployments → ⋯ → Redeploy**.
8. **Settings → Deployment Protection** → turn **Vercel Authentication** **off** → Save.
   (The web app calls the API server-to-server; with protection on, every call gets a Vercel login page. The API has its own login.)
9. Test: open `https://tyregrow-api.vercel.app/api/health`. You must see:
   `{"status":"ok","name":"TyreGrow","env":"staging"}`

## Step 6 — Deploy the web app (Vercel project 2 of 2)

1. Vercel dashboard → **Add New… → Project** → import `tyreworld` **again**.
2. **Project Name**: `tyregrow` (this becomes `https://tyregrow.vercel.app` if available).
3. **Root Directory** → `frontend`. Framework Preset is detected as **Next.js**.
4. **Environment Variables**:

   | Key | Value |
   |---|---|
   | `API_URL` | `https://tyregrow-api.vercel.app` (your API domain from step 5, no trailing `/`) |
   | `NEXT_PUBLIC_BRAND_NAME` | `TyreGrow` |

5. **Deploy**. Open the domain shown, e.g. `https://tyregrow.vercel.app`. You should see the **TyreGrow** sign-in page.

> `API_URL` and `NEXT_PUBLIC_BRAND_NAME` are applied at build time. If you change them, go to **Deployments → ⋯ → Redeploy**.

## Step 7 — (Optional) Your own domain

Web app project → **Settings → Domains → Add** → e.g. `app.tyregrow.com` → follow the DNS instructions shown (a CNAME at your domain registrar). HTTPS is automatic. No change is needed on the API project.

## Step 8 — Start the pilot

Open the **web app** domain (always the web app, not the API domain). Each person signs in with their email and temporary password, then chooses their own password.

Suggested first steps with real data:

| # | Who | Do this |
|---|---|---|
| 1 | Warehouse Manager | **Products**: add products (or import the Excel product master once available). The dealer price list is under **Products → Reference documents**. |
| 2 | Warehouse Manager | **Purchasing & Shipments → Receive without PO** (or **Warehouse → Opening balance**) for the stock actually on hand. |
| 3 | Relationship Manager | **Resellers**: check the pilot reseller, add locations, consignment SKU targets and customer prices. |
| 4 | Warehouse Manager | **Warehouse → Opening balance** at the reseller location for stock already placed there, or allocate and dispatch replenishment. |
| 5 | Reseller / Sales Representative | **Report Sale** / **Record sale** for real sales. Replenishment is raised automatically. |
| 6 | Everyone | **User menu → Pilot feedback** for anything that is wrong, missing or unclear. |

The full role guide is in [PILOT_USERS.md](PILOT_USERS.md).

### Automated end-to-end tests
They **create data**, so run them only against a disposable local database (see `frontend/e2e/helpers.ts`). Never run them against the pilot.

## Step 9 — Day-to-day updates

- Every push/merge to `main` redeploys both projects automatically.
- If a change includes a database migration (a new file in `backend/alembic/versions/`), run **Actions → Database setup** with **pilot_reset left empty** **before** or right after the deploy. Pilot data is never removed by deployments or migrations.
- Logs: Vercel project → **Logs** (API errors show here). Database usage: Vercel → Storage → your Neon database.

## Nightly photo clean-up (archiving)

Drop-off photos are archived after the period set in **Settings** (default 6 months), then deleted 90 days later.
A nightly job does this; `backend/vercel.json` schedules it for 03:15 UTC.

1. Generate a random secret, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
2. Vercel → API project → **Settings → Environment Variables** → add `CRON_SECRET` with that value (Production) → **Redeploy**.
3. Check: Vercel → API project → **Settings → Cron Jobs** lists `/api/proofs/retention/cron`.

Without `CRON_SECRET` the nightly call is refused and nothing is archived automatically. A Relationship Manager or
Administrator can still use **Settings → Run clean-up now**.

## Daily stock-check invoicing (release 1.11)

Tyres not found at a stock check are invoiced as sold when the dealer's find window ends (`STOCKTAKE_FIND_DAYS`,
default 5). This already happens whenever someone has TyreGrow open (the notification bell checks every 20 seconds);
a daily job also runs it so nothing waits for a sign-in. `backend/vercel.json` schedules
`/api/stocktakes/auto-invoice/cron` for 04:05 UTC.

1. It uses the same `CRON_SECRET` as the photo clean-up; if that is already set, there is nothing to add.
2. Optional: set `STOCKTAKE_FIND_DAYS` on the API project to change the window (whole days) → **Redeploy**.
3. Check: Vercel → API project → **Settings → Cron Jobs** lists `/api/stocktakes/auto-invoice/cron`.

Running it more than once does no harm: each stock check is invoiced once. Checks where the dealer asked for a
re-check or raised a dispute are never invoiced automatically.

## Troubleshooting

| What you see | Fix |
|---|---|
| Sign-in page shows "Request failed (404)" or nothing happens | `API_URL` wrong or missing in the web app project → fix → Redeploy the web app |
| API calls return an HTML "Vercel Authentication" page | Step 5.8: turn off Deployment Protection on the API project |
| `/api/health` returns `{"status":"error", "reason": ...}` | The reason names the bad setting (e.g. `JWT_SECRET` too short, `APP_ENV` not lowercase) → fix it → Redeploy API |
| Logs: `ModuleNotFoundError: No module named 'fastapi'` | Dependencies were not installed: make sure the deployment includes the commit that lists them in `backend/pyproject.toml`, then Redeploy **without build cache** |
| Logs: `relation "users" does not exist` | Step 3 was not run against this database |
| Logs: `prepared statement ... does not exist` | Set `DB_DISABLE_PREPARED_STATEMENTS=true` on the API → Redeploy |
| Signed in, then immediately asked to sign in again | You opened the API domain. Use the web app domain |
| "Invalid email or password" | Use the temporary password from the set-up secrets; the Relationship Manager can reset a password under **Administration → Users** |
| First request after a quiet period is slow | Normal on free tiers (function cold start + Neon waking up) |
| GitHub action fails at "Check secret" | Add the `DATABASE_URL_UNPOOLED` repository secret (step 3A.1) |

## Before going live with real data
- Create a **separate** Neon database for production and set `APP_ENV=production`. Create its accounts with the guarded reset (see `docs/PILOT_USERS.md`), then add further users from **Administration → Users**.
- Configure tax rates (**Administration → Tax rates**), the warehouse, products, resellers, agreements and targets, then post opening balances (**Warehouse → Opening balance**).
- Turn on Neon backups / point-in-time restore, and review `docs/DEPLOYMENT.md` and the open business decisions in `docs/DECISION_LOG.md`.
