// Computador: barra lateral por papel, rotas por hash e carga de cada tela em telas/<tela>.js.
import { el, limpar } from "./base/dom.js";
import { logo } from "./base/logo.js";
import { icone } from "./base/icones.js";
import { lerRota, rotaPermitida } from "./base/rotas.js";
import { contadorDefinido, reaplicarContador } from "./base/contador.js";
import { atualizarContadorDePendencias } from "./telas/inicio.js";
import { PAPEIS, escolherPapel, itensDeMenu, lerSessao, papeisDoFinanceiro } from "./base/sessao.js";
import { atualizarUsuario, lerSessao as lerSessaoDaPlataforma, sair as sairDaPlataforma } from "../Shared/plataforma.js";

const INICIO_DA_PLATAFORMA = "../";

export { definirContador } from "./base/contador.js";

function iniciais(nome) {
  return nome.trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("");
}

/** Monta o aplicativo dentro de `raiz`; `redirecionar` leva à página inicial ou ao app do celular. */
export function iniciar(raiz, { redirecionar = (destino) => window.location.assign(destino) } = {}) {
  let vez = 0;

  const navegar = (hash) => {
    if (window.location.hash === hash) mostrarTela();
    else window.location.hash = hash;
  };

  async function sair() {
    await sairDaPlataforma();
    redirecionar(INICIO_DA_PLATAFORMA);
  }

  function barraLateral(sessao, tela, variosPapeis) {
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
        variosPapeis ? el("button", { type: "button", class: "lateral__trocar", onclick: () => navegar("#/papel") }, "Trocar papel") : null,
        el("button", { type: "button", class: "lateral__trocar", onclick: sair }, "Sair"),
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

  function telaSemAcesso() {
    limpar(raiz).append(
      el(
        "section",
        { class: "acesso" },
        el("h1", {}, "Financeiro"),
        el("p", { class: "ajuda" }, "Seu perfil não tem acesso ao Financeiro."),
        el("a", { class: "btn btn--sec", href: INICIO_DA_PLATAFORMA }, "Voltar ao início"),
      ),
    );
  }

  function telaEntrarComo(papeis, tela) {
    const escolher = (papel) => {
      escolherPapel(papel);
      if (tela === "papel") navegar("#/inicio");
      else mostrarTela();
    };
    limpar(raiz).append(
      el(
        "section",
        { class: "acesso" },
        el("h1", {}, "Entrar como"),
        el("p", { class: "ajuda" }, "Escolha com qual papel usar o Financeiro."),
        el(
          "div",
          { class: "acesso__papeis" },
          papeis.map((papel) => el("button", { type: "button", class: "btn btn--sec", onclick: () => escolher(papel) }, PAPEIS[papel])),
        ),
      ),
    );
  }

  function mostrarTela() {
    vez += 1;
    const minhaVez = vez;
    const plataforma = lerSessaoDaPlataforma();
    if (!plataforma) return redirecionar(INICIO_DA_PLATAFORMA);
    const papeis = papeisDoFinanceiro(plataforma);
    if (!papeis.length) return telaSemAcesso();

    const sessao = lerSessao();
    const { tela, parametros } = lerRota(window.location.hash);
    const variosPapeis = papeis.length > 1;

    if (!sessao.papel || (tela === "papel" && variosPapeis)) return telaEntrarComo(papeis, tela);
    if (sessao.papel === "educador") return redirecionar("lancamento/");
    if (tela === "papel" || !rotaPermitida(tela, sessao.papel)) return navegar("#/inicio");

    const container = el("main", { class: "principal" }, el("p", { class: "carregando", role: "status" }, "Carregando…"));
    limpar(raiz).append(barraLateral(sessao, tela, variosPapeis), container);
    reaplicarContador();
    if (!contadorDefinido() && tela !== "inicio" && tela !== "lancamentos") atualizarContadorDePendencias(sessao.papel);
    return carregarTela(container, tela, parametros, sessao, minhaVez);
  }

  /** Papéis dados ou tirados pela administração desde o login valem ao abrir a página. */
  async function conferirPessoa() {
    const antes = lerSessaoDaPlataforma();
    if (!antes) return;
    const atual = await atualizarUsuario();
    if (!atual) return redirecionar(INICIO_DA_PLATAFORMA); // 401: sessão apagada
    if (JSON.stringify(atual.usuario) !== JSON.stringify(antes.usuario)) mostrarTela();
  }

  window.addEventListener("hashchange", mostrarTela);
  const primeira = mostrarTela();
  conferirPessoa();
  return primeira;
}

const raiz = typeof document !== "undefined" ? document.getElementById("app") : null;
if (raiz) iniciar(raiz);
