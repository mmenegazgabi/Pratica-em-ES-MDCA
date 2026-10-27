// T-13 · US-03 — Tela de lançamento de despesa no celular (educador).

import {
  API_PADRAO,
  enviarLancamento,
  esquecerAcesso,
  listarOrcamentos,
  salvarAcesso,
  tokenSalvo,
  urlDaApi,
} from "../base/api.js";
import { lerSessao, salvarSessao } from "../base/sessao.js";
import {
  converterValor,
  deveComprimir,
  dimensoesReduzidas,
  formatarMoeda,
  hojeISO,
  mensagemDeErro,
  montarFormData,
  validarFormulario,
} from "./formulario.js";

// Esta tela é do celular do educador: sem sessão ainda, entra como educador.
if (!lerSessao()) salvarSessao({ papel: "educador", nome: "Educador" });

const $ = (id) => document.getElementById(id);

const el = {
  carregando: $("carregando"),
  painelAcesso: $("painel-acesso"),
  formAcesso: $("form-acesso"),
  campoToken: $("campo-token"),
  campoApi: $("campo-api"),
  erroAcesso: $("erro-acesso"),
  botaoAcesso: $("botao-acesso"),
  form: $("form-lancamento"),
  aviso: $("aviso-geral"),
  projeto: $("campo-projeto"),
  categoria: $("campo-categoria"),
  valor: $("campo-valor"),
  data: $("campo-data"),
  descricao: $("campo-descricao"),
  camera: $("campo-camera"),
  galeria: $("campo-galeria"),
  vazio: $("comprovante-vazio"),
  escolhido: $("comprovante-escolhido"),
  previa: $("previa"),
  previaPdf: $("previa-pdf"),
  nomeArquivo: $("nome-arquivo"),
  tamanhoArquivo: $("tamanho-arquivo"),
  trocar: $("trocar-arquivo"),
  enviar: $("botao-enviar"),
  sucesso: $("painel-sucesso"),
  novo: $("botao-novo"),
};

const CAMPOS = ["projeto", "categoria", "valor", "data", "descricao", "comprovante"];
const ELEMENTO_DO_CAMPO = {
  projeto: el.projeto,
  categoria: el.categoria,
  valor: el.valor,
  data: el.data,
  descricao: el.descricao,
  comprovante: el.camera,
};

let orcamentos = [];
let arquivo = null;
let urlDaPrevia = "";

// --- Navegação entre painéis -------------------------------------------------

function mostrar(painel) {
  for (const p of [el.painelAcesso, el.form, el.sucesso, el.carregando]) p.hidden = p !== painel;
}

function abrirAcesso(mensagem = "") {
  el.campoToken.value = "";
  el.campoApi.value = urlDaApi();
  el.erroAcesso.textContent = mensagem;
  el.erroAcesso.hidden = !mensagem;
  $("cancelar-acesso").hidden = !tokenSalvo();
  $("esquecer-acesso").hidden = !tokenSalvo();
  mostrar(el.painelAcesso);
  el.campoToken.focus();
}

// --- Erros por campo ---------------------------------------------------------

function limparErros() {
  for (const campo of CAMPOS) {
    const p = $(`erro-${campo}`);
    p.textContent = "";
    p.hidden = true;
    ELEMENTO_DO_CAMPO[campo].removeAttribute("aria-invalid");
  }
  el.aviso.hidden = true;
}

function limparErroDoCampo(campo) {
  const p = $(`erro-${campo}`);
  if (p.hidden) return;
  p.textContent = "";
  p.hidden = true;
  ELEMENTO_DO_CAMPO[campo].removeAttribute("aria-invalid");
}

function mostrarErros(erros) {
  limparErros();
  let primeiro = null;
  for (const campo of CAMPOS) {
    if (!erros[campo]) continue;
    const p = $(`erro-${campo}`);
    p.textContent = erros[campo];
    p.hidden = false;
    ELEMENTO_DO_CAMPO[campo].setAttribute("aria-invalid", "true");
    primeiro ??= campo;
  }
  if (primeiro) {
    const alvo = primeiro === "comprovante" ? $("erro-comprovante").closest("fieldset") : ELEMENTO_DO_CAMPO[primeiro];
    alvo.scrollIntoView({ behavior: "smooth", block: "center" });
    if (primeiro !== "comprovante") alvo.focus({ preventScroll: true });
  }
}

function avisar(texto) {
  el.aviso.textContent = texto;
  el.aviso.hidden = false;
  el.aviso.scrollIntoView({ behavior: "smooth", block: "center" });
}

// --- Projetos e categorias ---------------------------------------------------

function orcamentoEscolhido() {
  return orcamentos.find((o) => o.id === el.projeto.value);
}

function preencherProjetos() {
  el.projeto.innerHTML = "";
  const placeholder = new Option(orcamentos.length ? "Escolha o projeto" : "Nenhum projeto com orçamento vigente", "");
  el.projeto.add(placeholder);
  for (const o of orcamentos) el.projeto.add(new Option(o.projeto_id, o.id));
  if (orcamentos.length === 1) el.projeto.value = orcamentos[0].id;
  preencherCategorias();
}

function preencherCategorias() {
  const o = orcamentoEscolhido();
  el.categoria.innerHTML = "";
  el.categoria.add(new Option(o ? "Escolha a categoria" : "Escolha o projeto primeiro", ""));
  el.categoria.disabled = !o;
  if (!o) return;
  for (const c of o.categorias_despesa) el.categoria.add(new Option(c, c));
  if (o.categorias_despesa.length === 1) el.categoria.value = o.categorias_despesa[0];
  el.data.min = o.data_inicio;
  el.data.max = o.data_fim;
}

async function carregarProjetos() {
  mostrar(el.carregando);
  const { status, corpo } = await listarOrcamentos(hojeISO());
  if (status === 401) return abrirAcesso("Código de acesso inválido. Informe de novo.");
  mostrar(el.form);
  if (status !== 200) {
    orcamentos = [];
    preencherProjetos();
    avisar(mensagemDeErro(status, corpo));
    return;
  }
  orcamentos = corpo;
  preencherProjetos();
}

// --- Comprovante -------------------------------------------------------------

async function reduzirFoto(original) {
  if (!deveComprimir(original)) return original;
  try {
    const imagem = await createImageBitmap(original);
    const { largura, altura } = dimensoesReduzidas(imagem.width, imagem.height);
    const canvas = document.createElement("canvas");
    canvas.width = largura;
    canvas.height = altura;
    canvas.getContext("2d").drawImage(imagem, 0, 0, largura, altura);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.82));
    if (!blob || blob.size >= original.size) return original;
    const nome = (original.name || "comprovante").replace(/\.\w+$/, "") + ".jpg";
    return new File([blob], nome, { type: "image/jpeg" });
  } catch {
    return original; // ex.: HEIC em navegador que não decodifica; o servidor valida
  }
}

function tamanhoLegivel(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

async function escolherArquivo(evento) {
  const original = evento.target.files?.[0];
  evento.target.value = ""; // permite escolher o mesmo arquivo de novo
  if (!original) return;

  arquivo = await reduzirFoto(original);
  if (urlDaPrevia) URL.revokeObjectURL(urlDaPrevia);
  urlDaPrevia = "";

  const ehPdf = arquivo.type === "application/pdf" || /\.pdf$/i.test(arquivo.name);
  if (!ehPdf && arquivo.type.startsWith("image/")) {
    urlDaPrevia = URL.createObjectURL(arquivo);
    el.previa.src = urlDaPrevia;
  }
  el.previa.hidden = ehPdf || !urlDaPrevia;
  el.previaPdf.hidden = !ehPdf;
  el.nomeArquivo.textContent = arquivo.name || "comprovante";
  el.tamanhoArquivo.textContent = tamanhoLegivel(arquivo.size);
  el.vazio.hidden = true;
  el.escolhido.hidden = false;

  const erros = validarFormulario({ ...lerCampos(), arquivo });
  const p = $("erro-comprovante");
  p.textContent = erros.comprovante || "";
  p.hidden = !erros.comprovante;
}

function removerArquivo() {
  arquivo = null;
  if (urlDaPrevia) URL.revokeObjectURL(urlDaPrevia);
  urlDaPrevia = "";
  el.previa.removeAttribute("src");
  el.escolhido.hidden = true;
  el.vazio.hidden = false;
}

// --- Envio -------------------------------------------------------------------

function lerCampos() {
  return {
    orcamento: orcamentoEscolhido(),
    categoria: el.categoria.value,
    valor: el.valor.value,
    data: el.data.value,
    descricao: el.descricao.value,
    arquivo,
  };
}

function formatarData(iso) {
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

async function enviar(evento) {
  evento.preventDefault();
  const dados = lerCampos();
  const erros = validarFormulario(dados);
  if (Object.keys(erros).length) return mostrarErros(erros);

  limparErros();
  el.enviar.disabled = true;
  el.enviar.textContent = "Enviando…";
  const { status, corpo } = await enviarLancamento(montarFormData(dados));
  el.enviar.disabled = false;
  el.enviar.textContent = "Enviar para aprovação";

  if (status === 201) return mostrarSucesso(dados, corpo);
  if (status === 401) return abrirAcesso("Código de acesso inválido. Informe de novo para enviar.");
  avisar(mensagemDeErro(status, corpo));
}

function mostrarSucesso(dados, corpo) {
  $("sucesso-status").textContent = corpo.status_descricao || "Pendente de aprovação";
  $("sucesso-projeto").textContent = dados.orcamento.projeto_id;
  $("sucesso-categoria").textContent = corpo.categoria;
  $("sucesso-valor").textContent = formatarMoeda(corpo.valor ?? converterValor(dados.valor));
  $("sucesso-data").textContent = formatarData(corpo.data_despesa || dados.data);
  $("sucesso-comprovante").textContent = corpo.comprovante?.nome_original || dados.arquivo.name;
  mostrar(el.sucesso);
  window.scrollTo({ top: 0 });
  el.sucesso.focus();
}

function novoLancamento() {
  const projeto = el.projeto.value;
  el.form.reset();
  el.projeto.value = projeto; // educador costuma lançar várias no mesmo projeto
  preencherCategorias();
  el.data.value = hojeISO();
  removerArquivo();
  limparErros();
  mostrar(el.form);
  el.categoria.focus();
}

// --- Código de acesso --------------------------------------------------------

function salvarCodigo(evento) {
  evento.preventDefault();
  const token = el.campoToken.value.trim();
  if (!token) {
    el.erroAcesso.textContent = "Informe o código de acesso.";
    el.erroAcesso.hidden = false;
    return;
  }
  salvarAcesso(token, el.campoApi.value || API_PADRAO);
  carregarProjetos();
}

// --- Início ------------------------------------------------------------------

el.projeto.addEventListener("change", () => {
  preencherCategorias();
  limparErroDoCampo("projeto");
  limparErroDoCampo("categoria");
});
el.categoria.addEventListener("change", () => limparErroDoCampo("categoria"));
el.valor.addEventListener("input", () => limparErroDoCampo("valor"));
el.data.addEventListener("input", () => limparErroDoCampo("data"));
el.descricao.addEventListener("input", () => limparErroDoCampo("descricao"));
el.camera.addEventListener("change", escolherArquivo);
el.galeria.addEventListener("change", escolherArquivo);
el.trocar.addEventListener("click", removerArquivo);
el.form.addEventListener("submit", enviar);
el.novo.addEventListener("click", novoLancamento);
el.formAcesso.addEventListener("submit", salvarCodigo);
el.botaoAcesso.addEventListener("click", () => abrirAcesso());
$("cancelar-acesso").addEventListener("click", () => {
  if (tokenSalvo()) carregarProjetos();
});
$("esquecer-acesso").addEventListener("click", () => {
  esquecerAcesso();
  abrirAcesso("Código removido deste aparelho.");
});

el.data.value = hojeISO();
if (tokenSalvo()) carregarProjetos();
else abrirAcesso();
