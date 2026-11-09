// Cliente único da API para o módulo de Gestão: toda chamada HTTP das telas passa por aqui.
//
// O código de acesso (token de serviço provisório, até o login da T-35) NÃO fica no
// código, porque o repositório é público. Ele é informado na própria tela e fica
// salvo só neste aparelho, nas mesmas chaves do Financeiro: o código e o servidor
// valem para os dois módulos.
//
// As rotas de programa também exigem saber QUEM chama (cabeçalho X-Usuario-Id, com o
// id da tabela `usuarios`). Até o login, a pessoa informa o próprio usuário na tela de
// acesso; ele fica salvo só neste aparelho, numa chave própria de Gestão.
//
// Login único (T-35): quando a pessoa entra pela tela inicial da plataforma, a sessão
// fica em "mdca.sessao". Com ela, toda chamada leva o token de sessão e a API sabe quem
// é a pessoa; o código de acesso e o X-Usuario-Id só são usados sem sessão.

export const API_PADRAO = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

const CHAVE_TOKEN = "mdca.financeiro.token";
const CHAVE_API = "mdca.financeiro.api";
const CHAVE_USUARIO = "mdca.gestao.usuario";
const CHAVE_SESSAO = "mdca.sessao";
const TEMPO_LIMITE_MS = 15000;
// Texto do 400 da API quando falta o X-Usuario-Id (Financeiro/autenticacao.py).
const FALTA_USUARIO = "Identificação do usuário obrigatória.";

export const ERROS = Object.freeze({
  REDE: "rede",
  SESSAO_EXPIRADA: "sessao_expirada",
  NAO_AUTENTICADO: "nao_autenticado",
  SEM_USUARIO: "sem_usuario",
  SEM_PERMISSAO: "sem_permissao",
  NAO_ENCONTRADO: "nao_encontrado",
  INDISPONIVEL: "indisponivel",
  FALHA: "falha",
});

const MENSAGENS = {
  [ERROS.REDE]: "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.",
  [ERROS.SESSAO_EXPIRADA]: "Sua sessão expirou. Entre de novo para continuar.",
  [ERROS.NAO_AUTENTICADO]: "Informe o código de acesso para carregar estes dados.",
  [ERROS.SEM_USUARIO]: "Informe seu usuário para carregar estes dados.",
  [ERROS.SEM_PERMISSAO]: "Seu perfil não tem acesso a estes dados.",
  [ERROS.NAO_ENCONTRADO]: "Este recurso ainda não está disponível no servidor.",
  [ERROS.INDISPONIVEL]: "O servidor está temporariamente indisponível. Tente de novo em instantes.",
  [ERROS.FALHA]: "O servidor não conseguiu atender o pedido. Tente de novo.",
};

/** Erro de uma chamada; `tipo` é um de ERROS e `detalhe` traz o `detail` da API, quando houver. */
export class ErroApi extends Error {
  constructor(tipo, status = 0, detalhe = "") {
    super(MENSAGENS[tipo] || MENSAGENS[ERROS.FALHA]);
    this.name = "ErroApi";
    this.tipo = tipo;
    this.status = status;
    this.detalhe = detalhe;
  }
}

function tipoDoStatus(status, detalhe) {
  if (status === 401) return ERROS.NAO_AUTENTICADO;
  if (status === 400 && detalhe === FALTA_USUARIO) return ERROS.SEM_USUARIO;
  if (status === 403) return ERROS.SEM_PERMISSAO;
  if (status === 404) return ERROS.NAO_ENCONTRADO;
  if (status === 503) return ERROS.INDISPONIVEL;
  return ERROS.FALHA;
}

function ler(chave) {
  try {
    return localStorage.getItem(chave) || "";
  } catch {
    return "";
  }
}

function gravar(chave, valor) {
  try {
    if (valor) localStorage.setItem(chave, valor);
    else localStorage.removeItem(chave);
  } catch {
    /* navegador sem armazenamento: o código vale só até fechar a página */
  }
}

let tokenEmMemoria = "";

export function urlDaApi() {
  // O endereço só muda pelo campo "Servidor (avançado)". Não o aceitamos pela URL da
  // página: um link malicioso poderia mandar o código de acesso para outro servidor.
  return (ler(CHAVE_API) || API_PADRAO).replace(/\/+$/, "");
}

export function tokenSalvo() {
  return tokenEmMemoria || ler(CHAVE_TOKEN);
}

/** Troca o servidor da API; vazio ou o endereço padrão voltam para a API publicada. */
export function salvarServidor(api) {
  const endereco = api.trim().replace(/\/+$/, "");
  gravar(CHAVE_API, endereco === API_PADRAO ? "" : endereco);
}

export function salvarAcesso(token, api) {
  tokenEmMemoria = token.trim();
  gravar(CHAVE_TOKEN, tokenEmMemoria);
  if (api !== undefined) salvarServidor(api);
}

export function esquecerAcesso() {
  tokenEmMemoria = "";
  gravar(CHAVE_TOKEN, "");
}

/**
 * Sessão do login único ({ token, expira_em, usuario: { id, nome, email, papeis } }),
 * ou `null` sem sessão ou com ela expirada. A tela inicial grava em localStorage
 * ("Manter conectado") ou em sessionStorage.
 */
export function sessaoAtiva() {
  let sessao = null;
  try {
    sessao = JSON.parse(localStorage.getItem(CHAVE_SESSAO) || sessionStorage.getItem(CHAVE_SESSAO) || "null");
  } catch {
    return null;
  }
  if (!sessao?.token || !(new Date(sessao.expira_em) > new Date())) return null;
  return sessao;
}

/** Apaga a sessão do login único deste navegador (sair, ou sessão recusada pela API). */
export function encerrarSessao() {
  try {
    localStorage.removeItem(CHAVE_SESSAO);
    sessionStorage.removeItem(CHAVE_SESSAO);
  } catch {
    /* navegador sem armazenamento */
  }
}

let usuarioEmMemoria = "";

/** Id do usuário (tabela `usuarios`): o da sessão ou o enviado em X-Usuario-Id; vazio se nenhum. */
export function usuarioSalvo() {
  return sessaoAtiva()?.usuario?.id || usuarioEmMemoria || ler(CHAVE_USUARIO);
}

export function salvarUsuario(usuario) {
  usuarioEmMemoria = String(usuario ?? "").trim();
  gravar(CHAVE_USUARIO, usuarioEmMemoria);
}

/**
 * Chama a API e devolve o corpo JSON (ou `null` sem corpo).
 * Qualquer falha vira `ErroApi`: sem conexão, tempo esgotado ou status de erro.
 */
export async function requisitar(caminho, { metodo = "GET", dados, tempoLimite = TEMPO_LIMITE_MS } = {}) {
  const cabecalhos = { Accept: "application/json" };
  const sessao = sessaoAtiva();
  if (sessao) {
    // Com sessão, o token diz quem é a pessoa: nada de código de acesso nem X-Usuario-Id.
    cabecalhos.Authorization = `Bearer ${sessao.token}`;
  } else {
    const token = tokenSalvo();
    if (token) cabecalhos.Authorization = `Bearer ${token}`;
    const usuario = usuarioSalvo();
    if (usuario) cabecalhos["X-Usuario-Id"] = usuario;
  }
  const opcoes = { method: metodo, headers: cabecalhos };
  if (dados !== undefined) {
    cabecalhos["Content-Type"] = "application/json";
    opcoes.body = JSON.stringify(dados);
  }

  const controle = new AbortController();
  const relogio = setTimeout(() => controle.abort(), tempoLimite);
  let resposta;
  let corpo = null;
  try {
    resposta = await fetch(urlDaApi() + caminho, { ...opcoes, signal: controle.signal });
    const texto = await resposta.text();
    if (texto) {
      try {
        corpo = JSON.parse(texto);
      } catch {
        /* resposta sem JSON */
      }
    }
  } catch {
    throw new ErroApi(ERROS.REDE);
  } finally {
    clearTimeout(relogio);
  }

  if (!resposta.ok) {
    const detalhe = typeof corpo?.detail === "string" ? corpo.detail : "";
    if (sessao && resposta.status === 401) {
      // Token expirado, conta desativada ou login desligado no servidor.
      encerrarSessao();
      throw new ErroApi(ERROS.SESSAO_EXPIRADA, 401, detalhe);
    }
    throw new ErroApi(tipoDoStatus(resposta.status, detalhe), resposta.status, detalhe);
  }
  return corpo;
}

export const listarProgramas = () => requisitar("/gestao/programas");

// Equipe e espaços do programa (T-39). Ids vão sempre codificados no caminho.
const programa = (id) => `/gestao/programas/${encodeURIComponent(id)}`;

export const listarEquipe = (programaId, { incluirDesligados = false } = {}) =>
  requisitar(`${programa(programaId)}/equipe${incluirDesligados ? "?incluir_desligados=true" : ""}`);

/** dados: { usuario_id, papel_id, data_entrada } (data em AAAA-MM-DD). */
export const vincularProfissional = (programaId, dados) =>
  requisitar(`${programa(programaId)}/equipe`, { metodo: "POST", dados });

export const registrarDesligamento = (programaId, vinculoId, dataSaida) =>
  requisitar(`${programa(programaId)}/equipe/${encodeURIComponent(vinculoId)}/desligamento`, {
    metodo: "PATCH",
    dados: { data_saida: dataSaida },
  });

export const listarEspacos = (programaId) => requisitar(`${programa(programaId)}/espacos`);

/** dados: { nome, capacidade? } */
export const criarEspaco = (programaId, dados) =>
  requisitar(`${programa(programaId)}/espacos`, { metodo: "POST", dados });

// Usuários e papéis da plataforma (T-40).
export const listarUsuarios = () => requisitar("/gestao/usuarios");
export const listarPapeis = () => requisitar("/gestao/papeis");

// Programas, convênios, vagas e plano de ação (API da T-44; edição da T-45).
export const obterPrograma = (programaId) => requisitar(programa(programaId));

/** dados: { nome, identificador, publico, responsavel, vigencia_inicio, vigencia_fim, descricao? } */
export const cadastrarPrograma = (dados) => requisitar("/gestao/programas", { metodo: "POST", dados });

/** Só os campos enviados mudam; o programa resultante segue as regras do cadastro. */
export const editarPrograma = (programaId, dados) => requisitar(programa(programaId), { metodo: "PATCH", dados });

export const listarConvenios = (programaId) => requisitar(`${programa(programaId)}/convenios`);

/** dados: { nome, concedente?, vigencia_inicio?, vigencia_fim? } */
export const cadastrarConvenio = (programaId, dados) =>
  requisitar(`${programa(programaId)}/convenios`, { metodo: "POST", dados });

export const listarVagas = (programaId) => requisitar(`${programa(programaId)}/vagas`);

/** dados: { descricao, quantidade } */
export const cadastrarVagas = (programaId, dados) => requisitar(`${programa(programaId)}/vagas`, { metodo: "POST", dados });

export const listarObjetivos = (programaId) => requisitar(`${programa(programaId)}/objetivos`);

/** dados: { descricao } */
export const cadastrarObjetivo = (programaId, dados) =>
  requisitar(`${programa(programaId)}/objetivos`, { metodo: "POST", dados });

export const listarAcoes = (programaId) => requisitar(`${programa(programaId)}/acoes`);

/** dados: { objetivo_id, descricao, periodo_inicio, periodo_fim, resultado_esperado, periodicidade } */
export const cadastrarAcao = (programaId, dados) => requisitar(`${programa(programaId)}/acoes`, { metodo: "POST", dados });

/** dados: { acao_id, descricao, valor_planejado, unidade? } */
export const cadastrarMeta = (programaId, dados) => requisitar(`${programa(programaId)}/metas`, { metodo: "POST", dados });

/** dados: { data, valor_realizado, observacao? } */
export const registrarRealizado = (programaId, metaId, dados) =>
  requisitar(`${programa(programaId)}/metas/${encodeURIComponent(metaId)}/registros`, { metodo: "POST", dados });

/** { programa_id, metas: [{ meta_id, descricao, unidade, acao_id, acao, objetivo_id, objetivo, planejado, realizado, percentual }] } */
export const obterPainel = (programaId) => requisitar(`${programa(programaId)}/painel`);
