// T-08 · US-02 — Indicador de saldo com alerta em 80% e 100%.
//
// Faixas de cor (critérios de aceitação da T-08):
//   consumo  < 80%        -> cor neutra  (verde)
//   consumo 80% a 99,99%  -> cor de alerta (amarelo)
//   consumo >= 100%       -> cor crítica (vermelho)
//
// A regra dos limiares fica no backend (Backend/Financeiro/alerta_saldo.py)
// e chega pronta no campo `nivel_alerta` de GET /orcamentos/{id} e
// GET /orcamentos/projeto/{id}. Este componente só converte o nível em cor.
//
// Uso:
//   import { criarIndicadorSaldo } from "./componentes/indicador-saldo.js";
//   const orcamento = await (await fetch(`${API}/orcamentos/${id}`)).json();
//   container.append(criarIndicadorSaldo(orcamento));
//
// Lembre de incluir também ./componentes/indicador-saldo.css na página.

// Cores do design system MDCA (tokens de status), com fallback em hexadecimal.
export const CORES = Object.freeze({
  neutra: Object.freeze({
    nome: "neutra",
    valor: "var(--status-approved, #6aba60)",
    texto: "#2f6b28",
    fundo: "#e8f4e6",
  }),
  alerta: Object.freeze({
    nome: "alerta",
    valor: "var(--status-pending, #fde118)",
    texto: "#6b5a00",
    fundo: "#fdf6c4",
  }),
  critica: Object.freeze({
    nome: "critica",
    valor: "var(--status-rejected, #f02d34)",
    texto: "#b3261e",
    fundo: "#fdeaea",
  }),
});

export const FAIXAS = Object.freeze({
  normal: Object.freeze({ cor: CORES.neutra, rotulo: "Dentro do orçado", icone: "✓" }),
  atencao: Object.freeze({ cor: CORES.alerta, rotulo: "Atenção · 80% ou mais consumido", icone: "⚠" }),
  estourado: Object.freeze({ cor: CORES.critica, rotulo: "Estourado · 100% ou mais consumido", icone: "⛔" }),
});

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
// A API já trunca em 2 casas; mostrar as 2 evita que 79,99% vire "80%".
const pct = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });

/**
 * Calcula o que o indicador deve mostrar, sem tocar no DOM (testável no Node).
 * @param {{saldo:number, percentual_consumido:number|null, nivel_alerta:string}} orcamento
 */
export function estadoIndicador(orcamento) {
  const nivel = Object.hasOwn(FAIXAS, orcamento.nivel_alerta) ? orcamento.nivel_alerta : "normal";
  const faixa = FAIXAS[nivel];
  const percentual = orcamento.percentual_consumido;

  return {
    nivel,
    cor: faixa.cor,
    rotulo: faixa.rotulo,
    icone: faixa.icone,
    saldoTexto: `Saldo ${brl.format(orcamento.saldo)}`,
    percentualTexto: percentual == null ? "— consumido" : `${pct.format(percentual)}% consumido`,
    larguraBarra: `${Math.max(0, Math.min(100, percentual ?? 100))}%`,
  };
}

function el(doc, tag, classe, texto) {
  const node = doc.createElement(tag);
  if (classe) node.className = classe;
  if (texto !== undefined) node.textContent = texto;
  return node;
}

/**
 * Cria o indicador a partir de um orçamento retornado pela API.
 * @param {{saldo:number, percentual_consumido:number|null, nivel_alerta:string}} orcamento
 * @param {Document} [doc] documento onde criar os elementos (para testes)
 * @returns {HTMLElement}
 */
export function criarIndicadorSaldo(orcamento, doc = globalThis.document) {
  const estado = estadoIndicador(orcamento);

  const raiz = el(doc, "div", `indicador-saldo indicador-saldo--${estado.nivel}`);
  raiz.dataset.nivel = estado.nivel;
  raiz.dataset.cor = estado.cor.nome;
  raiz.style.setProperty("--indicador-cor", estado.cor.valor);
  raiz.style.setProperty("--indicador-cor-texto", estado.cor.texto);
  raiz.style.setProperty("--indicador-cor-fundo", estado.cor.fundo);

  const valores = el(doc, "div", "indicador-saldo__valores");
  valores.append(
    el(doc, "span", "indicador-saldo__saldo", estado.saldoTexto),
    el(doc, "span", "indicador-saldo__percentual", estado.percentualTexto),
  );

  // A barra é decorativa; a informação para leitor de tela está no texto.
  const barra = el(doc, "div", "indicador-saldo__barra");
  barra.setAttribute("aria-hidden", "true");
  const preenchimento = el(doc, "div", "indicador-saldo__preenchimento");
  preenchimento.style.width = estado.larguraBarra;
  barra.append(preenchimento, el(doc, "div", "indicador-saldo__marca"));

  // O alerta não depende só da cor: tem ícone e texto.
  const etiqueta = el(doc, "span", "indicador-saldo__alerta");
  const icone = el(doc, "span", "indicador-saldo__icone", estado.icone);
  icone.setAttribute("aria-hidden", "true");
  etiqueta.append(icone, el(doc, "span", "indicador-saldo__rotulo", estado.rotulo));

  raiz.append(valores, barra, etiqueta);
  return raiz;
}
