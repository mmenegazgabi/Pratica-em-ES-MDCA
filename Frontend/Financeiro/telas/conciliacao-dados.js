// Conciliação: regras sem DOM (testáveis no Node).
import { diasDesde, formatarMoeda } from "../base/formatar.js";

export const LIMITE_DIAS_ABERTO = 7;

// No extrato do banco a saída vem negativa e o lançamento é sempre positivo:
// a comparação de valores usa o valor sem o sinal.
const centavos = (valor) => Math.abs(Math.round(Number(valor) * 100));

export const LIMITE_ARQUIVO_EXTRATO = 1024 * 1024;

/** "−R$ 180,00" para saída, "+R$ 50,00" para entrada. */
export function valorDoExtrato(valor) {
  const numero = Number(valor);
  return numero < 0 ? `−${formatarMoeda(-numero)}` : `+${formatarMoeda(numero)}`;
}

/** Resultado do POST /extrato: "3 itens importados, 2 repetidos ignorados." */
export function mensagemDaImportacao({ importados = 0, ignorados_repetidos: repetidos = 0 }) {
  const novos = importados === 1 ? "1 item importado" : `${importados} itens importados`;
  const ignorados = repetidos === 1 ? "1 repetido ignorado" : `${repetidos} repetidos ignorados`;
  return `${novos}, ${ignorados}.`;
}

/** Aprovados sem conciliação, os abertos há mais tempo primeiro. */
export function aprovadosEmAberto(lancamentos) {
  return lancamentos
    .filter((l) => l.status === "aprovado" && !l.conciliado)
    .sort((a, b) => String(a.aprovado_em ?? "").localeCompare(String(b.aprovado_em ?? "")));
}

/** Ids dos lançamentos com o mesmo valor (em centavos, sem o sinal) do item do extrato. */
export function mesmoValor(item, lancamentos) {
  if (!item) return [];
  return lancamentos.filter((l) => centavos(l.valor) === centavos(item.valor)).map((l) => l.id);
}

/** Dias desde a aprovação, ou null quando ainda não passou do limite. */
export function diasEmAberto(lancamento, agora = new Date()) {
  if (!lancamento.aprovado_em) return null;
  const dias = diasDesde(lancamento.aprovado_em, agora);
  return dias > LIMITE_DIAS_ABERTO ? dias : null;
}

/** Valores diferentes não impedem, mas a tela avisa antes de conciliar. */
export function valoresDiferentes(item, lancamento) {
  return Boolean(item && lancamento) && centavos(item.valor) !== centavos(lancamento.valor);
}
