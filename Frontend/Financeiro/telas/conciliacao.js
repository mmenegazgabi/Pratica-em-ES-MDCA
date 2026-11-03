// Conciliação (Lucas): extrato de um lado, lançamentos aprovados do outro; marca um de cada e concilia.
import { el, limpar } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { definirContador } from "../base/contador.js";
import { formatarDataCurta, formatarMoeda } from "../base/formatar.js";
import { nomeDoAutor } from "../base/sessao.js";
import { conciliarLancamento, listarLancamentos, listarOrcamentos } from "../base/api.js";
import { montarPendencias } from "./inicio-dados.js";
import { falhou, mensagemDeErro } from "./orcamento-dialogo.js";
import { aprovadosEmAberto, diasEmAberto, extratoEmAberto, mesmoValor, valoresDiferentes } from "./conciliacao-dados.js";
import { EXTRATO_EXEMPLO } from "./dados-exemplo.js";

const ESTILO_LINHA = "display:flex;justify-content:space-between;align-items:center;gap:10px;padding:9px 12px;border-bottom:1px solid var(--linha);cursor:pointer;width:100%;box-sizing:border-box;background:none;border-left:0;border-right:0;border-top:0;font:inherit;color:inherit;text-align:left";
const ESTILO_SELECIONADA = ";background:var(--fundo-selecionado);box-shadow:inset 3px 0 0 var(--verde)";

function marcador(selecionado) {
  const estilo = selecionado ? "border:4px solid var(--verde)" : "border:1.5px solid #a1a1aa";
  return el("span", { "aria-hidden": "true", style: `width:13px;height:13px;border-radius:50%;flex:none;box-sizing:border-box;${estilo}` });
}

function coluna(titulo, extra, linhas, vazio) {
  return el(
    "div",
    { class: "caixa", style: "overflow:hidden" },
    el("div", { style: "display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-bottom:1px solid var(--borda);background:var(--fundo-suave);font-weight:500;font-size:11.5px" }, titulo, extra),
    linhas.length ? el("div", { role: "radiogroup", "aria-label": titulo }, linhas) : el("p", { class: "vazio" }, vazio),
  );
}

export async function mostrar(container, { sessao }) {
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));

  let lancamentos = [];
  let orcamentos = [];
  let extratoId = null;
  let lancamentoId = null;
  let mensagem = null; // { texto, erro }
  let ocupado = false;
  let avisoImportar = false;

  async function carregar() {
    const [l, o] = await Promise.all([listarLancamentos(), listarOrcamentos()]);
    if (falhou(l) || falhou(o)) return false;
    lancamentos = l.corpo;
    orcamentos = o.corpo;
    definirContador(montarPendencias(sessao.papel, { lancamentos, orcamentos }).total);
    return true;
  }

  const nomeDoProjeto = (l) => orcamentos.find((o) => o.id === l.orcamento_id)?.projeto_nome || l.projeto_id || "";

  async function conciliar(item, lancamento) {
    ocupado = true;
    mensagem = null;
    desenhar();
    const resposta = await conciliarLancamento(lancamento.id, item.referencia);
    ocupado = false;
    if (falhou(resposta)) {
      mensagem = { texto: mensagemDeErro(resposta, "Não foi possível conciliar. Tente de novo."), erro: true };
      return desenhar();
    }
    extratoId = null;
    lancamentoId = null;
    mensagem = { texto: `${formatarMoeda(lancamento.valor)} · ${item.descricao} conciliado com ${lancamento.categoria}.`, erro: false };
    if (!(await carregar())) mensagem = { texto: "Conciliado, mas não foi possível atualizar a lista. Recarregue a página.", erro: true };
    desenhar();
  }

  function desenhar() {
    const agora = new Date();
    const extrato = extratoEmAberto(EXTRATO_EXEMPLO, lancamentos);
    const aprovados = aprovadosEmAberto(lancamentos);
    const item = extrato.find((i) => i.referencia === extratoId) || null;
    const lancamento = aprovados.find((l) => l.id === lancamentoId) || null;
    const sugeridos = new Set(mesmoValor(item, aprovados));

    const linhasExtrato = extrato.map((i) => {
      const marcado = i.referencia === extratoId;
      return el(
        "button",
        { type: "button", role: "radio", "aria-checked": String(marcado), style: ESTILO_LINHA + (marcado ? ESTILO_SELECIONADA : ""), onclick: () => { extratoId = marcado ? null : i.referencia; mensagem = null; desenhar(); } },
        el("span", { style: "display:flex;gap:10px;align-items:center;min-width:0" }, marcador(marcado), el("span", {}, i.descricao, el("small", { style: "display:block;color:var(--texto-suave);font-size:11px" }, `${formatarDataCurta(i.data)} · ${i.referencia}`))),
        el("span", { class: "num" }, `−${formatarMoeda(i.valor)}`),
      );
    });

    const linhasAprovados = aprovados.map((l) => {
      const marcado = l.id === lancamentoId;
      const dias = diasEmAberto(l, agora);
      const detalhe = [nomeDoAutor(l.autor_id), l.data_despesa ? formatarDataCurta(l.data_despesa) : ""].filter(Boolean).join(" · ");
      return el(
        "button",
        { type: "button", role: "radio", "aria-checked": String(marcado), style: ESTILO_LINHA + (marcado ? ESTILO_SELECIONADA : ""), onclick: () => { lancamentoId = marcado ? null : l.id; mensagem = null; desenhar(); } },
        el(
          "span",
          { style: "display:flex;gap:10px;align-items:center;min-width:0" },
          marcador(marcado),
          el(
            "span",
            {},
            `${l.categoria} · ${nomeDoProjeto(l)}`,
            el(
              "small",
              { style: "display:block;color:var(--texto-suave);font-size:11px" },
              detalhe,
              sugeridos.has(l.id) ? el("span", { style: "color:var(--ativo-texto)" }, `${detalhe ? " · " : ""}mesmo valor`) : null,
              dias ? el("span", { style: "color:#b45309;font-weight:500" }, `${detalhe ? " · " : ""}aberto há ${dias} dias`) : null,
            ),
          ),
        ),
        el("span", { class: "num" }, formatarMoeda(l.valor)),
      );
    });

    const barra =
      item && lancamento
        ? el(
            "div",
            { style: "margin-top:12px;border:1px solid var(--verde);background:var(--fundo-selecionado);border-radius:8px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;gap:12px" },
            el(
              "span",
              {},
              el("b", { class: "num" }, formatarMoeda(item.valor)),
              ` · ${item.descricao} ↔ ${lancamento.categoria} · ${nomeDoProjeto(lancamento)}`,
              valoresDiferentes(item, lancamento) ? el("small", { style: "display:block;color:#b45309;margin-top:2px" }, `Atenção: o lançamento é de ${formatarMoeda(lancamento.valor)}.`) : null,
            ),
            el("button", { type: "button", class: "btn", disabled: ocupado, onclick: () => conciliar(item, lancamento) }, ocupado ? "Conciliando…" : "Conciliar"),
          )
        : el("p", { style: "margin:12px 0 0;color:var(--texto-suave)" }, "Marque um item do extrato e um lançamento para conciliar.");

    limpar(container).append(
      ...[
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:flex-start" },
        el("div", {}, el("h1", {}, "Conciliação"), el("p", { class: "sub" }, aprovados.length === 1 ? "1 lançamento aprovado sem vínculo com o extrato" : `${aprovados.length} lançamentos aprovados sem vínculo com o extrato`)),
        el("button", { type: "button", class: "btn btn--sec", onclick: () => { avisoImportar = true; desenhar(); } }, icone("importar"), "Importar extrato"),
      ),
      avisoImportar ? el("p", { role: "status", style: "margin:0 0 12px;color:var(--texto-suave)" }, "A importação do arquivo do banco ainda não está disponível. O extrato abaixo é de exemplo.") : null,
      mensagem ? el("p", { role: mensagem.erro ? "alert" : "status", style: `margin:0 0 12px;color:${mensagem.erro ? "var(--perigo-texto)" : "var(--ativo-texto)"}` }, mensagem.texto) : null,
      el(
        "div",
        { style: "display:grid;grid-template-columns:1fr 1fr;gap:14px;align-items:start" },
        coluna("Extrato bancário", el("span", { style: "color:var(--texto-suave);font-weight:400" }, "exemplo"), linhasExtrato, "Todos os itens do extrato já foram conciliados."),
        coluna("Lançamentos aprovados", null, linhasAprovados, "Nenhum lançamento aprovado esperando conciliação."),
      ),
      barra,
      ].filter(Boolean),
    );
  }

  if (!(await carregar())) {
    return limpar(container).append(el("h1", {}, "Conciliação"), el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar os lançamentos. Verifique a conexão e tente de novo."));
  }
  desenhar();
}
