// Fila do aparelho para o registro em campo (T-57 · US-05).
//
// Todo registro entra primeiro aqui e só depois vai para a API: sem conexão, ele fica
// guardado no aparelho; com a rede de volta, a fila envia na ordem em que foi gravada.
// Cada encontro (com a chamada) e cada evidência é um item com o próprio `registro_id`,
// gerado aqui. Por isso o reenvio é seguro: a API (T-56) responde 200 com o que já tinha
// gravado, sem duplicar, mesmo que a resposta do primeiro envio tenha se perdido.
//
// Situação de cada item:
// - pendente: aguardando envio (uma evidência também espera o envio do seu encontro);
// - enviado: confirmado pela API, com a data e a hora do envio;
// - erro: o envio falhou e o item continua na fila com a mensagem. Falhas de conexão ou
//   do servidor são tentadas de novo sozinhas; recusas da API (dados inválidos, sem
//   permissão) esperam a pessoa tentar de novo ou descartar.
//
// Os itens ficam no IndexedDB, que guarda também as fotos (o localStorage não comporta).

import { ERROS, ErroApi } from "./api.js";

export const SITUACAO = Object.freeze({ PENDENTE: "pendente", ENVIADO: "enviado", ERRO: "erro" });

// Falhas que passam sozinhas: o item é tentado de novo na próxima sincronização, e as
// demais tentativas desta rodada param (sem conexão, todas falhariam igual).
const PASSAGEIRAS = new Set([ERROS.REDE, ERROS.INDISPONIVEL, ERROS.SESSAO_EXPIRADA, ERROS.NAO_AUTENTICADO, ERROS.SEM_USUARIO]);
const ehPassageira = (erro) => PASSAGEIRAS.has(erro.tipo) || erro.status >= 500;

// Itens enviados somem da lista depois deste prazo (a confirmação já foi vista).
const DIAS_DE_HISTORICO = 7;

const mensagemDoErro = (erro) => erro.detalhe || erro.message;

// --- Armazenamento -----------------------------------------------------------------

/** Para os testes e para navegadores sem IndexedDB: some ao fechar a página. */
export function armazenamentoEmMemoria() {
  const itens = new Map();
  return {
    persistente: false,
    listar: async () => [...itens.values()].map((i) => ({ ...i })),
    gravar: async (item) => void itens.set(item.id, { ...item }),
    remover: async (id) => void itens.delete(id),
  };
}

/** Itens no IndexedDB do aparelho (banco `mdca-gestao`, coleção `fila`). */
export function armazenamentoIndexedDB(idb = globalThis.indexedDB, nome = "mdca-gestao") {
  let aberto = null;

  function abrir() {
    aberto ??= new Promise((resolver, rejeitar) => {
      const pedido = idb.open(nome, 1);
      pedido.onupgradeneeded = () => pedido.result.createObjectStore("fila", { keyPath: "id" });
      pedido.onsuccess = () => resolver(pedido.result);
      pedido.onerror = () => {
        aberto = null;
        rejeitar(pedido.error);
      };
    });
    return aberto;
  }

  async function operar(modo, fazer) {
    const banco = await abrir();
    return new Promise((resolver, rejeitar) => {
      const transacao = banco.transaction("fila", modo);
      const pedido = fazer(transacao.objectStore("fila"));
      transacao.oncomplete = () => resolver(pedido.result);
      transacao.onerror = () => rejeitar(transacao.error);
      transacao.onabort = () => rejeitar(transacao.error);
    });
  }

  return {
    persistente: true,
    listar: () => operar("readonly", (loja) => loja.getAll()),
    gravar: async (item) => void (await operar("readwrite", (loja) => loja.put(item))),
    remover: async (id) => void (await operar("readwrite", (loja) => loja.delete(id))),
  };
}

/** O do aparelho; sem IndexedDB (navegação privada em alguns navegadores), em memória. */
export function armazenamentoDoAparelho() {
  return globalThis.indexedDB ? armazenamentoIndexedDB() : armazenamentoEmMemoria();
}

// --- Fila ----------------------------------------------------------------------------

// Ordem de gravação; as evidências ficam logo depois do seu encontro, mesmo quando dois
// registros têm o mesmo horário.
const grupo = (item) => item.atividadeRegistroId || item.id;
const emOrdem = (a, b) => a.criadoEm.localeCompare(b.criadoEm) || grupo(a).localeCompare(grupo(b)) || a.ordem - b.ordem;

/**
 * api: { registrarAtividade(programaId, turmaId, dados), enviarEvidencia(programaId, atividadeId, evidencia) }
 */
export function criarFila({ armazenamento, api, agora = () => new Date(), novoId = () => crypto.randomUUID() }) {
  const ouvintes = new Set();
  let rodada = null;

  async function listar() {
    return (await armazenamento.listar()).sort(emOrdem);
  }

  async function avisar() {
    if (!ouvintes.size) return;
    const itens = await listar();
    for (const ouvinte of ouvintes) ouvinte(itens);
  }

  /** Chama `ouvinte(itens)` a cada mudança; devolve a função que para de ouvir. */
  function aoMudar(ouvinte) {
    ouvintes.add(ouvinte);
    return () => ouvintes.delete(ouvinte);
  }

  /**
   * Guarda o encontro com a chamada e as evidências. Nada vai para a rede aqui: quem
   * chama decide quando sincronizar (logo em seguida, se houver conexão).
   * registro: { programaId, turmaId, turma, data, conteudo, observacao?, presencas, evidencias?: [{ arquivo, nome, descricao? }] }
   */
  async function adicionarRegistro({ programaId, turmaId, turma, data, conteudo, observacao = "", presencas, evidencias = [] }) {
    const criadoEm = agora().toISOString();
    const base = { programaId, turmaId, turma, data, criadoEm, situacao: SITUACAO.PENDENTE, erro: "", repetir: false, tentativas: 0, enviadoEm: "", resultadoId: "" };
    const id = novoId();
    const atividade = {
      ...base,
      id,
      tipo: "atividade",
      ordem: 0,
      dados: { registro_id: id, data, conteudo, observacao: observacao || null, presencas },
    };
    await armazenamento.gravar(atividade);
    for (const [indice, evidencia] of evidencias.entries()) {
      await armazenamento.gravar({
        ...base,
        id: novoId(),
        tipo: "evidencia",
        ordem: indice + 1,
        atividadeRegistroId: id,
        nome: evidencia.nome,
        tamanho: evidencia.arquivo.size,
        descricao: evidencia.descricao || "",
        arquivo: evidencia.arquivo,
      });
    }
    await avisar();
    return atividade;
  }

  const devePartir = (item) => item.situacao === SITUACAO.PENDENTE || (item.situacao === SITUACAO.ERRO && item.repetir);

  async function enviar(item, atividadeId) {
    if (item.tipo === "atividade") return api.registrarAtividade(item.programaId, item.turmaId, item.dados);
    return api.enviarEvidencia(item.programaId, atividadeId, {
      registro_id: item.id,
      arquivo: item.arquivo,
      nome: item.nome,
      descricao: item.descricao,
    });
  }

  async function rodar() {
    const itens = await listar();
    // Encontros já confirmados: as evidências deles vão para o id que a API devolveu.
    const confirmadas = new Map(
      itens.filter((i) => i.tipo === "atividade" && i.situacao === SITUACAO.ENVIADO).map((i) => [i.id, i.resultadoId]),
    );
    const resultado = { enviados: 0, falhas: 0 };
    for (const item of itens) {
      if (!devePartir(item)) continue;
      const atividadeId = item.tipo === "evidencia" ? confirmadas.get(item.atividadeRegistroId) : "";
      if (item.tipo === "evidencia" && !atividadeId) continue; // espera o envio do encontro
      try {
        const resposta = await enviar(item, atividadeId);
        await armazenamento.gravar({
          ...item,
          situacao: SITUACAO.ENVIADO,
          erro: "",
          repetir: false,
          tentativas: item.tentativas + 1,
          enviadoEm: agora().toISOString(),
          resultadoId: resposta.id,
          // O arquivo já está no servidor; não ocupa mais o aparelho.
          arquivo: null,
        });
        if (item.tipo === "atividade") confirmadas.set(item.id, resposta.id);
        resultado.enviados += 1;
      } catch (e) {
        const erro = e instanceof ErroApi ? e : new ErroApi(ERROS.FALHA);
        const passageira = ehPassageira(erro);
        await armazenamento.gravar({
          ...item,
          situacao: SITUACAO.ERRO,
          erro: mensagemDoErro(erro),
          repetir: passageira,
          tentativas: item.tentativas + 1,
        });
        resultado.falhas += 1;
        await avisar();
        if (passageira) break;
        continue;
      }
      await avisar();
    }
    resultado.aguardando = (await listar()).filter((i) => i.situacao !== SITUACAO.ENVIADO).length;
    return resultado;
  }

  /** Envia o que está na fila, em ordem. Chamadas simultâneas esperam a mesma rodada. */
  function sincronizar() {
    rodada ??= rodar().finally(() => {
      rodada = null;
    });
    return rodada;
  }

  async function alterar(id, mudar) {
    const item = (await armazenamento.listar()).find((i) => i.id === id);
    if (!item) return null;
    const novo = mudar(item);
    await armazenamento.gravar(novo);
    await avisar();
    return novo;
  }

  /** Volta um item com erro para a fila e sincroniza. */
  async function tentarDeNovo(id) {
    await alterar(id, (item) => ({ ...item, situacao: SITUACAO.PENDENTE, erro: "", repetir: false }));
    return sincronizar();
  }

  /** Tira da fila um item não enviado; o encontro leva junto as evidências dele. */
  async function descartar(id) {
    const itens = await armazenamento.listar();
    const item = itens.find((i) => i.id === id);
    if (!item || item.situacao === SITUACAO.ENVIADO) return;
    const juntas = item.tipo === "atividade" ? itens.filter((i) => i.atividadeRegistroId === id && i.situacao !== SITUACAO.ENVIADO) : [];
    for (const removido of [item, ...juntas]) await armazenamento.remover(removido.id);
    await avisar();
  }

  /** Apaga os enviados (todos, ou só os mais antigos que `antesDe`). Um encontro cujas
   * evidências ainda não foram enviadas fica: elas precisam do id dele. */
  async function limparEnviados({ antesDe = null } = {}) {
    const itens = await armazenamento.listar();
    const esperando = new Set(itens.filter((i) => i.tipo === "evidencia" && i.situacao !== SITUACAO.ENVIADO).map((i) => i.atividadeRegistroId));
    const sair = itens.filter(
      (i) => i.situacao === SITUACAO.ENVIADO && !esperando.has(i.id) && (!antesDe || i.enviadoEm < antesDe.toISOString()),
    );
    for (const item of sair) await armazenamento.remover(item.id);
    if (sair.length) await avisar();
    return sair.length;
  }

  /** Limpeza ao abrir o app: enviados há mais de uma semana. */
  function podarHistorico() {
    return limparEnviados({ antesDe: new Date(agora().getTime() - DIAS_DE_HISTORICO * 86400000) });
  }

  return { listar, aoMudar, adicionarRegistro, sincronizar, tentarDeNovo, descartar, limparEnviados, podarHistorico, persistente: armazenamento.persistente };
}
