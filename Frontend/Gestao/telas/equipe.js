// Equipe e espaços de um programa, ligada à API da T-39 (T-40 · US-01).
//
// Mostra a equipe com o histórico (quem saiu continua listado como Desligado) e os
// espaços. Quem gerencia (coordenação e administração) vincula, desliga e cadastra
// espaços; os botões só aparecem para esses perfis, mas quem decide é a API: uma
// recusa (403, 409…) aparece no próprio formulário.

import * as api from "../base/api.js";
import { carregarNaTela } from "../base/estados.js";
import { el } from "../base/dom.js";
import { abrirFormulario, campo, hojeIso, selecao } from "../base/formulario.js";

// Papéis que fazem sentido dentro de um programa; direção, administração e o
// voluntariado financeiro são papéis da plataforma.
export const PAPEIS_DE_PROGRAMA = ["coordenacao", "educador", "assistente_social", "psicologo"];

const API_PADRAO = {
  listarEquipe: api.listarEquipe,
  listarEspacos: api.listarEspacos,
  listarUsuarios: api.listarUsuarios,
  listarPapeis: api.listarPapeis,
  vincularProfissional: api.vincularProfissional,
  registrarDesligamento: api.registrarDesligamento,
  criarEspaco: api.criarEspaco,
};

export const dataBr = (iso) => (iso ? String(iso).split("-").reverse().join("/") : "—");
const badge = (texto, tom) => el("span", { class: `badge ${tom}` }, texto);

function tabela(cabecalhos, linhas) {
  return el(
    "div",
    { class: "table-wrap" },
    el(
      "table",
      {},
      el("thead", {}, el("tr", {}, cabecalhos.map((c) => el("th", { scope: "col" }, c)))),
      el("tbody", {}, linhas),
    ),
  );
}

function cartao(titulo, subtitulo, corpo, acao = null) {
  return el(
    "section",
    { class: "card" },
    el("div", { class: "card-head" }, el("div", {}, el("h2", {}, titulo), subtitulo ? el("small", {}, subtitulo) : null), acao),
    el("div", { class: "card-body" }, corpo),
  );
}

const vazio = (titulo, texto) => el("div", { class: "empty" }, el("h2", {}, titulo), el("p", {}, texto));

function situacao(v) {
  // Sem data de saída, o vínculo só está inativo porque a conta foi desativada.
  if (!v.ativo) return badge(v.data_saida ? "Desligado" : "Conta desativada", "gray");
  if (v.data_saida) return badge(`Ativo até ${dataBr(v.data_saida)}`, "amber");
  return badge("Ativo", "green");
}

export function mostrarEquipe(container, programaId, { podeGerenciar = false, avisar = () => {}, ...substitutos } = {}) {
  const chamadas = { ...API_PADRAO, ...substitutos };
  const recarregar = () => mostrarEquipe(container, programaId, { podeGerenciar, avisar, ...substitutos });

  function concluir(mensagem) {
    avisar(mensagem);
    return recarregar();
  }

  async function abrirVinculo(botao) {
    botao.disabled = true;
    let usuarios, papeis;
    try {
      [usuarios, papeis] = await Promise.all([chamadas.listarUsuarios(), chamadas.listarPapeis()]);
    } catch (erro) {
      avisar(erro.detalhe || erro.message);
      return;
    } finally {
      botao.disabled = false;
    }
    const pessoa = selecao(
      "usuario_id",
      usuarios.filter((u) => u.ativo).map((u) => [u.id, `${u.nome} (${u.id})`]),
      { vazio: "Selecione a pessoa" },
    );
    const papel = selecao(
      "papel_id",
      papeis.filter((p) => PAPEIS_DE_PROGRAMA.includes(p.id)).map((p) => [p.id, p.nome]),
      { vazio: "Selecione o papel" },
    );
    const entrada = el("input", { name: "data_entrada", type: "date", required: true });
    entrada.value = hojeIso();

    abrirFormulario({
      titulo: "Vincular profissional",
      campos: [
        campo("f-vinculo-pessoa", "Pessoa", pessoa, { largo: true, dica: "Contas ativas da plataforma." }),
        campo("f-vinculo-papel", "Papel no programa", papel),
        campo("f-vinculo-entrada", "Data de entrada", entrada),
      ],
      botao: "Vincular",
      validar: () => {
        if (!pessoa.value) return "Selecione a pessoa.";
        if (!papel.value) return "Selecione o papel no programa.";
        if (!entrada.value) return "Informe a data de entrada.";
        return "";
      },
      enviar: () =>
        chamadas.vincularProfissional(programaId, { usuario_id: pessoa.value, papel_id: papel.value, data_entrada: entrada.value }),
      aoConcluir: () => concluir("Profissional vinculado ao programa."),
    });
  }

  function abrirDesligamento(vinculo) {
    const saida = el("input", { name: "data_saida", type: "date", required: true, min: vinculo.data_entrada });

    abrirFormulario({
      titulo: `Encerrar vínculo · ${vinculo.nome}`,
      aviso: el(
        "div",
        { class: "info-box amber" },
        el("span", {}, "O acesso ao programa é bloqueado a partir da data de saída. O vínculo continua no histórico."),
      ),
      campos: [campo("f-desligamento-saida", "Data de saída", saida, { dica: `Entrada em ${dataBr(vinculo.data_entrada)}.` })],
      botao: "Confirmar desligamento",
      validar: () => {
        if (!saida.value) return "Informe a data de saída.";
        if (saida.value < vinculo.data_entrada) return "A data de saída não pode ser anterior à data de entrada.";
        return "";
      },
      enviar: () => chamadas.registrarDesligamento(programaId, vinculo.id, saida.value),
      aoConcluir: () => concluir("Vínculo encerrado. O histórico foi preservado."),
    });
  }

  function abrirEspaco() {
    const nome = el("input", { name: "nome", type: "text", required: true, maxlength: 200 });
    const capacidade = el("input", { name: "capacidade", type: "number", min: 1, step: 1 });

    abrirFormulario({
      titulo: "Cadastrar espaço",
      campos: [
        campo("f-espaco-nome", "Nome do espaço", nome, { largo: true }),
        campo("f-espaco-capacidade", "Capacidade", capacidade, { dica: "Opcional. Número de pessoas." }),
      ],
      validar: () => {
        if (!nome.value.trim()) return "Informe o nome do espaço.";
        const n = Number(capacidade.value);
        if (capacidade.value !== "" && (!Number.isInteger(n) || n < 1)) return "A capacidade deve ser um número inteiro maior que zero.";
        return "";
      },
      enviar: () =>
        chamadas.criarEspaco(programaId, {
          nome: nome.value.trim(),
          capacidade: capacidade.value === "" ? null : Number(capacidade.value),
        }),
      aoConcluir: () => concluir("Espaço cadastrado."),
    });
  }

  function linhaDaEquipe(v) {
    const acao =
      // Conta desativada ainda pode ter a saída registrada.
      podeGerenciar && !v.data_saida
        ? el("button", { type: "button", class: "btn small", onclick: () => abrirDesligamento(v) }, "Desligar")
        : "—";
    return el(
      "tr",
      {},
      el("td", {}, el("strong", {}, v.nome), el("small", {}, v.usuario_id)),
      el("td", {}, v.papel),
      el("td", {}, dataBr(v.data_entrada)),
      el("td", {}, dataBr(v.data_saida)),
      el("td", {}, situacao(v)),
      el("td", {}, acao),
    );
  }

  function tela([equipe, espacos]) {
    const vincular = podeGerenciar
      ? el("button", { type: "button", class: "btn small", onclick: (e) => abrirVinculo(e.currentTarget) }, "+ Vincular profissional")
      : null;
    const adicionar = podeGerenciar ? el("button", { type: "button", class: "btn small", onclick: abrirEspaco }, "+ Adicionar espaço") : null;

    return el(
      "div",
      { class: "tela-equipe stack" },
      cartao(
        "Equipe e acesso",
        "Vínculos e responsabilidades dentro deste programa. Quem foi desligado perde o acesso e continua no histórico.",
        equipe.length
          ? tabela(["Profissional", "Papel", "Entrada", "Saída", "Situação", ""], equipe.map(linhaDaEquipe))
          : vazio("Nenhum profissional vinculado", "Os vínculos da equipe deste programa aparecem aqui."),
        vincular,
      ),
      el("div", { class: "section-heading" }, el("h2", {}, "Espaços de atendimento"), adicionar),
      cartao(
        "Locais disponíveis",
        "",
        espacos.length
          ? tabela(
              ["Espaço", "Capacidade"],
              espacos.map((s) => el("tr", {}, el("td", {}, s.nome), el("td", {}, s.capacidade ? `${s.capacidade} pessoas` : "—"))),
            )
          : vazio("Nenhum espaço cadastrado", "Os espaços de atendimento do programa aparecem aqui."),
      ),
    );
  }

  return carregarNaTela(
    container,
    () => Promise.all([chamadas.listarEquipe(programaId, { incluirDesligados: true }), chamadas.listarEspacos(programaId)]),
    tela,
  );
}
