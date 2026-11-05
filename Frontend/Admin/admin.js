// Administração de pessoas e papéis (T-35). Mesmo padrão do Financeiro: iniciar(raiz, { redirecionar }).
import { el, limpar } from "../Financeiro/base/dom.js";
import { logo } from "../Financeiro/base/logo.js";
import { encerrarSessaoLocal, lerSessao, sair, temPapel, urlDaApi } from "../Shared/plataforma.js";

const SITUACOES = {
  ativo: "Ativo",
  aguardando_primeiro_acesso: "Aguardando primeiro acesso",
  desativado: "Desativado",
};
const SEM_ACESSO = "Esta área é só da administração.";
const SEM_CONEXAO = "Sem conexão com o servidor. Tente de novo.";
const ERRO_GENERICO = "Não foi possível concluir. Tente de novo.";
const AVISO_CODIGO =
  "Este código não aparece de novo. Entregue à pessoa: ela entra em Primeiro acesso, informa o e-mail e o código e cria a senha.";

const doisDigitos = (n) => String(n).padStart(2, "0");
export function formatarValidade(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return `${doisDigitos(d.getDate())}/${doisDigitos(d.getMonth() + 1)}/${d.getFullYear()} ${doisDigitos(d.getHours())}:${doisDigitos(d.getMinutes())}`;
}

function iniciais(nome) {
  return String(nome || "").trim().split(/\s+/).slice(0, 2).map((p) => p[0]?.toUpperCase() || "").join("");
}

export function iniciar(raiz, { redirecionar = (destino) => window.location.assign(destino) } = {}) {
  const sessao = lerSessao();
  if (!sessao) return redirecionar("../");

  raiz.classList.add("admin");
  if (!temPapel(sessao, "administracao")) return limpar(raiz).append(avisoSemAcesso());

  let papeis = [];
  const principal = el("main", { class: "principal" });

  function avisoSemAcesso() {
    return el(
      "div",
      { class: "caixa admin__aviso" },
      el("p", { role: "alert" }, SEM_ACESSO),
      el("a", { href: "../" }, "Voltar ao início"),
    );
  }

  /** Chamada autenticada. Devolve {status, corpo}; status 0 = sem conexão. */
  async function chamar(metodo, caminho, corpo) {
    const atual = lerSessao();
    if (!atual) return { status: 401, corpo: null };
    const headers = { Authorization: `Bearer ${atual.token}` };
    const opcoes = { method: metodo, headers };
    if (corpo !== undefined) {
      headers["Content-Type"] = "application/json";
      opcoes.body = JSON.stringify(corpo);
    }
    let resposta;
    try {
      resposta = await fetch(`${urlDaApi()}${caminho}`, opcoes);
    } catch {
      return { status: 0, corpo: null };
    }
    let dados = null;
    try {
      dados = await resposta.json();
    } catch {
      dados = null;
    }
    if (resposta.status === 401) {
      encerrarSessaoLocal();
      redirecionar("../");
    }
    return { status: resposta.status, corpo: dados, ok: resposta.ok };
  }

  function mensagem(resposta) {
    if (resposta.status === 0) return SEM_CONEXAO;
    if (resposta.status === 403) return SEM_ACESSO;
    const detalhe = resposta.corpo?.detail;
    return typeof detalhe === "string" && detalhe ? detalhe : ERRO_GENERICO;
  }

  async function sairDaConta() {
    await sair();
    redirecionar("../");
  }

  function lateral() {
    return el(
      "aside",
      { class: "lateral" },
      el("div", { class: "lateral__marca" }, logo(), el("span", {}, "Administração")),
      el("nav", { class: "lateral__menu", "aria-label": "Seções" },
        el("a", { class: "lateral__item", href: "./", "aria-current": "page" }, "Pessoas e papéis"),
        el("a", { class: "lateral__item", href: "../" }, "Voltar ao início"),
      ),
      el(
        "div",
        { class: "lateral__usuario" },
        el(
          "div",
          { class: "lateral__pessoa" },
          el("div", { class: "lateral__avatar" }, iniciais(sessao.usuario.nome)),
          el("div", { class: "lateral__nome" }, sessao.usuario.nome, el("small", {}, sessao.usuario.email || "")),
        ),
        el("button", { type: "button", class: "lateral__trocar", onclick: sairDaConta }, "Sair"),
      ),
    );
  }

  // ---------- diálogos ----------

  function abrirDialogo(dialogo, foco) {
    raiz.append(dialogo);
    if (typeof dialogo.showModal === "function") dialogo.showModal();
    else dialogo.setAttribute("open", "");
    foco?.focus();
  }

  function dialogoBase(titulo, ...filhos) {
    const dialogo = el("dialog", { class: "dialogo", "aria-label": titulo });
    dialogo.addEventListener("cancel", () => dialogo.remove());
    dialogo.append(...filhos);
    return dialogo;
  }

  function caixasDePapeis(marcados = []) {
    return el(
      "div",
      { class: "admin__papeis" },
      papeis.map((p) =>
        el("label", {}, el("input", { type: "checkbox", name: "papel", value: p.id, checked: marcados.includes(p.id) }), p.nome),
      ),
    );
  }
  const papeisMarcados = (dialogo) => [...dialogo.querySelectorAll('input[name="papel"]:checked')].map((i) => i.value);

  function campo(rotulo, entrada) {
    return el("div", { class: "campo" }, el("label", { for: entrada.id }, rotulo), entrada);
  }

  function rodape(dialogo, rotuloSalvar) {
    const cancelar = el("button", { type: "button", class: "btn btn--sec", onclick: () => dialogo.remove() }, "Cancelar");
    const salvar = el("button", { type: "submit", class: "btn" }, rotuloSalvar);
    return { cancelar, salvar, no: el("div", { class: "admin__rodape" }, cancelar, salvar) };
  }

  function mostrarCodigo(titulo, nome, codigo, expiraEm) {
    const copiar = el("button", { type: "button", class: "btn btn--sec" }, "Copiar");
    copiar.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(codigo);
        copiar.textContent = "Copiado";
      } catch {
        copiar.textContent = "Não foi possível copiar";
      }
    });
    const dialogo = dialogoBase(titulo);
    dialogo.append(
      el("h2", { style: "font-size:15px;margin:0 0 4px" }, titulo),
      el("p", { class: "admin__ajuda", style: "margin:0" }, nome),
      el("div", { class: "admin__codigo" }, codigo),
      el("p", { class: "admin__ajuda" }, `Vale até ${formatarValidade(expiraEm)}.`),
      el("p", { class: "admin__ajuda" }, AVISO_CODIGO),
      el(
        "div",
        { class: "admin__rodape" },
        copiar,
        el("button", { type: "button", class: "btn", onclick: () => dialogo.remove() }, "Fechar"),
      ),
    );
    return dialogo;
  }

  function dialogoCadastro() {
    const nome = el("input", { id: "adm-nome", name: "nome", class: "entrada", type: "text", autocomplete: "off" });
    const email = el("input", { id: "adm-email", name: "email", class: "entrada", type: "email", autocomplete: "off", autocapitalize: "off" });
    const erro = el("p", { class: "admin__erro", role: "alert", hidden: true });
    const form = el("form", { novalidate: true });
    const dialogo = dialogoBase("Cadastrar pessoa", form);
    const rod = rodape(dialogo, "Cadastrar");
    form.append(
      el("h2", { style: "font-size:15px;margin:0 0 4px" }, "Cadastrar pessoa"),
      campo("Nome", nome),
      campo("E-mail", email),
      el("div", { class: "campo" }, el("span", { class: "campo__rotulo" }, "Papéis"), caixasDePapeis()),
      erro,
      rod.no,
    );
    const falha = (texto) => {
      erro.textContent = texto;
      erro.hidden = !texto;
    };
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const dados = { nome: nome.value.trim(), email: email.value.trim(), papeis: papeisMarcados(dialogo) };
      if (!dados.nome) return falha("Informe o nome.");
      if (!dados.email) return falha("Informe o e-mail.");
      if (!dados.papeis.length) return falha("Escolha ao menos um papel.");
      falha("");
      rod.salvar.disabled = true;
      rod.cancelar.disabled = true;
      const resposta = await chamar("POST", "/admin/usuarios", dados);
      if (resposta.status !== 201 || !resposta.corpo?.codigo) {
        rod.salvar.disabled = false;
        rod.cancelar.disabled = false;
        return falha(mensagem(resposta));
      }
      dialogo.remove();
      abrirDialogo(mostrarCodigo("Pessoa cadastrada", dados.nome, resposta.corpo.codigo, resposta.corpo.codigo_expira_em));
      carregarLista();
    });
    return { dialogo, foco: nome };
  }

  function dialogoEdicao(pessoa) {
    const nome = el("input", { id: "adm-nome", name: "nome", class: "entrada", type: "text", autocomplete: "off" });
    nome.value = pessoa.nome;
    const ativo = el("input", { type: "checkbox", name: "ativo", checked: pessoa.ativo });
    const erro = el("p", { class: "admin__erro", role: "alert", hidden: true });
    const form = el("form", { novalidate: true });
    const dialogo = dialogoBase("Editar pessoa", form);
    const rod = rodape(dialogo, "Salvar");
    const idsAtuais = pessoa.papeis.map((p) => p.id);
    form.append(
      el("h2", { style: "font-size:15px;margin:0 0 4px" }, "Editar pessoa"),
      el("p", { class: "admin__ajuda", style: "margin:0" }, pessoa.email),
      campo("Nome", nome),
      el("div", { class: "campo" }, el("span", { class: "campo__rotulo" }, "Papéis"), caixasDePapeis(idsAtuais)),
      el("div", { class: "admin__papeis", style: "margin-top:14px" }, el("label", {}, ativo, "Conta ativa")),
      erro,
      rod.no,
    );
    const falha = (texto) => {
      erro.textContent = texto;
      erro.hidden = !texto;
    };
    form.addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const mudancas = {};
      const novoNome = nome.value.trim();
      if (!novoNome) return falha("Informe o nome.");
      if (novoNome !== pessoa.nome) mudancas.nome = novoNome;
      const novosPapeis = papeisMarcados(dialogo);
      if (!novosPapeis.length) return falha("Escolha ao menos um papel.");
      if ([...novosPapeis].sort().join() !== [...idsAtuais].sort().join()) mudancas.papeis = novosPapeis;
      if (ativo.checked !== pessoa.ativo) mudancas.ativo = ativo.checked;
      if (!Object.keys(mudancas).length) return dialogo.remove();
      falha("");
      rod.salvar.disabled = true;
      rod.cancelar.disabled = true;
      const resposta = await chamar("PATCH", `/admin/usuarios/${encodeURIComponent(pessoa.id)}`, mudancas);
      if (resposta.status !== 200) {
        rod.salvar.disabled = false;
        rod.cancelar.disabled = false;
        return falha(mensagem(resposta));
      }
      dialogo.remove();
      carregarLista();
    });
    return { dialogo, foco: nome };
  }

  async function gerarCodigo(pessoa) {
    const resposta = await chamar("POST", `/admin/usuarios/${encodeURIComponent(pessoa.id)}/codigo`);
    if (resposta.status === 200 && resposta.corpo?.codigo) {
      abrirDialogo(mostrarCodigo("Novo código", pessoa.nome, resposta.corpo.codigo, resposta.corpo.codigo_expira_em));
      carregarLista();
      return;
    }
    const fechar = el("button", { type: "button", class: "btn", onclick: () => dialogo.remove() }, "Fechar");
    const dialogo = dialogoBase("Não foi possível gerar o código", el("p", { class: "admin__erro", role: "alert", style: "margin:0 0 12px" }, mensagem(resposta)), el("div", { class: "admin__rodape" }, fechar));
    abrirDialogo(dialogo, fechar);
  }

  function abrir({ dialogo, foco }) {
    abrirDialogo(dialogo, foco);
  }

  // ---------- lista ----------

  function cabecalho() {
    return el(
      "div",
      { class: "admin__topo" },
      el("div", {}, el("h1", {}, "Pessoas e papéis"), el("p", { class: "sub" }, "Quem entra na plataforma e o que cada pessoa pode acessar.")),
      el("div", { class: "admin__acoes" }, el("button", { type: "button", class: "btn", onclick: () => abrir(dialogoCadastro()) }, "Cadastrar pessoa")),
    );
  }

  function tabela(pessoas) {
    if (!pessoas.length) return el("p", { class: "aviso-tela" }, "Nenhuma pessoa cadastrada ainda.");
    return el(
      "div",
      { class: "caixa admin__tabela" },
      el(
        "table",
        { class: "tabela" },
        el("thead", {}, el("tr", {}, ["Nome", "E-mail", "Papéis", "Situação", "Ações"].map((t) => el("th", {}, t)))),
        el(
          "tbody",
          {},
          pessoas.map((p) =>
            el(
              "tr",
              {},
              el("td", {}, p.nome),
              el("td", {}, p.email),
              el("td", {}, p.papeis.map((x) => x.nome).join(", ")),
              el("td", { class: `admin__situacao--${p.situacao}` }, SITUACOES[p.situacao] || p.situacao),
              el(
                "td",
                {},
                el(
                  "div",
                  { class: "admin__acoes" },
                  el("button", { type: "button", class: "btn btn--sec btn--pequeno", onclick: () => abrir(dialogoEdicao(p)) }, "Editar"),
                  p.situacao === "desativado"
                    ? null
                    : el("button", { type: "button", class: "btn btn--sec btn--pequeno", onclick: () => gerarCodigo(p) }, "Gerar código"),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  let vez = 0;
  async function carregarLista() {
    vez += 1;
    const minha = vez;
    const [lista, catalogo] = await Promise.all([chamar("GET", "/admin/usuarios"), chamar("GET", "/gestao/papeis")]);
    if (minha !== vez) return;
    if (lista.status === 401 || catalogo.status === 401) return;
    limpar(principal);
    if (lista.status === 403) {
      principal.append(avisoSemAcesso());
      return;
    }
    principal.append(cabecalho());
    if (lista.status !== 200 || !Array.isArray(lista.corpo)) {
      principal.append(el("p", { class: "admin__erro", role: "alert" }, mensagem(lista)));
      return;
    }
    if (catalogo.status === 200 && Array.isArray(catalogo.corpo)) papeis = catalogo.corpo;
    principal.append(tabela(lista.corpo));
  }

  limpar(raiz).append(lateral(), principal);
  principal.append(el("p", { class: "carregando" }, "Carregando…"));
  carregarLista();
}
