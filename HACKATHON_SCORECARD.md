# Hackathon judging guide

## Project thesis

**UniBazar makes verified local stock the routing rule.** A shop speaks or types its shelf state once, reviews a structured draft, and confirms it. A customer basket is offered only to shops whose confirmed quantities can fulfil every line. Acceptance rechecks stock inside one SQLite write transaction, records the accepted prices, deducts stock, closes competing offers, and creates the next delivery task.

This is a neighbourhood commerce system with a stock-truth loop, not a quick-commerce storefront clone. The product mechanism is: **low-friction stock capture → explicit human confirmation → whole-basket eligibility → bounded offer waves → atomic acceptance and stock decrement → less stale stock for the next basket.** We make no claim that the parser or matching algorithm is novel; the idea is the way low-effort inventory capture and truthful dispatch reinforce each other.

## Rubric evidence

### Technical Implementation — 30%

- Flask + SQLite; keys are not required for the core demo and are not shipped to the browser.
- Hinglish parsing is deterministic and local. Parsed stock remains a draft until the shop reviews and saves it.
- Matching aggregates quantities and checks the whole basket before creating offers.
- Substitutions are opt-in, must come from recorded shop inventory, require customer choice, and are checked against the resulting complete basket.
- Acceptance runs under `BEGIN IMMEDIATE`; stale stock and duplicate acceptance return a conflict instead of over-selling. Unit prices are snapshotted at acceptance.
- Eight isolated API tests cover parsing/units, exact eligibility, quantity shortfall, acceptance and price snapshot, simultaneous acceptance attempts, opt-in grounded substitutions, offer-wave advancement, and delivery state transitions.
- Demo database and test databases are separate. Tests create temporary SQLite files under `work/` and remove them after each case.

Run checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
.\.venv\Scripts\python.exe -m py_compile app.py
```

### Innovation & Creativity — 25%

The central design choice is to route **only after a shop has confirmed inventory**, then let acceptance atomically consume that same stock. This directly addresses the failure mode of sending a request to every shop and discovering shortages after the customer has been promised availability. If the exact basket has no match, the customer can opt into a same-category suggestion grounded in a shop's recorded inventory; the customer still chooses before a substitute order is dispatched.

Pitch the invention as **“voice-to-verified-stock routing”** or **“stock truth before speed.”** Do not pitch the UI resemblance to any marketplace as the innovation.

### Sponsor / Track Fit — 25%

The supplied brief names **Local Business & Creator Tools** and mentions Urban Mobility as a delivery-related touch. Evidence for the primary track is the shop-owner workflow: voice/text inventory, correction before save, and fewer irrelevant requests through complete-stock routing. Evidence for the mobility touch is the assigned sample delivery task and sequential pickup/delivery status.

The supplied brief does not name a sponsor, partner, required SDK, or required API. The repo has no sponsor SDK integration, so this guide does not claim one. Delivery is a state-flow demo, not geospatial routing, fleet optimization, or a live mobility integration. The demo Google control is not OAuth.

### Execution & Completeness — 20%

The working demo path is: shop confirms stock → customer places the exact seeded basket → only Asha receives the offer → owner accepts → quantities and order value update → delivery partner marks pickup and delivery → customer sees the final status. The browser view is backed by the same API state, rather than a disconnected mock.

Sample records are labeled. The local parser works without an API key or internet. Errors distinguish an unrecognized basket, a no-match result, changed stock, expired/duplicate acceptance, and invalid delivery transitions. `README.md` includes local setup, demo credentials, API map, test command, and the limits of the prototype.

## Three-minute demo script

1. **Show the shop's input:** use Store owner → Open demo. Enter `10 kilo atta, 5 Fortune tel, 20 Maggi`; review and confirm the parsed rows. Point out that nothing saves before confirmation.
2. **Show the routing rule:** sign out, use Customer demo, place `2 Maggi, 1 Fortune oil`. Explain that eligibility checks every SKU and requested quantity. The seeded exact match is only Sample · Asha Kirana.
3. **Show the consequential action:** sign in as Store owner and accept the offer. Show Maggi decreasing by 2 and Fortune oil by 1, and the accepted basket estimate appearing in the store history.
4. **Close the loop:** sign in as Delivery partner, confirm pickup, mark delivered, then check the customer tracking state.
5. **Optional recovery case:** reset demo data if needed; place `1 Fortune oil, 1 Sundrop oil, 1 Maggi` with substitutions off (no exact match), then retry with substitutions on. Choose the recorded Sundrop stock suggestion and show that the complete resulting basket is rechecked before the offer.

Do not claim real customers, shops, revenue, payments, delivery routes, or notification delivery. The sample data exists to make the mechanism visible in a short judging session.

## Evidence boundary

| Claim | Evidence in the repo | Limit |
|---|---|---|
| Voice/text stock entry | Browser speech when supported; deterministic text parser; editable review | Speech support and transcription quality vary by browser/device |
| Correct shop receives an offer | Server-side whole-basket, quantity-aware eligibility | Small seeded catalog, not production catalog scale |
| No accidental double sale | Immediate write transaction, stock recheck, accepted-order guard | Prototype is SQLite/local; no load claim |
| Customer-approved substitution | Inventory-grounded suggestions and explicit selection endpoint | Same-category heuristic does not prove brand/quality equivalence |
| Delivery flow | Assigned → picked up → delivered state changes | No live courier, map, or geo-routing integration |
| Track fit | Local inventory and order workflow; sample last-mile state | No named sponsor SDK/API in supplied brief |
