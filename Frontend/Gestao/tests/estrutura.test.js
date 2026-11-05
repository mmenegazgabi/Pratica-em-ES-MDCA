// Toda chamada HTTP passa pelo cliente de API: nenhum outro arquivo usa fetch ou XHR.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = fileURLToPath(new URL("..", import.meta.url));

function arquivosJs(pasta) {
  return readdirSync(pasta, { withFileTypes: true }).flatMap((item) => {
    if (["node_modules", "tests"].includes(item.name)) return [];
    const caminho = join(pasta, item.name);
    return item.isDirectory() ? arquivosJs(caminho) : item.name.endsWith(".js") ? [caminho] : [];
  });
}

test("só base/api.js faz requisições HTTP", () => {
  const usam = arquivosJs(RAIZ)
    .filter((arquivo) => /\bfetch\s*\(|XMLHttpRequest|navigator\.sendBeacon/.test(readFileSync(arquivo, "utf8")))
    // Separador do POSIX também no Windows, para a comparação valer em qualquer máquina.
    .map((arquivo) => relative(RAIZ, arquivo).split(sep).join("/"));

  assert.deepEqual(usam, ["base/api.js"]);
});
