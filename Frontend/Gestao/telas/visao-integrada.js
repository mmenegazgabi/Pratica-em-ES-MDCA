// Visão integrada da execução física e financeira (T-79 · US-12), ligada à API da T-78.
//
// Para o programa e o período escolhidos, mostra lado a lado as metas da Gestão
// (planejado × realizado) e o orçado, o realizado e o saldo do Financeiro. Mudar o
// programa ou o período faz uma única consulta, então as duas partes mudam juntas.
//
// A API decide o que cada papel vê: sem acesso aos valores financeiros, a parte
// financeira vem vazia e a tela mostra só a execução física. Programa sem projeto no
// Financeiro também mostra só a execução física, sem erro.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";

const API_PADRAO = { listarProgramas: api.listarProgramas, obterVisaoIntegrada: api.obterVisaoIntegrada };

const dataBr = (iso) => (iso ? String(iso).split("-").reverse().join("/") : "");
const numero = (valor) => Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const porcento = (valor) => `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
export const dinheiro = (valor) => Number(valor).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

function cartao(titulo, subtitulo, corpo, extra = null) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), extra),
    el("div", { class: "card-body" }, corpo),
  );
}

function barra(percentual) {
  return el(
    "div",
    { class: `progress${percentual < 65 ? " amber" : ""}`, role: "img", "aria-label": `${porcento(percentual)}` },
    el("span", { style: `width:${Math.min(100, Math.max(0, percentual))}%` }),
  );
}

const indicador = (rotulo, valor, nota = "") =>
  el("div", { class: "stat" }, el("div", { class: "stat-top" }, rotulo), el("div", { class: "stat-value" }, valor), el("div", { class: "stat-note" }, nota));

export function periodoDescrito(inicio, fim) {
  if (inicio && fim) return `de ${dataBr(inicio)} a ${dataBr(fim)}`;
  if (inicio) return `a partir de ${dataBr(inicio)}`;
  if (fim) return `até ${dataBr(fim)}`;
  return "todo o período";
}

function fisica({ metas, percentual_medio: medio }) {
  if (!metas.length) {
    return cartao(
      "Execução física",
      "Gestão · metas do plano de ação",
      el("div", { class: "empty" }, el("h2", {}, "Nenhuma meta cadastrada"), el("p", {}, "Cadastre as metas no Plano e metas do programa.")),
    );
  }
  const linhas = metas.map((m) => {
    const unidade = m.unidade ? ` ${m.unidade}` : "";
    return el(
      "tr",
      {},
      el("td", {}, el("strong", {}, m.descricao), el("small", {}, m.acao)),
      el("td", {}, `${numero(m.planejado)}${unidade}`),
      el("td", {}, `${numero(m.realizado)}${unidade}`),
      el("td", {}, el("div", { class: "meta-percentual" }, el("strong", {}, porcento(m.percentual)), barra(m.percentual))),
    );
  });
  return cartao(
    "Execução física",
    "Gestão · metas do plano de ação",
    el(
      "div",
      { class: "pilha-justa" },
      el("div", { class: "stats integrada-stats" }, indicador("Média das metas", porcento(medio), `${metas.length} ${metas.length === 1 ? "meta" : "metas"}`)),
      el(
        "div",
        { class: "table-wrap" },
        el(
          "table",
          {},
          el("thead", {}, el("tr", {}, ["Meta", "Planejado", "Realizado", "Percentual"].map((c) => el("th", { scope: "col" }, c)))),
          el("tbody", {}, linhas),
        ),
      ),
    ),
  );
}

function financeira(dados) {
  if (dados === null) {
    return cartao(
      "Execução financeira",
      "Financeiro",
      el("p", { class: "muted", role: "note" }, "Seu perfil vê só a execução física deste programa. Os valores financeiros ficam com a coordenação, a direção e a administração."),
    );
  }
  if (dados.vinculo === "nenhum") {
    return cartao(
      "Execução financeira",
      "Financeiro",
      el("p", { class: "muted", role: "note" }, "Este programa ainda não tem projeto no Financeiro. A visão mostra só a execução física."),
    );
  }
  const executado = dados.percentual_executado;
  return cartao(
    "Execução financeira",
    `Financeiro · projeto ${dados.projeto}`,
    el(
      "div",
      { class: "pilha-justa" },
      el(
        "div",
        { class: "stats integrada-stats" },
        indicador("Orçado", dinheiro(dados.orcado)),
        indicador("Realizado", dinheiro(dados.realizado), "lançamentos aprovados"),
        indicador("Saldo", dinheiro(dados.saldo)),
      ),
      executado === null
        ? el("p", { class: "muted" }, "Sem orçamento no período.")
        : el("div", {}, el("div", { class: "progress-label" }, el("span", {}, "Executado do orçamento"), el("strong", {}, porcento(executado))), barra(executado)),
      dados.vinculo === "nome"
        ? el(
            "p",
            { class: "muted integrada-vinculo", role: "note" },
            `O projeto do Financeiro foi encontrado pelo nome (${dados.projeto}), porque o Financeiro ainda tem cadastro próprio de projetos. Quando ele usar o cadastro único, o vínculo passa a ser pelo identificador.`,
          )
        : null,
    ),
  );
}

export function visaoDoPrograma(visao) {
  const { programa, inicio, fim } = visao;
  return el(
    "div",
    {},
    el(
      "p",
      { class: "integrada-resumo" },
      el("strong", {}, programa.nome),
      programa.identificador ? el("code", {}, programa.identificador) : null,
      el("span", { class: "muted" }, ` · ${periodoDescrito(inicio, fim)}`),
    ),
    el("div", { class: "detail-grid integrada-grid" }, fisica(visao.fisica), financeira(visao.financeira)),
  );
}

export function mostrarVisaoIntegrada(container, { programaInicial = "", ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };

  return carregarNaTela(container, chamadas.listarProgramas, (programas) => {
    if (!programas?.length) {
      return cartao(
        "Visão integrada",
        null,
        el("div", { class: "empty" }, el("h2", {}, "Nenhum programa cadastrado"), el("p", {}, "Cadastre um programa para acompanhar a execução física e financeira.")),
      );
    }
    const escolhido = programas.some((p) => p.id === programaInicial) ? programaInicial : programas[0].id;
    const programa = el(
      "select",
      { class: "filter-control", "aria-label": "Programa", name: "programa" },
      programas.map((p) => el("option", { value: p.id }, p.identificador ? `${p.nome} (${p.identificador})` : p.nome)),
    );
    programa.value = escolhido;
    const inicio = el("input", { type: "date", class: "filter-control", "aria-label": "Início do período", name: "inicio" });
    const fim = el("input", { type: "date", class: "filter-control", "aria-label": "Fim do período", name: "fim" });
    const aviso = el("p", { class: "error-message", role: "alert", hidden: true });
    const resultado = el("div", { class: "integrada-resultado" });

    function consultar() {
      if (inicio.value && fim.value && fim.value < inicio.value) {
        aviso.textContent = "O fim do período não pode ser anterior ao início.";
        aviso.hidden = false;
        return;
      }
      aviso.hidden = true;
      // Uma consulta só para as duas partes: física e financeira mudam juntas.
      carregarNaTela(
        resultado,
        () => chamadas.obterVisaoIntegrada(programa.value, { inicio: inicio.value, fim: fim.value }),
        visaoDoPrograma,
      );
    }

    function limpar() {
      inicio.value = "";
      fim.value = "";
      consultar();
    }

    programa.addEventListener("change", consultar);
    const filtros = el(
      "form",
      {
        class: "toolbar integrada-filtros",
        novalidate: true,
        onsubmit: (evento) => {
          evento.preventDefault();
          // O app tem um tratador global de submit para os formulários do protótipo.
          evento.stopPropagation();
          consultar();
        },
      },
      el(
        "div",
        { class: "filters" },
        el("span", { class: "filter-label" }, "Programa"),
        programa,
        el("span", { class: "filter-label" }, "Período"),
        inicio,
        el("span", { class: "filter-label" }, "a"),
        fim,
        el("button", { type: "submit", class: "btn" }, "Aplicar"),
        el("button", { type: "button", class: "text-link", onclick: limpar }, "Todo o período"),
      ),
    );
    consultar();
    return el("div", { class: "stack" }, filtros, aviso, resultado);
  });
}
