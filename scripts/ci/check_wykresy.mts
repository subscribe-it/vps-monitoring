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
  ODSWIEZANIA,
  ODSWIEZANIE_DOMYSLNE,
  PODMIOT_WSZYSTKIE,
  WYKRES_LINIE,
  WYKRES_MARGINES,
  WYKRES_SZEROKOSC,
  WYKRES_WYSOKOSC,
  ZAKRESY,
  ZAKRES_DOMYSLNY,
  czyLiczba,
  czyOdswiezac,
  czyTrasaWykresow,
  doHaszaWykresow,
  dokladnoscOsi,
  etykietyCzasu,
  etykietyOsiX,
  etykietaPunktu,
  formatujBajty,
  formatujLiczbe,
  formatujProcent,
  formatujPrzeplywnosc,
  graniceWykresu,
  indeksNajblizszy,
  kluczSerii,
  limitCpuProcent,
  opisCpu,
  opisDysku,
  opisRam,
  opisSieci,
  odswiezanieZId,
  osieY,
  podpisOdswiezania,
  podmiotEtykieta,
  podpisZakresu,
  procentLimitu,
  punktyWykresu,
  statystyki,
  statystykiCpu,
  statystykiDysku,
  statystykiRam,
  statystykiSieci,
  tytulWykresu,
  wierszeTooltipa,
  zHaszaWykresy,
  zapytaniaVps,
  zakresZId,
  zapytaniaZbiorcze,
  zapytaniaTop,
  zapytanieTop,
  zbudujUrlQueryInstant,
  zbudujUrlQueryRange,
  znajdzUsluge,
  formatujWartoscTop,
  metrykaTopZId,
  ograniczTop,
  parsujTop,
  szerokoscSlupka,
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
rowne(graniceWykresu([5, 5, 5], { odZera: true }), { min: 4.5, max: 5.5 }, 'granice: płaska wartość rozciągana w obie strony (kotwica w zerze tylko przy danych przy zerze)');
rowne(graniceWykresu([10, 10]), { min: 9, max: 11 }, 'granice: płaska wartość bez zera rozciągana w obie strony');
// Próg kotwicy: minimum ≤ 25% maksimum (patrz `graniceWykresu`).
const granice = graniceWykresu([10, 100], { odZera: true });
ok(granice.min === 0, 'granice: seria schodząca blisko zera zostaje kotwiczona w zerze');
const graniceWysokieCpu = graniceWykresu([24, 30, 36], { odZera: true });
ok(
  graniceWysokieCpu.min > 0,
  'granice: CPU 24-36% NIE jest kotwiczone w zerze (inaczej linia ściska się do góry wykresu)',
);
ok(granice.max > 100, 'granice: zapas nad maksimum, żeby linia nie kleiła się do krawędzi');
const graniceOdDolu = graniceWykresu([50, 100]);
ok(graniceOdDolu.min < 50 && graniceOdDolu.min > 0, 'granice: RAM/sieć bez „od zera" schodzą pod minimum');

const ticki = osieY({ min: 0, max: 100 }, 5);
rowne(ticki, [100, 75, 50, 25, 0], 'osie: „ładne" wartości i kolejność od góry');
ok(
  ticki.every((v, i) => i === 0 || v < (ticki[i - 1] as number)),
  'osie: malejąco (rysowanie idzie wprost po indeksie)',
);
// Wymaganie użytkownika: 4–6 linii i etykiet, a nie trzy przypadkowe liczby.
ok(
  ticki.length >= 4 && ticki.length <= 6,
  'osie: gęstość 4–6 linii na każdym zakresie',
);
rowne(osieY({ min: 0, max: 0 }, 5), [0], 'osie: zerowy zakres nie dzieli przez zero');
// Realny przypadek z mocka: RAM 40–52 MiB przy limicie 512 MiB — „ładny" krok
// dawał za mało linii, więc równy podział musi dać pełne 5.
const tickiRam = osieY({ min: 38 * 1024 * 1024, max: 546 * 1024 * 1024 }, 5);
rowne(tickiRam.length, 5, 'osie: przy zbyt małej liczbie „ładnych" ticków dzielimy zakres równo');
rowne(
  new Set(osieY({ min: 0, max: 3200 }, 5)).size,
  osieY({ min: 0, max: 3200 }, 5).length,
  'osie: wartości są unikalne (żadna linia nie leży na drugiej)',
);
rowne(
  new Set(osieY({ min: 38 * 1024 * 1024, max: 546 * 1024 * 1024 }, 5)).size,
  5,
  'osie: pięć różnych wartości (środek nie zlewa się z dołem)',
);
ok(tickiRam[0] !== tickiRam[tickiRam.length - 1], 'osie: góra i dół osi to różne wartości');
ok(
  tickiRam.every((v, i) => i === 0 || v < (tickiRam[i - 1] as number)),
  'osie: fallback też jest malejąco',
);
// Kotwica w zerze tylko wtedy, gdy dane naprawdę siedzą przy zerze — inaczej
// linia ściska się do góry wykresu (zgłoszenie: „wykresy się rozjeżdżają”).
const cpuGranice = graniceWykresu([24, 30, 36], { odZera: true });
ok(cpuGranice.min > 0, 'granice: CPU 24–36% nie jest kotwiczone w zerze (zero tylko przy danych przy zerze)');
const siecGranice = graniceWykresu([0, 120, 900], { odZera: true });
rowne(siecGranice.min, 0, 'granice: sieć z wartościami przy zerze zostaje na zerze');

/* ---------------- etykiety osi czasu ---------------- */

const os1h = etykietyOsiX(zakresZId('1h'), 1_700_000_000, 1_700_003_600, 605);
ok(os1h.length >= 2 && os1h.length <= 6, 'osie X: 2–6 etykiet zależnie od szerokości');
ok(
  os1h.every((e, i) => i === 0 || e.udzial > (os1h[i - 1] as { udzial: number }).udzial),
  'osie X: rosnąco po szerokości',
);
rowne(os1h[0]?.udzial, 0, 'osie X: pierwsza etykieta przy lewej krawędzi');
rowne(os1h[os1h.length - 1]?.udzial, 1, 'osie X: ostatnia etykieta przy prawej krawędzi');
ok(
  etykietyOsiX(zakresZId('7d'), 1_700_000_000, 1_700_600_000, 605)[0]!.tekst.includes('.'),
  'osie X: przy 7 d etykieta pokazuje datę, nie samą godzinę',
);
ok(
  !etykietyOsiX(zakresZId('1h'), 1_700_000_000, 1_700_003_600, 605)[0]!.tekst.includes('.'),
  'osie X: przy 1 h etykieta to sama godzina',
);
ok(
  etykietyOsiX(zakresZId('1h'), 1_700_000_000, 1_700_003_600, 1200).length >=
    etykietyOsiX(zakresZId('1h'), 1_700_000_000, 1_700_003_600, 500).length,
  'osie X: szersza karta mieści co najmniej tyle samo etykiet',
);
rowne(etykietyOsiX(zakresZId('1h'), 0, 0, 605).length, 0, 'osie X: brak danych → brak etykiet');


/* ---------------- dokładność etykiet osi Y ---------------- */

rowne(dokladnoscOsi(0.5), 1, 'dokładność osi: krok 0,5 wymaga jednego miejsca (25,5% vs 26%)');
rowne(dokladnoscOsi(0.05), 2, 'dokładność osi: krok 0,05 wymaga dwóch miejsc');
rowne(dokladnoscOsi(5), 0, 'dokładność osi: krok całkowity bez miejsc po przecinku');
rowne(dokladnoscOsi(0), 0, 'dokładność osi: zerowy krok nie wywala formatowania');
// Krok „ładny" dobrany do widełek 4–6 linii (zgłoszenie: osie bez sensu).
const tickiCpu = osieY({ min: 22.7, max: 27.3 }, 5);
ok(tickiCpu.length >= 4 && tickiCpu.length <= 6, 'osie: wąski zakres CPU nadal ma 4–6 linii');
const krokCpu = Math.abs((tickiCpu[0] as number) - (tickiCpu[1] as number));
ok([0.5, 1, 2, 2.5, 5].some((r) => Math.abs(krokCpu / r - Math.round(krokCpu / r)) < 1e-9),
   'osie: krok jest „ładny" (1, 2, 2,5, 5 × 10ⁿ), a nie 0,04');
const tekstyCpu = tickiCpu.map((v) => formatujProcent(v, dokladnoscOsi(krokCpu)));
rowne(new Set(tekstyCpu).size, tekstyCpu.length, 'osie: etykiety przy wąskim zakresie są unikalne');

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
rowne(zapytania.length, 7, 'zapytania: siedem metryk na cały widok');
rowne(
  zapytania.map((z) => z.id),
  ['cpu', 'ram', 'limit', 'rx', 'tx', 'io_r', 'io_w'],
  'zapytania: kolejność i identyfikatory',
);
ok(
  zapytania.some((z) => z.id === 'io_r' && z.expr.includes('block_read_bytes_total')),
  'zapytania: I/O dysku — odczyt z licznika blokowego',
);
ok(
  zapytania.some((z) => z.id === 'io_w' && z.expr.includes('rate(swarm_container_block_write_bytes_total')),
  'zapytania: I/O dysku — zapis liczony jako rate (B/s), nie licznik narastający',
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

rowne(
  zHaszaWykresy('#/wykresy'),
  { podmiot: null, zakres: ZAKRES_DOMYSLNY, odswiez: ODSWIEZANIE_DOMYSLNE },
  'hasz: lista → cały VPS, domyślny zakres i odświeżanie',
);
rowne(
  zHaszaWykresy('#/wykresy/ventiplan-prod%2Fapi?zakres=24h'),
  { podmiot: 'ventiplan-prod/api', zakres: '24h', odswiez: ODSWIEZANIE_DOMYSLNE },
  'hasz: usługa z ukośnikiem i zakres z parametru',
);
rowne(zHaszaWykresy('#/wykresy/api?zakres=bzdura').zakres, ZAKRES_DOMYSLNY, 'hasz: nieznany zakres → domyślny');
rowne(zHaszaWykresy('#/wykresy/%E4%B8%AD').podmiot, '中', 'hasz: nazwa z procentami dekodowana');
rowne(zHaszaWykresy('#/wykresy/').podmiot, null, 'hasz: końcowy ukośnik to wciąż lista');

rowne(doHaszaWykresow(null), '#/wykresy', 'hasz: lista bez zakresu (domyślny się nie zaśmieca)');
rowne(doHaszaWykresow('api', '6h'), '#/wykresy/api', 'hasz: domyślny zakres nie trafia do adresu');
rowne(doHaszaWykresow('api', '1h'), '#/wykresy/api?zakres=1h', 'hasz: inny zakres trafia do adresu');
rowne(
  zHaszaWykresy(doHaszaWykresow('ventiplan-prod/api', '7d')),
  { podmiot: 'ventiplan-prod/api', zakres: '7d', odswiez: ODSWIEZANIE_DOMYSLNE },
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

/* ---------------- dysk (I/O) ---------------- */

ok(opisDysku(2048, 1024, 4096).includes('odczyt'), 'dysk: podpis odczytu');
ok(opisDysku(2048, 1024, 4096).includes('zapis'), 'dysk: podpis zapisu');
ok(opisDysku(2048, 1024, 4096).includes('/s'), 'dysk: jednostka na sekundę (rate, nie licznik)');
ok(opisDysku(null, null, null).includes('—'), 'dysk: brak danych → kreska, nie zero');
rowne(opisDysku(1024, null, null).includes('maks.'), false, 'dysk: bez maksimum nie zmyślamy podpisu');
ok(
  statystykiDysku(statystyki([1, 2, 3]), statystyki([4, 5, 6])).includes('średnia'),
  'dysk: statystyki mają średnią',
);

/* ---------------- ranking „Top 10 usług" ---------------- */

const rankingi = zapytaniaTop();
rowne(rankingi.length, 3, 'top: trzy metryki przełącznika (CPU / RAM / sieć)');
rowne(
  rankingi.map((r) => r.id),
  ['cpu', 'ram', 'siec'],
  'top: kolejność i identyfikatory przełącznika',
);
ok(
  rankingi.every((r) => r.expr.startsWith('topk(10, ')),
  'top: dziesięć pozycji liczy Prometheus, nie panel',
);
ok(
  rankingi.every((r) => r.expr.includes('by (stack, service)')),
  'top: jedno zapytanie na metrykę dla wszystkich usług',
);
ok(
  (rankingi.find((r) => r.id === 'siec')?.expr ?? '').includes('network_receive_bytes_total')
    && (rankingi.find((r) => r.id === 'siec')?.expr ?? '').includes('network_transmit_bytes_total'),
  'top: sieć to rx + tx (oba kierunki w jednym rankingu)',
);
rowne(zapytanieTop('ram').jednostka, 'bajty', 'top: jednostka RAM to bajty');
rowne(zapytanieTop('siec').jednostka, 'przeplywnosc', 'top: jednostka sieci to przepustowość');
rowne(metrykaTopZId('bzdura'), 'cpu', 'top: nieznana metryka → CPU');
rowne(metrykaTopZId(null), 'cpu', 'top: brak metryki → CPU');
rowne(formatujWartoscTop('cpu', 12.34), '12,3%', 'top: formatowanie procentu');
ok(formatujWartoscTop('ram', 536_870_912).includes('MiB'), 'top: formatowanie bajtów');
ok(formatujWartoscTop('siec', 2048).includes('/s'), 'top: formatowanie przepustowości na sekundę');
rowne(formatujWartoscTop('cpu', null), '—', 'top: brak wartości → kreska');

rowne(szerokoscSlupka(50, 100), 50, 'słupek: połowa wartości = połowa szerokości');
rowne(szerokoscSlupka(100, 100), 100, 'słupek: maksimum = pełna szerokość');
rowne(szerokoscSlupka(0, 100), 0, 'słupek: zero = brak słupka (nie kłamie o zużyciu)');
rowne(szerokoscSlupka(0.001, 1000), 2, 'słupek: wartość śladowa ma minimalną szerokość');
rowne(szerokoscSlupka(1000, 0), 0, 'słupek: brak maksimum → brak słupka (bez dzielenia przez zero)');
rowne(szerokoscSlupka(null, 100), 0, 'słupek: brak wartości → brak słupka');

const odpTop = {
  data: {
    result: [
      { metric: { stack: 'a', service: 'api' }, value: [1758567000, '4'] },
      { metric: { stack: 'b', service: 'db' }, value: [1758567000, '9'] },
      { metric: { service: 'bez-stacka' }, value: [1758567000, '7'] },
      { metric: { stack: 'c', service: 'x' } },
      'śmieć',
    ],
  },
};
const pozycje = parsujTop(odpTop);
rowne(pozycje.length, 2, 'top: serie bez kompletu etykiet pominięte');
rowne(pozycje[0]?.usluga, 'db', 'top: sortowanie malejąco po wartości');
rowne(pozycje[0]?.klucz, 'b/db', 'top: klucz serii zgodny z mapą przebiegów');
const instant = zbudujUrlQueryInstant('topk(10, up)', 1_700_000_000);
ok(instant.startsWith('/prometheus/api/v1/query?'), 'top: ranking pyta o migawkę (instant), nie o przebieg');
rowne(new URLSearchParams(instant.split('?')[1]).get('time'), '1700000000', 'top: czas migawki przekazany');
ok(
  parsujTop({ data: { result: [{ metric: { stack: 'a', service: 'b' }, values: [[1, '1'], [2, '5']] }] } })[0]
    ?.wartosc === 5,
  'top: macierz z query_range też działa (bierzemy ostatni punkt)',
);
rowne(parsujTop(null), [], 'top: null → pusta lista');
rowne(ograniczTop(pozycje, 10).length, 2, 'top: lista krótsza niż limit zostaje bez zmian');
rowne(
  ograniczTop(
    Array.from({ length: 50 }, (_, i) => ({ stack: 's', usluga: `u${i}`, klucz: `s/u${i}`, wartosc: 50 - i })),
    10,
  ).length,
  10,
  'top: lista dłuższa niż limit jest przycinana do 10',
);
rowne(ograniczTop(pozycje, 0).length, 0, 'top: limit 0 daje pustą listę');
rowne(parsujTop({ data: { result: 'bzdura' } }), [], 'top: zły kształt → pusta lista');


/* ---------------- odświeżanie (5 s / 10 s / 30 s / wyłączone) ---------------- */

rowne(ODSWIEZANIA.length, 4, 'odświeżanie: cztery opcje');
rowne(odswiezanieZId('5s').ms, 5000, 'odświeżanie: 5 s → 5000 ms');
rowne(odswiezanieZId('30s').ms, 30000, 'odświeżanie: 30 s → 30000 ms');
rowne(odswiezanieZId('off').ms, null, 'odświeżanie: wyłączone nie ma interwału');
rowne(odswiezanieZId('bzdura').id, ODSWIEZANIE_DOMYSLNE, 'odświeżanie: nieznane → domyślne 10 s');
rowne(odswiezanieZId(null).id, ODSWIEZANIE_DOMYSLNE, 'odświeżanie: brak → domyślne 10 s');
ok(czyOdswiezac(odswiezanieZId('10s')), 'odświeżanie: 10 s ustawia timer');
ok(!czyOdswiezac(odswiezanieZId('off')), 'odświeżanie: „wyłączone" nie ustawia timera (zero zapytań w tle)');
rowne(podpisOdswiezania(odswiezanieZId('5s')), 'dane co 5 s', 'odświeżanie: podpis z interwałem');
rowne(
  podpisOdswiezania(odswiezanieZId('off')),
  'odświeżanie wyłączone',
  'odświeżanie: podpis dla „wyłączone"',
);

/* ---------------- trasa: podmiot + zakres + odświeżanie ---------------- */

const trasaVps = zHaszaWykresy('#/wykresy');
rowne(trasaVps.podmiot, null, 'trasa: #/wykresy to cały VPS');
rowne(trasaVps.odswiez, ODSWIEZANIE_DOMYSLNE, 'trasa: bez parametru odświeżanie domyślne');
rowne(zHaszaWykresy('#/wykresy/wszystkie').podmiot, PODMIOT_WSZYSTKIE, 'trasa: tryb „wszystkie usługi"');
rowne(
  zHaszaWykresy('#/wykresy/ventiplan-prod%2Fapi?zakres=24h&odswiez=5s').podmiot,
  'ventiplan-prod/api',
  'trasa: usługa z ukośnikiem wraca z hasza',
);
rowne(zHaszaWykresy('#/wykresy/ventiplan-prod%2Fapi?zakres=24h&odswiez=5s').odswiez, '5s', 'trasa: odświeżanie z hasza');
rowne(doHaszaWykresow(null), '#/wykresy', 'trasa: domyślny adres jest krótki (bez parametrów)');
rowne(
  doHaszaWykresow('ventiplan-prod/api', '24h', '5s'),
  '#/wykresy/ventiplan-prod%2Fapi?zakres=24h&odswiez=5s',
  'trasa: pełny adres z parametrami',
);
rowne(
  doHaszaWykresow('bugsink/db', ZAKRES_DOMYSLNY, 'off'),
  '#/wykresy/bugsink%2Fdb?odswiez=off',
  'trasa: pomijamy tylko wartości domyślne',
);
rowne(
  zHaszaWykresy(doHaszaWykresow('star-sign/web', '7d', '30s')).podmiot,
  'star-sign/web',
  'trasa: zapis i odczyt są spójne',
);

/* ---------------- tytuły i podmiot ---------------- */

rowne(podmiotEtykieta(null), 'cały VPS', 'podmiot: null → „cały VPS"');
rowne(podmiotEtykieta(PODMIOT_WSZYSTKIE), 'wszystkie usługi', 'podmiot: tryb zbiorczy');
rowne(podmiotEtykieta('ventiplan-prod/api'), 'api', 'podmiot: nazwa usługi bez stacka');
rowne(tytulWykresu('CPU', null), 'CPU — cały VPS', 'tytuł: CPU całego VPS-a');
rowne(tytulWykresu('RAM', 'jpolski/db'), 'RAM — db', 'tytuł: RAM wskazanej usługi');
rowne(
  tytulWykresu('Sieć (rx / tx)', 'jpolski/na6_pl_prod_wordpress'),
  'Sieć (rx / tx) — na6_pl_prod_wordpress',
  'tytuł: nazwa serii zostaje, nazwa usługi bez stacka',
);

/* ---------------- geometria i tooltip ---------------- */

rowne(WYKRES_SZEROKOSC, 800, 'geometria: karta wykresu ma maks. 800 px szerokości');
ok(WYKRES_WYSOKOSC >= 220 && WYKRES_WYSOKOSC <= 260, 'geometria: wysokość wykresu w widełkach 220–260 px');
rowne(WYKRES_LINIE, 5, 'geometria: pięć linii siatki = pięć etykiet osi Y (widełki 4–6)');
rowne(WYKRES_MARGINES, 12, 'geometria: margines rysunku');
rowne(indeksNajblizszy(0, 800, 10), 0, 'tooltip: lewa krawędź → pierwszy punkt');
rowne(indeksNajblizszy(800, 800, 10), 9, 'tooltip: prawa krawędź → ostatni punkt');
rowne(indeksNajblizszy(400, 800, 11), 5, 'tooltip: środek → punkt środkowy');
rowne(indeksNajblizszy(-50, 800, 10), 0, 'tooltip: poza wykresem z lewej przycinamy do pierwszego');
rowne(indeksNajblizszy(900, 800, 10), 9, 'tooltip: poza wykresem z prawej przycinamy do ostatniego');
rowne(indeksNajblizszy(100, 800, 0), null, 'tooltip: brak punktów → brak indeksu');
rowne(indeksNajblizszy(Number.NaN, 800, 10), null, 'tooltip: NaN nie wywala się');
rowne(indeksNajblizszy(500, 800, 1), 0, 'tooltip: jedna wartość → punkt zerowy');

const zakres1h = zakresZId('1h');
const zakres24h = zakresZId('24h');
const zakres7d = zakresZId('7d');
const chwila = Date.UTC(2026, 8, 22, 21, 6, 30) / 1000;
ok(etykietaPunktu(chwila, zakres1h).includes(':30'), 'tooltip: 1 h pokazuje sekundy');
ok(etykietaPunktu(chwila, zakres1h).endsWith('UTC'), 'tooltip: czas zawsze w UTC');
rowne(etykietaPunktu(chwila, zakres24h), '21:06 UTC', 'tooltip: 24 h bez daty (godzina wystarcza)');
ok(etykietaPunktu(chwila, zakres7d).startsWith('22.09'), 'tooltip: 7 d z datą (inaczej „21:06" nic nie mówi)');

const wiersze = wierszeTooltipa(
  [
    { nazwa: 'rx (odbiór)', wartosci: [1024, 2048] },
    { nazwa: 'tx (wysyłka)', wartosci: [512, null] },
  ],
  1,
  (v) => (v === null ? '—' : `${v} B/s`),
);
rowne(wiersze.length, 2, 'tooltip: tyle wierszy, ile serii');
rowne(wiersze[0]?.nazwa, 'rx (odbiór)', 'tooltip: nazwa serii jest pokazywana');
rowne(wiersze[0]?.tekst, '2048 B/s', 'tooltip: wartość w jednostce wykresu');
rowne(wiersze[1]?.tekst, '—', 'tooltip: brak punktu pokazujemy kreską, nie zerem');

/* ---------------- zapytania VPS-a ---------------- */

const vps = zapytaniaVps();
rowne(vps.length, 9, 'VPS: dziewięć zapytań (pięć wykresów + cztery serie pomocnicze)');
ok(new Set(vps.map((z) => z.id)).size === vps.length, 'VPS: identyfikatory zapytań są unikalne');
ok(vps.every((z) => z.expr.trim().length > 0), 'VPS: każde zapytanie ma treść');
ok(vps.every((z) => z.expr.includes('node_')), 'VPS: wszystko opiera się na metrykach node_*');
ok(
  vps.some((z) => z.expr.includes('node_cpu_seconds_total')),
  'VPS: CPU z node_cpu_seconds_total',
);
ok(vps.some((z) => z.expr.includes('node_memory_MemAvailable_bytes')), 'VPS: RAM z node_memory_*');
ok(vps.some((z) => z.expr.includes('node_load1')), 'VPS: obciążenie z node_load1');
ok(
  vps.some((z) => z.expr.includes('node_network_receive_bytes_total') && z.expr.includes('device!~')),
  'VPS: sieć pomija interfejsy wirtualne (inaczej liczymy podwójnie)',
);
ok(
  vps.some((z) => z.expr.includes('node_filesystem_size_bytes') && z.expr.includes('mountpoint="/"')),
  'VPS: dysk liczy partycję główną',
);

/* ---------------- wynik ---------------- */

if (bledy.length > 0) {
  console.error(`✗ wykresy panelu: ${bledy.length} z ${sprawdzen} sprawdzeń nie przeszło`);
  for (const blad of bledy.slice(0, 20)) console.error(`   - ${blad}`);
  process.exit(1);
}

console.log(`✓ wykresy panelu: ${sprawdzen} sprawdzeń OK`);
