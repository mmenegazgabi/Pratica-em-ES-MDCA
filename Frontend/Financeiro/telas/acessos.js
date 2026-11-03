// Acessos (admin): abas "Pessoas e papéis" e "Auditoria". Coordenação e direção abrem só a Auditoria (telas/auditoria.js).
import { el, limpar } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { PAPEIS } from "../base/sessao.js";
import { abrirDocumento } from "./orcamento-dialogo.js";
import { filtrarAuditoria, validarPessoa } from "./acessos-dados.js";
import { AUDITORIA_EXEMPLO, PESSOAS_EXEMPLO } from "./dados-exemplo.js";

const AVISO_EXEMPLO = "Dados de exemplo: as mudanças ainda não são salvas.";

function quando(iso) {
  const [data, hora = ""] = iso.split("T");
  const [a, m, d] = data.split("-");
  return `${d}/${m}/${a} ${hora.slice(0, 5)}`;
}

/** Tabela do histórico com busca; usada pela aba e pela tela Auditoria. */
export function blocoAuditoria() {
  const busca = el("input", { class: "entrada", type: "search", placeholder: "Buscar por pessoa, ação ou detalhe", "aria-label": "Buscar no histórico", style: "max-width:320px;margin-bottom:12px" });
  const corpo = el("div", {});
  function desenhar() {
    const registros = filtrarAuditoria(AUDITORIA_EXEMPLO, busca.value);
    limpar(corpo).append(
      registros.length === 0
        ? el("p", { class: "vazio" }, "Nenhuma ação encontrada.")
        : el(
            "div",
            { class: "caixa" },
            el(
              "table",
              { class: "tabela" },
              el("thead", {}, el("tr", {}, el("th", {}, "Quando"), el("th", {}, "Quem"), el("th", {}, "Ação"), el("th", {}, "Detalhe"))),
              el("tbody", {}, registros.map((r) => el("tr", {}, el("td", { class: "num", style: "white-space:nowrap" }, quando(r.quando)), el("td", {}, r.quem), el("td", {}, r.acao), el("td", {}, r.alvo)))),
            ),
          ),
    );
  }
  busca.addEventListener("input", desenhar);
  desenhar();
  return el("div", {}, busca, corpo, el("p", { style: "margin:10px 0 0;color:var(--texto-suave);font-size:11px" }, "Histórico de exemplo até o registro de ações existir no sistema."));
}

export async function mostrar(container) {
  const pessoas = PESSOAS_EXEMPLO.map((p) => ({ ...p }));
  let aba = "pessoas";

  function dialogoPessoa(pessoa) {
    const novo = !pessoa;
    const nome = el("input", { id: "pessoa-nome", class: "entrada", value: pessoa?.nome || "" });
    const email = el("input", { id: "pessoa-email", class: "entrada", type: "email", value: pessoa?.email || "" });
    const papel = el("select", { id: "pessoa-papel", class: "entrada" }, el("option", { value: "" }, "Escolha…"), Object.entries(PAPEIS).map(([valor, rotulo]) => el("option", { value: valor }, rotulo)));
    papel.value = pessoa?.papel || "";
    const projetos = el("input", { id: "pessoa-projetos", class: "entrada", value: pessoa?.projetos || "", placeholder: "Ex.: Leitura, Esporte ou Todos" });
    const erros = {};
    const campo = (rotulo, id, controle, chave) => {
      erros[chave] = el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:11px;margin:4px 0 0", hidden: true });
      return el("div", { class: "campo" }, el("label", { for: id }, rotulo), controle, erros[chave]);
    };
    const cancelar = el("button", { type: "button", class: "btn btn--sec" }, "Cancelar");
    const salvar = el("button", { type: "submit", class: "btn" }, novo ? "Convidar" : "Salvar");
    const dialogo = el(
      "dialog",
      { class: "dialogo", "aria-labelledby": "pessoa-titulo" },
      el(
        "form",
        { method: "dialog", novalidate: true },
        el("h2", { id: "pessoa-titulo", style: "font-size:15px;margin:0 0 4px" }, novo ? "Convidar pessoa" : "Editar acesso"),
        el("p", { style: "margin:0;color:var(--texto-suave);font-size:11px" }, AVISO_EXEMPLO),
        campo("Nome", "pessoa-nome", nome, "nome"),
        campo("E-mail", "pessoa-email", email, "email"),
        campo("Papel", "pessoa-papel", papel, "papel"),
        campo("Projetos", "pessoa-projetos", projetos, "projetos"),
        el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:14px" }, cancelar, salvar),
      ),
    );
    const fechar = () => dialogo.remove();
    cancelar.addEventListener("click", fechar);
    dialogo.addEventListener("cancel", fechar);
    dialogo.querySelector("form").addEventListener("submit", (evento) => {
      evento.preventDefault();
      const dados = { nome: nome.value.trim(), email: email.value.trim(), papel: papel.value, projetos: projetos.value.trim() };
      const problemas = validarPessoa(dados, pessoas, pessoa?.id || null);
      for (const [chave, p] of Object.entries(erros)) {
        p.hidden = !problemas[chave];
        p.textContent = problemas[chave] || "";
      }
      if (Object.keys(problemas).length) return;
      if (novo) pessoas.push({ id: `novo-${pessoas.length + 1}`, ...dados, convite: true });
      else Object.assign(pessoa, dados);
      fechar();
      desenhar();
    });
    abrirDocumento(container, dialogo, nome);
  }

  function abaPessoas() {
    return el(
      "div",
      {},
      el(
        "div",
        { class: "caixa" },
        el(
          "table",
          { class: "tabela" },
          el("thead", {}, el("tr", {}, el("th", {}, "Pessoa"), el("th", {}, "Papel"), el("th", {}, "Projetos"), el("th", {}))),
          el(
            "tbody",
            {},
            pessoas.map((p) =>
              el(
                "tr",
                {},
                el("td", {}, p.nome, p.convite ? el("span", { class: "etiqueta etiqueta--pendente", style: "margin-left:6px" }, "Convite pendente") : null, el("small", {}, p.email)),
                el("td", {}, PAPEIS[p.papel] || p.papel),
                el("td", {}, p.projetos),
                el("td", { class: "num" }, el("button", { type: "button", class: "btn btn--sec btn--pequeno", onclick: () => dialogoPessoa(p) }, "Editar")),
              ),
            ),
          ),
        ),
      ),
      el("p", { style: "margin:10px 0 0;color:var(--texto-suave);font-size:11px" }, AVISO_EXEMPLO),
    );
  }

  function desenhar() {
    const botaoAba = (id, rotulo) =>
      el(
        "button",
        {
          type: "button",
          role: "tab",
          "aria-selected": String(aba === id),
          style: `background:none;border:0;padding:0 0 8px;font:inherit;cursor:pointer;${aba === id ? "color:var(--texto);font-weight:500;box-shadow:inset 0 -2px 0 var(--verde)" : "color:var(--texto-suave)"}`,
          onclick: () => { aba = id; desenhar(); },
        },
        rotulo,
      );
    limpar(container).append(
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:flex-start" },
        el("div", {}, el("h1", {}, "Acessos"), el("p", { class: "sub" }, "Quem usa o módulo financeiro")),
        aba === "pessoas" ? el("button", { type: "button", class: "btn btn--sec", onclick: () => dialogoPessoa(null) }, icone("mais"), "Convidar pessoa") : null,
      ),
      el("div", { role: "tablist", style: "display:flex;gap:18px;border-bottom:1px solid var(--borda);margin-bottom:14px" }, botaoAba("pessoas", "Pessoas e papéis"), botaoAba("auditoria", "Auditoria")),
      aba === "pessoas" ? abaPessoas() : blocoAuditoria(),
    );
  }

  desenhar();
}
