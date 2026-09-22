// Troque pela URL do backend publicado no Google Cloud Run, sem barra no final.
// Exemplo: https://nome-do-servico-xxxxxxxxxx.southamerica-east1.run.app
const API_BASE_URL = "https://pratica-em-es-mdca-547285598829.southamerica-east1.run.app";

async function testarEndpoint(caminho, elementoId) {
  const elemento = document.getElementById(elementoId);
  elemento.textContent = "Verificando...";
  try {
    const resposta = await fetch(`${API_BASE_URL}${caminho}`);
    const dados = await resposta.json();
    elemento.textContent = resposta.ok
      ? `OK: ${JSON.stringify(dados)}`
      : `Erro: ${JSON.stringify(dados)}`;
  } catch (erro) {
    elemento.textContent = `Erro ao acessar ${API_BASE_URL}: ${erro.message}`;
  }
}

document
  .getElementById("btn-testar-api")
  .addEventListener("click", () => testarEndpoint("/health", "api-status"));
document
  .getElementById("btn-testar-db")
  .addEventListener("click", () => testarEndpoint("/db/health", "db-status"));
document
  .getElementById("btn-testar-storage")
  .addEventListener("click", () => testarEndpoint("/storage/health", "storage-status"));

document.getElementById("form-upload").addEventListener("submit", async (evento) => {
  evento.preventDefault();

  const status = document.getElementById("upload-status");
  const link = document.getElementById("upload-link");
  const arquivo = document.getElementById("arquivo").files[0];

  status.textContent = "Enviando...";
  link.textContent = "";

  const dados = new FormData();
  dados.append("arquivo", arquivo);

  try {
    const resposta = await fetch(`${API_BASE_URL}/files`, {
      method: "POST",
      body: dados,
    });
    const resultado = await resposta.json();

    if (!resposta.ok) {
      throw new Error(resultado.detail || "Erro ao enviar arquivo.");
    }

    status.textContent = `Arquivo enviado: ${resultado.filename}`;
    const anchor = document.createElement("a");
    anchor.href = resultado.url;
    anchor.target = "_blank";
    anchor.rel = "noreferrer";
    anchor.textContent = resultado.url;
    link.appendChild(anchor);
  } catch (erro) {
    status.textContent = `Erro: ${erro.message}`;
  }
});

testarEndpoint("/health", "api-status");
testarEndpoint("/db/health", "db-status");
testarEndpoint("/storage/health", "storage-status");
