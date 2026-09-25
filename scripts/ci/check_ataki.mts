/**
 * Testy czystej logiki sekcji „Ataki i skanowanie” (`panel/src/lib/ataki.ts`).
 *
 * Powód istnienia: te reguły decydują, czy panel mówi prawdę o ataku. Trzy
 * błędy są tu ciche i drogie:
 *
 *   1. „brak danych” pokazane jako „zero ataków” (zielono, choć nie wiemy) —
 *      panel usypia czujność dokładnie wtedy, gdy access log nie płynie,
 *   2. niestabilna kolejność list — panel migocze między odświeżeniami i nie da
 *      się porównać z poprzednim spojrzeniem,
 *   3. polska odmiana liczebników (1 próba / 2 próby / 5 prób, ale 12 prób).
 *
 * Uruchomienie: `node scripts/ci/check_ataki.mts` (krok w jobie `panel`).
 */
import {
  KOLEJNOSC_WZORCOW,
  etykietaWzorca,
  ileAktywnychWzorcow,
  liczba,
  maDaneAtakow,
  opisSkanowania,
  opisZdarzen,
  podsumowanieAtakow,
  sciezkiDoListy,
  stanAtakow,
  wzorceDoListy,
  zrodlaDoListy,
} from '../../panel/src/lib/ataki.ts';
import type { Ataki } from '../../panel/src/lib/status.ts';

let sprawdzen = 0;
let bledy = 0;

function ok(warunek: boolean, opis: string): void {
  sprawdzen += 1;
  if (!warunek) {
    bledy += 1;
    console.log(`  ✗ ${opis}`);
  }
}

/** Sekcja z danymi (domyślnie: źródło płynie, zero zdarzeń). */
function sekcja(nadpisania: Partial<Ataki> = {}): Ataki {
  return {
    state: 'ok',
    zrodlo_aktywne: true,
    zdarzenia_24h: 0,
    wzorce: [],
    top_ip: [],
    top_sciezki: [],
    skanowanie_10m: 0,
    ostatnie: null,
    ...nadpisania,
  };
}

/* --- 1. Stan: brak danych NIE MOŻE wyglądać jak zero ataków --- */
ok(stanAtakow(null) === 'unknown', 'brak sekcji => unknown (nie „ok”)');
ok(stanAtakow(sekcja({ zrodlo_aktywne: false })) === 'unknown',
  'access log nie płynie => unknown, nawet gdy licznik mówi 0');
ok(stanAtakow(sekcja({ zrodlo_aktywne: null, zdarzenia_24h: null })) === 'unknown',
  'brak wiedzy o źródle => unknown');
ok(stanAtakow(sekcja({ zdarzenia_24h: null })) === 'unknown',
  'brak licznika => unknown');
ok(stanAtakow(sekcja()) === 'ok', 'źródło płynie i zero zdarzeń => ok (sprawdzone, czysto)');
ok(stanAtakow(sekcja({ zdarzenia_24h: 1 })) === 'warning', 'jedno zdarzenie => warning');
ok(stanAtakow(sekcja({ zdarzenia_24h: 512 })) === 'warning', 'dużo zdarzeń => warning');

ok(!maDaneAtakow(null) && !maDaneAtakow(sekcja({ zrodlo_aktywne: false })),
  'maDaneAtakow: fałsz, gdy nie wiemy');
ok(maDaneAtakow(sekcja()) && maDaneAtakow(sekcja({ zdarzenia_24h: 7 })),
  'maDaneAtakow: prawda, gdy źródło płynie');

/* --- 2. Podpisy kafelków --- */
ok(opisZdarzen(null).includes('brak danych'), 'podpis zdarzeń bez danych mówi „brak danych”');
ok(opisZdarzen(sekcja({ zrodlo_aktywne: false })).includes('brak danych'),
  'podpis zdarzeń przy nieaktywnym źródle mówi „brak danych”');
ok(opisZdarzen(sekcja()) === 'brak prób ataku w 24 h', 'zero zdarzeń => jasny komunikat');
ok(opisZdarzen(sekcja({ zdarzenia_24h: 12, top_ip: [
  { ip: '1.1.1.1', ile: 9, wzorce: ['xss'] },
  { ip: '2.2.2.2', ile: 3, wzorce: ['sqli'] },
] })) === '2 adresy źródłowe', 'dwa adresy => „2 adresy źródłowe”');
ok(opisZdarzen(sekcja({ zdarzenia_24h: 4, top_ip: [{ ip: '1.1.1.1', ile: 4, wzorce: ['xss'] }] }))
  === '1 adres źródłowy', 'jeden adres => liczba pojedyncza');
ok(opisZdarzen(sekcja({ zdarzenia_24h: 9, top_ip: Array.from({ length: 5 }, (_, i) => ({
  ip: `10.0.0.${i}`, ile: 1, wzorce: ['skaner'],
})) })) === '5 adresów źródłowych', 'pięć adresów => „adresów źródłowych”');

ok(opisSkanowania(null, 40) === 'brak danych', 'skanowanie bez danych => „brak danych”');
ok(opisSkanowania(sekcja({ skanowanie_10m: null }), 40) === 'brak danych',
  'skanowanie bez licznika => „brak danych”');
ok(opisSkanowania(sekcja({ skanowanie_10m: 0 }), 40).includes('nikt nie przekroczył'),
  'skanowanie: zero => informacja o progu');
ok(opisSkanowania(sekcja({ skanowanie_10m: 1 }), 40) === '1 adres skanuje',
  'skanowanie: jeden adres');
ok(opisSkanowania(sekcja({ skanowanie_10m: 3 }), 40) === '3 adresy skanują',
  'skanowanie: trzy adresy');

ok(podsumowanieAtakow(null) === 'brak danych o atakach', 'podsumowanie bez danych');
ok(podsumowanieAtakow(sekcja()) === 'brak prób ataku w 24 h', 'podsumowanie: czysto');
ok(podsumowanieAtakow(sekcja({ zdarzenia_24h: 12, wzorce: [
  { klucz: 'xss', nazwa: 'XSS', ile: 7 },
  { klucz: 'sqli', nazwa: 'SQLi', ile: 5 },
] })) === '12 zdarzeń w 2 kategoriach', 'podsumowanie z kategoriami');

/* --- 3. Kolejność list (powtarzalna) --- */
const wzorce = wzorceDoListy(sekcja({ wzorce: [
  { klucz: 'skaner', nazwa: 'Skaner', ile: 0 },
  { klucz: 'xss', nazwa: 'XSS', ile: 3 },
  { klucz: 'log4shell', nazwa: 'Log4Shell', ile: 0 },
  { klucz: 'sqli', nazwa: 'SQLi', ile: 10 },
] }));
ok(wzorce[0].klucz === 'sqli' && wzorce[1].klucz === 'xss',
  'wzorce: trafienia najpierw, malejąco po liczbie');
ok(wzorce[2].klucz === 'log4shell' && wzorce[3].klucz === 'skaner',
  'wzorce bez trafień: wg stałej kolejności ważności');
ok(ileAktywnychWzorcow(sekcja({ wzorce: [
  { klucz: 'xss', nazwa: 'XSS', ile: 1 },
  { klucz: 'sqli', nazwa: 'SQLi', ile: 0 },
] })) === 1, 'ileAktywnychWzorcow liczy tylko kategorie z trafieniami');
ok(KOLEJNOSC_WZORCOW[0] === 'log4shell', 'najgroźniejsza kategoria jest pierwsza w stałej kolejności');

const zrodla = zrodlaDoListy(sekcja({ top_ip: [
  { ip: '9.9.9.9', ile: 2, wzorce: ['xss'] },
  { ip: '1.1.1.1', ile: 7, wzorce: ['sqli'] },
  { ip: '2.2.2.2', ile: 2, wzorce: ['skaner'] },
] }));
ok(zrodla[0].ip === '1.1.1.1', 'adresy: malejąco po liczbie prób');
ok(zrodla[1].ip === '2.2.2.2' && zrodla[2].ip === '9.9.9.9',
  'adresy: przy remisie rosnąco po adresie (powtarzalnie)');

const sciezki = sciezkiDoListy(sekcja({ top_sciezki: [
  { sciezka: '/b', ile: 1 },
  { sciezka: '/a', ile: 1 },
  { sciezka: '/c', ile: 9 },
] }));
ok(sciezki[0].sciezka === '/c', 'ścieżki: malejąco po liczbie');
ok(sciezki[1].sciezka === '/a' && sciezki[2].sciezka === '/b',
  'ścieżki: przy remisie rosnąco po ścieżce');

/* --- 4. Etykiety kategorii --- */
ok(etykietaWzorca('xss') === 'XSS' && etykietaWzorca('sqli') === 'SQLi',
  'etykiety: znane klucze mają krótkie nazwy');
ok(etykietaWzorca('log4shell') === 'Log4Shell', 'etykiety: Log4Shell zachowuje zapis');
ok(etykietaWzorca('cos-nowego') === 'cos-nowego', 'etykiety: nieznany klucz wraca bez zmian');
ok(etykietaWzorca('') === 'atak', 'etykiety: pusty klucz => „atak”');

/* --- 5. Polska odmiana --- */
ok(liczba(1, 'próba', 'próby', 'prób') === '1 próba', 'odmiana: 1');
ok(liczba(2, 'próba', 'próby', 'prób') === '2 próby', 'odmiana: 2');
ok(liczba(4, 'próba', 'próby', 'prób') === '4 próby', 'odmiana: 4');
ok(liczba(5, 'próba', 'próby', 'prób') === '5 prób', 'odmiana: 5');
ok(liczba(12, 'próba', 'próby', 'prób') === '12 prób', 'odmiana: 12 (nasteenastka => „prób”)');
ok(liczba(22, 'próba', 'próby', 'prób') === '22 próby', 'odmiana: 22');
ok(liczba(0, 'próba', 'próby', 'prób') === '0 prób', 'odmiana: 0');

/* --- 6. Odporność na śmieci (API może zwrócić cokolwiek) --- */
const smieci = sekcja({ wzorce: [], top_ip: [], top_sciezki: [], zdarzenia_24h: null });
ok(wzorceDoListy(smieci).length === 0 && zrodlaDoListy(smieci).length === 0
  && sciezkiDoListy(smieci).length === 0, 'puste listy nie wywalają sortowania');
ok(stanAtakow(sekcja({ state: 'critical', zdarzenia_24h: 0 })) === 'ok',
  'stan sekcji liczymy z danych, a nie z pola `state` (to rollup, nie źródło)');

if (bledy) {
  console.log(`✗ ataki: ${bledy} z ${sprawdzen} sprawdzeń nie przeszło`);
  process.exit(1);
}
console.log(`✓ ataki i skanowanie: ${sprawdzen} sprawdzeń OK`);
