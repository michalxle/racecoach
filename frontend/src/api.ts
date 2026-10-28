export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const message =
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((x: { msg: string }) => x.msg).join("; ")
          : "Nie udało się wykonać operacji";
    throw new ApiError(message, response.status);
  }
  return response.json();
}
export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
export function lapTime(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "—";
  const milliseconds = Math.round(value * 1000);
  const mins = Math.floor(milliseconds / 60000);
  return `${mins}:${((milliseconds % 60000) / 1000).toFixed(3).padStart(6, "0")}`;
}
export function delta(value: number | null | undefined) {
  if (value == null) return "—";
  const rounded =
    (Math.sign(value) * Math.round(Math.abs(value) * 1000)) / 1000;
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(3)} s`;
}
export function date(value: number) {
  return new Intl.DateTimeFormat("pl-PL", {
    timeZone: "Europe/Warsaw",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value * 1000));
}
export const statusNames: Record<string, string> = {
  idle: "Gotowe",
  live: "W trakcie jazdy",
  paused: "Pauza",
  error: "Wymaga uwagi",
  preparing: "Przygotowanie",
  ready: "Gotowe do startu",
  starting: "Uruchamianie",
  running: "W trakcie",
  stopping: "Zatrzymywanie",
  completed: "Zakończona",
  interrupted: "Przerwana",
  failed: "Błąd",
  attention: "Wymaga uwagi",
  planned: "Zaplanowana",
  passed: "Zaliczona",
  repeat: "Do powtórzenia",
  skipped: "Pominięta",
  queued: "Zlecono",
  accepted: "Przyjęto",
  succeeded: "Potwierdzono",
  rejected: "Odrzucono",
  expired: "Wygasło",
  unknown: "Wynik nieznany",
};
