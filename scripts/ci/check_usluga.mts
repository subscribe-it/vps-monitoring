/**
 * Testy czystej logiki obsługi usługi (`panel/src/lib/usluga.ts`).
 *
 * Po co: te funkcje tłumaczą surowe dane Dockera na to, co widzi człowiek —
 * powód padnięcia zadania, skrót digestu obrazu, gotowe komendy. Pomyłka tutaj
 * wysyła administratora w złe miejsce (albo pokazuje „brak nieudanych zadań”
 * przy usłudze, która właśnie się przewraca).
 *
 *   node scripts/ci/check_usluga.mts
 */

import {
  komendyDocker,
  linkPortainer,
  obrazBezDigestu,
  odKiedy,
  opisRestartow,
  opisZadania,
  skrotDigest,
} from '../../panel/src/lib/usluga.ts';

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

/* ---------------- digest i obraz ---------------- */

const OBRAZ =
  'ghcr.io/subscribe-it/vps-monitoring-discovery:main@sha256:4e5b75269473c68732895c037f4129d2b67d3caebcb0d799ef152913e1d77996';
// 12 znaków DOTYCZY skrótu hex (plus prefiks „sha256:”), żeby dało się go
// porównać z `docker service inspect` bez przewijania całego hasha.
rowne(skrotDigest(OBRAZ), 'sha256:4e5b75269473', 'digest: 12 znaków hex + prefiks');
ok(skrotDigest(OBRAZ)?.startsWith('sha256:'), 'digest: prefiks algorytmu zostaje (inaczej nie wiadomo, co to)');
rowne(skrotDigest('nginx:1.27'), null, 'digest: obraz bez digestu → null (nie zmyślamy wersji)');
rowne(skrotDigest(null), null, 'digest: brak obrazu → null');
rowne(skrotDigest(OBRAZ, 4), 'sha256:4e5b', 'digest: długość konfigurowalna');
rowne(obrazBezDigestu(OBRAZ), 'ghcr.io/subscribe-it/vps-monitoring-discovery:main', 'obraz: bez digestu');
rowne(obrazBezDigestu('  nginx:1.27  '), 'nginx:1.27', 'obraz: przycięte spacje');
rowne(obrazBezDigestu(''), '—', 'obraz: puste → kreska');
rowne(obrazBezDigestu(null), '—', 'obraz: null → kreska');

/* ---------------- komendy ---------------- */

const komendy = komendyDocker('jpolski_na6_pl_prod_wp-cron');
rowne(komendy.length, 3, 'komendy: trzy komendy diagnostyczne');
rowne(komendy[0]?.komenda, 'docker service ps jpolski_na6_pl_prod_wp-cron --no-trunc', 'komendy: najpierw powód padnięcia');
ok(
  komendy[1]?.komenda.includes('logs --tail 200'),
  'komendy: druga pokazuje logi (200 linii)',
);
ok(komendy[2]?.komenda.includes('inspect '), 'komendy: trzecia to pełny opis');
ok(
  komendy.every((k) => k.komenda.includes('jpolski_na6_pl_prod_wp-cron')),
  'komendy: każda dotyczy właściwej usługi',
);
ok(
  komendy.every((k) => !k.komenda.includes('rm ') && !k.komenda.includes('update') && !k.komenda.includes('scale')),
  'komendy: zero operacji zmieniających (panel jest tylko do odczytu)',
);
rowne(komendyDocker(null), [], 'komendy: bez nazwy usługi → pusta lista');
rowne(komendyDocker('   '), [], 'komendy: białe znaki → pusta lista');

/* ---------------- link do Portainera ---------------- */

const link = linkPortainer('https://portainer.subscribeit.pl/', 'monitoring_panel');
rowne(
  link,
  'https://portainer.subscribeit.pl/#!/1/docker/services?search=monitoring_panel',
  'Portainer: link z wyszukiwaniem usługi',
);
rowne(linkPortainer(null, 'x'), null, 'Portainer: brak bazy w API → brak linku (nie hardkodujemy)');
rowne(linkPortainer('https://p.pl', null), null, 'Portainer: brak usługi → brak linku');
rowne(linkPortainer('', 'x'), null, 'Portainer: pusta baza → brak linku');

/* ---------------- opis zadania ---------------- */

const odrzucone = opisZadania('rejected', 'No such image: coreruleset/modsecurity-crs:4.26.0-nginx-alpine');
rowne(odrzucone.stan, 'critical', 'zadanie: rejected to stan krytyczny');
ok(odrzucone.tekst.includes('odrzucone'), 'zadanie: tekst mówi o odrzuceniu');
ok(odrzucone.szczegol?.includes('No such image'), 'zadanie: powód z Dockera zachowany');

const padniete = opisZadania('failed', 'task: non-zero exit (137): dockerexec: unhealthy container');
rowne(padniete.stan, 'warning', 'zadanie: failed to ostrzeżenie');
ok(padniete.szczegol?.includes('unhealthy container'), 'zadanie: powód padnięcia zachowany');

const brak = opisZadania(null, null);
rowne(brak.stan, 'unknown', 'zadanie: brak danych → unknown (nie „ok”)');
rowne(brak.szczegol, null, 'zadanie: brak powodu → null');
ok(brak.tekst.includes('Brak nieudanych'), 'zadanie: tekst mówi wprost o braku danych');

rowne(opisZadania('failed', '   ').szczegol, null, 'zadanie: biały powód → null (bez pustego prostokąta)');
rowne(opisZadania('REJECTED', 'x').stan, 'critical', 'zadanie: stan bez rozróżniania wielkości liter');
rowne(opisZadania('shutdown', 'x').stan, 'warning', 'zadanie: inny nieudany stan też ostrzega');

/* ---------------- czas i restarty ---------------- */

const TERAZ = Date.UTC(2026, 8, 22, 18, 45, 0) / 1000;
rowne(odKiedy('2026-09-22T18:44:30Z', TERAZ), 'teraz', 'czas: poniżej minuty → „teraz”');
rowne(odKiedy('2026-09-22T18:15:00Z', TERAZ), '30 min temu', 'czas: minuty');
rowne(odKiedy('2026-09-22T15:45:00Z', TERAZ), '3 h temu', 'czas: godziny');
rowne(odKiedy('2026-09-20T18:45:00Z', TERAZ), '2 dni temu', 'czas: dni (liczba mnoga)');
rowne(odKiedy('2026-09-21T18:45:00Z', TERAZ), '1 dzień temu', 'czas: jeden dzień (liczba pojedyncza)');
rowne(odKiedy('bzdura', TERAZ), '—', 'czas: niepoprawna data → kreska');
rowne(odKiedy(null, TERAZ), '—', 'czas: brak daty → kreska');
rowne(odKiedy('2026-09-23T18:45:00Z', TERAZ), 'teraz', 'czas: data z przyszłości nie pokazuje ujemnych minut');

rowne(opisRestartow(0), 'brak w ostatniej godzinie', 'restarty: zero po ludzku');
rowne(opisRestartow(7), '7 w ostatniej godzinie', 'restarty: liczba');
rowne(opisRestartow(null), '—', 'restarty: brak danych → kreska');
rowne(opisRestartow(Number.NaN), '—', 'restarty: NaN → kreska');

if (bledy.length > 0) {
  console.error(`✗ obsługa usługi: ${bledy.length} z ${sprawdzen} sprawdzeń NIE przeszło:`);
  for (const blad of bledy) console.error(`  • ${blad}`);
  process.exit(1);
}
console.log(`✓ obsługa usługi: ${sprawdzen} sprawdzeń OK`);
