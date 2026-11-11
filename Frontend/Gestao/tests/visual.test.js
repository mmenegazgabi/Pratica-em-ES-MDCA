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
