// Menu por perfil: cada perfil vê só os itens do protótipo que pode acessar.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { PAPEIS, PAPEL_PADRAO, lerPapel, menuDoPapel, perfilDaSessao, perfisDaSessao, rotaPermitida, salvarPapel } from "../base/papeis.js";

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

// Login (T-35): perfil a partir dos papéis da sessão.
const sessao = (...papeis) => ({ usuario: { papeis: papeis.map((id) => ({ id, nome: id })) } });

test("os papéis da plataforma viram perfis da Gestão, do mais amplo ao mais restrito", () => {
  assert.deepEqual(perfisDaSessao(sessao("educador", "direcao", "coordenacao")), ["coord", "director", "educator"]);
  assert.deepEqual(perfisDaSessao(sessao("administracao")), ["admin"]);
  assert.deepEqual(perfisDaSessao(sessao("assistente_social", "psicologo")), ["social", "psych"]);
  // Papéis em texto (formato antigo da sessão) também valem.
  assert.deepEqual(perfisDaSessao({ usuario: { papeis: ["coordenacao"] } }), ["coord"]);
});

test("voluntário financeiro e sessão sem papéis não têm perfil na Gestão", () => {
  assert.deepEqual(perfisDaSessao(sessao("voluntario_financeiro")), []);
  assert.equal(perfilDaSessao(sessao("voluntario_financeiro")), null);
  assert.equal(perfilDaSessao({ usuario: {} }), null);
  assert.equal(perfilDaSessao(null), null);
});

test("com login, vale o perfil salvo só se for da pessoa; senão, o mais amplo", () => {
  assert.equal(perfilDaSessao(sessao("coordenacao", "direcao"), "director"), "director");
  assert.equal(perfilDaSessao(sessao("coordenacao", "direcao"), "admin"), "coord");
  assert.equal(perfilDaSessao(sessao("educador"), null), "educator");
});
