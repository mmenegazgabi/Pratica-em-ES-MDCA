// Menu único da plataforma: quem tem um papel nos dois módulos (Coordenação, Direção,
// Educador) vê as abas da Gestão e do Financeiro juntas, sem trocar de módulo.
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { menuUnificado, papelDaPlataforma, sincronizarPapel } from "../../Shared/menu-unificado.js";

const armazem = () => {
  const dados = new Map();
  return {
    getItem: (k) => (dados.has(k) ? dados.get(k) : null),
    setItem: (k, v) => dados.set(k, String(v)),
    removeItem: (k) => dados.delete(k),
    clear: () => dados.clear(),
  };
};
globalThis.localStorage = armazem();
beforeEach(() => localStorage.clear());

const sessao = (...papeis) => ({ usuario: { id: "u", nome: "Luana", papeis: papeis.map((id) => ({ id, nome: id })) } });
const rotulos = (itens) => itens.map((i) => i.rotulo);

test("coordenação vê as abas dos dois módulos numa lista só, com nomes que não se repetem", () => {
  const itens = menuUnificado(sessao("coordenacao"), "coordenacao", { modulo: "gestao" });
  assert.deepEqual(rotulos(itens), [
    "Visão geral",
    "Programas e turmas",
    "Pessoas e famílias",
    "Atividades e frequência",
    "Acompanhamento técnico",
    "Aprendizagem",
    "Relatório técnico",
    "Visão integrada",
    "Resumo financeiro",
    "Lançamentos",
    "Projetos",
    "Prestação de contas",
    "Auditoria",
    "Importação e piloto",
  ]);
});

test("direção recebe o painel da Diretoria e só as abas da Gestão que já pode ver", () => {
  const itens = rotulos(menuUnificado(sessao("direcao"), "direcao", { modulo: "gestao" }));
  assert.ok(itens.includes("Painel"));
  assert.ok(!itens.includes("Lançamentos"));
  assert.ok(!itens.includes("Pessoas e famílias")); // a Direção não vê pessoas na Gestão
});

test("educador vê as abas da Gestão e uma aba para lançar despesa", () => {
  const itens = menuUnificado(sessao("educador"), "educador", { modulo: "gestao" });
  const lancar = itens.find((i) => i.rotulo === "Lançar despesa");
  assert.equal(lancar?.href, "../Financeiro/lancamento/");
  assert.ok(itens.some((i) => i.rotulo === "Atividades e frequência"));
});

test("os links apontam para o próprio módulo com # e para o outro com o caminho dele", () => {
  const naGestao = menuUnificado(sessao("coordenacao"), "coordenacao", { modulo: "gestao" });
  assert.equal(naGestao.find((i) => i.rotulo === "Visão geral").href, "#/inicio");
  assert.equal(naGestao.find((i) => i.rotulo === "Projetos").href, "../Financeiro/#/projetos");

  const noFinanceiro = menuUnificado(sessao("coordenacao"), "coordenacao", { modulo: "financeiro" });
  assert.equal(noFinanceiro.find((i) => i.rotulo === "Visão geral").href, "../Gestao/#/inicio");
  assert.equal(noFinanceiro.find((i) => i.rotulo === "Projetos").href, "#/projetos");
});

test("marca como atual só a aba da tela aberta, no módulo certo", () => {
  const naGestao = menuUnificado(sessao("coordenacao"), "coordenacao", { modulo: "gestao", atual: "turmas" });
  assert.deepEqual(naGestao.filter((i) => i.ativo).map((i) => i.rotulo), ["Programas e turmas"]);

  const noFinanceiro = menuUnificado(sessao("coordenacao"), "coordenacao", { modulo: "financeiro", atual: "inicio" });
  assert.deepEqual(noFinanceiro.filter((i) => i.ativo).map((i) => i.rotulo), ["Resumo financeiro"]);
});

test("sem menu único para quem só tem papel num módulo", () => {
  assert.equal(menuUnificado(sessao("voluntario_financeiro"), "voluntario_financeiro", { modulo: "financeiro" }), null);
  assert.equal(menuUnificado(sessao("psicologo"), "psicologo", { modulo: "gestao" }), null);
  assert.equal(menuUnificado(sessao("administracao"), "administracao", { modulo: "gestao" }), null);
  // Papel que a pessoa não tem não abre o menu único.
  assert.equal(menuUnificado(sessao("educador"), "coordenacao", { modulo: "gestao" }), null);
});

test("perfil da Gestão vira o papel da plataforma", () => {
  assert.equal(papelDaPlataforma("coord"), "coordenacao");
  assert.equal(papelDaPlataforma("director"), "direcao");
  assert.equal(papelDaPlataforma("educator"), "educador");
  assert.equal(papelDaPlataforma("psych"), "psicologo");
  assert.equal(papelDaPlataforma("inventado"), null);
});

test("o papel em uso num módulo é gravado só no outro", () => {
  sincronizarPapel("direcao", { para: "gestao" });
  assert.equal(localStorage.getItem("mdca.gestao.papel"), "director");
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), null);

  localStorage.clear();
  sincronizarPapel("direcao", { para: "financeiro" });
  assert.equal(localStorage.getItem("mdca.financeiro.papel"), "direcao");
  assert.equal(localStorage.getItem("mdca.gestao.papel"), null);
});
