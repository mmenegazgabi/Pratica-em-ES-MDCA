import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { encerrarSessao, itensDeMenu, lerSessao, nomeDoAutor, salvarSessao, usuarioId } from "../base/sessao.js";

beforeEach(() => {
  const dados = new Map();
  globalThis.localStorage = {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
});

test("usuarioId normaliza o nome", () => {
  assert.equal(usuarioId(" Marcos Vieira "), "marcos-vieira");
  assert.equal(usuarioId("José  da Conceição"), "jose-da-conceicao");
});

test("sessão é salva, lida e encerrada", () => {
  assert.equal(lerSessao(), null);
  salvarSessao({ papel: "coordenacao", nome: "Ana" });
  assert.deepEqual(lerSessao(), { papel: "coordenacao", nome: "Ana" });
  encerrarSessao();
  assert.equal(lerSessao(), null);
});

test("sessão com papel inválido ou armazenamento quebrado vira null", () => {
  localStorage.setItem("mdca.financeiro.sessao", JSON.stringify({ papel: "hacker", nome: "x" }));
  assert.equal(lerSessao(), null);
  globalThis.localStorage = { getItem() { throw new Error("bloqueado"); } };
  assert.equal(lerSessao(), null);
});

test("itensDeMenu por papel", () => {
  const ids = (papel) => itensDeMenu(papel).map((i) => i.id);
  assert.deepEqual(ids("coordenacao"), ["inicio", "lancamentos", "projetos"]);
  assert.deepEqual(ids("direcao"), ["inicio", "projetos"]);
  assert.deepEqual(ids("voluntario_financeiro"), ["inicio", "lancamentos"]);
  assert.deepEqual(ids("educador"), []);
  for (const item of itensDeMenu("coordenacao")) assert.ok(item.rotulo && item.icone && item.rota);
});

test("nomeDoAutor capitaliza o slug e tolera vazio", () => {
  assert.equal(nomeDoAutor("marcos-vieira"), "Marcos Vieira");
  assert.equal(nomeDoAutor(null), "");
  assert.equal(nomeDoAutor(""), "");
});
