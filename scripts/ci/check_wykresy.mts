/**
 * Testy czystej logiki widoku „Wykresy" (`panel/src/lib/wykresy.ts`) —
 * bez przeglądarki i bez nowych zależności.
 *
 * Uruchamiane Node'em 23.6+ (type stripping wbudowany; w CI jest Node 24).
 * Powód istnienia: geometria wykresu, procenty limitów i formatowanie liczb to
 * reguły, których nie widać w kodzie, a pomyłka w nich pokazuje nieprawdę
 * (np. „120% limitu", gdy limit wynosi zero, albo oś Y rozciągniętą do
 * jednego piksela przy płaskiej serii).
 *
 *   node scripts/ci/check_wykresy.mts
 */

import {
  ZAKRESY,
  ZAKRES_DOMYSLNY,
  czyLiczba,
  czyTrasaWykresow,
  doHaszaWykresow,
  etykietyCzasu,
  formatujBajty,
  formatujLiczbe,
  formatujProcent,
  formatujPrzeplywnosc,
  graniceWykresu,
  kluczSerii,
  limitCpuProcent,
  opisCpu,
  opisRam,
  opisSieci,
  osieY,
  podpisZakresu,
  procentLimitu,
  punktyWykresu,
  statystyki,
  statystykiCpu,
  statystykiRam,
  statystykiSieci,
  zHaszaWykresy,
  zakresZId,
  zapytaniaZbiorcze,
  zbudujUrlQueryRange,
  znajdzUsluge,
} from '../../panel/src/lib/wykresy.ts';

let sprawdzen = 0;
const bledy: string[] = [];

function ok(warunek: boolean, opis: string): void {
  sprawdzen += 1;
  if (!warunek) bledy.push(opis);
}

function rowne(a: unknown, b: unknown, opis: string): void {
  sprawdzen += 1;
  const sa = JSON.stringify(a);
  const sb = JSON.stringify(b);
  if (sa !== sb) bledy.push(`${opis} — jest ${sa}, ma być ${sb}`);
}

/* ---------------- zakresy i czas ---------------- */

rowne(zakresZId('1h').id, '1h', 'zakres: 1h rozpoznany');
rowne(zakresZId('7d').krok, 3600, 'zakres: 7d próbkowany co godzinę');
rowne(zakresZId('bzdura').id, ZAKRES_DOMYSLNY, 'zakres: nieznany → domyślny');
rowne(zakresZId(null).id, ZAKRES_DOMYSLNY, 'zakres: brak → domyślny');
rowne(zakresZId(undefined).id, ZAKRES_DOMYSLNY, 'zakres: undefined → domyślny');
rowne(ZAKRESY.length, 4, 'zakresy: cztery przyciski (1 h / 6 h / 24 h / 7 d)');
ok(
  ZAKRESY.every((z, i) => i === 0 || z.sekundy > (ZAKRESY[i - 1] as { sekundy: number }).sekundy),
  'zakresy: rosnące okna',
);
ok(
  ZAKRESY.every((z, i) => i === 0 || z.krok >= (ZAKRESY[i - 1] as { krok: number }).krok),
  'zakresy: dłuższe okno → rzadszy krok (tyle samo punktów)',
);
rowne(podpisZakresu(zakresZId('24h')), 'ostatnie 24 h', 'zakres: podpis do zdania');

// Stała chwila: 2026-09-22T18:45:00Z — wynik nie może zależeć od strefy maszyny.
const TERAZ = Date.UTC(2026, 8, 22, 18, 45, 0) / 1000;
const czas6h = etykietyCzasu(zakresZId('6h'), TERAZ);
rowne(czas6h.od, '12:45', 'czas: 6 h zaczyna się 12:45 UTC');
rowne(czas6h.do, '18:45', 'czas: 6 h kończy się 18:45 UTC');
const czas24h = etykietyCzasu(zakresZId('24h'), TERAZ);
rowne(czas24h.od, '21.09 18:45', 'czas: 24 h pokazuje datę (inaczej góra i dół osi to ta sama godzina)');
rowne(czas24h.do, '22.09 18:45', 'czas: koniec 24 h z datą');
rowne(etykietyCzasu(zakresZId('1h'), TERAZ).od, '17:45', 'czas: 1 h to same godziny');
const czas7d = etykietyCzasu(zakresZId('7d'), TERAZ);
rowne(czas7d.od, '15.09 18:45', 'czas: 7 d pokazuje datę i godzinę');
rowne(czas7d.do, '22.09 18:45', 'czas: koniec 7 d z datą');

/* ---------------- formatowanie ---------------- */

rowne(formatujLiczbe(3.842, 2), '3,84', 'liczby: przecinek dziesiętny');
rowne(formatujLiczbe(null), '—', 'liczby: brak wartości to kreska');
rowne(formatujProcent(3.842), '3,84%', 'liczby: procent z przecinkiem');
rowne(formatujProcent(Number.NaN), '—', 'liczby: NaN to kreska');
rowne(formatujBajty(0), '0 B', 'bajty: zero bez miejsc po przecinku');
rowne(formatujBajty(536870912), '512,0 MiB', 'bajty: limit 512 MiB czytelnie');
rowne(formatujBajty(82599936), '78,8 MiB', 'bajty: realny RAM usługi');
rowne(formatujBajty(1536), '1,5 KiB', 'bajty: kilobajty binarne');
rowne(formatujPrzeplywnosc(92.244), '92 B/s', 'sieć: bajty na sekundę');
rowne(formatujPrzeplywnosc(2048), '2,0 KiB/s', 'sieć: KiB na sekundę');
rowne(formatujPrzeplywnosc(null), '—', 'sieć: brak danych to kreska');
ok(czyLiczba(0) && !czyLiczba(null) && !czyLiczba(Number.POSITIVE_INFINITY), 'liczby: strażnik wartości');

/* ---------------- limity ---------------- */

rowne(procentLimitu(256, 512), 50, 'limit: połowa limitu');
rowne(procentLimitu(256, 0), null, 'limit: zero nie daje procentu (nie dzielimy przez zero)');
rowne(procentLimitu(256, null), null, 'limit: brak limitu → null');
rowne(procentLimitu(null, 512), null, 'limit: brak wartości → null');

rowne(opisCpu(3.84, null, 12.1), 'teraz 3,84% · maks. 12,10% · limit: brak w API', 'opis CPU bez limitu mówi o tym wprost');
// Limit CPU przychodzi z API w rdzeniach (NanoCPUs/1e9), a `cpu_percent` jest
// w procentach jednego rdzenia — stąd przelicznik ×100 i „% limitu".
rowne(limitCpuProcent(0.25), 25, 'limit CPU: 0,25 vCPU to 25% jednego rdzenia');
rowne(limitCpuProcent(null), null, 'limit CPU: brak limitu → null (nie zero)');
rowne(limitCpuProcent(0), null, 'limit CPU: zero traktujemy jak brak limitu');
rowne(opisCpu(12, 0.25), 'teraz 12,00% · limit 0,25 vCPU · 48,0% limitu', 'opis CPU: teraz vs limit i procent');
rowne(opisCpu(50, 0.5, 80), 'teraz 50,00% · maks. 80,00% · limit 0,50 vCPU · 100,0% limitu', 'opis CPU: maks. i limit razem');
ok(opisCpu(12, 0.25).includes('vCPU'), 'opis CPU: jednostka limitu jest nazwana');
ok(opisCpu(null, 0.25).includes('brak danych o zużyciu'), 'opis CPU: brak wartości „teraz" nie udaje procentu');
rowne(opisRam(82599936, 536870912, 90000000), '78,8 MiB / 512,0 MiB · 15,4% limitu · maks. 85,8 MiB', 'opis RAM: teraz/limit i procent');
ok(opisRam(1, null).includes('brak limitu'), 'opis RAM: bez limitu mówi o tym wprost');
ok(opisSieci(92.2, 127.1).includes('brak limitu'), 'opis sieci: sieć nie ma limitu');
ok(opisSieci(92.2, 127.1).startsWith('rx 92 B/s · tx 127 B/s'), 'opis sieci: najpierw rx, potem tx');

/* ---------------- statystyki ---------------- */

rowne(statystyki([]), { teraz: null, maks: null, minimum: null, srednia: null, ile: 0 }, 'statystyki: pusta seria');
rowne(
  statystyki([null, 2, undefined, 4]),
  { teraz: 4, maks: 4, minimum: 2, srednia: 3, ile: 2 },
  'statystyki: dziury w serii pomijane, „teraz" to ostatnia wartość',
);
rowne(statystyki([5, 5, 5]).srednia, 5, 'statystyki: średnia z płaskiej serii');

const stCpu = statystyki([1, 2, 3]);
ok(statystykiCpu(stCpu, null, 2.5).includes('teraz 2,50%'), 'statystyki CPU: „teraz" z API ma pierwszeństwo');
ok(statystykiCpu(stCpu).includes('teraz 3,00%'), 'statystyki CPU: bez API bierze ostatni punkt');
ok(statystykiCpu(stCpu).includes('limit: brak w API'), 'statystyki CPU: brak limitu nazwany wprost');
ok(
  statystykiCpu(stCpu, 0.25, 12).includes('limit 0,25 vCPU (48,0%)'),
  'statystyki CPU: limit z API i procent zużycia',
);
ok(
  statystykiCpu(statystyki([50]), 0.25).includes('limit 0,25 vCPU (200,0%)'),
  'statystyki CPU: przekroczenie limitu pokazujemy jako >100%',
);
ok(
  statystykiRam(statystyki([100]), 400, 200).includes('limit 400 B (50,0%)'),
  'statystyki RAM: limit i procent',
);
ok(statystykiRam(statystyki([100]), null).includes('brak w danych'), 'statystyki RAM: brak limitu → brak w danych');
ok(
  statystykiSieci(statystyki([10, 20]), statystyki([30, 40])).includes('maks. rx 20 B/s / tx 40 B/s'),
  'statystyki sieci: maksima obu kierunków',
);

/* ---------------- granice i osie ---------------- */

rowne(graniceWykresu([]), { min: 0, max: 1 }, 'granice: pusta seria → 0–1');
rowne(graniceWykresu([0, 0, 0], { odZera: true }), { min: 0, max: 1 }, 'granice: płaskie zero → 0–1');
rowne(graniceWykresu([5, 5, 5], { odZera: true }), { min: 0, max: 5.4 }, 'granice: płaska wartość z zapasem od zera');
rowne(graniceWykresu([10, 10]), { min: 9, max: 11 }, 'granice: płaska wartość bez zera rozciągana w obie strony');
const granice = graniceWykresu([50, 100], { odZera: true });
ok(granice.min === 0, 'granice: tryb „od zera" (CPU) trzyma dół osi w zerze');
ok(granice.max > 100, 'granice: zapas nad maksimum, żeby linia nie kleiła się do krawędzi');
const graniceOdDolu = graniceWykresu([50, 100]);
ok(graniceOdDolu.min < 50 && graniceOdDolu.min > 0, 'granice: RAM/sieć bez „od zera" schodzą pod minimum');

const ticki = osieY({ min: 0, max: 100 }, 4);
rowne(ticki, [100, 50, 0], 'osie: „ładne" wartości i kolejność od góry');
ok(
  ticki.every((v, i) => i === 0 || v < (ticki[i - 1] as number)),
  'osie: malejąco (rysowanie idzie wprost po indeksie)',
);
rowne(osieY({ min: 0, max: 0 }, 3), [0], 'osie: zerowy zakres nie dzieli przez zero');
// Realny przypadek z mocka: RAM 40–52 MiB przy limicie 512 MiB — „ładny" krok
// dawał jedną linię, więc góra i dół osi pokazywały tę samą liczbę.
const tickiRam = osieY({ min: 38 * 1024 * 1024, max: 546 * 1024 * 1024 }, 3);
rowne(tickiRam.length, 3, 'osie: przy zbyt małej liczbie „ładnych" ticków dzielimy zakres równo');
rowne(osieY({ min: 0, max: 3200 }, 4).length, 4, 'osie: sieć o małym zakresie dostaje pełny zestaw linii');
rowne(
  new Set(osieY({ min: 38 * 1024 * 1024, max: 546 * 1024 * 1024 }, 4)).size,
  4,
  'osie: cztery różne wartości (środek nie zlewa się z dołem)',
);
ok(tickiRam[0] !== tickiRam[tickiRam.length - 1], 'osie: góra i dół osi to różne wartości');
ok(
  tickiRam.every((v, i) => i === 0 || v < (tickiRam[i - 1] as number)),
  'osie: fallback też jest malejąco',
);

/* ---------------- punkty linii ---------------- */

rowne(punktyWykresu([], 100, 50, { min: 0, max: 1 }), '', 'punkty: pusta seria → brak linii');
const jeden = punktyWykresu([7], 100, 50, { min: 0, max: 10 });
rowne(jeden.split(' ').length, 2, 'punkty: pojedynczy pomiar rysujemy jako linię poziomą');
// wysokość 50, margines 4 → środek użytecznej wysokości to 4 + (50−8)/2 = 25
ok(jeden.split(' ')[0]?.endsWith(',25.00') === true, 'punkty: linia pozioma w połowie wysokości');

const linia = punktyWykresu([1, 2, 3], 100, 50, { min: 0, max: 3 });
const pary = linia.split(' ').map((para) => para.split(',').map(Number));
rowne(pary.length, 3, 'punkty: tyle par, ile pomiarów');
rowne(pary[0]?.[0], 0, 'punkty: pierwszy pomiar przy lewej krawędzi');
rowne(pary[2]?.[0], 100, 'punkty: ostatni pomiar przy prawej krawędzi');
ok(
  (pary[0]?.[1] as number) > (pary[1]?.[1] as number) &&
    (pary[1]?.[1] as number) > (pary[2]?.[1] as number),
  'punkty: wyższa wartość rysowana wyżej (oś Y odwrócona)',
);
ok(
  pary.every(([, y]) => (y as number) >= 4 && (y as number) <= 46),
  'punkty: margines 4 px trzyma linię w ramce (bez obcinania po krawędziach)',
);
const pozaZakresem = punktyWykresu([-5, 50], 100, 50, { min: 0, max: 10 });
ok(
  pozaZakresem
    .split(' ')
    .map((p) => Number(p.split(',')[1]))
    .every((y) => y >= 4 && y <= 46),
  'punkty: wartości poza granicami przycinane do ramki (bez wyjścia z SVG)',
);

/* ---------------- zapytania do Prometheusa ---------------- */

const zapytania = zapytaniaZbiorcze();
rowne(zapytania.length, 5, 'zapytania: pięć metryk na cały widok');
rowne(
  zapytania.map((z) => z.id),
  ['cpu', 'ram', 'limit', 'rx', 'tx'],
  'zapytania: kolejność i identyfikatory',
);
ok(
  zapytania.every((z) => z.expr.includes('by (stack, service)')),
  'zapytania: jedno zapytanie na metrykę dla wszystkich usług (nie per usługa)',
);
ok(zapytania.some((z) => z.id === 'limit' && z.expr.includes('memory_limit_bytes')), 'zapytania: limit RAM z metryki');
ok(
  zapytania.some((z) => z.id === 'rx' && z.expr.startsWith('sum by (stack, service) (rate(')),
  'zapytania: sieć liczona jako rate (B/s), nie licznik narastający',
);
rowne(kluczSerii('ventiplan-prod', 'api'), 'ventiplan-prod/api', 'klucz serii: stack/usługa');

const url = zbudujUrlQueryRange('sum(up{a="b"})', zakresZId('24h'), 1_000_000);
ok(url.startsWith('/prometheus/api/v1/query_range?'), 'url: ścieżka przez proxy panelu (ten sam origin)');
const parametry = new URLSearchParams(url.split('?')[1]);
rowne(parametry.get('query'), 'sum(up{a="b"})', 'url: zapytanie zakodowane i odzyskane bez zmian');
rowne(parametry.get('step'), '900', 'url: krok zależy od zakresu (24 h → 900 s)');
rowne(Number(parametry.get('end')), 1_000_000, 'url: koniec = teraz');
rowne(Number(parametry.get('start')), 1_000_000 - 24 * 3600, 'url: początek = teraz − zakres');

/* ---------------- trasa w haszu ---------------- */

ok(czyTrasaWykresow('#/wykresy'), 'trasa: lista wykresów');
ok(czyTrasaWykresow('#/wykresy/ventiplan-prod/api'), 'trasa: szczegóły usługi');
ok(czyTrasaWykresow('#/wykresy?zakres=1h'), 'trasa: lista z zakresem');
ok(!czyTrasaWykresow('#/'), 'trasa: widok stanu to nie wykresy');
ok(!czyTrasaWykresow('#/tool/grafana'), 'trasa: podgląd narzędzia to nie wykresy');
ok(!czyTrasaWykresow('#/wykresyx'), 'trasa: podobna nazwa nie łapie się na wykresy');

rowne(zHaszaWykresy('#/wykresy'), { usluga: null, zakres: ZAKRES_DOMYSLNY }, 'hasz: lista → brak usługi, domyślny zakres');
rowne(
  zHaszaWykresy('#/wykresy/ventiplan-prod%2Fapi?zakres=24h'),
  { usluga: 'ventiplan-prod/api', zakres: '24h' },
  'hasz: usługa z ukośnikiem i zakres z parametru',
);
rowne(zHaszaWykresy('#/wykresy/api?zakres=bzdura').zakres, ZAKRES_DOMYSLNY, 'hasz: nieznany zakres → domyślny');
rowne(zHaszaWykresy('#/wykresy/%E4%B8%AD').usluga, '中', 'hasz: nazwa z procentami dekodowana');
rowne(zHaszaWykresy('#/wykresy/').usluga, null, 'hasz: końcowy ukośnik to wciąż lista');

rowne(doHaszaWykresow(null), '#/wykresy', 'hasz: lista bez zakresu (domyślny się nie zaśmieca)');
rowne(doHaszaWykresow('api', '6h'), '#/wykresy/api', 'hasz: domyślny zakres nie trafia do adresu');
rowne(doHaszaWykresow('api', '1h'), '#/wykresy/api?zakres=1h', 'hasz: inny zakres trafia do adresu');
rowne(
  zHaszaWykresy(doHaszaWykresow('ventiplan-prod/api', '7d')),
  { usluga: 'ventiplan-prod/api', zakres: '7d' },
  'hasz: zapis i odczyt dają to samo (link do wysłania)',
);

/* ---------------- wybór usługi z trasy ---------------- */

const uslugi = [
  { stack: 'ventiplan-prod', usluga: { name: 'api', full_name: 'ventiplan-prod_api' } },
  { stack: 'bugsink', usluga: { name: 'db', full_name: 'bugsink_db' } },
  { stack: 'star-sign', usluga: { name: 'db', full_name: 'star-sign_db' } },
];
rowne(znajdzUsluge(uslugi, 'ventiplan-prod/api')?.stack, 'ventiplan-prod', 'wybór: po „stack/usługa"');
rowne(znajdzUsluge(uslugi, 'bugsink_db')?.usluga.name, 'db', 'wybór: po pełnej nazwie z API');
rowne(znajdzUsluge(uslugi, 'api')?.stack, 'ventiplan-prod', 'wybór: po jednoznacznej nazwie usługi');
rowne(znajdzUsluge(uslugi, 'db'), null, 'wybór: powtarzalna nazwa bez stacka jest niejednoznaczna → null');
rowne(znajdzUsluge(uslugi, 'nie-ma-takiej'), null, 'wybór: nieznana usługa → null');
rowne(znajdzUsluge(uslugi, null), null, 'wybór: brak segmentu → null');

/* ---------------- wynik ---------------- */

if (bledy.length > 0) {
  console.error(`✗ wykresy panelu: ${bledy.length} z ${sprawdzen} sprawdzeń nie przeszło`);
  for (const blad of bledy.slice(0, 20)) console.error(`   - ${blad}`);
  process.exit(1);
}

console.log(`✓ wykresy panelu: ${sprawdzen} sprawdzeń OK`);
