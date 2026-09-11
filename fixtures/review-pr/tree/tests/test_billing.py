import unittest

from shopkit.billing import BillingError, charge_order


class ChargeOrderTest(unittest.TestCase):
    def test_charges_a_valid_order(self):
        self.assertEqual(charge_order({"items": ["x"], "total_cents": 500}), "charge:500")

    def test_rejects_an_empty_order(self):
        with self.assertRaises(BillingError):
            charge_order({"items": [], "total_cents": 500})
