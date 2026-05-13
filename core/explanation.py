"""Human-readable Chinese explanations for generated routes."""

from __future__ import annotations

from typing import Any


PREFERENCE_LABELS = {
    "火锅": "想吃火锅",
    "小吃": "想吃小吃",
    "咖啡": "想喝咖啡",
    "拍照": "重视拍照出片",
    "夜景": "重视夜景",
    "少排队": "希望少排队",
    "少走路": "希望少走路、别太累",
    "室内": "需要室内或雨天友好",
}

REASON_CODE_LABELS = {
    "strong_poi_quality": "整体POI质量较高",
    "within_budget": "预算可控",
    "over_budget": "预算略有超出",
    "compact_route": "路线比较紧凑",
    "long_travel_time": "交通时间偏长",
    "low_queue_risk": "排队风险较低",
    "high_queue_risk": "排队风险偏高",
    "category_diverse": "品类较丰富",
    "contains_food": "包含餐饮补给",
    "missing_food": "餐饮补给不足",
    "matches_user_preferences": "匹配用户偏好",
    "covers_strong_preferences": "覆盖了关键偏好",
    "misses_strong_preferences": "部分关键偏好未覆盖",
    "photo_friendly_route": "适合拍照",
    "indoor_friendly_route": "适合室内安排",
    "high_quality": "品质较高",
    "matches_preferences": "匹配偏好",
    "budget_friendly": "性价比好",
    "over_budget": "预算偏高",
    "low_queue_risk": "排队少",
    "high_queue_risk": "排队较多",
    "profile_fit": "适合你的偏好",
    "photo_friendly": "适合拍照",
    "night_view_friendly": "夜景好",
    "indoor_friendly": "室内体验好",
    "neutral_match": "综合体验均衡",
}


def generate_explanation(routes: list[dict[str, Any]], intent: dict[str, Any] | Any) -> str:
    """Generate a frontend-ready Chinese explanation for route results.

    Args:
        routes: Route dictionaries returned by ``generate_routes``.
        intent: Parsed user intent dictionary.

    Returns:
        A natural Chinese explanation string covering recognized needs, route
        timelines, budget, duration, travel time, recommendation reasons, risks
        and adjustment suggestions.
    """

    intent_data = _to_dict(intent)
    lines: list[str] = []
    lines.append("已根据你的需求生成路线建议。")
    lines.append("")
    lines.append("【识别到的需求】")
    lines.append(_describe_intent(intent_data))
    lines.append("")

    if not routes:
        lines.append("当前没有生成可行路线。可能原因是营业时间、结束时间、预算或偏好约束过紧。")
        lines.append("可调整建议：放宽结束时间、提高预算、减少必选偏好，或允许更长交通时间。")
        return "\n".join(lines)

    lines.append("【路线推荐】")
    for index, route in enumerate(routes, start=1):
        lines.extend(_describe_route(index, route))
        lines.append("")

    lines.append("【可调整建议】")
    lines.extend(_adjustment_suggestions(routes, intent_data))
    return "\n".join(lines).strip()


def explain_route(plan: Any) -> str:
    """Backward-compatible wrapper for older ``RoutePlan`` style objects."""

    if isinstance(plan, dict):
        routes = [plan] if "pois" in plan else plan.get("routes", [])
        intent = plan.get("intent") or plan.get("request") or {}
        return generate_explanation(routes, intent)

    stops = getattr(plan, "stops", [])
    names = "、".join(getattr(getattr(stop, "poi", None), "name", "") for stop in stops)
    return f"本路线包含{len(stops)}个点位：{names}。"


def _describe_intent(intent: dict[str, Any]) -> str:
    preferences = [PREFERENCE_LABELS.get(item, str(item)) for item in intent.get("preferences", [])]
    avoid = intent.get("avoid", [])

    parts = [
        f"城市：{intent.get('city', '成都')}",
        f"起点：{intent.get('start_location', '春熙路')}",
        f"时间：{intent.get('start_time') or '未指定'} 至 {intent.get('end_time') or '21:00'}",
        f"预算：{intent.get('budget', 300)}元以内",
    ]

    if preferences:
        parts.append("偏好：" + "、".join(preferences))
    else:
        parts.append("偏好：未指定，优先按综合体验排序")

    if avoid:
        parts.append("避开：" + "、".join(str(item) for item in avoid))

    return "；".join(parts) + "。"


def _describe_route(index: int, route: dict[str, Any]) -> list[str]:
    title = route.get("title") or f"路线{index}"
    total_score = route.get("total_score", 0)
    total_budget = route.get("total_budget", 0)
    total_duration = route.get("total_duration_minutes", 0)
    total_travel = route.get("total_travel_minutes", 0)
    total_travel_cost = route.get("total_travel_cost", 0)
    score_detail = route.get("score_detail", {})

    emoji = ["🥇", "🥈", "🥉"]
    tag = emoji[index - 1] if index <= 3 else f"  {index}."

    lines = [
        f"{tag} {title}（综合评分 {total_score}）",
        f"   💰 预算：约{total_budget}元（含交通费{total_travel_cost}元） | ⏱ 总耗时：约{total_duration}分钟",
        "   📍 行程：",
    ]

    for i, step in enumerate(route.get("pois", []), 1):
        queue_text = ""
        queue_minutes = int(step.get("estimated_queue_minutes") or 0)
        if queue_minutes > 0:
            queue_text = f"，排队约{queue_minutes}分钟"
        travel_mode = step.get("travel_mode", "步行")
        travel_cost = step.get("travel_cost", 0)
        price = step.get("price", 0)
        travel_text = f"{travel_mode}{step.get('travel_from_previous_minutes')}分钟"
        if travel_cost > 0:
            travel_text += f"（¥{travel_cost}）"
        cost_text = f"，人均¥{price}" if price > 0 else ""
        lines.append(
            f"      {i}. {step.get('arrival_time')}→{step.get('name')} "
            f"（{travel_text}，停留{step.get('stay_minutes')}分钟{cost_text}{queue_text}）"
        )

    reasons = _route_reasons(route)
    lines.append(f"   ✅ 推荐：{reasons}")

    risk_text = _route_risks(route, score_detail)
    lines.append(f"   ⚠️ 提示：{risk_text}")
    return lines


def _route_reasons(route: dict[str, Any]) -> str:
    reason_labels = [
        REASON_CODE_LABELS.get(code, code)
        for code in route.get("reason_codes", [])
        if code not in {"over_budget", "long_travel_time", "high_queue_risk", "missing_food"}
    ]
    poi_reasons = [
        step.get("reason", "")
        for step in route.get("pois", [])
        if step.get("reason")
    ]

    combined: list[str] = []
    for item in reason_labels + poi_reasons:
        if item and item not in combined:
            combined.append(item)

    if not combined:
        return "路线在预算、距离和兴趣匹配之间较为均衡。"
    return "；".join(combined[:5]) + "。"


def _route_risks(route: dict[str, Any], score_detail: dict[str, Any]) -> str:
    risks = list(route.get("warnings", []))
    average_queue_risk = float(score_detail.get("average_queue_risk", 0))
    if average_queue_risk >= 0.6:
        risks.append("部分点位排队风险偏高，建议避开饭点或热门时段。")
    if route.get("total_travel_minutes", 0) >= 80:
        risks.append("交通时间偏长，实际体验可能会被路程拉散。")
    if not risks:
        return "暂无明显风险，按当前时间和预算约束可正常执行。"
    return " ".join(str(item) for item in risks)


def _adjustment_suggestions(routes: list[dict[str, Any]], intent: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    best_route = max(routes, key=lambda item: item.get("total_score", 0))
    preferences = set(intent.get("preferences", []))

    if any(route.get("warnings") for route in routes):
        suggestions.append("- 如果想更稳，可以提高预算或减少高客单价餐饮点。")
    if "少排队" not in preferences and _avg_queue_risk(best_route) >= 0.5:
        suggestions.append("- 如果临时不想等位，可以补充“少排队”，系统会更偏向低排队风险点位。")
    if "少走路" not in preferences and best_route.get("total_travel_minutes", 0) >= 60:
        suggestions.append("- 如果担心体力，可以补充“少走路”或缩短路线点位数量。")
    if "室内" not in preferences:
        suggestions.append("- 如果遇到下雨，可以补充“雨天”或“室内”，系统会优先选择商场、书店、茶馆等点位。")
    if not suggestions:
        suggestions.append("- 当前路线约束比较清晰，可以按综合最优路线执行；若临时变化，可反馈“便宜点”“少走路”“不想排队”等重新规划。")
    return suggestions


def _avg_queue_risk(route: dict[str, Any]) -> float:
    score_detail = route.get("score_detail", {})
    if score_detail.get("average_queue_risk") is not None:
        return float(score_detail["average_queue_risk"])
    queue_minutes = [
        int(step.get("estimated_queue_minutes") or 0)
        for step in route.get("pois", [])
    ]
    if not queue_minutes:
        return 0.0
    return min(1.0, sum(queue_minutes) / len(queue_minutes) / 40)


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
