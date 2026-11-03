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

function celula(texto) {
  const t = String(texto ?? "");
  return /[;"\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
}

const decimal = (valor) => Number(valor).toFixed(2).replace(".", ",");

/** Planilha CSV (separador ";" e vírgula decimal, como o Excel em português abre). */
export function montarCsv(orcamento, doPeriodo, inicio, fim) {
  const resumo = resumoDoPeriodo(orcamento, doPeriodo);
  const linhas = [
    ["Prestação de contas", orcamento.projeto_nome || orcamento.projeto_id],
    ["Período", `${inicio} a ${fim}`],
    ["Orçado", decimal(resumo.orcado)],
    ["Executado no período", decimal(resumo.executado)],
    ["Saldo", decimal(resumo.saldo)],
    [],
    ["Data", "Categoria", "Descrição", "Valor", "Conciliado"],
    ...doPeriodo.map((l) => [l.data_despesa, l.categoria, l.descricao, decimal(l.valor), l.conciliado ? "sim" : "não"]),
  ];
  return linhas.map((linha) => linha.map(celula).join(";")).join("\r\n") + "\r\n";
}
