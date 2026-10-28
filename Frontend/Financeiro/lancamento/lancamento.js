// Redesign Financeiro · celular do educador — "fotografa agora, completa depois".
//
// Uma página, telas trocadas por location.hash:
//   #/                       Minhas despesas
//   #/completar/<rascunho>   Completar despesa
//   #/despesa/<lancamento>   Despesa (rejeitada: motivo + "Corrigir e reenviar")
//   #/corrigir/<lancamento>  Mesmo formulário, preenchido, para reenviar
//   #/avisos                 Notificações
//   #/perfil                 Nome, código de acesso, servidor, sair

import {
  API_PADRAO,
  baixarArquivo,
  completarRascunho,
  criarRascunho,
  esquecerAcesso,
  listarLancamentos,
  listarNotificacoes,
  listarOrcamentos,
  listarRascunhos,
  marcarNotificacaoLida,
  obterLancamento,
  reenviarLancamento,
  salvarAcesso,
  tokenSalvo,
  urlDaApi,
} from "../base/api.js";
import { el, limpar } from "../base/dom.js";
import { formatarData, formatarMoeda, tempoRelativo } from "../base/formatar.js";
import { icone } from "../base/icones.js";
import { CHAVE_SESSAO_CELULAR, encerrarSessao, lerSessao, salvarSessao, usarChaveDeSessao } from "../base/sessao.js";
import {
  agruparDespesas,
  legendaDaDespesa,
  nomeDoProjeto,
  quandoFoiTirada,
  rotuloDoStatus,
  ultimoProjetoUsado,
} from "./despesas-dados.js";
import {
  DESCRICAO_MAXIMA,
  deveComprimir,
  dimensoesReduzidas,
  erroDoComprovante,
  hojeISO,
  mensagemDeErro,
  montarFormDataDados,
  validarFormulario,
} from "./formulario.js";

usarChaveDeSessao(CHAVE_SESSAO_CELULAR);

const $ = (id) => document.getElementById(id);
const tela = $("tela");
const abas = $("abas");
const avisoFlutuante = $("aviso-flutuante");
const entradaCamera = $("campo-camera");
const entradaGaleria = $("campo-galeria");

const CODIGO_INVALIDO = "Código de acesso inválido. Informe de novo.";
const LIMITE_ENVIADAS = 5;

let vez = 0; // cada troca de tela descarta respostas que chegarem da tela anterior
let urlsDeImagem = [];
let verTodas = false;
let temporizadorDoAviso = 0;

// --- Utilitários de tela ---------------------------------------------------

function montar(...filhos) {
  limpar(tela).append(...filhos.flat().filter(Boolean));
  window.scrollTo(0, 0);
}

function carregando() {
  montar(el("p", { class: "carregando", role: "status" }, "Carregando…"));
}

function cabecalho(titulo, voltarPara = "#/") {
  return el(
    "header",
    { class: "cabecalho" },
    el("a", { class: "cabecalho__voltar", href: voltarPara, "aria-label": "Voltar" }, icone("voltar")),
    el("h1", { class: "cabecalho__titulo" }, titulo),
  );
}

function etiqueta(status) {
  const { texto, classe } = rotuloDoStatus(status);
  return el("span", { class: `etiqueta ${classe}` }, texto);
}

function vazio(texto) {
  return el("p", { class: "vazio" }, texto);
}

function liberarImagens() {
  for (const url of urlsDeImagem) URL.revokeObjectURL(url);
  urlsDeImagem = [];
}

/** Comprovante protegido pela API: baixa com o código de acesso e mostra. */
async function preencherPrevia(caixa, caminho, minhaVez) {
  if (!caminho) return;
  const { blob } = await baixarArquivo(caminho);
  if (!blob || minhaVez !== vez) return;
  limpar(caixa);
  if (blob.type.startsWith("image/")) {
    const url = URL.createObjectURL(blob);
    urlsDeImagem.push(url);
    caixa.append(el("img", { src: url, alt: "Comprovante" }));
  } else {
    caixa.append(el("span", { class: "previa__pdf" }, "PDF"));
  }
}

function previa(caminho, minhaVez, classe = "previa") {
  const caixa = el("div", { class: classe });
  preencherPrevia(caixa, caminho, minhaVez);
  return caixa;
}

function fecharAviso() {
  window.clearTimeout(temporizadorDoAviso);
  avisoFlutuante.hidden = true;
}

/** Aviso que aparece por cima da barra inferior; `acao` = { texto, href }. */
function avisar(texto, acao = null) {
  window.clearTimeout(temporizadorDoAviso);
  limpar(avisoFlutuante).append(el("span", {}, texto));
  if (acao) avisoFlutuante.append(el("a", { href: acao.href, onclick: () => (avisoFlutuante.hidden = true) }, acao.texto));
  avisoFlutuante.hidden = false;
  temporizadorDoAviso = window.setTimeout(() => (avisoFlutuante.hidden = true), 6000);
}

function respostaComFalha(respostas) {
  return respostas.find((r) => r.status !== 200);
}

function mostrarFalha({ status, corpo }) {
  if (status === 401) return telaPrimeiroAcesso(CODIGO_INVALIDO);
  montar(
    el("p", { class: "aviso", role: "alert" }, mensagemDeErro(status, corpo)),
    el("button", { type: "button", class: "botao botao--sec", onclick: mostrarTela }, "Tentar de novo"),
  );
}

function vigentesHoje(orcamentos) {
  const hoje = hojeISO();
  return orcamentos.filter((o) => o.data_inicio <= hoje && hoje <= o.data_fim);
}

// --- Rotas -----------------------------------------------------------------

function rotaAtual() {
  const [nome = "", id = ""] = window.location.hash.replace(/^#\/?/, "").split("/");
  return { nome, id: decodeURIComponent(id) };
}

function precisaPrimeiroAcesso() {
  const sessao = lerSessao();
  return !sessao || sessao.papel !== "educador" || !tokenSalvo();
}

const TELAS = {
  "": { abrir: telaDespesas, aba: "despesas" },
  completar: { abrir: telaCompletar },
  despesa: { abrir: telaDespesa },
  corrigir: { abrir: telaCorrigir },
  avisos: { abrir: telaAvisos, aba: "avisos" },
  perfil: { abrir: telaPerfil, aba: "perfil" },
};

function mostrarTela() {
  vez += 1;
  liberarImagens();
  if (precisaPrimeiroAcesso()) return telaPrimeiroAcesso();
  const { nome, id } = rotaAtual();
  const rota = TELAS[nome] || TELAS[""];
  if (rota.aba && rota.aba !== "despesas") fecharAviso();
  abas.hidden = !rota.aba;
  for (const item of abas.querySelectorAll("[data-aba]")) {
    if (item.dataset.aba === rota.aba) item.setAttribute("aria-current", "page");
    else item.removeAttribute("aria-current");
  }
  return rota.abrir(id, vez);
}

// --- Primeiro acesso -------------------------------------------------------

function telaPrimeiroAcesso(mensagem = "") {
  vez += 1;
  abas.hidden = true;
  const sessao = lerSessao();
  const nome = el("input", { id: "campo-nome", class: "entrada", type: "text", autocomplete: "name", required: true });
  nome.value = sessao?.papel === "educador" ? sessao.nome : "";
  const token = el("input", { id: "campo-token", class: "entrada", type: "password", autocomplete: "off", autocapitalize: "off", spellcheck: "false", required: true });
  const api = el("input", { id: "campo-api", class: "entrada", type: "url", inputmode: "url", autocapitalize: "off", spellcheck: "false" });
  api.value = urlDaApi();
  const erro = el("p", { id: "erro-acesso", class: "erro", role: "alert", hidden: !mensagem }, mensagem);

  function entrar(evento) {
    evento.preventDefault();
    const falta = !nome.value.trim() ? "Informe seu nome." : !token.value.trim() ? "Informe o código de acesso." : "";
    if (falta) {
      erro.textContent = falta;
      erro.hidden = false;
      return;
    }
    salvarSessao({ papel: "educador", nome: nome.value.trim() });
    salvarAcesso(token.value, api.value || API_PADRAO);
    mostrarTela();
  }

  montar(
    el(
      "form",
      { id: "form-acesso", class: "formulario", novalidate: true, onsubmit: entrar },
      el("h1", { class: "titulo" }, "Minhas despesas"),
      el("p", { class: "ajuda" }, "Informe seu nome e o código de acesso do Financeiro. Eles ficam salvos só neste aparelho."),
      campo("Seu nome", nome),
      campo("Código de acesso", token),
      el("details", { class: "avancado" }, el("summary", {}, "Servidor (avançado)"), campo("Endereço da API", api)),
      erro,
      el("button", { type: "submit", class: "botao" }, "Entrar"),
    ),
  );
  (nome.value ? token : nome).focus();
}

function campo(rotulo, entrada, erro = null) {
  return el("div", { class: "campo" }, el("label", { for: entrada.id }, rotulo), entrada, erro);
}

// --- Minhas despesas -------------------------------------------------------

async function telaDespesas(_id, minhaVez) {
  carregando();
  const respostas = await Promise.all([listarLancamentos(), listarRascunhos(), listarOrcamentos()]);
  if (minhaVez !== vez) return;
  const falha = respostaComFalha(respostas);
  if (falha) return mostrarFalha(falha);
  const [{ corpo: lancamentos }, { corpo: rascunhos }, { corpo: orcamentos }] = respostas;

  const { ajuste, aCompletar, enviadas } = agruparDespesas(lancamentos, rascunhos, {
    limiteEnviadas: verTodas ? Infinity : LIMITE_ENVIADAS,
  });
  const totalEnviadas = lancamentos.filter((l) => l.status !== "rejeitado").length;
  const itemDespesa = (l) => itemDeDespesa(l, orcamentos);

  montar(
    el("h1", { class: "titulo" }, "Minhas despesas"),
    el("button", { type: "button", id: "botao-fotografar", class: "botao botao--grande", onclick: () => entradaCamera.click() }, icone("camera"), "Fotografar comprovante"),
    el("button", { type: "button", class: "botao-link", onclick: () => entradaGaleria.click() }, icone("galeria"), "Escolher da galeria ou arquivo"),
    ajuste.length ? secao(`Precisa de ajuste (${ajuste.length})`, lista(ajuste.map(itemDespesa), "lista--alerta"), null, "secao-ajuste") : null,
    aCompletar.length ? secao(`A completar (${aCompletar.length})`, lista(aCompletar.map((r) => itemDeRascunho(r, minhaVez))), null, "secao-completar") : null,
    secao(
      "Enviadas",
      enviadas.length ? lista(enviadas.map(itemDespesa)) : vazio("Nenhuma despesa enviada ainda."),
      !verTodas && totalEnviadas > LIMITE_ENVIADAS
        ? el("button", { type: "button", class: "secao__acao", onclick: () => { verTodas = true; mostrarTela(); } }, "Ver todas")
        : null,
      "secao-enviadas",
    ),
  );
}

function secao(titulo, conteudo, acao, id) {
  return el("section", { class: "secao", id }, el("div", { class: "secao__topo" }, el("h2", {}, titulo), acao), conteudo);
}

function lista(itens, classe = "") {
  return el("ul", { class: `lista ${classe}` }, itens.map((item) => el("li", {}, item)));
}

function itemDeDespesa(lancamento, orcamentos) {
  return el(
    "a",
    { class: "item", href: `#/despesa/${encodeURIComponent(lancamento.id)}` },
    el("span", { class: "item__texto" }, el("span", { class: "item__titulo" }, lancamento.categoria), el("small", {}, legendaDaDespesa(lancamento, orcamentos))),
    el("span", { class: "item__lado" }, el("span", { class: "num" }, formatarMoeda(lancamento.valor)), etiqueta(lancamento.status)),
  );
}

function itemDeRascunho(rascunho, minhaVez) {
  return el(
    "a",
    { class: "item", href: `#/completar/${encodeURIComponent(rascunho.id)}` },
    el(
      "span",
      { class: "item__foto" },
      previa(rascunho.comprovante_url, minhaVez, "miniatura"),
      el("span", { class: "item__texto" }, el("span", { class: "item__titulo" }, "Comprovante"), el("small", {}, quandoFoiTirada(rascunho.criado_em))),
    ),
    icone("seta"),
  );
}

// --- Câmera: foto vira rascunho --------------------------------------------

async function reduzirFoto(original) {
  if (!deveComprimir(original)) return original;
  try {
    const imagem = await createImageBitmap(original);
    const { largura, altura } = dimensoesReduzidas(imagem.width, imagem.height);
    const canvas = document.createElement("canvas");
    canvas.width = largura;
    canvas.height = altura;
    canvas.getContext("2d").drawImage(imagem, 0, 0, largura, altura);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.82));
    if (!blob || blob.size >= original.size) return original;
    const nome = (original.name || "comprovante").replace(/\.\w+$/, "") + ".jpg";
    return new File([blob], nome, { type: "image/jpeg" });
  } catch {
    return original; // ex.: HEIC em navegador que não decodifica; o servidor valida
  }
}

/** Lê o arquivo escolhido num <input type=file>, já reduzido; inválido → avisa e devolve null. */
async function lerArquivoEscolhido(entrada) {
  const original = entrada.files?.[0];
  entrada.value = ""; // permite escolher o mesmo arquivo de novo
  if (!original) return null;
  const arquivo = await reduzirFoto(original);
  const erro = erroDoComprovante(arquivo);
  if (erro) {
    avisar(erro);
    return null;
  }
  return arquivo;
}

async function fotografar(evento) {
  const arquivo = await lerArquivoEscolhido(evento.target);
  if (!arquivo) return;
  avisar("Salvando a foto…");
  const { status, corpo } = await criarRascunho(arquivo);
  if (status === 201) {
    avisar("Foto salva em \"A completar\"", { texto: "Completar agora", href: `#/completar/${encodeURIComponent(corpo.id)}` });
    if (rotaAtual().nome === "") mostrarTela();
    return;
  }
  avisoFlutuante.hidden = true;
  if (status === 401) return telaPrimeiroAcesso(CODIGO_INVALIDO);
  avisar(mensagemDeErro(status, corpo));
}

// --- Formulário de despesa (completar e corrigir) --------------------------

const CAMPOS = ["valor", "projeto", "categoria", "descricao", "data", "comprovante"];

/**
 * Uma tela só: foto, valor, projeto, categoria (botões), o que foi comprado e data.
 * `config.enviar(dados, arquivoNovo)` faz a chamada; `config.trocarFoto` libera trocar a foto.
 */
function formularioDespesa(config, minhaVez) {
  const { titulo, voltarPara, comprovanteUrl, trocarFoto, orcamentos, projetoFixo, inicial, statusDeSucesso, enviar, textoDoBotao } = config;
  let categoria = inicial.categoria || "";
  let arquivoNovo = null;

  const erros = Object.fromEntries(CAMPOS.map((c) => [c, el("p", { id: `erro-${c}`, class: "erro", hidden: true })]));
  const aviso = el("p", { id: "aviso-geral", class: "aviso", role: "alert", hidden: true });

  const foto = previa(comprovanteUrl, minhaVez);
  const entradaFoto = el("input", { id: "campo-foto", class: "arquivo-oculto", type: "file", accept: "image/*,application/pdf", capture: "environment", tabindex: "-1", "aria-hidden": "true" });
  entradaFoto.addEventListener("change", async () => {
    const arquivo = await lerArquivoEscolhido(entradaFoto);
    if (!arquivo) return;
    arquivoNovo = arquivo;
    limpar(foto);
    if (arquivo.type.startsWith("image/")) {
      const url = URL.createObjectURL(arquivo);
      urlsDeImagem.push(url);
      foto.append(el("img", { src: url, alt: "Comprovante novo" }));
    } else {
      foto.append(el("span", { class: "previa__pdf" }, "PDF"));
    }
    limparErro("comprovante");
  });

  const valor = el("input", { id: "campo-valor", class: "entrada entrada--valor num", type: "text", inputmode: "decimal", autocomplete: "off", placeholder: "R$ 0,00" });
  valor.value = inicial.valor || "";

  const projeto = el("select", { id: "campo-projeto", class: "entrada", disabled: projetoFixo });
  projeto.append(el("option", { value: "" }, orcamentos.length ? "Escolha o projeto" : "Nenhum projeto com orçamento vigente"));
  for (const o of orcamentos) projeto.append(el("option", { value: o.id }, nomeDoProjeto(o.id, orcamentos)));
  projeto.value = inicial.orcamentoId || "";

  const categorias = el("div", { id: "campo-categoria", class: "escolhas", role: "group", "aria-labelledby": "rotulo-categoria" });

  const descricao = el("input", { id: "campo-descricao", class: "entrada", type: "text", maxlength: DESCRICAO_MAXIMA, placeholder: "Ex.: livros para a oficina" });
  descricao.value = inicial.descricao || "";

  const data = el("input", { id: "campo-data", class: "entrada", type: "date" });
  data.value = inicial.data || hojeISO();

  const botao = el("button", { type: "submit", id: "botao-enviar", class: "botao" }, textoDoBotao);

  const orcamentoEscolhido = () => orcamentos.find((o) => o.id === projeto.value);

  function desenharCategorias() {
    const o = orcamentoEscolhido();
    limpar(categorias);
    if (!o) return categorias.append(el("span", { class: "ajuda" }, "Escolha o projeto primeiro."));
    if (!o.categorias_despesa.includes(categoria)) categoria = o.categorias_despesa.length === 1 ? o.categorias_despesa[0] : "";
    for (const c of o.categorias_despesa) {
      categorias.append(
        el("button", {
          type: "button",
          class: "escolha",
          "aria-pressed": String(c === categoria),
          onclick: () => {
            categoria = c;
            limparErro("categoria");
            desenharCategorias();
          },
        }, c),
      );
    }
    data.min = o.data_inicio;
    data.max = o.data_fim;
  }

  function limparErro(nome) {
    erros[nome].textContent = "";
    erros[nome].hidden = true;
  }

  function mostrarErros(encontrados) {
    let primeiro = null;
    for (const nome of CAMPOS) {
      erros[nome].textContent = encontrados[nome] || "";
      erros[nome].hidden = !encontrados[nome];
      if (encontrados[nome]) primeiro ??= nome;
    }
    const alvo = { valor, projeto, categoria: categorias, descricao, data, comprovante: foto }[primeiro];
    alvo?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  async function aoEnviar(evento) {
    evento.preventDefault();
    if (botao.disabled) return;
    const dados = { orcamento: orcamentoEscolhido(), categoria, valor: valor.value, data: data.value, descricao: descricao.value, arquivo: arquivoNovo };
    const encontrados = validarFormulario(dados, { exigirArquivo: false });
    mostrarErros(encontrados);
    aviso.hidden = true;
    if (Object.keys(encontrados).length) return;

    botao.disabled = true;
    botao.textContent = "Enviando…";
    const { status, corpo } = await enviar(dados, arquivoNovo);
    botao.disabled = false;
    botao.textContent = textoDoBotao;
    if (status === statusDeSucesso) {
      avisar("Despesa enviada para aprovação");
      window.location.hash = "#/";
      return;
    }
    if (status === 401) return telaPrimeiroAcesso(CODIGO_INVALIDO);
    aviso.textContent = mensagemDeErro(status, corpo);
    aviso.hidden = false;
    aviso.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  projeto.addEventListener("change", () => {
    desenharCategorias();
    limparErro("projeto");
  });
  valor.addEventListener("input", () => limparErro("valor"));
  descricao.addEventListener("input", () => limparErro("descricao"));
  data.addEventListener("input", () => limparErro("data"));
  desenharCategorias();

  montar(
    cabecalho(titulo, voltarPara),
    el(
      "form",
      { id: "form-despesa", class: "formulario", novalidate: true, onsubmit: aoEnviar },
      aviso,
      el(
        "div",
        { class: "foto" },
        foto,
        trocarFoto ? el("button", { type: "button", class: "foto__trocar", onclick: () => entradaFoto.click() }, "Trocar foto") : null,
        trocarFoto ? entradaFoto : null,
      ),
      erros.comprovante,
      campo("Valor", valor, erros.valor),
      campo("Projeto", projeto, erros.projeto),
      el("div", { class: "campo" }, el("span", { id: "rotulo-categoria", class: "campo__rotulo" }, "Categoria"), categorias, erros.categoria),
      campo("O que foi comprado", descricao, erros.descricao),
      campo("Data", data, erros.data),
      botao,
    ),
  );
}

async function telaCompletar(id, minhaVez) {
  carregando();
  const respostas = await Promise.all([listarRascunhos(), listarLancamentos(), listarOrcamentos()]);
  if (minhaVez !== vez) return;
  const falha = respostaComFalha(respostas);
  if (falha) return mostrarFalha(falha);
  const [{ corpo: rascunhos }, { corpo: lancamentos }, { corpo: orcamentos }] = respostas;

  const rascunho = rascunhos.find((r) => r.id === id);
  if (!rascunho) return montar(cabecalho("Completar despesa"), vazio("Esta foto já foi completada ou não existe mais."));

  const vigentes = vigentesHoje(orcamentos);
  const ultimo = ultimoProjetoUsado(lancamentos);
  const padrao = vigentes.some((o) => o.id === ultimo) ? ultimo : vigentes.length === 1 ? vigentes[0].id : "";

  formularioDespesa(
    {
      titulo: "Completar despesa",
      comprovanteUrl: rascunho.comprovante_url,
      trocarFoto: false,
      orcamentos: vigentes,
      projetoFixo: false,
      inicial: { orcamentoId: padrao, data: hojeISO(new Date(rascunho.criado_em)) },
      statusDeSucesso: 201,
      textoDoBotao: "Enviar para aprovação",
      enviar: (dados) => completarRascunho(id, montarFormDataDados(dados)),
    },
    minhaVez,
  );
}

async function telaCorrigir(id, minhaVez) {
  carregando();
  const respostas = await Promise.all([obterLancamento(id), listarOrcamentos()]);
  if (minhaVez !== vez) return;
  const falha = respostaComFalha(respostas);
  if (falha) return mostrarFalha(falha);
  const [{ corpo: despesa }, { corpo: orcamentos }] = respostas;
  if (despesa.status !== "rejeitado") {
    window.location.hash = `#/despesa/${encodeURIComponent(id)}`;
    return;
  }

  formularioDespesa(
    {
      titulo: "Corrigir despesa",
      voltarPara: `#/despesa/${encodeURIComponent(id)}`,
      comprovanteUrl: despesa.comprovante_url,
      trocarFoto: true,
      // O reenvio não troca de projeto: só o orçamento da despesa.
      orcamentos: orcamentos.filter((o) => o.id === despesa.orcamento_id),
      projetoFixo: true,
      inicial: {
        orcamentoId: despesa.orcamento_id,
        categoria: despesa.categoria,
        valor: despesa.valor.toFixed(2).replace(".", ","),
        descricao: despesa.descricao,
        data: despesa.data_despesa,
      },
      statusDeSucesso: 200,
      textoDoBotao: "Reenviar para aprovação",
      enviar: (dados, arquivo) => {
        const formData = montarFormDataDados(dados);
        if (arquivo) formData.append("comprovante", arquivo, arquivo.name || "comprovante.jpg");
        return reenviarLancamento(id, formData);
      },
    },
    minhaVez,
  );
}

// --- Despesa (rejeitada ou não) --------------------------------------------

async function telaDespesa(id, minhaVez) {
  carregando();
  const respostas = await Promise.all([obterLancamento(id), listarOrcamentos()]);
  if (minhaVez !== vez) return;
  const [resposta, { corpo: orcamentos }] = respostas;
  if (resposta.status === 404) return montar(cabecalho("Despesa"), vazio("Despesa não encontrada."));
  const falha = respostaComFalha(respostas);
  if (falha) return mostrarFalha(falha);
  const despesa = resposta.corpo;
  const rejeitada = despesa.status === "rejeitado";
  const projeto = nomeDoProjeto(despesa.orcamento_id, orcamentos);
  const anteriores = despesa.motivos_rejeicao_anteriores || [];

  montar(
    cabecalho("Despesa"),
    el(
      "div",
      { class: "despesa" },
      el(
        "div",
        { class: "despesa__topo" },
        el("div", {}, el("p", { class: "despesa__legenda" }, [despesa.categoria, projeto].filter(Boolean).join(" · ")), el("p", { class: "despesa__valor num" }, formatarMoeda(despesa.valor))),
        etiqueta(despesa.status),
      ),
      rejeitada
        ? el("div", { id: "motivo-rejeicao", class: "alerta", role: "note" }, el("strong", {}, "Motivo informado pela coordenação"), el("p", {}, despesa.motivo_rejeicao || ""))
        : null,
      anteriores.length
        ? el("details", { class: "anteriores" }, el("summary", {}, `Rejeições anteriores (${anteriores.length})`), el("ul", {}, anteriores.map((m) => el("li", {}, m))))
        : null,
      previa(despesa.comprovante_url, minhaVez),
      el("p", { class: "despesa__descricao" }, [despesa.descricao, despesa.data_despesa ? formatarData(despesa.data_despesa) : ""].filter(Boolean).join(" · ")),
      rejeitada ? el("a", { id: "botao-corrigir", class: "botao", href: `#/corrigir/${encodeURIComponent(despesa.id)}` }, "Corrigir e reenviar") : null,
    ),
  );
}

// --- Avisos ----------------------------------------------------------------

async function telaAvisos(_id, minhaVez) {
  carregando();
  const resposta = await listarNotificacoes();
  if (minhaVez !== vez) return;
  if (resposta.status !== 200) return mostrarFalha(resposta);
  const avisos = resposta.corpo; // a API já devolve das mais recentes para as mais antigas

  montar(
    el("h1", { class: "titulo" }, "Avisos"),
    avisos.length
      ? lista(
          avisos.map((n) =>
            el(
              "a",
              { class: `item item--aviso${n.lida ? "" : " item--novo"}`, href: `#/despesa/${encodeURIComponent(n.lancamento_id)}` },
              el("span", { class: "item__texto" }, el("span", {}, n.mensagem), el("small", {}, tempoRelativo(n.criada_em))),
            ),
          ),
        )
      : vazio("Nenhum aviso por enquanto."),
  );
  // Abriu a tela, leu: os novos ficam destacados só desta vez.
  for (const n of avisos) if (!n.lida) marcarNotificacaoLida(n.id);
}

// --- Perfil ----------------------------------------------------------------

function telaPerfil() {
  const sessao = lerSessao();
  const token = el("input", { id: "campo-token", class: "entrada", type: "password", autocomplete: "off", autocapitalize: "off", spellcheck: "false", placeholder: "Deixe em branco para manter" });
  const api = el("input", { id: "campo-api", class: "entrada", type: "url", inputmode: "url", autocapitalize: "off", spellcheck: "false" });
  api.value = urlDaApi();

  function salvar(evento) {
    evento.preventDefault();
    salvarAcesso(token.value.trim() || tokenSalvo(), api.value || API_PADRAO);
    token.value = "";
    avisar("Dados de acesso salvos");
  }

  function sair() {
    encerrarSessao();
    esquecerAcesso();
    window.location.hash = "#/";
    mostrarTela();
  }

  montar(
    el("h1", { class: "titulo" }, "Perfil"),
    el("div", { class: "perfil" }, el("span", { class: "campo__rotulo" }, "Nome"), el("p", { id: "perfil-nome", class: "perfil__nome" }, sessao.nome), el("p", { class: "ajuda" }, "Educador")),
    el(
      "form",
      { id: "form-perfil", class: "formulario", novalidate: true, onsubmit: salvar },
      campo("Código de acesso", token),
      el("details", { class: "avancado" }, el("summary", {}, "Servidor (avançado)"), campo("Endereço da API", api)),
      el("button", { type: "submit", class: "botao botao--sec" }, "Salvar"),
    ),
    el("button", { type: "button", id: "botao-sair", class: "botao botao--perigo", onclick: sair }, "Sair deste aparelho"),
  );
}

// --- Início ----------------------------------------------------------------

for (const marcador of abas.querySelectorAll("[data-icone]")) marcador.replaceWith(icone(marcador.dataset.icone));
entradaCamera.addEventListener("change", fotografar);
entradaGaleria.addEventListener("change", fotografar);
window.addEventListener("hashchange", () => {
  if (rotaAtual().nome === "") verTodas = false;
  mostrarTela();
});
mostrarTela();
