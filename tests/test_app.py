"""Isolated API checks for the stock-truth ordering loop."""
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TEST_HOME = tempfile.TemporaryDirectory(prefix="unibazar-tests-", dir=ROOT / "work")
os.environ["DATABASE_PATH"] = str(Path(TEST_HOME.name) / "import.sqlite3")
import app as server  # noqa: E402


class UniBazarApiTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="case-", dir=ROOT / "work")
        server.DB = Path(self.tempdir.name) / "case.sqlite3"
        server.initialize()
        self.client = server.app.test_client()

    def tearDown(self):
        self.tempdir.cleanup()

    def state(self):
        response = self.client.get("/api/state")
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def order(self, text, **extra):
        response = self.client.post("/api/orders", json={"text": text, **extra})
        self.assertEqual(response.status_code, 201, response.get_json())
        return response.get_json()

    def offer_for(self, order_id, shop_id="asha"):
        return next(o for o in self.state()["offers"]
                    if o["order_id"] == order_id and o["shop_id"] == shop_id)

    def test_hinglish_quantity_parser_preserves_units(self):
        response = self.client.post("/api/parse", json={"text": "2 Maggi, 1 Fortune tel"})
        self.assertEqual(response.status_code, 200)
        items = {i["sku"]: i for i in response.get_json()["items"]}
        self.assertEqual((items["maggi"]["qty"], items["maggi"]["unit"]), (2, "packet"))
        self.assertEqual((items["fortune_oil"]["qty"], items["fortune_oil"]["unit"]), (1, "litre"))

    def test_complete_basket_only_notifies_fully_stocked_shop(self):
        order = self.order("2 Maggi, 1 Fortune oil")
        self.assertEqual((order["status"], order["eligible_count"]), ("offered", 1))
        offers = [o for o in self.state()["offers"] if o["order_id"] == order["order_id"]]
        self.assertEqual([o["shop_id"] for o in offers], ["asha"])

    def test_quantity_shortfall_gets_no_offer(self):
        order = self.order("21 Maggi, 1 Fortune oil")
        self.assertEqual(order["status"], "no_match")
        self.assertFalse([o for o in self.state()["offers"] if o["order_id"] == order["order_id"]])

    def test_acceptance_is_first_winner_and_snapshots_prices(self):
        order = self.order("2 Maggi, 1 Fortune oil")
        offer = self.offer_for(order["order_id"])
        result = self.client.post(f"/api/offers/{offer['id']}/accept", json={})
        self.assertEqual(result.status_code, 200, result.get_json())
        state = self.state()
        shop = next(s for s in state["shops"] if s["id"] == "asha")
        stock = {i["sku"]: i["qty"] for i in shop["inventory"]}
        self.assertEqual((stock["maggi"], stock["fortune_oil"]), (18, 4))
        accepted = next(o for o in state["orders"] if o["id"] == order["order_id"])
        self.assertTrue(accepted["accepted_at"])
        self.assertEqual({i["sku"]: i["unit_price"] for i in accepted["items"]},
                         {"fortune_oil": 150, "maggi": 14})
        self.assertEqual(len(state["deliveries"]), 1)
        duplicate = self.client.post(f"/api/offers/{offer['id']}/accept", json={})
        self.assertEqual(duplicate.status_code, 409)

    def test_substitutions_are_opt_in_and_use_real_stock(self):
        exact = self.order("1 Fortune oil, 1 Sundrop oil, 1 Maggi")
        self.assertEqual((exact["status"], exact["substitutions"]), ("no_match", []))
        opted = self.order("1 Fortune oil, 1 Sundrop oil, 1 Maggi", allow_substitutions=True)
        choice = next(s for s in opted["substitutions"] if s["shop_id"] == "ravi")
        selected = self.client.post(f"/api/orders/{opted['order_id']}/substitute", json={
            "items": [{"requested_sku": choice["requested_sku"], "sku": choice["sku"]}]
        })
        self.assertEqual(selected.status_code, 200, selected.get_json())
        sundrop = next(i for i in selected.get_json()["items"] if i["sku"] == "sundrop_oil")
        self.assertEqual(sundrop["qty"], 2)
        self.assertEqual(self.offer_for(opted["order_id"], "ravi")["status"], "pending")

    def test_expired_wave_advances_to_next_eligible_shop(self):
        with server.tx(True) as c:
            for sid in ("ravi", "meena", "imran"):
                c.execute("INSERT INTO inventory VALUES(?,?,?,?,?,?,?) ON CONFLICT(shop_id,sku) DO UPDATE SET qty=excluded.qty,price=excluded.price",
                          (sid, "fortune_oil", "Fortune oil", "oil", 3, "litre", 150))
                c.execute("INSERT INTO inventory VALUES(?,?,?,?,?,?,?) ON CONFLICT(shop_id,sku) DO UPDATE SET qty=excluded.qty,price=excluded.price",
                          (sid, "maggi", "Maggi noodles", "noodles", 3, "packet", 14))
        order = self.order("1 Maggi, 1 Fortune oil")
        offers = [o for o in self.state()["offers"] if o["order_id"] == order["order_id"]]
        self.assertEqual({o["shop_id"] for o in offers}, {"asha", "ravi", "meena"})
        advanced = self.client.post("/api/dispatch/tick", json={"force": True})
        self.assertEqual(advanced.get_json()["sent"][0]["shop_ids"], ["imran"])

    def test_concurrent_accepts_have_exactly_one_winner(self):
        order = self.order("1 Maggi")
        offers = [o for o in self.state()["offers"] if o["order_id"] == order["order_id"]]
        self.assertEqual({o["shop_id"] for o in offers}, {"asha", "ravi"})
        barrier = threading.Barrier(len(offers))

        def accept(offer_id):
            with server.app.test_client() as client:
                barrier.wait(timeout=5)
                return client.post(f"/api/offers/{offer_id}/accept", json={}).status_code

        with ThreadPoolExecutor(max_workers=len(offers)) as pool:
            results = list(pool.map(accept, [o["id"] for o in offers]))
        self.assertEqual(sorted(results), [200, 409])
        state = self.state()
        self.assertEqual(len(state["deliveries"]), 1)
        maggi_stock = sum(
            next(i["qty"] for i in shop["inventory"] if i["sku"] == "maggi")
            for shop in state["shops"] if shop["id"] in {"asha", "ravi"}
        )
        self.assertEqual(maggi_stock, 49)

    def test_delivery_requires_ordered_state_transitions(self):
        order = self.order("1 Maggi, 1 Fortune oil")
        offer = self.offer_for(order["order_id"])
        accepted = self.client.post(f"/api/offers/{offer['id']}/accept", json={}).get_json()
        did = accepted["delivery_id"]
        skipped = self.client.post(f"/api/deliveries/{did}/status", json={"status": "delivered"})
        self.assertEqual(skipped.status_code, 409)
        for status in ("picked_up", "delivered"):
            response = self.client.post(f"/api/deliveries/{did}/status", json={"status": status})
            self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.state()["orders"][0]["status"], "delivered")


if __name__ == "__main__":
    unittest.main()


