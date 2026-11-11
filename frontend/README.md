# Frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. See the repository root `README.md` for setup.

- `src/config/branding.ts`: product name, tagline and logo (the only place the brand is defined).
- `src/lib`: API client (`/api/*` is proxied to the backend by `next.config.ts`), auth context, hooks, types.
- `src/components`: shared UI kit (`ui.tsx`), app shell, pickers, domain tables and panels.
- `src/app/(app)/…`: one folder per navigation module.

```bash
npm run dev         # http://localhost:3000 (expects the API on http://localhost:8000, override with API_URL)
npm run typecheck && npm run lint && npm test
npm run test:e2e    # Playwright; creates data — disposable local database only (see e2e/helpers.ts)
```
