import argparse
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from bitbucket_cloud import BitbucketCloud

from config import settings
from logger import setup_logging

logger = logging.getLogger(__name__)


class MigracaoRepositoriosGit:
    def __init__(
        self,
        chave_projeto=None,
        slug_repositorio=None,
        confirmar=False,
    ):
        self.chave_projeto = chave_projeto
        self.slug_repositorio = slug_repositorio
        self.confirmar = confirmar
        self.bitbucket = BitbucketCloud()

        self.servidor_origem = self._obter_host_origem()
        self.porta_origem = settings.BITBUCKET_SERVER_PORT
        self.chave_ssh = Path(settings.BITBUCKET_SSH_KEY).expanduser()

        self.timeout_clone = 2000
        self.timeout_push = 2000

    def _obter_host_origem(self):
        url = settings.BITBUCKET_SERVER_URL

        if not url:
            raise ValueError("BITBUCKET_SERVER_URL não configurada.")

        endereco = url if "://" in url else f"//{url}"
        servidor = urlsplit(endereco).hostname

        if not servidor:
            raise ValueError("Não foi possível identificar o servidor de origem.")

        return servidor

    def executar(self):

        if self.slug_repositorio:
            repositorios = self._buscar_repositorio()

        else:
            projeto = self.bitbucket.validar_projeto(self.chave_projeto)

            repositorios = self.bitbucket.listar_repositorios_projeto(
                self.chave_projeto
            )

            logger.info("Projeto: %s", projeto.get("name"))
            logger.info("Chave: %s", projeto.get("key"))

        logger.info("=" * 60)
        logger.info("MIGRAÇÃO DE REPOSITÓRIOS GIT")
        logger.info("=" * 60)

        logger.info("Servidor de origem: %s", self.servidor_origem)
        logger.info("Workspace destino: %s", self.bitbucket.workspace)
        logger.info("Total de repositórios: %s", len(repositorios))
        logger.info(
            "Modo: %s",
            "EXECUÇÃO REAL" if self.confirmar else "SIMULAÇÃO",
        )

        if not repositorios:
            logger.warning("Nenhum repositório encontrado.")
            return

        migrados = 0
        ignorados = 0
        simulados = 0
        sem_referencias = 0
        erros = 0

        for indice, repo in enumerate(repositorios, start=1):
            slug = repo.get("slug")

            logger.info("-" * 60)
            logger.info("[%s/%s] %s", indice, len(repositorios), slug)
            logger.info("-" * 60)

            try:
                status = self._migrar_repositorio(repo)

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
                    logger.warning(
                        "Repositório sem branches e tags. Nenhum envio realizado."
                    )

            except Exception:
                erros += 1
                logger.exception(
                    "Falha na migração do repositório: %s",
                    slug,
                )

        logger.info("=" * 60)
        logger.info("RESUMO FINAL")
        logger.info("=" * 60)

        logger.info("Total consultado:     %s", len(repositorios))
        logger.info("Migrados:             %s", migrados)
        logger.info("Já existentes:        %s", ignorados)
        logger.info("Simulados:            %s", simulados)
        logger.info("Sem referências:      %s", sem_referencias)
        logger.info("Erros:                %s", erros)

        logger.info("Processo finalizado.")

    def _buscar_repositorio(self):
        repositorios = self.bitbucket.listar_repositorios()

        repo = repositorios.get(self.slug_repositorio)

        if not repo:
            raise RuntimeError(
                f"Repositório '{self.slug_repositorio}' "
                "não encontrado no Bitbucket Cloud."
            )

        return [repo]

    def _migrar_repositorio(self, repo):
        slug = repo.get("slug")

        if slug == "gs-imagens-iso":
            return "IGNORADO"

        projeto = repo.get("project", {}).get("key")

        if not projeto:
            projeto = self.chave_projeto

        if not projeto:
            raise RuntimeError(
                f"Não foi possível identificar o projeto do repositório '{slug}'."
            )

        origem = (
            f"ssh://git@{self.servidor_origem}:"
            f"{self.porta_origem}/"
            f"{projeto.lower()}/{slug}.git"
        )

        destino = self._obter_url_destino(repo)

        logger.info("Projeto: %s", projeto)
        logger.info("Origem: %s", origem)
        logger.info("Destino: %s", destino)

        logger.info("Verificando referências pela API do Bitbucket Cloud...")

        # Verificação de destino existente desativada para permitir atualização.
        if self._repositorio_possui_referencias(slug):
            logger.info(
                "JÁ EXISTENTE - O repositório possui referências Git. "
                "Migração ignorada."
            )
            return "JÁ EXISTENTE"

        logger.info("Verificação de destino concluída.")

        if not self.confirmar:
            logger.info("Comandos que seriam executados:")
            logger.info(
                "git clone --mirror %s <diretorio_temporario>",
                origem,
            )
            logger.info("git push --mirror %s", destino)

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

    def _repositorio_possui_referencias(self, slug):
        return self.bitbucket.repositorio_possui_referencias(slug)

    def _obter_url_destino(self, repo):
        clones = repo.get("links", {}).get("clone", [])

        for clone in clones:
            if clone.get("name") == "ssh":
                return clone.get("href")

        raise RuntimeError(f"URL SSH não encontrada para '{repo.get('slug')}'.")

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


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Migra repositórios Git para o Bitbucket Cloud."
    )

    grupo = parser.add_mutually_exclusive_group(required=True)

    grupo.add_argument(
        "--projeto",
        help="Migra todos os repositórios do projeto informado.",
    )

    grupo.add_argument(
        "--repo",
        help="Migra somente um repositório pelo slug.",
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
