"""
Cliente do Ollama via API HTTP local (http://127.0.0.1:11434).

Por que HTTP e não `ollama run`:
  - não depende de spawnar o binário a cada chamada;
  - deixa controlar `keep_alive` (mantém o modelo quente -> respostas seguintes
    rápidas) e os parâmetros de amostragem direto no request;
  - dispensa o "modelo calibrado" do v1: o system prompt + temperatura baixa
    viajam no próprio request, então não precisa mais do `ollama create wic`.

Só usa a stdlib (urllib) — nada de pip, o que mantém a fórmula do Homebrew limpa.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

HOST = os.environ.get("WIC_OLLAMA_HOST", "http://127.0.0.1:11434")
MODELO_PADRAO = os.environ.get("WIC_OLLAMA_MODEL", "qwen2.5-coder:1.5b")
TIMEOUT = int(os.environ.get("WIC_TIMEOUT", "60"))
KEEP_ALIVE = os.environ.get("WIC_KEEP_ALIVE", "10m")


class OllamaError(Exception):
    """Falha ao falar com o Ollama (serviço fora do ar, timeout, modelo ausente…)."""


def _detectar_ambiente() -> str:
    """String curta do SO real, p/ ancorar o system prompt (anti-alucinação)."""
    sistema = platform.system()
    if sistema == "Darwin":
        return f"macOS {platform.mac_ver()[0]}".strip()
    if sistema == "Linux":
        try:
            with open("/etc/os-release") as fh:
                for linha in fh:
                    if linha.startswith("PRETTY_NAME="):
                        return linha.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
        return "Linux"
    return sistema or "Unix"


def _system_prompt() -> str:
    amb = _detectar_ambiente()
    return (
        f"Você é um especialista em linha de comando do Unix.\n"
        f"Ambiente real do usuário: {amb}, terminal interativo.\n\n"
        "Tarefa: dado um pedido em linguagem natural, responda com EXATAMENTE 5 "
        "variações de comando REAIS que resolvem o pedido NESSE ambiente.\n\n"
        "Cada linha DEVE ter a forma:\n"
        "<comando pronto para colar> ::: <explicação curta>\n"
        "onde <comando pronto para colar> é o comando shell de verdade — "
        'NUNCA escreva a palavra literal "comando".\n\n'
        "Exemplos do FORMATO (não copie estes; use o comando real do pedido):\n"
        "ls -lh ::: lista com tamanhos legíveis\n"
        "du -sh * ::: tamanho de cada item da pasta\n\n"
        "Regras absolutas:\n"
        "- Exatamente 5 linhas, uma por variação.\n"
        "- A explicação é CURTA: no MÁXIMO 6 palavras, em português, dizendo só o "
        "que aquela variação faz de diferente das outras.\n"
        "- As 5 variações devem ser GENUINAMENTE diferentes (ferramentas ou "
        "abordagens distintas).\n"
        "- Use apenas comandos e flags REAIS e comuns. NUNCA invente flags nem "
        "comandos. NUNCA use comandos de outro SO.\n"
        "- NUNCA invente caminhos como /path/to/algo. Use o diretório atual (.) "
        "ou marcadores claramente editáveis (ex.: <arquivo>, <porta>).\n"
        "- O comando, antes do :::, deve estar completo e pronto para colar.\n"
        "- Pipes e encadeamentos ficam na mesma linha, antes do :::.\n"
        "- Coloque a solução mais segura e idiomática na primeira linha.\n"
        "- Responda SOMENTE as 5 linhas. SEM markdown, SEM crases, SEM numeração, "
        "SEM linhas em branco, SEM nenhum texto antes ou depois."
    )


def _http_json(caminho: str, payload: dict | None = None, timeout: int = TIMEOUT):
    """POST (se payload) ou GET em HOST+caminho; devolve o JSON decodificado."""
    url = f"{HOST}{caminho}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def servico_no_ar() -> bool:
    try:
        _http_json("/api/tags", timeout=3)
        return True
    except Exception:
        return False


def modelo_presente(modelo: str) -> bool:
    try:
        tags = _http_json("/api/tags", timeout=5)
    except Exception:
        return False
    nomes = {m.get("name", "") for m in tags.get("models", [])}
    base = modelo.split(":")[0]
    return any(n == modelo or n.split(":")[0] == base for n in nomes)


def iniciar_servico(timeout: int = 15) -> None:
    """
    Garante o daemon do Ollama no ar — e SOBE ELE SOZINHO se estiver desligado,
    em segundo plano. O usuário nunca precisa rodar `ollama serve`, mexer com
    systemctl nem abrir o app: o wic cuida disso de forma invisível.

    Levanta OllamaError só se o Ollama nem estiver instalado ou não subir a tempo.
    """
    if servico_no_ar():
        return
    try:
        # destacado (start_new_session): o daemon sobrevive ao fim do wic e fica
        # disponível pras próximas chamadas. Saída silenciada (invisível).
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as e:
        raise OllamaError(
            "Ollama não encontrado. Instale com:\n"
            "  curl -fsSL https://ollama.com/install.sh | sh   (Linux)\n"
            "  brew install ollama                             (macOS)"
        ) from e
    # espera o daemon responder (sobe em ~1-2s normalmente)
    for _ in range(timeout * 2):
        time.sleep(0.5)
        if servico_no_ar():
            return
    raise OllamaError(
        "Não consegui iniciar o assistente local automaticamente.\n"
        "Tente uma vez na mão pra ver o erro:  ollama serve"
    )


def garantir_modelo(modelo: str = MODELO_PADRAO) -> None:
    """
    Garante o serviço no ar (subindo sozinho se preciso) e baixa o modelo no
    primeiro uso, se faltar (~1 GB, uma vez só). Levanta OllamaError se não der.
    """
    iniciar_servico()            # sobe o Ollama sozinho se estiver desligado
    if modelo_presente(modelo):
        return
    sys.stderr.write(
        f"  Preparando o assistente (download único, ~1 GB): {modelo}\n"
        f"  Isso só acontece na primeira vez.\n"
    )
    sys.stderr.flush()
    try:
        subprocess.run(["ollama", "pull", modelo], check=True)
    except FileNotFoundError as e:
        raise OllamaError(
            "Ollama não encontrado. Instale com:\n"
            "  curl -fsSL https://ollama.com/install.sh | sh   (Linux)\n"
            "  brew install ollama                             (macOS)"
        ) from e
    except subprocess.CalledProcessError as e:
        raise OllamaError(f"Falha ao baixar o modelo {modelo}.") from e


class _Spinner:
    """Spinner discreto enquanto a IA pensa. Some sem deixar rastro na tela."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, texto="Buscando sugestões..."):
        self.texto = texto
        self._parar = threading.Event()
        self._t: threading.Thread | None = None

    def __enter__(self):
        if sys.stderr.isatty():
            self._t = threading.Thread(target=self._loop, daemon=True)
            self._t.start()
        return self

    def _loop(self):
        i = 0
        while not self._parar.is_set():
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stderr.write(f"\r  {frame} {self.texto}")
            sys.stderr.flush()
            i += 1
            time.sleep(0.08)

    def __exit__(self, *exc):
        self._parar.set()
        if self._t:
            self._t.join()
            sys.stderr.write("\r\033[K")  # limpa a linha do spinner
            sys.stderr.flush()


def gerar(pedido: str, modelo: str = MODELO_PADRAO) -> str:
    """
    Pede ao Ollama as 5 variações para `pedido`. Devolve a saída crua (texto).
    Levanta OllamaError em falha (serviço fora, timeout, etc.).
    """
    payload = {
        "model": modelo,
        "system": _system_prompt(),
        "prompt": f"O usuário quer: {pedido}",
        "stream": False,
        "keep_alive": KEEP_ALIVE,
        "options": {
            "temperature": 0.15,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "num_predict": 384,
        },
    }
    try:
        with _Spinner():
            resp = _http_json("/api/generate", payload, timeout=TIMEOUT)
    except urllib.error.URLError as e:
        raise OllamaError(
            "Não consegui falar com o Ollama. O serviço está rodando?\n"
            "  Linux:  systemctl status ollama\n"
            "  macOS:  abra o app do Ollama (ou: ollama serve)"
        ) from e
    except TimeoutError as e:
        raise OllamaError(
            f"Demorou demais (>{TIMEOUT}s) e foi cancelado. Tente de novo."
        ) from e

    texto = (resp.get("response") or "").strip()
    if not texto:
        raise OllamaError("O modelo não retornou nada. Tente de novo.")
    return texto
