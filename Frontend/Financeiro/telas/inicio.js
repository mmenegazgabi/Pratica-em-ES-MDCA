// Início · "O que precisa de você": só o que o papel precisa resolver agora.
import { el, limpar } from "../base/dom.js";
import { definirContador } from "../base/contador.js";
import { formatarMoeda } from "../base/formatar.js";
import { listarLancamentos, listarOrcamentos, resumoDosProjetos } from "../base/api.js";
import { montarPendencias, painelDaDirecao } from "./inicio-dados.js";

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
  const coluna = secao.coluna || (tipo === "uso" ? "Usado" : "Valor");
  return el(
    "div",
    { class: "caixa", style: "margin-top:12px" },
    el(
      "table",
      { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, secao.titulo), el("th", { class: "num" }, coluna), el("th", {}))),
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

/** Direção: orçado, realizado e saldo de cada projeto, do painel do backend. */
function painelDosProjetos(resposta) {
  const titulo = el("h2", { style: "font-size:13px;font-weight:600;margin:20px 0 0" }, "Projetos");
  if (falhou(resposta) || !Array.isArray(resposta.corpo)) {
    return el("div", {}, titulo, el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar o resumo dos projetos. Verifique a conexão e tente de novo."));
  }
  const { linhas, total } = painelDaDirecao(resposta.corpo);
  if (linhas.length === 0) return el("div", {}, titulo, el("p", { class: "vazio" }, "Nenhum projeto cadastrado ainda."));
  const celulas = (orcado, realizado, saldo) => [el("td", { class: "num" }, formatarMoeda(orcado)), el("td", { class: "num" }, formatarMoeda(realizado)), el("td", { class: "num" }, formatarMoeda(saldo))];
  return el(
    "div",
    {},
    titulo,
    el(
      "div",
      { class: "caixa", style: "margin-top:12px" },
      el(
        "table",
        { class: "tabela" },
        el("thead", {}, el("tr", {}, el("th", {}, "Projeto"), el("th", { class: "num" }, "Orçado"), el("th", { class: "num" }, "Realizado"), el("th", { class: "num" }, "Saldo"))),
        el(
          "tbody",
          {},
          linhas.map((p) =>
            el(
              "tr",
              {},
              el("td", {}, p.nome, p.status === "encerrado" ? el("small", {}, "Encerrado") : null),
              ...celulas(p.orcado, p.realizado, p.saldo),
            ),
          ),
          el("tr", { style: "font-weight:600" }, el("td", {}, "Total"), ...celulas(total.orcado, total.realizado, total.saldo)),
        ),
      ),
    ),
  );
}

function carregarDados(papel) {
  return Promise.all([
    COM_LANCAMENTOS.includes(papel) ? listarLancamentos() : { status: 200, corpo: [] },
    COM_ORCAMENTOS.includes(papel) ? listarOrcamentos() : { status: 200, corpo: [] },
  ]);
}

/** Preenche o contador do Início quando a primeira tela aberta é outra (ex.: #/projetos). */
export async function atualizarContadorDePendencias(papel) {
  const [lancamentos, orcamentos] = await carregarDados(papel);
  if (falhou(lancamentos) || falhou(orcamentos)) return;
  definirContador(montarPendencias(papel, { lancamentos: lancamentos.corpo, orcamentos: orcamentos.corpo}, new Date()).total);
}

export async function mostrar(container, { sessao, navegar }) {
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));
  const direcao = sessao.papel === "direcao";
  const [[lancamentos, orcamentos], painel] = await Promise.all([carregarDados(sessao.papel), direcao ? resumoDosProjetos() : null]);

  const agora = new Date();
  const primeiroNome = String(sessao.nome || "").trim().split(/\s+/)[0];
  const titulo = el("h1", {}, `${saudacao(agora.getHours())}${primeiroNome ? ", " + primeiroNome : ""}`);

  if (falhou(lancamentos) || falhou(orcamentos)) {
    limpar(container).append(titulo, el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar as pendências. Verifique a conexão e tente de novo."));
    return;
  }

  const { total, secoes } = montarPendencias(sessao.papel, { lancamentos: lancamentos.corpo, orcamentos: orcamentos.corpo}, agora);
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
      direcao ? painelDosProjetos(painel) : null,
    ),
  );
}
