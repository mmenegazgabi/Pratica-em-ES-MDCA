// Pessoas e famílias ligadas à API da T-48 (T-49 · US-03): lista, cadastro em etapas com
// revisão e perfil da pessoa com trajetória, família, documentos e autorizações.
//
// Quem decide o acesso é a API: lista só os programas em que a pessoa usuária atua,
// e cadastro e alterações só para coordenação e serviço social do programa (e a
// administração). Os botões aparecem conforme o perfil, e uma recusa da API aparece
// na própria tela.
//
// O cadastro confere duas regras antes de concluir, e a API confere de novo:
// - **possível duplicidade:** a revisão consulta a API e, se houver semelhantes, pede
//   a confirmação explícita de que é outra pessoa;
// - **responsável legal:** menor de 18 anos sem responsável legal não é concluído.
//
// Documentos (T-88): o arquivo vai para o armazenamento privado (R2) e pode ser baixado por
// quem vê o cadastro; cada download fica na trilha de auditoria. Registros antigos, de
// antes do envio do arquivo, aparecem sem "Baixar".

import * as api from "../base/api.js";
import { ErroApi } from "../base/api.js";
import { carregando, carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { abrirFormulario, campo, hojeIso, selecao } from "../base/formulario.js";
import { validarArquivo } from "./atividades.js";

const API_PADRAO = {
  listarPessoas: api.listarPessoas,
  listarProgramas: api.listarProgramas,
  obterPessoa: api.obterPessoa,
  obterTrajetoria: api.obterTrajetoria,
  verificarDuplicidade: api.verificarDuplicidade,
  cadastrarPessoa: api.cadastrarPessoa,
  incluirResponsavel: api.incluirResponsavel,
  registrarDocumento: api.registrarDocumento,
  baixarDocumento: api.baixarDocumento,
  registrarAutorizacao: api.registrarAutorizacao,
  revogarAutorizacao: api.revogarAutorizacao,
  buscarNucleos: api.buscarNucleos,
};

export const MAIORIDADE = 18;
export const TIPOS_DE_DOCUMENTO = ["Certidão de nascimento", "Documento de identidade", "CPF", "Comprovante de residência", "Cartão de vacinação", "Outro"];

const IMAGEM = {
  vigente: ["Autorização vigente", "green"],
  vencida: ["Autorização vencida", "amber"],
  revogada: ["Autorização revogada", "amber"],
  sem_autorizacao: ["Sem autorização", "gray"],
};
const MOTIVOS = { nascimento: "mesma data de nascimento", responsavel: "mesmo responsável" };

// --- Apoio ---------------------------------------------------------------------------

export const dataBr = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");

/** Idade em anos completos na data `hoje` (AAAA-MM-DD). */
export function idade(nascimento, hoje = hojeIso()) {
  const [a, m, d] = nascimento.split("-").map(Number);
  const [ha, hm, hd] = hoje.split("-").map(Number);
  return ha - a - (hm < m || (hm === m && hd < d) ? 1 : 0);
}

export const precisaDeResponsavelLegal = (nascimento, responsaveis, hoje = hojeIso()) =>
  Boolean(nascimento) && idade(nascimento, hoje) < MAIORIDADE && !responsaveis.some((r) => r.responsavel_legal);

const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const imagem = (situacao) => badge(...(IMAGEM[situacao] || IMAGEM.sem_autorizacao));
const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const aviso = (texto, tom = "") => el("div", { class: `info-box ${tom}`.trim() }, el("span", {}, texto));
const motivoDoErro = (erro) => (erro instanceof ErroApi ? erro.detalhe || erro.message : "Não foi possível salvar. Tente de novo.");

function cartao(titulo, subtitulo, corpo, acao = null) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), acao),
    el("div", { class: "card-body" }, corpo),
  );
}

function tabela(cabecalhos, linhas) {
  return el(
    "div",
    { class: "table-wrap" },
    el("table", {}, el("thead", {}, el("tr", {}, cabecalhos.map((c) => el("th", { scope: "col" }, c)))), el("tbody", {}, linhas)),
  );
}

function detalhes(pares) {
  return el(
    "dl",
    { class: "details" },
    pares.map(([rotulo, valor]) => el("div", {}, el("dt", {}, rotulo), el("dd", {}, valor || "Não informado"))),
  );
}

const entrada = (nome, tipo = "text", valor = "", extras = {}) => {
  const no = el("input", { name: nome, type: tipo, ...extras });
  no.value = valor ?? "";
  return no;
};

// --- Lista ---------------------------------------------------------------------------

function linhaDaPessoa(p) {
  return el(
    "tr",
    {},
    el("td", {}, el("a", { class: "activity-title", href: `#/pessoas/${encodeURIComponent(p.id)}` }, p.nome), el("small", {}, `Nascimento: ${dataBr(p.data_nascimento)}`)),
    el("td", {}, badge(p.programa, "gray")),
    el("td", {}, p.nucleo_familiar.nome, el("small", {}, p.responsaveis.join(", ") || "Sem responsável informado")),
    el("td", {}, imagem(p.autorizacao_imagem)),
  );
}

export function tabelaDePessoas(pessoas, { filtrado = false } = {}) {
  if (!pessoas.length) {
    return el(
      "section",
      { class: "card" },
      filtrado
        ? vazio("Nenhuma pessoa encontrada", "Tente outro nome ou outro programa.")
        : vazio("Nenhuma pessoa cadastrada", "As pessoas atendidas pelos programas em que você atua aparecem aqui."),
    );
  }
  return el("section", { class: "card" }, tabela(["Pessoa atendida", "Programa", "Núcleo familiar", "Uso de imagem"], pessoas.map(linhaDaPessoa)));
}

/** Lista com busca por nome e filtro de programa; cada busca é uma consulta à API. */
export function mostrarPessoas(container, substitutos = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const filtros = { programaId: "", busca: "" };
  const resultado = el("div", {});
  const busca = entrada("busca", "search", "", { class: "filter-control", placeholder: "Buscar pelo nome", "aria-label": "Buscar pessoa pelo nome" });
  const programa = el("select", { name: "programa", class: "filter-control", "aria-label": "Filtrar programa" }, el("option", { value: "" }, "Todos os programas"));

  function consultar() {
    const filtrado = Boolean(filtros.programaId || filtros.busca.trim());
    return carregarNaTela(resultado, () => chamadas.listarPessoas({ ...filtros }), (pessoas) => tabelaDePessoas(pessoas, { filtrado }));
  }

  function enviar(evento) {
    evento.preventDefault();
    evento.stopPropagation();
    filtros.busca = busca.value;
    filtros.programaId = programa.value;
    return consultar();
  }

  const barra = el(
    "form",
    { class: "toolbar pessoas-filtros", role: "search", novalidate: true, onsubmit: enviar },
    el("div", { class: "filters" }, programa, busca, el("button", { type: "submit", class: "btn" }, "Buscar")),
  );
  programa.addEventListener("change", () => {
    filtros.programaId = programa.value;
    filtros.busca = busca.value;
    consultar();
  });
  container.replaceChildren(barra, resultado);

  // A lista de programas só enche o filtro; se falhar, a lista de pessoas segue igual.
  chamadas
    .listarProgramas()
    .then((programas) => programa.append(...programas.map((p) => el("option", { value: p.id }, p.nome))))
    .catch(() => {});
  return consultar();
}

// --- Cadastro em etapas --------------------------------------------------------------

// Mesmos tipos e limite das evidências (T-56) e dos comprovantes do Financeiro.
const ACEITOS = "image/*,.pdf";

const ETAPAS = ["Dados pessoais", "Família", "Documentos e autorizações", "Revisão"];

function etapas(atual) {
  return el(
    "div",
    { class: "stepper" },
    ETAPAS.map((nome, i) => el("div", { class: i + 1 === atual ? "step active" : "step", "aria-current": i + 1 === atual ? "step" : null }, el("b", {}, i + 1 < atual ? "✓" : String(i + 1)), nome)),
  );
}

export function novoRascunho(programaId = "", hoje = hojeIso()) {
  return {
    passo: 1,
    nome: "",
    data_nascimento: "",
    programa_id: programaId,
    telefone: "",
    observacao: "",
    nucleo_id: "",
    nucleo_nome: "",
    responsaveis: [],
    documentos: [],
    autorizacao: { registrar: false, valida_de: hoje, valida_ate: "" },
    duplicados: null,
    confirmou: false,
  };
}

/** Corpo do POST /gestao/pessoas (e, sem os extras, do POST de duplicidades). */
export function corpoDoCadastro(r) {
  const responsaveis = r.responsaveis.map((x) => ({
    nome: x.nome.trim(),
    parentesco: x.parentesco.trim() || null,
    telefone: x.telefone.trim() || null,
    responsavel_legal: x.responsavel_legal,
  }));
  return {
    programa_id: r.programa_id,
    nome: r.nome.trim(),
    data_nascimento: r.data_nascimento,
    responsaveis,
    nucleo_familiar_id: r.nucleo_id || null,
    nucleo_familiar_nome: r.nucleo_id ? null : r.nucleo_nome.trim(),
    telefone: r.telefone.trim() || null,
    observacao: r.observacao.trim() || null,
    confirmar_duplicidade: Boolean(r.duplicados?.length && r.confirmou),
  };
}

/** Problema que impede sair da etapa (ou vazio). */
export function validarEtapa(r, passo, hoje = hojeIso()) {
  if (passo === 1) {
    if (!r.nome.trim()) return "Informe o nome completo.";
    if (!r.data_nascimento) return "Informe a data de nascimento.";
    if (r.data_nascimento > hoje) return "A data de nascimento não pode estar no futuro.";
    if (!r.programa_id) return "Escolha o programa.";
  }
  if (passo === 2) {
    if (!r.nucleo_id && !r.nucleo_nome.trim()) return "Informe o núcleo familiar.";
    if (r.responsaveis.some((x) => !x.nome.trim())) return "Informe o nome de cada responsável (ou remova a linha vazia).";
    if (precisaDeResponsavelLegal(r.data_nascimento, r.responsaveis, hoje)) {
      return "Pessoa com menos de 18 anos precisa de ao menos um responsável legal.";
    }
  }
  if (passo === 3 && r.autorizacao.registrar) {
    if (!r.autorizacao.valida_ate) return "Informe até quando a autorização de imagem vale.";
    if (r.autorizacao.valida_de && r.autorizacao.valida_ate < r.autorizacao.valida_de) return "O fim da autorização não pode ser anterior ao início.";
  }
  return "";
}

/**
 * Cadastro em quatro etapas. `aoConcluir(pessoa, pendencias)` recebe a pessoa criada e
 * o que não pôde ser gravado depois dela (documentos, autorização), para avisar.
 */
export function mostrarCadastroDePessoa(container, { programaInicial = "", aoConcluir = () => {}, hoje = hojeIso(), ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const r = novoRascunho(programaInicial, hoje);
  let programas = [];
  let nucleos = [];
  // O assistente desenha aqui dentro, depois que programas e núcleos carregam.
  const alvo = el("div", {});

  const erro = el("div", { class: "error-message", role: "alert", hidden: true });
  function mostrarErro(texto) {
    erro.textContent = texto;
    erro.hidden = !texto;
    if (texto) erro.scrollIntoView?.({ block: "nearest" });
  }

  // --- Etapa 1
  function dadosPessoais() {
    const nome = entrada("nome", "text", r.nome, { required: true, autocomplete: "off" });
    const nascimento = entrada("data_nascimento", "date", r.data_nascimento, { required: true, max: hoje });
    const programa = selecao("programa_id", programas.map((p) => [p.id, p.nome]));
    programa.value = r.programa_id;
    const telefone = entrada("telefone", "tel", r.telefone);
    const observacao = el("textarea", { name: "observacao", rows: 3 });
    observacao.value = r.observacao;
    const ler = () => Object.assign(r, { nome: nome.value, data_nascimento: nascimento.value, programa_id: programa.value, telefone: telefone.value, observacao: observacao.value });
    return {
      ler,
      campos: [
        campo("pessoa-nome", "Nome completo", nome, { largo: true }),
        campo("pessoa-nascimento", "Data de nascimento", nascimento),
        campo("pessoa-programa", "Programa", programa),
        campo("pessoa-telefone", "Telefone de contato", telefone),
        campo("pessoa-observacao", "Observação cadastral", observacao, { largo: true }),
      ],
    };
  }

  // --- Etapa 2
  function familia() {
    const nucleo = el(
      "select",
      { name: "nucleo_id" },
      el("option", { value: "" }, "Novo núcleo familiar"),
      nucleos.map((n) => el("option", { value: n.id }, n.nome)),
    );
    nucleo.value = r.nucleo_id;
    const nomeDoNucleo = entrada("nucleo_nome", "text", r.nucleo_nome || r.nome.trim().split(/\s+/).at(-1) || "");
    const campoNome = campo("pessoa-nucleo-nome", "Nome do novo núcleo", nomeDoNucleo, { dica: "Por exemplo, o sobrenome da família." });
    const alternar = () => (campoNome.hidden = Boolean(nucleo.value));
    nucleo.addEventListener("change", alternar);
    alternar();

    const lista = el("div", { class: "pessoa-responsaveis wide" });
    const linhas = [];
    function linha(resp) {
      const nome = entrada("responsavel_nome", "text", resp.nome, { "aria-label": "Nome do responsável" });
      const parentesco = entrada("responsavel_parentesco", "text", resp.parentesco, { "aria-label": "Parentesco", placeholder: "Parentesco" });
      const telefone = entrada("responsavel_telefone", "tel", resp.telefone, { "aria-label": "Telefone do responsável", placeholder: "Telefone" });
      const legal = el("input", { type: "checkbox", name: "responsavel_legal", "aria-label": "Responsável legal" });
      legal.checked = resp.responsavel_legal;
      const item = { ler: () => ({ nome: nome.value, parentesco: parentesco.value, telefone: telefone.value, responsavel_legal: legal.checked }) };
      const no = el(
        "div",
        { class: "pessoa-responsavel" },
        nome,
        parentesco,
        telefone,
        el("label", { class: "check-row" }, legal, " Responsável legal"),
        el("button", { type: "button", class: "btn small", onclick: () => { linhas.splice(linhas.indexOf(item), 1); no.remove(); } }, "Remover"),
      );
      linhas.push(item);
      lista.append(no);
    }
    r.responsaveis.forEach(linha);
    const adicionar = el("button", { type: "button", class: "btn small", onclick: () => linha({ nome: "", parentesco: "", telefone: "", responsavel_legal: false }) }, "+ Adicionar responsável");
    if (!r.responsaveis.length) linha({ nome: "", parentesco: "", telefone: "", responsavel_legal: true });

    const menor = r.data_nascimento && idade(r.data_nascimento, hoje) < MAIORIDADE;
    const ler = () => {
      r.nucleo_id = nucleo.value;
      r.nucleo_nome = nucleo.value ? "" : nomeDoNucleo.value;
      // Linhas totalmente vazias são ignoradas; meio preenchidas a validação recusa.
      r.responsaveis = linhas.map((l) => l.ler()).filter((x) => x.nome.trim() || x.parentesco.trim() || x.telefone.trim());
    };
    return {
      ler,
      campos: [
        campo("pessoa-nucleo", "Núcleo familiar", nucleo, { dica: nucleos.length ? "Escolha um núcleo já cadastrado ou crie um novo." : "" }),
        campoNome,
        el(
          "div",
          { class: "field wide" },
          el("span", { class: "field-label" }, "Responsáveis"),
          menor ? aviso("Menor de 18 anos: marque ao menos um responsável legal.", "amber") : null,
          lista,
          adicionar,
        ),
      ],
    };
  }

  // --- Etapa 3
  function documentosEAutorizacao() {
    const lista = el("div", { class: "wide" });
    function desenharLista() {
      lista.replaceChildren(
        ...r.documentos.map((d, i) =>
          el(
            "div",
            { class: "file-item" },
            el("span", {}, `${d.tipo} · ${d.nome_arquivo}`),
            el("button", { type: "button", class: "btn small", onclick: () => { r.documentos.splice(i, 1); desenharLista(); } }, "Remover"),
          ),
        ),
      );
    }
    desenharLista();
    const tipo = selecao("documento_tipo", TIPOS_DE_DOCUMENTO.map((t) => [t, t]), { vazio: "Tipo do documento" });
    const arquivo = el("input", { type: "file", name: "documento_arquivo", accept: ACEITOS, "aria-label": "Arquivo do documento" });
    const incluir = el(
      "button",
      {
        type: "button",
        class: "btn small",
        onclick: () => {
          const escolhido = arquivo.files?.[0];
          if (!tipo.value || !escolhido) return mostrarErro("Escolha o tipo e o arquivo do documento.");
          const problema = validarArquivo(escolhido);
          if (problema) return mostrarErro(problema);
          mostrarErro("");
          r.documentos.push({ tipo: tipo.value, nome_arquivo: escolhido.name, tamanho: escolhido.size, arquivo: escolhido });
          arquivo.value = "";
          tipo.value = "";
          desenharLista();
        },
      },
      "Adicionar documento",
    );

    const registrar = el("input", { type: "checkbox", name: "autorizacao_registrar" });
    registrar.checked = r.autorizacao.registrar;
    const de = entrada("autorizacao_de", "date", r.autorizacao.valida_de);
    const ate = entrada("autorizacao_ate", "date", r.autorizacao.valida_ate);
    const datas = el("div", { class: "form-grid wide" }, campo("pessoa-autorizacao-de", "Válida a partir de", de), campo("pessoa-autorizacao-ate", "Válida até", ate));
    const alternar = () => (datas.hidden = !registrar.checked);
    registrar.addEventListener("change", alternar);
    alternar();

    const ler = () => {
      r.autorizacao = { registrar: registrar.checked, valida_de: de.value, valida_ate: ate.value };
    };
    return {
      ler,
      campos: [
        el(
          "div",
          { class: "field wide" },
          el("span", { class: "field-label" }, "Documentos"),
          aviso("Foto (JPG, PNG, WEBP, HEIC) ou PDF, até 5 MB. O arquivo fica guardado com acesso restrito à equipe do programa."),
          lista,
          el("div", { class: "pessoa-documento" }, tipo, arquivo, incluir),
        ),
        el("label", { class: "check-row wide" }, registrar, " Registrar autorização de uso de imagem"),
        datas,
      ],
    };
  }

  // --- Etapa 4
  function revisao() {
    const corpo = el("div", { class: "wide" }, carregando("Conferindo cadastros semelhantes…"));
    const confirmar = el("input", { type: "checkbox", name: "confirmar_duplicidade" });
    confirmar.checked = r.confirmou;

    function desenhar() {
      confirmar.checked = r.confirmou;
      const blocos = [];
      if (precisaDeResponsavelLegal(r.data_nascimento, r.responsaveis, hoje)) {
        blocos.push(aviso("Cadastro bloqueado: pessoa com menos de 18 anos precisa de ao menos um responsável legal. Volte à etapa Família.", "amber"));
      }
      if (r.duplicados?.length) {
        blocos.push(
          el(
            "div",
            { class: "info-box amber pessoa-duplicados", role: "alert" },
            el(
              "div",
              {},
              el("strong", {}, "Possível duplicidade"),
              el("p", {}, "Já existe cadastro parecido. Confira antes de concluir:"),
              el(
                "ul",
                {},
                r.duplicados.map((d) =>
                  el(
                    "li",
                    {},
                    `${d.nome} · nascimento ${dataBr(d.data_nascimento)} · ${d.programa}`,
                    d.responsaveis.length ? ` · responsáveis: ${d.responsaveis.join(", ")}` : "",
                    ` (${d.motivos.map((m) => MOTIVOS[m] || m).join(" e ")})`,
                  ),
                ),
              ),
            ),
          ),
          el("label", { class: "check-row" }, confirmar, " Conferi os cadastros semelhantes e trata-se de outra pessoa."),
        );
      }
      const programa = programas.find((p) => p.id === r.programa_id)?.nome || r.programa_id;
      const nucleo = r.nucleo_id ? nucleos.find((n) => n.id === r.nucleo_id)?.nome : `${r.nucleo_nome.trim()} (novo)`;
      blocos.push(
        aviso("Confira os dados antes de concluir o cadastro."),
        detalhes([
          ["Pessoa", r.nome.trim()],
          ["Nascimento", `${dataBr(r.data_nascimento)} (${idade(r.data_nascimento, hoje)} anos)`],
          ["Programa", programa],
          ["Núcleo familiar", nucleo],
          ["Responsáveis", r.responsaveis.map((x) => x.nome.trim() + (x.responsavel_legal ? " (responsável legal)" : "")).join(", ") || "Nenhum"],
          ["Documentos", r.documentos.map((d) => d.tipo).join(", ") || "Nenhum"],
          ["Uso de imagem", r.autorizacao.registrar ? `Autorizado de ${dataBr(r.autorizacao.valida_de)} a ${dataBr(r.autorizacao.valida_ate)}` : "Sem autorização"],
        ]),
      );
      corpo.replaceChildren(...blocos);
    }

    async function conferir() {
      try {
        const { confirmar_duplicidade, telefone, observacao, nucleo_familiar_id, nucleo_familiar_nome, ...consulta } = corpoDoCadastro(r);
        r.duplicados = await chamadas.verificarDuplicidade(consulta);
        desenhar();
      } catch (e) {
        corpo.replaceChildren(
          aviso(`Não foi possível conferir os cadastros semelhantes: ${motivoDoErro(e)}`, "amber"),
          el("button", { type: "button", class: "btn", onclick: () => { corpo.replaceChildren(carregando("Conferindo cadastros semelhantes…")); conferir(); } }, "Tentar de novo"),
        );
      }
    }
    conferir();
    return { ler: () => (r.confirmou = confirmar.checked), campos: [corpo], redesenhar: desenhar };
  }

  async function concluir(botao, etapa) {
    etapa.ler();
    if (precisaDeResponsavelLegal(r.data_nascimento, r.responsaveis, hoje)) {
      return mostrarErro("Pessoa com menos de 18 anos precisa de ao menos um responsável legal.");
    }
    if (r.duplicados === null) return mostrarErro("Aguarde a conferência dos cadastros semelhantes.");
    if (r.duplicados.length && !r.confirmou) return mostrarErro("Confirme que conferiu os cadastros semelhantes.");
    mostrarErro("");
    botao.disabled = true;
    let pessoa;
    try {
      pessoa = await chamadas.cadastrarPessoa(corpoDoCadastro(r));
    } catch (e) {
      botao.disabled = false;
      // Alguém cadastrou um semelhante entre a revisão e a conclusão: a API devolve a lista.
      if (e instanceof ErroApi && e.dados?.codigo === "possivel_duplicidade") {
        r.duplicados = e.dados.candidatos || [];
        r.confirmou = false;
        etapa.redesenhar?.();
      }
      return mostrarErro(motivoDoErro(e));
    }
    const pendencias = [];
    for (const documento of r.documentos) {
      try {
        await chamadas.registrarDocumento(pessoa.id, { tipo: documento.tipo, arquivo: documento.arquivo });
      } catch (e) {
        pendencias.push(`documento ${documento.tipo} (${motivoDoErro(e)})`);
      }
    }
    if (r.autorizacao.registrar) {
      try {
        await chamadas.registrarAutorizacao(pessoa.id, { tipo: "uso_de_imagem", valida_de: r.autorizacao.valida_de || null, valida_ate: r.autorizacao.valida_ate });
      } catch (e) {
        pendencias.push(`autorização de imagem (${motivoDoErro(e)})`);
      }
    }
    aoConcluir(pessoa, pendencias);
  }

  function desenhar() {
    mostrarErro("");
    const etapa = [dadosPessoais, familia, documentosEAutorizacao, revisao][r.passo - 1]();
    const voltar =
      r.passo > 1
        ? el("button", { type: "button", class: "btn", onclick: () => { etapa.ler(); r.passo -= 1; desenhar(); } }, "Voltar")
        : el("a", { class: "btn", href: "#/pessoas" }, "Cancelar");
    const avancar = el("button", { type: "submit", class: "btn primary" }, r.passo === ETAPAS.length ? "Concluir cadastro" : "Continuar");

    function enviar(evento) {
      evento.preventDefault();
      // O app tem um tratador global de submit para os formulários do protótipo.
      evento.stopPropagation();
      if (r.passo === ETAPAS.length) return concluir(avancar, etapa);
      etapa.ler();
      const problema = validarEtapa(r, r.passo, hoje);
      if (problema) return mostrarErro(problema);
      if (r.passo === 2) r.duplicados = null; // nome ou responsáveis podem ter mudado
      r.passo += 1;
      desenhar();
    }

    alvo.replaceChildren(
      el(
        "section",
        { class: "card wizard" },
        etapas(r.passo),
        el(
          "form",
          { class: "pessoa-cadastro", novalidate: true, onsubmit: enviar },
          el("div", { class: "form-body" }, erro, el("div", { class: "form-grid" }, etapa.campos)),
          el("div", { class: "form-actions" }, voltar, avancar),
        ),
      ),
    );
    alvo.querySelector("input, select, textarea")?.focus();
  }

  return carregarNaTela(
    container,
    () => Promise.all([chamadas.listarProgramas(), chamadas.buscarNucleos().catch(() => [])]),
    ([listaDeProgramas, listaDeNucleos]) => {
      programas = listaDeProgramas;
      nucleos = listaDeNucleos;
      if (!r.programa_id && programas.length === 1) r.programa_id = programas[0].id;
      desenhar();
      return alvo;
    },
  );
}

// --- Perfil da pessoa ----------------------------------------------------------------

const ABAS_DA_PESSOA = [
  ["trajetoria", "Trajetória", ""],
  ["familia", "Família e cadastro", "/familia"],
  ["documentos", "Documentos e autorizações", "/documentos"],
];

function abas(pessoaId, ativa) {
  return el(
    "nav",
    { class: "tabs", "aria-label": "Seções" },
    ABAS_DA_PESSOA.map(([chave, nome, caminho]) =>
      el("a", { class: chave === ativa ? "tab active" : "tab", href: `#/pessoas/${encodeURIComponent(pessoaId)}${caminho}`, "aria-current": chave === ativa ? "page" : null }, nome),
    ),
  );
}

export function linhaDoTempo(eventos) {
  if (!eventos.length) return vazio("A trajetória começa aqui.", "Nenhum registro ainda.");
  return el(
    "div",
    { class: "timeline" },
    eventos.map((e) =>
      el(
        "div",
        { class: `timeline-item timeline-item--${e.tipo}` },
        el("small", {}, dataBr(e.data)),
        // Faltas (T-89) levam ao encontro, com a chamada completa.
        el("h3", {}, e.atividade_id && e.programa_id ? el("a", { href: `#/atividades/${encodeURIComponent(e.programa_id)}/encontro/${encodeURIComponent(e.atividade_id)}` }, e.titulo) : e.titulo),
        el("p", {}, e.descricao),
      ),
    ),
  );
}

function cabecalho(p) {
  return el(
    "section",
    { class: "card pessoa-cabecalho" },
    el(
      "div",
      { class: "card-body" },
      el("h2", {}, p.nome),
      el("p", { class: "muted" }, `${p.idade} anos · nascimento ${dataBr(p.data_nascimento)} · ${p.programa} · núcleo ${p.nucleo_familiar.nome}`),
      el("div", { class: "badges" }, badge(p.situacao === "ativo" ? "Ativa" : p.situacao, p.situacao === "ativo" ? "green" : "gray"), " ", imagem(p.autorizacao_imagem)),
    ),
  );
}

/** Perfil da pessoa: cabeçalho, abas e o conteúdo da aba (`trajetoria`, `familia` ou `documentos`). */
export function mostrarPessoa(container, pessoaId, { aba = "trajetoria", podeCadastrar = false, avisar = () => {}, hoje = hojeIso(), ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const ativa = ABAS_DA_PESSOA.some(([chave]) => chave === aba) ? aba : "trajetoria";
  const recarregar = () => mostrarPessoa(container, pessoaId, { aba: ativa, podeCadastrar, avisar, hoje, ...substitutos });
  const concluir = (mensagem) => {
    avisar(mensagem);
    return recarregar();
  };

  function incluirResponsavel() {
    const nome = entrada("nome", "text", "", { required: true });
    const parentesco = entrada("parentesco");
    const telefone = entrada("telefone", "tel");
    const legal = el("input", { type: "checkbox", name: "responsavel_legal" });
    abrirFormulario({
      titulo: "Incluir responsável",
      campos: [
        campo("resp-nome", "Nome", nome, { largo: true }),
        campo("resp-parentesco", "Parentesco", parentesco),
        campo("resp-telefone", "Telefone", telefone),
        el("label", { class: "check-row wide" }, legal, " Responsável legal"),
      ],
      validar: () => (nome.value.trim() ? "" : "Informe o nome do responsável."),
      enviar: () => chamadas.incluirResponsavel(pessoaId, { nome: nome.value.trim(), parentesco: parentesco.value.trim() || null, telefone: telefone.value.trim() || null, responsavel_legal: legal.checked }),
      aoConcluir: () => concluir("Responsável incluído."),
    });
  }

  /** Baixa o arquivo com o token (um link simples não levaria a identificação). */
  async function baixar(d, botao) {
    botao.disabled = true;
    try {
      const arquivo = await chamadas.baixarDocumento(pessoaId, d.id);
      const endereco = URL.createObjectURL(arquivo);
      const link = el("a", { href: endereco, download: d.nome_arquivo, hidden: true });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(endereco), 60000);
    } catch (e) {
      avisar(motivoDoErro(e));
    } finally {
      botao.disabled = false;
    }
  }

  function linhaDoDocumento(d) {
    return el(
      "div",
      { class: "file-item" },
      el("span", {}, `${d.tipo} · ${d.nome_arquivo}`, el("small", { style: "display:block" }, `Registrado em ${dataBr(d.criado_em)}`)),
      d.tem_arquivo
        ? el("button", { type: "button", class: "btn small", onclick: (ev) => baixar(d, ev.currentTarget) }, "Baixar")
        : el("small", {}, "Sem arquivo (registro antigo)"),
    );
  }

  function registrarDocumento() {
    const tipo = selecao("tipo", TIPOS_DE_DOCUMENTO.map((t) => [t, t]));
    const arquivo = el("input", { type: "file", name: "arquivo", accept: ACEITOS });
    abrirFormulario({
      titulo: "Registrar documento",
      aviso: aviso("Foto (JPG, PNG, WEBP, HEIC) ou PDF, até 5 MB. O arquivo fica guardado com acesso restrito à equipe do programa."),
      campos: [campo("doc-tipo", "Tipo", tipo), campo("doc-arquivo", "Arquivo", arquivo)],
      validar: () => (!tipo.value ? "Escolha o tipo do documento." : !arquivo.files?.[0] ? "Escolha o arquivo." : validarArquivo(arquivo.files[0])),
      enviar: () => chamadas.registrarDocumento(pessoaId, { tipo: tipo.value, arquivo: arquivo.files[0] }),
      aoConcluir: () => concluir("Documento registrado."),
    });
  }

  function registrarAutorizacao() {
    const de = entrada("valida_de", "date", hoje);
    const ate = entrada("valida_ate", "date", "", { required: true });
    abrirFormulario({
      titulo: "Nova autorização de uso de imagem",
      campos: [campo("aut-de", "Válida a partir de", de), campo("aut-ate", "Válida até", ate)],
      validar: () => (!ate.value ? "Informe até quando a autorização vale." : de.value && ate.value < de.value ? "O fim não pode ser anterior ao início." : ""),
      enviar: () => chamadas.registrarAutorizacao(pessoaId, { tipo: "uso_de_imagem", valida_de: de.value || null, valida_ate: ate.value }),
      aoConcluir: () => concluir("Autorização registrada."),
    });
  }

  function revogar(autorizacao) {
    abrirFormulario({
      titulo: "Revogar autorização de uso de imagem",
      aviso: aviso(`A autorização válida até ${dataBr(autorizacao.valida_ate)} deixa de valer agora. O uso externo de imagem fica bloqueado até uma nova autorização.`, "amber"),
      campos: [],
      botao: "Revogar",
      enviar: () => chamadas.revogarAutorizacao(pessoaId, autorizacao.id),
      aoConcluir: () => concluir("Autorização revogada."),
    });
  }

  const botao = (texto, acao) => (podeCadastrar ? el("button", { type: "button", class: "btn small", onclick: acao }, texto) : null);

  function conteudo(p, eventos) {
    if (ativa === "familia") {
      return el(
        "div",
        { class: "stack" },
        cartao(`Núcleo familiar ${p.nucleo_familiar.nome}`, "", detalhes([["Telefone de contato", p.telefone], ["Observação cadastral", p.observacao]])),
        cartao(
          "Responsáveis",
          "",
          p.responsaveis.length
            ? tabela(
                ["Nome", "Parentesco", "Telefone", ""],
                p.responsaveis.map((x) => el("tr", {}, el("td", {}, el("strong", {}, x.nome)), el("td", {}, x.parentesco || "—"), el("td", {}, x.telefone || "—"), el("td", {}, x.responsavel_legal ? badge("Responsável legal", "green") : ""))),
              )
            : vazio("Nenhum responsável", "Inclua o responsável pela pessoa."),
          botao("Incluir responsável", incluirResponsavel),
        ),
      );
    }
    if (ativa === "documentos") {
      const vigente = p.autorizacao_imagem === "vigente";
      return el(
        "div",
        { class: "stack" },
        cartao(
          "Autorizações de uso de imagem",
          "",
          el(
            "div",
            {},
            aviso(vigente ? "Uso externo de imagem permitido." : "Uso externo de imagem bloqueado: não há autorização vigente. O uso interno não depende dela.", vigente ? "" : "amber"),
            p.autorizacoes.length
              ? tabela(
                  ["Validade", "Situação", ""],
                  p.autorizacoes.map((a) =>
                    el(
                      "tr",
                      {},
                      el("td", {}, `${dataBr(a.valida_de)} a ${dataBr(a.valida_ate)}`),
                      el("td", {}, imagem(a.situacao)),
                      el("td", {}, a.situacao === "vigente" ? botao("Revogar", () => revogar(a)) : a.revogada_em ? el("small", {}, `Revogada em ${dataBr(a.revogada_em)}`) : ""),
                    ),
                  ),
                )
              : null,
          ),
          botao("Nova autorização", registrarAutorizacao),
        ),
        cartao(
          "Documentos",
          "Arquivos com acesso restrito; cada download fica registrado",
          p.documentos.length
            ? el("div", {}, p.documentos.map((d) => linhaDoDocumento(d)))
            : vazio("Nenhum documento registrado", "Os documentos do cadastro aparecem aqui."),
          botao("Registrar documento", registrarDocumento),
        ),
      );
    }
    return cartao("Uma trajetória conectada", "Cadastro, família, documentos e autorizações. Frequência e atendimentos entram aqui quando existirem.", linhaDoTempo(eventos));
  }

  return carregarNaTela(
    container,
    () => Promise.all([chamadas.obterPessoa(pessoaId), chamadas.obterTrajetoria(pessoaId)]),
    ([p, eventos]) => el("div", { class: "stack" }, cabecalho(p), abas(pessoaId, ativa), conteudo(p, eventos)),
  );
}
