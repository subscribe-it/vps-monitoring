/**
 * Ikony narzędzi.
 *
 * `tools[].icon` z `/status/api.json` przychodzi w czasie działania, więc nie da
 * się jej wyrenderować komponentem `astro-icon` (ten pracuje w czasie budowania).
 * Dlatego budujemy raz, na etapie build, sprite SVG (`IconSprite.astro`) z tej
 * właśnie listy, a klient wstawia `<use href="#i-<nazwa>">`.
 *
 * Ikony spoza listy dostają `FALLBACK_TOOL_ICON` — panel nigdy nie zostaje
 * z pustym kafelkiem.
 */
export const TOOL_ICONS = [
  // nazwy używane wprost przez kontrakt
  'activity',
  'chart-line',
  'database',
  'bell',
  'heart-pulse',
  'container',
  // sensowne odpowiedniki dla innych narzędzi self-hosted
  'server',
  'server-cog',
  'cpu',
  'memory-stick',
  'hard-drive',
  'gauge',
  'globe',
  'cloud',
  'box',
  'package',
  'terminal',
  'square-terminal',
  'monitor',
  'network',
  'wrench',
  'scroll-text',
  'file-text',
  'radio',
  'send',
  'list',
  'layout-dashboard',
  'shield',
  'shield-check',
  'lock',
  'key-round',
  'git-branch',
  'archive',
  'database-backup',
  'siren',
  'link',
  'plug-zap',
  'radar',
  'users',
  'inbox',
  'folder-lock',
  'signal',
  'bug',
  'timer',
  'calendar-clock',
  'circle-dot',
] as const;

/** Ikona dla nieznanej nazwy z API. */
export const FALLBACK_TOOL_ICON = 'box';

const ICON_SET = new Set<string>(TOOL_ICONS);

/** Zamienia nazwę ikony z API na nazwę istniejącą w sprite. */
export function resolveToolIcon(name: string | null | undefined): string {
  if (typeof name !== 'string') return FALLBACK_TOOL_ICON;
  const clean = name.trim().toLowerCase().replace(/^lucide:/, '');
  return ICON_SET.has(clean) ? clean : FALLBACK_TOOL_ICON;
}

/** Identyfikator symbolu w sprite (do `<use href>`) wraz z `#`. */
export function spriteHref(name: string | null | undefined): string {
  return `#i-${resolveToolIcon(name)}`;
}
