"""Tests for the tool profile filter (no network, no credentials)."""

import unittest
from types import SimpleNamespace

from mcp_google.profiles import (
    PROFILE_FULL,
    PROFILE_READ_ONLY,
    PROFILE_READ_WRITE,
    ProfileError,
    resolve_profile,
)


def tool(name, read_only=False, destructive=False):
    return SimpleNamespace(
        name=name,
        annotations=SimpleNamespace(
            readOnlyHint=read_only, destructiveHint=destructive
        ),
    )


TOOLS = [
    tool("workspace_search", read_only=True),
    tool("read_sheet", read_only=True),
    tool("send_email"),
    tool("delete_email", destructive=True),
]


class ProfileTests(unittest.TestCase):
    def test_full_keeps_every_tool(self):
        profile = resolve_profile(PROFILE_FULL)
        self.assertEqual(len(profile.filter(TOOLS)), 4)

    def test_default_profile_is_full(self):
        self.assertEqual(resolve_profile(None).name, PROFILE_FULL)
        self.assertEqual(resolve_profile("").name, PROFILE_FULL)

    def test_read_only_keeps_only_read_tools(self):
        profile = resolve_profile(PROFILE_READ_ONLY)
        names = [item.name for item in profile.filter(TOOLS)]
        self.assertEqual(names, ["workspace_search", "read_sheet"])

    def test_read_write_drops_destructive_tools(self):
        profile = resolve_profile(PROFILE_READ_WRITE)
        names = [item.name for item in profile.filter(TOOLS)]
        self.assertEqual(names, ["workspace_search", "read_sheet", "send_email"])

    def test_allow_list_intersects_profile(self):
        profile = resolve_profile(PROFILE_FULL, allowed_tools=["read_sheet", "send_email"])
        names = [item.name for item in profile.filter(TOOLS)]
        self.assertEqual(names, ["read_sheet", "send_email"])

    def test_deny_list_wins_over_allow_list(self):
        profile = resolve_profile(
            PROFILE_FULL,
            allowed_tools=["read_sheet", "send_email"],
            denied_tools=["send_email"],
        )
        names = [item.name for item in profile.filter(TOOLS)]
        self.assertEqual(names, ["read_sheet"])

    def test_allowed_names_uses_tool_annotations(self):
        profile = resolve_profile(PROFILE_READ_ONLY)
        self.assertEqual(
            profile.allowed_names(TOOLS), frozenset({"workspace_search", "read_sheet"})
        )

    def test_plain_name_is_rejected_when_annotations_are_required(self):
        # A bare name carries no annotations, so read-only cannot prove it is safe.
        profile = resolve_profile(PROFILE_READ_ONLY)
        self.assertFalse(profile.allows("workspace_search"))
        self.assertFalse(profile.allows("send_email"))

    def test_unknown_profile_raises(self):
        with self.assertRaises(ProfileError):
            resolve_profile("read-sometimes")

    def test_describe_mentions_profile_and_lists(self):
        profile = resolve_profile("full", allowed_tools=["a"], denied_tools=["b"])
        described = profile.describe()
        self.assertIn("profile=full", described)
        self.assertIn("allowed=1", described)
        self.assertIn("denied=1", described)


if __name__ == "__main__":
    unittest.main()
