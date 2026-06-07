# wic v2 — standalone, cross-shell, Homebrew-ready

Reescrita do `wic` como **programa Python** (não mais função de zsh). Roda igual
em **bash e zsh**, **Linux e macOS**, e reaproveita o motor de cache semântico
do v1 (`cache_comandos.py`) sem mudanças.

## O que muda em relação ao v1

| | v1 | v2 |
|---|---|---|
| Forma | função de zsh (`source` no `.zshrc`) | binário Python (PATH) |
| Shell | só zsh | **bash e zsh** |
| Ollama | `ollama run` (subprocesso por chamada) | **API HTTP** (`/api/generate`, keep-alive) |
| Modelo calibrado | `ollama create wic` (passo extra) | **dispensado** — system prompt vai no request |
| Cache | spawna `python3 wic_cache.py` por consulta | motor **no mesmo processo** (mais rápido) |
| `cd`/`export` | funciona (roda no shell) | via wrapper opcional (`wic.sh`) |
| Distribuição | `curl \| bash` (Linux) | **Homebrew** (Mac + Linux) |

Sem dependências de pip — **só a stdlib** (`urllib`, `sqlite3`, `termios`…),
o que mantém a fórmula do Homebrew limpa.

## Estrutura

```
v2/
  wic/                  pacote Python
    cli.py              orquestração (a lógica do antigo wic())
    ollama_client.py    fala com o Ollama via HTTP + spinner + auto-pull
    menu.py             menu interativo (termios, /dev/tty) — bash e zsh
    parsing.py          "comando ::: explicação" -> pares
    modes.py            modo wic|cache|ia (persistido)
    cache_comandos.py   motor TF-IDF (copiado do v1, sem mudar)
    dados_wic.py        76 comandos canônicos (copiado do v1)
  bin/wic               launcher (acha o pacote e chama o CLI)
  wic.sh                wrapper de shell OPCIONAL (cd/export + histórico)
  packaging/homebrew/wic.rb   fórmula pronta p/ o tap
```

## Rodar localmente (antes do Homebrew)

```bash
cd v2

# uso direto — executa o comando escolhido (qualquer shell, sem source):
./bin/wic listar portas em uso
./bin/wic encontrar arquivos maiores que 100MB

# subcomandos:
./bin/wic --modo            # mostra o modo (wic|cache|ia)
./bin/wic --modo cache      # só cache, sem IA
./bin/wic --stats           # estado do cache
./bin/wic --seed            # (re)popula os comandos canônicos
```

Para `cd`/`export` "pegarem" no shell atual, ative o wrapper opcional:

```bash
source ./wic.sh
wic ir para a pasta home   # agora um `cd` resultante persiste
```

## Ajustes (variáveis de ambiente)

| Variável | Padrão | Para quê |
|---|---|---|
| `WIC_OLLAMA_MODEL` | `qwen2.5-coder:1.5b` | modelo local |
| `WIC_OLLAMA_HOST` | `http://127.0.0.1:11434` | endereço do Ollama |
| `WIC_TIMEOUT` | `60` | segundos antes de desistir |
| `WIC_KEEP_ALIVE` | `10m` | mantém o modelo quente |
| `WIC_MODO` | `wic` | força o modo |
| `WIC_CACHE_DB` | `~/.config/wic/wic_cache.db` | banco do cache |

## Estado

- ✅ Motor de cache, modos, auto-seed, parser, API HTTP do Ollama: testados.
- ⏳ Menu interativo: precisa de teste ao vivo num terminal (teclas reais).
