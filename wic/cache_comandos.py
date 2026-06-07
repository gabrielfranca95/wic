"""
Cache de respostas por palavra-chave (SQLite) para reduzir a latência da IA.

Ideia central
-------------
Antes de chamar a IA, normalizamos a pergunta, extraímos as palavras-chave e
procuramos no SQLite uma entrada parecida. Se a similaridade passar do limiar,
devolvemos a resposta guardada (milissegundos). Se não, chamamos a IA e
gravamos o novo par no cache — então a próxima pergunta parecida vira HIT.

Como medimos "parecida"
-----------------------
1. Normaliza  (minúsculas, sem acento, sem pontuação).
2. Tokeniza   (remove palavras de enchimento / stopwords).
3. Sinônimos  (cada token vira um CONCEITO canônico: "containers"≈"docker").
4. TF-IDF + cosseno: cada conceito é pesado pela sua RARIDADE no cache, e
   comparamos pergunta x entrada por similaridade de cosseno. Conceitos
   genéricos (ex.: "arquivo", em dezenas de comandos) pesam pouco; conceitos
   raros (ex.: "kubernetes") pesam muito. Assim uma pergunta vaga ("arquivos")
   não casa com confiança em nada — vira MISS e (no modo AUTO) cai pra IA.

Três modos de controle (CacheMode)
-----------------------------------
- AUTO  : tenta o cache; em MISS chama a IA e grava o resultado. (padrão)
- FORCE : SÓ usa o cache; em MISS NÃO chama a IA (retorna source="miss").
          Útil para medir cobertura do cache ou garantir custo zero.
- OFF   : ignora o cache por completo — sempre chama a IA, não lê nem grava.

A chamada de IA é injetada (parâmetro `ia_fn`), então este módulo não depende
de nenhum provedor específico. Para produção, troque o stub por uma chamada
real (ex.: SDK da Anthropic).
"""

from __future__ import annotations

import re
import json
import math
import time
import sqlite3
import unicodedata
from enum import Enum
from dataclasses import dataclass
from typing import Callable, Optional


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #

class CacheMode(str, Enum):
    AUTO = "auto"    # cache + IA (grava em miss)
    FORCE = "force"  # só cache (nunca chama IA)
    OFF = "off"      # só IA (ignora cache)


# Stopwords PT/EN comuns — removidas antes de comparar palavras-chave.
# Mantemos termos técnicos (git, docker, push, etc.) sempre.
_STOPWORDS = {
    "o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das", "no",
    "na", "nos", "nas", "em", "para", "pra", "por", "com", "que", "qual",
    "quais", "como", "e", "ou", "se", "meu", "minha", "seu", "sua", "eu",
    "voce", "vc", "tem", "ter", "fazer", "faco", "faz", "usar", "uso", "the",
    "a", "an", "of", "to", "in", "on", "for", "with", "how", "do", "i", "my",
    "is", "are", "what", "me", "quero", "mostra", "mostrar", "ver", "vejo",
    "comando", "comandos", "sem", "minhas", "minha", "meus", "meu", "as", "os",
}


# Grupos de sinônimos: termos no mesmo grupo são tratados como equivalentes.
# É o que faz "containers rodando" casar com "docker ps". Edite à vontade
# para o seu domínio — é aqui que mora a "inteligência" do match por keyword.
#
# REGRA DE OURO: cada termo aparece em UM ÚNICO grupo. Se um termo estiver em
# dois grupos, ele "fundiria" os dois conceitos e bagunçaria o match.
#
# Note a distinção proposital entre gerúndio e infinitivo:
#   "rodando/executando" (algo JÁ em execução -> listar)  != grupo de
#   "rodar/executar"     (INICIAR algo)                    -> grupos separados.
#
_GRUPOS_SINONIMOS: list[set[str]] = [
    # --- ferramentas / domínios ---
    {"docker", "container", "containers", "conteiner", "conteineres"},
    {"repositorio", "repo", "repos", "projeto", "projetos"},
    {"kubernetes", "k8s", "kube"},
    {"git", "versionamento"},
    # --- git: verbos e objetos ---
    {"status", "estado", "situacao"},
    {"commit", "commitar", "comitar"},
    {"push", "enviar", "enviando", "mandar"},
    {"pull", "atualizar", "atualizacao", "atualizo", "atualiza", "sincronizar", "puxar"},
    {"clone", "clonar"},
    {"branch", "branches", "ramo", "ramos", "ramificacao"},
    {"merge", "mesclar", "juntar"},
    {"rebase", "rebasear"},
    {"stash", "guardar", "esconder", "engavetar"},
    {"log", "logs", "historico"},
    {"diff", "diferenca", "diferencas"},
    {"checkout", "alternar", "trocar", "troco"},
    {"fetch"},
    {"tag", "tags", "etiqueta"},
    {"remote", "remoto", "origin", "github", "gitlab"},
    {"reset", "resetar"},
    {"reverter", "desfazer", "revert"},
    {"add", "adicionar", "stage", "rastrear"},
    {"blame", "autor", "culpa"},
    {"cherry", "cherrypick"},
    # --- objetos / substantivos ---
    {"alteracoes", "alteracao", "mudancas", "modificacoes", "trabalho"},
    {"perder", "perca", "perco", "descartar", "sobrescrever", "jogar", "fora"},
    {"arquivo", "arquivos", "file", "files"},
    {"pasta", "pastas", "diretorio", "diretorios", "dir"},
    {"imagens", "images", "imagem", "image"},
    {"processos", "processo", "process"},
    {"porta", "portas", "port"},
    {"volume", "volumes"},
    {"rede", "redes", "network"},
    {"recursos", "cpu", "uso"},
    {"conteudo", "texto"},
    {"variavel", "ambiente", "export", "env"},
    {"caminho", "pwd", "atual", "onde", "estou", "localizacao"},
    {"link", "simbolico", "atalho", "ln"},
    # --- verbos genéricos ---
    {"listar", "lista", "ls", "listagem"},
    {"criar", "cria", "novo", "nova", "gerar"},
    {"iniciar", "init", "inicializar", "comecar"},
    {"remover", "deletar", "apagar", "excluir", "remove", "rm"},
    {"parar", "stop", "encerrar", "finalizar"},
    {"matar", "kill"},
    {"rodando", "executando", "ativo", "ativos", "execucao", "ps"},  # listar em execução
    {"rodar", "run", "executar"},                                    # iniciar algo
    {"copiar", "copia", "cp"},
    {"mover", "mv", "renomear", "rename"},
    {"buscar", "procurar", "encontrar", "find"},
    {"filtrar", "grep"},
    {"instalar", "install", "instalacao"},
    {"baixar", "download", "wget", "curl"},
    {"compactar", "comprimir", "zipar", "tar"},
    {"extrair", "descompactar", "unzip"},
    {"permissao", "permissoes", "chmod"},
    {"dono", "owner", "chown"},
    {"espaco", "disco", "armazenamento"},
    {"memoria", "ram"},
    {"tamanho", "size"},
    {"deploy", "deployar", "implantar", "publicar", "subir"},
    {"build", "buildar", "construir", "compilar"},
    {"acompanhar", "monitorar", "seguir"},
    {"configurar", "config", "configuracao"},
    {"entrar", "acessar", "exec", "shell"},
    {"inicio", "head", "primeiras"},
    {"final", "fim", "tail", "ultimas"},
    {"inspecionar", "inspect", "detalhes"},
    {"limpar", "prune", "liberar"},
]

# Índice term -> conjunto de todos os termos equivalentes (inclui o próprio).
_SIN_INDEX: dict[str, set[str]] = {}
for _grupo in _GRUPOS_SINONIMOS:
    for _termo in _grupo:
        _SIN_INDEX.setdefault(_termo, set()).update(_grupo)


def expandir(tokens: list[str]) -> set[str]:
    """Expande cada token com seus sinônimos (usado só no pré-filtro do SQL)."""
    expandido: set[str] = set()
    for tok in tokens:
        expandido.add(tok)
        expandido.update(_SIN_INDEX.get(tok, ()))
    return expandido


def _conceito(token: str) -> str:
    """
    Mapeia um token para o seu CONCEITO canônico (um id estável por grupo de
    sinônimos). Ex.: "containers", "docker", "conteiner" -> todos viram o mesmo
    conceito. Tokens fora de qualquer grupo viram conceito de si mesmos.

    É o que permite contar "quantos comandos falam de docker" uma vez só,
    independentemente de qual sinônimo cada um usou — base do peso TF-IDF.
    """
    grupo = _SIN_INDEX.get(token)
    return min(grupo) if grupo else token


def conceitos(tokens: list[str]) -> set[str]:
    """Conjunto de conceitos canônicos de uma lista de tokens."""
    return {_conceito(t) for t in tokens}


@dataclass
class CacheResult:
    """Resultado de uma consulta ao cache/IA."""
    resposta: Optional[str]
    source: str          # "exact" | "keyword" | "ia" | "miss"
    score: float         # similaridade do melhor match (0..1)
    latencia_ms: float
    entry_id: Optional[int] = None


# --------------------------------------------------------------------------- #
# Normalização e tokenização (a parte "palavra-chave")
# --------------------------------------------------------------------------- #

def _strip_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """lowercase, sem acento, sem pontuação irrelevante, espaços colapsados."""
    texto = _strip_acentos(texto.lower())
    texto = re.sub(r"[^\w\s\-./]", " ", texto)  # mantém - . / (git/docker paths)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto


def tokenizar(texto: str) -> list[str]:
    """Palavras-chave: tokens normalizados sem stopwords, dedup preservando ordem."""
    norm = normalizar(texto)
    vistos: dict[str, None] = {}
    for tok in norm.split(" "):
        if tok and tok not in _STOPWORDS:
            vistos.setdefault(tok, None)
    return list(vistos.keys())


def similaridade(tokens_a: list[str], tokens_b: list[str]) -> float:
    """
    Similaridade por sobreposição de palavras-chave, COM expansão de sinônimos.

    Cada lado é expandido para o conjunto de conceitos equivalentes antes de
    comparar — então "containers/rodando" e "docker/ps" se sobrepõem.

    Combinamos dois sinais:
      - overlap coefficient: |A∩B| / min(|A|,|B|)  -> pega "subconjunto" bem
      - jaccard:             |A∩B| / |A∪B|          -> penaliza tamanhos díspares
    A média harmônica dos dois dá um score equilibrado em [0, 1].
    """
    if not tokens_a or not tokens_b:
        return 0.0
    sa, sb = expandir(tokens_a), expandir(tokens_b)
    inter = len(sa & sb)
    if inter == 0:
        return 0.0
    overlap = inter / min(len(sa), len(sb))
    jaccard = inter / len(sa | sb)
    return 2 * overlap * jaccard / (overlap + jaccard)


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

class CacheComandos:
    """
    Cache de respostas com backend SQLite.

    Parâmetros
    ----------
    db_path : caminho do arquivo SQLite (":memory:" para testes).
    limiar  : similaridade mínima para considerar HIT por palavra-chave (0..1).
              Com o peso TF-IDF + cosseno, 0.58 separa bem "match real" de
              "pergunta genérica demais" (esta vira MISS -> vai pra IA no AUTO).
    ttl_seg : se definido, entradas mais velhas que isso são ignoradas/expiradas.
    """

    def __init__(
        self,
        db_path: str = "cache_comandos.db",
        limiar: float = 0.58,
        ttl_seg: Optional[float] = None,
    ):
        self.limiar = limiar
        self.ttl_seg = ttl_seg
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._criar_schema()
        # Estado do TF-IDF (recalculado preguiçosamente quando o cache muda).
        self._idf: dict[str, float] = {}
        self._n_docs: int = 0
        self._idf_sujo: bool = True  # força o 1º cálculo

    def _criar_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entradas (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                pergunta     TEXT NOT NULL,
                pergunta_norm TEXT NOT NULL,
                tokens       TEXT NOT NULL,   -- JSON: lista de palavras-chave
                resposta     TEXT NOT NULL,
                negativo     INTEGER NOT NULL DEFAULT 0,  -- 1 = rejeição (não serve p/ esta pergunta)
                origem       TEXT NOT NULL DEFAULT 'user', -- 'seed' (imutável) | 'user' (curadoria)
                hits         INTEGER NOT NULL DEFAULT 0,
                criado_em    REAL NOT NULL,
                usado_em     REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_norm ON entradas(pergunta_norm);
            """
        )
        self._migrar_colunas()
        # No máximo 1 semente e 1 entrada de usuário por forma normalizada.
        try:
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_norm_origem "
                "ON entradas(pergunta_norm, origem)"
            )
        except sqlite3.OperationalError:
            pass  # dados legados com duplicatas; o índice é só uma garantia
        self.conn.commit()

    def _migrar_colunas(self) -> None:
        """Adiciona colunas novas a bancos antigos (idempotente)."""
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(entradas)")}
        if "negativo" not in cols:
            self.conn.execute(
                "ALTER TABLE entradas ADD COLUMN negativo INTEGER NOT NULL DEFAULT 0"
            )
        if "origem" not in cols:
            self.conn.execute(
                "ALTER TABLE entradas ADD COLUMN origem TEXT NOT NULL DEFAULT 'user'"
            )

    # ---- operações de baixo nível ---------------------------------------- #

    def _expirou(self, criado_em: float, agora: float) -> bool:
        return self.ttl_seg is not None and (agora - criado_em) > self.ttl_seg

    def _buscar_exato(self, norm: str, agora: float) -> Optional[sqlite3.Row]:
        # Desempate determinista: a curadoria do usuário ('user') prevalece sobre
        # a semente para a MESMA frase; entre iguais, a usada mais recentemente.
        row = self.conn.execute(
            """SELECT * FROM entradas WHERE pergunta_norm = ?
               ORDER BY (origem='user') DESC,
                        (resposta<>'' OR negativo=1) DESC,
                        usado_em DESC
               LIMIT 1""",
            (norm,),
        ).fetchone()
        if row and not self._expirou(row["criado_em"], agora):
            return row
        return None

    # ---- TF-IDF: peso por raridade do termo ------------------------------ #

    def _recalcular_idf(self) -> None:
        """
        Recalcula o IDF de cada conceito a partir de TODAS as entradas do cache.

        IDF (Inverse Document Frequency) = quão RARO um conceito é no cache.
        Um conceito que aparece em quase todo comando (ex.: "arquivo") é
        genérico -> peso baixo. Um que aparece em um só (ex.: "kubernetes")
        é distintivo -> peso alto. Assim, casar por uma palavra genérica vale
        pouco, e casar por uma palavra rara vale muito.

        Fórmula suavizada: idf = ln((N+1) / (df+1)) + 1  (sempre > 0).

        IMPORTANTE: contamos SÓ as sementes (origem='seed', não-negativas). Assim
        o que o usuário aprende/rejeita depois não altera os pesos e não regride
        as buscas que já funcionavam.
        """
        rows = self.conn.execute(
            "SELECT tokens FROM entradas WHERE origem='seed' AND negativo=0"
        ).fetchall()
        n = len(rows)
        df: dict[str, int] = {}
        for r in rows:
            for c in conceitos(json.loads(r["tokens"])):
                df[c] = df.get(c, 0) + 1
        self._n_docs = n
        self._idf = {c: math.log((n + 1) / (d + 1)) + 1.0 for c, d in df.items()}
        self._idf_sujo = False

    def _peso(self, conceito: str) -> float:
        """
        Peso IDF de um conceito.

        Conceito que NÃO existe em nenhuma entrada (palavra de enchimento, gíria,
        typo) recebe peso BAIXO (1.0): é ruído, não deve dominar nem afundar o
        score. Só conceitos que de fato aparecem no cache têm peso pela raridade.
        """
        if self._idf_sujo:
            self._recalcular_idf()
        return self._idf.get(conceito, 1.0)

    def _sim_ponderada(self, tokens_q: list[str], tokens_e: list[str]) -> float:
        """
        Similaridade de cosseno entre os vetores TF-IDF da pergunta e da entrada.

        Cada conceito vira uma dimensão com peso = IDF (raridade). O cosseno é
        o produto interno normalizado pelos tamanhos dos vetores:

            cos = Σ(idf² nos conceitos em comum) / (‖q‖ · ‖e‖)

        Por que isso resolve o caso ambíguo: se a única palavra em comum é
        genérica (idf baixo, ex.: "arquivo"), o numerador é pequeno e o cosseno
        fica baixo -> MISS. Se há um termo raro em comum (ex.: "kubernetes",
        "conteudo"), ele domina o numerador e o cosseno sobe -> HIT certeiro.
        """
        cq, ce = conceitos(tokens_q), conceitos(tokens_e)
        if not cq or not ce:
            return 0.0
        inter = cq & ce
        if not inter:
            return 0.0
        produto = sum(self._peso(c) ** 2 for c in inter)
        norma_q = math.sqrt(sum(self._peso(c) ** 2 for c in cq))
        norma_e = math.sqrt(sum(self._peso(c) ** 2 for c in ce))
        return produto / (norma_q * norma_e)

    def _buscar_keyword(
        self, tokens: list[str], agora: float
    ) -> tuple[Optional[sqlite3.Row], float]:
        """Melhor entrada POSITIVA (resposta real, não-negativa) por similaridade."""
        if not tokens:
            return None, 0.0
        # Pré-filtro barato: candidatos que citem qualquer termo equivalente
        # ao da pergunta (já expandido por sinônimos). Assim "containers" puxa
        # também linhas que guardaram "docker".
        # (Em escala maior, troque por FTS5 ou um índice invertido.)
        termos = sorted(expandir(tokens))
        like_clauses = " OR ".join(["tokens LIKE ?"] * len(termos))
        params = [f'%"{t}"%' for t in termos]
        # Só as SEMENTES fazem match amplo por cosseno. Positivos aprendidos do
        # usuário casam por subconjunto (ver _buscar_user_subset) para não poluir.
        rows = self.conn.execute(
            f"SELECT * FROM entradas WHERE ({like_clauses}) "
            f"AND resposta <> '' AND negativo = 0 AND origem = 'seed'",
            params,
        ).fetchall()

        melhor, melhor_score = None, 0.0
        for row in rows:
            if self._expirou(row["criado_em"], agora):
                continue
            score = self._sim_ponderada(tokens, json.loads(row["tokens"]))
            if score > melhor_score:
                melhor, melhor_score = row, score
        return melhor, melhor_score

    def _buscar_user_subset(
        self, tokens: list[str], agora: float
    ) -> Optional[sqlite3.Row]:
        """
        Melhor entrada POSITIVA do USUÁRIO cujos conceitos ⊆ os da pergunta
        (mesma regra de subconjunto das negativas). Serve a resposta aprendida
        para a frase e suas reformulações, sem vazar para perguntas que só
        compartilham um conceito genérico. A mais específica (mais conceitos) vence.
        """
        cq = conceitos(tokens)
        if not cq:
            return None
        termos = sorted(expandir(tokens))
        like_clauses = " OR ".join(["tokens LIKE ?"] * len(termos))
        params = [f'%"{t}"%' for t in termos]
        rows = self.conn.execute(
            f"SELECT * FROM entradas WHERE origem='user' AND negativo=0 "
            f"AND resposta<>'' AND ({like_clauses})",
            params,
        ).fetchall()
        cands = []
        for row in rows:
            if self._expirou(row["criado_em"], agora):
                continue
            cn = conceitos(json.loads(row["tokens"]))
            if len(cn) >= 2 and cn <= cq:
                cands.append((len(cn), row["usado_em"], row))
        if not cands:
            return None
        cands.sort(key=lambda t: (t[0], t[1]), reverse=True)
        return cands[0][2]

    def _suprimido_por_negativa(self, tokens: list[str], agora: float) -> bool:
        """
        True se alguma REJEIÇÃO (negativo=1) cobre esta pergunta.

        Regra (subconjunto de conceitos): uma negativa com ≥2 conceitos suprime
        a pergunta quando TODOS os seus conceitos estão presentes na pergunta.
        Ex.: rejeitar "baixar homebrew" {baixar,homebrew} suprime "baixar o
        homebrew" e "como baixar o homebrew no mac" (contêm baixar+homebrew),
        mas NÃO "baixar node" nem "baixar gemini cli" (não têm 'homebrew').
        O mínimo de 2 conceitos evita que uma rejeição de 1 palavra ("docker")
        bloqueie tudo que cita aquela palavra.
        """
        cq = conceitos(tokens)
        if not cq:
            return False
        termos = sorted(expandir(tokens))
        like_clauses = " OR ".join(["tokens LIKE ?"] * len(termos))
        params = [f'%"{t}"%' for t in termos]
        rows = self.conn.execute(
            f"SELECT tokens, criado_em FROM entradas "
            f"WHERE negativo = 1 AND ({like_clauses})",
            params,
        ).fetchall()
        for row in rows:
            if self._expirou(row["criado_em"], agora):
                continue
            cn = conceitos(json.loads(row["tokens"]))
            if len(cn) >= 2 and cn <= cq:   # negativa ⊆ pergunta
                return True
        return False

    def _registrar_hit(self, entry_id: int, agora: float) -> None:
        self.conn.execute(
            "UPDATE entradas SET hits = hits + 1, usado_em = ? WHERE id = ?",
            (agora, entry_id),
        )
        self.conn.commit()

    def inserir(self, pergunta: str, resposta: str,
                negativo: int = 0, origem: str = "user") -> int:
        agora = time.time()
        cur = self.conn.execute(
            """INSERT INTO entradas
               (pergunta, pergunta_norm, tokens, resposta, negativo, origem,
                hits, criado_em, usado_em)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)""",
            (
                pergunta,
                normalizar(pergunta),
                json.dumps(tokenizar(pergunta)),
                resposta,
                negativo,
                origem,
                agora,
                agora,
            ),
        )
        self.conn.commit()
        if origem == "seed":
            self._idf_sujo = True  # IDF é calculado só sobre as sementes
        return cur.lastrowid

    def upsert(self, pergunta: str, resposta: str, negativo: int = 0) -> int:
        """
        Insere/substitui uma entrada de USUÁRIO, chaveada pela forma normalizada.
        NUNCA toca nas sementes (origem='seed') — a curadoria do usuário convive
        como uma linha separada, sem destruir o catálogo compartilhado.
        """
        norm = normalizar(pergunta)
        self.conn.execute(
            "DELETE FROM entradas WHERE pergunta_norm = ? AND origem = 'user'", (norm,)
        )
        return self.inserir(pergunta, resposta, negativo=negativo, origem="user")

    def atualizar(self, entry_id: int, resposta: str) -> None:
        """Troca a resposta de uma entrada existente (ex.: remover opções ruins)."""
        self.conn.execute(
            "UPDATE entradas SET resposta = ?, usado_em = ? WHERE id = ?",
            (resposta, time.time(), entry_id),
        )
        self.conn.commit()
        # Os tokens (pergunta) não mudaram, então o IDF continua válido.

    def remover(self, entry_id: int) -> int:
        """Apaga uma entrada pelo id (ex.: resposta toda errada). Retorna nº removido."""
        cur = self.conn.execute("DELETE FROM entradas WHERE id = ?", (entry_id,))
        self.conn.commit()
        self._idf_sujo = True  # uma entrada saiu -> IDF muda
        return cur.rowcount

    # ---- API principal ---------------------------------------------------- #

    def consultar(
        self,
        pergunta: str,
        ia_fn: Callable[[str], str],
        modo: CacheMode = CacheMode.AUTO,
    ) -> CacheResult:
        """
        Responde uma pergunta respeitando o modo escolhido.

        ia_fn: função que recebe a pergunta e devolve a resposta da IA.
        """
        t0 = time.perf_counter()
        agora = time.time()

        def _ms() -> float:
            return (time.perf_counter() - t0) * 1000

        # OFF: ignora o cache totalmente -> sempre IA, sem ler nem gravar.
        if modo == CacheMode.OFF:
            resposta = ia_fn(pergunta)
            return CacheResult(resposta, "ia", 0.0, _ms())

        # --- tentativa de HIT no cache (AUTO e FORCE leem) --- #
        norm = normalizar(pergunta)
        tokens = tokenizar(pergunta)
        score = 0.0
        resposta_cache = None
        fonte = "miss"
        eid = None

        exato = self._buscar_exato(norm, agora)
        if exato is not None and not exato["negativo"]:
            # match exato positivo -> HIT
            self._registrar_hit(exato["id"], agora)
            resposta_cache, fonte, score, eid = exato["resposta"], "exact", 1.0, exato["id"]
        elif exato is not None and exato["negativo"]:
            # rejeição explícita para ESTA frase -> MISS, sem cair no keyword
            fonte = "miss"
        elif self._suprimido_por_negativa(tokens, agora):
            # uma rejeição parecida cobre esta pergunta -> MISS (vai pra IA)
            fonte = "miss"
        else:
            up = self._buscar_user_subset(tokens, agora)
            if up is not None:
                # resposta aprendida do usuário (frase ou reformulação dela)
                self._registrar_hit(up["id"], agora)
                resposta_cache, fonte, score, eid = up["resposta"], "user", 1.0, up["id"]
            else:
                kw, score = self._buscar_keyword(tokens, agora)
                if kw is not None and score >= self.limiar:
                    self._registrar_hit(kw["id"], agora)
                    resposta_cache, fonte, eid = kw["resposta"], "keyword", kw["id"]

        if fonte != "miss":
            return CacheResult(resposta_cache, fonte, score, _ms(), eid)

        # --- MISS --- #
        if modo == CacheMode.FORCE:
            # Só cache: não chamamos a IA. Quem chamou decide o que fazer.
            return CacheResult(None, "miss", score, _ms())

        # AUTO: chama a IA e aprende (entrada de usuário).
        resposta = ia_fn(pergunta)
        entry_id = self.upsert(pergunta, resposta)
        return CacheResult(resposta, "ia", score, _ms(), entry_id)

    # ---- manutenção ------------------------------------------------------- #

    def expirar_velhas(self) -> int:
        """Remove fisicamente entradas além do TTL. Retorna quantas saíram."""
        if self.ttl_seg is None:
            return 0
        limite = time.time() - self.ttl_seg
        cur = self.conn.execute("DELETE FROM entradas WHERE criado_em < ?", (limite,))
        self.conn.commit()
        self._idf_sujo = True
        return cur.rowcount

    def evictar_lru(self, max_entradas: int) -> int:
        """Mantém só as `max_entradas` mais recentemente usadas (descarta o resto)."""
        cur = self.conn.execute(
            """DELETE FROM entradas WHERE id NOT IN (
                   SELECT id FROM entradas ORDER BY usado_em DESC LIMIT ?
               )""",
            (max_entradas,),
        )
        self.conn.commit()
        self._idf_sujo = True
        return cur.rowcount

    def stats(self) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) n, COALESCE(SUM(hits),0) hits FROM entradas"
        ).fetchone()
        return {"entradas": row["n"], "hits_totais": row["hits"]}

    def seed(self, pares: dict[str, str]) -> None:
        """Pré-popula o cache com comandos canônicos (git, docker, etc.) imutáveis."""
        for pergunta, resposta in pares.items():
            norm = normalizar(pergunta)
            existe = self.conn.execute(
                "SELECT 1 FROM entradas WHERE pergunta_norm=? AND origem='seed' LIMIT 1",
                (norm,),
            ).fetchone()
            if not existe:
                self.inserir(pergunta, resposta, origem="seed")

    def close(self) -> None:
        self.conn.close()


# --------------------------------------------------------------------------- #
# Demonstração
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    # IA DESLIGADA: rodamos em modo FORCE (só cache). Se a IA fosse chamada,
    # este stub estouraria — é a prova de que nenhuma resposta veio da IA.
    def ia_proibida(_pergunta: str) -> str:
        raise RuntimeError("IA não deveria ser chamada no modo FORCE!")

    cache = CacheComandos(db_path=":memory:", limiar=0.5)

    # Comandos principais pré-carregados (o cache canônico).
    cache.seed({
        "git status": "Mostra o estado da árvore de trabalho: `git status`.",
        "git push origin": "Envia commits para o remoto: `git push origin <branch>`.",
        "git log": "Histórico de commits: `git log --oneline`.",
        "docker ps": "Lista containers em execução: `docker ps` (use -a para todos).",
        "docker images": "Lista imagens locais: `docker images`.",
        "listar arquivos pastas": "Lista arquivos e pastas: `ls -la`.",
        "deploy kubernetes": "Aplica os manifests: `kubectl apply -f .`.",
        # Duas entradas para o MESMO verbo "atualizar", com intenções diferentes:
        "atualizar repositorio git": "Traz as mudanças do remoto: `git pull`.",
        "atualizar repositorio git perder alteracoes": (
            "Sem perder seu trabalho: `git stash` → `git pull` → `git stash pop` "
            "(ou, num passo só: `git pull --rebase --autostash`)."
        ),
    })

    # Perguntas em LINGUAGEM NATURAL (variações dos comandos canônicos).
    # Tudo em FORCE: ou bate no cache, ou retorna "miss" — nunca chama IA.
    perguntas = [
        # --- as duas frases que você escreveu ---
        "qual comando para listar as pastas?",
        "como atualizar meu repositorio git sem perder as minhas alteracoes?",
        # --- e a variação genérica, pra mostrar a diferença de intenção ---
        "como atualizar meu repositorio git?",
        # --- demais variações ---
        "como vejo os containers rodando?",  # sinônimos -> docker ps
        "quero enviar meus commits",         # sinônimos -> git push
        "ver o historico do git",            # sinônimos -> git log
        "qual a previsao do tempo amanha?",  # sem relação -> miss (sem IA)
    ]

    print("=== MODO FORCE — somente cache, IA desligada ===\n")
    hits = 0
    for p in perguntas:
        r = cache.consultar(p, ia_proibida, CacheMode.FORCE)
        marca = "HIT " if r.source != "miss" else "MISS"
        if r.source != "miss":
            hits += 1
        print(f"  [{marca}|{r.source:7}] score={r.score:.2f} {r.latencia_ms:6.2f}ms | {p}")
        print(f"           -> {r.resposta}")

    print(f"\n  Cobertura: {hits}/{len(perguntas)} perguntas atendidas só pelo cache.")
    print(" ", cache.stats())
    cache.close()
