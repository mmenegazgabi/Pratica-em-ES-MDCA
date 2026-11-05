// Cliente único da API para o módulo de Gestão: toda chamada HTTP das telas passa por aqui.
//
// O código de acesso (token de serviço provisório, até o login da T-35) NÃO fica no
// código, porque o repositório é público. Ele é informado na própria tela e fica
// salvo só neste aparelho, nas mesmas chaves do Financeiro: o código e o servidor
// valem para os dois módulos.

export const API_PADRAO = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

const CHAVE_TOKEN = "mdca.financeiro.token";
const CHAVE_API = "mdca.financeiro.api";
const TEMPO_LIMITE_MS = 15000;

export const ERROS = Object.freeze({
  REDE: "rede",
  NAO_AUTENTICADO: "nao_autenticado",
  SEM_PERMISSAO: "sem_permissao",
  NAO_ENCONTRADO: "nao_encontrado",
  INDISPONIVEL: "indisponivel",
  FALHA: "falha",
});

const MENSAGENS = {
  [ERROS.REDE]: "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.",
  [ERROS.NAO_AUTENTICADO]: "Informe o código de acesso para carregar estes dados.",
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

function tipoDoStatus(status) {
  if (status === 401) return ERROS.NAO_AUTENTICADO;
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
 * Chama a API e devolve o corpo JSON (ou `null` sem corpo).
 * Qualquer falha vira `ErroApi`: sem conexão, tempo esgotado ou status de erro.
 */
export async function requisitar(caminho, { metodo = "GET", dados, tempoLimite = TEMPO_LIMITE_MS } = {}) {
  const cabecalhos = { Accept: "application/json" };
  const token = tokenSalvo();
  if (token) cabecalhos.Authorization = `Bearer ${token}`;
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
    throw new ErroApi(tipoDoStatus(resposta.status), resposta.status, detalhe);
  }
  return corpo;
}

export const listarProgramas = () => requisitar("/gestao/programas");
