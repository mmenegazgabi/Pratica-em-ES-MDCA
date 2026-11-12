// Aplicação inteira no jsdom: menu lateral do protótipo, aviso de demonstração,
// Programas pela API, troca de módulo e menu por perfil.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(/<script[\s\S]*?<\/script>/, "");
// Console silenciado: o jsdom não implementa window.scrollTo, que o app chama a cada navegação.
const dom = new JSDOM(html, { url: "http://localhost/Gestao/#/inicio", virtualConsole: new VirtualConsole() });
const { window } = dom;
Object.assign(globalThis, {
  window,
  document: window.document,
  location: window.location,
  localStorage: window.localStorage,
  sessionStorage: window.sessionStorage,
  DOMParser: window.DOMParser,
});

const chamadas = [];
const RESPOSTAS = [
  [/\/atividades\/a-1$/, { id: "a-1", turma: "Oficina de arte", data: "2026-11-05", educador: "Jéssica", conteudo: "Pintura.", observacao: null, presentes: 0, ausentes: 1, chamada: [{ pessoa_id: "pe-lara", pessoa: "Lara Oliveira", presente: false, justificativa: null }], evidencias: [] }],
  [/\/equipe(\?|$)/, [{ id: "v-1", usuario_id: "ana", nome: "Ana Martins", papel_id: "coordenacao", papel: "Coordenação", data_entrada: "2025-01-10", data_saida: null, ativo: true }]],
  [/\/espacos$/, []],
  [/\/gestao\/usuarios$/, [{ id: "ana", nome: "Ana Martins", email: null, ativo: true, papeis: [], vinculos: [] }]],
  [/\/gestao\/programas$/, [{ id: "p-1", nome: "Semear" }]],
  [/\/gestao\/programas\/p-1\/turmas$/, [{ id: "t-9", programa_id: "p-1", nome: "Oficina de arte", espaco: "Ateliê", responsavel: "Jéssica", capacidade: 2, ativas: 2, em_espera: 1, vagas_livres: 0, dias_semana: [1, 3], hora_inicio: "14:00:00", hora_fim: "16:00:00" }]],
  [/\/gestao\/alertas(\?situacao=aberto)?$/, [{ id: "al-9", descricao: "4 faltas seguidas na turma Oficina de arte.", titulo: "Lara Oliveira precisa de um contato", programa_id: "p-1", pessoa_id: "pe-lara", pessoa: "Lara Oliveira", turma: "Oficina de arte", responsavel: "Patrícia Souza", situacao: "aberto", faltas_consecutivas: 3, limite: 3, primeira_falta: "2026-11-03", ultima_falta: "2026-11-05", criado_em: "2026-11-05T18:00:00Z" }]],
  [/\/gestao\/pessoas$/, [{ id: "pe-lara", nome: "Lara Oliveira", data_nascimento: "2013-05-12", programa_id: "p-1", programa: "Semear", nucleo_familiar: { id: "f-1", nome: "Oliveira" }, responsaveis: [], situacao: "ativo", autorizacao_imagem: "vigente" }]],
];
globalThis.fetch = async (url, opcoes = {}) => {
  chamadas.push({ url, ...opcoes });
  const corpo = RESPOSTAS.find(([padrao]) => padrao.test(url))?.[1] ?? [];
  return new Response(JSON.stringify(corpo), { status: 200 });
};
// Login único (T-35): a sessão da plataforma, gravada pela página inicial.
// Com o login, a pessoa só troca entre os próprios perfis: os testes de troca precisam
// dos três papéis. Coordenação fica salva para o app abrir nela.
const SESSAO = { token: "sessao-de-teste", expira_em: "2999-01-01T00:00:00Z", usuario: { id: "ana", nome: "Ana Martins", email: "ana@mdca.test", papeis: ["coordenacao", "direcao", "administracao"] } };
localStorage.setItem("mdca.sessao", JSON.stringify(SESSAO));
localStorage.setItem("mdca.gestao.papel", "coord");

await import("../app.js");

const $ = (s) => document.querySelector(s);
const esperar = () => new Promise((r) => setTimeout(r, 20));
// Barra lateral com as classes do Financeiro (T-00k): .lateral, .lateral__item.
const menu = () => [...document.querySelectorAll(".lateral .lateral__item > span:first-of-type")].map((s) => s.textContent);
async function irPara(hash) {
  window.location.hash = hash;
  await esperar();
}

test("abre na Visão geral com o menu lateral do protótipo e o aviso de demonstração", () => {
  assert.equal($("#main h1").textContent.startsWith("Bom dia"), true);
  assert.deepEqual(
    [...document.querySelectorAll(".lateral .lateral__grupo")].map((g) => g.textContent),
    ["Programas e público", "Execução e atendimento", "Resultados", "Auditoria e implantação"],
  );
  assert.ok($(".demo-banner"));
  // A única chamada da Visão geral é a dos alertas abertos, para os avisos da equipe (T-90).
  assert.deepEqual(chamadas.map((c) => c.url.replace(/^https?:\/\/[^/]+/, "")), ["/gestao/alertas?situacao=aberto"]);
});

test("notificações e Visão geral mostram os alertas reais da API, sem os de infrequência fictícios (T-90)", async () => {
  await irPara("#/inicio");
  await esperar();

  // O contador de alertas abertos fica no item Visão geral, como o contador do Início no Financeiro.
  const contador = $('.lateral__item[href="#/inicio"] .lateral__contador');
  assert.equal(contador.hidden, false);
  assert.match(contador.textContent, /^\d+$/);
  const destinos = [...document.querySelectorAll("#main .priority-item a")].map((a) => a.getAttribute("href"));
  assert.equal(destinos[0], "#/alertas/al-9");
  assert.match(document.querySelector("#main .priority-item").textContent, /Lara Oliveira precisa de um contato.*4 faltas seguidas/);
  // Os alertas fictícios de infrequência do protótipo saíram (o "al1" era de infrequência).
  assert.ok(!destinos.includes("#/alertas/al1"));

});

test("Programas carrega pela API, sem o aviso de demonstração", async () => {
  await irPara("#/programas");

  assert.equal(chamadas.at(-1).url.endsWith("/gestao/programas"), true);
  assert.equal(chamadas.at(-1).headers.Authorization, "Bearer sessao-de-teste");
  assert.equal($("#tela-api tbody td").textContent, "Semear");
  assert.equal($(".demo-banner"), null);
  assert.equal($('.lateral__item[aria-current="page"] span').textContent, "Programas e turmas");
});

test("Equipe e espaços de um programa do cadastro carrega pela API, com a sessão do login", async () => {
  chamadas.length = 0;
  await irPara("#/programas/p-1/equipe");

  const urls = chamadas.map((c) => c.url.replace(/^https?:\/\/[^/]+/, ""));
  assert.ok(urls.includes("/gestao/programas/p-1/equipe?incluir_desligados=true"));
  assert.ok(urls.includes("/gestao/programas/p-1/espacos"));
  // Quem chama vem do token da sessão; não há mais código de acesso nem X-Usuario-Id.
  assert.ok(chamadas.every((c) => c.headers.Authorization === "Bearer sessao-de-teste" && !("X-Usuario-Id" in c.headers)));
  assert.equal($("#tela-api tbody strong").textContent, "Ana Martins");
  assert.equal($("#main .subtitle").textContent, "Semear");
  assert.equal($(".demo-banner"), null);
});

test("o menu do usuário mostra a conta da sessão, sem formulário de usuário", () => {
  assert.match($(".api-user").textContent, /Conectado como Ana Martins \(ana@mdca\.test\)/);
  assert.equal(document.querySelector('[data-action="api-user"]'), null);
});

test("detalhe de programa fictício do protótipo continua na demonstração", async () => {
  await irPara("#/programas/p1");

  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("Pessoas e famílias carrega pela API; pessoas fictícias do protótipo seguem na demonstração", async () => {
  chamadas.length = 0;
  await irPara("#/pessoas");

  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/pessoas")));
  assert.equal($("#tela-api tbody a").textContent, "Lara Oliveira");
  assert.equal($(".demo-banner"), null);

  await irPara("#/pessoas/u1");
  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("Visão integrada carrega pela API, sem o aviso de demonstração", async () => {
  await irPara("#/integracao");

  assert.equal($(".demo-banner"), null);
  assert.ok($("#tela-api"));
  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/programas")));
});

test("programa do cadastro real abre pela API, com as abas Resumo, Plano e metas, Equipe, Turmas e Visão integrada", async () => {
  await irPara("#/programas/p-1/plano");

  assert.equal($(".demo-banner"), null);
  assert.ok($("#tela-api"));
  assert.equal($("#main h1").textContent, "Plano e metas");
  assert.deepEqual(
    [...document.querySelectorAll("#main .tabs a")].map((a) => a.getAttribute("href")),
    ["#/programas/p-1", "#/programas/p-1/plano", "#/programas/p-1/equipe", "#/turmas/p-1", "#/programas/p-1/integrada"],
  );
});

test("a aba Visão integrada de um programa real abre a tela da API já nesse programa", async () => {
  chamadas.length = 0;
  await irPara("#/programas/p-1/integrada");
  await esperar();

  assert.equal($(".demo-banner"), null);
  assert.equal($("#main h1").textContent, "Visão integrada");
  assert.equal($('#tela-api select[name="programa"]').value, "p-1");
  assert.ok(chamadas.some((c) => c.url.includes("/gestao/programas/p-1/visao-integrada")));
  assert.equal($("#main .tabs a.active").getAttribute("href"), "#/programas/p-1/integrada");
});

test("Novo programa abre o formulário ligado à API, com sugestões no Responsável", async () => {
  await irPara("#/programas/novo");

  assert.equal($(".demo-banner"), null);
  assert.ok($('#tela-api form [name="identificador"]'));
  assert.equal($('#tela-api [name="responsavel"]').getAttribute("list"), "f-programa-responsaveis");
});

test("Turmas carrega pela API por programa; turmas fictícias do protótipo seguem na demonstração", async () => {
  chamadas.length = 0;
  await irPara("#/turmas");
  await esperar();

  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/programas/p-1/turmas")));
  assert.equal($("#tela-api tbody a").textContent, "Oficina de arte");
  assert.match($("#tela-api tbody").textContent, /2 de 2.*Turma lotada.*1 na espera/);
  assert.equal($(".demo-banner"), null);

  await irPara("#/turmas/t1");
  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("Alertas e busca ativa carrega pela API; alertas fictícios do protótipo seguem na demonstração", async () => {
  chamadas.length = 0;
  await irPara("#/alertas");
  await esperar();

  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/alertas")));
  assert.equal($("#tela-api tbody a").textContent, "Lara Oliveira precisa de um contato");
  assert.match($("#tela-api tbody").textContent, /Semear.*3 faltas seguidas \(limite 3\)/);
  assert.equal($(".demo-banner"), null);

  chamadas.length = 0;
  await irPara("#/alertas/al-9");
  await esperar();
  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/alertas/al-9")));

  await irPara("#/alertas/al1");
  assert.ok($(".demo-banner"));
  assert.equal($("#tela-api"), null);
});

test("encontro registrado abre pela API, com a chamada (T-89)", async () => {
  chamadas.length = 0;
  await irPara("#/atividades/p-1/encontro/a-1");
  await esperar();

  assert.ok(chamadas.some((c) => c.url.endsWith("/gestao/programas/p-1/atividades/a-1")));
  assert.equal($("#main h1").textContent, "Encontro registrado");
  assert.equal($(".demo-banner"), null);
});

test("nenhuma tela do protótipo tem caixa dentro de caixa nem blocos encostados (T-00m)", async () => {
  const { problemasDeLayout } = await import("./ajuda-layout.js");
  const rotas = [
    "#/inicio", "#/programas/p1", "#/programas/p1/plano", "#/turmas", "#/turmas/t1", "#/pessoas/u1", "#/pessoas/u1/familia",
    "#/pessoas/u1/documentos", "#/atividades/a1", "#/alertas/al2", "#/atendimentos", "#/rede", "#/aprendizagem",
    "#/indicadores", "#/relatorios", "#/auditoria", "#/importacao", "#/sincronizacao", "#/guia", "#/mapa", "#/plataforma",
  ];
  const problemas = [];
  for (const rota of rotas) {
    await irPara(rota);
    for (const p of problemasDeLayout($("#main") || document.body)) problemas.push(`${rota}: ${p}`);
  }
  assert.deepEqual(problemas, []);
  await irPara("#/inicio");
});

test("seletor de módulo leva ao Financeiro e o logo ao menu inicial", () => {
  const financas = [...document.querySelectorAll(".lateral__modulos a")].find((a) => a.textContent === "Finanças");

  assert.equal(financas.getAttribute("href"), "../Financeiro/");
  assert.equal($(".lateral .lateral__marca").getAttribute("href"), "../");
});

test("trocar de perfil muda o menu e fica salvo neste aparelho", async () => {
  await irPara("#/inicio");
  assert.equal(menu().includes("Pessoas e famílias"), true);

  $('[data-action="persona:director"]').click();
  await esperar();

  assert.equal(localStorage.getItem("mdca.gestao.papel"), "director");
  assert.equal(menu().includes("Pessoas e famílias"), false);
  assert.equal(menu().includes("Visão integrada"), true);
});

test("rota fora do perfil mostra acesso restrito", async () => {
  await irPara("#/pessoas");

  assert.equal($("#main h1").textContent, "Acesso restrito");
});

test("Usuários e acessos fica restrito fora da administração, sem chamar a API", async () => {
  chamadas.length = 0;
  await irPara("#/usuarios");

  assert.equal($("#main h1").textContent, "Acesso restrito");
  assert.equal(chamadas.length, 0);
});

test("na administração, Usuários e acessos carrega pela API, sem o aviso de demonstração", async () => {
  await irPara("#/inicio");
  $('[data-action="persona:admin"]').click();
  await esperar();
  chamadas.length = 0;
  await irPara("#/usuarios");

  assert.equal(chamadas.at(-1).url.endsWith("/gestao/usuarios"), true);
  assert.equal($("#tela-api tbody strong").textContent, "Ana Martins");
  assert.equal($(".demo-banner"), null);
});
