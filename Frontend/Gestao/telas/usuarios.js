// Usuários e acessos: contas da plataforma com perfis e programas (T-40 · US-01).
//
// Só consulta (GET /gestao/usuarios). Criar, editar e desativar contas ainda não têm
// rota na API; até lá a tela não oferece esses botões. Quem não pode consultar recebe
// 403 da API e vê a tela de acesso restrito.

import { listarUsuarios } from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";

const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);

function lista(itens, vazio) {
  return itens.length ? el("div", { class: "badges" }, itens.flatMap((texto) => [badge(texto), " "])) : el("span", { class: "muted" }, vazio);
}

function linha(u) {
  const contato = u.email ? `${u.id} · ${u.email}` : u.id;
  return el(
    "tr",
    {},
    el("td", {}, el("strong", {}, u.nome), el("small", {}, contato)),
    el("td", {}, lista(u.papeis.map((p) => p.nome), "—")),
    el("td", {}, lista(u.vinculos.map((v) => `${v.programa} · ${v.papel}`), "Sem vínculo ativo")),
    el("td", {}, u.ativo ? badge("Ativo", "green") : badge("Desativado", "amber")),
  );
}

export function tabelaDeUsuarios(usuarios) {
  const aviso = el(
    "div",
    { class: "info-box" },
    el("span", {}, "Os perfis da plataforma e os vínculos com programas definem o que cada pessoa acessa. O cadastro e a edição de contas ainda não estão disponíveis nesta versão."),
  );
  if (!usuarios?.length) {
    return el("div", {}, aviso, el("section", { class: "card" }, el("div", { class: "empty" }, el("h2", {}, "Nenhum usuário cadastrado"), el("p", {}, "As contas da plataforma aparecem aqui."))));
  }
  return el(
    "div",
    {},
    aviso,
    el(
      "section",
      { class: "card" },
      el(
        "div",
        { class: "table-wrap" },
        el(
          "table",
          {},
          el("thead", {}, el("tr", {}, ["Usuário", "Perfis da plataforma", "Programas", "Situação"].map((c) => el("th", { scope: "col" }, c)))),
          el("tbody", {}, usuarios.map(linha)),
        ),
      ),
    ),
  );
}

export function mostrarUsuarios(container, { buscar = listarUsuarios } = {}) {
  return carregarNaTela(container, buscar, tabelaDeUsuarios);
}
