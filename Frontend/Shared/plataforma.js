// Sessão compartilhada da plataforma MDCA (página inicial, Financeiro e administração).
//
// A sessão {token, expira_em, usuario} fica na chave `mdca.sessao`: em localStorage
// quando a pessoa marca "Manter conectado neste aparelho", em sessionStorage quando não.
// O endereço da API fica em `mdca.api` (lemos também a chave antiga do Financeiro).

export const API_PADRAO = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

export const CHAVE_SESSAO = "mdca.sessao";
export const CHAVE_API = "mdca.api";
export const CHAVE_API_ANTIGA = "mdca.financeiro.api";
export const CHAVE_PAPEL_FINANCEIRO = "mdca.financeiro.papel";

const SEM_CONEXAO = "Sem conexão com o servidor. Tente de novo.";
const ERRO_GENERICO = "Não foi possível concluir. Tente de novo.";

function armazem(nome) {
  try {
    return globalThis[nome] || null;
  } catch {
    return null;
  }
}

function ler(nome, chave) {
  try {
    return armazem(nome)?.getItem(chave) ?? null;
  } catch {
    return null;
  }
}

function gravar(nome, chave, valor) {
  try {
    armazem(nome)?.setItem(chave, valor);
  } catch {
    /* navegador sem armazenamento: a sessão vale só até fechar a página */
  }
}

function apagar(nome, chave) {
  try {
    armazem(nome)?.removeItem(chave);
  } catch {
    /* navegador sem armazenamento */
  }
}

const semBarraFinal = (url) => String(url).trim().replace(/\/+$/, "");

export function urlDaApi() {
  return semBarraFinal(ler("localStorage", CHAVE_API) || ler("localStorage", CHAVE_API_ANTIGA) || API_PADRAO);
}

/** Guarda o endereço da API; vazio ou o padrão voltam ao padrão. */
export function salvarUrlDaApi(url) {
  const limpo = semBarraFinal(url || "");
  if (!limpo || limpo === API_PADRAO) {
    apagar("localStorage", CHAVE_API);
    apagar("localStorage", CHAVE_API_ANTIGA);
  } else {
    gravar("localStorage", CHAVE_API, limpo);
  }
}

function sessaoValida(dados) {
  return (
    dados &&
    typeof dados.token === "string" &&
    dados.token &&
    typeof dados.expira_em === "string" &&
    dados.usuario &&
    typeof dados.usuario === "object"
  );
}

/** Sessão salva neste navegador, ou null. Sessão vencida ou estragada é apagada. */
export function lerSessao() {
  for (const nome of ["localStorage", "sessionStorage"]) {
    const bruto = ler(nome, CHAVE_SESSAO);
    if (!bruto) continue;
    let dados = null;
    try {
      dados = JSON.parse(bruto);
    } catch {
      dados = null;
    }
    const expira = sessaoValida(dados) ? Date.parse(dados.expira_em) : NaN;
    if (!Number.isFinite(expira) || expira <= Date.now()) {
      apagar(nome, CHAVE_SESSAO);
      continue;
    }
    return { token: dados.token, expira_em: dados.expira_em, usuario: dados.usuario };
  }
  return null;
}

function salvarSessao(sessao, lembrar) {
  encerrarSessaoLocal();
  gravar(lembrar ? "localStorage" : "sessionStorage", CHAVE_SESSAO, JSON.stringify(sessao));
}

/** Apaga a sessão e o papel escolhido no Financeiro, sem falar com o servidor. */
export function encerrarSessaoLocal() {
  apagar("localStorage", CHAVE_SESSAO);
  apagar("sessionStorage", CHAVE_SESSAO);
  apagar("localStorage", CHAVE_PAPEL_FINANCEIRO);
}

async function mensagemDeErro(resposta) {
  try {
    const corpo = await resposta.json();
    if (corpo && typeof corpo.detail === "string" && corpo.detail) return corpo.detail;
  } catch {
    /* resposta sem JSON */
  }
  return ERRO_GENERICO;
}

async function autenticar(caminho, corpo, lembrar) {
  let resposta;
  try {
    resposta = await fetch(`${urlDaApi()}${caminho}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
    });
  } catch {
    return { ok: false, mensagem: SEM_CONEXAO };
  }
  if (!resposta.ok) return { ok: false, mensagem: await mensagemDeErro(resposta) };
  let dados;
  try {
    dados = await resposta.json();
  } catch {
    dados = null;
  }
  if (!sessaoValida(dados)) return { ok: false, mensagem: ERRO_GENERICO };
  const sessao = { token: dados.token, expira_em: dados.expira_em, usuario: dados.usuario };
  salvarSessao(sessao, lembrar);
  return { ok: true, sessao };
}

export function entrar({ email, senha, lembrar }) {
  return autenticar("/auth/entrar", { email, senha, lembrar: !!lembrar }, !!lembrar);
}

export function primeiroAcesso({ email, codigo, senha, lembrar }) {
  return autenticar("/auth/primeiro-acesso", { email, codigo, senha, lembrar: !!lembrar }, !!lembrar);
}

/** Encerra a sessão no servidor (ignora falhas) e neste navegador. */
export async function sair() {
  const sessao = lerSessao();
  if (sessao) {
    try {
      await fetch(`${urlDaApi()}/auth/sair`, {
        method: "POST",
        headers: { Authorization: `Bearer ${sessao.token}` },
      });
    } catch {
      /* sem conexão: a sessão local é apagada mesmo assim */
    }
  }
  encerrarSessaoLocal();
}

export function temPapel(sessao, papel) {
  const papeis = sessao?.usuario?.papeis;
  if (!Array.isArray(papeis)) return false;
  return papeis.some((p) => (typeof p === "string" ? p : p?.id) === papel);
}
