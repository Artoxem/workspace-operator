import unittest

from workspace_operator.http_transport import weak_token_problems


class TokenStrengthTests(unittest.TestCase):
    def test_placeholder_rejected(self):
        self.assertTrue(weak_token_problems({"default": "change_me"}))
        self.assertTrue(weak_token_problems({"default": "CHANGE_ME"}))

    def test_short_rejected(self):
        self.assertTrue(weak_token_problems({"default": "abc123"}))

    def test_strong_accepted(self):
        self.assertEqual(weak_token_problems({"a": "x" * 24, "b": "Zk3" * 12}), [])


if __name__ == "__main__":
    unittest.main()
