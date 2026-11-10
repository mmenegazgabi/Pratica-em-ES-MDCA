// Avisos da equipe com os alertas reais (T-90 · US-06): o que entra nas notificações e na
// Visão geral, quem vê, e quando a lista é buscada de novo.
import { test } from "node:test";
import assert from "node:assert/strict";

const { comoAviso, criarAvisos } = await import("../base/avisos.js");

const alerta = (id, extra = {}) => ({
  id,
  titulo: `Alerta ${id}`,
  descricao: "3 faltas seguidas na turma Oficina de arte.",
  pessoa_id: "pe-lara",
  situacao: "aberto",
  faltas_consecutivas: 3,
  criado_em: "2026-11-05T18:00:00Z",
  ...extra,
});

function montar({ respostas = [[alerta("al-1")]], pode = true } = {}) {
  const estado = { pode, relogio: 0, buscas: 0, redesenhos: 0 };
  const fila = [...respostas];
  const avisos = criarAvisos({
    listar: async () => {
      estado.buscas += 1;
      const r = fila.length > 1 ? fila.shift() : fila[0];
      if (r instanceof Error) throw r;
      return r;
    },
    podeAcompanhar: () => estado.pode,
    aoMudar: () => (estado.redesenhos += 1),
    agora: () => estado.relogio,
    validade: 60000,
  });
  return { avisos, estado };
}

test("o alerta da API vira aviso com título, descrição e destino no acompanhamento", () => {
  assert.deepEqual(comoAviso(alerta("al-1")), {
    id: "al-1",
    title: "Alerta al-1",
    description: "3 faltas seguidas na turma Oficina de arte.",
    type: "Infrequência",
    status: "Em aberto",
    person: "pe-lara",
    date: "2026-11-05",
    link: "/alertas/al-1",
    origem: "api",
  });
});

test("busca os alertas abertos e redesenha uma vez quando chegam", async () => {
  const { avisos, estado } = montar();
  assert.deepEqual(avisos.abertos(), []);

  await avisos.atualizar({ perfil: "social" });

  assert.deepEqual(avisos.abertos().map((a) => a.link), ["/alertas/al-1"]);
  assert.equal(estado.redesenhos, 1);
  // Dentro da validade não busca de novo; a mesma lista não redesenha.
  await avisos.atualizar({ perfil: "social" });
  assert.equal(estado.buscas, 1);
  await avisos.atualizar({ perfil: "social", forcar: true });
  assert.equal(estado.buscas, 2);
  assert.equal(estado.redesenhos, 1);
});

test("o alerta encerrado sai dos avisos na próxima busca", async () => {
  const { avisos, estado } = montar({ respostas: [[alerta("al-1"), alerta("al-2")], [alerta("al-2")]] });
  await avisos.atualizar({ perfil: "social" });
  assert.equal(avisos.abertos().length, 2);

  estado.relogio = 60000;
  await avisos.atualizar({ perfil: "social" });

  assert.deepEqual(avisos.abertos().map((a) => a.id), ["al-2"]);
  assert.equal(estado.redesenhos, 2);
});

test("perfil que não acompanha alertas não chama a API nem vê avisos de infrequência", async () => {
  const { avisos, estado } = montar({ pode: false });

  await avisos.atualizar({ perfil: "educator" });

  assert.equal(estado.buscas, 0);
  assert.deepEqual(avisos.abertos(), []);
});

test("trocar para um perfil sem acompanhamento esconde os avisos que já estavam na tela", async () => {
  const { avisos, estado } = montar();
  await avisos.atualizar({ perfil: "social" });

  estado.pode = false;
  await avisos.atualizar({ perfil: "educator" });

  assert.deepEqual(avisos.abertos(), []);
  assert.equal(estado.redesenhos, 2);
});

test("sem conexão, mantém o que tinha e tenta de novo na próxima vez", async () => {
  const { avisos, estado } = montar({ respostas: [[alerta("al-1")], new Error("rede"), [alerta("al-1")]] });
  await avisos.atualizar({ perfil: "social" });

  estado.relogio = 60000;
  await avisos.atualizar({ perfil: "social" });
  assert.deepEqual(avisos.abertos().map((a) => a.id), ["al-1"]);

  await avisos.atualizar({ perfil: "social" });
  assert.equal(estado.buscas, 3);
});

test("trocar de perfil busca de novo, mesmo dentro da validade", async () => {
  const { avisos, estado } = montar();
  await avisos.atualizar({ perfil: "social" });
  await avisos.atualizar({ perfil: "coord" });
  assert.equal(estado.buscas, 2);
});
