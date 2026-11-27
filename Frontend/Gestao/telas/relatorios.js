// Relatório técnico (T-76 · US-11), ligado à API da T-75.
//
// #/relatorios: histórico das emissões (lido da trilha de auditoria).
// #/relatorios/novo: três passos, como no protótipo.
//   1. Configurar: programa, período, finalidade e seções.
//   2. Pendências e evidências: o que falta no período e quais evidências entram.
//   3. Prévia: o conteúdo exato do arquivo, já minimizado pela finalidade, e a exportação
//      em PDF ou XLSX. Cada exportação entra no histórico.
//
// A tela não monta o relatório: a prévia e os arquivos vêm da mesma montagem da API,
// então o que se vê na prévia é o que sai no PDF e no XLSX.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { campo, hojeIso } from "../base/formulario.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  obterPreviaDoRelatorio: api.obterPreviaDoRelatorio,
  exportarRelatorio: api.exportarRelatorio,
  listarEmissoes: api.listarEmissoes,
};

export const FINALIDADES = {
  externa: ["Circulação externa", "Financiadores, conselho e divulgação. Sem dados pessoais: pessoas só em número, encontros sem o conteúdo e só evidências com autorização de imagem de todos os presentes."],
  interna: ["Consulta interna", "Uso da equipe. Traz o nome e a frequência de cada pessoa e o conteúdo dos encontros. Não circular fora da instituição."],
};
export const SECOES = [
  ["plano", "Objetivos, ações e resultados"],
  ["pessoas", "Pessoas atendidas"],
  ["atividades", "Atividades e frequência"],
  ["indicadores", "Indicadores"],
  ["evidencias", "Evidências"],
  ["financeiro", "Execução física e financeira"],
];
const ONDE_CORRIGIR = {
  chamadas_sem_registro: "#/atividades",
  encontros_sem_evidencia: "#/atividades",
  autorizacoes_de_imagem_vencidas: "#/pessoas",
  evidencias_nao_liberadas: "#/pessoas",
};
const PASSOS = ["Configurar", "Pendências e evidências", "Pré-visualizar"];

const dataBr = (iso) => (iso ? String(iso).slice(0, 10).split("-").reverse().join("/") : "—");
const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const tabela = (colunas, linhas) =>
  el(
    "div",
    { class: "table-wrap" },
    el("table", {}, el("thead", {}, el("tr", {}, colunas.map((c) => el("th", { scope: "col" }, c)))), el("tbody", {}, linhas)),
  );

/** Primeiro e último dia do mês de uma data AAAA-MM-DD. */
export function mesDe(iso) {
  const [ano, mes] = iso.split("-").map(Number);
  const ultimo = new Date(Date.UTC(ano, mes, 0)).getUTCDate();
  return [`${iso.slice(0, 7)}-01`, `${iso.slice(0, 7)}-${String(ultimo).padStart(2, "0")}`];
}

/** Nome do arquivo baixado, igual ao da API (sem acentos nem símbolos). */
export function nomeDoArquivo(programa, inicio, fim, formato) {
  const base = `relatorio-tecnico-${programa}-${dataBr(inicio)}-a-${dataBr(fim)}`
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
  return `${base}.${formato}`;
}

/** Valida o passo 1; devolve a mensagem do problema ou "". */
export function validarConfiguracao({ programa_id, inicio, fim, finalidade, secoes }) {
  if (!programa_id) return "Escolha o programa.";
  if (!inicio || !fim) return "Informe o início e o fim do período.";
  if (fim < inicio) return "O fim do período não pode ser anterior ao início.";
  if (!finalidade) return "Escolha a finalidade.";
  if (!secoes.length) return "Escolha ao menos uma seção do relatório.";
  return "";
}

function stepper(passo) {
  return el(
    "div",
    { class: "stepper" },
    PASSOS.map((rotulo, i) =>
      el("div", { class: `step${i + 1 === passo ? " active" : ""}`, "aria-current": i + 1 === passo ? "step" : null }, el("b", {}, i + 1 < passo ? "✓" : String(i + 1)), rotulo),
    ),
  );
}

function baixarNoNavegador(arquivo, nome) {
  const endereco = URL.createObjectURL(arquivo);
  const link = el("a", { href: endereco, download: nome, hidden: true });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(endereco), 60000);
}

// --- Histórico --------------------------------------------------------------------------

export function mostrarEmissoes(container, substitutos = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  return carregarNaTela(container, chamadas.listarEmissoes, (emissoes) => {
    if (!emissoes.length) {
      return el(
        "section",
        { class: "card" },
        el("div", { class: "empty" }, el("h2", {}, "Nenhum relatório emitido"), el("p", {}, "Os relatórios exportados em PDF ou XLSX aparecem aqui."), el("a", { class: "btn primary", href: "#/relatorios/novo" }, "+ Gerar relatório")),
      );
    }
    return el(
      "section",
      { class: "card" },
      el("div", { class: "card-head" }, el("div", {}, el("h2", {}, "Relatórios emitidos"), el("small", {}, "Exportações registradas na trilha de auditoria, com a configuração usada"))),
      tabela(
        ["Data", "Programa", "Período", "Finalidade", "Seções", "Formato", "Emitido por"],
        emissoes.map((e) =>
          el(
            "tr",
            {},
            el("td", {}, dataBr(e.momento), el("small", {}, new Date(e.momento).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }))),
            el("td", {}, e.programa || e.programa_id || "—"),
            el("td", {}, `${dataBr(e.inicio)} a ${dataBr(e.fim)}`),
            el("td", {}, badge(FINALIDADES[e.finalidade]?.[0] || e.finalidade || "—", e.finalidade === "interna" ? "amber" : "green")),
            el("td", {}, String(e.secoes.length)),
            el("td", {}, (e.formato || "").toUpperCase()),
            el("td", {}, e.usuario || "—"),
          ),
        ),
      ),
    );
  });
}

// --- Novo relatório ---------------------------------------------------------------------

/**
 * finalidades: as que o perfil emite (a direção, só "externa"); a API confere de novo.
 * comFinanceiro: oferece a seção financeira. avisar: mensagem curta (toast).
 */
export function mostrarNovoRelatorio(
  container,
  { finalidades = ["externa", "interna"], comFinanceiro = false, hoje = hojeIso(), avisar = () => {}, baixar = baixarNoNavegador, ...substitutos } = {},
) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const [inicioPadrao, fimPadrao] = mesDe(hoje);
  const estado = {
    programa_id: "",
    inicio: inicioPadrao,
    fim: fimPadrao,
    finalidade: finalidades.includes("externa") ? "externa" : finalidades[0],
    secoes: SECOES.map(([id]) => id).filter((id) => id !== "financeiro"),
    evidencias: null,
  };
  let programas = [];
  const pedido = () => ({ ...estado });
  const nomeDoPrograma = () => programas.find((p) => p.id === estado.programa_id)?.nome || estado.programa_id;

  // Passo 1 ------------------------------------------------------------------------------
  function configurar() {
    carregarNaTela(container, chamadas.listarProgramas, (lista) => {
      programas = lista;
      if (!lista.length) {
        return el("section", { class: "card" }, el("div", { class: "empty" }, el("h2", {}, "Nenhum programa disponível"), el("p", {}, "Os relatórios são emitidos por programa.")));
      }
      if (!estado.programa_id) estado.programa_id = lista[0].id;
      const programa = el("select", { name: "programa", required: true }, lista.map((p) => el("option", { value: p.id }, p.identificador ? `${p.nome} (${p.identificador})` : p.nome)));
      programa.value = estado.programa_id;
      const inicio = el("input", { type: "date", name: "inicio", required: true, value: estado.inicio });
      const fim = el("input", { type: "date", name: "fim", required: true, value: estado.fim });
      const finalidade = el("select", { name: "finalidade", required: true }, finalidades.map((f) => el("option", { value: f }, FINALIDADES[f][0])));
      finalidade.value = estado.finalidade;
      const dica = el("small", { class: "muted" }, FINALIDADES[estado.finalidade][1]);
      finalidade.addEventListener("change", () => (dica.textContent = FINALIDADES[finalidade.value][1]));
      const opcoes = SECOES.filter(([id]) => id !== "financeiro" || comFinanceiro);
      const caixas = opcoes.map(([id, rotulo]) =>
        el("label", { class: "check-row" }, el("input", { type: "checkbox", name: "secoes", value: id, checked: estado.secoes.includes(id) }), rotulo),
      );
      const erro = el("p", { class: "error-message", role: "alert", hidden: true });

      function enviar(evento) {
        evento.preventDefault();
        evento.stopPropagation();
        const novo = {
          programa_id: programa.value,
          inicio: inicio.value,
          fim: fim.value,
          finalidade: finalidade.value,
          secoes: caixas.map((c) => c.querySelector("input")).filter((i) => i.checked).map((i) => i.value),
        };
        const problema = validarConfiguracao(novo);
        if (problema) {
          erro.textContent = problema;
          erro.hidden = false;
          return;
        }
        Object.assign(estado, novo, { evidencias: null });
        conferir();
      }

      return el(
        "section",
        { class: "card form-card" },
        stepper(1),
        el(
          "form",
          { novalidate: true, onsubmit: enviar },
          el(
            "div",
            { class: "form-body" },
            erro,
            el(
              "div",
              { class: "form-grid" },
              campo("rel-programa", "Programa", programa),
              campo("rel-finalidade", "Finalidade", finalidade),
              campo("rel-inicio", "Início do período", inicio),
              campo("rel-fim", "Fim do período", fim),
            ),
            dica,
            el("h3", { class: "afastado" }, "Conteúdo do relatório"),
            caixas,
          ),
          el("div", { class: "form-actions" }, el("a", { class: "btn", href: "#/relatorios" }, "Cancelar"), el("button", { type: "submit", class: "btn primary" }, "Conferir pendências")),
        ),
      );
    });
  }

  // Passo 2 ------------------------------------------------------------------------------
  function conferir() {
    carregarNaTela(
      container,
      () => chamadas.obterPreviaDoRelatorio({ ...pedido(), evidencias: null }),
      (previa) => {
        const comEvidencias = estado.secoes.includes("evidencias");
        const externa = estado.finalidade === "externa";
        const marcadas = new Set(estado.evidencias ?? previa.evidencias_disponiveis.map((e) => e.id));
        const evidencias = previa.evidencias_disponiveis.map((e) => {
          const barrada = externa && !e.liberada_externa;
          const caixa = el("input", { type: "checkbox", name: "evidencias", value: e.id, checked: !barrada && marcadas.has(e.id), disabled: barrada });
          return el("label", { class: "check-row" }, caixa, el("span", {}, `${dataBr(e.data)} · ${e.turma}`, barrada ? badge("Sem autorização de imagem de todos os presentes", "amber") : null));
        });

        function seguir(evento) {
          evento.preventDefault();
          evento.stopPropagation();
          estado.evidencias = comEvidencias ? evidencias.map((l) => l.querySelector("input")).filter((i) => i.checked).map((i) => i.value) : null;
          previsualizar();
        }

        const pendencias = previa.pendencias;
        return el(
          "section",
          { class: "card form-card" },
          stepper(2),
          el(
            "form",
            { novalidate: true, onsubmit: seguir },
            el(
              "div",
              { class: "form-body" },
              el(
                "p",
                { class: pendencias.length ? "aviso-pendencias" : "muted", role: "note" },
                pendencias.length
                  ? `${pendencias.length} ${pendencias.length === 1 ? "pendência encontrada" : "pendências encontradas"} no período. Corrija os registros para a versão final ou siga para um rascunho.`
                  : "Todos os registros do período estão prontos para a emissão.",
              ),
              pendencias.length
                ? tabela(
                    ["Pendência", "Quantidade", ""],
                    pendencias.map((p) =>
                      el("tr", {}, el("td", {}, p.descricao), el("td", {}, String(p.quantidade)), el("td", {}, el("a", { class: "text-link", href: ONDE_CORRIGIR[p.tipo] || "#/atividades" }, "Corrigir"))),
                    ),
                  )
                : null,
              comEvidencias ? el("h3", { class: "afastado" }, "Evidências desta versão") : null,
              comEvidencias
                ? evidencias.length
                  ? [el("p", { class: "muted" }, externa ? "Na circulação externa, só entram evidências com autorização de imagem de todas as pessoas presentes." : "Escolha o que entra no relatório."), ...evidencias]
                  : el("p", { class: "muted" }, "Nenhuma evidência no período.")
                : null,
            ),
            el(
              "div",
              { class: "form-actions" },
              el("button", { type: "button", class: "btn", onclick: configurar }, "Voltar"),
              el("button", { type: "submit", class: "btn primary" }, pendencias.length ? "Visualizar rascunho" : "Pré-visualizar relatório"),
            ),
          ),
        );
      },
    );
  }

  // Passo 3 ------------------------------------------------------------------------------
  function previsualizar() {
    carregarNaTela(
      container,
      () => chamadas.obterPreviaDoRelatorio(pedido()),
      (previa) => {
        const rascunho = previa.pendencias.length > 0;
        async function exportar(formato, botao) {
          botao.disabled = true;
          try {
            const arquivo = await chamadas.exportarRelatorio(pedido(), formato);
            baixar(arquivo, nomeDoArquivo(nomeDoPrograma(), estado.inicio, estado.fim, formato));
            avisar(`Relatório exportado em ${formato.toUpperCase()} e registrado no histórico.`);
          } catch (e) {
            avisar(e?.detalhe || e?.message || "Não foi possível exportar o relatório.");
          } finally {
            botao.disabled = false;
          }
        }
        const botaoPdf = el("button", { type: "button", class: "btn", onclick: () => exportar("pdf", botaoPdf) }, "Exportar PDF");
        const botaoXlsx = el("button", { type: "button", class: "btn primary", onclick: () => exportar("xlsx", botaoXlsx) }, "Exportar XLSX");
        return el(
          "div",
          { class: "stack" },
          stepper(3),
          el("div", { class: "actions acoes-direita no-print" }, el("button", { type: "button", class: "btn", onclick: configurar }, "Ajustar configuração"), botaoPdf, botaoXlsx),
          el(
            "article",
            { class: "report-preview" },
            el("div", { class: "eyebrow" }, `${rascunho ? "Rascunho · pendências em aberto" : "Relatório técnico"} · ${FINALIDADES[previa.finalidade][0]}`),
            el("h1", {}, previa.titulo),
            el("dl", { class: "details" }, previa.cabecalho.flatMap(([rotulo, valor]) => [el("dt", {}, rotulo), el("dd", {}, valor)])),
            previa.conteudo.flatMap((s) => [
              el("h2", {}, s.titulo),
              s.linhas.length ? tabela(s.colunas, s.linhas.map((linha) => el("tr", {}, linha.map((v) => el("td", {}, v))))) : el("p", { class: "muted" }, s.vazio),
              s.nota ? el("p", { class: "texto-12 muted" }, s.nota) : null,
            ]),
            el("p", { class: "muted afastado" }, previa.rodape),
          ),
        );
      },
    );
  }

  configurar();
}
