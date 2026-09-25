/**
 * Czysta logika sekcji „Ataki i skanowanie” (`ataki` w `/status/api.json`).
 *
 * Powód istnienia: te reguły decydują, czy panel mówi prawdę o ataku. Trzy
 * rzeczy łatwo tu zepsuć i nie zobaczyć tego w pojedynczym zrzucie:
 *
 *   1. „brak danych” nie może wyglądać jak „zero ataków” — gdy access log nie
 *      płynie (`zrodlo_aktywne === false`), sekcja musi być `unknown`, a nie
 *      zielona, bo zielona znaczy „sprawdziłem i jest czysto”,
 *   2. kolejność list musi być powtarzalna (malejąco po liczbie, a przy remisie
 *      po adresie/ścieżce), inaczej panel „migocze” między odświeżeniami,
 *   3. podpisy muszą być po polsku i w liczbie mnogiej poprawnej dla 1/2–4/5+.
 *
 * Testy: `node scripts/ci/check_ataki.mts` (krok w jobie `panel`).
 */
import type { Ataki, State } from './status';

/** Krótkie etykiety kategorii — na wąskich wierszach nie zmieszczą się pełne nazwy. */
export const ETYKIETY_WZORCOW: Record<string, string> = {
  xss: 'XSS',
  sqli: 'SQLi',
  traversal: 'traversal',
  log4shell: 'Log4Shell',
  skaner: 'skaner',
};

/** Kolejność kategorii na liście: najgroźniejsze najpierw. */
export const KOLEJNOSC_WZORCOW = ['log4shell', 'sqli', 'xss', 'traversal', 'skaner'];

/** Etykieta kategorii do pokazania użytkownikowi (nieznany klucz wraca bez zmian). */
export function etykietaWzorca(klucz: string): string {
  const czysty = (klucz ?? '').trim();
  return ETYKIETY_WZORCOW[czysty] ?? (czysty === '' ? 'atak' : czysty);
}

/**
 * Stan sekcji.
 *
 * `unknown`, gdy nie wiemy (brak sekcji, źródło nieaktywne, brak licznika).
 * `warning`, gdy w oknie 24 h cokolwiek dopasowano.
 * `ok` tylko wtedy, gdy źródło płynie i licznik zdarzeń wynosi dokładnie 0.
 */
export function stanAtakow(ataki: Ataki | null): State {
  if (!ataki) return 'unknown';
  if (ataki.zrodlo_aktywne === null || ataki.zdarzenia_24h === null) return 'unknown';
  if (ataki.zrodlo_aktywne === false) return 'unknown';
  return ataki.zdarzenia_24h > 0 ? 'warning' : 'ok';
}

/**
 * Czy WIEMY cokolwiek o atakach (do wyboru między „brak danych” a „czysto”).
 *
 * Wymagamy `zrodlo_aktywne === true`: gdy access log nie płynie, liczniki mogą
 * być zerami z braku danych — pokazanie ich jako „czysto” byłoby kłamstwem
 * dokładnie w sytuacji, w której jesteśmy ślepi.
 */
export function maDaneAtakow(ataki: Ataki | null): boolean {
  return Boolean(ataki) && ataki?.zrodlo_aktywne === true && ataki?.zdarzenia_24h !== null;
}

/** Podpis pod kaflem liczby zdarzeń — mówi, skąd one są i z ilu adresów. */
export function opisZdarzen(ataki: Ataki | null): string {
  if (!maDaneAtakow(ataki)) return 'brak danych — access log nie płynie';
  const zrodla = ataki?.top_ip.length ?? 0;
  if ((ataki?.zdarzenia_24h ?? 0) === 0) return 'brak prób ataku w 24 h';
  return liczba(zrodla, 'adres źródłowy', 'adresy źródłowe', 'adresów źródłowych');
}

/** Ile kategorii miało w ogóle trafienia (do podpisu listy wzorców). */
export function ileAktywnychWzorcow(ataki: Ataki | null): number {
  return (ataki?.wzorce ?? []).filter((w) => w.ile > 0).length;
}

/** Wzorce do pokazania: najpierw te z trafieniami, potem reszta wg stałej kolejności. */
export function wzorceDoListy(ataki: Ataki | null): Ataki['wzorce'] {
  const lista = [...(ataki?.wzorce ?? [])];
  const waga = (klucz: string): number => {
    const indeks = KOLEJNOSC_WZORCOW.indexOf(klucz);
    return indeks === -1 ? KOLEJNOSC_WZORCOW.length : indeks;
  };
  return lista.sort((a, b) => {
    if ((b.ile > 0 ? 1 : 0) !== (a.ile > 0 ? 1 : 0)) return (b.ile > 0 ? 1 : 0) - (a.ile > 0 ? 1 : 0);
    if (b.ile !== a.ile) return b.ile - a.ile;
    return waga(a.klucz) - waga(b.klucz);
  });
}

/** Lista adresów: malejąco po liczbie, przy remisie rosnąco po adresie (powtarzalnie). */
export function zrodlaDoListy(ataki: Ataki | null): Ataki['top_ip'] {
  return [...(ataki?.top_ip ?? [])].sort((a, b) => {
    if (b.ile !== a.ile) return b.ile - a.ile;
    return a.ip.localeCompare(b.ip, 'pl');
  });
}

/** Lista ścieżek: malejąco po liczbie, przy remisie rosnąco po ścieżce. */
export function sciezkiDoListy(ataki: Ataki | null): Ataki['top_sciezki'] {
  return [...(ataki?.top_sciezki ?? [])].sort((a, b) => {
    if (b.ile !== a.ile) return b.ile - a.ile;
    return a.sciezka.localeCompare(b.sciezka, 'pl');
  });
}

/** Opis detekcji behawioralnej (skanery łapane po liczbie błędów, nie po wzorcu). */
export function opisSkanowania(ataki: Ataki | null, prog: number): string {
  if (!maDaneAtakow(ataki) || ataki?.skanowanie_10m === null) return 'brak danych';
  const ile = ataki?.skanowanie_10m ?? 0;
  if (ile === 0) return `nikt nie przekroczył ${prog} błędów 4xx w 10 min`;
  return liczba(ile, 'adres skanuje', 'adresy skanują', 'adresów skanuje');
}

/** Podpis sekcji: krótko, co widać — używane w nagłówku listy. */
export function podsumowanieAtakow(ataki: Ataki | null): string {
  if (!maDaneAtakow(ataki)) return 'brak danych o atakach';
  if ((ataki?.zdarzenia_24h ?? 0) === 0) return 'brak prób ataku w 24 h';
  const kategorie = ileAktywnychWzorcow(ataki);
  return `${liczba(ataki?.zdarzenia_24h ?? 0, 'zdarzenie', 'zdarzenia', 'zdarzeń')} w ${liczba(
    kategorie,
    'kategorii',
    'kategoriach',
    'kategoriach',
  )}`;
}

/** Polska odmiana: 1 / 2–4 / 5+ (z wyjątkiem nastek, które idą jak 5+). */
export function liczba(n: number, jeden: string, kilka: string, wiele: string): string {
  const wartosc = Number.isFinite(n) ? Math.abs(Math.trunc(n)) : 0;
  const setki = wartosc % 100;
  const dziesiatki = wartosc % 10;
  if (wartosc === 1) return `${wartosc} ${jeden}`;
  if (dziesiatki >= 2 && dziesiatki <= 4 && !(setki >= 12 && setki <= 14)) return `${wartosc} ${kilka}`;
  return `${wartosc} ${wiele}`;
}
