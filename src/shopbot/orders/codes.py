"""Human-friendly order codes, e.g. A123."""

from __future__ import annotations

import random
import string


def new_order_code(existing: set[str]) -> str:
    for _ in range(1000):
        letter = random.choice(string.ascii_uppercase)
        number = random.randint(100, 999)
        code = f"{letter}{number}"
        if code not in existing:
            return code
    raise RuntimeError("could not allocate a unique order code")
