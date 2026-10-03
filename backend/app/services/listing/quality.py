"""Small explainable text heuristics, not semantic or marketplace SEO scoring."""
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from app.schemas.listing import ListingPolicy
from app.services.listing.signals import ListingSignals

# Presence means mentioned, not independently verified or guaranteed applicable.
CATEGORY_TERMS = {
    "electronics": {"mouse", "keyboard", "speaker", "headphones", "charger", "usb", "wireless", "monitor", "earbuds"},
    "clothing": {"shirt", "cotton", "hoodie", "jacket", "socks", "pants", "dress", "merino"},
    "home": {"lamp", "pillow", "blanket", "kitchen", "bottle", "mug", "towel"},
}
ATTRIBUTE_PATTERNS = {
    "electronics": {"connectivity": r"\b(usb|bluetooth|wireless|wired|wi-fi)\b",
                    "power": r"\b(battery|batteries|powered|rechargeable|charging|power)\b",
                    "compatibility": r"\b(compatible|compatibility|windows|macos|android|ios)\b",
                    "dimensions": r"\b\d+(?:\.\d+)?\s*(?:cm|mm|inches|inch)\b"},
    "clothing": {"material": r"\b(cotton|wool|merino|polyester|linen|silk)\b",
                 "size": r"\b(size|sizes|small|medium|large)\b",
                 "care": r"\b(wash|washable|care|dry.clean)\b"},
    "home": {"material": r"\b(steel|glass|wood|cotton|ceramic|plastic)\b",
             "dimensions": r"\b\d+(?:\.\d+)?\s*(?:cm|mm|inches|inch)\b"},
}
CATEGORY_ALIASES = {"apparel": "clothing", "home & kitchen": "home"}
GENERIC_TITLES = {"product", "item", "new product", "sale", "untitled"}
KEYWORD_STOPWORDS = {"a", "an", "the", "and", "or", "with", "for", "of", "to", "in", "is", "this", "product", "item"}


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self.ignored += 1
        self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self.ignored:
            self.ignored -= 1
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def clean_text(value: str | None) -> str:
    parser = _PlainText()
    parser.feed(value or "")
    return " ".join("".join(parser.parts).split())


def words(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+(?:[-.][^\W_]+)*", value.casefold()))


@dataclass(frozen=True)
class ListingQuality:
    title: str
    description: str
    category: str
    issues: tuple[str, ...]
    suggestions: tuple[str, ...]
    missing_attributes: tuple[str, ...]
    category_consistency: str
    score: float


def analyze_quality(signals: ListingSignals, policy: ListingPolicy) -> ListingQuality:
    title, description, category = map(clean_text, (signals.title, signals.description, signals.category))
    if not title:
        raise ValueError("Product title is empty; verify source product data.")
    issues, suggestions = [], []
    title_checks = [policy.min_title_length <= len(title) <= policy.max_title_length,
                    len(words(title)) > 2 and title.casefold() not in GENERIC_TITLES,
                    title == signals.title.strip()]
    if len(title) < policy.min_title_length:
        issues.append("Title is too short")
    if len(title) > policy.max_title_length:
        issues.append("Title exceeds the configured length limit")
    if not title_checks[1]:
        issues.append("Title lacks descriptive detail")
    if not title_checks[2]:
        issues.append("Title formatting needs cleanup")
    if not all(title_checks):
        suggestions.append("Use a concise title based only on verified product information.")
    description_checks = [bool(description), policy.min_description_length <= len(description) <= policy.max_description_length,
                          bool(description) and description.casefold().rstrip(".! ") != title.casefold().rstrip(".! "),
                          bool(description) and description == (signals.description or "").strip()]
    if not description:
        issues.append("Description is missing")
    elif len(description) < policy.min_description_length:
        issues.append("Description is too short")
    elif len(description) > policy.max_description_length:
        issues.append("Description exceeds the configured length limit")
    if description and not description_checks[2]:
        issues.append("Description duplicates the title")
    if description and not description_checks[3]:
        issues.append("Description formatting needs cleanup")
    if not all(description_checks):
        suggestions.append("Provide clear factual details and verified usage benefits; do not invent claims.")
    content = f"{title} {description}".casefold()
    category_key = CATEGORY_ALIASES.get(category.casefold(), category.casefold())
    terms = CATEGORY_TERMS.get(category_key)
    mentioned = words(content)
    if not category:
        consistency = "missing"
        issues.append("Category is missing")
        suggestions.append("Verify the product category before editing listing content.")
    elif not terms:
        consistency = "unverified"
    elif mentioned & terms:
        consistency = "consistent"
    elif any(mentioned & other for key, other in CATEGORY_TERMS.items() if key != category_key):
        consistency = "inconsistent"
        issues.append("Listing content may contradict the recorded category")
        suggestions.append("Review category consistency; no category change is applied.")
    else:
        consistency = "unverified"
        issues.append("Category alignment could not be verified from listing text")
    patterns = ATTRIBUTE_PATTERNS.get(category_key, {})
    missing = tuple(name for name, pattern in patterns.items() if not re.search(pattern, content))
    if missing:
        issues.append("Useful product attributes are not mentioned")
        suggestions.extend(f"Verify and add {attribute} details if applicable." for attribute in missing)
    if not patterns:
        suggestions.append("Review category-specific attributes manually; no structured attribute data exists.")
    attributes = (len(patterns) - len(missing)) / len(patterns) if patterns else .5
    alignment = 1 if consistency == "consistent" else .5 if consistency == "unverified" else 0
    score = round(.25 * sum(title_checks)/3 + .35 * sum(description_checks)/4 + .25 * attributes + .15 * alignment, 2)
    return ListingQuality(title, description, category, tuple(issues), tuple(suggestions), missing, consistency, score)
