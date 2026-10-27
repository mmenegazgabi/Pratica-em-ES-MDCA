// Detalhe do projeto: números, gasto por categoria, últimos lançamentos e edição do orçamento.
import { el, limpar } from "../base/dom.js";
import { formatarData, formatarDataCurta, formatarMoeda } from "../base/formatar.js";
import { nomeDoAutor } from "../base/sessao.js";
import { editarOrcamento, listarLancamentos, obterOrcamento } from "../base/api.js";
import { gastoPorCategoria } from "./projetos-dados.js";
import { abrirDialogoOrcamento, falhou } from "./orcamento-dialogo.js";

const ROTULO_STATUS = { pendente: "Aguardando", aprovado: "Aprovado", rejeitado: "Rejeitado" };
const DESTAQUE = {
  atencao: { fundo: "#fffbeb", borda: "#fde68a", texto: "#92400e" },
  estourado: { fundo: "var(--rejeitado-fundo)", borda: "var(--perigo-borda)", texto: "var(--rejeitado-texto)" },
};

function numero(rotulo, valor, destaque) {
  const estilo = destaque ? `padding:12px 14px;background:${destaque.fundo};border-color:${destaque.borda}` : "padding:12px 14px";
  return el(
    "div",
    { class: "caixa", style: estilo },
    el("div", { style: `font-size:11px;color:${destaque ? destaque.texto : "var(--texto-suave)"}` }, rotulo),
    el("div", { class: "num", style: "font-size:18px;font-weight:600;margin-top:2px" }, valor),
  );
}

export async function mostrar(container, { parametros = {}, sessao, navegar }) {
  const coordenacao = sessao.papel === "coordenacao";
  const voltar = el("a", { href: "#/projetos", style: "color:var(--texto-suave);font-size:11px;text-decoration:none" }, "Projetos /");
  limpar(container).append(el("p", { class: "carregando" }, "Carregando…"));
  let orcamento = null;
  let lancamentos = [];
  let lancamentosOk = true;

  async function carregar() {
    const [o, l] = await Promise.all([obterOrcamento(parametros.id), listarLancamentos({ orcamento_id: parametros.id })]);
    if (falhou(o)) return o;
    orcamento = o.corpo;
    lancamentosOk = !falhou(l);
    lancamentos = lancamentosOk ? l.corpo.filter((x) => x.orcamento_id === orcamento.id) : [];
    return o;
  }

  function dialogoEdicao() {
    abrirDialogoOrcamento(container, {
      titulo: "Editar orçamento",
      subtitulo: orcamento.projeto_nome || orcamento.projeto_id,
      rotuloSalvar: "Salvar",
      inicial: orcamento,
      salvar: (dados) => editarOrcamento(orcamento.id, dados),
      aoSalvar: async () => {
        if (!falhou(await carregar())) desenhar();
      },
    });
  }

  function porCategoria() {
    const itens = gastoPorCategoria(orcamento, lancamentos);
    const maior = Math.max(0, ...itens.map((i) => i.gasto));
    return el(
      "div",
      { class: "caixa" },
      el("div", { style: "padding:10px 12px;font-weight:600;font-size:12px;border-bottom:1px solid var(--borda)" }, "Por categoria"),
      itens.length === 0
        ? el("p", { class: "vazio" }, "Nenhuma categoria cadastrada.")
        : el(
            "div",
            { style: "padding:12px;display:grid;grid-template-columns:1fr auto;gap:10px 12px;align-items:end" },
            itens.flatMap((i) => [
              el("div", { style: "font-size:12px" }, i.categoria, el("div", { class: "barra-uso", style: "width:100%;margin-top:4px" }, el("i", { style: `width:${maior > 0 ? (i.gasto / maior) * 100 : 0}%` }))),
              el("span", { class: "num", style: "font-size:11px" }, formatarMoeda(i.gasto)),
            ]),
          ),
    );
  }

  function ultimos() {
    const recentes = [...lancamentos].sort((a, b) => String(b.criado_em ?? "").localeCompare(String(a.criado_em ?? ""))).slice(0, 5);
    const rota = `#/lancamentos?orcamento=${encodeURIComponent(orcamento.id)}&status=todos`;
    return el(
      "div",
      { class: "caixa" },
      el(
        "div",
        { style: "padding:10px 12px;font-weight:600;font-size:12px;border-bottom:1px solid var(--borda);display:flex;justify-content:space-between" },
        "Últimos lançamentos",
        sessao.papel === "direcao" ? null : el("a", { href: rota, style: "color:var(--verde);font-weight:500;text-decoration:none", onclick: (e) => { e.preventDefault(); navegar(rota); } }, "Ver todos"),
      ),
      !lancamentosOk
        ? el("p", { class: "vazio" }, "Não foi possível carregar os lançamentos.")
        : recentes.length === 0
          ? el("p", { class: "vazio" }, "Nenhum lançamento neste orçamento.")
          : recentes.map((l) =>
              el(
                "div",
                { style: "display:flex;justify-content:space-between;align-items:center;padding:9px 12px;border-bottom:1px solid var(--linha);font-size:12px" },
                el("span", {}, l.categoria, el("small", { style: "display:block;color:var(--texto-suave);font-size:11px" }, [nomeDoAutor(l.autor_id), l.data_despesa ? formatarDataCurta(l.data_despesa) : ""].filter(Boolean).join(" · "))),
                el(
                  "span",
                  { style: "text-align:right" },
                  el("span", { class: "num" }, formatarMoeda(l.valor)),
                  el("br"),
                  l.conciliado ? el("span", { class: "etiqueta etiqueta--conciliado" }, "Conciliado") : el("span", { class: `etiqueta etiqueta--${l.status}` }, ROTULO_STATUS[l.status] || l.status),
                ),
              ),
            ),
    );
  }

  function desenhar() {
    const nome = orcamento.projeto_nome || orcamento.projeto_id;
    limpar(container).append(
      voltar,
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:flex-start;margin-top:4px" },
        el("div", {}, el("h1", {}, nome), el("p", { class: "sub" }, `${formatarData(orcamento.data_inicio)} a ${formatarData(orcamento.data_fim)}`)),
        coordenacao ? el("button", { type: "button", class: "btn btn--sec", onclick: dialogoEdicao }, "Editar orçamento") : null,
      ),
      el(
        "div",
        { style: "display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px" },
        numero("Orçado", formatarMoeda(orcamento.valor_total)),
        numero("Gasto", formatarMoeda(orcamento.realizado)),
        numero(`Disponível · ${Math.floor(orcamento.percentual_consumido)}% usado`, formatarMoeda(orcamento.saldo), DESTAQUE[orcamento.nivel_alerta]),
      ),
      el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start" }, porCategoria(), ultimos()),
    );
  }

  const resposta = await carregar();
  if (falhou(resposta)) {
    const texto = resposta.status === 404 ? "Projeto não encontrado." : "Não foi possível carregar o projeto. Verifique a conexão e tente de novo.";
    return limpar(container).append(voltar, el("p", { class: "aviso-tela", role: "alert" }, texto));
  }
  desenhar();
}
