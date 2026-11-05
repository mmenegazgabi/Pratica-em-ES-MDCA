import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import * as modulo from "../base/sessao.js";
import { escolherPapel, esquecerPapel, itensDeMenu, lerSessao, nomeDoAutor, papeisDoFinanceiro } from "../base/sessao.js";
import { sessaoDeTeste } from "./ajuda-sessao.js";

function armazemFalso() {
  const dados = new Map();
  return {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
}

beforeEach(() => {
  globalThis.localStorage = armazemFalso();
  globalThis.sessionStorage = armazemFalso();
});

test("saíram a sessão própria do Financeiro e as chaves do celular", () => {
  for (const nome of ["salvarSessao", "usarChaveDeSessao", "CHAVE_SESSAO_COMPUTADOR", "CHAVE_SESSAO_CELULAR"]) {
    assert.equal(nome in modulo, false, nome);
  }
});

test("sem sessão da plataforma não há sessão do Financeiro", () => {
  assert.equal(lerSessao(), null);
});

test("papeisDoFinanceiro segue a ordem de PAPEIS e ignora papéis de fora", () => {
  const sessao = sessaoDeTeste({ papeis: ["educador", "administracao", "coordenacao"] });
  assert.deepEqual(papeisDoFinanceiro(sessao), ["coordenacao", "educador"]);
  assert.deepEqual(papeisDoFinanceiro(null), []);
});

test("papel único entra direto, com nome e id do banco", () => {
  sessaoDeTeste({ papeis: ["direcao"], nome: "Jane Almeida", id: "u-jane" });
  assert.deepEqual(lerSessao(), { papel: "direcao", nome: "Jane Almeida", usuarioId: "u-jane" });
});

test("dois papéis sem escolha ficam sem papel; a escolha persiste", () => {
  sessaoDeTeste({ papeis: ["coordenacao", "educador"] });
  assert.equal(lerSessao().papel, null);
  escolherPapel("educador");
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "educador");
  assert.equal(lerSessao().papel, "educador");
  esquecerPapel();
  assert.equal(lerSessao().papel, null);
});

test("papel salvo que a pessoa perdeu é ignorado", () => {
  sessaoDeTeste({ papeis: ["voluntario_financeiro"], papel: "coordenacao" });
  assert.equal(lerSessao().papel, "voluntario_financeiro");
  sessaoDeTeste({ papeis: ["voluntario_financeiro", "direcao"], papel: "coordenacao" });
  assert.equal(lerSessao().papel, null);
});

test("sem papel do Financeiro a sessão existe, mas sem papel", () => {
  sessaoDeTeste({ papeis: ["administracao"] });
  assert.equal(lerSessao().papel, null);
});

test("armazenamento quebrado não derruba a leitura", () => {
  globalThis.localStorage = { getItem() { throw new Error("bloqueado"); }, setItem() { throw new Error("bloqueado"); }, removeItem() {} };
  assert.equal(lerSessao(), null);
  escolherPapel("coordenacao");
  esquecerPapel();
});

test("itensDeMenu por papel", () => {
  const ids = (papel) => itensDeMenu(papel).map((i) => i.id);
  assert.deepEqual(ids("coordenacao"), ["inicio", "lancamentos", "projetos", "relatorios", "auditoria"]);
  assert.deepEqual(ids("direcao"), ["inicio", "projetos", "relatorios", "auditoria"]);
  assert.deepEqual(ids("voluntario_financeiro"), ["inicio", "lancamentos", "conciliacao"]);
  assert.deepEqual(ids("educador"), []);
  for (const papel of ["coordenacao", "direcao", "voluntario_financeiro"]) {
    for (const item of itensDeMenu(papel)) assert.ok(item.rotulo && item.icone && item.rota);
  }
});

test("nomeDoAutor capitaliza o slug e tolera vazio", () => {
  assert.equal(nomeDoAutor("marcos-vieira"), "Marcos Vieira");
  assert.equal(nomeDoAutor(null), "");
  assert.equal(nomeDoAutor(""), "");
});
