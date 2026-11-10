// Avisos de alertas reais para a equipe (T-90 · US-06): o botão de notificações e a
// Visão geral passam a mostrar os alertas de infrequência abertos vindos da API (T-59),
// cada um levando ao acompanhamento da T-60 (#/alertas/{id}).
//
// A tela é desenhada de forma síncrona (render do protótipo), então os alertas ficam
// guardados aqui: `abertos()` devolve o que já chegou e `atualizar()` busca de novo em
// segundo plano, chamando `aoMudar` só quando a lista mudou (sem laço de redesenho).
// Perfis que não acompanham alertas não chamam a API. Sem conexão ou com erro, os avisos
// só não aparecem: o resto da tela segue normal.

/** Alerta da API no formato dos avisos do protótipo (título, descrição e destino). */
export const comoAviso = (a) => ({
  id: a.id,
  title: a.titulo,
  description: a.descricao,
  type: "Infrequência",
  status: "Em aberto",
  person: a.pessoa_id,
  date: String(a.criado_em || "").slice(0, 10),
  link: `/alertas/${a.id}`,
  origem: "api",
});

const chave = (lista) => lista.map((a) => `${a.id}:${a.faltas_consecutivas}`).join("|");

/**
 * listar: () => Promise<alertas abertos da API>
 * podeAcompanhar: () => boolean (perfil atual acompanha alertas)
 * aoMudar: () => void (redesenhar a tela)
 */
export function criarAvisos({ listar, podeAcompanhar, aoMudar = () => {}, agora = () => Date.now(), validade = 60000 }) {
  let alertas = [];
  let buscadoEm = -Infinity;
  let buscando = null;
  let perfilDaBusca = null;

  function abertos() {
    return podeAcompanhar() ? alertas.map(comoAviso) : [];
  }

  /** Busca de novo se passou da validade, se o perfil mudou ou se `forcar`. */
  function atualizar({ forcar = false, perfil = "" } = {}) {
    if (!podeAcompanhar()) {
      const mudou = alertas.length > 0;
      alertas = [];
      perfilDaBusca = perfil;
      if (mudou) aoMudar();
      return Promise.resolve();
    }
    const vencido = agora() - buscadoEm >= validade || perfil !== perfilDaBusca;
    if (buscando || (!forcar && !vencido)) return buscando || Promise.resolve();
    perfilDaBusca = perfil;
    buscadoEm = agora();
    buscando = listar()
      .then((lista) => {
        const anterior = chave(alertas);
        alertas = Array.isArray(lista) ? lista.filter((a) => a.situacao === "aberto") : [];
        if (chave(alertas) !== anterior) aoMudar();
      })
      .catch(() => {
        // Sem conexão ou sem permissão: mantém o que já tinha e tenta na próxima vez.
        buscadoEm = -Infinity;
      })
      .finally(() => {
        buscando = null;
      });
    return buscando;
  }

  return { abertos, atualizar };
}
