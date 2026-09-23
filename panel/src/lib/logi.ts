/**
 * Czysta logika widoku „Logi" (`#/logi`, `#/logi/<stack>/<usługa>`).
 *
 * Po co osobny moduł: trasa, zapytania LogQL, parsowanie odpowiedzi Loki
 * i filtrowanie linii to reguły, których pomyłki nie widać w kodzie, a widać
 * je na produkcji jako „pusto" albo — gorzej — jako logi nie tej usługi.
 * Moduł jest samowystarczalny (zero importów), więc testuje go Node bez DOM-u
 * (`node scripts/ci/check_logi.mts`).
 *
 * Zasady, które ten moduł wymusza:
 * 1. **Fraza od użytkownika nigdy nie trafia do LogQL** — filtrujemy już
 *    pobrane linie (podciąg, bez rozróżniania wielkości liter). Inaczej tekst
 *    użytkownika byłby fragmentem zapytania (wstrzyknięcie/regex) i mógłby
 *    położyć Loki'ego albo zwrócić coś spoza wybranej usługi.
 * 2. Etykieta `service` w Loki ma **prefiks stacka** (`<stack>_<usługa>`), bo
 *    tak ustawia ją promtail z metki Dockera — zapytanie budujemy z tego
 *    faktu, a nie z nazwy usługi samej w sobie.
 * 3. Brak danych to `null`/pusta lista i czytelny komunikat — nigdy zmyślona
 *    linia ani „0 logów" udające zdrowie.
 */

/* ------------------------------------------------------------------ *
 * Zakres czasu i limit linii
 * ------------------------------------------------------------------ */

export type ZakresLogowId = '15m' | '1h' | '24h';

export interface ZakresLogow {
  id: ZakresLogowId;
  sekundy: number;
  /** Krótki podpis na przycisku („15 min"). */
  etykieta: string;
  /** Podpis do zdania („ostatnie 15 minut"). */
  podpis: string;
}

export const ZAKRESY_LOGOW: readonly ZakresLogow[] = [
  { id: '15m', sekundy: 900, etykieta: '15 min', podpis: 'ostatnie 15 minut' },
  { id: '1h', sekundy: 3600, etykieta: '1 h', podpis: 'ostatnia godzina' },
  { id: '24h', sekundy: 86_400, etykieta: '24 h', podpis: 'ostatnie 24 godziny' },
] as const;

export const ZAKRES_LOGOW_DOMYSLNY: ZakresLogowId = '1h';

export function zakresLogowZId(id: string | null | undefined): ZakresLogow {
  return ZAKRESY_LOGOW.find((zakres) => zakres.id === id) ?? (ZAKRESY_LOGOW[1] as ZakresLogow);
}

export function podpisZakresuLogow(zakres: ZakresLogow): string {
  return zakres.podpis;
}

/**
 * Limity linii. Loki oddaje surowe linie, więc „wszystko" nie istnieje —
 * musimy wybrać kompromis między kompletem a czasem odpowiedzi.
 */
export const LIMITY_LINII = [200, 500, 1000] as const;
export type LimitLinii = (typeof LIMITY_LINII)[number];
export const LIMIT_LINII_DOMYSLNY: LimitLinii = 200;

export function limitLiniiZId(wartosc: string | number | null | undefined): LimitLinii {
  const liczba = Number(wartosc);
  return (LIMITY_LINII as readonly number[]).includes(liczba)
    ? (liczba as LimitLinii)
    : LIMIT_LINII_DOMYSLNY;
}

/* ------------------------------------------------------------------ *
 * Źródła logów
 * ------------------------------------------------------------------ */

export type ZrodloLogowId = 'usluga' | 'host' | 'traefik';

export interface ZrodloLogow {
  id: ZrodloLogowId;
  nazwa: string;
  opis: string;
}

export const ZRODLA_LOGOW: readonly ZrodloLogow[] = [
  { id: 'usluga', nazwa: 'Usługa', opis: 'Logi kontenerów wybranej usługi (z Docker API)' },
  { id: 'host', nazwa: 'Host (journald)', opis: 'Journal systemowy: sshd, docker, jądro' },
  { id: 'traefik', nazwa: 'Traefik (access log)', opis: 'Żądania HTTP edge’a — host, ścieżka, kod' },
] as const;

export function zrodloLogowZId(id: string | null | undefined): ZrodloLogow {
  return ZRODLA_LOGOW.find((zrodlo) => zrodlo.id === id) ?? (ZRODLA_LOGOW[0] as ZrodloLogow);
}

/**
 * Selektory LogQL. `service` w Loki to `<stack>_<usługa>` (promtail bierze to
 * z `com.docker.swarm.service.name`), a `stack` to przestrzeń nazw stacka.
 */
export function zapytanieUslugi(stack: string, usluga: string): string {
  return `{job="docker", stack="${stack}", service="${stack}_${usluga}"}`;
}

export function zapytanieZrodla(
  zrodlo: ZrodloLogowId,
  stack: string,
  usluga: string,
): string {
  if (zrodlo === 'host') return '{job="journald", unit=~".+"}';
  if (zrodlo === 'traefik') return '{job="traefik"}';
  return zapytanieUslugi(stack, usluga);
}

/**
 * Adres żądania logów do NASZEJ usługi discovery (`/status/logs`).
 *
 * Świadome odejście od wołania Loki'ego wprost z przeglądarki: panel wysyła
 * parametry strukturalne, a LogQL buduje serwer, więc tekst użytkownika nigdy
 * nie trafia do zapytania (brak wstrzykiwania/regexów) i działa to niezależnie
 * od tego, czy edge wystawia `/loki` na tym samym originie — a `/status/*`
 * jest trasowane na pewno, bo panel już z niego czyta stan usług.
 */
export function zbudujUrlLogow(
  stack: string,
  usluga: string,
  zrodlo: ZrodloLogowId,
  zakres: ZakresLogow,
  limit: LimitLinii,
): string {
  const parametry = new URLSearchParams({
    zrodlo,
    zakres: zakres.id,
    limit: String(limit),
  });
  if (zrodlo === 'usluga') {
    parametry.set('stack', stack);
    parametry.set('usluga', usluga);
  }
  return `/status/logs?${parametry.toString()}`;
}

/** Deep link do Grafana Explore z tym samym zapytaniem (względny — jedno logowanie). */
export function linkGrafanaExplore(expr: string, zakres: ZakresLogow): string {
  const panes = {
    logi: {
      datasource: 'loki',
      queries: [{ refId: 'A', expr, queryType: 'range' }],
      range: { from: `now-${zakres.sekundy}s`, to: 'now' },
    },
  };
  const parametry = new URLSearchParams({
    schemaVersion: '1',
    orgId: '1',
    panes: JSON.stringify(panes),
  });
  return `/grafana/explore?${parametry.toString()}`;
}

/* ------------------------------------------------------------------ *
 * Odpowiedź Loki
 * ------------------------------------------------------------------ */

export interface LiniaLogu {
  /** Czas linii w sekundach (z nanosekund Loki'ego). */
  czas: number;
  tekst: string;
  /** Etykiety strumienia, z którego przyszła linia (skrócone do istotnych). */
  strumien: string;
}

const DASH = '—';

function rekord(wartosc: unknown): Record<string, unknown> | null {
  return typeof wartosc === 'object' && wartosc !== null && !Array.isArray(wartosc)
    ? (wartosc as Record<string, unknown>)
    : null;
}

function tekst(wartosc: unknown): string | null {
  return typeof wartosc === 'string' && wartosc.length > 0 ? wartosc : null;
}

/** Krótki opis strumienia: `service` → `unit` → `container` → `job`. */
export function opisStrumienia(labels: unknown): string {
  const etykiety = rekord(labels);
  if (!etykiety) return DASH;
  return (
    tekst(etykiety.service) ??
    tekst(etykiety.unit) ??
    tekst(etykiety.container) ??
    tekst(etykiety.RequestHost) ??
    tekst(etykiety.job) ??
    DASH
  );
}

/**
 * Parsuje `data.result` z Loki na płaską listę linii, najnowsze pierwsze.
 *
 * Odpowiedź bywa dziurawa (brak `values`, zły znacznik czasu, `null` w treści),
 * a wywalenie się na niej oznaczałoby pusty widok bez wyjaśnienia — dlatego
 * każdy krok jest sprawdzany, a śmieci są pomijane, nie „naprawiane".
 */
export function parsujOdpowiedzLoki(dane: unknown): LiniaLogu[] {
  const korzen = rekord(dane);
  // Kształt z naszego `/status/logs`: gotowa lista linii.
  if (Array.isArray(korzen?.linie)) {
    const gotowe: LiniaLogu[] = [];
    for (const wpis of korzen.linie as unknown[]) {
      const linia = rekord(wpis);
      if (!linia) continue;
      const czas = Number(linia.czas);
      const tekst = typeof linia.tekst === 'string' ? linia.tekst : null;
      if (!Number.isFinite(czas) || tekst === null) continue;
      gotowe.push({
        czas,
        tekst,
        strumien: typeof linia.strumien === 'string' && linia.strumien.length > 0 ? linia.strumien : DASH,
      });
    }
    gotowe.sort((a, b) => b.czas - a.czas);
    return gotowe;
  }
  // Kształt surowej odpowiedzi Loki (`data.result[].values`) — przydatny
  // w testach i gdyby panel kiedyś czytał Loki bezpośrednio.
  const wynik = rekord(korzen?.data)?.result;
  if (!Array.isArray(wynik)) return [];
  const linie: LiniaLogu[] = [];
  for (const strumien of wynik) {
    const opis = rekord(strumien);
    if (!opis) continue;
    const etykieta = opisStrumienia(opis.stream);
    const wartosci = Array.isArray(opis.values) ? opis.values : [];
    for (const wpis of wartosci) {
      if (!Array.isArray(wpis) || wpis.length < 2) continue;
      const nanosekundy = Number(wpis[0]);
      const tresc = typeof wpis[1] === 'string' ? wpis[1] : null;
      if (!Number.isFinite(nanosekundy) || tresc === null) continue;
      linie.push({ czas: nanosekundy / 1e9, tekst: tresc, strumien: etykieta });
    }
  }
  linie.sort((a, b) => b.czas - a.czas);
  return linie;
}

/* ------------------------------------------------------------------ *
 * Filtrowanie i prezentacja
 * ------------------------------------------------------------------ */

/**
 * Filtr podciągiem (bez rozróżniania wielkości liter), kilka słów = wszystkie
 * muszą wystąpić (AND). Pusty filtr przepuszcza wszystko.
 */
export function filtrujLinie(linie: readonly LiniaLogu[], fraza: string): LiniaLogu[] {
  const slowa = fraza
    .toLowerCase()
    .split(/\s+/)
    .filter((slowo) => slowo.length > 0);
  if (slowa.length === 0) return [...linie];
  return linie.filter((linia) => {
    const tresc = linia.tekst.toLowerCase();
    return slowa.every((slowo) => tresc.includes(slowo));
  });
}

/** Etykiety czasu dla nagłówka (UTC, jak reszta panelu). */
export function etykietyCzasuLogow(zakres: ZakresLogow, teraz: number): { od: string; do: string } {
  const format = (sekundy: number): string => {
    const data = new Date(sekundy * 1000);
    const godzina = `${String(data.getUTCHours()).padStart(2, '0')}:${String(data.getUTCMinutes()).padStart(2, '0')}`;
    const dzien = `${String(data.getUTCDate()).padStart(2, '0')}.${String(data.getUTCMonth() + 1).padStart(2, '0')}`;
    return zakres.sekundy >= 86_400 ? `${dzien} ${godzina}` : godzina;
  };
  return { od: format(teraz - zakres.sekundy), do: format(teraz) };
}

/** Godzina linii w kontekście zakresu (24 h → z datą). */
export function formatujCzasLogu(czas: number, zakres: ZakresLogow): string {
  if (!Number.isFinite(czas) || czas <= 0) return DASH;
  const data = new Date(czas * 1000);
  const godzina = `${String(data.getUTCHours()).padStart(2, '0')}:${String(data.getUTCMinutes()).padStart(2, '0')}:${String(data.getUTCSeconds()).padStart(2, '0')}`;
  if (zakres.sekundy < 86_400) return godzina;
  const dzien = `${String(data.getUTCDate()).padStart(2, '0')}.${String(data.getUTCMonth() + 1).padStart(2, '0')}`;
  return `${dzien} ${godzina}`;
}

/** Zdanie o komplecie: ile linii widzimy, a ile przyszło z Loki'ego. */
export function podsumowanieLogow(widoczne: number, wszystkie: number, limit: LimitLinii): string {
  if (wszystkie === 0) return 'brak linii w tym zakresie';
  if (widoczne === wszystkie) {
    return wszystkie >= limit
      ? `${widoczne} linii (osiągnięty limit pobrania — zawęź zakres lub filtr)`
      : `${widoczne} linii`;
  }
  return `${widoczne} z ${wszystkie} linii (filtr)`;
}

/** Tekst do schowka / pliku: czas + strumień + treść. */
export function eksportLogow(linie: readonly LiniaLogu[], zakres: ZakresLogow): string {
  return linie
    .map((linia) => `${formatujCzasLogu(linia.czas, zakres)} [${linia.strumien}] ${linia.tekst}`)
    .join('\n');
}

/* ------------------------------------------------------------------ *
 * Trasa `#/logi`
 * ------------------------------------------------------------------ */

export interface TrasaLogow {
  usluga: string | null;
  zakres: ZakresLogowId;
  zrodlo: ZrodloLogowId;
}

export function czyTrasaLogow(hash: string = ''): boolean {
  return /^#\/logi(?:\/|\?|$)/.test(hash || '');
}

export function zHaszaLogi(hash: string): TrasaLogow {
  const czysty = (hash || '').replace(/^#/, '');
  const [sciezka = '', zapytanie = ''] = czysty.split('?');
  const czesci = sciezka.split('/').filter((kawalek) => kawalek.length > 0);
  const surowa = czesci.length > 1 ? czesci.slice(1).join('/') : '';
  let usluga: string | null = null;
  if (surowa) {
    try {
      usluga = decodeURIComponent(surowa);
    } catch {
      usluga = surowa;
    }
  }
  const parametry = new URLSearchParams(zapytanie);
  return {
    usluga: usluga && usluga.length > 0 ? usluga : null,
    zakres: zakresLogowZId(parametry.get('zakres')).id,
    zrodlo: zrodloLogowZId(parametry.get('zrodlo')).id,
  };
}

/** Adres widoku logów; domyślne wartości pomijamy (krótszy, czytelniejszy link). */
export function doHaszaLogi(
  usluga: string | null,
  zakres: ZakresLogowId = ZAKRES_LOGOW_DOMYSLNY,
  zrodlo: ZrodloLogowId = 'usluga',
): string {
  const baza = usluga ? `#/logi/${encodeURIComponent(usluga)}` : '#/logi';
  const parametry = new URLSearchParams();
  if (zakres !== ZAKRES_LOGOW_DOMYSLNY) parametry.set('zakres', zakres);
  if (zrodlo !== 'usluga') parametry.set('zrodlo', zrodlo);
  const ogon = parametry.toString();
  return ogon ? `${baza}?${ogon}` : baza;
}

/**
 * Podpowiedź pod listą, gdy nic nie przyszło. Osobno dla access logu, bo jego
 * brak to najczęstsza (i prawdziwa) przyczyna pustki — a nie „brak ruchu".
 */
export function podpowiedzPustki(zrodlo: ZrodloLogowId, zakres: ZakresLogow): string {
  if (zrodlo === 'traefik') {
    return `Brak linii w zakresie (${zakres.podpis}). Access log edge’a bywa wyłączony — jeśli tak jest, alert „TraefikNoAccessLogs” jest aktywny, a brak linii nie oznacza braku ruchu.`;
  }
  if (zrodlo === 'host') {
    return `Brak linii z journala w zakresie (${zakres.podpis}). Cisza w journalu bywa normalna — sprawdź filtr albo dłuższy zakres.`;
  }
  return `Brak linii tej usługi w zakresie (${zakres.podpis}). Kontener mógł nie pisać do stdout albo wystartował później.`;
}

/** Komunikat błędu z `/status/logs` (albo `null`, gdy odpowiedź jest dobra). */
export function bladLogow(dane: unknown): string | null {
  const korzen = rekord(dane);
  const blad = korzen?.error;
  return typeof blad === 'string' && blad.trim().length > 0 ? blad.trim() : null;
}
