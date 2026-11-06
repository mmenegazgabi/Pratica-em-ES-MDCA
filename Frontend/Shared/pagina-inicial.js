// Página inicial (Frontend/index.html): Entrar, Primeiro acesso, Esqueci minha senha e,
// depois de entrar, a escolha de módulo. Textos digitados pela pessoa ou vindos da API
// entram sempre por textContent.

import {
  atualizarUsuario,
  entrar,
  lerSessao,
  primeiroAcesso,
  sair,
  salvarUrlDaApi,
  temPapel,
  urlDaApi,
} from "./plataforma.js";

const EMAIL_VALIDO = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function iniciar(documento = document) {
  const $ = (id) => documento.getElementById(id);
  const formularios = { entrar: $("formEntrar"), primeiro: $("formPrimeiro"), esqueci: $("esqueci") };

  // — menu do celular —
  $("navToggle").addEventListener("click", () => {
    const aberto = $("sidebar").classList.toggle("is-open");
    $("navToggle").setAttribute("aria-expanded", String(aberto));
  });

  // — servidor (avançado) —
  $("apiEndereco").value = urlDaApi();
  const guardarServidor = () => salvarUrlDaApi($("apiEndereco").value);

  function mostrarFormulario(qual, focar = true) {
    for (const [nome, el] of Object.entries(formularios)) el.hidden = nome !== qual;
    limparErro("loginErro", ["loginEmail", "loginSenha"]);
    limparErro("primeiroErro", ["primeiroEmail", "primeiroCodigo", "primeiroSenha", "primeiroRepetir"]);
    if (!focar) return;
    const foco = { entrar: "loginEmail", primeiro: "primeiroEmail", esqueci: "esqueciIrPrimeiro" }[qual];
    $(foco).focus();
  }

  function limparErro(caixa, campos) {
    $(caixa).hidden = true;
    $(caixa).textContent = "";
    for (const id of campos) $(id).classList.remove("login-entrada--erro");
  }

  function mostrarErro(caixa, texto, campo) {
    $(caixa).textContent = texto;
    $(caixa).hidden = false;
    if (campo) {
      $(campo).classList.add("login-entrada--erro");
      $(campo).focus();
    }
  }

  function mostrarModulos(sessao) {
    const nome = String(sessao.usuario?.nome || "").trim();
    $("saudacao").textContent = nome ? `Olá, ${nome}` : "Olá";
    const admin = temPapel(sessao, "administracao");
    $("navAdmin").hidden = !admin;
    $("cartaoAdmin").hidden = !admin;
    $("login").hidden = true;
    $("app").hidden = false;
    documento.title = "Sistema MDCA";
  }

  function mostrarLogin() {
    $("app").hidden = true;
    $("login").hidden = false;
    documento.title = "Entrar · Sistema MDCA";
  }

  async function enviar(botao, textoEnviando, acao) {
    const original = botao.textContent;
    botao.disabled = true;
    botao.textContent = textoEnviando;
    try {
      return await acao();
    } finally {
      botao.disabled = false;
      botao.textContent = original;
    }
  }

  // — Entrar —
  $("formEntrar").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const botao = $("entrarBotao");
    if (botao.disabled) return;
    limparErro("loginErro", ["loginEmail", "loginSenha"]);
    const email = $("loginEmail").value.trim();
    const senha = $("loginSenha").value;
    if (!EMAIL_VALIDO.test(email)) return mostrarErro("loginErro", "Informe um e-mail válido.", "loginEmail");
    if (!senha) return mostrarErro("loginErro", "Informe a senha.", "loginSenha");
    guardarServidor();
    const resultado = await enviar(botao, "Entrando…", () =>
      entrar({ email, senha, lembrar: $("loginLembrar").checked }),
    );
    if (!resultado.ok) return mostrarErro("loginErro", resultado.mensagem);
    $("loginSenha").value = "";
    mostrarModulos(resultado.sessao);
  });

  // — Primeiro acesso —
  $("formPrimeiro").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const botao = $("primeiroBotao");
    if (botao.disabled) return;
    limparErro("primeiroErro", ["primeiroEmail", "primeiroCodigo", "primeiroSenha", "primeiroRepetir"]);
    const email = $("primeiroEmail").value.trim();
    const codigo = $("primeiroCodigo").value.trim();
    const senha = $("primeiroSenha").value;
    const repetir = $("primeiroRepetir").value;
    if (!EMAIL_VALIDO.test(email)) return mostrarErro("primeiroErro", "Informe um e-mail válido.", "primeiroEmail");
    if (!codigo) return mostrarErro("primeiroErro", "Informe o código de acesso.", "primeiroCodigo");
    if (!senha) return mostrarErro("primeiroErro", "Crie uma senha.", "primeiroSenha");
    if (senha !== repetir) return mostrarErro("primeiroErro", "As senhas não conferem.", "primeiroRepetir");
    guardarServidor();
    const resultado = await enviar(botao, "Salvando…", () =>
      primeiroAcesso({ email, codigo, senha, lembrar: $("primeiroLembrar").checked }),
    );
    if (!resultado.ok) return mostrarErro("primeiroErro", resultado.mensagem);
    $("primeiroSenha").value = "";
    $("primeiroRepetir").value = "";
    $("primeiroCodigo").value = "";
    mostrarModulos(resultado.sessao);
  });

  // — trocas de formulário —
  $("irEsqueci").addEventListener("click", () => mostrarFormulario("esqueci"));
  $("irPrimeiro").addEventListener("click", () => mostrarFormulario("primeiro"));
  $("esqueciIrPrimeiro").addEventListener("click", () => mostrarFormulario("primeiro"));
  $("esqueciVoltar").addEventListener("click", () => mostrarFormulario("entrar"));
  $("primeiroVoltar").addEventListener("click", () => mostrarFormulario("entrar"));

  $("mostrarSenha").addEventListener("click", () => {
    const campo = $("loginSenha");
    const ver = campo.type === "password";
    campo.type = ver ? "text" : "password";
    $("mostrarSenha").textContent = ver ? "Ocultar" : "Mostrar";
  });

  // — Sair —
  $("sair").addEventListener("click", async () => {
    const botao = $("sair");
    if (botao.disabled) return;
    botao.disabled = true;
    try {
      await sair();
    } finally {
      botao.disabled = false;
    }
    $("sidebar").classList.remove("is-open");
    $("navToggle").setAttribute("aria-expanded", "false");
    mostrarLogin();
    mostrarFormulario("entrar");
  });

  const sessao = lerSessao();
  if (sessao) {
    mostrarModulos(sessao);
    // A administração pode ter dado ou tirado papéis desde o login: confere em /auth/eu.
    return atualizarUsuario().then((atual) => {
      if ($("app").hidden) return; // a pessoa já saiu enquanto isso
      if (atual) return mostrarModulos(atual);
      mostrarLogin();
      mostrarFormulario("entrar", false);
    });
  } else {
    mostrarLogin();
    mostrarFormulario("entrar", false);
  }
}
