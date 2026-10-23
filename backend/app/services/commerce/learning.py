"""Bounded merchant-owned co-purchase training and optional provider semantic index.

Item2Vec uses a small reproducible skip-gram/negative-sampling model, implemented
with the standard library. It is an experimental ranking signal, not proven lift.
"""
import asyncio
import threading
import hashlib
import math
import random
import time
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.models.commerce import CommerceModel
from app.models.order import Order
from app.models.order_item import OrderItem
from app.schemas.commerce import StoreProduct

DIMENSIONS = 64
MIN_ORDERS = 30


def cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    norm = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
    return sum(a*b for a, b in zip(left, right)) / norm if norm else 0.0


def train(sequences: list[list[int]]) -> dict:
    sequences = [sorted(set(row))[:20] for row in sequences if len(set(row)) >= 2][:500]
    if len(sequences) < MIN_ORDERS:
        raise ValueError(f"Need at least {MIN_ORDERS} completed multi-product orders.")
    vocabulary = sorted({item for row in sequences for item in row})
    if len(vocabulary) > 500:
        raise ValueError("Training supports at most 500 distinct products.")
    rng = random.Random(17)
    inputs = {item: [rng.uniform(-.1, .1) for _ in range(DIMENSIONS)] for item in vocabulary}
    outputs = {item: [0.0] * DIMENSIONS for item in vocabulary}
    pairs = [(left, right) for row in sequences for left in row for right in row if left != right][:20000]
    for _ in range(3):
        rng.shuffle(pairs)
        for target, context in pairs:
            for candidate, label in [(context, 1)] + [(rng.choice(vocabulary), 0) for _ in range(2)]:
                if not label and candidate == context:
                    continue
                source, dest = inputs[target], outputs[candidate]
                dot = max(-15.0, min(15.0, sum(a*b for a, b in zip(source, dest))))
                gradient = .035 * (label - 1.0 / (1.0 + math.exp(-dot)))
                previous = source[:]
                for index in range(DIMENSIONS):
                    source[index] += gradient * dest[index]
                    dest[index] += gradient * previous[index]
    return {"vectors": {str(key): value for key, value in inputs.items()}, "orders": len(sequences),
            "dimensions": DIMENSIONS, "algorithm": "skip-gram negative sampling", "epochs": 3}


async def train_for_store(session: AsyncSession, merchant_id: int) -> dict:
    orders = select(Order.id).where(Order.merchant_id == merchant_id, Order.status == "delivered").order_by(Order.id.desc()).limit(500)
    rows = (await session.execute(select(OrderItem.order_id, OrderItem.product_id).join(Order).where(
        Order.merchant_id == merchant_id, OrderItem.order_id.in_(orders)).order_by(OrderItem.order_id, OrderItem.id).limit(10000))).all()
    sequences: dict[int, list[int]] = {}
    for order, product in rows:
        sequences.setdefault(order, []).append(product)
    try:
        data = await asyncio.to_thread(train, list(sequences.values()))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    await save_model(session, merchant_id, "item2vec", data)
    return {"orders": data["orders"], "products": len(data["vectors"]), "dimensions": DIMENSIONS}


async def save_model(session: AsyncSession, merchant_id: int, kind: str, data: dict) -> None:
    model = await session.get(CommerceModel, (merchant_id, kind))
    if model is None:
        model = CommerceModel(merchant_id=merchant_id, kind=kind)
        session.add(model)
    model.data, model.updated_at = data, int(time.time())
    await session.commit()


def fingerprint(product: StoreProduct) -> str:
    return hashlib.sha256(f"{product.name}\n{product.category}\n{product.description}".encode()).hexdigest()


_LOCAL_MODEL = None
_LOCAL_MODEL_LOCK = threading.Lock()


def local_embedding(text: str) -> list[float]:
    global _LOCAL_MODEL
    try:
        from sentence_transformers import SentenceTransformer
        with _LOCAL_MODEL_LOCK:
            if _LOCAL_MODEL is None:
                _LOCAL_MODEL = SentenceTransformer("all-MiniLM-L6-v2")
        vector = _LOCAL_MODEL.encode(text[:10000], normalize_embeddings=True).tolist()
        if len(vector) != 384 or any(not math.isfinite(value) for value in vector):
            raise ValueError("Invalid local embedding")
        return vector
    except (ImportError, OSError, RuntimeError):
        raise ValueError("Local MiniLM is unavailable; check optional dependencies and model installation.") from None


def embedding_identity() -> str:
    return "local/all-MiniLM-L6-v2" if settings.BUYER_LOCAL_EMBEDDINGS else settings.BUYER_EMBEDDING_MODEL


async def embed(text: str, task: str) -> list[float]:
    if settings.BUYER_LOCAL_EMBEDDINGS:
        return await asyncio.to_thread(local_embedding, text)
    if not settings.BUYER_SEMANTIC_ENABLED or (not settings.GEMINI_API_KEY and not settings.BUYER_LOCAL_EMBEDDINGS):
        raise ValueError("Semantic provider is not configured.")
    async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
        response = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.BUYER_EMBEDDING_MODEL}:embedContent",
            headers={"x-goog-api-key": settings.GEMINI_API_KEY},
            json={"model": f"models/{settings.BUYER_EMBEDDING_MODEL}", "content": {"parts": [{"text": text[:10000]}]},
                  "taskType": task, "outputDimensionality": 768})
        response.raise_for_status()
        vector = response.json()["embedding"]["values"]
        if not isinstance(vector, list) or len(vector) != 768 or any(isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x) for x in vector):
            raise ValueError("Invalid embedding response")
        return vector


async def index_catalog(session: AsyncSession, merchant_id: int, products: list[StoreProduct]) -> dict:
    if not settings.BUYER_SEMANTIC_ENABLED or (not settings.GEMINI_API_KEY and not settings.BUYER_LOCAL_EMBEDDINGS):
        raise HTTPException(503, "Enable the semantic provider before indexing.")
    # Explicit merchant operation: at most 50 documents per request, shared concurrency 4.
    # Existing valid vectors are reused. Repeated calls progress through the catalog.
    model = await session.get(CommerceModel, (merchant_id, "semantic"))
    data = model.data if model and model.data.get("model") == embedding_identity() else {}
    vectors = dict(data.get("vectors", {}))
    hashes = dict(data.get("fingerprints", {}))
    pending = [p for p in products if hashes.get(str(p.id)) != fingerprint(p)]
    semaphore = asyncio.Semaphore(4)
    async def one(product: StoreProduct):
        async with semaphore:
            return product, await embed(f"{product.name}. {product.category}. {product.description}", "RETRIEVAL_DOCUMENT")
    try:
        results = await asyncio.gather(*(one(p) for p in pending[:50]))
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Semantic indexing failed; the previous index is retained.") from None
    for product, vector in results:
        vectors[str(product.id)] = vector
        hashes[str(product.id)] = fingerprint(product)
    active = {str(p.id) for p in products}
    await save_model(session, merchant_id, "semantic", {"model": embedding_identity(),
        "vectors": {key: value for key, value in vectors.items() if key in active},
        "fingerprints": {key: value for key, value in hashes.items() if key in active}})
    return {"indexed": len(results), "remaining": max(0, len(pending) - 50), "model": embedding_identity()}


async def learned_scores(session: AsyncSession, merchant_id: int, query: str, products: list[StoreProduct], anchor: int | None) -> tuple[dict[int, float], dict[int, float]]:
    behavioral: dict[int, float] = {}
    semantic: dict[int, float] = {}
    model = await session.get(CommerceModel, (merchant_id, "item2vec"))
    if model and anchor is not None:
        vectors = model.data.get("vectors", {})
        source = vectors.get(str(anchor), [])
        behavioral = {p.id: max(0.0, cosine(source, vectors.get(str(p.id), []))) for p in products}
    index = await session.get(CommerceModel, (merchant_id, "semantic"))
    if index and index.data.get("model") == embedding_identity() and settings.BUYER_SEMANTIC_ENABLED:
        try:
            query_vector = await embed(query, "RETRIEVAL_QUERY")
            semantic = {p.id: max(0.0, cosine(query_vector, index.data["vectors"].get(str(p.id), [])))
                for p in products if index.data["fingerprints"].get(str(p.id)) == fingerprint(p)}
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass  # Search still works; lexical and stock/budget checks remain active.
    return behavioral, semantic
