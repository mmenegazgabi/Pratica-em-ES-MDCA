"""Erros de regra do cadastro de pessoas (US-03), traduzidos em HTTP pelas rotas."""

from typing import Optional


class ErroDeCadastro(Exception):
    """Erro de regra; ``status`` é a resposta HTTP, ``codigo`` identifica o caso para o
    frontend e ``dados`` vai junto no corpo (ex.: os possíveis duplicados)."""

    status = 400

    def __init__(self, mensagem: str, *, codigo: str = "", dados: Optional[dict] = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo
        self.dados = dados or {}


class DadosInvalidos(ErroDeCadastro):
    status = 400


class NaoEncontrado(ErroDeCadastro):
    status = 404


class Conflito(ErroDeCadastro):
    status = 409
