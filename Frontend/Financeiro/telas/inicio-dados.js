// Início: monta as pendências de cada papel (sem DOM, testável no Node).
import { diasDesde, formatarData, formatarMoeda, tempoRelativo } from "../base/formatar.js";

const LIMITE_DIAS_ABERTO = 7;

function porData(campo) {
  return (a, b) => String(a[campo] ?? "").localeCompare(String(b[campo] ?? ""));
}

function nomeDoProjeto(orcamentos, lancamento) {
  const orcamento = orcamentos.find((o) => o.id === lancamento.orcamento_id);
  return orcamento?.projeto_nome || lancamento.projeto_id;
}

function aguardandoAprovacao({ lancamentos, orcamentos }, agora) {
  const itens = lancamentos
    .filter((l) => l.status === "pendente")
    .sort(porData("criado_em"))
    .map((l) => ({
      rotulo: l.categoria,
      detalhe: `${nomeDoProjeto(orcamentos, l)} · enviada ${tempoRelativo(l.criado_em, agora)}`,
      valor: l.valor,
      acao: { rotulo: "Analisar", rota: `#/lancamentos?status=pendente&abrir=${encodeURIComponent(l.id)}` },
    }));
  return { titulo: "Despesas aguardando aprovação", itens };
}

function alertasDeOrcamento({ orcamentos }) {
  const itens = orcamentos
    .filter((o) => o.nivel_alerta === "atencao" || o.nivel_alerta === "estourado")
    .map((o) => ({
      rotulo: o.nivel_alerta === "estourado" ? `${o.projeto_nome} estourou o orçamento` : `${o.projeto_nome} passou de 80% do orçamento`,
      detalhe:
        o.saldo >= 0
          ? `Restam ${formatarMoeda(o.saldo)} até ${formatarData(o.data_fim)}`
          : `Passou ${formatarMoeda(-o.saldo)} do orçado · vigência até ${formatarData(o.data_fim)}`,
      valor: o.percentual_consumido,
      nivel: o.nivel_alerta,
      acao: { rotulo: "Ver projeto", rota: `#/projetos/${encodeURIComponent(o.projeto_id)}` },
    }));
  return { titulo: "Alertas de orçamento", itens };
}

function aprovadosSemConciliacao({ lancamentos, orcamentos }, agora) {
  const itens = lancamentos
    .filter((l) => l.status === "aprovado" && l.conciliado === false)
    .sort(porData("aprovado_em"))
    .map((l) => {
      const projeto = nomeDoProjeto(orcamentos, l);
      const dias = l.aprovado_em ? diasDesde(l.aprovado_em, agora) : 0;
      return {
        rotulo: l.categoria,
        detalhe: dias > LIMITE_DIAS_ABERTO ? `${projeto} · aberto há ${dias} dias` : projeto,
        valor: l.valor,
        acao: { rotulo: "Ver", rota: `#/lancamentos?status=aprovado&abrir=${encodeURIComponent(l.id)}` },
      };
    });
  return { titulo: "Aprovados sem conciliação", itens };
}

const SECOES_POR_PAPEL = {
  coordenacao: [aguardandoAprovacao, alertasDeOrcamento],
  direcao: [alertasDeOrcamento],
  voluntario_financeiro: [aprovadosSemConciliacao],
};

export function montarPendencias(papel, dados, agora = new Date()) {
  const secoes = (SECOES_POR_PAPEL[papel] || []).map((montar) => montar(dados, agora)).filter((s) => s.itens.length > 0);
  return { total: secoes.reduce((soma, s) => soma + s.itens.length, 0), secoes };
}
