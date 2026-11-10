// Uso sem rede no navegador do celular (T-57): o service worker guarda todos os arquivos
// do app e não intercepta a API.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
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
  const existentes = new Set(arquivos(RAIZ, [""]));

  assert.deepEqual(ARQUIVOS.filter((a) => a !== "./" && !existentes.has(a)), []);
});

test("o service worker não intercepta a API nem envios", () => {
  assert.match(SW, /pedido\.method !== "GET"/);
  assert.match(SW, /origin !== self\.location\.origin/);
  assert.doesNotMatch(SW, /pratica-em-es-mdca|\/gestao\//);
});

test("o service worker é um script clássico (sem import/export)", () => {
  assert.doesNotMatch(SW, /^\s*(import|export)\s/m);
});
