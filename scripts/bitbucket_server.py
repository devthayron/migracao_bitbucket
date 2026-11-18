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
