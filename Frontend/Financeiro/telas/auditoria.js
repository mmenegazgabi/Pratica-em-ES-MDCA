// Auditoria (coordenação e direção): trilha de ações do Financeiro (T-34 · US-08),
// lida de GET /auditoria. Só leitura: a tela não tem nenhuma ação de alterar ou apagar.
import { el, limpar } from "../base/dom.js";
import { listarAuditoria } from "../base/api.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import { validarPeriodo } from "./painel-dados.js";
import { TAMANHO_DA_PAGINA, filtrarAuditoria, filtrosDaApi, formatarQuando, intervaloDaPagina, ultimaPagina } from "./auditoria-dados.js";

function campo(rotulo, id, controle) {
  return el("div", { class: "campo", style: "margin:0" }, el("label", { for: id }, rotulo), controle);
}

export async function mostrar(container) {
  const filtros = { desde: "", ate: "", pagina: 1 };
  let pagina = { itens: [], total: 0, pagina: 1, tamanho: TAMANHO_DA_PAGINA };
  let pedido = 0; // só a resposta da consulta mais recente é desenhada

  const desde = el("input", { id: "auditoria-desde", class: "entrada", type: "date" });
  const ate = el("input", { id: "auditoria-ate", class: "entrada", type: "date" });
  const busca = el("input", {
    id: "auditoria-busca",
    class: "entrada",
    type: "search",
    placeholder: "Pessoa, ação ou detalhe",
    "aria-label": "Buscar nesta página",
  });
  const erro = el("p", { role: "alert", style: "margin:8px 0 0;color:var(--perigo-texto);font-size:12px", hidden: true });
  const corpo = el("div", { "aria-live": "polite", style: "margin-top:12px" });

  function navegacao() {
    const anterior = el("button", { type: "button", class: "btn btn--sec", disabled: pagina.pagina <= 1 }, "Anterior");
    const proxima = el("button", { type: "button", class: "btn btn--sec", disabled: pagina.pagina >= ultimaPagina(pagina.tamanho, pagina.total) }, "Próxima");
    anterior.addEventListener("click", () => irPara(pagina.pagina - 1));
    proxima.addEventListener("click", () => irPara(pagina.pagina + 1));
    return el(
      "div",
      { style: "display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:10px" },
      el("span", { class: "auditoria-intervalo", style: "color:var(--texto-suave);font-size:12px;margin-right:auto" }, intervaloDaPagina(pagina.pagina, pagina.tamanho, pagina.total)),
      anterior,
      proxima,
    );
  }

  function desenhar() {
    const registros = filtrarAuditoria(pagina.itens, busca.value);
    let lista;
    if (pagina.total === 0) lista = el("p", { class: "vazio" }, "Nenhuma ação registrada neste período.");
    else if (registros.length === 0) lista = el("p", { class: "vazio" }, "Nenhuma ação desta página corresponde à busca.");
    else {
      lista = el(
        "div",
        { class: "caixa", style: "overflow-x:auto" },
        el(
          "table",
          { class: "tabela" },
          el("thead", {}, el("tr", {}, el("th", {}, "Quando"), el("th", {}, "Quem"), el("th", {}, "Ação"), el("th", {}, "Detalhe"))),
          el(
            "tbody",
            {},
            registros.map((r) =>
              el(
                "tr",
                { "data-codigo": r.codigo },
                el("td", { style: "white-space:nowrap;font-variant-numeric:tabular-nums" }, formatarQuando(r.quando)),
                el("td", {}, r.quem || "—"),
                el("td", {}, r.acao),
                el("td", {}, r.alvo || "—"),
              ),
            ),
          ),
        ),
      );
    }
    limpar(corpo).append(lista, pagina.total ? navegacao() : null);
  }

  async function irPara(numero) {
    filtros.pagina = numero;
    const este = ++pedido;
    limpar(corpo).append(el("p", { class: "carregando" }, "Carregando…"));
    const resposta = await listarAuditoria(filtrosDaApi(filtros));
    if (este !== pedido) return;
    if (falhou(resposta)) {
      return limpar(corpo).append(
        el("p", { class: "aviso-tela", role: "alert" }, mensagemDeErro(resposta, "Não foi possível carregar a auditoria. Tente de novo.")),
      );
    }
    pagina = { itens: [], total: 0, pagina: numero, tamanho: TAMANHO_DA_PAGINA, ...resposta.corpo };
    desenhar();
  }

  function consultar() {
    const invalido = validarPeriodo(desde.value, ate.value);
    erro.hidden = !invalido;
    erro.textContent = invalido;
    if (invalido) return;
    filtros.desde = desde.value;
    filtros.ate = ate.value;
    irPara(1);
  }

  busca.addEventListener("input", desenhar);
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
    campo("De", "auditoria-desde", desde),
    campo("Até", "auditoria-ate", ate),
    el("button", { type: "submit", class: "btn" }, "Aplicar"),
    el("div", { style: "margin-left:auto;min-width:240px" }, campo("Buscar nesta página", "auditoria-busca", busca)),
  );

  limpar(container).append(
    el("h1", {}, "Auditoria"),
    el("p", { class: "sub" }, "Histórico de ações no módulo financeiro, só para consulta"),
    formulario,
    erro,
    corpo,
  );
  await irPara(1);
}
