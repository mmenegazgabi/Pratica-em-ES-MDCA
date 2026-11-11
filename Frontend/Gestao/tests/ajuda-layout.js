// Verificador de layout das telas (T-00m · plano-identidade-visual-gestao.md, seção 8).
//
// Pega, no HTML montado por uma tela, os dois problemas que o redesenho quer evitar:
// - caixa dentro de caixa (.card dentro de .card);
// - blocos irmãos (caixa, seção, aviso, abas, tabela…) dentro de um elemento que não dá
//   espaço entre os filhos: é o que deixa dois blocos encostados.
//
// O espaço entre blocos vem sempre do contêiner (gap ou "> * + *" no CSS), nunca da margem
// de cada bloco. Por isso a regra olha o pai.

export const BLOCOS = [
  ".card",
  ".secao",
  ".info-box",
  ".error-message",
  ".resumo-linha",
  ".tabs",
  ".table-wrap",
  ".stats",
  ".detail-grid",
  ".grid-main",
  ".toolbar",
  ".aviso-faixa",
].join(", ");

// Elementos que dão espaço entre os filhos (gap ou "> * + *" no style.css).
export const CONTEINERES = [
  ".stack",
  ".pilha-justa",
  ".main",
  ".detail-grid",
  ".grid-main",
  ".guide-grid",
  ".program-grid",
  ".card-body",
  ".secao__corpo",
  ".form-grid",
  ".form-body",
  ".dialog-body",
].join(", ");

const descrever = (no) => `${no.tagName.toLowerCase()}${no.className ? "." + String(no.className).trim().split(/\s+/).join(".") : ""}`;

/** Lista de problemas de layout dentro de `raiz` (vazia quando está tudo certo). */
export function problemasDeLayout(raiz) {
  const problemas = [];
  for (const caixa of raiz.querySelectorAll(".card")) {
    const externa = caixa.parentElement?.closest(".card");
    if (externa && raiz.contains(externa)) problemas.push(`caixa dentro de caixa: ${descrever(caixa)} em ${descrever(externa)}`);
  }
  for (const pai of [raiz, ...raiz.querySelectorAll("*")]) {
    const blocos = [...pai.children].filter((filho) => filho.matches(BLOCOS));
    if (blocos.length >= 2 && !pai.matches(CONTEINERES)) {
      problemas.push(`blocos sem espaço entre eles em ${descrever(pai)}: ${blocos.map(descrever).join(" + ")}`);
    }
  }
  return problemas;
}
