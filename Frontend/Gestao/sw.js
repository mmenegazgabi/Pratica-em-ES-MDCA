// Service worker do Módulo de Gestão (T-57 · US-05): guarda os arquivos do app para ele
// abrir no navegador do celular sem conexão (o app não é instalado). Só arquivos do
// próprio site: as chamadas à API (outro domínio) não passam por aqui, e os registros
// feitos sem rede ficam na fila do app (base/fila.js), não neste cache.
//
// Rede primeiro: com conexão, sempre a versão publicada mais recente (e o cache é
// atualizado); sem conexão, a última versão guardada.

const VERSAO = "mdca-gestao-v1";

// O teste tests/pwa.test.js confere que todo arquivo .js do app está nesta lista.
// (Script clássico, sem import/export: nem todo navegador aceita service worker módulo.)
const ARQUIVOS = [
  "./",
  "index.html",
  "style.css",
  "app.js",
  "base/api.js",
  "base/copia-local.js",
  "base/dom.js",
  "base/estados.js",
  "base/fila.js",
  "base/formulario.js",
  "base/papeis.js",
  "telas/alertas.js",
  "telas/atividades.js",
  "telas/equipe.js",
  "telas/pessoas.js",
  "telas/plano.js",
  "telas/programas.js",
  "telas/turmas.js",
  "telas/usuarios.js",
  "telas/visao-integrada.js",
  "assets/bitter-italic-latin.woff2",
  "assets/bitter-latin.woff2",
  "assets/general-sans-400.woff2",
  "assets/general-sans-500.woff2",
  "assets/general-sans-600.woff2",
  "assets/general-sans-700.woff2",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(caches.open(VERSAO).then((cache) => cache.addAll(ARQUIVOS)));
  self.skipWaiting();
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((nomes) => Promise.all(nomes.filter((n) => n.startsWith("mdca-gestao-") && n !== VERSAO).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const pedido = evento.request;
  if (pedido.method !== "GET" || new URL(pedido.url).origin !== self.location.origin) return;
  evento.respondWith(
    fetch(pedido)
      .then((resposta) => {
        if (resposta.ok) {
          const copia = resposta.clone();
          caches.open(VERSAO).then((cache) => cache.put(pedido, copia));
        }
        return resposta;
      })
      .catch(async () => {
        const guardada = await caches.match(pedido, { ignoreSearch: true });
        if (guardada) return guardada;
        // Navegação para uma rota do app sem conexão: a página do app, que lê o endereço.
        if (pedido.mode === "navigate") return caches.match("index.html");
        return Response.error();
      }),
  );
});
