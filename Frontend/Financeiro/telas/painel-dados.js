// Painel da Diretoria (T-30/T-31 · US-07): regras sem DOM (testáveis no Node).
import { somarReais } from "../base/formatar.js";

/** Filtro de situação do projeto: valor na tela → rótulo. "todos" não vai para a API. */
export const SITUACOES = [
  ["todos", "Todos"],
  ["ativo", "Ativos"],
  ["encerrado", "Encerrados"],
];

/** Filtros iniciais a partir da rota (#/painel?inicio=…&fim=…&situacao=…). */
export function filtrosDaRota(parametros = {}) {
  const data = (v) => (/^\d{4}-\d{2}-\d{2}$/.test(String(v || "")) ? v : "");
  const situacao = SITUACOES.some(([v]) => v === parametros.situacao) ? parametros.situacao : "todos";
  return { inicio: data(parametros.inicio), fim: data(parametros.fim), situacao };
}

/** Mensagem de erro do período, ou "". Uma ponta só vale: a API aceita. */
export function validarPeriodo(inicio, fim) {
  if (inicio && fim && fim < inicio) return "O fim do período não pode ser antes do início.";
  return "";
}

/** Filtros da tela → parâmetros de GET /dashboard/projetos (vazios ficam de fora). */
export function filtrosDaApi({ inicio, fim, situacao }) {
  return {
    data_inicio: inicio || "",
    data_fim: fim || "",
    status: situacao && situacao !== "todos" ? situacao : "",
  };
}

/** Totais dos projetos exibidos, somados em centavos. */
export function totais(resumos) {
  return {
    orcado: somarReais(resumos.map((r) => r.orcado)),
    realizado: somarReais(resumos.map((r) => r.realizado)),
    saldo: somarReais(resumos.map((r) => r.saldo)),
  };
}

/** Percentual do orçado já realizado; null sem orçamento no período. */
export function percentualExecutado({ orcado, realizado }) {
  return orcado > 0 ? (realizado / orcado) * 100 : null;
}

/** Projetos em ordem de nome, para a tabela não mudar de ordem entre consultas. */
export function ordenar(resumos) {
  return [...resumos].sort((a, b) => String(a.nome).localeCompare(String(b.nome), "pt-BR"));
}

/** Texto do que está sendo exibido: "Projetos ativos · de 01/03/2026 a 30/06/2026". */
export function descreverFiltros({ inicio, fim, situacao }, formatarData) {
  const quais = { todos: "Todos os projetos", ativo: "Projetos ativos", encerrado: "Projetos encerrados" }[situacao] || "Todos os projetos";
  let periodo = "todo o período";
  if (inicio && fim) periodo = `de ${formatarData(inicio)} a ${formatarData(fim)}`;
  else if (inicio) periodo = `a partir de ${formatarData(inicio)}`;
  else if (fim) periodo = `até ${formatarData(fim)}`;
  return `${quais} · ${periodo}`;
}

/** Mensagem para a tabela vazia, de acordo com o filtro de situação. */
export function mensagemSemProjetos(situacao) {
  if (situacao === "ativo") return "Nenhum projeto ativo.";
  if (situacao === "encerrado") return "Nenhum projeto encerrado.";
  return "Nenhum projeto cadastrado ainda.";
}
