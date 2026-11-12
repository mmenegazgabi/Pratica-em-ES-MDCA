// Painel da Diretoria (T-30/T-31 · US-07): orçado, realizado e saldo de cada projeto,
// filtrados por período e por situação (ativo/encerrado). Os números vêm prontos de
// GET /dashboard/projetos: a tela só escolhe os filtros e mostra o resultado.
import { el, limpar } from "../base/dom.js";
import { formatarData, formatarMoeda } from "../base/formatar.js";
import { resumoDosProjetos } from "../base/api.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import {
  SITUACOES,
  descreverFiltros,
  filtrosDaApi,
  filtrosDaRota,
  mensagemSemProjetos,
  ordenar,
  percentualExecutado,
  totais,
  validarPeriodo,
} from "./painel-dados.js";

function campo(rotulo, id, controle) {
  return el("div", { class: "campo", style: "margin:0" }, el("label", { for: id }, rotulo), controle);
}

function numero(rotulo, valor) {
  return el(
    "div",
    { class: "caixa", style: "padding:12px 14px" },
    el("div", { style: "font-size:11px;color:var(--texto-suave)" }, rotulo),
    el("div", { class: "num", style: "font-size:18px;font-weight:600;margin-top:2px" }, valor),
  );
}

function situacao(status) {
  return el("span", { class: `etiqueta ${status === "encerrado" ? "etiqueta--rejeitado" : "etiqueta--aprovado"}` }, status === "encerrado" ? "Encerrado" : "Ativo");
}

function execucao(resumo) {
  const percentual = percentualExecutado(resumo);
  if (percentual === null) return el("span", { style: "color:var(--texto-suave)" }, "Sem orçamento");
  const classe = percentual > 100 ? "barra-uso barra-uso--critica" : percentual >= 80 ? "barra-uso barra-uso--alerta" : "barra-uso";
  return el(
    "div",
    { style: "display:flex;gap:8px;align-items:center" },
    el("div", { class: classe, style: "width:90px" }, el("i", { style: `width:${Math.max(0, Math.min(100, percentual))}%` })),
    el("span", { class: "num" }, `${Math.floor(percentual)}%`),
  );
}

export async function mostrar(container, { parametros = {} } = {}) {
  const filtros = filtrosDaRota(parametros);
  const inicio = el("input", { id: "painel-inicio", class: "entrada", type: "date", value: filtros.inicio });
  const fim = el("input", { id: "painel-fim", class: "entrada", type: "date", value: filtros.fim });
  const aplicar = el("button", { type: "submit", class: "btn" }, "Aplicar");
  const todoPeriodo = el("button", { type: "button", class: "btn btn--sec" }, "Todo o período");
  const erro = el("p", { role: "alert", style: "margin:8px 0 0;color:var(--perigo-texto);font-size:12px", hidden: true });
  const situacoes = el("div", { role: "group", "aria-label": "Situação do projeto", style: "display:flex;flex-wrap:wrap;gap:6px" });
  const descricao = el("p", { class: "painel-descricao", style: "margin:14px 0 10px;color:var(--texto-suave);font-size:12px" });
  const resultado = el("div", { "aria-live": "polite" });
  let pedido = 0; // só a resposta da consulta mais recente é desenhada

  function desenharSituacoes() {
    limpar(situacoes).append(
      ...SITUACOES.map(([valor, rotulo]) =>
        el(
          "button",
          {
            type: "button",
            class: `filtro${filtros.situacao === valor ? " filtro--ativo" : ""}`,
            "aria-pressed": String(filtros.situacao === valor),
            onclick: () => {
              filtros.situacao = valor;
              desenharSituacoes();
              consultar();
            },
          },
          rotulo,
        ),
      ),
    );
  }

  function desenharResultado(resumos) {
    const linhas = ordenar(resumos);
    const t = totais(linhas);
    limpar(resultado).append(
      el(
        "div",
        { style: "display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:14px" },
        numero("Orçado", formatarMoeda(t.orcado)),
        numero("Realizado", formatarMoeda(t.realizado)),
        numero("Saldo", formatarMoeda(t.saldo)),
      ),
      linhas.length === 0
        ? el("p", { class: "vazio" }, mensagemSemProjetos(filtros.situacao))
        : el(
            "div",
            { class: "caixa", style: "overflow-x:auto" },
            el(
              "table",
              { class: "tabela" },
              el(
                "thead",
                {},
                el(
                  "tr",
                  {},
                  el("th", {}, "Projeto"),
                  el("th", {}, "Situação"),
                  el("th", { class: "num" }, "Orçado"),
                  el("th", { class: "num" }, "Realizado"),
                  el("th", { class: "num" }, "Saldo"),
                  el("th", {}, "Executado"),
                ),
              ),
              el(
                "tbody",
                {},
                linhas.map((r) =>
                  el(
                    "tr",
                    { "data-projeto": r.projeto_id },
                    el("td", {}, r.nome),
                    el("td", {}, situacao(r.status)),
                    el("td", { class: "num" }, formatarMoeda(r.orcado)),
                    el("td", { class: "num" }, formatarMoeda(r.realizado)),
                    el("td", { class: "num" }, formatarMoeda(r.saldo)),
                    el("td", {}, execucao(r)),
                  ),
                ),
              ),
            ),
          ),
      el("p", { style: "margin:10px 0 0;color:var(--texto-suave);font-size:11px" }, "Realizado: só despesas aprovadas com data dentro do período. Orçado: orçamentos cuja vigência cruza o período."),
    );
  }

  async function consultar() {
    filtros.inicio = inicio.value;
    filtros.fim = fim.value;
    const invalido = validarPeriodo(filtros.inicio, filtros.fim);
    erro.hidden = !invalido;
    erro.textContent = invalido;
    if (invalido) return;
    descricao.textContent = descreverFiltros(filtros, formatarData);
    const este = ++pedido;
    limpar(resultado).append(el("p", { class: "carregando" }, "Carregando…"));
    const resposta = await resumoDosProjetos(filtrosDaApi(filtros));
    if (este !== pedido) return;
    if (falhou(resposta)) {
      return limpar(resultado).append(
        el("p", { class: "aviso-tela", role: "alert" }, mensagemDeErro(resposta, "Não foi possível carregar o painel. Tente de novo.")),
      );
    }
    desenharResultado(resposta.corpo || []);
  }

  todoPeriodo.addEventListener("click", () => {
    inicio.value = "";
    fim.value = "";
    consultar();
  });
  const formulario = el(
    "form",
    {
      novalidate: true,
      style: "display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end",
      onsubmit: (evento) => {
        evento.preventDefault();
        consultar();
      },
    },
    campo("Início do período", "painel-inicio", inicio),
    campo("Fim do período", "painel-fim", fim),
    aplicar,
    todoPeriodo,
    el("div", { style: "margin-left:auto" }, situacoes),
  );

  desenharSituacoes();
  limpar(container).append(
    el("h1", {}, "Painel"),
    el("p", { class: "sub" }, "Orçado, realizado e saldo de cada projeto"),
    formulario,
    erro,
    descricao,
    resultado,
  );
  await consultar();
}
