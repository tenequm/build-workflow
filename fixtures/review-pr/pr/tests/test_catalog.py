import unittest

from shopkit.catalog import catalog_listing, catalog_slugs


class CatalogTest(unittest.TestCase):
    def test_listing_reports_stock(self):
        entry = catalog_listing(["Blue Mug"])[0]
        self.assertEqual(entry, {"name": "Blue Mug", "slug": "blue-mug", "stock": 0})

    def test_slugs(self):
        self.assertEqual(catalog_slugs(["A B"]), ["a-b"])
