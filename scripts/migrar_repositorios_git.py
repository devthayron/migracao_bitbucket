import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from bitbucket_cloud import BitbucketCloud

from config import settings
from logger import setup_logging
from scripts.bitbucket_server import BitbucketServer

logger = logging.getLogger(__name__)

PROJETO_ORIGEM = "CRED"


class MigracaoRepositoriosGit:
    def __init__(
        self,
        chave_projeto=None,
        slug_repositorio=None,
        confirmar=False,
    ):
        self.chave_projeto = (chave_projeto or PROJETO_ORIGEM).upper()
        self.slug_repositorio = slug_repositorio
        self.confirmar = confirmar

        self.bitbucket_server = BitbucketServer()
        self.bitbucket_cloud = BitbucketCloud()

        self.repositorios_cloud = {}

        self.chave_ssh = Path(settings.BITBUCKET_SSH_KEY).expanduser()

        self.timeout_clone = 2000
        self.timeout_push = 2000

        self.nao_encontrados = []
        self.projeto_incorreto = []

    def executar(self):
        logger.info("Consultando repositórios no Bitbucket Server...")

        repositorios_origem = self.bitbucket_server.listar_repositorios(PROJETO_ORIGEM)

        if self.slug_repositorio:
            repositorios_origem = [
                repo
                for repo in repositorios_origem
                if repo.get("slug") == self.slug_repositorio
            ]

            if not repositorios_origem:
                raise RuntimeError(
                    f"Repositório '{self.slug_repositorio}' "
                    f"não encontrado no projeto {PROJETO_ORIGEM} do Server."
                )

        if not repositorios_origem:
            logger.warning("Nenhum repositório encontrado na origem.")
            return

        logger.info(
            "Total de repositórios encontrados no Server: %s",
            len(repositorios_origem),
        )

        # Consulta individual ou consulta geral no Cloud.
        if self.slug_repositorio:
            logger.info(
                "Consultando repositório '%s' no Bitbucket Cloud...",
                self.slug_repositorio,
            )

            repo = self.bitbucket_cloud.obter_repositorio(self.slug_repositorio)

            self.repositorios_cloud = {repo["slug"]: repo} if repo else {}

        else:
            logger.info("Consultando TODOS os repositórios do Bitbucket Cloud...")

            self.repositorios_cloud = self.bitbucket_cloud.listar_repositorios()

        logger.info(
            "Total de repositórios encontrados no Cloud: %s",
            len(self.repositorios_cloud),
        )

        projeto = self.bitbucket_cloud.validar_projeto(self.chave_projeto)

        logger.info("=" * 60)
        logger.info("MIGRAÇÃO DE REPOSITÓRIOS GIT")
        logger.info("=" * 60)

        logger.info("Projeto de origem: %s", PROJETO_ORIGEM)
        logger.info("Projeto de destino: %s", projeto.get("name"))
        logger.info("Chave de destino: %s", projeto.get("key"))
        logger.info("Workspace: %s", self.bitbucket_cloud.workspace)

        logger.info(
            "Modo: %s",
            "EXECUÇÃO REAL" if self.confirmar else "SIMULAÇÃO",
        )

        logger.info("Total na origem: %s", len(repositorios_origem))

        migrados = 0
        ignorados = 0
        simulados = 0
        sem_referencias = 0
        erros = 0

        for indice, repo_origem in enumerate(
            repositorios_origem,
            start=1,
        ):
            slug = repo_origem.get("slug")

            logger.info("-" * 60)
            logger.info(
                "[%s/%s] %s",
                indice,
                len(repositorios_origem),
                slug,
            )
            logger.info("-" * 60)

            try:
                repo_destino = self._validar_repositorio_destino(slug)

                if not repo_destino:
                    continue

                status = self._migrar_repositorio(
                    repo_origem,
                    repo_destino,
                )

                if status == "MIGRADO":
                    migrados += 1
                    logger.info("Migração concluída com sucesso.")

                elif status == "JÁ EXISTENTE":
                    ignorados += 1
                    logger.info("Repositório ignorado.")

                elif status == "SIMULADO":
                    simulados += 1
                    logger.info("Simulação concluída.")

                elif status == "SEM REFERENCIAS":
                    sem_referencias += 1
                    logger.warning("Repositório sem branches e tags.")

                elif status == "IGNORADO":
                    ignorados += 1
                    logger.warning("Repositório ignorado.")

            except Exception:
                erros += 1
                logger.exception(
                    "Falha na migração do repositório: %s",
                    slug,
                )

        self.exibir_resumo(
            total=len(repositorios_origem),
            migrados=migrados,
            ignorados=ignorados,
            simulados=simulados,
            sem_referencias=sem_referencias,
            erros=erros,
        )

    def _validar_repositorio_destino(self, slug):
        repo = self.repositorios_cloud.get(slug)

        if not repo:
            self.nao_encontrados.append(slug)

            logger.warning(
                "NÃO ENCONTRADO NO CLOUD: %s",
                slug,
            )

            return None

        projeto = repo.get("project") or {}

        chave_projeto = projeto.get("key")
        nome_projeto = projeto.get("name", "SEM NOME")

        if chave_projeto != self.chave_projeto:
            self.projeto_incorreto.append(
                {
                    "slug": slug,
                    "projeto": nome_projeto,
                    "chave": chave_projeto,
                }
            )

            logger.warning(
                "PROJETO INCORRETO: %s | Encontrado em: %s (%s) | Esperado: %s",
                slug,
                nome_projeto,
                chave_projeto,
                self.chave_projeto,
            )

            return None

        logger.info(
            "DESTINO VALIDADO: %s | Projeto: %s (%s)",
            slug,
            nome_projeto,
            chave_projeto,
        )

        return repo

    def _migrar_repositorio(self, repo_origem, repo_destino):
        slug = repo_origem.get("slug")

        # Exclusão temporária mantida do código original.
        if slug == "gs-imagens-iso":
            logger.warning(
                "Repositório %s está configurado para ser ignorado.",
                slug,
            )
            return "IGNORADO"

        origem = self._obter_url_origem(repo_origem)
        destino = self._obter_url_destino(repo_destino)

        logger.info("Origem: %s", origem)
        logger.info("Destino: %s", destino)

        # Verificação controlada pelo .env.
        if settings.VERIFICAR_REFERENCIAS_DESTINO:
            logger.info("Verificando referências no destino...")

            if self._repositorio_possui_referencias(slug):
                logger.warning(
                    "JÁ EXISTENTE - O repositório possui referências Git. "
                    "Migração ignorada."
                )
                return "JÁ EXISTENTE"

        else:
            logger.warning(
                "Verificação de referências desativada. "
                "O destino poderá ter referências substituídas ou removidas."
            )

        if not self.confirmar:
            logger.info("Comandos que seriam executados:")

            logger.info(
                "git clone --mirror %s <diretorio_temporario>",
                origem,
            )

            logger.info(
                "git push --mirror %s",
                destino,
            )

            return "SIMULADO"

        with tempfile.TemporaryDirectory() as diretorio:
            caminho_repositorio = Path(diretorio) / f"{slug}.git"

            logger.info("Clonando repositório do Bitbucket Server...")

            self._executar_comando(
                [
                    "git",
                    "clone",
                    "--mirror",
                    origem,
                    str(caminho_repositorio),
                ],
                timeout=self.timeout_clone,
            )

            logger.info("Verificando referências na origem...")

            if not self._possui_referencias_locais(caminho_repositorio):
                logger.warning(
                    "SEM REFERÊNCIAS - O repositório não possui branches nem tags."
                )
                return "SEM REFERENCIAS"

            logger.info("Referências encontradas na origem.")

            logger.info("Enviando repositório para o Bitbucket Cloud...")

            self._executar_comando(
                [
                    "git",
                    "-C",
                    str(caminho_repositorio),
                    "push",
                    "--mirror",
                    destino,
                ],
                timeout=self.timeout_push,
            )

        return "MIGRADO"

    def _obter_url_origem(self, repo):
        clones = repo.get("links", {}).get("clone", [])

        for clone in clones:
            if clone.get("name") == "ssh":
                return clone.get("href")

        raise RuntimeError(
            f"URL SSH de origem não encontrada para '{repo.get('slug')}'."
        )

    def _obter_url_destino(self, repo):
        clones = repo.get("links", {}).get("clone", [])

        for clone in clones:
            if clone.get("name") == "ssh":
                return clone.get("href")

        raise RuntimeError(
            f"URL SSH de destino não encontrada para '{repo.get('slug')}'."
        )

    def _repositorio_possui_referencias(self, slug):
        return self.bitbucket_cloud.repositorio_possui_referencias(slug)

    def _possui_referencias_locais(self, caminho_repositorio):
        resultado = subprocess.run(
            [
                "git",
                "-C",
                str(caminho_repositorio),
                "for-each-ref",
                "--format=%(refname)",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )

        return bool(resultado.stdout.strip())

    def _executar_comando(self, comando, timeout=90):
        if not self.chave_ssh.exists():
            raise FileNotFoundError(f"Chave SSH não encontrada: {self.chave_ssh}")

        env = os.environ.copy()

        env["GIT_SSH_COMMAND"] = f'ssh -i "{self.chave_ssh}" -o IdentitiesOnly=yes'

        resultado = subprocess.run(
            comando,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if resultado.stdout:
            logger.info("%s", resultado.stdout.strip())

        if resultado.returncode != 0:
            raise RuntimeError(
                resultado.stderr.strip() or "Erro ao executar comando Git."
            )

    def exibir_resumo(
        self,
        total,
        migrados,
        ignorados,
        simulados,
        sem_referencias,
        erros,
    ):
        logger.info("=" * 60)
        logger.info("RESUMO FINAL")
        logger.info("=" * 60)

        logger.info("Total consultado:          %s", total)
        logger.info("Migrados:                  %s", migrados)
        logger.info("Já existentes:             %s", ignorados)
        logger.info("Simulados:                 %s", simulados)
        logger.info("Sem referências:           %s", sem_referencias)
        logger.info("Não encontrados no Cloud:  %s", len(self.nao_encontrados))
        logger.info("Em projetos diferentes:    %s", len(self.projeto_incorreto))
        logger.info("Erros:                     %s", erros)

        if self.projeto_incorreto:
            logger.info("=" * 60)
            logger.info("REPOSITÓRIOS EM PROJETOS DIFERENTES")
            logger.info("=" * 60)

            for item in self.projeto_incorreto:
                logger.warning(
                    "%s | Projeto: %s | Chave: %s",
                    item["slug"],
                    item["projeto"],
                    item["chave"],
                )

        if self.nao_encontrados:
            logger.info("=" * 60)
            logger.info("REPOSITÓRIOS NÃO ENCONTRADOS NO CLOUD")
            logger.info("=" * 60)

            for slug in self.nao_encontrados:
                logger.warning("%s", slug)

        logger.info("Processo finalizado.")


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Migra repositórios Git para o Bitbucket Cloud."
    )

    grupo = parser.add_mutually_exclusive_group(required=True)

    grupo.add_argument(
        "--projeto",
        help="Projeto de origem no Server e destino no Cloud.",
    )

    grupo.add_argument(
        "--repo",
        help="Migra somente um repositório pelo slug, dentro do projeto CRED.",
    )

    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Executa a migração real. Sem essa opção, apenas simula.",
    )

    return parser.parse_args()


def main():
    setup_logging()

    args = configurar_argumentos()

    migracao = MigracaoRepositoriosGit(
        chave_projeto=args.projeto,
        slug_repositorio=args.repo,
        confirmar=args.confirmar,
    )

    migracao.executar()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("FALHA NA MIGRAÇÃO")
        raise
