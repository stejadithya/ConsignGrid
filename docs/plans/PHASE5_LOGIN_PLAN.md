# Phase 5: login page and final polish, plan (for approval, not implemented)

Branch `feature/login-polish-phase5`, from `main` at 8b88bce. Scope: `/login` only, plus the design-system inconsistencies
that are visible there.

## 1. What the review found

Measured at 390 / 820 / 1180 / 1440 px (390 and 820 as touch devices). No page scrolls sideways, and axe finds no
violations at 390 or 1440.

| # | Issue | Where |
|---|---|---|
| A | Own type sizes instead of tokens: headline 26.4 / 36 px (600), copy 15 / 16 px, "Sign in" 22 px, list 15 px, captions 13 px | Whole page |
| B | "Sign in" heading has a 20 px line height on 22 px text (lines would overlap if it wrapped) | Sign-in panel |
| C | The "loop" is a straight row of 4 chips with no return to Warehouse. It is hidden below 1024 px, and at 1180 px it wraps onto two lines | Left panel |
| D | Decoration the design system rules out: a dotted grid, a blurred yellow circle, and a yellow highlighter under "Faster replenishment." (yellow should mark the current step only) | Left panel |
| E | The supporting copy (4–5 lines on a phone), the 3-item capability list and the bottom tagline say the same thing three times | Left panel |
| F | 820 px: a small card floating in a large empty canvas, with about 400 px of empty space below it. 1440 px: the headline sits mid-panel and the chips at the bottom, with large gaps in between | Layout |
| G | Show-password button is 32 × 32 px (under 44 on touch) | Password field |
| H | The show-password button changes its label and also sets aria-pressed, so it is read as "Hide password, pressed" | Password field |
| I | Field errors use role="alert" but aren't linked to their input (no aria-describedby). This is the shared `Field` | Form |
| J | Muted caption on the off-white background (the tagline) | Left panel, desktop |
| K | Hard-coded `rounded-2xl` and `max-w-[440px]` instead of tokens (`rounded-card`) | Card |

What works and stays:
- The charcoal "Sign in" button.
- 44 px inputs.
- 16 px input text on touch screens.
- Logical keyboard order: email → password → show password → Sign in.
- Errors placed under each field, with the server error in an alert above the form.
- Autocomplete attributes.

## 2. Typography (approved tokens only)

| Element | Now | Proposed |
|---|---|---|
| Headline (unchanged words) | 26.4 / 33 px → 36 / 41 px, 600 | `text-display-compact` 24 / 32 on phones, `text-display` 28 / 36 from 640 px, 700 |
| Supporting copy | 15 / 28 → 16 / 28 px | `text-body-lg` 16 / 24, ink-secondary |
| "Sign in" | 22 / 20 px | `text-heading` 18 / 26, 600 |
| "Welcome back…" | 14 px (raw) | `text-body` 14 / 20, ink-secondary |
| Labels | 13 px (Field) | `text-label` 13 / 18 (no change) |
| Help line ("Forgot your password?") | 13 px, ink-muted | `text-label` 13 / 18, ink-secondary |
| Loop step names | 13 px chips | `text-label` 13, 500 |
| Loop step captions | none | `text-caption` 12 / 16, ink-secondary |

There is no separate marketing type scale. A 28 px headline is calmer and more "enterprise" than the current 36 px.
To stop it looking small at 1440 px, the left column gets a narrower measure (about 30rem).

## 3. Layout and spacing

- **Phone (390):** logo → headline → copy (3 lines) → sign-in card → loop.
  - Sign in stays above the fold on an 844 px screen.
  - The loop moves below the form, so the form comes first.
  - Card padding 20 px, page gutter 16 px.
- **Tablet portrait (820):** one centred column, max about 36rem: logo, headline, copy, card (full column width), loop.
  - Centred vertically in the viewport, which removes most of the empty space.
- **Tablet landscape (1180) and desktop (1440):** keep the two columns.
  - Left on canvas: logo at the top, then headline, copy and loop as one group, vertically centred, in place of the spread-out `mt-auto` layout.
  - Right: white panel with the form centred, max 400 px.
- **Removed:** dotted grid, yellow glow, the yellow highlighter, the capability list and the bottom tagline (the copy and the loop cover them).
- **Tokens:** `rounded-card`, `shadow-raised`, the 4 px spacing scale, `max-w-sm/md` instead of hard-coded pixel values.

## 4. Operational loop concept

A closed loop of four steps, drawn as a 2 × 2 cycle read clockwise. It is the same shape at every size (about 320 px wide on
a phone, 440 px on desktop):

```
  ┌─────────────────┐          ┌─────────────────┐
  │ [■] Warehouse   │ ───────▶ │ [■] Dealer      │
  │ Stock received  │          │ On consignment  │
  └─────────────────┘          └─────────────────┘
           ▲                            │
           │                            ▼
  ┌─────────────────┐          ┌─────────────────┐
  │ [■] Replenish-  │ ◀─────── │ [■] Sale        │
  │ ment (yellow)   │          │ Sold to a       │
  │ Raised auto-    │          │ customer        │
  │ matically       │          │                 │
  └─────────────────┘          └─────────────────┘
```

- Charcoal is the base: white tiles with a `line` border, charcoal icons and text, charcoal connector arrows. There is no fill, gradient or shadow beyond `shadow-card`.
- Yellow appears only on **Replenishment**: a yellow icon chip with charcoal icon (ink on brand) and a 3 px yellow marker. That is the step TyreGrow automates, and it echoes "Faster replenishment."
- Captions make it about TyreGrow rather than a generic process:
  - Warehouse: "Stock received"
  - Dealer: "On consignment"
  - Sale: "Sold to a customer"
  - Replenishment: "Raised automatically" (every sale raises one)
- Accessibility: an ordered list named "How TyreGrow keeps stock moving". The last item's screen-reader text ends "…then back to the warehouse". Arrows are aria-hidden. The highlight is not colour alone: the step also carries the caption and an sr-only "(automated by TyreGrow)".
- Built in HTML and CSS (grid plus lucide icons), not an image, so it scales and stays readable.

## 5. Supporting copy

Preferred: "One view of stock across your warehouse and dealer network. Manage consignment, replenishment, transfers and
backorders in one place."

It's good, and shorter and clearer than the current text. One small suggestion: it says "one" twice ("One view" … "in one
place"). Alternative: "One view of stock across your warehouse and dealer network. Manage consignment, replenishment,
transfers and backorders together." Either is fine; nothing changes until you choose.

The headline stays exactly as it is: "Smarter consignment. / Better stock control. / Faster replenishment."

## 6. Accessibility

| Item | Change |
|---|---|
| Password control (G, H) | 44 × 44 tap area on touch (`touch-target`). A fixed label "Show password" with aria-pressed (the toggle pattern), so it is read as "Show password, pressed / not pressed". Same fix in `PasswordForm.tsx`, whose label changes the same way. |
| Field errors (I) | `Field` gives the error or hint an id, and passes it to the control as aria-describedby. This is additive: the render function gets the id as a second argument, and the login inputs use it. |
| Server error | Stays in the alert above the form (role="alert", announced). It is cleared when the user edits a field. |
| Contrast (J) | Captions on canvas use ink-secondary. Checked with axe at all four widths. |
| Focus | All controls already use the charcoal focus ring; the toggle gets the same visible ring. |
| Keyboard-only sign-in | Unchanged order; a browser test will cover it. |

## 7. Files expected

- `frontend/src/app/login/page.tsx`: layout, tokens, copy, loop.
- `frontend/src/components/OperationalLoop.tsx` (new): the loop, reusable for empty states as `DESIGN_SYSTEM.md` intends.
- `frontend/src/components/ui.tsx`: `Field` aria-describedby (additive).
- `frontend/src/components/PasswordForm.tsx`: same show-password toggle fix.
- `frontend/e2e/responsive.spec.ts`: login checks at four widths (no overflow, form above the fold on a phone, loop visible and named, 44 px controls, keyboard-only sign-in, axe), plus a unit test for the loop.
- `docs/DESIGN_SYSTEM.md`: the Phase 5 line in Rollout; the note that the login page keeps its own sizes is removed.

No backend, API, route or permission changes. The existing tests that use "Email", "Password", "Sign in" and "Show password"
keep working (labels unchanged).
