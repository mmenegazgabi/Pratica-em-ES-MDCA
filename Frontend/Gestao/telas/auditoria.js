// Auditoria: a trilha única da plataforma (Gestão, Financeiro, acesso e contas), lida de
// GET /auditoria. Uma tela só para os dois módulos, no menu único e no menu da Gestão.
//
// Só leitura: nenhuma ação altera ou apaga um registro (o banco também recusa). A API
// decide o que cada papel vê: Coordenação, Direção e Administração veem tudo; a
// Psicologia vê só os próprios registros (`escopo: "proprios"`); os demais recebem 403.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import {
  MODULOS,
  filtrarAuditoria,
  filtrosDaApi,
  formatarQuando,
  intervaloDaPagina,
  rotuloDoModulo,
  ultimaPagina,
} from "../../Shared/auditoria-dados.js";

const TOM_DO_MODULO = { gestao: "green", financeiro: "blue", plataforma: "amber" };

function linha(r) {
  return el(
    "tr",
    { "data-codigo": r.codigo, "data-modulo": r.modulo },
    el("td", { class: "auditoria-quando" }, formatarQuando(r.quando)),
    el("td", {}, el("span", { class: `badge ${TOM_DO_MODULO[r.modulo] || ""}`.trim() }, rotuloDoModulo(r.modulo))),
    el("td", {}, r.quem || "—"),
    el("td", {}, r.acao),
    el("td", {}, r.alvo || "—"),
  );
}

/** Tabela de uma página da trilha; `busca` filtra só o que já veio. */
export function tabelaDaAuditoria(pagina, busca = "", { irPara = () => {} } = {}) {
  const registros = filtrarAuditoria(pagina.itens || [], busca);
  const aviso =
    pagina.escopo === "proprios"
      ? el("div", { class: "info-box", id: "auditoria-escopo", role: "note" }, el("span", {}, "Você vê só os registros feitos por você."))
      : null;

  if (!pagina.total) {
    return el("div", { class: "stack" }, aviso, el("section", { class: "card" }, el("div", { class: "empty" }, el("h2", {}, "Nenhuma ação registrada"), el("p", {}, "Nada foi registrado com estes filtros."))));
  }
  const lista = registros.length
    ? el(
        "div",
        { class: "table-wrap" },
        el(
          "table",
          { id: "auditoria-tabela" },
          el("thead", {}, el("tr", {}, ["Quando", "Módulo", "Quem", "Ação", "Detalhe"].map((c) => el("th", { scope: "col" }, c)))),
          el("tbody", {}, registros.map(linha)),
        ),
      )
    : el("div", { class: "empty" }, el("p", {}, "Nenhuma ação desta página corresponde à busca."));

  const anterior = el("button", { type: "button", class: "btn", id: "auditoria-anterior", disabled: pagina.pagina <= 1, onclick: () => irPara(pagina.pagina - 1) }, "Anterior");
  const proxima = el(
    "button",
    { type: "button", class: "btn", id: "auditoria-proxima", disabled: pagina.pagina >= ultimaPagina(pagina.tamanho, pagina.total), onclick: () => irPara(pagina.pagina + 1) },
    "Próxima",
  );
  return el(
    "div",
    { class: "stack" },
    aviso,
    el(
      "section",
      { class: "card" },
      lista,
      el(
        "div",
        { class: "auditoria-paginas" },
        el("span", { class: "muted", id: "auditoria-intervalo" }, intervaloDaPagina(pagina.pagina, pagina.tamanho, pagina.total)),
        anterior,
        proxima,
      ),
    ),
  );
}

export function mostrarAuditoria(container, { listar = api.listarAuditoria } = {}) {
  const estado = { modulo: "todos", desde: "", ate: "", pagina: 1 };
  let ultima = null; // última página recebida, para a busca filtrar sem chamar a API

  const modulo = el(
    "select",
    { class: "filter-control", id: "auditoria-modulo", name: "modulo", "aria-label": "Módulo" },
    MODULOS.map(([valor, texto]) => el("option", { value: valor }, texto)),
  );
  const desde = el("input", { type: "date", class: "filter-control", id: "auditoria-desde", name: "desde", "aria-label": "De" });
  const ate = el("input", { type: "date", class: "filter-control", id: "auditoria-ate", name: "ate", "aria-label": "Até" });
  const busca = el("input", { type: "search", class: "filter-control", id: "auditoria-busca", placeholder: "Pessoa, ação ou detalhe", "aria-label": "Buscar nesta página" });
  const aviso = el("p", { class: "error-message", role: "alert", hidden: true });
  const resultado = el("div", { class: "auditoria-resultado", "aria-live": "polite" });

  function desenhar() {
    if (ultima) resultado.replaceChildren(tabelaDaAuditoria(ultima, busca.value, { irPara }));
  }

  function irPara(numero) {
    estado.pagina = numero;
    return carregarNaTela(
      resultado,
      () => listar(filtrosDaApi(estado)),
      (pagina) => {
        ultima = { itens: [], total: 0, pagina: numero, tamanho: filtrosDaApi(estado).tamanho, escopo: "todos", ...pagina };
        return tabelaDaAuditoria(ultima, busca.value, { irPara });
      },
    );
  }

  function consultar() {
    if (desde.value && ate.value && ate.value < desde.value) {
      aviso.textContent = "A data final não pode ser anterior à inicial.";
      aviso.hidden = false;
      return null;
    }
    aviso.hidden = true;
    Object.assign(estado, { modulo: modulo.value, desde: desde.value, ate: ate.value });
    return irPara(1);
  }

  modulo.addEventListener("change", consultar);
  busca.addEventListener("input", desenhar);
  const filtros = el(
    "form",
    {
      class: "toolbar auditoria-filtros",
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
      el("span", { class: "filter-label" }, "Módulo"),
      modulo,
      el("span", { class: "filter-label" }, "De"),
      desde,
      el("span", { class: "filter-label" }, "Até"),
      ate,
      el("button", { type: "submit", class: "btn" }, "Aplicar"),
    ),
    el("div", { class: "filters" }, busca),
  );

  container.replaceChildren(el("div", { class: "stack" }, filtros, aviso, resultado));
  return consultar();
}
