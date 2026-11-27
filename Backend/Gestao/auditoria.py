"""Registro de eventos de Gestão na trilha única da plataforma (``log_auditoria``, T-32 · T-81).

A gravação é a mesma do Financeiro (``Shared/auditoria.py``); aqui ficam o módulo
``gestao``, os códigos das ações da Gestão e os rótulos que a tela única de Auditoria
mostra (``ROTULOS``, lidos por ``Financeiro/auditoria.py``). A tabela só aceita inclusão
(trigger no banco).

O que a Gestão registra (US-13):

- **Consultas a dados sensíveis:** cadastro e trajetória de uma pessoa atendida, chamada
  de um encontro (nomes e presenças) e alerta de infrequência. Listas não entram: só a
  abertura de um registro individual.
- **Alterações:** todo cadastro e mudança em programas, plano de ação, equipe, espaços,
  pessoas, documentos, autorizações, turmas, matrículas, encontros e evidências.
- **Acessos negados** (``acesso_negado``), downloads e os eventos automáticos (alerta).

Cada evento guarda quem fez, quando, a ação, o item (``alvo_tipo`` e ``alvo_id``) e o
programa nos detalhes. A descrição (o "Detalhe" da tela) diz o tipo do item e o
programa, sem nome de pessoa atendida.

``registrar`` e ``registrar_evento`` não fazem commit: o evento entra na mesma transação
da ação e, se ela falhar, o registro também não fica. Nas consultas, a rota faz o commit
só do evento.
"""

from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from Shared import auditoria as _trilha
from Shared.auditoria import ACESSO_NEGADO

__all__ = ["ACESSO_NEGADO", "ALVOS", "MODULO", "ROTULOS", "registrar", "registrar_evento"]

MODULO = "gestao"

# Consultas a registros sensíveis.
CONSULTA_PESSOA = "consulta_pessoa"
CONSULTA_TRAJETORIA = "consulta_trajetoria"
CONSULTA_CHAMADA = "consulta_chamada"
CONSULTA_ALERTA = "consulta_alerta"

# Alterações.
PROGRAMA_CADASTRADO = "programa_cadastrado"
PROGRAMA_EDITADO = "programa_editado"
OBJETIVO_CADASTRADO = "objetivo_cadastrado"
ACAO_CADASTRADA = "acao_cadastrada"
META_CADASTRADA = "meta_cadastrada"
REALIZADO_REGISTRADO = "realizado_registrado"
VINCULO_CADASTRADO = "vinculo_cadastrado"
VINCULO_DESLIGADO = "vinculo_desligado"
ESPACO_CADASTRADO = "espaco_cadastrado"
PESSOA_CADASTRADA = "pessoa_cadastrada"
RESPONSAVEL_INCLUIDO = "responsavel_incluido"
DOCUMENTO_ENVIADO = "documento_enviado"
AUTORIZACAO_REGISTRADA = "autorizacao_registrada"
TURMA_CADASTRADA = "turma_cadastrada"
TURMA_EDITADA = "turma_editada"
INSCRICAO_REGISTRADA = "inscricao_registrada"
LISTA_DE_ESPERA_CHAMADA = "lista_de_espera_chamada"
MATRICULA_DESLIGADA = "matricula_desligada"
ENCONTRO_REGISTRADO = "encontro_registrado"
EVIDENCIA_ENVIADA = "evidencia_enviada"

# Texto da coluna "Ação" na tela de Auditoria. Toda ação que a Gestão grava tem rótulo
# (um teste confere); sem rótulo, a tela mostraria o código.
ROTULOS = {
    CONSULTA_PESSOA: "Consultou cadastro de pessoa atendida",
    CONSULTA_TRAJETORIA: "Consultou trajetória de pessoa atendida",
    CONSULTA_CHAMADA: "Consultou chamada de encontro",
    CONSULTA_ALERTA: "Consultou alerta de infrequência",
    "consulta_visao_integrada": "Consultou a visão integrada",
    PROGRAMA_CADASTRADO: "Cadastrou programa",
    PROGRAMA_EDITADO: "Editou programa",
    OBJETIVO_CADASTRADO: "Cadastrou objetivo do plano",
    ACAO_CADASTRADA: "Cadastrou ação do plano",
    META_CADASTRADA: "Cadastrou meta do plano",
    REALIZADO_REGISTRADO: "Registrou realizado de meta",
    VINCULO_CADASTRADO: "Vinculou profissional à equipe",
    VINCULO_DESLIGADO: "Desligou profissional da equipe",
    ESPACO_CADASTRADO: "Cadastrou espaço",
    PESSOA_CADASTRADA: "Cadastrou pessoa atendida",
    RESPONSAVEL_INCLUIDO: "Incluiu responsável",
    DOCUMENTO_ENVIADO: "Enviou documento de pessoa atendida",
    AUTORIZACAO_REGISTRADA: "Registrou autorização",
    "autorizacao_revogada": "Revogou autorização",
    "duplicidade_confirmada": "Cadastrou pessoa com possível duplicidade",
    TURMA_CADASTRADA: "Cadastrou turma",
    TURMA_EDITADA: "Editou turma",
    INSCRICAO_REGISTRADA: "Inscreveu pessoa em turma",
    LISTA_DE_ESPERA_CHAMADA: "Chamou a lista de espera",
    MATRICULA_DESLIGADA: "Desligou matrícula",
    "conflito_de_horario": "Matrícula com conflito de horário",
    ENCONTRO_REGISTRADO: "Registrou encontro e chamada",
    EVIDENCIA_ENVIADA: "Enviou evidência de atividade",
    "download_evidencia": "Baixou evidência de atividade",
    "download_documento": "Baixou documento de pessoa atendida",
    "alerta_infrequencia": "Alerta de infrequência criado",
    "acao_busca_ativa": "Registrou ação de busca ativa",
    "alerta_encerrado": "Encerrou alerta de infrequência",
    "relatorio_tecnico_emitido": "Emitiu relatório técnico",
    ACESSO_NEGADO: "Acesso negado",
}

# Nome do tipo de item, para a descrição do evento.
ALVOS = {
    "programa": "Programa",
    "objetivo": "Objetivo do plano",
    "acao": "Ação do plano",
    "meta": "Meta do plano",
    "registro_meta": "Realizado de meta",
    "vinculo": "Vínculo da equipe",
    "espaco": "Espaço",
    "pessoa": "Pessoa atendida",
    "documento_pessoa": "Documento de pessoa atendida",
    "autorizacao": "Autorização",
    "turma": "Turma",
    "matricula": "Matrícula",
    "atividade": "Encontro",
    "evidencia": "Evidência",
    "alerta": "Alerta de infrequência",
}


def registrar(
    conexao: Connection,
    *,
    usuario_id: Optional[str],
    acao: str,
    alvo_tipo: Optional[str] = None,
    alvo_id: Optional[str] = None,
    descricao: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    """Inclui um evento de Gestão. Quem chama decide quando fazer o commit."""
    _trilha.registrar(
        conexao,
        modulo=MODULO,
        usuario_id=usuario_id,
        acao=acao,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        descricao=descricao,
        detalhes=detalhes,
    )


def registrar_evento(
    conexao: Connection,
    *,
    usuario_id: Optional[str],
    acao: str,
    alvo_tipo: str,
    alvo_id: Optional[str],
    programa_id: Optional[str] = None,
    detalhes: Optional[Dict[str, Any]] = None,
) -> None:
    """Evento de consulta ou alteração: a descrição é o tipo do item e o programa
    (ex.: "Pessoa atendida · Semear"), e o programa vai também nos detalhes."""
    partes = [ALVOS.get(alvo_tipo, alvo_tipo)]
    if programa_id:
        nome = conexao.execute(sa.text("SELECT nome FROM projetos WHERE id = :id"), {"id": programa_id}).scalar_one_or_none()
        if nome:
            partes.append(nome)
    registrar(
        conexao,
        usuario_id=usuario_id,
        acao=acao,
        alvo_tipo=alvo_tipo,
        alvo_id=alvo_id,
        descricao=" · ".join(partes),
        detalhes={**({"programa_id": programa_id} if programa_id else {}), **(detalhes or {})},
    )
