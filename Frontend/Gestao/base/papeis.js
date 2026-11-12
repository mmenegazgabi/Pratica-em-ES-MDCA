// Perfis de acesso e menu lateral de Gestão, vindos do protótipo da E2.
//
// Aqui só se decide o que cada perfil VÊ na interface. Quem protege os dados é a
// API (RBAC, T-33): esconder um item do menu não impede ninguém de chamar a rota.
// Com o login (T-35), o perfil vem dos papéis da pessoa (`perfisDaSessao`); sem
// sessão (modo de teste com o código de acesso), ele é escolhido no menu do usuário
// e fica salvo neste aparelho.

export const PAPEIS = {
  coord: { name: "Ana Martins", label: "Coordenação", programs: ["p1", "p2", "p3"] },
  educator: { name: "Jéssica Almeida", label: "Educadora", programs: ["p1"] },
  social: { name: "Patrícia Souza", label: "Assistente social", programs: ["p1", "p2"] },
  psych: { name: "Rafael Nunes", label: "Psicólogo", programs: ["p1"] },
  director: { name: "Diretoria", label: "Consulta institucional", programs: ["p1", "p2", "p3"] },
  admin: { name: "Administrador", label: "Administração do sistema", programs: ["p1", "p2", "p3"] },
};

export const PAPEL_PADRAO = "coord";

export const DESCRICOES = {
  coord: "Organiza programas, equipes, cadastros e relatórios. Consulta a visão integrada, a lista de atendimentos e a rede, sem acessar conteúdo sigiloso.",
  educator: "Registra atividades, frequência e evidências apenas nos programas em que atua.",
  social: "Acompanha famílias, atendimentos sociais, busca ativa e retornos da rede.",
  psych: "Consulta e registra atendimentos psicológicos. Acesso restrito aos próprios registros.",
  director: "Consulta indicadores, relatórios técnicos e dados integrados, sem editar cadastros.",
  admin: "Acessa e gerencia todas as áreas da plataforma, incluindo usuários, perfis e programas de cada conta.",
};

// Quem pode cada tarefa; uma tarefa fora da lista vale para todos os perfis.
const TAREFAS = {
  manage: ["coord"],
  technical: ["social", "psych"],
  social: ["social"],
  psych: ["psych"],
  audit: ["coord", "psych"],
  finance: ["coord", "director"],
  report: ["coord", "director"],
  record: ["coord", "educator"],
  people: ["coord", "social"],
  import: ["coord"],
};

export function pode(papel, tarefa) {
  return papel === "admin" || (TAREFAS[tarefa] || Object.keys(PAPEIS)).includes(papel);
}

export function rotaPermitida(papel, secao) {
  if (papel === "admin") return true;
  if (secao === "usuarios") return false;
  if (["importacao", "equipe"].includes(secao)) return pode(papel, "manage");
  if (secao === "auditoria") return pode(papel, "audit");
  if (secao === "relatorios") return pode(papel, "report");
  if (secao === "atendimentos") return pode(papel, "technical") || papel === "coord";
  if (secao === "rede") return pode(papel, "social") || papel === "coord";
  if (secao === "integracao") return pode(papel, "finance");
  if (secao === "aprendizagem") return ["coord", "social", "director"].includes(papel);
  if (secao === "alertas") return ["coord", "social"].includes(papel);
  if (secao === "pessoas") return papel !== "director";
  return true;
}

// Grupos curtos, no padrão do Financeiro; cada item reúne rotas irmãs e abre a
// primeira que o perfil pode ver.
export const MENU = [
  ["Programas e público", [["Visão geral", ["inicio"]], ["Programas e turmas", ["programas", "turmas", "projetos"]], ["Pessoas e famílias", ["pessoas"]]]],
  ["Execução e atendimento", [["Atividades e frequência", ["atividades", "sincronizacao"]], ["Acompanhamento técnico", ["alertas", "atendimentos", "rede"]], ["Aprendizagem", ["aprendizagem"]]]],
  ["Resultados", [["Indicadores e relatórios", ["indicadores", "relatorios"]], ["Visão integrada", ["integracao"]]]],
  ["Auditoria e implantação", [["Usuários e acessos", ["usuarios"]], ["Trilha de auditoria", ["auditoria"]], ["Importação e piloto", ["importacao"]]]],
];

// Abas que ligam telas irmãs agrupadas no mesmo item do menu.
export const ABAS = {
  programas: [["Programas", "programas"], ["Turmas", "turmas"]],
  acompanhamento: [["Alertas e busca ativa", "alertas"], ["Atendimentos", "atendimentos"], ["Rede de proteção", "rede"]],
  resultados: [["Indicadores", "indicadores"], ["Relatório técnico", "relatorios"]],
};

/** Menu do perfil: grupos sem item permitido somem. */
export function menuDoPapel(papel, secaoAtual = "") {
  return MENU.map(([grupo, itens]) => ({
    grupo,
    itens: itens.flatMap(([rotulo, secoes]) => {
      const destino = secoes.find((s) => rotaPermitida(papel, s));
      return destino ? [{ rotulo, secao: destino, ativo: secoes.includes(secaoAtual) }] : [];
    }),
  })).filter((g) => g.itens.length);
}

// Login (T-35): papel da plataforma (tabela `papeis`) -> perfil da interface.
// O voluntário financeiro não tem perfil na Gestão.
export const PERFIL_DO_PAPEL = {
  administracao: "admin",
  coordenacao: "coord",
  direcao: "director",
  assistente_social: "social",
  psicologo: "psych",
  educador: "educator",
};
// Do mais amplo ao mais restrito: sem escolha salva, a pessoa entra com o primeiro.
const ORDEM_DOS_PERFIS = ["admin", "coord", "director", "social", "psych", "educator"];

/** Perfis da Gestão que a pessoa logada tem, do mais amplo ao mais restrito. */
export function perfisDaSessao(sessao) {
  const papeis = Array.isArray(sessao?.usuario?.papeis) ? sessao.usuario.papeis : [];
  const ids = new Set(papeis.map((p) => PERFIL_DO_PAPEL[typeof p === "string" ? p : p?.id]).filter(Boolean));
  return ORDEM_DOS_PERFIS.filter((perfil) => ids.has(perfil));
}

/**
 * Perfil com que a pessoa logada entra: o escolhido antes neste aparelho, se ainda
 * for um dos dela, ou o mais amplo. ``null`` quando ela não tem papel na Gestão.
 */
export function perfilDaSessao(sessao, salvo = lerPapelSalvo()) {
  const perfis = perfisDaSessao(sessao);
  if (!perfis.length) return null;
  return perfis.includes(salvo) ? salvo : perfis[0];
}

const CHAVE_PAPEL = "mdca.gestao.papel";

function lerPapelSalvo() {
  try {
    return localStorage.getItem(CHAVE_PAPEL);
  } catch {
    return null;
  }
}

export function lerPapel() {
  try {
    const papel = localStorage.getItem(CHAVE_PAPEL);
    return PAPEIS[papel] ? papel : PAPEL_PADRAO;
  } catch {
    return PAPEL_PADRAO;
  }
}

export function salvarPapel(papel) {
  try {
    localStorage.setItem(CHAVE_PAPEL, papel);
  } catch {
    /* navegador sem armazenamento: o perfil vale só até fechar a página */
  }
}
