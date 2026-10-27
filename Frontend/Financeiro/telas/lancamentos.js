// Lançamentos: lista por status com painel de análise (aprovar / rejeitar).
import { el, limpar } from "../base/dom.js";
import { icone } from "../base/icones.js";
import { definirContador } from "../base/contador.js";
import { formatarData, formatarDataCurta, formatarMoeda } from "../base/formatar.js";
import { nomeDoAutor } from "../base/sessao.js";
import { aprovarLancamento, baixarArquivo, listarLancamentos, listarOrcamentos, obterLancamento, rejeitarLancamento } from "../base/api.js";
import { montarPendencias } from "./inicio-dados.js";
import { contarPorStatus, MOTIVO_MAXIMO, ordenarParaAba, saldoAposAprovar, validarMotivo } from "./lancamentos-dados.js";

const ABAS = [
  { status: "pendente", rotulo: "Aguardando" },
  { status: "aprovado", rotulo: "Aprovados" },
  { status: "rejeitado", rotulo: "Rejeitados" },
  { status: "todos", rotulo: "Todos" },
];
const ROTULO_STATUS = { pendente: "Aguardando aprovação", aprovado: "Aprovado", rejeitado: "Rejeitado" };
const PODE_DECIDIR = ["coordenacao", "direcao"];

const falhou = (resposta) => resposta.status === 0 || resposta.status >= 400;

function mensagemDeErro(resposta, padrao) {
  if (resposta.status === 0) return "Não foi possível falar com o servidor. Verifique a conexão e tente de novo.";
  const detalhe = resposta.corpo?.detail;
  return typeof detalhe === "string" && detalhe ? detalhe : padrao;
}

function rotaDaLista(status, orcamento) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (orcamento) params.set("orcamento", orcamento);
  const texto = params.toString();
  return texto ? `#/lancamentos?${texto}` : "#/lancamentos";
}

function linhaDeDados(rotulo, valor, classe) {
  return [el("dt", { style: "color:var(--texto-suave)" }, rotulo), el("dd", { class: classe, style: "margin:0" }, valor)];
}

export async function mostrar(container, { parametros = {}, sessao, navegar }) {
  const podeDecidir = PODE_DECIDIR.includes(sessao.papel);
  const padrao = sessao.papel === "voluntario_financeiro" ? "aprovado" : "pendente";
  let status = ABAS.some((a) => a.status === parametros.status) ? parametros.status : null;
  const filtroOrcamento = parametros.orcamento || "";

  let lancamentos = [];
  let orcamentos = [];
  let abertoId = null;
  let painel = null; // { meta, detalhe, erro, ocupado, comprovante: {url, ehPdf} | null }
  let vez = 0; // descarta respostas de um painel que já foi trocado ou fechado
  let urlComprovante = null;

  const liberarComprovante = () => {
    if (urlComprovante) URL.revokeObjectURL(urlComprovante);
    urlComprovante = null;
  };

  async function carregarDados() {
    const [l, o] = await Promise.all([listarLancamentos(), listarOrcamentos()]);
    if (falhou(l) || falhou(o)) return false;
    lancamentos = l.corpo;
    orcamentos = o.corpo;
    definirContador(montarPendencias(sessao.papel, { lancamentos, orcamentos }).total);
    return true;
  }

  const nomeDoProjeto = (l) => orcamentos.find((o) => o.id === l.orcamento_id)?.projeto_nome || l.projeto_id || "";

  function fecharPainel() {
    vez += 1;
    liberarComprovante();
    abertoId = null;
    painel = null;
    desenhar();
  }

  async function abrirPainel(lancamento) {
    const minhaVez = ++vez;
    liberarComprovante();
    abertoId = lancamento.id;
    painel = { meta: lancamento, detalhe: null, erro: "", ocupado: false, comprovante: null };
    desenhar();
    const resposta = await obterLancamento(lancamento.id);
    if (minhaVez !== vez) return;
    if (falhou(resposta)) {
      painel.erro = mensagemDeErro(resposta, "Não foi possível carregar esta despesa.");
      return desenhar();
    }
    painel.detalhe = resposta.corpo;
    desenhar();
    if (!resposta.corpo.comprovante_url) return;
    const arquivo = await baixarArquivo(resposta.corpo.comprovante_url);
    if (minhaVez !== vez) return;
    if (arquivo.blob) {
      urlComprovante = URL.createObjectURL(arquivo.blob);
      painel.comprovante = { url: urlComprovante, ehPdf: arquivo.blob.type === "application/pdf" };
    } else {
      painel.comprovante = { indisponivel: true };
    }
    desenhar();
  }

  async function decidir(acao) {
    const minhaVez = vez;
    painel.ocupado = true;
    painel.erro = "";
    desenhar();
    const resposta = await acao();
    if (minhaVez !== vez) return;
    if (falhou(resposta)) {
      painel.ocupado = false;
      painel.erro = mensagemDeErro(resposta, "Não foi possível concluir. Tente de novo.");
      return desenhar();
    }
    liberarComprovante();
    vez += 1;
    abertoId = null;
    painel = null;
    if (!(await carregarDados())) lancamentos = lancamentos.filter((l) => l.id !== resposta.corpo?.id);
    desenhar();
  }

  function abrirDialogoDeRejeicao() {
    const campo = el("textarea", { id: "motivo", rows: "4", maxlength: String(MOTIVO_MAXIMO + 100), style: "width:100%;box-sizing:border-box;font:13px var(--fonte);padding:8px;border:1px solid var(--borda-campo);border-radius:7px;resize:vertical" });
    const erro = el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:12px;margin:6px 0 0", hidden: true });
    const cancelar = el("button", { type: "button", class: "btn btn--sec" }, "Cancelar");
    const confirmar = el("button", { type: "submit", class: "btn btn--perigo" }, "Rejeitar despesa");
    const dialogo = el(
      "dialog",
      { class: "dialogo", "aria-labelledby": "motivo-titulo" },
      el(
        "form",
        { method: "dialog", novalidate: true },
        el("h2", { id: "motivo-titulo", style: "font-size:15px;margin:0 0 4px" }, "Rejeitar despesa"),
        el("p", { style: "color:var(--texto-suave);font-size:12px;margin:0 0 12px" }, "O motivo aparece para quem enviou, que poderá corrigir e reenviar."),
        el("label", { for: "motivo", class: "campo__rotulo" }, "Motivo da rejeição"),
        campo,
        erro,
        el("div", { style: "display:flex;gap:8px;justify-content:flex-end;margin-top:14px" }, cancelar, confirmar),
      ),
    );
    const fechar = () => dialogo.remove();
    cancelar.addEventListener("click", fechar);
    dialogo.addEventListener("cancel", fechar);
    dialogo.querySelector("form").addEventListener("submit", async (evento) => {
      evento.preventDefault();
      const problema = validarMotivo(campo.value);
      erro.hidden = !problema;
      erro.textContent = problema || "";
      if (problema) return campo.focus();
      confirmar.disabled = true;
      cancelar.disabled = true;
      const resposta = await rejeitarLancamento(painel.meta.id, campo.value.trim());
      if (!falhou(resposta)) {
        fechar();
        return decidir(async () => resposta);
      }
      confirmar.disabled = false;
      cancelar.disabled = false;
      if (resposta.status === 409) {
        fechar();
        painel.erro = mensagemDeErro(resposta, "Esta despesa já foi analisada.");
        return desenhar();
      }
      erro.hidden = false;
      erro.textContent = mensagemDeErro(resposta, "Não foi possível rejeitar. Tente de novo.");
    });
    container.append(dialogo);
    if (typeof dialogo.showModal === "function") dialogo.showModal();
    else dialogo.setAttribute("open", "");
    campo.focus();
  }

  function comprovante(p) {
    if (!p.detalhe?.comprovante_url) return null;
    const caixa = { style: "margin:12px 0;border:1px solid var(--borda);border-radius:8px;background:var(--fundo-suave);min-height:120px;display:flex;align-items:center;justify-content:center;overflow:hidden" };
    if (!p.comprovante) return el("div", caixa, el("span", { style: "color:var(--texto-suave);font-size:12px" }, "Carregando comprovante…"));
    if (p.comprovante.indisponivel) return el("div", caixa, el("span", { style: "color:var(--texto-suave);font-size:12px" }, "Comprovante indisponível agora."));
    if (p.comprovante.ehPdf) {
      return el("div", caixa, el("a", { class: "btn btn--sec", href: p.comprovante.url, target: "_blank", rel: "noopener" }, "Abrir comprovante"));
    }
    return el("div", caixa, el("img", { src: p.comprovante.url, alt: "Comprovante da despesa", style: "max-width:100%;max-height:260px;display:block" }));
  }

  function montarPainel() {
    const { meta, detalhe, erro, ocupado } = painel;
    const projeto = nomeDoProjeto(meta);
    const orcamento = orcamentos.find((o) => o.id === meta.orcamento_id);
    const situacao = detalhe?.status || meta.status;
    const dados = [];
    if (detalhe) {
      dados.push(linhaDeDados("Projeto", projeto), linhaDeDados("Categoria", detalhe.categoria));
      const data = detalhe.data_despesa || meta.data_despesa;
      if (data) dados.push(linhaDeDados("Data", formatarData(data), "num"));
      const autor = nomeDoAutor(meta.autor_id);
      if (autor) dados.push(linhaDeDados("Enviada por", autor));
      if (situacao === "pendente" && orcamento) dados.push(linhaDeDados("Saldo após", formatarMoeda(saldoAposAprovar(orcamento, detalhe)), "num"));
    }
    const rodape = [];
    if (detalhe && podeDecidir && situacao === "pendente") {
      rodape.push(
        el(
          "div",
          { style: "margin-top:auto;padding-top:16px;display:flex;gap:8px" },
          el("button", { type: "button", class: "btn btn--perigo", style: "flex:1;justify-content:center", disabled: ocupado, onclick: abrirDialogoDeRejeicao }, "Rejeitar"),
          el("button", { type: "button", class: "btn", style: "flex:1;justify-content:center", disabled: ocupado, onclick: () => decidir(() => aprovarLancamento(meta.id)) }, "Aprovar"),
        ),
      );
    }
    return el(
      "aside",
      { class: "painel-lateral", "aria-label": "Análise da despesa" },
      el(
        "div",
        { style: "display:flex;justify-content:space-between;align-items:center" },
        el("span", { class: `etiqueta etiqueta--${situacao}` }, ROTULO_STATUS[situacao] || situacao),
        el("button", { type: "button", class: "btn btn--sec btn--pequeno", "aria-label": "Fechar painel", onclick: fecharPainel }, icone("fechar")),
      ),
      el("div", { class: "num", style: "font-size:22px;font-weight:600;margin-top:10px" }, formatarMoeda(meta.valor)),
      detalhe ? el("div", { style: "color:var(--texto-medio)" }, detalhe.descricao) : el("p", { class: "carregando" }, erro ? "" : "Carregando…"),
      comprovante(painel),
      el("dl", { style: "display:grid;grid-template-columns:auto 1fr;gap:6px 14px;font-size:12px;margin:8px 0 0" }, dados.flat()),
      detalhe && situacao === "rejeitado" && detalhe.motivo_rejeicao
        ? el("p", { style: "font-size:12px;margin:12px 0 0;color:var(--rejeitado-texto)" }, el("strong", {}, "Motivo: "), detalhe.motivo_rejeicao)
        : null,
      detalhe && situacao === "pendente" && detalhe.motivos_rejeicao_anteriores?.length
        ? el("p", { style: "font-size:12px;margin:12px 0 0;color:var(--texto-suave)" }, el("strong", {}, "Rejeitada antes: "), detalhe.motivos_rejeicao_anteriores.join(" · "))
        : null,
      detalhe?.conciliado
        ? el("p", { style: "margin:12px 0 0;font-size:12px" }, el("span", { class: "etiqueta etiqueta--conciliado" }, "Conciliado"), detalhe.referencia_extrato ? ` ${detalhe.referencia_extrato}` : "")
        : null,
      erro ? el("p", { role: "alert", style: "color:var(--perigo-texto);font-size:12px;margin:12px 0 0" }, erro) : null,
      rodape,
    );
  }

  function montarTabela(visiveis) {
    if (visiveis.length === 0) return el("p", { class: "vazio" }, "Nenhuma despesa aqui.");
    return el(
      "table",
      { class: "tabela" },
      el("thead", {}, el("tr", {}, el("th", {}, "Despesa"), el("th", { class: "num" }, "Data"), el("th", { class: "num" }, "Valor"))),
      el(
        "tbody",
        {},
        visiveis.map((l) => {
          const autor = nomeDoAutor(l.autor_id);
          const detalhe = [autor, nomeDoProjeto(l)].filter(Boolean).join(" · ");
          return el(
            "tr",
            {
              class: l.id === abertoId ? "selecionada" : "",
              tabindex: "0",
              style: "cursor:pointer",
              onclick: () => abrirPainel(l),
              onkeydown: (e) => {
                if (e.key === "Enter") abrirPainel(l);
              },
            },
            el("td", {}, l.categoria, status === "todos" ? el("span", { class: `etiqueta etiqueta--${l.status}`, style: "margin-left:8px" }, ROTULO_STATUS[l.status] || l.status) : null, el("small", {}, detalhe)),
            el("td", { class: "num" }, l.data_despesa ? formatarDataCurta(l.data_despesa) : ""),
            el("td", { class: "num" }, formatarMoeda(l.valor)),
          );
        }),
      ),
    );
  }

  function desenhar() {
    const doProjeto = filtroOrcamento ? lancamentos.filter((l) => l.orcamento_id === filtroOrcamento) : lancamentos;
    const contagem = contarPorStatus(doProjeto);
    const visiveis = ordenarParaAba(status === "todos" ? doProjeto : doProjeto.filter((l) => l.status === status), status);
    const seletor = el(
      "select",
      { "aria-label": "Projeto", class: "filtro", style: "margin-left:auto", onchange: (e) => navegar(rotaDaLista(status, e.target.value)) },
      el("option", { value: "" }, "Projeto: todos"),
      orcamentos.map((o) => el("option", { value: o.id, selected: o.id === filtroOrcamento }, o.projeto_nome)),
    );
    const abas = ABAS.map((a) =>
      el(
        "button",
        { type: "button", class: `filtro${a.status === status ? " filtro--ativo" : ""}`, "aria-pressed": String(a.status === status), onclick: () => navegar(rotaDaLista(a.status, filtroOrcamento)) },
        a.rotulo,
        el("span", { class: "filtro__contagem" }, String(a.status === "todos" ? contagem.todos : contagem[a.status])),
      ),
    );
    limpar(raiz).append(
      el(
        "div",
        {},
        el("h1", {}, "Lançamentos"),
        el("p", { class: "sub" }, "Despesas enviadas pela equipe"),
        el("div", { style: "display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:14px" }, abas, seletor),
        el(
          "div",
          { style: "position:relative;min-height:440px" },
          el("div", { class: "caixa", style: painel ? "width:calc(100% - 316px)" : "" }, montarTabela(visiveis)),
          painel ? montarPainel() : null,
        ),
      ),
    );
  }

  // O diálogo de rejeição fica fora de "raiz" para sobreviver aos redesenhos.
  const raiz = el("div");
  limpar(container).append(raiz, el("p", { class: "carregando" }, "Carregando…"));
  if (!(await carregarDados())) {
    limpar(container).append(el("h1", {}, "Lançamentos"), el("p", { class: "aviso-tela", role: "alert" }, "Não foi possível carregar os lançamentos. Verifique a conexão e tente de novo."));
    return;
  }
  const alvo = parametros.abrir ? lancamentos.find((l) => l.id === parametros.abrir) : null;
  container.querySelector(".carregando")?.remove();
  if (!status) status = alvo ? alvo.status : padrao;
  desenhar();
  if (alvo) await abrirPainel(alvo);
}
