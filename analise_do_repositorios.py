import argparse
import csv
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

RAIZ_PROJETO = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ_PROJETO))

from config import settings
from logger import setup_logging

logger = logging.getLogger(__name__)


class InventarioRepositorios:
    def __init__(self, projeto):
        self.projeto = projeto.lower()

        self.diretorio_data = RAIZ_PROJETO / "data" / self.projeto

        self.arquivo_json = self.diretorio_data / "repositorios.json"

        self.arquivo_csv = self.diretorio_data / "inventario.csv"

        self.chave_ssh = settings.BITBUCKET_SSH_KEY.expanduser()
        self.servidor = self._obter_host_origem()
        self.porta = settings.BITBUCKET_SERVER_PORT

    def _obter_host_origem(self):
        url = settings.BITBUCKET_SERVER_URL

        endereco = url if "://" in url else f"//{url}"
        servidor = urlsplit(endereco).hostname

        if not servidor:
            raise ValueError("Não foi possível identificar o servidor de origem.")

        return servidor

    def carregar_repositorios(self):
        if not self.chave_ssh.exists():
            raise FileNotFoundError(f"Chave SSH não encontrada: {self.chave_ssh}")

        if not self.arquivo_json.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {self.arquivo_json}")

        dados = json.loads(self.arquivo_json.read_text(encoding="utf-8"))

        if isinstance(dados, dict):
            repositorios = dados.get("values", [])
        elif isinstance(dados, list):
            repositorios = dados
        else:
            raise ValueError("Formato inesperado do JSON.")

        slugs = []

        for repositorio in repositorios:
            if isinstance(repositorio, dict):
                slug = repositorio.get("slug")
            else:
                slug = str(repositorio)

            if slug:
                slugs.append(slug)

        slugs = list(dict.fromkeys(slugs))

        if not slugs:
            raise ValueError("Nenhum repositório encontrado no JSON.")

        return slugs

    def consultar_repositorios(self, slugs):
        env = os.environ.copy()
        env["GIT_SSH_COMMAND"] = f'ssh -i "{self.chave_ssh}" -o IdentitiesOnly=yes'

        inventario = []
        total = len(slugs)

        logger.info("Projeto: %s", self.projeto)
        logger.info("Servidor: %s", self.servidor)
        logger.info("Total de repositórios: %s", total)

        for indice, nome in enumerate(slugs, start=1):
            logger.info(
                "[%s/%s] Consultando: %s",
                indice,
                total,
                nome,
            )

            url = f"ssh://git@{self.servidor}:{self.porta}/{self.projeto}/{nome}.git"

            try:
                resultado = subprocess.run(
                    [
                        "git",
                        "ls-remote",
                        "--heads",
                        "--tags",
                        url,
                    ],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )

                if resultado.returncode != 0:
                    erro = resultado.stderr.strip()

                    logger.error(
                        "Falha ao consultar %s: %s",
                        nome,
                        erro,
                    )

                    inventario.append(
                        {
                            "repositorio": nome,
                            "status": "ERRO",
                            "quantidade_branches": 0,
                            "branches": "",
                            "quantidade_tags": 0,
                            "tags": "",
                            "erro": erro,
                        }
                    )

                    continue

                branches = []
                tags = []

                for linha in resultado.stdout.splitlines():
                    hash_commit, referencia = linha.split("\t", 1)

                    if referencia.startswith("refs/heads/"):
                        branch = referencia.removeprefix("refs/heads/")
                        branches.append(f"{branch} ({hash_commit})")

                    elif referencia.startswith("refs/tags/"):
                        if referencia.endswith("^{}"):
                            continue

                        tag = referencia.removeprefix("refs/tags/")
                        tags.append(f"{tag} ({hash_commit})")

                logger.info(
                    "Consultado: %s | Branches: %s | Tags: %s",
                    nome,
                    len(branches),
                    len(tags),
                )

                inventario.append(
                    {
                        "repositorio": nome,
                        "status": "ACESSIVEL",
                        "quantidade_branches": len(branches),
                        "branches": "; ".join(branches),
                        "quantidade_tags": len(tags),
                        "tags": "; ".join(tags),
                        "erro": "",
                    }
                )

            except subprocess.TimeoutExpired:
                logger.error(
                    "Timeout ao consultar o repositório: %s",
                    nome,
                )

                inventario.append(
                    {
                        "repositorio": nome,
                        "status": "TIMEOUT",
                        "quantidade_branches": 0,
                        "branches": "",
                        "quantidade_tags": 0,
                        "tags": "",
                        "erro": "Tempo limite excedido",
                    }
                )

            except Exception as erro:
                logger.exception(
                    "Erro inesperado ao consultar %s",
                    nome,
                )

                inventario.append(
                    {
                        "repositorio": nome,
                        "status": "ERRO",
                        "quantidade_branches": 0,
                        "branches": "",
                        "quantidade_tags": 0,
                        "tags": "",
                        "erro": str(erro),
                    }
                )

        return inventario

    def gerar_csv(self, inventario):
        campos = [
            "repositorio",
            "status",
            "quantidade_branches",
            "branches",
            "quantidade_tags",
            "tags",
            "erro",
        ]

        with self.arquivo_csv.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as arquivo:
            escritor = csv.DictWriter(
                arquivo,
                fieldnames=campos,
            )

            escritor.writeheader()
            escritor.writerows(inventario)

        logger.info(
            "CSV gerado: %s",
            self.arquivo_csv.resolve(),
        )

    def exibir_resumo(self, inventario, total):
        acessiveis = sum(item["status"] == "ACESSIVEL" for item in inventario)

        erros = sum(item["status"] == "ERRO" for item in inventario)

        timeouts = sum(item["status"] == "TIMEOUT" for item in inventario)

        total_branches = sum(item["quantidade_branches"] for item in inventario)

        total_tags = sum(item["quantidade_tags"] for item in inventario)

        logger.info("=" * 45)
        logger.info("INVENTÁRIO CONCLUÍDO")
        logger.info("=" * 45)

        logger.info("Total de repositórios: %s", total)
        logger.info("Acessíveis: %s", acessiveis)
        logger.info("Com erro: %s", erros)
        logger.info("Timeout: %s", timeouts)
        logger.info("Total de branches: %s", total_branches)
        logger.info("Total de tags: %s", total_tags)

    def executar(self):
        if not self.chave_ssh.exists():
            raise FileNotFoundError(f"Chave SSH não encontrada: {self.chave_ssh}")

        self.diretorio_data.mkdir(
            parents=True,
            exist_ok=True,
        )

        slugs = self.carregar_repositorios()
        inventario = self.consultar_repositorios(slugs)

        self.gerar_csv(inventario)
        self.exibir_resumo(inventario, len(slugs))


def configurar_argumentos():
    parser = argparse.ArgumentParser(
        description="Consulta branches e tags dos repositórios Git."
    )

    parser.add_argument(
        "--projeto",
        default="cred",
        help="Projeto de origem. Padrão: cred.",
    )

    return parser.parse_args()


def main():
    setup_logging()

    args = configurar_argumentos()

    inventario = InventarioRepositorios(
        projeto=args.projeto,
    )

    inventario.executar()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logger.exception("FALHA NO INVENTÁRIO")
        raise
