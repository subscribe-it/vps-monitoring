/**
 * Testy czystej logiki zwijania grup (`panel/src/lib/zwijanie.ts`) — bez
 * przeglądarki i bez nowych zależności.
 *
 * Powód istnienia: stan zwinięcia żyje w `localStorage` i steruje tym, co
 * użytkownik widzi po odświeżeniu. Błąd w parsowaniu zapisu albo w polityce
 * domyślnych stanów potrafi:
 *  - ukryć to, co się psuje (grupa z problemem zwinięta na starcie),
 *  - skasować ustawienia użytkownika przy jednym uszkodzonym wpisie,
 *  - pokazać przycisk zbiorczy, który kłamie („Rozwiń wszystko", gdy nic nie
 *    jest zwinięte).
 *
 *   node scripts/ci/check_zwijanie.mts
 */

import {
  KLUCZ_ZWIJANIA,
  PROG_AUTO_ZWIJANIA,
  czyZwinięta,
  domyslnieZwinięta,
  etykietaZbiorcza,
  identyfikatorWierszy,
  ileZwinietych,
  kluczGrupy,
  parsujZapis,
  przelaczGrupe,
  serializujZapis,
  ustawWszystkie,
  wszystkieZwinięte,
} from '../../panel/src/lib/zwijanie.ts';

let sprawdzen = 0;
const bledy: string[] = [];

function sprawdz(warunek: boolean, opis: string): void {
  sprawdzen += 1;
  if (!warunek) bledy.push(opis);
}

function rowne(a: unknown, b: unknown, opis: string): void {
  sprawdzen += 1;
  const te = JSON.stringify(a);
  const tamte = JSON.stringify(b);
  if (te !== tamte) bledy.push(`${opis} — jest ${te}, miało być ${tamte}`);
}

/* ---- 1. klucze grup: stabilne mimo wielkości liter i spacji ---- */
rowne(kluczGrupy('checks', 'Publiczne endpointy'), 'checks/publiczne endpointy', 'klucz grupy normalizuje nazwę');
rowne(kluczGrupy('checks', '  Publiczne   endpointy '), kluczGrupy('checks', 'publiczne endpointy'), 'spacje i wielkość liter nie tworzą dwóch kluczy');
rowne(kluczGrupy('stacki', 'JPolski_NA6_PL_prod'), 'stacki/jpolski_na6_pl_prod', 'klucz stacka normalizuje nazwę');
sprawdz(kluczGrupy('certs', 'Do odnowienia') !== kluczGrupy('alerts', 'Do odnowienia'), 'ta sama nazwa w dwóch sekcjach to dwa klucze');
rowne(kluczGrupy('', ''), '/', 'puste wejście nie wywala klucza');

/* ---- 2. parsowanie zapisu: odporność na śmieci ---- */
rowne(parsujZapis('{"a":true,"b":false}'), { a: true, b: false }, 'poprawny zapis czytamy w całości');
rowne(parsujZapis('{'), {}, 'urwany JSON to brak zapisu, nie wyjątek');
rowne(parsujZapis('[]'), {}, 'tablica to nie mapa');
rowne(parsujZapis('null'), {}, 'null to brak zapisu');
rowne(parsujZapis(null), {}, 'brak klucza w localStorage to brak zapisu');
rowne(parsujZapis(undefined), {}, 'undefined to brak zapisu');
rowne(
  parsujZapis('{"dobry":true,"zly":"tak","tezZly":1,"nulowy":null,"":true}'),
  { dobry: true },
  'wpisy nieboolowskie i pusty klucz są pomijane, reszta zostaje',
);

/* ---- 3. serializacja: stabilna i bez śmieci ---- */
rowne(serializujZapis({ b: true, a: false }), '{"a":false,"b":true}', 'klucze sortowane (stabilny zapis)');
rowne(serializujZapiszOdczyt(serializujZapis({ a: true })), { a: true }, 'zapis i odczyt są odwracalne');

function serializujZapiszOdczyt(tekst: string): Record<string, boolean> {
  return parsujZapis(tekst);
}

/* ---- 4. czy zwinięta: zapis użytkownika bije domyślny ---- */
sprawdz(czyZwinięta({}, 'x', true) === true, 'bez zapisu obowiązuje domyślny (zwinięta)');
sprawdz(czyZwinięta({}, 'x', false) === false, 'bez zapisu obowiązuje domyślny (rozwinięta)');
sprawdz(czyZwinięta({ x: false }, 'x', true) === false, 'zapis „rozwinięta" wygrywa z domyślnym „zwinięta"');
sprawdz(czyZwinięta({ x: true }, 'x', false) === true, 'zapis „zwinięta" wygrywa z domyślnym „rozwinięta"');

/* ---- 5. przełączanie pojedynczej grupy ---- */
const start = { a: true };
rowne(przelaczGrupe(start, 'a', false), { a: false }, 'przełączenie zwiniętej rozwija ją');
rowne(przelaczGrupe(start, 'b', false), { a: true, b: true }, 'przełączenie nowej grupy zwija ją');
rowne(start, { a: true }, 'funkcja nie mutuje wejścia (czysty stan)');

/* ---- 6. zbiorcze zwijanie i licznik ---- */
const klucze = ['a', 'b', 'c'];
rowne(ustawWszystkie({ a: true }, klucze, false), { a: false, b: false, c: false }, 'zbiorcze rozwijanie ustawia false');
rowne(ustawWszystkie({}, klucze, true), { a: true, b: true, c: true }, 'zbiorcze zwijanie ustawia true');
rowne(ustawWszystkie({ a: true }, ['', '  '], false), { a: true }, 'puste klucze są ignorowane');
sprawdz(wszystkieZwinięte({}, [], []) === false, 'pusta sekcja nie jest „wszystko zwinięte"');
sprawdz(wszystkieZwinięte({ a: true, b: true }, ['a', 'b'], [false, false]) === true, 'wszystkie zwinięte rozpoznane');
sprawdz(wszystkieZwinięte({ a: true }, ['a', 'b'], [false, false]) === false, 'jedna rozwinięta psuje „wszystkie zwinięte"');
sprawdz(wszystkieZwinięte({}, ['a', 'b'], [true, true]) === true, 'domyślne zwinięcie też się liczy');
rowne(ileZwinietych({ a: true }, ['a', 'b', 'c'], [false, true, false]), 2, 'licznik zwiniętych uwzględnia domyślne');
rowne(ileZwinietych({}, [], []), 0, 'pusta lista daje zero');

/* ---- 7. polityka domyślnych stanów (nie może ukrywać problemów) ---- */
sprawdz(domyslnieZwinięta(3, 'ok') === false, 'mała sekcja: grupa OK startuje rozwinięta');
sprawdz(domyslnieZwinięta(PROG_AUTO_ZWIJANIA, 'ok') === true, 'duża sekcja: grupa bez problemów startuje zwinięta');
sprawdz(domyslnieZwinięta(PROG_AUTO_ZWIJANIA, 'warning') === false, 'grupa z ostrzeżeniem ZAWSZE rozwinięta');
sprawdz(domyslnieZwinięta(PROG_AUTO_ZWIJANIA, 'critical') === false, 'grupa krytyczna ZAWSZE rozwinięta');
sprawdz(domyslnieZwinięta(PROG_AUTO_ZWIJANIA, 'unknown') === false, 'grupa bez danych rozwinięta (nie ukrywamy niewiedzy)');
sprawdz(domyslnieZwinięta(999, 'disabled') === true, 'wyłączone traktujemy jak bezproblemowe');

/* ---- 8. identyfikatory dla aria-controls ---- */
rowne(identyfikatorWierszy('checks', 'Publiczne endpointy', 0), 'grupa-checks-publiczne-endpointy-0', 'id z sekcji, grupy i indeksu');
sprawdz(identyfikatorWierszy('checks', 'Publiczne endpointy', 0) !== identyfikatorWierszy('checks', 'Publiczne endpointy', 1), 'indeks rozróżnia grupy o tej samej nazwie');
sprawdz(/^[a-z0-9-]+$/.test(identyfikatorWierszy('certs', 'Wygasają wkrótce', 2)), 'id bez polskich znaków i bez spacji');
sprawdz(identyfikatorWierszy('certs', '!!!', 3).startsWith('grupa-certs-x-'), 'nazwa bez znaków alfanumerycznych dostaje zastępczy slug');

/* ---- 9. etykieta przycisku zbiorczego mówi prawdę ---- */
rowne(etykietaZbiorcza(true, 4), 'Rozwiń wszystko', 'gdy wszystko zwinięte, przycisk oferuje rozwinięcie');
rowne(etykietaZbiorcza(false, 0), 'Zwiń wszystko', 'gdy nic nie jest zwinięte, przycisk oferuje zwinięcie');
sprawdz(etykietaZbiorcza(false, 2).includes('2'), 'częściowe zwinięcie pokazuje licznik');

/* ---- 10. klucz magazynu jest jeden i stabilny ---- */
rowne(KLUCZ_ZWIJANIA, 'panel-zwijanie', 'klucz localStorage nie zmienił nazwy (migracja użytkowników)');
sprawdz(PROG_AUTO_ZWIJANIA >= 4, 'auto-zwijanie nie odpala się w małych sekcjach');

if (bledy.length > 0) {
  console.error(`✗ zwijanie grup: ${bledy.length} błędów z ${sprawdzen} sprawdzeń`);
  for (const blad of bledy) console.error(`   ✗ ${blad}`);
  process.exit(1);
}
console.log(`✓ zwijanie grup (MatExpansionPanel): ${sprawdzen} sprawdzeń OK`);
