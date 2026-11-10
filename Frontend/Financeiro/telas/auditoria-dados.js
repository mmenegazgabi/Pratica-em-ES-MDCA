// Auditoria: regras sem DOM (testáveis no Node).

export const MODULOS = [
  ["financeiro", "Financeiro"],
  ["gestao", "Gestão"],
  ["plataforma", "Plataforma"],
];

// Ações conhecidas da trilha (log_auditoria); as outras aparecem com o código legível.
const ACOES = {
  login: "Entrou",
  login_falhou: "Login recusado",
  logout: "Saiu",
  primeiro_acesso: "Primeiro acesso",
  codigo_gerado: "Código de acesso gerado",
  codigo_emitido: "Código de acesso emitido",
  acesso_negado: "Acesso negado",
  usuario_criado: "Usuário criado",
  usuario_editado: "Usuário editado",
  usuario_reativado: "Usuário reativado",
  usuario_desativado: "Usuário desativado",
  alerta_infrequencia: "Alerta de infrequência",
  alerta_encerrado: "Alerta encerrado",
  acao_busca_ativa: "Busca ativa registrada",
  download_documento: "Download de documento",
  download_evidencia: "Download de evidência",
  autorizacao_revogada: "Autorização revogada",
  duplicidade_confirmada: "Duplicidade confirmada",
  conflito_de_horario: "Conflito de horário",
  consulta_visao_integrada: "Consulta à visão integrada",
};

export function rotuloDaAcao(acao) {
  if (!acao) return "—";
  if (ACOES[acao]) return ACOES[acao];
  const texto = String(acao).replace(/_/g, " ").trim();
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

export function rotuloDoModulo(modulo) {
  if (!modulo) return "—";
  return MODULOS.find(([id]) => id === modulo)?.[1] || String(modulo);
}

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

/** Filtros da tela → consulta do GET /auditoria; período invertido não vai para a API. */
export function filtrosDaAuditoria({ texto = "", modulo = "", desde = "", ate = "" } = {}) {
  if (desde && ate && desde > ate) return { filtros: null, erro: "A data inicial não pode ser depois da final." };
  const filtros = {};
  const busca = String(texto).trim();
  if (busca) filtros.texto = busca;
  if (modulo) filtros.modulo = modulo;
  if (desde) filtros.desde = desde;
  if (ate) filtros.ate = ate;
  return { filtros, erro: null };
}
