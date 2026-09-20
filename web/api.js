let token = sessionStorage.getItem("radar-token");
export function setToken(value) {
  token = value;
  value
    ? sessionStorage.setItem("radar-token", value)
    : sessionStorage.removeItem("radar-token");
}
export async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(`/api${path}`, { ...options, headers });
  if (response.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("session-expired"));
  }
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Não foi possível concluir a solicitação." }));
    throw Error(
      typeof error.detail === "string"
        ? error.detail
        : Array.isArray(error.detail)
          ? error.detail
              .map(
                (x) =>
                  `${(x.loc || []).filter((k) => k !== "body").join(".")}: ${x.msg || "Valor inválido"}`,
              )
              .join("; ")
          : "Não foi possível concluir a solicitação.",
    );
  }
  return response.status === 204 ? null : response.json();
}
export async function download(path, name) {
  const r = await fetch(`/api${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!r.ok)
    throw Error(
      "Não foi possível baixar o arquivo. Entre novamente e tente de novo.",
    );
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export const hasSession = () => !!token;
