// Programas: primeira tela ligada à API (GET /gestao/programas, cadastro canônico).
// O cadastro completo, com convênios, metas e vagas, chega com a US-02 (T-44 e T-45).

import { listarProgramas } from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";

function semProgramas() {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "empty" }, el("h2", {}, "Nenhum programa cadastrado"), el("p", {}, "Os programas cadastrados na plataforma aparecem aqui.")),
  );
}

export function listaDeProgramas(programas) {
  if (!programas?.length) return semProgramas();
  const linhas = programas.map((p) => el("tr", {}, el("td", {}, p.nome), el("td", {}, el("code", {}, p.id))));
  return el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        {},
        el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Programa"), el("th", { scope: "col" }, "Identificador"))),
        el("tbody", {}, linhas),
      ),
    ),
  );
}

export function mostrarProgramas(container, { buscar = listarProgramas } = {}) {
  return carregarNaTela(container, buscar, listaDeProgramas);
}
