"""Merchant-owned compatibility, growth controls and bounded descriptive analytics."""
import time
from collections import Counter
from itertools import combinations
from datetime import datetime, timezone
import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.commerce import CommercePolicy, ShoppingCart
from app.models.commerce_workflows import CommerceRules
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.commerce import ShoppingIntent
from app.schemas.commerce_workflows import RulesRequest
from app.services.commerce import carts, learning
from app.services.commerce.catalog import catalog, rank, co_purchases, local_intent


async def rules_for(session: AsyncSession, merchant_id: int) -> CommerceRules:
    record = await session.get(CommerceRules, merchant_id)
    return record or CommerceRules(merchant_id=merchant_id, compatibility=[], growth_rules=[],
        scheduler_enabled=False, interval_seconds=300, next_run_at=0, last_result={})


def active_rule(rule: dict, timestamp: int | None = None) -> bool:
    now = int(time.time()) if timestamp is None else timestamp
    if not rule.get("enabled"):
        return False
    if (rule.get("starts_at") is not None and now < rule["starts_at"]) or (rule.get("ends_at") is not None and now >= rule["ends_at"]):
        return False
    month = datetime.fromtimestamp(now, timezone.utc).month
    season = "summer" if month in (3, 4, 5) else "monsoon" if month in (6, 7, 8, 9) else "winter" if month in (12, 1, 2) else "transition"
    return not rule.get("season") or rule["season"] == season


async def save_rules(session: AsyncSession, merchant_id: int, body: RulesRequest) -> CommerceRules:
    record = await session.get(CommerceRules, merchant_id, with_for_update=True)
    if record is None:
        record = await rules_for(session, merchant_id)
        session.add(record)
    for key, value in body.model_dump().items():
        setattr(record, key, value)
    await session.commit()
    return record


async def purchase_lift(session: AsyncSession, merchant_id: int) -> list[dict]:
    orders = select(Order.id).where(Order.merchant_id == merchant_id, Order.status == "delivered").order_by(Order.id.desc()).limit(500)
    rows = (await session.execute(select(OrderItem.order_id, OrderItem.product_id).join(Order).where(
        Order.merchant_id == merchant_id, OrderItem.order_id.in_(orders)).limit(10000))).all()
    baskets: dict[int, set[int]] = {}
    for order_id, product_id in rows:
        baskets.setdefault(order_id, set()).add(product_id)
    singles: Counter[int] = Counter()
    pairs: Counter[tuple[int, int]] = Counter()
    for basket in baskets.values():
        bounded = sorted(basket)[:20]
        singles.update(bounded)
        pairs.update(combinations(bounded, 2))
    total = len(baskets)
    return sorted([{"product_a": a, "product_b": b, "orders_together": count,
        "lift": round(count * total / (singles[a] * singles[b]), 4), "sample_orders": total}
        for (a, b), count in pairs.items()], key=lambda row: (-row["lift"], row["product_a"], row["product_b"]))[:100]


async def generate_compatibility(session: AsyncSession, merchant_id: int) -> dict:
    products, _ = await catalog(session, merchant_id)
    categories = {p.id: p.category.casefold() for p in products}
    from pydantic import Field
    from app.schemas.commerce import Contract
    from app.schemas.commerce_workflows import CompatibilityPair
    from app.services.commerce.providers import structured
    class Suggestions(Contract):
        pairs: list[CompatibilityPair] = Field(max_length=100)
    try:
        import json
        suggestions, source = await structured(Suggestions,
            "Suggest complementary category pairs using only the supplied category names. Do not invent sales history or claim measured lift. Return bounded weights and merchandising explanations. Suggestions require human review.",
            json.dumps(sorted(set(categories.values()))[:50]))
        allowed = set(categories.values())
        safe = [p.model_dump() for p in suggestions.pairs if p.category_a in allowed and p.category_b in allowed]
        return {"compatibility": safe, "source": source, "requires_review": True}
    except ValueError:
        pass
    edges: dict[tuple[str, str], dict] = {}
    for pair in await purchase_lift(session, merchant_id):
        a, b = categories.get(pair["product_a"]), categories.get(pair["product_b"])
        if not a or not b or a == b:
            continue
        key = tuple(sorted((a, b)))
        edges[key] = {"category_a": key[0], "category_b": key[1], "weight": min(1, pair["lift"] / 3),
            "reason": "Observed category co-purchase association; merchant review required."}
    # Suggestions are returned for explicit review/save, not silently persisted by AI.
    return {"compatibility": list(edges.values())[:100], "source": "completed_order_association", "requires_review": True}


async def contextual_snapshot() -> dict:
    from app.core.config import settings
    now = datetime.now(timezone.utc)
    month = now.month
    season = "summer" if month in (3, 4, 5) else "monsoon" if month in (6, 7, 8, 9) else "winter" if month in (12, 1, 2) else "transition"
    result = {"as_of": now.isoformat(), "season": season, "region": "India seasonal heuristic",
        "weather": None, "events": [], "note": "Seasonal tags are suggestions; no price or promotion is changed."}
    if settings.COMMERCE_WEATHER_ENABLED:
        try:
            async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
                response = await client.get("https://api.open-meteo.com/v1/forecast", params={
                    "latitude": settings.COMMERCE_WEATHER_LATITUDE, "longitude": settings.COMMERCE_WEATHER_LONGITUDE,
                    "current": "temperature_2m,precipitation", "forecast_days": 1})
                response.raise_for_status()
                weather = response.json()["current"]
                temperature = float(weather["temperature_2m"])
                precipitation = float(weather["precipitation"])
                import math
                if not math.isfinite(temperature) or not math.isfinite(precipitation):
                    raise ValueError()
                result["weather"] = {"temperature_c": temperature, "precipitation_mm": precipitation}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            result["note"] += " Weather unavailable."
    return result


async def preview(session: AsyncSession, merchant_id: int, query: str, budget: int, anchor: int | None) -> dict:
    products, truncated = await catalog(session, merchant_id)
    policy = await carts.policy_for(session, merchant_id)
    intent = local_intent(query)
    intent.budget_paise = min(budget, intent.budget_paise or budget, policy.max_spend_paise)
    reference = next((p for p in products if p.id == anchor), None)
    behavioral, semantic = await learning.learned_scores(session, merchant_id, query, products, anchor)
    hybrid = rank(products, intent, policy, await co_purchases(session, merchant_id, anchor), reference, behavioral, semantic)
    base_policy = CommercePolicy(merchant_id=merchant_id, max_spend_paise=policy.max_spend_paise,
        blocked_categories=policy.blocked_categories, boosted_product_ids=[])
    baseline = rank(products, intent, base_policy, Counter(), reference)
    positions = {p.id: i + 1 for i, p in enumerate(baseline)}
    return {"baseline": baseline, "hybrid": hybrid, "changes": [{"product_id": p.id,
        "baseline_rank": positions.get(p.id), "hybrid_rank": i + 1} for i, p in enumerate(hybrid)],
        "truncated": truncated, "interpretation": "Ranking comparison only; no conversion or revenue lift was measured."}


async def opportunities(session: AsyncSession, merchant_id: int) -> list[dict]:
    products, _ = await catalog(session, merchant_id)
    rules = await rules_for(session, merchant_id)
    policy = await carts.policy_for(session, merchant_id)
    candidates = []
    for rule in rules.growth_rules:
        if not active_rule(rule):
            continue
        matches = [p for p in products if p.category.casefold() == rule["category"].casefold()
            and p.available > 0 and p.category.casefold() not in policy.blocked_categories]
        if rule["kind"] in {"feature_category", "seasonal_feature"}:
            for product in matches[:2]:
                candidates.append({"rule_id": rule["id"], "kind": "feature_product", "product_id": product.id,
                    "reason": f"Eligible in-stock product for merchant rule {rule['id']}.", "already_featured": product.id in policy.boosted_product_ids})
        elif rule["kind"] == "recovery_offer":
            candidates.append({"rule_id": rule["id"], "kind": "recovery_offer", "category": rule["category"],
                "discount_percent": rule["discount_percent"], "reason": "Offer remains subject to current cost, stock, margin and explicit shopper acceptance."})
    return candidates[:50]


async def run_cycle(session: AsyncSession, merchant_id: int, *, scheduled: bool = False) -> dict:
    rules = await session.get(CommerceRules, merchant_id, with_for_update=True)
    if rules is None:
        return {"executed": [], "reason": "No merchant rules configured."}
    now = int(time.time())
    if scheduled:
        claim = await session.execute(update(CommerceRules).where(CommerceRules.merchant_id == merchant_id,
            CommerceRules.scheduler_enabled.is_(True), CommerceRules.next_run_at <= now)
            .values(next_run_at=now + rules.interval_seconds).execution_options(synchronize_session=False))
        if claim.rowcount != 1:
            await session.rollback()
            return {"executed": [], "reason": "Disabled or not due."}
        # Keep claim and policy update in one transaction under the merchant rule lock.
    policy = await carts.policy_for(session, merchant_id)
    if await session.get(CommercePolicy, merchant_id) is None:
        session.add(policy)
    candidates = await opportunities(session, merchant_id)
    additions = [row["product_id"] for row in candidates if row["kind"] == "feature_product" and not row["already_featured"]][:2]
    policy.boosted_product_ids = sorted(set(policy.boosted_product_ids + additions))[:100]
    result = {"executed": [{"kind": "ranking_feature", "product_id": value} for value in additions],
        "recovery_insights": [row for row in candidates if row["kind"] == "recovery_offer"], "as_of": now,
        "note": "Only configured ranking features change; financial operations require separate confirmation."}
    rules.last_result = result
    await session.commit()
    return result
