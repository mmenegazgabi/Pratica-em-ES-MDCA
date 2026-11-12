// Painel e Auditoria: regras sem DOM.
import test, { describe } from "node:test";
import assert from "node:assert/strict";
import { formatarData } from "../base/formatar.js";
import {
  descreverFiltros,
  filtrosDaApi,
  filtrosDaRota,
  mensagemSemProjetos,
  ordenar,
  percentualExecutado,
  totais,
  validarPeriodo,
} from "../telas/painel-dados.js";
import { filtrarAuditoria, formatarQuando, filtrosDaApi as filtrosDaAuditoria, intervaloDaPagina, ultimaPagina } from "../telas/auditoria-dados.js";

describe("painel", () => {
  test("filtros da tela viram parâmetros da API; 'todos' e vazios ficam de fora", () => {
    assert.deepEqual(filtrosDaApi({ inicio: "", fim: "", situacao: "todos" }), { data_inicio: "", data_fim: "", status: "" });
    assert.deepEqual(filtrosDaApi({ inicio: "2026-03-01", fim: "2026-03-31", situacao: "ativo" }), {
      data_inicio: "2026-03-01",
      data_fim: "2026-03-31",
      status: "ativo",
    });
  });

  test("filtros da rota: datas e situação válidas passam, o resto vira padrão", () => {
    assert.deepEqual(filtrosDaRota({ inicio: "2026-01-01", situacao: "encerrado" }), { inicio: "2026-01-01", fim: "", situacao: "encerrado" });
    assert.deepEqual(filtrosDaRota({ inicio: "01/01/2026", fim: "x", situacao: "todos-mesmo" }), { inicio: "", fim: "", situacao: "todos" });
    assert.deepEqual(filtrosDaRota(), { inicio: "", fim: "", situacao: "todos" });
  });

  test("período: só recusa fim antes do início; uma ponta só vale", () => {
    assert.equal(validarPeriodo("", ""), "");
    assert.equal(validarPeriodo("2026-01-01", ""), "");
    assert.equal(validarPeriodo("", "2026-01-01"), "");
    assert.equal(validarPeriodo("2026-01-01", "2026-01-01"), "");
    assert.match(validarPeriodo("2026-02-01", "2026-01-01"), /não pode ser antes/);
  });

  test("totais em centavos e percentual executado", () => {
    const r = [
      { orcado: 0.1, realizado: 0.2, saldo: -0.1 },
      { orcado: 0.2, realizado: 0.1, saldo: 0.1 },
    ];
    assert.deepEqual(totais(r), { orcado: 0.3, realizado: 0.3, saldo: 0 });
    assert.equal(percentualExecutado({ orcado: 200, realizado: 50 }), 25);
    assert.equal(percentualExecutado({ orcado: 0, realizado: 50 }), null);
  });

  test("ordem por nome e textos do filtro", () => {
    assert.deepEqual(ordenar([{ nome: "Oficina" }, { nome: "Adolescer" }, { nome: "Ébano" }]).map((p) => p.nome), ["Adolescer", "Ébano", "Oficina"]);
    assert.equal(descreverFiltros({ inicio: "", fim: "", situacao: "todos" }, formatarData), "Todos os projetos · todo o período");
    assert.equal(descreverFiltros({ inicio: "2026-03-01", fim: "2026-03-31", situacao: "ativo" }, formatarData), "Projetos ativos · de 01/03/2026 a 31/03/2026");
    assert.equal(descreverFiltros({ inicio: "", fim: "2026-03-31", situacao: "encerrado" }, formatarData), "Projetos encerrados · até 31/03/2026");
    assert.equal(mensagemSemProjetos("ativo"), "Nenhum projeto ativo.");
    assert.equal(mensagemSemProjetos("todos"), "Nenhum projeto cadastrado ainda.");
  });
});

describe("auditoria", () => {
  test("filtrar por texto em quem, ação e detalhe (campos vazios não quebram)", () => {
    const registros = [
      { quem: "Luana", acao: "Aprovou despesa", alvo: "Leitura" },
      { quem: "Lucas", acao: "Conciliou lançamento", alvo: null },
    ];
    assert.equal(filtrarAuditoria(registros, "  ").length, 2);
    assert.deepEqual(filtrarAuditoria(registros, "concil").map((r) => r.quem), ["Lucas"]);
    assert.deepEqual(filtrarAuditoria(registros, "LEITURA").map((r) => r.quem), ["Luana"]);
  });

  test("horário em Brasília, inclusive na virada do dia em UTC", () => {
    assert.equal(formatarQuando("2026-11-11T21:06:00+00:00"), "11/11/2026 18:06");
    assert.equal(formatarQuando("2026-11-12T01:30:00Z"), "11/11/2026 22:30");
    assert.equal(formatarQuando("não é data"), "não é data");
  });

  test("parâmetros, intervalo e última página", () => {
    assert.deepEqual(filtrosDaAuditoria({ desde: "", ate: "2026-11-11", pagina: 2 }), { desde: "", ate: "2026-11-11", pagina: 2, tamanho: 50 });
    assert.equal(intervaloDaPagina(1, 50, 0), "Nenhum registro");
    assert.equal(intervaloDaPagina(1, 50, 3), "1–3 de 3");
    assert.equal(intervaloDaPagina(3, 50, 120), "101–120 de 120");
    assert.equal(ultimaPagina(50, 120), 3);
    assert.equal(ultimaPagina(50, 0), 1);
  });
});
