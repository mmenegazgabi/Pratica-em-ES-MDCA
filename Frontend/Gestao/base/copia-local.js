// Última resposta de consultas que o registro em campo precisa sem conexão (T-57):
// a agenda do programa e a turma com a lista de matriculados. Com rede, a consulta vai
// à API e a cópia é atualizada; sem rede, a tela usa a cópia e avisa de quando ela é.
//
// A cópia da turma tem nomes de crianças e adolescentes: fica só neste aparelho, no
// mesmo navegador em que a pessoa entrou, e sai em `apagarCopias()` (ao sair).

import { ERROS, ErroApi } from "./api.js";

const PREFIXO = "mdca.gestao.copia.";

function armazenamento() {
  try {
    return globalThis.localStorage || null;
  } catch {
    return null;
  }
}

/**
 * `buscar()` chama a API. Devolve `{ dados, copiaDe }`: `copiaDe` é vazio quando os dados
 * vieram agora da API, ou a data (ISO) da cópia usada por falta de conexão.
 */
export async function consultarComCopia(chave, buscar, { agora = () => new Date() } = {}) {
  const local = armazenamento();
  try {
    const dados = await buscar();
    try {
      local?.setItem(PREFIXO + chave, JSON.stringify({ salvoEm: agora().toISOString(), dados }));
    } catch {
      /* aparelho sem espaço: a tela funciona, só não terá a cópia sem rede */
    }
    return { dados, copiaDe: "" };
  } catch (erro) {
    if (!(erro instanceof ErroApi) || erro.tipo !== ERROS.REDE) throw erro;
    let copia = null;
    try {
      copia = JSON.parse(local?.getItem(PREFIXO + chave) || "null");
    } catch {
      copia = null;
    }
    if (!copia) throw erro;
    return { dados: copia.dados, copiaDe: copia.salvoEm };
  }
}

/** Apaga todas as cópias deste aparelho. */
export function apagarCopias() {
  const local = armazenamento();
  if (!local) return;
  const chaves = [];
  for (let i = 0; i < local.length; i += 1) if (local.key(i)?.startsWith(PREFIXO)) chaves.push(local.key(i));
  for (const chave of chaves) local.removeItem(chave);
}
