// Início · "O que precisa de você": pendências por papel (sem DOM).
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import { montarPendencias } from "../telas/inicio-dados.js";

const AGORA = new Date("2026-10-27T15:00:00Z");

const orcamentos = [
  { id: "o1", projeto_id: "p1", projeto_nome: "Esporte", valor_total: 10000, saldo: 1500, realizado: 8500, percentual_consumido: 85, nivel_alerta: "atencao", data_fim: "2026-12-31" },
  { id: "o2", projeto_id: "p2", projeto_nome: "Leitura", valor_total: 10000, saldo: 3800, realizado: 6200, percentual_consumido: 62, nivel_alerta: "normal", data_fim: "2026-12-31" },
  { id: "o3", projeto_id: "p3", projeto_nome: "Música", valor_total: 1000, saldo: -50, realizado: 1050, percentual_consumido: 105, nivel_alerta: "estourado", data_fim: "2026-11-30" },
];

const lancamentos = [
  { id: "l1", orcamento_id: "o2", projeto_id: "p2", valor: 180, categoria: "Materiais", autor_id: "marcos-vieira", status: "pendente", conciliado: false, criado_em: "2026-10-26T12:00:00Z" },
  { id: "l2", orcamento_id: "o1", projeto_id: "p1", valor: 92.5, categoria: "Alimentação", status: "pendente", conciliado: false, criado_em: "2026-10-27T10:00:00Z" },
  { id: "l3", orcamento_id: "o2", projeto_id: "p2", valor: 45, categoria: "Transporte", status: "aprovado", conciliado: false, criado_em: "2026-10-10T10:00:00Z", aprovado_em: "2026-10-19T10:00:00Z" },
  { id: "l4", orcamento_id: "o1", projeto_id: "p1", valor: 30, categoria: "Materiais", status: "aprovado", conciliado: true, criado_em: "2026-10-01T10:00:00Z", aprovado_em: "2026-10-02T10:00:00Z" },
  { id: "l5", orcamento_id: "o1", projeto_id: "p1", valor: 20, categoria: "Materiais", status: "aprovado", conciliado: false, criado_em: "2026-10-25T10:00:00Z", aprovado_em: "2026-10-25T12:00:00Z" },
];

const dados = { lancamentos, orcamentos };

describe("montarPendencias", () => {
  test("coordenação: aprovações pendentes (mais antigas primeiro) e alertas", () => {
    const r = montarPendencias("coordenacao", dados, AGORA);
    assert.deepEqual(r.secoes.map((s) => s.titulo), ["Despesas aguardando aprovação", "Alertas de orçamento"]);
    const [aprov, alertas] = r.secoes;
    assert.equal(aprov.itens.length, 2);
    assert.equal(aprov.itens[0].rotulo, "Materiais · Marcos Vieira");
    assert.equal(aprov.itens[1].rotulo, "Alimentação");
    assert.equal(aprov.itens[0].detalhe, "Projeto Leitura · enviada há 1 dia");
    assert.equal(aprov.itens[0].valor, 180);
    assert.deepEqual(aprov.itens[0].acao, { rotulo: "Analisar", rota: "#/lancamentos?status=pendente&abrir=l1" });
    assert.equal(aprov.itens[1].detalhe, "Projeto Esporte · enviada hoje");
    assert.equal(alertas.itens.length, 2);
    assert.equal(alertas.itens[0].rotulo, "Esporte passou de 80% do orçamento");
    assert.match(alertas.itens[0].detalhe, /^Restam R\$\s1\.500,00 até 31\/12\/2026$/);
    assert.equal(alertas.itens[0].nivel, "atencao");
    assert.equal(alertas.itens[0].valor, 85);
    assert.deepEqual(alertas.itens[0].acao, { rotulo: "Ver projeto", rota: "#/projetos/o1" });
    assert.equal(alertas.itens[1].rotulo, "Música estourou o orçamento");
    assert.equal(alertas.itens[1].nivel, "estourado");
    assert.equal(r.total, 4);
  });

  test("direção: só alertas de orçamento", () => {
    const r = montarPendencias("direcao", dados, AGORA);
    assert.deepEqual(r.secoes.map((s) => s.titulo), ["Alertas de orçamento"]);
    assert.equal(r.total, 2);
  });

  test("voluntário financeiro: aprovados sem conciliação", () => {
    const r = montarPendencias("voluntario_financeiro", dados, AGORA);
    assert.deepEqual(r.secoes.map((s) => s.titulo), ["Aprovados sem conciliação"]);
    const [i1, i2] = r.secoes[0].itens;
    assert.equal(r.total, 2);
    assert.equal(i1.acao.rota, "#/lancamentos?status=aprovado&abrir=l3");
    assert.equal(i1.acao.rotulo, "Ver");
    assert.equal(i2.detalhe, "Projeto Esporte");
  });

  test("aprovado há 8 dias mostra 'aberto há 8 dias'", () => {
    const r = montarPendencias("voluntario_financeiro", dados, AGORA);
    assert.equal(r.secoes[0].itens[0].detalhe, "Projeto Leitura · aberto há 8 dias");
  });

  test("sem pendências: total 0 e nenhuma seção", () => {
    const r = montarPendencias("coordenacao", { lancamentos: [], orcamentos: [] }, AGORA);
    assert.deepEqual(r, { total: 0, secoes: [] });
  });

  test("voluntário: rótulo com autor quando há autor_id", () => {
    const com = { ...lancamentos[2], autor_id: "ana-souza" };
    const r = montarPendencias("voluntario_financeiro", { lancamentos: [com], orcamentos }, AGORA);
    assert.equal(r.secoes[0].itens[0].rotulo, "Transporte · Ana Souza");
  });

  test("sem nome de projeto no orçamento, usa o projeto_id", () => {
    const r = montarPendencias("coordenacao", { lancamentos: [lancamentos[0]], orcamentos: [] }, AGORA);
    assert.equal(r.secoes[0].itens[0].detalhe, "Projeto p2 · enviada há 1 dia");
  });
});
