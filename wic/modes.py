"""
Modo do wic: wic (cache+IA, padrão) | cache (só cache) | ia (só IA).

Mapeia 1:1 ao CacheMode do motor:
    wic   -> AUTO   (tenta cache; miss vai pra IA e aprende)
    cache -> FORCE  (só cache; miss não chama IA)
    ia    -> OFF    (sempre IA; nem lê nem grava o cache)

O modo persiste num arquivo simples (~/.config/wic/modo), e pode ser
sobrescrito pela variável de ambiente WIC_MODO.
"""

from __future__ import annotations

import os

from .cache_comandos import CacheMode

VALIDOS = ("wic", "cache", "ia")

_MAP = {
    "wic": CacheMode.AUTO,
    "cache": CacheMode.FORCE,
    "ia": CacheMode.OFF,
}


def _arquivo() -> str:
    base = os.environ.get(
        "WIC_CONFIG_DIR", os.path.expanduser("~/.config/wic")
    )
    return os.path.join(base, "modo")


def ler() -> str:
    """Modo atual (env tem prioridade; senão o arquivo; senão 'wic')."""
    m = os.environ.get("WIC_MODO", "").strip().lower()
    if m in VALIDOS:
        return m
    try:
        with open(_arquivo()) as fh:
            m = fh.read().strip().lower()
            if m in VALIDOS:
                return m
    except OSError:
        pass
    return "wic"


def gravar(modo: str) -> None:
    """Persiste o modo escolhido."""
    if modo not in VALIDOS:
        raise ValueError(f"modo inválido: {modo} (use: {', '.join(VALIDOS)})")
    caminho = _arquivo()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w") as fh:
        fh.write(modo)


def cache_mode(modo: str) -> CacheMode:
    """Converte o modo do wic no CacheMode do motor."""
    return _MAP.get(modo, CacheMode.AUTO)
