export const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export const money = (v) =>
  v == null
    ? "Não informado"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
        maximumFractionDigits: 0,
      }).format(v);
export const number = (v) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }).format(v);
export const date = (v) =>
  !v
    ? "Não informado"
    : Number.isNaN(new Date(v).getTime())
      ? "Data desconhecida"
      : new Date(v).toLocaleString("pt-BR");
export function safeURL(v) {
  try {
    const u = new URL(v);
    return ["http:", "https:"].includes(u.protocol) ? esc(u.href) : "";
  } catch {
    return "";
  }
}
export const link = (url, label) =>
  safeURL(url)
    ? `<a href="${safeURL(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`
    : "";
export const header = (title, sub, action = "") =>
  `<div class="heading"><div><p class="eyebrow">ENCONTRE. COMPARE. ESCOLHA BEM.</p><h1>${esc(title)}</h1><p class="subtitle">${esc(sub)}</p></div>${action}</div>`;
export const field = (name, label, value = "", type = "text", extra = "") =>
  `<div class="form-field"><label for="${name}">${esc(label)}</label><input id="${name}" name="${name}" type="${type}" value="${esc(value)}" ${extra}></div>`;
export function toast(message) {
  const e = document.querySelector("#toast");
  e.textContent = message;
  e.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (e.style.display = "none"), 5500);
}
export const score = (v) => (v == null ? "Pendente" : `${number(v)}/100`);
export const confidence = (v) =>
  ({
    insufficient: "insuficiente",
    low: "baixa",
    medium: "média",
    high: "alta",
  })[v] || "insuficiente";
export function opportunity(e = {}) {
  return e.opportunity_percent == null
    ? "Preço sem estimativa"
    : `${number(Math.abs(e.opportunity_percent))}% ${e.opportunity_percent >= 0 ? "abaixo" : "acima"} dos similares`;
}
export function photo(p) {
  return `<div class="property-photo"><div class="photo-placeholder"><span aria-hidden="true">⌂</span><small>FOTO NÃO DISPONÍVEL</small></div>${safeURL(p.image_url) ? `<img src="${safeURL(p.image_url)}" alt="${esc(listingTitle(p))}" loading="lazy" referrerpolicy="no-referrer">` : ""}</div>`;
}
export function card(p, compare) {
  const e = p.evaluation || {};
  return `<article class="property">${photo(p)}<div class="property-body"><div class="property-title"><div><span class="tag">${esc(p.source)} · ${esc(listingStatus(p.status))}</span>${!p.observed_at ? '<span class="tag amber">Data não confirmada</span>' : ""}<h3>${esc(listingTitle(p))}</h3><p>${esc([p.address, p.neighborhood, p.city].filter(Boolean).join(" · "))}</p></div><button class="save ${p.saved ? "saved" : ""}" data-save="${p.id}" data-saved="${p.saved ? "true" : "false"}" aria-label="${p.saved ? "Remover dos" : "Adicionar aos"} salvos" aria-pressed="${!!p.saved}">${p.saved ? "♥" : "♡"}</button></div><div class="features"><span>${number(p.area)} m²</span><span>${number(p.bedrooms)} quartos</span><span>${number(p.parking)} vagas</span><span>${number(p.metro_minutes)} min do metrô</span></div><div class="price-line"><div class="price">${money(p.price)}<small>${p.combined_monthly_cost != null ? `Cond. + IPTU combinados: ${money(p.combined_monthly_cost)}${p.combined_cost_period === "unknown" ? " · período a confirmar" : "/mês"}` : `Condomínio: ${money(p.condo_fee)}`}</small></div><div class="opportunity">${opportunity(e)}<small>${e.comparables_count || 0} comparáveis · confiança ${confidence(e.confidence)}</small></div></div><div class="score-line"><span class="score">${score(e.fit_score)}</span> aderência pessoal · qualidade ${score(e.quality_score)}</div><div class="card-bottom"><span>${money(p.price / p.area)}/m²</span><label><input type="checkbox" data-compare="${p.id}" ${compare.has(p.id) ? "checked" : ""}> Comparar</label><button class="text-button" data-detail="${p.id}">Ver dossiê ↗</button></div></div></article>`;
}
export const stages = {
  saved: "Salvo",
  contacted: "Contato iniciado",
  visit: "Visita marcada",
  visited: "Visitado",
  offer: "Proposta",
  rejected: "Descartado",
  bought: "Comprado",
};
export async function busy(button, fn) {
  if (button) button.disabled = true;
  try {
    await fn();
  } catch (e) {
    toast(e.message);
  } finally {
    if (button?.isConnected) button.disabled = false;
  }
}

export const fieldLabel = (key) =>
  ({
    condition: "Conservação",
    documentation: "Documentação",
    sunlight: "Luz natural",
    ventilation: "Ventilação",
    price: "Preço",
    area: "Área",
    bedrooms: "Quartos",
    bathrooms: "Banheiros",
    parking: "Vagas",
    floor: "Andar",
    elevator: "Elevador",
    condo_fee: "Condomínio",
    property_tax: "IPTU",
    tax_period: "Periodicidade do IPTU",
    metro_minutes: "Tempo até o metrô",
    neighborhood: "Bairro",
    city: "Cidade",
    address: "Endereço",
    property_type: "Tipo de imóvel",
    latitude: "Latitude",
    longitude: "Longitude",
    observed_at: "Data da observação",
    image_url: "Foto",
    url: "Link original",
    title: "Título",
    status: "Disponibilidade",
    amenities: "Comodidades",
    combined_monthly_cost: "Condomínio e IPTU combinados",
    source: "Fonte",
    external_id: "Identificador na fonte",
  })[key] || key;
export const listingTitle = (p) =>
  p.title ||
  [
    p.property_type === "house"
      ? "Casa"
      : p.property_type === "studio"
        ? "Studio"
        : "Apartamento",
    p.neighborhood || p.city,
  ]
    .filter(Boolean)
    .join(" · ");
export const listingStatus = (status) =>
  ({
    active: "Ativo",
    unavailable: "Indisponível",
    unknown: "Disponibilidade não confirmada",
  })[status] || "Disponibilidade não confirmada";
