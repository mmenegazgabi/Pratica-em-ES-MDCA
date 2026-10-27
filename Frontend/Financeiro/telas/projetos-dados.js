// Projetos: totais, gasto por categoria e validação da edição (sem DOM, testável no Node).
import { somarReais } from "../base/formatar.js";

export function totaisGerais(orcamentos, pendentes) {
  return {
    orcado: somarReais(orcamentos.map((o) => o.valor_total)),
    gasto: somarReais(orcamentos.map((o) => o.realizado)),
    disponivel: somarReais(orcamentos.map((o) => o.saldo)),
    aguardando: somarReais(pendentes.map((l) => l.valor)),
  };
}

/** Todas as categorias do orçamento (na ordem dele), com o total já aprovado de cada uma. */
export function gastoPorCategoria(orcamento, lancamentos) {
  return orcamento.categorias_despesa.map((categoria) => ({
    categoria,
    gasto: somarReais(lancamentos.filter((l) => l.orcamento_id === orcamento.id && l.status === "aprovado" && l.categoria === categoria).map((l) => l.valor)),
  }));
}

export function validarEdicao({ valor_total, data_inicio, data_fim, categorias }) {
  const erros = {};
  const valor = Number(valor_total);
  if (valor_total === "" || valor_total === null || valor_total === undefined || !(valor > 0)) erros.valor_total = "Informe um valor maior que zero.";
  if (!data_inicio) erros.data_inicio = "Informe o início da vigência.";
  if (!data_fim) erros.data_fim = "Informe o fim da vigência.";
  else if (data_inicio && data_fim < data_inicio) erros.data_fim = "O fim não pode ser antes do início.";
  if (!categorias || categorias.length === 0) erros.categorias = "Inclua ao menos uma categoria.";
  return erros;
}

/** Um projeto pode ter vários orçamentos: o vigente em `hoje` (AAAA-MM-DD) ou, sem vigente, o de início mais recente. */
export function orcamentoDoProjeto(projetoId, orcamentos, hoje) {
  const doProjeto = orcamentos.filter((o) => o.projeto_id === projetoId);
  if (doProjeto.length === 0) return null;
  const vigente = doProjeto.find((o) => o.data_inicio <= hoje && hoje <= o.data_fim);
  if (vigente) return vigente;
  return [...doProjeto].sort((a, b) => String(b.data_inicio).localeCompare(String(a.data_inicio)))[0];
}
