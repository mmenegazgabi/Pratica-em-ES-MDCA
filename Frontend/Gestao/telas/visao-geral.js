// Visão geral (#/inicio) ligada à API (T-91 · US-10).
//
// Cada parte vem de uma fonte que já existe, sem cálculo próprio na tela:
//
// | Parte                                   | Fonte                                         |
// |-----------------------------------------|-----------------------------------------------|
// | Pessoas, encontros e frequência         | GET /gestao/indicadores (T-72), mês atual     |
// | Cada programa, um caminho (metas)       | a mesma resposta dos indicadores              |
// | Pontos de atenção e Precisam do seu olhar | alertas abertos (avisos da T-90)            |
// | Na agenda da semana                     | GET …/programas/{id}/agenda (T-56)            |
// | Antes de fechar o período               | GET /gestao/pendencias (T-91)                 |
//
// O filtro de programa vale para todos os cartões. Cada cartão carrega sozinho: se uma
// fonte falha, só aquele cartão mostra o erro, com "Tentar de novo"; os outros seguem.
// A API já limita cada perfil aos programas que ele pode consultar.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el, secao } from "../base/dom.js";
import { hojeIso } from "../base/formulario.js";
import { rotaDoEncontro, rotaDoRegistro } from "./atividades.js";

const API_PADRAO = {
  listarProgramas: api.listarProgramas,
  obterIndicadores: api.obterIndicadores,
  obterPendencias: api.obterPendencias,
  obterAgenda: api.obterAgenda,
};

const DIAS = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"];
const numero = (valor) => Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: 1 });
const porcento = (valor) => (valor === null || valor === undefined ? "—" : `${numero(valor)}%`);
const dataCurta = (iso) => iso.slice(8, 10) + "/" + iso.slice(5, 7);
const hora = (texto) => String(texto).slice(0, 5);
const badge = (texto, tom = "") => el("span", { class: `badge ${tom}`.trim() }, texto);
const seta = (texto, href) => el("a", { class: "text-link", href }, texto);

/** AAAA-MM-DD somando dias (datas em UTC, sem fuso). */
export function somarDias(iso, dias) {
  const data = new Date(`${iso}T00:00:00Z`);
  data.setUTCDate(data.getUTCDate() + dias);
  return data.toISOString().slice(0, 10);
}

const diaDaSemana = (iso) => DIAS[new Date(`${iso}T00:00:00Z`).getUTCDay()];

/** Situação do encontro na agenda: registrado, pendente (já passou) ou agendado. */
export function situacao(encontro, hoje) {
  if (encontro.atividades.length) return { texto: "Concluída", tom: "green" };
  if (encontro.data < hoje) return { texto: "Chamada pendente", tom: "amber" };
  return { texto: encontro.data === hoje ? "Hoje" : "Agendada", tom: "gray" };
}

const indicador = (rotulo, valor, nota) =>
  el("div", { class: "stat" }, el("div", { class: "stat-top" }, rotulo), el("div", { class: "stat-value" }, valor), el("div", { class: "stat-note" }, nota));

/** Uma busca por consulta, repetida só depois de falhar (o "Tentar de novo" de cada cartão). */
function umaVez(buscar) {
  let promessa = null;
  return () =>
    (promessa ||= buscar().catch((erro) => {
      promessa = null;
      throw erro;
    }));
}

// --- Cartões -------------------------------------------------------------------------

function numerosDoMes({ totais, programas }) {
  const n = programas.length;
  return [
    indicador("Pessoas acompanhadas", numero(totais.pessoas_acompanhadas), `em ${n} ${n === 1 ? "programa" : "programas"} no seu recorte`),
    indicador("Encontros realizados", numero(totais.encontros_realizados), "com chamada registrada no mês"),
    indicador("Frequência registrada", porcento(totais.frequencia), "presenças sobre as chamadas do mês"),
  ];
}

function caminhos({ programas, periodo }) {
  if (!programas.length) return el("p", { class: "muted" }, "Nenhum programa no seu recorte.");
  return el(
    "div",
    {},
    programas.map(({ programa_id: id, nome, numeros: n }) => {
      const pct = n.percentual_medio_das_metas;
      const atencao = pct !== null && pct < 65;
      return el(
        "div",
        { class: "program-row" },
        el(
          "div",
          { class: "row-top" },
          el("a", { class: "program-title", href: `#/programas/${encodeURIComponent(id)}/plano` }, nome),
          n.metas ? badge(atencao ? "Atenção à meta" : "No caminho", atencao ? "amber" : "green") : badge("Sem metas", "gray"),
        ),
        n.metas ? el("div", { class: `progress${atencao ? " amber" : ""}` }, el("span", { style: `width:${Math.min(100, Math.max(0, pct))}%` })) : null,
        el(
          "div",
          { class: "progress-label" },
          el(
            "span",
            {},
            n.metas ? `Média de ${n.metas} ${n.metas === 1 ? "meta" : "metas"} até ${dataCurta(periodo.fim)}` : "Cadastre as metas no plano do programa",
          ),
          n.metas ? el("strong", {}, porcento(pct)) : null,
        ),
      );
    }),
  );
}

function olhar(alertas) {
  if (!alertas.length) return el("p", { class: "muted" }, "Nenhuma pendência no momento.");
  return alertas
    .slice(0, 3)
    .map((a) =>
      el("div", { class: "priority-item" }, el("div", {}, el("h3", {}, a.title), el("p", {}, a.description), a.link ? seta("Acompanhar", `#${a.link}`) : null)),
    );
}

function agenda(encontros, nomes, { hoje, podeRegistrar }) {
  if (!encontros.length) {
    return el(
      "section",
      { class: "card" },
      el("div", { class: "empty" }, el("h2", {}, "Agenda livre"), el("p", {}, "Nenhum encontro previsto nos próximos sete dias.")),
    );
  }
  return el(
    "section",
    { class: "card" },
    el(
      "div",
      { class: "table-wrap" },
      el(
        "table",
        {},
        el(
          "thead",
          {},
          el(
            "tr",
            {},
            ["Data · hora", "Turma", "Programa", "Educador", "Situação", ""].map((c) => el("th", { scope: "col" }, c)),
          ),
        ),
        el(
          "tbody",
          {},
          encontros.map((e) => {
            const s = situacao(e, hoje);
            const destino = e.atividades.length
              ? rotaDoEncontro(e.programa_id, e.atividades[0])
              : podeRegistrar && e.data <= hoje
                ? rotaDoRegistro(e.programa_id, e.turma_id, e.data)
                : "";
            return el(
              "tr",
              {},
              el("td", {}, `${diaDaSemana(e.data)} ${dataCurta(e.data)}`, el("small", {}, `${hora(e.hora_inicio)}–${hora(e.hora_fim)}`)),
              el("td", {}, e.turma),
              el("td", {}, badge(nomes[e.programa_id] || e.programa_id, "gray")),
              el("td", {}, e.responsavel),
              el("td", {}, badge(s.texto, s.tom)),
              el("td", {}, destino ? seta(e.atividades.length ? "Ver chamada" : "Fazer chamada", destino) : null),
            );
          }),
        ),
      ),
    ),
  );
}

const PENDENCIAS = [
  ["chamadas_sem_registro", "Chamadas sem registro", "Encontros previstos que já passaram e ainda não têm chamada.", "/atividades"],
  ["encontros_sem_evidencia", "Encontros sem evidência", "Encontros do mês sem fotos ou documentos vinculados.", "/atividades"],
  ["autorizacoes_de_imagem_vencidas", "Autorizações de imagem", "Autorizações de uso de imagem vencidas ou revogadas.", "/pessoas"],
];

function pendencias({ totais }, rotaPermitida) {
  const itens = PENDENCIAS.filter(([chave, , , rota]) => totais[chave] > 0 && rotaPermitida(rota));
  if (!itens.length) return el("p", { class: "muted" }, "Nenhum dado ausente no período.");
  return el(
    "div",
    {},
    itens.map(([chave, titulo, texto, rota]) =>
      el("div", { class: "priority-item" }, el("div", {}, el("h3", {}, `${titulo} · ${totais[chave]}`), el("p", {}, texto), seta("Conferir", `#${rota}`))),
    ),
  );
}

// --- Tela ----------------------------------------------------------------------------

/**
 * hoje: AAAA-MM-DD · alertas: () => avisos abertos ({ title, description, link, programa? })
 * podeRegistrar: mostra "Fazer chamada" · mostrarPendencias: cartão "Antes de fechar o período"
 * rotaPermitida: (rota) => boolean, para não levar a uma tela que o perfil não abre
 */
export function mostrarVisaoGeral(
  container,
  { hoje = hojeIso(), alertas = () => [], podeRegistrar = false, mostrarPendencias = false, rotaPermitida = () => true, ...substitutos },
) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const inicio = `${hoje.slice(0, 7)}-01`;
  const programa = el(
    "select",
    { class: "filter-control", "aria-label": "Filtrar programa", name: "programa" },
    el("option", { value: "" }, "Todos os programas"),
  );
  const buscarProgramas = umaVez(() => chamadas.listarProgramas());

  const caixas = {
    numeros: el("div", { class: "visao-geral-numeros" }),
    atencao: el("div", { class: "stat visao-geral-atencao" }),
    caminhos: el("div", {}),
    olhar: el("div", {}),
    agenda: el("div", {}),
    pendencias: el("div", {}),
  };
  const contagemDoOlhar = el("span", {});

  function alertasDoRecorte() {
    const escolhido = programa.value;
    // Alertas da API trazem `programa`; os de demonstração, `program` (ids do protótipo).
    return alertas().filter((a) => !escolhido || (a.programa ?? a.program) === escolhido);
  }

  function carregar() {
    const programaId = programa.value;
    const filtros = { programaId, inicio };
    const indicadores = umaVez(() => chamadas.obterIndicadores(filtros));

    // Números do mês e metas: a mesma resposta, então os dois cartões mudam juntos.
    carregarNaTela(caixas.numeros, indicadores, (r) => el("div", { class: "visao-geral-numeros" }, numerosDoMes(r)));
    carregarNaTela(caixas.caminhos, indicadores, caminhos);

    const abertos = alertasDoRecorte();
    caixas.atencao.replaceChildren(
      el("div", { class: "stat-top" }, "Pontos de atenção"),
      el("div", { class: "stat-value" }, String(abertos.length)),
      el("div", { class: "stat-note" }, "acompanhamentos em aberto"),
    );
    contagemDoOlhar.replaceChildren(badge(`${abertos.length} ${abertos.length === 1 ? "aberto" : "abertos"}`, "amber"));
    caixas.olhar.replaceChildren(...[olhar(abertos)].flat());

    carregarNaTela(
      caixas.agenda,
      async () => {
        const lista = await buscarProgramas();
        const nomes = Object.fromEntries(lista.map((p) => [p.id, p.nome]));
        const ids = programaId ? [programaId] : lista.map((p) => p.id);
        const fim = somarDias(hoje, 6);
        const porPrograma = await Promise.all(
          ids.map(async (id) => (await chamadas.obterAgenda(id, { inicio: hoje, fim })).map((e) => ({ ...e, programa_id: id }))),
        );
        const encontros = porPrograma
          .flat()
          .sort((a, b) => a.data.localeCompare(b.data) || String(a.hora_inicio).localeCompare(String(b.hora_inicio)))
          .slice(0, 6);
        return { encontros, nomes };
      },
      ({ encontros, nomes }) => agenda(encontros, nomes, { hoje, podeRegistrar }),
    );

    if (mostrarPendencias) {
      carregarNaTela(
        caixas.pendencias,
        () => chamadas.obterPendencias(filtros),
        (r) => pendencias(r, rotaPermitida),
      );
    }
  }

  // Os programas do filtro são os que a pessoa pode consultar (a API já filtra).
  buscarProgramas()
    .then((lista) => {
      for (const p of lista) programa.append(el("option", { value: p.id }, p.identificador ? `${p.nome} (${p.identificador})` : p.nome));
    })
    .catch(() => {});
  programa.addEventListener("change", carregar);

  const tela = el(
    "div",
    { class: "stack" },
    el("div", { class: "toolbar" }, el("div", { class: "filters" }, el("span", { class: "filter-label" }, "Visualizando"), programa)),
    el("div", { class: "stats visao-geral-stats" }, caixas.numeros, caixas.atencao),
    el(
      "div",
      { class: "grid-main" },
      secao("Cada programa, um caminho", "Metas do plano de ação, com o realizado até o fim do mês", caixas.caminhos, seta("Ver programas", "#/programas")),
      secao("Precisam do seu olhar", "Próximos passos para a equipe", caixas.olhar, contagemDoOlhar),
    ),
    secao("Na agenda da semana", "Encontros de hoje até os próximos seis dias", caixas.agenda, seta("Ver agenda", "#/atividades")),
    mostrarPendencias ? secao("Antes de fechar o período", "Dados ausentes no mês, no seu recorte", caixas.pendencias) : null,
  );
  container.replaceChildren(tela);
  carregar();
  return tela;
}
