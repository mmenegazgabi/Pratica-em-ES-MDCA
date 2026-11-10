// Prestação de contas: regras sem DOM (testáveis no Node).
import { somarReais } from "../base/formatar.js";

/** Aprovados com data da despesa dentro do período (inclusive), em ordem de data. */
export function lancamentosDoPeriodo(lancamentos, inicio, fim) {
  return lancamentos
    .filter((l) => l.status === "aprovado" && l.data_despesa && l.data_despesa >= inicio && l.data_despesa <= fim)
    .sort((a, b) => a.data_despesa.localeCompare(b.data_despesa));
}

/** Números do topo do relatório. */
export function resumoDoPeriodo(orcamento, doPeriodo) {
  return {
    orcado: orcamento.valor_total,
    executado: somarReais(doPeriodo.map((l) => l.valor)),
    saldo: orcamento.saldo,
    naoConciliados: doPeriodo.filter((l) => !l.conciliado).length,
  };
}

/** Período válido: as duas datas preenchidas e o fim não antes do início. */
export function validarPeriodo(inicio, fim) {
  if (!inicio || !fim) return "Informe o início e o fim do período.";
  if (fim < inicio) return "O fim do período não pode ser antes do início.";
  return null;
}

/** Nome do arquivo quando a API não manda o Content-Disposition. */
export function nomePadraoDoRelatorio(orcamento, inicio, fim, formato) {
  const projeto = String(orcamento.projeto_nome || orcamento.projeto_id || "projeto")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `prestacao-de-contas-${projeto || "projeto"}-${inicio}-a-${fim}.${formato}`;
}
