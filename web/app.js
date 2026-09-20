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
  q: "",
  sort: "fit",
  tab: "all",
  apply: false,
  page: 1,
};
const nav = [
  ["radar", "◉", "Radar de oportunidades"],
  ["compare", "⇆", "Comparar imóveis"],
  ["journey", "♡", "Minha jornada"],
  ["budget", "▤", "Planejar a compra"],
  ["profile", "⚙", "Minha busca"],
  ["sources", "↻", "Fontes e atualização"],
  ["alerts", "◎", "Alertas"],
];
let renderVersion = 0,
  lastDetailFocus = null;
function navigation() {
  document.querySelector("#nav").innerHTML = state.user
    ? nav
        .map(
          ([id, icon, title]) =>
            `<a href="#${id}" ${(location.hash.slice(1) || "radar") === id ? 'aria-current="page"' : ""} class="${(location.hash.slice(1) || "radar") === id ? "active" : ""}"><span class="nav-icon">${icon}</span>${title}${id === "compare" && state.compare.size ? ` (${state.compare.size})` : ""}</a>`,
        )
        .join("")
    : "";
  document.querySelector("#identity").textContent = state.user?.name || "";
  document.querySelector("#logout").hidden = !state.user;
}
async function render() {
  const v = ++renderVersion;
  navigation();
  if (!state.user) return auth();
  main.innerHTML =
    '<div class="panel" role="status">Carregando seus dados…</div>';
  try {
    const page = location.hash.slice(1) || "radar";
    const html = await (
      { radar, compare: comparison, journey, budget, profile, sources, alerts }[
        page
      ] || radar
    )();
    if (v !== renderVersion) return;
    main.innerHTML = html;
    bind();
  } catch (e) {
    if (v !== renderVersion) return;
    if (!state.user) return auth();
    main.innerHTML =
      header(
        "Não foi possível carregar.",
        "Seus dados salvos permanecem preservados.",
      ) +
      `<div class="panel" role="alert">${esc(e.message)}<p><button data-retry>Tentar novamente</button></p></div>`;
    main.querySelector("[data-retry]").onclick = render;
  }
}
function auth(register = false) {
  main.innerHTML =
    header(
      register ? "Comece sua busca." : "Seu próximo lar começa aqui.",
      "Sua conta organiza anúncios, preferências e histórico de decisão.",
    ) +
    `<form id="auth" class="panel auth-panel">${register ? field("name", "Seu nome", "", "text", 'required maxlength="100"') : ""}${field("email", "E-mail", "", "email", 'required autocomplete="email"')}${field("password", "Senha (mínimo 12 caracteres)", "", "password", `required minlength="12" autocomplete="${register ? "new-password" : "current-password"}"`)}<p id="auth-error" role="alert"></p><div class="form-actions"><button class="primary">${register ? "Criar conta" : "Entrar"}</button><button type="button" id="switch-auth">${register ? "Já tenho conta" : "Criar minha conta"}</button></div></form>`;
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
  const params = new URLSearchParams({
    q: state.q,
    sort: state.sort,
    saved: state.tab === "saved",
    drops: state.tab === "drops",
    apply_profile: state.apply,
    page: state.page,
    page_size: 20,
  });
  const r = await api(`/properties?${params}`),
    s = r.summary || {};
  return (
    header(
      "Seu próximo lar começa aqui.",
      "Acompanhe oportunidades. Decida com evidências.",
      "<button data-refresh>↻ Atualizar fontes</button>",
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
      )}</section>${state.compare.size ? `<div class="comparison-tray"><b>${state.compare.size} de 4 imóveis selecionados</b><a href="#compare">Abrir comparador →</a></div>` : ""}<div class="radar-grid"><section><div class="tabs">${[
      ["all", "Todos"],
      ["drops", "Preço caiu"],
      ["saved", "Salvos"],
    ]
      .map(
        ([id, label]) =>
          `<button class="tab ${state.tab === id ? "active" : ""}" data-tab="${id}">${label}</button>`,
      )
      .join(
        "",
      )}</div><form id="search-form" class="filter-line"><input name="q" type="search" aria-label="Buscar imóvel, bairro ou fonte" placeholder="Busque por bairro, imóvel ou fonte…" value="${esc(state.q)}"><select name="sort" aria-label="Ordenar">${[
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
      )}</select><button>Buscar</button></form><label class="small"><input id="apply-profile" type="checkbox" ${state.apply ? "checked" : ""}> Aplicar minha busca</label><p class="listing-count">${r.total} imóveis · atualização: ${date(r.last_updated)}</p>${r.items.length ? r.items.map((p) => card(p, state.compare)).join("") : `<div class="empty"><h3>${state.q || state.apply || state.tab !== "all" ? "Nenhum imóvel nesses filtros" : "Seu radar está pronto para começar"}</h3><p>Importe seus anúncios ou conecte um feed autorizado para construir seu histórico.</p><a href="#sources">Importar e configurar fontes →</a><p><button data-reset>Limpar filtros</button></p></div>`}<div class="pagination"><button data-page="${state.page - 1}" ${state.page <= 1 ? "disabled" : ""}>Anterior</button><span>Página ${state.page} de ${Math.max(1, Math.ceil(r.total / 20))}</span><button data-page="${state.page + 1}" ${state.page * 20 >= r.total ? "disabled" : ""}>Próxima</button></div></section><aside class="rail"><div class="daily"><p class="eyebrow">SUA DECISÃO, COM CONTEXTO</p><h2>Preço bom precisa de evidência.</h2><p>Avaliação de qualidade, aderência pessoal e preço relativo são medidas diferentes. Poucos comparáveis? A estimativa fica pendente.</p><a href="#alerts">Ver mudanças e alertas →</a></div><div class="panel"><h3>Uma busca com sua cara</h3><div class="check-row"><span>Orçamento</span><b>${money(state.profile.budget_max)}</b></div><div class="check-row"><span>Área mínima</span><b>${number(state.profile.area_min)} m²</b></div><a href="#profile">Editar preferências →</a></div><div class="subtle">Anúncios importados não se atualizam sozinhos. Fontes e atualização mostra quais feeds estão ativos e a saúde da rotina diária.</div></aside></div>`
  );
}
async function detail(id) {
  if (!dialog.open) lastDetailFocus = document.activeElement;
  const p = await api(`/properties/${id}`),
    e = p.evaluation || {};
  document.querySelector("#detail-content").innerHTML =
    `<div class="dialog-header"><div><p class="eyebrow">DOSSIÊ DO IMÓVEL</p><h2>${esc(listingTitle(p))}</h2></div><button data-close aria-label="Fechar dossiê">×</button></div><div class="detail-grid"><div>${photo(p)}${!p.observed_at ? '<span class="tag amber">Data não confirmada</span>' : ""}<p>${esc(p.address)} · ${esc(p.neighborhood)} · ${esc(p.city)}</p><div class="features">${[
      ["Área", `${number(p.area)} m²`],
      ["Quartos", number(p.bedrooms)],
      ["Vagas", number(p.parking)],
      ["Andar", number(p.floor)],
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
      )}</ul></details>${p.latitude != null && p.longitude != null ? link(`https://www.openstreetmap.org/?mlat=${encodeURIComponent(p.latitude)}&mlon=${encodeURIComponent(p.longitude)}#map=17/${encodeURIComponent(p.latitude)}/${encodeURIComponent(p.longitude)}`, "Ver localização informada no mapa") : ""}</section></div><div><div class="price">${money(p.price)}</div><p>${money(p.price / p.area)}/m²</p>${p.combined_monthly_cost != null ? `<div class="check-row"><span>Condomínio + IPTU combinados (origem)</span><b>${money(p.combined_monthly_cost)}${p.combined_cost_period === "unknown" ? " · período a confirmar" : "/mês"}</b></div><p class="small">Total informado pela fonte; componentes e periodicidade do IPTU não confirmados.</p>` : ""}<div class="check-row"><span>Condomínio mensal</span><b>${money(p.condo_fee)}</b></div><div class="check-row"><span>IPTU (${esc({ annual: "anual", monthly: "mensal", unknown: "periodicidade desconhecida" }[p.tax_period] || "não informado")})</span><b>${money(p.property_tax)}</b></div><section class="panel"><h2>${opportunity(e)}</h2><p>${e.comparables_count || 0} comparáveis · confiança ${confidence(e.confidence)}</p><p>Referência: ${money(e.benchmark_m2)}/m². Preços de anúncios, não de transações.</p><details><summary>Ver comparáveis usados</summary>${(e.comparables || []).map((c) => `<p><button data-detail="${c.id}">Imóvel ${c.id}</button> ${money(c.price)} · ${number(c.area)} m² · ${money(c.price_m2)}/m²</p>`).join("") || "<p>Amostra insuficiente.</p>"}</details></section><section class="panel"><h3>Aderência ${score(e.fit_score)}</h3><p>Qualidade observável ${score(e.quality_score)}</p>${e.quality_coverage != null ? `<p>Cobertura da qualidade: ${number(e.quality_coverage)}% dos fatores conhecidos.</p>` : ""}${e.fit_coverage != null ? `<p>Cobertura da aderência: ${number(e.fit_coverage)}% dos requisitos conhecidos.</p>` : ""}<p>${e.eligible ? "Atende aos requisitos conhecidos." : "Não atende a todos os requisitos da sua busca."}</p><ul>${(e.reasons || []).map((r) => `<li>${esc(r)}</li>`).join("")}</ul><details><summary>Fatores e pesos</summary>${[...(e.fit_factors || []), ...(e.quality_factors || [])].map((f) => `<div class="check-row"><span>${esc(f.label)}</span><b>${esc(f.score ?? f.value ?? "Pendente")} · peso ${number(f.weight)}</b></div>`).join("")}<p>Versão: ${esc(e.score_version)}</p></details></section><button class="primary" data-save="${id}" data-saved="${!!p.saved}">${p.saved ? "Remover dos salvos" : "Salvar na minha jornada"}</button><a href="#journey" data-close>Organizar visita e notas →</a></div></div>`;
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
  for (let page = 2; r.items.length < r.total && r.items.length < 500; page++) {
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
            `<form class="journey-card" data-tracking="${p.id}"><h3>${esc(listingTitle(p))}</h3><p>${money(p.price)} · ${esc(p.neighborhood)}</p><button type="button" class="text-button" data-detail="${p.id}">Abrir dossiê ↗</button><label>Etapa<select name="stage">${Object.entries(
              stages,
            )
              .map(
                ([v, l]) =>
                  `<option value="${v}" ${(p.stage || "saved") === v ? "selected" : ""}>${l}</option>`,
              )
              .join(
                "",
              )}</select></label><label>Visita marcada<input type="datetime-local" name="visit_at" value="${p.visit_at ? esc(new Date(new Date(p.visit_at).getTime() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)) : ""}"></label><label>Notas<textarea name="notes" maxlength="10000" placeholder="Luz, ruído, estado do prédio, negociação…">${esc(p.notes)}</textarea></label><div class="checks">${[
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
    }</div>${r.total > r.items.length ? "<p>Mostrando os primeiros 500 salvos. Use a busca do radar para encontrar outros.</p>" : ""}`
  );
}
async function profile() {
  const p = (state.profile = await api("/profile"));
  return (
    header(
      "Uma busca com a sua cara.",
      "Requisitos pessoais filtram a busca. Qualidade e oportunidade continuam independentes.",
    ) +
    `<form id="profile-form"><div class="form-grid"><section class="panel"><h2>Seu imóvel ideal</h2>${field("name", "Nome", p.name)}${[
      ["budget_max", "Preço máximo (R$)"],
      ["area_min", "Área mínima (m²)"],
      ["area_max", "Área máxima (m²)"],
      ["bedrooms_min", "Quartos mínimos"],
      ["parking_min", "Vagas mínimas"],
      ["metro_max", "Metrô a pé: máximo (min)"],
      ["monthly_max", "Condomínio + IPTU mensal: máximo (R$)"],
    ]
      .map(([k, l]) => field(k, l, p[k] ?? "", "number", 'min="0" step="any"'))
      .join(
        "",
      )}${field("cities", "Cidades (separadas por vírgula)", (p.cities || []).join(", "))}${field("neighborhoods", "Bairros (separados por vírgula)", (p.neighborhoods || []).join(", "))}<p>Deixe limites vazios para não restringir aquele critério. Quartos e vagas vazios usam mínimo zero.</p></section><section class="panel"><h2>O que pesa para você</h2>${[
      ["price", "Preço"],
      ["location", "Localização"],
      ["quality", "Qualidade"],
    ]
      .map(([k, l]) =>
        field(
          `weight_${k}`,
          `Peso: ${l}`,
          p.weights?.[k] ?? 0,
          "number",
          'min="0" max="100" required',
        ),
      )
      .join(
        "",
      )}<div class="checks"><label><input type="checkbox" name="require_elevator" ${p.require_elevator ? "checked" : ""}>Elevador obrigatório</label><label><input type="checkbox" name="exclude_unknown_required" ${p.exclude_unknown_required ? "checked" : ""}>Excluir imóveis com requisitos desconhecidos</label></div>${field("alert_drop_percent", "Alertar queda de preço a partir de (%)", p.alert_drop_percent ?? 5, "number", 'min="0" max="100" required')}<button class="primary">Salvar preferências</button><p>As notas usam fatores explicáveis. Dados ausentes não recebem nota máxima.</p><button type="button" data-export>Exportar dados da minha conta</button></section></div></form>`
  );
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
async function sources() {
  const [r, status] = await Promise.all([api("/sources"), api("/status")]),
    schedule = r.schedule || {};
  return (
    header(
      "Dados bons também têm histórico.",
      "Importe anúncios ou configure feeds que você tem autorização para consultar.",
      "<button data-refresh>↻ Atualizar feeds</button>",
    ) +
    `<div class="subtle">Rotina diária: ${esc(schedule.hour ?? "não configurada")}h · ${esc(schedule.timezone || "fuso não informado")} · rotina ${schedule.worker_status === "running" ? "ativa" : "offline"} · Último sinal da rotina: ${date(schedule.worker_heartbeat)}. Portais pendentes não são integrações ativas.</div><div class="form-grid import-area"><section class="panel"><h2>Importar anúncios</h2><p>CSV, JSON ou XLSX. Confira a prévia antes de gravar. Máximo de 10 MB e 5.000 linhas.</p><form id="import-form"><div class="form-field"><label for="import-file">Arquivo de anúncios</label><input id="import-file" type="file" name="file" accept=".csv,.json,.xlsx" required></div><button class="primary">Validar e ver prévia</button><button type="button" data-template>Baixar modelo CSV</button></form>${status.legacy_import_available ? '<p><button type="button" data-legacy-preview>Pré-visualizar planilha original (24 anúncios)</button></p>' : ""}<div id="import-preview" aria-live="polite" tabindex="-1"></div></section><section class="panel"><h2>Conectar feed</h2><form id="source-form">${field("feed_name", "Nome da fonte", "", "text", 'required maxlength="100"')}${field("feed_url", "URL pública do feed", "", "url", 'required placeholder="https://…"')}<label class="small"><input name="authorized" type="checkbox" required> Tenho autorização para consultar este feed.</label><p>Use feeds JSON/CSV/XML disponibilizados pela fonte. Uma página de busca de portal não é um feed.</p><button class="primary">Adicionar fonte</button></form></section></div><div class="source-grid">${r.items.map((s) => `<article class="panel"><div class="source-logo">${esc(s.name?.[0] || "↻")}</div><h2>${esc(s.name)}</h2><span class="tag ${s.last_success ? "" : "amber"}">${esc({ pending_access: "Acesso pendente", imported: "Dados importados", healthy: "Atualizada", running: "Atualizando", pending: "Aguardando primeira atualização", success: "Atualizada", error: "Falha na atualização", feed: "Feed autorizado", portal: "Portal" }[s.status || s.kind] || s.status || s.kind)}</span><p>${link(s.url, "Abrir fonte")}</p><div class="check-row"><span>Última tentativa</span><b>${date(s.last_attempt)}</b></div><div class="check-row"><span>Último sucesso</span><b>${date(s.last_success)}</b></div><div class="check-row"><span>Registros</span><b>${number(s.record_count)}</b></div>${s.error ? `<p class="error" role="alert">${esc(s.error)}</p>` : ""}${s.authorized ? `<div class="form-actions"><button data-source-refresh="${esc(s.id)}">Atualizar agora</button><button data-source-toggle="${esc(s.id)}" data-enabled="${!!s.enabled}">${s.enabled ? "Pausar" : "Ativar"} rotina</button></div>` : s.kind === "import" ? "<p>Importação manual: estes anúncios não são atualizados automaticamente.</p>" : "<p>Acesso ainda pendente. Você pode importar dados obtidos de forma autorizada.</p>"}</article>`).join("")}</div><details class="panel manual-area"><summary>Adicionar um imóvel manualmente</summary><form id="manual-form" class="form-grid">${field("title", "Título", "", "text", "required")}${field("url", "Link original", "", "url")}${field("price", "Preço (R$)", "", "number", 'required min="1" step="any"')}${field("area", "Área (m²)", "", "number", 'required min="1" step="any"')}${field("city", "Cidade", "São Paulo", "text", "required")}${field("neighborhood", "Bairro")}${field("address", "Endereço")}${field("bedrooms", "Quartos", "", "number", 'min="0"')}${field("parking", "Vagas", "", "number", 'min="0"')}${field("condo_fee", "Condomínio mensal", "", "number", 'min="0" step="any"')}<button class="primary">Adicionar ao radar</button></form></details>`
  );
}
async function alerts() {
  const r = await api("/alerts");
  return (
    header(
      "O que mudou no seu radar.",
      "Mudanças persistidas na sua conta, sem depender de manter esta tela aberta.",
    ) +
    `<p>${r.unread || 0} alertas não lidos</p>${r.items.map((a) => `<article class="panel"><span class="tag">${a.read ? "Lido" : "Novo"}</span><h2>${esc(a.title)}</h2><p>${esc(a.body)}</p><p>${date(a.created_at)}</p><div class="form-actions">${a.property_id ? `<button data-detail="${a.property_id}">Ver imóvel</button>` : ""}${!a.read ? `<button data-read="${a.id}">Marcar como lido</button>` : ""}</div></article>`).join("") || '<div class="empty"><h3>Nenhuma mudança por enquanto</h3><p>Atualize suas fontes para acompanhar novos anúncios e mudanças de preço.</p></div>'}`
  );
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
function bind(root = main) {
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
        render();
      }),
  );
  root.querySelectorAll("[data-uncompare]").forEach(
    (b) =>
      (b.onclick = () => {
        state.compare.delete(Number(b.dataset.uncompare));
        render();
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
        state.apply = false;
        state.tab = "all";
        state.page = 1;
        render();
      }),
  );
  root.querySelectorAll("[data-refresh]").forEach(
    (b) =>
      (b.onclick = () =>
        busy(b, async () => {
          const r = await api("/refresh", { method: "POST" });
          const failures = (r.results || []).filter(
            (x) => x.status === "error",
          );
          toast(
            failures.length
              ? `${failures.length} fonte(s) falharam. Confira Fontes e atualização.`
              : r.message || "Atualização concluída.",
          );
          await render();
        })),
  );
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
          await api(
            `/sources/${encodeURIComponent(b.dataset.sourceRefresh)}/refresh`,
            { method: "POST" },
          );
          toast("Fonte atualizada.");
          render();
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
  root.querySelector("#search-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    state.q = f.get("q");
    state.sort = f.get("sort");
    state.page = 1;
    render();
  });
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
          toast("Acompanhamento salvo.");
        });
      }),
  );
  root.querySelector("#profile-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    busy(e.submitter, async () => {
      const f = new FormData(e.target),
        p = {
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
        "budget_max",
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
            ? ["bedrooms_min", "parking_min"].includes(k)
              ? 0
              : null
            : Number(f.get(k));
      state.profile = await api("/profile", { method: "PUT", body: p });
      toast("Preferências salvas.");
    });
  });
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
window.addEventListener("hashchange", () => {
  dialog.close();
  render();
  main.focus({ preventScroll: true });
});
window.addEventListener("session-expired", () => {
  state.user = null;
  state.compare.clear();
  navigation();
  auth();
});
document.querySelector("#logout").onclick = (e) =>
  busy(e.target, async () => {
    await api("/auth/logout", { method: "POST" });
    setToken(null);
    state.user = null;
    state.compare.clear();
    await render();
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
