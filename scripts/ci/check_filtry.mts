/**
 * Testy czystej logiki panelu (`panel/src/lib/filtry.ts`) — bez przeglądarki
 * i bez nowych zależności.
 *
 * Uruchamiane Node'em 23.6+ (type stripping wbudowany; w CI jest Node 24).
 * Powód istnienia: filtrowanie, sortowanie i hasz to reguły, których nie da
 * się sensownie „obejrzeć" — a pomyłka w nich cicho pokazuje zły stan
 * produkcji (np. filtr „problemy" gubiący `unknown`).
 *
 *   node scripts/ci/check_filtry.ts
 */

import {
  PUSTY_FILTR,
  czyAktywny,
  doHasza,
  filtrujAlerty,
  filtrujCertyfikaty,
  filtrujEndpointy,
  filtrujLogowania,
  kluczFokusa,
  normalizuj,
  opisFiltra,
  pasujeStan,
  pasujeTekst,
  przygotujStacki,
  punktySparkline,
  rozbijFokus,
  sortujUslugi,
  uslugiDoCsv,
  zakresSparkline,
  zHasza,
  zmianyMiedzy,
  type Filtr,
  type Uslugowe,
} from '../../panel/src/lib/filtry.ts';

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

/* ---------------- dane testowe ---------------- */

function usluga(czesci: Partial<Uslugowe> & { name: string }): Uslugowe {
  return {
    state: 'ok',
    full_name: null,
    desired: 1,
    running: 1,
    image: null,
    cpu_percent: 0,
    mem_bytes: 0,
    restarts_1h: 0,
    replicas_text: null,
    ...czesci,
  };
}

const stacki = [
  {
    name: 'monitoring',
    state: 'warning',
    services_running: 2,
    services_desired: 2,
    services: [
      usluga({ name: 'panel', full_name: 'monitoring_panel', cpu_percent: 1.5, mem_bytes: 30_000_000, image: 'ghcr.io/subscribe-it/vps-monitoring-panel:main' }),
      usluga({ name: 'grafana', state: 'critical', cpu_percent: 42, mem_bytes: 400_000_000, restarts_1h: 3, image: 'grafana/grafana:13' }),
    ],
  },
  {
    name: 'ventiplan-prod',
    state: 'ok',
    services_running: 1,
    services_desired: 2,
    services: [
      usluga({ name: 'db', state: 'ok', desired: 2, running: 1, cpu_percent: 9, mem_bytes: 90_000_000, image: 'postgres:17-alpine' }),
    ],
  },
];

const filtr = (czesci: Partial<Filtr>): Filtr => ({ ...PUSTY_FILTR, ...czesci });

/* ---------------- normalizacja i dopasowanie ---------------- */

rowne(normalizuj('Usługa Łódź'), 'usluga lodz', 'normalizacja: diakrytyki i wielkość liter');
rowne(normalizuj('  Wiele   spacji  '), 'wiele spacji', 'normalizacja: spacje');
ok(pasujeTekst('', 'cokolwiek') === true, 'puste zapytanie pasuje do wszystkiego');
ok(pasujeTekst('grafana', 'monitoring_grafana') === true, 'trafienie w podłańcuch');
ok(pasujeTekst('panel grafana', 'monitoring_panel', 'grafana') === true, 'wiele słów = AND');
ok(pasujeTekst('nginx', 'monitoring_panel', 'grafana') === false, 'brak trafienia');
ok(pasujeTekst('usluga', 'Usługa') === true, 'szukanie bez polskich znaków');
ok(pasujeTekst(null as unknown as string, 'x') === true, 'null jako zapytanie nie wywala');

ok(pasujeStan('warning', 'problemy') === true, 'problemy: warning');
ok(pasujeStan('unknown', 'problemy') === true, 'problemy: unknown (brak danych też wymaga spojrzenia)');
ok(pasujeStan('ok', 'problemy') === false, 'problemy: ok nie należy');
ok(pasujeStan('disabled', 'problemy') === false, 'problemy: disabled nie należy');
ok(pasujeStan('critical', 'krytyczne') === true, 'krytyczne: tylko critical');
ok(pasujeStan('warning', 'krytyczne') === false, 'krytyczne: warning nie należy');
ok(pasujeStan('ok', 'zdrowe') === true, 'zdrowe: ok');
ok(pasujeStan('unknown', 'zdrowe') === false, 'zdrowe: unknown nie należy');
ok(pasujeStan('disabled', 'wszystko') === true, 'wszystko: bez zawężania');

/* ---------------- widok stacków ---------------- */

const bezFiltra = przygotujStacki(stacki, PUSTY_FILTR);
rowne(bezFiltra.wszystkich, 3, 'licznik wszystkich usług');
rowne(bezFiltra.pokazano, 3, 'bez filtra pokazujemy wszystko');
rowne(bezFiltra.ukryteStacki, 0, 'bez filtra nic nie znika');

const poTekst = przygotujStacki(stacki, filtr({ q: 'postgres' }));
rowne(poTekst.pokazano, 1, 'filtr tekstowy zawęża do jednej usługi (także po obrazie)');
rowne(poTekst.stacki.map((s) => s.name), ['ventiplan-prod'], 'stack bez trafień znika w całości');
rowne(poTekst.ukryteStacki, 1, 'licznik ukrytych stacków');

const poStanie = przygotujStacki(stacki, filtr({ stan: 'problemy' }));
rowne(poStanie.pokazano, 1, 'filtr „problemy" zostawia tylko usługi nie-ok');
rowne(poStanie.ukryteStacki, 1, 'stack bez problemów znika');

const zFokusem = przygotujStacki(stacki, filtr({ q: 'nie-ma-takiej' }), kluczFokusa('monitoring', 'panel'));
rowne(zFokusem.pokazano, 1, 'fokus wygrywa z filtrem — wskazana usługa zostaje');
rowne(zFokusem.stacki[0].services[0].name, 'panel', 'fokus pokazuje właściwą usługę');

/* ---------------- sortowanie ---------------- */

const poCpu = przygotujStacki(stacki, filtr({ sort: 'cpu', kierunek: 'desc' }));
rowne(poCpu.stacki.map((s) => s.name), ['monitoring', 'ventiplan-prod'], 'stacki wg największego CPU malejąco');
rowne(poCpu.stacki[0].services.map((s) => s.name), ['grafana', 'panel'], 'usługi wg CPU malejąco');

const poCpuAsc = przygotujStacki(stacki, filtr({ sort: 'cpu', kierunek: 'asc' }));
rowne(poCpuAsc.stacki[0].name, 'ventiplan-prod', 'rosnąco: stack z najmniejszym CPU na górze');
rowne(
  poCpuAsc.stacki.find((s) => s.name === 'monitoring')?.services.map((s) => s.name),
  ['panel', 'grafana'],
  'usługi wg CPU rosnąco',
);

const poRestartach = przygotujStacki(stacki, filtr({ sort: 'restarty', kierunek: 'desc' }));
rowne(poRestartach.stacki[0].name, 'monitoring', 'stack z restartami na górze');

const poReplikach = przygotujStacki(stacki, filtr({ sort: 'repliki', kierunek: 'desc' }));
rowne(poReplikach.stacki[0].name, 'ventiplan-prod', 'przy sortowaniu replik deficyt (2→1) idzie na górę');

const poNazwie = przygotujStacki(stacki, filtr({ sort: 'usluga', kierunek: 'asc' }));
rowne(poNazwie.stacki.map((s) => s.name), ['monitoring', 'ventiplan-prod'], 'alfabetycznie po nazwie stacka');

const stabilne = sortujUslugi(
  [usluga({ name: 'b', cpu_percent: 1 }), usluga({ name: 'a', cpu_percent: 1 })],
  'cpu',
  'desc',
);
rowne(stabilne.map((s) => s.name), ['a', 'b'], 'przy równych wartościach decyduje nazwa (stabilność)');

/* ---------------- listy ---------------- */

const endpointy = filtrujEndpointy(
  [
    { state: 'ok', name: 'app.ventiplan.pl', group: 'ventiplan-prod', detail: 'HTTP 200', url: null },
    { state: 'critical', name: 'api.star-sign.pl', group: 'star-sign', detail: 'HTTP 503', url: null },
  ],
  filtr({ stan: 'problemy' }),
);
rowne([endpointy.pokazano, endpointy.wszystkich], [1, 2], 'endpointy: licznik „X z Y"');
rowne(endpointy.pozycje[0].name, 'api.star-sign.pl', 'endpointy: zostaje tylko problem');

const certy = filtrujCertyfikaty(
  [
    { state: 'ok', host: 'app.ventiplan.pl', days_left: 60 },
    { state: 'warning', host: 'api.star-sign.pl', days_left: 20 },
  ],
  filtr({ q: 'star' }),
);
rowne([certy.pokazano, certy.wszystkich], [1, 2], 'certyfikaty: filtr tekstowy i licznik');

const alerty = filtrujAlerty(
  [
    { state: 'critical', name: 'AppDown', severity: 'critical', stack: 'ventiplan-prod', summary: 'brak 200' },
    { state: 'warning', name: 'HighCpu', severity: 'warning', stack: 'monitoring', summary: 'CPU 92%' },
  ],
  filtr({ q: 'cpu' }),
);
rowne(alerty.pozycje.map((a) => a.name), ['HighCpu'], 'alerty: szukanie po nazwie i podsumowaniu');

const logowania = filtrujLogowania(
  [
    { service: 'cockpit', ip: '1.2.3.4' },
    { service: 'ssh', ip: '10.0.0.1' },
  ],
  filtr({ q: '10.0' }),
);
rowne([logowania.pokazano, logowania.wszystkich], [1, 2], 'logowania: filtr po IP i licznik');

/* ---------------- hasz ---------------- */

rowne(doHasza(PUSTY_FILTR), '#/', 'domyślny filtr daje czysty hasz');
const hasz = doHasza(filtr({ q: 'grafana', stan: 'problemy', sort: 'cpu' }), kluczFokusa('monitoring', 'panel'));
ok(hasz.startsWith('#/?'), 'hasz z filtrem ma postać #/?…');
const zHaszaWynik = zHasza(hasz);
rowne(zHaszaWynik.filtr.q, 'grafana', 'hasz: zapytanie wraca');
rowne(zHaszaWynik.filtr.stan, 'problemy', 'hasz: stan wraca');
rowne(zHaszaWynik.filtr.sort, 'cpu', 'hasz: sortowanie wraca');
rowne(zHaszaWynik.fokus, 'monitoring/panel', 'hasz: fokus wraca');

const smieci = zHasza('#/?q=x&stan=bzdura&sort=nope&kier=zle&fokus=zle');
rowne(smieci.filtr.stan, 'wszystko', 'hasz: nieznany stan → domyślny');
rowne(smieci.filtr.sort, 'stan', 'hasz: nieznany klucz sortowania → domyślny');
rowne(smieci.filtr.kierunek, 'desc', 'hasz: nieznany kierunek → domyślny');
rowne(smieci.fokus, null, 'hasz: zły fokus → brak fokusu');
rowne(zHasza('#/').filtr, PUSTY_FILTR, 'hasz: pusto → filtr domyślny');
rowne(zHasza('#/tool/grafana').filtr, PUSTY_FILTR, 'hasz: widok narzędzia nie udaje filtra');
rowne(rozbijFokus('a/b/c'), null, 'fokus: trzy człony to śmieć');
rowne(rozbijFokus(null), null, 'fokus: null bezpieczny');

ok(czyAktywny(PUSTY_FILTR) === false, 'pusty filtr nie jest aktywny');
ok(czyAktywny(filtr({ q: 'x' })) === true, 'zapytanie czyni filtr aktywnym');
ok(czyAktywny(filtr({ stan: 'problemy' })) === true, 'stan czyni filtr aktywnym');
ok(opisFiltra(filtr({ q: 'grafana', sort: 'cpu' })).includes('grafana'), 'opis filtra zawiera zapytanie');
ok(opisFiltra(filtr({ sort: 'cpu' })).includes('CPU'), 'opis filtra zawiera klucz sortowania');

/* ---------------- sparkline ---------------- */

rowne(zakresSparkline([]), null, 'sparkline: brak danych → brak zakresu');
rowne(zakresSparkline([Number.NaN, 5]), { min: 5, max: 5 }, 'sparkline: NaN pomijany');
rowne(punktySparkline([], 100, 20), '', 'sparkline: pusty → brak punktów');
rowne(punktySparkline([5], 100, 20), '0,10 100,10', 'sparkline: jeden punkt → linia w połowie');
const dwa = punktySparkline([0, 10], 100, 20).split(' ');
rowne(dwa.length, 2, 'sparkline: dwa punkty dla dwóch wartości');
ok(dwa[0].endsWith(',19.0') || dwa[0].endsWith(',19'), `sparkline: minimum na dole (jest ${dwa[0]})`);
ok(dwa[1].endsWith(',1.0') || dwa[1].endsWith(',1'), `sparkline: maksimum na górze (jest ${dwa[1]})`);
const plaska = punktySparkline([3, 3, 3], 100, 20).split(' ');
rowne(plaska.length, 3, 'sparkline: płaska seria nadal ma punkty');
ok(!plaska.some((p) => p.includes('NaN')), 'sparkline: płaska seria bez NaN');
const procenty = punktySparkline([10, 50, 90], 100, 20, { min: 0, max: 100 }).split(' ');
ok(procenty[0] !== procenty[2], 'sparkline: skala 0–100 rozróżnia wartości');

/* ---------------- CSV ---------------- */

const csv = uslugiDoCsv([
  { stack: 'monitoring', usluga: 'panel;zły', stan: 'ok', repliki: '1/1', cpu: '1,5 %', ram: '30 MiB', restarty: '0', obraz: 'ghcr.io/x' },
]);
ok(csv.startsWith('\uFEFF'), 'CSV zaczyna się od BOM');
ok(csv.split('\r\n')[0].includes(';usluga;'), 'CSV ma nagłówek z separatorem ;');
ok(csv.includes('"panel;zły"'), 'CSV cytuje wartość ze średnikiem');
rowne(csv.split('\r\n').filter((l) => l.trim()).length, 2, 'CSV: nagłówek + jeden wiersz');

/* ---------------- zmiany między snapshotami ---------------- */

ok(zmianyMiedzy(null, { stacks: [], checks: [], alerts: [] }).length === 0, 'zmiany: brak poprzedniego snapshotu → brak zmian');

const poprzedni = {
  stacks: [
    { name: 'monitoring', state: 'ok', services: [usluga({ name: 'panel', state: 'ok', running: 1 })] },
    { name: 'stary', state: 'ok', services: [usluga({ name: 'duch' })] },
  ],
  checks: [{ state: 'ok', name: 'app.ventiplan.pl', group: 'ventiplan-prod' }],
  alerts: [{ state: 'warning', name: 'HighCpu', severity: 'warning', stack: 'monitoring' }],
};
const obecny = {
  stacks: [
    { name: 'monitoring', state: 'warning', services: [usluga({ name: 'panel', state: 'critical', running: 0, desired: 1 })] },
    { name: 'nowy', state: 'ok', services: [usluga({ name: 'swiezak' })] },
  ],
  checks: [{ state: 'critical', name: 'app.ventiplan.pl', group: 'ventiplan-prod', detail: 'HTTP 503' }],
  alerts: [
    { state: 'critical', name: 'AppDown', severity: 'critical', stack: 'ventiplan-prod', summary: 'brak 200' },
  ],
};
const zmiany = zmianyMiedzy(poprzedni, obecny);
const rodzaje = zmiany.map((z) => z.rodzaj);
rowne(rodzaje[0], 'alert-nowy', 'zmiany: nowy alert ma najwyższy priorytet');
ok(rodzaje.includes('alert-zamkniety'), 'zmiany: wykryty zamknięty alert');
ok(rodzaje.includes('stan-uslugi'), 'zmiany: wykryta zmiana stanu usługi');
ok(rodzaje.includes('usluga-nowa'), 'zmiany: wykryta nowa usługa');
ok(rodzaje.includes('usluga-zniknela'), 'zmiany: wykryta zniknięta usługa');
ok(rodzaje.includes('stan-endpointu'), 'zmiany: wykryta zmiana endpointu');
const zmianaStanu = zmiany.find((z) => z.rodzaj === 'stan-uslugi');
rowne(zmianaStanu?.fokus, 'monitoring/panel', 'zmiany: zmiana stanu niesie fokus do kliknięcia');
ok(zmianyMiedzy(poprzedni, obecny, 2).length === 2, 'zmiany: limit respektowany');
const bezZmian = zmianyMiedzy(poprzedni, poprzedni);
rowne(bezZmian.length, 0, 'zmiany: identyczne snapshoty → brak zmian');
const zmianaReplik = zmianyMiedzy(
  { stacks: [{ name: 'a', state: 'ok', services: [usluga({ name: 's', running: 2, desired: 2 })] }], checks: [], alerts: [] },
  { stacks: [{ name: 'a', state: 'ok', services: [usluga({ name: 's', running: 1, desired: 2 })] }], checks: [], alerts: [] },
);
rowne(zmianaReplik.map((z) => z.rodzaj), ['repliki'], 'zmiany: zmiana replik bez zmiany stanu');

/* ---------------- wynik ---------------- */

if (bledy.length > 0) {
  console.error(`✗ filtry panelu: ${bledy.length} z ${sprawdzen} sprawdzeń nie przeszło`);
  for (const blad of bledy.slice(0, 20)) console.error(`   - ${blad}`);
  process.exit(1);
}

console.log(`✓ filtry panelu: ${sprawdzen} sprawdzeń OK`);
