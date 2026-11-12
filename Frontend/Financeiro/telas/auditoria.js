// Auditoria (coordenação e direção): trilha do Financeiro (GET /auditoria?modulo=financeiro),
// em leitura, por período e em páginas de 50. A busca filtra só a página carregada.
import { el, limpar } from "../base/dom.js";
import { listarAuditoria } from "../base/api.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import { filtrarNaPagina, filtrosDaAuditoria, formatarOcorrido, paginacao } from "./auditoria-dados.js";

const ESPERA_DA_BUSCA_MS = 300;

// Busca pendente da tela aberta: abrir a tela de novo cancela a anterior.
let esperaPendente = null;

function campo(rotulo, id, controle) {
  return el("div", { class: "campo", style: "margin:0" }, el("label", { for: id }, rotulo), controle);
}

// Só os campos de texto da trilha; `detalhes` (dados técnicos) nunca aparece na tela.
function tabela(eventos) {
  return el(
    "div",
    { class: "caixa" },
    el(
      "table",
      { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Data/hora"), el("th", {}, "Pessoa"), el("th", {}, "Ação"), el("th", {}, "Descrição"))),
      el(
        "tbody",
        {},
        eventos.map((e) =>
          el(
            "tr",
            {},
            el("td", { style: "white-space:nowrap;font-variant-numeric:tabular-nums" }, formatarOcorrido(e.quando)),
            el("td", {}, e.quem || "—"),
            el("td", {}, e.acao || "—"),
            el("td", {}, e.alvo || "—"),
          ),
        ),
      ),
    ),
  );
}

export async function mostrar(container) {
  const busca = el("input", { id: "aud-busca", class: "entrada", type: "search", placeholder: "Pessoa, ação ou descrição (busca nesta página)", "aria-label": "Buscar nesta página do histórico" });
  const desde = el("input", { id: "aud-desde", class: "entrada", type: "date" });
  const ate = el("input", { id: "aud-ate", class: "entrada", type: "date" });
  const corpo = el("div", {}, el("p", { class: "carregando" }, "Carregando…"));
  const total = el("span", { class: "sub", "aria-live": "polite" });
  const qualPagina = el("span", { class: "sub" });
  const anterior = el("button", { type: "button", class: "btn btn--sec", disabled: true }, "Anterior");
  const proxima = el("button", { type: "button", class: "btn btn--sec", disabled: true }, "Próxima");

  let pagina = 1;
  let carregados = null; // itens da página atual, para a busca local
  // Só a resposta do pedido mais recente vale (troca rápida de período ou página).
  let pedido = 0;
  clearTimeout(esperaPendente);

  function mostrarPagina() {
    if (!carregados) return;
    const visiveis = filtrarNaPagina(carregados, busca.value);
    let conteudo;
    if (carregados.length === 0) conteudo = el("p", { class: "vazio" }, "Nenhuma ação encontrada.");
    else if (visiveis.length === 0) conteudo = el("p", { class: "vazio" }, "Nenhuma ação desta página corresponde à busca.");
    else conteudo = tabela(visiveis);
    limpar(corpo).append(conteudo);
  }

  function semPaginacao() {
    total.textContent = "";
    qualPagina.textContent = "";
    anterior.disabled = true;
    proxima.disabled = true;
  }

  async function carregar() {
    if (!busca.isConnected) return; // a pessoa já saiu da tela
    const { filtros, erro } = filtrosDaAuditoria({ desde: desde.value, ate: ate.value, pagina });
    const meu = ++pedido;
    if (erro) {
      carregados = null;
      semPaginacao();
      return limpar(corpo).append(el("p", { class: "aviso-tela", role: "alert" }, erro));
    }
    const resposta = await listarAuditoria(filtros);
    if (meu !== pedido) return;
    if (falhou(resposta) || !Array.isArray(resposta.corpo?.itens)) {
      carregados = null;
      semPaginacao();
      return limpar(corpo).append(el("p", { class: "aviso-tela", role: "alert" }, mensagemDeErro(resposta, "Não foi possível carregar o histórico. Tente de novo.")));
    }
    carregados = resposta.corpo.itens;
    const resumo = paginacao({ total: Number(resposta.corpo.total) || 0, pagina, tamanho: Number(resposta.corpo.tamanho) || filtros.tamanho });
    total.textContent = resumo.total;
    qualPagina.textContent = resumo.pagina;
    anterior.disabled = !resumo.temAnterior;
    proxima.disabled = !resumo.temProxima;
    mostrarPagina();
  }

  busca.addEventListener("input", () => {
    clearTimeout(esperaPendente);
    esperaPendente = setTimeout(() => {
      if (busca.isConnected) mostrarPagina();
    }, ESPERA_DA_BUSCA_MS);
  });
  for (const controle of [desde, ate]) {
    controle.addEventListener("change", () => {
      pagina = 1;
      carregar();
    });
  }
  anterior.addEventListener("click", () => {
    if (pagina > 1) {
      pagina -= 1;
      carregar();
    }
  });
  proxima.addEventListener("click", () => {
    pagina += 1;
    carregar();
  });

  limpar(container).append(
    el("h1", {}, "Auditoria"),
    el("p", { class: "sub" }, "Histórico de ações no Financeiro"),
    el(
      "div",
      { style: "display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:12px" },
      el("div", { style: "flex:1;min-width:220px;max-width:320px" }, campo("Buscar", "aud-busca", busca)),
      campo("De", "aud-desde", desde),
      campo("Até", "aud-ate", ate),
    ),
    corpo,
    el("div", { style: "display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin-top:12px" }, total, anterior, qualPagina, proxima),
  );
  await carregar();
}
