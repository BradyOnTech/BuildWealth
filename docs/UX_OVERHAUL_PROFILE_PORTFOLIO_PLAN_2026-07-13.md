# UX Overhaul: Profile & Portfolio Setup — Implementation Plan (2026-07-13)

Source: founder dogfooding of new-profile setup + browser walkthrough of every
Profile tab, composer, Taxes/Investing forms, Plan assumptions, and the
Portfolio maintenance surfaces.

## Problem statement (user's words)

Setting up a profile, investments, and plan is clunky. It must be **obvious how
to do each item**, **easy to add/modify/delete** anything, and the app should
**propose defaults** for values most people don't know (marginal tax rate),
estimated from data already entered or population averages.

## Findings being fixed

Profile: ten-tab filing cabinet with no flow; composers show 7 fields when 2
matter; amounts asked monthly when people know annual; rows have Remove but no
Edit; Taxes asks for three rates the app can compute; Investing choices all
"Not set" with no recommended option; capture paths (photo, copilot, inference)
live on different pages from the fields they fill; Plan shows the literal
string "app default" for nine assumptions.

Portfolio: reading surfaces are strong, but all add/edit hides behind
Maintenance → nine sub-cards; adding a holding requires knowing it's a "BUY
transaction" (9-field composer: date, symbol, action, quantity, unit price,
fee, account, currency, lot method); cash means a CASH_DEPOSIT transaction; a
house means custom asset + manual price. No inline edit on anything; no
guided "get your money in here" for a new user.

## Design principles

1. **Confirmation over interrogation** — never show a blank the app can
   estimate; pre-fill with a labeled suggestion and let the user correct it.
2. **Two required fields per add** — everything else defaults or collapses
   behind "More detail".
3. **Every value editable in place** — click to edit, Remove stays, undo toast
   after destructive/applied changes.
4. **Meet the user where the question is** — photo capture, copilot handoff,
   and inference suggestions render inline in the section they fill, not on
   another page.
5. **No hidden numbers** — anywhere a default is used (Plan assumptions), show
   the resolved value and its provenance, never the words "app default".

---

## Workstream A — Smart Defaults engine (backend foundation)

New `services/profile_defaults.py`: one service that, given the current
profile + household + holdings, returns a suggestion per estimable field:
`{field_path, value, display, basis: "computed"|"typical", explanation}`.

- Tax rates: marginal/effective from filing status + income via
  `tax_engine` brackets (already real); state rate from a new
  `data/state_tax_rates_seed.json` (flat approximations per state, honestly
  labeled); when income unknown, fall back to "typical household" values
  with basis="typical".
- Guardrails: risk comfort, tax sensitivity, simplicity, research confidence
  get recommended options (age- and horizon-aware where the self member's
  birth_year exists; otherwise the moderate column).
- Target mix: named presets ("Three-fund 80/20", "Classic 60/40",
  "Age-based" = ~(110 − age) equity) computed from the self member.
- Emergency cushion months from household size (single 3–6, family 6+).
- Endpoint: `GET /api/profile/defaults` → suggestions map. Confirming a
  suggestion writes with provenance `inferred` source `profile_defaults`,
  flipping to `user_confirmed` on explicit accept (metadata system already
  supports this).

Tests: bracket math per filing status, state fallbacks, typical-value
fallbacks, age-based mix, endpoint shape.

## Workstream B — Edit-everywhere primitives (shared frontend)

1. **Inline row editing** in `views/profile/tables.js`: click a cell → input
   with the composer field's kind/options; Enter/blur saves the row via the
   existing full-list PUT; Escape cancels. Add an Edit affordance per row for
   discoverability; keep Remove.
2. **Undo toast**: small shared `lib/undo.js` — after Remove/Apply, show
   "Removed Salary — Undo" for 6s; undo restores the prior list (client holds
   the pre-change payload; one PUT to restore).
3. **Composer redesign**: exactly the required fields visible (label +
   amount for money rows; name + relationship for household), an
   **Annual/Monthly toggle** on all amount fields (store monthly, display
   preference remembered per session), advanced fields behind a "More
   detail" disclosure.
4. **Suggested-value field component**: renders a pre-filled suggestion with
   basis label ("22% · estimated from your income — tap to correct") and an
   accept-on-save behavior; used by Taxes, Investing, and the setup rail.

Same primitives get reused by Portfolio (workstream D).

Tests: node unit tests for inline-edit render/build round-trips, toggle math
(annual→monthly), undo restore; Playwright spec for edit-in-place + undo.

## Workstream C — Guided setup rail (Profile)

New `views/profile/setup_rail.js`, shown at the top of Profile (and linked
from Today's next-question card) whenever readiness < complete:

- Five steps: **Household → Money in & out → Debt & goals → Taxes →
  Guardrails**. "Step N of 5" progress, each step 2–4 questions using the
  workstream-B composers and workstream-A suggestions.
- Every step offers three inline alternates: 📷 *From a document* (existing
  document capture, moved into the rail), 💬 *Ask me in chat* (deep-link to
  copilot with the section interview + chips), and *Use estimates* (accept
  all suggestions for the step, provenance `inferred`).
- Completing a step auto-advances; the rail collapses to a "Setup complete"
  line when readiness is all-complete (tabs remain for later editing).
- Inference candidates and document suggestions for a section render inside
  that step (the Inbox lane remains as the audit trail).
- Copy pass: kill machine strings ("0 income item(s) configured") in
  readiness details; write human sentences.

Tests: node tests for step derivation from readiness + suggestion acceptance
payloads; Playwright spec walking the full rail with mocked APIs.

## Workstream D — Portfolio: a real front door + inline maintenance

1. **"Add to portfolio" front door** — one prominent button on Standing with
   four plain flows (new `views/portfolio/add_flow.js`):
   - *I own an investment*: symbol (registry-backed autocomplete), quantity
     OR current dollar value, account (create inline), optional cost basis
     ("don't know" → uses current price and marks basis estimated). Writes
     the BUY/TRANSFER_IN transaction under the hood.
   - *Cash balance*: account + amount → CASH_DEPOSIT.
   - *Property or other asset*: label + value (+ type) → custom asset +
     manual price in one step.
   - *Import a statement*: routes to the existing Import & Review.
2. **Inline holding actions** — on each Standing/Top-holdings row: "Update
   value/quantity" (for custom/manual-priced assets), "Record buy/sell"
   pre-filled with symbol+account, "Remove position" (guided: creates the
   offsetting SELL/TRANSFER_OUT rather than deleting history), all using the
   workstream-B inline patterns.
3. **Transactions table** gains inline edit for note/date/fee and Remove
   with undo (existing delete endpoint), and the composer gets the
   two-field + "More detail" treatment (defaults: today, USD, FIFO, fee 0).
4. **Maintenance reorganization**: rename to "Records & tools"; the nine
   cards group under *Records* (transactions, accounts, audit, export) and
   *Advanced* (manual prices, FX, cost basis, guardrails-link); each card
   states when a normal user needs it.

Tests: pytest for the add-flow endpoints' transaction writes (quantity-only
and value-only paths, estimated-basis flag); node + Playwright for the four
flows and inline actions.

## Workstream E — Plan: resolved assumptions, never "app default"

- `plan.js` key-assumptions strip renders the **resolved number** for every
  assumption (the engine already resolves them server-side; expose the
  resolved set on the plan payload if not present) with provenance
  ("from your profile" / "BuildWealth default") and click-through to the
  Simulations editor primed on that field.
- Marginal tax + filing status pull from profile via workstream A rather
  than the hardcoded settings defaults; mismatches surface as a one-line
  "Plan assumes 28%, your profile says 22% — use profile?" action.

Tests: pytest for resolved-assumption payload; node test asserting no
"app default" string renders; Playwright for the mismatch action.

---

## Status (2026-07-13)

- Phase 1 (A + B): **shipped** — ca422243
- Phase 2 (C): **shipped** — d2dd4dcc
- Phase 4 (E): **shipped** — 4ee997bb (rode ahead of phase 3; small and independent)
- Phase 3 (D): **shipped** — see commit below; note: share transfers record as BUY-at-basis until the ledger supports position transfers

## Sequencing

1. **Phase 1: A + B** — defaults engine + edit-everywhere primitives.
   Immediately fixes the worst pain (no edit, blank rates) on existing tabs
   without moving anything.
2. **Phase 2: C** — setup rail on top of A+B.
3. **Phase 3: D** — portfolio front door + inline maintenance.
4. **Phase 4: E** — plan assumption resolution (small; can ride with 3).

Each phase: full pytest + node + Playwright green before commit; live
browser verification against the running app; one commit per phase, no
co-author trailer.

## Acceptance criteria (user's bar)

- Adding any profile or portfolio item requires ≤ 2 decisions before Save;
  everything else defaulted or collapsible.
- Any value visible in Profile or Portfolio maintenance can be corrected in
  ≤ 2 clicks without re-entering the row, and destructive actions offer undo.
- No estimable field ever renders blank: marginal/effective/state rates,
  guardrail choices, and target mix always show a labeled suggestion.
- A brand-new user reaches "profile complete + first holdings entered"
  purely by following on-screen next steps (rail + front door), never by
  discovering tabs.
- The string "app default" does not appear anywhere in the UI.
