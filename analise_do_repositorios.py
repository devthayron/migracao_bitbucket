import csv
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

from config import settings


class BitbucketServer:
    def __init__(self):
        self.base_url = f"{settings.BITBUCKET_SERVER_URL}/rest/api/1.0"

        self.sessao = requests.Session()
        self.sessao.auth = HTTPBasicAuth(
            settings.BITBUCKET_SERVER_USERNAME,
            settings.BITBUCKET_SERVER_PASSWORD,
        )
        self.sessao.headers.update({"Accept": "application/json"})

        # Cria data caso ainda não exista
        self.diretorio_data = (
            Path(__file__).resolve().parent.parent / "migracao_bitbucket" / "data"
        )
        self.diretorio_data.mkdir(parents=True, exist_ok=True)

        self.arquivo_relatorio = self.diretorio_data / "relatorio.csv"

    def listar_repositorios(self, projeto):
        url = f"{self.base_url}/projects/{projeto}/repos"

        repositorios = []
        start = 0
        limit = 100

        while True:
            resposta = self.sessao.get(
                url,
                params={
                    "start": start,
                    "limit": limit,
                },
                timeout=30,
            )

            resposta.raise_for_status()
            dados = resposta.json()

            repositorios.extend(dados.get("values", []))

            if dados.get("isLastPage", True):
                break

            start = dados["nextPageStart"]

        return repositorios

    def gerar_relatorio(self, repositorios):
        with self.arquivo_relatorio.open(
            "w",
            newline="",
            encoding="utf-8-sig",
        ) as arquivo:
            campos = [
                "nome",
                "slug",
                "projeto",
                "url_ssh",
            ]

            escritor = csv.DictWriter(
                arquivo,
                fieldnames=campos,
                delimiter=";",
            )

            escritor.writeheader()

            for repo in repositorios:
                url_ssh = next(
                    (
                        clone["href"]
                        for clone in repo.get("links", {}).get("clone", [])
                        if clone.get("name") == "ssh"
                    ),
                    "",
                )

                escritor.writerow(
                    {
                        "nome": repo["name"],
                        "slug": repo["slug"],
                        "projeto": repo["project"]["key"],
                        "url_ssh": url_ssh,
                    }
                )

        print(f"\nRelatório gerado: {self.arquivo_relatorio}")
        print(f"Total de repositórios: {len(repositorios)}")


def main():
    bitbucket = BitbucketServer()

    repositorios = bitbucket.listar_repositorios("CRED")

    bitbucket.gerar_relatorio(repositorios)


if __name__ == "__main__":
    main()
