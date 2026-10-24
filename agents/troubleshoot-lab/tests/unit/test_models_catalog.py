import pytest

from tl_support import (
    make_catalog,
    mission_spec,
    scenario_spec,
    write_mission,
    write_plan,
    write_scenario,
)
from troubleshoot_lab.catalog import load_catalog, parse_hints


def _errors(cat, item_id):
    return " | ".join(e.message for e in cat.errors if e.id == item_id)


def _plan_errors(cat):
    return " | ".join(e.message for e in cat.plan_errors())


def _a_then(d):
    return "a" if d > 1 else "c-one"


def test_valid_catalog_loads_with_field_from_directory(lab_root):
    cat = load_catalog(lab_root)
    assert cat.errors == []
    assert set(cat.missions) == {"m-one", "m-two", "c-one"}
    assert set(cat.scenarios) == {"d-easy", "w-easy", "d-mid"}
    assert cat.missions["c-one"].field == "network"
    assert cat.scenarios["w-easy"].field == "network"
    assert cat.hints["d-easy"][0] == "HINT-SENTINEL-d-easy-1"
    assert cat.plan is not None and cat.plan.get(1).items == ["c-one"]


@pytest.mark.parametrize(
    "patch,message",
    [
        ({"id": "Bad_Id"}, "id"),
        ({"title": "x" * 61}, "title"),
        ({"goals": []}, "goals"),
        ({"steps": []}, "steps"),
        ({"env": "aws"}, "env"),
        ({"minutes": 61}, "5–60"),
        ({"kind": "concept", "minutes": 20}, "30–90"),
        ({"field": "network"}, "does not match directory"),
    ],
)
def test_mission_field_rules(tmp_path, patch, message):
    write_mission(tmp_path, "linux", {**mission_spec("m-bad"), **patch}, dirname="m-bad")
    cat = load_catalog(tmp_path)
    assert "m-bad" not in cat.missions
    assert message in _errors(cat, "m-bad")


def test_concept_missions_may_take_up_to_90_minutes(tmp_path):
    write_mission(tmp_path, "network", mission_spec("c-long", kind="concept", minutes=90))
    assert "c-long" in load_catalog(tmp_path).missions


def test_unknown_field_directory(tmp_path):
    write_mission(tmp_path, "docker", mission_spec("m-x"))
    assert "unknown field" in _errors(load_catalog(tmp_path), "m-x")


@pytest.mark.parametrize(
    "patch,message",
    [
        ({"difficulty": "expert"}, "difficulty"),
        ({"curriculum_no": "3b"}, "curriculum_no"),
        ({"fields": []}, "fields"),
        ({"fields": ["linux", "network", "webserver", "db-cache"]}, "fields"),
        ({"warmups": []}, "warmups"),
        ({"warmups": ["missing"]}, "unknown warmup"),
        ({"warmups": ["c-one"]}, "concept mission"),
        ({"minutes": 10}, "minutes"),
        ({"interview": []}, "interview"),
        ({"interview": ["a", "b", "c"]}, "interview"),
        ({"interview": ["x" * 201]}, "1–200"),
        ({"measure": {"path": "http://evil/x", "service": "api"}}, "measure"),
        ({"measure": {"path": "/x", "service": "api", "vus": 51}}, "vus"),
        ({"measure": {"path": "/x", "service": "api", "duration_s": 41}}, "duration_s"),
        ({"env": "aws"}, "env"),
    ],
)
def test_scenario_field_rules(lab_root, patch, message):
    write_scenario(lab_root, {**scenario_spec("s-bad"), **patch}, field_dir="linux")
    cat = load_catalog(lab_root)
    assert "s-bad" not in cat.scenarios
    assert message in _errors(cat, "s-bad")
    assert "d-easy" in cat.scenarios


def test_primary_field_must_match_directory(lab_root):
    write_scenario(lab_root, scenario_spec("s-dir", fields=["network"]), field_dir="linux")
    assert "fields[0]" in _errors(load_catalog(lab_root), "s-dir")


def test_curriculum_no_unique(lab_root):
    write_scenario(lab_root, scenario_spec("s-a", no="7"))
    write_scenario(lab_root, scenario_spec("s-b", no="7"))
    cat = load_catalog(lab_root)
    assert "also used by" in _errors(cat, "s-a") + _errors(cat, "s-b")


def test_scenario_files_and_permissions(lab_root):
    d = write_scenario(lab_root, scenario_spec("s-files"), solution="  \n")
    (d / "reset.sh").unlink()
    (d / "verify.sh").chmod(0o644)
    errors = _errors(load_catalog(lab_root), "s-files")
    assert "missing reset.sh" in errors
    assert "verify.sh is not executable" in errors
    assert "solution.md is empty" in errors


def test_secret_looking_yaml_keys_rejected(lab_root):
    write_scenario(lab_root, {**scenario_spec("s-sec"), "api_key": "x"})
    assert "secret-looking" in _errors(load_catalog(lab_root), "s-sec")


def test_parse_hints_requires_three_ordered_nonempty_headings():
    text = "## 힌트 1\na\n## 힌트 2\nb\n\n## 힌트 3\nc\nmore\n"
    assert parse_hints(text) == ["a", "b", "c\nmore"]
    with pytest.raises(ValueError, match="in order"):
        parse_hints("## 힌트 1\na\n## 힌트 2\nb\n")
    with pytest.raises(ValueError, match="empty"):
        parse_hints("## 힌트 1\n\n## 힌트 2\nb\n## 힌트 3\nc")


# --- plan (data-model.md Plan) ---------------------------------------------------------


def test_missing_plan_is_a_plan_error(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("s1")], plan=False)
    cat = load_catalog(tmp_path)
    assert cat.plan is None and "missing curriculum/plan.yaml" in _plan_errors(cat)


def test_plan_needs_all_21_days_in_order(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a")])
    path = tmp_path / "curriculum" / "plan.yaml"
    path.write_text(path.read_text().replace("day: 21", "day: 20"))
    assert "1..21" in _plan_errors(load_catalog(tmp_path))


def test_plan_items_or_pool_exactly_one(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a"), scenario_spec("b")])
    write_plan(
        tmp_path, {2: {"items": ["a"], "pool": ["a", "b"]}, 3: {"items": ["b"]}}, fill=_a_then
    )
    assert "exactly one of items or pool" in _plan_errors(load_catalog(tmp_path))


def test_plan_minutes_60_to_90_with_all_warmups(tmp_path):
    # 45 min scenario + one 15 min warmup = 60 ok; 20 min scenario + 15 = 35 too short
    make_catalog(tmp_path, scenarios=[scenario_spec("ok"), scenario_spec("short", minutes=20)])
    errors = _plan_errors(load_catalog(tmp_path))
    assert "short takes 35 min" in errors and "ok takes" not in errors


def test_plan_pool_checks_every_candidate(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a"), scenario_spec("b", minutes=20)])
    write_plan(tmp_path, {7: {"pool": ["a", "b"]}}, fill=_a_then)
    assert "b takes 35 min" in _plan_errors(load_catalog(tmp_path))


def test_plan_concept_mission_rules(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a")])
    write_plan(
        tmp_path, {1: {"items": ["m-one"]}, 2: {"items": ["a", "c-one"]}}, fill=lambda d: "a"
    )
    errors = _plan_errors(load_catalog(tmp_path))
    assert "mission m-one must be a concept day's only item" in errors
    assert "mission c-one must be a concept day's only item" in errors


def test_plan_extras_and_coverage(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a"), scenario_spec("b"), scenario_spec("c")])
    write_plan(tmp_path, extras=["a", "nope"], fill=_a_then)
    errors = _plan_errors(load_catalog(tmp_path))
    assert "already in the days" in errors
    assert "unknown scenario nope" in errors
    assert "not in the plan: b, c" in errors


def test_unknown_plan_item(tmp_path):
    make_catalog(tmp_path, scenarios=[scenario_spec("a")])
    write_plan(tmp_path, {3: {"items": ["ghost"]}}, fill=_a_then)
    assert "day 3: unknown item ghost" in _plan_errors(load_catalog(tmp_path))
