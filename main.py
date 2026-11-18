import argparse
import logging

from logger import setup_logging
from scripts.migrar_repositorios_git import MigracaoRepositoriosGit

logger = logging.getLogger(__name__)


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Migra repositórios Git para o Bitbucket Cloud."
    )

    grupo = parser.add_mutually_exclusive_group(required=True)

    grupo.add_argument(
        "--projeto",
        help="Chave do projeto de destino no Cloud.",
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

    MigracaoRepositoriosGit(
        chave_projeto=args.projeto,
        slug_repositorio=args.repo,
        confirmar=args.confirmar,
    ).executar()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("FALHA NA MIGRAÇÃO")
        raise
