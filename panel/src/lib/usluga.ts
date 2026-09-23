/**
 * Obsługa usługi w panelu — **tylko do odczytu**.
 *
 * Panel nie restartuje, nie skaluje i nie usuwa niczego na produkcji: pokazuje
 * stan i daje gotowe komendy do skopiowania, żeby człowiek wykonał je sam
 * (świadomie, z SSH). To decyzja o bezpieczeństwie, nie brak funkcji — panel
 * ma poświadczenia do Dockera, więc Operacje „jednym klikiem” byłyby zbyt
 * łatwe do przypadkowego kliknięcia o 3 w nocy.
 *
 * Moduł jest samowystarczalny (zero importów), więc testuje go Node bez DOM-u:
 * `node scripts/ci/check_usluga.mts`.
 */

const DASH = '—';

/** Znaczenie stanu zadania dla panelu (kolory kropek). */
export type StanZadania = 'critical' | 'warning' | 'unknown';

/**
 * Skrót digestu obrazu: `ghcr.io/x/y:tag@sha256:abcdef…` → `sha256:abcdef…`.
 *
 * W Swarmie obrazy są przypięte po digestcie, więc to jedyny pewny
 * identyfikator wersji, jaka naprawdę działa — sam tag `:main` bywa mylący
 * (na węźle może leżeć starszy obraz pod tym samym tagiem).
 */
export function skrotDigest(obraz: string | null | undefined, dlugosc = 12): string | null {
  const dopasowanie = /@(sha256:[0-9a-f]+)/i.exec(obraz ?? '');
  const digest = dopasowanie?.[1];
  if (!digest) return null;
  return `${digest.slice(0, 7 + dlugosc)}`;
}

/** Repozytorium + tag bez digestu — czytelniejszy podpis obok skrótu. */
export function obrazBezDigestu(obraz: string | null | undefined): string {
  const czysty = (obraz ?? '').split('@')[0]?.trim() ?? '';
  return czysty.length > 0 ? czysty : DASH;
}

export interface KomendaDocker {
  /** Krótki opis, po co ta komenda. */
  opis: string;
  /** Gotowa komenda do wklejenia (bez `sudo` — panel nie wie, jak wchodzisz na host). */
  komenda: string;
}

/**
 * Komendy diagnostyczne dla usługi. Kolejność jest świadoma: najpierw „dlaczego
 * padło” (`ps --no-trunc` pokazuje błąd zadania), potem logi, na końcu pełny
 * opis konfiguracji.
 */
export function komendyDocker(fullName: string | null | undefined): KomendaDocker[] {
  const nazwa = (fullName ?? '').trim();
  if (!nazwa) return [];
  return [
    { opis: 'Zadania i powód padnięcia', komenda: `docker service ps ${nazwa} --no-trunc` },
    { opis: 'Ostatnie logi kontenera', komenda: `docker service logs --tail 200 ${nazwa}` },
    { opis: 'Pełna konfiguracja (limity, obrazy, sieci)', komenda: `docker service inspect ${nazwa}` },
  ];
}

/**
 * Link do Portainera. Bazę bierzemy z API (`tools[].url`), więc panel nie
 * hardkoduje cudzej domeny; brak narzędzia = brak linku (nie zmyślamy adresu).
 */
export function linkPortainer(baza: string | null | undefined, fullName: string | null | undefined): string | null {
  const korzen = (baza ?? '').trim().replace(/\/+$/, '');
  const nazwa = (fullName ?? '').trim();
  if (!korzen || !nazwa) return null;
  return `${korzen}/#!/1/docker/services?search=${encodeURIComponent(nazwa)}`;
}

/** Opis ostatniego nieudanego zadania — dosłowna przyczyna z Dockera. */
export function opisZadania(
  stan: string | null | undefined,
  blad: string | null | undefined,
): { tekst: string; stan: StanZadania; szczegol: string | null } {
  const szczegol = (blad ?? '').trim() || null;
  const nazwaStanu = (stan ?? '').trim().toLowerCase();
  if (nazwaStanu === 'rejected') {
    return {
      tekst: 'Zadanie odrzucone przez Swarm',
      stan: 'critical',
      szczegol,
    };
  }
  if (nazwaStanu === 'failed') {
    return { tekst: 'Ostatnie zadanie padło', stan: 'warning', szczegol };
  }
  if (nazwaStanu) {
    return { tekst: `Ostatni nieudany stan: ${nazwaStanu}`, stan: 'warning', szczegol };
  }
  return { tekst: 'Brak nieudanych zadań w pamięci Dockera', stan: 'unknown', szczegol: null };
}

/** Kiedy zaktualizowano usługę — po polsku i bez kłamania przy braku danych. */
export function odKiedy(iso: string | null | undefined, terazSekundy: number): string {
  const znacznik = Date.parse(iso ?? '');
  if (!Number.isFinite(znacznik)) return DASH;
  const roznica = Math.max(0, Math.floor(terazSekundy - znacznik / 1000));
  if (roznica < 60) return 'teraz';
  const minuty = Math.floor(roznica / 60);
  if (minuty < 60) return `${minuty} min temu`;
  const godziny = Math.floor(minuty / 60);
  if (godziny < 24) return `${godziny} h temu`;
  const dni = Math.floor(godziny / 24);
  return `${dni} ${dni === 1 ? 'dzień' : 'dni'} temu`;
}

/** Liczba restartsów w czytelnej formie (z ostrzeżeniem, gdy realnie się sypie). */
export function opisRestartow(restarty: number | null | undefined): string {
  if (typeof restarty !== 'number' || !Number.isFinite(restarty)) return DASH;
  if (restarty <= 0) return 'brak w ostatniej godzinie';
  return `${restarty} w ostatniej godzinie`;
}
