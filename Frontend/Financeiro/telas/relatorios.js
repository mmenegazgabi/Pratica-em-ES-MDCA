// Relatórios · prestação de contas: escolhas à esquerda, prévia do documento à direita.
import { el, limpar } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { formatarData, formatarMoeda } from "../base/formatar.js";
import { baixarRelatorio, listarLancamentos, listarOrcamentos } from "../base/api.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import { lancamentosDoPeriodo, nomePadraoDoRelatorio, resumoDoPeriodo, validarPeriodo } from "./relatorios-dados.js";

function campo(rotulo, id, controle) {
  return el("div", { class: "campo" }, el("label", { for: id }, rotulo), controle);
}

function numero(rotulo, valor) {
  return el("div", {}, el("div", { style: "color:var(--texto-suave)" }, rotulo), el("b", { class: "num" }, valor));
}

function baixar(nome, blob) {
  const url = URL.createObjectURL(blob);
  const link = el("a", { href: url, download: nome, style: "display:none" });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function mostrar(container, { parametros = {} }) {
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));
  const resposta = await listarOrcamentos();
  if (falhou(resposta)) {
    return limpar(container).append(el("h1", {}, "Prestação de contas"), el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar os projetos. Verifique a conexão e tente de novo."));
  }
  const orcamentos = [...resposta.corpo].sort((a, b) => String(a.projeto_nome || a.projeto_id).localeCompare(String(b.projeto_nome || b.projeto_id)));
  if (orcamentos.length === 0) {
    return limpar(container).append(el("h1", {}, "Prestação de contas"), el("p", { class: "vazio" }, "Nenhum orçamento cadastrado ainda."));
  }

  const inicial = orcamentos.find((o) => o.id === parametros.orcamento) || orcamentos[0];
  let lancamentos = [];
  let lancamentosOk = true;

  const projeto = el("select", { id: "rel-projeto", class: "entrada" }, orcamentos.map((o) => el("option", { value: o.id }, o.projeto_nome || o.projeto_id)));
  projeto.value = inicial.id;
  const inicio = el("input", { id: "rel-inicio", class: "entrada", type: "date", value: inicial.data_inicio });
  const fim = el("input", { id: "rel-fim", class: "entrada", type: "date", value: inicial.data_fim });
  let formato = "pdf";
  const formatos = el("div", { role: "radiogroup", "aria-label": "Formato", style: "display:flex;border:1px solid var(--borda-campo);border-radius:var(--raio);overflow:hidden" });
  const nota = el("p", { style: "margin:12px 0 0;color:var(--texto-suave);font-size:11px;line-height:1.5" });
  const erro = el("p", { role: "alert", style: "margin:8px 0 0;color:var(--perigo-texto);font-size:12px", hidden: true });
  const erroGerar = el("p", { role: "alert", style: "margin:8px 0 0;color:var(--perigo-texto);font-size:12px", hidden: true });
  let gerando = false;
  const gerar = el("button", { type: "button", class: "btn", style: "margin-top:16px;width:100%;justify-content:center" }, icone("baixar"), "Gerar relatório");
  const previa = el("div", { style: "background:var(--fundo-suave);border-radius:8px;padding:16px;min-height:420px" });

  const atual = () => orcamentos.find((o) => o.id === projeto.value);

  function desenharFormatos() {
    limpar(formatos).append(
      ...[["pdf", "PDF"], ["xlsx", "Planilha (XLSX)"]].map(([valor, rotulo]) =>
        el(
          "button",
          {
            type: "button",
            role: "radio",
            "aria-checked": String(formato === valor),
            style: `flex:1;padding:6px;border:0;font:inherit;cursor:pointer;${formato === valor ? "background:var(--ativo-fundo);color:var(--ativo-texto);font-weight:500" : "background:var(--fundo)"}`,
            onclick: () => { formato = valor; desenharFormatos(); },
          },
          rotulo,
        ),
      ),
    );
  }

  function desenharPrevia() {
    const orcamento = atual();
    const invalido = validarPeriodo(inicio.value, fim.value);
    erro.hidden = !invalido;
    erro.textContent = invalido || "";
    gerar.disabled = Boolean(invalido) || !lancamentosOk || gerando;
    if (!lancamentosOk) {
      nota.textContent = "";
      return limpar(previa).append(el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar os lançamentos deste projeto."));
    }
    if (invalido) return limpar(previa);
    const doPeriodo = lancamentosDoPeriodo(lancamentos, inicio.value, fim.value);
    const resumo = resumoDoPeriodo(orcamento, doPeriodo);
    nota.textContent =
      "O arquivo oficial inclui só lançamentos aprovados." +
      (resumo.naoConciliados === 0 ? "" : resumo.naoConciliados === 1 ? " 1 lançamento do período ainda não foi conciliado." : ` ${resumo.naoConciliados} lançamentos do período ainda não foram conciliados.`);
    limpar(previa).append(
      el(
        "div",
        { style: "background:#fff;border:1px solid var(--borda);border-radius:4px;padding:18px 22px;font-size:11px" },
        el(
          "div",
          { style: "display:flex;justify-content:space-between;gap:12px" },
          el("div", {}, el("h2", { style: "font-size:14px;margin:0 0 2px" }, `Prestação de contas — ${orcamento.projeto_nome || orcamento.projeto_id}`), el("div", { style: "color:var(--texto-suave)" }, `${formatarData(inicio.value)} a ${formatarData(fim.value)} · MDCA`)),
          el("b", {}, "MDCA"),
        ),
        el("div", { style: "display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0" }, numero("Orçado", formatarMoeda(resumo.orcado)), numero("Executado no período", formatarMoeda(resumo.executado)), numero("Saldo", formatarMoeda(resumo.saldo))),
        doPeriodo.length === 0
          ? el("p", { class: "vazio" }, "Nenhum lançamento aprovado neste período.")
          : el(
              "table",
              { class: "tabela", style: "font-size:10.5px" },
              el("thead", {}, el("tr", {}, el("th", {}, "Data"), el("th", {}, "Categoria"), el("th", {}, "Descrição"), el("th", { class: "num" }, "Valor"))),
              el("tbody", {}, doPeriodo.map((l) => el("tr", {}, el("td", { style: "font-variant-numeric:tabular-nums;white-space:nowrap" }, formatarData(l.data_despesa)), el("td", {}, l.categoria), el("td", {}, l.descricao), el("td", { class: "num" }, formatarMoeda(l.valor))))),
            ),
      ),
    );
  }

  async function carregarLancamentos() {
    const r = await listarLancamentos({ orcamento_id: projeto.value, status: "aprovado" });
    lancamentosOk = !falhou(r);
    lancamentos = lancamentosOk ? r.corpo.filter((l) => l.orcamento_id === projeto.value) : [];
    desenharPrevia();
  }

  function mostrarErroGerar(texto) {
    erroGerar.hidden = !texto;
    erroGerar.textContent = texto || "";
  }

  // O arquivo oficial vem da API (PDF ou XLSX); a prévia é só para conferir.
  async function gerarRelatorio() {
    const orcamento = atual();
    const pedido = { projeto_id: orcamento.projeto_id, data_inicio: inicio.value, data_fim: fim.value, formato };
    mostrarErroGerar("");
    gerando = true;
    gerar.disabled = true;
    gerar.lastChild.textContent = "Gerando…";
    const r = await baixarRelatorio(pedido);
    gerando = false;
    gerar.lastChild.textContent = "Gerar relatório";
    desenharPrevia();
    if (falhou(r) || !r.blob) return mostrarErroGerar(mensagemDeErro(r, "Não foi possível gerar o relatório. Tente de novo."));
    baixar(r.nome || nomePadraoDoRelatorio(orcamento, pedido.data_inicio, pedido.data_fim, formato), r.blob);
  }

  projeto.addEventListener("change", () => {
    inicio.value = atual().data_inicio;
    fim.value = atual().data_fim;
    mostrarErroGerar("");
    carregarLancamentos();
  });
  inicio.addEventListener("change", desenharPrevia);
  fim.addEventListener("change", desenharPrevia);
  gerar.addEventListener("click", gerarRelatorio);

  desenharFormatos();
  limpar(container).append(
    el(
      "div",
      { style: "display:flex;gap:20px;align-items:flex-start" },
      el(
        "div",
        { style: "width:230px;flex:none" },
        el("h1", {}, "Prestação de contas"),
        el("p", { class: "sub" }, "Para financiadores e conselho"),
        campo("Projeto", "rel-projeto", projeto),
        campo("Início do período", "rel-inicio", inicio),
        campo("Fim do período", "rel-fim", fim),
        el("div", { class: "campo" }, el("span", { class: "campo__rotulo" }, "Formato"), formatos),
        erro,
        nota,
        gerar,
        erroGerar,
      ),
      el("div", { style: "flex:1;min-width:0" }, previa),
    ),
  );
  await carregarLancamentos();
}
