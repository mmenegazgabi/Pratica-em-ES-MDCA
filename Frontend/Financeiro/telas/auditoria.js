// Auditoria (coordenação e direção): histórico de ações, em leitura, com busca.
import { el, limpar } from "../base/dom.js";
import { filtrarAuditoria } from "./auditoria-dados.js";
import { AUDITORIA_EXEMPLO } from "./dados-exemplo.js";

function quando(iso) {
  const [data, hora = ""] = iso.split("T");
  const [a, m, d] = data.split("-");
  return `${d}/${m}/${a} ${hora.slice(0, 5)}`;
}

function blocoAuditoria() {
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
  limpar(container).append(el("h1", {}, "Auditoria"), el("p", { class: "sub" }, "Histórico de ações no módulo financeiro"), blocoAuditoria());
}
