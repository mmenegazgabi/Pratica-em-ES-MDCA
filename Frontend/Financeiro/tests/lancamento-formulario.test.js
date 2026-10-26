// T-13 · US-03 — Regras do formulário de lançamento no celular.
// Rodar em Frontend/Financeiro:  node --test

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  TAMANHO_MAXIMO_BYTES,
  converterValor,
  deveComprimir,
  dimensoesReduzidas,
  ehArquivoAceito,
  hojeISO,
  mensagemDeErro,
  montarFormData,
  validarFormulario,
} from "../lancamento/formulario.js";

const ORCAMENTO = {
  id: "orc-1",
  projeto_id: "semear",
  categorias_despesa: ["alimentacao", "transporte"],
  data_inicio: "2026-01-01",
  data_fim: "2026-12-31",
};

function arquivo({ nome = "nota.jpg", tipo = "image/jpeg", tamanho = 1000 } = {}) {
  return new File([new Uint8Array(tamanho)], nome, { type: tipo });
}

function dadosValidos(extra = {}) {
  return {
    orcamento: ORCAMENTO,
    categoria: "alimentacao",
    valor: "486,90",
    data: "2026-10-12",
    descricao: "Lanche da oficina",
    arquivo: arquivo(),
    ...extra,
  };
}

describe("valor digitado no celular", () => {
  for (const [texto, esperado] of [
    ["486,90", 486.9],
    ["486.90", 486.9],
    ["R$ 1.234,56", 1234.56],
    ["1.234", 1234],
    ["10", 10],
    [" 7,5 ", 7.5],
  ]) {
    test(`"${texto}" vira ${esperado}`, () => assert.equal(converterValor(texto), esperado));
  }

  for (const texto of ["", "abc", "1,234", "10,999", "1.2.3", "-5"]) {
    test(`"${texto}" é inválido`, () => assert.equal(converterValor(texto), null));
  }
});

describe("campos obrigatórios (projeto, categoria, valor, data, descrição, comprovante)", () => {
  test("formulário completo não tem erro", () => {
    assert.deepEqual(validarFormulario(dadosValidos()), {});
  });

  test("formulário vazio aponta erro em todos os campos obrigatórios", () => {
    const erros = validarFormulario({});
    assert.deepEqual(Object.keys(erros).sort(), ["categoria", "comprovante", "data", "descricao", "projeto", "valor"]);
  });

  test("valor zero é recusado", () => {
    assert.match(validarFormulario(dadosValidos({ valor: "0,00" })).valor, /maior que zero/);
  });

  test("categoria de outro projeto é recusada", () => {
    assert.ok(validarFormulario(dadosValidos({ categoria: "aluguel" })).categoria);
  });

  test("data fora da vigência é recusada", () => {
    assert.match(validarFormulario(dadosValidos({ data: "2025-12-31" })).data, /vigência/);
  });

  test("descrição só com espaços é recusada", () => {
    assert.ok(validarFormulario(dadosValidos({ descricao: "   " })).descricao);
  });
});

describe("comprovante (foto ou PDF, até 5 MB)", () => {
  for (const [nome, tipo] of [
    ["foto.jpg", "image/jpeg"],
    ["foto.png", "image/png"],
    ["foto.webp", "image/webp"],
    ["foto.heic", "image/heic"],
    ["foto.heic", ""], // alguns celulares mandam HEIC sem tipo
    ["nota.pdf", "application/pdf"],
  ]) {
    test(`aceita ${nome} (${tipo || "sem tipo"})`, () => assert.ok(ehArquivoAceito(arquivo({ nome, tipo }))));
  }

  test("recusa outros tipos", () => {
    const erros = validarFormulario(dadosValidos({ arquivo: arquivo({ nome: "nota.docx", tipo: "application/msword" }) }));
    assert.match(erros.comprovante, /foto|PDF/);
  });

  test("recusa arquivo acima de 5 MB", () => {
    const grande = arquivo({ tamanho: TAMANHO_MAXIMO_BYTES + 1 });
    assert.match(validarFormulario(dadosValidos({ arquivo: grande })).comprovante, /5 MB/);
  });

  test("sem comprovante é erro", () => {
    assert.ok(validarFormulario(dadosValidos({ arquivo: null })).comprovante);
  });

  test("fotos grandes são reduzidas antes do envio; PDF e HEIC não", () => {
    assert.equal(deveComprimir(arquivo({ tamanho: 3 * 1024 * 1024 })), true);
    assert.equal(deveComprimir(arquivo({ tamanho: 500 * 1024 })), false);
    assert.equal(deveComprimir(arquivo({ nome: "n.pdf", tipo: "application/pdf", tamanho: 3 * 1024 * 1024 })), false);
    assert.equal(deveComprimir(arquivo({ nome: "f.heic", tipo: "image/heic", tamanho: 3 * 1024 * 1024 })), false);
  });

  test("redução mantém a proporção com o maior lado em 1600 px", () => {
    assert.deepEqual(dimensoesReduzidas(4032, 3024), { largura: 1600, altura: 1200 });
    assert.deepEqual(dimensoesReduzidas(3024, 4032), { largura: 1200, altura: 1600 });
    assert.deepEqual(dimensoesReduzidas(800, 600), { largura: 800, altura: 600 });
  });
});

describe("envio para o POST /lancamentos", () => {
  test("monta o multipart com os nomes de campo da API", () => {
    const dados = montarFormData(dadosValidos({ descricao: "  Lanche  " }));

    assert.equal(dados.get("orcamento_id"), "orc-1");
    assert.equal(dados.get("valor"), "486.90");
    assert.equal(dados.get("descricao"), "Lanche");
    assert.equal(dados.get("categoria"), "alimentacao");
    assert.equal(dados.get("data_despesa"), "2026-10-12");
    assert.equal(dados.get("comprovante").name, "nota.jpg");
  });

  test("mensagens de erro da API viram texto para o educador", () => {
    assert.match(mensagemDeErro(0, null), /conexão/);
    assert.match(mensagemDeErro(401, null), /código de acesso/);
    assert.match(mensagemDeErro(413, null), /5 MB/);
    assert.equal(mensagemDeErro(400, { detail: "Comprovante obrigatório." }), "Comprovante obrigatório.");
  });

  test("data de hoje sai no formato AAAA-MM-DD", () => {
    assert.match(hojeISO(new Date(2026, 9, 26, 22, 30)), /^2026-10-26$/);
  });
});
