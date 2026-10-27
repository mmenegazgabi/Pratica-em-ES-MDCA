// Contador de pendências ao lado de "Início" na barra lateral.
// As telas chamam definirContador(n); a barra lateral marca o selo com data-contador.

let valor = 0;
let definido = false;

function aplicar() {
  for (const selo of document.querySelectorAll("[data-contador]")) {
    selo.textContent = String(valor);
    selo.hidden = valor <= 0;
  }
}

export function definirContador(n) {
  definido = true;
  valor = Math.max(0, Number(n) || 0);
  aplicar();
}

/** A barra lateral chama depois de ser redesenhada. */
export function reaplicarContador() {
  aplicar();
}

/** Já houve alguma contagem desde que a página abriu? */
export function contadorDefinido() {
  return definido;
}
