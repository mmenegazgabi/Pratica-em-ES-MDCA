// Menu único da plataforma: quem tem um papel nos dois módulos (Coordenação, Direção,
// Educador) vê as abas da Gestão e do Financeiro numa lista só, sem trocar de módulo.
//
// Os dois módulos continuam sendo páginas separadas (/Gestao/ e /Financeiro/); cada um
// monta a barra lateral com esta lista, e a aba do outro módulo leva direto para ele.
// Quem só tem papel num módulo continua com o menu do módulo (`menuUnificado` dá null).
// Como sempre, o menu só esconde telas: quem protege os dados é a API.

import { PERFIL_DO_PAPEL, menuDoPapel, salvarPapel } from "../Gestao/base/papeis.js";
import { escolherPapel, itensDeMenu } from "../Financeiro/base/sessao.js";
import { temPapel } from "./plataforma.js";

const PAPEIS_DOS_DOIS_MODULOS = ["coordenacao", "direcao", "educador"];

// Abas com o mesmo nome nos dois módulos ganham nomes diferentes no menu único.
// A Auditoria é uma aba só, da Gestão, com a trilha dos dois módulos (telas/auditoria.js).
const NOMES_GESTAO = { "Indicadores e relatórios": "Relatório técnico" };
const NOMES_FINANCEIRO = { inicio: "Resumo financeiro", relatorios: "Prestação de contas" };
const GRUPO_DO_FIM = "Auditoria e implantação"; // fica por último, depois das abas do Financeiro

// Ícone de cada aba no desenho de cada módulo: {gestao, financeiro}.
const ICONE_DA_SECAO = {
  inicio: ["home", "inicio"],
  programas: ["program", "projetos"],
  turmas: ["program", "projetos"],
  projetos: ["program", "projetos"],
  pessoas: ["people", "perfil"],
  atividades: ["calendar", "calendario"],
  sincronizacao: ["calendar", "calendario"],
  alertas: ["bell", "sino"],
  atendimentos: ["bell", "sino"],
  rede: ["bell", "sino"],
  aprendizagem: ["book", "lancamentos"],
  indicadores: ["chart", "relatorios"],
  relatorios: ["chart", "relatorios"],
  integracao: ["grid", "painel"],
  usuarios: ["settings", "perfil"],
  auditoria: ["shield", "auditoria"],
  importacao: ["upload", "importar"],
};
const ICONE_DO_FINANCEIRO = {
  inicio: "home",
  lancamentos: "file",
  painel: "grid",
  projetos: "money",
  conciliacao: "check",
  relatorios: "chart",
  lancar: "plus",
};
const icones = ([gestao, financeiro] = ["file", "lancamentos"]) => ({ gestao, financeiro });

/** Perfil da Gestão ("coord") → papel da plataforma ("coordenacao"); null se não houver. */
export function papelDaPlataforma(perfil) {
  return Object.keys(PERFIL_DO_PAPEL).find((papel) => PERFIL_DO_PAPEL[papel] === perfil) || null;
}

/**
 * Grava o papel em uso no módulo `para` ("gestao" ou "financeiro"), para a aba do outro
 * módulo abrir com o mesmo papel. Só o outro: a escolha do módulo atual fica como está.
 */
export function sincronizarPapel(papel, { para } = {}) {
  if (!PAPEIS_DOS_DOIS_MODULOS.includes(papel)) return;
  if (para === "financeiro") escolherPapel(papel);
  if (para === "gestao") salvarPapel(PERFIL_DO_PAPEL[papel]);
}

/**
 * Abas do menu único para a pessoa agindo com `papel` (id da plataforma), ou null quando
 * esse papel não existe nos dois módulos ou não é dela. `modulo` é onde a página está
 * ("gestao" ou "financeiro"); `atual`, a seção (Gestão) ou tela (Financeiro) aberta.
 * Cada aba: {rotulo, href, ativo, icone: {gestao, financeiro}}.
 */
export function menuUnificado(sessao, papel, { modulo, atual = "" } = {}) {
  if (!PAPEIS_DOS_DOIS_MODULOS.includes(papel) || !temPapel(sessao, papel)) return null;
  const naGestao = modulo === "gestao";
  const hrefGestao = (secao) => (naGestao ? "" : "../Gestao/") + "#/" + secao;
  const hrefFinanceiro = (rota) => (naGestao ? "../Financeiro/" : "") + rota;

  const gestao = [];
  const fimDaGestao = [];
  for (const { grupo, itens } of menuDoPapel(PERFIL_DO_PAPEL[papel], naGestao ? atual : "")) {
    for (const item of itens) {
      (grupo === GRUPO_DO_FIM ? fimDaGestao : gestao).push({
        rotulo: NOMES_GESTAO[item.rotulo] || item.rotulo,
        href: hrefGestao(item.secao),
        ativo: item.ativo,
        icone: icones(ICONE_DA_SECAO[item.secao]),
      });
    }
  }

  const telaAtual = !naGestao && atual === "projeto" ? "projetos" : atual;
  const financeiro = itensDeMenu(papel).map((item) => ({
    id: item.id,
    rotulo: NOMES_FINANCEIRO[item.id] || item.rotulo,
    href: hrefFinanceiro(item.rota),
    ativo: !naGestao && item.id === telaAtual,
    icone: { gestao: ICONE_DO_FINANCEIRO[item.id] || "file", financeiro: item.icone },
  }));
  // O educador lança despesas pela tela do celular, que não tem menu.
  if (papel === "educador") {
    financeiro.push({
      id: "lancar",
      rotulo: "Lançar despesa",
      href: hrefFinanceiro("lancamento/"),
      ativo: false,
      icone: { gestao: ICONE_DO_FINANCEIRO.lancar, financeiro: "mais" },
    });
  }

  return [...gestao, ...financeiro, ...fimDaGestao].map(({ id, ...item }) => item);
}
