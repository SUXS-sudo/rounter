"""Route replanning based on short user feedback."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from core.preference import get_strong_preferences, matches_preference
from core.poi_retriever import retrieve_candidate_pois
from core.route_optimizer import generate_routes
from utils.time_utils import add_minutes, parse_hhmm


DEFAULT_START_LOCATION = {
    "label": "春熙路",
    "lat": 30.65708,
    "lng": 104.08096,
}

LOCATION_COORDS = {
    "春熙路": {"label": "春熙路", "lat": 30.65708, "lng": 104.08096},
    "太古里": {"label": "太古里", "lat": 30.65398, "lng": 104.08394},
    "宽窄巷子": {"label": "宽窄巷子", "lat": 30.66994, "lng": 104.05958},
    "九眼桥": {"label": "九眼桥", "lat": 30.64057, "lng": 104.09194},
    "大慈寺": {"label": "大慈寺", "lat": 30.65461, "lng": 104.08511},
    "安顺廊桥": {"label": "安顺廊桥", "lat": 30.64202, "lng": 104.08856},
    "望江楼公园": {"label": "望江楼公园", "lat": 30.63582, "lng": 104.09597},
}


def replan_route(
    previous_intent: dict[str, Any] | Any,
    user_feedback: str,
    user_profile: dict[str, Any] | Any,
    pois: list[dict[str, Any] | Any],
) -> dict[str, Any]:
    """Update route constraints from feedback and regenerate route candidates.

    Args:
        previous_intent: The intent used for the previous route generation.
        user_feedback: Natural-language feedback, for example ``"太贵了，少走路"``.
        user_profile: Current user profile as dict or Pydantic model.
        pois: Full POI pool as dicts or Pydantic models.

    Returns:
        A dictionary containing ``updated_intent``, regenerated ``routes``,
        ``candidate_count`` and a list of applied ``changes``. The function
        always calls ``retrieve_candidate_pois`` and ``generate_routes`` after
        applying feedback rules.
    """

    intent = _normalize_intent(previous_intent)
    profile = _to_dict(user_profile)
    poi_dicts = [_to_dict(poi) for poi in pois]
    feedback = (user_feedback or "").strip()

    changes = _apply_feedback_rules(intent, feedback)
    start_location = _resolve_start_location(intent.get("start_location"))
    available_pois = _filter_pois_by_avoid(poi_dicts, intent.get("avoid", []))
    candidates = retrieve_candidate_pois(intent, profile, available_pois, limit=24)
    routes = generate_routes(
        start_location=start_location,
        candidate_pois=candidates,
        intent=intent,
        user_profile=profile,
        top_k=3,
        beam_size=8,
        max_steps=5,
    )

    warnings: list[str] = []
    if not candidates:
        warnings.append("根据新的约束没有召回到候选POI，建议放宽偏好或预算。")
    elif not routes:
        warnings.append("已重新召回候选POI，但营业时间、预算或结束时间约束过紧，暂未生成可行路线。")
    else:
        for preference in get_strong_preferences(intent):
            candidate_has_match = any(matches_preference(poi, preference) for poi in candidates)
            route_has_match = any(
                matches_preference(_poi_by_id(poi_dicts, step.get("poi_id")), preference)
                for route in routes
                for step in route.get("pois", [])
            )
            if candidate_has_match and not route_has_match:
                warnings.append(f"候选中存在{preference}点位，但当前可行路线未覆盖，可放宽时间或减少其他偏好。")

    return {
        "updated_intent": intent,
        "routes": routes,
        "candidate_count": len(candidates),
        "changes": changes,
        "warnings": warnings,
    }


def _apply_feedback_rules(intent: dict[str, Any], feedback: str) -> list[str]:
    changes: list[str] = []

    explicit_budget = _extract_budget(feedback)
    if explicit_budget is not None:
        intent["budget"] = explicit_budget
        changes.append(f"预算已调整为{explicit_budget}元以内")
    elif _contains_any(feedback, ("太贵了", "便宜点", "便宜一点", "省钱点", "预算低点")):
        current_budget = _safe_int(intent.get("budget"), 300)
        new_budget = max(80, int(round(current_budget * 0.75)))
        intent["budget"] = new_budget
        changes.append(f"已根据“更便宜”的反馈把预算下调到约{new_budget}元")

    if _contains_any(feedback, ("少走路", "别太累", "不想太累")):
        _add_preference(intent, "少走路")
        changes.append("已加入少走路偏好")

    if _contains_any(feedback, ("下雨了", "下雨", "雨天")):
        _add_preference(intent, "室内")
        changes.append("已加入室内/雨天友好偏好")

    if "不要火锅" in feedback:
        _remove_preference(intent, "火锅")
        _add_avoid(intent, "火锅")
        changes.append("已移除火锅偏好，并加入避开火锅")

    if "换成小吃" in feedback:
        _remove_preference(intent, "火锅")
        _add_preference(intent, "小吃")
        changes.append("已将餐饮偏好从火锅调整为小吃")

    if _contains_any(feedback, ("想多拍照", "多拍照", "更出片", "多出片")):
        _add_preference(intent, "拍照")
        _add_preference(intent, "拍照")
        changes.append("已加强拍照/出片偏好")

    if _contains_any(feedback, ("不想排队", "少排队", "别排队")):
        _add_preference(intent, "少排队")
        _add_avoid(intent, "排队")
        changes.append("已加入少排队偏好")

    if "晚点出发" in feedback:
        old_time = str(intent.get("start_time") or "09:00")
        intent["start_time"] = _shift_time(old_time, 60)
        changes.append(f"开始时间已从{old_time}调整为{intent['start_time']}")

    if "早点结束" in feedback:
        old_time = str(intent.get("end_time") or "21:00")
        intent["end_time"] = _shift_time(old_time, -60)
        changes.append(f"结束时间已从{old_time}调整为{intent['end_time']}")

    if not changes:
        changes.append("未识别到明确约束变化，已基于原始意图重新规划")

    _dedupe_intent_lists(intent)
    return changes


def _extract_budget(text: str) -> int | None:
    patterns = (
        r"控制在\s*(\d{2,5})\s*(?:元|块)?\s*(?:以内|以下|内)?",
        r"(?:预算|人均)\s*(\d{2,5})",
        r"(\d{2,5})\s*(?:元|块)?\s*(?:以内|以下|内)",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return None


def _resolve_start_location(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value.get("lat") is not None and value.get("lng") is not None:
        return dict(value)

    label = str(value or DEFAULT_START_LOCATION["label"])
    for location_name, location in LOCATION_COORDS.items():
        if location_name in label:
            return dict(location)
    return dict(DEFAULT_START_LOCATION)


def _normalize_intent(previous_intent: dict[str, Any] | Any) -> dict[str, Any]:
    intent = deepcopy(_to_dict(previous_intent))
    intent.setdefault("city", "成都")
    intent.setdefault("start_location", "春熙路")
    intent.setdefault("end_location", None)
    intent.setdefault("start_time", "09:00")
    intent.setdefault("end_time", "21:00")
    intent.setdefault("budget", 300)
    intent.setdefault("preferences", [])
    intent.setdefault("avoid", [])
    intent.setdefault("travel_mode", "walking")
    intent.setdefault("people_count", 1)
    intent.setdefault("scenario", "general")
    return intent


def _add_preference(intent: dict[str, Any], preference: str) -> None:
    preferences = intent.setdefault("preferences", [])
    if not isinstance(preferences, list):
        preferences = [preferences]
        intent["preferences"] = preferences
    preferences.append(preference)


def _remove_preference(intent: dict[str, Any], preference: str) -> None:
    preferences = intent.get("preferences", [])
    if not isinstance(preferences, list):
        preferences = [preferences]
    intent["preferences"] = [item for item in preferences if item != preference]


def _add_avoid(intent: dict[str, Any], avoid_item: str) -> None:
    avoid = intent.setdefault("avoid", [])
    if not isinstance(avoid, list):
        avoid = [avoid]
        intent["avoid"] = avoid
    avoid.append(avoid_item)


def _dedupe_intent_lists(intent: dict[str, Any]) -> None:
    for key in ("preferences", "avoid"):
        values = intent.get(key, [])
        if not isinstance(values, list):
            values = [values]
        deduped: list[Any] = []
        for value in values:
            if value not in deduped:
                deduped.append(value)
        intent[key] = deduped


def _filter_pois_by_avoid(pois: list[dict[str, Any]], avoid_items: Any) -> list[dict[str, Any]]:
    if not isinstance(avoid_items, list):
        avoid_items = [avoid_items]

    hard_keywords: list[str] = []
    for item in avoid_items:
        if item == "火锅":
            hard_keywords.extend(["火锅", "hotpot", "skewer_hotpot"])

    if not hard_keywords:
        return pois

    return [poi for poi in pois if not _contains_any(_poi_text(poi), tuple(hard_keywords))]


def _poi_by_id(pois: list[dict[str, Any]], poi_id: Any) -> dict[str, Any]:
    for poi in pois:
        if str(poi.get("id")) == str(poi_id):
            return poi
    return {}


def _poi_text(poi: dict[str, Any]) -> str:
    tags = poi.get("tags") or []
    if not isinstance(tags, list):
        tags = [tags]
    return " ".join(
        str(value)
        for value in (
            poi.get("name", ""),
            poi.get("category", ""),
            poi.get("sub_category", ""),
            poi.get("address", ""),
            " ".join(str(tag) for tag in tags),
        )
    )


def _shift_time(time_value: str, minutes: int) -> str:
    try:
        parse_hhmm(time_value)
    except ValueError:
        time_value = "09:00" if minutes > 0 else "21:00"
    return add_minutes(time_value, minutes)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


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
