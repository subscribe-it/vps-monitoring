/**
 * Strażnik motywu: jasny/ciemny, przełącznik w pasku i jego wpływ na ramki.
 *
 * Powód istnienia: motyw jest widoczny u użytkownika, a błędy w nim są ciche —
 * ciemny prostokąt na jasnym tle, zapisany wybór, który nie wraca po
 * odświeżeniu, albo ramka Grafany zostająca w starym motywie. Ten test pilnuje
 * niezmienników, których nie widać w pojedynczym zrzucie:
 *
 *   1. oba motywy definiują DOKŁADNIE ten sam zestaw tokenów,
 *   2. motyw jasny jest domyślny, ciemny wchodzi przez `prefersdark`,
 *   3. każdy motyw ustawia własne `color-scheme`,
 *   4. w regułach nie ma kolorów zapisanych na sztywno (hex/rgb),
 *   5. wybór użytkownika (auto/jasny/ciemny) mapuje się na atrybut, `color-scheme`
 *      i motyw efektywny — a `auto` NIE ustawia atrybutu (ma działać na żywo),
 *   6. zapis w `localStorage` przeżywa uszkodzoną wartość i brak dostępu,
 *   7. skrypt w `<head>` ustawia motyw przed pierwszym malowaniem,
 *   8. motyw efektywny (nie „systemowy”) trafia do adresu ramek Grafany
 *      i Prometheusa, bez dublowania parametru,
 *   9. nawigacja klawiaturą w przełączniku i tap targety ≥ 24 px.
 *
 * Uruchomienie: `node scripts/ci/check_motyw.mts` (krok w jobie `panel`).
 */
import { readFileSync } from 'node:fs';
import {
  ATRYBUT_CIEMNY,
  ATRYBUT_JASNY,
  KLUCZ_MOTYWU,
  NARZEDZIA_Z_MOTYWEM,
  SKRYPT_MOTYWU,
  WYBORY,
  adresPoZmianieMotywu,
  atrybutDlaWyboru,
  motywEfektywny,
  motywZSystemu,
  nastepnyWybor,
  normalizujWybor,
  odczytajWybor,
  opisWyboru,
  parametrMotywu,
  schematKolorow,
  skrotWyboru,
  zapiszWybor,
  zbudujAdres,
} from '../../panel/src/lib/motyw.ts';

let bledy = 0;
let sprawdzen = 0;
const ok = (warunek: boolean, opis: string) => {
  sprawdzen++;
  if (!warunek) {
    bledy++;
    console.log(`  ✗ ${opis}`);
  }
};

const css = readFileSync('panel/src/styles/global.css', 'utf-8');
const base = readFileSync('panel/src/layouts/Base.astro', 'utf-8');
const pasek = readFileSync('panel/src/components/StatusBar.astro', 'utf-8');
const index = readFileSync('panel/src/pages/index.astro', 'utf-8');

// --- 1) bloki motywów ------------------------------------------------------
const bloki = [...css.matchAll(/@plugin "daisyui\/theme" \{([\s\S]*?)\n\}/g)].map((m) => m[1]);
ok(bloki.length === 2, `oczekuję dwóch motywów w global.css, znalazłem ${bloki.length}`);

const nazwa = (blok: string) => blok.match(/name:\s*"([^"]+)"/)?.[1] ?? '';
const tryb = (blok: string) => blok.match(/color-scheme:\s*([a-z ]+);/)?.[1]?.trim() ?? '';
const flagi = (blok: string) => ({
  domyslny: /default:\s*true/.test(blok),
  ciemny: /prefersdark:\s*true/.test(blok),
});
const tokeny = (blok: string) =>
  new Set(
    [...blok.matchAll(/(--[a-z0-9-]+):/g)]
      .map((m) => m[1])
      .filter((t) => !t.startsWith('--radius') && !t.startsWith('--size'))
      .filter((t) => !['--border', '--depth', '--noise'].includes(t)),
  );

const jasny = bloki.find((b) => tryb(b) === 'light') ?? '';
const ciemny = bloki.find((b) => tryb(b) === 'dark') ?? '';
ok(jasny !== '', 'brak motywu z `color-scheme: light`');
ok(ciemny !== '', 'brak motywu z `color-scheme: dark`');
ok(nazwa(jasny) === ATRYBUT_JASNY, `motyw jasny powinien nazywać się ${ATRYBUT_JASNY}, jest „${nazwa(jasny)}”`);
ok(nazwa(ciemny) === ATRYBUT_CIEMNY, `motyw ciemny powinien nazywać się ${ATRYBUT_CIEMNY}, jest „${nazwa(ciemny)}”`);

// --- 2) wybór przez system -------------------------------------------------
const fj = flagi(jasny);
const fc = flagi(ciemny);
ok(fj.domyslny && !fj.ciemny, 'motyw jasny ma być domyślny i nie „prefersdark” (system bez preferencji = dzień)');
ok(!fc.domyslny && fc.ciemny, 'motyw ciemny ma wchodzić przez „prefersdark” (system w trybie ciemnym)');

// --- 3) ten sam zestaw tokenów w obu motywach ------------------------------
const tj = tokeny(jasny);
const tc = tokeny(ciemny);
const brakujaceWJasnym = [...tc].filter((t) => !tj.has(t));
const brakujaceWCiemnym = [...tj].filter((t) => !tc.has(t));
ok(brakujaceWJasnym.length === 0, `ciemny motyw ma tokeny, których nie ma jasny: ${brakujaceWJasnym.join(', ')}`);
ok(brakujaceWCiemnym.length === 0, `jasny motyw ma tokeny, których nie ma ciemny: ${brakujaceWCiemnym.join(', ')}`);
ok(tj.size >= 18, `zestaw tokenów wygląda na niekompletny: ${tj.size}`);

// --- 4) brak kolorów na sztywno w regułach ---------------------------------
const bezMotywow = css.replace(/@plugin "daisyui\/theme" \{[\s\S]*?\n\}/g, '');
const sztywne = [...bezMotywow.matchAll(/#[0-9a-fA-F]{3,8}\b|\brgba?\(/g)].map((m) => m[0]);
ok(sztywne.length === 0, `kolory na sztywno poza motywami: ${[...new Set(sztywne)].join(', ')}`);

// --- 5) własne tokeny mają wariant ciemny ----------------------------------
ok(/@media \(prefers-color-scheme: dark\)/.test(css), 'brak bloku @media (prefers-color-scheme: dark) z naszymi tokenami');
ok(
  /\[data-theme="ops"\]/.test(css) && /\[data-theme="ops-day"\]/.test(css),
  'brak jawnych zakresów [data-theme="ops"]/[data-theme="ops-day"] dla naszych tokenów',
);
for (const token of ['--state-unknown', '--state-disabled', '--shadow-overlay']) {
  const wystapienia = bezMotywow.split(token).length - 1;
  ok(wystapienia >= 3, `${token} powinien mieć wariant jasny, ciemny (media) i jawny — wystąpień: ${wystapienia}`);
}

// --- 6) wybór użytkownika: normalizacja i mapowanie ------------------------
ok(KLUCZ_MOTYWU === 'panel-motyw', `klucz w localStorage ma być „panel-motyw”, jest „${KLUCZ_MOTYWU}”`);
ok(WYBORY.join(',') === 'auto,jasny,ciemny', `kolejność wyborów: ${WYBORY.join(',')}`);
for (const wybor of WYBORY) {
  ok(normalizujWybor(wybor) === wybor, `„${wybor}” ma przechodzić normalizację bez zmian`);
  ok(skrotWyboru(wybor).length > 0 && opisWyboru(wybor).length > 0, `brak etykiety/opisu dla „${wybor}”`);
  ok(/[a-ząćęłńóśźż]/i.test(opisWyboru(wybor)), `opis „${wybor}” powinien być po polsku (krótki i konkretny)`);
}
ok(normalizujWybor(' JASNY ') === 'jasny', 'normalizacja ma trymować i ignorować wielkość liter');
ok(normalizujWybor('CIEMNY') === 'ciemny', 'normalizacja ma przyjmować wielkie litery');
ok(normalizujWybor('losowa') === 'auto', 'nieznana wartość ma dawać auto (nie zostawiać losowego motywu)');
ok(normalizujWybor('') === 'auto' && normalizujWybor(null) === 'auto' && normalizujWybor(42) === 'auto',
  'pusta/nie-tekstowa wartość ma dawać auto');
ok(normalizujWybor({ theme: 'ops' }) === 'auto', 'obiekt (np. z ręcznie zepsutego storage) ma dawać auto');

ok(motywZSystemu(true) === 'dark' && motywZSystemu(false) === 'light',
  'motywZSystemu ma mapować preferencję systemu na light/dark');
ok(motywEfektywny('auto', true) === 'dark' && motywEfektywny('auto', false) === 'light',
  'auto ma rozstrzygać się z systemu');
ok(motywEfektywny('jasny', true) === 'light', '„jasny” ma wygrywać z ciemnym systemem');
ok(motywEfektywny('ciemny', false) === 'dark', '„ciemny” ma wygrywać z jasnym systemem');

ok(atrybutDlaWyboru('auto', true) === null && atrybutDlaWyboru('auto', false) === null,
  'auto NIE może ustawiać data-theme — inaczej media query przestaje działać na żywo');
ok(atrybutDlaWyboru('jasny', true) === ATRYBUT_JASNY, '„jasny” ma dawać data-theme=ops-day także przy ciemnym systemie');
ok(atrybutDlaWyboru('ciemny', false) === ATRYBUT_CIEMNY, '„ciemny” ma dawać data-theme=ops także przy jasnym systemie');
ok(schematKolorow('auto', false) === 'light dark', 'auto ma zostawiać color-scheme „light dark” (kontrolki idą za systemem)');
ok(schematKolorow('jasny', true) === 'light' && schematKolorow('ciemny', false) === 'dark',
  'jawny wybór ma ustawiać color-scheme, żeby scrollbar i pola nie zostały w motywie systemu');

ok(nastepnyWybor('auto', 1) === 'jasny', 'strzałka w prawo z auto ma iść na „jasny”');
ok(nastepnyWybor('ciemny', 1) === 'auto', 'nawigacja ma zawijać na końcu listy');
ok(nastepnyWybor('auto', -1) === 'ciemny', 'nawigacja ma zawijać także w lewo');

// --- 7) zapis i odczyt wyboru ----------------------------------------------
const magazyn = new Map<string, string>();
ok(zapiszWybor((k, v) => magazyn.set(k, v), 'ciemny') === true, 'zapis wyboru ma się udawać');
ok(magazyn.get(KLUCZ_MOTYWU) === 'ciemny', 'zapis ma trafić pod klucz panel-motyw');
ok(odczytajWybor((k) => magazyn.get(k)) === 'ciemny', 'odczyt ma zwrócić zapisany wybór');
magazyn.set(KLUCZ_MOTYWU, 'bzdura');
ok(odczytajWybor((k) => magazyn.get(k)) === 'auto', 'uszkodzona wartość w storage ma dawać auto');
ok(odczytajWybor(() => { throw new Error('brak dostępu'); }) === 'auto',
  'wyjątek przy czytaniu (tryb prywatny) ma dawać auto, a nie wywracać panelu');
ok(zapiszWybor(() => { throw new Error('brak miejsca'); }, 'jasny') === false,
  'wyjątek przy zapisie ma zwracać false, a nie wywracać panelu');

// --- 8) skrypt przed pierwszym malowaniem ----------------------------------
ok(SKRYPT_MOTYWU.includes(`localStorage.getItem(${JSON.stringify(KLUCZ_MOTYWU)})`),
  'skrypt motywu ma czytać ten sam klucz co reszta panelu');
ok(SKRYPT_MOTYWU.includes('dataset.theme'), 'skrypt motywu ma ustawiać data-theme');
ok(SKRYPT_MOTYWU.includes(ATRYBUT_CIEMNY) && SKRYPT_MOTYWU.includes(ATRYBUT_JASNY),
  'skrypt motywu ma używać nazw motywów z jednego źródła prawdy');
ok(SKRYPT_MOTYWU.indexOf('return') < SKRYPT_MOTYWU.indexOf('dataset.theme'),
  'w trybie auto skrypt ma się wycofać PRZED ustawieniem atrybutu (decyduje media query)');
ok(/try\{/.test(SKRYPT_MOTYWU) && /catch\(e\)\{\}/.test(SKRYPT_MOTYWU),
  'skrypt motywu ma być odporny na brak localStorage (try/catch)');

ok(/import \{ SKRYPT_MOTYWU \} from '\.\.\/lib\/motyw'/.test(base),
  'Base.astro ma brać skrypt motywu z lib/motyw.ts (jedno źródło prawdy)');
ok(/<script is:inline set:html=\{SKRYPT_MOTYWU\}><\/script>/.test(base),
  'Base.astro ma wstrzykiwać skrypt inline (bez niego motyw pojawi się po pierwszym malowaniu)');
const znacznikHtml = base.match(/<html[^>]*>/)?.[0] ?? '';
ok(!/data-theme/.test(znacznikHtml),
  'statyczny <html> nie może mieć data-theme — nadpisałoby preferencję systemu');
const pozycjaSkryptu = base.indexOf('set:html={SKRYPT_MOTYWU}');
const pozycjaTresci = base.indexOf('<body>');
ok(pozycjaSkryptu > -1 && pozycjaSkryptu < pozycjaTresci, 'skrypt motywu ma być w <head>, przed treścią');
ok(/name="color-scheme" content="light dark"/.test(base), 'meta color-scheme powinno być „light dark”');
ok(!/color-scheme:\s*dark;/.test(css.split('@plugin')[0]), 'w regułach bazowych nie może być sztywnego `color-scheme: dark`');

// --- 9) kontrolka w pasku --------------------------------------------------
ok(/role="radiogroup"/.test(pasek), 'przełącznik motywu ma być radiogroup (jeden wybór z trzech, nie trzy przełączniki)');
ok(/aria-label="Motyw panelu"/.test(pasek), 'radiogroup potrzebuje nazwy dostępnej');
ok(/aria-checked="true"/.test(pasek) && (pasek.match(/aria-checked="false"/g) ?? []).length === 2,
  'dokładnie jedna opcja ma być zaznaczona na starcie');
for (const wybor of WYBORY) {
  ok(pasek.includes(`data-wybor="${wybor}"`), `brak przycisku dla wyboru „${wybor}”`);
  ok(pasek.includes(`opisWyboru('${wybor}')`), `przycisk „${wybor}” ma brać podpowiedź z lib/motyw.ts`);
}
ok((pasek.match(/tabindex="-1"/g) ?? []).length === 2,
  'roving tabindex: tylko zaznaczona opcja jest przystankiem Tab');
ok(/data-action="motyw"/.test(pasek), 'przyciski mają nieść akcję obsługiwaną przez delegowany handler');
ok(/class="sr-only"/.test(pasek), 'ikona bez etykiety widocznej na wąskim ekranie potrzebuje opisu dla czytnika');
ok(/\.motyw-opcja\s*\{[\s\S]*?min-height:\s*1\.5rem/.test(css),
  'tap target opcji motywu ma mieć ≥ 24 px (1.5rem)');
ok(/\.motyw-opcja\[aria-checked="true"\]/.test(css), 'zaznaczona opcja musi mieć własny styl (tło + obramowanie)');
ok(/@media \(max-width: 640px\)[\s\S]*?\.motyw-etykieta\s*\{[\s\S]*?display:\s*none/.test(css),
  'na wąskim ekranie etykiety mają się chować, a nie rozpychać pasek');

// --- 10) spięcie w skrypcie klienta ----------------------------------------
ok(/let wyborMotywu: WyborMotywu = odczytajWybor\(/.test(index),
  'stan motywu ma startować z zapisanego wyboru');
ok(/zapiszWybor\(/.test(index), 'zmiana motywu ma się zapisywać (inaczej nie przetrwa odświeżenia)');
ok(/const mediaMotyw = window\.matchMedia\('\(prefers-color-scheme: dark\)'\)/.test(index),
  'panel ma trzymać jedno źródło preferencji systemu');
ok(/mediaMotyw\.addEventListener\('change'/.test(index), 'brak nasłuchu zmiany preferencji systemu');
ok(/if \(wyborMotywu !== 'auto'\) return;/.test(index),
  'przy jawnym wyborze zmiana systemu nie może nic robić (żadnego przeładowania ramki)');
ok(/action === 'motyw'\) ustawWyborMotywu\(trigger\.dataset\.wybor\)/.test(index),
  'klik w opcję motywu ma wołać ustawWyborMotywu');
ok(/ustawWyborMotywu\(nastepnyWybor\(/.test(index) && /klawisz === 'Home'/.test(index),
  'przełącznik ma obsługiwać strzałki i Home/End (radiogroup)');
ok(/zastosujMotyw\(\);\n/.test(index), 'przy starcie panel ma odzwierciedlić wybór w kontrolce');
ok(/delete korzen\.dataset\.theme/.test(index),
  'powrót do auto ma USUWAĆ atrybut, żeby media query znów decydowało');
ok(/frame\.getAttribute\('src'\)/.test(index),
  'porównanie adresu ramki ma iść po atrybucie — inaczej każde odświeżenie przeładowuje ramkę');

// --- 11) motyw efektywny w ramkach narzędzi --------------------------------
ok(/parametrMotywu\(tool\.id, motywEfektywny\(wyborMotywu, mediaMotyw\.matches\)\)/.test(index),
  'embedSrc ma przekazywać motyw EFEKTYWNY (w auto rozstrzygnięty z systemu), nie samą preferencję systemu');
ok(parametrMotywu('grafana', 'dark') === 'theme=dark', 'Grafana w trybie ciemnym ma dostać theme=dark');
ok(parametrMotywu('prometheus', 'light') === 'theme=light', 'Prometheus w trybie jasnym ma dostać theme=light');
ok(parametrMotywu('portainer', 'dark') === null, 'Portainer nie zna parametru theme — ma być null, nie zgadywanie');
ok(parametrMotywu('alertmanager', 'dark') === null, 'Alertmanager nie zna parametru theme — ma być null');
ok(NARZEDZIA_Z_MOTYWEM.length === 2, 'lista narzędzi rozumiejących theme ma zostać krótka i świadoma');

ok(zbudujAdres('/grafana', ['kiosk', 'theme=dark']) === '/grafana?kiosk&theme=dark',
  'adres bez zapytania ma dostać `?` i oba parametry');
ok(zbudujAdres('/grafana?kiosk', ['theme=light']) === '/grafana?kiosk&theme=light',
  'adres z istniejącym zapytaniem ma dostać `&`, bez psucia `kiosk`');
ok(zbudujAdres('/grafana', [null, undefined, '   ']) === '/grafana',
  'puste parametry nie mogą zostawiać wiszącego `?` ani `&`');
ok(zbudujAdres('/grafana?theme=light', ['theme=dark']) === '/grafana?theme=light',
  'parametr już obecny w adresie nie może być dublowany');
ok(zbudujAdres('', ['theme=dark']) === '', 'brak adresu = brak ramki, nie „?theme=dark”');

ok(adresPoZmianieMotywu('portainer', '/portainer', null, 'dark') === null,
  'zmiana motywu nie może przeładowywać ramek narzędzi, które tego nie rozumieją');
ok(adresPoZmianieMotywu('grafana', '/grafana', 'kiosk', 'dark') === '/grafana?kiosk&theme=dark',
  'zmiana motywu ma przeładować ramkę Grafany z nowym motywem');
ok(adresPoZmianieMotywu('grafana', '/grafana?kiosk&theme=dark', 'kiosk', 'dark') === '/grafana?kiosk&theme=dark',
  'ten sam motyw ma dawać ten sam adres — inaczej ramka przeładowuje się bez potrzeby');
ok(adresPoZmianieMotywu('grafana', '', 'kiosk', 'dark') === null, 'brak adresu = nic nie robimy');

if (bledy) {
  console.log(`✗ motyw panelu: ${bledy} z ${sprawdzen} sprawdzeń nie przeszło`);
  process.exit(1);
}
console.log(`✓ motyw panelu (jasny/ciemny + przełącznik): ${sprawdzen} sprawdzeń OK`);
