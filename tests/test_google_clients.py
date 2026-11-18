"""The Google client cache: one client per config, isolated between configs."""

import unittest
from dataclasses import replace
from unittest import mock

from workspace_operator import google_clients
from workspace_operator.config import Config


def make_config(**overrides) -> Config:
    base = Config(
        client_secrets_file="secrets.json",
        token_file="token.json",
        backup_dir="backups",
        log_file=None,
        mcp_auth_token="token",
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    return replace(base, **overrides)


class ClientCacheTests(unittest.TestCase):
    def setUp(self):
        google_clients.reset()
        self.addCleanup(google_clients.reset)
        self.config = make_config()
        self.built = []

    def _fake_build(self, api, version, **kwargs):
        client = {"api": api, "version": version, "creds": kwargs.get("credentials")}
        self.built.append(client)
        return client

    def test_same_client_is_reused(self):
        with mock.patch.object(google_clients.discovery, "build", self._fake_build), mock.patch.object(
            google_clients.auth_module, "get_creds", return_value=mock.MagicMock(expired=False)
        ):
            first = google_clients.api_client(self.config, "drive", "v3")
            second = google_clients.api_client(self.config, "drive", "v3")
        self.assertIs(first, second)
        self.assertEqual(len(self.built), 1, "the client must be built once")

    def test_different_apis_get_different_clients(self):
        with mock.patch.object(google_clients.discovery, "build", self._fake_build), mock.patch.object(
            google_clients.auth_module, "get_creds", return_value=mock.MagicMock(expired=False)
        ):
            drive = google_clients.api_client(self.config, "drive", "v3")
            gmail = google_clients.api_client(self.config, "gmail", "v1")
        self.assertIsNot(drive, gmail)
        self.assertEqual(google_clients.cached_service_count(self.config), 2)

    def test_another_config_does_not_share_clients(self):
        other = make_config(token_file="other-token.json")
        with mock.patch.object(google_clients.discovery, "build", self._fake_build), mock.patch.object(
            google_clients.auth_module, "get_creds", return_value=mock.MagicMock(expired=False)
        ):
            a = google_clients.api_client(self.config, "drive", "v3")
            b = google_clients.api_client(other, "drive", "v3")
        self.assertIsNot(a, b)
        self.assertEqual(len(self.built), 2)

    def test_credentials_are_read_once(self):
        creds = mock.MagicMock(expired=False)
        with mock.patch.object(google_clients.auth_module, "get_creds", return_value=creds) as get_creds:
            first = google_clients.credentials(self.config)
            second = google_clients.credentials(self.config)
        self.assertIs(first, second)
        self.assertEqual(get_creds.call_count, 1)

    def test_expired_credentials_are_refreshed(self):
        expired = mock.MagicMock(expired=True, refresh_token="rt")
        with mock.patch.object(google_clients.auth_module, "get_creds", return_value=expired):
            google_clients.credentials(self.config)
        with mock.patch("google.auth.transport.requests.Request"), mock.patch.object(
            google_clients.auth_module, "get_creds", side_effect=AssertionError("must not re-read the file")
        ):
            google_clients.credentials(self.config)
        self.assertTrue(expired.refresh.called)

    def test_refresh_failure_falls_back_to_the_token_file(self):
        expired = mock.MagicMock(expired=True, refresh_token="rt")
        expired.refresh.side_effect = RuntimeError("revoked")
        fresh = mock.MagicMock(expired=False)
        with mock.patch.object(google_clients.auth_module, "get_creds", side_effect=[expired, fresh]):
            self.assertIs(google_clients.credentials(self.config), expired)
            self.assertIs(google_clients.credentials(self.config), fresh)

    def test_reset_clears_one_or_all(self):
        with mock.patch.object(google_clients.discovery, "build", self._fake_build), mock.patch.object(
            google_clients.auth_module, "get_creds", return_value=mock.MagicMock(expired=False)
        ):
            google_clients.api_client(self.config, "drive", "v3")
            google_clients.reset(self.config)
            self.assertEqual(google_clients.cached_service_count(self.config), 0)
            google_clients.api_client(self.config, "drive", "v3")
            google_clients.reset()
            self.assertEqual(google_clients.cached_service_count(self.config), 0)

    def test_cache_discovery_is_passed_through(self):
        build = mock.MagicMock(side_effect=self._fake_build)
        creds = mock.MagicMock(expired=False)
        with mock.patch.object(google_clients.discovery, "build", build), mock.patch.object(
            google_clients.auth_module, "get_creds", return_value=creds
        ):
            google_clients.api_client(self.config, "docs", "v1")
            default_flag = build.call_args.kwargs["cache_discovery"]
            google_clients.api_client(self.config, "sheets", "v4", cache_discovery=True)
            explicit_flag = build.call_args.kwargs["cache_discovery"]
        self.assertFalse(default_flag, "clients are built without disk discovery by default")
        self.assertTrue(explicit_flag)


if __name__ == "__main__":
    unittest.main()
