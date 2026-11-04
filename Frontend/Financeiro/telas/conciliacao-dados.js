// Conciliação: regras sem DOM (testáveis no Node).
import { diasDesde } from "../base/formatar.js";

export const LIMITE_DIAS_ABERTO = 7;

const centavos = (valor) => Math.round(Number(valor) * 100);

/** Itens do extrato que ainda não estão vinculados a nenhum lançamento. */
export function extratoEmAberto(extrato, lancamentos) {
  const usadas = new Set(lancamentos.filter((l) => l.conciliado && l.referencia_extrato).map((l) => l.referencia_extrato));
  return extrato.filter((item) => !usadas.has(item.referencia));
}

/** Aprovados sem conciliação, os abertos há mais tempo primeiro. */
export function aprovadosEmAberto(lancamentos) {
  return lancamentos
    .filter((l) => l.status === "aprovado" && !l.conciliado)
    .sort((a, b) => String(a.aprovado_em ?? "").localeCompare(String(b.aprovado_em ?? "")));
}

/** Ids dos lançamentos com o mesmo valor (em centavos) do item do extrato. */
export function mesmoValor(item, lancamentos) {
  if (!item) return [];
  return lancamentos.filter((l) => centavos(l.valor) === centavos(item.valor)).map((l) => l.id);
}

/** Dias desde a aprovação, ou null quando ainda não passou do limite. */
export function diasEmAberto(lancamento, agora = new Date()) {
  if (!lancamento.aprovado_em) return null;
  const dias = diasDesde(lancamento.aprovado_em, agora);
  return dias > LIMITE_DIAS_ABERTO ? dias : null;
}

/** Valores diferentes não impedem, mas a tela avisa antes de conciliar. */
export function valoresDiferentes(item, lancamento) {
  return Boolean(item && lancamento) && centavos(item.valor) !== centavos(lancamento.valor);
}
