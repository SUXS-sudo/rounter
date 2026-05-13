"""Candidate POI retrieval for the local route planner."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from models.config import settings
from models.schemas import POI


DEFAULT_CITY = "成都"

PREFERENCE_KEYWORDS = {
    "火锅": ("火锅", "hotpot", "skewer_hotpot"),
    "小吃": ("小吃", "snack", "street_food", "food_street", "chengdu_snack"),
    "咖啡": ("咖啡", "coffee", "cafe"),
    "拍照": ("拍照", "出片", "打卡", "地标", "建筑", "landmark"),
    "夜景": ("夜景", "夜游", "夜生活", "night"),
    "室内": ("室内", "雨天友好", "商场", "影院", "书店", "indoor", "mall", "cinema", "bookstore"),
    "少排队": ("少排队", "不排队", "不用排队"),
}


def load_pois(path: Path = settings.pois_file) -> list[POI]:
    """Load POIs from JSON and validate them with the local schema."""

    with path.open("r", encoding="utf-8") as file:
        return [POI.model_validate(item) for item in json.load(file)]


def find_by_tags(tags: list[str]) -> list[POI]:
    """Find POIs that contain any of the requested tags."""

    wanted = set(tags)
    return [poi for poi in load_pois() if wanted.intersection(poi.tags)]


def retrieve_candidate_pois(
    intent: dict[str, Any],
    user_profile: dict[str, Any] | Any | None,
    pois: list[dict[str, Any] | Any],
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Retrieve relevant, diverse POI candidates for an intent.

    Args:
        intent: Parsed user intent. Expected keys include ``city``, ``budget``
            and ``preferences``.
        user_profile: Optional user profile as a dict or Pydantic model.
        pois: POI records as dicts or Pydantic models.
        limit: Maximum number of candidates to return.

    Returns:
        Up to ``limit`` POI dictionaries, filtered by city, ranked by preference
        match, budget fit, quality and user profile affinity, then diversified
        by category.
    """

    if limit <= 0:
        return []

    intent_data = _to_dict(intent)
    profile_data = _to_dict(user_profile) if user_profile is not None else {}
    city = str(intent_data.get("city") or DEFAULT_CITY)
    budget = _resolve_budget(intent_data, profile_data)
    preferences = [str(item) for item in intent_data.get("preferences", [])]

    city_matched_pois = [
        _to_dict(poi)
        for poi in pois
        if not city or str(_to_dict(poi).get("city") or city) == city
    ]

    scored_candidates: list[tuple[float, dict[str, Any]]] = []
    for poi in city_matched_pois:
        preference_score = _preference_match_score(poi, preferences)
        if preferences and preference_score <= 0 and not _profile_matches_poi(poi, profile_data):
            continue

        score = _candidate_score(poi, preferences, budget, profile_data)
        scored_candidates.append((score, poi))

    if not scored_candidates and preferences:
        scored_candidates = [
            (_candidate_score(poi, [], budget, profile_data), poi)
            for poi in city_matched_pois
        ]

    ranked = [poi for _, poi in sorted(scored_candidates, key=lambda item: item[0], reverse=True)]
    diversified = _diversify_by_category(ranked, limit)
    return _ensure_food_pois(diversified, ranked, limit)


def _candidate_score(
    poi: dict[str, Any],
    preferences: list[str],
    budget: int | float,
    user_profile: dict[str, Any],
) -> float:
    quality_score = _clamp(_num(poi.get("rating")) / 5)
    preference_score = _preference_match_score(poi, preferences) if preferences else 0.55
    budget_score = _budget_fit_score(_num(poi.get("price")), budget)
    queue_score = 1 - _feature(poi, "queue_risk", 0.5)
    personalization_score = _profile_affinity_score(poi, user_profile)

    weights = {
        "quality": 0.25,
        "preference": 0.38,
        "budget": 0.16,
        "queue": 0.08,
        "personalization": 0.13,
    }

    if budget <= 200:
        weights["budget"] += 0.12
        weights["preference"] -= 0.06
        weights["quality"] -= 0.03
        weights["personalization"] -= 0.03
    elif budget <= 300:
        weights["budget"] += 0.06
        weights["preference"] -= 0.03
        weights["quality"] -= 0.03

    if "少排队" in preferences:
        weights["queue"] += 0.12
        weights["preference"] += 0.04
        weights["quality"] -= 0.06
        weights["personalization"] -= 0.10

    weights = _normalize_weights(weights)
    return (
        quality_score * weights["quality"]
        + preference_score * weights["preference"]
        + budget_score * weights["budget"]
        + queue_score * weights["queue"]
        + personalization_score * weights["personalization"]
    )


def _preference_match_score(poi: dict[str, Any], preferences: list[str]) -> float:
    if not preferences:
        return 0.5

    scores = [_single_preference_score(poi, preference) for preference in preferences]
    return _clamp(sum(scores) / len(scores))


def _single_preference_score(poi: dict[str, Any], preference: str) -> float:
    feature_scores = {
        "火锅": max(_keyword_score(poi, "火锅"), _keyword_score(poi, "hotpot"), _feature(poi, "taste", 0.5) * 0.8),
        "小吃": max(_keyword_score(poi, "小吃"), _keyword_score(poi, "snack"), _feature(poi, "taste", 0.5) * 0.75),
        "咖啡": max(_keyword_score(poi, "咖啡"), _keyword_score(poi, "coffee"), 0.85 if poi.get("category") == "cafe" else 0),
        "拍照": max(_feature(poi, "photo", 0.5), _keyword_score(poi, "拍照"), _keyword_score(poi, "出片")),
        "夜景": max(_feature(poi, "night_view", 0.5), _keyword_score(poi, "夜景"), _keyword_score(poi, "夜游")),
        "室内": max(_feature(poi, "indoor", 0.5), _keyword_score(poi, "室内"), _keyword_score(poi, "雨天友好")),
        "少排队": 1 - _feature(poi, "queue_risk", 0.5),
        "少走路": 0.65,
    }

    if preference in feature_scores:
        return _clamp(feature_scores[preference])

    keywords = PREFERENCE_KEYWORDS.get(preference, (preference,))
    return max((_keyword_score(poi, keyword) for keyword in keywords), default=0.0)


def _profile_affinity_score(poi: dict[str, Any], user_profile: dict[str, Any]) -> float:
    if not user_profile:
        return 0.5

    score = 0.5
    tags = set(_as_list(poi.get("tags")))
    preferred_tags = set(_as_list(user_profile.get("preferred_tags")))
    disliked_tags = set(_as_list(user_profile.get("disliked_tags")))
    favorite_categories = set(_as_list(user_profile.get("favorite_categories")))

    score += min(0.24, 0.06 * len(tags.intersection(preferred_tags)))
    score -= min(0.30, 0.10 * len(tags.intersection(disliked_tags)))

    if poi.get("category") in favorite_categories:
        score += 0.12

    feature_weights = _to_dict(user_profile.get("feature_weights", {}))
    if feature_weights:
        weighted_total = 0.0
        weight_sum = 0.0
        for feature_name, weight in feature_weights.items():
            numeric_weight = _num(weight)
            weighted_total += _feature(poi, feature_name, 0.5) * numeric_weight
            weight_sum += numeric_weight
        if weight_sum > 0:
            score = score * 0.65 + (weighted_total / weight_sum) * 0.35

    return _clamp(score)


def _profile_matches_poi(poi: dict[str, Any], user_profile: dict[str, Any]) -> bool:
    if not user_profile:
        return False

    tags = set(_as_list(poi.get("tags")))
    preferred_tags = set(_as_list(user_profile.get("preferred_tags")))
    favorite_categories = set(_as_list(user_profile.get("favorite_categories")))
    return bool(tags.intersection(preferred_tags) or poi.get("category") in favorite_categories)


def _diversify_by_category(ranked_pois: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if not ranked_pois:
        return []

    categories = {str(poi.get("category") or "unknown") for poi in ranked_pois}
    soft_cap = max(2, limit // max(1, min(4, len(categories))))
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    category_counts: Counter[str] = Counter()

    for poi in ranked_pois:
        category = str(poi.get("category") or "unknown")
        poi_id = str(poi.get("id") or id(poi))
        if category_counts[category] >= soft_cap:
            continue
        selected.append(poi)
        selected_ids.add(poi_id)
        category_counts[category] += 1
        if len(selected) >= limit:
            return selected

    for poi in ranked_pois:
        poi_id = str(poi.get("id") or id(poi))
        if poi_id in selected_ids:
            continue
        selected.append(poi)
        selected_ids.add(poi_id)
        if len(selected) >= limit:
            break

    return selected


FOOD_CATEGORIES = {"food", "cafe"}


def _ensure_food_pois(
    diversified: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    """Guarantee at least a few food/cafe POIs in the candidate pool."""

    min_food = max(2, limit // 8)
    existing_food = [poi for poi in diversified if str(poi.get("category")) in FOOD_CATEGORIES]
    if len(existing_food) >= min_food:
        return diversified

    diversified_ids = {str(poi.get("id")) for poi in diversified}
    missing = min_food - len(existing_food)
    for poi in ranked:
        if missing <= 0:
            break
        poi_id = str(poi.get("id"))
        if poi_id in diversified_ids:
            continue
        if str(poi.get("category")) in FOOD_CATEGORIES:
            diversified.append(poi)
            diversified_ids.add(poi_id)
            missing -= 1

    return diversified


def _resolve_budget(intent: dict[str, Any], user_profile: dict[str, Any]) -> float:
    if intent.get("budget") is not None:
        return max(0, _num(intent["budget"]))
    if user_profile.get("budget_per_day") is not None:
        return max(0, _num(user_profile["budget_per_day"]))
    return 300.0


def _budget_fit_score(price: float, budget: float) -> float:
    if budget <= 0:
        return 0.5
    if price <= budget:
        return _clamp(1 - (price / budget) * 0.35)
    return _clamp((budget / max(price, 1)) * 0.6)


def _keyword_score(poi: dict[str, Any], keyword: str) -> float:
    text = _poi_text(poi).lower()
    keyword_lower = keyword.lower()
    if keyword_lower in text:
        return 1.0
    for mapped_keyword in PREFERENCE_KEYWORDS.get(keyword, ()):
        if mapped_keyword.lower() in text:
            return 1.0
    return 0.0


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


def _feature(poi: dict[str, Any], name: str, default: float = 0.0) -> float:
    features = _to_dict(poi.get("features", {}))
    return _clamp(_num(features.get(name, default)))


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


def _normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    cleaned = {key: max(0.02, value) for key, value in weights.items()}
    total = sum(cleaned.values())
    if total <= 0:
        return {key: 1 / len(weights) for key in weights}
    return {key: value / total for key, value in cleaned.items()}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
