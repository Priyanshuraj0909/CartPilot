"""Grounded text recommendations copy existing facts and request verification."""
from app.schemas.listing import ListingPolicy, ListingRecommendation
from app.services.listing.signals import ListingSignals
from app.services.listing.quality import analyze_quality, clean_text, words, KEYWORD_STOPWORDS, GENERIC_TITLES


def bounded_description(value: str, limit: int) -> str:
    """Preserve the entire factual context or request verification; never cut qualifiers."""
    return value if len(value) <= limit else ""


def generate_listing_recommendation(signals: ListingSignals, policy: ListingPolicy) -> ListingRecommendation:
    quality = analyze_quality(signals, policy)
    title = quality.title
    if len(words(title)) <= 2 and quality.description:
        # Copy the entire short source description, including negations. Never synthesize features.
        sentence = quality.description.rstrip(".")
        candidate = f"{title} — {sentence}"
        if sentence.casefold() != title.casefold() and len(candidate) <= policy.max_title_length:
            title = candidate
    if len(title) < policy.min_title_length:
        for detail in (quality.category, clean_text(signals.sku)):
            if detail:
                title += f" — {detail}"
            if len(title) >= policy.min_title_length:
                break
    if len(title) > policy.max_title_length:
        # Do not truncate a product claim mid-sentence; use known identifiers or a neutral label.
        identified = f"Product — {clean_text(signals.sku)}"
        title = identified if clean_text(signals.sku) and len(identified) <= policy.max_title_length else "Product listing"
    if len(title) < policy.min_title_length:
        raise ValueError("Available title information cannot satisfy configured output bounds; verify product details.")
    description = quality.description
    if not description or description.casefold().rstrip(".! ") == quality.title.casefold().rstrip(".! "):
        description = f"{quality.title.rstrip('.')}."
        if quality.category:
            description += f" Category: {quality.category}."
        if clean_text(signals.sku):
            description += f" SKU: {clean_text(signals.sku)}."
    description = bounded_description(description, policy.max_description_length)
    if not description:
        description = "Listing details require merchant verification."
    if len(description) > policy.max_description_length:
        raise ValueError("Available description cannot satisfy configured bounds.")
    sparse = quality.title.casefold() in GENERIC_TITLES and not quality.description or not quality.description and not quality.category
    confidence = .2 if sparse else round(min(.9, .45 + (.2 if quality.description else 0) + (.15 if quality.category else 0) + (.1 if signals.sku.strip() else 0)), 2)
    substantial = not quality.description or len(quality.description) > policy.max_description_length or len(quality.title) > policy.max_title_length
    risk = "high" if sparse or quality.category_consistency == "inconsistent" else "medium" if substantial or quality.score < policy.poor_quality_threshold else "low"
    keywords = sorted(words(f"{quality.title} {quality.category}") - KEYWORD_STOPWORDS)
    reason = "Review listing completeness and verify missing details before considering content changes." if quality.issues else "Listing meets the available quality checks; preserve existing factual content."
    return ListingRecommendation(product_id=signals.product_id, current_title=signals.title,
        recommended_title=title, current_description=signals.description, recommended_description=description,
        issues=list(quality.issues), suggestions=list(quality.suggestions), missing_attributes=list(quality.missing_attributes),
        quality_score=quality.score, recommended_keywords=keywords, category_consistency=quality.category_consistency,
        confidence=confidence, risk_level=risk, reason=reason)
