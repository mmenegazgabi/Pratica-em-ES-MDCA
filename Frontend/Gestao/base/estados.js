// Estados das telas que dependem da API: carregando, erro e acesso restrito.
//
// `carregarNaTela` é o caminho comum: mostra "Carregando…", chama a API e troca o
// conteúdo pelo resultado ou pelo estado certo do erro, com como tentar de novo.

import { API_PADRAO, ERROS, ErroApi, salvarAcesso, salvarServidor, salvarUsuario, urlDaApi, usuarioSalvo } from "./api.js";
import { el } from "./dom.js";

const campo = (id, rotulo, entrada, dica) =>
  el("div", { class: "field wide" }, el("label", { for: id }, rotulo), entrada, dica ? el("small", {}, dica) : null);

function entradaServidor() {
  const servidor = el("input", { id: "f-servidor-api", name: "servidor", type: "url", autocapitalize: "off", spellcheck: "false" });
  servidor.value = urlDaApi();
  return servidor;
}

function servidorAvancado(servidor, ...extras) {
  // Aberto quando há um servidor fora do padrão: costuma ser a causa do erro.
  return el(
    "details",
    { class: "field wide", open: urlDaApi() !== API_PADRAO },
    el("summary", {}, "Servidor (avançado)"),
    campo("f-servidor-api", "Endereço da API", servidor, "Em branco, usa a API publicada."),
    ...extras,
  );
}

export function carregando(texto = "Carregando…") {
  return el("div", { class: "estado estado--carregando", role: "status" }, el("span", { class: "estado__giro", "aria-hidden": "true" }), texto);
}

// Sem isto, um endereço errado salvo em "Servidor (avançado)" só sairia pelo console do navegador.
function trocarServidor(tentarDeNovo) {
  const servidor = entradaServidor();

  function enviar(evento) {
    evento.preventDefault();
    salvarServidor(servidor.value);
    tentarDeNovo();
  }

  return el(
    "form",
    { class: "form-grid estado__formulario estado__servidor", novalidate: true, onsubmit: enviar },
    servidorAvancado(servidor, el("button", { type: "submit", class: "btn" }, "Usar este servidor")),
  );
}

export function falha(erro, tentarDeNovo) {
  return el(
    "section",
    { class: "card estado estado--erro" },
    el(
      "div",
      { class: "empty", role: "alert" },
      el("h2", {}, "Não foi possível carregar"),
      el("p", {}, erro.message),
      // No 404 o detail é o "Not Found" genérico do FastAPI; nos outros casos ele explica a falha.
      erro.detalhe && erro.tipo !== ERROS.NAO_ENCONTRADO ? el("p", { class: "estado__detalhe" }, erro.detalhe) : null,
      el("button", { type: "button", class: "btn primary", onclick: tentarDeNovo }, "Tentar de novo"),
    ),
    trocarServidor(tentarDeNovo),
  );
}

function semPermissao(erro) {
  return el(
    "section",
    { class: "card estado estado--restrito" },
    el(
      "div",
      { class: "empty", role: "alert" },
      el("h2", {}, "Acesso restrito"),
      el("p", {}, erro.message),
      el("p", {}, "O papel, o programa e o nível de sigilo determinam o que cada pessoa pode consultar."),
    ),
  );
}

// Pede o código (401) e/ou o usuário (400 sem X-Usuario-Id). Os dois campos aparecem
// sempre; só o que causou o erro é obrigatório, e o código em branco mantém o salvo.
function pedirCodigo(erro, tentarDeNovo) {
  const pedeCodigo = erro.tipo === ERROS.NAO_AUTENTICADO;
  const codigo = el("input", { id: "f-codigo-acesso", name: "codigo", type: "password", autocomplete: "off", autocapitalize: "off", spellcheck: "false", required: pedeCodigo });
  const usuario = el("input", { id: "f-usuario", name: "usuario", type: "text", autocomplete: "username", autocapitalize: "off", spellcheck: "false", required: !pedeCodigo });
  usuario.value = usuarioSalvo();
  const servidor = entradaServidor();
  const aviso = el("p", { class: "error-message", role: "alert", hidden: true });

  function recusar(texto, campo) {
    aviso.textContent = texto;
    aviso.hidden = false;
    campo.focus();
  }

  function enviar(evento) {
    evento.preventDefault();
    if (pedeCodigo && !codigo.value.trim()) return recusar("Informe o código de acesso.", codigo);
    if (!pedeCodigo && !usuario.value.trim()) return recusar("Informe seu usuário.", usuario);
    if (codigo.value.trim()) salvarAcesso(codigo.value, servidor.value);
    else salvarServidor(servidor.value);
    salvarUsuario(usuario.value);
    tentarDeNovo();
  }

  return el(
    "section",
    { class: "card estado estado--restrito" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, "Acesso restrito"), el("small", {}, erro.message))),
    el(
      "div",
      { class: "card-body" },
      el(
        "form",
        { class: "form-grid estado__formulario", novalidate: true, onsubmit: enviar },
        campo("f-codigo-acesso", "Código de acesso", codigo, pedeCodigo ? "O mesmo código do Financeiro. Fica salvo só neste aparelho." : "Em branco, mantém o código já salvo."),
        campo("f-usuario", "Seu usuário", usuario, "Identificador da sua conta na plataforma (ex.: jessica). Fica salvo só neste aparelho."),
        servidorAvancado(servidor),
        aviso,
        el("div", { class: "field wide" }, el("button", { type: "submit", class: "btn primary" }, "Entrar e carregar")),
      ),
    ),
  );
}

const PEDE_IDENTIFICACAO = [ERROS.NAO_AUTENTICADO, ERROS.SEM_USUARIO];
export const ehRestrito = (erro) => [...PEDE_IDENTIFICACAO, ERROS.SEM_PERMISSAO].includes(erro?.tipo);

export function acessoRestrito(erro, tentarDeNovo) {
  return PEDE_IDENTIFICACAO.includes(erro.tipo) ? pedirCodigo(erro, tentarDeNovo) : semPermissao(erro);
}

/**
 * Carrega dados da API dentro de `container`: `buscar()` chama a API e `mostrar(dados)`
 * devolve o nó da tela. Se o usuário já saiu da tela quando a resposta chega, nada muda.
 */
export function carregarNaTela(container, buscar, mostrar) {
  async function tentar() {
    container.replaceChildren(carregando());
    let conteudo;
    try {
      conteudo = mostrar(await buscar());
    } catch (e) {
      const erro = e instanceof ErroApi ? e : new ErroApi(ERROS.FALHA);
      conteudo = ehRestrito(erro) ? acessoRestrito(erro, tentar) : falha(erro, tentar);
    }
    if (container.isConnected) container.replaceChildren(conteudo);
  }
  return tentar();
}
