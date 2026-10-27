// T-14 · US-03 — Testes da TELA de lançamento (formulário de verdade).
//
// Carrega Frontend/Financeiro/lancamento/index.html + lancamento.js num
// navegador simulado (jsdom), com a API simulada, e clica em
// "Enviar para aprovação" como o educador faria.
//
// Rodar em Frontend/Financeiro:  npm install  (uma vez)  e  node --test

import { describe, test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

let JSDOM = null;
try {
  ({ JSDOM } = await import("jsdom"));
} catch {
  /* sem jsdom: os testes abaixo são pulados com aviso */
}
const SEM_JSDOM = JSDOM ? false : "jsdom não instalado — rode `npm install` em Frontend/Financeiro";

const HTML = await readFile(new URL("../lancamento/index.html", import.meta.url), "utf8");
const API = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

const ORCAMENTO = {
  id: "orc-semear",
  projeto_id: "semear-contraturno",
  valor_total: 15000,
  data_inicio: "2026-01-01",
  data_fim: "2026-12-31",
  categorias_despesa: ["alimentacao", "transporte"],
  saldo: 15000,
};

const RESPOSTA_CRIADO = {
  status: 201,
  corpo: {
    id: "lanc-1",
    orcamento_id: "orc-semear",
    valor: 486.9,
    descricao: "Lanche da oficina",
    categoria: "alimentacao",
    data_despesa: "2026-10-12",
    status: "pendente",
    status_descricao: "Pendente de aprovação",
    comprovante: { chave: "comprovantes/2026/10/x.jpg", url: "/comprovantes/2026/10/x.jpg", nome_original: "nota.jpg" },
  },
};

let versao = 0;

async function esperar(condicao, descricao = "condição", limiteMs = 2000) {
  const inicio = Date.now();
  while (!condicao()) {
    if (Date.now() - inicio > limiteMs) throw new Error(`Tempo esgotado esperando: ${descricao}`);
    await new Promise((ok) => setTimeout(ok, 5));
  }
}

/** Abre a tela com a API simulada. `responderEnvio` decide a resposta do POST. */
async function abrirTela({ orcamentos = [ORCAMENTO], responderEnvio = async () => RESPOSTA_CRIADO } = {}) {
  const dom = new JSDOM(HTML, { url: "https://mdca-sistema.pages.dev/Financeiro/lancamento/" });
  const { window } = dom;
  window.HTMLElement.prototype.scrollIntoView = () => {};
  window.scrollTo = () => {};
  window.localStorage.setItem("mdca.financeiro.token", "token-de-teste");

  globalThis.window = window;
  globalThis.document = window.document;
  globalThis.localStorage = window.localStorage;
  globalThis.Option = window.Option;

  const chamadas = [];
  globalThis.fetch = async (url, opcoes = {}) => {
    const metodo = opcoes.method || "GET";
    chamadas.push({ url, metodo, headers: opcoes.headers || {}, corpo: opcoes.body });
    if (metodo === "GET" && url.startsWith(`${API}/orcamentos`)) {
      return new Response(JSON.stringify(orcamentos), { status: 200 });
    }
    if (metodo === "POST" && url === `${API}/lancamentos`) {
      const { status, corpo } = await responderEnvio();
      return new Response(JSON.stringify(corpo), { status });
    }
    return new Response("{}", { status: 404 });
  };

  versao += 1;
  await import(`../lancamento/lancamento.js?tela=${versao}`);

  const $ = (id) => window.document.getElementById(id);
  await esperar(() => !$("form-lancamento").hidden && $("campo-projeto").options.length > 0, "formulário carregar");

  const envios = () => chamadas.filter((c) => c.metodo === "POST");
  return { window, $, chamadas, envios };
}

function definirCampo(tela, id, valor, evento) {
  const campo = tela.$(id);
  campo.value = valor;
  campo.dispatchEvent(new tela.window.Event(evento, { bubbles: true }));
}

function preencherTudo(tela, extra = {}) {
  const dados = {
    projeto: "orc-semear",
    categoria: "alimentacao",
    valor: "486,90",
    data: "2026-10-12",
    descricao: "  Lanche da oficina  ",
    ...extra,
  };
  definirCampo(tela, "campo-projeto", dados.projeto, "change");
  definirCampo(tela, "campo-categoria", dados.categoria, "change");
  definirCampo(tela, "campo-valor", dados.valor, "input");
  definirCampo(tela, "campo-data", dados.data, "input");
  definirCampo(tela, "campo-descricao", dados.descricao, "input");
}

function arquivo({ nome = "nota.jpg", tipo = "image/jpeg", tamanho = 2048 } = {}) {
  return new File([new Uint8Array(tamanho)], nome, { type: tipo });
}

async function anexar(tela, arq = arquivo(), entrada = "campo-camera") {
  const input = tela.$(entrada);
  Object.defineProperty(input, "files", { value: [arq], configurable: true });
  input.dispatchEvent(new tela.window.Event("change", { bubbles: true }));
  await esperar(() => !tela.$("comprovante-escolhido").hidden, "comprovante aparecer");
}

async function enviar(tela) {
  tela.$("botao-enviar").click();
  await new Promise((ok) => setTimeout(ok, 20));
}

function erroVisivel(tela, campo) {
  const p = tela.$(`erro-${campo}`);
  return p.hidden ? null : p.textContent;
}

// --- Critério 1: envio sem campo obrigatório é bloqueado ---------------------

describe("Critério 1 · envio sem campo obrigatório é bloqueado", { skip: SEM_JSDOM }, () => {
  test("formulário em branco: nada é enviado e todos os erros aparecem", async () => {
    const tela = await abrirTela({ orcamentos: [ORCAMENTO, { ...ORCAMENTO, id: "orc-2", projeto_id: "outro" }] });
    definirCampo(tela, "campo-data", "", "input");

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    for (const campo of ["projeto", "categoria", "valor", "data", "descricao", "comprovante"]) {
      assert.ok(erroVisivel(tela, campo), `esperava erro em ${campo}`);
    }
    assert.equal(tela.$("painel-sucesso").hidden, true);
  });

  for (const [campo, id, evento] of [
    ["categoria", "campo-categoria", "change"],
    ["valor", "campo-valor", "input"],
    ["data", "campo-data", "input"],
    ["descricao", "campo-descricao", "input"],
  ]) {
    test(`sem ${campo}: bloqueia o envio e aponta só esse campo`, async () => {
      const tela = await abrirTela();
      preencherTudo(tela);
      await anexar(tela);
      definirCampo(tela, id, "", evento);

      await enviar(tela);

      assert.equal(tela.envios().length, 0, "não pode chamar POST /lancamentos");
      assert.ok(erroVisivel(tela, campo));
      assert.equal(tela.$(id).getAttribute("aria-invalid"), "true");
      for (const outro of ["projeto", "categoria", "valor", "data", "descricao", "comprovante"]) {
        if (outro !== campo) assert.equal(erroVisivel(tela, outro), null, `erro inesperado em ${outro}`);
      }
      assert.equal(tela.$("form-lancamento").hidden, false);
    });
  }

  test("sem projeto: bloqueia (com mais de um projeto não há seleção automática)", async () => {
    const tela = await abrirTela({ orcamentos: [ORCAMENTO, { ...ORCAMENTO, id: "orc-2", projeto_id: "outro" }] });
    preencherTudo(tela, { projeto: "" });
    await anexar(tela);

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    assert.ok(erroVisivel(tela, "projeto"));
  });

  test("valor zero ou em formato inválido bloqueia", async () => {
    for (const valor of ["0,00", "abc", "-5"]) {
      const tela = await abrirTela();
      preencherTudo(tela, { valor });
      await anexar(tela);

      await enviar(tela);

      assert.equal(tela.envios().length, 0, `valor "${valor}" não deveria ser enviado`);
      assert.ok(erroVisivel(tela, "valor"));
    }
  });

  test("ao corrigir o campo, o erro some e o envio passa", async () => {
    const tela = await abrirTela();
    preencherTudo(tela, { descricao: "" });
    await anexar(tela);
    await enviar(tela);
    assert.ok(erroVisivel(tela, "descricao"));

    definirCampo(tela, "campo-descricao", "Lanche", "input");
    assert.equal(erroVisivel(tela, "descricao"), null);

    await enviar(tela);
    await esperar(() => !tela.$("painel-sucesso").hidden, "confirmação");
    assert.equal(tela.envios().length, 1);
  });
});

// --- Critério 2: envio sem comprovante é bloqueado ---------------------------

describe("Critério 2 · envio sem comprovante é bloqueado", { skip: SEM_JSDOM }, () => {
  test("todos os campos preenchidos, sem comprovante: nada é enviado", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    assert.equal(erroVisivel(tela, "comprovante"), "Anexe a foto ou o PDF do comprovante.");
  });

  test("comprovante removido com 'Trocar' volta a bloquear", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);
    await anexar(tela);
    tela.$("trocar-arquivo").click();

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    assert.ok(erroVisivel(tela, "comprovante"));
  });

  test("arquivo que não é foto nem PDF bloqueia", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);
    await anexar(tela, arquivo({ nome: "nota.docx", tipo: "application/msword" }), "campo-galeria");

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    assert.match(erroVisivel(tela, "comprovante"), /foto|PDF/);
  });

  test("arquivo acima de 5 MB bloqueia", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);
    await anexar(tela, arquivo({ nome: "nota.pdf", tipo: "application/pdf", tamanho: 5 * 1024 * 1024 + 1 }), "campo-galeria");

    await enviar(tela);

    assert.equal(tela.envios().length, 0);
    assert.match(erroVisivel(tela, "comprovante"), /5 MB/);
  });

  test("se a API recusar por falta de comprovante, a tela mostra o motivo e não confirma", async () => {
    const tela = await abrirTela({
      responderEnvio: async () => ({ status: 400, corpo: { detail: "Comprovante obrigatório." } }),
    });
    preencherTudo(tela);
    await anexar(tela);

    await enviar(tela);
    await esperar(() => !tela.$("aviso-geral").hidden, "aviso de erro");

    assert.equal(tela.$("aviso-geral").textContent, "Comprovante obrigatório.");
    assert.equal(tela.$("painel-sucesso").hidden, true);
  });
});

// --- Critério 3: envio válido completo cria lançamento pendente --------------

describe("Critério 3 · envio válido completo cria lançamento pendente", { skip: SEM_JSDOM }, () => {
  test("envia uma vez para POST /lancamentos com os campos da API", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);
    await anexar(tela, arquivo({ nome: "nota.jpg" }));

    await enviar(tela);
    await esperar(() => !tela.$("painel-sucesso").hidden, "confirmação");

    const [envio] = tela.envios();
    assert.equal(tela.envios().length, 1);
    assert.equal(envio.url, `${API}/lancamentos`);
    assert.equal(envio.headers.Authorization, "Bearer token-de-teste");
    assert.equal(envio.headers["X-Papel-Usuario"], "educador");
    assert.equal(envio.corpo.get("orcamento_id"), "orc-semear");
    assert.equal(envio.corpo.get("categoria"), "alimentacao");
    assert.equal(envio.corpo.get("valor"), "486.90");
    assert.equal(envio.corpo.get("data_despesa"), "2026-10-12");
    assert.equal(envio.corpo.get("descricao"), "Lanche da oficina");
    assert.equal(envio.corpo.get("comprovante").name, "nota.jpg");
  });

  test("mostra a confirmação 'Lançamento enviado · Pendente de aprovação' com o resumo", async () => {
    const tela = await abrirTela();
    preencherTudo(tela);
    await anexar(tela);

    await enviar(tela);
    await esperar(() => !tela.$("painel-sucesso").hidden, "confirmação");

    assert.equal(tela.$("form-lancamento").hidden, true);
    assert.equal(tela.$("sucesso-status").textContent, "Pendente de aprovação");
    assert.equal(tela.$("sucesso-projeto").textContent, "semear-contraturno");
    assert.equal(tela.$("sucesso-categoria").textContent, "alimentacao");
    assert.match(tela.$("sucesso-valor").textContent, /486,90/);
    assert.equal(tela.$("sucesso-data").textContent, "12/10/2026");
    assert.equal(tela.$("sucesso-comprovante").textContent, "nota.jpg");
  });

  test("toque duplo em 'Enviar' não cria dois lançamentos", async () => {
    let liberar;
    const tela = await abrirTela({
      responderEnvio: () => new Promise((ok) => { liberar = () => ok(RESPOSTA_CRIADO); }),
    });
    preencherTudo(tela);
    await anexar(tela);

    await enviar(tela);
    assert.equal(tela.$("botao-enviar").disabled, true);
    assert.equal(tela.$("botao-enviar").textContent, "Enviando…");
    await enviar(tela);
    liberar();
    await esperar(() => !tela.$("painel-sucesso").hidden, "confirmação");

    assert.equal(tela.envios().length, 1);
  });

  test("'Lançar outra despesa' limpa o formulário e mantém o projeto", async () => {
    const tela = await abrirTela({ orcamentos: [ORCAMENTO, { ...ORCAMENTO, id: "orc-2", projeto_id: "outro" }] });
    preencherTudo(tela);
    await anexar(tela);
    await enviar(tela);
    await esperar(() => !tela.$("painel-sucesso").hidden, "confirmação");

    tela.$("botao-novo").click();

    assert.equal(tela.$("form-lancamento").hidden, false);
    assert.equal(tela.$("campo-projeto").value, "orc-semear");
    assert.equal(tela.$("campo-valor").value, "");
    assert.equal(tela.$("campo-descricao").value, "");
    assert.equal(tela.$("comprovante-escolhido").hidden, true);
  });

  test("código de acesso recusado pela API leva de volta à tela de código", async () => {
    const tela = await abrirTela({ responderEnvio: async () => ({ status: 401, corpo: { detail: "Autenticação obrigatória." } }) });
    preencherTudo(tela);
    await anexar(tela);

    await enviar(tela);
    await esperar(() => !tela.$("painel-acesso").hidden, "tela de código");

    assert.equal(tela.$("painel-sucesso").hidden, true);
  });
});
