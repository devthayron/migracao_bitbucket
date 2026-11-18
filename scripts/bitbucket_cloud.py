import requests

from config import settings


class BitbucketCloud:
    def __init__(self):
        self.workspace = settings.CLOUD_WORKSPACE
        self.base_url = settings.BITBUCKET_CLOUD_API_URL
        self.sessao = self._criar_sessao()

    def _criar_sessao(self):
        sessao = requests.Session()
        sessao.auth = (
            settings.ATLASSIAN_EMAIL,
            settings.BITBUCKET_CLOUD_TOKEN,
        )

        sessao.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

        return sessao

    def validar_projeto(self, chave_projeto):
        url = f"{self.base_url}/workspaces/{self.workspace}/projects/{chave_projeto}"

        resposta = self.sessao.get(url, timeout=30)

        if resposta.status_code != 200:
            raise RuntimeError(
                f"Projeto '{chave_projeto}' não encontrado "
                f"ou sem acesso. HTTP {resposta.status_code}: "
                f"{resposta.text}"
            )

        return resposta.json()

    def listar_repositorios(self):
        url = f"{self.base_url}/repositories/{self.workspace}"
        existentes = {}

        while url:
            resposta = self.sessao.get(
                url,
                params={"pagelen": 100} if "?" not in url else None,
                timeout=30,
            )

            if resposta.status_code != 200:
                raise RuntimeError(
                    f"Falha ao listar repositórios: "
                    f"HTTP {resposta.status_code} - {resposta.text}"
                )

            dados = resposta.json()

            for repo in dados.get("values", []):
                existentes[repo["slug"]] = repo

            url = dados.get("next")

        return existentes

    def obter_repositorio(self, slug):
        url = f"{self.base_url}/repositories/{self.workspace}/{slug}"

        resposta = self.sessao.get(url, timeout=30)

        if resposta.status_code == 404:
            return None

        if resposta.status_code != 200:
            raise RuntimeError(
                f"Falha ao consultar repositório '{slug}': "
                f"HTTP {resposta.status_code} - {resposta.text}"
            )

        return resposta.json()

    def listar_repositorios_projeto(self, chave_projeto):
        url = f"{self.base_url}/repositories/{self.workspace}"

        parametros = {
            "q": f'project.key="{chave_projeto}"',
            "pagelen": 100,
        }

        repositorios = []

        while url:
            resposta = self.sessao.get(
                url,
                params=parametros,
                timeout=30,
            )

            if resposta.status_code != 200:
                raise RuntimeError(
                    f"Falha ao consultar projeto {chave_projeto}: "
                    f"HTTP {resposta.status_code} - {resposta.text}"
                )

            dados = resposta.json()

            repositorios.extend(dados.get("values", []))

            url = dados.get("next")
            parametros = None

        return repositorios

    def repositorio_possui_referencias(self, slug):
        url = f"{self.base_url}/repositories/{self.workspace}/{slug}/refs"

        resposta = self.sessao.get(
            url,
            params={"pagelen": 1},
            timeout=30,
        )

        if resposta.status_code != 200:
            raise RuntimeError(
                f"Falha ao consultar referências do repositório "
                f"'{slug}': HTTP {resposta.status_code} - {resposta.text}"
            )

        dados = resposta.json()

        return bool(dados.get("values"))

    def criar_repositorio(self, slug, chave_projeto):
        url = f"{self.base_url}/repositories/{self.workspace}/{slug}"

        resposta = self.sessao.post(
            url,
            json={
                "scm": "git",
                "is_private": True,
                "project": {"key": chave_projeto},
            },
            timeout=30,
        )

        if resposta.status_code in (200, 201):
            return True, "Criado com sucesso."

        if resposta.status_code == 409:
            return False, "Conflito: o repositório já existe."

        return False, (f"HTTP {resposta.status_code}: {resposta.text}")

    def listar_projetos(self):
        url = f"{self.base_url}/workspaces/{self.workspace}/projects"

        projetos = []

        while url:
            resposta = self.sessao.get(
                url,
                params={"pagelen": 100} if "?" not in url else None,
                timeout=30,
            )

            if resposta.status_code != 200:
                raise RuntimeError(
                    f"Falha ao listar projetos: "
                    f"HTTP {resposta.status_code} - {resposta.text}"
                )

            dados = resposta.json()

            projetos.extend(dados.get("values", []))

            url = dados.get("next")

        return projetos
