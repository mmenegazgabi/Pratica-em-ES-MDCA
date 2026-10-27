// Lançamentos: contagens, saldo e validação do motivo (sem DOM, testável no Node).
import { somarReais } from "../base/formatar.js";

export const MOTIVO_MAXIMO = 500;

export function contarPorStatus(lancamentos) {
  const contagem = { pendente: 0, aprovado: 0, rejeitado: 0, todos: lancamentos.length };
  for (const l of lancamentos) {
    if (l.status in contagem && l.status !== "todos") contagem[l.status] += 1;
  }
  return contagem;
}

/** Saldo do orçamento depois de aprovar o lançamento (em reais, sem erro de ponto flutuante). */
export function saldoAposAprovar(orcamento, lancamento) {
  return somarReais([orcamento.saldo, -lancamento.valor]);
}

export function validarMotivo(texto) {
  const motivo = String(texto ?? "").trim();
  if (!motivo) return "Informe o motivo da rejeição.";
  if (motivo.length > MOTIVO_MAXIMO) return `Use no máximo ${MOTIVO_MAXIMO} caracteres.`;
  return null;
}

/** Fila de aprovação: mais antigas primeiro; demais abas: mais novas primeiro. */
export function ordenarParaAba(lancamentos, status) {
  const sentido = status === "pendente" ? 1 : -1;
  return [...lancamentos].sort((a, b) => sentido * String(a.criado_em ?? "").localeCompare(String(b.criado_em ?? "")));
}
