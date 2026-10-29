import { useEffect, useId, useRef, useState } from "react";
import type { Analysis, Sample, SectionResult, Track } from "./types";
import { delta } from "./api";

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(700);
  useEffect(() => {
    if (!ref.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(200, entry.contentRect.width)),
    );
    observer.observe(ref.current);
    return () => observer.disconnect();
  }, []);
  return { ref, width };
}
const path = (points: number[][]) =>
  points
    .map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`)
    .join(" ");
export function nearest(points: Sample[], p: number) {
  return points.reduce(
    (best, item) =>
      Math.abs(item.progress - p) < Math.abs(best.progress - p) ? item : best,
    points[0],
  );
}

/** Kierowca na żywo na mapie (pozycja z ostatniego heartbeatu stanowiska). */
export type MapCar = {
  id: string;
  label: string;
  x: number;
  z: number;
  color: string;
};
export const carColors = [
  "#ff9a63",
  "#5aa9ff",
  "#73d6a3",
  "#f4d35e",
  "#d78cf2",
  "#ff6f91",
  "#7fdbda",
  "#c0c7cf",
];

export function TrackMap({
  track,
  sections = [],
  selected = null,
  onSelect,
  current = [],
  reference = [],
  progress,
  compact = false,
  cars = [],
  caption,
}: {
  track: Track;
  sections?: SectionResult[];
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  current?: Sample[];
  reference?: Sample[];
  progress?: number;
  compact?: boolean;
  cars?: MapCar[];
  caption?: string;
}) {
  const { ref, width } = useWidth();
  const height = compact ? 250 : width < 400 ? 270 : 360;
  const xs = track.geometry.map((p) => p[0]),
    zs = track.geometry.map((p) => p[1]);
  const minX = Math.min(...xs),
    maxX = Math.max(...xs),
    minZ = Math.min(...zs),
    maxZ = Math.max(...zs);
  const scale = Math.min(
    (width - 80) / Math.max(1, maxX - minX),
    (height - 70) / Math.max(1, maxZ - minZ),
  );
  const project = (x: number, z: number) => [
    width / 2 + (x - (minX + maxX) / 2) * scale,
    height / 2 + (z - (minZ + maxZ) / 2) * scale,
  ];
  const outline = track.geometry.map((p) => project(p[0], p[1]));
  const base = reference.length ? reference : current;
  const position =
    current.length && progress != null ? nearest(current, progress) : null;
  return (
    <div className="track-map" ref={ref}>
      <div className="map-caption">
        <span className="eyebrow">
          {track.source === "demo" ? "TOR DEMONSTRACYJNY" : "MAPA TORU"}
        </span>
        <span>
          {(track.length / 1000).toFixed(2)} km ·{" "}
          {track.layout || "pełna pętla"}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`Mapa ${track.name}, sekcje i linie przejazdu`}
      >
        <defs>
          <pattern
            id="track-grid"
            width="24"
            height="24"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="1" cy="1" r=".7" fill="#33434e" />
          </pattern>
        </defs>
        <rect width={width} height={height} fill="url(#track-grid)" />
        <path
          d={path(outline)}
          fill="none"
          stroke="#25333e"
          strokeWidth="22"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <path
          d={path(outline)}
          fill="none"
          stroke="#596670"
          strokeWidth="2"
          strokeLinejoin="round"
        />
        {sections.length ? (
          sections.map((s) => {
            const pts = base.length
              ? base
                  .filter((p) => p.progress >= s.start && p.progress <= s.end)
                  .map((p) => project(p.x, p.z))
              : outline.slice(
                  Math.floor(s.start * (outline.length - 1)),
                  Math.ceil(s.end * (outline.length - 1)) + 1,
                );
            const color =
              Math.abs(s.delta) < 0.03
                ? "#aeb9c0"
                : s.delta > 0
                  ? "#f08a68"
                  : "#73bdb1";
            return (
              <path
                key={s.id}
                d={path(pts)}
                fill="none"
                stroke={color}
                opacity={selected && selected !== s.id ? 0.35 : 1}
                strokeWidth={selected === s.id ? 11 : 7}
                strokeLinecap="round"
                onClick={() => onSelect?.(selected === s.id ? null : s.id)}
                className={onSelect ? "map-section" : ""}
              />
            );
          })
        ) : (
          <path
            d={path(outline)}
            fill="none"
            stroke="#ef824d"
            strokeWidth="5"
            strokeLinejoin="round"
          />
        )}
        {reference.length > 0 && (
          <path
            d={path(reference.map((p) => project(p.x, p.z)))}
            fill="none"
            stroke="#8caac4"
            strokeWidth="2"
            strokeDasharray="5 4"
            opacity=".8"
          />
        )}
        {current.length > 0 && (
          <path
            d={path(current.map((p) => project(p.x, p.z)))}
            fill="none"
            stroke="#f8d0b0"
            strokeWidth="1.4"
            opacity=".9"
          />
        )}
        {track.sections
          .filter((s) => width >= 400 || s.start > 0.01)
          .map((s) => {
            const mid =
              outline[
                Math.min(
                  outline.length - 1,
                  Math.floor(((s.start + s.end) / 2) * (outline.length - 1)),
                )
              ];
            return (
              <g key={s.id} transform={`translate(${mid[0]},${mid[1] - 18})`}>
                <rect
                  x="-13"
                  y="-12"
                  width="26"
                  height="22"
                  rx="5"
                  fill="#15212b"
                />
                <text
                  textAnchor="middle"
                  dominantBaseline="middle"
                  fill="#e4edf2"
                  fontSize="11"
                >
                  S{s.id}
                </text>
              </g>
            );
          })}
        <g transform={`translate(${outline[0][0]},${outline[0][1]})`}>
          <rect x="-4" y="-13" width="8" height="26" rx="2" fill="#eef2f4" />
          {width >= 400 && (
            <text x="13" y="6" fill="#eef2f4" fontSize="11">
              START
            </text>
          )}
        </g>
        {cars.map((c) => {
          const [x, y] = project(c.x, c.z);
          return (
            <g
              key={c.id}
              className="map-car"
              style={{
                transform: `translate(${x.toFixed(1)}px,${y.toFixed(1)}px)`,
              }}
            >
              <circle r="11" fill={c.color} opacity=".22" />
              <circle r="6" fill={c.color} stroke="#0d161d" strokeWidth="2" />
              <text
                y="-12"
                textAnchor="middle"
                fill="#eef2f4"
                fontSize="11"
                fontWeight="600"
              >
                {c.label}
              </text>
            </g>
          );
        })}
        {position && (
          <g
            transform={`translate(${project(position.x, position.z).join(",")})`}
          >
            <circle r="10" fill="#fff1e6" opacity=".18" />
            <circle r="5" fill="#ff9a63" stroke="#fff1e6" strokeWidth="2" />
          </g>
        )}
      </svg>
      <div className="map-bottom">
        <strong>{track.name}</strong>
        <span>
          {caption ??
            (sections.length
              ? "Kolor: wynik lokalnej sekcji"
              : "Geometria trasy")}
        </span>
      </div>
    </div>
  );
}

export function Meter({
  label,
  value,
  color = "orange",
}: {
  label: string;
  value: number;
  color?: string;
}) {
  return (
    <div className="meter">
      <div>
        <span>{label}</span>
        <strong>{Math.round(value * 100)}%</strong>
      </div>
      <div className="meter-track">
        <i
          className={color}
          style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
        />
      </div>
    </div>
  );
}

export function TelemetryChart({
  analysis,
  field,
  label,
  unit,
  range,
  progress,
  onProgress,
}: {
  analysis: Analysis;
  field: "speed" | "throttle" | "brake" | "steer";
  label: string;
  unit: string;
  range: [number, number];
  progress: number;
  onProgress: (p: number) => void;
}) {
  const { ref, width } = useWidth();
  const id = useId().replace(/:/g, "");
  const height = 185,
    L = 48,
    R = 16,
    T = 15,
    B = 32;
  const inRange = (s: Sample) =>
    s.progress >= range[0] && s.progress <= range[1];
  const current = analysis.current.filter(inRange),
    reference = analysis.reference.filter(inRange);
  const multiplier = field === "throttle" || field === "brake" ? 100 : 1;
  const all = [...current, ...reference].map((p) => p[field] * multiplier);
  const low = field === "steer" ? Math.min(-0.1, ...all) : 0,
    high =
      field === "speed"
        ? Math.max(80, ...all) * 1.1
        : field === "steer"
          ? Math.max(0.1, ...all) * 1.1
          : 100;
  const x = (p: number) =>
    L + ((p - range[0]) / (range[1] - range[0])) * (width - L - R);
  const y = (v: number) =>
    height - B - ((v - low) / (high - low)) * (height - T - B);
  const plot = (samples: Sample[]) =>
    path(samples.map((p) => [x(p.progress), y(p[field] * multiplier)]));
  const own = nearest(analysis.current, progress),
    target = nearest(analysis.reference, progress);
  return (
    <div className="chart" ref={ref}>
      <div className="chart-heading">
        <strong>
          {label} <span>{unit}</span>
        </strong>
        <span>
          <i className="legend-dot orange" />
          {(own[field] * multiplier).toFixed(field === "steer" ? 2 : 0)}
          <i className="legend-dot blue" />
          {(target[field] * multiplier).toFixed(field === "steer" ? 2 : 0)}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={`${label} kursanta i wzorca względem położenia na torze`}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * width;
          onProgress(
            Math.min(
              range[1],
              Math.max(
                range[0],
                range[0] + ((px - L) / (width - L - R)) * (range[1] - range[0]),
              ),
            ),
          );
        }}
      >
        <defs>
          <clipPath id={id}>
            <rect x={L} y={T} width={width - L - R} height={height - T - B} />
          </clipPath>
        </defs>
        {[0, 0.5, 1].map((t) => {
          const value = low + (high - low) * t;
          return (
            <g key={t}>
              <line
                x1={L}
                x2={width - R}
                y1={y(value)}
                y2={y(value)}
                stroke="#e9edf0"
              />
              <text
                x={L - 9}
                y={y(value) + 4}
                textAnchor="end"
                fill="#77838b"
                fontSize="11"
              >
                {value.toFixed(field === "steer" ? 1 : 0)}
              </text>
            </g>
          );
        })}
        {[0, 0.5, 1].map((t) => {
          const p = range[0] + t * (range[1] - range[0]);
          return (
            <text
              key={t}
              x={x(p)}
              y={height - 10}
              textAnchor={t === 0 ? "start" : t === 1 ? "end" : "middle"}
              fill="#77838b"
              fontSize="11"
            >
              {Math.round(p * analysis.track.length)} m
            </text>
          );
        })}
        <g clipPath={`url(#${id})`}>
          <path
            d={plot(reference)}
            fill="none"
            stroke="#7b98b2"
            strokeWidth="1.6"
            strokeDasharray="4 3"
          />
          <path
            d={plot(current)}
            fill="none"
            stroke="#e7773e"
            strokeWidth="2"
          />
          {progress >= range[0] && progress <= range[1] && (
            <>
              <line
                x1={x(progress)}
                x2={x(progress)}
                y1={T}
                y2={height - B}
                stroke="#8998a3"
                strokeDasharray="3 3"
              />
              <circle
                cx={x(progress)}
                cy={y(own[field] * multiplier)}
                r="3.5"
                fill="#e7773e"
              />
            </>
          )}
        </g>
      </svg>
    </div>
  );
}

export function DeltaValue({ value }: { value: number | null | undefined }) {
  return (
    <span
      className={`delta ${value == null ? "" : value > 0.03 ? "loss" : value < -0.03 ? "gain" : "neutral"}`}
    >
      {delta(value)}
    </span>
  );
}
