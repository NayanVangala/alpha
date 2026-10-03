import unittest

from pager import page, page_count


class PagerTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page(list(range(25)), 1), list(range(10)))

    def test_last_page_is_short(self):
        self.assertEqual(page(list(range(25)), 3), list(range(20, 25)))

    def test_page_count(self):
        self.assertEqual(page_count(list(range(25))), 3)


if __name__ == "__main__":
    unittest.main()
