"""
Parser da saída crua (5 linhas `comando ::: explicação`) -> lista de pares.

Replica a limpeza que o v1 fazia no zsh: remove cercas de código (```),
tags de linguagem soltas (bash/sh/...), crases, numeração (1. 2.) e marcadores
de lista (- ). Tolera linhas sem ':::' (vira comando sem explicação).
"""

from __future__ import annotations

import re

_NUMERACAO = re.compile(r"^\d+\.\s*")
_CERCA = re.compile(r"^```")
_TAG_LING = re.compile(r"^(bash|sh|shell|zsh)$")

# Placeholders do template que modelos pequenos às vezes ecoam como se fossem
# comando de verdade (ex.: "comando ::: ..."). Nunca são comando real -> descartar.
_PLACEHOLDERS = {"comando", "<comando>", "comando completo", "<comando pronto para colar>"}


def parse(raw: str, limite: int = 5) -> list[tuple[str, str]]:
    """Devolve [(comando, explicação), ...] já limpo, no máximo `limite` itens."""
    pares: list[tuple[str, str]] = []
    for linha in raw.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        if _CERCA.match(linha) or _TAG_LING.match(linha):
            continue
        linha = linha.replace("`", "")
        linha = _NUMERACAO.sub("", linha)
        if linha.startswith("- "):
            linha = linha[2:]
        linha = linha.strip()
        if not linha:
            continue

        if ":::" in linha:
            cmd, desc = linha.split(":::", 1)
        else:
            cmd, desc = linha, ""
        cmd = cmd.strip()
        desc = desc.strip()
        if not cmd or cmd.lower() in _PLACEHOLDERS:
            continue
        pares.append((cmd, desc))
        if len(pares) >= limite:
            break
    return pares


def tem_placeholder(cmd: str) -> bool:
    """Comando ainda tem um marcador <…> não preenchido? (ex.: <url>, <arquivo>)"""
    return "<" in cmd and ">" in cmd and cmd.index("<") < cmd.rindex(">")


def juntar(pares: list[tuple[str, str]]) -> str:
    """Serializa de volta para o formato `comando ::: explicação` (uma linha cada)."""
    return "\n".join(f"{c} ::: {d}" if d else c for c, d in pares)
