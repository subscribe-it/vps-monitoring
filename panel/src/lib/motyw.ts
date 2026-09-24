/**
 * Motyw systemowy i jego wpływ na osadzane narzędzia.
 *
 * Panel sam jest w motywie wybranym przez `prefers-color-scheme` (patrz
 * `global.css`), ale ramki narzędzi (Grafana, Prometheus) mają WŁASNY motyw,
 * niezależny od naszego. Bez przekazania parametru w adresie jasny panel
 * świeciłby ciemnym prostokątem w środku (i odwrotnie) — a to najbrzydsza
 * możliwa wersja „trybu systemowego”.
 *
 * Tu jest jedno miejsce, które wie, kto rozumie jaki parametr. Nie zgadujemy:
 * Grafana przyjmuje `theme=light|dark` (obok `kiosk` z API), Prometheus
 * przyjmuje `theme=light|dark`. Alertmanager, Portainer, Cockpit
 * i healthchecks.io nie mają potwierdzonego parametru motywu w adresie —
 * dla nich zwracamy `null` i zostawiamy ich własne ustawienie.
 */

export type Motyw = 'light' | 'dark';

/** Identyfikatory narzędzi, które rozumieją `theme=` w adresie. */
export const NARZEDZIA_Z_MOTYWEM: readonly string[] = ['grafana', 'prometheus'];

/** Motyw wynikający z preferencji systemu. */
export function motywZSystemu(ciemny: boolean): Motyw {
  return ciemny ? 'dark' : 'light';
}

/**
 * Parametr motywu dla danego narzędzia albo `null`, gdy go nie obsługuje.
 * `null` (a nie pusty napis) jest kontraktem: `zbudujAdres` go pomija.
 */
export function parametrMotywu(id: string, ciemny: boolean): string | null {
  if (!NARZEDZIA_Z_MOTYWEM.includes(id)) return null;
  return `theme=${motywZSystemu(ciemny)}`;
}

/**
 * Skleja adres z listą parametrów. Puste i `null` pomija, dokłada `?` albo `&`
 * zależnie od tego, co już jest w adresie, i nie duplikuje parametru, który
 * już występuje (np. gdyby API zaczęło samo podawać `theme`).
 */
export function zbudujAdres(baza: string, parametry: readonly (string | null | undefined)[]): string {
  if (!baza) return '';
  const czyste = parametry
    .map((p) => (p ?? '').trim())
    .filter((p) => p.length > 0)
    .filter((p) => {
      const klucz = p.split('=')[0];
      return !new RegExp(`(^|[?&])${klucz}=`).test(baza);
    });
  if (!czyste.length) return baza;
  const separator = baza.includes('?') ? '&' : '?';
  return `${baza}${separator}${czyste.join('&')}`;
}

/**
 * Reakcja na zmianę preferencji systemu w trakcie pracy: podmiana adresu ramki
 * tylko wtedy, gdy narzędzie rozumie `theme=`. Zwraca `null`, gdy nic nie
 * trzeba robić (brak ramki, brak parametru, ten sam adres).
 */
export function adresPoZmianieMotywu(
  id: string,
  url: string,
  embedQuery: string | null,
  ciemny: boolean,
): string | null {
  const parametr = parametrMotywu(id, ciemny);
  if (!parametr || !url) return null;
  const nowy = zbudujAdres(url, [embedQuery, parametr]);
  return nowy;
}
