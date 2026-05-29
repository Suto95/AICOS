import unittest

from cosai_app.accounts import DEFAULT_GMAIL_QUERY_FILTER


class TestAccountsDefaults(unittest.TestCase):
    def test_default_gmail_filter(self):
        self.assertEqual(DEFAULT_GMAIL_QUERY_FILTER, "in:inbox category:primary")


if __name__ == "__main__":
    unittest.main()
