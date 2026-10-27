// Sessão provisória (papel + nome) guardada neste aparelho, até o login (US-08).

export const PAPEIS = {
  coordenacao: "Coordenação",
  direcao: "Diretoria",
  voluntario_financeiro: "Voluntário financeiro",
  educador: "Educador",
};

const CHAVE_SESSAO = "mdca.financeiro.sessao";

export function lerSessao() {
  try {
    const dados = JSON.parse(localStorage.getItem(CHAVE_SESSAO));
    if (dados && PAPEIS[dados.papel] && typeof dados.nome === "string") {
      return { papel: dados.papel, nome: dados.nome };
    }
  } catch {
    /* sem armazenamento ou conteúdo inválido: sem sessão */
  }
  return null;
}

export function salvarSessao({ papel, nome }) {
  try {
    localStorage.setItem(CHAVE_SESSAO, JSON.stringify({ papel, nome }));
  } catch {
    /* navegador sem armazenamento */
  }
}

export function encerrarSessao() {
  try {
    localStorage.removeItem(CHAVE_SESSAO);
  } catch {
    /* navegador sem armazenamento */
  }
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
};

const MENU_POR_PAPEL = {
  coordenacao: ["inicio", "lancamentos", "projetos"],
  direcao: ["inicio", "projetos"],
  voluntario_financeiro: ["inicio", "lancamentos"],
  educador: [],
};

export function itensDeMenu(papel) {
  return (MENU_POR_PAPEL[papel] || []).map((id) => ({ ...ITENS[id] }));
}
