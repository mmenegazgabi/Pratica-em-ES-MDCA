// Sessão do Financeiro = sessão da plataforma (login único) + papel em uso neste navegador.

import { CHAVE_PAPEL_FINANCEIRO, lerSessao as lerSessaoDaPlataforma, temPapel } from "../../Shared/plataforma.js";

export const PAPEIS = {
  coordenacao: "Coordenação",
  direcao: "Diretoria",
  voluntario_financeiro: "Voluntário financeiro",
  educador: "Educador",
};

/** Papéis do Financeiro que a pessoa da sessão tem, na ordem de PAPEIS. */
export function papeisDoFinanceiro(sessaoPlataforma) {
  return Object.keys(PAPEIS).filter((papel) => temPapel(sessaoPlataforma, papel));
}

function papelSalvo() {
  try {
    return localStorage.getItem(CHAVE_PAPEL_FINANCEIRO);
  } catch {
    return null;
  }
}

/**
 * {papel, nome, usuarioId} da pessoa logada, ou null sem sessão da plataforma.
 * Papel: o escolhido (se ainda for da pessoa), senão o único do Financeiro, senão null.
 */
export function lerSessao() {
  const sessao = lerSessaoDaPlataforma();
  if (!sessao) return null;
  const papeis = papeisDoFinanceiro(sessao);
  const salvo = papelSalvo();
  const papel = papeis.includes(salvo) ? salvo : papeis.length === 1 ? papeis[0] : null;
  return { papel, nome: String(sessao.usuario.nome || ""), usuarioId: String(sessao.usuario.id || "") };
}

export function escolherPapel(papel) {
  if (!PAPEIS[papel]) return;
  try {
    localStorage.setItem(CHAVE_PAPEL_FINANCEIRO, papel);
  } catch {
    /* navegador sem armazenamento: a escolha não fica salva */
  }
}

export function esquecerPapel() {
  try {
    localStorage.removeItem(CHAVE_PAPEL_FINANCEIRO);
  } catch {
    /* navegador sem armazenamento */
  }
}

/** "marcos-vieira" → "Marcos Vieira"; vazio → "". */
export function nomeDoAutor(autorId) {
  return String(autorId || "")
    .split("-")
    .filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join(" ");
}

/** " Marcos Vieira " → "marcos-vieira". */
export function usuarioId(nome) {
  return String(nome)
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "-");
}

const ITENS = {
  inicio: { id: "inicio", rotulo: "Início", icone: "inicio", rota: "#/inicio" },
  lancamentos: { id: "lancamentos", rotulo: "Lançamentos", icone: "lancamentos", rota: "#/lancamentos" },
  projetos: { id: "projetos", rotulo: "Projetos", icone: "projetos", rota: "#/projetos" },
  conciliacao: { id: "conciliacao", rotulo: "Conciliação", icone: "conciliacao", rota: "#/conciliacao" },
  relatorios: { id: "relatorios", rotulo: "Relatórios", icone: "relatorios", rota: "#/relatorios" },
  auditoria: { id: "auditoria", rotulo: "Auditoria", icone: "auditoria", rota: "#/auditoria" },
};

const MENU_POR_PAPEL = {
  coordenacao: ["inicio", "lancamentos", "projetos", "relatorios", "auditoria"],
  direcao: ["inicio", "projetos", "relatorios", "auditoria"],
  voluntario_financeiro: ["inicio", "lancamentos", "conciliacao"],
  educador: [],
};

export function itensDeMenu(papel) {
  return (MENU_POR_PAPEL[papel] || []).map((id) => ({ ...ITENS[id] }));
}
