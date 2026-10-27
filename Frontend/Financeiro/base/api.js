// Acesso à API do Financeiro a partir do navegador (base de todas as telas).
//
// O código de acesso (FINANCEIRO_API_TOKEN) NÃO fica no código: este
// repositório é público no GitHub. O educador informa o código uma vez e ele
// fica salvo só naquele aparelho (localStorage). Quando a US-08 (login)
// existir, o token dá lugar à sessão do usuário.

import { lerSessao, usuarioId } from "./sessao.js";

export const API_PADRAO = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

// Opcional e NÃO recomendado: preencher aqui faz o código de acesso ir para o
// GitHub (repositório público) e para o site publicado. Deixe vazio para o
// educador informar o código no próprio celular.
export const TOKEN_FIXO = "";

const CHAVE_TOKEN = "mdca.financeiro.token";
const CHAVE_API = "mdca.financeiro.api";

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
  // Para testar com o backend local, use "Servidor (avançado)" na tela de
  // código de acesso. Não aceitamos o endereço pela URL da página: um link
  // malicioso poderia mandar o código de acesso para outro servidor.
  return (ler(CHAVE_API) || API_PADRAO).replace(/\/+$/, "");
}

export function tokenSalvo() {
  return TOKEN_FIXO || tokenEmMemoria || ler(CHAVE_TOKEN);
}

export function salvarAcesso(token, api) {
  tokenEmMemoria = token.trim();
  gravar(CHAVE_TOKEN, tokenEmMemoria);
  if (api !== undefined) gravar(CHAVE_API, api.trim() === API_PADRAO ? "" : api.trim());
}

export function esquecerAcesso() {
  tokenEmMemoria = "";
  gravar(CHAVE_TOKEN, "");
}

function cabecalhos() {
  const cab = { Authorization: `Bearer ${tokenSalvo()}` };
  const sessao = lerSessao();
  if (sessao) {
    cab["X-Papel-Usuario"] = sessao.papel;
    cab["X-Usuario-Id"] = usuarioId(sessao.nome);
  }
  return cab;
}

export async function requisitar(caminho, opcoes = {}) {
  let resposta;
  try {
    resposta = await fetch(urlDaApi() + caminho, {
      ...opcoes,
      headers: { ...cabecalhos(), ...(opcoes.headers || {}) },
    });
  } catch {
    return { status: 0, corpo: null };
  }
  let corpo = null;
  try {
    corpo = await resposta.json();
  } catch {
    /* resposta sem JSON */
  }
  return { status: resposta.status, corpo };
}

/** Arquivo protegido (ex.: comprovante_url) como Blob: a rota exige o código de acesso. */
export async function baixarArquivo(caminho) {
  try {
    const resposta = await fetch(urlDaApi() + caminho, { headers: cabecalhos() });
    return { status: resposta.status, blob: resposta.ok ? await resposta.blob() : null };
  } catch {
    return { status: 0, blob: null };
  }
}

function comJson(metodo, dados) {
  return { method: metodo, headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) };
}

function consulta(filtros = {}) {
  const params = new URLSearchParams();
  for (const [chave, valor] of Object.entries(filtros)) {
    if (valor !== undefined && valor !== null && valor !== "") params.set(chave, String(valor));
  }
  const texto = params.toString();
  return texto ? `?${texto}` : "";
}

const rota = (id) => encodeURIComponent(id);

export const listarProjetos = () => requisitar("/projetos");
export const criarProjeto = (nome) => requisitar("/projetos", comJson("POST", { nome }));

export const listarOrcamentos = (vigentesEm) => requisitar(`/orcamentos${consulta({ vigentes_em: vigentesEm })}`);
export const obterOrcamento = (id) => requisitar(`/orcamentos/${rota(id)}`);
export const criarOrcamento = (dados) => requisitar("/orcamentos", comJson("POST", dados));
export const editarOrcamento = (id, dados) => requisitar(`/orcamentos/${rota(id)}`, comJson("PATCH", dados));

export const listarLancamentos = (filtros = {}) => requisitar(`/lancamentos${consulta(filtros)}`);
export const obterLancamento = (id) => requisitar(`/lancamentos/${rota(id)}`);
export const aprovarLancamento = (id) => requisitar(`/lancamentos/${rota(id)}/aprovar`, { method: "PATCH" });
export const rejeitarLancamento = (id, motivo) => requisitar(`/lancamentos/${rota(id)}/rejeitar`, comJson("PATCH", { motivo }));

// Multipart: sem Content-Type, o navegador monta o boundary certo.
export const enviarLancamento = (formData) => requisitar("/lancamentos", { method: "POST", body: formData });
export const reenviarLancamento = (id, formData) => requisitar(`/lancamentos/${rota(id)}/reenviar`, { method: "PATCH", body: formData });

export function criarRascunho(arquivo) {
  const formData = new FormData();
  formData.append("comprovante", arquivo);
  return requisitar("/rascunhos", { method: "POST", body: formData });
}
export const listarRascunhos = () => requisitar("/rascunhos");
export const completarRascunho = (id, formData) => requisitar(`/rascunhos/${rota(id)}/completar`, { method: "POST", body: formData });

export const listarNotificacoes = () => requisitar("/notificacoes");
export const marcarNotificacaoLida = (id) => requisitar(`/notificacoes/${rota(id)}/lida`, { method: "PATCH" });
