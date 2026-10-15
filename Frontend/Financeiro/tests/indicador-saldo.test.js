// T-09 · US-02 — Testes das três faixas de cor do indicador de saldo.
// Rodar em Frontend/Financeiro:  node --test   (Node 18+, sem dependências)

import { test, describe } from "node:test";
import assert from "node:assert/strict";

import {
  CORES,
  criarIndicadorSaldo,
  estadoIndicador,
} from "../componentes/indicador-saldo.js";

// Formato igual ao que a API devolve em GET /orcamentos/{id} (valor_total 1000).
function orcamento(percentual, nivel) {
  return {
    valor_total: 1000,
    saldo: 1000 - percentual * 10,
    realizado: percentual * 10,
    percentual_consumido: percentual,
    nivel_alerta: nivel,
  };
}

// DOM mínimo para testar o componente fora do navegador.
function criarDocumentoFalso() {
  const criar = (tag) => {
    const props = new Map();
    const node = {
      tag,
      className: "",
      textContent: "",
      dataset: {},
      atributos: {},
      filhos: [],
      style: {
        setProperty: (nome, valor) => props.set(nome, valor),
        getPropertyValue: (nome) => props.get(nome) ?? "",
      },
      setAttribute(nome, valor) { this.atributos[nome] = valor; },
      append(...nos) { this.filhos.push(...nos); },
    };
    return node;
  };
  return { createElement: criar };
}

function buscarPorClasse(no, classe) {
  if (no.className?.split(" ").includes(classe)) return no;
  for (const filho of no.filhos ?? []) {
    const achado = buscarPorClasse(filho, classe);
    if (achado) return achado;
  }
  return null;
}

const FAIXAS_DE_TESTE = [
  {
    nome: "faixa < 80% → cor neutra (verde)",
    cor: CORES.neutra,
    hex: "#6aba60",
    casos: [orcamento(0, "normal"), orcamento(50, "normal"), orcamento(79.99, "normal")],
  },
  {
    nome: "faixa 80–99% → cor de alerta (amarelo)",
    cor: CORES.alerta,
    hex: "#fde118",
    casos: [orcamento(80, "atencao"), orcamento(90, "atencao"), orcamento(99.99, "atencao")],
  },
  {
    nome: "faixa ≥ 100% → cor crítica (vermelho)",
    cor: CORES.critica,
    hex: "#f02d34",
    casos: [orcamento(100, "estourado"), orcamento(120, "estourado")],
  },
];

for (const faixa of FAIXAS_DE_TESTE) {
  describe(faixa.nome, () => {
    for (const caso of faixa.casos) {
      const rotulo = `${caso.percentual_consumido}% consumido`;

      test(`${rotulo}: estado usa a cor ${faixa.cor.nome}`, () => {
        const estado = estadoIndicador(caso);

        assert.equal(estado.cor.nome, faixa.cor.nome);
        assert.ok(estado.cor.valor.includes(faixa.hex), `esperava ${faixa.hex} em ${estado.cor.valor}`);
      });

      test(`${rotulo}: componente pinta a barra com a cor ${faixa.cor.nome}`, () => {
        const indicador = criarIndicadorSaldo(caso, criarDocumentoFalso());

        assert.equal(indicador.dataset.cor, faixa.cor.nome);
        assert.equal(indicador.style.getPropertyValue("--indicador-cor"), faixa.cor.valor);
        assert.ok(indicador.className.includes(`indicador-saldo--${caso.nivel_alerta}`));
      });
    }
  });
}

describe("detalhes do componente", () => {
  test("as três faixas têm cores diferentes", () => {
    const valores = new Set([CORES.neutra.valor, CORES.alerta.valor, CORES.critica.valor]);
    assert.equal(valores.size, 3);
  });

  test("nível desconhecido ou ausente cai na cor neutra", () => {
    assert.equal(estadoIndicador({ saldo: 0, percentual_consumido: 10 }).cor.nome, "neutra");
    assert.equal(estadoIndicador({ saldo: 0, percentual_consumido: 10, nivel_alerta: "xyz" }).cor.nome, "neutra");
  });

  test("79,99% não é exibido como 80%", () => {
    const estado = estadoIndicador(orcamento(79.99, "normal"));
    assert.equal(estado.percentualTexto, "79,99% consumido");
  });

  test("barra é limitada a 100% mesmo quando o consumo passa disso", () => {
    const estado = estadoIndicador(orcamento(120, "estourado"));
    assert.equal(estado.larguraBarra, "100%");
  });

  test("alerta tem texto além da cor (acessibilidade)", () => {
    const indicador = criarIndicadorSaldo(orcamento(90, "atencao"), criarDocumentoFalso());
    const rotulo = buscarPorClasse(indicador, "indicador-saldo__rotulo");
    assert.match(rotulo.textContent, /Atenção/);
  });
});
