// Dados FIXOS de exemplo das telas que ainda não têm backend (Parte 2 do redesign).
//
// TROCAR PELO BACKEND: quando existirem as rotas de extrato, pessoas/papéis e
// auditoria, as telas passam a buscar estes dados na API e este arquivo sai.
// Nada aqui é salvo: o que a tela muda vale só até recarregar a página.

/** Itens do extrato bancário do mês (saídas em valor positivo). */
export const EXTRATO_EXEMPLO = [
  { referencia: "EXT-1027-04", data: "2026-10-27", descricao: "PIX PAPELARIA CENTRAL", valor: 180 },
  { referencia: "EXT-1024-02", data: "2026-10-24", descricao: "UBER *TRIP", valor: 45 },
  { referencia: "EXT-1023-11", data: "2026-10-23", descricao: "DEB MERCADO BOM PRECO", valor: 92.5 },
  { referencia: "EXT-1012-07", data: "2026-10-12", descricao: "PIX MALHARIA SUL", valor: 310 },
  { referencia: "EXT-1009-03", data: "2026-10-09", descricao: "DEB PADARIA ESPERANCA", valor: 76.4 },
  { referencia: "EXT-1005-01", data: "2026-10-05", descricao: "TAR MANUTENCAO CONTA", valor: 19.9 },
];

/** Pessoas com acesso ao módulo financeiro. `convite` = ainda não entrou. */
export const PESSOAS_EXEMPLO = [
  { id: "p1", nome: "Luana Ferraz", email: "luana@mdca.org.br", papel: "coordenacao", projetos: "Todos", convite: false },
  { id: "p2", nome: "Jane Almeida", email: "jane@mdca.org.br", papel: "direcao", projetos: "Todos", convite: false },
  { id: "p3", nome: "Lucas Prado", email: "lucas@mdca.org.br", papel: "voluntario_financeiro", projetos: "Todos", convite: false },
  { id: "p4", nome: "Marcos Vieira", email: "marcos@mdca.org.br", papel: "educador", projetos: "Leitura", convite: false },
  { id: "p5", nome: "Carla Souza", email: "carla@mdca.org.br", papel: "educador", projetos: "Esporte", convite: true },
];

/** Histórico de ações (mais recentes primeiro). */
export const AUDITORIA_EXEMPLO = [
  { quando: "2026-10-27T14:32:00", quem: "Luana Ferraz", acao: "Aprovou despesa", alvo: "Materiais · R$ 180,00 · Leitura" },
  { quando: "2026-10-27T11:05:00", quem: "Lucas Prado", acao: "Conciliou lançamento", alvo: "Transporte · R$ 45,00 · EXT-1024-02" },
  { quando: "2026-10-26T16:48:00", quem: "Luana Ferraz", acao: "Rejeitou despesa", alvo: "Alimentação · R$ 64,00 · Esporte" },
  { quando: "2026-10-25T09:20:00", quem: "Luana Ferraz", acao: "Editou orçamento", alvo: "Esporte · valor total R$ 10.000,00" },
  { quando: "2026-10-24T18:02:00", quem: "Ana Santos", acao: "Convidou pessoa", alvo: "Carla Souza · Educador" },
  { quando: "2026-10-22T10:15:00", quem: "Jane Almeida", acao: "Gerou prestação de contas", alvo: "Leitura · 3º trimestre" },
];
