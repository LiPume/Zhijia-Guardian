import pytest

from zhijia_guardian.utils.geometry import oriented_box_margin


def test_oriented_box_margin_distinguishes_adjacent_lane_from_overlap():
    adjacent = oriented_box_margin(0, 0, 0, 0, 3.6, 0, 4.5, 1.9)
    overlapping = oriented_box_margin(0, 0, 0, 1.0, 0, 0, 4.5, 1.9)
    assert adjacent == pytest.approx(1.7)
    assert overlapping < 0


def test_oriented_box_margin_returns_longitudinal_clearance():
    margin = oriented_box_margin(0, 0, 0, 10, 0, 0, 4.5, 1.9)
    assert margin == pytest.approx(5.35)
