// Auditoria (coordenação e direção): histórico de ações da plataforma (GET /auditoria), em leitura,
// com busca, filtro de módulo e período.
import { el, limpar } from "../base/dom.js";
import { listarAuditoria } from "../base/api.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import { MODULOS, filtrosDaAuditoria, formatarOcorrido, rotuloDaAcao, rotuloDoModulo } from "./auditoria-dados.js";

const ESPERA_DA_BUSCA_MS = 300;

// Busca pendente da tela aberta: abrir a tela de novo cancela a anterior.
let esperaPendente = null;

function campo(rotulo, id, controle) {
  return el("div", { class: "campo", style: "margin:0" }, el("label", { for: id }, rotulo), controle);
}

function tabela(registros) {
  return el(
    "div",
    { class: "caixa" },
    el(
      "table",
      { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Data/hora"), el("th", {}, "Pessoa"), el("th", {}, "Módulo"), el("th", {}, "Ação"), el("th", {}, "Descrição"))),
      el(
        "tbody",
        {},
        registros.map((r) =>
          el(
            "tr",
            {},
            el("td", { style: "white-space:nowrap;font-variant-numeric:tabular-nums" }, formatarOcorrido(r.ocorrido_em)),
            el("td", {}, r.usuario_nome || r.usuario_id || "—"),
            el("td", {}, rotuloDoModulo(r.modulo)),
            el("td", {}, rotuloDaAcao(r.acao)),
            el("td", {}, r.descricao || "—"),
          ),
        ),
      ),
    ),
  );
}

export async function mostrar(container) {
  const busca = el("input", { id: "aud-busca", class: "entrada", type: "search", placeholder: "Buscar por ação, descrição ou pessoa", "aria-label": "Buscar no histórico" });
  const modulo = el("select", { id: "aud-modulo", class: "entrada" }, el("option", { value: "" }, "Todos os módulos"), MODULOS.map(([id, rotulo]) => el("option", { value: id }, rotulo)));
  const desde = el("input", { id: "aud-desde", class: "entrada", type: "date" });
  const ate = el("input", { id: "aud-ate", class: "entrada", type: "date" });
  const corpo = el("div", {}, el("p", { class: "carregando" }, "Carregando…"));

  // Só a resposta do pedido mais recente vale (busca rápida pode chegar fora de ordem).
  let pedido = 0;
  clearTimeout(esperaPendente);

  async function carregar() {
    clearTimeout(esperaPendente);
    if (!busca.isConnected) return; // a pessoa já saiu da tela
    const { filtros, erro } = filtrosDaAuditoria({ texto: busca.value, modulo: modulo.value, desde: desde.value, ate: ate.value });
    const meu = ++pedido;
    if (erro) return limpar(corpo).append(el("p", { class: "aviso-tela", role: "alert" }, erro));
    const resposta = await listarAuditoria(filtros);
    if (meu !== pedido) return;
    if (falhou(resposta) || !Array.isArray(resposta.corpo)) {
      return limpar(corpo).append(el("p", { class: "aviso-tela", role: "alert" }, mensagemDeErro(resposta, "Não foi possível carregar o histórico. Tente de novo.")));
    }
    limpar(corpo).append(resposta.corpo.length === 0 ? el("p", { class: "vazio" }, "Nenhuma ação encontrada.") : tabela(resposta.corpo));
  }

  busca.addEventListener("input", () => {
    clearTimeout(esperaPendente);
    esperaPendente = setTimeout(carregar, ESPERA_DA_BUSCA_MS);
  });
  for (const controle of [modulo, desde, ate]) controle.addEventListener("change", carregar);

  limpar(container).append(
    el("h1", {}, "Auditoria"),
    el("p", { class: "sub" }, "Histórico de ações na plataforma"),
    el(
      "div",
      { style: "display:flex;flex-wrap:wrap;gap:10px;align-items:flex-end;margin-bottom:12px" },
      el("div", { style: "flex:1;min-width:220px;max-width:320px" }, campo("Buscar", "aud-busca", busca)),
      campo("Módulo", "aud-modulo", modulo),
      campo("De", "aud-desde", desde),
      campo("Até", "aud-ate", ate),
    ),
    corpo,
  );
  await carregar();
}
