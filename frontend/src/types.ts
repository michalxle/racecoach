export type User = {
  id: string;
  name: string;
  email: string;
  role: "instructor" | "trainee" | "service";
};
export type Trainee = User & { notes: string; created: number };
export type Section = { id: string; name: string; start: number; end: number };
export type Track = {
  id: string;
  game_id: string;
  name: string;
  layout: string;
  length: number;
  geometry: number[][];
  sections: Section[];
  version: string;
  source: string;
};
export type Conditions = {
  weather: string;
  air_temp: number;
  road_temp: number;
  grip: number;
  rain: number;
  time: string;
};
export type Exercise = {
  id: string;
  title: string;
  track_id: string;
  track_name: string;
  car: string;
  conditions: Conditions;
  duration: number;
  mode: string;
  revision: number;
  hardware_profile?: { degrees: number; strength: number } | null;
  reference?: { attempt_id: string; lap: number } | null;
};
export type PlanItem = {
  id: string;
  plan_id: string;
  exercise_id: string;
  title: string;
  goal: string;
  criteria: string;
  mode: string;
  sequence: number;
  scheduled: string | null;
  status: string;
  revision: number;
};
export type Plan = {
  id: string;
  trainee_id: string;
  trainee_name: string;
  title: string;
  items: PlanItem[];
};
export type Sample = {
  seq: number;
  t: number;
  lap: number;
  progress: number;
  x: number;
  y: number;
  z: number;
  speed: number;
  throttle: number;
  brake: number;
  steer: number;
  gear: number;
  rpm: number;
  valid: boolean;
};
export type Hardware = {
  connected: boolean;
  firmware?: string;
  degrees?: number;
  strength?: number;
  error?: string;
  max_strength?: number;
  live?: { position: number; torque: number; clipping: boolean };
  controllers?: { id: number; name: string; axes: number[]; buttons: number }[];
};
export type Station = {
  id: string;
  name: string;
  online: boolean;
  simulated: number;
  last_seen: number | null;
  state: {
    game: string;
    hardware: Hardware;
    telemetry?: Sample;
    error?: string;
    capabilities?: string[];
    catalog?: string[];
  };
  attempt: null | {
    id: string;
    trainee_id: string;
    trainee_name: string;
    run_id: string;
  };
};
export type Scenario = {
  exercise_id: string;
  track_key: string;
  track: Track;
  track_id: string;
  layout: string;
  car: string;
  conditions: Conditions;
  duration: number;
  mode: string;
};
export type Attempt = {
  id: string;
  run_id: string;
  trainee_id: string;
  trainee_name: string;
  station_id: string;
  station_name: string;
  plan_item_id: string | null;
  status: string;
  exercise_title: string;
  mode: string;
  created: number;
  sample_count: number;
  scenario: Scenario;
  note: string;
  config: Record<string, unknown>;
  result: { decision?: string };
};
export type Run = {
  id: string;
  mode: string;
  title: string;
  status: string;
  created: number;
  scenario: Scenario;
  weather_control?: boolean;
  participants: {
    id: string;
    status: string;
    station_id: string;
    trainee_id: string;
    trainee_name: string;
    station_name: string;
  }[];
};
export type Command = {
  id: string;
  station_name: string;
  kind: string;
  status: string;
  created: number;
  result: { error?: string; actual?: unknown };
};
export type Lap = {
  lap: number;
  duration: number;
  complete: boolean;
  usable: boolean;
  samples: number;
  max_gap: number;
};
export type Metrics = {
  duration: number;
  entry_speed: number;
  min_speed: number;
  exit_speed: number;
  brake_start: number | null;
  peak_brake: number;
};
export type SectionResult = Section & {
  current: Metrics;
  reference: Metrics;
  delta: number;
  accumulated: number;
  brake_difference_m: number | null;
};
export type Analysis = {
  track: Track;
  sections: SectionResult[];
  current: Sample[];
  reference: Sample[];
  duration: number;
  reference_duration: number;
  delta: number;
  lap: number;
  reference_lap: number;
  simulated: boolean;
  warnings: string[];
  quality: {
    current_samples: number;
    reference_samples: number;
    max_gap: number;
  };
};
export type Data = {
  trainees: Trainee[];
  plans: Plan[];
  stations: Station[];
  exercises: Exercise[];
  tracks: Track[];
  attempts: Attempt[];
  runs: Run[];
  commands: Command[];
};
