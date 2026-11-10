// Detalhe do projeto: números, gasto por categoria, últimos lançamentos, edição do orçamento
// e encerrar/reativar o projeto (PATCH /projetos/{id}/status).
import { el, limpar } from "../base/dom.js";
import { formatarData, formatarDataCurta, formatarMoeda } from "../base/formatar.js";
import { nomeDoAutor } from "../base/sessao.js";
import { alterarStatusProjeto, editarOrcamento, listarLancamentos, listarProjetos, obterOrcamento } from "../base/api.js";
import { categoriasDoOrcamento } from "./projetos-dados.js";
import { abrirDialogoOrcamento, abrirDocumento, falhou, mensagemDeErro } from "./orcamento-dialogo.js";

const MUDAM_STATUS = ["coordenacao", "direcao"];

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
  let projeto = null; // {id, nome, status} de GET /projetos; null se não carregou

  async function carregar() {
    const [o, l, p] = await Promise.all([obterOrcamento(parametros.id), listarLancamentos({ orcamento_id: parametros.id }), listarProjetos()]);
    if (falhou(o)) return o;
    orcamento = o.corpo;
    lancamentosOk = !falhou(l);
    lancamentos = lancamentosOk ? l.corpo.filter((x) => x.orcamento_id === orcamento.id) : [];
    projeto = !falhou(p) && Array.isArray(p.corpo) ? p.corpo.find((x) => x.id === orcamento.projeto_id) || null : null;
    return o;
  }

  function dialogoStatus() {
    const encerrar = projeto.status !== "encerrado";
    const nome = projeto.nome || orcamento.projeto_nome || orcamento.projeto_id;
    const erro = el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:12px;margin:12px 0 0", hidden: true });
    const cancelar = el("button", { type: "button", class: "btn btn--sec" }, "Cancelar");
    const confirmar = el("button", { type: "submit", class: "btn" }, encerrar ? "Encerrar projeto" : "Reativar projeto");
    const dialogo = el(
      "dialog",
      { class: "dialogo", "aria-labelledby": "status-titulo", style: "width:400px" },
      el(
        "form",
        { method: "dialog", novalidate: true },
        el("h2", { id: "status-titulo", style: "font-size:15px;margin:0 0 4px" }, encerrar ? "Encerrar projeto?" : "Reativar projeto?"),
        el(
          "p",
          { style: "color:var(--texto-suave);font-size:12px;margin:8px 0 0;line-height:1.5" },
          encerrar
            ? `${nome} passa a aparecer como encerrado em Projetos e no painel da direção. Dá para reativar depois.`
            : `${nome} volta a aparecer como ativo em Projetos e no painel da direção.`,
        ),
        erro,
        el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:16px" }, cancelar, confirmar),
      ),
    );
    const fechar = () => dialogo.remove();
    cancelar.addEventListener("click", fechar);
    dialogo.addEventListener("cancel", fechar);
    dialogo.querySelector("form").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      confirmar.disabled = true;
      cancelar.disabled = true;
      erro.hidden = true;
      const novo = encerrar ? "encerrado" : "ativo";
      const resposta = await alterarStatusProjeto(projeto.id, novo);
      if (!falhou(resposta)) {
        fechar();
        projeto = { ...projeto, status: resposta.corpo?.status || novo };
        return desenhar();
      }
      confirmar.disabled = false;
      cancelar.disabled = false;
      erro.hidden = false;
      erro.textContent = mensagemDeErro(resposta, encerrar ? "Não foi possível encerrar o projeto. Tente de novo." : "Não foi possível reativar o projeto. Tente de novo.");
    });
    abrirDocumento(container, dialogo, cancelar);
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
    const itens = categoriasDoOrcamento(orcamento, lancamentos);
    const maior = Math.max(0, ...itens.map((i) => i.gasto));
    const barra = (i) => {
      if (i.limite === null) return el("div", { class: "barra-uso", style: "width:100%;margin-top:4px" }, el("i", { style: `width:${maior > 0 ? (i.gasto / maior) * 100 : 0}%` }));
      const classe = i.nivel === "estourado" ? "barra-uso barra-uso--critica" : i.nivel === "atencao" ? "barra-uso barra-uso--alerta" : "barra-uso";
      const largura = i.percentual === null ? (i.gasto > 0 ? 100 : 0) : Math.max(0, Math.min(100, i.percentual));
      return el("div", { class: classe, style: "width:100%;margin-top:4px" }, el("i", { style: `width:${largura}%` }));
    };
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
              el("div", { style: "font-size:12px" }, i.categoria, barra(i)),
              el("span", { class: "num", style: "font-size:11px" }, i.limite === null ? formatarMoeda(i.gasto) : `${formatarMoeda(i.gasto)} / ${formatarMoeda(i.limite)}`),
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
    const encerrado = projeto?.status === "encerrado";
    const mudaStatus = projeto && MUDAM_STATUS.includes(sessao.papel);
    limpar(container).append(
      voltar,
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:flex-start;margin-top:4px;gap:12px" },
        el(
          "div",
          {},
          el("h1", {}, nome, encerrado ? el("span", { class: "etiqueta etiqueta--encerrado", style: "margin-left:8px;vertical-align:middle" }, "Encerrado") : null),
          el("p", { class: "sub" }, `${formatarData(orcamento.data_inicio)} a ${formatarData(orcamento.data_fim)}`),
        ),
        el(
          "div",
          { style: "display:flex;gap:8px" },
          coordenacao ? el("button", { type: "button", class: "btn btn--sec", onclick: dialogoEdicao }, "Editar orçamento") : null,
          mudaStatus ? el("button", { type: "button", class: "btn btn--sec", onclick: dialogoStatus }, encerrado ? "Reativar projeto" : "Encerrar projeto") : null,
        ),
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
