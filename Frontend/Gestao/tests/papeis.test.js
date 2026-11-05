// Menu por perfil: cada perfil vê só os itens do protótipo que pode acessar.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { PAPEIS, PAPEL_PADRAO, lerPapel, menuDoPapel, rotaPermitida, salvarPapel } from "../base/papeis.js";

const rotulos = (papel) => menuDoPapel(papel).flatMap((g) => g.itens.map((i) => i.rotulo));
const grupos = (papel) => menuDoPapel(papel).map((g) => g.grupo);

beforeEach(() => {
  const dados = new Map();
  globalThis.localStorage = {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
  };
});

test("administrador vê todos os itens, inclusive Usuários e acessos", () => {
  assert.deepEqual(rotulos("admin"), [
    "Visão geral",
    "Programas e turmas",
    "Pessoas e famílias",
    "Atividades e frequência",
    "Acompanhamento técnico",
    "Aprendizagem",
    "Indicadores e relatórios",
    "Visão integrada",
    "Usuários e acessos",
    "Trilha de auditoria",
    "Importação e piloto",
  ]);
});

test("só o administrador vê Usuários e acessos", () => {
  for (const papel of Object.keys(PAPEIS).filter((p) => p !== "admin")) {
    assert.equal(rotulos(papel).includes("Usuários e acessos"), false, papel);
  }
});

test("coordenação vê tudo menos Usuários e acessos", () => {
  assert.deepEqual(rotulos("coord"), rotulos("admin").filter((r) => r !== "Usuários e acessos"));
});

test("educadora vê só programas, pessoas, atividades e indicadores", () => {
  assert.deepEqual(rotulos("educator"), ["Visão geral", "Programas e turmas", "Pessoas e famílias", "Atividades e frequência", "Indicadores e relatórios"]);
  assert.deepEqual(grupos("educator"), ["Programas e público", "Execução e atendimento", "Resultados"]);
});

test("diretoria consulta resultados, sem cadastros de pessoas nem atendimento técnico", () => {
  assert.deepEqual(rotulos("director"), ["Visão geral", "Programas e turmas", "Atividades e frequência", "Aprendizagem", "Indicadores e relatórios", "Visão integrada"]);
});

test("psicólogo abre Acompanhamento técnico direto em Atendimentos", () => {
  const item = menuDoPapel("psych").flatMap((g) => g.itens).find((i) => i.rotulo === "Acompanhamento técnico");

  assert.equal(item.secao, "atendimentos");
  assert.equal(rotaPermitida("psych", "alertas"), false);
});

test("item ativo acompanha a seção atual, inclusive as rotas irmãs", () => {
  const ativos = (secao) => menuDoPapel("coord", secao).flatMap((g) => g.itens).filter((i) => i.ativo).map((i) => i.rotulo);

  assert.deepEqual(ativos("turmas"), ["Programas e turmas"]);
  assert.deepEqual(ativos("rede"), ["Acompanhamento técnico"]);
});

test("perfil salvo neste aparelho; sem perfil ou inválido, vale a coordenação", () => {
  assert.equal(lerPapel(), PAPEL_PADRAO);

  salvarPapel("psych");
  assert.equal(lerPapel(), "psych");

  localStorage.setItem("mdca.gestao.papel", "hacker");
  assert.equal(lerPapel(), PAPEL_PADRAO);
});
