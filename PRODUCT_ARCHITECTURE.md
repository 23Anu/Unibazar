# UniBazar product and architecture notes

## Product promise

Make local grocery ordering feel predictable for customers and low-effort for shop owners. The core proof is: a shop only receives a basket offer when its confirmed stock can fill every line and quantity.

## Screen hierarchy

### Customer

1. **Context and search:** brand, delivery area, product search, and clear sample-data status.
2. **Browse:** category chips followed by a compact product grid. Every card shows product image (with a local visual fallback), brand, pack size, indicative price, availability, and one Add action.
3. **Basket:** keep quantities, subtotal, and store-matching rules together. Make the next action explicit: find a store.
4. **Order status:** after placement, replace the empty-state with the actual state (searching, no match, offer sent, accepted, picked up, delivered). Never label a no-match order as searching.

### Shop owner

1. **At-a-glance:** accepted order value (marked as a demo estimate), accepted orders, waiting requests, and low-stock count.
2. **New requests:** keep the inbox visible near the top because each offer expires. Show basket lines and give Accept / Decline equal, clear choices. New requests create one notification, and the inbox remains the source of truth.
3. **Stock update:** voice or text -> editable review -> explicit save. The preview is a draft; saving changes only the products spoken/typed.
4. **Current stock:** quantities and prices, with low / out labels. A per-shop sample selector is for demo rehearsal only.
5. **History:** recent accepted baskets use the accepted-time price snapshot, so later price edits do not rewrite old sales estimates.

### Delivery partner

1. Show only the active queue and its next action.
2. Keep one prominent step at a time: Confirm pickup, then Mark delivered.
3. Do not imply a live map, address, or fleet assignment until those services exist.

## Interaction rules

- One clear primary action per step; secondary actions stay visually quieter.
- Confirm destructive actions with their exact scope. “Reset sample stock” must not silently delete orders.
- Give immediate feedback after saves and state transitions. Keep persistent connectivity failures out of a repeating toast loop; retry with backoff and show recovery once.
- Voice is optional. Text remains fully usable without microphone permission or browser speech support.
- Treat sample accounts, shops, prices, and order values as demo data. Do not imply real delivery or paid revenue.

## Domain boundaries

The current prototype stays Flask + SQLite and is intentionally small. Keep business rules on the server:

- **Inventory:** parse draft, validate known SKUs / quantities / units, confirm, upsert only mentioned stock.
- **Matching and dispatch:** compare the complete basket, create timed waves, expire and advance them, and reject unavailable shops.
- **Orders:** customer preference controls whether substitution suggestions are offered; accept is first-winner and atomic with stock deduction.
- **Pricing:** snapshot the selected shop's item prices when an offer is accepted.
- **Delivery:** advance only through allowed statuses.
- **UI:** role-specific views consume `/api/state`; controls call narrow endpoints and show their result.

For the next growth step, split the monolith by these boundaries rather than adding more branching to one file:

```text
app/
  routes/          # HTTP parsing, status codes, response shapes
  domain/          # inventory, matching, order and delivery rules
  repositories/    # SQLite queries and transactions
  services/        # orchestration across domain + repositories
static/js/
  api.js           # fetch, errors, retry and polling
  customer.js      # catalog, basket, order status
  store.js         # stock, request inbox, performance
  delivery.js      # delivery queue and transitions
```

Before real shops use this, add authenticated role-to-shop ownership, schema migrations, inventory audit events, stock reservations, cancellation/refund rules, pagination, idempotency for retryable actions, and integration/concurrency coverage. The current sample-shop selector and demo credentials are not access control.
