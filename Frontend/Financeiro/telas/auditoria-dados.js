// Auditoria: regras sem DOM (testáveis no Node).

/** Quantos eventos a tela pede por página ao GET /auditoria. */
export const TAMANHO_DA_PAGINA = 50;

const FORMATO_OCORRIDO = new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** "2026-10-05T12:00:00Z" → "05/10/2026 09:00" (horário de Brasília). */
export function formatarOcorrido(iso) {
  const data = iso ? new Date(iso) : null;
  if (!data || Number.isNaN(data.getTime())) return "—";
  const partes = Object.fromEntries(FORMATO_OCORRIDO.formatToParts(data).map((p) => [p.type, p.value]));
  return `${partes.day}/${partes.month}/${partes.year} ${partes.hour}:${partes.minute}`;
}

/** Período e página da tela → consulta do GET /auditoria; período invertido não vai para a API. */
export function filtrosDaAuditoria({ desde = "", ate = "", pagina = 1 } = {}) {
  if (desde && ate && desde > ate) return { filtros: null, erro: "A data inicial não pode ser depois da final." };
  const filtros = { pagina: Math.max(1, Math.trunc(Number(pagina)) || 1), tamanho: TAMANHO_DA_PAGINA };
  if (desde) filtros.desde = desde;
  if (ate) filtros.ate = ate;
  return { filtros, erro: null };
}

const semAcento = (texto) =>
  String(texto ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase();

/** Busca na página já carregada: pessoa, ação ou descrição (sem diferenciar acento e maiúsculas). */
export function filtrarNaPagina(itens, texto) {
  const busca = semAcento(texto).trim();
  if (!busca) return itens;
  return itens.filter((e) => [e.quem, e.acao, e.alvo].some((campo) => semAcento(campo).includes(busca)));
}

/** "N eventos", "Página X de Y" e se há página anterior/próxima. */
export function paginacao({ total = 0, pagina = 1, tamanho = TAMANHO_DA_PAGINA } = {}) {
  const paginas = Math.max(1, Math.ceil(total / tamanho));
  return {
    total: `${total} ${total === 1 ? "evento" : "eventos"}`,
    pagina: `Página ${Math.min(pagina, paginas)} de ${paginas}`,
    temAnterior: pagina > 1,
    temProxima: pagina < paginas,
  };
}
