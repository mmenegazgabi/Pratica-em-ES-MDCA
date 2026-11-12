// Acesso à API do Financeiro a partir do navegador (base de todas as telas).
//
// Quem chama é identificado pela sessão da plataforma (login único): o token vai em
// Authorization e o papel em uso no Financeiro em X-Papel-Usuario. Sessão inválida ou
// vencida (401) apaga a sessão e volta para a página inicial.

import { encerrarSessaoLocal, lerSessao as lerSessaoDaPlataforma, urlDaApi } from "../../Shared/plataforma.js";
import { lerSessao } from "./sessao.js";

export { API_PADRAO, urlDaApi } from "../../Shared/plataforma.js";

let saida = "../";

/** Página inicial relativa à página atual: "../" no computador, "../../" no celular. */
export function configurarSaida(url) {
  saida = url;
}

function cabecalhos() {
  const cab = {};
  const sessao = lerSessaoDaPlataforma();
  if (!sessao) return cab;
  cab.Authorization = `Bearer ${sessao.token}`;
  const papel = lerSessao()?.papel;
  if (papel) cab["X-Papel-Usuario"] = papel;
  return cab;
}

function sessaoRecusada(status) {
  if (status !== 401) return;
  encerrarSessaoLocal();
  globalThis.window?.location?.assign(saida);
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
  sessaoRecusada(resposta.status);
  let corpo = null;
  try {
    corpo = await resposta.json();
  } catch {
    /* resposta sem JSON */
  }
  return { status: resposta.status, corpo };
}

/** Arquivo protegido (ex.: comprovante_url) como Blob: a rota exige a sessão. */
export async function baixarArquivo(caminho) {
  try {
    const resposta = await fetch(urlDaApi() + caminho, { headers: cabecalhos() });
    sessaoRecusada(resposta.status);
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
export const conciliarLancamento = (id, referenciaExtrato) =>
  requisitar(`/lancamentos/${rota(id)}/conciliar`, comJson("PATCH", { referencia_extrato: referenciaExtrato }));

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

// T-30/T-31 · US-07: orçado, realizado e saldo por projeto (só a Direção), com período e situação.
export const resumoDosProjetos = (filtros = {}) => requisitar(`/dashboard/projetos${consulta(filtros)}`);

// T-34 · US-08: trilha de auditoria do Financeiro (Coordenação e Direção), mais recentes primeiro.
export const listarAuditoria = (filtros = {}) => requisitar(`/auditoria${consulta({ modulo: "financeiro", ...filtros })}`);

export const listarNotificacoes = () => requisitar("/notificacoes");
export const marcarNotificacaoLida = (id) => requisitar(`/notificacoes/${rota(id)}/lida`, { method: "PATCH" });
