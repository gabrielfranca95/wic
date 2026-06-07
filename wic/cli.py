"""
Orquestração do wic — a lógica que no v1 vivia na função zsh `wic()`.

Fluxo (igual ao v1, agora em Python e shell-agnóstico):
  1. resolve o modo (wic | cache | ia)
  2. obtém 5 sugestões: do cache (motor TF-IDF, no mesmo processo) ou do Ollama
  3. mostra o menu interativo
  4. curadoria do cache conforme as marcações (aprende boas / grava negativa)
  5. executa a escolhida — ou imprime no stdout (--print) p/ o wrapper de shell
     dar `eval` e preservar cd/export
"""

from __future__ import annotations

import os
import subprocess
import sys

from . import modes
from .cache_comandos import CacheComandos, CacheMode
from .ollama_client import OllamaError, garantir_modelo, gerar
from .menu import CANCEL, EXEC, SAVE_ONLY, selecionar
from .parsing import juntar, parse, tem_placeholder

HEADER = ("⌨  ↑↓ navegar · → expandir · x errada · Enter executar · "
          "a rejeitar tudo · q sair:")


# --- cores p/ mensagens (só se for tty) ------------------------------------- #
def _c(code: str, txt: str) -> str:
    return f"\033[{code}m{txt}\033[0m" if sys.stderr.isatty() else txt


def _erro(msg: str) -> None:
    sys.stderr.write(_c("1;31", "✗ ") + msg + "\n")


def _info(msg: str) -> None:
    sys.stderr.write(msg + "\n")


# --- banco ------------------------------------------------------------------ #
def _db_path() -> str:
    p = os.environ.get("WIC_CACHE_DB")
    if p:
        return p
    base = os.environ.get("WIC_CONFIG_DIR", os.path.expanduser("~/.config/wic"))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "wic_cache.db")


def _abrir_cache() -> CacheComandos:
    limiar = float(os.environ.get("WIC_CACHE_LIMIAR", "0.62"))
    cache = CacheComandos(db_path=_db_path(), limiar=limiar)
    # auto-seed no primeiro uso: popula os comandos canônicos (git/docker/…).
    if cache.stats()["entradas"] == 0:
        try:
            from .dados_wic import COMANDOS_WIC
            cache.seed(COMANDOS_WIC)
        except Exception:
            pass
    return cache


def _ler_cache(cache: CacheComandos, pedido: str) -> str | None:
    """Lê SÓ o cache (sem IA). Devolve a saída crua (5 linhas) ou None se miss."""
    def _ia_off(_):
        raise RuntimeError("não deve chamar IA aqui")
    r = cache.consultar(pedido, _ia_off, CacheMode.FORCE)
    if r.source == "miss" or not r.resposta:
        return None
    return r.resposta


# --- execução --------------------------------------------------------------- #
def _executar(cmd: str) -> int:
    shell = os.environ.get("SHELL", "/bin/sh")
    sys.stderr.write("\n" + _c("1;32", "▶ ") + _c("1", f"Executando: {cmd}") + "\n")
    sys.stderr.write(_c("2;37", "─" * 41) + "\n")
    sys.stderr.flush()
    try:
        return subprocess.run([shell, "-c", cmd]).returncode
    except KeyboardInterrupt:
        return 130


# --- comando principal ------------------------------------------------------ #
def _rodar(pedido: str, imprimir: bool) -> int:
    modo = modes.ler()
    cache = _abrir_cache()
    forcar_ia = False
    try:
        while True:
            veio_da_ia = False

            # 1. obter sugestões -------------------------------------------- #
            if modo == "ia" or forcar_ia:
                try:
                    garantir_modelo()
                    raw = gerar(pedido)
                except OllamaError as e:
                    _erro(str(e))
                    return 1
                veio_da_ia = True
            else:
                raw = _ler_cache(cache, pedido)
                if raw is not None:
                    _info("  " + _c("36", "⚡") + " resposta do cache (instantânea, sem IA)")
                else:
                    if modo == "cache":
                        _info("  " + _c("33", "∅") + " nada no cache (modo cache: IA desligada).")
                        return 0
                    try:
                        garantir_modelo()
                        raw = gerar(pedido)
                    except OllamaError as e:
                        _erro(str(e))
                        return 1
                    veio_da_ia = True
            forcar_ia = False

            # 2. parse ------------------------------------------------------ #
            pares = parse(raw, limite=5)
            if not pares:
                _erro("Nenhum comando válido retornado.")
                return 1

            # 3. menu ------------------------------------------------------- #
            res = selecionar(pares, HEADER)

            # 4. curadoria do cache (nunca no modo ia; nunca em CANCEL) ----- #
            if modo != "ia" and res.status != CANCEL:
                rej = set(res.rejeitados)
                bons = [(c, d) for c, d in pares if c not in rej]
                if not bons:
                    cache.upsert(pedido, "", negativo=1)            # tudo errado → negativa
                elif rej or veio_da_ia:
                    cache.upsert(pedido, juntar(bons))              # aprende as boas

            # 5. agir ------------------------------------------------------- #
            if res.status == EXEC:
                cmd = res.comando or ""
                if tem_placeholder(cmd):  # defesa em profundidade
                    _info(_c("33", "! ") + f"Tem placeholder <…>; não executei: {cmd}")
                    return 0
                if imprimir:
                    print(cmd)            # o wrapper de shell dá eval (preserva cd/export)
                    return 0
                return _executar(cmd)

            if (res.status == SAVE_ONLY and res.rejeitados and modo in ("wic", "ia")):
                _info("  " + _c("36", "↻") + " essas não serviram — buscando alternativa na IA...")
                forcar_ia = True
                continue

            _info(_c("33", "⊘ ") + "Sem execução.")
            return 0
    finally:
        cache.close()


# --- subcomandos ------------------------------------------------------------ #
def _cmd_modo(args: list[str]) -> int:
    if not args:
        _info(f"modo atual: {modes.ler()}   (use: wic --modo wic|cache|ia)")
        return 0
    m = args[0].lower()
    if m not in modes.VALIDOS:
        _erro(f"modo inválido: {m}  (use: wic | cache | ia)")
        return 1
    modes.gravar(m)
    desc = {"wic": "cache + IA (padrão)", "cache": "só cache, sem IA", "ia": "só IA, sem cache"}
    _info(_c("1;32", "✓ ") + f"modo {m} — {desc[m]}")
    return 0


def _cmd_stats() -> int:
    cache = _abrir_cache()
    try:
        s = cache.stats()
        _info(f"banco: {_db_path()}")
        _info(f"  entradas    : {s['entradas']}")
        _info(f"  hits totais : {s['hits_totais']}")
    finally:
        cache.close()
    return 0


def _cmd_seed() -> int:
    cache = _abrir_cache()
    try:
        from .dados_wic import COMANDOS_WIC
        antes = cache.stats()["entradas"]
        cache.seed(COMANDOS_WIC)
        depois = cache.stats()["entradas"]
        _info(f"sementes: +{depois - antes} novas (total {depois})")
    finally:
        cache.close()
    return 0


HELP = """\
wic — what is command: linguagem natural → comando de shell (100% local)

Uso:
  wic <descrição>          sugere 5 comandos e executa o escolhido
  wic --print <descrição>  imprime o comando escolhido (p/ o wrapper de shell)
  wic --modo [wic|cache|ia]  mostra/troca o modo
  wic --stats              estado do cache
  wic --seed               (re)popula os comandos canônicos
  wic --version            (ou --v) mostra a versão do wic
  wic --help               esta ajuda

Modos:  wic = cache+IA (padrão) · cache = só cache · ia = só IA
Ajustes: WIC_OLLAMA_MODEL, WIC_TIMEOUT, WIC_CACHE_DB, WIC_MODO
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(HELP)
        return 0
    if argv[0] in ("--version", "--v", "-v"):
        from . import __version__
        sys.stdout.write(f"wic {__version__}\n")
        return 0
    if argv[0] == "--modo":
        return _cmd_modo(argv[1:])
    if argv[0] == "--stats":
        return _cmd_stats()
    if argv[0] == "--seed":
        return _cmd_seed()

    imprimir = False
    if argv[0] == "--print":
        imprimir = True
        argv = argv[1:]
    if not argv:
        _erro("Uso: wic descrição do que você quer fazer  (sem aspas)")
        return 1

    pedido = " ".join(argv).strip()
    try:
        return _rodar(pedido, imprimir)
    except KeyboardInterrupt:
        sys.stderr.write("\r\033[K")
        _info(_c("33", "⊘ ") + "Cancelado.")
        return 130
