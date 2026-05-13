from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import PlanRequest, ReplanRequest, get_enriched_pois, plan_route, replan


def _poi_by_id() -> dict[str, dict]:
    return {poi["id"]: poi for poi in get_enriched_pois()}


def _route_ids(route: dict) -> list[str]:
    return [step["poi_id"] for step in route["pois"]]


def _poi_text(poi: dict) -> str:
    return " ".join(
        str(value)
        for value in (
            poi.get("name", ""),
            poi.get("category", ""),
            poi.get("sub_category", ""),
            " ".join(str(tag) for tag in poi.get("tags", [])),
        )
    ).lower()


def _route_has_hotpot(route: dict, pois: dict[str, dict]) -> bool:
    return any(
        "hotpot" in _poi_text(pois[poi_id]) or "火锅" in _poi_text(pois[poi_id])
        for poi_id in _route_ids(route)
    )


def _route_has_snack(route: dict, pois: dict[str, dict]) -> bool:
    return any(
        "snack" in _poi_text(pois[poi_id]) or "小吃" in _poi_text(pois[poi_id])
        for poi_id in _route_ids(route)
    )


def _avg_feature(route: dict, pois: dict[str, dict], feature: str) -> float:
    values = [pois[poi_id]["features"][feature] for poi_id in _route_ids(route)]
    return sum(values) / len(values)


def _plan(query: str) -> dict:
    return plan_route(PlanRequest(user_id="u001", query=query))


def test_hotpot_preference_route_contains_hotpot() -> None:
    pois = _poi_by_id()
    result = _plan("我周六下午从春熙路出发，想吃火锅、拍照，不想排队，预算300，晚上9点前结束")

    assert "火锅" in result["intent"]["preferences"]
    assert result["routes"]
    assert _route_has_hotpot(result["routes"][0], pois)


def test_replan_no_hotpot_switch_to_snack() -> None:
    pois = _poi_by_id()
    original = _plan("下午从春熙路出发，想吃火锅、拍照，不想排队，预算300，晚上9点前结束")
    result = replan(
        ReplanRequest(
            user_id="u001",
            previous_intent=original["intent"],
            feedback="不要火锅了，换成小吃",
        )
    )

    assert "火锅" not in result["intent"]["preferences"]
    assert "火锅" in result["intent"]["avoid"]
    assert "小吃" in result["intent"]["preferences"]
    assert result["routes"]
    assert not any(_route_has_hotpot(route, pois) for route in result["routes"])
    assert any(_route_has_snack(route, pois) for route in result["routes"]) or result["warnings"]


def test_rainy_indoor_route_has_higher_indoor_score() -> None:
    pois = _poi_by_id()
    rainy = _plan("今天下雨，我想下午在春熙路附近玩，不想排队，预算300，尽量安排室内")
    normal = _plan("今天下午在春熙路附近玩，不想排队，预算300")

    assert "室内" in rainy["intent"]["preferences"]
    assert _avg_feature(rainy["routes"][0], pois, "indoor") > _avg_feature(normal["routes"][0], pois, "indoor")


def test_low_walk_route_is_more_compact_than_general_food_route() -> None:
    compact = _plan("下午从春熙路出发，想吃点好吃的，少走路，别太累，预算300")
    normal = _plan("下午从春熙路出发，想吃点好吃的，预算300")

    assert "少走路" in compact["intent"]["preferences"]
    compact_detail = compact["routes"][0]["score_detail"]
    normal_detail = normal["routes"][0]["score_detail"]
    assert (
        compact["routes"][0]["total_travel_minutes"] <= normal["routes"][0]["total_travel_minutes"]
        or compact_detail["compact_score"] >= normal_detail["compact_score"]
    )


def test_reviews_are_enriched_into_pois() -> None:
    pois = get_enriched_pois()

    assert pois
    assert all("ugc_summary" in poi for poi in pois)
    assert any(poi["ugc_summary"] for poi in pois)


def test_diverse_routes_are_not_identical() -> None:
    result = _plan("下午从春熙路出发，想喝咖啡拍照，预算300")
    route_sets = [tuple(_route_ids(route)) for route in result["routes"]]

    assert len(route_sets) >= 3
    assert len(set(route_sets)) == len(route_sets)


def test_low_budget_replan_reduces_budget_or_warns() -> None:
    original = _plan("下午从春熙路出发，想吃火锅、拍照，预算300，晚上9点前结束")
    replanned = replan(
        ReplanRequest(
            user_id="u001",
            previous_intent=original["intent"],
            feedback="太贵了，控制在150以内",
        )
    )

    assert replanned["intent"]["budget"] == 150
    assert (
        replanned["routes"][0]["total_budget"] <= original["routes"][0]["total_budget"]
        or replanned["routes"][0]["warnings"]
        or replanned["warnings"]
    )
