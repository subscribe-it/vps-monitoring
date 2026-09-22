/**
 * Czysta logika widoku „Wykresy" — bez DOM i bez importów, więc testuje się
 * ją Node'em (`scripts/ci/check_wykresy.mts`), a nie „na oko" w przeglądarce.
 *
 * Po co osobny widok: żeby zobaczyć zużycie jednej usługi nie trzeba było
 * wchodzić do Grafany (osadzona ramka oddaje wykresy razem z jej nawigacją
 * i nie da się w niej kliknąć „pokaż mi tę usługę w 24 h").
 *
 * Skąd dane (sprawdzone na produkcji 22.09.2026):
 *  - `/status/api.json` — wartości BIEŻĄCE per usługa (`cpu_percent`,
 *    `mem_bytes`). Uwaga: API NIE wystawia limitów (ani CPU, ani RAM),
 *  - Prometheus — szeregi czasowe przez `/prometheus/api/v1/query_range`:
 *    `sum by (stack, service) (swarm_container_cpu_percent)`,
 *    `…_memory_bytes`, `…_memory_limit_bytes` (limit RAM jest TYLKO tutaj)
 *    oraz `rate(…_network_receive/transmit_bytes_total[5m])` w B/s.
 *
 * LIMIT CPU: nie ma go ani w API, ani w metrykach (limity CPU żyją w specyfikacji
 * usługi Swarm i nie są eksportowane). Dlatego CPU pokazujemy jako wartość
 * bezwzględną w procentach, a nie jako „% limitu".
 *
 * // TODO: [待确认] limit CPU nie jest wystawiany przez API — pokazujemy %
 * // bezwzględny; gdy discovery zacznie eksportować limit (albo dojdzie metryka
 * // `swarm_service_cpu_limit`), wrócić tutaj i dorysować procent limitu.
 */

/* ------------------------------------------------------------------ *
 * Zakresy czasu
 * ------------------------------------------------------------------ */

export type ZakresId = '1h' | '6h' | '24h' | '7d';

export interface Zakres {
  id: ZakresId;
  /** Podpis na przycisku. */
  label: string;
  sekundy: number;
  /** Krok próbkowania Prometheusa (im dłuższy zakres, tym rzadszy). */
  krok: number;
}

export const ZAKRESY: readonly Zakres[] = [
  { id: '1h', label: '1 h', sekundy: 3600, krok: 60 },
  { id: '6h', label: '6 h', sekundy: 6 * 3600, krok: 300 },
  { id: '24h', label: '24 h', sekundy: 24 * 3600, krok: 900 },
  { id: '7d', label: '7 d', sekundy: 7 * 24 * 3600, krok: 3600 },
] as const;

export const ZAKRES_DOMYSLNY: ZakresId = '6h';

/** Zakres po identyfikatorze z hasza; nieznany (lub brak) → domyślny. */
export function zakresZId(id: string | null | undefined): Zakres {
  const znaleziony = ZAKRESY.find((z) => z.id === id);
  return znaleziony ?? (ZAKRESY.find((z) => z.id === ZAKRES_DOMYSLNY) as Zakres);
}

/** Podpis zakresu do zdań: „ostatnie 6 h". */
export function podpisZakresu(zakres: Zakres): string {
  return `ostatnie ${zakres.label}`;
}

/**
 * Etykiety początku i końca osi czasu. Liczone w UTC (panel wszędzie pokazuje
 * UTC), więc wynik nie zależy od strefy maszyny — inaczej testy i produkcja
 * pokazywałyby inne godziny.
 */
export function etykietyCzasu(zakres: Zakres, teraz: number): { od: string; do: string } {
  const koniec = new Date(teraz * 1000);
  const poczatek = new Date((teraz - zakres.sekundy) * 1000);
  return { od: etykietaChwili(poczatek, zakres), do: etykietaChwili(koniec, zakres) };
}

function etykietaChwili(data: Date, zakres: Zakres): string {
  const godzina = `${dwa(data.getUTCHours())}:${dwa(data.getUTCMinutes())}`;
  // 24 h też pokazuje datę: bez niej początek i koniec osi mają tę samą godzinę
  // (22:06 → 22:06) i wyglądają na błąd rysowania.
  if (zakres.sekundy < 24 * 3600) return godzina;
  return `${dwa(data.getUTCDate())}.${dwa(data.getUTCMonth() + 1)} ${godzina}`;
}

function dwa(liczba: number): string {
  return String(liczba).padStart(2, '0');
}

/* ------------------------------------------------------------------ *
 * Formatowanie liczb (polski przecinek, jednostki binarne)
 * ------------------------------------------------------------------ */

const DASH = '—';

/** Czy wartość nadaje się na wykres (odrzuca `null`, `NaN`, `Infinity`). */
export function czyLiczba(wartosc: unknown): wartosc is number {
  return typeof wartosc === 'number' && Number.isFinite(wartosc);
}

/** Liczba z przecinkiem dziesiętnym; `null` → „—". */
export function formatujLiczbe(wartosc: number | null | undefined, miejsca = 2): string {
  if (!czyLiczba(wartosc)) return DASH;
  return wartosc.toFixed(miejsca).replace('.', ',');
}

/** Procent z przecinkiem: „48,3%". */
export function formatujProcent(wartosc: number | null | undefined, miejsca = 2): string {
  if (!czyLiczba(wartosc)) return DASH;
  return `${formatujLiczbe(wartosc, miejsca)}%`;
}

const JEDNOSTKI_BAJTOW = ['B', 'KiB', 'MiB', 'GiB', 'TiB'] as const;

/**
 * Bajty w jednostkach binarnych (jak `fmtBytes` w `status.ts` — trzymamy tę
 * samą konwencję, żeby panel nie pokazywał dwóch różnych „MiB").
 */
export function formatujBajty(bajty: number | null | undefined, miejsca = 1): string {
  if (!czyLiczba(bajty)) return DASH;
  let wartosc = bajty;
  let indeks = 0;
  while (Math.abs(wartosc) >= 1024 && indeks < JEDNOSTKI_BAJTOW.length - 1) {
    wartosc /= 1024;
    indeks += 1;
  }
  const dokladnosc = indeks === 0 ? 0 : miejsca;
  return `${formatujLiczbe(wartosc, dokladnosc)} ${JEDNOSTKI_BAJTOW[indeks]}`;
}

/** Przepustowość sieci: „12,4 KiB/s". */
export function formatujPrzeplywnosc(bajtyNaSekunde: number | null | undefined, miejsca = 1): string {
  if (!czyLiczba(bajtyNaSekunde)) return DASH;
  return `${formatujBajty(bajtyNaSekunde, miejsca)}/s`;
}

/** Ile procent limitu zajmuje wartość; brak sensownego limitu → `null`. */
export function procentLimitu(
  wartosc: number | null | undefined,
  limit: number | null | undefined,
): number | null {
  if (!czyLiczba(wartosc) || !czyLiczba(limit) || limit <= 0) return null;
  return (wartosc / limit) * 100;
}

/**
 * Linia z liczbami pod wykresem CPU.
 *
 * Limit CPU nie istnieje w danych (patrz nagłówek pliku) — mówimy to wprost,
 * zamiast pokazywać procent, którego nie ma z czego policzyć.
 */
export function opisCpu(teraz: number | null, maks: number | null = null): string {
  const czesci = [`teraz ${formatujProcent(teraz)}`];
  if (czyLiczba(maks)) czesci.push(`maks. ${formatujProcent(maks)}`);
  czesci.push('limit: brak w API');
  return czesci.join(' · ');
}

/** Linia z liczbami pod wykresem RAM: „teraz / limit" i procent limitu. */
export function opisRam(
  teraz: number | null,
  limit: number | null,
  maks: number | null = null,
): string {
  const procent = procentLimitu(teraz, limit);
  const czesci = [
    `${formatujBajty(teraz)} / ${formatujBajty(limit)}`,
    procent === null ? 'brak limitu' : `${formatujLiczbe(procent, 1)}% limitu`,
  ];
  if (czyLiczba(maks)) czesci.push(`maks. ${formatujBajty(maks)}`);
  return czesci.join(' · ');
}

/** Linia z liczbami pod wykresem sieci — sieć nie ma limitu i tak to nazywamy. */
export function opisSieci(
  rx: number | null,
  tx: number | null,
  maksRx: number | null = null,
): string {
  const czesci = [`rx ${formatujPrzeplywnosc(rx)}`, `tx ${formatujPrzeplywnosc(tx)}`];
  if (czyLiczba(maksRx)) czesci.push(`maks. rx ${formatujPrzeplywnosc(maksRx)}`);
  czesci.push('brak limitu');
  return czesci.join(' · ');
}

/**
 * Pełny podpis statystyk dla widoku szczegółów (teraz / maks / średnia).
 *
 * Wartość „teraz" bierzemy z API (świeższa niż ostatni punkt serii), a gdy
 * jej nie ma — z serii. Limit CPU nie istnieje w danych, więc zamiast procentu
 * mówimy wprost, że go nie ma.
 */
export function statystykiCpu(st: Statystyki, teraz: number | null = null): string {
  const biezace = czyLiczba(teraz) ? teraz : st.teraz;
  return [
    `teraz ${formatujProcent(biezace)}`,
    `maks. ${formatujProcent(st.maks)}`,
    `średnia ${formatujProcent(st.srednia)}`,
    'limit: brak w API',
  ].join(' · ');
}

export function statystykiRam(st: Statystyki, limit: number | null, teraz: number | null = null): string {
  const biezace = czyLiczba(teraz) ? teraz : st.teraz;
  const procent = procentLimitu(biezace, limit);
  const czesci = [
    `teraz ${formatujBajty(biezace)}`,
    `maks. ${formatujBajty(st.maks)}`,
    `średnia ${formatujBajty(st.srednia)}`,
    procent === null
      ? 'limit: brak w danych'
      : `limit ${formatujBajty(limit)} (${formatujLiczbe(procent, 1)}%)`,
  ];
  return czesci.join(' · ');
}

export function statystykiSieci(
  rx: Statystyki,
  tx: Statystyki,
  terazRx: number | null = null,
  terazTx: number | null = null,
): string {
  const biezaceRx = czyLiczba(terazRx) ? terazRx : rx.teraz;
  const biezaceTx = czyLiczba(terazTx) ? terazTx : tx.teraz;
  return [
    `teraz rx ${formatujPrzeplywnosc(biezaceRx)} / tx ${formatujPrzeplywnosc(biezaceTx)}`,
    `maks. rx ${formatujPrzeplywnosc(rx.maks)} / tx ${formatujPrzeplywnosc(tx.maks)}`,
    `średnia rx ${formatujPrzeplywnosc(rx.srednia)} / tx ${formatujPrzeplywnosc(tx.srednia)}`,
    'brak limitu',
  ].join(' · ');
}

/* ------------------------------------------------------------------ *
 * Statystyki serii
 * ------------------------------------------------------------------ */

export interface Statystyki {
  teraz: number | null;
  maks: number | null;
  minimum: number | null;
  srednia: number | null;
  ile: number;
}

/** Teraz / maksimum / minimum / średnia z serii (odporne na dziury i `null`-e). */
export function statystyki(wartosci: readonly (number | null | undefined)[]): Statystyki {
  const czyste = wartosci.filter(czyLiczba);
  if (czyste.length === 0) {
    return { teraz: null, maks: null, minimum: null, srednia: null, ile: 0 };
  }
  const suma = czyste.reduce((razem, v) => razem + v, 0);
  return {
    teraz: czyste[czyste.length - 1] as number,
    maks: Math.max(...czyste),
    minimum: Math.min(...czyste),
    srednia: suma / czyste.length,
    ile: czyste.length,
  };
}

/* ------------------------------------------------------------------ *
 * Geometria wykresu (SVG)
 * ------------------------------------------------------------------ */

export interface Granice {
  min: number;
  max: number;
}

/**
 * Granice osi Y. Domyślnie z danych, z opcjonalnym „od zera" (CPU) i zapasem,
 * żeby linia nie kleiła się do krawędzi. Seria płaska dostaje sensowną wysokość,
 * a nie zerową (inaczej wykres wygląda na zepsuty).
 */
export function graniceWykresu(
  wartosci: readonly (number | null | undefined)[],
  opcje: { odZera?: boolean; zapas?: number } = {},
): Granice {
  const czyste = wartosci.filter(czyLiczba);
  const zapas = opcje.zapas ?? 0.08;
  if (czyste.length === 0) return { min: 0, max: 1 };
  const surowyMin = Math.min(...czyste);
  const surowyMax = Math.max(...czyste);
  let min = opcje.odZera ? 0 : surowyMin;
  let max = surowyMax;
  if (opcje.odZera) min = 0;
  if (max === min) {
    // Płaska seria: dla zera pokazujemy 0–1, dla wartości dodatniej ±10%.
    if (max === 0) return { min: 0, max: 1 };
    const rozstep = Math.abs(max) * 0.1;
    min = opcje.odZera ? 0 : max - rozstep;
    max = max + rozstep;
  } else {
    const rozstep = (max - min) * zapas;
    max += rozstep;
    if (!opcje.odZera) min -= rozstep;
  }
  return { min, max };
}

/**
 * Wartości linii siatki (osie Y) — „ładne" liczby: 1, 2, 5 × 10ⁿ.
 * Zawsze malejąco (od góry wykresu), więc rysowanie idzie wprost po indeksie.
 *
 * Gdy „ładny" krok daje tylko jedną linię (zmierzone na mocku: RAM z limitem
 * 512 MiB, dane 40–52 MiB — jedyny ładny krok to 500 MiB), dzielimy zakres
 * równo. Inaczej górna i dolna etykieta osi pokazują tę samą liczbę, co wygląda
 * na błąd rysowania i myli przy czytaniu wykresu.
 */
export function osieY(granice: Granice, ile = 4): number[] {
  const kroki = ile < 2 ? 2 : Math.floor(ile);
  const zakres = granice.max - granice.min;
  if (!(zakres > 0)) return [granice.max];
  const krok = ladnyKrok(zakres / (kroki - 1));
  const wynik: number[] = [];
  const start = Math.ceil(granice.min / krok) * krok;
  for (let v = start; v <= granice.max + krok / 1000 && wynik.length < kroki + 2; v += krok) {
    wynik.push(Number(v.toFixed(6)));
  }
  if (wynik.length < Math.min(3, kroki)) {
    // Dwie linie to za mało: etykieta „środek" zlałaby się z dolną (zmierzone
    // na RAM z limitem 512 MiB i na sieci — obie pokazywały tę samą wartość).
    return Array.from({ length: kroki }, (_, indeks) =>
      Number((granice.max - (zakres * indeks) / (kroki - 1)).toFixed(6)),
    );
  }
  return wynik.reverse();
}

function ladnyKrok(surowy: number): number {
  if (!(surowy > 0)) return 1;
  const wykladnik = Math.floor(Math.log10(surowy));
  const podstawa = surowy / 10 ** wykladnik;
  const ladna = podstawa <= 1 ? 1 : podstawa <= 2 ? 2 : podstawa <= 5 ? 5 : 10;
  return ladna * 10 ** wykladnik;
}

/** Punkty `<polyline>` dla serii: `x,y x,y …` (Y odwrócone — SVG rośnie w dół). */
export function punktyWykresu(
  wartosci: readonly (number | null | undefined)[],
  szerokosc: number,
  wysokosc: number,
  granice: Granice,
  opcje: { margines?: number } = {},
): string {
  const czyste = wartosci.filter(czyLiczba);
  if (czyste.length === 0) return '';
  const margines = opcje.margines ?? 4;
  const uzyteczna = Math.max(1, wysokosc - 2 * margines);
  const rozstep = granice.max - granice.min || 1;
  const indeksy = wartosci
    .map((v, i) => ({ v, i }))
    .filter((p): p is { v: number; i: number } => czyLiczba(p.v));

  if (indeksy.length === 1) {
    const y = margines + uzyteczna / 2;
    return `0,${y.toFixed(2)} ${szerokosc},${y.toFixed(2)}`;
  }

  const krokX = szerokosc / Math.max(1, wartosci.length - 1);
  return indeksy
    .map(({ v, i }) => {
      const x = i * krokX;
      const udzial = (v - granice.min) / rozstep;
      const y = margines + (1 - Math.min(1, Math.max(0, udzial))) * uzyteczna;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

/* ------------------------------------------------------------------ *
 * Zapytania do Prometheusa
 * ------------------------------------------------------------------ */

export interface ZapytanieZbiorcze {
  id: 'cpu' | 'ram' | 'limit' | 'rx' | 'tx';
  expr: string;
  opis: string;
}

/**
 * Pięć zapytań na CAŁY widok (zamiast trzech na usługę).
 *
 * Powód: lista pokazuje ~50 usług × 3 wykresy — zapytanie per usługa to ~150
 * żądań na jedno wejście. Prometheus oddaje wszystkie serie jednym zapytaniem
 * (`by (stack, service)`), a panel tylko wybiera z nich swoją usługę.
 */
export function zapytaniaZbiorcze(): readonly ZapytanieZbiorcze[] {
  return [
    { id: 'cpu', expr: 'sum by (stack, service) (swarm_container_cpu_percent)', opis: 'CPU' },
    { id: 'ram', expr: 'sum by (stack, service) (swarm_container_memory_bytes)', opis: 'RAM' },
    {
      id: 'limit',
      expr: 'sum by (stack, service) (swarm_container_memory_limit_bytes)',
      opis: 'Limit RAM',
    },
    {
      id: 'rx',
      expr: 'sum by (stack, service) (rate(swarm_container_network_receive_bytes_total[5m]))',
      opis: 'Sieć odbiór',
    },
    {
      id: 'tx',
      expr: 'sum by (stack, service) (rate(swarm_container_network_transmit_bytes_total[5m]))',
      opis: 'Sieć wysyłka',
    },
  ] as const;
}

/** Klucz serii w mapie odpowiedzi — `stack/usługa` (jak `kluczFokusa`). */
export function kluczSerii(stack: string, usluga: string): string {
  return `${stack}/${usluga}`;
}

/** Adres `query_range` dla wyrażenia i zakresu (start liczony od `teraz`). */
export function zbudujUrlQueryRange(expr: string, zakres: Zakres, teraz: number): string {
  const parametry = new URLSearchParams({
    query: expr,
    start: String(Math.floor(teraz - zakres.sekundy)),
    end: String(Math.floor(teraz)),
    step: String(zakres.krok),
  });
  return `/prometheus/api/v1/query_range?${parametry.toString()}`;
}

/* ------------------------------------------------------------------ *
 * Trasa `#/wykresy`
 * ------------------------------------------------------------------ */

export interface TrasaWykresow {
  usluga: string | null;
  zakres: ZakresId;
}

/** Czy hasz opisuje widok wykresów (`#/wykresy`, `#/wykresy/<usługa>?zakres=…`)? */
export function czyTrasaWykresow(hash: string = ''): boolean {
  return /^#\/wykresy(?:\/|\?|$)/.test(hash || '');
}

export function zHaszaWykresy(hash: string): TrasaWykresow {
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
    zakres: zakresZId(parametry.get('zakres')).id,
  };
}

/** Adres widoku wykresów (zakres domyślny pomijamy — krótszy, czytelniejszy link). */
export function doHaszaWykresow(usluga: string | null, zakres: ZakresId = ZAKRES_DOMYSLNY): string {
  const baza = usluga ? `#/wykresy/${encodeURIComponent(usluga)}` : '#/wykresy';
  return zakres === ZAKRES_DOMYSLNY ? baza : `${baza}?zakres=${zakres}`;
}

/**
 * Znajduje usługę po segmencie trasy. Nazwy usług bywają powtarzalne między
 * stackami (`db` jest w kilku), więc przyjmujemy trzy postacie:
 * `stack/usługa`, pełna nazwa z API (`stack_usługa`) i sama nazwa — o ile
 * jest jednoznaczna. Zwraca `null`, gdy nic nie pasuje.
 */
export function znajdzUsluge<T extends { name: string; full_name: string | null }>(
  uslugi: readonly { stack: string; usluga: T }[],
  segment: string | null,
): { stack: string; usluga: T } | null {
  if (!segment) return null;
  const poFokusie = uslugi.find((p) => kluczSerii(p.stack, p.usluga.name) === segment);
  if (poFokusie) return poFokusie;
  const poPelnej = uslugi.find((p) => p.usluga.full_name === segment);
  if (poPelnej) return poPelnej;
  const poNazwie = uslugi.filter((p) => p.usluga.name === segment);
  return poNazwie.length === 1 ? (poNazwie[0] as { stack: string; usluga: T }) : null;
}
