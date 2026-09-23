/**
 * Testy czystej logiki widoku „Logi" (`panel/src/lib/logi.ts`).
 *
 * Po co: pomyłka w zapytaniu LogQL pokazuje logi **nie tej usługi** (etykieta
 * `service` ma prefiks stacka!), a pomyłka w filtrze — pustą listę bez powodu.
 * Sprawdzamy też, że fraza użytkownika NIE trafia do zapytania (wstrzyknięcie).
 *
 *   node scripts/ci/check_logi.mts
 */

import {
  LIMITY_LINII,
  LIMIT_LINII_DOMYSLNY,
  ZAKRESY_LOGOW,
  ZAKRES_LOGOW_DOMYSLNY,
  ZRODLA_LOGOW,
  czyTrasaLogow,
  doHaszaLogi,
  etykietyCzasuLogow,
  eksportLogow,
  filtrujLinie,
  formatujCzasLogu,
  limitLiniiZId,
  linkGrafanaExplore,
  opisStrumienia,
  parsujOdpowiedzLoki,
  podpowiedzPustki,
  podsumowanieLogow,
  zakresLogowZId,
  zapytanieUslugi,
  zapytanieZrodla,
  zbudujUrlLogow,
  bladLogow,
  zHaszaLogi,
  zrodloLogowZId,
} from '../../panel/src/lib/logi.ts';

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

/* ---------------- zakresy i limity ---------------- */

rowne(ZAKRESY_LOGOW.length, 3, 'zakresy logów: trzy przyciski (15 min / 1 h / 24 h)');
rowne(zakresLogowZId('24h').sekundy, 86_400, 'zakres: 24 h = 86400 s');
rowne(zakresLogowZId('bzdura').id, ZAKRES_LOGOW_DOMYSLNY, 'zakres: nieznany → domyślny');
rowne(zakresLogowZId(null).id, ZAKRES_LOGOW_DOMYSLNY, 'zakres: brak → domyślny');
ok(
  ZAKRESY_LOGOW.every((z, i) => i === 0 || z.sekundy > (ZAKRESY_LOGOW[i - 1] as { sekundy: number }).sekundy),
  'zakresy logów: rosnące okna',
);
rowne(LIMITY_LINII.length, 3, 'limity: trzy wartości (200/500/1000)');
rowne(limitLiniiZId('500'), 500, 'limit: tekst z select-a działa');
rowne(limitLiniiZId('7'), LIMIT_LINII_DOMYSLNY, 'limit: spoza listy → domyślny');
rowne(limitLiniiZId(null), LIMIT_LINII_DOMYSLNY, 'limit: brak → domyślny');
rowne(ZRODLA_LOGOW.length, 3, 'źródła: usługa / host / traefik');
rowne(zrodloLogowZId('traefik').id, 'traefik', 'źródło: traefik rozpoznany');
rowne(zrodloLogowZId('bzdura').id, 'usluga', 'źródło: nieznane → usługa');

/* ---------------- zapytania ---------------- */

rowne(
  zapytanieUslugi('jpolski_na6_pl_prod', 'wordpress'),
  '{job="docker", stack="jpolski_na6_pl_prod", service="jpolski_na6_pl_prod_wordpress"}',
  'LogQL: etykieta service ma prefiks stacka',
);
rowne(zapytanieZrodla('host', 'a', 'b'), '{job="journald", unit=~".+"}', 'LogQL: journald hosta');
rowne(zapytanieZrodla('traefik', 'a', 'b'), '{job="traefik"}', 'LogQL: access log Traefika');
rowne(
  zapytanieZrodla('usluga', 'stack1', 'api'),
  '{job="docker", stack="stack1", service="stack1_api"}',
  'LogQL: źródło „usługa" = kontenery tej usługi',
);
ok(
  !zapytanieUslugi('s', 'u').includes('|~') && !zapytanieUslugi('s', 'u').includes('|='),
  'LogQL: filtr nie jest wstrzykiwany do zapytania (brak operatorów textowych)',
);

const TERAZ = Date.UTC(2026, 8, 22, 18, 45, 0) / 1000;
const url = zbudujUrlLogow('stack1', 'api', 'usluga', zakresLogowZId('1h'), 500);
ok(url.startsWith('/status/logs?'), 'URL: przez naszą usługę (/status/* jest trasowane na pewno)');
const parametry = new URLSearchParams(url.split('?')[1] ?? '');
rowne(parametry.get('limit'), '500', 'URL: limit linii przekazany');
rowne(parametry.get('zakres'), '1h', 'URL: zakres przekazany');
rowne(parametry.get('zrodlo'), 'usluga', 'URL: źródło przekazane');
rowne(parametry.get('stack'), 'stack1', 'URL: stack przekazany');
rowne(parametry.get('usluga'), 'api', 'URL: usługa przekazana');
ok(!url.includes('query='), 'URL: LogQL NIE jedzie z przeglądarki (buduje go serwer)');

const urlHosta = zbudujUrlLogow('stack1', 'api', 'host', zakresLogowZId('24h'), 200);
const parametryHosta = new URLSearchParams(urlHosta.split('?')[1] ?? '');
ok(!parametryHosta.has('stack') && !parametryHosta.has('usluga'), 'URL: dla hosta nie wysyłamy stacka/usługi');
rowne(parametryHosta.get('zrodlo'), 'host', 'URL: źródło host przekazane');

const explore = linkGrafanaExplore('{job="traefik"}', zakresLogowZId('15m'));
ok(explore.startsWith('/grafana/explore?'), 'Grafana: link względny (jedno logowanie)');
const exploreOdkodowany = decodeURIComponent(explore);
// `JSON.stringify` escapuje cudzysłowy w LogQL, więc szukamy samego zapytania
// i źródła danych — nie całego literału z cudzysłowami.
ok(exploreOdkodowany.includes('traefik'), 'Grafana: zapytanie w linku');
ok(exploreOdkodowany.includes('loki'), 'Grafana: źródło danych loki w linku');

/* ---------------- parsowanie odpowiedzi ---------------- */

rowne(parsujOdpowiedzLoki(null), [], 'parsowanie: null → pusta lista');
rowne(parsujOdpowiedzLoki({ data: {} }), [], 'parsowanie: brak result → pusta lista');
rowne(parsujOdpowiedzLoki({ data: { result: 'bzdura' } }), [], 'parsowanie: result nie-lista → pusta lista');

const zApi = {
  linie: [
    { czas: 1758567060, tekst: 'druga linia', strumien: 'monitoring_panel' },
    { czas: 1758567000, tekst: 'pierwsza linia', strumien: 'monitoring_panel' },
    { czas: 'bzdura', tekst: 'śmieć' },
    { czas: 1758567030 },
    null,
  ],
  zapytanie: '{job="docker"}',
  limit: 200,
};
const zApiLinie = parsujOdpowiedzLoki(zApi);
rowne(zApiLinie.length, 2, 'API: śmieci pominięte, dwie prawdziwe linie');
rowne(zApiLinie[0]?.tekst, 'druga linia', 'API: najnowsza linia pierwsza');
rowne(zApiLinie[1]?.strumien, 'monitoring_panel', 'API: strumień zachowany');
rowne(parsujOdpowiedzLoki({ linie: [] }), [], 'API: pusta lista linii');
rowne(bladLogow({ error: 'Loki nie odpowiedziało' }), 'Loki nie odpowiedziało', 'API: błąd odczytany');
rowne(bladLogow({ linie: [] }), null, 'API: brak błędu w dobrej odpowiedzi');
rowne(bladLogow({ error: '   ' }), null, 'API: biały błąd to brak błędu');

const odpowiedz = {
  data: {
    result: [
      {
        stream: { service: 'monitoring_panel', job: 'docker' },
        values: [
          ['1758567000000000000', 'pierwsza linia'],
          ['1758567060000000000', 'druga linia'],
        ],
      },
      { stream: { unit: 'ssh.service' }, values: [['1758567030000000000', 'sshd: Accepted']] },
      { stream: { job: 'docker' }, values: [['zły-znacznik', 'śmieć'], ['1758567090000000000', null]] },
      { bez: 'streamu' },
      'śmieć',
    ],
  },
};
const linie = parsujOdpowiedzLoki(odpowiedz);
rowne(linie.length, 3, 'parsowanie: śmieci pominięte, trzy prawdziwe linie');
rowne(linie[0]?.tekst, 'druga linia', 'parsowanie: najnowsza linia pierwsza');
ok((linie[0]?.czas ?? 0) > (linie[2]?.czas ?? 0), 'parsowanie: sortowanie malejące po czasie');
rowne(linie[0]?.strumien, 'monitoring_panel', 'parsowanie: etykieta service wygrywa');
rowne(linie[1]?.strumien, 'ssh.service', 'parsowanie: fallback na unit');
rowne(opisStrumienia({ container: 'x' }), 'x', 'opis strumienia: container');
rowne(opisStrumienia({ job: 'docker' }), 'docker', 'opis strumienia: job');
rowne(opisStrumienia(null), '—', 'opis strumienia: brak etykiet → kreska');

/* ---------------- filtr i podpisy ---------------- */

rowne(filtrujLinie(linie, '').length, 3, 'filtr: pusty przepuszcza wszystko');
rowne(filtrujLinie(linie, 'DRUGA').length, 1, 'filtr: bez rozróżniania wielkości liter');
rowne(filtrujLinie(linie, 'druga linia').length, 1, 'filtr: podciąg zamiast całej linii');
rowne(filtrujLinie(linie, 'druga sshd').length, 0, 'filtr: dwa słowa = AND (muszą być w jednej linii)');
// Kolejność słów nie ma znaczenia, a oba muszą wystąpić (linia „sshd: Accepted”).
rowne(filtrujLinie(linie, 'sshd Accepted').length, 1, 'filtr: kolejność słów bez znaczenia (AND)');
rowne(filtrujLinie(linie, 'Accepted sshd').length, 1, 'filtr: odwrotna kolejność słów trafia tak samo');
rowne(filtrujLinie(linie, 'accepted').length, 1, 'filtr: trafienie w pojedyncze słowo');
rowne(filtrujLinie(linie, '.*').length, 0, 'filtr: regex nie działa (podciąg, nie wyrażenie)');
ok(filtrujLinie(linie, 'druga') !== linie, 'filtr: zwraca kopię, nie tę samą tablicę');

rowne(podsumowanieLogow(0, 0, 200), 'brak linii w tym zakresie', 'podsumowanie: pustka');
rowne(podsumowanieLogow(12, 12, 200), '12 linii', 'podsumowanie: komplet');
ok(
  podsumowanieLogow(200, 200, 200).includes('limit pobrania'),
  'podsumowanie: osiągnięty limit mówi o tym wprost',
);
rowne(podsumowanieLogow(3, 40, 200), '3 z 40 linii (filtr)', 'podsumowanie: filtr zawęził listę');

rowne(etykietyCzasuLogow(zakresLogowZId('1h'), TERAZ).od, '17:45', 'czas: 1 h bez daty');
// 24 h wcześniej to POPRZEDNI dzień — inaczej etykieta „od” kłamałaby o dacie.
rowne(etykietyCzasuLogow(zakresLogowZId('24h'), TERAZ).od, '21.09 18:45', 'czas: 24 h z datą');
rowne(formatujCzasLogu(TERAZ, zakresLogowZId('1h')), '18:45:00', 'czas linii: godzina z sekundami');
rowne(formatujCzasLogu(TERAZ, zakresLogowZId('24h')), '22.09 18:45:00', 'czas linii: z datą przy 24 h');
rowne(formatujCzasLogu(0, zakresLogowZId('1h')), '—', 'czas linii: brak czasu → kreska');

const eksport = eksportLogow(linie, zakresLogowZId('1h'));
rowne(eksport.split('\n').length, 3, 'eksport: jedna linia na wpis');
ok(eksport.includes('[monitoring_panel]'), 'eksport: strumień w treści');
ok(eksport.includes('druga linia'), 'eksport: treść linii w eksporcie');

ok(podpowiedzPustki('traefik', zakresLogowZId('1h')).includes('TraefikNoAccessLogs'), 'pustka: traefik tłumaczy się alertem');
ok(podpowiedzPustki('usluga', zakresLogowZId('1h')).includes('stdout'), 'pustka: usługa mówi o stdout');

/* ---------------- trasa ---------------- */

ok(czyTrasaLogow('#/logi'), 'trasa: #/logi rozpoznana');
ok(czyTrasaLogow('#/logi/stack/usluga?zakres=24h'), 'trasa: szczegóły rozpoznane');
ok(czyTrasaLogow('#/logi?zrodlo=traefik'), 'trasa: źródło w zapytaniu');
ok(!czyTrasaLogow('#/wykresy'), 'trasa: wykresy to nie logi');
ok(!czyTrasaLogow('#/logistyka'), 'trasa: podobna nazwa nie łapie się przypadkiem');

rowne(zHaszaLogi('#/logi').usluga, null, 'hasz: lista bez usługi');
rowne(zHaszaLogi('#/logi').zakres, ZAKRES_LOGOW_DOMYSLNY, 'hasz: domyślny zakres');
rowne(zHaszaLogi('#/logi').zrodlo, 'usluga', 'hasz: domyślne źródło');
rowne(zHaszaLogi('#/logi/stack1/api').usluga, 'stack1/api', 'hasz: usługa z segmentu trasy');
rowne(zHaszaLogi('#/logi/stack1/api?zakres=24h&zrodlo=host').zakres, '24h', 'hasz: zakres z zapytania');
rowne(zHaszaLogi('#/logi/stack1/api?zrodlo=traefik').zrodlo, 'traefik', 'hasz: źródło z zapytania');
rowne(zHaszaLogi('#/logi?zrodlo=bzdura').zrodlo, 'usluga', 'hasz: nieznane źródło → domyślne');
rowne(zHaszaLogi('#/logi/a%2Fb').usluga, 'a/b', 'hasz: dekodowanie segmentu');

rowne(doHaszaLogi(null), '#/logi', 'link: domyślny najkrótszy');
rowne(doHaszaLogi('stack/api', '24h', 'host'), '#/logi/stack%2Fapi?zakres=24h&zrodlo=host', 'link: pełny wariant');
rowne(doHaszaLogi('stack/api'), '#/logi/stack%2Fapi', 'link: domyślne parametry pominięte');
rowne(
  zHaszaLogi(doHaszaLogi('stack/api', '15m', 'traefik')).usluga,
  'stack/api',
  'link ↔ hasz: round-trip usługi',
);
rowne(
  zHaszaLogi(doHaszaLogi('stack/api', '15m', 'traefik')).zrodlo,
  'traefik',
  'link ↔ hasz: round-trip źródła',
);

if (bledy.length > 0) {
  console.error(`✗ logi panelu: ${bledy.length} z ${sprawdzen} sprawdzeń NIE przeszło:`);
  for (const blad of bledy) console.error(`  • ${blad}`);
  process.exit(1);
}
console.log(`✓ logi panelu: ${sprawdzen} sprawdzeń OK`);
