// Montagem de DOM sem innerHTML: texto do usuário entra só por textContent.

/** el("div", {class: "caixa", onclick: fn}, "texto", outroNo) */
export function el(tag, atributos = {}, ...filhos) {
  const no = document.createElement(tag);
  for (const [nome, valor] of Object.entries(atributos || {})) {
    if (valor === undefined || valor === null || valor === false) continue;
    if (nome.startsWith("on") && typeof valor === "function") {
      no.addEventListener(nome.slice(2).toLowerCase(), valor);
    } else if (nome === "class") {
      no.className = valor;
    } else if (nome === "texto") {
      no.textContent = valor;
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

export function limpar(no) {
  while (no.firstChild) no.removeChild(no.firstChild);
  return no;
}
