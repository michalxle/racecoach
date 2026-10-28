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
  Users,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { ApiError, api, date, delta, lapTime, post, statusNames } from "./api";
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
  DeltaValue,
  Meter,
  nearest,
  TelemetryChart,
  TrackMap,
} from "./visuals";

type Page =
  | "overview"
  | "stations"
  | "trainees"
  | "plans"
  | "exercises"
  | "attempts"
  | "analysis"
  | "settings";
type Modal = {
  kind:
    | "trainee"
    | "plan"
    | "item"
    | "exercise"
    | "run"
    | "profile"
    | "pair"
    | "import"
    | "review"
    | "weather";
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
};
const navigation = [
  { id: "overview", name: "Przegląd", icon: LayoutDashboard },
  { id: "stations", name: "Stanowiska", icon: Monitor },
  { id: "trainees", name: "Kursanci", icon: Users },
  { id: "plans", name: "Plany szkolenia", icon: ClipboardList },
  { id: "exercises", name: "Scenariusze", icon: Flag },
  { id: "attempts", name: "Przejazdy", icon: Timer },
  { id: "analysis", name: "Analiza przejazdu", icon: Activity },
  { id: "settings", name: "Integracje i dziennik", icon: Settings },
] as const;
const modeName = (value: string) =>
  value === "individual"
    ? "Indywidualna"
    : value === "multiplayer"
      ? "Grupowa"
      : "Oba tryby";
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
  const refresh = useCallback(async () => {
    if (!session) return;
    try {
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
    };
    result = await post(endpoints[kind], body);
    if (kind === "pair") setSecret(result as { name: string; token: string });
    if (kind === "run") setPage("stations");
    await refresh();
    setModal(null);
    setToast({
      text:
        kind === "run"
          ? "Przygotowanie zlecone. Poczekaj na gotowość stanowisk, a następnie wybierz Start."
          : kind === "profile"
            ? "Profil wysłany. Wynik odczytu zwrotnego zobaczysz w dzienniku."
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
        ["overview", "plans", "attempts", "analysis"].includes(n.id),
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
            <Exercises data={data} onModal={setModal} />
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
}: {
  data: Data;
  onModal: (m: Modal) => void;
  action: (path: string, body?: unknown, message?: string) => Promise<void>;
  pending: boolean;
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
            <div key={r.id} className="run-row">
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
              </div>
              <Badge status={r.status} />
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
                    disabled={pending}
                  >
                    Zmień warunki
                  </button>
                )}
              </div>
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
}: {
  data: Data;
  onModal: (m: Modal) => void;
}) {
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
        <Button onClick={() => onModal({ kind: "exercise" })}>
          <Plus size={16} />
          Nowy scenariusz
        </Button>
      </PageIntro>
      <div className="exercise-grid">
        {data.exercises.map((e) => {
          const track = data.tracks.find((t) => t.id === e.track_id);
          return (
            <section key={e.id} className="panel exercise-card">
              {track && <TrackMap track={track} compact />}
              <div className="exercise-body">
                <div className="eyebrow">
                  {modeName(e.mode)} · REWIZJA {e.revision}
                </div>
                <h2>{e.title}</h2>
                <p>
                  {e.track_name} · {e.car}
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
                      {e.conditions.rain
                        ? `Deszcz ${e.conditions.rain * 100}%`
                        : e.conditions.weather}
                    </strong>
                  </div>
                  <div>
                    <span>Czas sesji</span>
                    <strong>
                      {e.duration} min · {e.conditions.time}
                    </strong>
                  </div>
                </div>
              </div>
            </section>
          );
        })}
      </div>
      {!data.exercises.length && (
        <section className="panel">
          <Empty title="Zbuduj katalog ćwiczeń">
            Najpierw zaimportuj tor, następnie dodaj scenariusz.
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
    exercise_id: data.exercises[0]?.id || "",
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
    exercise: "Nowy scenariusz treningowy",
    run: "Przygotuj sesję",
    profile: `Profil DD · ${station?.name}`,
    pair: "Zarejestruj stanowisko",
    import: "Importuj pakiet toru",
    review: "Ocena przejazdu",
    weather: "Zmień warunki podczas jazdy",
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
        };
      if (modal.kind === "review")
        body = { note: values.note, decision: values.decision };
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
        modal.kind === "run"
          ? "Przygotowanie nie rozpoczyna jeszcze jazdy."
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
                  {data.exercises.map((e) => (
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
          {modal.kind === "exercise" && (
            <>
              {field("title", "Nazwa scenariusza")}
              <label>
                Tor i wersja
                <select
                  required
                  value={values.track_id}
                  onChange={(e) => set("track_id", e.target.value)}
                >
                  {data.tracks.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name} · {t.layout || "pełna pętla"} · {t.version}
                    </option>
                  ))}
                </select>
              </label>
              {field("car", "Identyfikator samochodu w grze")}
              <div className="form-grid">
                {modes}
                {field("duration", "Długość sesji (min)", "number", 1, 180)}
                {field(
                  "air_temp",
                  "Temperatura powietrza (°C)",
                  "number",
                  -10,
                  50,
                )}
                {field("road_temp", "Temperatura toru (°C)", "number", -10, 80)}
                {field("grip", "Przyczepność (%)", "number", 50, 100)}
                {field("time", "Pora dnia", "time")}
                {field("rain", "Deszcz (%)", "number", 0, 100)}
                {field("weather", "Identyfikator pogody")}
              </div>
              <p className="muted">
                Scenariusz deszczowy wymaga adaptera CSP. Bazowy agent odmówi
                uruchomienia zamiast zastąpić deszcz suchą pogodą.
              </p>
              <label>
                Profil bazy wymagany w ćwiczeniu
                <select
                  value={values.profile}
                  onChange={(e) => set("profile", e.target.value)}
                >
                  <option value="off">
                    Zachowaj bieżący profil stanowiska
                  </option>
                  <option value="on">
                    Zastosuj i potwierdź wskazany profil
                  </option>
                </select>
              </label>
              {values.profile === "on" && (
                <div className="form-grid">
                  {field("degrees", "Zakres obrotu (°)", "number", 180, 1440)}
                  {field("strength", "Siła (%)", "number", 0, 100)}
                </div>
              )}
            </>
          )}
          {modal.kind === "weather" && (
            <>
              <div className="notice">
                Polecenie zostanie zastosowane do wspólnej sesji i zapisane w
                jej historii. Rzeczywista gra wymaga skonfigurowanego adaptera
                pogodowego.
              </div>
              <div className="form-grid">
                {field("rain", "Intensywność deszczu (%)", "number", 0, 100)}
                {field("wetness", "Mokrość nawierzchni (%)", "number", 0, 100)}
                {field("water", "Stojąca woda (%)", "number", 0, 100)}
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

function RunForm({
  data,
  onSubmit,
  onClose,
}: {
  data: Data;
  onSubmit: (body: unknown) => Promise<unknown>;
  onClose: () => void;
}) {
  const [exercise, setExercise] = useState(data.exercises[0]?.id || ""),
    [mode, setMode] = useState("individual"),
    [rows, setRows] = useState([
      {
        trainee_id: data.trainees[0]?.id || "",
        station_id:
          data.stations.find(
            (s) => s.online && s.state.game === "idle" && !s.attempt,
          )?.id || "",
        plan_item_id: "",
      },
    ]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const selected = data.exercises.find((e) => e.id === exercise);
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onSubmit({
        exercise_id: exercise,
        mode,
        participants: rows.map((r) => ({
          ...r,
          plan_item_id: r.plan_item_id || null,
        })),
      });
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
          {data.exercises.map((e) => (
            <option key={e.id} value={e.id}>
              {e.title} · {e.track_name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Tryb sesji
        <select
          value={mode}
          onChange={(e) => {
            setMode(e.target.value);
            setRows(rows.slice(0, 1));
          }}
        >
          <option value="individual">Indywidualna</option>
          <option value="multiplayer">Grupowa na wspólnym serwerze</option>
        </select>
      </label>
      {selected && (
        <div className="session-preview">
          <Flag size={18} />
          <span>
            {selected.car} · {selected.duration} min ·{" "}
            {selected.conditions.air_temp}°C ·{" "}
            {selected.conditions.rain ? "deszcz" : "sucho"}
          </span>
        </div>
      )}
      {rows.map((row, index) => {
        const items = data.plans
          .filter((p) => p.trainee_id === row.trainee_id)
          .flatMap((p) => p.items)
          .filter(
            (i) =>
              i.exercise_id === exercise &&
              ["either", mode].includes(i.mode) &&
              !["passed", "skipped"].includes(i.status),
          );
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
                station_id:
                  data.stations.find(
                    (s) =>
                      s.online &&
                      s.state.game === "idle" &&
                      !s.attempt &&
                      !rows.some((r) => r.station_id === s.id),
                  )?.id || "",
                plan_item_id: "",
              },
            ])
          }
        >
          <Plus size={16} />
          Dodaj uczestnika
        </button>
      )}
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
        <button className="button" disabled={busy || !data.exercises.length}>
          {busy ? "Zlecanie…" : "Przygotuj stanowiska"}
          <ArrowRight size={16} />
        </button>
      </div>
    </form>
  );
}
