import unittest

from shopkit.text import slugify


class SlugifyTest(unittest.TestCase):
    def test_collapses_runs(self):
        self.assertEqual(slugify("Hello,   World!"), "hello-world")

    def test_trims_and_cuts(self):
        self.assertEqual(slugify("  A B  ", limit=3), "a-b")
