// Início · "O que precisa de você": só o que o papel precisa resolver agora.
import { el, limpar } from "../base/dom.js";
import { definirContador } from "../base/contador.js";
import { formatarMoeda } from "../base/formatar.js";
import { listarLancamentos, listarOrcamentos } from "../base/api.js";
import { montarPendencias } from "./inicio-dados.js";

const COM_LANCAMENTOS = ["coordenacao", "voluntario_financeiro"];
const COM_ORCAMENTOS = ["coordenacao", "direcao", "voluntario_financeiro"];

export function saudacao(hora) {
  if (hora < 12) return "Bom dia";
  return hora < 18 ? "Boa tarde" : "Boa noite";
}

function falhou(resposta) {
  return resposta.status === 0 || resposta.status >= 400;
}

function celulaDeValor(item, tipo) {
  if (tipo === "uso") {
    const classe = item.nivel === "estourado" ? "barra-uso barra-uso--critica" : "barra-uso barra-uso--alerta";
    return el(
      "td",
      { class: "num" },
      el(
        "div",
        { style: "display:flex;gap:8px;align-items:center;justify-content:flex-end" },
        el("div", { class: classe, style: "width:70px" }, el("i", { style: `width:${Math.min(100, item.valor)}%` })),
        el("span", {}, `${Math.floor(item.valor)}%`),
      ),
    );
  }
  return el("td", { class: "num" }, formatarMoeda(item.valor));
}

function tabelaDaSecao(secao, navegar) {
  const tipo = secao.itens[0]?.nivel ? "uso" : "dinheiro";
  return el(
    "div",
    { class: "caixa", style: "margin-top:12px" },
    el(
      "table",
      { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, secao.titulo), el("th", { class: "num" }, tipo === "uso" ? "Usado" : "Valor"), el("th", {}))),
      el(
        "tbody",
        {},
        secao.itens.map((item) =>
          el(
            "tr",
            {},
            el("td", {}, item.rotulo, el("small", {}, item.detalhe)),
            celulaDeValor(item, tipo),
            el("td", { class: "num" }, el("button", { type: "button", class: "btn btn--sec btn--pequeno", onclick: () => navegar(item.acao.rota) }, item.acao.rotulo)),
          ),
        ),
      ),
    ),
  );
}

export async function mostrar(container, { sessao, navegar }) {
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));
  const [lancamentos, orcamentos] = await Promise.all([
    COM_LANCAMENTOS.includes(sessao.papel) ? listarLancamentos() : { status: 200, corpo: [] },
    COM_ORCAMENTOS.includes(sessao.papel) ? listarOrcamentos() : { status: 200, corpo: [] },
  ]);

  const agora = new Date();
  const primeiroNome = String(sessao.nome || "").trim().split(/\s+/)[0];
  const titulo = el("h1", {}, `${saudacao(agora.getHours())}${primeiroNome ? ", " + primeiroNome : ""}`);

  if (falhou(lancamentos) || falhou(orcamentos)) {
    limpar(container).append(titulo, el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar as pendências. Verifique a conexão e tente de novo."));
    return;
  }

  const { total, secoes } = montarPendencias(sessao.papel, { lancamentos: lancamentos.corpo, orcamentos: orcamentos.corpo }, agora);
  definirContador(total);

  const resumo = total === 0 ? "Nada pendente" : total === 1 ? "1 item precisa de você" : `${total} itens precisam de você`;
  limpar(container).append(
    el(
      "div",
      {},
      titulo,
      el("p", { class: "sub" }, resumo),
      total === 0 ? el("p", { class: "vazio" }, "Quando algo precisar de uma decisão sua, aparece aqui.") : null,
      secoes.map((s) => tabelaDaSecao(s, navegar)),
    ),
  );
}
