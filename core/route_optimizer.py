"""Beam-search route generation for the local route planner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.preference import (
    STRONG_FOOD_PREFERENCES,
    candidate_has_preference,
    get_covered_strong_preferences,
    get_strong_preferences,
    matches_preference,
    route_contains_food,
)
from core.scorer import score_poi, score_route
from utils.geo import auto_travel, haversine_distance
from utils.time_utils import DAY_MINUTES, format_hhmm, minutes_between, parse_hhmm


FOOD_CATEGORIES = {"food", "cafe"}
DEFAULT_START_TIME = "09:00"
DEFAULT_END_TIME = "21:00"
DEFAULT_BUDGET = 300.0
DEFAULT_START_LOCATION = {
    "label": "春熙路",
    "lat": 30.65708,
    "lng": 104.08096,
}


@dataclass
class RouteState:
    """Internal state used by Beam Search."""

    steps: list[dict[str, Any]] = field(default_factory=list)
    visited_ids: set[str] = field(default_factory=set)
    current_lat: float = DEFAULT_START_LOCATION["lat"]
    current_lng: float = DEFAULT_START_LOCATION["lng"]
    current_time: int = 0
    total_budget: float = 0.0
    total_travel_cost: float = 0.0
    total_travel_minutes: int = 0
    total_queue_minutes: int = 0
    total_wait_minutes: int = 0
    total_stay_minutes: int = 0
    warnings: list[str] = field(default_factory=list)
    beam_score: float = 0.0


def generate_routes(
    start_location: dict[str, Any],
    candidate_pois: list[dict[str, Any]],
    intent: dict[str, Any],
    user_profile: dict[str, Any],
    top_k: int = 3,
    beam_size: int = 8,
    max_steps: int = 5,
) -> list[dict[str, Any]]:
    """Generate top route plans with Beam Search.

    Args:
        start_location: Starting point dictionary with ``lat`` and ``lng``. If
            missing, the function falls back to Spring Road / Chunxi Road.
        candidate_pois: Candidate POIs as dictionaries.
        intent: Parsed user intent containing ``start_time``, ``end_time``,
            ``budget``, ``preferences`` and ``travel_mode``.
        user_profile: User profile dictionary used by POI and route scoring.
        top_k: Number of final routes to return.
        beam_size: Maximum number of partial routes kept after each expansion.
        max_steps: Maximum POIs per route. Clamped to the requested 3-5 range.

    Returns:
        A list of route dictionaries. Each route has 3 to 5 POIs, at least one
        food/cafe POI, calculated arrival and leave times, score details and
        warnings.
    """

    if top_k <= 0 or not candidate_pois:
        return []

    intent_data = _to_dict(intent)
    profile_data = _to_dict(user_profile)
    candidates = [_to_dict(poi) for poi in candidate_pois]
    max_steps = max(3, min(5, max_steps))
    beam_size = max(1, beam_size)
    if get_strong_preferences(intent_data):
        beam_size = max(beam_size, 18)

    start = _normalize_start_location(start_location)
    start_time = str(intent_data.get("start_time") or DEFAULT_START_TIME)
    end_time = str(intent_data.get("end_time") or DEFAULT_END_TIME)
    start_minutes = parse_hhmm(start_time)
    end_minutes = start_minutes + minutes_between(start_time, end_time)
    if end_minutes <= start_minutes:
        end_minutes += DAY_MINUTES

    initial_state = RouteState(
        current_lat=_num(start.get("lat"), DEFAULT_START_LOCATION["lat"]),
        current_lng=_num(start.get("lng"), DEFAULT_START_LOCATION["lng"]),
        current_time=start_minutes,
        beam_score=0.0,
    )

    beam: list[RouteState] = [initial_state]
    complete_states: list[RouteState] = []

    for _ in range(max_steps):
        expanded_states: list[RouteState] = []
        for state in beam:
            expanded_states.extend(
                _expand_state(
                    state=state,
                    candidates=candidates,
                    intent=intent_data,
                    user_profile=profile_data,
                    end_minutes=end_minutes,
                )
            )

        if not expanded_states:
            break

        expanded_states.sort(key=lambda item: item.beam_score, reverse=True)
        beam = expanded_states[:beam_size]

        for state in beam:
            if 3 <= len(state.steps) <= max_steps and _has_food_poi(state.steps):
                complete_states.append(state)

    unique_states = _dedupe_states(complete_states)
    if not unique_states:
        return []

    final_routes = [
        _build_route(
            state=state,
            route_id=f"route_{index:03d}",
            title="候选路线",
            intent=intent_data,
            user_profile=profile_data,
            start_minutes=start_minutes,
            budget=_resolve_budget(intent_data, profile_data),
        )
        for index, state in enumerate(unique_states, start=1)
    ]
    required_preferences = _required_preferences_present_in_candidates(intent_data, candidates)
    final_routes = _enforce_strong_preference_coverage(final_routes, required_preferences)

    selected_routes = select_diverse_routes(final_routes, top_k)
    for index, route in enumerate(selected_routes, start=1):
        route["route_id"] = f"route_{index:03d}"
    return selected_routes


def optimize_route(pois: list[Any], max_pois: int = 6) -> list[Any]:
    """Backward-compatible helper that returns high-rating POIs first."""

    return sorted(pois, key=lambda poi: _num(_to_dict(poi).get("rating")), reverse=True)[:max_pois]


def _expand_state(
    state: RouteState,
    candidates: list[dict[str, Any]],
    intent: dict[str, Any],
    user_profile: dict[str, Any],
    end_minutes: int,
) -> list[RouteState]:
    expanded: list[RouteState] = []
    prefer_low_queue = "少排队" in _preferences(intent)

    for poi in candidates:
        poi_id = str(poi.get("id") or poi.get("name") or id(poi))
        if poi_id in state.visited_ids:
            continue
        if not _has_coordinates(poi):
            continue

        distance_km = haversine_distance(
            state.current_lat,
            state.current_lng,
            _num(poi.get("lat")),
            _num(poi.get("lng")),
        )
        travel = auto_travel(distance_km)
        travel_minutes = travel["minutes"]
        travel_cost = travel["cost"]
        arrival_minutes = state.current_time + travel_minutes
        queue_minutes = _estimated_queue_minutes(poi, prefer_low_queue)
        stay_minutes = max(1, int(_num(poi.get("avg_stay_minutes"), 60)))
        visit_minutes = stay_minutes + queue_minutes
        schedule = _schedule_visit(poi, arrival_minutes, visit_minutes)

        if not schedule["ok"]:
            continue
        if schedule["leave_minutes"] > end_minutes:
            continue

        step = {
            "poi": poi,
            "poi_id": poi_id,
            "name": poi.get("name", ""),
            "arrival_time": format_hhmm(arrival_minutes),
            "leave_time": format_hhmm(schedule["leave_minutes"]),
            "stay_minutes": stay_minutes,
            "travel_from_previous_minutes": travel_minutes,
            "travel_mode": travel["mode_cn"],
            "travel_cost": travel_cost,
            "estimated_queue_minutes": queue_minutes,
            "reason": _poi_reason(
                poi=poi,
                intent=intent,
                distance_km=distance_km,
                wait_minutes=schedule["wait_minutes"],
                queue_minutes=queue_minutes,
            ),
            "_arrival_minutes": arrival_minutes,
            "_visit_start_minutes": schedule["visit_start_minutes"],
            "_leave_minutes": schedule["leave_minutes"],
            "_wait_minutes": schedule["wait_minutes"],
            "_distance_from_previous_km": round(distance_km, 3),
        }

        new_steps = state.steps + [step]
        new_warnings = list(state.warnings)
        total_budget = state.total_budget + _num(poi.get("price")) + travel_cost
        total_travel_cost = state.total_travel_cost + travel_cost
        budget = _resolve_budget(intent, user_profile)
        if budget > 0 and total_budget > budget and not any("预算" in warning for warning in new_warnings):
            new_warnings.append(
                f"预计总预算{int(round(total_budget))}元，超过预算{int(round(budget))}元，已在评分中扣分。"
            )

        new_state = RouteState(
            steps=new_steps,
            visited_ids=set(state.visited_ids) | {poi_id},
            current_lat=_num(poi.get("lat")),
            current_lng=_num(poi.get("lng")),
            current_time=schedule["leave_minutes"],
            total_budget=total_budget,
            total_travel_cost=total_travel_cost,
            total_travel_minutes=state.total_travel_minutes + travel_minutes,
            total_queue_minutes=state.total_queue_minutes + queue_minutes,
            total_wait_minutes=state.total_wait_minutes + schedule["wait_minutes"],
            total_stay_minutes=state.total_stay_minutes + stay_minutes,
            warnings=new_warnings,
        )
        new_state.beam_score = _partial_beam_score(new_state, intent, user_profile)
        expanded.append(new_state)

    return expanded


def _build_route(
    state: RouteState,
    route_id: str,
    title: str,
    intent: dict[str, Any],
    user_profile: dict[str, Any],
    start_minutes: int,
    budget: float,
) -> dict[str, Any]:
    route_stops = [
        {
            "poi": step["poi"],
            "travel_minutes_from_previous": step["travel_from_previous_minutes"],
        }
        for step in state.steps
    ]
    scorer_result = score_route({"stops": route_stops}, intent, user_profile)
    route_adjustment = _route_adjustment_score(state, intent, budget)
    route_pois = [step["poi"] for step in state.steps]
    strong_preferences = get_strong_preferences(intent)
    covered_strong_preferences = get_covered_strong_preferences(route_pois, intent)
    preference_coverage_score = (
        len(covered_strong_preferences) / len(strong_preferences)
        if strong_preferences
        else 1.0
    )
    missing_food_preference = (
        any(preference in STRONG_FOOD_PREFERENCES for preference in strong_preferences)
        and not any(preference in covered_strong_preferences for preference in STRONG_FOOD_PREFERENCES)
    )
    missing_food_penalty = 0.35 if missing_food_preference else 0.0
    total_score = _clamp(
        scorer_result["score"] * 0.58
        + route_adjustment["score"] * 0.22
        + preference_coverage_score * 0.20
        - missing_food_penalty
    )
    total_duration_minutes = max(0, state.current_time - start_minutes)
    warnings = _route_warnings(state, budget)

    score_detail = {
        **scorer_result.get("score_detail", {}),
        "beam_score": round(state.beam_score, 4),
        "route_adjustment_score": round(route_adjustment["score"], 4),
        "preference_coverage_score": round(preference_coverage_score, 4),
        "covered_strong_preferences": covered_strong_preferences,
        "missing_food_preference": missing_food_preference,
        "budget_penalty": round(route_adjustment["budget_penalty"], 4),
        "queue_penalty": round(route_adjustment["queue_penalty"], 4),
        "time_efficiency_score": round(route_adjustment["time_efficiency_score"], 4),
        "indoor_adjustment_score": round(route_adjustment["indoor_adjustment_score"], 4),
        "total_wait_minutes": state.total_wait_minutes,
    }

    return {
        "route_id": route_id,
        "title": title,
        "total_score": round(total_score, 4),
        "total_budget": int(round(state.total_budget)),
        "total_travel_cost": round(state.total_travel_cost, 1),
        "total_travel_minutes": state.total_travel_minutes,
        "total_duration_minutes": total_duration_minutes,
        "pois": [_public_step(step) for step in state.steps],
        "score_detail": score_detail,
        "reason_codes": scorer_result.get("reason_codes", []),
        "warnings": warnings,
    }


def _required_preferences_present_in_candidates(
    intent: dict[str, Any],
    candidate_pois: list[dict[str, Any]],
) -> list[str]:
    return [
        preference
        for preference in get_strong_preferences(intent)
        if candidate_has_preference(candidate_pois, preference)
    ]


def _enforce_strong_preference_coverage(
    routes: list[dict[str, Any]],
    required_preferences: list[str],
) -> list[dict[str, Any]]:
    if not required_preferences:
        return routes

    covered_routes = [
        route
        for route in routes
        if all(
            preference in route.get("score_detail", {}).get("covered_strong_preferences", [])
            for preference in required_preferences
        )
    ]
    if covered_routes:
        return covered_routes

    relaxed_routes: list[dict[str, Any]] = []
    for route in routes:
        route = dict(route)
        warnings = list(route.get("warnings", []))
        covered = set(route.get("score_detail", {}).get("covered_strong_preferences", []))
        missing = [preference for preference in required_preferences if preference not in covered]
        if missing:
            route["total_score"] = round(_clamp(float(route.get("total_score", 0)) - 0.30), 4)
            warnings.append(f"候选中存在{','.join(missing)}点位，但该路线未覆盖，已在评分中大幅扣分。")
        route["warnings"] = list(dict.fromkeys(warnings))
        relaxed_routes.append(route)
    return relaxed_routes


def select_diverse_routes(routes: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    """Select high-scoring routes while limiting POI-set similarity."""

    selected: list[dict[str, Any]] = []

    objectives = [
        ("综合最优路线", lambda route: route["total_score"]),
        (
            "少排队优先路线",
            lambda route: (
                route["score_detail"].get("queue_score", 0) * 0.55
                + route["total_score"] * 0.35
                + (1 - _clamp(route["score_detail"].get("average_queue_risk", 0.5))) * 0.10
            ),
        ),
        (
            "低预算优先路线",
            lambda route: (
                route["score_detail"].get("budget_score", 0) * 0.55
                + (1 - _clamp(route["total_budget"] / max(1, route["score_detail"].get("budget", DEFAULT_BUDGET)))) * 0.25
                + route["total_score"] * 0.20
            ),
        ),
    ]

    for title, key_func in objectives[: max(0, min(top_k, len(objectives)))]:
        route = _best_diverse_route(routes, key_func, selected, max_similarity=0.7)
        if route is None:
            continue
        route = dict(route)
        route["title"] = title
        selected.append(route)

    if len(selected) < top_k:
        fallback_routes = sorted(routes, key=lambda item: item["total_score"], reverse=True)
        for route in fallback_routes:
            if any(_route_signature(route) == _route_signature(existing) for existing in selected):
                continue
            route = dict(route)
            route["title"] = f"备选路线{len(selected) + 1}"
            selected.append(route)
            if len(selected) >= top_k:
                break

    return selected[:top_k]


def _select_top_routes(routes: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    return select_diverse_routes(routes, top_k)


def _best_unused_route(
    routes: list[dict[str, Any]],
    key_func: Any,
    used_signatures: set[tuple[str, ...]],
) -> dict[str, Any] | None:
    for route in sorted(routes, key=key_func, reverse=True):
        if _route_signature(route) not in used_signatures:
            return route
    return None


def _best_diverse_route(
    routes: list[dict[str, Any]],
    key_func: Any,
    selected: list[dict[str, Any]],
    max_similarity: float,
) -> dict[str, Any] | None:
    ranked = sorted(routes, key=key_func, reverse=True)
    for route in ranked:
        signature = _route_signature(route)
        if any(signature == _route_signature(existing) for existing in selected):
            continue
        if all(_jaccard_similarity(signature, _route_signature(existing)) <= max_similarity for existing in selected):
            return route
    for route in ranked:
        signature = _route_signature(route)
        if not any(signature == _route_signature(existing) for existing in selected):
            return route
    return None


def _jaccard_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return len(left_set.intersection(right_set)) / len(left_set.union(right_set))


def _partial_beam_score(state: RouteState, intent: dict[str, Any], user_profile: dict[str, Any]) -> float:
    if not state.steps:
        return 0.0

    poi_scores = [
        score_poi(
            step["poi"],
            intent,
            user_profile,
            context={
                "travel_minutes": step["travel_from_previous_minutes"],
                "distance_from_previous_km": step["_distance_from_previous_km"],
                "route_categories": [previous["poi"].get("category") for previous in state.steps[:-1]],
            },
        )["score"]
        for step in state.steps
    ]
    avg_poi_score = sum(poi_scores) / len(poi_scores)
    queue_weight = 1.35 if "少排队" in _preferences(intent) else 1.0
    queue_penalty = _clamp((state.total_queue_minutes / max(1, len(state.steps))) / 40 * 0.28 * queue_weight)
    travel_limit = 95 if "少走路" in _preferences(intent) else 160
    travel_penalty = _clamp(state.total_travel_minutes / travel_limit * 0.22)
    food_bonus = 0.08 if _has_food_poi(state.steps) else 0.0
    length_bonus = min(0.10, len(state.steps) * 0.02)
    route_pois = [step["poi"] for step in state.steps]
    strong_preferences = get_strong_preferences(intent)
    covered = get_covered_strong_preferences(route_pois, intent)
    coverage_bonus = 0.16 * (len(covered) / len(strong_preferences)) if strong_preferences else 0.0
    missing_food_penalty = (
        0.20
        if any(preference in STRONG_FOOD_PREFERENCES for preference in strong_preferences)
        and not any(preference in covered for preference in STRONG_FOOD_PREFERENCES)
        else 0.0
    )
    return _clamp(avg_poi_score - queue_penalty - travel_penalty + food_bonus + length_bonus + coverage_bonus - missing_food_penalty)


def _route_adjustment_score(state: RouteState, intent: dict[str, Any], budget: float) -> dict[str, float]:
    preferences = _preferences(intent)
    prefer_low_queue = "少排队" in preferences
    prefer_compact = "少走路" in preferences
    prefer_indoor = "室内" in preferences
    queue_weight = 1.45 if prefer_low_queue else 1.0
    budget_penalty = 0.0
    if budget > 0 and state.total_budget > budget:
        budget_penalty = _clamp((state.total_budget - budget) / budget)

    queue_penalty = _clamp((state.total_queue_minutes / max(1, len(state.steps))) / 40 * queue_weight)
    travel_threshold = 70 if prefer_compact else 120
    time_efficiency_score = _clamp(1 - state.total_travel_minutes / travel_threshold)
    wait_score = _clamp(1 - state.total_wait_minutes / 90)
    completion_score = 1.0 if 3 <= len(state.steps) <= 5 and _has_food_poi(state.steps) else 0.4
    indoor_score = (
        sum(_feature(step["poi"], "indoor", 0.5) for step in state.steps) / len(state.steps)
        if state.steps
        else 0.5
    )

    score = _clamp(
        time_efficiency_score * (0.38 if prefer_compact else 0.30)
        + wait_score * 0.15
        + (1 - queue_penalty) * (0.32 if prefer_low_queue else 0.25)
        + (1 - budget_penalty) * 0.15
        + completion_score * 0.15
        + (indoor_score * 0.18 if prefer_indoor else 0)
    )
    return {
        "score": score,
        "budget_penalty": budget_penalty,
        "queue_penalty": queue_penalty,
        "time_efficiency_score": time_efficiency_score,
        "indoor_adjustment_score": indoor_score,
    }


def _schedule_visit(poi: dict[str, Any], arrival_minutes: int, visit_minutes: int) -> dict[str, Any]:
    open_minutes = parse_hhmm(str(poi.get("open_time", "00:00")))
    close_minutes = parse_hhmm(str(poi.get("close_time", "23:59")))

    if open_minutes == close_minutes:
        return {
            "ok": True,
            "visit_start_minutes": arrival_minutes,
            "leave_minutes": arrival_minutes + visit_minutes,
            "wait_minutes": 0,
            "reason": "全天营业",
        }

    for window_start, window_end in _candidate_business_windows(open_minutes, close_minutes, arrival_minutes):
        if arrival_minutes > window_end:
            continue
        visit_start = max(arrival_minutes, window_start)
        leave_minutes = visit_start + visit_minutes
        if leave_minutes <= window_end:
            return {
                "ok": True,
                "visit_start_minutes": visit_start,
                "leave_minutes": leave_minutes,
                "wait_minutes": max(0, visit_start - arrival_minutes),
                "reason": "营业时间内可访问",
            }
        if arrival_minutes <= window_end:
            return {
                "ok": False,
                "visit_start_minutes": visit_start,
                "leave_minutes": leave_minutes,
                "wait_minutes": max(0, visit_start - arrival_minutes),
                "reason": f"预计{format_hhmm(leave_minutes)}离开，超过闭店时间{format_hhmm(window_end)}",
            }

    return {
        "ok": False,
        "visit_start_minutes": arrival_minutes,
        "leave_minutes": arrival_minutes + visit_minutes,
        "wait_minutes": 0,
        "reason": "没有匹配到可访问的营业时间窗口",
    }


def _candidate_business_windows(
    open_minutes: int,
    close_minutes: int,
    arrival_minutes: int,
) -> list[tuple[int, int]]:
    day = arrival_minutes // DAY_MINUTES
    windows: list[tuple[int, int]] = []
    for day_offset in range(-1, 3):
        base = (day + day_offset) * DAY_MINUTES
        window_start = base + open_minutes
        window_end = base + close_minutes
        if close_minutes < open_minutes:
            window_end += DAY_MINUTES
        windows.append((window_start, window_end))
    return sorted(windows, key=lambda item: item[0])


def _estimated_queue_minutes(poi: dict[str, Any], prefer_low_queue: bool) -> int:
    queue_risk = _feature(poi, "queue_risk", 0.5)
    multiplier = 1.35 if prefer_low_queue else 1.0
    return int(round(queue_risk * 40 * multiplier))


def _poi_reason(
    poi: dict[str, Any],
    intent: dict[str, Any],
    distance_km: float,
    wait_minutes: int,
    queue_minutes: int,
) -> str:
    preferences = set(_preferences(intent))
    reasons: list[str] = []

    if "拍照" in preferences and _feature(poi, "photo", 0.5) >= 0.7:
        reasons.append("适合拍照")
    if "夜景" in preferences and _feature(poi, "night_view", 0.5) >= 0.7:
        reasons.append("夜景表现好")
    if "室内" in preferences and _feature(poi, "indoor", 0.5) >= 0.7:
        reasons.append("适合室内安排")
    if "少排队" in preferences and _feature(poi, "queue_risk", 0.5) <= 0.45:
        reasons.append("排队风险较低")
    if distance_km <= 0.8:
        reasons.append("距离上一站近")
    if _is_food_poi(poi):
        reasons.append("可补充餐饮")
    if wait_minutes > 0:
        reasons.append(f"需等待{wait_minutes}分钟开门")
    if queue_minutes > 0 and "少排队" not in preferences:
        reasons.append(f"预计排队{queue_minutes}分钟")

    return "，".join(reasons[:3]) or "综合评分较高，适合作为路线节点"


def _route_warnings(state: RouteState, budget: float) -> list[str]:
    warnings = list(dict.fromkeys(state.warnings))
    if budget > 0 and state.total_budget > budget:
        over = int(round(state.total_budget - budget))
        if not any("预算" in warning for warning in warnings):
            warnings.append(f"预算超出约{over}元，可保留但已在评分中扣分。")
    if state.total_queue_minutes >= 60:
        warnings.append(f"预计总排队时间约{state.total_queue_minutes}分钟。")
    if state.total_travel_minutes >= 90:
        warnings.append(f"预计交通时间约{state.total_travel_minutes}分钟，路线可能偏分散。")
    return list(dict.fromkeys(warnings))


def _public_step(step: dict[str, Any]) -> dict[str, Any]:
    poi = step.get("poi", {})
    price = poi.get("price", 0)
    travel_cost = step.get("travel_cost", 0)
    return {
        "poi_id": step["poi_id"],
        "name": step["name"],
        "lat": poi.get("lat"),
        "lng": poi.get("lng"),
        "category": poi.get("category", ""),
        "price": price,
        "travel_cost": travel_cost,
        "stop_cost": round(price + travel_cost, 1),
        "rating": poi.get("rating", 0),
        "arrival_time": step["arrival_time"],
        "leave_time": step["leave_time"],
        "stay_minutes": step["stay_minutes"],
        "travel_from_previous_minutes": step["travel_from_previous_minutes"],
        "travel_mode": step.get("travel_mode", "步行"),
        "estimated_queue_minutes": step["estimated_queue_minutes"],
        "reason": step["reason"],
    }


def _dedupe_states(states: list[RouteState]) -> list[RouteState]:
    best_by_signature: dict[tuple[str, ...], RouteState] = {}
    for state in states:
        signature = tuple(step["poi_id"] for step in state.steps)
        current = best_by_signature.get(signature)
        if current is None or state.beam_score > current.beam_score:
            best_by_signature[signature] = state
    return sorted(best_by_signature.values(), key=lambda item: item.beam_score, reverse=True)


def _route_signature(route: dict[str, Any]) -> tuple[str, ...]:
    return tuple(step["poi_id"] for step in route.get("pois", []))


def _normalize_start_location(start_location: dict[str, Any] | None) -> dict[str, Any]:
    start = _to_dict(start_location)
    if start.get("lat") is not None and start.get("lng") is not None:
        return start
    label = str(start.get("label") or start.get("name") or start.get("start_location") or "")
    if "春熙路" in label or not label:
        return dict(DEFAULT_START_LOCATION)
    return {**DEFAULT_START_LOCATION, "label": label}


def _has_food_poi(steps: list[dict[str, Any]]) -> bool:
    return route_contains_food([step["poi"] for step in steps])


def _is_food_poi(poi: dict[str, Any]) -> bool:
    if poi.get("category") in FOOD_CATEGORIES:
        return True
    text = _poi_text(poi)
    return any(keyword in text for keyword in ("火锅", "小吃", "咖啡", "餐饮", "food", "hotpot", "coffee"))


def _resolve_budget(intent: dict[str, Any], user_profile: dict[str, Any]) -> float:
    if intent.get("budget") is not None:
        return max(0.0, _num(intent["budget"], DEFAULT_BUDGET))
    if user_profile.get("budget_per_day") is not None:
        return max(0.0, _num(user_profile["budget_per_day"], DEFAULT_BUDGET))
    return DEFAULT_BUDGET


def _preferences(intent: dict[str, Any]) -> list[str]:
    value = intent.get("preferences") or []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _has_coordinates(poi: dict[str, Any]) -> bool:
    return poi.get("lat") is not None and poi.get("lng") is not None


def _feature(poi: dict[str, Any], name: str, default: float = 0.0) -> float:
    features = _to_dict(poi.get("features", {}))
    return _clamp(_num(features.get(name, default), default))


def _poi_text(poi: dict[str, Any]) -> str:
    tags = " ".join(str(tag) for tag in _as_list(poi.get("tags")))
    return " ".join(
        str(value)
        for value in (
            poi.get("name", ""),
            poi.get("category", ""),
            poi.get("sub_category", ""),
            poi.get("address", ""),
            tags,
        )
    )


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return dict(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    return [value]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
