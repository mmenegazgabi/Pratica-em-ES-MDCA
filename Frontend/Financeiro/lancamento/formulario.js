// T-13 · US-03 — Regras do formulário de lançamento (sem DOM, testável no Node).
//
// As regras espelham as do backend (POST /lancamentos, T-12): o servidor
// continua validando tudo; aqui é só para o educador ver o erro na hora.

export const TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024;
export const LIMITE_PARA_COMPRIMIR_BYTES = 1.5 * 1024 * 1024;
export const LADO_MAXIMO_PX = 1600;
export const DESCRICAO_MAXIMA = 200;

const TIPOS_DE_IMAGEM = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
const EXTENSOES_ACEITAS = /\.(jpe?g|png|webp|heic|heif|pdf)$/i;

/** "486,90", "1.234,56", "R$ 10", "12.5" → número com 2 casas; inválido → null. */
export function converterValor(texto) {
  let t = String(texto ?? "").replace(/R\$/gi, "").replace(/\s/g, "");
  if (!t) return null;
  if (t.includes(",")) {
    t = t.replace(/\./g, "").replace(",", ".");
  } else if (/^\d{1,3}(\.\d{3})+$/.test(t)) {
    t = t.replace(/\./g, ""); // "1.234" = mil duzentos e trinta e quatro
  }
  if (!/^\d+(\.\d{1,2})?$/.test(t)) return null;
  return Math.round(Number(t) * 100) / 100;
}

export { formatarMoeda } from "../base/formatar.js";

export function ehArquivoAceito(arquivo) {
  if (!arquivo) return false;
  const tipo = (arquivo.type || "").toLowerCase();
  if (TIPOS_DE_IMAGEM.includes(tipo) || tipo === "application/pdf") return true;
  // Alguns celulares mandam HEIC sem tipo; a extensão resolve.
  return !tipo && EXTENSOES_ACEITAS.test(arquivo.name || "");
}

/** Só vale a pena reduzir fotos grandes em formatos que o navegador decodifica. */
export function deveComprimir(arquivo) {
  const tipo = (arquivo?.type || "").toLowerCase();
  return ["image/jpeg", "image/png", "image/webp"].includes(tipo) && arquivo.size > LIMITE_PARA_COMPRIMIR_BYTES;
}

/** Novo tamanho mantendo a proporção, com o maior lado em LADO_MAXIMO_PX. */
export function dimensoesReduzidas(largura, altura, ladoMaximo = LADO_MAXIMO_PX) {
  const maior = Math.max(largura, altura);
  if (maior <= ladoMaximo) return { largura, altura };
  const escala = ladoMaximo / maior;
  return { largura: Math.round(largura * escala), altura: Math.round(altura * escala) };
}

/**
 * Valida os campos. Devolve um objeto { campo: mensagem }; vazio = tudo certo.
 * `orcamento` é o item de GET /orcamentos escolhido (ou undefined).
 */
export function validarFormulario({ orcamento, categoria, valor, data, descricao, arquivo }) {
  const erros = {};

  if (!orcamento) erros.projeto = "Escolha o projeto.";

  if (!categoria) erros.categoria = "Escolha a categoria.";
  else if (orcamento && !orcamento.categorias_despesa.includes(categoria)) {
    erros.categoria = "Categoria não pertence a este projeto.";
  }

  const numero = converterValor(valor);
  if (numero === null) erros.valor = "Informe o valor, por exemplo 486,90.";
  else if (numero <= 0) erros.valor = "O valor deve ser maior que zero.";

  if (!data) erros.data = "Informe a data da despesa.";
  else if (orcamento && (data < orcamento.data_inicio || data > orcamento.data_fim)) {
    erros.data = "A data está fora da vigência do projeto.";
  }

  const texto = (descricao || "").trim();
  if (!texto) erros.descricao = "Descreva a despesa.";
  else if (texto.length > DESCRICAO_MAXIMA) erros.descricao = `Use no máximo ${DESCRICAO_MAXIMA} caracteres.`;

  if (!arquivo) erros.comprovante = "Anexe a foto ou o PDF do comprovante.";
  else if (!ehArquivoAceito(arquivo)) erros.comprovante = "Envie uma foto (JPG, PNG, WEBP, HEIC) ou um PDF.";
  else if (arquivo.size > TAMANHO_MAXIMO_BYTES) erros.comprovante = "O arquivo passa de 5 MB. Tire outra foto ou escolha um arquivo menor.";

  return erros;
}

/** Monta o multipart exatamente como o POST /lancamentos (T-12) espera. */
export function montarFormData({ orcamento, categoria, valor, data, descricao, arquivo }) {
  const dados = new FormData();
  dados.append("orcamento_id", orcamento.id);
  dados.append("valor", converterValor(valor).toFixed(2));
  dados.append("descricao", descricao.trim());
  dados.append("categoria", categoria);
  dados.append("data_despesa", data);
  dados.append("comprovante", arquivo, arquivo.name || "comprovante.jpg");
  return dados;
}

/** Mensagem amigável a partir da resposta de erro da API. */
export function mensagemDeErro(status, corpo) {
  if (status === 0) return "Sem conexão com o servidor. Verifique a internet e tente de novo.";
  if (status === 401) return "Acesso não autorizado. Confira o código de acesso deste aparelho.";
  if (status === 413) return "O comprovante passa de 5 MB. Tire outra foto ou escolha um arquivo menor.";
  if (status === 503) return "O servidor não conseguiu salvar o comprovante agora. Tente de novo em instantes.";
  const detalhe = corpo?.detail;
  if (typeof detalhe === "string") return detalhe;
  if (Array.isArray(detalhe)) return "Confira os campos: algum valor está em formato inválido.";
  return "Não foi possível enviar o lançamento. Tente de novo.";
}

/** Data de hoje no fuso do aparelho, no formato AAAA-MM-DD. */
export function hojeISO(agora = new Date()) {
  const fuso = agora.getTimezoneOffset() * 60000;
  return new Date(agora.getTime() - fuso).toISOString().slice(0, 10);
}
