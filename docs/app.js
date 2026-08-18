/* Raio-X do Candidato — SPA vanilla (sem build, sem framework)
   Rotas por hash:  #/            → busca (UF default)
                    #/go          → busca na UF
                    #/go/1234567  → ficha do candidato                     */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const app = $("#app");
const BASE = location.pathname.replace(/index\.html$/, "").replace(/\/$/, "");
const UF_DEFAULT = "go";

const state = { ufs: null, indices: {}, filtroCargo: "todos", termo: "", compara: [], modoCompara: false };

/* ── utilidades ─────────────────────────────────────────────── */
const norm = (s) => (s || "")
  .toString().normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().trim();

const brl = new Intl.NumberFormat("pt-BR",
  { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

function brlCompacto(v) {
  if (v == null) return "não declarado";
  if (v >= 1e9) return "R$ " + (v / 1e9).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " bi";
  if (v >= 1e6) return "R$ " + (v / 1e6).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " mi";
  if (v >= 1e3) return "R$ " + (v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 }) + " mil";
  return brl.format(v);
}

function fdata(s) {
  s = (s ?? "").toString();
  let m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (m) return `${m[3]}/${m[2]}/${m[1]}`;
  m = s.match(/^(\d{4})-(\d{2})$/);
  if (m) return `${m[2]}/${m[1]}`;
  return s;
}

function esc(s) {
  return (s ?? "").toString().replace(/[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function pillClass(st) {
  const s = norm(st);
  if (/DEFERIDO COM|INDEFERIDO|CASSADO|CANCELADO|INAPTO|IMPUGNADO|RENUNC/.test(s))
    return /^DEFERIDO COM/.test(s) ? "warn" : "bad";
  if (/^(DEFERIDO|APTO)/.test(s)) return "ok";
  return "warn"; // aguardando julgamento, sub judice, pendente
}

const DEMO = window.__DEMO_DATA__ || null; // modo demo: dados embutidos num único HTML

async function getJSON(path) {
  if (DEMO) {
    if (DEMO.files[path]) return DEMO.files[path];
    throw new Error("fora do demo");
  }
  const r = await fetch(`${BASE}/${path}`);
  if (!r.ok) throw new Error(`${r.status} em ${path}`);
  return r.json();
}

function fotoURL(uf, sq) {
  if (DEMO) return DEMO.fotos[sq] || null;
  return `${BASE}/data/${uf.toUpperCase()}/fotos/${sq}.jpg`;
}

async function carregarIndice(uf) {
  uf = uf.toUpperCase();
  if (!state.indices[uf]) {
    const idx = await getJSON(`data/${uf}/index.json`);
    idx.candidatos.forEach((c) => {
      c._busca = norm(`${c.nu} ${c.nm} ${c.pt}`);
      c._nr = c.nr || "";
    });
    state.indices[uf] = idx;
  }
  return state.indices[uf];
}

/* ── busca ──────────────────────────────────────────────────── */
const CARGOS = [
  ["todos", "Todos"],
  ["GOVERNADOR", "Governador"],
  ["SENADOR", "Senador"],
  ["DEPUTADO FEDERAL", "Dep. Federal"],
  ["DEPUTADO ESTADUAL", "Dep. Estadual"],
];

function filtrar(idx) {
  const termo = norm(state.termo);
  const soNumero = /^\d+$/.test(state.termo.trim());
  let lista = idx.candidatos;

  if (state.filtroCargo !== "todos")
    lista = lista.filter((c) => norm(c.cg) === state.filtroCargo);

  if (termo) {
    lista = soNumero
      ? lista.filter((c) => c._nr.startsWith(state.termo.trim()))
      : lista.filter((c) => c._busca.includes(termo));
    lista = [...lista].sort((a, b) => {
      const pa = a._busca.startsWith(termo) || a._nr === state.termo.trim() ? 0 : 1;
      const pb = b._busca.startsWith(termo) || b._nr === state.termo.trim() ? 0 : 1;
      return pa - pb || (b.pat || 0) - (a.pat || 0);
    });
  } else if (state.filtroCargo === "todos") {
    // sem busca: majoritários primeiro (governador/senador), depois por nome
    const peso = (c) => (/GOVERNADOR|SENADOR/.test(norm(c.cg)) && !/VICE|SUPLENTE/.test(norm(c.cg)) ? 0 : 1);
    lista = [...lista].sort((a, b) => peso(a) - peso(b) || (a.nu || "").localeCompare(b.nu || "", "pt-BR"));
  }
  return lista;
}

function cardCandidato(uf, c) {
  const fsrc = c.ft ? fotoURL(uf, c.sq) : null;
  const foto = fsrc
    ? `<img class="cand-foto" loading="lazy" src="${fsrc}" alt="">`
    : `<div class="cand-foto vazia" aria-hidden="true">👤</div>`;
  return `<a class="cand-card" href="#/${uf}/${c.sq}">
    ${foto}
    <div class="cand-info">
      <div class="cand-nome">${esc(c.nu || c.nm)}</div>
      <div class="cand-sub">${esc(c.cg)} · ${esc(c.pt || "")} · patrimônio: ${brlCompacto(c.pat)}${
        c.ve ? ` · já eleito ${c.ve}×` : (c.vc ? ` · concorreu ${c.vc}×` : " · estreante")}</div>
    </div>
    <div class="cand-lado">
      <div class="cand-num">${esc(c.nr || "")}</div>
      <span class="pill ${pillClass(c.st)}">${esc(c.st)}</span>
    </div>
  </a>`;
}

async function telaBusca(uf) {
  document.title = "Raio-X do Candidato — Eleições 2026";
  app.innerHTML = `<p class="carregando">Carregando candidatos…</p>`;
  let idx;
  try { idx = await carregarIndice(uf); }
  catch {
    app.innerHTML = `<p class="erro">Ainda não publicamos os dados de <b>${esc(uf.toUpperCase())}</b>.
      <a href="#/${UF_DEFAULT}">Ver Goiás</a></p>`;
    return;
  }

  app.innerHTML = `
    <div class="hero">
      <h1>Quem é esse candidato, <em>de verdade</em>?</h1>
      <p>Digite o nome ou o número e veja a ficha única — patrimônio declarado desde 2014,
         situação do registro e mais. Cada dado com link da fonte oficial. Sem nota, sem ranking.</p>
    </div>
    <div class="busca-box">
      <input class="busca" id="q" type="search" autocomplete="off"
             placeholder="Nome de urna ou número · ${esc(uf.toUpperCase())} 2026"
             aria-label="Buscar candidato">
    </div>
    <div class="chips" role="group" aria-label="Filtrar por cargo">
      ${CARGOS.map(([v, l]) =>
        `<button class="chip" data-cargo="${v}" aria-pressed="${v === state.filtroCargo}">${l}</button>`).join("")}
      <button class="chip chip-comparar" id="btn-modo-comparar" aria-pressed="${state.modoCompara}">⇄ Comparar</button>
    </div>
    <div class="compara-barra" id="compara-barra" hidden>
      <span id="compara-info"></span>
      <button class="btn" id="btn-ver-comparacao" disabled>Ver comparação</button>
      <button class="btn sec" id="btn-limpar-comparacao">Limpar</button>
    </div>
    <p class="meta-busca" id="meta"></p>
    <div class="lista" id="lista"></div>`;

  const lista = $("#lista"), meta = $("#meta"), q = $("#q");
  q.value = state.termo;

  function render() {
    const res = filtrar(idx);
    meta.textContent = `${res.length} candidato${res.length === 1 ? "" : "s"} · ` +
      `dados do TSE de ${idx.dados_tse_de || idx.gerado_em}`;
    const LIM = 60;
    lista.innerHTML = res.slice(0, LIM).map((c) => cardCandidato(uf, c)).join("") +
      (res.length > LIM ? `<p class="meta-busca">Mostrando ${LIM} de ${res.length} — refine a busca.</p>` : "");
    if (typeof renderBarraRef === "function") renderBarraRef();
  }
  let renderBarraRef = null;
  q.addEventListener("input", () => { state.termo = q.value; render(); });

  // ── modo comparar: clicar num card seleciona em vez de abrir ──
  const barra = $("#compara-barra"), btnModo = $("#btn-modo-comparar");
  function renderBarra() {
    const n = state.compara.length;
    barra.hidden = !state.modoCompara;
    btnModo.setAttribute("aria-pressed", state.modoCompara);
    if (!state.modoCompara) return;
    const nomes = state.compara.map((sq) => {
      const c = idx.candidatos.find((x) => x.sq === sq);
      return c ? (c.nu || c.nm) : sq;
    });
    $("#compara-info").textContent = n
      ? `${nomes.join(" × ")} (${n}/3)` : "Toque em até 3 candidatos para comparar";
    $("#btn-ver-comparacao").disabled = n < 2;
    lista.querySelectorAll(".cand-card").forEach((a) => {
      const sq = a.getAttribute("href").split("/").pop();
      a.classList.toggle("selecionado", state.compara.includes(sq));
    });
  }
  btnModo.addEventListener("click", () => {
    state.modoCompara = !state.modoCompara;
    if (!state.modoCompara) state.compara = [];
    renderBarraRef = renderBarra;
  renderBarra();
  });
  $("#btn-limpar-comparacao").addEventListener("click", () => { state.compara = []; renderBarra(); });
  $("#btn-ver-comparacao").addEventListener("click", () => {
    location.hash = `#/${uf}/comparar/${state.compara.join(",")}`;
  });
  lista.addEventListener("click", (e) => {
    if (!state.modoCompara) return;
    const a = e.target.closest(".cand-card");
    if (!a) return;
    e.preventDefault();
    const sq = a.getAttribute("href").split("/").pop();
    const i = state.compara.indexOf(sq);
    if (i >= 0) state.compara.splice(i, 1);
    else if (state.compara.length < 3) state.compara.push(sq);
    renderBarra();
  });
  renderBarra();
  app.querySelectorAll(".chip[data-cargo]").forEach((ch) => ch.addEventListener("click", () => {
    state.filtroCargo = ch.dataset.cargo;
    app.querySelectorAll(".chip[data-cargo]").forEach((o) => o.setAttribute("aria-pressed", o === ch));
    render();
  }));
  render();
  q.focus({ preventScroll: true });
}

/* ── gráfico patrimonial (série única, rótulos diretos) ─────── */
function graficoPatrimonio(serie) {
  const W = 640, H = 240, padL = 10, padB = 34, padT = 30;
  const max = Math.max(...serie.map((p) => p.total || 0), 1);
  const bw = 90, gap = (W - padL * 2 - bw * serie.length) / (serie.length - 1);
  const bars = serie.map((p, i) => {
    const x = padL + i * (bw + gap);
    const h = p.declarou && p.total ? Math.max(4, (p.total / max) * (H - padB - padT - 8)) : 0;
    const y = H - padB - h;
    const rotY = p.declarou ? y - 8 : H - padB - 10;
    const rot = p.declarou ? brlCompacto(p.total) : "não declarou";
    return `
      <g>
        <title>${p.ano}: ${p.declarou ? brl.format(p.total) + ` (${p.n_bens} bens)` : "não declarou bens"}</title>
        ${p.declarou
          ? `<rect class="barra" x="${x}" y="${y}" width="${bw}" height="${h}" rx="4"/>`
          : `<rect class="barra vazia" x="${x}" y="${H - padB - 4}" width="${bw}" height="4" rx="2"/>`}
        <text class="rotulo ${p.declarou ? "" : "mut"}" x="${x + bw / 2}" y="${rotY}" text-anchor="middle">${rot}</text>
        <text class="eixo" x="${x + bw / 2}" y="${H - padB + 20}" text-anchor="middle">${p.ano}</text>
      </g>`;
  }).join("");
  return `<div class="graf" role="img"
      aria-label="Patrimônio declarado por eleição: ${serie.map((p) =>
        `${p.ano} ${p.declarou ? brl.format(p.total) : "não declarou"}`).join("; ")}">
    <svg viewBox="0 0 ${W} ${H}">
      <line x1="0" y1="${H - padB}" x2="${W}" y2="${H - padB}" stroke="#e2e8f2" stroke-width="1"/>
      ${bars}
    </svg></div>`;
}

/* ── ficha ──────────────────────────────────────────────────── */
function dado(rot, val) {
  return val ? `<div class="dado"><div class="rot">${rot}</div><div class="val">${esc(val)}</div></div>` : "";
}

function secaoEmBreve(ico, titulo, texto) {
  return `<section class="secao"><h2><span class="ico">${ico}</span>${titulo}</h2>
    <p class="embreve">${texto} <span class="pill warn">em breve</span></p></section>`;
}

async function telaFicha(uf, sq) {
  app.innerHTML = `<p class="carregando">Carregando ficha…</p>`;
  let f;
  try { f = await getJSON(`data/${uf.toUpperCase()}/${sq}.json`); }
  catch {
    app.innerHTML = `<p class="erro">Ficha não encontrada. <a href="#/${uf}">Voltar à busca</a></p>`;
    return;
  }
  const nome = f.nome_urna || f.nome;
  document.title = `${nome} (${f.partido?.sigla}) — ${f.cargo} · ${f.uf} 2026 | Raio-X do Candidato`;

  const serie = f.patrimonio?.serie || [];
  const tot26 = serie.find((p) => p.ano === f.ano && p.declarou)?.total ?? null;
  const vars = (f.patrimonio?.variacoes || []).filter((v) => v.pct != null);
  const bens = f.patrimonio?.bens || [];

  const varsHTML = vars.length ? `<ul class="var-lista">${vars.map((v) =>
    `<li>${v.de} → ${v.para}: <b class="${v.pct >= 0 ? "up" : "down"}">${v.pct > 0 ? "+" : ""}${v.pct.toLocaleString("pt-BR")}%</b>
     (declarado pelo próprio candidato)</li>`).join("")}</ul>` : "";

  const bensLinhas = (lim) => bens.slice(0, lim).map((b) => `<tr>
      <td>${esc(b.tipo)}</td><td>${esc(b.descricao || "")}</td>
      <td class="v">${b.valor != null ? brl.format(b.valor) : "—"}</td></tr>`).join("");

  const tcuHTML = (() => {
    const t = f.tcu || {};
    if (!t.disponivel)
      return `<p class="embreve">Cruzamento com a lista de contas julgadas irregulares do TCU
        (~6 mil responsáveis; a lista oficial é publicada pelo TCU para cada eleição) <span class="pill warn">em breve</span></p>`;
    if (!t.listado)
      return `<p class="tcu-ok">✓ Não consta da lista de contas julgadas irregulares do TCU.</p>`;
    return `<p class="tcu-hit">Consta da lista do TCU${t.criterio === "nome"
        ? " (cruzamento por nome — pode haver homônimo, confira na fonte)" : ""}.</p>
      <table class="bens-tabela"><tr><th>Processo</th><th>Deliberação</th><th>Trânsito em julgado</th></tr>
      ${t.registros.map((r) => `<tr><td>${esc(r.processo)}</td><td>${esc(r.deliberacao)}</td><td>${esc(r.transito)}</td></tr>`).join("")}
      </table><div class="disclaimer">${esc(t.disclaimer || "")}</div>`;
  })();

  const planoHTML = f.resumo_plano ? `
    <section class="secao"><h2><span class="ico">📋</span>Plano de governo — resumo</h2>
      <p class="fonte-linha">Resumo automatizado (IA) do PDF oficial protocolado no TSE ·
        <a href="${esc(f.resumo_plano.fonte)}" target="_blank" rel="noopener">documento original</a></p>
      <p>${esc(f.resumo_plano.resumo)}</p>
      ${(f.resumo_plano.temas || []).map((t) =>
        `<p><b>${esc(t.tema)}:</b> ${t.propostas.map(esc).join("; ")}</p>`).join("")}
    </section>` : "";

  app.innerHTML = `
    <a class="voltar" href="#/${uf}">← voltar à busca</a>
    <div class="ficha-topo">
      ${f.foto && fotoURL(uf, sq) ? `<img class="ficha-foto" src="${fotoURL(uf, sq)}" alt="Foto oficial de ${esc(nome)}">` : ""}
      <div class="ficha-id">
        <h1>${esc(nome)}</h1>
        <div class="completo">${esc(f.nome)}${f.nome_social ? ` · nome social: ${esc(f.nome_social)}` : ""}</div>
        <div class="cargo-linha">${esc(f.cargo)} · ${esc(f.partido?.sigla || "")}
          ${f.federacao ? ` · ${esc(f.federacao)}` : ""} · ${esc(f.uf)}</div>
        <div class="acoes">
          <span class="pill ${pillClass(f.situacao?.label)}">${esc(f.situacao?.label)}</span>
          <button class="btn" id="btn-share">Compartilhar ficha</button>
          <a class="btn sec" target="_blank" rel="noopener" href="${esc(f.fontes?.divulgacand)}">Ver no TSE ↗</a>
        </div>
      </div>
      <div class="ficha-num"><div class="num">${esc(f.numero || "")}</div><div class="rot">número na urna</div></div>
    </div>

    <section class="secao">
      <h2><span class="ico">🪪</span>Perfil</h2>
      <p class="fonte-linha">Fonte: registro de candidatura no
        <a href="${esc(f.fontes?.divulgacand)}" target="_blank" rel="noopener">DivulgaCandContas/TSE</a> ·
        <a href="${esc(f.fontes?.dataset_candidatos)}" target="_blank" rel="noopener">dados abertos</a> ·
        dados de ${esc(f.dados_tse_de || "")}</p>
      <div class="grade">
        ${dado("Idade", f.idade ? `${f.idade} anos (${f.nascimento})` : f.nascimento)}
        ${dado("Naturalidade", f.uf_nascimento)}
        ${dado("Escolaridade", f.instrucao)}
        ${dado("Ocupação declarada", f.ocupacao)}
        ${dado("Gênero", f.genero)}
        ${dado("Cor/raça (autodeclarada)", f.cor_raca)}
        ${dado("CPF", f.cpf_mascarado)}
        ${dado("Coligação", f.coligacao)}
      </div>
    </section>

    <section class="secao">
      <h2><span class="ico">🗂️</span>Histórico eleitoral</h2>
      <p class="fonte-linha">Fonte: resultados das eleições gerais nos
        <a href="${esc(f.fontes?.dataset_candidatos)}" target="_blank" rel="noopener">dados abertos do TSE</a>,
        cruzados por CPF</p>
      ${f.historico?.ja_concorreu ? `
        <p>Concorreu <b>${f.historico.vezes_candidato}×</b> em eleições gerais anteriores${
          f.historico.vezes_eleito ? `, foi eleito <b>${f.historico.vezes_eleito}×</b>` : ", nunca foi eleito"}${
          f.historico.trocas_partido ? ` · trocou de partido <b>${f.historico.trocas_partido}×</b> entre as eleições` : " · sempre pelo mesmo partido"}.</p>
        ${(f.historico.mandatos || []).length ? `<p><b>Mandatos exercidos:</b> ${
          f.historico.mandatos.map((m) =>
            `${esc(m.cargo)} de ${esc(m.onde)} (${m.inicio}–${m.fim})`).join("; ")}.</p>` : ""}
        <table class="bens-tabela">
          <tr><th>Ano</th><th>Cargo</th><th>Onde</th><th>Partido</th><th>Resultado</th></tr>
          ${(f.historico.eleicoes || []).map((h) => `<tr>
            <td>${h.ano}</td><td>${esc(h.cargo || "")}</td>
            <td>${esc(h.municipio ? `${h.municipio} · ${h.uf}` : h.uf || "")}</td>
            <td>${esc(h.partido || "")}</td>
            <td>${h.ano === f.ano ? "Concorrendo agora" : esc(h.resultado || "—")}</td></tr>`).join("")}
        </table>`
        : `<p>Primeira candidatura desde 2014 — não concorreu em eleições gerais nem municipais no período coberto pela base.</p>`}
      <p class="fonte-linha" style="margin-top:8px">${esc(f.historico?.nota || "")}</p>
    </section>

    <section class="secao">
      <h2><span class="ico">💰</span>Evolução patrimonial declarada</h2>
      <p class="fonte-linha">Fonte: declarações de bens ao TSE em cada eleição (cruzadas por CPF) ·
        <a href="${esc(f.fontes?.dataset_bens)}" target="_blank" rel="noopener">dados abertos</a></p>
      ${tot26 != null ? `<p>Patrimônio declarado em 2026: <b>${brl.format(tot26)}</b></p>` : ""}
      ${graficoPatrimonio(serie)}
      ${varsHTML}
      ${bens.length ? `
        <table class="bens-tabela" id="bens">
          <tr><th>Tipo</th><th>Descrição (como declarado)</th><th>Valor</th></tr>
          ${bensLinhas(8)}
        </table>
        ${bens.length > 8 ? `<button class="ver-mais" id="btn-bens">ver todos os ${bens.length} bens ↓</button>` : ""}`
        : `<p class="embreve">Nenhum bem declarado nesta eleição.</p>`}
      <div class="disclaimer">${esc(f.patrimonio?.disclaimer || "")}</div>
    </section>

    <section class="secao">
      <h2><span class="ico">⚖️</span>Contas julgadas irregulares (TCU)</h2>
      ${tcuHTML}
    </section>

    <section class="secao">
      <h2><span class="ico">🧾</span>Registros em cadastros oficiais de sanção (CGU)</h2>
      <p class="fonte-linha">CEIS, CNEP e CEAF —
        <a href="${esc(f.sancoes?.consulta_oficial)}" target="_blank" rel="noopener">consulta oficial no Portal da Transparência</a></p>
      ${!f.sancoes?.disponivel
        ? `<p class="embreve">Cruzamento em preparação <span class="pill warn">em breve</span></p>`
        : (f.sancoes.registros || []).length
          ? `<table class="bens-tabela">
              <tr><th>Cadastro</th><th>Categoria</th><th>Órgão sancionador</th><th>Processo</th><th>Vigência</th></tr>
              ${f.sancoes.registros.map((s) => `<tr>
                <td>${esc(s.cadastro)}</td><td>${esc(s.categoria || "")}</td>
                <td>${esc(s.orgao || "")}${s.uf_orgao ? ` · ${esc(s.uf_orgao)}` : ""}</td>
                <td>${esc(s.processo || "")}</td>
                <td>${esc(s.inicio || "")}${s.fim ? ` a ${esc(s.fim)}` : ""}</td></tr>`).join("")}
            </table>
            ${f.sancoes.registros.some((s) => s.criterio !== "cpf")
              ? `<p class="fonte-linha">Registro(s) do CEAF identificados por CPF parcial + nome — confira a identidade na consulta oficial.</p>` : ""}
            <div class="disclaimer">${esc(f.sancoes.disclaimer || "")}</div>`
          : `<p class="tcu-ok">✓ Nada consta nos cadastros CEIS, CNEP e CEAF (consulta por CPF em ${fdata(f.gerado_em)}).</p>`}
    </section>

    ${uf.toUpperCase() === "GO" ? `
    <section class="secao">
      <h2><span class="ico">🏛️</span>Contas no Tribunal de Contas dos Municípios (TCM-GO)</h2>
      ${f.tcmgo?.registros?.length ? `
        <p class="fonte-linha">Fonte: <a href="${esc(f.tcmgo.fonte_url)}" target="_blank"
          rel="noopener">${esc(f.tcmgo.fonte)}</a> · consulta de ${fdata(f.tcmgo.gerado_em)}</p>
        <p class="tcu-hit">Consta da lista oficial do TCM-GO (identificação por nome + iniciais do CPF — confira no processo).</p>
        <table class="bens-tabela">
          <tr><th>Lista</th><th>Município/órgão</th><th>Assunto</th><th>Decisão</th><th>Trânsito</th><th>Processo</th></tr>
          ${f.tcmgo.registros.map((r) => `<tr>
            <td>${esc(r.tipo_lista)}</td><td>${esc(r.municipio)}</td><td>${esc(r.assunto || "")}</td>
            <td>${esc(r.acordao || "")}</td><td>${esc(r.transito_em_julgado || "")}</td>
            <td>${r.processo_url ? `<a href="${esc(r.processo_url)}" target="_blank" rel="noopener">${esc(r.processo)} ↗</a>` : esc(r.processo)}${r.municipio_no_historico ? `<br><span class="fonte-linha">município consta do histórico do candidato ✓</span>` : ""}</td></tr>`).join("")}
        </table>
        <p class="fonte-linha">O sistema de processos do TCM-GO exige verificação anti-robô — o link identifica o processo; resolva a verificação no site para ver os detalhes.</p>
        <div class="disclaimer">${esc(f.tcmgo.disclaimer || "")}</div>`
        : (() => {
            const foiGestorMun = (f.historico?.mandatos || []).some((m) =>
              m.executivo && /PREFEITO/i.test(m.cargo || "") && !/VICE/i.test(m.cargo || ""));
            return `<p class="tcu-ok">✓ Não consta da lista de contas com parecer pela rejeição ou julgadas irregulares do TCM-GO (consulta de ${fdata(f.gerado_em)}).</p>
           <p class="fonte-linha">${foiGestorMun
             ? "O candidato já foi gestor municipal em Goiás e não aparece na lista."
             : "Atenção ao escopo: essa lista só alcança quem geriu recursos municipais em Goiás — para quem nunca exerceu gestão municipal, a ausência é esperada e não significa \u201ccontas aprovadas\u201d."}
             <a href="https://www.tcmgo.tc.br/site/contas-com-parecer-previo-pela-rejeicao-ou-julgamentos-irregulares/"
             target="_blank" rel="noopener">consulta oficial no TCM-GO</a></p>`;
          })()}
    </section>` : ""}

    ${uf.toUpperCase() === "GO" ? `
    <section class="secao">
      <h2><span class="ico">🏛️</span>Contas no Tribunal de Contas do Estado (TCE-GO)</h2>
      ${f.tcego?.registros?.length ? `
        <p class="fonte-linha">Fonte: <a href="${esc(f.tcego.fonte_url)}" target="_blank"
          rel="noopener">${esc(f.tcego.fonte)}</a> · consulta de ${fdata(f.tcego.gerado_em)}</p>
        <p class="tcu-hit">Consta da relação oficial do TCE-GO (identificação por CPF).</p>
        <table class="bens-tabela">
          <tr><th>Natureza</th><th>Processo</th><th>Acórdão</th><th>Trânsito em julgado</th></tr>
          ${f.tcego.registros.map((r) => `<tr>
            <td>${esc(r.natureza || "")}</td>
            <td>${esc(r.processo || "")}${r.processo_url ? ` <a href="${esc(r.processo_url)}" target="_blank" rel="noopener">(consultar ↗)</a>` : ""}</td>
            <td>${esc(r.acordao || "")}</td><td>${esc(r.transito_em_julgado || "")}</td></tr>`).join("")}
        </table>
        <p class="fonte-linha">A consulta de processos do TCE-GO não aceita link direto (exige verificação anti-robô) — abra a consulta e cole o número.</p>
        <div class="disclaimer">${esc(f.tcego.disclaimer || "")}</div>`
        : `<p class="tcu-ok">✓ Não consta da relação de responsáveis com contas julgadas irregulares do TCE-GO (consulta de ${fdata(f.gerado_em)}).</p>
           <p class="fonte-linha">Atenção ao escopo: essa relação só alcança quem geriu recursos estaduais (secretarias, autarquias, órgãos do estado) — para quem nunca exerceu gestão estadual, a ausência é esperada e não significa \u201ccontas aprovadas\u201d.
             <a href="https://portal.tce.go.gov.br/contas-irregulares"
             target="_blank" rel="noopener">consulta oficial no TCE-GO</a></p>`}
    </section>` : ""}

    ${f.cnia?.registros?.length ? `
    <section class="secao">
      <h2><span class="ico">⚖️</span>Condenações por improbidade administrativa (CNIA/CNJ)</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.cnia.fonte_url)}" target="_blank"
        rel="noopener">${esc(f.cnia.fonte)}</a> · consulta de ${fdata(f.cnia.gerado_em)}</p>
      <table class="bens-tabela">
        <tr><th>Processo</th><th>Órgão</th><th>Trânsito em julgado</th><th>Registro</th></tr>
        ${f.cnia.registros.map((r) => `<tr>
          <td>${esc(r.processo || "")}</td><td>${esc(r.orgao || "")}</td>
          <td>${esc(r.transito_em_julgado || "")}</td><td>${esc(r.pena || "")}</td></tr>`).join("")}
      </table>
      ${f.cnia.registros.some((r) => r.criterio === "nome")
        ? `<p class="fonte-linha">Registro(s) identificados por nome — pode haver homônimo, confira na consulta oficial.</p>` : ""}
      <div class="disclaimer">${esc(f.cnia.disclaimer || "")}</div>
    </section>` : ""}

    ${f.gestao?.blocos?.length ? `
    <section class="secao">
      <h2><span class="ico">🏫</span>Gestão em números</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.gestao.fonte_url)}" target="_blank"
        rel="noopener">${esc(f.gestao.fonte)}</a></p>
      ${f.gestao.blocos.map((b) => `
        <p><b>${esc(b.indicador)}</b> — ${esc(b.cargo)} de ${esc(b.onde)}, mandato ${esc(b.mandato)}
           ${b.baseline ? ` (edição ${b.baseline} como linha de base)` : ""}
           ${/^VICE/i.test(b.cargo || "") ? `<br><span class="fonte-linha">mandato como vice — a gestão e a responsabilidade pelas contas são do titular</span>` : ""}</p>
        <table class="bens-tabela">
          <tr><th>Edição</th><th>${esc(b.onde)} (rede municipal)</th><th>Média das redes municipais do estado</th></tr>
          ${b.pontos.map((p) => `<tr><td>${p.edicao}</td>
            <td class="v">${p.municipio != null ? p.municipio.toLocaleString("pt-BR") : "—"}</td>
            <td class="v">${p.media_estado != null ? p.media_estado.toLocaleString("pt-BR") : "—"}</td></tr>`).join("")}
        </table>`).join("")}
      <div class="disclaimer">${esc(f.gestao.disclaimer || "")}</div>
    </section>` : ""}

    ${f.siconfi?.blocos?.length ? `
    <section class="secao">
      <h2><span class="ico">🏦</span>Finanças do município no mandato</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.siconfi.fonte_url)}" target="_blank"
        rel="noopener">${esc(f.siconfi.fonte)}</a></p>
      ${f.siconfi.blocos.map((b) => `
        <p><b>${esc(b.onde)}</b> — ${esc(b.cargo)}, mandato ${esc(b.mandato)}
          (${b.baseline} como ano-base; valores por habitante, a preços de ${b.ano_precos})
          ${/^VICE/i.test(b.cargo || "") ? `<br><span class="fonte-linha">mandato como vice — a gestão e a responsabilidade pelas contas são do titular</span>` : ""}</p>
        <table class="bens-tabela">
          <tr><th>Ano</th><th>Receita / hab.</th><th>Despesa / hab.</th><th>Investimento / hab.</th><th>População</th></tr>
          ${b.pontos.map((p) => `<tr>
            <td>${p.ano}${p.ano === b.baseline ? " (base)" : ""}</td>
            <td class="v">${p.receita_total_pc_corrigido != null ? brl.format(p.receita_total_pc_corrigido) : "—"}</td>
            <td class="v">${p.despesa_total_pc_corrigido != null ? brl.format(p.despesa_total_pc_corrigido) : "—"}</td>
            <td class="v">${p.investimentos_pc_corrigido != null ? brl.format(p.investimentos_pc_corrigido) : "—"}</td>
            <td class="v">${p.populacao != null ? p.populacao.toLocaleString("pt-BR") : "—"}</td></tr>`).join("")}
        </table>`).join("")}
      <div class="disclaimer">${esc(f.siconfi.disclaimer || "")}</div>
    </section>` : ""}

    ${f.qsa?.empresas?.length ? `
    <section class="secao">
      <h2><span class="ico">🏢</span>Participações em empresas (QSA/Receita Federal)</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.qsa.fonte_url)}" target="_blank"
        rel="noopener">${esc(f.qsa.fonte)}</a> · dados de ${fdata(f.qsa.referencia_dados)} ·
        <a href="${esc(f.qsa.consulta_oficial)}" target="_blank" rel="noopener">consulta oficial de CNPJ</a></p>
      <table class="bens-tabela">
        <tr><th>Empresa</th><th>CNPJ (raiz)</th><th>Qualificação</th><th>Sócio desde</th><th>Cadastros de sanção da empresa</th></tr>
        ${f.qsa.empresas.map((e) => `<tr>
          <td>${esc(e.razao_social || "—")}</td><td>${esc(e.cnpj_basico)}</td>
          <td>${esc(e.qualificacao || "")}</td><td>${esc(e.desde || "")}</td>
          <td>${e.sancoes_da_empresa?.length
            ? e.sancoes_da_empresa.map((s) =>
                `<span class="pill warn">${esc(s.cadastro)}</span> ${esc(s.orgao || "")} ${esc(s.processo || "")} (${esc(s.inicio || "")}${s.fim ? ` a ${esc(s.fim)}` : ""})`).join("<br>")
            : `<span class="tcu-ok">✓ nada consta</span>`}</td></tr>`).join("")}
      </table>
      <div class="disclaimer">${esc(f.qsa.disclaimer || "")}</div>
    </section>` : ""}

    ${f.doacoes_feitas?.disponivel && (f.doacoes_feitas.itens || []).length ? `
    <section class="secao">
      <h2><span class="ico">🤝</span>Doações de campanha que ele fez</h2>
      <p class="fonte-linha">Fonte: prestação de contas eleitorais
        (<a href="https://dadosabertos.tse.jus.br" target="_blank" rel="noopener">dados abertos do TSE</a>),
        eleições de ${(f.doacoes_feitas.anos_cobertos || []).join(" e ")}, cruzadas pelo CPF do doador</p>
      <p>${f.doacoes_feitas.total_terceiros > 0
          ? `Doou <b>${brl.format(f.doacoes_feitas.total_terceiros)}</b> para campanhas de terceiros`
          : "Nenhuma doação a campanhas de terceiros registrada"}${
          f.doacoes_feitas.total_propria > 0
          ? ` · ${brl.format(f.doacoes_feitas.total_propria)} para a própria campanha` : ""}.</p>
      ${f.doacoes_feitas.itens.filter((d) => !d.propria).length ? `
      <table class="bens-tabela">
        <tr><th>Data</th><th>Beneficiado</th><th>Disputa</th><th>Valor</th></tr>
        ${f.doacoes_feitas.itens.filter((d) => !d.propria).map((d) => `<tr>
          <td>${esc(d.data || d.ano)}</td><td>${esc(d.beneficiado)} (${esc(d.partido || "")})</td>
          <td>${esc(d.cargo)}${d.municipio ? ` · ${esc(d.municipio)}` : ""} · ${esc(d.uf)}</td>
          <td class="v">${brl.format(d.valor)}</td></tr>`).join("")}
      </table>` : ""}
      ${f.doacoes_feitas.truncado ? `<p class="meta-busca">+ ${f.doacoes_feitas.truncado} doações não exibidas.</p>` : ""}
      <div class="disclaimer">${esc(f.doacoes_feitas.nota || "")}</div>
    </section>` : ""}

    ${(f.redes_sociais || []).length ? `
    <section class="secao">
      <h2><span class="ico">📱</span>Redes e site oficiais</h2>
      <p class="fonte-linha">Declarados pelo próprio candidato ao TSE no registro da candidatura</p>
      <p>${f.redes_sociais.map((r) =>
        `<a class="pill" style="margin:0 6px 6px 0" href="${esc(r.url)}" target="_blank"
            rel="noopener nofollow">${esc(r.plataforma)} ↗</a>`).join(" ")}</p>
    </section>` : ""}

    ${f.noticias?.itens?.length ? `
    <section class="secao">
      <h2><span class="ico">📰</span>Radar de imprensa</h2>
      <p class="fonte-linha">Menções recentes em veículos jornalísticos estabelecidos
        (<a href="metodologia.html" target="_blank">critério da lista</a>) · busca: ${esc(f.noticias.consulta)}
        · coletado em ${fdata(f.noticias.coletado_em)}</p>
      <ul class="var-lista">
        ${f.noticias.itens.map((n) => `<li style="margin-bottom:8px">
          <a href="${esc(n.url)}" target="_blank" rel="noopener nofollow">${esc(n.titulo)}</a>
          <span style="color:var(--ink-3)"> — ${esc(n.veiculo)}</span></li>`).join("")}
      </ul>
      <div class="disclaimer">${esc(f.noticias.disclaimer || "")}</div>
    </section>` : ""}

    ${f.processos_tse ? `
    <section class="secao">
      <h2><span class="ico">🏛️</span>Processos da candidatura no TSE</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.fontes?.divulgacand)}" target="_blank"
        rel="noopener">DivulgaCandContas/TSE</a> · coletado em ${esc(f.processos_tse.coletado_em)}</p>
      ${f.processos_tse.processos?.length ? `
        <table class="bens-tabela"><tr><th>Processo</th><th>Tipo</th><th>Data</th></tr>
        ${f.processos_tse.processos.map((p) => `<tr><td>${esc(p.processo || p.protocolo || "")}</td>
          <td>${esc(p.tipo || "")}</td><td>${esc(p.data || "")}</td></tr>`).join("")}</table>`
        : `<p class="tcu-ok">✓ Nenhum processo registrado contra a candidatura até a última coleta.</p>`}
      ${f.processos_tse.motivos?.length
        ? `<p><b>Motivos registrados:</b> ${f.processos_tse.motivos.map(esc).join("; ")}</p>` : ""}
    </section>` : ""}

    ${planoHTML}

    ${f.financiamento ? `
    <section class="secao">
      <h2><span class="ico">💸</span>Quem financia (${f.financiamento.ano})</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.financiamento.fonte_url)}" target="_blank"
        rel="noopener">${esc(f.financiamento.fonte)}</a> · consulta de ${fdata(f.financiamento.gerado_em)} ·
        números PARCIAIS durante a campanha</p>
      <p>Receitas declaradas: <b>${brl.format(f.financiamento.receita_total)}</b> ·
         gastos contratados: <b>${brl.format(f.financiamento.despesa_contratada_total)}</b></p>
      ${f.financiamento.origens?.length ? `
      <table class="bens-tabela">
        <tr><th>De onde vem o dinheiro</th><th>Valor</th></tr>
        ${f.financiamento.origens.map((o) => `<tr><td>${esc(o.origem)}</td>
          <td class="v">${brl.format(o.valor)}</td></tr>`).join("")}
      </table>` : ""}
      ${f.financiamento.top_doadores?.length ? `
      <p style="margin-bottom:2px"><b>Maiores doadores</b></p>
      <table class="bens-tabela">
        <tr><th>Doador</th><th>CPF/CNPJ</th><th>Valor</th></tr>
        ${f.financiamento.top_doadores.map((d) => `<tr><td>${esc(d.nome)}</td>
          <td>${esc(d.doc)}</td><td class="v">${brl.format(d.valor)}</td></tr>`).join("")}
      </table>` : ""}
      ${f.financiamento.top_fornecedores?.length ? `
      <p style="margin-bottom:2px"><b>Maiores fornecedores contratados</b></p>
      <table class="bens-tabela">
        <tr><th>Fornecedor</th><th>CPF/CNPJ</th><th>Valor</th><th>Cadastros de sanção</th></tr>
        ${f.financiamento.top_fornecedores.map((fo) => `<tr><td>${esc(fo.nome)}</td>
          <td>${esc(fo.doc)}</td><td class="v">${brl.format(fo.valor)}</td>
          <td>${fo.sancoes_da_empresa?.length
            ? fo.sancoes_da_empresa.map((s) => `<span class="pill warn">${esc(s.cadastro)}</span> ${esc(s.processo || "")}`).join("<br>")
            : `<span class="tcu-ok">✓ nada consta</span>`}</td></tr>`).join("")}
      </table>` : ""}
      <div class="disclaimer">${esc(f.financiamento.disclaimer || "")}</div>
    </section>`
    : secaoEmBreve("💸", "Quem financia",
      "Doadores, fornecedores e fundo eleitoral — a prestação parcial de contas cai no TSE entre 09 e 13/09.")}
    ${f.parlamentar ? `
    <section class="secao">
      <h2><span class="ico">🗳️</span>Atuação como deputado federal (legislatura atual)</h2>
      <p class="fonte-linha">Fonte: <a href="${esc(f.parlamentar.fonte_url)}" target="_blank"
        rel="noopener">Dados Abertos da Câmara dos Deputados</a> · coletado em ${fdata(f.parlamentar.gerado_em)}</p>
      <div class="grade">
        <div class="dado"><div class="rot">Projetos apresentados (2023–2026)</div>
          <div class="val">${f.parlamentar.projetos_total_legislatura}${
            Object.keys(f.parlamentar.projetos_legislatura || {}).length
            ? ` <span style="font-weight:400;color:var(--ink-3)">(${
                Object.entries(f.parlamentar.projetos_legislatura).map(([t, n]) => `${n} ${t}`).join(", ")})</span>` : ""}</div></div>
        <div class="dado"><div class="rot">Propostas que subscreveu (autor/coautor) transformadas em lei — carreira</div>
          <div class="val">${f.parlamentar.normas_sancionadas_carreira}</div></div>
        <div class="dado"><div class="rot">Cota parlamentar (CEAP) na legislatura</div>
          <div class="val">${brl.format(f.parlamentar.ceap_total || 0)}</div></div>
      </div>
      ${Object.keys(f.parlamentar.participacao_votacoes || {}).length ? `
      <table class="bens-tabela">
        <tr><th>Ano</th><th>Votações nominais no Plenário</th><th>Participou</th><th>Participação</th></tr>
        ${Object.entries(f.parlamentar.participacao_votacoes).map(([ano, p]) => `<tr>
          <td>${ano}</td><td class="v">${p.votacoes}</td><td class="v">${p.votou}</td>
          <td class="v">${p.pct.toLocaleString("pt-BR")}%</td></tr>`).join("")}
      </table>` : ""}
      ${Object.keys(f.parlamentar.ceap_por_ano || {}).length ? `
      <p class="fonte-linha">CEAP por ano: ${Object.entries(f.parlamentar.ceap_por_ano)
        .map(([a, v]) => `${a}: ${brl.format(v)}`).join(" · ")}</p>` : ""}
      <div class="disclaimer">${esc(f.parlamentar.nota || "")}</div>
    </section>`
    : secaoEmBreve("🗳️", "Como votou de verdade",
      "Votos nominais na Câmara/Senado, para quem já é parlamentar (Dados Abertos da Câmara e do Senado).")}
    ${f.processos_tse ? "" : secaoEmBreve("🏛️", "Processos da candidatura e judiciais",
      `Impugnações e ações contra a candidatura estão públicas no
       <a href="${esc(f.fontes?.divulgacand)}" target="_blank" rel="noopener">DivulgaCandContas/TSE</a>;
       certidões e consulta ao DataJud/CNJ entram na ficha em breve.`)}

    <p class="fonte-linha" style="margin-top:16px">Ficha gerada em ${fdata(f.gerado_em)} ·
      dados do TSE de ${esc(f.dados_tse_de || "")} · mesma ficha, mesmos campos, mesma ordem para todos.</p>`;

  $("#btn-bens")?.addEventListener("click", (e) => {
    $("#bens").innerHTML =
      `<tr><th>Tipo</th><th>Descrição (como declarado)</th><th>Valor</th></tr>` + bensLinhas(bens.length);
    e.target.remove();
  });

  $("#btn-share")?.addEventListener("click", async () => {
    // compartilha a página estática (tem OG card pro preview no WhatsApp)
    const url = `${location.origin}${BASE}/c/${uf.toLowerCase()}/${sq}.html`;
    const texto = `Raio-X de ${nome} (${f.partido?.sigla}) — ${f.cargo} · dados oficiais do TSE`;
    if (navigator.share) {
      try { await navigator.share({ title: texto, text: texto, url }); return; } catch {}
    }
    window.open(`https://wa.me/?text=${encodeURIComponent(`${texto}\n${url}`)}`, "_blank");
  });

  window.scrollTo({ top: 0 });
}

/* ── comparador (2-3 candidatos, mesmos campos, mesma ordem) ─── */
function _resumoIntegridade(f) {
  const linhas = [];
  const conta = (regs) => (regs && regs.length ? `${regs.length} registro(s)` : null);
  linhas.push(["TCU (contas irregulares)", !f.tcu?.disponivel ? "cruzamento em preparação"
    : (f.tcu.listado ? conta(f.tcu.registros) : "não consta")]);
  linhas.push(["CGU (CEIS/CNEP/CEAF)", !f.sancoes?.disponivel ? "cruzamento em preparação"
    : (conta(f.sancoes.registros) || "nada consta")]);
  linhas.push(["TCM-GO (contas municipais)", conta(f.tcmgo?.registros) || "não consta*"]);
  linhas.push(["TCE-GO (contas estaduais)", conta(f.tcego?.registros) || "não consta*"]);
  if (f.cnia) linhas.push(["CNIA/CNJ (improbidade)", conta(f.cnia.registros) || "não consta"]);
  return linhas;
}

async function telaComparar(uf, sqs) {
  document.title = "Comparar candidatos — Raio-X do Candidato";
  app.innerHTML = `<p class="carregando">Carregando comparação…</p>`;
  let fichas;
  try {
    fichas = await Promise.all(sqs.map((sq) => getJSON(`data/${uf.toUpperCase()}/${sq}.json`)));
  } catch {
    app.innerHTML = `<p class="erro">Não foi possível carregar um dos candidatos.
      <a href="#/${uf}">Voltar à busca</a></p>`;
    return;
  }
  const tot = (f) => f.patrimonio?.serie?.find((p) => p.ano === f.ano && p.declarou)?.total ?? null;
  const mandatos = (f) => (f.historico?.mandatos || [])
    .map((m) => `${esc(m.cargo)} de ${esc(m.onde)} (${m.inicio}–${m.fim})`).join("; ") || "—";
  const linha = (rot, fn) => `<tr><th scope="row">${rot}</th>${fichas.map((f) =>
    `<td>${fn(f)}</td>`).join("")}</tr>`;

  app.innerHTML = `
    <a class="voltar" href="#/${uf}">← voltar à busca</a>
    <h1 class="compara-titulo">Comparação lado a lado</h1>
    <p class="fonte-linha">Mesmos campos, mesma ordem, mesmas fontes oficiais das fichas —
      comparação não é ranking: julgar é papel do eleitor. Clique no nome para a ficha completa.</p>
    <div class="compara-scroll">
    <table class="bens-tabela compara-tabela">
      <tr><th scope="row"></th>${fichas.map((f) => `<td class="compara-cab">
        ${f.foto && fotoURL(uf, f.sq) ? `<img class="compara-foto" src="${fotoURL(uf, f.sq)}" alt="">` : ""}
        <a href="#/${uf}/${f.sq}"><b>${esc(f.nome_urna || f.nome)}</b></a><br>
        ${esc(f.partido?.sigla || "")} · nº ${esc(f.numero || "")}<br>
        <span class="pill ${pillClass(f.situacao?.label)}">${esc(f.situacao?.label)}</span></td>`).join("")}</tr>
      ${linha("Cargo disputado", (f) => esc(f.cargo))}
      ${linha("Idade", (f) => f.idade ? `${f.idade} anos` : "—")}
      ${linha("Escolaridade", (f) => esc(f.instrucao || "—"))}
      ${linha("Ocupação declarada", (f) => esc(f.ocupacao || "—"))}
      ${linha("Patrimônio declarado (2026)", (f) => tot(f) != null ? brl.format(tot(f)) : "não declarado")}
      ${linha("Já concorreu (desde 2014)", (f) => f.historico?.ja_concorreu
        ? `${f.historico.vezes_candidato}× · eleito ${f.historico.vezes_eleito || 0}×` : "estreante")}
      ${linha("Trocas de partido", (f) => f.historico?.ja_concorreu
        ? `${f.historico.trocas_partido || 0}` : "—")}
      ${linha("Mandatos exercidos", mandatos)}
      ${_resumoIntegridade(fichas[0]).map((_, i) =>
        linha(_resumoIntegridade(fichas[0])[i][0],
              (f) => esc(_resumoIntegridade(f)[i]?.[1] ?? "—"))).join("")}
      ${linha("Empresas na Receita (QSA)", (f) => {
        const es = f.qsa?.empresas || [];
        if (!es.length) return "nenhum vínculo confirmado";
        const sanc = es.filter((e) => e.sancoes_da_empresa?.length).length;
        return `${es.length} vínculo(s)` + (sanc ? ` · ${sanc} empresa(s) em cadastro de sanção` : "");
      })}
      ${linha("Doações que fez (2022/2024)", (f) => f.doacoes_feitas?.disponivel
        ? (f.doacoes_feitas.total_terceiros > 0
            ? brl.format(f.doacoes_feitas.total_terceiros) + " a terceiros" : "nenhuma a terceiros")
        : "—")}
    </table>
    </div>
    <p class="fonte-linha">* listas do TCM-GO e do TCE-GO só alcançam quem geriu recursos
      municipais/estaduais em Goiás — para os demais, a ausência é esperada. Datas de consulta
      e fontes de cada dado: ver a ficha individual.</p>
    <p class="fonte-linha">Ficha gerada em ${fdata(fichas[0].gerado_em)} · dados do TSE de
      ${esc(fichas[0].dados_tse_de || "")}</p>`;
  window.scrollTo({ top: 0 });
}

/* ── router ─────────────────────────────────────────────────── */
async function rotear() {
  const partes = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  const uf = (partes[0] || UF_DEFAULT).toLowerCase();
  try {
    if (partes[1] === "comparar" && partes[2]) await telaComparar(uf, partes[2].split(",").slice(0, 3));
    else if (partes.length >= 2) await telaFicha(uf, partes[1]);
    else await telaBusca(uf);
  } catch (e) {
    app.innerHTML = `<p class="erro">Algo deu errado: ${esc(e.message)} — <a href="#/">recarregar</a></p>`;
  }
}
window.addEventListener("hashchange", rotear);
rotear();
