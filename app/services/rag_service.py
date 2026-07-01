"""RAG retrieval — sunucudaki hazir Qdrant `librelane_verilog` koleksiyonu.

Indexleme sunucudaki indexer.py ile yapilmistir; burada yalnizca sorguyu ayni
embedding modeliyle (nomic-embed-text, oneksiz) vektorleyip Qdrant'ta arama yapariz.
Tum fonksiyonlar degrade-safe'tir: Qdrant/embedding erisilemezse sohbet kirilmaz.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import ollama
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.services.ollama_config import load_ollama_prefs
from app.services.ollama_runtime import resolve_ollama_base_url_sync

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagHit:
    file_path: str
    category: str
    content: str
    score: float


def _embedding_base_url() -> str:
    prefs = load_ollama_prefs()
    return resolve_ollama_base_url_sync(prefs) or prefs.base_url.rstrip("/")


def embed_query(text: str) -> list[float] | None:
    """Sorguyu indexer.py ile birebir ayni sekilde embed'ler (nomic-embed-text, oneksiz)."""
    text = (text or "").strip()
    if not text:
        return None
    settings = get_settings()
    try:
        client = ollama.Client(host=_embedding_base_url(), timeout=settings.rag_timeout_seconds)
        response = client.embeddings(model=settings.rag_embedding_model, prompt=text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG embed_query basarisiz: %s", exc)
        return None

    embedding = response.get("embedding") if isinstance(response, dict) else getattr(response, "embedding", None)
    if not isinstance(embedding, list) or not embedding:
        logger.warning("RAG embed_query bos vektor dondu")
        return None
    return [float(x) for x in embedding]


def _qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, timeout=settings.rag_timeout_seconds)


def retrieve(query: str, top_k: int | None = None) -> list[RagHit]:
    """Sorguyla ilgili kod parcalarini Qdrant'tan ceker. Hata halinde bos liste doner."""
    settings = get_settings()
    if not settings.rag_enabled:
        return []

    vector = embed_query(query)
    if vector is None:
        return []

    limit = top_k if top_k and top_k > 0 else settings.rag_top_k
    try:
        results = _qdrant_client().search(
            collection_name=settings.qdrant_collection,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAG Qdrant araması basarisiz: %s", exc)
        return []

    hits: list[RagHit] = []
    for point in results:
        payload: dict[str, Any] = getattr(point, "payload", None) or {}
        content = str(payload.get("content") or "").strip()
        if not content:
            continue
        hits.append(
            RagHit(
                file_path=str(payload.get("file_path") or payload.get("file_name") or "bilinmeyen"),
                category=str(payload.get("category") or ""),
                content=content,
                score=float(getattr(point, "score", 0.0) or 0.0),
            )
        )
    return hits


def build_context_block(hits: list[RagHit], *, max_chars: int | None = None) -> str:
    """Retrieval sonuclarini modele verilecek tek bir referans metnine cevirir."""
    if not hits:
        return ""
    limit = max_chars if max_chars is not None else get_settings().rag_max_context_chars

    blocks: list[str] = []
    used = 0
    for hit in hits:
        header = f"--- Kaynak: {hit.file_path}"
        if hit.category:
            header += f" ({hit.category})"
        header += " ---"
        block = f"{header}\n```\n{hit.content}\n```"
        if used + len(block) > limit and blocks:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def retrieve_context(query: str, top_k: int | None = None) -> str:
    """retrieve + build_context_block kisayolu; ai_service icin."""
    return build_context_block(retrieve(query, top_k))


def rag_status() -> dict[str, Any]:
    """Frontend gostergesi icin Qdrant baglantisi ve koleksiyon durumu."""
    settings = get_settings()
    result: dict[str, Any] = {
        "enabled": settings.rag_enabled,
        "qdrant_url": settings.qdrant_url,
        "collection": settings.qdrant_collection,
        "embedding_model": settings.rag_embedding_model,
        "ready": False,
    }
    if not settings.rag_enabled:
        result["message"] = "RAG kapali (rag_enabled=false)."
        return result
    try:
        info = _qdrant_client().get_collection(settings.qdrant_collection)
        result["ready"] = True
        result["points_count"] = getattr(info, "points_count", None)
        result["message"] = f"Qdrant bagli — {settings.qdrant_collection}"
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"Qdrant erisilemedi ({settings.qdrant_url}): {exc}"
    return result
