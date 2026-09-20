"""Conversation states (SPEC 8.2)."""

from __future__ import annotations

IDLE = "IDLE"
COLLECTING = "COLLECTING"
NEED_FULFILMENT = "NEED_FULFILMENT"
NEED_ADDRESS = "NEED_ADDRESS"
CONFIRMING = "CONFIRMING"
AWAITING_PAYMENT = "AWAITING_PAYMENT"
DONE = "DONE"

GLOBAL_COMMANDS = {"menu", "cancel", "status", "help", "repeat", "human"}

AFFIRMATIVES = {"yes", "y", "ok", "okay", "confirm", "confirmed", "haan", "hoyeche", "ha", "sure"}
NEGATIVES = {"no", "n", "cancel", "nah", "na"}

FULFILMENT_TAKEOUT = {"takeout", "take out", "pickup", "pick up", "take away", "takeaway"}
FULFILMENT_DELIVERY = {"delivery", "deliver", "hostel"}
