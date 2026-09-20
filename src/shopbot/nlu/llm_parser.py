"""Optional LLM order-parser plug-in (SPEC 9.7). OFF by default
(`NLU_MODE=rules`). If enabled, it must return the same `ParseResult` shape
as `parser.parse_order`; prices are NEVER taken from the model, and any item
id not in the menu is discarded. Only a stub + interface + fake-client test
ship here — no real LLM call is wired in, so this costs nothing unless a
future owner explicitly implements `LlmClient` and flips `NLU_MODE=llm`."""

from __future__ import annotations

from typing import Protocol

from shopbot.nlu.parser import MenuIndexItem, ParseResult, parse_order


class LlmClient(Protocol):
    def parse(self, text: str, menu_names: list[str]) -> dict:
        """Return a JSON-shaped dict describing item/qty guesses. Implementations
        are responsible for calling a real LLM API; none is provided here."""
        ...


class FakeLlmClient:
    """Test double: deterministic, no network call."""

    def __init__(self, canned_response: dict | None = None):
        self.canned_response = canned_response or {"lines": []}

    def parse(self, text: str, menu_names: list[str]) -> dict:
        return self.canned_response


def parse_order_via_llm(
    text_norm: str, segments: list[str], menu_items: list[MenuIndexItem], client: LlmClient
) -> ParseResult:
    """Fallback to the rules parser: this is a stub interface only, kept
    inert until an owner wires a real client and sets NLU_MODE=llm."""
    return parse_order(text_norm, segments, menu_items)
