"""Load menu.yaml, seed the DB, and export back to YAML (SPEC section 7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from shopbot.models import MenuItem


@dataclass
class MenuConfig:
    delivery_fee_paise: int
    delivery_fee_by_hostel: dict[str, int] = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)


def load_menu_yaml(path: str | Path) -> MenuConfig:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return MenuConfig(
        delivery_fee_paise=int(data.get("delivery_fee_paise", 1500)),
        delivery_fee_by_hostel={
            k: int(v) for k, v in (data.get("delivery_fee_by_hostel") or {}).items()
        },
        items=data.get("items", []),
    )


def seed_menu(session: Session, menu: MenuConfig) -> None:
    """Insert menu items that don't already exist (matched by name). Does not
    overwrite prices/availability the owner has already edited in the DB."""
    existing_names = {m.name for m in session.scalars(select(MenuItem))}
    for sort, item in enumerate(menu.items):
        if item["name"] in existing_names:
            continue
        session.add(
            MenuItem(
                name=item["name"],
                price_paise=round(float(item["price"]) * 100),
                aliases=item.get("aliases", []),
                category=item.get("category"),
                available=item.get("available", True),
                max_qty=item.get("max_qty", 20),
                sort=sort,
            )
        )


def export_menu_yaml(session: Session, path: str | Path, delivery_fee_paise: int) -> None:
    items = session.scalars(select(MenuItem).order_by(MenuItem.sort)).all()
    data = {
        "delivery_fee_paise": delivery_fee_paise,
        "delivery_fee_by_hostel": {},
        "items": [
            {
                "name": m.name,
                "price": m.price_paise / 100,
                "aliases": m.aliases,
                "max_qty": m.max_qty,
                "available": m.available,
            }
            for m in items
        ],
    }
    Path(path).write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
