/**
 * Strażnik motywu jasny/ciemny.
 *
 * Powód istnienia: motyw wybiera SYSTEM (`prefers-color-scheme`), a nie
 * JavaScript — więc każdy błąd w tokenach jest widoczny dopiero u użytkownika,
 * w połowie ekranu (np. ciemny prostokąt na jasnym tle). Ten test pilnuje
 * niezmienników, których nie widać w pojedynczym zrzucie:
 *
 *   1. oba motywy definiują DOKŁADNIE ten sam zestaw tokenów,
 *   2. motyw jasny jest domyślny, ciemny wchodzi przez `prefersdark`,
 *   3. każdy motyw ustawia własne `color-scheme`,
 *   4. w regułach nie ma kolorów zapisanych na sztywno (hex/rgb) — poza samymi
 *      definicjami motywów,
 *   5. `Base.astro` nie ustawia `data-theme` (to nadpisałoby preferencję
 *      użytkownika) i deklaruje `color-scheme: light dark`,
 *   6. nasze własne tokeny (stany, cień) mają wariant dla trybu ciemnego.
 *
 * Uruchomienie: `node scripts/ci/check_motyw.mts` (krok w jobie `panel`).
 */
import { readFileSync } from 'node:fs';
import {
  NARZEDZIA_Z_MOTYWEM,
  adresPoZmianieMotywu,
  motywZSystemu,
  parametrMotywu,
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
  new Set([...blok.matchAll(/(--[a-z0-9-]+):/g)].map((m) => m[1]).filter((t) => !t.startsWith('--radius') && !t.startsWith('--size') && !['--border', '--depth', '--noise'].includes(t)));

const jasny = bloki.find((b) => tryb(b) === 'light') ?? '';
const ciemny = bloki.find((b) => tryb(b) === 'dark') ?? '';
ok(jasny !== '', 'brak motywu z `color-scheme: light`');
ok(ciemny !== '', 'brak motywu z `color-scheme: dark`');
ok(nazwa(jasny) === 'ops-day', `motyw jasny powinien nazywać się ops-day, jest „${nazwa(jasny)}”`);
ok(nazwa(ciemny) === 'ops', `motyw ciemny powinien nazywać się ops, jest „${nazwa(ciemny)}”`);

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
ok(/\[data-theme="ops"\]/.test(css) && /\[data-theme="ops-day"\]/.test(css),
   'brak jawnych zakresów [data-theme="ops"]/[data-theme="ops-day"] dla naszych tokenów');
for (const token of ['--state-unknown', '--state-disabled', '--shadow-overlay']) {
  const wystapienia = bezMotywow.split(token).length - 1;
  ok(wystapienia >= 3, `${token} powinien mieć wariant jasny, ciemny (media) i jawny — wystąpień: ${wystapienia}`);
}

// --- 6) powłoka HTML oddaje motyw systemowi --------------------------------
ok(!/data-theme=/.test(base), 'Base.astro nie może ustawiać data-theme — to nadpisuje preferencję użytkownika');
ok(/name="color-scheme" content="light dark"/.test(base), 'meta color-scheme powinno być „light dark”');
ok(!/color-scheme:\s*dark;/.test(css.split('@plugin')[0]), 'w regułach bazowych nie może być sztywnego `color-scheme: dark`');


// --- 7) motyw przekazany osadzanym narzędziom -------------------------------
// Grafana i Prometheus mają własny motyw: bez `theme=` jasny panel trzymałby
// ciemną ramkę w środku (i odwrotnie).
ok(motywZSystemu(true) === 'dark' && motywZSystemu(false) === 'light',
   'motywZSystemu ma mapować preferencję systemu na light/dark');
ok(parametrMotywu('grafana', true) === 'theme=dark', 'Grafana w trybie ciemnym ma dostać theme=dark');
ok(parametrMotywu('prometheus', false) === 'theme=light', 'Prometheus w trybie jasnym ma dostać theme=light');
ok(parametrMotywu('portainer', true) === null, 'Portainer nie zna parametru theme — ma być null, nie zgadywanie');
ok(parametrMotywu('alertmanager', true) === null, 'Alertmanager nie zna parametru theme — ma być null');
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

ok(adresPoZmianieMotywu('portainer', '/portainer', null, true) === null,
   'zmiana motywu nie może przeładowywać ramek narzędzi, które tego nie rozumieją');
ok(adresPoZmianieMotywu('grafana', '/grafana', 'kiosk', true) === '/grafana?kiosk&theme=dark',
   'zmiana motywu ma przeładować ramkę Grafany z nowym motywem');
ok(adresPoZmianieMotywu('grafana', '', 'kiosk', true) === null, 'brak adresu = nic nie robimy');

const index = readFileSync('panel/src/pages/index.astro', 'utf-8');
ok(/parametrMotywu\(tool\.id, ciemnySystemu\(\)\)/.test(index),
   'embedSrc musi dokładać parametr motywu z aktualnej preferencji systemu');
ok(/matchMedia\('\(prefers-color-scheme: dark\)'\)\.addEventListener\('change'/.test(index),
   'brak nasłuchu zmiany preferencji systemu — ramka Grafany zostałaby w starym motywie');

if (bledy) {
  console.log(`✗ motyw panelu: ${bledy} z ${sprawdzen} sprawdzeń nie przeszło`);
  process.exit(1);
}
console.log(`✓ motyw panelu (jasny/ciemny): ${sprawdzen} sprawdzeń OK`);
