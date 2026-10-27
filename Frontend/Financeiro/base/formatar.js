// Formatação de valores e datas (sem DOM, testável no Node).

const DIA_MS = 24 * 60 * 60 * 1000;

export function formatarMoeda(valor) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(valor);
}

/** Soma em centavos inteiros: 0.1 + 0.2 = 0.3. */
export function somarReais(valores) {
  const centavos = valores.reduce((total, v) => total + Math.round(Number(v) * 100), 0);
  return centavos / 100;
}

/** "2026-10-26" (ou "2026-10-26T10:00:00Z") → "26/10/2026". */
export function formatarData(iso) {
  const [ano, mes, dia] = String(iso).slice(0, 10).split("-");
  return `${dia}/${mes}/${ano}`;
}

export function formatarDataCurta(iso) {
  return formatarData(iso).slice(0, 5);
}

/** Dias inteiros entre o instante informado e agora (nunca negativo). */
export function diasDesde(isoDataHora, agora = new Date()) {
  const dias = Math.floor((agora.getTime() - new Date(isoDataHora).getTime()) / DIA_MS);
  return Math.max(0, dias);
}

export function tempoRelativo(isoDataHora, agora = new Date()) {
  const dias = diasDesde(isoDataHora, agora);
  if (dias === 0) return "hoje";
  return dias === 1 ? "há 1 dia" : `há ${dias} dias`;
}
