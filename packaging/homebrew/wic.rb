# Fórmula do Homebrew para o wic (v2).
#
# Vai para o SEU tap: um repo no GitHub chamado `homebrew-wic`, neste caminho:
#   homebrew-wic/Formula/wic.rb
# Depois o usuário instala com:
#   brew install SEU_USUARIO/wic/wic
#
# Antes de publicar, preencha url + sha256 (veja v2/packaging/homebrew/README.md).
class Wic < Formula
  desc "Assistente de terminal local: linguagem natural -> comando de shell"
  homepage "https://github.com/SEU_USUARIO/wic"
  url "https://github.com/SEU_USUARIO/wic/archive/refs/tags/v0.2.0.tar.gz"
  sha256 "PREENCHA_O_SHA256_DO_TARBALL"
  license "MIT"

  # Dependências: o brew garante que existam antes de instalar o wic.
  depends_on "ollama"
  depends_on "python@3.12"

  def install
    # Caso o tarball tenha tudo na raiz do repo; se o código v2 ficar numa subpasta
    # `v2/`, troque os caminhos abaixo por "v2/wic", "v2/bin/wic", "v2/wic.sh".
    libexec.install "wic"                      # pacote Python -> libexec/wic
    (libexec/"bin").install "bin/wic"          # launcher      -> libexec/bin/wic
    bin.install_symlink libexec/"bin/wic"      # expõe `wic` no PATH (realpath acha o pacote)
    pkgshare.install "wic.sh"                  # wrapper opcional -> share/wic/wic.sh
  end

  def caveats
    <<~EOS
      O wic já funciona direto:  wic listar portas em uso

      (Opcional) Para que comandos como `cd`/`export` "peguem" no shell atual,
      adicione ao seu ~/.bashrc ou ~/.zshrc:

        source #{opt_pkgshare}/wic.sh

      No primeiro uso, o wic baixa o modelo local (~1 GB, uma vez só).
      Requer o serviço do Ollama no ar:
        Linux:  systemctl status ollama
        macOS:  abra o app do Ollama (ou: ollama serve)
    EOS
  end

  test do
    assert_match "wic 0.2", shell_output("#{bin}/wic --version")
    assert_path_exists pkgshare/"wic.sh"
  end
end
