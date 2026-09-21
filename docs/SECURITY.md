# Bezpieczeństwo — co jest publiczne i co z tym robimy

## Stan

Repozytorium `subscribe-it/vps-monitoring` jest **publiczne** (decyzja właściciela,
2026-09-21). To nie wyciek poświadczeń, ale **publiczna mapa infrastruktury** —
i trzeba o tym wiedzieć, żeby podejmować świadome decyzje.

## Co zostało sprawdzone

Skan pełnej historii gita (62 commity, wszystkie gałęzie) i całego drzewa:

| Wzorzec | Wynik |
| --- | --- |
| Klucze prywatne (PEM), klucz prywatny age | 0 |
| Tokeny GitHub, klucze AWS, tokeny botów | 0 |
| Hasła wprost, klucze R2/S3 | 0 |
| Hashe htpasswd | tylko placeholdery testowe i przykłady w dokumentacji |
| Identyfikatory webhooków | 1 — **martwy** (Portainer zwraca 404) |

GitHub potwierdza to samo: **0 alertów secret scanning, 0 alertów Dependabota**.

## Co jest włączone w repozytorium

- **Secret scanning** i **push protection** — przyszły commit z sekretem zostanie zablokowany.
- **Dependabot security updates** (alerty + aktualizacje bezpieczeństwa).
- **PR-y z forków wymagają zatwierdzenia** od wszystkich zewnętrznych autorów —
  `Validate` uruchamia kod z PR-a na runnerze, więc to istotne.
- Domyślne uprawnienia `GITHUB_TOKEN`: **read**.

Nie udało się włączyć `validity checks` i `non-provider patterns` (funkcje płatnego planu).

## Co jest publiczne, choć nie powinno być „łatwe do znalezienia"

Repozytorium wymienia z nazwy: domeny produkcyjne i stagingowe, 10 stacków i ich usługi,
adres IP hosta, port SSH (2222), fakt że **Cockpit (9090)** i **Portainer (9443)** są
wystawione do internetu, nazwy usług backupu i wolumenów, a `docs/BASELINE.md` listuje,
co jest dziś zepsute.

**Wniosek: powierzchnia ataku się nie zmieniła — zmieniła się jej widoczność.**

## Lista utwardzeń (priorytet malejąco)

| Priorytet | Co | Dlaczego |
| --- | --- | --- |
| **1** | Ogranicz **Cockpit (9090)** do swojego IP / tunelu SSH | panel z uprawnieniami roota, publicznie i teraz łatwy do znalezienia |
| **2** | Potwierdź, że **SSH przyjmuje wyłącznie klucze** (`PasswordAuthentication no`) | fail2ban działa (53 bany), ale hasła nie powinny być w ogóle możliwe |
| **3** | Rozważ ograniczenie **Portainera (9443/9000)** do swojego IP | panel administracyjny |
| **4** | Ustaw **Dependabot alerts** jako obserwowane (maile) | panel ma drzewo npm |
| **5** | Przejrzyj `docs/BASELINE.md` pod kątem „co jeszcze warto zabrać z repo" | np. nazwy stacków można wynieść do env |

## Czego nie wolno wkładać do tego repozytorium

- żadnych wartości z `env.portainer.example` poza placeholderami,
- ping URL-i healthchecks.io (to sekrety — kto je zna, ten uciszy alarm),
- tematu i tokenu ntfy, danych SMTP, hasła Grafany, hasha htpasswd,
- kluczy R2, klucza prywatnego age, tokenów GitHub i Portainera.

Wszystkie te wartości żyją **wyłącznie** w zmiennych środowiskowych stacka w Portainerze.

## Gdyby kiedyś trzeba było zrotować

1. Zmień wartość w Portainerze (env stacka `monitoring`) i zapisz stack — usługa podniesie się z nową wartością.
2. Dla webhooka: Portainer → stack → Webhooks → usuń i dodaj nowy, potem zaktualizuj sekret w GitHubie.
3. Dla htpasswd: wygeneruj nowy hash i podmień `PANEL_AUTH_PASSWORD_HTPASSWD` (bez przebudowy obrazów).
