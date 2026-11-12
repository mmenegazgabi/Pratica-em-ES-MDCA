// Dados FIXOS de exemplo das telas que ainda não têm backend (Parte 2 do redesign).
//
// TROCAR PELO BACKEND: quando existir a rota do extrato, a Conciliação passa a buscar
// estes dados na API e este arquivo sai. A Auditoria já lê de GET /auditoria.
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

