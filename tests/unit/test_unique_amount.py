from shopbot.payments.unique_amount import allocate_unique_paise


def test_allocates_smallest_unused():
    assert allocate_unique_paise(set(), 30) == 0
    assert allocate_unique_paise({0}, 30) == 1
    assert allocate_unique_paise({0, 1, 2}, 30) == 3


def test_returns_none_when_exhausted():
    used = set(range(31))
    assert allocate_unique_paise(used, 30) is None
