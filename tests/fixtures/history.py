"""Credential-free recorder and logbook examples for Phase 3 tests."""

from typing import Any

HISTORY_PAYLOAD: list[list[dict[str, Any]]] = [
    [
        {
            "entity_id": "cover.garage_door",
            "state": "closed",
            "last_changed": "2024-08-25T11:50:00+00:00",
            "attributes": {"friendly_name": "Garage Door", "current_position": 0},
        },
        {"state": "closed", "last_changed": "2024-08-25T12:01:00+00:00"},
        {
            "state": "open",
            "last_changed": "2024-08-25T12:10:00+00:00",
            "attributes": {"current_position": 100, "access_token": "do-not-return"},
            "context": {"id": "ctx-open", "parent_id": "ctx-parent", "user_id": "private"},
        },
        {
            "state": "closed",
            "last_changed": "2024-08-25T12:15:00+00:00",
            "attributes": {"current_position": 0},
        },
    ],
    [
        {
            "entity_id": "light.kitchen_ceiling",
            "state": "off",
            "last_changed": "2024-08-25T11:55:00+00:00",
            "attributes": {"brightness": 0},
        },
        {
            "state": "on",
            "last_changed": "2024-08-25T12:20:00+00:00",
            "attributes": {"brightness": 180, "entity_picture": "https://private.example"},
        },
    ],
]

LOGBOOK_PAYLOAD: list[dict[str, Any]] = [
    {
        "when": "2024-08-25T12:10:00+00:00",
        "domain": "cover",
        "entity_id": "cover.garage_door",
        "name": "Garage Door",
        "message": "changed to open",
        "context_id": "ctx-open",
    },
    {
        "when": "2024-08-25T12:15:00+00:00",
        "domain": "cover",
        "entity_id": "cover.garage_door",
        "name": "Garage Door",
        "message": "opened https://private.example/?access_token=private",
    },
]
