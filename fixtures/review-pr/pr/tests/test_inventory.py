import unittest

from shopkit.inventory import StockLevel, release, reserve


class InventoryTest(unittest.TestCase):
    def test_reserve_reduces_what_is_available(self):
        self.assertEqual(reserve(StockLevel("mug", on_hand=5, reserved=0), 2).available, 3)

    def test_reserve_refuses_more_than_is_available(self):
        with self.assertRaises(ValueError):
            reserve(StockLevel("mug", on_hand=1, reserved=1), 1)

    def test_release_never_goes_negative(self):
        self.assertEqual(release(StockLevel("mug", on_hand=5, reserved=1), 4).reserved, 0)
