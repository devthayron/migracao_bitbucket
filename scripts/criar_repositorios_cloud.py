import argparse
import logging
import sys
from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ_PROJETO))

from bitbucket_cloud import BitbucketCloud

from logger import setup_logging
from scripts.bitbucket_server import BitbucketServer

logger = logging.getLogger(__name__)

PROJETO_ORIGEM = "CRED"


class MigracaoRepositorios:
    def __init__(self, chave_projeto):
        self.chave_projeto = chave_projeto.upper()

        self.bitbucket_server = BitbucketServer()
        self.bitbucket_cloud = BitbucketCloud()

        self.slugs_origem = []
        self.existentes = {}
        self.para_criar = []
        self.ignorados = []
        self.criados = []
        self.erros = []

    def carregar_repositorios(self):
        logger.info(
            "Consultando repositórios no Bitbucket Server: %s",
            PROJETO_ORIGEM,
        )

        repositorios = self.bitbucket_server.listar_repositorios(PROJETO_ORIGEM)

        if not repositorios:
            raise ValueError(
                f"Nenhum repositório encontrado no projeto {PROJETO_ORIGEM}."
            )

        self.slugs_origem = sorted(
            {
                repo["slug"]
                for repo in repositorios
                if isinstance(repo, dict) and repo.get("slug")
            }
        )

        if not self.slugs_origem:
            raise ValueError("Nenhum slug de repositório encontrado na origem.")

        logger.info(
            "Repositórios encontrados na origem: %s",
            len(self.slugs_origem),
        )

    def analisar_repositorios(self):
        logger.info("Analisando repositórios...")

        for slug in self.slugs_origem:
            if slug in self.existentes:
                self.ignorados.append(slug)
            else:
                self.para_criar.append(slug)

        logger.info("Total na origem: %s", len(self.slugs_origem))
        logger.info("Já existentes no Cloud: %s", len(self.ignorados))
        logger.info("Pendentes de criação: %s", len(self.para_criar))

        if self.para_criar:
            logger.info("Repositórios pendentes:")

            for indice, slug in enumerate(self.para_criar, start=1):
                logger.info("%03d. %s", indice, slug)

        if self.ignorados:
            logger.info("Repositórios já existentes:")

            for indice, slug in enumerate(self.ignorados, start=1):
                logger.info("%03d. %s", indice, slug)

    def executar_criacoes(self):
        total = len(self.para_criar)

        logger.info("Iniciando criação de %s repositórios...", total)

        for indice, slug in enumerate(self.para_criar, start=1):
            logger.info(
                "[%s/%s] Criando repositório: %s",
                indice,
                total,
                slug,
            )

            try:
                sucesso, mensagem = self.bitbucket_cloud.criar_repositorio(
                    slug,
                    self.chave_projeto,
                )

                if sucesso:
                    self.criados.append(slug)
                    logger.info(
                        "Repositório criado: %s - %s",
                        slug,
                        mensagem,
                    )
                else:
                    self.erros.append({"slug": slug, "erro": mensagem})
                    logger.error(
                        "Falha ao criar %s: %s",
                        slug,
                        mensagem,
                    )

            except Exception as erro:
                self.erros.append({"slug": slug, "erro": str(erro)})
                logger.exception(
                    "Erro ao criar repositório: %s",
                    slug,
                )

    def exibir_resumo(self):
        logger.info("=" * 60)
        logger.info("RESUMO FINAL")
        logger.info("=" * 60)

        logger.info("Total na origem:          %s", len(self.slugs_origem))
        logger.info("Já existentes no Cloud:   %s", len(self.ignorados))
        logger.info("Pendentes inicialmente:   %s", len(self.para_criar))
        logger.info("Criados nesta execução:   %s", len(self.criados))
        logger.info("Erros:                    %s", len(self.erros))

        if self.erros:
            logger.error("Repositórios com erro:")

            for item in self.erros:
                logger.error(
                    "%s: %s",
                    item["slug"],
                    item["erro"],
                )

        logger.info("Processo finalizado.")

    def executar(self, confirmar=False):
        self.carregar_repositorios()

        projeto = self.bitbucket_cloud.validar_projeto(self.chave_projeto)

        logger.info("Projeto de destino: %s", projeto.get("name"))
        logger.info("Chave: %s", projeto.get("key"))
        logger.info("Workspace: %s", self.bitbucket_cloud.workspace)
        logger.info(
            "Modo: %s",
            "EXECUÇÃO REAL" if confirmar else "SIMULAÇÃO",
        )

        logger.info("Consultando repositórios existentes no Cloud...")

        self.existentes = self.bitbucket_cloud.listar_repositorios()

        logger.info(
            "Repositórios encontrados no Cloud: %s",
            len(self.existentes),
        )

        self.analisar_repositorios()

        if not confirmar:
            logger.info("SIMULAÇÃO CONCLUÍDA")
            logger.info("Nenhum repositório foi criado.")

            logger.info(
                "Para criar os repositórios pendentes, execute: "
                "python scripts/criar_repositorios_cloud.py "
                "--projeto %s --confirmar",
                self.chave_projeto,
            )

            return

        if not self.para_criar:
            logger.info("Todos os repositórios já existem no Cloud.")
            return

        self.executar_criacoes()
        self.exibir_resumo()


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Cria os repositórios da origem no Bitbucket Cloud."
    )

    parser.add_argument(
        "--projeto",
        required=True,
        help="Chave do projeto de destino no Bitbucket Cloud.",
    )

    parser.add_argument(
        "--confirmar",
        action="store_true",
        help="Confirma a criação dos repositórios.",
    )

    return parser.parse_args()


def main():
    setup_logging()

    args = configurar_argumentos()

    migracao = MigracaoRepositorios(args.projeto)
    migracao.executar(confirmar=args.confirmar)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("FALHA NO PROCESSO")
        raise
