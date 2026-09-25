/**
 * Kontrakt danych panelu monitoringu.
 *
 * Źródło: `GET /status/api.json` (ten sam origin, cookie wysyłane domyślnie).
 * Typy poniżej odwzorowują format "z drutu" (snake_case) 1:1, żeby parser i
 * kontrakt dało się czytać równolegle.
 *
 * Zasada: `parseStatus()` nigdy nie rzuca wyjątku. Każde brakujące lub błędne
 * pole staje się `null` / pustą tablicą / stanem `unknown`, a widok pokazuje
 * kreskę zamiast się wywalać.
 */

/** Wartość zastępcza dla brakujących danych. */
export const DASH = '—';

/** Dozwolone stany w całym kontrakcie. */
export type State = 'ok' | 'warning' | 'critical' | 'unknown' | 'disabled';

const STATE_RANK: Record<State, number> = {
  critical: 4,
  warning: 3,
  unknown: 2,
  ok: 1,
  disabled: 0,
};

/** Progi "miękkie" wyłącznie do wizualizacji (API nie zwraca stanu per metryka). */
export const USAGE_THRESHOLDS = { warning: 75, critical: 90 } as const;

/** Progi dla liczby dni do wygaśnięcia certyfikatu (tylko wyróżnienie wartości). */
export const CERT_THRESHOLDS = { warning: 30, critical: 14 } as const;

export interface HostSnapshot {
  cpu_percent: number | null;
  load1: number | null;
  load5: number | null;
  load15: number | null;
  mem_total_bytes: number | null;
  mem_used_bytes: number | null;
  mem_used_percent: number | null;
  swap_total_bytes: number | null;
  disk_total_bytes: number | null;
  disk_used_bytes: number | null;
  disk_used_percent: number | null;
  inodes_used_percent: number | null;
  uptime_seconds: number | null;
  time_utc: string | null;
}

export interface Check {
  id: string;
  name: string;
  group: string;
  kind: string;
  state: State;
  detail: string | null;
  url: string | null;
  /** Ścieżka, którą naprawdę sondujemy (np. "/" albo "/api"). */
  probe_path: string | null;
  /** Skąd ścieżka: label | probe | rule | default. */
  path_source: string | null;
  /** Gotowa etykieta do wklejenia, gdy ścieżki nikt nie ustawił świadomie. */
  health_label: string | null;
  since: string | null;
  latency_ms: number | null;
}

export interface Service {
  name: string;
  full_name: string | null;
  state: State;
  desired: number | null;
  running: number | null;
  image: string | null;
  cpu_percent: number | null;
  mem_bytes: number | null;
  /**
   * Limit CPU z spec usługi Swarm w rdzeniach (`NanoCPUs / 1e9`); `null` =
   * limit nieustawiony. Potrzebne do „teraz vs limit" na wykresie CPU.
   */
  cpu_limit_cores: number | null;
  /** Limit RAM z spec usługi Swarm w bajtach; `null` = brak limitu. */
  mem_limit_bytes: number | null;
  restarts_1h: number | null;
  replicas_text: string | null;
  /** Kiedy Swarm ostatnio aktualizował usługę (ISO Z); `null` = brak danych. */
  updated_at: string | null;
  /** Stan najnowszego zadania, które padło (`failed`/`rejected`); `null` = brak. */
  last_task_state: string | null;
  /** Treść `Status.Err` tego zadania — DLACZEGO usługa się przewraca. */
  last_task_error: string | null;
}

export interface Stack {
  name: string;
  state: State;
  services_running: number | null;
  services_desired: number | null;
  services: Service[];
}

export interface Cert {
  host: string;
  days_left: number | null;
  expires_at: string | null;
  state: State;
}

export interface Backup {
  state: State;
  last_success_at: string | null;
  age_hours: number | null;
  size_bytes: number | null;
  objects_in_r2: number | null;
  restore_test_days: number | null;
}

export interface Alert {
  name: string;
  severity: State;
  stack: string | null;
  summary: string | null;
  since: string | null;
}

export interface Login {
  service: string;
  ip: string;
  at: string | null;
}

export interface SshSource {
  ip: string;
  count: number;
}

export interface Security {
  ssh_failed_24h: number | null;
  ssh_bans_24h: number | null;
  /** Najaktywniejsze źródła nieudanych prób SSH (top 5), liczone w discovery. */
  ssh_failed_ips: SshSource[];
  /** Ile RÓŻNYCH adresów IP próbowało (null = brak danych, nie zero). */
  ssh_failed_sources: number | null;
  logins_24h: Login[];
  state: State;
}

export interface Tool {
  id: string;
  name: string;
  url: string | null;
  embed: boolean;
  /** Parametry dokładane do adresu podglądu (np. `kiosk` dla Grafany). */
  embed_query: string | null;
  state: State;
  kind: string;
  icon: string;
  description: string | null;
}

export interface StatusSnapshot {
  generated_at: string | null;
  overall: State;
  host: HostSnapshot | null;
  checks: Check[];
  stacks: Stack[];
  certs: Cert[];
  backup: Backup | null;
  alerts: Alert[];
  security: Security | null;
  tools: Tool[];
}

/* ------------------------------------------------------------------ *
 * Normalizacja stanu
 * ------------------------------------------------------------------ */

export function normalizeState(value: unknown): State {
  if (typeof value !== 'string') return 'unknown';
  const v = value.trim().toLowerCase();
  return v === 'ok' || v === 'warning' || v === 'critical' || v === 'disabled' || v === 'unknown'
    ? v
    : 'unknown';
}

/** Najgorszy stan z listy — do zbiorczych wskaźników sekcji. */
export function worstState(states: readonly State[]): State {
  if (states.length === 0) return 'unknown';
  return states.reduce<State>(
    (worst, s) => (STATE_RANK[s] > STATE_RANK[worst] ? s : worst),
    'ok',
  );
}

/** Krótka etykieta stanu (pojedynczy element). */
export function stateLabel(state: State): string {
  switch (state) {
    case 'ok':
      return 'OK';
    case 'warning':
      return 'Ostrzeżenie';
    case 'critical':
      return 'Awaria';
    case 'disabled':
      return 'Wyłączone';
    default:
      return 'Nieznany';
  }
}

/** Etykieta stanu ogólnego (nagłówek). */
export function overallLabel(state: State): string {
  switch (state) {
    case 'ok':
      return 'Wszystko sprawne';
    case 'warning':
      return 'Ostrzeżenia';
    case 'critical':
      return 'Awaria';
    case 'disabled':
      return 'Monitoring wyłączony';
    default:
      return 'Stan nieznany';
  }
}

/** Etykieta wagi alertu. */
export function severityLabel(severity: State): string {
  switch (severity) {
    case 'critical':
      return 'Krytyczny';
    case 'warning':
      return 'Ostrzeżenie';
    case 'ok':
      return 'Informacja';
    case 'disabled':
      return 'Wyłączony';
    default:
      return 'Nieznany';
  }
}

/** Stan wynikający z progu procentowego (CPU / RAM / dysk / inody). */
export function usageState(percent: number | null): State {
  if (percent === null) return 'unknown';
  if (percent >= USAGE_THRESHOLDS.critical) return 'critical';
  if (percent >= USAGE_THRESHOLDS.warning) return 'warning';
  return 'ok';
}

/** Stan wynikający z dni do wygaśnięcia (wyróżnienie wartości). */
export function certDaysState(days: number | null): State {
  if (days === null) return 'unknown';
  if (days <= CERT_THRESHOLDS.critical) return 'critical';
  if (days <= CERT_THRESHOLDS.warning) return 'warning';
  return 'ok';
}

/* ------------------------------------------------------------------ *
 * Formatowanie (pl-PL, liczby z przecinkiem, czas w UTC)
 * ------------------------------------------------------------------ */

const NBSP = '\u00a0';

function decimal(value: number, digits: number): string {
  return new Intl.NumberFormat('pl-PL', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function integer(value: number): string {
  return new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 0 }).format(value);
}

/** Odmiana rzeczownika "dzień" dla liczby całkowitej. */
function daysWord(n: number): string {
  const abs = Math.abs(n);
  return abs === 1 ? 'dzień' : 'dni';
}

export function fmtNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return decimal(value, digits);
}

export function fmtPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return `${decimal(value, digits)}${NBSP}%`;
}

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  return integer(value);
}

const BYTE_UNITS = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB'] as const;

/** Rozmiar w jednostkach binarnych (KiB/MiB/GiB). */
export function fmtBytes(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  const negative = value < 0;
  let n = Math.abs(value);
  let unit = 0;
  while (n >= 1024 && unit < BYTE_UNITS.length - 1) {
    n /= 1024;
    unit += 1;
  }
  const text = unit === 0 ? integer(n) : decimal(n, digits);
  return `${negative ? '-' : ''}${text}${NBSP}${BYTE_UNITS[unit]}`;
}

/** Czas trwania: "12 s", "45 min", "3 godz. 12 min", "74 dni 21 godz.". */
export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds) || seconds < 0) {
    return DASH;
  }
  const total = Math.floor(seconds);
  if (total < 60) return `${total}${NBSP}s`;

  const minutes = Math.floor(total / 60);
  if (total < 3600) return `${minutes}${NBSP}min`;

  const hours = Math.floor(total / 3600);
  if (total < 86400) {
    const restMin = minutes % 60;
    return restMin > 0
      ? `${hours}${NBSP}godz.${NBSP}${restMin}${NBSP}min`
      : `${hours}${NBSP}godz.`;
  }
  const days = Math.floor(total / 86400);
  const restHours = hours % 24;
  return restHours > 0
    ? `${days}${NBSP}${daysWord(days)}${NBSP}${restHours}${NBSP}godz.`
    : `${days}${NBSP}${daysWord(days)}`;
}

/** Uptime w dniach/godzinach (skrót dla nagłówka). */
export function fmtUptime(seconds: number | null | undefined): string {
  return fmtDuration(seconds);
}

/** Wiek w godzinach: "16 godz. 30 min". */
export function fmtHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours) || hours < 0) return DASH;
  if (hours < 1) return `${Math.round(hours * 60)}${NBSP}min`;
  const wholeHours = Math.floor(hours);
  const minutes = Math.round((hours - wholeHours) * 60);
  if (minutes === 60) return `${wholeHours + 1}${NBSP}godz.`;
  return minutes > 0
    ? `${wholeHours}${NBSP}godz.${NBSP}${minutes}${NBSP}min`
    : `${wholeHours}${NBSP}godz.`;
}

/** Liczba dni: "61,5 dnia", "1 dzień", "7 dni". */
export function fmtDays(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return DASH;
  if (Number.isInteger(value)) return `${integer(value)}${NBSP}${daysWord(value)}`;
  return `${decimal(value, 1)}${NBSP}dnia`;
}

function toDate(value: string | Date | null | undefined): Date | null {
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value;
  if (typeof value !== 'string' || value.trim() === '') return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

const dateTimeFmt = new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'UTC',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const timeFmt = new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'UTC',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
});

const shortDateFmt = new Intl.DateTimeFormat('pl-PL', {
  timeZone: 'UTC',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
});

/** "21.09.2026, 19:45:00 UTC". */
export function fmtDateTimeUTC(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return DASH;
  return `${dateTimeFmt.format(date)}${NBSP}UTC`;
}

/** "19:45:00 UTC". */
export function fmtTimeUTC(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return DASH;
  return `${timeFmt.format(date)}${NBSP}UTC`;
}

/** "21.09.2026". */
export function fmtDateUTC(value: string | Date | null | undefined): string {
  const date = toDate(value);
  if (!date) return DASH;
  return shortDateFmt.format(date);
}

/** "3 s temu", "5 min temu", "2 godz. temu" (ujemne → "za ..."). */
export function fmtAgo(value: string | Date | null | undefined, now: Date = new Date()): string {
  const date = toDate(value);
  if (!date) return DASH;
  const diffSeconds = Math.round((now.getTime() - date.getTime()) / 1000);
  const future = diffSeconds < 0;
  const abs = Math.abs(diffSeconds);

  let text: string;
  if (abs < 60) text = `${abs}${NBSP}s`;
  else if (abs < 3600) text = `${Math.floor(abs / 60)}${NBSP}min`;
  else if (abs < 86400) text = `${Math.floor(abs / 3600)}${NBSP}godz.`;
  else text = `${Math.floor(abs / 86400)}${NBSP}${daysWord(Math.floor(abs / 86400))}`;

  return future ? `za${NBSP}${text}` : `${text}${NBSP}temu`;
}

/* ------------------------------------------------------------------ *
 * Parser z walidacją (tolerancyjny — nigdy nie rzuca)
 * ------------------------------------------------------------------ */

type Rec = Record<string, unknown>;

function isRec(value: unknown): value is Rec {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function str(value: unknown): string | null {
  if (typeof value === 'string' && value.trim() !== '') return value;
  return null;
}

function bool(value: unknown): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.toLowerCase() === 'true' || value === '1';
  if (typeof value === 'number') return value !== 0;
  return false;
}

function arr(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function rows(value: unknown): Rec[] {
  return arr(value).filter(isRec);
}

function parseHost(raw: unknown): HostSnapshot | null {
  if (!isRec(raw)) return null;
  return {
    cpu_percent: num(raw.cpu_percent),
    load1: num(raw.load1),
    load5: num(raw.load5),
    load15: num(raw.load15),
    mem_total_bytes: num(raw.mem_total_bytes),
    mem_used_bytes: num(raw.mem_used_bytes),
    mem_used_percent: num(raw.mem_used_percent),
    swap_total_bytes: num(raw.swap_total_bytes),
    disk_total_bytes: num(raw.disk_total_bytes),
    disk_used_bytes: num(raw.disk_used_bytes),
    disk_used_percent: num(raw.disk_used_percent),
    inodes_used_percent: num(raw.inodes_used_percent),
    uptime_seconds: num(raw.uptime_seconds),
    time_utc: str(raw.time_utc),
  };
}

function parseChecks(raw: unknown): Check[] {
  return rows(raw).map((row, index) => ({
    id: str(row.id) ?? `check-${index}`,
    name: str(row.name) ?? str(row.id) ?? 'Bez nazwy',
    group: str(row.group) ?? 'Pozostałe',
    kind: str(row.kind) ?? 'unknown',
    state: normalizeState(row.state),
    detail: str(row.detail),
    url: str(row.url),
    probe_path: str(row.probe_path),
    path_source: str(row.path_source),
    health_label: str(row.health_label),
    since: str(row.since),
    latency_ms: num(row.latency_ms),
  }));
}

function parseServices(raw: unknown): Service[] {
  return rows(raw).map((row, index) => ({
    name: str(row.name) ?? `service-${index}`,
    full_name: str(row.full_name),
    state: normalizeState(row.state),
    desired: num(row.desired),
    running: num(row.running),
    image: str(row.image),
    cpu_percent: num(row.cpu_percent),
    mem_bytes: num(row.mem_bytes),
    // `num()` zamienia brak/None na null — panel dzięki temu mówi „brak limitu",
    // a nie „0 vCPU" (usługi bez limitów w cudzych stackach są normą).
    cpu_limit_cores: num(row.cpu_limit_cores),
    mem_limit_bytes: num(row.mem_limit_bytes),
    restarts_1h: num(row.restarts_1h),
    replicas_text: str(row.replicas_text),
    updated_at: str(row.updated_at),
    last_task_state: str(row.last_task_state),
    last_task_error: str(row.last_task_error),
  }));
}

function parseStacks(raw: unknown): Stack[] {
  return rows(raw).map((row, index) => ({
    name: str(row.name) ?? `stack-${index}`,
    state: normalizeState(row.state),
    services_running: num(row.services_running),
    services_desired: num(row.services_desired),
    services: parseServices(row.services),
  }));
}

function parseCerts(raw: unknown): Cert[] {
  return rows(raw).map((row) => ({
    host: str(row.host) ?? 'Bez nazwy',
    days_left: num(row.days_left),
    expires_at: str(row.expires_at),
    state: normalizeState(row.state),
  }));
}

function parseBackup(raw: unknown): Backup | null {
  if (!isRec(raw)) return null;
  return {
    state: normalizeState(raw.state),
    last_success_at: str(raw.last_success_at),
    age_hours: num(raw.age_hours),
    size_bytes: num(raw.size_bytes),
    objects_in_r2: num(raw.objects_in_r2),
    restore_test_days: num(raw.restore_test_days),
  };
}

function parseAlerts(raw: unknown): Alert[] {
  return rows(raw).map((row, index) => ({
    name: str(row.name) ?? `alert-${index}`,
    severity: normalizeState(row.severity),
    stack: str(row.stack),
    summary: str(row.summary),
    since: str(row.since),
  }));
}

function parseSecurity(raw: unknown): Security | null {
  if (!isRec(raw)) return null;
  return {
    ssh_failed_24h: num(raw.ssh_failed_24h),
    ssh_bans_24h: num(raw.ssh_bans_24h),
    ssh_failed_ips: rows(raw.ssh_failed_ips).map((row) => ({
      ip: str(row.ip) ?? DASH,
      count: num(row.count) ?? 0,
    })),
    ssh_failed_sources: num(raw.ssh_failed_sources),
    state: normalizeState(raw.state),
    logins_24h: rows(raw.logins_24h).map((row) => ({
      service: str(row.service) ?? 'unknown',
      ip: str(row.ip) ?? DASH,
      at: str(row.at),
    })),
  };
}

function parseTools(raw: unknown): Tool[] {
  return rows(raw).map((row, index) => ({
    id: str(row.id) ?? `tool-${index}`,
    name: str(row.name) ?? str(row.id) ?? 'Narzędzie',
    url: str(row.url),
    embed: bool(row.embed),
    embed_query: str(row.embed_query),
    state: normalizeState(row.state),
    kind: str(row.kind) ?? 'internal',
    icon: str(row.icon) ?? '',
    description: str(row.description),
  }));
}

/**
 * Zamienia odpowiedź `/status/api.json` na `StatusSnapshot`.
 * Nie rzuca wyjątku dla żadnych danych wejściowych.
 */
export function parseStatus(raw: unknown): StatusSnapshot {
  const root: Rec = isRec(raw) ? raw : {};
  return {
    generated_at: str(root.generated_at),
    overall: normalizeState(root.overall),
    host: parseHost(root.host),
    checks: parseChecks(root.checks),
    stacks: parseStacks(root.stacks),
    certs: parseCerts(root.certs),
    backup: parseBackup(root.backup),
    alerts: parseAlerts(root.alerts),
    security: parseSecurity(root.security),
    tools: parseTools(root.tools),
  };
}

/**
 * Czy sparsowana odpowiedź wygląda jak snapshot statusu?
 *
 * `parseStatus` jest celowo tolerancyjny, więc przypadkowy JSON (np. treść
 * błędu zwrócona z kodem 200) dałby „pusty” snapshot i skasowałby ostatnie
 * znane dane z ekranu. Ten test odrzuca takie odpowiedzi — panel pokazuje
 * wtedy banner i zachowuje poprzednie dane.
 */
export function isStatusSnapshot(snapshot: StatusSnapshot): boolean {
  return (
    snapshot.host !== null ||
    snapshot.backup !== null ||
    snapshot.security !== null ||
    snapshot.checks.length > 0 ||
    snapshot.stacks.length > 0 ||
    snapshot.certs.length > 0 ||
    snapshot.tools.length > 0 ||
    snapshot.generated_at !== null ||
    snapshot.overall !== 'unknown'
  );
}

/**
 * Stan ogólny liczony z danych, gdy API go nie poda (`overall` brak/nieznany).
 */
export function deriveOverall(snapshot: StatusSnapshot): State {
  if (snapshot.overall !== 'unknown') return snapshot.overall;
  const states: State[] = [
    ...snapshot.checks.map((c) => c.state),
    ...snapshot.stacks.map((s) => s.state),
    ...snapshot.certs.map((c) => c.state),
    ...snapshot.alerts.map((a) => a.severity),
  ];
  if (snapshot.backup) states.push(snapshot.backup.state);
  if (snapshot.security) states.push(snapshot.security.state);
  return states.length > 0 ? worstState(states) : 'unknown';
}

/** Grupowanie endpointów po `group`, z zachowaniem kolejności z API. */
export function groupChecks(checks: readonly Check[]): Array<{ group: string; items: Check[] }> {
  const groups = new Map<string, Check[]>();
  for (const check of checks) {
    const bucket = groups.get(check.group);
    if (bucket) bucket.push(check);
    else groups.set(check.group, [check]);
  }
  return [...groups].map(([group, items]) => ({ group, items }));
}
