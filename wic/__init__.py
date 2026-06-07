"""
wic — "what is command": linguagem natural → comando de shell, 100% local.

Versão 2: CLI standalone em Python (roda em bash E zsh, Linux e macOS),
reaproveitando o motor de cache semântico do v1 (cache_comandos.py).

A diferença central para o v1 (função de zsh) é que aqui o wic é um PROGRAMA:
não depende de shell nenhum, fala com o Ollama pela API HTTP e usa o motor do
cache no MESMO processo (sem spawnar um python só pro cache, como o v1 fazia).
"""

# Pasta "v2" = segunda encarnação do wic. Número de versão = 0.2.x (pré-1.0).
__version__ = "0.2.0"
