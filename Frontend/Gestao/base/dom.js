// Montagem de DOM sem innerHTML: texto vindo da API entra só por textContent.

/** el("div", {class: "caixa", onclick: fn}, "texto", outroNo) */
export function el(tag, atributos = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos || {})) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (nome.startsWith("on") && typeof valor === "function") {
      no.addEventListener(nome.slice(2).toLowerCase(), valor);
    } else if (nome === "class") {
      no.className = valor;
    } else if (valor === true) {
      no.setAttribute(nome, "");
    } else {
      no.setAttribute(nome, String(valor));
    }
  }
  for (const filho of filhos.flat()) {
    if (filho === undefined || filho === null || filho === false) continue;
    no.append(typeof filho === "string" || typeof filho === "number" ? String(filho) : filho);
  }
  return no;
}

/**
 * Seção sem caixa (T-00l): título pequeno com uma linha embaixo, como o cabeçalho das
 * caixas do Financeiro, mas sem a borda em volta. Para dados, texto, linha do tempo e
 * listas curtas; tabelas e formulários continuam em caixa (.card).
 */
export function secao(titulo, subtitulo, corpo, acao = null, extras = {}) {
  return el(
    "section",
    { ...extras, class: ["secao", extras.class].filter(Boolean).join(" ") },
    el("div", { class: "secao__cabeca" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), acao),
    el("div", { class: "secao__corpo" }, corpo),
  );
}
