"""
Menu interativo de seleção, em Python puro (sem dependências).

Lê teclas cru (cbreak) direto de /dev/tty e renderiza ANSI no mesmo tty — então
funciona igual em bash ou zsh, Linux ou macOS, e mesmo quando o stdout do wic
está sendo capturado por $(...) (modo --print do wrapper de shell).

Teclas (iguais ao v1):
    ↑ ↓     navegar
    → / ←   expandir / recolher a explicação completa
    x       marca/desmarca a opção como ERRADA (some do cache p/ esta pergunta)
    Enter   executa a destacada (recusa se marcada errada ou com placeholder <…>)
    a       rejeita TODAS e sai sem executar
    q       sai preservando as marcações já feitas

Devolve um Resultado(status, comando, rejeitados).
"""

from __future__ import annotations

import os
import sys
import termios
import tty
from dataclasses import dataclass, field

from .parsing import tem_placeholder

EXEC = "EXEC"
SAVE_ONLY = "SAVE_ONLY"
CANCEL = "CANCEL"


@dataclass
class Resultado:
    status: str                       # EXEC | SAVE_ONLY | CANCEL
    comando: str | None = None        # preenchido só no EXEC
    rejeitados: list[str] = field(default_factory=list)


def _trunc(s: str, n: int) -> str:
    if n < 1:
        n = 1
    return s if len(s) <= n else s[: n - 1] + "…"


class _Menu:
    def __init__(self, itens: list[tuple[str, str]], header: str):
        self.itens = itens
        self.header = header
        self.sel = 0
        self.expandido = False
        self.rejeitados = [False] * len(itens)
        self.aviso = ""
        self.prev_lines = 0
        self.tty_in = open("/dev/tty", "rb", buffering=0)
        self.tty_out = open("/dev/tty", "w")

    # -- terminal -------------------------------------------------------- #
    def _cols(self) -> int:
        try:
            return os.get_terminal_size(self.tty_out.fileno()).columns
        except OSError:
            return 80

    def _w(self, s: str) -> None:
        self.tty_out.write(s)

    def _hide_cursor(self):
        self._w("\033[?25l")

    def _show_cursor(self):
        self._w("\033[?25h")

    # -- render ---------------------------------------------------------- #
    def _render(self):
        cols = self._cols()
        if self.prev_lines:
            self._w(f"\033[{self.prev_lines}A\033[J")
        linhas = 0
        self._w(f"\033[1;36m{_trunc(self.header, cols)}\033[0m\n")
        linhas += 1

        avail = cols - 5
        for i, (cmd, desc) in enumerate(self.itens):
            sel = i == self.sel
            rej = self.rejeitados[i]

            if sel and self.expandido and desc:
                cmd_show = _trunc(cmd, avail)
                if rej:
                    self._w(f"  \033[1;31m✗ \033[9;31m{cmd_show}\033[0m\033[K\n")
                else:
                    self._w(f"  \033[1;32m❯ {cmd_show}\033[0m\033[K\n")
                linhas += 1
                # descrição completa quebrada em várias linhas
                wrapw = max(10, cols - 7)
                linha = ""
                for w in desc.split():
                    if not linha:
                        linha = w
                    elif len(linha) + 1 + len(w) <= wrapw:
                        linha += " " + w
                    else:
                        self._w(f"      \033[2;37m{linha}\033[0m\033[K\n")
                        linhas += 1
                        linha = w
                if linha:
                    self._w(f"      \033[2;37m{linha}\033[0m\033[K\n")
                    linhas += 1
                continue

            # linha única (comando + explicação truncados)
            if len(cmd) >= avail:
                cmd_show, desc_show = _trunc(cmd, avail), ""
            else:
                cmd_show = cmd
                rem = avail - len(cmd) - 2
                desc_show = _trunc(desc, rem) if (rem >= 2 and desc) else ""

            if rej:
                if desc_show:
                    self._w(f"  \033[1;31m✗ \033[9;31m{cmd_show}\033[0m  "
                            f"\033[9;2;31m{desc_show}\033[0m\033[K\n")
                else:
                    self._w(f"  \033[1;31m✗ \033[9;31m{cmd_show}\033[0m\033[K\n")
            elif sel:
                if desc_show:
                    self._w(f"  \033[1;32m❯ {cmd_show}\033[0m  "
                            f"\033[2;37m{desc_show}\033[0m\033[K\n")
                else:
                    self._w(f"  \033[1;32m❯ {cmd_show}\033[0m\033[K\n")
            else:
                if desc_show:
                    self._w(f"    \033[0;37m{cmd_show}\033[0m  "
                            f"\033[2;90m{desc_show}\033[0m\033[K\n")
                else:
                    self._w(f"    \033[0;37m{cmd_show}\033[0m\033[K\n")
            linhas += 1

        if self.aviso:
            self._w(f"  \033[1;33m! {_trunc(self.aviso, cols - 4)}\033[0m\033[K\n")
            linhas += 1

        self.prev_lines = linhas
        self.tty_out.flush()

    # -- input ----------------------------------------------------------- #
    def _ler_tecla(self) -> str:
        ch = self.tty_in.read(1)
        if not ch:
            return "q"
        if ch == b"\x1b":  # ESC: provável seta (ESC [ X)
            seq = self.tty_in.read(2)
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(
                seq[-1:].decode("latin1"), "esc"
            )
        if ch in (b"\r", b"\n"):
            return "enter"
        return ch.decode("latin1").lower()

    def _coletar_rejeitados(self) -> list[str]:
        return [self.itens[i][0] for i, r in enumerate(self.rejeitados) if r]

    # -- loop ------------------------------------------------------------ #
    def rodar(self) -> Resultado:
        if not self.itens:
            return Resultado(CANCEL)
        fd = self.tty_in.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            self._hide_cursor()
            self._render()
            while True:
                self.aviso = ""
                k = self._ler_tecla()
                total = len(self.itens)
                if k == "up":
                    self.sel = (self.sel - 1) % total
                    self.expandido = False
                elif k == "down":
                    self.sel = (self.sel + 1) % total
                    self.expandido = False
                elif k == "right":
                    self.expandido = True
                elif k == "left":
                    self.expandido = False
                elif k == "x":
                    self.rejeitados[self.sel] = not self.rejeitados[self.sel]
                elif k == "enter":
                    cmd = self.itens[self.sel][0]
                    if self.rejeitados[self.sel]:
                        self.aviso = "marcada como errada — desmarque com x, ou 'a' p/ rejeitar tudo"
                    elif tem_placeholder(cmd):
                        self.aviso = "tem placeholder <…> — edite antes; escolha outra, ou 'a'/'q'"
                    else:
                        return Resultado(EXEC, cmd, self._coletar_rejeitados())
                elif k == "a":
                    self.rejeitados = [True] * total
                    return Resultado(SAVE_ONLY, None, self._coletar_rejeitados())
                elif k == "q":
                    rej = self._coletar_rejeitados()
                    return Resultado(SAVE_ONLY if rej else CANCEL, None, rej)
                self._render()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            self._show_cursor()
            self.tty_out.write("\n")
            self.tty_out.flush()
            self.tty_in.close()
            self.tty_out.close()


def selecionar(itens: list[tuple[str, str]], header: str) -> Resultado:
    """Abre o menu e devolve a escolha do usuário."""
    return _Menu(itens, header).rodar()
