/**
 * Filtrowanie, sortowanie i „fokus" dla panelu — czysta logika bez DOM.
 *
 * Dlaczego osobny moduł i dlaczego bez importów:
 *  - te reguły łatwo oprzeć na fałszywych założeniach („puste = wszystko",
 *    „najgorszy stan znaczy największa liczba") i nikt tego nie złapie okiem,
 *    więc muszą być testowalne bez przeglądarki — patrz `scripts/ci/check_filtry.ts`;
 *  - testy uruchamiamy Node'em z type-strippingiem, a Node nie rozwiązuje
 *    importów bez rozszerzenia. Moduł jest więc samowystarczalny: deklaruje
 *    własne typy strukturalne (podzbiór pól z `status.ts`) i używa generyków,
 *    żeby oddawać dokładnie te obiekty, które dostał.
 *
 * Semantyka filtrów (zapisana wprost, bo to najczęstsze źródło pomyłek):
 *   wszystko   — bez zawężania,
 *   problemy   — warning | critical | unknown („nie wiem" też wymaga spojrzenia),
 *   krytyczne  — critical,
 *   zdrowe     — ok (disabled wypada wszędzie poza „wszystko").
 */

/* ------------------------------------------------------------------ *
 * Typy strukturalne (podzbiór `status.ts`)
 * ------------------------------------------------------------------ */

export interface Stanowe {
  state: string;
}

export interface Uslugowe extends Stanowe {
  name: string;
  full_name?: string | null;
  desired?: number | null;
  running?: number | null;
  image?: string | null;
  cpu_percent?: number | null;
  mem_bytes?: number | null;
  restarts_1h?: number | null;
  replicas_text?: string | null;
}

export interface Stackowe<T extends Uslugowe> extends Stanowe {
  name: string;
  services_running?: number | null;
  services_desired?: number | null;
  services: T[];
}

/* ------------------------------------------------------------------ *
 * Filtr
 * ------------------------------------------------------------------ */

export type StanFiltra = 'wszystko' | 'problemy' | 'krytyczne' | 'zdrowe';
export type KluczSortowania = 'stan' | 'usluga' | 'repliki' | 'cpu' | 'ram' | 'restarty' | 'obraz';
export type Kierunek = 'asc' | 'desc';

export interface Filtr {
  q: string;
  stan: StanFiltra;
  sort: KluczSortowania;
  kierunek: Kierunek;
}

export const PUSTY_FILTR: Filtr = { q: '', stan: 'wszystko', sort: 'stan', kierunek: 'desc' };

export const STANY_FILTRA: readonly StanFiltra[] = ['wszystko', 'problemy', 'krytyczne', 'zdrowe'];
export const KLUCZE_SORTOWANIA: readonly KluczSortowania[] = [
  'stan',
  'usluga',
  'repliki',
  'cpu',
  'ram',
  'restarty',
  'obraz',
];

const RANGA: Record<string, number> = { critical: 4, warning: 3, unknown: 2, disabled: 1, ok: 0 };
/** Ranga dla stanu spoza słownika (np. nowa wartość z API) — jak „nie wiem". */
const RANGA_NIEZNANY = 2;

/** Ranga stanu — do sortowania „najgorszy pierwszy". */
export function rangaStanu(state: string): number {
  return RANGA[state] ?? RANGA_NIEZNANY;
}

/* ------------------------------------------------------------------ *
 * Dopasowanie tekstu i stanu
 * ------------------------------------------------------------------ */

/**
 * Normalizacja do porównań: małe litery, bez znaków diakrytycznych, bez
 * nadmiarowych spacji. Dzięki temu „usługa" i „usluga" trafiają to samo,
 * a wpisanie „cpu" nie wymaga polskiej klawiatury.
 */
export function normalizuj(tekst: unknown): string {
  if (tekst === null || tekst === undefined) return '';
  return String(tekst)
    // Najpierw małe litery: `Ł` (U+0141) nie dekomponuje się w NFD, więc
    // podmiana `ł` musi trafić już po obniżeniu wielkości liter.
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\u0142/g, 'l')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Czy tekst pasuje do zapytania? Wszystkie słowa zapytania muszą wystąpić
 * (AND), w dowolnej kolejności — „monitoring panel" znajduje usługę
 * `monitoring_panel` i odwrotnie.
 */
export function pasujeTekst(q: string, ...pola: Array<string | null | undefined>): boolean {
  const zapytanie = normalizuj(q);
  if (!zapytanie) return true;
  const slowa = zapytanie.split(' ');
  const tresc = normalizuj(pola.filter(Boolean).join(' '));
  return slowa.every((slowo) => tresc.includes(slowo));
}

export function pasujeStan(state: string, stan: StanFiltra): boolean {
  switch (stan) {
    case 'problemy':
      return state === 'warning' || state === 'critical' || state === 'unknown';
    case 'krytyczne':
      return state === 'critical';
    case 'zdrowe':
      return state === 'ok';
    default:
      return true;
  }
}

export function czyAktywny(f: Filtr): boolean {
  return (
    normalizuj(f.q).length > 0 ||
    f.stan !== PUSTY_FILTR.stan ||
    f.sort !== PUSTY_FILTR.sort ||
    f.kierunek !== PUSTY_FILTR.kierunek
  );
}

export function etykietaStanu(stan: StanFiltra): string {
  switch (stan) {
    case 'problemy':
      return 'Problemy';
    case 'krytyczne':
      return 'Krytyczne';
    case 'zdrowe':
      return 'Zdrowe';
    default:
      return 'Wszystko';
  }
}

export function etykietaSortowania(klucz: KluczSortowania): string {
  switch (klucz) {
    case 'usluga':
      return 'Usługa';
    case 'repliki':
      return 'Repliki';
    case 'cpu':
      return 'CPU';
    case 'ram':
      return 'RAM';
    case 'restarty':
      return 'Restarty 1 h';
    case 'obraz':
      return 'Obraz';
    default:
      return 'Najgorszy stan';
  }
}

export function opisFiltra(f: Filtr): string {
  const czesci: string[] = [];
  if (normalizuj(f.q)) czesci.push(`„${f.q.trim()}"`);
  if (f.stan !== 'wszystko') czesci.push(etykietaStanu(f.stan).toLowerCase());
  if (f.sort !== PUSTY_FILTR.sort || f.kierunek !== PUSTY_FILTR.kierunek) {
    czesci.push(`${etykietaSortowania(f.sort)} ${f.kierunek === 'desc' ? '↓' : '↑'}`);
  }
  return czesci.join(' · ');
}

/* ------------------------------------------------------------------ *
 * Fokus
 * ------------------------------------------------------------------ */

/** Klucz fokusu: `stack/usluga` (bez ukośników w częściach). */
export function kluczFokusa(stack: string, usluga: string): string {
  return `${stack}/${usluga}`;
}

export function rozbijFokus(fokus: string | null): { stack: string; usluga: string } | null {
  if (!fokus) return null;
  const czesci = fokus.split('/');
  if (czesci.length !== 2 || !czesci[0] || !czesci[1]) return null;
  return { stack: czesci[0], usluga: czesci[1] };
}

/* ------------------------------------------------------------------ *
 * Sortowanie usług i stacków
 * ------------------------------------------------------------------ */

function wartosc(usluga: Uslugowe, klucz: KluczSortowania): number | string {
  switch (klucz) {
    case 'cpu':
      return usluga.cpu_percent ?? -1;
    case 'ram':
      return usluga.mem_bytes ?? -1;
    case 'restarty':
      return usluga.restarts_1h ?? -1;
    case 'repliki':
      /*
       * Klucz sortowania to DEFICYT (ile replik brakuje), nie „running/desired":
       * usługa 2/3 jest ważniejsza niż 1/1, a przy równych deficytach decyduje
       * nazwa. Kolumna w tabeli nadal pokazuje pełny stosunek.
       */
      return Math.max(0, (usluga.desired ?? 0) - (usluga.running ?? 0));
    case 'obraz':
      return normalizuj(usluga.image);
    case 'usluga':
      return normalizuj(usluga.name);
    default:
      return rangaStanu(usluga.state);
  }
}

function porownaj(a: number | string, b: number | string): number {
  if (typeof a === 'number' && typeof b === 'number') return a - b;
  return String(a).localeCompare(String(b), 'pl');
}

export function sortujUslugi<T extends Uslugowe>(
  uslugi: readonly T[],
  klucz: KluczSortowania,
  kierunek: Kierunek,
): T[] {
  const znak = kierunek === 'desc' ? -1 : 1;
  return [...uslugi].sort((a, b) => {
    const roznica = porownaj(wartosc(a, klucz), wartosc(b, klucz)) * znak;
    // Stabilnie: przy równych wartościach alfabetycznie, żeby kolejność nie
    // skakała między odświeżeniami.
    return roznica !== 0 ? roznica : a.name.localeCompare(b.name, 'pl');
  });
}

/* ------------------------------------------------------------------ *
 * Widok stacków (filtr + sort + fokus)
 * ------------------------------------------------------------------ */

export interface WidokStackow<T extends Uslugowe, S extends Stackowe<T> = Stackowe<T>> {
  stacki: S[];
  /** Usługi widoczne po filtrze. */
  pokazano: number;
  /** Usługi w całym snapshocie. */
  wszystkich: number;
  /** Stacki ukryte w całości przez filtr. */
  ukryteStacki: number;
}

/**
 * Przefiltrowany i posortowany widok stacków.
 *
 * Dwie zasady, obie widoczne dla użytkownika:
 *
 * 1. **Sortowanie działa wewnątrz stacka, nie między stackami.** Klucz
 *    z nagłówka kolumny przestawia wyłącznie usługi w środku swojego stacka,
 *    a kolejność stacków zostaje taka, jak przyszła z API (tam jest już
 *    posortowana po nazwie). Powód: przy sortowaniu globalnym jeden klik
 *    w „CPU" przerzucał całe sekcje — stack, na który się patrzyło, uciekał
 *    z ekranu razem z resztą tabeli, a porównywanie stacków po maksimum CPU
 *    (2 usługi vs 20) mówiło więcej o liczbie usług niż o stanie produkcji.
 * 2. **Fokus wygrywa z filtrem**: usługa wskazana fokusem zostaje na ekranie
 *    nawet wtedy, gdy nie pasuje do filtra — użytkownik kliknął ją świadomie
 *    i zniknięcie jej w tym samym momencie byłoby zgubne.
 */
export function przygotujStacki<T extends Uslugowe, S extends Stackowe<T>>(
  stacki: readonly S[],
  f: Filtr,
  fokus: string | null = null,
): WidokStackow<T, S> {
  const wskazany = rozbijFokus(fokus);
  let wszystkich = 0;
  let pokazano = 0;
  let ukryteStacki = 0;

  const wynik: S[] = [];
  for (const stack of stacki) {
    wszystkich += stack.services.length;
    const widoczne = stack.services.filter((usluga) => {
      const toFokus = wskazany !== null && wskazany.stack === stack.name && wskazany.usluga === usluga.name;
      if (toFokus) return true;
      const trafiaTekst = pasujeTekst(f.q, usluga.name, usluga.full_name, usluga.image, stack.name);
      return trafiaTekst && pasujeStan(usluga.state, f.stan);
    });
    if (widoczne.length === 0) {
      ukryteStacki += 1;
      continue;
    }
    pokazano += widoczne.length;
    // Rozszerzamy oryginalny obiekt stacka i podmieniamy tylko listę usług,
    // dzięki czemu do sekcji trafia dokładnie ten sam typ, co z API.
    // `wynik` zachowuje kolejność wejściową — sortujemy tylko w środku stacka.
    wynik.push({ ...stack, services: sortujUslugi(widoczne, f.sort, f.kierunek) });
  }

  return { stacki: wynik, pokazano, wszystkich, ukryteStacki };
}

/* ------------------------------------------------------------------ *
 * Widok list (endpointy, certyfikaty, alerty, logowania)
 * ------------------------------------------------------------------ */

export interface WidokListy<T> {
  pozycje: T[];
  pokazano: number;
  wszystkich: number;
}

function filtrujListe<T>(
  pozycje: readonly T[],
  f: Filtr,
  teksty: (element: T) => Array<string | null | undefined>,
  stan: (element: T) => string,
): WidokListy<T> {
  const wynik = pozycje.filter(
    (element) => pasujeTekst(f.q, ...teksty(element)) && pasujeStan(stan(element), f.stan),
  );
  return { pozycje: wynik, pokazano: wynik.length, wszystkich: pozycje.length };
}

export interface CheckPodobne extends Stanowe {
  name: string;
  group: string;
  detail?: string | null;
  url?: string | null;
}

export interface CertPodobne extends Stanowe {
  host: string;
}

/**
 * Alerty nie mają pola `state` — ich „stanem" jest `severity`, dlatego ten
 * interfejs nie dziedziczy po `Stanowe`.
 */
export interface AlertPodobne {
  name: string;
  severity: string;
  stack?: string | null;
  summary?: string | null;
}

export interface LoginPodobne {
  service: string;
  ip: string;
}

export function filtrujEndpointy<T extends CheckPodobne>(pozycje: readonly T[], f: Filtr): WidokListy<T> {
  return filtrujListe(
    pozycje,
    f,
    (element) => [element.name, element.group, element.detail, element.url],
    (element) => element.state,
  );
}

export function filtrujCertyfikaty<T extends CertPodobne>(pozycje: readonly T[], f: Filtr): WidokListy<T> {
  return filtrujListe(pozycje, f, (element) => [element.host], (element) => element.state);
}

export function filtrujAlerty<T extends AlertPodobne>(pozycje: readonly T[], f: Filtr): WidokListy<T> {
  return filtrujListe(
    pozycje,
    f,
    (element) => [element.name, element.stack, element.summary],
    (element) => element.severity,
  );
}

/**
 * Logowania nie mają stanu — filtrujemy je po tekście i (dla stanów innych niż
 * „wszystko") pokazujemy tylko w widoku problemów/zdrowych, żeby liczniki
 * w sekcji bezpieczeństwa nie kłamały.
 */
export function filtrujLogowania<T extends LoginPodobne>(pozycje: readonly T[], f: Filtr): WidokListy<T> {
  const wynik = pozycje.filter((element) =>
    pasujeTekst(f.q, element.service, element.ip),
  );
  return { pozycje: wynik, pokazano: wynik.length, wszystkich: pozycje.length };
}

/* ------------------------------------------------------------------ *
 * Hash (udostępnialny widok)
 * ------------------------------------------------------------------ */

function poprawnyStan(wartosc: string | null): StanFiltra {
  return STANY_FILTRA.includes(wartosc as StanFiltra) ? (wartosc as StanFiltra) : PUSTY_FILTR.stan;
}

function poprawnyKlucz(wartosc: string | null): KluczSortowania {
  return KLUCZE_SORTOWANIA.includes(wartosc as KluczSortowania)
    ? (wartosc as KluczSortowania)
    : PUSTY_FILTR.sort;
}

function poprawnyKierunek(wartosc: string | null): Kierunek {
  return wartosc === 'asc' || wartosc === 'desc' ? wartosc : PUSTY_FILTR.kierunek;
}

export interface StanWidoku {
  filtr: Filtr;
  fokus: string | null;
}

/**
 * Odczyt filtra i fokusu z hasza. Przyjmuje zarówno `#/?q=…`, jak i samo
 * `#/` (albo śmieci) — nigdy nie rzuca, zawsze oddaje poprawny stan.
 */
export function zHasza(hash: string): StanWidoku {
  const czysty = (hash || '').replace(/^#/, '');
  const zapytanie = czysty.startsWith('/?') ? czysty.slice(2) : '';
  const parametry = new URLSearchParams(zapytanie);
  const fokusRaw = parametry.get('fokus');
  return {
    filtr: {
      q: (parametry.get('q') ?? '').slice(0, 120),
      stan: poprawnyStan(parametry.get('stan')),
      sort: poprawnyKlucz(parametry.get('sort')),
      kierunek: poprawnyKierunek(parametry.get('kier')),
    },
    fokus: rozbijFokus(fokusRaw) ? fokusRaw : null,
  };
}

/** Budowa hasza: pomijamy wartości domyślne, żeby linki zostały krótkie. */
export function doHasza(f: Filtr, fokus: string | null = null): string {
  const parametry = new URLSearchParams();
  const q = f.q.trim();
  if (q) parametry.set('q', q);
  if (f.stan !== PUSTY_FILTR.stan) parametry.set('stan', f.stan);
  if (f.sort !== PUSTY_FILTR.sort) parametry.set('sort', f.sort);
  if (f.kierunek !== PUSTY_FILTR.kierunek) parametry.set('kier', f.kierunek);
  if (rozbijFokus(fokus)) parametry.set('fokus', fokus as string);
  const zapytanie = parametry.toString();
  return zapytanie ? `#/?${zapytanie}` : '#/';
}

/* ------------------------------------------------------------------ *
 * Sparkline (SVG) — czysta matematyka, testowalna bez przeglądarki
 * ------------------------------------------------------------------ */

export interface Zakres {
  min: number;
  max: number;
}

export function zakresSparkline(wartosci: readonly number[]): Zakres | null {
  const skonczone = wartosci.filter((v) => Number.isFinite(v));
  if (skonczone.length === 0) return null;
  return { min: Math.min(...skonczone), max: Math.max(...skonczone) };
}

/**
 * Punkty dla `<polyline>`: `x,y x,y …`. Skala Y rozciąga się między minimum
 * i maksimum serii (dla CPU dodatkowo przycinamy do 0–100), a gdy seria jest
 * płaska — rysujemy linię w połowie wysokości, żeby nie udała „zera".
 */
export function punktySparkline(
  wartosci: readonly number[],
  szerokosc: number,
  wysokosc: number,
  opcje: { min?: number; max?: number } = {},
): string {
  const punktowe = wartosci.map((v, i) => ({ x: i, y: v })).filter((p) => Number.isFinite(p.y));
  if (punktowe.length === 0) return '';
  if (punktowe.length === 1) {
    const y = Math.round(wysokosc / 2);
    return `0,${y} ${szerokosc},${y}`;
  }

  const zakres = zakresSparkline(punktowe.map((p) => p.y)) as Zakres;
  let min = opcje.min ?? zakres.min;
  let max = opcje.max ?? zakres.max;
  if (opcje.min === undefined) min = zakres.min;
  if (opcje.max === undefined) max = zakres.max;
  if (max - min < 1e-9) {
    const srodek = (min + max) / 2;
    min = srodek - 0.5;
    max = srodek + 0.5;
  }

  const skalaX = szerokosc / (punktowe.length - 1);
  const margines = 1;
  const dostepna = Math.max(1, wysokosc - margines * 2);
  return punktowe
    .map((p) => {
      const x = (p.x * skalaX).toFixed(1);
      const udzial = (p.y - min) / (max - min);
      const y = (margines + (1 - Math.min(1, Math.max(0, udzial))) * dostepna).toFixed(1);
      return `${x},${y}`;
    })
    .join(' ');
}

/* ------------------------------------------------------------------ *
 * CSV (eksport aktualnego widoku)
 * ------------------------------------------------------------------ */

export interface WierszCsv {
  stack: string;
  usluga: string;
  stan: string;
  repliki: string;
  cpu: string;
  ram: string;
  restarty: string;
  obraz: string;
}

function poleCsv(wartosc: string): string {
  const tekst = wartosc ?? '';
  return /[";\n]/.test(tekst) ? `"${tekst.replace(/"/g, '""')}"` : tekst;
}

/**
 * CSV dla arkusza w polskiej lokalizacji: separator `;` i BOM, żeby Excel
 * otworzył plik od razu z polskimi znakami i w kolumnach.
 */
export function uslugiDoCsv(wiersze: readonly WierszCsv[]): string {
  const naglowek = ['stack', 'usluga', 'stan', 'repliki', 'cpu', 'ram', 'restarty_1h', 'obraz'];
  const linie = [naglowek.join(';')];
  for (const w of wiersze) {
    linie.push(
      [w.stack, w.usluga, w.stan, w.repliki, w.cpu, w.ram, w.restarty, w.obraz]
        .map(poleCsv)
        .join(';'),
    );
  }
  return `\uFEFF${linie.join('\r\n')}\r\n`;
}

/* ------------------------------------------------------------------ *
 * Zmiany między odświeżeniami („co właśnie się stało")
 * ------------------------------------------------------------------ */

export type RodzajZmiany =
  | 'alert-nowy'
  | 'alert-zamkniety'
  | 'stan-uslugi'
  | 'stan-endpointu'
  | 'repliki'
  | 'usluga-nowa'
  | 'usluga-zniknela';

export interface Zmiana {
  rodzaj: RodzajZmiany;
  tytul: string;
  opis: string;
  stan: string;
  /** Klucz fokusu (`stack/usluga`), gdy zmiana dotyczy konkretnej usługi. */
  fokus: string | null;
}

interface SnapshotPodobny {
  stacks: Array<Stackowe<Uslugowe>>;
  checks: Array<CheckPodobne>;
  alerts: Array<AlertPodobne>;
}

function mapaUslug(s: SnapshotPodobny): Map<string, Uslugowe> {
  const mapa = new Map<string, Uslugowe>();
  for (const stack of s.stacks) {
    for (const usluga of stack.services) {
      mapa.set(kluczFokusa(stack.name, usluga.name), usluga);
    }
  }
  return mapa;
}

/**
 * Porównanie dwóch snapshotów → lista zmian do sekcji „Ostatnie zmiany".
 * Kolejność ma znaczenie: najpierw to, co wymaga reakcji (nowe alerty,
 * krytyczne stany), na końcu porządki (zamknięte alerty).
 */
export function zmianyMiedzy(
  poprzedni: SnapshotPodobny | null,
  obecny: SnapshotPodobny,
  limit = 12,
): Zmiana[] {
  if (!poprzedni) return [];
  const zmiany: Zmiana[] = [];

  // Nowe i zamknięte alerty.
  const kluczAlertu = (a: AlertPodobne): string => `${a.name}|${a.stack ?? ''}`;
  const stareAlerty = new Set(poprzedni.alerts.map(kluczAlertu));
  const noweAlerty = new Set(obecny.alerts.map(kluczAlertu));
  for (const alert of obecny.alerts) {
    if (stareAlerty.has(kluczAlertu(alert))) continue;
    zmiany.push({
      rodzaj: 'alert-nowy',
      tytul: `Nowy alert: ${alert.name}`,
      opis: alert.summary ?? alert.stack ?? '',
      stan: alert.severity,
      fokus: null,
    });
  }
  for (const alert of poprzedni.alerts) {
    if (noweAlerty.has(kluczAlertu(alert))) continue;
    zmiany.push({
      rodzaj: 'alert-zamkniety',
      tytul: `Alert zamknięty: ${alert.name}`,
      opis: alert.stack ?? '',
      stan: 'ok',
      fokus: null,
    });
  }

  // Usługi: nowe, zniknięte, zmiana stanu, zmiana replik.
  const stareUslugi = mapaUslug(poprzedni);
  const noweUslugi = mapaUslug(obecny);
  for (const [klucz, usluga] of noweUslugi) {
    const poprzednia = stareUslugi.get(klucz);
    if (!poprzednia) {
      zmiany.push({
        rodzaj: 'usluga-nowa',
        tytul: `Nowa usługa: ${klucz}`,
        opis: usluga.image ?? '',
        stan: usluga.state,
        fokus: klucz,
      });
      continue;
    }
    if (poprzednia.state !== usluga.state) {
      zmiany.push({
        rodzaj: 'stan-uslugi',
        tytul: `Zmiana stanu: ${klucz}`,
        opis: `${poprzednia.state} → ${usluga.state}`,
        stan: usluga.state,
        fokus: klucz,
      });
    } else if ((poprzednia.running ?? -1) !== (usluga.running ?? -1)) {
      zmiany.push({
        rodzaj: 'repliki',
        tytul: `Zmiana replik: ${klucz}`,
        opis: `${poprzednia.running ?? '—'}/${poprzednia.desired ?? '—'} → ${usluga.running ?? '—'}/${usluga.desired ?? '—'}`,
        stan: usluga.state,
        fokus: klucz,
      });
    }
  }
  for (const [klucz, usluga] of stareUslugi) {
    if (noweUslugi.has(klucz)) continue;
    zmiany.push({
      rodzaj: 'usluga-zniknela',
      tytul: `Usługa zniknęła: ${klucz}`,
      opis: usluga.image ?? '',
      stan: 'unknown',
      fokus: null,
    });
  }

  // Endpointy.
  const mapaCheckow = new Map(poprzedni.checks.map((c) => [c.name, c]));
  for (const check of obecny.checks) {
    const poprzedniCheck = mapaCheckow.get(check.name);
    if (!poprzedniCheck || poprzedniCheck.state === check.state) continue;
    zmiany.push({
      rodzaj: 'stan-endpointu',
      tytul: `Endpoint: ${check.name}`,
      opis: `${poprzedniCheck.state} → ${check.state}${check.detail ? ` · ${check.detail}` : ''}`,
      stan: check.state,
      fokus: null,
    });
  }

  const waga = (z: Zmiana): number => {
    const rangi: Record<RodzajZmiany, number> = {
      'alert-nowy': 0,
      'stan-uslugi': 1,
      repliki: 2,
      'stan-endpointu': 3,
      'usluga-zniknela': 4,
      'usluga-nowa': 5,
      'alert-zamkniety': 6,
    };
    return rangi[z.rodzaj] * 10 + (4 - rangaStanu(z.stan));
  };

  return zmiany.sort((a, b) => waga(a) - waga(b)).slice(0, limit);
}
