"""Conversation states (SPEC 8.2)."""

from __future__ import annotations

IDLE = "IDLE"
COLLECTING = "COLLECTING"
NEED_FULFILMENT = "NEED_FULFILMENT"
NEED_ADDRESS = "NEED_ADDRESS"
NEED_NOTES = "NEED_NOTES"
CONFIRMING = "CONFIRMING"
AWAITING_PAYMENT = "AWAITING_PAYMENT"
DONE = "DONE"

GLOBAL_COMMANDS = {"menu", "cancel", "status", "help", "repeat", "human"}

# Developer-only testing keyword (not a SPEC feature, not advertised to
# customers): sending this exact word lets that one conversation bypass
# OPEN_HOURS, so the app can be sanity-checked at any time of day.
DEV_BYPASS_KEYWORD = "adityaorder"

AFFIRMATIVES = {"yes", "y", "ok", "okay", "confirm", "confirmed", "haan", "hoyeche", "ha", "sure"}
NEGATIVES = {"no", "n", "cancel", "nah", "na"}

FULFILMENT_TAKEOUT = {"takeout", "take out", "pickup", "pick up", "take away", "takeaway"}
FULFILMENT_DELIVERY = {"delivery", "deliver", "hostel"}
