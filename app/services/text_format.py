"""Model metni (thinking / yanit) icin akis birlestirme ve Markdown normalizasyonu."""

from __future__ import annotations

import re

# Delta birlestirmede bosluk gerektirmeyen bas / son karakterler
_NO_SPACE_BEFORE = frozenset(".,;:!?)]}\"'`…’")
_NO_SPACE_AFTER = frozenset("([{\"'`“‘")
# Kucuk ek parcalari (think+ing) birlestirmede bosluk ekleme
_SUFFIX_PIECES = frozenset(
    {"ing", "ed", "ly", "er", "es", "ment", "ness", "tion", "s", "d", "n", "m", "t", "re"}
)

# Ollama num_predict varsayilani; -1 = model baglami dolana kadar (Ollama "sinirsiz")
DEFAULT_CHAT_MAX_TOKENS = 32768


def merge_stream_field(acc: str, piece: str) -> str:
    """
    Ollama akisinda alan birikimini birlestirir.
    NOT: piece uzerinde strip() kullanilmaz; delta'daki bas bosluklar korunur.
    """
    if not piece:
        return acc
    if not acc:
        return piece
    if piece.startswith(acc):
        return piece
    if len(piece) > len(acc) and acc == piece[: len(acc)]:
        return piece
    if acc.startswith(piece) and len(acc) > len(piece):
        return acc
    if _needs_space_between(acc, piece):
        return acc + " " + piece
    return acc + piece


def _is_likely_suffix_piece(piece: str) -> bool:
    p = piece.strip().lower()
    if not p or not p.isalpha():
        return False
    if p in _SUFFIX_PIECES:
        return True
    return len(p) <= 2


def _needs_space_between(acc: str, piece: str) -> bool:
    if acc[-1].isspace() or piece[0].isspace():
        return False
    if acc[-1] in _NO_SPACE_AFTER or piece[0] in _NO_SPACE_BEFORE:
        return False
    if acc[-1] in ".!?" and piece[0].isalnum():
        return True
    a, b = acc[-1], piece[0]
    if a.islower() and b.isupper():
        return True
    if not (a.isalnum() and b.isalnum()):
        return False
    if _is_likely_suffix_piece(piece):
        return False
    # Kisa kucuk parca: akista kelime ortasi (TR: ona+ylı, yoru+m)
    if len(piece) <= 4 and piece.islower() and a.islower():
        return False
    # Uzun kucuk parca: yeni kelime (Merhaba + dunya)
    if len(piece) >= 5 and piece.islower():
        return True
    return False


def normalize_model_markdown(text: str | None) -> str | None:
    """Yayin oncesi Markdown'i okunakli hale getirir; satir sonlarini korur."""
    if text is None:
        return None
    if not text.strip():
        return text.strip() if text else text

    s = text.replace("\r\n", "\n").replace("\r", "\n")
    # Ayni satirda birden fazla bosluk (satir sonu haric)
    s = re.sub(r"[^\S\n]+", " ", s)
    # Baslik / liste oncesi bos satir
    s = re.sub(r"\n(#{1,6}\s)", r"\n\n\1", s)
    s = re.sub(r"\n([-*+]\s)", r"\n\n\1", s)
    s = re.sub(r"\n(\d+\.\s)", r"\n\n\1", s)
    # Fazla bos satirlari sinirla
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
