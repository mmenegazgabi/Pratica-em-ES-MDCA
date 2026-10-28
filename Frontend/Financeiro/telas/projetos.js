// Projetos: visão geral (quatro números e uma linha por projeto).
import { el, limpar } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { formatarData, formatarMoeda } from "../base/formatar.js";
import { criarOrcamento, criarProjeto, listarLancamentos, listarOrcamentos, listarProjetos } from "../base/api.js";
import { orcamentoDoProjeto, totaisGerais } from "./projetos-dados.js";
import { abrirDialogoOrcamento, abrirDocumento, falhou, mensagemDeErro } from "./orcamento-dialogo.js";

const hojeISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const vigenciaTexto = (o) => `${formatarData(o.data_inicio)} a ${formatarData(o.data_fim)}`;

function numero(rotulo, valor) {
  return el("div", { class: "caixa", style: "padding:12px 14px" }, el("div", { style: "font-size:11px;color:var(--texto-suave)" }, rotulo), el("div", { class: "num", style: "font-size:18px;font-weight:600;margin-top:2px" }, valor));
}

function barraDeUso(o) {
  const classe = o.nivel_alerta === "estourado" ? "barra-uso barra-uso--critica" : o.nivel_alerta === "atencao" ? "barra-uso barra-uso--alerta" : "barra-uso";
  return el(
    "div",
    { style: "display:flex;gap:8px;align-items:center" },
    el("div", { class: classe, style: "width:90px" }, el("i", { style: `width:${Math.max(0, Math.min(100, o.percentual_consumido))}%` })),
    el("span", { class: "num" }, `${Math.floor(o.percentual_consumido)}%`),
  );
}

export async function mostrar(container, { sessao, navegar }) {
  const coordenacao = sessao.papel === "coordenacao";
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));
  let projetos = [];
  let orcamentos = [];
  let pendentes = null; // null: não foi possível carregar

  async function carregar() {
    const [p, o, l] = await Promise.all([listarProjetos(), listarOrcamentos(), listarLancamentos({ status: "pendente" })]);
    if (falhou(p) || falhou(o)) return false;
    projetos = p.corpo;
    orcamentos = o.corpo;
    pendentes = falhou(l) ? null : l.corpo.filter((x) => x.status === "pendente");
    return true;
  }

  function dialogoNovoProjeto() {
    const nome = el("input", { id: "projeto-nome", class: "entrada", maxlength: "100" });
    const erro = el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:12px;margin:6px 0 0", hidden: true });
    const cancelar = el("button", { type: "button", class: "btn btn--sec" }, "Cancelar");
    const confirmar = el("button", { type: "submit", class: "btn" }, "Criar projeto");
    const dialogo = el(
      "dialog",
      { class: "dialogo", "aria-labelledby": "projeto-titulo" },
      el(
        "form",
        { method: "dialog", novalidate: true },
        el("h2", { id: "projeto-titulo", style: "font-size:15px;margin:0 0 4px" }, "Novo projeto"),
        el("div", { class: "campo" }, el("label", { for: "projeto-nome" }, "Nome do projeto"), nome),
        erro,
        el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:14px" }, cancelar, confirmar),
      ),
    );
    const fechar = () => dialogo.remove();
    cancelar.addEventListener("click", fechar);
    dialogo.addEventListener("cancel", fechar);
    dialogo.querySelector("form").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      if (!nome.value.trim()) {
        erro.hidden = false;
        erro.textContent = "Informe o nome do projeto.";
        return nome.focus();
      }
      confirmar.disabled = true;
      cancelar.disabled = true;
      const resposta = await criarProjeto(nome.value.trim());
      if (!falhou(resposta)) {
        fechar();
        await recarregar();
        return;
      }
      confirmar.disabled = false;
      cancelar.disabled = false;
      erro.hidden = false;
      erro.textContent = resposta.status === 409 ? mensagemDeErro(resposta, "Já existe um projeto com esse nome.") : mensagemDeErro(resposta, "Não foi possível criar o projeto. Tente de novo.");
    });
    abrirDocumento(container, dialogo, nome);
  }

  function dialogoNovoOrcamento(projeto) {
    abrirDialogoOrcamento(container, {
      titulo: "Criar orçamento",
      subtitulo: `Projeto: ${projeto.nome}`,
      rotuloSalvar: "Criar orçamento",
      inicial: null,
      salvar: (dados) => criarOrcamento({ projeto_id: projeto.id, ...dados }),
      aoSalvar: () => recarregar(),
    });
  }

  async function recarregar() {
    if (!(await carregar())) return desenhar(true);
    desenhar();
  }

  function linha(projeto) {
    const o = orcamentoDoProjeto(projeto.id, orcamentos, hojeISO());
    if (!o) {
      return el(
        "tr",
        {},
        el("td", {}, projeto.nome, el("small", {}, "Sem orçamento")),
        el("td", { class: "num" }, "—"),
        el("td", { class: "num" }, "—"),
        el("td", {}, ""),
        el("td", { class: "num" }, coordenacao ? el("button", { type: "button", class: "btn btn--sec btn--pequeno", onclick: () => dialogoNovoOrcamento(projeto) }, "Criar orçamento") : null),
      );
    }
    const abrir = () => navegar(`#/projetos/${encodeURIComponent(o.id)}`);
    return el(
      "tr",
      { tabindex: "0", style: "cursor:pointer", onclick: abrir, onkeydown: (e) => { if (e.key === "Enter") abrir(); } },
      el("td", {}, projeto.nome, el("small", {}, vigenciaTexto(o))),
      el("td", { class: "num" }, formatarMoeda(o.valor_total)),
      el("td", { class: "num" }, formatarMoeda(o.realizado)),
      el("td", {}, barraDeUso(o)),
      el("td", { class: "num" }, icone("seta")),
    );
  }

  function desenhar(falha = false) {
    const cabecalho = el(
      "div",
      { style: "display:flex;justify-content:space-between;align-items:flex-start" },
      el("div", {}, el("h1", {}, "Projetos"), el("p", { class: "sub" }, "Orçamento, gasto e uso de cada projeto")),
      coordenacao ? el("button", { type: "button", class: "btn btn--sec", onclick: dialogoNovoProjeto }, icone("mais"), "Novo projeto") : null,
    );
    if (falha) {
      return limpar(container).append(cabecalho, el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar os projetos. Verifique a conexão e tente de novo."));
    }
    const doProjeto = projetos.map((p) => orcamentoDoProjeto(p.id, orcamentos, hojeISO())).filter(Boolean);
    const t = totaisGerais(doProjeto, pendentes || []);
    limpar(container).append(
      cabecalho,
      el(
        "div",
        { style: "display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px" },
        numero("Orçado", formatarMoeda(t.orcado)),
        numero("Gasto", formatarMoeda(t.gasto)),
        numero("Disponível", formatarMoeda(t.disponivel)),
        numero("Aguardando aprovação", pendentes ? formatarMoeda(t.aguardando) : "—"),
      ),
      projetos.length === 0
        ? el("p", { class: "vazio" }, "Nenhum projeto cadastrado ainda.")
        : el(
            "div",
            { class: "caixa" },
            el(
              "table",
              { class: "tabela" },
              el("thead", {}, el("tr", {}, el("th", {}, "Projeto"), el("th", { class: "num" }, "Orçado"), el("th", { class: "num" }, "Gasto"), el("th", {}, "Uso"), el("th", {}))),
              el("tbody", {}, projetos.map(linha)),
            ),
          ),
    );
  }

  desenhar(!(await carregar()));
}
