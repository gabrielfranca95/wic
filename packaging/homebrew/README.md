# Publicar o wic no Homebrew (via tap)

Sem aprovação de ninguém: um tap é só um repo seu. O usuário final instala com
`brew install gabrielfranca95/tap/wic` — no Mac **e** no Linux.

## Passo a passo

### 1. Repo de código com uma release
O wic (a pasta `v2/`) precisa virar um repo no GitHub com uma **tag**:

```bash
# na raiz do código do wic
git init && git add -A && git commit -m "wic v2"
git tag v0.2.0
git remote add origin git@github.com:gabrielfranca95/wic.git
git push -u origin main --tags
```

A tag gera, de graça, este tarball:
`https://github.com/gabrielfranca95/wic/archive/refs/tags/v0.2.0.tar.gz`

### 2. Calcular o sha256 do tarball
```bash
curl -fsSL https://github.com/gabrielfranca95/wic/archive/refs/tags/v0.2.0.tar.gz \
  | shasum -a 256
```
Cole o resultado no campo `sha256` de `wic.rb` (a `url` e a `homepage` já
apontam para o seu repo `gabrielfranca95/wic`).

> Se o código do wic ficar dentro de uma subpasta `v2/` no repo, ajuste os
> caminhos do `def install` (comentário na própria fórmula).

### 3. Criar o tap
Um repo no GitHub **obrigatoriamente** chamado `homebrew-tap`, com a fórmula em
`Formula/wic.rb`:

```bash
mkdir -p homebrew-tap/Formula
cp wic.rb homebrew-tap/Formula/wic.rb     # já com url+sha256 preenchidos
cd homebrew-tap
git init && git add -A && git commit -m "wic formula"
git remote add origin git@github.com:gabrielfranca95/homebrew-tap.git
git push -u origin main
```

### 4. Instalar e testar
```bash
brew install gabrielfranca95/tap/wic     # baixa, resolve ollama+python, instala
wic listar portas em uso             # 1º uso baixa o modelo (~1 GB)
brew test wic                        # roda o bloco test do
```

### 5. Lançar versões novas
Toda vez que mexer no código:
```bash
git tag v0.2.1 && git push --tags                 # no repo de código
# no homebrew-tap: atualize url (v0.2.1) + sha256 e dê push
```
Os usuários atualizam com `brew upgrade`.

## Subir pro homebrew-core (depois, se ficar popular)
O `brew install wic` puro exige notoriedade (estrelas/forks) e passar no
`brew audit --strict`. Comece pelo tap; o core vira viável quando houver
usuários. Veja a discussão no histórico do projeto.