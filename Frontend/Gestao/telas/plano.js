// Plano e metas de um programa, ligado à API da T-44 (T-45 · US-02).
//
// Mostra objetivo → ação → metas com planejado, realizado e percentual (painel
// planejado × realizado). Cada meta tem o percentual da API; a ação mostra a média dos
// percentuais das suas metas, porque metas da mesma ação podem ter unidades diferentes
// (pessoas, encontros…) e não dá para somá-las.
//
// Quem gerencia cadastra objetivos, ações e metas e registra o realizado; os botões só
// aparecem para esses perfis, mas quem decide é a API.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { abrirFormulario, campo, hojeIso, selecao } from "../base/formulario.js";
import { dataBr } from "./programas.js";

export const PERIODICIDADES = ["semanal", "quinzenal", "mensal", "bimestral", "trimestral", "semestral", "anual"];

const API_PADRAO = {
  listarObjetivos: api.listarObjetivos,
  listarAcoes: api.listarAcoes,
  obterPainel: api.obterPainel,
  cadastrarObjetivo: api.cadastrarObjetivo,
  cadastrarAcao: api.cadastrarAcao,
  cadastrarMeta: api.cadastrarMeta,
  registrarRealizado: api.registrarRealizado,
};

const numero = (valor) => Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 2 });
const porcento = (valor) => `${Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`;
const maiuscula = (texto) => texto.charAt(0).toUpperCase() + texto.slice(1);
const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const botao = (texto, onclick, extra = {}) => el("button", { type: "button", class: "btn", onclick, ...extra }, texto);

/** Média dos percentuais das metas, com uma casa; `null` quando a ação ainda não tem metas. */
export function percentualDaAcao(metas) {
  if (!metas.length) return null;
  const media = metas.reduce((soma, m) => soma + m.percentual, 0) / metas.length;
  return Math.round(media * 10) / 10;
}

function barra(percentual) {
  const atencao = percentual < 65;
  return el(
    "div",
    { class: `progress${atencao ? " amber" : ""}`, role: "img", "aria-label": `${porcento(percentual)} realizado` },
    el("span", { style: `width:${Math.min(100, Math.max(0, percentual))}%` }),
  );
}

function linhaDaMeta(meta, registrar) {
  const unidade = meta.unidade ? ` ${meta.unidade}` : "";
  return el(
    "tr",
    {},
    el("td", {}, meta.descricao),
    el("td", {}, `${numero(meta.planejado)}${unidade}`),
    el("td", {}, `${numero(meta.realizado)}${unidade}`),
    el("td", {}, el("div", { class: "meta-percentual" }, el("strong", {}, porcento(meta.percentual)), barra(meta.percentual))),
    el("td", {}, registrar ? el("button", { type: "button", class: "text-link", onclick: () => registrar(meta) }, "Registrar realizado") : null),
  );
}

function blocoDaAcao(acao, metas, registrar) {
  const percentual = percentualDaAcao(metas);
  const resumo = el(
    "div",
    { class: "row-top" },
    el("div", {}, el("h3", {}, acao.descricao), el("small", {}, `${dataBr(acao.periodo_inicio)} a ${dataBr(acao.periodo_fim)} · acompanhamento ${acao.periodicidade}`)),
    percentual === null
      ? el("span", { class: "badge gray" }, "Sem metas")
      : el("span", { class: `badge ${percentual < 65 ? "amber" : "green"}` }, `${porcento(percentual)} da ação`),
  );
  return el(
    "div",
    { class: "plano-acao" },
    resumo,
    el("p", { class: "muted" }, `Resultado esperado: ${acao.resultado_esperado}`),
    metas.length
      ? el(
          "div",
          { class: "table-wrap" },
          el(
            "table",
            {},
            el(
              "thead",
              {},
              el("tr", {}, ["Meta", "Planejado", "Realizado", "Percentual", ""].map((c) => el("th", { scope: "col" }, c))),
            ),
            el("tbody", {}, metas.map((m) => linhaDaMeta(m, registrar))),
          ),
        )
      : el("p", { class: "muted" }, "Nenhuma meta cadastrada para esta ação."),
  );
}

export function planoDoPrograma({ objetivos, acoes, painel }, { podeGerenciar = false, acoesDeTopo = [], registrar = null } = {}) {
  const metasPorAcao = new Map();
  for (const meta of painel.metas) {
    if (!metasPorAcao.has(meta.acao_id)) metasPorAcao.set(meta.acao_id, []);
    metasPorAcao.get(meta.acao_id).push(meta);
  }
  const geral = percentualDaAcao(painel.metas);

  const topo = el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "card-head" },
      el(
        "div",
        {},
        el("h2", {}, "Planejado × realizado"),
        el(
          "small",
          {},
          geral === null
            ? "Cadastre metas para acompanhar a execução."
            : `${painel.metas.length} ${painel.metas.length === 1 ? "meta" : "metas"} · média ${porcento(geral)}`,
        ),
      ),
      podeGerenciar ? el("div", { class: "actions" }, acoesDeTopo) : null,
    ),
    el(
      "div",
      { class: "card-body" },
      el("p", { class: "muted" }, "O percentual da ação é a média dos percentuais das suas metas, porque metas da mesma ação podem ter unidades diferentes."),
    ),
  );

  if (!objetivos.length) {
    return el("div", {}, topo, el("section", { class: "card" }, vazio("Nenhum objetivo cadastrado", "Comece pelo objetivo do programa; depois cadastre as ações e as metas de cada uma.")));
  }

  const cartoes = objetivos.map((objetivo) => {
    const daqui = acoes.filter((a) => a.objetivo_id === objetivo.id);
    return el(
      "section",
      { class: "card" },
      el("div", { class: "card-head" }, el("div", {}, el("small", {}, "Objetivo"), el("h2", {}, objetivo.descricao))),
      el(
        "div",
        { class: "card-body" },
        daqui.length
          ? daqui.map((acao) => blocoDaAcao(acao, metasPorAcao.get(acao.id) || [], registrar))
          : el("p", { class: "muted" }, "Nenhuma ação cadastrada para este objetivo."),
      ),
    );
  });
  return el("div", {}, topo, cartoes);
}

export function mostrarPlano(container, programaId, { podeGerenciar = false, avisar = () => {}, ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  let atual = { objetivos: [], acoes: [] };

  const recarregar = () =>
    carregarNaTela(
      container,
      async () => {
        const [objetivos, acoes, painel] = await Promise.all([
          chamadas.listarObjetivos(programaId),
          chamadas.listarAcoes(programaId),
          chamadas.obterPainel(programaId),
        ]);
        atual = { objetivos, acoes };
        return { objetivos, acoes, painel };
      },
      (dados) =>
        planoDoPrograma(dados, {
          podeGerenciar,
          registrar: podeGerenciar ? registrarRealizado : null,
          acoesDeTopo: [
            botao("+ Objetivo", novoObjetivo),
            botao("+ Ação", novaAcao, { disabled: !dados.objetivos.length, title: dados.objetivos.length ? "" : "Cadastre um objetivo antes" }),
            botao("+ Meta", novaMeta, { disabled: !dados.acoes.length, title: dados.acoes.length ? "" : "Cadastre uma ação antes" }),
          ],
        }),
    );

  const concluir = (texto) => () => {
    avisar(texto);
    recarregar();
  };

  function novoObjetivo() {
    const descricao = el("textarea", { rows: 3, maxlength: 2000, required: true });
    abrirFormulario({
      titulo: "Novo objetivo",
      campos: [campo("f-objetivo-descricao", "Objetivo", descricao, { largo: true })],
      validar: () => (descricao.value.trim() ? "" : "Descreva o objetivo."),
      enviar: () => chamadas.cadastrarObjetivo(programaId, { descricao: descricao.value.trim() }),
      aoConcluir: concluir("Objetivo cadastrado."),
    });
  }

  function novaAcao() {
    const objetivo = selecao("objetivo_id", atual.objetivos.map((o) => [o.id, o.descricao]), { vazio: "Selecione o objetivo" });
    const descricao = el("input", { type: "text", maxlength: 2000, required: true });
    const inicio = el("input", { type: "date", required: true });
    const fim = el("input", { type: "date", required: true });
    const resultado = el("input", { type: "text", maxlength: 2000, required: true });
    const periodicidade = selecao("periodicidade", PERIODICIDADES.map((p) => [p, maiuscula(p)]), { vazio: "Selecione" });
    abrirFormulario({
      titulo: "Nova ação",
      campos: [
        campo("f-acao-objetivo", "Objetivo", objetivo, { largo: true }),
        campo("f-acao-descricao", "Ação", descricao, { largo: true }),
        campo("f-acao-inicio", "Início do período", inicio),
        campo("f-acao-fim", "Fim do período", fim),
        campo("f-acao-resultado", "Resultado esperado", resultado, { largo: true }),
        campo("f-acao-periodicidade", "Periodicidade de acompanhamento", periodicidade),
      ],
      validar: () => {
        const faltam = [
          [objetivo, "o objetivo"],
          [descricao, "a ação"],
          [inicio, "o início"],
          [fim, "o fim"],
          [resultado, "o resultado esperado"],
          [periodicidade, "a periodicidade"],
        ].filter(([no]) => !no.value.trim()).map(([, rotulo]) => rotulo);
        if (faltam.length) return `Informe ${faltam.join(", ")}.`;
        if (fim.value < inicio.value) return "O fim do período não pode ser anterior ao início.";
        return "";
      },
      enviar: () =>
        chamadas.cadastrarAcao(programaId, {
          objetivo_id: objetivo.value,
          descricao: descricao.value.trim(),
          periodo_inicio: inicio.value,
          periodo_fim: fim.value,
          resultado_esperado: resultado.value.trim(),
          periodicidade: periodicidade.value,
        }),
      aoConcluir: concluir("Ação cadastrada."),
    });
  }

  function novaMeta() {
    const acao = selecao("acao_id", atual.acoes.map((a) => [a.id, a.descricao]), { vazio: "Selecione a ação" });
    const descricao = el("input", { type: "text", maxlength: 2000, required: true });
    const planejado = el("input", { type: "number", min: "0.01", step: "0.01", required: true });
    const unidade = el("input", { type: "text", maxlength: 100 });
    abrirFormulario({
      titulo: "Nova meta",
      campos: [
        campo("f-meta-acao", "Ação", acao, { largo: true }),
        campo("f-meta-descricao", "Meta", descricao, { largo: true }),
        campo("f-meta-planejado", "Valor planejado", planejado),
        campo("f-meta-unidade", "Unidade (opcional)", unidade, { dica: "Ex.: pessoas, encontros." }),
      ],
      validar: () => {
        if (!acao.value) return "Selecione a ação.";
        if (!descricao.value.trim()) return "Descreva a meta.";
        if (!(Number(planejado.value) > 0)) return "Informe um valor planejado maior que zero.";
        return "";
      },
      enviar: () =>
        chamadas.cadastrarMeta(programaId, {
          acao_id: acao.value,
          descricao: descricao.value.trim(),
          valor_planejado: Number(planejado.value),
          unidade: unidade.value.trim() || null,
        }),
      aoConcluir: concluir("Meta cadastrada."),
    });
  }

  function registrarRealizado(meta) {
    const data = el("input", { type: "date", required: true });
    data.value = hojeIso();
    const valor = el("input", { type: "number", min: "0.01", step: "0.01", required: true });
    const observacao = el("textarea", { rows: 2, maxlength: 2000 });
    abrirFormulario({
      titulo: "Registrar realizado",
      aviso: el("p", { class: "muted" }, `${meta.descricao} · planejado ${numero(meta.planejado)}${meta.unidade ? ` ${meta.unidade}` : ""}`),
      campos: [
        campo("f-registro-data", "Data", data),
        campo("f-registro-valor", "Valor realizado", valor),
        campo("f-registro-observacao", "Observação (opcional)", observacao, { largo: true }),
      ],
      validar: () => {
        if (!data.value) return "Informe a data.";
        if (!(Number(valor.value) > 0)) return "Informe um valor realizado maior que zero.";
        return "";
      },
      enviar: () =>
        chamadas.registrarRealizado(programaId, meta.meta_id, {
          data: data.value,
          valor_realizado: Number(valor.value),
          observacao: observacao.value.trim() || null,
        }),
      aoConcluir: concluir("Realizado registrado."),
    });
  }

  return recarregar();
}
