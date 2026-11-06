"""Tests for calendar update/delete/invite helpers (no network)."""

import unittest

from workspace_operator.handlers.calendar_writes import build_event_patch, set_attendee_response

EVENT = {
    "summary": "Planning",
    "attendees": [
        {"email": "me@example.com", "responseStatus": "needsAction"},
        {"email": "bob@example.com", "responseStatus": "accepted"},
    ],
}


class PatchTests(unittest.TestCase):
    def test_only_provided_fields(self):
        body = build_event_patch(summary="New title")
        self.assertEqual(body, {"summary": "New title"})

    def test_times_are_wrapped(self):
        body = build_event_patch(
            start_time="2026-11-07T10:00:00+03:00",
            end_time="2026-11-07T10:30:00+03:00",
        )
        self.assertEqual(body["start"]["dateTime"], "2026-11-07T10:00:00+03:00")
        self.assertEqual(body["end"]["dateTime"], "2026-11-07T10:30:00+03:00")

    def test_attendees_are_mapped(self):
        body = build_event_patch(attendees=["a@x.io", "b@x.io"])
        self.assertEqual(body["attendees"], [{"email": "a@x.io"}, {"email": "b@x.io"}])

    def test_empty_patch(self):
        self.assertEqual(build_event_patch(), {})

    def test_empty_attendees_list_clears_guests(self):
        self.assertEqual(build_event_patch(attendees=[]), {"attendees": []})


class ResponseTests(unittest.TestCase):
    def test_sets_self_response(self):
        attendees, found = set_attendee_response(EVENT, "ME@example.com", "declined")
        self.assertTrue(found)
        self.assertEqual(attendees[0]["responseStatus"], "declined")

    def test_leaves_other_attendees(self):
        attendees, _ = set_attendee_response(EVENT, "me@example.com", "accepted")
        self.assertEqual(attendees[1]["responseStatus"], "accepted")

    def test_not_on_guest_list(self):
        attendees, found = set_attendee_response(EVENT, "stranger@example.com", "accepted")
        self.assertFalse(found)
        self.assertEqual(len(attendees), 2)

    def test_does_not_mutate_input(self):
        set_attendee_response(EVENT, "me@example.com", "declined")
        self.assertEqual(EVENT["attendees"][0]["responseStatus"], "needsAction")

    def test_event_without_attendees(self):
        attendees, found = set_attendee_response({}, "me@example.com", "accepted")
        self.assertEqual(attendees, [])
        self.assertFalse(found)


if __name__ == "__main__":
    unittest.main()
