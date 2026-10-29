import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent, ReactNode } from "react";
import { Check, ChevronDown, Search } from "lucide-react";
import { api, post } from "./api";
import type { Data, Exercise } from "./types";

export type ContentCar = {
  id: string;
  name: string;
  brand: string;
  class: string;
  skins: number;
};
export type ContentTrack = {
  id: string;
  layout: string;
  name: string;
  track_name: string;
  length_m: number | null;
  country: string;
  has_ai: boolean;
  has_map: boolean;
  online: boolean;
  track_id: string | null;
};
export type Content = {
  cars: ContentCar[];
  tracks: ContentTrack[];
  weather: { id: string; name: string }[];
};
export type Option = {
  value: string;
  label: string;
  detail?: string;
  disabled?: boolean;
};

const weatherNames: Record<string, string> = {
  "1_heavy_fog": "Gęsta mgła",
  "2_light_fog": "Lekka mgła",
  "3_clear": "Bezchmurnie",
  "4_mid_clear": "Prawie bezchmurnie",
  "5_light_clouds": "Lekkie zachmurzenie",
  "6_mid_clouds": "Umiarkowane zachmurzenie",
  "7_heavy_clouds": "Duże zachmurzenie",
};
export const weatherLabel = (id: string, fallback?: string) =>
  weatherNames[id] ?? fallback ?? id;

const fold = (text: string) =>
  text.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/ł/g, "l");

/** Rozwijana lista z wyszukiwaniem (wiele słów, bez polskich znaków) i obsługą klawiatury. */
export function SearchSelect({
  label,
  value,
  options,
  onChange,
  placeholder = "Wybierz…",
  hint,
}: {
  label: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  placeholder?: string;
  hint?: string;
}) {
  const [open, setOpen] = useState(false),
    [query, setQuery] = useState(""),
    [active, setActive] = useState(0);
  const root = useRef<HTMLDivElement>(null),
    input = useRef<HTMLInputElement>(null),
    list = useRef<HTMLUListElement>(null);
  const id = useId();
  const selected = options.find((o) => o.value === value);
  const filtered = useMemo(() => {
    const words = fold(query).split(/\s+/).filter(Boolean);
    return options
      .filter((o) =>
        words.every((w) =>
          fold(`${o.label} ${o.detail ?? ""} ${o.value}`).includes(w),
        ),
      )
      .slice(0, 300);
  }, [options, query]);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(
      Math.max(
        0,
        options.findIndex((o) => o.value === value),
      ),
    );
    setTimeout(() => input.current?.focus(), 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => {
    list.current
      ?.querySelector(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);
  function choose(option?: Option) {
    if (!option || option.disabled) return;
    onChange(option.value);
    setOpen(false);
  }
  function keys(e: KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(filtered[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    }
  }
  return (
    <div className="search-select" ref={root}>
      <span className="ss-label">{label}</span>
      <button
        type="button"
        className="ss-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {selected ? (
          <span className="ss-value">
            <b>{selected.label}</b>
            {selected.detail && <small>{selected.detail}</small>}
          </span>
        ) : (
          <span className="ss-placeholder">{placeholder}</span>
        )}
        <ChevronDown size={15} />
      </button>
      {hint && <span className="ss-hint">{hint}</span>}
      {open && (
        <div className="ss-popover">
          <div className="ss-search">
            <Search size={14} />
            <input
              ref={input}
              role="combobox"
              aria-expanded
              aria-controls={id}
              aria-activedescendant={`${id}-${active}`}
              placeholder="Szukaj…"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              onKeyDown={keys}
            />
          </div>
          <ul role="listbox" id={id} ref={list}>
            {filtered.map((o, i) => (
              <li
                key={o.value}
                id={`${id}-${i}`}
                data-index={i}
                role="option"
                aria-selected={o.value === value}
                aria-disabled={o.disabled}
                className={`${i === active ? "active" : ""} ${o.disabled ? "disabled" : ""}`}
                onMouseDown={(e) => {
                  e.preventDefault();
                  choose(o);
                }}
                onMouseEnter={() => setActive(i)}
              >
                <span>
                  {o.label}
                  {o.detail && <small>{o.detail}</small>}
                </span>
                {o.value === value && <Check size={14} />}
              </li>
            ))}
            {!filtered.length && <li className="ss-empty">Brak wyników</li>}
          </ul>
          <div className="ss-count">
            {filtered.length} z {options.length}
          </div>
        </div>
      )}
    </div>
  );
}

/** Dane scenariusza z formularza (tworzenie, edycja, szybki przejazd). */
export type ScenarioBody = {
  title: string;
  track_id: string;
  car: string;
  mode: string;
  duration: number;
  hardware_profile: { degrees: number; strength: number } | null;
  conditions: {
    weather: string;
    air_temp: number;
    road_temp: number;
    grip: number;
    rain: number;
    time: string;
  };
};

export function useContent(enabled = true) {
  const [content, setContent] = useState<Content | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!enabled) return;
    api<Content>("/content")
      .then(setContent)
      .catch((e: Error) => setError(e.message));
  }, [enabled]);
  return { content, error };
}

export const carOptions = (cars: ContentCar[]): Option[] =>
  cars.map((c) => ({
    value: c.id,
    label: c.name,
    detail: [c.brand, c.class, c.id].filter(Boolean).join(" · "),
  }));

function trackDetail(t: ContentTrack) {
  const map = t.track_id
    ? "mapa w systemie"
    : t.has_ai
      ? "mapa zostanie pobrana"
      : "brak linii AI – niedostępny";
  return [
    t.country,
    t.length_m ? `${(t.length_m / 1000).toFixed(2)} km` : "",
    map,
  ]
    .filter(Boolean)
    .join(" · ");
}

/** Kreator scenariusza: auto, tor z wariantem i pogoda wybierane z gry stanowisk.
 *
 * `initial` - edycja istniejącego scenariusza; `quick` - szybki przejazd (bez nazwy, trybu i profilu DD,
 * a `extra` dokłada uczestników sesji).
 */
export function ExerciseForm({
  data,
  onSubmit,
  onClose,
  initial,
  quick = false,
  extra,
  submitLabel,
  note,
}: {
  data: Data;
  onSubmit: (body: ScenarioBody) => Promise<unknown>;
  onClose: () => void;
  initial?: Exercise;
  quick?: boolean;
  extra?: ReactNode;
  submitLabel?: string;
  note?: ReactNode;
}) {
  const { content, error: loadError } = useContent();
  const [v, setV] = useState({
    title: initial?.title ?? "",
    car: initial?.car ?? "",
    track: initial ? `track:${initial.track_id}` : "",
    weather: initial?.conditions.weather ?? "3_clear",
    time: initial?.conditions.time ?? "13:00",
    duration: String(initial?.duration ?? (quick ? 20 : 15)),
    air_temp: String(initial?.conditions.air_temp ?? 22),
    road_temp: String(initial?.conditions.road_temp ?? 29),
    grip: String(Math.round((initial?.conditions.grip ?? 1) * 100)),
    rain: String(Math.round((initial?.conditions.rain ?? 0) * 100)),
    mode: initial?.mode ?? "either",
    profile: initial?.hardware_profile ? "on" : "off",
    degrees: String(initial?.hardware_profile?.degrees ?? 900),
    strength: String(initial?.hardware_profile?.strength ?? 15),
  });
  // Przy edycji tor jest znany po identyfikatorze; po wczytaniu katalogu gry wybieramy jego wpis z listy.
  useEffect(() => {
    if (!initial || !content) return;
    const game = content.tracks.find((t) => t.track_id === initial.track_id);
    if (game)
      setV((old) =>
        old.track === `track:${initial.track_id}`
          ? { ...old, track: `game:${game.id}|${game.layout}` }
          : old,
      );
  }, [content, initial]);
  const [titleTouched, setTitleTouched] = useState(!!initial),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const set = (key: keyof typeof v, value: string) =>
    setV((old) => ({ ...old, [key]: value }));
  const fromGame = !!content && content.tracks.length > 0;
  const trackOptions: Option[] = useMemo(() => {
    if (!content) return [];
    const options: Option[] = content.tracks.map((t) => ({
      value: `game:${t.id}|${t.layout}`,
      label: t.name,
      detail: trackDetail(t),
      disabled: !t.track_id && !t.has_ai,
    }));
    const known = new Set(content.tracks.map((t) => t.track_id));
    for (const t of data.tracks.filter((t) => t.source !== "demo" || !fromGame))
      if (!known.has(t.id))
        options.push({
          value: `track:${t.id}`,
          label: t.name,
          detail: `${t.layout || "pełna pętla"} · zaimportowany · ${t.version}`,
        });
    return options;
  }, [content, data.tracks, fromGame]);
  const cars = content?.cars ?? [];
  const weather = (
    content?.weather.length
      ? content.weather
      : Object.keys(weatherNames).map((id) => ({ id, name: id }))
  ).map((w) => ({
    value: w.id,
    label: weatherLabel(w.id, w.name),
    detail: w.id,
  }));
  const pickedTrack = trackOptions.find((o) => o.value === v.track);
  const pickedCar = cars.find((c) => c.id === v.car);
  const rain = Number(v.rain);
  const suggested = [
    pickedTrack?.label,
    pickedCar?.name ?? v.car,
    rain > 0 ? "deszcz" : "",
  ]
    .filter(Boolean)
    .join(" · ");
  const title = titleTouched ? v.title : suggested;

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    if (!v.track) return setError("Wybierz tor.");
    if (!v.car) return setError("Wybierz samochód.");
    if (!quick && title.trim().length < 2)
      return setError("Podaj nazwę scenariusza.");
    try {
      let trackId = "";
      if (v.track.startsWith("track:")) trackId = v.track.slice(6);
      else {
        const [id, layout] = v.track.slice(5).split("|");
        const known = content?.tracks.find(
          (t) => t.id === id && t.layout === layout,
        )?.track_id;
        if (known) trackId = known;
        else {
          setBusy("Pobieranie mapy toru ze stanowiska…");
          trackId = (
            await post<{ id: string }>("/content/tracks", {
              track: id,
              layout,
            })
          ).id;
        }
      }
      setBusy(quick ? "Zlecanie przygotowania…" : "Zapisywanie…");
      await onSubmit({
        title: title.trim(),
        track_id: trackId,
        car: v.car,
        mode: v.mode,
        duration: Number(v.duration),
        hardware_profile:
          v.profile === "on"
            ? { degrees: Number(v.degrees), strength: Number(v.strength) }
            : null,
        conditions: {
          weather: v.weather,
          air_temp: Number(v.air_temp),
          road_temp: Number(v.road_temp),
          grip: Number(v.grip) / 100,
          rain: rain / 100,
          time: v.time,
        },
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy("");
    }
  }
  const num = (
    key: keyof typeof v,
    label: string,
    min: number,
    max: number,
    type = "number",
  ) => (
    <label>
      {label}
      <input
        type={type}
        min={type === "number" ? min : undefined}
        max={type === "number" ? max : undefined}
        required
        value={v[key]}
        onChange={(e) => set(key, e.target.value)}
      />
    </label>
  );
  return (
    <form onSubmit={save}>
      {loadError && <div className="notice warning">{loadError}</div>}
      {content && !fromGame && (
        <div className="notice">
          Żadne stanowisko nie przesłało jeszcze listy aut i torów z gry.
          Uruchom agenta na stanowisku albo wybierz tor zaimportowany ręcznie.
        </div>
      )}
      <SearchSelect
        label="Tor i wariant"
        value={v.track}
        options={trackOptions}
        onChange={(value) => set("track", value)}
        placeholder={content ? "Wybierz tor…" : "Wczytywanie torów…"}
      />
      {fromGame ? (
        <SearchSelect
          key="car"
          label="Samochód"
          value={v.car}
          options={carOptions(cars)}
          onChange={(value) => set("car", value)}
          placeholder="Wybierz samochód…"
        />
      ) : (
        <label>
          Identyfikator samochodu w grze
          <input
            required
            value={v.car}
            onChange={(e) => set("car", e.target.value)}
          />
        </label>
      )}
      {!quick && (
        <label>
          Nazwa scenariusza
          <input
            required
            minLength={2}
            maxLength={150}
            value={title}
            placeholder="Uzupełni się po wyborze toru i auta"
            onChange={(e) => {
              setTitleTouched(true);
              set("title", e.target.value);
            }}
          />
        </label>
      )}
      <div className="form-grid">
        <SearchSelect
          label="Niebo (pakiet pogody z gry)"
          value={v.weather}
          options={weather}
          onChange={(value) => set("weather", value)}
        />
        {num("rain", "Deszcz na starcie (%)", 0, 100)}
        {num("time", "Pora dnia", 0, 0, "time")}
        {num("duration", "Długość sesji (min)", 1, 180)}
        {num("air_temp", "Temperatura powietrza (°C)", -10, 50)}
        {num("road_temp", "Temperatura toru (°C)", -10, 80)}
        {num("grip", "Przyczepność (%)", 50, 100)}
        {!quick && (
          <label>
            Tryb
            <select
              value={v.mode}
              onChange={(e) => set("mode", e.target.value)}
            >
              <option value="either">Indywidualny i grupowy</option>
              <option value="individual">Indywidualny</option>
              <option value="multiplayer">Grupowy</option>
            </select>
          </label>
        )}
      </div>
      <p className="muted">
        Deszcz na starcie i zmiany pogody podczas jazdy wymagają na stanowisku
        Custom Shaders Patch z WeatherFX. Godzina 08:00–18:00.
      </p>
      {!quick && (
        <label>
          Profil bazy wymagany w ćwiczeniu
          <select
            value={v.profile}
            onChange={(e) => set("profile", e.target.value)}
          >
            <option value="off">Zachowaj bieżący profil stanowiska</option>
            <option value="on">Zastosuj i potwierdź wskazany profil</option>
          </select>
        </label>
      )}
      {!quick && v.profile === "on" && (
        <div className="form-grid">
          {num("degrees", "Zakres obrotu (°)", 180, 1440)}
          {num("strength", "Siła (%)", 0, 100)}
        </div>
      )}
      {note}
      {extra}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="dialog-actions">
        <button type="button" className="button secondary" onClick={onClose}>
          Anuluj
        </button>
        <button className="button" disabled={!!busy}>
          {busy || submitLabel || "Zapisz scenariusz"}
          <Check size={15} />
        </button>
      </div>
    </form>
  );
}
