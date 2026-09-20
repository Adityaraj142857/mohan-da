import pytest

from shopbot.nlu.normalizer import normalize_text, split_segments
from shopbot.nlu.parser import MenuIndexItem, parse_order

MENU = [
    MenuIndexItem("tea", "Tea", 1000, ["chai", "cha", "tea"], 20),
    MenuIndexItem("coffee", "Coffee", 1500, ["coffee", "kofi"], 20),
    MenuIndexItem("samosa", "Samosa", 1000, ["samosa", "samosha", "singara"], 30),
    MenuIndexItem("vegroll", "Veg Roll", 4000, ["veg roll", "vegroll"], 20),
    MenuIndexItem("eggroll", "Egg Roll", 5000, ["egg roll", "eggroll", "e roll"], 20),
    MenuIndexItem("chickenroll", "Chicken Roll", 7000, ["chicken roll", "chkn roll"], 20),
    MenuIndexItem("maggi", "Maggi", 3500, ["maggi", "noodles"], 20),
    MenuIndexItem("eggmaggi", "Egg Maggi", 4500, ["egg maggi"], 20),
    MenuIndexItem("vegrice", "Veg Fried Rice", 8000, ["veg rice", "veg fried rice"], 10),
    MenuIndexItem("chickenrice", "Chicken Fried Rice", 11000, ["chicken rice", "chicken fried rice"], 10),
    MenuIndexItem("colddrink", "Cold Drink", 2000, ["coke", "pepsi", "cold drink"], 20),
]


def parse(text: str):
    norm = normalize_text(text)
    segments = split_segments(norm)
    return parse_order(norm, segments, MENU)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("2 samosa and 1 chai", [("Samosa", 2), ("Tea", 1)]),
        ("2 samosa, 1 chai", [("Samosa", 2), ("Tea", 1)]),
        ("2 samosa n 1 chai", [("Samosa", 2), ("Tea", 1)]),
        ("samosa aur chai", [("Samosa", 1), ("Tea", 1)]),
        ("samosa ar cha", [("Samosa", 1), ("Tea", 1)]),
        ("1 samosa o 1 tea", [("Samosa", 1), ("Tea", 1)]),
        ("do samosa ar ek chai", [("Samosa", 2), ("Tea", 1)]),
        ("teen chai", [("Tea", 3)]),
        ("ek egg roll", [("Egg Roll", 1)]),
        ("dui samosa", [("Samosa", 2)]),
        ("tinte chai", [("Tea", 3)]),
        ("charta samosa", [("Samosa", 4)]),
        ("paanch chai", [("Tea", 5)]),
        ("x2 samosa", [("Samosa", 2)]),
        ("2x samosa", [("Samosa", 2)]),
        ("2 pcs samosa", [("Samosa", 2)]),
        ("2 plate samosa", [("Samosa", 2)]),
        ("samosa 2", [("Samosa", 2)]),
        ("chai", [("Tea", 1)]),
        ("cha", [("Tea", 1)]),
        ("chai and samosa and egg roll", [("Tea", 1), ("Samosa", 1), ("Egg Roll", 1)]),
        ("2 chai + 1 samosa", [("Tea", 2), ("Samosa", 1)]),
        ("egg roll", [("Egg Roll", 1)]),
        ("e roll", [("Egg Roll", 1)]),
        ("2 e roll", [("Egg Roll", 2)]),
        ("veg roll", [("Veg Roll", 1)]),
        ("vegroll", [("Veg Roll", 1)]),
        ("chicken roll", [("Chicken Roll", 1)]),
        ("chkn roll", [("Chicken Roll", 1)]),
        ("maggi", [("Maggi", 1)]),
        ("noodles", [("Maggi", 1)]),
        ("egg maggi", [("Egg Maggi", 1)]),
        ("veg rice", [("Veg Fried Rice", 1)]),
        ("veg fried rice", [("Veg Fried Rice", 1)]),
        ("chicken rice", [("Chicken Fried Rice", 1)]),
        ("coke", [("Cold Drink", 1)]),
        ("pepsi", [("Cold Drink", 1)]),
        ("cold drink", [("Cold Drink", 1)]),
        ("coffee", [("Coffee", 1)]),
        ("kofi", [("Coffee", 1)]),
        ("2 samosha", [("Samosa", 2)]),  # typo, fuzzy match
        ("singara", [("Samosa", 1)]),
        ("2 samosa, 1 chai, 1 coffee", [("Samosa", 2), ("Tea", 1), ("Coffee", 1)]),
        ("1 samosa\n1 chai", [("Samosa", 1), ("Tea", 1)]),
        ("3 samosa and 2 chai and 1 coffee", [("Samosa", 3), ("Tea", 2), ("Coffee", 1)]),
        ("SAMOSA", [("Samosa", 1)]),
        ("  2   samosa  ", [("Samosa", 2)]),
        ("2 samosa 🙏", [("Samosa", 2)]),
        ("2 samosa!!", [("Samosa", 2)]),
        ("no onion samosa", [("Samosa", 1)]),
        ("extra spicy egg roll", [("Egg Roll", 1)]),
        ("1 chai without sugar", [("Tea", 1)]),
        ("2 chai and 1 samosa without onion", [("Tea", 2), ("Samosa", 1)]),
        ("panch samosa", [("Samosa", 5)]),
        ("char egg roll", [("Egg Roll", 4)]),
        ("2 chai, 1 maggi, 1 coke", [("Tea", 2), ("Maggi", 1), ("Cold Drink", 1)]),
        ("chicken fried rice", [("Chicken Fried Rice", 1)]),
        ("1 veg fried rice and 1 chicken fried rice", [("Veg Fried Rice", 1), ("Chicken Fried Rice", 1)]),
        ("2 tea", [("Tea", 2)]),
        ("tea x3", [("Tea", 3)]),
        ("3x tea", [("Tea", 3)]),
        ("one samosa", [("Samosa", 1)]),
        ("two chai", [("Tea", 2)]),
        ("three samosa", [("Samosa", 3)]),
    ],
)
def test_parser_accuracy_table(text, expected):
    result = parse(text)
    got = [(l.name, l.qty) for l in result.lines]
    assert got == expected, f"'{text}' -> {got}, expected {expected}"


def test_unknown_item_is_unresolved():
    result = parse("2 pizza")
    assert result.unresolved == ["2 pizza"] or any("pizza" in u for u in result.unresolved)
    assert not result.lines


def test_over_max_qty_flagged():
    result = parse("50 samosa")
    assert result.over_max_qty
    assert result.over_max_qty[0][0] == "Samosa"


def test_ambiguous_when_two_items_close_in_score():
    # deliberately garbled text that fuzzy-matches multiple items weakly
    result = parse("xyzroll")
    assert result.ambiguous or result.unresolved
