"""FastAPI entrypoint for the local intelligent route planner."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.explanation import generate_explanation
from core.intent_parser import parse_user_intent
from core.poi_retriever import retrieve_candidate_pois
from core.replanner import replan_route
from core.route_optimizer import generate_routes
from core.ugc_analyzer import enrich_pois_with_ugc
from models.config import settings
from models.schemas import POI, Review, UserProfile


BASE_DIR = Path(__file__).resolve().parent


app = FastAPI(title=settings.app_name, version=settings.app_version)


_raw_cache: dict[str, list[dict[str, Any]]] = {}


def _get_raw_data() -> dict[str, list[dict[str, Any]]]:
    if not _raw_cache:
        _raw_cache["pois"] = load_json_list(settings.pois_file, "pois")
        _raw_cache["reviews"] = load_json_list(settings.reviews_file, "reviews")
        _raw_cache["user_profiles"] = load_json_list(settings.user_profiles_file, "user_profiles")
    return _raw_cache


START_LOCATIONS = {
    "春熙路": {"label": "春熙路", "lat": 30.65708, "lng": 104.08096},
    "太古里": {"label": "太古里", "lat": 30.65398, "lng": 104.08394},
    "宽窄巷子": {"label": "宽窄巷子", "lat": 30.66994, "lng": 104.05958},
    "九眼桥": {"label": "九眼桥", "lat": 30.64057, "lng": 104.09194},
    "大慈寺": {"label": "大慈寺", "lat": 30.65461, "lng": 104.08511},
    "安顺廊桥": {"label": "安顺廊桥", "lat": 30.64202, "lng": 104.08856},
    "望江楼公园": {"label": "望江楼公园", "lat": 30.63582, "lng": 104.09597},
}
DEFAULT_START_LOCATION = START_LOCATIONS["春熙路"]


class PlanRequest(BaseModel):
    """Request model for creating a route plan from a natural-language query."""

    user_id: str = Field(..., examples=["u001"])
    query: str = Field(
        ...,
        min_length=1,
        examples=["我周六2.下午从春熙路出发，可以步行，打车和坐地铁，0.5公里以内步行，大于1公里可以选择打车和坐地铁，，想吃火锅、拍照，不想排队，预算600，晚上9点前结束"],
    )


class ReplanRequest(BaseModel):
    """Request model for replanning from previous intent and user feedback."""

    user_id: str = Field(..., examples=["u001"])
    previous_intent: dict[str, Any]
    feedback: str = Field(..., min_length=1, examples=["从早上8.出发，想吃火锅、拍照，不想排队，预算600，晚上9点前结束"])


class LocalData(BaseModel):
    """Validated local data bundle used by the planning pipeline."""

    pois: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    user_profiles: list[dict[str, Any]]


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """Return API errors in a stable JSON envelope."""

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Catch unexpected failures and expose a concise error to clients."""

    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)},
    )


@app.get("/start")
def start() -> dict[str, str]:
    """Start check endpoint."""

    return {"status": "ok"}


@app.get("/profiles")
def list_profiles() -> list[dict[str, Any]]:
    """Return all available user profiles."""

    raw = _get_raw_data()
    return raw["user_profiles"]


@app.get("/pois")
def list_pois() -> dict[str, Any]:
    """Return city-level POI summary."""

    raw = _get_raw_data()
    raw_pois = raw["pois"]
    city_counts: dict[str, int] = {}
    for p in raw_pois:
        c = p.get("city", "未知")
        city_counts[c] = city_counts.get(c, 0) + 1
    return {"total": len(raw_pois), "cities": city_counts}


def get_enriched_pois(city: str = "") -> list[dict[str, Any]]:
    """Return the enriched POI list for testing / CLI use."""

    data = _load_city_data(city)
    return data.pois


@app.post("/plan")
def plan_route(request: PlanRequest) -> dict[str, Any]:
    """Create route plans from a user query."""

    intent = parse_user_intent(request.query)
    city = str(intent.get("city") or "").strip()

    data = _load_city_data(city)
    user_profile = get_user_profile(data.user_profiles, request.user_id)
    start_location = resolve_start_location(intent.get("start_location"))
    candidate_pois = retrieve_candidate_pois(intent, user_profile, data.pois, limit=24)
    routes = generate_routes(
        start_location=start_location,
        candidate_pois=candidate_pois,
        intent=intent,
        user_profile=user_profile,
        top_k=3,
        beam_size=8,
        max_steps=5,
    )
    explanation = generate_explanation(routes, intent)

    return {
        "intent": intent,
        "routes": routes,
        "explanation": explanation,
        "meta": {
            "user_id": request.user_id,
            "poi_count": len(data.pois),
            "review_count": len(data.reviews),
            "user_profile_count": len(data.user_profiles),
            "candidate_count": len(candidate_pois),
        },
    }


@app.post("/replan")
def replan(request: ReplanRequest) -> dict[str, Any]:
    """Regenerate route plans from prior intent and user feedback."""

    city = str(request.previous_intent.get("city") or "").strip()

    data = _load_city_data(city)
    user_profile = get_user_profile(data.user_profiles, request.user_id)
    result = replan_route(
        previous_intent=request.previous_intent,
        user_feedback=request.feedback,
        user_profile=user_profile,
        pois=data.pois,
    )
    updated_intent = result["updated_intent"]
    routes = result["routes"]
    explanation = generate_explanation(routes, updated_intent)

    return {
        "intent": updated_intent,
        "routes": routes,
        "explanation": explanation,
        "changes": result.get("changes", []),
        "warnings": result.get("warnings", []),
        "meta": {
            "user_id": request.user_id,
            "poi_count": len(data.pois),
            "review_count": len(data.reviews),
            "user_profile_count": len(data.user_profiles),
            "candidate_count": result.get("candidate_count", 0),
        },
    }


_city_cache: dict[str, LocalData] = {}


def _load_city_data(city: str) -> LocalData:
    """Load and validate POI/review data filtered by city, with caching."""

    cache_key = city or "__all__"
    if cache_key in _city_cache:
        return _city_cache[cache_key]

    raw = _get_raw_data()

    if city:
        city_pois = [p for p in raw["pois"] if p.get("city") == city]
    else:
        city_pois = raw["pois"]

    city_poi_ids = {p.get("id") for p in city_pois}
    city_reviews = [r for r in raw["reviews"] if r.get("poi_id") in city_poi_ids]

    try:
        validated_pois = [POI.model_validate(p).model_dump() for p in city_pois]
        validated_reviews = [Review.model_validate(r).model_dump() for r in city_reviews]
        enriched_pois = enrich_pois_with_ugc(validated_pois, validated_reviews)
        validated_profiles = [UserProfile.model_validate(p).model_dump() for p in raw["user_profiles"]]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Local data validation failed: {exc}") from exc

    result = LocalData(
        pois=enriched_pois,
        reviews=validated_reviews,
        user_profiles=validated_profiles,
    )
    _city_cache[cache_key] = result
    return result


def load_json_list(path: Path, display_name: str) -> list[dict[str, Any]]:
    """Load a JSON array file and return a list of dictionaries."""

    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"Local data file not found: {display_name}") from exc
    except JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Local data file is invalid JSON: {display_name}") from exc

    if not isinstance(payload, list):
        raise HTTPException(status_code=500, detail=f"Local data file must contain a JSON array: {display_name}")
    if not all(isinstance(item, dict) for item in payload):
        raise HTTPException(status_code=500, detail=f"Local data file must contain objects only: {display_name}")
    return payload


def get_user_profile(user_profiles: list[dict[str, Any]], user_id: str) -> dict[str, Any]:
    """Find a user profile by ID or return a clear 404 error."""

    for profile in user_profiles:
        if profile.get("id") == user_id:
            return profile
    raise HTTPException(status_code=404, detail=f"User profile not found: {user_id}")


def resolve_start_location(start_location: Any) -> dict[str, Any]:
    """Resolve an intent start location into coordinates."""

    if isinstance(start_location, dict) and start_location.get("lat") is not None and start_location.get("lng") is not None:
        return dict(start_location)

    label = str(start_location or DEFAULT_START_LOCATION["label"])
    for name, location in START_LOCATIONS.items():
        if name in label:
            return dict(location)
    return dict(DEFAULT_START_LOCATION)
