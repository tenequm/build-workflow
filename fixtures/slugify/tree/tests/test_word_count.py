import unittest

from textkit import word_count


class WordCountTest(unittest.TestCase):
    def test_counts_words(self):
        self.assertEqual(word_count("a quick  test"), 3)

    def test_empty(self):
        self.assertEqual(word_count("   "), 0)


if __name__ == "__main__":
    unittest.main()
