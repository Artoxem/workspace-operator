"""Tests for the HTTP transport's security decisions (no server started)."""

import unittest
from types import SimpleNamespace

from workspace_operator.http_transport import (
    HttpOptions,
    _security_settings,
    authenticate,
    build_tokens,
    resolve_bind,
)


class BindTests(unittest.TestCase):
    def test_loopback_is_allowed_by_default(self):
        for host in ("127.0.0.1", "localhost", "::1"):
            with self.subTest(host=host):
                allowed, reason = resolve_bind(host, allow_network=False, insecure=False)
                self.assertTrue(allowed)
                self.assertIsNone(reason)

    def test_network_requires_flag(self):
        allowed, reason = resolve_bind("0.0.0.0", allow_network=False, insecure=False)
        self.assertFalse(allowed)
        self.assertIn("--allow-network", reason)

    def test_network_requires_insecure_acknowledgement(self):
        allowed, reason = resolve_bind("0.0.0.0", allow_network=True, insecure=False)
        self.assertFalse(allowed)
        self.assertIn("--insecure", reason)

    def test_network_with_both_flags(self):
        allowed, _ = resolve_bind("192.168.1.10", allow_network=True, insecure=True)
        self.assertTrue(allowed)


class AuthTests(unittest.TestCase):
    TOKENS = {"laptop": "secret-one", "ci": "secret-two"}

    def test_valid_token_returns_client_name(self):
        self.assertEqual(authenticate("Bearer secret-one", self.TOKENS), "laptop")
        self.assertEqual(authenticate("bearer secret-two", self.TOKENS), "ci")

    def test_wrong_token(self):
        self.assertIsNone(authenticate("Bearer nope", self.TOKENS))

    def test_wrong_scheme(self):
        self.assertIsNone(authenticate("Basic secret-one", self.TOKENS))

    def test_missing_header(self):
        self.assertIsNone(authenticate(None, self.TOKENS))
        self.assertIsNone(authenticate("", self.TOKENS))

    def test_no_tokens_configured(self):
        self.assertIsNone(authenticate("Bearer anything", {}))


class TokenMapTests(unittest.TestCase):
    def test_explicit_map(self):
        config = SimpleNamespace(http_tokens={"a": "1", "b": "2"}, mcp_auth_token="x")
        self.assertEqual(build_tokens(config), {"a": "1", "b": "2"})

    def test_falls_back_to_activation_token(self):
        config = SimpleNamespace(http_tokens=None, mcp_auth_token="solo")
        self.assertEqual(build_tokens(config), {"default": "solo"})

    def test_nothing_configured(self):
        config = SimpleNamespace(http_tokens=None, mcp_auth_token=None)
        self.assertEqual(build_tokens(config), {})


class SecuritySettingsTests(unittest.TestCase):
    def test_hosts_include_bind_address_and_localhost(self):
        settings = _security_settings("127.0.0.1", 8765)
        self.assertTrue(settings.enable_dns_rebinding_protection)
        self.assertIn("127.0.0.1:8765", settings.allowed_hosts)
        self.assertIn("localhost:8765", settings.allowed_hosts)
        self.assertEqual(settings.allowed_origins, [])

    def test_loopback_accepts_any_port(self):
        """A container published on another host port must still pass the check."""
        settings = _security_settings("0.0.0.0", 8765)
        self.assertIn("127.0.0.1:*", settings.allowed_hosts)
        self.assertIn("localhost:*", settings.allowed_hosts)
        self.assertIn("[::1]:*", settings.allowed_hosts)

    def test_extra_hosts_are_appended_once(self):
        settings = _security_settings(
            "127.0.0.1", 8765, ["mcp.example.com", "mcp.example.com"]
        )
        self.assertIn("mcp.example.com", settings.allowed_hosts)
        self.assertEqual(settings.allowed_hosts.count("mcp.example.com"), 1)


class OptionsTests(unittest.TestCase):
    def test_defaults_are_local(self):
        options = HttpOptions()
        self.assertEqual(options.host, "127.0.0.1")
        self.assertFalse(options.allow_network)
        self.assertFalse(options.insecure)
        self.assertEqual(options.extra_hosts, [])

    def test_cli_accepts_allow_host(self):
        from workspace_operator.cli import build_parser

        args = build_parser().parse_args(
            ["serve", "--http", "--allow-host", "a.example:443", "--allow-host", "b"]
        )
        self.assertEqual(args.allow_host, ["a.example:443", "b"])


if __name__ == "__main__":
    unittest.main()
