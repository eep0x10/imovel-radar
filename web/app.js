import { animateRadar, clearRadarMotion } from "./motion.js";
import { api, setToken, hasSession, download } from "./api.js";
import {
  esc,
  fieldLabel,
  listingTitle,
  money,
  number,
  date,
  link,
  header,
  field,
  toast,
  score,
  opportunity,
  priceChange,
  photo,
  card,
  stages,
  busy,
  confidence,
} from "./ui.js";
const main = document.querySelector("#main"),
  dialog = document.querySelector("#detail");
const state = {
  user: null,
  profile: {},
  compare: new Set(),
  sourceResults: {},
  searchJob: null,
  q: "",
  sort: "fit",
  construction: "all",
  tab: "all",
  apply: true,
  settingsTab: "account",
  unread: 0,
  unreadOnly: false,
  notificationPages: 1,
  page: 1,
};
const nav = [
  ["radar", "◉", "Radar"],
  ["budget", "▤", "Planejar a compra"],
  ["settings", "⚙", "Configurações"],
  ["alerts", "◎", "Notificações"],
];
let lastPage = null,
  lastHtml = null,
  rendering = 0,
  searchTimer;
const dirtyForms = new WeakSet();
function editingControl() {
  return (
    main.contains(document.activeElement) &&
    document.activeElement.matches(
      'input, textarea, select, [contenteditable="true"]',
    )
  );
}
function safeToSync() {
  return (
    !document.hidden &&
    !dialog.open &&
    !rendering &&
    !loadingMore &&
    !main.querySelector("button:disabled:not([data-page])") &&
    !editingControl() &&
    ![...main.querySelectorAll("form")].some((f) => dirtyForms.has(f))
  );
}
main.addEventListener("input", (e) => {
  const form = e.target.closest("form");
  if (form && form.id !== "search-form" && !e.target.matches("[data-compare]"))
    dirtyForms.add(form);
});
main.addEventListener("change", (e) => {
  const form = e.target.closest("form");
  if (form && form.id !== "search-form" && !e.target.matches("[data-compare]"))
    dirtyForms.add(form);
});
let flushProfile = null,
  cancelProfile = null;
let radarQuery = "",
  radarLoaded = 0,
  radarTotal = 0,
  radarObserver = null,
  loadingMore = false;
let detailVersion = 0;
let renderVersion = 0,
  lastDetailFocus = null;
function navigation() {
  document.querySelector("#nav").innerHTML = state.user
    ? nav
        .map(
          ([id, icon, title]) =>
            `<a href="#${id}" ${(location.hash.slice(1) || "radar") === id ? 'aria-current="page"' : ""} class="${(location.hash.slice(1) || "radar") === id ? "active" : ""}"><span class="nav-icon">${icon}</span>${title}${id === "alerts" ? ` <span class="notification-count">${state.unread || ""}</span>` : ""}</a>`,
        )
        .join("")
    : "";
  document.querySelector("#identity").textContent = state.user?.name || "";
  document.querySelector("#logout").hidden = !state.user;
}
async function render({ background = false } = {}) {
  if (background && !safeToSync()) return;
  const v = ++renderVersion;
  let page = location.hash.slice(1) || "radar";
  if (["profile", "sources", "compare", "journey"].includes(page)) {
    if (page === "journey") state.tab = "saved";
    if (page === "sources") state.settingsTab = "sources";
    const compareRequested = page === "compare";
    page = page === "sources" ? "settings" : "radar";
    history.replaceState(null, "", `#${page}`);
    if (compareRequested) setTimeout(openComparison, 0);
  }
  const samePage = lastPage === page && !!state.user;
  if (!background) navigation();
  if (!state.user) return auth();
  rendering++;
  if (!samePage)
    main.innerHTML =
      '<div class="panel" role="status">Carregando seus dados…</div>';
  main.setAttribute("aria-busy", "true");
  try {
    const html = await (
      { radar, journey, budget, settings, alerts }[page] || radar
    )();
    if (v !== renderVersion) return;
    // A user may begin editing while the request is in flight.
    if (
      background &&
      (dialog.open ||
        editingControl() ||
        [...main.querySelectorAll("form")].some((f) => dirtyForms.has(f)))
    )
      return;
    if (samePage && html === lastHtml) {
      document.querySelector("#live-status").textContent = "Dados atualizados";
      return;
    }
    const retainedProfile = samePage
      ? main.querySelector("#profile-form")
      : null;
    const search = samePage ? main.querySelector("#search-form") : null;
    const focused =
      search?.contains(document.activeElement) ||
      retainedProfile?.contains(document.activeElement)
        ? document.activeElement
        : null;
    const selection =
      focused && focused.selectionStart != null
        ? [focused.selectionStart, focused.selectionEnd]
        : null;
    const scroll = [window.scrollX, window.scrollY];
    clearRadarMotion();
    main.innerHTML = html;
    if (retainedProfile && main.querySelector("#profile-form"))
      main.querySelector("#profile-form").replaceWith(retainedProfile);
    if (search && main.querySelector("#search-form"))
      main.querySelector("#search-form").replaceWith(search);
    lastPage = page;
    lastHtml = html;
    bind();
    if (page === "radar" && !background) animateRadar(main);
    updateComparisonSelection();
    if (focused) {
      focused.focus({ preventScroll: true });
      if (selection) focused.setSelectionRange(...selection);
    }
    if (samePage) window.scrollTo(...scroll);
    document.querySelector("#live-status").textContent = "Dados atualizados";
  } catch (e) {
    if (v !== renderVersion || !state.user) return;
    if (samePage) {
      document.querySelector("#live-status").textContent =
        "Sem conexão. Dados anteriores preservados; nova tentativa automática.";
      if (!background) toast(e.message);
      return;
    }
    main.innerHTML =
      header(
        "Não foi possível carregar.",
        "Seus dados salvos permanecem preservados.",
      ) +
      `<div class="panel" role="alert">${esc(e.message)}<p><button data-retry>Tentar novamente</button></p></div>`;
    main.querySelector("[data-retry]").onclick = () => render();
  } finally {
    rendering--;
    if (v === renderVersion) main.removeAttribute("aria-busy");
  }
}

function auth(register = false) {
  main.innerHTML =
    header(
      register ? "Comece sua busca." : "Seu próximo lar começa aqui.",
      "Sua conta organiza anúncios, preferências e histórico de decisão.",
    ) +
    `<form id="auth" class="panel auth-panel">${register ? field("name", "Seu nome", "", "text", 'required maxlength="100"') : ""}${field("email", "E-mail", "", "email", 'required autocomplete="email"')}${field("password", "Senha (mínimo 8 caracteres)", "", "password", `required minlength="8" autocomplete="${register ? "new-password" : "current-password"}"`)}<p id="auth-error" role="alert"></p><div class="form-actions"><button class="primary">${register ? "Criar conta" : "Entrar"}</button><button type="button" id="switch-auth">${register ? "Já tenho conta" : "Criar minha conta"}</button></div></form>`;
  document.querySelector("#switch-auth").onclick = () => auth(!register);
  document.querySelector("#auth").onsubmit = async (e) => {
    e.preventDefault();
    const b = e.submitter;
    b.disabled = true;
    try {
      const response = await api(`/auth/${register ? "register" : "login"}`, {
        method: "POST",
        body: Object.fromEntries(new FormData(e.target)),
      });
      setToken(response.token);
      state.user = response.user;
      state.profile = await api("/profile");
      await render();
    } catch (error) {
      document.querySelector("#auth-error").textContent = error.message;
    } finally {
      b.disabled = false;
    }
  };
}
async function radar() {
  const requestVersion = renderVersion;
  const params = new URLSearchParams({
    q: state.q,
    sort: state.sort,
    construction: state.construction,
    saved: state.tab === "saved",
    apply_profile: state.apply,
    page: 1,
    page_size: 20,
  });
  const query = params.toString();
  const r = await api(`/properties?${params}`),
    s = r.summary || {};
  // Refresh all already-visible rows without dropping the user's scroll position.
  for (let page = 2; page <= state.page && r.items.length < r.total; page++) {
    params.set("page", page);
    const next = await api(`/properties?${params}`);
    r.items.push(...next.items);
    if (!next.items.length) break;
  }
  if (requestVersion !== renderVersion) return "";
  radarQuery = query;
  radarLoaded = r.items.length;
  radarTotal = r.total;
  return (
    header(
      "Seu próximo lar começa aqui.",
      "Acompanhe oportunidades. Decida com evidências.",
      "<button data-refresh>Pesquisar nas fontes</button>",
    ) +
    `<section class="stats">${[
      ["NO SEU RADAR", s.total],
      ["NOVOS ENDEREÇOS", s.new],
      ["PREÇO CAIU", s.price_drops],
      ["SUA LISTA", s.saved],
    ]
      .map(
        ([label, value]) =>
          `<div class="stat"><span class="stat-head">${label}</span><b>${value || 0}</b></div>`,
      )
      .join(
        "",
      )}</section>${await profile()}<div id="search-progress" role="status" aria-live="polite">${searchProgress()}</div><div class="radar-actions"><button class="primary" data-create-alert>Criar alerta desta busca</button><span class="small">Edite os filtros para ver os dados já coletados. Pesquisar nas fontes busca novos anúncios com esses critérios.</span></div>${state.compare.size ? `<div class="comparison-tray"><b>${state.compare.size} de 4 imóveis selecionados</b><button data-open-compare>Abrir comparador →</button></div>` : ""}<div class="radar-grid"><section><div class="tabs">${[
      ["all", "Todos"],
      ["saved", "Salvos"],
    ]
      .map(
        ([id, label]) =>
          `<button class="tab ${state.tab === id ? "active" : ""}" data-tab="${id}">${label}</button>`,
      )
      .join(
        "",
      )}</div><form id="search-form" class="filter-line"><input name="q" type="search" aria-label="Buscar imóvel, bairro ou fonte" placeholder="Filtrar resultados por bairro, título ou fonte…" value="${esc(state.q)}"><select name="sort" aria-label="Ordenar">${[
      ["fit", "Maior aderência"],
      ["price", "Menor preço"],
      ["price_m2", "Menor preço por m²"],
      ["opportunity", "Melhor oportunidade"],
    ]
      .map(
        ([id, label]) =>
          `<option value="${id}" ${state.sort === id ? "selected" : ""}>${label}</option>`,
      )
      .join(
        "",
      )}</select><select name="construction" aria-label="Fase do imóvel">${[
      ["all", "Todas as fases"],
      ["under_construction", "Na planta / em construção"],
      ["ready", "Pronto"],
    ]
      .map(
        ([id, label]) =>
          `<option value="${id}" ${state.construction === id ? "selected" : ""}>${label}</option>`,
      )
      .join(
        "",
      )}</select><button>Pesquisar nas fontes</button></form><p class="small">Sem indicação de planta ou obra, o imóvel é classificado como pronto. Confirme a fase no anúncio.</p><label class="small"><input id="apply-profile" type="checkbox" ${state.apply ? "checked" : ""}> Aplicar minha busca</label><p class="listing-count">${r.total} imóveis encontrados entre ${r.summary.total} coletados · atualização: ${date(r.last_updated)}</p><div id="radar-list">${r.items.length ? r.items.map((p) => card(p, state.compare)).join("") : `<div class="empty"><h3>${state.q || state.apply || state.tab !== "all" || state.construction !== "all" ? "Nenhum imóvel nesses filtros" : "Seu radar está pronto para começar"}</h3><p>${state.q || state.apply || state.tab !== "all" || state.construction !== "all" ? "Nenhum anúncio já coletado corresponde a todos os filtros. Consulte as fontes com os critérios atuais ou revise limites de área, quartos, despesas e regiões geográficas." : "Configure a coleta dos portais em Fontes e atualização para trazer anúncios reais ao radar. Você também pode importar um arquivo ou conectar um feed."}</p><a href="#settings" data-settings-link="sources">Configurar coleta e fontes →</a><p><button data-reset>Limpar filtros</button></p></div>`}</div><div id="radar-more" class="pagination" aria-live="polite">${radarLoaded < radarTotal ? '<button type="button" data-load-more>Carregar mais imóveis</button>' : "<span>Todos os imóveis desta busca foram exibidos.</span>"}</div></section><aside class="rail"><div class="daily"><p class="eyebrow">SUA DECISÃO, COM CONTEXTO</p><h2>Preço bom precisa de evidência.</h2><p>Avaliação de qualidade, aderência pessoal e preço relativo são medidas diferentes. Poucos comparáveis? A estimativa fica pendente.</p><a href="#alerts">Ver notificações →</a></div><div class="subtle">Anúncios importados não se atualizam sozinhos. Em Fontes e atualização, confira quais coletas estão ativas, suas falhas e a saúde da rotina diária.</div></aside></div>`
  );
}
async function detail(id) {
  dialog.dataset.mode = "detail";
  const requestVersion = ++detailVersion;
  if (!dialog.open) lastDetailFocus = document.activeElement;
  const p = await api(`/properties/${id}`),
    e = p.evaluation || {};
  if (requestVersion !== detailVersion || !state.user) return;
  document.querySelector("#detail-content").innerHTML =
    `<div class="dialog-header"><div><p class="eyebrow">DOSSIÊ DO IMÓVEL</p><h2>${esc(listingTitle(p))}</h2></div><button data-close aria-label="Fechar dossiê">×</button></div><div class="detail-grid"><div>${photo(p)}${!p.observed_at ? '<span class="tag amber">Data não confirmada</span>' : ""}<p>${esc(p.address)} · ${esc(p.neighborhood)} · ${esc(p.city)}</p><div class="features">${[
      ["Área", `${number(p.area)} m²`],
      ["Quartos", number(p.bedrooms)],
      [
        "Fase do imóvel",
        {
          off_plan: "Na planta",
          under_construction: "Na planta / em construção",
          ready: "Pronto",
          unknown: "Não informada",
        }[p.construction_status] || "Não informada",
      ],
      ["Vagas", number(p.parking)],
      [
        "Andar",
        p.floor != null
          ? number(p.floor)
          : p.floor_min_reported != null && p.floor_max_reported != null
            ? `${number(p.floor_min_reported)}–${number(p.floor_max_reported)} (faixa da fonte)`
            : "Não informado",
      ],
      ...(p.occupied != null
        ? [["Ocupação", p.occupied ? "Ocupado" : "Desocupado"]]
        : []),
      [
        "Elevador",
        p.elevator == null ? "Não informado" : p.elevator ? "Sim" : "Não",
      ],
    ]
      .map(([l, v]) => `<span>${l}: ${v}</span>`)
      .join(
        "",
      )}</div><section class="panel"><h3>Histórico de preço</h3><div class="timeline">${(p.history || []).map((h) => `<div><span>Observado: ${date(h.observed_at)}<br>Registrado: ${date(h.recorded_at)}</span><b>${money(h.price)}</b></div>`).join("") || "<p>Ainda sem histórico.</p>"}</div></section><section class="panel"><h3>Dados pendentes</h3><ul>${[...(e.missing || []), ...(e.pending_requirements || [])].map((m) => `<li>${esc(fieldLabel(m))}</li>`).join("") || "<li>Nenhuma pendência identificada pelo modelo. Confirme na visita.</li>"}</ul></section><section class="panel"><h3>Origem e atualização</h3><p>Observado: ${date(p.observed_at)} · importado: ${date(p.imported_at || p.first_seen)}</p>${(p.source_links || [{ source: p.source, url: p.url }]).map((s) => `<p>${link(s.url, s.source)}</p>`).join("")}<details><summary>Origem por campo</summary><ul>${Object.entries(
      p.provenance || {},
    )
      .map(
        ([k, v]) =>
          `<li>${esc(fieldLabel(k))}: ${esc(v.source)} · ${date(v.observed_at)}</li>`,
      )
      .join(
        "",
      )}</ul></details>${p.latitude != null && p.longitude != null ? link(`https://www.openstreetmap.org/?mlat=${encodeURIComponent(p.latitude)}&mlon=${encodeURIComponent(p.longitude)}#map=17/${encodeURIComponent(p.latitude)}/${encodeURIComponent(p.longitude)}`, "Ver localização informada no mapa") : ""}</section></div><div><div class="price">${money(p.price)}</div>${priceChange(p)}<p>${money(p.price / p.area)}/m²</p>${p.combined_monthly_cost != null ? `<div class="check-row"><span>Condomínio + IPTU combinados (origem)</span><b>${money(p.combined_monthly_cost)}${p.combined_cost_period === "unknown" ? " · período a confirmar" : "/mês"}</b></div><p class="small">Total informado pela fonte; componentes e periodicidade do IPTU não confirmados.</p>` : ""}<div class="check-row"><span>Condomínio mensal</span><b>${money(p.condo_fee)}</b></div><div class="check-row"><span>IPTU (${esc({ annual: "anual", monthly: "mensal", unknown: "periodicidade desconhecida" }[p.tax_period] || "não informado")})</span><b>${money(p.property_tax)}</b></div><section class="panel"><h2>${opportunity(e)}</h2><p>${e.comparables_count || 0} comparáveis · confiança ${confidence(e.confidence)}</p><p>Referência: ${money(e.benchmark_m2)}/m². Preços de anúncios, não de transações.</p><details><summary>Ver comparáveis usados</summary>${(e.comparables || []).map((c) => `<p><button data-detail="${c.id}">Imóvel ${c.id}</button> ${money(c.price)} · ${number(c.area)} m² · ${money(c.price_m2)}/m²</p>`).join("") || "<p>Amostra insuficiente.</p>"}</details></section><section class="panel"><h3>Aderência ${score(e.fit_score)}</h3><p>Qualidade observável ${score(e.quality_score)}</p>${e.quality_coverage != null ? `<p>Cobertura da qualidade: ${number(e.quality_coverage)}% dos fatores conhecidos.</p>` : ""}${e.fit_coverage != null ? `<p>Cobertura da aderência: ${number(e.fit_coverage)}% dos requisitos conhecidos.</p>` : ""}<p>${e.eligible ? "Atende aos requisitos conhecidos." : "Não atende a todos os requisitos da sua busca."}</p><ul>${(e.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul><details><summary>Fatores e pesos</summary>${[...(e.fit_factors || []), ...(e.quality_factors || [])].map((f) => `<div class="check-row"><span>${esc(f.label)}</span><b>${esc(f.score ?? f.value ?? "Pendente")} · peso ${number(f.weight)}</b></div>`).join("")}<p>Versão: ${esc(e.score_version)}</p></details></section><button class="primary" data-save="${id}" data-saved="${!!p.saved}">${p.saved ? "Remover dos salvos" : "Salvar imóvel"}</button></div></div>`;
  if (!dialog.open) dialog.showModal();
  bind(dialog);
  dialog.querySelector("[data-close]").focus();
}
async function comparison() {
  const items = await Promise.all(
    [...state.compare].map((id) => api(`/properties/${id}`)),
  );
  return (
    header(
      "Lado a lado, sem perder contexto.",
      "Compare até quatro imóveis selecionados no radar.",
    ) +
    (items.length
      ? `<div class="table-wrap"><table><caption>Valores desconhecidos permanecem pendentes.</caption><thead><tr><th>Critério</th>${items.map((p) => `<th>${esc(listingTitle(p))}<p><button data-uncompare="${p.id}">Remover</button></p></th>`).join("")}</tr></thead><tbody>${[
          ["Preço", (p) => money(p.price)],
          ["Área", (p) => `${number(p.area)} m²`],
          ["Preço por m²", (p) => money(p.price / p.area)],
          [
            "Condomínio + IPTU combinados (origem)",
            (p) =>
              p.combined_monthly_cost == null
                ? money(null)
                : `${money(p.combined_monthly_cost)}${p.combined_cost_period === "unknown" ? " · período a confirmar" : "/mês"}`,
          ],
          ["Condomínio", (p) => money(p.condo_fee)],
          [
            "IPTU / período",
            (p) =>
              `${money(p.property_tax)} / ${esc(p.tax_period || "desconhecido")}`,
          ],
          ["Aderência", (p) => score(p.evaluation?.fit_score)],
          ["Qualidade", (p) => score(p.evaluation?.quality_score)],
          ["Oportunidade", (p) => opportunity(p.evaluation)],
          ["Quartos", (p) => number(p.bedrooms)],
          ["Vagas", (p) => number(p.parking)],
          [
            "Andar",
            (p) =>
              p.floor != null
                ? number(p.floor)
                : p.floor_min_reported != null && p.floor_max_reported != null
                  ? `${number(p.floor_min_reported)}–${number(p.floor_max_reported)}`
                  : "Não informado",
          ],
          [
            "Ocupação",
            (p) =>
              p.occupied == null
                ? "Não informada"
                : p.occupied
                  ? "Ocupado"
                  : "Desocupado",
          ],
          ["Metrô a pé", (p) => `${number(p.metro_minutes)} min`],
          [
            "Observado",
            (p) =>
              p.observed_at ? date(p.observed_at) : "Data não confirmada",
          ],
          [
            "Detalhes",
            (p) => `<button data-detail="${p.id}">Abrir dossiê</button>`,
          ],
        ]
          .map(
            ([label, fn]) =>
              `<tr><th>${label}</th>${items.map((p) => `<td>${fn(p)}</td>`).join("")}</tr>`,
          )
          .join("")}</tbody></table></div>`
      : '<div class="empty"><h3>Escolha imóveis no radar</h3><a href="#radar">Voltar ao radar →</a></div>')
  );
}
const assessmentFields = [
  [
    "condition",
    "Conservação",
    [
      ["unknown", "Não avaliado"],
      ["good", "Bom estado"],
      ["needs_work", "Precisa de reforma"],
    ],
  ],
  [
    "sunlight",
    "Luz natural",
    [
      ["unknown", "Não avaliado"],
      ["good", "Boa"],
      ["poor", "Ruim"],
    ],
  ],
  [
    "ventilation",
    "Ventilação",
    [
      ["unknown", "Não avaliado"],
      ["good", "Boa"],
      ["poor", "Ruim"],
    ],
  ],
  [
    "documentation",
    "Documentação",
    [
      ["unknown", "Não avaliada"],
      ["pending", "Pendências identificadas"],
      ["verified", "Conferida"],
    ],
  ],
];
function assessmentForm(p) {
  return `<details class="visit-assessment"><summary>Sua avaliação da visita</summary><p>Informações registradas por você, preservadas nas atualizações da fonte. Marque documentação como conferida somente após verificar os documentos.</p>${assessmentFields.map(([key, label, options]) => `<label class="form-field">${label}<select name="assessment_${key}">${options.map(([value, text]) => `<option value="${value}" ${(p.assessments?.[key] || "unknown") === value ? "selected" : ""}>${text}</option>`).join("")}</select></label>`).join("")}</details>`;
}
async function journey() {
  const r = await api("/properties?saved=true&page_size=100");
  for (let page = 2; r.items.length < r.total; page++) {
    const next = await api(`/properties?saved=true&page_size=100&page=${page}`);
    if (!next.items.length) break;
    r.items.push(...next.items);
  }
  return (
    header(
      "Da descoberta à sua chave.",
      "Salve visitas, pendências e impressões na sua conta.",
    ) +
    `<div class="board">${
      r.items
        .map(
          (p) =>
            `<form class="journey-card" data-tracking="${p.id}"><h3>${esc(listingTitle(p))}</h3><p>${money(p.price)} · ${esc(p.neighborhood)}</p><div class="form-actions"><button type="button" class="text-button" data-detail="${p.id}">Abrir dossiê ↗</button><label><input type="checkbox" data-compare="${p.id}" ${state.compare.has(p.id) ? "checked" : ""}> Comparar</label><button type="button" data-save="${p.id}" data-saved="true">Remover dos favoritos</button></div><label>Etapa<select name="stage">${Object.entries(
              stages,
            )
              .map(
                ([v, l]) =>
                  `<option value="${v}" ${(p.stage || "saved") === v ? "selected" : ""}>${l}</option>`,
              )
              .join(
                "",
              )}</select></label><label>Visita marcada<input type="datetime-local" name="visit_at" value="${p.visit_at ? esc(new Date(new Date(p.visit_at).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)) : ""}"></label><label>Notas<textarea name="notes" maxlength="10000" placeholder="Luz, ruído, estado do prédio, negociação…">${esc(p.notes)}</textarea></label><div class="checks">${p.search_bounds?.length ? `<label><input type="checkbox" name="use_bounds" checked> Restringir às ${p.search_bounds.length} regiões geográficas antigas da conta (desmarque para buscar em toda São Paulo)</label>` : ""}${[
              ["documents", "Documentação conferida"],
              ["structure", "Estrutura e instalações avaliadas"],
              ["neighborhood", "Vizinhança visitada"],
              ["costs", "Custos totais confirmados"],
            ]
              .map(
                ([k, l]) =>
                  `<label><input name="check_${k}" type="checkbox" ${p.checklist?.[k] ? "checked" : ""}>${l}</label>`,
              )
              .join(
                "",
              )}</div>${assessmentForm(p)}<button class="primary">Salvar acompanhamento</button></form>`,
        )
        .join("") ||
      '<div class="empty"><h3>Sua jornada começa com um favorito</h3><a href="#radar">Explorar radar →</a></div>'
    }</div>`
  );
}
function activeCriteria(p) {
  return [
    p.area_min != null ? `Área a partir de ${p.area_min} m²` : null,
    p.area_max != null ? `máximo ${p.area_max} m²` : "sem área máxima",
    p.bedrooms_min ? `${p.bedrooms_min}+ quartos` : null,
    p.parking_min ? `${p.parking_min}+ vagas` : null,
    p.floor_min != null ? `andar ${p.floor_min}+` : null,
    p.monthly_max != null
      ? `condomínio + IPTU até ${money(p.monthly_max)}`
      : null,
    p.metro_max != null ? `metrô até ${p.metro_max} min` : null,
    p.search_bounds?.length
      ? `${p.search_bounds.length} regiões geográficas restritas`
      : null,
    p.require_elevator ? "elevador obrigatório" : null,
    p.exclude_unknown_required ? "dados desconhecidos excluídos" : null,
  ]
    .filter(Boolean)
    .join(" · ");
}
function searchProgress() {
  const job = state.searchJob;
  if (!job)
    return '<p class="small">A lista contém anúncios já coletados. Use Pesquisar nas fontes para consultar os portais agora.</p>';
  return `<section class="subtle"><strong>${esc(job.message || job.state)}</strong><p>${job.completed || 0} de ${job.total || 0} fontes${job.next_profile ? " · Nova busca agendada após esta" : ""} · ${esc(activeCriteria(job.profile || {}))}</p>${(job.sources || []).map((source) => `<p><b>${esc(source.name)}</b> · ${esc({ pending: "Aguardando", running: "Consultando", complete: "Concluída", partial: "Coleta parcial", error: "Falha" }[source.state] || "Aguardando")}${source.message ? ` — ${esc(source.message)}` : ""}${source.created != null ? ` · ${source.created} novos` : ""}${source.updated != null ? ` · ${source.updated} atualizados` : ""}${source.coverage?.pages != null ? ` · ${source.coverage.pages} páginas` : ""}</p>`).join("")}</section>`;
}
let pollingSearch = false,
  searchNeedsRender = false,
  accountEpoch = 0;
async function pollSourceSearch() {
  if (!state.user || pollingSearch) return;
  pollingSearch = true;
  const epoch = accountEpoch;
  try {
    const old = JSON.stringify(state.searchJob);
    const incoming = await api("/search");
    if (epoch !== accountEpoch) return;
    state.searchJob = incoming;
    const progress = document.querySelector("#search-progress");
    if (progress) progress.innerHTML = searchProgress();
    if (old !== JSON.stringify(state.searchJob)) searchNeedsRender = true;
    if (searchNeedsRender && safeToSync()) {
      await render({ background: true });
      searchNeedsRender = false;
    }
  } catch (error) {
    if (epoch !== accountEpoch) return;
    const progress = document.querySelector("#search-progress");
    if (progress)
      progress.textContent = `Não foi possível consultar a coleta: ${error.message}`;
  } finally {
    pollingSearch = false;
  }
}
async function startSourceSearch() {
  const epoch = accountEpoch;
  if (flushProfile && !(await flushProfile())) {
    toast("Corrija os filtros antes de pesquisar. A coleta não foi iniciada.");
    return;
  }
  const incoming = await api("/search", {
    method: "POST",
    body: state.profile,
  });
  if (epoch !== accountEpoch) return;
  state.searchJob = incoming;
  state.apply = true;
  toast(
    state.searchJob.queued
      ? "Novos filtros agendados. A próxima coleta começará após a atual."
      : state.searchJob.reused
        ? "Já existe uma pesquisa em andamento. Os critérios dessa coleta aparecem no progresso."
        : "Pesquisa iniciada. Os resultados aparecerão conforme cada fonte responder.",
  );
  await render();
}
setInterval(() => {
  if (!document.hidden) pollSourceSearch();
}, 5000);

async function profile() {
  const p = state.profile;
  const numeric = (items) =>
    items
      .map(([key, label]) =>
        field(key, label, p[key] ?? "", "number", 'min="0" step="any"'),
      )
      .join("");
  return `<form id="profile-form" class="radar-filters panel"><h2>Filtros da sua busca</h2><p>Área mínima e máxima definem um intervalo. Para buscar a partir de 70 m², use mínima 70 e deixe a máxima vazia. Os critérios avançados também restringem os resultados.</p><div class="filter-fields">${numeric(
    [
      ["budget_min", "Preço mínimo (R$)"],
      ["budget_max", "Preço máximo (R$)"],
      ["area_min", "Área mínima (m²)"],
      ["area_max", "Área máxima (m²)"],
      ["bedrooms_min", "Quartos mínimos"],
    ],
  )}${field("neighborhoods", "Bairros (separados por vírgula)", (p.neighborhoods || []).join(", "))}</div><p class="small" data-active-criteria>${esc(activeCriteria(p))}</p><details><summary>Localização e critérios avançados</summary><div class="filter-fields">${field("name", "Nome da busca", p.name)}${field("cities", "Cidades (separadas por vírgula)", (p.cities || []).join(", "))}${numeric(
    [
      ["parking_min", "Vagas mínimas"],
      ["bathrooms_min", "Banheiros mínimos"],
      ["floor_min", "Andar mínimo"],
      ["metro_max", "Metrô a pé: máximo (min)"],
      ["monthly_max", "Condomínio + IPTU máximo (R$)"],
    ],
  )}${field("metro_stations", "Estações preferidas (separadas por vírgula)", (p.metro_stations || []).join(", "))}${["price", "location", "quality"].map((k) => field(`weight_${k}`, `Peso: ${{ price: "Preço", location: "Localização", quality: "Qualidade" }[k]}`, p.weights?.[k] ?? 0, "number", 'min="0" max="100" required')).join("")}${field("alert_drop_percent", "Queda de preço mínima (%)", p.alert_drop_percent ?? 5, "number", 'min="0" max="100" required')}</div><div class="checks">${p.search_bounds?.length ? `<label><input type="checkbox" name="use_bounds" checked> Restringir às ${p.search_bounds.length} regiões geográficas antigas da conta (desmarque para buscar em toda São Paulo)</label>` : ""}${[
    ["exclude_occupied", "Excluir imóveis ocupados"],
    ["require_elevator", "Elevador obrigatório"],
    ["exclude_unknown_required", "Excluir requisitos desconhecidos"],
  ]
    .map(
      ([k, l]) =>
        `<label><input type="checkbox" name="${k}" ${p[k] ? "checked" : ""}>${l}</label>`,
    )
    .join(
      "",
    )}</div><p class="small">Limites vazios não restringem a busca. Dados ausentes permanecem pendentes.</p></details><div class="form-actions"><p id="profile-save-status" role="status" aria-live="polite">Filtros salvos automaticamente na lista local. Clique em Pesquisar nas fontes para atualizar a coleta.</p><button>Salvar agora</button></div></form>`;
}
async function budget() {
  return (
    header(
      "A compra vai além do anúncio.",
      "Simule parcelas e caixa inicial usando suas próprias hipóteses.",
    ) +
    `<div class="form-grid"><form id="budget-form" class="panel">${[
      ["price", "Preço do imóvel", state.profile.budget_max || 330000],
      ["down_payment", "Entrada", 66000],
      ["annual_rate", "Taxa anual efetiva (%)", 10],
      ["months", "Prazo em meses", 360],
      ["monthly_costs", "Custos mensais adicionais", 580],
      ["acquisition_costs", "Despesas de aquisição", 0],
      ["reserve", "Reserva após a compra", 0],
    ]
      .map(([k, l, v]) =>
        field(
          k,
          l,
          v,
          "number",
          `min="${k === "months" ? 1 : 0}" step="any" required`,
        ),
      )
      .join(
        "",
      )}<div class="form-field"><label for="model">Sistema</label><select id="model" name="model"><option value="sac">SAC</option><option value="price">Price</option></select></div><p>Informe custos de cartório, tributos, seguros e tarifas aplicáveis. Os valores iniciais são hipóteses editáveis, não uma oferta de crédito.</p><button class="primary">Calcular simulação</button></form><div id="budget-result" class="budget-result"><h2>Quanto cabe no seu plano?</h2><p>Preencha as hipóteses para ver parcelas, juros e reserva necessária.</p></div></div>`
  );
}
function collectionSummary(result) {
  if (!result) return "";
  const coverage = result.summary?.coverage || result.coverage;
  const warnings = result.warnings || result.summary?.warnings || [];
  return `${coverage ? `<div class="subtle"><b>${coverage.complete ? "Busca consultada até o fim" : "Coleta parcial"}</b><p>${number(coverage.pages)} páginas consultadas${coverage.total_reported != null ? ` · ${number(coverage.total_reported)} anúncios informados pela fonte` : ""}.</p>${coverage.reason ? `<p>${esc({ exhausted: "Todas as páginas retornadas para os critérios consultados foram lidas.", page_limit: "Limite de páginas atingido.", run_page_limit: "Limite desta coleta atingido.", time_limit: "Limite de tempo atingido.", repeated_page: "A fonte repetiu uma página.", error: "A fonte apresentou uma falha.", empty_page_before_total: "A fonte retornou uma página vazia antes do total informado.", empty_page_unverified: "A fonte retornou uma página vazia sem confirmar o total." }[coverage.reason] || "Consulte os avisos da coleta.")}</p>` : ""}</div>` : ""}${warnings.map((w) => `<p class="small">${esc(w)}</p>`).join("")}`;
}
function portalCatalog(r) {
  if (!r.catalog?.length) return "";
  return `<section class="portal-catalog"><h2>Coletar anúncios dos portais</h2><p class="subtitle">A coleta usa sua busca salva. Ajuste orçamento, localização e características em <a href="#radar">Minha busca</a>.</p><div class="source-grid">${r.catalog
    .map((p) => {
      const existing = r.items.find(
        (s) =>
          s.kind === "portal" &&
          s.id != null &&
          (s.portal === p.portal || s.name === p.name),
      );
      return `<article class="panel"><h3>${esc(p.name)}</h3><p>${link(p.url, "Abrir portal")}</p>${existing ? "<p>Fonte já configurada. Use os controles de coleta abaixo.</p>" : p.supported && p.portal ? `<button class="primary" data-portal="${esc(p.portal)}">Ativar e coletar anúncios</button>` : `<p>${esc(p.message || "Coleta ainda não disponível. Você pode importar um arquivo desta fonte.")}</p>`}</article>`;
    })
    .join("")}</div></section>`;
}
function walkingIntegrationStatus(status) {
  const integration = status.integrations?.google_maps;
  if (!integration) return "";
  const labels = {
    not_configured: "Não configurado",
    ready: "Configurado",
    billing_required: "Faturamento necessário",
    access_denied: "Acesso não autorizado pelo serviço",
    quota_exceeded: "Limite de consultas atingido",
    unavailable: "Temporariamente indisponível",
  };
  return `<section class="panel" aria-label="Status de rotas a pé"><h3>Status de rotas a pé</h3><span class="tag ${integration.status === "ready" ? "" : "amber"}">${esc(labels[integration.status] || "Estado não informado")}</span><p>${esc(integration.message || "Aguardando verificação do serviço de rotas.")}</p>${integration.checked_at ? `<p>Última verificação: ${date(integration.checked_at)}</p>` : ""}${integration.retry_after ? `<p>Nova tentativa a partir de: ${date(integration.retry_after)}</p>` : ""}${integration.status === "billing_required" ? `<p>${link("https://console.cloud.google.com/billing", "Abrir faturamento do Google Cloud")}</p>` : ""}</section>`;
}
async function sources() {
  const [r, status] = await Promise.all([api("/sources"), api("/status")]),
    schedule = r.schedule || {};
  return (
    header(
      "Dados bons também têm histórico.",
      "Ative a coleta dos portais, acompanhe sua cobertura ou conecte outras fontes.",
      "<button data-refresh>↻ Coletar fontes ativas</button>",
    ) +
    `<div class="subtle">Rotina diária: ${esc(schedule.hour ?? "não configurada")}h · ${esc(schedule.timezone || "fuso não informado")} · rotina ${schedule.worker_status === "running" ? "ativa" : "offline"} · Último sinal da rotina: ${date(schedule.worker_heartbeat)}. Confira o resultado de cada coleta: uma execução parcial não significa catálogo completo.</div>${walkingIntegrationStatus(status)}${portalCatalog(r)}<div class="form-grid import-area"><section class="panel"><h2>Importar anúncios</h2><p>CSV, JSON ou XLSX. Confira a prévia antes de gravar. Máximo de 10 MB e 5.000 linhas.</p><form id="import-form"><div class="form-field"><label for="import-file">Arquivo de anúncios</label><input id="import-file" type="file" name="file" accept=".csv,.json,.xlsx" required></div><button class="primary">Validar e ver prévia</button><button type="button" data-template>Baixar modelo CSV</button></form>${status.legacy_import_available ? '<p><button type="button" data-legacy-preview>Pré-visualizar planilha local</button></p>' : ""}<div id="import-preview" aria-live="polite" tabindex="-1"></div></section><section class="panel"><h2>Conectar feed</h2><form id="source-form">${field("feed_name", "Nome da fonte", "", "text", 'required maxlength="100"')}${field("feed_url", "URL pública do feed", "", "url", 'required placeholder="https://…"')}<label class="small"><input name="authorized" type="checkbox" required> Tenho autorização para consultar este feed.</label><p>Use feeds JSON/CSV/XML disponibilizados pela fonte. Uma página de busca de portal não é um feed.</p><button class="primary">Adicionar fonte</button></form></section></div><div class="source-grid">${r.items.map((s) => `<article class="panel"><div class="source-logo">${esc(s.name?.[0] || "↻")}</div><h2>${esc(s.name)}</h2><span class="tag ${s.last_success ? "" : "amber"}">${esc({ pending_access: "Acesso pendente", imported: "Dados importados", healthy: "Atualizada", partial: "Coleta parcial", running: "Atualizando", pending: "Aguardando primeira atualização", success: "Atualizada", error: "Falha na atualização", feed: "Feed autorizado", portal: "Portal" }[s.status || s.kind] || s.status || s.kind)}</span><p>${link(s.url, "Abrir fonte")}</p><div class="check-row"><span>Última tentativa</span><b>${date(s.last_attempt)}</b></div><div class="check-row"><span>Último sucesso</span><b>${date(s.last_success)}</b></div><div class="check-row"><span>Registros</span><b>${number(s.record_count)}</b></div>${s.error ? `<p class="error" role="alert">${esc(s.error)}</p>` : ""}${collectionSummary(state.sourceResults[s.id] || s.last_result || s.summary)}${s.authorized || (s.kind === "portal" && s.id != null) ? `<div class="form-actions"><button data-source-refresh="${esc(s.id)}">Atualizar agora</button><button data-source-toggle="${esc(s.id)}" data-enabled="${!!s.enabled}">${s.enabled ? "Pausar" : "Ativar"} rotina</button></div>` : s.kind === "import" ? "<p>Importação manual: estes anúncios não são atualizados automaticamente.</p>" : "<p>Acesso ainda pendente. Você pode importar dados obtidos de forma autorizada.</p>"}</article>`).join("")}</div><details class="panel manual-area"><summary>Adicionar um imóvel manualmente</summary><form id="manual-form" class="form-grid">${field("title", "Título", "", "text", "required")}${field("url", "Link original", "", "url")}${field("price", "Preço (R$)", "", "number", 'required min="1" step="any"')}${field("area", "Área (m²)", "", "number", 'required min="1" step="any"')}${field("city", "Cidade", "São Paulo", "text", "required")}${field("neighborhood", "Bairro")}${field("address", "Endereço")}${field("bedrooms", "Quartos", "", "number", 'min="0"')}${field("parking", "Vagas", "", "number", 'min="0"')}${field("condo_fee", "Condomínio mensal", "", "number", 'min="0" step="any"')}<button class="primary">Adicionar ao radar</button></form></details>`
  );
}
async function settings() {
  const tabs = `<div class="tabs">${[
    ["account", "Minha conta"],
    ["sources", "Fontes e atualizações"],
    ["data", "Notificações e dados"],
  ]
    .map(
      ([id, label]) =>
        `<button class="tab ${state.settingsTab === id ? "active" : ""}" data-setting="${id}">${label}</button>`,
    )
    .join("")}</div>`;
  let content;
  if (state.settingsTab === "sources") content = await sources();
  else if (state.settingsTab === "data")
    content = `<section class="panel"><h2>Seus dados e notificações</h2><p>Crie alertas a partir dos filtros do Radar. Gerencie as buscas e acompanhe novos imóveis em Notificações.</p><a href="#alerts">Gerenciar notificações →</a><p>Alertas anteriores às buscas salvas permanecem no histórico exportado da conta.</p><p><button data-export>Exportar dados da minha conta</button></p></section>`;
  else
    content = `<section class="panel"><h2>Minha conta</h2><form id="account-form">${field("name", "Seu nome", state.user.name, "text", 'required maxlength="100"')}<p>E-mail: ${esc(state.user.email)}</p><button class="primary">Salvar conta</button></form></section>`;
  return (
    header(
      "Configurações",
      "Sua conta, fontes e preferências de dados em um só lugar.",
    ) +
    tabs +
    content
  );
}
async function alerts() {
  const [r, rules] = await Promise.all([
    api(`/notifications?page=1&page_size=50&unread_only=${state.unreadOnly}`),
    api("/saved-searches"),
  ]);
  for (
    let page = 2;
    page <= state.notificationPages && r.items.length < r.total;
    page++
  ) {
    const next = await api(
      `/notifications?page=${page}&page_size=50&unread_only=${state.unreadOnly}`,
    );
    r.items.push(...next.items);
    if (!next.items.length) break;
  }
  state.unread = r.unread;
  navigation();
  return (
    header(
      "Notificações da sua busca.",
      "Novos imóveis que entraram nas buscas que você acompanha.",
      "<button data-read-all>Marcar todas como lidas</button>",
    ) +
    `<section class="panel"><h2>Buscas acompanhadas</h2><p>Os critérios ficam registrados ao criar o alerta. Alterações no Radar não modificam estes alertas.</p>${rules.items.map((rule) => `<div class="saved-search-row"><div><b>${esc(rule.name)}</b><p class="small">${rule.match_count} imóveis identificados · ${rule.enabled ? "Ativo" : "Pausado"} · ${esc(rule.q || "Todas as palavras")} · até ${money(rule.profile?.budget_max)} · ${esc(activeCriteria(rule.profile || {}))}</p></div><button data-rule="${rule.id}" data-enabled="${!!rule.enabled}">${rule.enabled ? "Pausar" : "Retomar"}</button></div>`).join("") || '<p>Nenhum alerta configurado. <a href="#radar">Crie um alerta no Radar →</a></p>'}</section><div class="form-actions"><b>${r.unread} não lidas</b><label><input type="checkbox" id="unread-only" ${state.unreadOnly ? "checked" : ""}> Apenas não lidas</label></div>${r.items.map((a) => `<article class="panel notification-item"><span class="tag">${a.read ? "Lida" : "Nova"}</span><p class="small">${esc(a.search_name || "Histórico anterior")} · ${date(a.created_at)}</p><h2>${esc(a.title)}</h2><p>${esc(a.body)}</p><div class="form-actions">${a.property_id ? `<button data-detail="${a.property_id}">Ver imóvel</button>` : ""}${a.property_url ? link(a.property_url, "Abrir anúncio original") : ""}${!a.read ? `<button data-read="${a.id}">Marcar como lida</button>` : ""}</div></article>`).join("") || '<div class="empty"><h3>Nenhuma notificação por enquanto</h3><p>Os imóveis atuais formam a lista inicial. Novos imóveis compatíveis aparecerão aqui após a coleta.</p></div>'}${r.items.length < r.total ? "<button data-more-notifications>Carregar mais notificações</button>" : ""}`
  );
}
async function openComparison() {
  if (!dialog.open) lastDetailFocus = document.activeElement;
  const version = ++detailVersion;
  const html = await comparison();
  if (version !== detailVersion) return;
  dialog.dataset.mode = "compare";
  document.querySelector("#detail-content").innerHTML =
    '<div class="dialog-header"><b>Comparação de imóveis</b><button data-close>Fechar</button></div>' +
    html;
  bind(dialog);
  if (!dialog.open) dialog.showModal();
}
async function createAlert() {
  clearTimeout(searchTimer);
  const currentSearch = main.querySelector("#search-form");
  if (currentSearch) {
    const form = new FormData(currentSearch);
    state.q = String(form.get("q") || "");
    state.construction = String(form.get("construction") || "all");
  }
  if (flushProfile && !(await flushProfile())) return;
  if (!state.apply) {
    state.apply = true;
    state.page = 1;
    await render();
    toast("Seus critérios foram aplicados ao Radar para criar este alerta.");
  }
  const snapshot = {
    profile: structuredClone(state.profile),
    q: state.q,
    construction: state.construction,
  };
  dialog.dataset.mode = "alert";
  lastDetailFocus = document.activeElement;
  document.querySelector("#detail-content").innerHTML =
    `<div class="dialog-header"><h2>Criar alerta desta busca</h2><button data-close>Fechar</button></div><form id="new-alert-form">${field("alert_name", "Nome do alerta", state.profile.name || "Minha busca", "text", 'required maxlength="100"')}<p><b>Critérios ativos:</b> até ${money(snapshot.profile.budget_max)} · ${esc(activeCriteria(snapshot.profile))} · ${esc(snapshot.q || "Todas as palavras")} · ${esc({ all: "Todas as fases", off_plan: "Na planta", under_construction: "Na planta / em construção", ready: "Pronto", unknown: "Fase não informada" }[snapshot.construction])}.</p><p>Os imóveis atuais formam sua lista inicial. Você receberá notificações quando outros imóveis corresponderem a estes critérios.</p><p>O alerta consulta as fontes com esta cópia dos critérios, mesmo após alterar o Radar. A primeira coleta começa pelo serviço de atualização; depois é diária. Mantenha a aplicação em execução.</p><button class="primary">Ativar alerta</button></form>`;
  bind(dialog);
  dialog.showModal();
  dialog.querySelector("#new-alert-form").onsubmit = (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      await api("/saved-searches", {
        method: "POST",
        body: { ...snapshot, name: new FormData(e.target).get("alert_name") },
      });
      dialog.close();
      toast(
        "Alerta criado. Lista inicial registrada sem notificações retroativas.",
      );
    });
  };
}
function showImportPreview(r) {
  const el = document.querySelector("#import-preview");
  el.innerHTML = `<h3>Prévia: ${r.valid} válidos de ${r.total}</h3>${(r.warnings || []).map((w) => `<p>${esc(w)}</p>`).join("")}${(r.errors || []).map((x) => `<p class="error">Linha ${esc(x.row)}: ${esc(x.message)}</p>`).join("")}<div class="table-wrap"><table><thead><tr><th>Imóvel</th><th>Preço</th><th>Área</th><th>Fonte</th></tr></thead><tbody>${(r.records || []).map((p) => `<tr><td>${esc(listingTitle(p))}</td><td>${money(p.price)}</td><td>${number(p.area)}</td><td>${esc(p.source)}</td></tr>`).join("")}</tbody></table></div><p>Até 20 registros exibidos. Nenhum dado foi gravado ainda.</p><button id="commit-import" class="primary" ${r.errors?.length || !r.valid ? "disabled" : ""}>Confirmar importação</button>`;
  el.querySelector("#commit-import").onclick = (event) =>
    busy(event.target, async () => {
      const result = await api("/import/commit", {
        method: "POST",
        body: { preview_id: r.preview_id },
      });
      el.innerHTML = `<div class="subtle" role="status">Importação concluída: ${result.created} criados, ${result.updated} atualizados, ${result.unchanged} sem mudanças. <a href="#radar">Abrir radar →</a></div>`;
    });
  document.querySelector("#import-preview").focus();
}
async function loadMore() {
  if (loadingMore || rendering || radarLoaded >= radarTotal) return;
  const version = renderVersion,
    query = radarQuery;
  const target = main.querySelector("#radar-more");
  if (!target) return;
  loadingMore = true;
  target.textContent = "Carregando mais imóveis…";
  try {
    const params = new URLSearchParams(query);
    params.set("page", state.page + 1);
    const result = await api(`/properties?${params}`);
    if (
      version !== renderVersion ||
      query !== radarQuery ||
      !target.isConnected
    )
      return;
    const batch = document.createElement("div");
    batch.innerHTML = result.items.map((p) => card(p, state.compare)).join("");
    main.querySelector("#radar-list").append(batch);
    bind(batch);
    animateRadar(batch);
    radarLoaded += result.items.length;
    radarTotal = result.total;
    state.page++;
    lastHtml = null;
    target.innerHTML =
      radarLoaded < radarTotal && result.items.length
        ? '<button type="button" data-load-more>Carregar mais imóveis</button>'
        : "<span>Todos os imóveis desta busca foram exibidos.</span>";
  } catch (error) {
    if (target.isConnected)
      target.innerHTML = `<span>${esc(error.message)}</span><button type="button" data-load-more>Tentar novamente</button>`;
    radarObserver?.disconnect();
  } finally {
    loadingMore = false;
    const button = target.querySelector("[data-load-more]");
    if (button) button.onclick = loadMore;
  }
}
function updateComparisonSelection() {
  if (!["radar", "journey"].includes(location.hash.slice(1) || "radar")) return;
  document
    .querySelectorAll("[data-compare]")
    .forEach((c) => (c.checked = state.compare.has(Number(c.dataset.compare))));
  let tray = main.querySelector(".comparison-tray");
  if (!tray && state.compare.size) {
    tray = document.createElement("div");
    tray.className = "comparison-tray";
    main.prepend(tray);
  }
  if (tray) {
    tray.innerHTML = state.compare.size
      ? `<b>${state.compare.size} de 4 imóveis selecionados</b><button data-open-compare>Abrir comparador →</button><button data-clear-compare>Limpar seleção</button>`
      : "";
    tray.hidden = !state.compare.size;
    tray
      .querySelector("[data-open-compare]")
      ?.addEventListener("click", () =>
        openComparison().catch((e) => toast(e.message)),
      );
    tray
      .querySelector("[data-clear-compare]")
      ?.addEventListener("click", () => {
        state.compare.clear();
        updateComparisonSelection();
      });
  }
}
function bind(root = main) {
  root.querySelectorAll("[data-settings-link]").forEach(
    (b) =>
      (b.onclick = () => {
        state.settingsTab = b.dataset.settingsLink;
      }),
  );
  root.querySelectorAll("[data-setting]").forEach(
    (b) =>
      (b.onclick = () => {
        state.settingsTab = b.dataset.setting;
        render();
      }),
  );
  root
    .querySelectorAll("[data-open-compare]")
    .forEach((b) => (b.onclick = () => busy(b, openComparison)));
  root
    .querySelectorAll("[data-create-alert]")
    .forEach((b) => (b.onclick = () => busy(b, createAlert)));
  root.querySelectorAll("[data-rule]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          await api(`/saved-searches/${b.dataset.rule}`, {
            method: "PATCH",
            body: { enabled: b.dataset.enabled !== "true" },
          });
          await render();
        })),
  );
  root.querySelector("[data-read-all]")?.addEventListener("click", (e) =>
    busy(e.target, async () => {
      await api("/notifications/read-all", { method: "PATCH" });
      await render();
    }),
  );
  root.querySelector("#unread-only")?.addEventListener("change", (e) => {
    state.unreadOnly = e.target.checked;
    state.notificationPages = 1;
    render();
  });
  root
    .querySelector("[data-more-notifications]")
    ?.addEventListener("click", () => {
      state.notificationPages++;
      render();
    });
  root.querySelector("#account-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      state.user = await api("/account", {
        method: "PATCH",
        body: { name: new FormData(e.target).get("alert_name") },
      });
      dirtyForms.delete(e.target);
      navigation();
      toast("Conta atualizada.");
    });
  });

  if (root === main) {
    radarObserver?.disconnect();
    const more = main.querySelector("#radar-more");
    const button = more?.querySelector("[data-load-more]");
    if (button) {
      button.onclick = loadMore;
      radarObserver = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) loadMore();
        },
        { rootMargin: "500px" },
      );
      radarObserver.observe(more);
    }
  }
  root.querySelectorAll("img").forEach((img) => {
    img.addEventListener("error", () => img.remove());
    if (img.complete && !img.naturalWidth) img.remove();
  });
  root
    .querySelectorAll("[data-close]")
    .forEach((b) => (b.onclick = () => dialog.close()));
  root
    .querySelectorAll("[data-detail]")
    .forEach(
      (b) =>
        (b.onclick = () => busy(b, () => detail(Number(b.dataset.detail)))),
    );
  root.querySelectorAll("[data-save]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          await api(`/properties/${b.dataset.save}/tracking`, {
            method: "PATCH",
            body: { saved: b.dataset.saved !== "true" },
          });
          toast("Favoritos atualizados.");
          if (dialog.open) await detail(Number(b.dataset.save));
          await render();
        })),
  );
  root.querySelectorAll("[data-compare]").forEach(
    (c) =>
      (c.onchange = () => {
        const id = Number(c.dataset.compare);
        if (c.checked && state.compare.size >= 4) {
          c.checked = false;
          return toast("Compare até quatro imóveis por vez.");
        }
        c.checked ? state.compare.add(id) : state.compare.delete(id);
        updateComparisonSelection();
      }),
  );
  root.querySelectorAll("[data-uncompare]").forEach(
    (b) =>
      (b.onclick = () => {
        state.compare.delete(Number(b.dataset.uncompare));
        updateComparisonSelection();
        if (dialog.open) openComparison();
      }),
  );
  root.querySelectorAll("[data-page]").forEach(
    (b) =>
      (b.onclick = () => {
        state.page = Number(b.dataset.page);
        render();
      }),
  );
  root.querySelectorAll("[data-tab]").forEach(
    (b) =>
      (b.onclick = () => {
        state.tab = b.dataset.tab;
        state.page = 1;
        render();
      }),
  );
  root.querySelectorAll("[data-reset]").forEach(
    (b) =>
      (b.onclick = () => {
        state.q = "";
        state.construction = "all";
        const searchForm = main.querySelector("#search-form");
        if (searchForm) {
          searchForm.elements.q.value = "";
          searchForm.elements.construction.value = "all";
        }
        state.apply = false;
        state.tab = "all";
        state.page = 1;
        render();
      }),
  );
  root.querySelectorAll("[data-refresh]").forEach((b) => {
    b.onclick = () => busy(b, startSourceSearch);
  });

  root.querySelectorAll("[data-read]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          await api(`/alerts/${b.dataset.read}`, {
            method: "PATCH",
            body: { read: true },
          });
          render();
        })),
  );
  root.querySelectorAll("[data-source-refresh]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          state.sourceResults[b.dataset.sourceRefresh] = await api(
            `/sources/${encodeURIComponent(b.dataset.sourceRefresh)}/refresh`,
            { method: "POST" },
          );
          toast("Fonte atualizada.");
          render();
        })),
  );
  root.querySelectorAll("[data-portal]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          const label = b.textContent;
          b.textContent = "Ativando fonte…";
          let source;
          try {
            source = await api("/sources/portal", {
              method: "POST",
              body: { portal: b.dataset.portal },
            });
            b.textContent = "Coletando anúncios…";
            toast("Fonte ativada. Consultando os anúncios da sua busca…");
            state.sourceResults[source.id] = await api(
              `/sources/${source.id}/refresh`,
              { method: "POST" },
            );
            toast(
              "Coleta concluída. Confira a cobertura abaixo e os anúncios no radar.",
            );
          } finally {
            if (b.isConnected) b.textContent = label;
            if (source) await render();
          }
        })),
  );
  root.querySelectorAll("[data-source-toggle]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          await api(`/sources/${encodeURIComponent(b.dataset.sourceToggle)}`, {
            method: "PATCH",
            body: { enabled: b.dataset.enabled !== "true" },
          });
          render();
        })),
  );
  root
    .querySelector("[data-export]")
    ?.addEventListener("click", (e) =>
      busy(e.target, () => download("/export", "imovel-radar-conta.json")),
    );
  root
    .querySelector("[data-template]")
    ?.addEventListener("click", (e) =>
      busy(e.target, () =>
        download("/import/template.csv", "modelo-imoveis.csv"),
      ),
    );
  const searchForm = root.querySelector("#search-form");
  if (searchForm) {
    const search = () => {
      clearTimeout(searchTimer);
      const f = new FormData(searchForm);
      state.q = f.get("q");
      state.sort = f.get("sort");
      state.construction = f.get("construction");
      state.page = 1;
      render();
    };
    searchForm.onsubmit = (e) => {
      e.preventDefault();
      const f = new FormData(searchForm);
      state.q = f.get("q");
      state.sort = f.get("sort");
      state.construction = f.get("construction");
      busy(e.submitter, startSourceSearch);
    };
    searchForm.onchange = search;
    searchForm.oninput = (e) => {
      if (e.target.name !== "q" || e.isComposing) return;
      renderVersion++;
      clearTimeout(searchTimer);
      searchTimer = setTimeout(search, 350);
    };
  }
  root.querySelector("#apply-profile")?.addEventListener("change", (e) => {
    state.apply = e.target.checked;
    state.page = 1;
    render();
  });
  root.querySelectorAll("[data-tracking]").forEach(
    (form) =>
      (form.onsubmit = (e) => {
        e.preventDefault();
        busy(e.submitter, async () => {
          const f = new FormData(form);
          await api(`/properties/${form.dataset.tracking}/tracking`, {
            method: "PATCH",
            body: {
              stage: f.get("stage"),
              notes: f.get("notes"),
              visit_at: f.get("visit_at")
                ? new Date(f.get("visit_at")).toISOString()
                : null,
              assessments: Object.fromEntries(
                assessmentFields.map(([key]) => [
                  key,
                  f.get(`assessment_${key}`) || "unknown",
                ]),
              ),
              checklist: Object.fromEntries(
                ["documents", "structure", "neighborhood", "costs"].map((k) => [
                  k,
                  f.has(`check_${k}`),
                ]),
              ),
            },
          });
          dirtyForms.delete(form);
          toast("Acompanhamento salvo.");
        });
      }),
  );
  const profileForm = root.querySelector("#profile-form");
  if (profileForm && !profileForm.dataset.bound) {
    profileForm.dataset.bound = "true";
    let cancelled = false;
    let timer,
      revision = 0,
      savedRevision = 0,
      saving = null;
    const status = profileForm.querySelector("#profile-save-status");
    const save = async () => {
      clearTimeout(timer);
      if (cancelled) return false;
      if (saving) {
        await saving;
        if (savedRevision === revision) return true;
      }
      if (savedRevision === revision) return true;
      if (!profileForm.checkValidity()) {
        profileForm.reportValidity();
        status.textContent =
          "Confira os campos inválidos. As últimas preferências salvas continuam ativas.";
        return;
      }
      const current = revision;
      status.textContent = "Salvando e atualizando o Radar…";
      saving = (async () => {
        try {
          const f = new FormData(profileForm),
            p = {
              ...state.profile,
              name: f.get("name"),
              cities: f
                .get("cities")
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
              neighborhoods: f
                .get("neighborhoods")
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
              metro_stations: f
                .get("metro_stations")
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
              search_bounds: f.has("use_bounds")
                ? state.profile.search_bounds
                : [],
              exclude_occupied: f.has("exclude_occupied"),
              require_elevator: f.has("require_elevator"),
              exclude_unknown_required: f.has("exclude_unknown_required"),
              weights: Object.fromEntries(
                ["price", "location", "quality"].map((k) => [
                  k,
                  Number(f.get(`weight_${k}`)),
                ]),
              ),
            };
          for (const k of [
            "budget_min",
            "budget_max",
            "bathrooms_min",
            "floor_min",
            "area_min",
            "area_max",
            "bedrooms_min",
            "parking_min",
            "metro_max",
            "monthly_max",
            "alert_drop_percent",
          ])
            p[k] =
              f.get(k) === ""
                ? ["bedrooms_min", "parking_min", "bathrooms_min"].includes(k)
                  ? 0
                  : null
                : Number(f.get(k));
          if (
            p.area_min != null &&
            p.area_max != null &&
            p.area_min > p.area_max
          )
            throw Error(
              "Área mínima maior que a máxima. Aumente a máxima ou deixe-a vazia",
            );
          state.profile = await api("/profile", { method: "PUT", body: p });

          const criteria = profileForm.querySelector("[data-active-criteria]");
          if (criteria) criteria.textContent = activeCriteria(state.profile);
          savedRevision = current;
          state.apply = true;
          state.page = 1;
          if (current === revision) dirtyForms.delete(profileForm);
          if (current === revision) {
            status.textContent =
              "Filtros salvos · lista local atualizada. Pesquisar nas fontes consulta novos anúncios.";
            if ((location.hash.slice(1) || "radar") === "radar") await render();
          }
        } catch (error) {
          status.textContent = `Não foi possível salvar: ${error.message}. Suas alterações continuam neste formulário.`;
        }
      })();
      await saving;
      saving = null;
      return savedRevision === revision;
    };
    const scheduleSave = () => {
      revision++;
      clearTimeout(timer);
      status.textContent = "Alterações pendentes…";
      timer = setTimeout(save, 650);
    };
    profileForm.oninput = scheduleSave;
    profileForm.onchange = scheduleSave;
    profileForm.onsubmit = (e) => {
      e.preventDefault();
      save();
    };
    flushProfile = save;
    cancelProfile = () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }
  root.querySelector("#budget-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      const f = Object.fromEntries(new FormData(e.target));
      for (const k of Object.keys(f)) if (k !== "model") f[k] = Number(f[k]);
      const r = await api("/budget", { method: "POST", body: f });
      document.querySelector("#budget-result").innerHTML =
        `<h2>Seu plano de compra · ${f.model === "sac" ? "SAC" : "Price"}</h2><div class="price">${money(r.first_month_total)}</div><p>Primeiro mês, incluindo custos informados</p>${[
          ["Primeira parcela", r.first_payment],
          ["Última parcela", r.last_payment],
          ["Juros totais", r.total_interest],
          ["Total das parcelas", r.total_paid],
          ["Caixa inicial necessário", r.initial_cash],
        ]
          .map(
            ([l, v]) =>
              `<div class="check-row"><span>${l}</span><b>${money(v)}</b></div>`,
          )
          .join(
            "",
          )}<p>Simulação sob as hipóteses informadas. Seguros e indexadores não informados não estão incluídos.</p><details><summary>Evolução das parcelas</summary><div class="table-wrap"><table><thead><tr><th>Mês</th><th>Parcela</th><th>Juros</th><th>Saldo</th></tr></thead><tbody>${(r.schedule || []).map((s) => `<tr><td>${s.month}</td><td>${money(s.payment)}</td><td>${money(s.interest)}</td><td>${money(s.balance)}</td></tr>`).join("")}</tbody></table></div></details>`;
    });
  });
  root.querySelector("#source-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      const f = new FormData(e.target);
      await api("/sources", {
        method: "POST",
        body: {
          name: f.get("feed_name"),
          url: f.get("feed_url"),
          authorized: f.has("authorized"),
        },
      });
      toast(
        "Fonte cadastrada. Execute uma atualização para verificar os dados.",
      );
      render();
    });
  });
  root.querySelector("#manual-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      const p = Object.fromEntries(new FormData(e.target));
      for (const k of ["price", "area", "bedrooms", "parking", "condo_fee"])
        p[k] = p[k] === "" ? null : Number(p[k]);
      if (!p.url) p.url = null;
      p.property_type = "apartment";
      await api("/properties", { method: "POST", body: p });
      toast("Imóvel adicionado.");
      location.hash = "radar";
    });
  });
  root
    .querySelector("[data-legacy-preview]")
    ?.addEventListener("click", (e) =>
      busy(e.target, async () =>
        showImportPreview(
          await api("/import/legacy-preview", { method: "POST" }),
        ),
      ),
    );
  root.querySelector("#import-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      const file = e.target.elements.file.files[0];
      if (file.size > 10 * 1024 * 1024) throw Error("Arquivo excede 10 MB.");
      const f = new FormData();
      f.append("file", file);
      const r = await api("/import/preview", { method: "POST", body: f });
      showImportPreview(r);
    });
  });
}
dialog.addEventListener("close", () => {
  if (lastDetailFocus?.isConnected) lastDetailFocus.focus();
  else main.focus({ preventScroll: true });
});
window.addEventListener("hashchange", async () => {
  if (flushProfile) {
    const save = flushProfile;
    flushProfile = null;
    const saved = await save();
    if (!saved) {
      flushProfile = save;
      history.replaceState(null, "", "#radar");
      toast(
        "Corrija ou salve suas preferências antes de sair; seu rascunho foi preservado.",
      );
      return;
    }
    cancelProfile?.();
    cancelProfile = null;
  }
  clearTimeout(searchTimer);
  detailVersion++;
  dialog.close();
  render();
  main.focus({ preventScroll: true });
});
function clearAccountState() {
  accountEpoch++;
  searchNeedsRender = false;
  cancelProfile?.();
  cancelProfile = null;
  clearTimeout(searchTimer);
  lastPage = lastHtml = null;
  flushProfile = null;
  renderVersion++;
  detailVersion++;
  dialog.close();
  document.querySelector("#detail-content").replaceChildren();
  state.user = null;
  state.profile = {};
  state.sourceResults = {};
  state.searchJob = null;
  state.compare.clear();
  state.q = "";
  state.construction = "all";
  state.sort = "fit";
  state.tab = "all";
  state.apply = true;
  state.page = 1;
  state.unread = 0;
  state.unreadOnly = false;
  state.notificationPages = 1;
  state.settingsTab = "account";
  navigation();
  auth();
}
window.addEventListener("session-expired", clearAccountState);
document.querySelector("#logout").onclick = (e) =>
  busy(e.target, async () => {
    await api("/auth/logout", { method: "POST" });
    setToken(null);
    clearAccountState();
  });
if (hasSession()) {
  try {
    state.user = await api("/auth/me");
    state.profile = await api("/profile");
  } catch {
    setToken(null);
    state.user = null;
  }
}
await render();

// Refresh visible data only; never reload the document or interrupt an edit.
const livePages = new Set(["radar", "settings", "alerts", "journey"]);
async function syncVisiblePage() {
  if (document.hidden) return;
  if (state.user) {
    try {
      const r = await api("/notifications?page_size=1");
      if (state.unread !== r.unread) {
        state.unread = r.unread;
        const badge = document.querySelector(".notification-count");
        if (badge) badge.textContent = state.unread || "";
      }
    } catch {}
  }
  if (!state.user || !livePages.has(location.hash.slice(1) || "radar")) return;
  await render({ background: true });
}
setInterval(syncVisiblePage, 15000);
window.addEventListener("online", syncVisiblePage);
window.addEventListener("focus", syncVisiblePage);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) syncVisiblePage();
});
