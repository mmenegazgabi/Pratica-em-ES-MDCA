// Auditoria: regra sem DOM (testável no Node).

/** Filtra o histórico por texto (quem, ação ou detalhe), sem diferenciar maiúsculas. */
export function filtrarAuditoria(registros, texto) {
  const busca = String(texto || "").trim().toLowerCase();
  if (!busca) return registros;
  return registros.filter((r) => [r.quem, r.acao, r.alvo].some((campo) => String(campo).toLowerCase().includes(busca)));
}
