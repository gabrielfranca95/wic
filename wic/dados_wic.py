"""
Comandos no FORMATO DO WIC (`comando ::: explicação curta`).

Mesmas chaves de `dados_comandos.py` (pra reaproveitar o match TF-IDF), mas o
valor agora é uma ou mais linhas `comando ::: explicação` — exatamente o que o
menu do wic espera. Assim os comandos pré-cadastrados aparecem no menu igual aos
que vêm do Ollama, só que instantâneos.

Regras (iguais às do wic): explicação curta (≤ 6 palavras), comando pronto para
colar, a opção mais segura/idiomática primeiro.
"""

GIT = {
    "git status estado":
        "git status ::: estado da árvore de trabalho",
    "git log historico commits":
        "git log --oneline --graph ::: histórico resumido de commits\n"
        "git log -p ::: histórico com as mudanças",
    "git add adicionar stage arquivos":
        "git add . ::: adiciona tudo ao stage\n"
        "git add <arquivo> ::: adiciona um arquivo",
    "git commit salvar mensagem":
        "git commit -m \"mensagem\" ::: salva o que está no stage\n"
        "git commit -am \"mensagem\" ::: adiciona e commita rastreados",
    "git push enviar commits repositorio remoto":
        "git push origin <branch> ::: envia commits ao remoto\n"
        "git push -u origin <branch> ::: envia e vincula a branch",
    "git pull atualizar repositorio":
        "git pull ::: traz e mescla do remoto\n"
        "git pull --rebase ::: atualiza sem commit de merge",
    "atualizar repositorio git perder alteracoes":
        "git pull --rebase --autostash ::: atualiza sem perder o trabalho\n"
        "git stash && git pull && git stash pop ::: guarda, atualiza e devolve",
    "git clone clonar repositorio":
        "git clone <url> ::: baixa um repositório remoto",
    "listar branches git":
        "git branch ::: lista branches locais\n"
        "git branch -a ::: inclui as remotas",
    "criar nova branch git":
        "git checkout -b <nome> ::: cria e troca de branch\n"
        "git switch -c <nome> ::: versão moderna",
    "trocar mudar branch checkout":
        "git switch <branch> ::: troca de branch (moderno)\n"
        "git checkout <branch> ::: troca de branch (clássico)",
    "remover deletar branch git":
        "git branch -d <nome> ::: apaga branch (segura)\n"
        "git branch -D <nome> ::: força apagar",
    "renomear branch git":
        "git branch -m <novo-nome> ::: renomeia a branch atual",
    "merge mesclar branch git":
        "git merge <branch> ::: junta a branch na atual\n"
        "git merge --no-ff <branch> ::: força commit de merge",
    "git rebase reaplicar commits":
        "git rebase <branch> ::: reaplica commits sobre a outra\n"
        "git rebase -i HEAD~3 ::: reescreve os últimos 3",
    "git stash guardar alteracoes":
        "git stash ::: guarda as mudanças\n"
        "git stash pop ::: recupera as mudanças\n"
        "git stash list ::: lista o que guardou",
    "git diff diferencas alteracoes":
        "git diff ::: mudanças não staged\n"
        "git diff --staged ::: mudanças no stage",
    "desfazer ultimo commit git":
        "git reset --soft HEAD~1 ::: desfaz commit, mantém mudanças\n"
        "git reset --hard HEAD~1 ::: desfaz commit e mudanças",
    "descartar alteracoes arquivo git":
        "git restore <arquivo> ::: descarta mudanças do arquivo\n"
        "git checkout -- <arquivo> ::: forma antiga",
    "reverter commit git":
        "git revert <hash> ::: cria commit que desfaz outro",
    "git reset hard descartar tudo":
        "git reset --hard HEAD ::: descarta tudo (cuidado!)\n"
        "git clean -fd ::: remove arquivos não rastreados",
    "adicionar remote origin git":
        "git remote add origin <url> ::: conecta a um remoto",
    "listar remotes git":
        "git remote -v ::: lista os remotos",
    "git fetch buscar remoto":
        "git fetch ::: busca do remoto sem mesclar\n"
        "git fetch --all --prune ::: busca tudo e limpa",
    "criar tag git versao":
        "git tag <nome> ::: cria tag leve\n"
        "git tag -a <nome> -m \"msg\" ::: tag anotada",
    "iniciar repositorio git init":
        "git init ::: inicializa repositório aqui",
    "configurar usuario git":
        "git config --global user.name \"Nome\" ::: define seu nome\n"
        "git config --global user.email \"email\" ::: define seu email",
    "git blame autor linha":
        "git blame <arquivo> ::: quem alterou cada linha",
    "git cherry pick commit":
        "git cherry-pick <hash> ::: aplica um commit aqui",
}

DOCKER = {
    "listar containers rodando docker":
        "docker ps ::: containers em execução\n"
        "docker ps -a ::: todos, inclusive parados",
    "listar todos containers docker parados":
        "docker ps -a ::: todos os containers",
    "listar imagens docker":
        "docker images ::: imagens locais",
    "rodar container docker imagem":
        "docker run -d <imagem> ::: roda em background\n"
        "docker run -it <imagem> bash ::: roda interativo\n"
        "docker run -p 8080:80 <imagem> ::: mapeia porta",
    "parar container docker":
        "docker stop <id> ::: para um container",
    "iniciar container docker parado":
        "docker start <id> ::: inicia container parado",
    "remover container docker":
        "docker rm <id> ::: remove container\n"
        "docker rm -f <id> ::: força remover",
    "remover imagem docker":
        "docker rmi <imagem> ::: apaga uma imagem",
    "logs container docker":
        "docker logs <id> ::: mostra os logs\n"
        "docker logs -f <id> ::: acompanha ao vivo",
    "entrar acessar container docker bash":
        "docker exec -it <id> bash ::: abre shell no container\n"
        "docker exec -it <id> sh ::: shell em imagens enxutas",
    "build construir imagem docker":
        "docker build -t <nome> . ::: constrói do Dockerfile",
    "baixar imagem docker pull":
        "docker pull <imagem> ::: baixa do registry",
    "enviar imagem docker push":
        "docker push <imagem> ::: envia ao registry",
    "docker compose subir servicos":
        "docker compose up -d ::: sobe serviços em background\n"
        "docker compose up ::: sobe vendo os logs",
    "docker compose parar remover":
        "docker compose down ::: para e remove serviços",
    "limpar docker prune liberar espaco":
        "docker system prune ::: limpa o não usado\n"
        "docker system prune -a ::: limpa tudo (cuidado!)",
    "inspecionar container docker detalhes":
        "docker inspect <id> ::: detalhes em JSON",
    "recursos cpu memoria docker stats":
        "docker stats ::: uso de CPU/memória ao vivo",
    "listar volumes docker":
        "docker volume ls ::: lista volumes",
    "listar redes docker":
        "docker network ls ::: lista redes",
}

TERMINAL = {
    "listar arquivos pasta":
        "ls -la ::: lista tudo, com ocultos\n"
        "ls -lh ::: tamanhos legíveis\n"
        "ls ::: lista simples",
    "mudar diretorio cd":
        "cd <pasta> ::: entra na pasta\n"
        "cd .. ::: sobe um nível\n"
        "cd ~ ::: vai para a home",
    "diretorio atual caminho pwd":
        "pwd ::: mostra a pasta atual",
    "criar pasta diretorio mkdir":
        "mkdir <nome> ::: cria uma pasta\n"
        "mkdir -p a/b/c ::: cria pastas aninhadas",
    "criar arquivo vazio touch":
        "touch <arquivo> ::: cria arquivo vazio",
    "remover arquivo terminal":
        "rm <arquivo> ::: apaga um arquivo",
    "remover pasta recursivo terminal":
        "rm -rf <pasta> ::: apaga pasta e conteúdo (cuidado!)",
    "copiar arquivo cp":
        "cp <origem> <destino> ::: copia um arquivo\n"
        "cp -r <origem> <destino> ::: copia uma pasta",
    "mover renomear arquivo mv":
        "mv <origem> <destino> ::: move ou renomeia",
    "conteudo arquivo cat":
        "cat <arquivo> ::: mostra o conteúdo todo\n"
        "less <arquivo> ::: navega página a página",
    "inicio primeiras linhas arquivo head":
        "head -n 20 <arquivo> ::: primeiras 20 linhas",
    "final ultimas linhas arquivo tail acompanhar":
        "tail -n 20 <arquivo> ::: últimas 20 linhas\n"
        "tail -f <arquivo> ::: acompanha em tempo real",
    "buscar filtrar texto arquivos grep":
        "grep -rn \"texto\" . ::: procura recursivo com linha\n"
        "grep -ri \"texto\" . ::: ignora maiúsculas",
    "encontrar arquivos find nome":
        "find . -name \"*.py\" ::: procura por nome\n"
        "find . -size +100M ::: procura por tamanho",
    "permissoes arquivo chmod executavel":
        "chmod +x <arquivo> ::: torna executável\n"
        "chmod 644 <arquivo> ::: leitura padrão",
    "dono arquivo chown":
        "chown usuario:grupo <arquivo> ::: muda o dono",
    "listar processos rodando ps":
        "ps aux ::: lista os processos\n"
        "htop ::: monitor interativo\n"
        "top ::: monitor padrão",
    "matar processo kill":
        "kill <pid> ::: encerra o processo\n"
        "kill -9 <pid> ::: força encerrar",
    "espaco livre disco df":
        "df -h ::: espaço livre nos discos",
    "tamanho pasta du":
        "du -sh <pasta> ::: tamanho total da pasta\n"
        "du -sh * ::: tamanho de cada item",
    "memoria ram free":
        "free -h ::: uso de memória",
    "baixar arquivo wget curl":
        "curl -O <url> ::: baixa com curl\n"
        "wget <url> ::: baixa com wget",
    "compactar zipar tar pasta":
        "tar -czvf arquivo.tar.gz <pasta> ::: cria um .tar.gz",
    "extrair descompactar tar":
        "tar -xzvf arquivo.tar.gz ::: extrai um .tar.gz",
    "historico comandos terminal":
        "history ::: comandos já digitados",
    "criar link simbolico atalho ln":
        "ln -s <alvo> <link> ::: cria atalho simbólico",
    "variavel ambiente export":
        "export VAR=valor ::: define variável da sessão",
}

# Tudo junto, no formato do wic.
COMANDOS_WIC = {**GIT, **DOCKER, **TERMINAL}

if __name__ == "__main__":
    print(f"git: {len(GIT)} | docker: {len(DOCKER)} | terminal: {len(TERMINAL)} "
          f"| total: {len(COMANDOS_WIC)}")
