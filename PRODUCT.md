# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Główny odbiorca:** operator serwera (właściciel panelu) — jedna osoba, która
pilnuje VPS-a z produkcją kilku klientów i wchodzi do panelu, gdy coś się dzieje
albo gdy chce sprawdzić stan „na spokojnie”.

**Odbiorca wtórny (potwierdzony przez użytkownika):** zespół i klienci — panel
bywa pokazywany osobom trzecim, nierzadko na udostępnianym ekranie albo przy
kliencie obok. To nie jest widok prywatnych notatek: liczby, nazwy i komunikaty
muszą być zrozumiałe bez tłumaczenia ich przez autora.

**Sytuacja użycia:** 13-calowy laptop jako podstawowy ekran, często w jasnym
pomieszczeniu (biuro, spotkanie) i wieczorem; przeglądarka w trybie zgodnym
z ustawieniem systemu. Telefon jako awaryjny podgląd.

## Product Purpose

Panel daje **jeden uczciwy obraz tego, co dzieje się na serwerze**: usługi i ich
stany, host, certyfikaty, backup, alerty, bezpieczeństwo oraz ruch i logi —
w jednym miejscu, bez wchodzenia do Grafany czy Portainera.

Sukces: osoba patrząca na panel **w kilka sekund wie, czy coś jest nie tak,
co konkretnie i od kiedy** — a gdy nic nie jest nie tak, nie ma wątpliwości, że
dane są świeże i kompletne.

## Positioning

Panel **nigdy nie udaje wiedzy, której nie ma**: brak danych to `unknown`
i „—”, nie zero i nie zielony. Zamiast samego koloru pokazuje **powód**
(treść błędu zadania z Dockera, realne linie logu, zużycie względem limitu,
„od kiedy trwa problem”). Sąsiednie narzędzia pokazują metrykę; ten panel
pokazuje metrykę razem z jej wiarygodnością.

## Operating Context

- Jeden VPS (Ubuntu, single-node Docker Swarm) — na nim monitoring w 12 usługach
  oraz **cudze, produkcyjne stacki klientów**, których nie wolno dotykać.
- Panel jest **tylko do odczytu**: żadnych restartów, skalowań ani zmian
  w cudzych stackach z poziomu UI.
- Dane: `/status/api.json` (nasz agregat), Prometheus (metryki), Loki (logi).
  Narzędzia zewnętrzne (Grafana, Prometheus, Alertmanager, Portainer, Cockpit)
  są osadzane w ramkach lub otwierane w nowej karcie.
- Praca odbywa się po polsku; interfejs, komunikaty i jednostki są polskie.
- Panel stoi za uwierzytelnianiem (Traefik ForwardAuth) i bywa otwierany
  równolegle z rozmową z klientem — nie może migać, przeskakiwać ani „myśleć”
  przy wejściu.

## Capabilities and Constraints

- Routing hashowy (`#/`, `#/wykresy/...`, `#/logi/...`, `#/tool/<id>`), jeden
  skrypt kliencki, zero frameworka po stronie przeglądarki.
- Zero zasobów z internetu: brak CDN, brak webfontów (tylko stosy systemowe),
  ikony jako wbudowany sprite SVG.
- Słownik stanów: `ok` | `warning` | `critical` | `unknown` | `disabled`.
- Nazwy `data-role` są globalnie unikalne; treści wstawiane wyłącznie przez
  `textContent` (żadnego `innerHTML` z danych).
- Motyw: **pełne wsparcie trybu jasnego i ciemnego zgodnie z ustawieniem
  systemu** (`prefers-color-scheme`), w całym panelu, bez migotania przy starcie.
- Ograniczenie techniczne: akceptowalny kontrast WCAG AA w obu motywach,
  tap targety ≥ 24 px, respektowane `prefers-reduced-motion`.

## Brand Commitments

- Nazwa i ton: **rzeczowy konsola operatorska**, nie produkt marketingowy —
  etykiety nazywają działanie, komunikaty nazywają problem i wyjście z niego.
- Język: polski, terminologia zgodna z resztą repo („usługa”, „stack”,
  „zadanie”, „odświeżenie”).
- Bez logo i bez materiałów graficznych do użycia (żadne nie istnieją).

## Evidence on Hand

- Realne dane produkcyjne: 12 usług monitoringu, ~47 usług w 9 stackach,
  metryki Prometheusa, logi Loki, access log Traefika.
- Historia incydentów, które ukształtowały produkt (opisana w repo): puste
  wdrożenie raportowane jako sukces, brak alertu przy padniętej bazie, logi
  odrzucane przez Lokiego, etykieta `stack` pusta przez zły `source_labels`.
- **Czego nie ma i nie wolno wymyślać:** testimoniale, benchmarki, dane
  o klientach, zrzuty ekranu produktu, cennik.

## Product Principles

1. **Nie kłam stanem.** Brak danych to `unknown` i „—”; zero pojawia się tylko
   wtedy, gdy naprawdę zmierzono zero.
2. **Kolor to skrót, powód to treść.** Obok stanu zawsze miejsce na konkret:
   treść błędu, linię logu, wartość względem limitu, czas trwania.
3. **Odczyt, nie sterowanie.** Panel opisuje rzeczywistość; zmiany robi człowiek
   świadomie, poza panelem.
4. **Działa bez sieci i bez ozdób.** Żadnych zewnętrznych zasobów; wszystko, co
   widać, pochodzi z naszego stacku.
5. **Czytelny w cudzej obecności.** Układ, kontrast i język muszą bronić się
   także wtedy, gdy panel widzi klient, a nie autor.

## Accessibility & Inclusion

- Kontrast tekstu ≥ 4,5:1 (duży tekst ≥ 3:1) w **obu** motywach — ciemnym
  i jasnym; osie i linie wykresów ≥ 3:1 wobec tła karty.
- Pełna obsługa klawiatury: `/` (filtr), `Esc`, strzałki na wykresach, widoczny
  pierścień fokusu.
- `prefers-reduced-motion` wyłącza animacje; `prefers-color-scheme` wybiera
  motyw bez JavaScriptu i bez migotania (First Paint już w docelowym motywie).
- Tap targety ≥ 24 px (na telefonie ≥ 44 px tam, gdzie to możliwe).
