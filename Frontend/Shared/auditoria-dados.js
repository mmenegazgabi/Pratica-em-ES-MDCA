// Auditoria única da plataforma (tela em Gestao/telas/auditoria.js): regras sem DOM,
// testáveis no Node. A trilha vem de GET /auditoria, com os três módulos.

/** Itens por página pedidos a GET /auditoria (a API aceita até 200). */
export const TAMANHO_DA_PAGINA = 50;

/** Opções do filtro "Módulo" (valor do parâmetro `modulo` → texto na tela). */
export const MODULOS = Object.freeze([
  ["todos", "Todos"],
  ["gestao", "Gestão"],
  ["financeiro", "Financeiro"],
  ["plataforma", "Acesso e contas"],
]);

/** "gestao" → "Gestão"; um módulo desconhecido aparece como veio. */
export function rotuloDoModulo(modulo) {
  const achado = MODULOS.find(([valor]) => valor === modulo && valor !== "todos");
  return achado ? achado[1] : String(modulo ?? "");
}

/** Filtra o histórico por texto (quem, ação, detalhe ou módulo), sem diferenciar maiúsculas. */
export function filtrarAuditoria(registros, texto) {
  const busca = String(texto || "").trim().toLowerCase();
  if (!busca) return registros;
  return registros.filter((r) =>
    [r.quem, r.acao, r.alvo, r.modulo ? rotuloDoModulo(r.modulo) : ""].some((campo) => String(campo ?? "").toLowerCase().includes(busca)),
  );
}

/** "2026-11-11T21:06:20+00:00" → "11/11/2026 18:06", no horário de Brasília (o da ONG). */
export function formatarQuando(iso) {
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return String(iso ?? "");
  const partes = Object.fromEntries(
    new Intl.DateTimeFormat("pt-BR", {
      timeZone: "America/Sao_Paulo",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(data)
      .map((p) => [p.type, p.value]),
  );
  return `${partes.day}/${partes.month}/${partes.year} ${partes.hour}:${partes.minute}`;
}

/** Filtros da tela → parâmetros de GET /auditoria (sem módulo escolhido, todos). */
export function filtrosDaApi({ modulo, desde, ate, pagina }) {
  return { modulo: modulo || "todos", desde: desde || "", ate: ate || "", pagina: pagina || 1, tamanho: TAMANHO_DA_PAGINA };
}

/** "1–50 de 120"; "Nenhum registro" quando não há nada. */
export function intervaloDaPagina(pagina, tamanho, total) {
  if (!total) return "Nenhum registro";
  const primeiro = (pagina - 1) * tamanho + 1;
  const ultimo = Math.min(pagina * tamanho, total);
  return `${primeiro}–${ultimo} de ${total}`;
}

export function ultimaPagina(tamanho, total) {
  return Math.max(1, Math.ceil((total || 0) / tamanho));
}
