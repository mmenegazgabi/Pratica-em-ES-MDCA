// T-08 · US-02 — Indicador de saldo com alerta em 80% e 100%.
//
// O componente só desenha: a regra dos limiares fica no backend
// (Backend/Financeiro/alerta_saldo.py) e chega pronta no campo
// `nivel_alerta` de GET /orcamentos/{id} e GET /orcamentos/projeto/{id}.
//
// Uso:
//   import { criarIndicadorSaldo } from "./componentes/indicador-saldo.js";
//   const orcamento = await (await fetch(`${API}/orcamentos/${id}`)).json();
//   container.append(criarIndicadorSaldo(orcamento));
//
// Lembre de incluir também ./componentes/indicador-saldo.css na página.

export const ALERTAS = {
  normal: { rotulo: "Dentro do orçado", icone: "" },
  atencao: { rotulo: "Atenção · 80% ou mais consumido", icone: "⚠" },
  estourado: { rotulo: "Estourado · 100% ou mais consumido", icone: "⛔" },
};

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
// A API já trunca em 2 casas; mostrar as 2 evita que 79,99% vire "80%".
const pct = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

export function descreverAlerta(nivel) {
  return ALERTAS[nivel] ?? ALERTAS.normal;
}

function el(tag, classe, texto) {
  const node = document.createElement(tag);
  if (classe) node.className = classe;
  if (texto !== undefined) node.textContent = texto;
  return node;
}

/**
 * Cria o indicador a partir de um orçamento retornado pela API.
 * @param {{saldo:number, percentual_consumido:number|null, nivel_alerta:string}} orcamento
 * @returns {HTMLElement}
 */
export function criarIndicadorSaldo(orcamento) {
  const nivel = ALERTAS[orcamento.nivel_alerta] ? orcamento.nivel_alerta : "normal";
  const alerta = ALERTAS[nivel];
  const percentual = orcamento.percentual_consumido;
  const percentualTexto = percentual == null ? "—" : `${pct.format(percentual)}%`;

  const raiz = el("div", `indicador-saldo indicador-saldo--${nivel}`);
  raiz.dataset.nivel = nivel;

  const valores = el("div", "indicador-saldo__valores");
  valores.append(
    el("span", "indicador-saldo__saldo", `Saldo ${brl.format(orcamento.saldo)}`),
    el("span", "indicador-saldo__percentual", `${percentualTexto} consumido`),
  );

  // A barra é decorativa; a informação para leitor de tela está no texto.
  const barra = el("div", "indicador-saldo__barra");
  barra.setAttribute("aria-hidden", "true");
  const preenchimento = el("div", "indicador-saldo__preenchimento");
  preenchimento.style.width = `${Math.max(0, Math.min(100, percentual ?? 100))}%`;
  barra.append(preenchimento, el("div", "indicador-saldo__marca"));

  // O alerta não depende só da cor: tem ícone e texto.
  const etiqueta = el("span", "indicador-saldo__alerta");
  if (alerta.icone) {
    const icone = el("span", "indicador-saldo__icone", alerta.icone);
    icone.setAttribute("aria-hidden", "true");
    etiqueta.append(icone);
  }
  etiqueta.append(document.createTextNode(alerta.rotulo));

  raiz.append(valores, barra, etiqueta);
  return raiz;
}
