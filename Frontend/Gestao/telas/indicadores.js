// Painel de indicadores (T-73 · US-10), ligado à API da T-72.
//
// Os filtros de programa e mês fazem uma consulta só: cartões, gráfico, tabela e metas
// vêm da mesma resposta, então mudam juntos. A tela não calcula nada; só mostra os
// números da API, que são os mesmos da Visão geral e do relatório técnico.
//
// Período em aberto (o mês inclui hoje ou o futuro): a tela avisa que os números ainda
// podem mudar. A resposta só traz números agregados, sem nome de pessoa.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";

const API_PADRAO = { obterIndicadores: api.obterIndicadores };

const dataBr = (iso) => String(iso).split("-").reverse().join("/");
const numero = (valor) => Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
const porcento = (valor) => (valor === null || valor === undefined ? "—" : `${numero(valor)}%`);
const contagem = (valor, um, varios) => `${numero(valor)} ${valor === 1 ? um : varios}`;
const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];

/** "AAAA-MM" do mês de hoje (hora local). */
export function mesAtual(hoje = new Date()) {
  return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
}

/** "setembro de 2026" para "2026-09-01". */
export function mesDescrito(iso) {
  const [ano, mes] = String(iso).split("-");
  return `${MESES[Number(mes) - 1]} de ${ano}`;
}

function cartao(titulo, subtitulo, corpo) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null)),
    el("div", { class: "card-body" }, corpo),
  );
}

const indicador = (rotulo, valor, nota) =>
  el("div", { class: "stat" }, el("div", { class: "stat-top" }, rotulo), el("div", { class: "stat-value" }, valor), el("div", { class: "stat-note" }, nota));

function barra(percentual) {
  return el(
    "div",
    { class: `progress${percentual < 65 ? " amber" : ""}`, role: "img", "aria-label": porcento(percentual) },
    el("span", { style: `width:${Math.min(100, Math.max(0, percentual))}%` }),
  );
}

export function avisoDoPeriodo({ inicio, fim, fechado }) {
  const texto = fechado
    ? `Período fechado: ${dataBr(inicio)} a ${dataBr(fim)}.`
    : `Período em aberto (${dataBr(inicio)} a ${dataBr(fim)}): os números ainda podem mudar com as próximas chamadas.`;
  return el("p", { class: `indicadores-periodo${fechado ? "" : " em-aberto"}`, role: "note" }, texto);
}

function cartoes({ totais, programas }) {
  const n = programas.length;
  return el(
    "div",
    { class: "stats" },
    indicador("Pessoas acompanhadas", numero(totais.pessoas_acompanhadas), `em ${n} ${n === 1 ? "programa" : "programas"}`),
    indicador("Encontros realizados", numero(totais.encontros_realizados), "com chamada registrada"),
    indicador("Frequência", porcento(totais.frequencia), `${contagem(totais.presencas, "presença", "presenças")} e ${contagem(totais.ausencias, "ausência", "ausências")}`),
    indicador("Horas de atividades", `${numero(totais.horas_de_atividades)} h`, "pela duração das turmas"),
  );
}

function grafico(programas) {
  const maior = Math.max(1, ...programas.map((p) => p.numeros.presencas + p.numeros.ausencias));
  const altura = (valor) => `height:${(valor / maior) * 100}%`;
  return cartao(
    "Presenças e ausências por programa",
    "Participações registradas nas chamadas do período",
    el(
      "div",
      {},
      el(
        "div",
        { class: "chart", role: "img", "aria-label": "Presenças e ausências por programa" },
        programas.map((p) =>
          el(
            "div",
            { class: "chart-column" },
            el("span", { title: `${p.numeros.presencas} presenças`, style: altura(p.numeros.presencas) }),
            el("span", { class: "plan", title: `${p.numeros.ausencias} ausências`, style: altura(p.numeros.ausencias) }),
            el("small", {}, p.identificador || p.nome),
          ),
        ),
      ),
      el("div", { class: "chart-legend" }, el("span", {}, "Presenças"), el("span", {}, "Ausências")),
    ),
  );
}

function tabela(programas) {
  return el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        {},
        el("thead", {}, el("tr", {}, ["Programa", "Pessoas", "Encontros", "Frequência", "Horas"].map((c) => el("th", { scope: "col" }, c)))),
        el(
          "tbody",
          {},
          programas.map(({ nome, numeros: n }) =>
            el(
              "tr",
              {},
              el("td", {}, el("strong", {}, nome)),
              el("td", {}, numero(n.pessoas_acompanhadas)),
              el("td", {}, numero(n.encontros_realizados)),
              el("td", {}, porcento(n.frequencia)),
              el("td", {}, `${numero(n.horas_de_atividades)} h`),
            ),
          ),
        ),
      ),
    ),
  );
}

function metas(programas, fim) {
  const linhas = programas.map(({ nome, numeros: n }) =>
    el(
      "div",
      { class: "indicadores-meta" },
      el(
        "div",
        { class: "progress-label" },
        el("span", {}, nome),
        el("strong", {}, n.metas ? porcento(n.percentual_medio_das_metas) : "Sem metas"),
      ),
      n.metas ? barra(n.percentual_medio_das_metas) : null,
    ),
  );
  return cartao("Metas do plano de ação", `Média das metas de cada programa, com o realizado até ${dataBr(fim)}`, el("div", { class: "pilha-justa" }, linhas));
}

export function painel(resposta) {
  const { periodo, programas } = resposta;
  if (!programas.length) {
    return el(
      "div",
      { class: "stack" },
      avisoDoPeriodo(periodo),
      cartao(
        "Indicadores",
        null,
        el("div", { class: "empty" }, el("h2", {}, "Nenhum programa no seu recorte"), el("p", {}, "Os indicadores aparecem para os programas em que você tem vínculo ativo.")),
      ),
    );
  }
  return el(
    "div",
    { class: "stack" },
    avisoDoPeriodo(periodo),
    cartoes(resposta),
    el("div", { class: "grid-main" }, grafico(programas), metas(programas, periodo.fim)),
    tabela(programas),
    el("p", { class: "muted texto-12", role: "note" }, "Esta visão usa só números agregados, sem identificar as pessoas atendidas."),
  );
}

export function mostrarIndicadores(container, { programaInicial = "", hoje = new Date(), ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const programa = el("select", { class: "filter-control", "aria-label": "Programa", name: "programa" }, el("option", { value: "" }, "Todos os programas"));
  const mes = el("input", { type: "month", class: "filter-control", "aria-label": "Mês", name: "mes" });
  mes.value = mesAtual(hoje);
  const resultado = el("div", { class: "indicadores-resultado" });
  let programasConhecidos = false;

  function preencherProgramas(resposta) {
    // A primeira resposta, sem filtro de programa, traz os programas que a pessoa vê.
    if (programasConhecidos || programa.value) return;
    programasConhecidos = true;
    for (const p of resposta.programas) {
      programa.append(el("option", { value: p.programa_id }, p.identificador ? `${p.nome} (${p.identificador})` : p.nome));
    }
    if (programaInicial && resposta.programas.some((p) => p.programa_id === programaInicial)) {
      programa.value = programaInicial;
      consultar();
      return true;
    }
    return false;
  }

  function consultar() {
    const inicio = mes.value ? `${mes.value}-01` : "";
    // Uma consulta só: cartões, gráfico, tabela e metas mudam juntos.
    carregarNaTela(
      resultado,
      () => chamadas.obterIndicadores({ programaId: programa.value, inicio }),
      (resposta) => {
        if (preencherProgramas(resposta)) return el("div", {});
        return painel(resposta);
      },
    );
  }

  programa.addEventListener("change", consultar);
  mes.addEventListener("change", consultar);
  const filtros = el(
    "div",
    { class: "toolbar" },
    el("div", { class: "filters" }, el("span", { class: "filter-label" }, "Programa"), programa, el("span", { class: "filter-label" }, "Mês"), mes),
  );
  const tela = el("div", { class: "stack" }, filtros, resultado);
  container.replaceChildren(tela);
  consultar();
  return tela;
}
