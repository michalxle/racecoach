import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Flag,
  Gauge,
  LayoutDashboard,
  LogOut,
  Map,
  Monitor,
  MoreHorizontal,
  Play,
  Plus,
  Radio,
  Settings,
  SlidersHorizontal,
  Square,
  Target,
  Timer,
  TrendingUp,
  Trophy,
  MessageSquare,
  Layers,
  Users,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { ApiError, api, date, delta, lapTime, post, statusNames } from "./api";
import { ExerciseForm } from "./content";
import { AttemptCoach, Classification, CoachLive, Rankings } from "./coaching";
import type { Content } from "./content";
import type {
  Analysis,
  Attempt,
  Command,
  Data,
  Exercise,
  Lap,
  Plan,
  PlanItem,
  Run,
  Station,
  Track,
  User,
} from "./types";
import {
  carColors,
  DeltaValue,
  Meter,
  nearest,
  TelemetryChart,
  TrackMap,
} from "./visuals";
import type { MapCar } from "./visuals";

type Page =
  | "overview"
  | "stations"
  | "trainees"
  | "plans"
  | "exercises"
  | "attempts"
  | "analysis"
  | "rankings"
  | "settings";
type Modal = {
  kind:
    | "trainee"
    | "plan"
    | "item"
    | "exercise"
    | "run"
    | "quick"
    | "profile"
    | "pair"
    | "import"
    | "review"
    | "weather"
    | "message";
  id?: string;
};
const empty: Data = {
  trainees: [],
  plans: [],
  stations: [],
  exercises: [],
  tracks: [],
  attempts: [],
  runs: [],
  commands: [],
  carNames: {},
};
const navigation = [
  { id: "overview", name: "Przegląd", icon: LayoutDashboard },
  { id: "stations", name: "Stanowiska", icon: Monitor },
  { id: "trainees", name: "Kursanci", icon: Users },
  { id: "plans", name: "Plany szkolenia", icon: ClipboardList },
  { id: "exercises", name: "Scenariusze", icon: Flag },
  { id: "attempts", name: "Przejazdy", icon: Timer },
  { id: "analysis", name: "Analiza przejazdu", icon: Activity },
  { id: "rankings", name: "Rankingi", icon: Trophy },
  { id: "settings", name: "Integracje i dziennik", icon: Settings },
] as const;
const modeName = (value: string) =>
  value === "individual"
    ? "Indywidualna"
    : value === "multiplayer"
      ? "Grupowa"
      : "Oba tryby";
const weatherNames: Record<string, string> = {
  "1_heavy_fog": "Gęsta mgła",
  "2_light_fog": "Lekka mgła",
  "3_clear": "Bezchmurnie",
  "4_mid_clear": "Prawie bezchmurnie",
  "5_light_clouds": "Lekkie zachmurzenie",
  "6_mid_clouds": "Umiarkowane zachmurzenie",
  "7_heavy_clouds": "Duże zachmurzenie",
};

/** Czytelna nazwa pakietu pogody AC (np. 3_clear → Bezchmurnie). */
const weatherName = (id: string) =>
  weatherNames[id] ??
  (id
    .replace(/^(sol|pure)_?\d*_?/i, "")
    .replace(/_/g, " ")
    .trim() ||
    id);

function Badge({ status, label }: { status: string; label?: string }) {
  return (
    <span className={`badge badge-${status}`}>
      <i />
      {label || statusNames[status] || status}
    </span>
  );
}
function Initials({ name }: { name: string }) {
  return (
    <span className="avatar">
      {name
        .split(" ")
        .slice(0, 2)
        .map((x) => x[0])
        .join("")}
    </span>
  );
}
function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Target size={30} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}
function Button({
  children,
  onClick,
  secondary = false,
  disabled = false,
}: {
  children: ReactNode;
  onClick: () => void;
  secondary?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      className={secondary ? "button secondary" : "button"}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
function PageIntro({
  eyebrow,
  title,
  description,
  children,
}: {
  eyebrow: string;
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="page-intro">
      <div>
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="intro-actions">{children}</div>
    </div>
  );
}

export default function App() {
  const [session, setSession] = useState<User | null | undefined>(undefined),
    [meta, setMeta] = useState<{
      demo: boolean;
      weather_bridge?: boolean;
      demo_login?: { email: string; password: string } | null;
    }>({ demo: false });
  const [page, setPage] = useState<Page>("overview"),
    [data, setData] = useState<Data>(empty),
    [modal, setModal] = useState<Modal | null>(null);
  const [toast, setToast] = useState<{ text: string; error?: boolean } | null>(
      null,
    ),
    [connected, setConnected] = useState(true),
    [attemptId, setAttemptId] = useState(""),
    [secret, setSecret] = useState<{ name: string; token: string } | null>(
      null,
    );
  const [pending, setPending] = useState(false);
  const carNames = useRef<Record<string, string> | null>(null);
  const refresh = useCallback(async () => {
    if (!session) return;
    try {
      if (!carNames.current)
        carNames.current = await api<Content>("/content")
          .then((c) => Object.fromEntries(c.cars.map((x) => [x.id, x.name])))
          .catch(() => null);
      const privileged = session.role !== "trainee";
      const [
        trainees,
        plans,
        stations,
        exercises,
        tracks,
        attempts,
        runs,
        commands,
      ] = await Promise.all([
        api<Data["trainees"]>("/trainees"),
        api<Plan[]>("/plans"),
        privileged ? api<Station[]>("/stations") : Promise.resolve([]),
        api<Exercise[]>("/exercises"),
        api<Track[]>("/tracks"),
        api<Attempt[]>("/attempts"),
        privileged ? api<Run[]>("/runs") : Promise.resolve([]),
        privileged ? api<Command[]>("/commands") : Promise.resolve([]),
      ]);
      setData({
        trainees,
        plans,
        stations,
        exercises,
        tracks,
        attempts,
        runs,
        commands,
        carNames: carNames.current ?? {},
      });
      setConnected(true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        setSession(null);
        setData(empty);
      }
      setConnected(false);
    }
  }, [session]);
  useEffect(() => {
    api<typeof meta>("/meta")
      .then(setMeta)
      .catch(() => {});
    api<User>("/auth/me")
      .then(setSession)
      .catch(() => setSession(null));
  }, []);
  useEffect(() => {
    if (!session) return;
    refresh();
    const timer = setInterval(refresh, 1500);
    return () => clearInterval(timer);
  }, [refresh, session]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 8000);
    return () => clearTimeout(timer);
  }, [toast]);
  function openAnalysis(id: string) {
    setAttemptId(id);
    setPage("analysis");
  }
  async function action(
    path: string,
    body: unknown = {},
    message = "Operacja została zlecona",
  ) {
    setPending(true);
    try {
      await post(path, body);
      setToast({ text: message });
      await refresh();
    } catch (e) {
      setToast({ text: (e as Error).message, error: true });
    } finally {
      setPending(false);
    }
  }
  async function submit(kind: string, body: unknown, id?: string) {
    let result: unknown;
    const endpoints: Record<string, string> = {
      trainee: "/trainees",
      plan: "/plans",
      item: `/plans/${id}/items`,
      exercise: "/exercises",
      run: "/runs",
      profile: `/stations/${id}/profile`,
      pair: "/stations",
      import: "/tracks",
      review: `/attempts/${id}/review`,
      weather: `/runs/${id}/weather`,
      message: `/stations/${id}/message`,
    };
    if (kind === "exercise" && id) {
      const edited = await api<{ new_revision: boolean }>(`/exercises/${id}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      await refresh();
      setModal(null);
      setToast({
        text: edited.new_revision
          ? "Zapisano nową rewizję. Poprzednia wersja (z historią przejazdów) jest w archiwum, a otwarte pozycje planów przeszły na nową."
          : "Scenariusz zaktualizowany.",
      });
      return;
    }
    result = await post(
      kind === "quick" ? "/runs/quick" : endpoints[kind],
      body,
    );
    if (kind === "pair") setSecret(result as { name: string; token: string });
    if (kind === "run" || kind === "quick") setPage("stations");
    await refresh();
    setModal(null);
    setToast({
      text:
        kind === "run" || kind === "quick"
          ? "Przygotowanie zlecone. Poczekaj na gotowość stanowisk, a następnie wybierz Start."
          : kind === "profile"
            ? "Profil wysłany. Wynik odczytu zwrotnego zobaczysz w dzienniku."
            : kind === "message"
              ? "Wiadomość wysłana – pojawi się w nakładce kierowcy."
              : "Zmiany zostały zapisane.",
    });
  }
  if (session === undefined)
    return (
      <div className="boot">
        <div className="brand-mark">
          R<span>C</span>
        </div>
        <p>Łączenie z centrum szkolenia…</p>
      </div>
    );
  if (!session) return <Login demo={meta.demo} onLogin={setSession} />;
  const privileged = session.role !== "trainee";
  const allowed = privileged
    ? navigation
    : navigation.filter((n) =>
        ["overview", "plans", "attempts", "analysis", "rankings"].includes(
          n.id,
        ),
      );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("overview");
          }}
        >
          <div className="brand-mark">
            R<span>C</span>
          </div>
          <div>
            RaceCoach<small>DRIVER DEVELOPMENT</small>
          </div>
        </a>
        <div className="sidebar-label">CENTRUM SZKOLENIA</div>
        <nav aria-label="Nawigacja główna">
          {allowed.map((n) => (
            <button
              key={n.id}
              className={page === n.id ? "nav-item active" : "nav-item"}
              onClick={() => setPage(n.id)}
            >
              <n.icon size={18} />
              {n.name}
              {n.id === "stations" && <span>{data.stations.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="workspace">
            <span className={`connection-dot ${connected ? "" : "offline"}`} />
            <div>
              {connected ? "Centrala dostępna" : "Brak połączenia"}
              <small>
                {meta.demo
                  ? "Środowisko demonstracyjne"
                  : "Sieć lokalna · RaceCoach"}
              </small>
            </div>
          </div>
          <div className="user-block">
            <Initials name={session.name} />
            <div>
              <strong>{session.name}</strong>
              <small>
                {privileged ? "Panel instruktora" : "Panel kursanta"}
              </small>
            </div>
            <button
              className="icon-button"
              aria-label="Wyloguj"
              onClick={async () => {
                await post("/auth/logout");
                setSession(null);
                setData(empty);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Centrum szkolenia <ChevronRight size={14} />
            <strong>{navigation.find((n) => n.id === page)?.name}</strong>
          </div>
          <div className="topbar-right">
            <span className="today">
              {new Intl.DateTimeFormat("pl-PL", {
                timeZone: "Europe/Warsaw",
                day: "numeric",
                month: "long",
                year: "numeric",
              }).format(new Date())}
            </span>
            <span className="live-label">
              <Radio size={14} />
              {connected ? "Połączenie aktywne" : "Rozłączono"}
            </span>
            <button
              className="icon-button mobile-logout"
              aria-label="Wyloguj"
              onClick={async () => {
                await post("/auth/logout");
                setSession(null);
                setData(empty);
              }}
            >
              <LogOut size={17} />
            </button>
          </div>
        </header>
        <main>
          {meta.demo && (
            <div className="demo-banner">
              <span>
                <span className="demo-tag">DEMO</span>Stanowiska, tor i
                telemetria są symulowane. Sesje demonstracyjne przebiegają w
                przyspieszonym czasie.
              </span>
            </div>
          )}
          {!connected && (
            <div className="notice error">
              Brak odpowiedzi centrali. Wyświetlane informacje mogą być
              nieaktualne; sprawdź połączenie przed zlecaniem operacji.
            </div>
          )}
          {page === "overview" && (
            <Overview
              data={data}
              privileged={privileged}
              onModal={setModal}
              onPage={setPage}
              onAnalysis={openAnalysis}
            />
          )}
          {page === "stations" && privileged && (
            <Stations
              data={data}
              onModal={setModal}
              action={action}
              pending={pending}
              weatherAvailable={meta.demo || !!meta.weather_bridge}
            />
          )}
          {page === "trainees" && privileged && (
            <Trainees
              data={data}
              onModal={setModal}
              onPage={setPage}
              onAnalysis={openAnalysis}
            />
          )}
          {page === "plans" && (
            <Plans
              data={data}
              privileged={privileged}
              onModal={setModal}
              refresh={refresh}
              notify={(text) => setToast({ text })}
            />
          )}
          {page === "exercises" && privileged && (
            <Exercises
              data={data}
              onModal={setModal}
              action={action}
              pending={pending}
              refresh={refresh}
              notify={(text, error) => setToast({ text, error })}
            />
          )}
          {page === "attempts" && (
            <Attempts
              data={data}
              privileged={privileged}
              onAnalysis={openAnalysis}
              onModal={setModal}
            />
          )}
          {page === "analysis" && (
            <Report
              data={data}
              selectedId={attemptId}
              setSelectedId={setAttemptId}
              privileged={privileged}
              onModal={setModal}
              pending={pending}
              onReference={(attempt, lap) =>
                action(
                  `/exercises/${attempt.scenario.exercise_id}/reference`,
                  { attempt_id: attempt.id, lap },
                  "Przejazd zapisany jako wzorzec tego ćwiczenia.",
                )
              }
            />
          )}
          {page === "rankings" && (
            <Rankings data={data} privileged={privileged} selfId={session.id} />
          )}
          {page === "settings" && privileged && (
            <Integrations data={data} onModal={setModal} />
          )}
        </main>
        <footer>
          RaceCoach <span>System szkolenia techniki jazdy · v0.1</span>
        </footer>
      </div>
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          {toast.error ? <Activity size={18} /> : <CheckCircle2 size={18} />}
          <span>{toast.text}</span>
          <button
            className="icon-button"
            aria-label="Zamknij komunikat"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {modal && (
        <FormModal
          modal={modal}
          data={data}
          onClose={() => setModal(null)}
          onSubmit={submit}
        />
      )}
      {secret && (
        <Dialog
          title="Stanowisko zarejestrowane"
          subtitle="Token jest pokazywany tylko teraz."
          onClose={() => setSecret(null)}
        >
          <p>
            Ustaw tę wartość jako <code>RACECOACH_AGENT_TOKEN</code> na
            komputerze {secret.name}.
          </p>
          <textarea
            aria-label="Token stanowiska"
            readOnly
            rows={3}
            value={secret.token}
          />
          <p className="muted">
            Instrukcja uruchomienia agenta znajduje się w dokumentacji
            repozytorium. Token daje dostęp wyłącznie do tego stanowiska.
          </p>
          <button className="button" onClick={() => setSecret(null)}>
            Zapisano token
          </button>
        </Dialog>
      )}
    </div>
  );
}

function Login({
  demo,
  onLogin,
}: {
  demo: boolean;
  onLogin: (u: User) => void;
}) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function login(e?: FormEvent, isDemo = false) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      onLogin(
        await post<User>("/auth/login", {
          email: isDemo ? "instruktor@demo.local" : email,
          password: isDemo ? "Trening2026!" : password,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login-shell">
      <section className="login-story">
        <a className="brand" href="#">
          <div className="brand-mark">
            R<span>C</span>
          </div>
          <div>
            RaceCoach<small>DRIVER DEVELOPMENT</small>
          </div>
        </a>
        <div className="login-copy">
          <div className="eyebrow">KAŻDY PRZEJAZD MA ZNACZENIE</div>
          <h1>
            Technika.
            <br />
            Powtarzalność.
            <br />
            <em>Postęp.</em>
          </h1>
          <p>
            Jedno centrum zarządzania stanowiskami i rozwojem Twoich kursantów.
          </p>
          <div className="login-marks">
            <span>
              <Monitor size={17} />
              Stanowiska
            </span>
            <span>
              <ClipboardList size={17} />
              Plany
            </span>
            <span>
              <Activity size={17} />
              Telemetria
            </span>
          </div>
        </div>
        <div className="login-bottom">
          ASSETTO CORSA <i /> DIY DIRECT DRIVE
        </div>
      </section>
      <section className="login-form">
        <div>
          <div className="eyebrow">CENTRUM SZKOLENIA</div>
          <h2>Witaj w RaceCoach</h2>
          <p className="muted">Zaloguj się, aby kontynuować szkolenie.</p>
          <form onSubmit={(e) => login(e)}>
            <label>
              E-mail
              <input
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="instruktor@local"
              />
            </label>
            <label>
              Hasło
              <input
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}
            <button className="button full" disabled={busy}>
              {busy ? "Logowanie…" : "Zaloguj się"}
              <ArrowRight size={17} />
            </button>
          </form>
          {demo && (
            <div className="demo-login">
              <span className="demo-tag">ŚRODOWISKO DEMO</span>
              <p>
                Sprawdź dwa stanowiska, plany i przykładowe przejazdy bez
                sprzętu.
              </p>
              <button
                className="button secondary full"
                disabled={busy}
                onClick={() => login(undefined, true)}
              >
                Otwórz demonstrację
                <ArrowRight size={16} />
              </button>
            </div>
          )}
          <p className="login-help">
            Pierwsze dane instruktora są zapisane lokalnie w pliku{" "}
            <code>
              {demo ? ".local/bootstrap.json" : ".local/live/bootstrap.json"}
            </code>{" "}
            (lub w wybranym folderze danych).
          </p>
        </div>
      </section>
    </div>
  );
}

function Overview({
  data,
  privileged,
  onModal,
  onPage,
  onAnalysis,
}: {
  data: Data;
  privileged: boolean;
  onModal: (m: Modal) => void;
  onPage: (p: Page) => void;
  onAnalysis: (id: string) => void;
}) {
  const online = data.stations.filter((s) => s.online).length,
    running = data.stations.filter((s) => s.state.game === "live").length,
    complete = data.attempts.filter((a) => a.status === "completed").length;
  const items = data.plans.flatMap((p) => p.items),
    passed = items.filter((i) => i.status === "passed").length,
    track = data.tracks[0];
  return (
    <>
      <PageIntro
        eyebrow="TWOJE CENTRUM DOWODZENIA"
        title={
          privileged
            ? "Dobry trening zaczyna się tutaj."
            : "Twój kolejny krok za kierownicą."
        }
        description={
          privileged
            ? "Stanowiska, kursanci i postępy — w jednym miejscu."
            : "Sprawdź plan, przejrzyj próby i zobacz, gdzie zyskujesz czas."
        }
      >
        {privileged && (
          <Button onClick={() => onModal({ kind: "run" })}>
            <Play size={16} />
            Przygotuj sesję
          </Button>
        )}
      </PageIntro>
      <div className="stats-grid">
        {[
          {
            label: privileged ? "Stanowiska online" : "Aktywne plany",
            value: privileged
              ? `${online} / ${data.stations.length}`
              : data.plans.length,
            icon: Monitor,
            detail: privileged
              ? `${running} w trakcie jazdy`
              : "Program dopasowany do Ciebie",
          },
          {
            label: "Kursanci",
            value: data.trainees.length,
            icon: Users,
            detail: privileged
              ? "Zarejestrowane konta"
              : "Twoje konto szkoleniowe",
          },
          {
            label: "Zapisane przejazdy",
            value: complete,
            icon: Flag,
            detail: "Historia i dane do porównań",
          },
          {
            label: "Zaliczone sesje planu",
            value: `${passed} / ${items.length}`,
            icon: TrendingUp,
            detail: "Ocena zatwierdzona przez instruktora",
          },
        ].map((s, i) => (
          <div className="stat-card" key={s.label}>
            <div className="stat-label">
              {s.label}
              <s.icon size={18} />
            </div>
            <div className="stat-value">{s.value}</div>
            <div className="stat-detail">
              <span className={i === 0 ? "green-dot" : ""} />
              {s.detail}
            </div>
          </div>
        ))}
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">
                {privileged ? "PODGLĄD NA ŻYWO" : "PROGRAM SZKOLENIA"}
              </span>
              <h2>{privileged ? "Stanowiska treningowe" : "Twoje plany"}</h2>
            </div>
            <button
              className="text-button"
              onClick={() => onPage(privileged ? "stations" : "plans")}
            >
              Zobacz wszystkie
              <ArrowRight size={15} />
            </button>
          </div>
          {privileged ? (
            <div className="station-overview">
              {data.stations.map((s) => (
                <div key={s.id} className="station-row">
                  <div
                    className={`station-icon ${s.state.game === "live" ? "active" : ""}`}
                  >
                    <Monitor size={23} />
                  </div>
                  <div className="station-row-name">
                    <strong>{s.name}</strong>
                    <span>
                      {s.attempt?.trainee_name || "Oczekuje na kursanta"}
                    </span>
                  </div>
                  <Badge
                    status={s.online ? s.state.game : "error"}
                    label={!s.online ? "Offline" : undefined}
                  />
                  <button
                    className="icon-button"
                    aria-label={`Otwórz ${s.name}`}
                    onClick={() => onPage("stations")}
                  >
                    <ChevronRight size={18} />
                  </button>
                </div>
              ))}
              {!data.stations.length && (
                <Empty title="Dodaj pierwsze stanowisko">
                  Zarejestruj agenta w zakładce Stanowiska.
                </Empty>
              )}
            </div>
          ) : (
            data.plans.map((p) => (
              <div key={p.id} className="plan-overview">
                <BookOpen size={20} />
                <div>
                  <strong>{p.title}</strong>
                  <span>
                    {p.items.filter((i) => i.status === "passed").length} z{" "}
                    {p.items.length} sesji zaliczonych
                  </span>
                </div>
                <button className="text-button" onClick={() => onPage("plans")}>
                  Otwórz
                  <ArrowRight size={15} />
                </button>
              </div>
            ))
          )}
          <div className="section-divider" />
          <div className="panel-heading compact">
            <h3>Ostatnie przejazdy</h3>
            <button className="text-button" onClick={() => onPage("attempts")}>
              Historia
              <ArrowRight size={15} />
            </button>
          </div>
          <div className="recent-list">
            {data.attempts.slice(0, 4).map((a) => (
              <button
                className="recent-row"
                key={a.id}
                onClick={() => onAnalysis(a.id)}
              >
                <Initials name={a.trainee_name} />
                <div>
                  <strong>{a.trainee_name}</strong>
                  <span>{a.exercise_title}</span>
                </div>
                <div>
                  <small>{date(a.created)}</small>
                  <span className="recent-link">
                    Analiza
                    <ChevronRight size={13} />
                  </span>
                </div>
              </button>
            ))}
          </div>
        </section>
        <div className="overview-right">
          {track ? (
            <TrackMap track={track} compact />
          ) : (
            <div className="panel">
              <Empty title="Katalog torów jest pusty">
                Zaimportuj geometrię toru, aby zobaczyć mapę.
              </Empty>
            </div>
          )}
          <section className="panel next-training">
            <span className="eyebrow">ROZWÓJ KROK PO KROKU</span>
            <h2>Od danych do lepszej jazdy.</h2>
            <p>
              Porównaj punkt hamowania, przebieg gazu i tempo na każdej sekcji
              toru.
            </p>
            <button className="text-button" onClick={() => onPage("analysis")}>
              Przejdź do analizy
              <ArrowRight size={16} />
            </button>
            <div className="training-steps">
              <div>
                <span>01</span>Wybierz przejazd
              </div>
              <div>
                <span>02</span>Ustaw wzorzec
              </div>
              <div>
                <span>03</span>Znajdź obszar do poprawy
              </div>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}

function Stations({
  data,
  onModal,
  action,
  pending,
  weatherAvailable,
}: {
  data: Data;
  onModal: (m: Modal) => void;
  action: (path: string, body?: unknown, message?: string) => Promise<void>;
  pending: boolean;
  weatherAvailable: boolean;
}) {
  const activeRuns = data.runs.filter(
    (r) => !["completed", "interrupted"].includes(r.status),
  );
  return (
    <>
      <PageIntro
        eyebrow="POŁĄCZONE STANOWISKA"
        title="Gotowość pod kontrolą."
        description="Przygotuj zajęcia, sprawdź sprzęt i rozpocznij sesję po potwierdzeniu stanowisk."
      >
        <Button secondary onClick={() => onModal({ kind: "pair" })}>
          <Plus size={16} />
          Zarejestruj agenta
        </Button>
        <Button secondary onClick={() => onModal({ kind: "quick" })}>
          <Gauge size={16} />
          Szybki przejazd
        </Button>
        <Button onClick={() => onModal({ kind: "run" })}>
          <Play size={16} />
          Przygotuj sesję
        </Button>
      </PageIntro>
      {!!activeRuns.length && (
        <section className="panel run-panel">
          <div className="panel-heading">
            <h2>Aktywne sesje</h2>
            <span className="muted">
              Gotowość jest potwierdzana przez agentów
            </span>
          </div>
          {activeRuns.map((r) => (
            <div key={r.id}>
              <div className="run-row">
                <div className="run-icon">
                  <Flag size={20} />
                </div>
                <div className="run-description">
                  <strong>{r.title}</strong>
                  <span>
                    {modeName(r.mode)} ·{" "}
                    {r.participants.map((p) => p.trainee_name).join(", ")}
                  </span>
                  <div className="run-members">
                    {r.participants.map((p) => (
                      <span key={p.id}>
                        {p.station_name}: {statusNames[p.status] || p.status}
                      </span>
                    ))}
                  </div>
                  <RunTags run={r} />
                </div>
                <Badge status={r.status} />
                {r.classification && r.classification.length > 0 && (
                  <div className="run-classification">
                    <span className="eyebrow">
                      Wyścig · {r.scenario.race_laps} okr.
                    </span>
                    <Classification rows={r.classification} />
                  </div>
                )}
                <div className="row-actions">
                  {r.status === "ready" && (
                    <button
                      className="button small"
                      disabled={pending}
                      onClick={() =>
                        action(
                          `/runs/${r.id}/start`,
                          {},
                          "Start zlecony. Oczekiwanie na potwierdzenie gry.",
                        )
                      }
                    >
                      <Play size={14} />
                      Start
                    </button>
                  )}
                  <button
                    className="button secondary small"
                    disabled={pending || r.status === "stopping"}
                    onClick={() =>
                      action(
                        `/runs/${r.id}/stop`,
                        {},
                        "Zatrzymanie zlecone do stanowisk.",
                      )
                    }
                  >
                    <Square size={13} />
                    Zakończ
                  </button>
                  {r.status === "running" && (
                    <button
                      className="button secondary small"
                      onClick={() => onModal({ kind: "weather", id: r.id })}
                      disabled={
                        pending || !(r.weather_control ?? weatherAvailable)
                      }
                      title={
                        (r.weather_control ?? weatherAvailable)
                          ? undefined
                          : r.mode === "individual"
                            ? "Stanowisko nie zgłasza Custom Shaders Patch z WeatherFX; zmiana pogody podczas jazdy jest niedostępna."
                            : "Sesja grupowa wymaga mostu pogodowego serwera (RACECOACH_WEATHER_BRIDGE)."
                      }
                    >
                      Zmień warunki
                    </button>
                  )}
                </div>
              </div>
              {["starting", "running"].includes(r.status) && (
                <LiveRunMap run={r} stations={data.stations} />
              )}
            </div>
          ))}
        </section>
      )}
      <div className="station-grid">
        {data.stations.map((s) => {
          const t = s.state.telemetry,
            h = s.state.hardware;
          return (
            <section key={s.id} className="panel station-card">
              <div className="panel-heading">
                <div className="station-title">
                  <Monitor size={23} />
                  <div>
                    <h2>{s.name}</h2>
                    <span>
                      {s.simulated ? "Agent demonstracyjny" : "Agent Windows"}
                    </span>
                  </div>
                </div>
                <Badge
                  status={s.online ? s.state.game : "error"}
                  label={!s.online ? "Offline" : undefined}
                />
              </div>
              <div className="station-driver">
                {s.attempt ? (
                  <>
                    <Initials name={s.attempt.trainee_name} />
                    <div>
                      <strong>{s.attempt.trainee_name}</strong>
                      <span>Przypisany kursant</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="avatar empty-avatar">
                      <Users size={17} />
                    </div>
                    <div>
                      <strong>Stanowisko dostępne</strong>
                      <span>Przypisz kursanta podczas przygotowania sesji</span>
                    </div>
                  </>
                )}
              </div>
              <div className="station-readout">
                <div>
                  <span>Prędkość</span>
                  <strong>
                    {s.online && s.state.game === "live" && t
                      ? Math.round(t.speed)
                      : "—"}
                    <small> km/h</small>
                  </strong>
                </div>
                <div>
                  <span>Bieg</span>
                  <strong>
                    {s.online && s.state.game === "live" && t
                      ? t.gear || "N"
                      : "—"}
                  </strong>
                </div>
                <div>
                  <span>Obroty</span>
                  <strong>
                    {s.online && s.state.game === "live" && t
                      ? Math.round(t.rpm).toLocaleString("pl-PL")
                      : "—"}
                    <small> rpm</small>
                  </strong>
                </div>
              </div>
              {s.online && s.state.coach && <CoachLive coach={s.state.coach} />}
              <div className="station-inputs">
                <Meter
                  label="Gaz"
                  value={s.state.game === "live" ? t?.throttle || 0 : 0}
                  color="green"
                />
                <Meter
                  label="Hamulec"
                  value={s.state.game === "live" ? t?.brake || 0 : 0}
                />
              </div>
              <div className="hardware-summary">
                <span>
                  <span className={h?.connected ? "green-dot" : "gray-dot"} />
                  {h?.firmware ||
                    (h?.connected
                      ? "Baza podłączona"
                      : "Brak połączonej bazy DD")}
                </span>
                <strong>
                  {h?.degrees ?? "—"}° <i /> {h?.strength ?? "—"}%
                </strong>
              </div>
              {(s.state.error || h?.error) && (
                <div className="notice error">{s.state.error || h?.error}</div>
              )}
              {h?.controllers?.map((c) => (
                <div key={c.id} className="controller-row">
                  <span>{c.name}</span>
                  <span>
                    Osie:{" "}
                    {c.axes.map((v) => Math.round(v * 100) + "%").join(" / ")} ·
                    Przyciski: {c.buttons}
                  </span>
                </div>
              ))}
              <div className="station-card-footer">
                <span>
                  <Wifi size={13} />
                  {s.last_seen ? date(s.last_seen) : "Brak sygnału"}
                </span>
                <button
                  className="text-button"
                  disabled={
                    !s.online ||
                    s.state.game !== "idle" ||
                    !!s.attempt ||
                    !s.state.capabilities?.includes("hardware.profile")
                  }
                  onClick={() => onModal({ kind: "profile", id: s.id })}
                >
                  <SlidersHorizontal size={14} />
                  Profil DD
                </button>
                {!s.simulated && (
                  <>
                    <button
                      className="text-button"
                      disabled={!s.online}
                      onClick={() => onModal({ kind: "message", id: s.id })}
                    >
                      <MessageSquare size={14} />
                      Wiadomość
                    </button>
                    <a
                      className="text-button"
                      href={`/overlay/${encodeURIComponent(s.id)}`}
                      target="_blank"
                      rel="noreferrer"
                      title="Podgląd i układ nakładek w grze"
                    >
                      <Layers size={14} />
                      Nakładki
                    </a>
                  </>
                )}
              </div>
            </section>
          );
        })}
      </div>
      {!data.stations.length && (
        <section className="panel">
          <Empty title="Połącz pierwszego agenta">
            Token stanowiska otrzymasz po wybraniu „Zarejestruj agenta”.
          </Empty>
        </section>
      )}
    </>
  );
}

/** Cechy sesji widoczne przy aktywnej sesji: tryb grupy, kolizje, szybki przejazd. */
function RunTags({ run }: { run: Run }) {
  const s = run.scenario;
  const tags = [
    s.quick ? "Szybki przejazd" : "",
    s.virtual_race ? "Wyścig wirtualny" : "",
    run.mode === "multiplayer" && !s.virtual_race
      ? s.collisions === false
        ? "Bez kolizji"
        : "Kolizje włączone"
      : "",
    run.mode === "multiplayer" && s.show_rivals === false
      ? "Rywale ukryci na minimapie"
      : "",
    s.conditions?.rain ? `Deszcz ${Math.round(s.conditions.rain * 100)}%` : "",
  ].filter(Boolean);
  if (!tags.length) return null;
  return (
    <div className="run-tags">
      {tags.map((t) => (
        <span key={t}>{t}</span>
      ))}
    </div>
  );
}

/** Mapa toru z pozycjami wszystkich kierowców sesji (telemetria stanowisk, ok. 1 raz/s). */
function LiveRunMap({ run, stations }: { run: Run; stations: Station[] }) {
  const track = run.scenario.track;
  if (!track?.geometry?.length) return null;
  const cars: MapCar[] = run.participants.flatMap((p, i) => {
    const station = stations.find((s) => s.id === p.station_id);
    const t =
      station?.online && station.state.game === "live"
        ? station.state.telemetry
        : undefined;
    if (!t || t.x == null || t.z == null) return [];
    return [
      {
        id: p.id,
        label: p.trainee_name.split(" ")[0],
        x: t.x,
        z: t.z,
        color: carColors[i % carColors.length],
      },
    ];
  });
  return (
    <div className="live-map">
      <TrackMap
        track={track}
        compact
        cars={cars}
        caption={
          cars.length
            ? `Na torze: ${cars.length} z ${run.participants.length} · pozycje co ok. 1 s`
            : "Pozycje pojawią się po wyjeździe na tor"
        }
      />
    </div>
  );
}

function Trainees({
  data,
  onModal,
  onPage,
  onAnalysis,
}: {
  data: Data;
  onModal: (m: Modal) => void;
  onPage: (p: Page) => void;
  onAnalysis: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  return (
    <>
      <PageIntro
        eyebrow="INDYWIDUALNY ROZWÓJ"
        title="Kursanci i ich postępy."
        description="Każde konto zachowuje plan oraz historię niezależnie od stanowiska."
      >
        <Button onClick={() => onModal({ kind: "trainee" })}>
          <Plus size={16} />
          Dodaj kursanta
        </Button>
      </PageIntro>
      <section className="panel">
        <div className="panel-heading">
          <h2>
            Zarejestrowani kursanci{" "}
            <span className="count">{data.trainees.length}</span>
          </h2>
          <input
            aria-label="Szukaj kursanta"
            className="search"
            placeholder="Szukaj po imieniu lub e-mailu…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kursant</th>
                <th>Plan szkolenia</th>
                <th>Postęp</th>
                <th>Przejazdy</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.trainees
                .filter((t) =>
                  (t.name + t.email)
                    .toLowerCase()
                    .includes(search.toLowerCase()),
                )
                .map((t) => {
                  const plans = data.plans.filter((p) => p.trainee_id === t.id),
                    items = plans.flatMap((p) => p.items),
                    passed = items.filter((i) => i.status === "passed").length,
                    attempts = data.attempts.filter(
                      (a) => a.trainee_id === t.id,
                    );
                  return (
                    <tr key={t.id}>
                      <td>
                        <div className="person-cell">
                          <Initials name={t.name} />
                          <div>
                            <strong>{t.name}</strong>
                            <span>{t.email}</span>
                          </div>
                        </div>
                      </td>
                      <td>{plans[0]?.title || "Nie przypisano planu"}</td>
                      <td>
                        <div className="small-progress">
                          <span>
                            {passed} / {items.length} sesji
                          </span>
                          <div>
                            <i
                              style={{
                                width: `${items.length ? (passed / items.length) * 100 : 0}%`,
                              }}
                            />
                          </div>
                        </div>
                      </td>
                      <td>{attempts.length}</td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="text-button"
                            onClick={() => onModal({ kind: "plan", id: t.id })}
                          >
                            Dodaj plan
                            <Plus size={13} />
                          </button>
                          {attempts.length > 0 && (
                            <button
                              className="icon-button"
                              aria-label={`Analiza: ${t.name}`}
                              onClick={() => onAnalysis(attempts[0].id)}
                            >
                              <Activity size={17} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        {!data.trainees.length && (
          <Empty title="Pierwszy kursant czeka na swój plan">
            Utwórz konto, a następnie przygotuj sesje szkoleniowe.
          </Empty>
        )}
      </section>
    </>
  );
}

function Plans({
  data,
  privileged,
  onModal,
  refresh,
  notify,
}: {
  data: Data;
  privileged: boolean;
  onModal: (m: Modal) => void;
  refresh: () => Promise<void>;
  notify: (s: string) => void;
}) {
  const [selected, setSelected] = useState(""),
    [busy, setBusy] = useState(false);
  const plan = data.plans.find((p) => p.id === selected) || data.plans[0];
  async function status(item: PlanItem, value: string) {
    setBusy(true);
    try {
      await api(`/plan-items/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status: value, note: "Zmiana w panelu planu" }),
      });
      await refresh();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="PLAN → PRÓBA → POSTĘP"
        title="Szkolenie dopasowane do osoby."
        description="Zaplanuj cele, wykonaj ćwiczenie i zachowaj każdą próbę do porównania."
      >
        {privileged && (
          <Button onClick={() => onModal({ kind: "plan" })}>
            <Plus size={16} />
            Nowy plan
          </Button>
        )}
      </PageIntro>
      {data.plans.length ? (
        <div className="plans-layout">
          <aside className="plan-picker">
            {data.plans.map((p) => (
              <button
                key={p.id}
                className={
                  p.id === plan?.id ? "plan-choice selected" : "plan-choice"
                }
                onClick={() => setSelected(p.id)}
              >
                <Initials name={p.trainee_name} />
                <div>
                  <strong>{p.trainee_name}</strong>
                  <span>{p.title}</span>
                </div>
                <ChevronRight size={16} />
              </button>
            ))}
          </aside>
          <section className="panel plan-detail">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">{plan.trainee_name}</span>
                <h2>{plan.title}</h2>
              </div>
              {privileged && (
                <Button
                  secondary
                  onClick={() => onModal({ kind: "item", id: plan.id })}
                >
                  <Plus size={16} />
                  Dodaj sesję
                </Button>
              )}
            </div>
            <div className="plan-progress">
              <span>
                {plan.items.filter((i) => i.status === "passed").length} z{" "}
                {plan.items.length} sesji zaliczonych
              </span>
              <div>
                <i
                  style={{
                    width: `${plan.items.length ? (plan.items.filter((i) => i.status === "passed").length / plan.items.length) * 100 : 0}%`,
                  }}
                />
              </div>
            </div>
            <div className="plan-timeline">
              {plan.items.map((item, index) => {
                const exercise = data.exercises.find(
                    (e) => e.id === item.exercise_id,
                  ),
                  attempts = data.attempts.filter(
                    (a) => a.plan_item_id === item.id,
                  );
                return (
                  <article className="plan-session" key={item.id}>
                    <div
                      className={`timeline-number ${item.status === "passed" ? "done" : ""}`}
                    >
                      {item.status === "passed" ? (
                        <Check size={17} />
                      ) : (
                        String(index + 1).padStart(2, "0")
                      )}
                    </div>
                    <div className="plan-session-body">
                      <div className="plan-session-header">
                        <h3>{item.title}</h3>
                        <Badge status={item.status} />
                      </div>
                      <p>{item.goal}</p>
                      <div className="session-meta">
                        <span>
                          <Flag size={13} />
                          {modeName(item.mode)}
                        </span>
                        <span>
                          <Map size={13} />
                          {exercise?.track_name || "Tor"}
                        </span>
                        <span>
                          <Timer size={13} />
                          {exercise?.duration || "—"} min
                        </span>
                        {item.scheduled && <span>{item.scheduled}</span>}
                      </div>
                      <div className="criteria">
                        <Target size={15} />
                        <span>{item.criteria}</span>
                      </div>
                      <div className="plan-session-footer">
                        <span>
                          {attempts.length} zapisanych prób · rewizja{" "}
                          {item.revision}
                        </span>
                        {privileged && (
                          <select
                            aria-label={`Status: ${item.title}`}
                            value={item.status}
                            disabled={busy || item.status === "running"}
                            onChange={(e) => status(item, e.target.value)}
                          >
                            {[
                              "planned",
                              "ready",
                              "repeat",
                              "passed",
                              "skipped",
                              ...(item.status === "running" ? ["running"] : []),
                            ].map((s) => (
                              <option key={s} value={s}>
                                {statusNames[s]}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                    </div>
                  </article>
                );
              })}
              {!plan.items.length && (
                <Empty title="Rozpisz pierwsze sesje">
                  Dodaj cel, scenariusz, tryb i kryteria oceny.
                </Empty>
              )}
            </div>
          </section>
        </div>
      ) : (
        <section className="panel">
          <Empty title="Brak planów szkolenia">
            Utwórz plan dla zarejestrowanego kursanta.
          </Empty>
        </section>
      )}
    </>
  );
}

function Exercises({
  data,
  onModal,
  action,
  pending,
  refresh,
  notify,
}: {
  data: Data;
  onModal: (m: Modal) => void;
  action: (path: string, body?: unknown, message?: string) => Promise<void>;
  pending: boolean;
  refresh: () => Promise<void>;
  notify: (text: string, error?: boolean) => void;
}) {
  const [showArchived, setShowArchived] = useState(false);
  const archivedCount = data.exercises.filter((e) => e.archived).length;
  const visible = data.exercises.filter((e) => showArchived || !e.archived);
  async function remove(e: Data["exercises"][number]) {
    const history = (e.runs ?? 0) > 0;
    const question = history
      ? `Scenariusz „${e.title}” ma przejazdy lub pozycje w planach. Przenieść go do archiwum? Historia zostanie zachowana.`
      : `Usunąć scenariusz „${e.title}”? Nie ma przejazdów, więc zostanie usunięty na stałe.`;
    if (!window.confirm(question)) return;
    try {
      const result = await api<{ archived: boolean }>(`/exercises/${e.id}`, {
        method: "DELETE",
      });
      await refresh();
      notify(
        result.archived
          ? "Scenariusz przeniesiony do archiwum. Historia przejazdów została zachowana."
          : "Scenariusz usunięty.",
      );
    } catch (err) {
      notify((err as Error).message, true);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="POWTARZALNE WARUNKI"
        title="Scenariusze treningowe."
        description="Zestaw auta, toru i warunków tworzy wersję ćwiczenia przypisywaną do planu."
      >
        <Button secondary onClick={() => onModal({ kind: "import" })}>
          <ArrowDownToLine size={16} />
          Importuj tor
        </Button>
        <Button secondary onClick={() => onModal({ kind: "quick" })}>
          <Gauge size={16} />
          Szybki przejazd
        </Button>
        <Button onClick={() => onModal({ kind: "exercise" })}>
          <Plus size={16} />
          Nowy scenariusz
        </Button>
      </PageIntro>
      {archivedCount > 0 && (
        <label className="toggle-archived">
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => setShowArchived(e.target.checked)}
          />
          Pokaż archiwalne ({archivedCount})
        </label>
      )}
      <div className="exercise-grid">
        {visible.map((e) => {
          const track = data.tracks.find((t) => t.id === e.track_id);
          return (
            <section
              key={e.id}
              className={`panel exercise-card${e.archived ? " archived" : ""}`}
            >
              {track && <TrackMap track={track} compact />}
              <div className="exercise-body">
                <div className="eyebrow">
                  {e.archived ? "ARCHIWUM · " : ""}
                  {modeName(e.mode)} · REWIZJA {e.revision}
                  {e.runs ? ` · ${e.runs} SESJI` : ""}
                </div>
                <h2>{e.title}</h2>
                <p>
                  {e.track_name} · {data.carNames[e.car] ?? e.car}
                </p>
                <div className="exercise-values">
                  <div>
                    <span>Temperatura</span>
                    <strong>
                      {e.conditions.air_temp}°C / {e.conditions.road_temp}°C
                    </strong>
                  </div>
                  <div>
                    <span>Przyczepność</span>
                    <strong>{Math.round(e.conditions.grip * 100)}%</strong>
                  </div>
                  <div>
                    <span>Warunki</span>
                    <strong>
                      {weatherName(e.conditions.weather)}
                      {e.conditions.rain
                        ? ` · deszcz ${Math.round(e.conditions.rain * 100)}%`
                        : ""}
                    </strong>
                  </div>
                  <div>
                    <span>Czas sesji</span>
                    <strong>
                      {e.duration} min · {e.conditions.time}
                    </strong>
                  </div>
                </div>
                <div className="exercise-actions">
                  {e.archived ? (
                    <button
                      className="button secondary small"
                      disabled={pending}
                      onClick={() =>
                        action(
                          `/exercises/${e.id}/restore`,
                          {},
                          "Scenariusz przywrócony z archiwum.",
                        )
                      }
                    >
                      Przywróć
                    </button>
                  ) : (
                    <>
                      <button
                        className="button secondary small"
                        onClick={() => onModal({ kind: "exercise", id: e.id })}
                      >
                        <SlidersHorizontal size={14} />
                        Edytuj
                      </button>
                      <button
                        className="button secondary small"
                        disabled={pending}
                        onClick={() => remove(e)}
                      >
                        <X size={14} />
                        {(e.runs ?? 0) > 0 ? "Archiwizuj" : "Usuń"}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </section>
          );
        })}
      </div>
      {!data.exercises.length && (
        <section className="panel">
          <Empty title="Zbuduj katalog ćwiczeń">
            Wybierz „Nowy scenariusz” – tory i auta pochodzą z gry na
            stanowiskach. Do jednorazowej jazdy użyj „Szybki przejazd”.
          </Empty>
        </section>
      )}
    </>
  );
}

function useLapSummaries(attempts: Attempt[]) {
  const [laps, setLaps] = useState<Record<string, Lap[]>>({});
  const signature = attempts
    .filter((a) => a.sample_count > 0)
    .map((a) => `${a.id}:${a.status}:${Math.floor(a.sample_count / 500)}`)
    .join(",");
  useEffect(() => {
    let valid = true;
    Promise.all(
      attempts
        .filter((a) => a.sample_count > 0)
        .map((a) =>
          api<Lap[]>(`/attempts/${a.id}/laps`).then((l) => [a.id, l] as const),
        ),
    )
      .then((result) => {
        if (valid) setLaps(Object.fromEntries(result));
      })
      .catch(() => {});
    return () => {
      valid = false;
    };
  }, [signature]);
  return laps;
}

function Attempts({
  data,
  privileged,
  onAnalysis,
  onModal,
}: {
  data: Data;
  privileged: boolean;
  onAnalysis: (id: string) => void;
  onModal: (m: Modal) => void;
}) {
  const [student, setStudent] = useState("");
  const laps = useLapSummaries(data.attempts);
  return (
    <>
      <PageIntro
        eyebrow="HISTORIA SZKOLENIA"
        title="Każda próba zostaje z Tobą."
        description="Wybierz przejazd, porównaj sekcje i zapisz ocenę instruktora."
      />
      <section className="panel">
        <div className="panel-heading">
          <h2>Archiwum przejazdów</h2>
          <select
            aria-label="Filtruj przejazdy kursanta"
            value={student}
            onChange={(e) => setStudent(e.target.value)}
          >
            <option value="">Wszyscy kursanci</option>
            {data.trainees.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Kursant i data</th>
                <th>Ćwiczenie / tor</th>
                <th>Najlepsze okrążenie</th>
                <th>Dane</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.attempts
                .filter((a) => !student || a.trainee_id === student)
                .map((a) => {
                  const usable = (laps[a.id] || []).filter((l) => l.usable),
                    best = usable.length
                      ? Math.min(...usable.map((l) => l.duration))
                      : null;
                  return (
                    <tr key={a.id}>
                      <td>
                        <strong>{a.trainee_name}</strong>
                        <span className="cell-sub">{date(a.created)}</span>
                      </td>
                      <td>
                        <strong>{a.exercise_title}</strong>
                        <span className="cell-sub">
                          {a.scenario.track.name} · {modeName(a.mode)}
                        </span>
                      </td>
                      <td className="time-value">{lapTime(best)}</td>
                      <td>
                        {a.sample_count.toLocaleString("pl-PL")}
                        <span className="cell-sub">próbek</span>
                      </td>
                      <td>
                        <Badge status={a.status} />
                      </td>
                      <td>
                        <div className="row-actions">
                          <button
                            className="text-button"
                            disabled={!a.sample_count}
                            onClick={() => onAnalysis(a.id)}
                          >
                            Analiza
                            <ArrowRight size={14} />
                          </button>
                          {privileged &&
                            ["completed", "interrupted", "failed"].includes(
                              a.status,
                            ) && (
                              <button
                                className="icon-button"
                                aria-label={`Oceń przejazd ${a.trainee_name}`}
                                onClick={() =>
                                  onModal({ kind: "review", id: a.id })
                                }
                              >
                                <ClipboardList size={17} />
                              </button>
                            )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        </div>
        {!data.attempts.length && (
          <Empty title="Archiwum jest jeszcze puste">
            Zakończ pierwszą próbę, aby przeanalizować jej wynik.
          </Empty>
        )}
      </section>
    </>
  );
}

function Report({
  data,
  selectedId,
  setSelectedId,
  privileged,
  onModal,
  onReference,
  pending,
}: {
  data: Data;
  selectedId: string;
  setSelectedId: (id: string) => void;
  privileged: boolean;
  onModal: (m: Modal) => void;
  onReference: (attempt: Attempt, lap: number) => Promise<void>;
  pending: boolean;
}) {
  const candidates = data.attempts.filter((a) => a.sample_count > 10),
    attempt = candidates.find((a) => a.id === selectedId) || candidates[0];
  const [referenceId, setReferenceId] = useState(""),
    [lap, setLap] = useState(""),
    [referenceLap, setReferenceLap] = useState(""),
    [analysis, setAnalysis] = useState<Analysis | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [section, setSection] = useState<string | null>(null),
    [progress, setProgress] = useState(0.15);
  const laps = useLapSummaries(candidates),
    refs = candidates.filter(
      (a) =>
        a.scenario.track_key === attempt?.scenario.track_key &&
        a.scenario.track.version === attempt?.scenario.track.version,
    );
  const designated = data.exercises.find(
    (e) => e.id === attempt?.scenario.exercise_id,
  )?.reference;
  const ref =
    refs.find((a) => a.id === referenceId) ||
    refs.find((a) => a.id === designated?.attempt_id) ||
    refs.find((a) => a.note.includes("referencyjny")) ||
    refs.find((a) => a.id !== attempt?.id) ||
    attempt;
  useEffect(() => {
    if (attempt && attempt.id !== selectedId) setSelectedId(attempt.id);
  }, [attempt?.id, selectedId, setSelectedId]);
  useEffect(() => {
    setLap("");
    setSection(null);
    setReferenceId("");
  }, [attempt?.id]);
  useEffect(() => setReferenceLap(""), [ref?.id]);
  useEffect(() => {
    if (!attempt || !ref) return;
    let active = true;
    setLoading(true);
    setError("");
    const q = new URLSearchParams({ reference_id: ref.id });
    if (lap) q.set("lap", lap);
    if (referenceLap) q.set("reference_lap", referenceLap);
    else if (designated?.attempt_id === ref.id)
      q.set("reference_lap", String(designated.lap));
    api<Analysis>(`/attempts/${attempt.id}/analysis?${q}`)
      .then((a) => {
        if (active) setAnalysis(a);
      })
      .catch((e) => {
        if (active) {
          setError((e as Error).message);
          setAnalysis(null);
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [
    attempt?.id,
    ref?.id,
    lap,
    referenceLap,
    attempt?.status,
    designated?.attempt_id,
    designated?.lap,
  ]);
  const selected = analysis?.sections.find((s) => s.id === section),
    range: [number, number] = selected
      ? [selected.start, selected.end]
      : [0, 1];
  function chooseSection(id: string | null) {
    setSection(id);
    const s = analysis?.sections.find((s) => s.id === id);
    if (s) setProgress((s.start + s.end) / 2);
  }
  async function download() {
    if (!attempt) return;
    try {
      const raw = await api(`/attempts/${attempt.id}/export`);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(raw)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `racecoach-${attempt.id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <PageIntro
        eyebrow="ZROZUM SWÓJ PRZEJAZD"
        title="Postęp w każdym zakręcie."
        description="Wspólna pozycja na torze. Dwa przejazdy. Konkretne obszary do poprawy."
      >
        {attempt && (
          <Button secondary onClick={download}>
            <ArrowDownToLine size={16} />
            Eksport danych
          </Button>
        )}
        {privileged &&
          attempt &&
          analysis &&
          ["completed", "interrupted"].includes(attempt.status) && (
            <Button
              secondary
              disabled={pending}
              onClick={() => onReference(attempt, analysis.lap)}
            >
              <Target size={16} />
              Ustaw jako wzorzec
            </Button>
          )}
        {privileged &&
          attempt &&
          ["completed", "interrupted", "failed"].includes(attempt.status) && (
            <Button onClick={() => onModal({ kind: "review", id: attempt.id })}>
              <ClipboardList size={16} />
              Ocena instruktora
            </Button>
          )}
      </PageIntro>
      {!attempt ? (
        <section className="panel">
          <Empty title="Potrzebujesz pierwszego nagrania">
            Mapa i porównanie pojawią się po zebraniu pełnego okrążenia.
          </Empty>
        </section>
      ) : (
        <>
          <div className="report-selectors panel">
            <label>
              Przejazd kursanta
              <select
                value={attempt.id}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                {candidates.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.trainee_name} · {date(a.created)} ·{" "}
                    {a.scenario.track.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Okrążenie
              <select value={lap} onChange={(e) => setLap(e.target.value)}>
                <option value="">Najlepsze z ciągłymi danymi</option>
                {(laps[attempt.id] || []).map((l) => (
                  <option disabled={!l.usable} key={l.lap} value={l.lap}>
                    Okrążenie {l.lap + 1} · {lapTime(l.duration)}
                    {!l.usable ? " · niepełne" : ""}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Przejazd referencyjny
              <select
                value={ref?.id || ""}
                onChange={(e) => setReferenceId(e.target.value)}
              >
                {refs.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.trainee_name} · {date(a.created)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Okrążenie wzorca
              <select
                value={referenceLap}
                onChange={(e) => setReferenceLap(e.target.value)}
              >
                <option value="">
                  {designated?.attempt_id === ref?.id
                    ? `Wzorzec ćwiczenia · okrążenie ${designated.lap + 1}`
                    : "Najlepsze z ciągłymi danymi"}
                </option>
                {(laps[ref?.id || ""] || []).map((l) => (
                  <option disabled={!l.usable} key={l.lap} value={l.lap}>
                    Okrążenie {l.lap + 1} · {lapTime(l.duration)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          {loading && (
            <div className="loading-line" role="status">
              Przeliczanie porównania…
            </div>
          )}
          {analysis && (
            <>
              <div className="report-summary">
                <div>
                  <span>WYBRANY PRZEJAZD</span>
                  <strong>{lapTime(analysis.duration)}</strong>
                  <small>
                    {attempt.trainee_name} · okrążenie {analysis.lap + 1}
                  </small>
                </div>
                <div>
                  <span>PRZEJAZD WZORCOWY</span>
                  <strong>{lapTime(analysis.reference_duration)}</strong>
                  <small>
                    {ref?.trainee_name} · okrążenie {analysis.reference_lap + 1}
                  </small>
                </div>
                <div>
                  <span>RÓŻNICA CAŁEGO OKRĄŻENIA</span>
                  <strong>
                    <DeltaValue value={analysis.delta} />
                  </strong>
                  <small>Dodatnia wartość oznacza stratę</small>
                </div>
                <div>
                  <span>JAKOŚĆ ZAPISU</span>
                  <strong>
                    {analysis.quality.current_samples.toLocaleString("pl-PL")}
                    <small> próbek</small>
                  </strong>
                  <small>
                    Maks. przerwa {(analysis.quality.max_gap * 1000).toFixed(0)}{" "}
                    ms
                  </small>
                </div>
              </div>
              {analysis.warnings.map((w) => (
                <div className="notice warning" key={w}>
                  {w}
                </div>
              ))}
              <div className="analysis-grid">
                <div>
                  <TrackMap
                    track={analysis.track}
                    sections={analysis.sections}
                    selected={section}
                    onSelect={chooseSection}
                    current={analysis.current}
                    reference={analysis.reference}
                    progress={progress}
                  />
                  <div className="map-legend">
                    <span>
                      <i className="legend-dot green" />
                      Zysk sekcji
                    </span>
                    <span>
                      <i className="legend-dot coral" />
                      Strata sekcji
                    </span>
                    <span>
                      <i className="legend-dot gray" />
                      Różnica do 0,03 s
                    </span>
                  </div>
                  <section className="panel selected-section">
                    <div className="eyebrow">
                      {selected ? "WYBRANA SEKCJA" : "PEŁNE OKRĄŻENIE"}
                    </div>
                    <h2>
                      {selected
                        ? selected.name
                        : "Wybierz sekcję na mapie lub w tabeli"}
                    </h2>
                    {selected && (
                      <div className="section-facts">
                        <div>
                          <span>Wynik sekcji</span>
                          <DeltaValue value={selected.delta} />
                        </div>
                        <div>
                          <span>Prędkość wyjścia</span>
                          <strong>
                            {selected.current.exit_speed.toFixed(1)}
                            <small>
                              {" "}
                              / {selected.reference.exit_speed.toFixed(1)} km/h
                            </small>
                          </strong>
                        </div>
                        <div>
                          <span>Początek hamowania</span>
                          <strong>
                            {selected.brake_difference_m == null
                              ? "Brak progu w sekcji"
                              : `${selected.brake_difference_m > 0 ? "+" : ""}${selected.brake_difference_m.toFixed(1)} m`}
                            <small> względem wzorca</small>
                          </strong>
                        </div>
                      </div>
                    )}
                    <p className="muted">
                      Wyniki opisują zapisane sygnały. Ocena techniki i
                      zaliczenie należą do instruktora.
                    </p>
                  </section>
                </div>
                <section className="panel section-table">
                  <div className="panel-heading">
                    <h2>Sekcje toru</h2>
                    {section && (
                      <button
                        className="text-button"
                        onClick={() => chooseSection(null)}
                      >
                        Cała pętla
                        <X size={13} />
                      </button>
                    )}
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Sekcja</th>
                          <th>Kursant</th>
                          <th>Wzorzec</th>
                          <th>Różnica sekcji</th>
                        </tr>
                      </thead>
                      <tbody>
                        {analysis.sections.map((s) => (
                          <tr
                            className={s.id === section ? "selected-row" : ""}
                            key={s.id}
                          >
                            <td>
                              <button
                                className="section-name"
                                onClick={() =>
                                  chooseSection(section === s.id ? null : s.id)
                                }
                              >
                                <span>S{s.id}</span>
                                {s.name}
                              </button>
                            </td>
                            <td className="time-value">
                              {s.current.duration.toFixed(3)}
                            </td>
                            <td className="time-value muted">
                              {s.reference.duration.toFixed(3)}
                            </td>
                            <td>
                              <DeltaValue value={s.delta} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="table-note">
                    Sekcje pokazują lokalną stratę lub zysk. Ich suma odpowiada
                    różnicy okrążenia, jeżeli obejmują całą trasę.
                  </div>
                </section>
              </div>
              <section className="panel charts-panel">
                <div className="panel-heading">
                  <div>
                    <span className="eyebrow">
                      TELEMETRIA WZGLĘDEM POŁOŻENIA
                    </span>
                    <h2>{selected ? selected.name : "Całe okrążenie"}</h2>
                  </div>
                  <div className="chart-legend">
                    <span>
                      <i className="legend-dot orange" />
                      {attempt.trainee_name}
                    </span>
                    <span>
                      <i className="legend-dot blue" />
                      Wzorzec
                    </span>
                  </div>
                </div>
                <label className="position-control">
                  Pozycja kursora{" "}
                  <strong>
                    {Math.round(progress * analysis.track.length)} m
                  </strong>
                  <input
                    type="range"
                    min="0"
                    max="1000"
                    value={Math.round(progress * 1000)}
                    onChange={(e) => setProgress(Number(e.target.value) / 1000)}
                    aria-label="Pozycja na torze"
                  />
                </label>
                <div className="charts-grid">
                  {(
                    [
                      { field: "speed", label: "Prędkość", unit: "km/h" },
                      { field: "throttle", label: "Gaz", unit: "%" },
                      { field: "brake", label: "Hamulec", unit: "%" },
                      {
                        field: "steer",
                        label: "Skręt",
                        unit: "sygnał gry",
                      },
                    ] as const
                  ).map((c) => (
                    <TelemetryChart
                      key={c.field}
                      analysis={analysis}
                      {...c}
                      range={range}
                      progress={progress}
                      onProgress={setProgress}
                    />
                  ))}
                </div>
                <div className="table-note">
                  Ciągłość telemetrii jest sprawdzana niezależnie od oficjalnej
                  ważności okrążenia w grze. Wskazania siły i skrętu wymagają
                  walidacji jednostek na stanowisku.
                </div>
              </section>
              {attempt.note && (
                <section className="panel instructor-note">
                  <ClipboardList size={20} />
                  <div>
                    <h3>Notatka instruktora</h3>
                    <p>{attempt.note}</p>
                  </div>
                </section>
              )}
            </>
          )}
          <AttemptCoach attemptId={attempt.id} />
        </>
      )}
    </>
  );
}

function Integrations({
  data,
  onModal,
}: {
  data: Data;
  onModal: (m: Modal) => void;
}) {
  return (
    <>
      <PageIntro
        eyebrow="STAN SYSTEMU"
        title="Integracje i wykonane polecenia."
        description="Potwierdzenia, błędy i jawny status połączeń ze sprzętem oraz grą."
      >
        <Button secondary onClick={() => onModal({ kind: "pair" })}>
          <Plus size={16} />
          Nowy agent
        </Button>
      </PageIntro>
      <div className="integration-grid">
        <div className="panel integration-card">
          <Monitor size={24} />
          <h3>Assetto Corsa</h3>
          <p>
            Agent Windows: konfiguracja sesji, uruchomienie gry i odczyt pamięci
            współdzielonej.
          </p>
          <span className="integration-status">
            Adapter gotowy do testu na Windows
          </span>
        </div>
        <div className="panel integration-card">
          <SlidersHorizontal size={24} />
          <h3>DIY Direct Drive</h3>
          <p>
            Import sterowników z istniejącego DD Control. Profil jest
            potwierdzany odczytem z urządzenia.
          </p>
          <span className="integration-status">OpenFFBoard / FFBeast</span>
        </div>
        <div className="panel integration-card">
          <Flag size={24} />
          <h3>Serwer grupowy i CSP</h3>
          <p>
            Dedykowana instalacja AC zarządzana przez centralę. Pogoda podczas
            jazdy wymaga własnego mostu HTTP CSP.
          </p>
          <span className="integration-status">Konfiguracja operatora</span>
        </div>
      </div>
      <section className="panel">
        <div className="panel-heading">
          <h2>Dziennik poleceń</h2>
          <span className="muted">Ostatnie 100 operacji</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Czas</th>
                <th>Stanowisko</th>
                <th>Operacja</th>
                <th>Status</th>
                <th>Wynik</th>
              </tr>
            </thead>
            <tbody>
              {data.commands.map((c) => (
                <tr key={c.id}>
                  <td>{date(c.created)}</td>
                  <td>{c.station_name}</td>
                  <td>
                    {{
                      prepare_session: "Przygotuj sesję",
                      start_session: "Uruchom grę",
                      stop_session: "Zakończ sesję",
                      hardware_profile: "Zastosuj profil DD",
                    }[c.kind] || c.kind}
                  </td>
                  <td>
                    <Badge status={c.status} />
                  </td>
                  <td className="result-cell">
                    {c.result.error ||
                      (c.status === "succeeded"
                        ? "Potwierdzenie agenta"
                        : "Oczekiwanie na wynik")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!data.commands.length && (
          <Empty title="Brak zleconych operacji">
            Pierwsze polecenia pojawią się po przygotowaniu sesji lub zmianie
            profilu.
          </Empty>
        )}
      </section>
    </>
  );
}

function Dialog({
  title,
  subtitle,
  children,
  onClose,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
    >
      <div className="dialog-heading">
        <div>
          <h2 id={titleId}>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <button
          className="icon-button"
          aria-label="Zamknij okno"
          onClick={onClose}
        >
          <X size={20} />
        </button>
      </div>
      <div className="dialog-body">{children}</div>
    </dialog>
  );
}

function FormModal({
  modal,
  data,
  onClose,
  onSubmit,
}: {
  modal: Modal;
  data: Data;
  onClose: () => void;
  onSubmit: (kind: string, body: unknown, id?: string) => Promise<unknown>;
}) {
  const station = data.stations.find((s) => s.id === modal.id),
    review = data.attempts.find((a) => a.id === modal.id);
  const [values, setValues] = useState<Record<string, string>>({
    name: "",
    email: "",
    password: "",
    title: "",
    trainee_id:
      modal.kind === "plan"
        ? modal.id || data.trainees[0]?.id || ""
        : data.trainees[0]?.id || "",
    exercise_id: data.exercises.find((e) => !e.archived)?.id || "",
    mode: "either",
    track_id: data.tracks[0]?.id || "",
    car: "abarth500",
    duration: "15",
    weather: "3_clear",
    air_temp: "22",
    road_temp: "29",
    grip: "100",
    rain: "0",
    wetness: "0",
    water: "0",
    transition: "30",
    text: "",
    time: "13:00",
    profile: "off",
    degrees: String(station?.state.hardware?.degrees ?? 900),
    strength: String(station?.state.hardware?.strength ?? 15),
    goal: "",
    criteria: "Ocena instruktora i trzy powtarzalne okrążenia.",
    scheduled: "",
    note: review?.note || "",
    decision: review?.result?.decision || "none",
    json: "",
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function set(key: string, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
  }
  const titles = {
    trainee: "Nowy kursant",
    plan: "Indywidualny plan szkolenia",
    item: "Sesja w planie kursanta",
    exercise: modal.id ? "Edytuj scenariusz" : "Nowy scenariusz treningowy",
    run: "Przygotuj sesję",
    quick: "Szybki przejazd",
    profile: `Profil DD · ${station?.name}`,
    pair: "Zarejestruj stanowisko",
    import: "Importuj pakiet toru",
    review: "Ocena przejazdu",
    weather: "Zmień warunki podczas jazdy",
    message: `Wiadomość do kierowcy · ${station?.name ?? ""}`,
  };
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      let body: unknown = {};
      if (modal.kind === "trainee")
        body = {
          name: values.name,
          email: values.email,
          password: values.password,
          notes: "",
        };
      if (modal.kind === "plan")
        body = { trainee_id: values.trainee_id, title: values.title };
      if (modal.kind === "item")
        body = {
          exercise_id: values.exercise_id,
          title: values.title,
          goal: values.goal,
          criteria: values.criteria,
          mode: values.mode,
          scheduled: values.scheduled || null,
        };
      if (modal.kind === "exercise")
        body = {
          title: values.title,
          track_id: values.track_id,
          car: values.car,
          mode: values.mode,
          duration: Number(values.duration),
          hardware_profile:
            values.profile === "on"
              ? {
                  degrees: Number(values.degrees),
                  strength: Number(values.strength),
                }
              : null,
          conditions: {
            weather: values.weather,
            air_temp: Number(values.air_temp),
            road_temp: Number(values.road_temp),
            grip: Number(values.grip) / 100,
            rain: Number(values.rain) / 100,
            time: values.time,
          },
        };
      if (modal.kind === "profile")
        body = {
          degrees: Number(values.degrees),
          strength: Number(values.strength),
        };
      if (modal.kind === "pair") body = { name: values.name };
      if (modal.kind === "weather")
        body = {
          rain: Number(values.rain) / 100,
          wetness: Number(values.wetness) / 100,
          water: Number(values.water) / 100,
          transition: Number(values.transition),
        };
      if (modal.kind === "review")
        body = { note: values.note, decision: values.decision };
      if (modal.kind === "message") body = { text: values.text };
      if (modal.kind === "import") body = JSON.parse(values.json);
      await onSubmit(modal.kind, body, modal.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const field = (
    key: string,
    label: string,
    type = "text",
    min?: number,
    max?: number,
  ) => (
    <label>
      {label}
      <input
        type={type}
        value={values[key]}
        required={key !== "scheduled"}
        min={min}
        max={max}
        minLength={key === "password" ? 10 : undefined}
        onChange={(e) => set(key, e.target.value)}
      />
    </label>
  );
  const modes = (
    <label>
      Tryb
      <select value={values.mode} onChange={(e) => set("mode", e.target.value)}>
        <option value="either">Indywidualny i grupowy</option>
        <option value="individual">Indywidualny</option>
        <option value="multiplayer">Grupowy</option>
      </select>
    </label>
  );
  return (
    <Dialog
      title={titles[modal.kind]}
      subtitle={
        modal.kind === "run" || modal.kind === "quick"
          ? "Przygotowanie nie rozpoczyna jeszcze jazdy."
          : modal.kind === "exercise" && modal.id
            ? "Po pierwszym przejeździe zmiana toru, auta lub warunków tworzy nową rewizję."
            : undefined
      }
      onClose={onClose}
    >
      {modal.kind === "run" ? (
        <RunForm
          data={data}
          onSubmit={(body) => onSubmit("run", body)}
          onClose={onClose}
        />
      ) : modal.kind === "quick" ? (
        <QuickRunForm
          data={data}
          onSubmit={(body) => onSubmit("quick", body)}
          onClose={onClose}
        />
      ) : modal.kind === "exercise" ? (
        <ExerciseForm
          data={data}
          initial={data.exercises.find((e) => e.id === modal.id)}
          onSubmit={(body) => onSubmit("exercise", body, modal.id)}
          onClose={onClose}
        />
      ) : (
        <form onSubmit={save}>
          {modal.kind === "trainee" && (
            <>
              {field("name", "Imię i nazwisko")}
              {field("email", "E-mail", "email")}
              {field(
                "password",
                "Hasło początkowe (min. 10 znaków)",
                "password",
              )}
            </>
          )}
          {modal.kind === "plan" && (
            <>
              <label>
                Kursant
                <select
                  required
                  value={values.trainee_id}
                  onChange={(e) => set("trainee_id", e.target.value)}
                >
                  {data.trainees.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              {field("title", "Nazwa planu")}
            </>
          )}
          {modal.kind === "item" && (
            <>
              <label>
                Scenariusz
                <select
                  required
                  value={values.exercise_id}
                  onChange={(e) => set("exercise_id", e.target.value)}
                >
                  {data.exercises
                    .filter((e) => !e.archived)
                    .map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.title}
                      </option>
                    ))}
                </select>
              </label>
              {field("title", "Nazwa sesji")}
              <label>
                Cel sesji
                <textarea
                  required
                  minLength={3}
                  value={values.goal}
                  onChange={(e) => set("goal", e.target.value)}
                  rows={3}
                />
              </label>
              <label>
                Kryteria zaliczenia
                <textarea
                  value={values.criteria}
                  onChange={(e) => set("criteria", e.target.value)}
                  rows={2}
                />
              </label>
              <div className="form-grid">
                {modes}
                {field("scheduled", "Planowany termin (opcjonalny)", "date")}
              </div>
            </>
          )}
          {modal.kind === "message" && (
            <>
              <div className="notice">
                Tekst pojawi się w nakładce „Instruktor” i na ekranie
                stanowiska. Krótko – kierowca czyta go w trakcie jazdy.
              </div>
              <label>
                Wiadomość
                <input
                  required
                  maxLength={300}
                  autoFocus
                  value={values.text}
                  placeholder="np. Hamuj 20 m później w zakręcie 1"
                  onChange={(e) => set("text", e.target.value)}
                />
              </label>
              <div className="quick-messages">
                {[
                  "Zjedź do boksu",
                  "Ostatnie okrążenie",
                  "Świetnie, utrzymaj tempo",
                  "Płynniej na wyjściu z zakrętów",
                ].map((t) => (
                  <button
                    type="button"
                    key={t}
                    className="chip"
                    onClick={() => set("text", t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </>
          )}
          {modal.kind === "weather" && (
            <>
              <div className="notice">
                Warunki zmienią się płynnie w podanym czasie, a zmiana zostanie
                zapisana w historii próby. Mokrość to wilgoć nawierzchni (przy
                deszczu szybko rośnie), stojąca woda to kałuże i ryzyko
                aquaplaningu. Ok. 50% deszczu to już mocna ulewa.
              </div>
              <div className="form-grid">
                {field("rain", "Intensywność deszczu (%)", "number", 0, 100)}
                {field("wetness", "Mokrość nawierzchni (%)", "number", 0, 100)}
                {field("water", "Stojąca woda (%)", "number", 0, 100)}
                {field("transition", "Czas przejścia (s)", "number", 0, 600)}
              </div>
            </>
          )}
          {modal.kind === "profile" && (
            <>
              <div className="notice">
                Zmiana dotyczy pamięci roboczej bazy. Lokalny limit agenta
                pozostaje nadrzędny. Pętla FFB działa na stanowisku.
              </div>
              <div className="form-grid">
                {field("degrees", "Zakres obrotu (°)", "number", 180, 1440)}
                {field("strength", "Siła (%)", "number", 0, 100)}
              </div>
              <p className="muted">
                Zmiana wymaga bezczynnego stanowiska i odczytu zwrotnego
                urządzenia. Panel nie udostępnia zdalnej kalibracji silnika.
              </p>
            </>
          )}
          {modal.kind === "pair" && (
            <>
              {field("name", "Nazwa stanowiska")}
              <p className="muted">
                Otrzymasz unikalny token do uruchomienia agenta Windows. Nie
                zamykaj kolejnego okna przed zapisaniem tokenu.
              </p>
            </>
          )}
          {modal.kind === "review" && (
            <>
              <label>
                Notatka instruktora
                <textarea
                  rows={5}
                  value={values.note}
                  onChange={(e) => set("note", e.target.value)}
                />
              </label>
              <label>
                Decyzja
                <select
                  value={values.decision}
                  onChange={(e) => set("decision", e.target.value)}
                >
                  <option value="none">
                    Zapisz notatkę bez zmiany zaliczenia
                  </option>
                  <option value="passed">Zalicz sesję w planie</option>
                  <option value="repeat">Skieruj sesję do powtórzenia</option>
                </select>
              </label>
            </>
          )}
          {modal.kind === "import" && (
            <>
              <p>
                Pakiet zawiera geometrię, identyfikator toru/layoutu, wersję i
                granice sekcji. Możesz zmienić nazwy i granice przed importem.
              </p>
              <label>
                Plik pakietu JSON
                <input
                  type="file"
                  accept=".json,application/json"
                  onChange={async (e) => {
                    const f = e.target.files?.[0];
                    if (f) set("json", await f.text());
                  }}
                />
              </label>
              <label>
                Geometria i sekcje
                <textarea
                  required
                  className="code-input"
                  rows={12}
                  placeholder={
                    '{"id":"magione-v1","game_id":"magione","name":"Magione", ...}'
                  }
                  value={values.json}
                  onChange={(e) => set("json", e.target.value)}
                />
              </label>
              <p className="muted">
                Eksport: <code>python -m racecoach_agent.track_export</code>.
                Każda wersja pakietu ma własny identyfikator; archiwalne sekcje
                pozostają niezmienne.
              </p>
            </>
          )}
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              className="button secondary"
              onClick={onClose}
            >
              Anuluj
            </button>
            <button className="button" disabled={busy}>
              {busy
                ? "Zapisywanie…"
                : modal.kind === "profile"
                  ? "Zleć zastosowanie"
                  : "Zapisz"}
              <Check size={15} />
            </button>
          </div>
        </form>
      )}
    </Dialog>
  );
}

type ParticipantRow = {
  trainee_id: string;
  station_id: string;
  plan_item_id: string;
};

function freeStation(data: Data, rows: ParticipantRow[] = []) {
  return (
    data.stations.find(
      (s) =>
        s.online &&
        s.state.game === "idle" &&
        !s.attempt &&
        !rows.some((r) => r.station_id === s.id),
    )?.id || ""
  );
}

/** Uczestnicy sesji: kursant, stanowisko i (dla scenariusza) pozycja planu. */
function Participants({
  data,
  rows,
  setRows,
  mode,
  exercise,
}: {
  data: Data;
  rows: ParticipantRow[];
  setRows: (rows: ParticipantRow[]) => void;
  mode: string;
  exercise?: string;
}) {
  return (
    <>
      {rows.map((row, index) => {
        const items = exercise
          ? data.plans
              .filter((p) => p.trainee_id === row.trainee_id)
              .flatMap((p) => p.items)
              .filter(
                (i) =>
                  i.exercise_id === exercise &&
                  ["either", mode].includes(i.mode) &&
                  !["passed", "skipped"].includes(i.status),
              )
          : [];
        function change(key: string, value: string) {
          setRows(
            rows.map((r, i) =>
              i === index
                ? {
                    ...r,
                    [key]: value,
                    ...(key === "trainee_id" ? { plan_item_id: "" } : {}),
                  }
                : r,
            ),
          );
        }
        return (
          <div className="participant" key={index}>
            <div className="participant-heading">
              <strong>Uczestnik {index + 1}</strong>
              {index > 0 && (
                <button
                  type="button"
                  className="icon-button"
                  aria-label="Usuń uczestnika"
                  onClick={() => setRows(rows.filter((_, i) => i !== index))}
                >
                  <X size={16} />
                </button>
              )}
            </div>
            <div className="form-grid">
              <label>
                Kursant
                <select
                  required
                  value={row.trainee_id}
                  onChange={(e) => change("trainee_id", e.target.value)}
                >
                  {data.trainees.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Stanowisko
                <select
                  required
                  value={row.station_id}
                  onChange={(e) => change("station_id", e.target.value)}
                >
                  <option value="">Wybierz gotowe stanowisko</option>
                  {data.stations.map((s) => (
                    <option
                      key={s.id}
                      value={s.id}
                      disabled={
                        !s.online || s.state.game !== "idle" || !!s.attempt
                      }
                    >
                      {s.name}
                      {!s.online ? " · offline" : s.attempt ? " · zajęte" : ""}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {exercise && (
              <label>
                Sesja z planu kursanta
                <select
                  value={row.plan_item_id}
                  onChange={(e) => change("plan_item_id", e.target.value)}
                >
                  <option value="">Próba dodatkowa, poza planem</option>
                  {items.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.sequence}. {i.title}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>
        );
      })}
      {mode === "multiplayer" && (
        <button
          type="button"
          className="button secondary full"
          disabled={rows.length >= data.stations.length}
          onClick={() =>
            setRows([
              ...rows,
              {
                trainee_id:
                  data.trainees.find(
                    (t) => !rows.some((r) => r.trainee_id === t.id),
                  )?.id || "",
                station_id: freeStation(data, rows),
                plan_item_id: "",
              },
            ])
          }
        >
          <Plus size={16} />
          Dodaj uczestnika
        </button>
      )}
    </>
  );
}

type SessionSettings = {
  mode: string;
  race: boolean;
  raceLaps: string;
  collisions: boolean;
  showRivals: boolean;
};

/** Tryb, rodzaj sesji i opcje sesji grupowej (kolizje, rywale na minimapie). */
function SessionOptionsFields({
  value,
  onChange,
  onModeChange,
}: {
  value: SessionSettings;
  onChange: (value: SessionSettings) => void;
  onModeChange: (mode: string) => void;
}) {
  const set = (patch: Partial<SessionSettings>) =>
    onChange({ ...value, ...patch });
  return (
    <>
      <div className="form-grid">
        <label>
          Tryb sesji
          <select
            value={value.mode}
            onChange={(e) => {
              set({ mode: e.target.value });
              onModeChange(e.target.value);
            }}
          >
            <option value="individual">Indywidualna</option>
            <option value="multiplayer">Grupowa</option>
          </select>
        </label>
        <label>
          Rodzaj
          <select
            value={value.race ? "race" : "practice"}
            onChange={(e) => set({ race: e.target.value === "race" })}
          >
            <option value="practice">Trening na czas sesji</option>
            <option value="race">Wyścig na liczbę okrążeń</option>
          </select>
        </label>
        {value.race && (
          <label>
            Liczba okrążeń
            <input
              type="number"
              min={1}
              max={200}
              required
              value={value.raceLaps}
              onChange={(e) => set({ raceLaps: e.target.value })}
            />
          </label>
        )}
      </div>
      {value.race && (
        <p className="muted">
          Po przejechaniu zadanej liczby okrążeń stanowisko kończy sesję, a
          panel liczy klasyfikację. W trybie grupowym bez serwera AC każdy
          jedzie u siebie (wyścig wirtualny).
        </p>
      )}
      {value.mode === "multiplayer" && (
        <>
          <label className="check-row">
            <input
              type="checkbox"
              checked={value.collisions}
              onChange={(e) => set({ collisions: e.target.checked })}
            />
            <span>
              Kolizje między autami
              <small>
                Wyłączone: tryb ducha – auta przenikają się, zostają kolizje z
                torem. Wymaga AssettoServer i CSP na stanowiskach.
              </small>
            </span>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={value.showRivals}
              onChange={(e) => set({ showRivals: e.target.checked })}
            />
            <span>
              Pozostali kierowcy na minimapie w grze
              <small>
                Niebieskie kropki z imionami w nakładce RaceCoach. Panel zawsze
                pokazuje wszystkich na mapie sesji.
              </small>
            </span>
          </label>
        </>
      )}
    </>
  );
}

const sessionBody = (o: SessionSettings, rows: ParticipantRow[]) => ({
  mode: o.mode,
  race_laps: o.race ? Number(o.raceLaps) : null,
  collisions: o.mode !== "multiplayer" || o.collisions,
  show_rivals: o.showRivals,
  participants: rows.map((r) => ({
    ...r,
    plan_item_id: r.plan_item_id || null,
  })),
});

const defaultSession: SessionSettings = {
  mode: "individual",
  race: false,
  raceLaps: "5",
  collisions: true,
  showRivals: true,
};

function RunForm({
  data,
  onSubmit,
  onClose,
}: {
  data: Data;
  onSubmit: (body: unknown) => Promise<unknown>;
  onClose: () => void;
}) {
  const available = data.exercises.filter((e) => !e.archived);
  const [exercise, setExercise] = useState(available[0]?.id || ""),
    [options, setOptions] = useState<SessionSettings>(defaultSession),
    [rows, setRows] = useState<ParticipantRow[]>([
      {
        trainee_id: data.trainees[0]?.id || "",
        station_id: freeStation(data),
        plan_item_id: "",
      },
    ]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const selected = available.find((e) => e.id === exercise);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit({ exercise_id: exercise, ...sessionBody(options, rows) });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={save}>
      <label>
        Ćwiczenie
        <select
          required
          value={exercise}
          onChange={(e) => {
            setExercise(e.target.value);
            setRows(rows.map((r) => ({ ...r, plan_item_id: "" })));
          }}
        >
          {available.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} · {e.track_name}
            </option>
          ))}
        </select>
      </label>
      <SessionOptionsFields
        value={options}
        onChange={setOptions}
        onModeChange={() => setRows(rows.slice(0, 1))}
      />
      {selected && (
        <div className="session-preview">
          <Flag size={18} />
          <span>
            {data.carNames[selected.car] ?? selected.car} · {selected.duration}{" "}
            min · {selected.conditions.air_temp}°C ·{" "}
            {selected.conditions.rain ? "deszcz" : "sucho"}
          </span>
        </div>
      )}
      <Participants
        data={data}
        rows={rows}
        setRows={setRows}
        mode={options.mode}
        exercise={exercise}
      />
      <p className="muted">
        Agent sprawdzi zawartość i gotowość. Przy sesji grupowej wszyscy
        uczestnicy korzystają z tego samego scenariusza.
      </p>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="dialog-actions">
        <button type="button" className="button secondary" onClick={onClose}>
          Anuluj
        </button>
        <button className="button" disabled={busy || !available.length}>
          {busy ? "Zlecanie…" : "Przygotuj stanowiska"}
          <ArrowRight size={16} />
        </button>
      </div>
    </form>
  );
}

/** Szybki przejazd: tor, auto i warunki bez zapisywania scenariusza. */
function QuickRunForm({
  data,
  onSubmit,
  onClose,
}: {
  data: Data;
  onSubmit: (body: unknown) => Promise<unknown>;
  onClose: () => void;
}) {
  const [options, setOptions] = useState<SessionSettings>(defaultSession),
    [rows, setRows] = useState<ParticipantRow[]>([
      {
        trainee_id: data.trainees[0]?.id || "",
        station_id: freeStation(data),
        plan_item_id: "",
      },
    ]);
  return (
    <ExerciseForm
      data={data}
      quick
      onClose={onClose}
      submitLabel="Przygotuj stanowiska"
      onSubmit={(body) =>
        onSubmit({
          track_id: body.track_id,
          car: body.car,
          duration: body.duration,
          conditions: body.conditions,
          title: `Szybki przejazd · ${body.title}`.slice(0, 150),
          ...sessionBody(options, rows),
        })
      }
      extra={
        <>
          <SessionOptionsFields
            value={options}
            onChange={setOptions}
            onModeChange={() => setRows(rows.slice(0, 1))}
          />
          <Participants
            data={data}
            rows={rows}
            setRows={setRows}
            mode={options.mode}
          />
        </>
      }
      note={
        <p className="muted">
          Szybki przejazd nie trafia do listy scenariuszy, ale okrążenia liczą
          się do rankingów auta i toru, a przejazd jest w historii i analizie.
        </p>
      }
    />
  );
}
