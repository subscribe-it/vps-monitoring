/**
 * Zwijanie grup w panelu — czysta logika (bez DOM), wzorzec jak
 * `MaterialExpansionPanel`: nagłówek grupy jest przyciskiem, a stan zwinięcia
 * przeżywa odświeżenie strony.
 *
 * Dlaczego osobny moduł: tę samą logikę wykorzystują sekcje (endpointy,
 * certyfikaty, alerty, logowania, stacki), a testy `check_zwijanie.mts` muszą
 * ją sprawdzić bez przeglądarki. Zasady, które muszą tu zostać:
 *  - zwinięcie NIGDY nie ukrywa stanu (nazwa, licznik i pigułka stanu są
 *    w nagłówku, więc zostają widoczne),
 *  - zapis w `localStorage` jest tolerancyjny: każdy śmieć znaczy „brak
 *    zapisu”, nigdy wyjątek ani utrata reszty mapy,
 *  - domyślny stan jest przewidywalny i wypisany w `panel/README.md`.
 */

/** Klucz w `localStorage` na mapę `sekcja/grupa → zwinięta`. */
export const KLUCZ_ZWIJANIA = 'panel-zwijanie';

/** Od ilu grup w sekcji wolno domyślnie zwijać grupy bez problemów. */
export const PROG_AUTO_ZWIJANIA = 6;

/** Mapa zapisana w `localStorage`: klucz grupy → czy zwinięta. */
export type MapaZwinięć = Record<string, boolean>;

/**
 * Klucz grupy w mapie. Normalizujemy, bo nazwy grup przychodzą z API
 * (spacje, wielkość liter, polskie znaki) — bez tego ten sam zapis po zmianie
 * brzmienia nazwy w API przestałby działać.
 */
export function kluczGrupy(sekcja: string, grupa: string): string {
  const czysc = (tekst: string): string =>
    String(tekst ?? '')
      .trim()
      .replace(/\s+/g, ' ')
      .toLocaleLowerCase('pl');
  return `${czysc(sekcja)}/${czysc(grupa)}`;
}

/**
 * Czyta zapis z `localStorage`. Śmieci (zły JSON, tablica, `null`, wartości
 * nieboolowskie) są pomijane — reszta mapy zostaje, żeby jedna zepsuta pozycja
 * nie kasowała ustawień użytkownika.
 */
export function parsujZapis(surowy: string | null | undefined): MapaZwinięć {
  if (!surowy) return {};
  let dane: unknown;
  try {
    dane = JSON.parse(surowy);
  } catch {
    return {};
  }
  if (!dane || typeof dane !== 'object' || Array.isArray(dane)) return {};
  const mapa: MapaZwinięć = {};
  for (const [klucz, wartosc] of Object.entries(dane as Record<string, unknown>)) {
    if (typeof wartosc === 'boolean' && klucz.trim() !== '') mapa[klucz] = wartosc;
  }
  return mapa;
}

/** Zapisuje mapę w postaci stabilnej (posortowane klucze → mniej migotania w diffach). */
export function serializujZapis(mapa: MapaZwinięć): string {
  const posortowane = Object.keys(mapa).sort();
  const wynik: MapaZwinięć = {};
  for (const klucz of posortowane) wynik[klucz] = mapa[klucz] === true;
  return JSON.stringify(wynik);
}

/**
 * Domyślny stan grupy.
 *
 * Zasada (wypisana też w README): wszystko jest ROZWINIĘTE. Wyjątek robimy
 * tylko wtedy, gdy sekcja ma dużo grup (≥ `PROG_AUTO_ZWIJANIA`) i grupa jest
 * bez problemów — wtedy startuje zwinięta, żeby nie zasłaniać tego, co się
 * faktycznie psuje. Grupa z problemem jest ZAWSZE rozwinięta na starcie.
 */
export function domyslnieZwinięta(
  liczbaGrupWSekcji: number,
  stanGrupy: string,
): boolean {
  const bezProblemow = stanGrupy === 'ok' || stanGrupy === 'disabled';
  return liczbaGrupWSekcji >= PROG_AUTO_ZWIJANIA && bezProblemow;
}

/** Czy grupa jest zwinięta: zapis użytkownika ma pierwszeństwo nad domyślnym. */
export function czyZwinięta(
  mapa: MapaZwinięć,
  klucz: string,
  domyslna: boolean,
): boolean {
  const zapis = mapa[klucz];
  return typeof zapis === 'boolean' ? zapis : domyslna;
}

/** Nowa mapa z przełączoną jedną grupą (stan bieżący → przeciwny). */
export function przelaczGrupe(
  mapa: MapaZwinięć,
  klucz: string,
  domyslna: boolean,
): MapaZwinięć {
  return { ...mapa, [klucz]: !czyZwinięta(mapa, klucz, domyslna) };
}

/** Nowa mapa z ustawionym stanem dla wielu grup naraz (przycisk „zwiń/rozwiń wszystko"). */
export function ustawWszystkie(
  mapa: MapaZwinięć,
  klucze: readonly string[],
  zwinięte: boolean,
): MapaZwinięć {
  const wynik: MapaZwinięć = { ...mapa };
  for (const klucz of klucze) {
    if (klucz.trim() !== '') wynik[klucz] = zwinięte;
  }
  return wynik;
}

/**
 * Czy sekcja jest w całości zwinięta — używane do etykiety przycisku
 * zbiorczego (`aria-pressed` musi mówić prawdę, nie być licznikiem kliknięć).
 */
export function wszystkieZwinięte(
  mapa: MapaZwinięć,
  klucze: readonly string[],
  domyslne: readonly boolean[],
): boolean {
  if (klucze.length === 0) return false;
  return klucze.every((klucz, indeks) =>
    czyZwinięta(mapa, klucz, domyslne[indeks] ?? false),
  );
}

/** Licznik dla UI: ile z podanych grup jest zwiniętych. */
export function ileZwinietych(
  mapa: MapaZwinięć,
  klucze: readonly string[],
  domyslne: readonly boolean[],
): number {
  return klucze.reduce(
    (suma, klucz, indeks) =>
      suma + (czyZwinięta(mapa, klucz, domyslne[indeks] ?? false) ? 1 : 0),
    0,
  );
}

/**
 * Identyfikator dla `aria-controls` — musi być unikalny w dokumencie i stabilny
 * między renderami (inaczej czytnik ekranu gubi powiązanie nagłówka z treścią).
 */
export function identyfikatorWierszy(sekcja: string, grupa: string, indeks: number): string {
  const slug = (tekst: string): string =>
    String(tekst ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .toLowerCase();
  return `grupa-${slug(sekcja)}-${slug(grupa) || 'x'}-${indeks}`;
}

/** Etykieta przycisku zbiorczego — jedno źródło prawdy dla tekstu i `aria-pressed`. */
export function etykietaZbiorcza(wszystkie: boolean, ile: number): string {
  if (wszystkie) return 'Rozwiń wszystko';
  return ile > 0 ? `Rozwiń wszystkie (zwinięte: ${ile})` : 'Zwiń wszystko';
}
