import argparse
import logging
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from bitbucket_cloud import BitbucketCloud

from logger import setup_logging

logger = logging.getLogger(__name__)


class ConsultaRepositorios:
    def __init__(
        self,
        chave_projeto=None,
        listar_projetos=False,
        listar_todos_repositorios=False,
    ):
        self.chave_projeto = chave_projeto
        self.listar_todos_projetos = listar_projetos
        self.listar_todos_repositorios = listar_todos_repositorios
        self.bitbucket = BitbucketCloud()

    def executar(self):

        if self.listar_todos_projetos:
            self._listar_projetos()

        elif self.listar_todos_repositorios:
            self._listar_todos_repositorios()

        else:
            self._listar_repositorios()

    def _listar_projetos(self):
        logger.info("Consultando projetos do workspace...")

        projetos = self.bitbucket.listar_projetos()

        logger.info("Workspace: %s", self.bitbucket.workspace)
        logger.info("Total de projetos: %s", len(projetos))

        if not projetos:
            logger.warning("Nenhum projeto encontrado.")
            return

        for indice, projeto in enumerate(projetos, start=1):
            logger.info(
                "%03d. %s (%s)",
                indice,
                projeto.get("name"),
                projeto.get("key"),
            )

        logger.info("Consulta finalizada.")

    def _listar_todos_repositorios(self):
        logger.info("Consultando todos os repositórios do workspace...")

        repositorios = self.bitbucket.listar_repositorios()

        logger.info("Workspace: %s", self.bitbucket.workspace)
        logger.info("Total de repositórios: %s", len(repositorios))

        if not repositorios:
            logger.warning("Nenhum repositório encontrado.")
            return

        for indice, repo in enumerate(
            sorted(
                repositorios.values(),
                key=lambda item: item.get("slug", ""),
            ),
            start=1,
        ):
            projeto = repo.get("project", {}).get("key", "SEM PROJETO")

            logger.info(
                "%03d. %s | Projeto: %s",
                indice,
                repo.get("slug"),
                projeto,
            )

        logger.info("Consulta finalizada.")

    def _listar_repositorios(self):
        logger.info(
            "Consultando repositórios do projeto: %s",
            self.chave_projeto,
        )

        projeto = self.bitbucket.validar_projeto(self.chave_projeto)

        repositorios = self.bitbucket.listar_repositorios_projeto(self.chave_projeto)

        logger.info("Projeto: %s", projeto.get("name"))
        logger.info("Chave: %s", projeto.get("key"))
        logger.info("Workspace: %s", self.bitbucket.workspace)
        logger.info("Total de repositórios: %s", len(repositorios))

        if not repositorios:
            logger.warning("Nenhum repositório encontrado no projeto.")
            return

        for indice, repo in enumerate(repositorios, start=1):
            logger.info(
                "%03d. %s (%s)",
                indice,
                repo.get("name"),
                repo.get("slug"),
            )

        logger.info("Consulta finalizada.")


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Consulta projetos e repositórios no Bitbucket Cloud."
    )

    grupo = parser.add_mutually_exclusive_group(required=True)

    grupo.add_argument(
        "--projeto",
        help="Chave do projeto para consultar seus repositórios.",
    )

    grupo.add_argument(
        "--projetos",
        action="store_true",
        help="Lista todos os projetos do workspace.",
    )

    grupo.add_argument(
        "--repositorios",
        action="store_true",
        help="Lista todos os repositórios do workspace.",
    )

    return parser.parse_args()


def main():
    setup_logging()

    args = configurar_argumentos()

    consulta = ConsultaRepositorios(
        chave_projeto=args.projeto,
        listar_projetos=args.projetos,
        listar_todos_repositorios=args.repositorios,
    )

    consulta.executar()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("FALHA NA CONSULTA")
        raise
