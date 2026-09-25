/**
 * Motyw panelu: wybór użytkownika (auto / jasny / ciemny), jego zapis
 * i wpływ na osadzane narzędzia.
 *
 * Dwa motywy (`ops-day` jasny, `ops` ciemny) definiuje `global.css`:
 * domyślnie wybiera je SYSTEM przez `@media (prefers-color-scheme: dark)`,
 * więc pierwsza klatka jest poprawna nawet bez JavaScriptu. Użytkownik może
 * tę decyzję nadpisać — wtedy `<html data-theme="ops|ops-day">` wygrywa
 * z media query, a zapis w `localStorage` przywraca wybór po odświeżeniu.
 *
 * Trzy wartości wyboru, jedna prawda o motywie:
 *   `auto`   — brak atrybutu, decyduje system i robi to na żywo,
 *   `jasny`  — atrybut `ops-day`,
 *   `ciemny` — atrybut `ops`.
 *
 * Drugi temat tego pliku to ramki narzędzi (Grafana, Prometheus): mają WŁASNY
 * motyw, niezależny od naszego, więc bez parametru w adresie jasny panel
 * świeciłby ciemnym prostokątem w środku (i odwrotnie). Tu jest jedno miejsce,
 * które wie, kto rozumie jaki parametr — nie zgadujemy: Alertmanager,
 * Portainer, Cockpit i healthchecks.io nie mają potwierdzonego parametru
 * motywu w adresie, więc dla nich zwracamy `null`.
 */

export type Motyw = 'light' | 'dark';
export type WyborMotywu = 'auto' | 'jasny' | 'ciemny';

/** Klucz w `localStorage`. Hash opisuje widok, nie preferencję — dlatego tu. */
export const KLUCZ_MOTYWU = 'panel-motyw';

/** Nazwy motywów z `global.css` (te same, co w `data-theme`). */
export const ATRYBUT_JASNY = 'ops-day';
export const ATRYBUT_CIEMNY = 'ops';

/** Kolejność w przełączniku i w nawigacji klawiaturą. */
export const WYBORY: readonly WyborMotywu[] = ['auto', 'jasny', 'ciemny'];

/** Identyfikatory narzędzi, które rozumieją `theme=` w adresie. */
export const NARZEDZIA_Z_MOTYWEM: readonly string[] = ['grafana', 'prometheus'];

const SKROTY: Record<WyborMotywu, string> = {
  auto: 'Auto',
  jasny: 'Jasny',
  ciemny: 'Ciemny',
};

const OPISY: Record<WyborMotywu, string> = {
  auto: 'Auto — zgodnie z ustawieniem systemu',
  jasny: 'Jasny — zawsze jasny motyw panelu',
  ciemny: 'Ciemny — zawsze ciemny motyw panelu',
};

/** Etykieta na przycisku. */
export function skrotWyboru(wybor: WyborMotywu): string {
  return SKROTY[wybor];
}

/** Podpowiedź (`title`) i opis dla czytników ekranu. */
export function opisWyboru(wybor: WyborMotywu): string {
  return OPISY[wybor];
}

/**
 * Cokolwiek przyszło z `localStorage` → poprawny wybór. Nieznana, uszkodzona
 * albo pusta wartość znaczy `auto`: lepiej wrócić do ustawienia systemu niż
 * zostać w losowym motywie po cudzej pomyłce.
 */
export function normalizujWybor(wartosc: unknown): WyborMotywu {
  if (typeof wartosc !== 'string') return 'auto';
  const czysta = wartosc.trim().toLowerCase();
  return (WYBORY as readonly string[]).includes(czysta) ? (czysta as WyborMotywu) : 'auto';
}

/** Motyw wynikający z preferencji systemu. */
export function motywZSystemu(ciemny: boolean): Motyw {
  return ciemny ? 'dark' : 'light';
}

/**
 * Motyw, który panel FAKTYCZNIE pokazuje. W trybie `auto` rozstrzyga system,
 * w jawnym wyborze — użytkownik (system przestaje mieć znaczenie).
 */
export function motywEfektywny(wybor: WyborMotywu, ciemnySystem: boolean): Motyw {
  if (wybor === 'ciemny') return 'dark';
  if (wybor === 'jasny') return 'light';
  return motywZSystemu(ciemnySystem);
}

/**
 * Wartość `data-theme` dla wyboru. `null` w trybie `auto` jest kontraktem:
 * atrybutu nie ustawiamy, żeby media query mogło działać na żywo.
 */
export function atrybutDlaWyboru(wybor: WyborMotywu, ciemnySystem: boolean): string | null {
  if (wybor === 'auto') return null;
  return motywEfektywny(wybor, ciemnySystem) === 'dark' ? ATRYBUT_CIEMNY : ATRYBUT_JASNY;
}

/**
 * Wartość `color-scheme` dla `<html>` — dzięki temu scrollbar, pola i kursor
 * idą za motywem panelu, a nie za systemem (rozjazd widać od razu).
 */
export function schematKolorow(
  wybor: WyborMotywu,
  ciemnySystem: boolean,
): 'light dark' | 'light' | 'dark' {
  if (wybor === 'auto') return 'light dark';
  return motywEfektywny(wybor, ciemnySystem) === 'dark' ? 'dark' : 'light';
}

/** Kolejny wybór przy nawigacji strzałkami (radiogroup), z zawijaniem. */
export function nastepnyWybor(wybor: WyborMotywu, krok: number): WyborMotywu {
  const indeks = WYBORY.indexOf(wybor);
  const baza = indeks === -1 ? 0 : indeks;
  const dlugosc = WYBORY.length;
  return WYBORY[(((baza + krok) % dlugosc) + dlugosc) % dlugosc]!;
}

/**
 * Odczyt zapisanego wyboru. Adapter (`localStorage.getItem`) wstrzykujemy,
 * żeby dało się to przetestować bez przeglądarki — i żeby wyjątek (tryb
 * prywatny, zablokowany storage) nie wywracał panelu.
 */
export function odczytajWybor(pobierz: (klucz: string) => string | null | undefined): WyborMotywu {
  try {
    return normalizujWybor(pobierz(KLUCZ_MOTYWU));
  } catch {
    return 'auto';
  }
}

/** Zapis wyboru. Zwraca `false`, gdy storage odmówił — panel działa dalej. */
export function zapiszWybor(
  zapisz: (klucz: string, wartosc: string) => void,
  wybor: WyborMotywu,
): boolean {
  try {
    zapisz(KLUCZ_MOTYWU, wybor);
    return true;
  } catch {
    return false;
  }
}

/**
 * Skrypt wstrzykiwany do `<head>` przed pierwszym malowaniem (`is:inline`).
 * Ustawia motyw TYLKO dla jawnego wyboru; w trybie `auto` nie dotyka atrybutu,
 * więc decyduje media query już w pierwszej klatce. Trzymamy go tutaj, a nie
 * w `Base.astro`, żeby klucz i nazwy motywów miały jedno źródło prawdy —
 * pilnuje tego `scripts/ci/check_motyw.mts`.
 */
export const SKRYPT_MOTYWU =
  '(function(){try{' +
  `var w=localStorage.getItem(${JSON.stringify(KLUCZ_MOTYWU)});` +
  'if(w!=="jasny"&&w!=="ciemny")return;' +
  'var c=w==="ciemny";' +
  `document.documentElement.dataset.theme=c?${JSON.stringify(ATRYBUT_CIEMNY)}:${JSON.stringify(ATRYBUT_JASNY)};` +
  'document.documentElement.style.colorScheme=c?"dark":"light";' +
  '}catch(e){}})();';

/**
 * Parametr motywu dla danego narzędzia albo `null`, gdy go nie obsługuje.
 * `null` (a nie pusty napis) jest kontraktem: `zbudujAdres` go pomija.
 */
export function parametrMotywu(id: string, motyw: Motyw): string | null {
  if (!NARZEDZIA_Z_MOTYWEM.includes(id)) return null;
  return `theme=${motyw}`;
}

/**
 * Skleja adres z listą parametrów. Puste i `null` pomija, dokłada `?` albo `&`
 * zależnie od tego, co już jest w adresie, i nie duplikuje parametru, który
 * już występuje (np. gdyby API zaczęło samo podawać `theme`).
 *
 * Uwaga na parametry bez wartości: Grafana dostaje `kiosk` (nie `kiosk=1`),
 * więc sam wzorzec `klucz=` nie wystarcza — inaczej po zmianie motywu adres
 * kończyłby się `…&theme=dark&kiosk`, a ramka przeładowywałaby się bez potrzeby.
 */
export function zbudujAdres(baza: string, parametry: readonly (string | null | undefined)[]): string {
  if (!baza) return '';
  const czyste = parametry
    .map((p) => (p ?? '').trim())
    .filter((p) => p.length > 0)
    .filter((p) => {
      const klucz = p.split('=')[0] ?? '';
      if (!/^[A-Za-z0-9_-]+$/.test(klucz)) return true;
      return !new RegExp(`(^|[?&])${klucz}(=|&|$)`).test(baza);
    });
  if (!czyste.length) return baza;
  const separator = baza.includes('?') ? '&' : '?';
  return `${baza}${separator}${czyste.join('&')}`;
}

/**
 * Reakcja na zmianę motywu w trakcie pracy: podmiana adresu ramki tylko wtedy,
 * gdy narzędzie rozumie `theme=`. Zwraca `null`, gdy nic nie trzeba robić
 * (brak ramki, brak parametru, ten sam adres) — wołający nie przeładowuje
 * ramki „na wszelki wypadek”, bo to gubi stan osadzonego narzędzia.
 */
export function adresPoZmianieMotywu(
  id: string,
  url: string,
  embedQuery: string | null,
  motyw: Motyw,
): string | null {
  const parametr = parametrMotywu(id, motyw);
  if (!parametr || !url) return null;
  return zbudujAdres(url, [embedQuery, parametr]);
}
