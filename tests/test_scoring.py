import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from engine.scoring import ScoringEngine


@pytest.fixture
def engine():
    return ScoringEngine()


def test_perfect(engine):
    s = engine.compute(blink_rate=15, session_minutes=10, distance_cm=65,
                       break_compliance=1.0, ambient_lux=300)
    assert s["overall_score"] >= 90
    assert s["strain_risk"] == "Low"


def test_bad(engine):
    s = engine.compute(blink_rate=3, session_minutes=120, distance_cm=25,
                       break_compliance=0.0, ambient_lux=10)
    assert s["overall_score"] < 40
    assert s["strain_risk"] == "High"


def test_clamped(engine):
    s = engine.compute(blink_rate=100, session_minutes=0, distance_cm=200,
                       break_compliance=1.0, ambient_lux=300)
    assert 0 <= s["overall_score"] <= 100


def test_fields(engine):
    s = engine.compute(15, 20, 60, 1.0, 300)
    for k in ("overall_score", "blink_score", "session_score",
              "distance_score", "break_score", "ambient_score", "strain_risk"):
        assert k in s
