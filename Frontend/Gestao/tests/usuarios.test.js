// Usuários e acessos (T-40): contas, perfis e programas pela API; só consulta (jsdom).
import { beforeEach, test } from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";

const dom = new JSDOM("<!DOCTYPE html><body></body>", { url: "http://localhost/Gestao/" });
Object.assign(globalThis, { window: dom.window, document: dom.window.document, localStorage: dom.window.localStorage });
const { ERROS, ErroApi } = await import("../base/api.js");
const { mostrarUsuarios } = await import("../telas/usuarios.js");

let container;
const texto = (no = container) => no.textContent.replace(/\s+/g, " ").trim();
// Nome e id ficam em elementos separados (<strong> e <small>): um espaço entre eles.
const celula = (td) => [...td.childNodes].map((n) => n.textContent).join(" ").replace(/\s+/g, " ").trim();

beforeEach(() => {
  container?.remove();
  container = document.createElement("div");
  document.body.append(container);
});

const USUARIOS = [
  {
    id: "admin",
    nome: "Administração",
    email: "admin@mdca.org",
    ativo: true,
    papeis: [{ id: "administracao", nome: "Administração do sistema" }],
    vinculos: [],
  },
  {
    id: "jessica",
    nome: "Jéssica Almeida",
    email: null,
    ativo: true,
    papeis: [],
    vinculos: [
      { programa_id: "p-2", programa: "Oficina", papel_id: "educador", papel: "Educador(a) social" },
      { programa_id: "p-1", programa: "Semear", papel_id: "educador", papel: "Educador(a) social" },
    ],
  },
  { id: "inativo", nome: "Conta Antiga", email: null, ativo: false, papeis: [], vinculos: [] },
];

test("mostra cada conta com perfis da plataforma, programas e situação", async () => {
  await mostrarUsuarios(container, { buscar: async () => USUARIOS });

  const linhas = [...container.querySelectorAll("tbody tr")].map((tr) => [...tr.cells].map(celula));
  assert.deepEqual(linhas, [
    ["Administração admin · admin@mdca.org", "Administração do sistema", "Sem vínculo ativo", "Ativo"],
    ["Jéssica Almeida jessica", "—", "Oficina · Educador(a) social Semear · Educador(a) social", "Ativo"],
    ["Conta Antiga inativo", "—", "Sem vínculo ativo", "Desativado"],
  ]);
});

test("é só consulta: não oferece criar nem editar contas", async () => {
  await mostrarUsuarios(container, { buscar: async () => USUARIOS });

  assert.equal(container.querySelector("button"), null);
  assert.match(texto(), /ainda não estão disponíveis/);
});

test("nome vindo da API entra como texto, nunca como HTML", async () => {
  await mostrarUsuarios(container, { buscar: async () => [{ ...USUARIOS[2], nome: '<img src=x onerror="alert(1)">' }] });

  assert.equal(container.querySelector("img"), null);
});

test("sem usuários mostra o estado vazio", async () => {
  await mostrarUsuarios(container, { buscar: async () => [] });

  assert.match(texto(), /Nenhum usuário cadastrado/);
  assert.equal(container.querySelector("table"), null);
});

test("perfil sem permissão (403) vê a tela de acesso restrito", async () => {
  await mostrarUsuarios(container, {
    buscar: async () => Promise.reject(new ErroApi(ERROS.SEM_PERMISSAO, 403, "Seu perfil não tem acesso à lista de usuários.")),
  });

  assert.match(texto(), /Acesso restrito/);
  assert.equal(container.querySelector("table"), null);
});
