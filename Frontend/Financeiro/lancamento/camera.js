// Câmera do comprovante.
//
// - Celular e tablet (tela de toque): a câmera do próprio aparelho, pelo <input> com
//   `capture` e `accept="image/*"`. Com PDF no `accept`, vários navegadores ignoram o
//   `capture` e abrem o seletor de arquivos, por isso a câmera aceita só imagem.
// - Computador: o `capture` não faz nada, então a webcam abre na própria página
//   (getUserMedia), com prévia, "Tirar foto", "Usar foto" e "Tirar outra".
// - Sem câmera ou sem permissão: aviso e o seletor de arquivo.

import { el } from "../base/dom.js";

export const MENSAGENS = {
  semPermissao: "Sem permissão para usar a câmera. Escolha um arquivo do comprovante.",
  semCamera: "Nenhuma câmera encontrada neste aparelho. Escolha um arquivo do comprovante.",
  falhou: "Não foi possível abrir a câmera. Escolha um arquivo do comprovante.",
};

const QUALIDADE_JPEG = 0.9;

/** Aparelho de toque (celular, tablet): a câmera abre pelo próprio sistema. */
export function temCameraDoAparelho(janela) {
  try {
    return Boolean(janela.matchMedia?.("(pointer: coarse)").matches);
  } catch {
    return false;
  }
}

/** O navegador deixa a página usar a webcam (getUserMedia, só em HTTPS ou localhost). */
export function podeUsarWebcam(janela) {
  return typeof janela.navigator?.mediaDevices?.getUserMedia === "function";
}

/** Texto para o erro do getUserMedia: sem permissão, sem câmera ou outro problema. */
export function mensagemDoErroDaCamera(erro) {
  const nome = erro?.name || "";
  if (["NotAllowedError", "PermissionDeniedError", "SecurityError"].includes(nome)) return MENSAGENS.semPermissao;
  if (["NotFoundError", "DevicesNotFoundError", "OverconstrainedError"].includes(nome)) return MENSAGENS.semCamera;
  return MENSAGENS.falhou;
}

/** "comprovante-20261124-180501.jpg" */
export function nomeDaFoto(agora = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const dia = `${agora.getFullYear()}${p(agora.getMonth() + 1)}${p(agora.getDate())}`;
  const hora = `${p(agora.getHours())}${p(agora.getMinutes())}${p(agora.getSeconds())}`;
  return `comprovante-${dia}-${hora}.jpg`;
}

/** Copia o quadro atual do vídeo para um JPEG; null se o navegador não conseguir. */
async function quadroDoVideo(documento, video) {
  const canvas = documento.createElement("canvas");
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  const contexto = canvas.getContext("2d");
  if (!contexto) return null;
  contexto.drawImage(video, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", QUALIDADE_JPEG));
  return blob ? new File([blob], nomeDaFoto(), { type: "image/jpeg" }) : null;
}

/**
 * Abre a webcam numa janela sobre a página.
 * `aoUsar(arquivo)` recebe a foto aceita; `aoEscolherArquivo()` abre o seletor de arquivo.
 * Devolve uma Promise que termina quando a janela fecha.
 */
export function abrirWebcam({ janela = window, aoUsar, aoEscolherArquivo }) {
  const documento = janela.document;
  let fluxo = null;
  let foto = null;
  let urlDaFoto = "";
  let terminar;
  const fechada = new Promise((ok) => (terminar = ok));

  const aviso = el("p", { id: "camera-aviso", class: "aviso", role: "alert", hidden: true });
  const video = el("video", { id: "camera-video", class: "camera__video", autoplay: true, playsinline: true, muted: true, "aria-label": "Imagem da câmera" });
  video.muted = true; // sem som: o navegador deixa o vídeo começar sozinho
  const imagem = el("img", { id: "camera-foto", class: "camera__video", alt: "Foto do comprovante", hidden: true });
  const botao = (id, texto, classe, aoClicar) => el("button", { type: "button", id, class: `botao ${classe}`, hidden: true, onclick: aoClicar }, texto);
  const tirar = botao("camera-tirar", "Tirar foto", "", tirarFoto);
  const usar = botao("camera-usar", "Usar foto", "", usarFoto);
  const outra = botao("camera-outra", "Tirar outra", "botao--sec", tirarOutra);
  const arquivo = botao("camera-arquivo", "Escolher arquivo", "", escolherArquivo);
  const cancelar = el("button", { type: "button", id: "camera-cancelar", class: "botao botao--sec", onclick: fechar }, "Cancelar");

  const janelaDaCamera = el(
    "div",
    { id: "camera", class: "camera", role: "dialog", "aria-modal": "true", "aria-labelledby": "camera-titulo" },
    el(
      "div",
      { class: "camera__caixa" },
      el("h2", { id: "camera-titulo", class: "camera__titulo" }, "Fotografar comprovante"),
      aviso,
      video,
      imagem,
      el("div", { class: "camera__acoes" }, tirar, usar, outra, arquivo, cancelar),
    ),
  );

  function aoTeclar(evento) {
    if (evento.key === "Escape") fechar();
  }

  function pararCamera() {
    for (const trilha of fluxo?.getTracks?.() || []) trilha.stop();
    fluxo = null;
    video.srcObject = null;
  }

  function fechar() {
    pararCamera();
    if (urlDaFoto) URL.revokeObjectURL(urlDaFoto);
    documento.removeEventListener("keydown", aoTeclar);
    janelaDaCamera.remove();
    terminar();
  }

  function mostrarFalha(mensagem) {
    pararCamera();
    aviso.textContent = mensagem;
    aviso.hidden = false;
    video.hidden = true;
    imagem.hidden = true;
    for (const b of [tirar, usar, outra]) b.hidden = true;
    arquivo.hidden = false;
    arquivo.focus();
  }

  async function tirarFoto() {
    tirar.disabled = true;
    try {
      foto = await quadroDoVideo(documento, video);
    } catch {
      foto = null;
    }
    tirar.disabled = false;
    if (!foto) return mostrarFalha(MENSAGENS.falhou);
    urlDaFoto = URL.createObjectURL(foto);
    imagem.src = urlDaFoto;
    imagem.hidden = false;
    video.hidden = true;
    tirar.hidden = true;
    usar.hidden = false;
    outra.hidden = false;
    usar.focus();
  }

  function tirarOutra() {
    if (urlDaFoto) URL.revokeObjectURL(urlDaFoto);
    urlDaFoto = "";
    foto = null;
    imagem.hidden = true;
    video.hidden = false;
    usar.hidden = true;
    outra.hidden = true;
    tirar.hidden = false;
    tirar.focus();
  }

  function usarFoto() {
    const escolhida = foto;
    fechar();
    if (escolhida) aoUsar(escolhida);
  }

  function escolherArquivo() {
    fechar();
    aoEscolherArquivo();
  }

  documento.body.append(janelaDaCamera);
  documento.addEventListener("keydown", aoTeclar);
  cancelar.focus();

  janela.navigator.mediaDevices
    .getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false })
    .then((recebido) => {
      if (!janelaDaCamera.isConnected) {
        // Fechou antes de a câmera abrir: devolve a câmera ao sistema.
        for (const trilha of recebido.getTracks?.() || []) trilha.stop();
        return;
      }
      fluxo = recebido;
      video.srcObject = recebido;
      video.play?.()?.catch?.(() => {});
      tirar.hidden = false;
      tirar.focus();
    })
    .catch((erro) => {
      if (janelaDaCamera.isConnected) mostrarFalha(mensagemDoErroDaCamera(erro));
    });

  return fechada;
}
