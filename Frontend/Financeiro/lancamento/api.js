// T-13 · US-03 — Acesso à API do Financeiro a partir do navegador.
//
// O código de acesso (FINANCEIRO_API_TOKEN) NÃO fica no código: este
// repositório é público no GitHub. O educador informa o código uma vez e ele
// fica salvo só naquele aparelho (localStorage). Quando a US-08 (login)
// existir, o token dá lugar à sessão do usuário.

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
  return {
    Authorization: `Bearer ${tokenSalvo()}`,
    "X-Papel-Usuario": "educador",
  };
}

async function requisitar(caminho, opcoes = {}) {
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

export function listarOrcamentosVigentes(dataISO) {
  return requisitar(`/orcamentos?vigentes_em=${encodeURIComponent(dataISO)}`);
}

export function enviarLancamento(formData) {
  // Sem Content-Type: o navegador monta o multipart com o boundary certo.
  return requisitar("/lancamentos", { method: "POST", body: formData });
}
