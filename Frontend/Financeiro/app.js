// Computador: barra lateral por papel, rotas por hash e carga de cada tela em telas/<tela>.js.
import { el, limpar } from "./base/dom.js";
import { logo } from "./base/logo.js";
import { icone } from "./base/icones.js";
import { lerRota, rotaPermitida } from "./base/rotas.js";
import { contadorDefinido, reaplicarContador } from "./base/contador.js";
import { atualizarContadorDePendencias } from "./telas/inicio.js";
import { PAPEIS, lerSessao, salvarSessao, encerrarSessao, itensDeMenu } from "./base/sessao.js";
import { API_PADRAO, esquecerAcesso, salvarAcesso, tokenSalvo, urlDaApi } from "./base/api.js";

export { definirContador } from "./base/contador.js";

const PAPEIS_DO_COMPUTADOR = ["coordenacao", "direcao", "voluntario_financeiro"];

function iniciais(nome) {
  return nome.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("");
}

/** Monta o aplicativo dentro de `raiz`; `redirecionar` leva o educador ao app do celular. */
export function iniciar(raiz, { redirecionar = (destino) => window.location.assign(destino) } = {}) {
  let vez = 0;

  const navegar = (hash) => {
    if (window.location.hash === hash) mostrarTela();
    else window.location.hash = hash;
  };

  function sair() {
    encerrarSessao();
    esquecerAcesso();
    navegar("#/entrar");
  }

  function barraLateral(sessao, tela) {
    const ativo = tela === "projeto" ? "projetos" : tela;
    const itens = itensDeMenu(sessao.papel).map((item) =>
      el(
        "a",
        { class: "lateral__item", href: item.rota, "aria-current": item.id === ativo ? "page" : false },
        icone(item.icone),
        item.rotulo,
        item.id === "inicio" ? el("span", { class: "lateral__contador", "data-contador": true, hidden: true }, "0") : null,
      ),
    );
    return el(
      "aside",
      { class: "lateral" },
      el("div", { class: "lateral__marca" }, logo(), el("span", {}, "Finanças")),
      el("nav", { class: "lateral__menu", "aria-label": "Seções" }, itens),
      el(
        "div",
        { class: "lateral__usuario" },
        el(
          "div",
          { class: "lateral__pessoa" },
          el("div", { class: "lateral__avatar" }, iniciais(sessao.nome)),
          el("div", { class: "lateral__nome" }, sessao.nome, el("small", {}, PAPEIS[sessao.papel])),
        ),
        el("button", { type: "button", class: "lateral__trocar", onclick: sair }, "Trocar perfil"),
      ),
    );
  }

  async function carregarTela(container, tela, parametros, sessao, minhaVez) {
    let modulo;
    try {
      modulo = await import(`./telas/${tela}.js`);
    } catch {
      if (minhaVez === vez) limpar(container).append(el("p", { class: "aviso-tela" }, "Esta tela ainda não está disponível."));
      return;
    }
    try {
      await modulo.mostrar(container, { parametros, sessao, navegar });
    } catch {
      if (minhaVez === vez) limpar(container).append(el("p", { class: "aviso-tela" }, "Não foi possível abrir esta tela. Tente de novo."));
    }
  }

  function telaEntrar(mensagem = "") {
    const nome = el("input", { id: "campo-nome", class: "entrada", type: "text", autocomplete: "name", required: true });
    const papel = el(
      "select",
      { id: "campo-papel", class: "entrada" },
      PAPEIS_DO_COMPUTADOR.map((id) => el("option", { value: id }, PAPEIS[id])),
    );
    const token = el("input", { id: "campo-token", class: "entrada", type: "password", autocomplete: "off", autocapitalize: "off", spellcheck: "false", required: true });
    const api = el("input", { id: "campo-api", class: "entrada", type: "url", autocapitalize: "off", spellcheck: "false" });
    api.value = urlDaApi();
    const erro = el("p", { id: "erro-acesso", class: "erro", role: "alert", hidden: !mensagem }, mensagem);
    const campo = (rotulo, entrada) => el("div", { class: "campo" }, el("label", { for: entrada.id }, rotulo), entrada);

    function entrar(evento) {
      evento.preventDefault();
      const falta = !nome.value.trim() ? "Informe seu nome." : !token.value.trim() ? "Informe o código de acesso." : "";
      if (falta) {
        erro.textContent = falta;
        erro.hidden = false;
        return;
      }
      salvarSessao({ papel: papel.value, nome: nome.value.trim() });
      salvarAcesso(token.value, api.value || API_PADRAO);
      navegar("#/inicio");
    }

    limpar(raiz).append(
      el(
        "form",
        { id: "form-entrar", class: "entrar", novalidate: true, onsubmit: entrar },
        el("h1", {}, "Entrar"),
        el("p", { class: "ajuda" }, "Informe seu nome, seu papel e o código de acesso do Financeiro. Eles ficam salvos só neste computador."),
        campo("Seu nome", nome),
        campo("Papel", papel),
        campo("Código de acesso", token),
        el("details", { class: "avancado" }, el("summary", {}, "Servidor (avançado)"), campo("Endereço da API", api)),
        erro,
        el("button", { type: "submit", class: "btn" }, "Entrar"),
      ),
    );
    nome.focus();
  }

  function mostrarTela() {
    vez += 1;
    const minhaVez = vez;
    const sessao = lerSessao();
    const { tela, parametros } = lerRota(window.location.hash);

    if (sessao?.papel === "educador") return redirecionar("lancamento/");
    if (!sessao || !tokenSalvo()) {
      if (tela !== "entrar") return navegar("#/entrar");
      return telaEntrar();
    }
    if (tela === "entrar") return navegar("#/inicio");
    if (!rotaPermitida(tela, sessao.papel)) return navegar("#/inicio");

    const container = el("main", { class: "principal" }, el("p", { class: "carregando", role: "status" }, "Carregando…"));
    limpar(raiz).append(barraLateral(sessao, tela), container);
    reaplicarContador();
    if (!contadorDefinido() && tela !== "inicio" && tela !== "lancamentos") atualizarContadorDePendencias(sessao.papel);
    return carregarTela(container, tela, parametros, sessao, minhaVez);
  }

  window.addEventListener("hashchange", mostrarTela);
  return mostrarTela();
}

const raiz = typeof document !== "undefined" ? document.getElementById("app") : null;
if (raiz) iniciar(raiz);
