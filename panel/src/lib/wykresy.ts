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
 *    `mem_bytes`) oraz LIMITY z spec usługi Swarm: `cpu_limit_cores`
 *    (NanoCPUs / 1e9) i `mem_limit_bytes` (MemoryBytes); `null` = limit
 *    nieustawiony (nie zero!),
 *  - Prometheus — szeregi czasowe przez `/prometheus/api/v1/query_range`:
 *    `sum by (stack, service) (swarm_container_cpu_percent)`,
 *    `…_memory_bytes`, `…_memory_limit_bytes` oraz
 *    `rate(…_network_receive/transmit_bytes_total[5m])` w B/s.
 *
 * KOLEJNOŚĆ ŹRÓDEŁ LIMITÓW (świadoma, patrz `index.astro`):
 *  1. RAM — `mem_limit_bytes` z API (to samo, co widzi Swarm w spec usługi),
 *     a gdy API nie ma limitu, fallback na metrykę `swarm_container_memory_limit_bytes`,
 *  2. CPU — `cpu_limit_cores` z API przeliczony na procent jednego rdzenia
 *     (`× 100`, bo `cpu_percent` jest w procentach rdzenia),
 *  3. brak limitu w API = „limit: brak w API" — nie zgadujemy progu.
 *
 * Uwaga o jednostkach: `NanoCPUs` 250000000 = 0,25 vCPU = 25% jednego rdzenia,
 * więc limit na wykresie CPU rysujemy na `cpu_limit_cores * 100` procentach.
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

/**
 * Limit CPU w procentach jednego rdzenia (250000000 NanoCPUs → 25).
 *
 * `cpu_percent` z Dockera jest w procentach rdzenia, więc tylko po takim
 * przeliczeniu procent limitu ma sens. Brak limitu → `null`.
 */
export function limitCpuProcent(limitCores: number | null | undefined): number | null {
  if (!czyLiczba(limitCores) || limitCores <= 0) return null;
  return limitCores * 100;
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
 * Linia z liczbami pod wykresem CPU: „teraz … · maks. … · limit 0,25 vCPU · 48%".
 *
 * Gdy API nie zna limitu (`cpu_limit_cores` = null), mówimy wprost
 * „limit: brak w API" — nie zgadujemy progu ani nie liczymy procentu z niczego.
 */
export function opisCpu(
  teraz: number | null,
  limitCores: number | null = null,
  maks: number | null = null,
): string {
  const czesci = [`teraz ${formatujProcent(teraz)}`];
  if (czyLiczba(maks)) czesci.push(`maks. ${formatujProcent(maks)}`);
  const limitProc = limitCpuProcent(limitCores);
  if (limitProc === null) {
    czesci.push('limit: brak w API');
  } else {
    czesci.push(`limit ${formatujLiczbe(limitCores as number, 2)} vCPU`);
    const procent = procentLimitu(teraz, limitProc);
    czesci.push(procent === null ? 'brak danych o zużyciu' : `${formatujLiczbe(procent, 1)}% limitu`);
  }
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
export function statystykiCpu(
  st: Statystyki,
  limitCores: number | null = null,
  teraz: number | null = null,
): string {
  const biezace = czyLiczba(teraz) ? teraz : st.teraz;
  const limitProc = limitCpuProcent(limitCores);
  const procent = limitProc === null ? null : procentLimitu(biezace, limitProc);
  return [
    `teraz ${formatujProcent(biezace)}`,
    `maks. ${formatujProcent(st.maks)}`,
    `średnia ${formatujProcent(st.srednia)}`,
    procent === null
      ? 'limit: brak w API'
      : `limit ${formatujLiczbe(limitCores as number, 2)} vCPU (${formatujLiczbe(procent, 1)}%)`,
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

/** Opis liczb dla wykresu dysku (odczyt / zapis) — jak `opisSieci`, inne słowa. */
export function opisDysku(
  odczyt: number | null | undefined,
  zapis: number | null | undefined,
  maksOdczyt: number | null | undefined,
): string {
  const czesc = (nazwa: string, wartosc: number | null | undefined): string =>
    `${nazwa} ${formatujPrzeplywnosc(wartosc, 1)}`;
  const maks = czyLiczba(maksOdczyt) ? ` · maks. odczyt ${formatujPrzeplywnosc(maksOdczyt, 1)}` : '';
  return `${czesc('odczyt', odczyt)} · ${czesc('zapis', zapis)}${maks}`;
}

/** Statystyki dla szczegółów: teraz / maks. / średnia dla obu kierunków I/O. */
export function statystykiDysku(stOdczyt: Statystyki, stZapis: Statystyki): string {
  const czesc = (nazwa: string, st: Statystyki): string =>
    `${nazwa} teraz ${formatujPrzeplywnosc(st.teraz, 1)} · maks. ${formatujPrzeplywnosc(st.maks, 1)} · średnia ${formatujPrzeplywnosc(st.srednia, 1)}`;
  return `${czesc('odczyt', stOdczyt)} · ${czesc('zapis', stZapis)}`;
}

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
  id: 'cpu' | 'ram' | 'limit' | 'rx' | 'tx' | 'io_r' | 'io_w';
  expr: string;
  opis: string;
}

/**
 * Siedem zapytań na CAŁY widok (zamiast trzech na usługę).
 *
 * Powód: lista pokazuje ~50 usług × 4 wykresy — zapytanie per usługa to ~200
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
    {
      id: 'io_r',
      expr: 'sum by (stack, service) (rate(swarm_container_block_read_bytes_total[5m]))',
      opis: 'Dysk odczyt',
    },
    {
      id: 'io_w',
      expr: 'sum by (stack, service) (rate(swarm_container_block_write_bytes_total[5m]))',
      opis: 'Dysk zapis',
    },
  ] as const;
}

/** Klucz serii w mapie odpowiedzi — `stack/usługa` (jak `kluczFokusa`). */
export function kluczSerii(stack: string, usluga: string): string {
  return `${stack}/${usluga}`;
}

/**
 * Adres zapytania NATYCHMIASTOWEGO (`/prometheus/api/v1/query`).
 *
 * Ranking „Top 10" to migawka, nie przebieg: `topk(10, …)` w `query_range`
 * oddaje macierz (`values`), a nam wystarczy jedna wartość na usługę — wtedy
 * odpowiedź ma kształt `value` i nie ciągniemy dziesiątek punktów na usługę.
 */
export function zbudujUrlQueryInstant(expr: string, teraz: number): string {
  const parametry = new URLSearchParams({ query: expr, time: String(Math.floor(teraz)) });
  return `/prometheus/api/v1/query?${parametry.toString()}`;
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
 * Odświeżanie danych w widoku wykresów
 * ------------------------------------------------------------------ */

/**
 * Interwał odświeżania danych. Domyślnie 10 s — użytkownik chce „na żywo",
 * ale 5 s potrafi już zamrugać na wolnym łączu, a 30 s jest dla porównania.
 * `off` znaczy „nie odpytuj Prometheusa w tle" (np. przy analizie wykresu).
 */
export type OdswiezId = '5s' | '10s' | '30s' | 'off';

export interface Odswiezanie {
  id: OdswiezId;
  etykieta: string;
  /** Milisekundy; `null` = odświeżanie wyłączone. */
  ms: number | null;
}

export const ODSWIEZANIA: readonly Odswiezanie[] = [
  { id: '5s', etykieta: '5 s', ms: 5_000 },
  { id: '10s', etykieta: '10 s', ms: 10_000 },
  { id: '30s', etykieta: '30 s', ms: 30_000 },
  { id: 'off', etykieta: 'Wyłączone', ms: null },
];

export const ODSWIEZANIE_DOMYSLNE: OdswiezId = '10s';

export function odswiezanieZId(id: string | null | undefined): Odswiezanie {
  const znalezione = ODSWIEZANIA.find((odswiezanie) => odswiezanie.id === id);
  if (znalezione) return znalezione;
  return ODSWIEZANIA.find((o) => o.id === ODSWIEZANIE_DOMYSLNE) as Odswiezanie;
}

export function podpisOdswiezania(odswiezanie: Odswiezanie): string {
  return odswiezanie.ms === null
    ? 'odświeżanie wyłączone'
    : `dane co ${odswiezanie.etykieta}`;
}

/** Czy w ogóle stawiać timer („wyłączone" = zero zapytań w tle). */
export function czyOdswiezac(odswiezanie: Odswiezanie): boolean {
  return odswiezanie.ms !== null && odswiezanie.ms > 0;
}

/* ------------------------------------------------------------------ *
 * Trasa `#/wykresy`
 * ------------------------------------------------------------------ */

export interface TrasaWykresow {
  /** `null` = cały VPS, `'wszystkie'` = lista usług, inaczej `stack/usługa`. */
  podmiot: string | null;
  zakres: ZakresId;
  odswiez: OdswiezId;
}

/** Czy hasz opisuje widok wykresów (`#/wykresy`, `#/wykresy/<podmiot>?zakres=…`)? */
export function czyTrasaWykresow(hash: string = ''): boolean {
  return /^#\/wykresy(?:\/|\?|$)/.test(hash || '');
}

export function zHaszaWykresy(hash: string): TrasaWykresow {
  const czysty = (hash || '').replace(/^#/, '');
  const [sciezka = '', zapytanie = ''] = czysty.split('?');
  const czesci = sciezka.split('/').filter((kawalek) => kawalek.length > 0);
  const surowa = czesci.length > 1 ? czesci.slice(1).join('/') : '';
  let podmiot: string | null = null;
  if (surowa) {
    try {
      podmiot = decodeURIComponent(surowa);
    } catch {
      podmiot = surowa;
    }
  }
  const parametry = new URLSearchParams(zapytanie);
  return {
    podmiot: podmiot && podmiot.length > 0 ? podmiot : null,
    zakres: zakresZId(parametry.get('zakres')).id,
    odswiez: odswiezanieZId(parametry.get('odswiez')).id,
  };
}

/**
 * Adres widoku wykresów. Wartości domyślne pomijamy — link ma być krótki
 * i czytelny (`#/wykresy/ventiplan-prod/api?zakres=24h`).
 */
export function doHaszaWykresow(
  podmiot: string | null,
  zakres: ZakresId = ZAKRES_DOMYSLNY,
  odswiez: OdswiezId = ODSWIEZANIE_DOMYSLNE,
): string {
  const baza = podmiot ? `#/wykresy/${encodeURIComponent(podmiot)}` : '#/wykresy';
  const parametry = new URLSearchParams();
  if (zakres !== ZAKRES_DOMYSLNY) parametry.set('zakres', zakres);
  if (odswiez !== ODSWIEZANIE_DOMYSLNE) parametry.set('odswiez', odswiez);
  const zapytanie = parametry.toString();
  return zapytanie ? `${baza}?${zapytanie}` : baza;
}

/** Identyfikator podmiotu „wszystkie usługi" (osobny od nazw usług). */
export const PODMIOT_WSZYSTKIE = 'wszystkie';

/* ------------------------------------------------------------------ *
 * Podmiot wykresu i tytuły
 * ------------------------------------------------------------------ */

/** Czytelna nazwa podmiotu: „cały VPS", „wszystkie usługi" albo nazwa usługi. */
export function podmiotEtykieta(podmiot: string | null): string {
  if (!podmiot) return 'cały VPS';
  if (podmiot === PODMIOT_WSZYSTKIE) return 'wszystkie usługi';
  const czesci = podmiot.split('/');
  const nazwa = czesci.length > 1 ? czesci[czesci.length - 1] : podmiot;
  return nazwa && nazwa.length > 0 ? nazwa : podmiot;
}

/**
 * Tytuł nad wykresem. Wymaganie użytkownika brzmi wprost: nad każdym wykresem
 * ma stać, co to za wykres i czego dotyczy („CPU — cały VPS",
 * „RAM — jolski_na6_pl_prod_wordpress").
 */
export function tytulWykresu(metryka: string, podmiot: string | null): string {
  return `${metryka} — ${podmiotEtykieta(podmiot)}`;
}

/* ------------------------------------------------------------------ *
 * Wykresy całego VPS-a (`node_*` z node-exportera)
 * ------------------------------------------------------------------ */

export interface ZapytanieVps {
  id: string;
  expr: string;
  opis: string;
}

/** Interfejsy wirtualne i mostki nie są ruchem VPS-a — inaczej liczymy podwójnie. */
const BEZ_WIRTUALNYCH = 'device!~"lo|docker.*|veth.*|br-.*|fake0"';

/**
 * Dziewięć zapytań dla widoku „cały VPS". Wszystkie opierają się na metrykach,
 * które na tym hoście realnie istnieją (sprawdzone zapytaniami do Prometheusa
 * 22.09.2026): `node_cpu_seconds_total`, `node_memory_*`, `node_network_*`,
 * `node_filesystem_*`, `node_load1`. Zapytania o „całość" (RAM, dysk, rdzenie)
 * służą wyłącznie do narysowania linii limitu — nie robią osobnych wykresów.
 */
export function zapytaniaVps(): readonly ZapytanieVps[] {
  return [
    {
      id: 'vps_cpu',
      expr: '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
      opis: 'CPU',
    },
    {
      id: 'vps_ram',
      expr: 'node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes',
      opis: 'RAM użyta',
    },
    { id: 'vps_ram_total', expr: 'node_memory_MemTotal_bytes', opis: 'RAM całość' },
    {
      id: 'vps_rx',
      expr: `sum(rate(node_network_receive_bytes_total{${BEZ_WIRTUALNYCH}}[5m]))`,
      opis: 'Sieć odbiór',
    },
    {
      id: 'vps_tx',
      expr: `sum(rate(node_network_transmit_bytes_total{${BEZ_WIRTUALNYCH}}[5m]))`,
      opis: 'Sieć wysyłka',
    },
    {
      id: 'vps_fs',
      expr: 'node_filesystem_size_bytes{mountpoint="/"} - node_filesystem_avail_bytes{mountpoint="/"}',
      opis: 'Dysk użyty',
    },
    {
      id: 'vps_fs_total',
      expr: 'node_filesystem_size_bytes{mountpoint="/"}',
      opis: 'Dysk całość',
    },
    { id: 'vps_load', expr: 'node_load1', opis: 'Obciążenie' },
    { id: 'vps_rdzenie', expr: 'count(node_cpu_seconds_total{mode="idle"})', opis: 'Rdzenie' },
  ];
}

/* ------------------------------------------------------------------ *
 * Geometria i tooltip
 * ------------------------------------------------------------------ */

/**
 * Rozmiar rysunku w jednostkach SVG. `viewBox` skaluje się do szerokości karty
 * (maks. 800 px), więc jedna figura obsługuje i listę, i szczegóły — nie ma już
 * dwóch rozmiarów wykresu („mały" był nieczytelny, co zgłosił użytkownik).
 */
export const WYKRES_SZEROKOSC = 800;
export const WYKRES_WYSOKOSC = 240;
export const WYKRES_MARGINES = 12;
/** Liczba linii siatki = liczba etykiet osi Y. */
export const WYKRES_LINIE = 4;

/**
 * Indeks najbliższego punktu dla pozycji kursora. Rysowanie rozkłada punkty
 * równomiernie po szerokości (`punktyWykresu`), więc ten sam rachunek daje
 * spójny tooltip: to, co pod kursorem, jest tym, co pokazujemy.
 */
export function indeksNajblizszy(
  pozycjaX: number,
  szerokosc: number = WYKRES_SZEROKOSC,
  ile: number,
): number | null {
  if (!(ile > 0) || !(szerokosc > 0) || !Number.isFinite(pozycjaX)) return null;
  if (ile === 1) return 0;
  const udzial = Math.min(1, Math.max(0, pozycjaX / szerokosc));
  return Math.round(udzial * (ile - 1));
}

/**
 * Etykieta chwili dla tooltipa — zawsze UTC i zawsze z datą przy długich
 * zakresach. Zmierzone na mocku: przy 24 h sama godzina dawała „22:06 → 22:06"
 * i nie było widać, że to doba.
 */
export function etykietaPunktu(ts: number, zakres: Zakres): string {
  const data = new Date(ts * 1000);
  const dzien = `${dwa(data.getUTCDate())}.${dwa(data.getUTCMonth() + 1)}`;
  const godzina = `${dwa(data.getUTCHours())}:${dwa(data.getUTCMinutes())}`;
  if (zakres.sekundy <= 3600) return `${godzina}:${dwa(data.getUTCSeconds())} UTC`;
  if (zakres.sekundy <= 86400) return `${godzina} UTC`;
  return `${dzien} ${godzina} UTC`;
}

/** Wiersz tooltipa: nazwa serii i wartość w jednostce wykresu. */
export interface WierszTooltipa {
  nazwa: string;
  wartosc: number | null;
  tekst: string;
}

/**
 * Buduje wiersze tooltipa dla jednego punktu. `serie` to kolejne linie wykresu
 * (przy rx/tx i odczycie/zapisie są dwie — bez nazwy nie da się ich odróżnić).
 */
export function wierszeTooltipa(
  serie: readonly { nazwa: string; wartosci: readonly (number | null | undefined)[] }[],
  indeks: number,
  jednostka: (wartosc: number | null) => string,
): WierszTooltipa[] {
  return serie.map((seria) => {
    const surowa = seria.wartosci[indeks];
    const wartosc = czyLiczba(surowa) ? surowa : null;
    return { nazwa: seria.nazwa, wartosc, tekst: jednostka(wartosc) };
  });
}

/* ------------------------------------------------------------------ *
 * Zbiorczy wykres „Top 10 usług" (`#/wykresy`)
 * ------------------------------------------------------------------ */

/**
 * Metryki zbiorczego rankingu. Jedno zapytanie na metrykę (`topk(10, …)`
 * po `sum by (stack, service)`), a nie po jednym na usługę — inaczej wejście
 * w widok oznaczałoby kilkadziesiąt zapytań do Prometheusa.
 */
export type MetrykaTop = 'cpu' | 'ram' | 'siec';

export interface ZapytanieTop {
  id: MetrykaTop;
  etykieta: string;
  expr: string;
  jednostka: 'procent' | 'bajty' | 'przeplywnosc';
}

export function zapytaniaTop(): readonly ZapytanieTop[] {
  return [
    {
      id: 'cpu',
      etykieta: 'CPU',
      expr: 'topk(10, sum by (stack, service) (swarm_container_cpu_percent))',
      jednostka: 'procent',
    },
    {
      id: 'ram',
      etykieta: 'RAM',
      expr: 'topk(10, sum by (stack, service) (swarm_container_memory_bytes))',
      jednostka: 'bajty',
    },
    {
      id: 'siec',
      etykieta: 'Sieć (rx + tx)',
      expr:
        'topk(10, sum by (stack, service) (rate(swarm_container_network_receive_bytes_total[5m]))'
        + ' + sum by (stack, service) (rate(swarm_container_network_transmit_bytes_total[5m])))',
      jednostka: 'przeplywnosc',
    },
  ] as const;
}

export function zapytanieTop(metryka: MetrykaTop): ZapytanieTop {
  return zapytaniaTop().find((zapytanie) => zapytanie.id === metryka) ?? (zapytaniaTop()[0] as ZapytanieTop);
}

export function metrykaTopZId(id: string | null | undefined): MetrykaTop {
  return zapytaniaTop().find((zapytanie) => zapytanie.id === id)?.id ?? 'cpu';
}

/** Formatuje wartość słupka w jednostce metryki (jedno miejsce na cały ranking). */
export function formatujWartoscTop(metryka: MetrykaTop, wartosc: number | null | undefined): string {
  if (metryka === 'cpu') return formatujProcent(wartosc, 1);
  if (metryka === 'ram') return formatujBajty(wartosc, 1);
  return formatujPrzeplywnosc(wartosc, 1);
}

/**
 * Szerokość słupka w procentach szerokości wiersza. Wartości poniżej progu
 * nie znikają całkiem (min. 2%), bo „prawie zero" też jest informacją, a słupek
 * zerowej szerokości wygląda jak brak danych.
 */
export function szerokoscSlupka(wartosc: number | null | undefined, maks: number | null | undefined): number {
  if (!czyLiczba(wartosc) || wartosc <= 0) return 0;
  if (!czyLiczba(maks) || maks <= 0) return 0;
  const udzial = (wartosc / maks) * 100;
  if (!Number.isFinite(udzial)) return 0;
  return Math.max(2, Math.min(100, Math.round(udzial * 10) / 10));
}

/**
 * Tnie ranking do `ile` pozycji. Prometheus z `topk(10, …)` sam oddaje
 * najwyżej 10 serii, ale panel nie może polegać na tym, że ktoś nie zmieni
 * zapytania — lista bez ograniczenia zalałaby widok setką wierszy.
 */
export function ograniczTop(pozycje: readonly PozycjaTop[], ile = 10): PozycjaTop[] {
  return [...pozycje].slice(0, Math.max(0, ile));
}

export interface PozycjaTop {
  stack: string;
  usluga: string;
  klucz: string;
  wartosc: number;
}

/**
 * Parsuje odpowiedź `topk(…)`. Kolejność: malejąco po wartości (Prometheus
 * oddaje już posortowane, ale nie polegamy na tym — panel ma pokazać ranking).
 */
export function parsujTop(dane: unknown): PozycjaTop[] {
  const rekord = (wartosc: unknown): Record<string, unknown> | null =>
    typeof wartosc === 'object' && wartosc !== null && !Array.isArray(wartosc)
      ? (wartosc as Record<string, unknown>)
      : null;
  const wynik = rekord(rekord(dane)?.data)?.result;
  if (!Array.isArray(wynik)) return [];
  const pozycje: PozycjaTop[] = [];
  for (const seria of wynik) {
    const opis = rekord(seria);
    if (!opis) continue;
    const metryki = rekord(opis.metric) ?? {};
    const stack = typeof metryki.stack === 'string' ? metryki.stack : '';
    const usluga = typeof metryki.service === 'string' ? metryki.service : '';
    // Kształt natychmiastowy (`value`) albo macierz z `query_range` (`values`) —
    // bierzemy ostatni punkt, żeby ranking działał niezależnie od źródła zapytania.
    const natychmiastowe = Array.isArray(opis.value) ? opis.value : null;
    const macierz = Array.isArray(opis.values) && opis.values.length > 0
      ? (opis.values[opis.values.length - 1] as unknown)
      : null;
    const punkt = natychmiastowe ?? (Array.isArray(macierz) ? macierz : null);
    const wartosc = Number(punkt?.[1]);
    if (!stack || !usluga || !Number.isFinite(wartosc)) continue;
    pozycje.push({ stack, usluga, klucz: kluczSerii(stack, usluga), wartosc });
  }
  pozycje.sort((a, b) => b.wartosc - a.wartosc);
  return pozycje;
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
