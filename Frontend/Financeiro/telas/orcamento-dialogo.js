// Diálogo de orçamento (criar para um projeto ou editar): valor total, vigência e categorias.
import { el } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { validarEdicao } from "./projetos-dados.js";

export const falhou = (resposta) => resposta.status === 0 || resposta.status >= 400;

export function mensagemDeErro(resposta, padrao) {
  if (resposta.status === 0) return "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";
  const detalhe = resposta.corpo?.detail;
  return typeof detalhe === "string" && detalhe ? detalhe : padrao;
}

export function abrirDocumento(container, dialogo, foco) {
  container.append(dialogo);
  if (typeof dialogo.showModal === "function") dialogo.showModal();
  else dialogo.setAttribute("open", "");
  foco?.focus();
}

/**
 * `salvar(dados)` devolve a resposta da API; em caso de sucesso o diálogo fecha e `aoSalvar` roda.
 * `inicial` = orçamento existente (edição) ou null (criação).
 */
export function abrirDialogoOrcamento(container, { titulo, subtitulo, rotuloSalvar, inicial, salvar, aoSalvar }) {
  let categorias = [...(inicial?.categorias_despesa || [])];
  const campoTexto = (id, rotulo, atributos, valor) => {
    const entrada = el("input", { id, class: "entrada", ...atributos });
    entrada.value = valor ?? "";
    const erro = el("small", { role: "alert", style: "color:var(--perigo-texto);font-size:11px;display:block;margin-top:3px", hidden: true });
    return { entrada, erro, no: el("div", { class: "campo" }, el("label", { for: id }, rotulo), entrada, erro) };
  };
  const valor = campoTexto("orc-valor", "Valor total (R$)", { type: "number", min: "0", step: "0.01", inputmode: "decimal" }, inicial?.valor_total);
  const inicio = campoTexto("orc-inicio", "Início da vigência", { type: "date" }, inicial?.data_inicio);
  const fim = campoTexto("orc-fim", "Fim da vigência", { type: "date" }, inicial?.data_fim);
  const novaCategoria = el("input", { id: "orc-categoria", class: "entrada", maxlength: "60", placeholder: "Nova categoria" });
  const erroCategorias = el("small", { role: "alert", style: "color:var(--perigo-texto);font-size:11px;display:block;margin-top:3px", hidden: true });
  const listaCategorias = el("ul", { style: "list-style:none;margin:8px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:6px" });
  const erroGeral = el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:12px;margin:12px 0 0", hidden: true });
  const cancelar = el("button", { type: "button", class: "btn btn--sec" }, "Cancelar");
  const confirmar = el("button", { type: "submit", class: "btn" }, rotuloSalvar);

  function mostrarErro(campo, texto) {
    campo.hidden = !texto;
    campo.textContent = texto || "";
  }

  function desenharCategorias() {
    listaCategorias.replaceChildren(
      ...categorias.map((c) =>
        el(
          "li",
          { style: "display:inline-flex;align-items:center;gap:4px;border:1px solid var(--borda);border-radius:6px;padding:2px 4px 2px 8px;font-size:12px" },
          c,
          el("button", { type: "button", class: "btn btn--sec btn--pequeno", style: "border:0;padding:2px", "aria-label": `Remover ${c}`, onclick: () => { categorias = categorias.filter((x) => x !== c); desenharCategorias(); } }, icone("fechar")),
        ),
      ),
    );
  }

  function adicionarCategoria() {
    const nome = novaCategoria.value.trim();
    if (!nome) return;
    if (categorias.some((c) => c.toLowerCase() === nome.toLowerCase())) {
      mostrarErro(erroCategorias, "Essa categoria já está na lista.");
      return;
    }
    categorias = [...categorias, nome];
    novaCategoria.value = "";
    mostrarErro(erroCategorias, "");
    desenharCategorias();
  }
  novaCategoria.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      adicionarCategoria();
    }
  });
  desenharCategorias();

  const dialogo = el(
    "dialog",
    { class: "dialogo", "aria-labelledby": "orc-titulo", style: "width:420px" },
    el(
      "form",
      { method: "dialog", novalidate: true },
      el("h2", { id: "orc-titulo", style: "font-size:15px;margin:0 0 4px" }, titulo),
      subtitulo ? el("p", { style: "color:var(--texto-suave);font-size:12px;margin:0" }, subtitulo) : null,
      valor.no,
      el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:10px" }, inicio.no, fim.no),
      el(
        "div",
        { class: "campo" },
        el("label", { for: "orc-categoria" }, "Categorias de despesa"),
        el("div", { style: "display:flex;gap:6px" }, novaCategoria, el("button", { type: "button", class: "btn btn--sec", onclick: adicionarCategoria }, "Adicionar")),
        erroCategorias,
        listaCategorias,
      ),
      erroGeral,
      el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:16px" }, cancelar, confirmar),
    ),
  );
  const fechar = () => dialogo.remove();
  cancelar.addEventListener("click", fechar);
  dialogo.addEventListener("cancel", fechar);
  dialogo.querySelector("form").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    adicionarCategoria();
    const dados = { valor_total: valor.entrada.value, data_inicio: inicio.entrada.value, data_fim: fim.entrada.value, categorias };
    const erros = validarEdicao(dados);
    mostrarErro(valor.erro, erros.valor_total);
    mostrarErro(inicio.erro, erros.data_inicio);
    mostrarErro(fim.erro, erros.data_fim);
    mostrarErro(erroCategorias, erros.categorias);
    mostrarErro(erroGeral, "");
    if (Object.keys(erros).length) return;
    confirmar.disabled = true;
    cancelar.disabled = true;
    const resposta = await salvar({ valor_total: Number(dados.valor_total), data_inicio: dados.data_inicio, data_fim: dados.data_fim, categorias_despesa: categorias });
    if (!falhou(resposta)) {
      fechar();
      return aoSalvar(resposta);
    }
    confirmar.disabled = false;
    cancelar.disabled = false;
    mostrarErro(erroGeral, mensagemDeErro(resposta, "Não foi possível salvar o orçamento. Tente de novo."));
  });
  abrirDocumento(container, dialogo, valor.entrada);
}
