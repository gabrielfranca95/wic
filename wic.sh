# ─────────────────────────────────────────────────────────────────────────
# wic.sh — wrapper OPCIONAL de shell (funciona em bash E zsh).
#
# O wic já roda sozinho como binário (`wic listar portas`) e executa o comando
# escolhido. Este wrapper é só pra quem quer que comandos como `cd`/`export`
# "peguem" no shell atual (um processo filho não muda o shell pai). Ele captura
# o comando escolhido (via --print) e dá `eval` no SEU shell.
#
# Ative com:   source /caminho/para/wic.sh    (ou via caveats do Homebrew)
# ─────────────────────────────────────────────────────────────────────────

_wic_run() {
  # Sem args, ou qualquer flag/subcomando (começa com '-'): passa direto pro
  # binário — não há comando pra "evalar". Uma pergunta em linguagem natural
  # nunca começa com '-', então isto cobre --version/-v/--modo/--stats/etc. de
  # uma vez só (e qualquer flag futura, sem precisar editar este wrapper).
  case "$1" in
    ""|-*) command wic "$@"; return $? ;;
  esac

  local _cmd
  _cmd="$(command wic --print "$@")" || return $?
  [ -z "$_cmd" ] && return 0

  # Guarda no histórico do shell, se der.
  if [ -n "$ZSH_VERSION" ]; then
    print -s -- "$_cmd"
  else
    history -s -- "$_cmd" 2>/dev/null || true
  fi

  printf '\033[1;32m▶\033[0m \033[1m%s\033[0m\n' "$_cmd"
  eval "$_cmd"
}

# wic-modo: atalho equivalente ao v1.
wic-modo() { command wic --modo "$@"; }

if [ -n "$ZSH_VERSION" ]; then
  # noglob impede que *, ?, ~ no pedido sejam expandidos como arquivos.
  alias wic='noglob _wic_run'
else
  # bash: sem noglob por palavra; use aspas se o pedido tiver * ou ?.
  wic() { _wic_run "$@"; }
fi
