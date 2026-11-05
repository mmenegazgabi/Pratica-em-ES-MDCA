// Formulário em diálogo para as telas ligadas à API, montado sem innerHTML.
//
// `validar(form)` devolve a mensagem que impede o envio (ou nada). `enviar(form)` chama
// a API: se ela recusar (400, 403, 409…), o diálogo continua aberto e mostra o motivo
// que veio do servidor; se der certo, fecha e chama `aoConcluir(resultado)`.

import { ErroApi } from "./api.js";
import { el } from "./dom.js";

function abrir(dialogo) {
  if (typeof dialogo.showModal === "function") dialogo.showModal();
  else dialogo.setAttribute("open", "");
}

export function fecharDialogo(dialogo = document.getElementById("dialog")) {
  if (!dialogo) return;
  if (typeof dialogo.close === "function") dialogo.close();
  else dialogo.removeAttribute("open");
  dialogo.replaceChildren();
}

const motivo = (erro) => (erro instanceof ErroApi ? erro.detalhe || erro.message : "Não foi possível salvar. Tente de novo.");

export function abrirFormulario({
  titulo,
  campos,
  aviso = null,
  botao = "Salvar",
  validar = () => "",
  enviar,
  aoConcluir = () => {},
  dialogo = document.getElementById("dialog"),
}) {
  const voltarPara = document.activeElement;
  const erro = el("div", { class: "error-message", role: "alert", hidden: true });
  const confirmar = el("button", { type: "submit", class: "btn primary" }, botao);

  function fechar() {
    fecharDialogo(dialogo);
    if (voltarPara?.isConnected) voltarPara.focus();
  }

  function mostrarErro(texto) {
    erro.textContent = texto;
    erro.hidden = false;
  }

  async function submeter(evento) {
    evento.preventDefault();
    // O app tem um tratador global de submit para os formulários do protótipo.
    evento.stopPropagation();
    const problema = validar(form);
    if (problema) return mostrarErro(problema);
    erro.hidden = true;
    confirmar.disabled = true;
    let resultado;
    try {
      resultado = await enviar(form);
    } catch (e) {
      confirmar.disabled = false;
      return mostrarErro(motivo(e));
    }
    fechar();
    aoConcluir(resultado);
  }

  const form = el(
    "form",
    { novalidate: true, onsubmit: submeter },
    aviso,
    erro,
    el("div", { class: "form-grid" }, campos),
    el(
      "div",
      { class: "actions", style: "justify-content:flex-end;margin-top:24px" },
      el("button", { type: "button", class: "btn", onclick: fechar }, "Cancelar"),
      confirmar,
    ),
  );

  dialogo.replaceChildren(
    el(
      "div",
      { class: "dialog-head" },
      el("h2", { id: "dialog-title" }, titulo),
      el("button", { type: "button", class: "icon-button", "aria-label": "Fechar janela", onclick: fechar }, "×"),
    ),
    el("div", { class: "dialog-body" }, form),
  );
  abrir(dialogo);
  form.querySelector("input, select, textarea")?.focus();
  return form;
}

/** Campo com rótulo, no padrão `.field` do design system. */
export function campo(id, rotulo, entrada, { dica = "", largo = false } = {}) {
  entrada.id = id;
  return el("div", { class: largo ? "field wide" : "field" }, el("label", { for: id }, rotulo), entrada, dica ? el("small", {}, dica) : null);
}

/** <select> com opções [valor, rótulo]; a primeira opção vazia pede a escolha. */
export function selecao(nome, opcoes, { vazio = "Selecione" } = {}) {
  return el(
    "select",
    { name: nome, required: true },
    el("option", { value: "" }, vazio),
    opcoes.map(([valor, rotulo]) => el("option", { value: valor }, rotulo)),
  );
}

/** Data de hoje em AAAA-MM-DD, no fuso do aparelho. */
export function hojeIso(agora = new Date()) {
  const dois = (n) => String(n).padStart(2, "0");
  return `${agora.getFullYear()}-${dois(agora.getMonth() + 1)}-${dois(agora.getDate())}`;
}
