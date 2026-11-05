import json

from bitminer import settings as S


def test_round_trip(tmp_path):
    path = tmp_path / "flight_tuning.json"
    s = S.Settings(S.Tuning(thrust_main=410, mass=2.5), S.Display(crt=True))
    S.save(s, path)
    back = S.load(path)
    assert back.tuning.thrust_main == 410
    assert back.tuning.mass == 2.5
    assert back.display.crt is True
    assert back.display.fullscreen is False
    data = json.loads(path.read_text())
    assert list(data)[:2] == ["thrust_main", "thrust_side"]


def test_missing_or_broken_files_give_defaults(tmp_path):
    assert S.load(tmp_path / "nope.json") == S.Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert S.load(bad) == S.Settings()
    bad.write_text("[1, 2]")
    assert S.load(bad) == S.Settings()


def test_bad_values_are_ignored_or_clamped(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({"thrust_main": 99999, "mass": "heavy", "bounce": -3,
                                "damper": float("nan"), "crt": "yes", "wings": 4}))
    s = S.load(path)
    assert s.tuning.thrust_main == 700
    assert s.tuning.mass == S.Tuning().mass
    assert s.tuning.bounce == 0
    assert s.tuning.damper == S.Tuning().damper
    assert s.display.crt is False


def test_defaults_sit_inside_slider_ranges_and_on_steps():
    t = S.Tuning()
    for spec in S.SLIDERS:
        v = getattr(t, spec.key)
        assert spec.lo <= v <= spec.hi
        assert spec.snap(v) == v


def test_slider_snapping_and_text():
    spec = {s.key: s for s in S.SLIDERS}
    assert spec["thrust_main"].snap(263) == 260
    assert spec["thrust_main"].snap(5000) == 700
    assert spec["damper"].snap(0.27) == 0.25
    assert spec["damper"].text(0) == "OFF"
    assert spec["damper"].text(0.25) == "0.25"
    assert spec["mass"].text(1.0) == "1.0"
    assert spec["turn_rate"].text(300) == "300"
