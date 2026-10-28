import { useEffect, useMemo, useState } from "react";
import { Award, Medal, Timer, Trophy } from "lucide-react";
import { api, date } from "./api";
import { SearchSelect } from "./content";
import type { Data } from "./types";

export type CoachTips = {
  lap_no?: number;
  summary: string;
  lines: { corner: number; loss_ms: number; text: string }[];
};
export type CoachState = {
  state?: string;
  live?: {
    lap_no?: number;
    current_ms?: number;
    delta_ms?: number | null;
    last_ms?: number | null;
    last_valid?: boolean;
    best_ms?: number | null;
  };
  pb_ms?: number | null;
  ref?: { label: string } | null;
  tips?: CoachTips | null;
  offtracks?: number;
  race?: { laps: number; done: boolean } | null;
  message?: { text: string } | null;
};
export type ClassRow = {
  attempt_id: string;
  position: number;
  trainee_name: string;
  station_name: string;
  laps: number;
  total_ms: number;
  best_ms: number | null;
  gap_ms: number | null;
  finished: boolean;
};

export function ms(value: number | null | undefined) {
  if (!value || value <= 0) return "—";
  const m = Math.floor(value / 60000),
    s = Math.floor((value % 60000) / 1000),
    x = Math.floor(value % 1000);
  return `${m}:${String(s).padStart(2, "0")}.${String(x).padStart(3, "0")}`;
}
const signed = (value: number) =>
  `${value >= 0 ? "+" : "−"}${(Math.abs(value) / 1000).toFixed(2)}`;

/** Trener na żywo w karcie stanowiska: okrążenie, delta, czasy i ostatnie wskazówki. */
export function CoachLive({ coach }: { coach: CoachState }) {
  const live = coach.live ?? {};
  const lap = (live.lap_no ?? 0) + 1;
  const delta = live.delta_ms;
  return (
    <div className="coach-live">
      <div className="coach-row">
        <div>
          <span>
            {coach.race
              ? `Wyścig ${Math.min(lap, coach.race.laps)}/${coach.race.laps}${coach.race.done ? " · meta" : ""}`
              : `Okrążenie ${lap}`}
          </span>
          <strong className="mono">{ms(live.current_ms)}</strong>
        </div>
        <div>
          <span>Delta{coach.ref ? ` · ${coach.ref.label}` : ""}</span>
          <strong
            className={`mono ${delta == null ? "" : delta < 0 ? "good" : "bad"}`}
          >
            {delta == null ? "—" : signed(delta)}
          </strong>
        </div>
        <div>
          <span>Ostatnie</span>
          <strong
            className={`mono ${live.last_ms && live.last_valid === false ? "bad" : ""}`}
          >
            {ms(live.last_ms)}
          </strong>
        </div>
        <div>
          <span>Najlepsze / rekord</span>
          <strong className="mono">
            {ms(live.best_ms)} <small>/ {ms(coach.pb_ms)}</small>
          </strong>
        </div>
      </div>
      {coach.tips && (
        <div className="coach-tips">
          <b>Po okrążeniu {coach.tips.lap_no}:</b> {coach.tips.summary}
          {coach.tips.lines.map((l) => (
            <div key={l.corner}>
              <span className="corner">{l.corner}</span>
              {l.text.replace(/^Zakręt \d+, /, "")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Classification({ rows }: { rows: ClassRow[] }) {
  if (!rows.length) return null;
  return (
    <table className="classification">
      <thead>
        <tr>
          <th>Poz.</th>
          <th>Kursant</th>
          <th>Okr.</th>
          <th>Czas</th>
          <th>Strata</th>
          <th>Najlepsze</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.attempt_id} className={r.finished ? "finished" : ""}>
            <td>{r.position}</td>
            <td>
              {r.trainee_name}
              <small> · {r.station_name}</small>
            </td>
            <td>{r.laps}</td>
            <td className="mono">{ms(r.total_ms)}</td>
            <td className="mono">
              {r.position === 1
                ? "—"
                : r.gap_ms == null
                  ? "okr."
                  : signed(r.gap_ms)}
            </td>
            <td className="mono">{ms(r.best_ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

type LapRow = {
  lap_no: number;
  time_ms: number;
  valid: boolean;
  offtracks: number;
  reason: string;
  tips: Partial<CoachTips>;
};

/** Okrążenia zmierzone przez grę i wskazówki trenera dla jednej próby. */
export function AttemptCoach({ attemptId }: { attemptId: string }) {
  const [laps, setLaps] = useState<LapRow[] | null>(null);
  useEffect(() => {
    setLaps(null);
    api<LapRow[]>(`/attempts/${attemptId}/coach`)
      .then(setLaps)
      .catch(() => setLaps([]));
  }, [attemptId]);
  if (!laps || !laps.length) return null;
  const best = Math.min(...laps.filter((l) => l.valid).map((l) => l.time_ms));
  return (
    <section className="panel coach-laps">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">TRENER NA STANOWISKU</span>
          <h2>Okrążenia z gry i wskazówki</h2>
        </div>
      </div>
      <ol>
        {laps.map((l) => (
          <li key={l.lap_no} className={l.valid ? "" : "invalid"}>
            <div className="lap-head">
              <b>Okrążenie {l.lap_no}</b>
              <span
                className={`mono ${l.time_ms === best ? "best" : ""}`}
                title={l.valid ? undefined : `Nieważne: ${l.reason}`}
              >
                {ms(l.time_ms)}
              </span>
              <span className="muted">
                {l.valid
                  ? l.offtracks
                    ? `${l.offtracks} wyjazdów`
                    : "czyste"
                  : `nieważne (${l.reason || "poza torem"})`}
              </span>
            </div>
            {l.tips?.summary && <p>{l.tips.summary}</p>}
            {l.tips?.lines?.map((t) => (
              <p key={t.corner} className="tip">
                <span className="corner">{t.corner}</span>
                {t.text.replace(/^Zakręt \d+, /, "")}
              </p>
            ))}
          </li>
        ))}
      </ol>
    </section>
  );
}

type Combo = {
  track: string;
  layout: string;
  car: string;
  track_name: string;
  laps: number;
  valid_laps: number;
  record_ms: number;
  drivers: number;
};
type BoardRow = {
  rank: number;
  trainee_id: string;
  name: string;
  best_ms: number;
  gap_ms: number;
  laps: number;
  date: number | null;
};
type Profile = {
  stats: {
    laps: number;
    valid_laps: number;
    offtracks: number;
    distance_km: number;
    sessions: number;
  };
  records: {
    track: string;
    layout: string;
    car: string;
    track_name: string;
    best_ms: number;
    date: number;
    rank: number | null;
    drivers: number;
    progress: { date: number; time_ms: number }[];
  }[];
  races: {
    run_id: string;
    date: number;
    position: number;
    drivers: number;
    track_name: string;
    car: string;
  }[];
  achievements: {
    title: string;
    desc: string;
    done: boolean;
    progress: string;
  }[];
};

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const min = Math.min(...points),
    max = Math.max(...points),
    span = max - min || 1;
  const d = points
    .map(
      (p, i) =>
        `${i ? "L" : "M"}${(i / (points.length - 1)) * 100},${4 + ((p - min) / span) * 22}`,
    )
    .join(" ");
  return (
    <svg
      className="sparkline"
      viewBox="0 0 100 30"
      preserveAspectRatio="none"
      role="img"
      aria-label="Postęp czasów okrążeń"
    >
      <path d={d} />
    </svg>
  );
}

/** Rankingi auto+tor, rekordy, postęp i osiągnięcia kursantów. */
export function Rankings({
  data,
  privileged,
  selfId,
}: {
  data: Data;
  privileged: boolean;
  selfId: string;
}) {
  const [combos, setCombos] = useState<Combo[]>([]),
    [combo, setCombo] = useState(""),
    [board, setBoard] = useState<BoardRow[]>([]),
    [trainee, setTrainee] = useState(privileged ? "" : selfId),
    [profile, setProfile] = useState<Profile | null>(null);
  useEffect(() => {
    api<Combo[]>("/combos")
      .then((list) => {
        setCombos(list);
        if (list[0])
          setCombo(`${list[0].track}|${list[0].layout}|${list[0].car}`);
      })
      .catch(() => setCombos([]));
  }, []);
  useEffect(() => {
    if (!combo) return;
    const [track, layout, car] = combo.split("|");
    api<BoardRow[]>(
      `/leaderboard?${new URLSearchParams({ track, layout, car })}`,
    )
      .then(setBoard)
      .catch(() => setBoard([]));
  }, [combo]);
  useEffect(() => {
    if (!trainee && privileged && data.trainees[0])
      setTrainee(data.trainees[0].id);
  }, [data.trainees, privileged, trainee]);
  useEffect(() => {
    if (!trainee) return;
    api<Profile>(`/trainees/${trainee}/profile`)
      .then(setProfile)
      .catch(() => setProfile(null));
  }, [trainee]);
  const options = useMemo(
    () =>
      combos.map((c) => ({
        value: `${c.track}|${c.layout}|${c.car}`,
        label: `${c.track_name || c.track} · ${data.carNames[c.car] ?? c.car}`,
        detail: `rekord ${ms(c.record_ms)} · ${c.drivers} kursantów · ${c.valid_laps} ważnych okrążeń`,
      })),
    [combos, data.carNames],
  );
  return (
    <>
      <div className="page-intro">
        <div>
          <div className="eyebrow">WYNIKI</div>
          <h1>Rankingi i rekordy.</h1>
          <p>
            Najlepsze ważne okrążenia na każdej kombinacji auta i toru, rekordy
            osobiste, postęp i osiągnięcia kursantów.
          </p>
        </div>
      </div>
      <div className="rankings-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">RANKING</span>
              <h2>Najlepsze czasy</h2>
            </div>
          </div>
          <div className="panel-body">
            {options.length ? (
              <SearchSelect
                label="Auto i tor"
                value={combo}
                options={options}
                onChange={setCombo}
              />
            ) : (
              <p className="muted">
                Ranking pojawi się po pierwszych okrążeniach zmierzonych przez
                trenera na stanowisku.
              </p>
            )}
            {board.length > 0 && (
              <table className="classification">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Kursant</th>
                    <th>Czas</th>
                    <th>Strata</th>
                    <th>Okr.</th>
                    <th>Data</th>
                  </tr>
                </thead>
                <tbody>
                  {board.map((r) => (
                    <tr
                      key={r.trainee_id}
                      className={r.rank === 1 ? "finished" : ""}
                    >
                      <td>{r.rank === 1 ? <Trophy size={14} /> : r.rank}</td>
                      <td>{r.name}</td>
                      <td className="mono">{ms(r.best_ms)}</td>
                      <td className="mono">
                        {r.rank === 1 ? "—" : signed(r.gap_ms)}
                      </td>
                      <td>{r.laps}</td>
                      <td>{r.date ? date(r.date) : "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">PROFIL</span>
              <h2>Rekordy i osiągnięcia</h2>
            </div>
          </div>
          <div className="panel-body">
            {privileged && (
              <SearchSelect
                label="Kursant"
                value={trainee}
                options={data.trainees.map((t) => ({
                  value: t.id,
                  label: t.name,
                  detail: t.email,
                }))}
                onChange={setTrainee}
              />
            )}
            {profile && (
              <>
                <div className="profile-stats">
                  <div>
                    <Timer size={15} />
                    <b>{profile.stats.laps}</b> okrążeń
                  </div>
                  <div>
                    <b>{profile.stats.valid_laps}</b> ważnych
                  </div>
                  <div>
                    <b>{profile.stats.distance_km}</b> km
                  </div>
                  <div>
                    <b>{profile.stats.sessions}</b> sesji
                  </div>
                </div>
                <h3>Rekordy osobiste</h3>
                {profile.records.length ? (
                  <ul className="records">
                    {profile.records.map((r) => (
                      <li key={`${r.track}|${r.layout}|${r.car}`}>
                        <div>
                          <b>{r.track_name || r.track}</b>
                          <small>{data.carNames[r.car] ?? r.car}</small>
                        </div>
                        <Sparkline points={r.progress.map((p) => p.time_ms)} />
                        <div className="record-time">
                          <span className="mono">{ms(r.best_ms)}</span>
                          <small>
                            {r.rank ? `${r.rank}. z ${r.drivers}` : ""}
                          </small>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">Brak ważnych okrążeń.</p>
                )}
                {profile.races.length > 0 && (
                  <>
                    <h3>Wyścigi</h3>
                    <ul className="records">
                      {profile.races.map((r) => (
                        <li key={r.run_id}>
                          <div>
                            <b>{r.track_name}</b>
                            <small>
                              {date(r.date)} · {data.carNames[r.car] ?? r.car}
                            </small>
                          </div>
                          <div className="record-time">
                            <span>
                              {r.position <= 3 && <Medal size={14} />}{" "}
                              {r.position}. miejsce
                            </span>
                            <small>z {r.drivers}</small>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </>
                )}
                <h3>Osiągnięcia</h3>
                <div className="achievements">
                  {profile.achievements.map((a) => (
                    <div key={a.title} className={a.done ? "done" : ""}>
                      <Award size={18} />
                      <b>{a.title}</b>
                      <small>{a.desc}</small>
                      {!a.done && a.progress && <em>{a.progress}</em>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
