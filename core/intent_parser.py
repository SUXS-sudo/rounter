"""Rule-based user intent parser for the local route planner.

The parser is intentionally lightweight and deterministic. It extracts the
small set of fields needed by the first version of the route planning pipeline
without calling an LLM or any remote service.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any


DEFAULT_CITY = "成都"
DEFAULT_START_LOCATION = "春熙路"
DEFAULT_END_TIME = "21:00"
DEFAULT_BUDGET = 300
DEFAULT_TRAVEL_MODE = "walking"
DEFAULT_PEOPLE_COUNT = 1
DEFAULT_SCENARIO = "general"

KNOWN_LOCATIONS = (
    "春熙路",
    "太古里",
    "宽窄巷子",
    "九眼桥",
    "大慈寺",
    "IFS",
    "安顺廊桥",
    "望江楼公园",
)

PREFERENCE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("火锅", ("火锅",)),
    ("小吃", ("小吃",)),
    ("咖啡", ("咖啡",)),
    ("拍照", ("拍照", "出片")),
    ("夜景", ("夜景",)),
    ("少排队", ("少排队", "不想排队", "别排队")),
    ("少走路", ("少走路", "别太累", "不想太累")),
    ("室内", ("下雨", "雨天")),
)

CHINESE_NUMBER_MAP = {
    "一": 1,
    "二": 2,
    "两": 2,
    "俩": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_user_intent(user_query: str) -> dict[str, Any]:
    """Parse a Chinese route-planning request into a normalized intent dict.

    Args:
        user_query: Natural-language user request, such as
            ``"下午想从春熙路出发吃火锅，预算300以内，晚上9点前结束"``.

    Returns:
        A dictionary containing ``city``, ``start_location``, ``end_location``,
        ``start_time``, ``end_time``, ``budget``, ``preferences``, ``avoid``,
        ``travel_mode``, ``people_count`` and ``scenario``. Missing budget and
        end time are filled with local defaults; unknown start time is returned
        as ``None``.
    """

    query = (user_query or "").strip()
    preferences = _extract_preferences(query)

    return {
        "city": DEFAULT_CITY,
        "start_location": _extract_start_location(query),
        "end_location": _extract_end_location(query),
        "start_time": _extract_start_time(query),
        "end_time": _extract_end_time(query) or DEFAULT_END_TIME,
        "budget": _extract_budget(query) or DEFAULT_BUDGET,
        "preferences": preferences,
        "avoid": _extract_avoid(preferences),
        "travel_mode": _extract_travel_mode(query),
        "people_count": _extract_people_count(query),
        "scenario": _extract_scenario(query),
    }


def parse_intent(user_query: str) -> dict[str, Any]:
    """Backward-compatible alias for callers using the earlier function name."""

    return parse_user_intent(user_query)


def _extract_preferences(query: str) -> list[str]:
    preferences: list[str] = []
    for preference, keywords in PREFERENCE_RULES:
        if _contains_any(query, keywords):
            preferences.append(preference)
    return preferences


def _extract_avoid(preferences: Iterable[str]) -> list[str]:
    avoid: list[str] = []
    preference_set = set(preferences)
    if "少排队" in preference_set:
        avoid.append("排队")
    if "少走路" in preference_set:
        avoid.append("长距离步行")
    if "室内" in preference_set:
        avoid.append("露天")
    return avoid


def _extract_budget(query: str) -> int | None:
    patterns = (
        r"(?:预算|人均)\s*(\d{2,5})",
        r"(\d{2,5})\s*(?:元|块)?\s*(?:以内|以下|内)",
    )
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            return int(match.group(1))
    return None


def _extract_start_time(query: str) -> str | None:
    if "下午" in query:
        return "14:00"
    if "上午" in query:
        return "09:00"
    return None


def _extract_end_time(query: str) -> str | None:
    colon_time_match = re.search(r"([01]?\d|2[0-3])[:：]([0-5]\d)\s*前", query)
    if colon_time_match:
        hour = int(colon_time_match.group(1))
        minute = int(colon_time_match.group(2))
        return f"{hour:02d}:{minute:02d}"

    point_time_match = re.search(r"(晚上|夜里|晚间)?\s*(\d{1,2})\s*点\s*前", query)
    if point_time_match:
        evening_hint = point_time_match.group(1)
        hour = int(point_time_match.group(2))
        if evening_hint and 1 <= hour <= 11:
            hour += 12
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"

    return None


def _extract_start_location(query: str) -> str:
    for location in KNOWN_LOCATIONS:
        patterns = (
            rf"从\s*{re.escape(location)}",
            rf"{re.escape(location)}\s*出发",
            rf"起点\s*(?:是|为|在)?\s*{re.escape(location)}",
        )
        if any(re.search(pattern, query) for pattern in patterns):
            return location
    return DEFAULT_START_LOCATION


def _extract_end_location(query: str) -> str | None:
    for location in KNOWN_LOCATIONS:
        patterns = (
            rf"到\s*{re.escape(location)}",
            rf"去\s*{re.escape(location)}",
            rf"终点\s*(?:是|为|在)?\s*{re.escape(location)}",
        )
        if any(re.search(pattern, query) for pattern in patterns):
            return location
    return None


def _extract_travel_mode(query: str) -> str:
    if _contains_any(query, ("打车", "出租车", "网约车")):
        return "taxi"
    if "地铁" in query:
        return "subway"
    if _contains_any(query, ("骑行", "骑车", "单车")):
        return "bike"
    if _contains_any(query, ("步行", "走路")):
        return "walking"
    return DEFAULT_TRAVEL_MODE


def _extract_people_count(query: str) -> int:
    if "一家三口" in query:
        return 3

    digit_match = re.search(r"(\d{1,2})\s*(?:个)?(?:人|位)", query)
    if digit_match:
        return max(1, int(digit_match.group(1)))

    chinese_match = re.search(r"([一二两俩三四五六七八九十])\s*(?:个)?(?:人|位)", query)
    if chinese_match:
        return CHINESE_NUMBER_MAP[chinese_match.group(1)]

    if _contains_any(query, ("情侣", "约会")):
        return 2
    if _contains_any(query, ("亲子", "带娃", "孩子", "家庭")):
        return 3

    return DEFAULT_PEOPLE_COUNT


def _extract_scenario(query: str) -> str:
    if _contains_any(query, ("亲子", "带娃", "孩子", "家庭", "一家")):
        return "family"
    if _contains_any(query, ("情侣", "约会")):
        return "date"
    if _contains_any(query, ("朋友", "同事", "团建", "聚餐")):
        return "friends"
    if _contains_any(query, ("一个人", "独自", "solo")):
        return "solo"
    if _contains_any(query, ("下雨", "雨天")):
        return "rainy_day"
    return DEFAULT_SCENARIO


def _contains_any(text: str, keywords: Iterable[str]) -> bool:
    return any(keyword in text for keyword in keywords)
