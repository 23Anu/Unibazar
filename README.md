# UniBazar (Kirana Express prototype)

**Stock truth before speed.** A Flask + SQLite prototype for neighbourhood grocery discovery, spoken/text stock entry, and full-basket order routing. Its proof point: an order request reaches a shop only when confirmed stock can fulfil every product and quantity.

All shops, prices, delivery tasks, and accounts are demo data. There is no real customer login, payment, fleet, or push-notification service.

## Run locally

### Windows

Double-click `run.bat`. It checks the local API before opening the app at <http://127.0.0.1:5001/>. Port 5001 is used because port 5000 is unavailable in some Windows environments.

### macOS / Linux

```sh
chmod +x run.sh
./run.sh
```

The first run creates a virtual environment, installs `requirements.txt`, copies `.env.example` to `.env`, and initializes the SQLite database. Voice input depends on browser support and microphone permission; text entry always works.

## Demo accounts

- Customer: `9999900001` / `demo123`
- Store owner: `asha@demo.in` / `demo123`
- Delivery partner: `rider@demo.in` / `demo123`

The store selector can switch among sample shops for rehearsals. It is a demo control, not shop-level authorization.

## Main workflows

1. **Store owner:** add a multi-product stock phrase, review the parsed draft, edit quantities/prices, and save. Only mentioned SKUs change. Shop reset restores that shop's starter stock and keeps order history.
2. **Customer:** place `2 Maggi, 1 Fortune oil`. Only Sample Asha Kirana has the complete basket, so it receives the offer.
3. **Offer acceptance:** accepting checks stock again inside a write transaction, records the accepted-time unit-price snapshot, deducts stock, and closes competing offers.
4. **Timed dispatch:** the UI polls the explicit dispatch endpoint. When a wave expires, the next eligible shops are offered the basket. **Advance demo wave** is available for rehearsal.
5. **Substitution:** request `1 Fortune oil, 1 Sundrop oil, 1 Maggi`. No seeded shop has all three lines. If the customer explicitly allows substitutions, the app can offer a same-category replacement only when a shop can fulfil the resulting complete basket.
6. **Delivery:** accept an order, then move its sample delivery from Assigned to Picked up to Delivered. Customer tracking follows the same state.

## Product and screen architecture

See [PRODUCT_ARCHITECTURE.md](PRODUCT_ARCHITECTURE.md) for role-specific screen hierarchy, interaction rules, domain boundaries, and the recommended next module split.

See [HACKATHON_SCORECARD.md](HACKATHON_SCORECARD.md) for evidence mapped to the judging rubric, the distinct product mechanism, sponsor/track fit boundaries, and a timed demo script.

## Verification

Run the isolated API checks against temporary SQLite databases (the sample `kirana.sqlite3` is not modified):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check static/app.js
.\.venv\Scripts\python.exe -m py_compile app.py
```

The suite covers parser quantities/units, complete-basket routing, stock shortfall, acceptance and price snapshots, opt-in inventory-grounded substitutions, wave advancement, and delivery transitions.

## API

- `GET /api/health` - readiness and parser mode
- `GET /api/state` - current shops, inventory, orders, offers, and deliveries
- `POST /api/parse` - parse text into an editable inventory/order draft
- `POST /api/shops/<shop_id>/inventory` - save only confirmed SKUs
- `POST /api/shops/<shop_id>/inventory/reset` - restore one sample shop's stock without deleting its order history
- `POST /api/orders` - create an order; substitution suggestions respect the customer's preference
- `POST /api/orders/<order_id>/substitute` - submit customer-approved substitution choices
- `POST /api/offers/<offer_id>/accept` - validate, snapshot prices, deduct stock, and close competing offers atomically
- `POST /api/offers/<offer_id>/reject` - decline a request and advance the wave if appropriate
- `POST /api/dispatch/tick` - process expired offer waves; `{ "force": true }` advances immediately
- `POST /api/deliveries/<delivery_id>/status` - advance to `picked_up` or `delivered`
- `POST /api/demo/reset` - reset all demo shops and delete demo orders/offers/deliveries (the UI asks for confirmation)

## Current limits

There is no production authentication or role enforcement, address/geospatial routing, real-time push notification, payment, cancellation/refund flow, or production database. Inventory parsing uses a small deterministic Hinglish vocabulary. Store-owner order alerts are in-app polling notifications, not browser push or SMS. Add real shop ownership, migrations, inventory audit events, reservations, idempotency, paging, integration/concurrency coverage, monitoring, and production hosting before onboarding real shops.
