// Visual do Financeiro na Gestão (T-00j): o CSS da Gestão não cria cor nem fonte
// próprias; tudo vem das variáveis de ../Financeiro/base/tokens.css
// (plano-identidade-visual-gestao.md, seção 3.1).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const css = readFileSync(new URL("../style.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

// A única cor literal aceita é a da sombra do diálogo, a mesma do .dialogo do Financeiro.
const SOMBRA_DO_DIALOGO = "rgba(0, 0, 0, .12)";

test("nenhuma cor escrita à mão: só as variáveis do Financeiro", () => {
  const semSombra = css.replace(SOMBRA_DO_DIALOGO, "");
  const cores = semSombra.match(/#[0-9a-f]{3,8}\b|rgba?\([^)]*\)|hsla?\([^)]*\)|:\s*(white|black)\b|,\s*(white|black)\)/gi) || [];
  assert.deepEqual(cores, []);
});

test("nenhuma fonte própria: a Inter do Financeiro", () => {
  assert.doesNotMatch(css, /@font-face/);
  assert.doesNotMatch(css, /Bitter|General Sans|Neue Montreal/);
  const familias = [...css.matchAll(/font-family\s*:\s*([^;}]+)/g)].map((m) => m[1].trim());
  assert.deepEqual(familias.filter((f) => !/^(var\(--(fonte|font-body|font-heading|serif|sans)\)|inherit)$/.test(f)), []);
});

test("as variáveis da Gestão apontam para as do Financeiro", () => {
  const raiz = css.match(/:root\s*\{([\s\S]*?)\}/)[1];
  const cores = [...raiz.matchAll(/--(color-[\w-]+|green-\d+|cream-\d+|beige-\d+|gray-\d+|logo-\w+|status-\w+)\s*:\s*([^;]+);/g)];
  assert.ok(cores.length > 30);
  assert.deepEqual(cores.filter(([, , valor]) => !/^var\(--[\w-]+\)$/.test(valor.trim())).map(([, nome]) => nome), []);
});

test("nenhum style fixo nas telas: só larguras e alturas que vêm do dado (T-00l)", () => {
  const ler = (f) => readFileSync(new URL(`../${f}`, import.meta.url), "utf8");
  const app = ler("app.js");
  const fixosNoApp = [...app.matchAll(/style="([^"]*)"/g)].map((m) => m[1]).filter((v) => !v.includes("'+"));
  assert.deepEqual(fixosNoApp, []);
  const telas = ["alertas", "atividades", "equipe", "pessoas", "plano", "programas", "turmas", "usuarios", "visao-integrada"].map((t) => ler(`telas/${t}.js`)).join("\n");
  // Só valores de CSS (propriedade: valor); `style: "currency"` é opção do Intl.NumberFormat.
  const fixosNasTelas = [...telas.matchAll(/style:\s*"([^"]*)"/g)].map((m) => m[1]).filter((v) => v.includes(":"));
  assert.deepEqual(fixosNasTelas, []);
});

// --- Espaçamento e consistência (T-00m) ------------------------------------------

/** Regras de fora de @media, na ordem do arquivo: [seletores, declarações]. */
function regras(texto) {
  const semMedia = texto.replace(/@media[^{]*\{(?:[^{}]*\{[^{}]*\})*[^{}]*\}/g, "");
  return [...semMedia.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => [m[1].split(",").map((x) => x.trim()), m[2]]);
}

test("caixas, avisos, abas e tabelas não têm margem própria: o espaço vem do contêiner", () => {
  const zero = (v) => v === undefined || /^0(px)?$/.test(v);
  for (const seletor of [".card", ".info-box", ".error-message", ".tabs", ".table-wrap", ".secao"]) {
    // Acompanha a margem de cima e a de baixo na ordem do arquivo (a forma curta muda as
    // duas; margin-top e margin-bottom, só uma). A que vale no fim precisa ser zero.
    let cima;
    let baixo;
    for (const [seletores, corpo] of regras(css)) {
      if (!seletores.includes(seletor)) continue;
      for (const [, propriedade, valor] of corpo.matchAll(/(?:^|;)\s*(margin(?:-top|-bottom)?)\s*:\s*([^;]+)/g)) {
        const partes = valor.trim().split(/\s+/);
        if (propriedade === "margin") [cima, baixo] = [partes[0], partes[2] ?? partes[0]];
        if (propriedade === "margin-top") cima = partes[0];
        if (propriedade === "margin-bottom") baixo = partes[0];
      }
    }
    assert.ok(zero(cima) && zero(baixo), `${seletor} termina com margem ${cima} / ${baixo}`);
  }
});

test("os contêineres de layout dão espaço entre os filhos", () => {
  for (const seletor of [".stack", ".pilha-justa"]) {
    assert.ok(regras(css).some(([seletores, corpo]) => seletores.includes(seletor) && /gap\s*:\s*\d+px/.test(corpo)), seletor);
  }
  assert.match(css, /\.gestao \.principal \.main \{[^}]*gap: \d+px/);
});

test("a parte nova do CSS só usa tamanhos de texto e raios que o Financeiro usa", () => {
  const nova = css.slice(css.indexOf(".btn { gap: 6px;"));
  const tamanhos = new Set([...nova.matchAll(/font(?:-size)?\s*:\s*(?:\d{3}\s+)?([\d.]+)px/g)].map((m) => m[1]));
  const DO_FINANCEIRO = new Set(["10", "10.5", "11", "11.5", "12", "13", "14", "15", "16", "18", "19"]);
  assert.deepEqual([...tamanhos].filter((t) => !DO_FINANCEIRO.has(t)), []);
  const raios = new Set([...nova.matchAll(/border-radius\s*:\s*([\d.]+)px/g)].map((m) => m[1]));
  assert.deepEqual([...raios].filter((r) => !["4", "6", "7", "8", "10"].includes(r)), []);
});

test("foco visível no verde do Financeiro ao navegar pelo teclado", () => {
  assert.match(css, /:focus-visible \{ outline: 2px solid var\(--verde\)/);
});
