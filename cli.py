"""Command-line interface for testing the route planner."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import (
    PlanRequest,
    ReplanRequest,
    list_pois,
    plan_route,
    replan,
)


INTENT_CACHE = Path(__file__).resolve().parent / ".last_intent.json"
PROFILES_FILE = Path(__file__).resolve().parent / "data" / "user_profiles.json"


def print_json(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_plan(query: str, user_id: str = "u001") -> None:
    result = plan_route(PlanRequest(user_id=user_id, query=query))
    with INTENT_CACHE.open("w", encoding="utf-8") as f:
        json.dump({"intent": result["intent"], "user_id": user_id}, f, ensure_ascii=False)
    print_json(result)


def cmd_replan(previous_intent: dict, feedback: str, user_id: str = "u001") -> None:
    result = replan(ReplanRequest(user_id=user_id, previous_intent=previous_intent, feedback=feedback))
    with INTENT_CACHE.open("w", encoding="utf-8") as f:
        json.dump({"intent": result["intent"], "user_id": user_id}, f, ensure_ascii=False)
    print_json(result)


def cmd_pois() -> None:
    print_json(list_pois())


def cmd_profiles() -> None:
    if not PROFILES_FILE.exists():
        print("错误：user_profiles.json 不存在", file=sys.stderr)
        sys.exit(1)
    with PROFILES_FILE.open(encoding="utf-8") as f:
        profiles = json.load(f)
    for p in profiles:
        print(f"  {p['id']}  {p['name']:　<8}  预算{p['budget_per_day']}元/天  偏好: {', '.join(p['preferred_tags'][:4])}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="智能路线规划系统 - 命令行工具")
    sub = parser.add_subparsers(dest="command")

    p_plan = sub.add_parser("plan", help="根据自然语言描述生成路线")
    p_plan.add_argument("query", help="用户查询，例如: 下午从春熙路出发，想吃火锅，预算300")
    p_plan.add_argument("--user", default="u001", help="用户ID (默认: u001)")

    p_replan = sub.add_parser("replan", help="根据反馈重新规划路线（自动使用上次plan的结果）")
    p_replan.add_argument("feedback", help="用户反馈，例如: 太贵了，控制在150以内")
    p_replan.add_argument("--user", default="u001", help="用户ID (默认: u001)")

    sub.add_parser("pois", help="查看POI数据概览")
    sub.add_parser("profiles", help="查看可用用户画像")

    args = parser.parse_args()

    if args.command == "plan":
        cmd_plan(args.query, args.user)
    elif args.command == "replan":
        if not INTENT_CACHE.exists():
            print("错误：没有上次的规划结果，请先运行 plan 命令。", file=sys.stderr)
            sys.exit(1)
        with INTENT_CACHE.open(encoding="utf-8") as f:
            cache = json.load(f)
        intent = cache["intent"] if "intent" in cache else cache
        user_id = cache.get("user_id", args.user)
        cmd_replan(intent, args.feedback, user_id)
    elif args.command == "pois":
        cmd_pois()
    elif args.command == "profiles":
        cmd_profiles()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
