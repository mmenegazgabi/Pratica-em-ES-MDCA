// Conciliação, Relatórios, Auditoria e categorias com limite: regras sem DOM.
import { describe, test } from "node:test";
import assert from "node:assert/strict";

import { aprovadosEmAberto, diasEmAberto, mensagemDaImportacao, mesmoValor, valorDoExtrato, valoresDiferentes } from "../telas/conciliacao-dados.js";
import { lancamentosDoPeriodo, nomePadraoDoRelatorio, resumoDoPeriodo, validarPeriodo } from "../telas/relatorios-dados.js";
import { TAMANHO_DA_PAGINA, filtrarNaPagina, filtrosDaAuditoria, formatarOcorrido, paginacao } from "../telas/auditoria-dados.js";
import { categoriasDoOrcamento } from "../telas/projetos-dados.js";

const AGORA = new Date("2026-10-27T15:00:00Z");

describe("conciliação", () => {
  // No extrato do banco, saída é valor negativo.
  const extrato = [
    { id: "E1", valor: -180, descricao: "PIX PAPELARIA" },
    { id: "E2", valor: -0.3, descricao: "TARIFA" },
  ];
  const lancamentos = [
    { id: "a", status: "aprovado", conciliado: false, valor: 180, aprovado_em: "2026-10-26T10:00:00Z" },
    { id: "b", status: "aprovado", conciliado: false, valor: 0.1 + 0.2, aprovado_em: "2026-10-10T10:00:00Z" },
    { id: "c", status: "aprovado", conciliado: true, referencia_extrato: "E9", valor: 50, aprovado_em: "2026-10-01T10:00:00Z" },
    { id: "d", status: "pendente", conciliado: false, valor: 180 },
  ];

  test("valor do extrato: saída com sinal de menos, entrada com mais", () => {
    assert.match(valorDoExtrato(-180), /^−R\$\s180,00$/);
    assert.match(valorDoExtrato(50), /^\+R\$\s50,00$/);
  });

  test("mensagem da importação no singular e no plural", () => {
    assert.equal(mensagemDaImportacao({ importados: 3, ignorados_repetidos: 2 }), "3 itens importados, 2 repetidos ignorados.");
    assert.equal(mensagemDaImportacao({ importados: 1, ignorados_repetidos: 1 }), "1 item importado, 1 repetido ignorado.");
    assert.equal(mensagemDaImportacao({ importados: 0, ignorados_repetidos: 0 }), "0 itens importados, 0 repetidos ignorados.");
  });

  test("aprovados em aberto: só aprovados não conciliados, mais antigos primeiro", () => {
    assert.deepEqual(aprovadosEmAberto(lancamentos).map((l) => l.id), ["b", "a"]);
  });

  test("mesmo valor compara em centavos", () => {
    const abertos = aprovadosEmAberto(lancamentos);
    assert.deepEqual(mesmoValor(extrato[0], abertos), ["a"]);
    assert.deepEqual(mesmoValor(extrato[1], abertos), ["b"]);
    assert.deepEqual(mesmoValor(null, abertos), []);
  });

  test("dias em aberto só aparece depois de 7 dias", () => {
    assert.equal(diasEmAberto(lancamentos[1], AGORA), 17);
    assert.equal(diasEmAberto(lancamentos[0], AGORA), null);
    assert.equal(diasEmAberto({ aprovado_em: null }, AGORA), null);
  });

  test("valores diferentes (o extrato compara sem o sinal)", () => {
    assert.equal(valoresDiferentes(extrato[0], lancamentos[0]), false);
    assert.equal(valoresDiferentes(extrato[0], lancamentos[1]), true);
    assert.equal(valoresDiferentes({ valor: 180 }, lancamentos[0]), false);
  });
});

describe("relatórios", () => {
  const orcamento = { projeto_nome: "Esporte; Base", valor_total: 10000, saldo: 1500 };
  const lancamentos = [
    { status: "aprovado", data_despesa: "2026-09-02", categoria: "Transporte", descricao: "Van", valor: 650, conciliado: true },
    { status: "aprovado", data_despesa: "2026-07-03", categoria: "Uniformes", descricao: 'Camisetas "sub-12"', valor: 1240.1, conciliado: false },
    { status: "pendente", data_despesa: "2026-08-01", categoria: "Lanche", descricao: "x", valor: 10, conciliado: false },
    { status: "aprovado", data_despesa: "2026-10-01", categoria: "Lanche", descricao: "fora", valor: 99, conciliado: false },
  ];

  test("período: só aprovados entre as datas, em ordem", () => {
    const doPeriodo = lancamentosDoPeriodo(lancamentos, "2026-07-01", "2026-09-30");
    assert.deepEqual(doPeriodo.map((l) => l.descricao), ['Camisetas "sub-12"', "Van"]);
    assert.deepEqual(resumoDoPeriodo(orcamento, doPeriodo), { orcado: 10000, executado: 1890.1, saldo: 1500, naoConciliados: 1 });
  });

  test("validar período", () => {
    assert.equal(validarPeriodo("", "2026-01-01"), "Informe o início e o fim do período.");
    assert.equal(validarPeriodo("2026-02-01", "2026-01-01"), "O fim do período não pode ser antes do início.");
    assert.equal(validarPeriodo("2026-01-01", "2026-01-01"), null);
  });

  test("nome padrão do arquivo quando a API não manda o Content-Disposition", () => {
    assert.equal(nomePadraoDoRelatorio(orcamento, "2026-07-01", "2026-09-30", "pdf"), "prestacao-de-contas-esporte-base-2026-07-01-a-2026-09-30.pdf");
    assert.equal(nomePadraoDoRelatorio({ projeto_id: "p1" }, "2026-07-01", "2026-09-30", "xlsx"), "prestacao-de-contas-p1-2026-07-01-a-2026-09-30.xlsx");
    assert.equal(nomePadraoDoRelatorio({ projeto_nome: "Ação & Música" }, "2026-01-01", "2026-01-31", "pdf"), "prestacao-de-contas-acao-musica-2026-01-01-a-2026-01-31.pdf");
  });
});

describe("auditoria", () => {
  test("filtros: período e página, sempre 50 por página; vazio fica de fora", () => {
    assert.deepEqual(filtrosDaAuditoria({ desde: "2026-10-01", ate: "2026-10-31", pagina: 2 }), {
      filtros: { pagina: 2, tamanho: 50, desde: "2026-10-01", ate: "2026-10-31" },
      erro: null,
    });
    assert.deepEqual(filtrosDaAuditoria({ desde: "", ate: "" }), { filtros: { pagina: 1, tamanho: 50 }, erro: null });
    assert.deepEqual(filtrosDaAuditoria({ pagina: 0 }).filtros.pagina, 1);
    assert.equal(TAMANHO_DA_PAGINA, 50);
  });

  test("filtros: período invertido não vai para a API", () => {
    assert.deepEqual(filtrosDaAuditoria({ desde: "2026-10-31", ate: "2026-10-01" }), { filtros: null, erro: "A data inicial não pode ser depois da final." });
  });

  test("data e hora no horário de Brasília", () => {
    assert.equal(formatarOcorrido("2026-10-05T12:00:00Z"), "05/10/2026 09:00");
    assert.equal(formatarOcorrido("2026-10-05T01:30:00+00:00"), "04/10/2026 22:30");
    assert.equal(formatarOcorrido(null), "—");
  });

  test("busca na página: pessoa, ação ou descrição, sem acento nem maiúsculas", () => {
    const itens = [
      { quem: "Luana Ferraz", acao: "Aprovou despesa", alvo: "Materiais · R$ 180,00 · Leitura", detalhes: { segredo: "luana" } },
      { quem: "vera", acao: "Importou extrato bancário", alvo: "2 itens novos" },
      { quem: null, acao: "Acesso negado", alvo: null },
    ];
    assert.equal(filtrarNaPagina(itens, ""), itens);
    assert.deepEqual(filtrarNaPagina(itens, "  LUANA "), [itens[0]]);
    assert.deepEqual(filtrarNaPagina(itens, "bancario"), [itens[1]]);
    assert.deepEqual(filtrarNaPagina(itens, "leitura"), [itens[0]]);
    assert.deepEqual(filtrarNaPagina(itens, "negado"), [itens[2]]);
    assert.deepEqual(filtrarNaPagina(itens, "segredo"), [], "detalhes não entram na busca");
  });

  test("paginação: total de eventos e limites", () => {
    assert.deepEqual(paginacao({ total: 0, pagina: 1, tamanho: 50 }), { total: "0 eventos", pagina: "Página 1 de 1", temAnterior: false, temProxima: false });
    assert.deepEqual(paginacao({ total: 1, pagina: 1, tamanho: 50 }), { total: "1 evento", pagina: "Página 1 de 1", temAnterior: false, temProxima: false });
    assert.deepEqual(paginacao({ total: 120, pagina: 2, tamanho: 50 }), { total: "120 eventos", pagina: "Página 2 de 3", temAnterior: true, temProxima: true });
    assert.deepEqual(paginacao({ total: 120, pagina: 3, tamanho: 50 }).temProxima, false);
  });
});

describe("categorias do orçamento", () => {
  test("com valor por categoria (US-01) usa limite, percentual e alerta do backend", () => {
    const orcamento = {
      categorias_despesa: ["Uniformes", "Lanche"],
      categorias: [
        { nome: "Uniformes", valor_orcado: 4000, realizado: 3840, percentual_consumido: 96, nivel_alerta: "atencao" },
        { nome: "Lanche", valor_orcado: null, realizado: 0, percentual_consumido: null, nivel_alerta: null },
      ],
    };
    assert.deepEqual(categoriasDoOrcamento(orcamento, []), [
      { categoria: "Uniformes", gasto: 3840, limite: 4000, percentual: 96, nivel: "atencao" },
      { categoria: "Lanche", gasto: 0, limite: null, percentual: null, nivel: null },
    ]);
  });

  test("sem categorias detalhadas, cai no gasto dos aprovados", () => {
    const orcamento = { id: "o1", categorias_despesa: ["A"] };
    const lancamentos = [{ orcamento_id: "o1", status: "aprovado", categoria: "A", valor: 10 }];
    assert.deepEqual(categoriasDoOrcamento(orcamento, lancamentos), [{ categoria: "A", gasto: 10, limite: null, percentual: null, nivel: null }]);
  });
});
