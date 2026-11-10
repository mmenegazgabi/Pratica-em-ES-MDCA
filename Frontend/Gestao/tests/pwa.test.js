// Uso sem rede no navegador do celular (T-57): o service worker guarda todos os arquivos
// do app e não intercepta a API.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = fileURLToPath(new URL("..", import.meta.url));
const SW = readFileSync(join(RAIZ, "sw.js"), "utf8");
const ARQUIVOS = [...SW.match(/const ARQUIVOS = \[([\s\S]*?)\];/)[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);

function arquivos(pasta, extensoes) {
  return readdirSync(pasta, { withFileTypes: true }).flatMap((item) => {
    if (["node_modules", "tests"].includes(item.name)) return [];
    const caminho = join(pasta, item.name);
    if (item.isDirectory()) return arquivos(caminho, extensoes);
    return extensoes.some((e) => item.name.endsWith(e)) ? [relative(RAIZ, caminho).split(sep).join("/")] : [];
  });
}

test("o service worker guarda todo arquivo do app (JS, CSS, fontes e página)", () => {
  const doApp = arquivos(RAIZ, [".js", ".css", ".woff2", ".html"]).filter((a) => a !== "sw.js");

  assert.deepEqual(doApp.filter((a) => !ARQUIVOS.includes(a)), []);
});

test("a lista do service worker só tem arquivos que existem", () => {
  // Inclui os CSS do Financeiro que a Gestão carrega (T-00j), fora da pasta da Gestão.
  assert.deepEqual(ARQUIVOS.filter((a) => a !== "./" && !existsSync(join(RAIZ, a))), []);
});

test("o service worker guarda os estilos do Financeiro que a página carrega (T-00j)", () => {
  const html = readFileSync(join(RAIZ, "index.html"), "utf8");
  const estilos = [...html.matchAll(/<link rel="stylesheet" href="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(estilos, ["../Financeiro/base/tokens.css", "../Financeiro/base/componentes.css", "../Financeiro/style.css", "style.css"]);
  assert.deepEqual(estilos.filter((e) => !ARQUIVOS.includes(e)), []);
});

test("o service worker não intercepta a API nem envios", () => {
  assert.match(SW, /pedido\.method !== "GET"/);
  assert.match(SW, /origin !== self\.location\.origin/);
  assert.doesNotMatch(SW, /pratica-em-es-mdca|\/gestao\//);
});

test("o service worker é um script clássico (sem import/export)", () => {
  assert.doesNotMatch(SW, /^\s*(import|export)\s/m);
});
