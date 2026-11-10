// Atividades e frequência, registro em campo e sincronização (T-57 · US-05), ligadas à
// API da T-56 por meio da fila do aparelho (base/fila.js). Seguem o protótipo da E2
// (Design/Gestao): agenda em tabela no computador e em cartões no celular, registro do
// encontro em quatro passos (Atividade, Chamada, Evidências, Revisão) e fila local.
//
// - Agenda: os encontros da semana por programa, com a situação de cada chamada,
//   inclusive as que estão no aparelho esperando envio.
// - Registro em campo: salvar sempre grava na fila; com conexão, a fila envia em seguida.
// - Fila local: cada registro com a confirmação de envio, ou o erro e como resolver.
//
// Sem conexão, a agenda e a lista da turma vêm da última cópia salva no aparelho.

import * as api from "../base/api.js";
import { consultarComCopia } from "../base/copia-local.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { SITUACAO } from "../base/fila.js";
import { hojeIso } from "../base/formulario.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  obterAgenda: api.obterAgenda,
  obterTurma: api.obterTurma,
};

// Mesmo limite e mesmos tipos que a API aceita (comprovantes do Financeiro).
export const TAMANHO_MAXIMO = 5 * 1024 * 1024;
const TIPOS_ACEITOS = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"];

const estaOnline = () => globalThis.navigator?.onLine !== false;

// --- Datas (AAAA-MM-DD, sem fuso) ----------------------------------------------------

const comoData = (iso) => {
  const [a, m, d] = iso.split("-").map(Number);
  return new Date(Date.UTC(a, m - 1, d));
};
const comoIso = (data) => data.toISOString().slice(0, 10);
export const somarDias = (iso, dias) => comoIso(new Date(comoData(iso).getTime() + dias * 86400000));
/** Segunda-feira da semana de `iso`. */
export const inicioDaSemana = (iso) => somarDias(iso, 1 - (comoData(iso).getUTCDay() || 7));

export const dataBr = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
const DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const diaDaSemana = (iso) => DIAS[comoData(iso).getUTCDay()];

/** "05/10 às 14:32", no fuso do aparelho. */
export function momento(isoComHora) {
  const d = new Date(isoComHora);
  const dois = (n) => String(n).padStart(2, "0");
  return `${dois(d.getDate())}/${dois(d.getMonth() + 1)} às ${dois(d.getHours())}:${dois(d.getMinutes())}`;
}

const tamanhoLegivel = (bytes) => (bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);
const hora = (h) => String(h || "").slice(0, 5);

// --- Peças do design system (as mesmas classes do protótipo) --------------------------

const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));
const aviso = (texto, tom = "") => el("div", { class: `info-box ${tom}`.trim(), role: tom ? "status" : null }, el("span", {}, texto));

/** Iniciais do nome, como o avatar do protótipo. */
const iniciais = (nome) =>
  String(nome || "")
    .split(/\s+/)
    .filter(Boolean)
    .filter((_, i, partes) => i === 0 || i === partes.length - 1)
    .map((p) => p[0].toUpperCase())
    .join("");
const avatar = (nome, tom = "") => el("span", { class: `avatar ${tom}`.trim(), "aria-hidden": "true" }, iniciais(nome));

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

/**
 * Tabela no computador e cartões no celular, como no protótipo. No celular, uma tabela
 * esconderia a coluna da situação atrás da rolagem lateral; os dois formatos ficam na
 * página e o CSS mostra um ou outro (mesmo ponto de quebra do design, 580 px).
 */
function emDoisFormatos(tabelaDoComputador, cartoesDoCelular, contagem) {
  return el(
    "div",
    {},
    el("div", { class: "so-computador" }, tabelaDoComputador),
    el("div", { class: "so-celular" }, el("div", { class: "phone-record-count" }, contagem), el("div", { class: "phone-record-list" }, cartoesDoCelular)),
  );
}

/** Cartão `.phone-record` do protótipo; vira link quando há para onde ir. */
function cartaoDoCelular({ titulo, situacao, meta, inferior = [], href = "", extra = [] }) {
  return el(
    href ? "a" : "div",
    { class: "phone-record", href: href || null },
    el("div", { class: "phone-record-top" }, el("strong", {}, titulo), situacao),
    meta ? el("div", { class: "phone-record-meta" }, meta) : null,
    extra,
    inferior.length ? el("div", { class: "phone-record-bottom" }, inferior.map((t) => el("span", {}, t))) : null,
  );
}

const avisoDeCopia = (copiaDe, o_que) =>
  copiaDe ? aviso(`Sem conexão: mostrando ${o_que} salva neste aparelho em ${momento(copiaDe)}.`, "amber") : null;

const rotaDoRegistro = (programaId, turmaId, data) =>
  `#/atividades/${encodeURIComponent(programaId)}/registro/${encodeURIComponent(turmaId)}?data=${data}`;

// --- Agenda --------------------------------------------------------------------------

/** Situação de um encontro da agenda, juntando a API e a fila do aparelho. */
export function situacaoDoEncontro(encontro, naFila, hoje) {
  if (encontro.atividades.length) return { texto: "Concluída", tom: "green", registrado: true };
  const local = naFila.filter((i) => i.tipo === "atividade" && i.turmaId === encontro.turma_id && i.data === encontro.data);
  if (local.some((i) => i.situacao === SITUACAO.ENVIADO)) return { texto: "Concluída", tom: "green", registrado: true };
  if (local.some((i) => i.situacao === SITUACAO.ERRO)) return { texto: "Erro no envio", tom: "red", registrado: true };
  if (local.length) return { texto: "Aguardando sincronização", tom: "amber", registrado: true };
  if (encontro.data > hoje) return { texto: "Agendada", tom: "gray", registrado: false };
  return { texto: "Chamada pendente", tom: "amber", registrado: false };
}

function agendaEmDoisFormatos(programaId, encontros, naFila, { podeRegistrar, hoje }) {
  const linhas = encontros.map((e) => {
    const situacao = situacaoDoEncontro(e, naFila, hoje);
    const destino = podeRegistrar && !situacao.registrado && e.data <= hoje ? rotaDoRegistro(programaId, e.turma_id, e.data) : "";
    return { e, situacao, destino, quando: `${diaDaSemana(e.data)} ${dataBr(e.data)}`, horario: `${hora(e.hora_inicio)}–${hora(e.hora_fim)}` };
  });
  const tabelaDoComputador = tabela(
    ["Data · hora", "Turma", "Local", "Educador", "Situação", ""],
    linhas.map(({ e, situacao, destino, quando, horario }) =>
      el(
        "tr",
        {},
        el("td", {}, quando, el("small", {}, horario)),
        el("td", {}, e.turma, e.previsto ? null : el("small", {}, "Fora da agenda da turma")),
        el("td", {}, e.espaco),
        el("td", {}, e.responsavel),
        el("td", {}, badge(situacao.texto, situacao.tom)),
        el("td", {}, destino ? el("a", { class: "btn small primary", href: destino }, "Fazer chamada") : "—"),
      ),
    ),
  );
  const cartoes = linhas.map(({ e, situacao, destino, quando, horario }) =>
    cartaoDoCelular({
      titulo: e.turma,
      situacao: badge(situacao.texto, situacao.tom),
      meta: `${e.espaco}${e.previsto ? "" : " · fora da agenda da turma"}`,
      inferior: [`${quando} · ${horario}`, destino ? "Fazer chamada →" : e.responsavel.split(" ")[0]],
      href: destino,
    }),
  );
  return emDoisFormatos(tabelaDoComputador, cartoes, `${encontros.length} encontro(s)`);
}

/** Encontros da semana do programa escolhido, com a situação de cada chamada. */
export function mostrarAgenda(container, { programaInicial = "", podeRegistrar = false, fila, hoje = hojeIso(), ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const conteudo = el("div", {});
  const programa = el("select", { name: "programa", class: "filter-control", "aria-label": "Programa" });
  const periodo = el("strong", { class: "agenda-periodo" });
  let semana = inicioDaSemana(hoje);

  function carregar() {
    const id = programa.value;
    const fim = somarDias(semana, 6);
    periodo.textContent = `${dataBr(semana).slice(0, 5)} a ${dataBr(fim)}`;
    if (!id) return conteudo.replaceChildren(cartao("Agenda", "", vazio("Nenhum programa", "Os encontros das turmas aparecem aqui.")));
    return carregarNaTela(
      conteudo,
      async () => {
        const [agenda, naFila] = await Promise.all([
          consultarComCopia(`agenda:${id}:${semana}`, () => chamadas.obterAgenda(id, { inicio: semana, fim })),
          fila ? fila.listar() : [],
        ]);
        return { ...agenda, naFila };
      },
      ({ dados: encontros, copiaDe, naFila }) =>
        el(
          "div",
          { class: "stack" },
          avisoDeCopia(copiaDe, "a agenda"),
          encontros.length
            ? el("section", { class: "card" }, agendaEmDoisFormatos(id, encontros, naFila, { podeRegistrar, hoje }))
            : cartao("Agenda", "", vazio("Nenhum encontro nesta semana", "As turmas do programa não têm encontros previstos neste período.")),
        ),
    );
  }

  const mudarSemana = (dias) => () => {
    semana = somarDias(semana, dias);
    carregar();
  };
  const navegacao = el(
    "div",
    { class: "actions agenda-semana" },
    el("button", { type: "button", class: "btn small", onclick: mudarSemana(-7) }, "← Anterior"),
    periodo,
    el("button", { type: "button", class: "btn small", onclick: mudarSemana(7) }, "Próxima →"),
  );

  programa.addEventListener("change", carregar);
  return carregarNaTela(
    container,
    () => consultarComCopia("programas", () => chamadas.listarProgramas()),
    ({ dados: programas }) => {
      programa.replaceChildren(...programas.map((p) => el("option", { value: p.id }, p.nome)));
      programa.value = programas.some((p) => p.id === programaInicial) ? programaInicial : programas[0]?.id || "";
      queueMicrotask(carregar);
      return el(
        "div",
        { class: "stack" },
        el("div", { class: "toolbar" }, el("div", { class: "filters" }, programa), navegacao),
        el("p", { class: "muted" }, el("a", { href: "#/sincronizacao" }, "Fila local de registros no dispositivo")),
        conteudo,
      );
    },
  );
}

// --- Registro em campo ---------------------------------------------------------------

export const PASSOS = ["Atividade", "Chamada", "Evidências", "Revisão"];

// Opções de presença do protótipo; a falta justificada vai para a API como ausência com
// justificativa, e por isso o motivo é obrigatório.
const PRESENCAS = [
  ["Presente", { presente: true }],
  ["Ausente", { presente: false }],
  ["Falta justificada", { presente: false, justificada: true }],
];

/** Quem estava matriculado na turma na data do encontro (mesma regra da API). */
export function matriculadosNaData(turma, data) {
  const todas = [...(turma.matriculas || []), ...(turma.desligadas || [])];
  const vistos = new Map();
  for (const m of todas) {
    if (!m.data_entrada || m.data_entrada > data) continue;
    if (m.data_saida && m.data_saida <= data) continue;
    vistos.set(m.pessoa_id, m.pessoa);
  }
  return [...vistos.entries()].map(([pessoa_id, pessoa]) => ({ pessoa_id, pessoa })).sort((a, b) => a.pessoa.localeCompare(b.pessoa, "pt-BR"));
}

/** Problema que impede passar do passo (ou vazio). presencas: Map pessoa_id -> { opcao, motivo }. */
export function validarPasso(passo, { data, conteudo, presencas, pessoas }, hoje) {
  if (passo === 1) {
    if (!data) return "Informe a data do encontro.";
    if (data > hoje) return "A data do encontro não pode estar no futuro.";
    if (!conteudo.trim()) return "Informe o conteúdo e as ocorrências do encontro.";
  }
  if (passo === 2) {
    if (!pessoas.length) return "Nenhuma pessoa estava matriculada na turma nessa data.";
    const semMarcacao = pessoas.filter((p) => !presencas.get(p.pessoa_id)?.opcao);
    if (semMarcacao.length) return `Selecione a presença de todos: falta ${semMarcacao.map((p) => p.pessoa).join(", ")}.`;
    const semMotivo = pessoas.filter((p) => presencas.get(p.pessoa_id).opcao === "Falta justificada" && !presencas.get(p.pessoa_id).motivo?.trim());
    if (semMotivo.length) return `Informe o motivo da falta justificada de ${semMotivo.map((p) => p.pessoa).join(", ")}.`;
  }
  return "";
}

/** Problema com um arquivo de evidência (ou vazio). */
export function validarArquivo(arquivo) {
  if (!arquivo.size) return `${arquivo.name}: arquivo vazio.`;
  if (arquivo.size > TAMANHO_MAXIMO) return `${arquivo.name}: maior que 5 MB.`;
  if (arquivo.type && !TIPOS_ACEITOS.includes(arquivo.type)) return `${arquivo.name}: envie foto (JPG, PNG, WEBP, HEIC) ou PDF.`;
  return "";
}

/** O que vai para a API na chamada, a partir das opções marcadas. */
export function presencasParaApi(pessoas, presencas) {
  return pessoas.map((p) => {
    const { opcao, motivo = "" } = presencas.get(p.pessoa_id);
    const regra = Object.fromEntries(PRESENCAS)[opcao];
    return { pessoa_id: p.pessoa_id, presente: regra.presente, justificativa: regra.justificada ? motivo.trim() : null };
  });
}

function stepper(passoAtual) {
  return el(
    "div",
    { class: "stepper" },
    PASSOS.map((rotulo, i) =>
      el(
        "div",
        { class: i + 1 === passoAtual ? "step active" : "step", "aria-current": i + 1 === passoAtual ? "step" : null },
        el("b", {}, i + 1 < passoAtual ? "✓" : String(i + 1)),
        rotulo,
      ),
    ),
  );
}

/** Registro do encontro em quatro passos, salvo na fila do aparelho. */
export function mostrarRegistro(
  container,
  programaId,
  turmaId,
  dataInicial,
  { fila, ir = () => {}, avisar = () => {}, online = estaOnline, hoje = hojeIso(), ...substitutos } = {},
) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const voltarAgenda = `#/atividades/${encodeURIComponent(programaId)}`;

  function assistente({ dados: turma, copiaDe }) {
    const t = turma.turma;
    // Os campos são criados uma vez: voltar a um passo mantém o que já foi preenchido.
    // Ids próprios: o app.js do protótipo tem tratadores globais para os ids da demonstração
    // (evidence-files, activity-form…), que quebrariam esta tela.
    const data = el("input", { id: "f-data", name: "data", type: "date", max: hoje, required: true });
    data.value = dataInicial && dataInicial <= hoje ? dataInicial : hoje;
    const conteudo = el("textarea", { id: "f-conteudo", name: "conteudo", maxlength: 5000, required: true });
    const presencas = new Map();
    const arquivos = [];
    const erro = el("div", { id: "registro-erro", role: "alert" });
    const corpo = el("div", {});
    const acoes = el("div", { class: "form-actions" });
    const marcador = el("div", {});
    let passo = 1;
    let pessoas = [];

    const mostrarErro = (texto) => {
      erro.replaceChildren(texto ? el("div", { class: "info-box red" }, el("span", {}, texto)) : "");
    };

    // Passo 1 · Atividade
    function passoAtividade() {
      return el(
        "div",
        { class: "form-grid" },
        el("div", { class: "field" }, el("label", {}, "Turma"), el("input", { type: "text", value: t.nome, disabled: true, "aria-label": "Turma" })),
        el("div", { class: "field" }, el("label", { for: "f-data" }, "Data"), data),
        el("div", { class: "field" }, el("label", {}, "Horário"), el("input", { type: "text", value: `${hora(t.hora_inicio)}–${hora(t.hora_fim)}`, disabled: true, "aria-label": "Horário" })),
        el("div", { class: "field" }, el("label", {}, "Local"), el("input", { type: "text", value: t.espaco, disabled: true, "aria-label": "Local" })),
        el("div", { class: "field wide" }, el("label", { for: "f-conteudo" }, "Conteúdo e ocorrências"), conteudo),
      );
    }

    // Passo 2 · Chamada
    function linhaDaPessoa({ pessoa_id, pessoa }) {
      const idCampo = `att-${pessoa_id}`;
      const atual = presencas.get(pessoa_id) || {};
      const escolha = el(
        "select",
        { id: idCampo, name: idCampo, required: true },
        el("option", { value: "" }, "Selecionar"),
        PRESENCAS.map(([rotulo]) => el("option", { value: rotulo }, rotulo)),
      );
      escolha.value = atual.opcao || "";
      const motivo = el("input", {
        type: "text",
        name: `motivo-${pessoa_id}`,
        class: "attendance-motivo",
        placeholder: "Motivo da falta",
        maxlength: 1000,
        "aria-label": `Motivo da falta de ${pessoa}`,
        hidden: atual.opcao !== "Falta justificada",
      });
      motivo.value = atual.motivo || "";
      const registrar = () => {
        presencas.set(pessoa_id, { opcao: escolha.value, motivo: motivo.value });
        motivo.hidden = escolha.value !== "Falta justificada";
      };
      escolha.addEventListener("change", registrar);
      motivo.addEventListener("input", registrar);
      return el(
        "div",
        { class: "attendance" },
        el("div", { class: "person" }, avatar(pessoa, "green"), el("label", { for: idCampo }, pessoa)),
        el("div", { class: "attendance-escolha" }, escolha, motivo),
      );
    }

    function passoChamada() {
      pessoas = matriculadosNaData(turma, data.value);
      const todosPresentes = () => {
        for (const p of pessoas) presencas.set(p.pessoa_id, { opcao: "Presente", motivo: "" });
        desenhar();
      };
      return el(
        "div",
        {},
        el(
          "div",
          { class: "row-top" },
          el("h2", {}, "Quem participou?"),
          el("button", { type: "button", class: "btn small", onclick: todosPresentes }, "Marcar todos presentes"),
        ),
        el("p", { class: "muted", style: "font-size:12px" }, `Turma ${t.nome} · ${dataBr(data.value)}`),
        pessoas.length ? pessoas.map(linhaDaPessoa) : vazio("Ninguém matriculado nessa data", "Volte e confira a data do encontro."),
      );
    }

    // Passo 3 · Evidências
    function passoEvidencias() {
      const lista = el("div", { id: "registro-evidencias-lista" });
      const montar = () =>
        lista.replaceChildren(
          ...arquivos.map((arquivo, indice) =>
            el(
              "div",
              { class: "file-item" },
              el("span", {}, arquivo.name, el("small", { style: "display:block" }, tamanhoLegivel(arquivo.size))),
              el("button", { type: "button", class: "btn small", onclick: () => (arquivos.splice(indice, 1), montar()) }, "Remover"),
            ),
          ),
        );
      const seletor = el("input", { id: "registro-evidencias", name: "evidencias", type: "file", multiple: true, accept: "image/*,.pdf", "aria-label": "Adicionar evidências" });
      seletor.addEventListener("change", () => {
        const escolhidos = [...seletor.files];
        arquivos.push(...escolhidos.filter((a) => !validarArquivo(a)));
        seletor.value = "";
        mostrarErro(escolhidos.map(validarArquivo).filter(Boolean).join(" "));
        montar();
      });
      montar();
      return el(
        "div",
        {},
        el("h2", {}, "Evidências do encontro"),
        el("p", { class: "muted" }, "Vincule fotos e documentos à atividade."),
        aviso("Os anexos recebem programa, atividade, autor e data."),
        el("div", { class: "dropzone" }, el("p", {}, "Adicionar fotos ou documentos"), seletor, el("p", {}, el("small", {}, "Até 5 MB por arquivo · fotos ou PDF"))),
        lista,
      );
    }

    // Passo 4 · Revisão
    function passoRevisao() {
      const marcadas = presencasParaApi(pessoas, presencas);
      const presentes = marcadas.filter((p) => p.presente).length;
      const detalhes = [
        ["Turma", t.nome],
        ["Data", `${dataBr(data.value)} · ${hora(t.hora_inicio)}`],
        ["Presentes", String(presentes)],
        ["Ausências", String(marcadas.length - presentes)],
        ["Evidências", `${arquivos.length} arquivo(s)`],
        ["Local", t.espaco],
      ];
      return el(
        "div",
        {},
        el("h2", {}, "Está tudo certo?"),
        el("p", { class: "muted" }, "Revise o encontro antes de concluir."),
        el("dl", { class: "details" }, detalhes.map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", {}, v)))),
        el("p", {}, conteudo.value.trim()),
        online()
          ? aviso("Ao concluir, o registro é guardado no dispositivo e enviado em seguida.")
          : aviso("Você está sem conexão. O registro ficará na fila local até a sincronização.", "amber"),
      );
    }

    const PASSO = { 1: passoAtividade, 2: passoChamada, 3: passoEvidencias, 4: passoRevisao };

    function desenhar() {
      marcador.replaceChildren(stepper(passo));
      corpo.replaceChildren(PASSO[passo]());
      const voltar =
        passo > 1
          ? el("button", { type: "button", class: "btn", onclick: () => (mostrarErro(""), (passo -= 1), desenhar()) }, "Voltar")
          : el("a", { class: "btn", href: voltarAgenda }, "Cancelar");
      const rotulo = passo < 4 ? "Continuar" : online() ? "Concluir atividade" : "Salvar no dispositivo";
      acoes.replaceChildren(voltar, el("button", { type: "submit", class: "btn primary" }, rotulo));
    }

    async function concluir(botao) {
      botao.disabled = true;
      try {
        await fila.adicionarRegistro({
          programaId,
          turmaId,
          turma: t.nome,
          data: data.value,
          conteudo: conteudo.value.trim(),
          presencas: presencasParaApi(pessoas, presencas),
          evidencias: arquivos.map((arquivo) => ({ arquivo, nome: arquivo.name })),
        });
      } catch {
        botao.disabled = false;
        return mostrarErro("Não foi possível guardar o registro neste aparelho. Verifique o espaço livre e tente de novo.");
      }
      if (online()) {
        fila.sincronizar();
        avisar("Atividade e chamada registradas. Enviando…");
      } else {
        avisar("Atividade salva no dispositivo.");
      }
      ir("/sincronizacao");
    }

    function enviar(evento) {
      evento.preventDefault();
      // O app tem um tratador global de submit para os formulários do protótipo.
      evento.stopPropagation();
      if (passo === 1) pessoas = matriculadosNaData(turma, data.value);
      const problema = validarPasso(passo, { data: data.value, conteudo: conteudo.value, presencas, pessoas }, hoje);
      if (problema) return mostrarErro(problema);
      mostrarErro("");
      if (passo < 4) {
        passo += 1;
        return desenhar();
      }
      return concluir(evento.submitter || acoes.querySelector("button[type=submit]"));
    }

    desenhar();
    return el(
      "div",
      { class: "stack" },
      avisoDeCopia(copiaDe, "a lista da turma"),
      el(
        "section",
        { class: "card wizard" },
        marcador,
        el("form", { id: "registro-encontro", novalidate: true, onsubmit: enviar }, el("div", { class: "form-body" }, erro, corpo), acoes),
      ),
    );
  }

  return carregarNaTela(container, () => consultarComCopia(`turma:${programaId}:${turmaId}`, () => chamadas.obterTurma(programaId, turmaId)), assistente);
}

// --- Fila local ----------------------------------------------------------------------

function descreverItem(item) {
  if (item.tipo === "atividade") {
    const presentes = item.dados.presencas.filter((p) => p.presente).length;
    return { titulo: `Chamada · ${item.turma}`, detalhe: `${presentes} presente(s), ${item.dados.presencas.length - presentes} ausência(s)` };
  }
  return { titulo: `Evidência · ${item.nome}`, detalhe: `${item.turma}${item.tamanho ? ` · ${tamanhoLegivel(item.tamanho)}` : ""}` };
}

function situacaoDoItem(item, itens) {
  if (item.situacao === SITUACAO.ENVIADO) return { selo: badge(`Enviado em ${momento(item.enviadoEm)}`, "green"), erro: [] };
  if (item.situacao === SITUACAO.ERRO) {
    return {
      selo: badge("Erro no envio", "red"),
      erro: [
        el("small", { class: "fila-erro", role: "alert" }, item.erro),
        item.repetir ? el("small", { class: "fila-erro-dica" }, "Será tentado de novo quando a conexão voltar.") : null,
      ],
    };
  }
  if (item.tipo === "evidencia") {
    const encontro = itens.find((i) => i.id === item.atividadeRegistroId);
    if (encontro && encontro.situacao !== SITUACAO.ENVIADO) return { selo: badge("Aguardando o envio da chamada", "amber"), erro: [] };
  }
  return { selo: badge("Aguardando sincronização", "amber"), erro: [] };
}

/** A fila do aparelho: confirmação de cada envio, erros visíveis e o que fazer. */
export function mostrarSincronizacao(container, { fila, online = estaOnline, avisar = () => {} } = {}) {
  let enviando = false;

  async function agir(fazer, mensagem) {
    enviando = true;
    await desenhar();
    try {
      const resultado = await fazer();
      if (mensagem && resultado) avisar(mensagem(resultado));
    } finally {
      enviando = false;
      await desenhar();
    }
  }

  const sincronizar = () =>
    agir(
      () => fila.sincronizar(),
      (r) => (r.enviados ? `${r.enviados} registro(s) sincronizado(s).` : r.falhas ? "O envio falhou. Veja o erro em cada registro." : "Nenhum registro pendente."),
    );

  function acoesDoItem(item) {
    if (item.situacao !== SITUACAO.ERRO) return [];
    return [
      el("button", { type: "button", class: "btn small", disabled: !online() || enviando, onclick: () => agir(() => fila.tentarDeNovo(item.id)) }, "Tentar de novo"),
      el("button", { type: "button", class: "btn small", onclick: () => agir(() => fila.descartar(item.id)) }, "Descartar"),
    ];
  }

  function filaEmDoisFormatos(itens) {
    // A situação é montada de novo para cada formato: um elemento do DOM só fica num lugar.
    const linhas = itens.map((item) => ({ item, ...descreverItem(item) }));
    const tabelaDoComputador = tabela(
      ["Atividade", "Data", "Situação", ""],
      linhas.map(({ item, titulo, detalhe }) => {
        const { selo, erro } = situacaoDoItem(item, itens);
        return el(
          "tr",
          {},
          el("td", {}, titulo, el("small", {}, detalhe)),
          el("td", {}, dataBr(item.data)),
          el("td", {}, selo, erro),
          el("td", {}, acoesDoItem(item).length ? el("div", { class: "actions" }, acoesDoItem(item)) : "—"),
        );
      }),
    );
    const cartoes = linhas.map(({ item, titulo, detalhe }) => {
      const { selo, erro } = situacaoDoItem(item, itens);
      return cartaoDoCelular({
        titulo,
        situacao: selo,
        meta: detalhe,
        extra: [...erro, acoesDoItem(item).length ? el("div", { class: "actions" }, acoesDoItem(item)) : null],
        inferior: [dataBr(item.data)],
      });
    });
    return emDoisFormatos(tabelaDoComputador, cartoes, `${itens.length} registro(s) no dispositivo`);
  }

  async function desenhar() {
    const itens = await fila.listar();
    const conectado = online();
    const aguardando = itens.filter((i) => i.situacao !== SITUACAO.ENVIADO).length;
    const enviados = itens.length - aguardando;
    container.replaceChildren(
      el(
        "div",
        { class: "stack" },
        conectado
          ? aviso(enviando ? "Sincronizando os registros…" : "Conectado. Os registros são enviados assim que concluídos.")
          : aviso("Sem conexão. Os registros ficam guardados neste dispositivo e são enviados quando a conexão voltar.", "amber"),
        fila.persistente ? null : aviso("Este navegador não guarda a fila: não feche a página antes do envio.", "red"),
        cartao(
          "Fila local",
          `${aguardando} registro(s) aguardando`,
          itens.length ? filaEmDoisFormatos(itens) : vazio("Tudo em dia", "Nenhum registro aguardando envio."),
          el(
            "div",
            { class: "actions" },
            enviados ? el("button", { type: "button", class: "btn small", disabled: enviando, onclick: () => agir(() => fila.limparEnviados()) }, "Limpar enviados") : null,
            el("button", { type: "button", class: "btn primary", disabled: !conectado || enviando || !aguardando, onclick: sincronizar }, "Sincronizar agora"),
          ),
        ),
      ),
    );
  }

  const parar = fila.aoMudar(() => {
    if (!container.isConnected) return parar();
    if (!enviando) desenhar();
  });
  return desenhar();
}
