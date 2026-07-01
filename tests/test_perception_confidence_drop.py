from zhijia_guardian.tools.perception_eval import _persistent_confidence_drop


def test_confidence_drop_requires_persistence():
    values = [
        (0.0, 0.90, 1600.0, True),
        (0.5, 0.40, 1550.0, True),
        (1.0, 0.85, 1500.0, True),
    ]

    assert _persistent_confidence_drop(values, 0.35) is None


def test_confidence_drop_rejects_shrinking_or_non_key_actor():
    shrinking = [
        (0.0, 0.90, 1600.0, True),
        (0.5, 0.40, 700.0, True),
        (1.0, 0.38, 600.0, True),
    ]
    no_longer_key = [
        (0.0, 0.90, 1600.0, True),
        (0.5, 0.40, 1500.0, False),
        (1.0, 0.38, 1400.0, False),
    ]

    assert _persistent_confidence_drop(shrinking, 0.35) is None
    assert _persistent_confidence_drop(no_longer_key, 0.35) is None


def test_confidence_drop_accepts_persistent_comparable_actor():
    values = [
        (0.0, 0.90, 1600.0, True),
        (0.5, 0.82, 1580.0, True),
        (1.0, 0.42, 1500.0, True),
        (1.5, 0.40, 1450.0, True),
    ]

    assert _persistent_confidence_drop(values, 0.35) == 1.0
