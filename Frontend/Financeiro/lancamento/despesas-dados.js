// Redesign Financeiro · celular — dados da tela "Minhas despesas" (sem DOM, testável no Node).

import { formatarDataCurta } from "../base/formatar.js";

const STATUS = {
  pendente: { texto: "Em análise", classe: "etiqueta--pendente" },
  aprovado: { texto: "Aprovada", classe: "etiqueta--aprovado" },
  rejeitado: { texto: "Rejeitada", classe: "etiqueta--rejeitado" },
};

/** GET /lancamentos vem dos mais antigos para os mais novos; aqui invertemos. */
function maisRecentesPrimeiro(lancamentos) {
  return [...lancamentos].sort((a, b) => String(b.criado_em).localeCompare(String(a.criado_em)));
}

/**
 * Separa o que o educador precisa ver: rejeitadas (ajuste), fotos sem dados
 * (a completar) e as demais (enviadas, no máximo `limiteEnviadas`).
 */
export function agruparDespesas(lancamentos, rascunhos, { limiteEnviadas = 5 } = {}) {
  const ordenados = maisRecentesPrimeiro(lancamentos || []);
  return {
    ajuste: ordenados.filter((l) => l.status === "rejeitado"),
    aCompletar: [...(rascunhos || [])],
    enviadas: ordenados.filter((l) => l.status !== "rejeitado").slice(0, limiteEnviadas),
  };
}

/** Orçamento da despesa mais recente — o projeto que o educador costuma usar. */
export function ultimoProjetoUsado(lancamentos) {
  const [maisRecente] = maisRecentesPrimeiro(lancamentos || []);
  return maisRecente ? maisRecente.orcamento_id : null;
}

export function rotuloDoStatus(status) {
  return STATUS[status] || { texto: status, classe: "etiqueta--pendente" };
}

export function nomeDoProjeto(orcamentoId, orcamentos, reserva = "") {
  const orcamento = (orcamentos || []).find((o) => o.id === orcamentoId);
  if (!orcamento) return reserva || "";
  return orcamento.projeto_nome || orcamento.projeto_id;
}

/** "Hoje, 10:42" ou "26/10, 09:05", no fuso do aparelho. */
export function quandoFoiTirada(isoDataHora, agora = new Date()) {
  const quando = new Date(isoDataHora);
  const hora = `${String(quando.getHours()).padStart(2, "0")}:${String(quando.getMinutes()).padStart(2, "0")}`;
  const mesmoDia = quando.toDateString() === agora.toDateString();
  if (mesmoDia) return `Hoje, ${hora}`;
  const dia = `${String(quando.getDate()).padStart(2, "0")}/${String(quando.getMonth() + 1).padStart(2, "0")}`;
  return `${dia}, ${hora}`;
}

/** "Esporte · 23/10" — linha de baixo de cada despesa na lista. */
export function legendaDaDespesa(lancamento, orcamentos) {
  const projeto = nomeDoProjeto(lancamento.orcamento_id, orcamentos, lancamento.projeto_id);
  const data = lancamento.data_despesa ? formatarDataCurta(lancamento.data_despesa) : "";
  return [projeto, data].filter(Boolean).join(" · ");
}
