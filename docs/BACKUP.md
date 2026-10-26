# Backup danych Portainera przez Duplicati

Stack `monitoring` uruchamia jedną usługę `monitoring_duplicati`. Usługa:

- montuje tylko `/var/lib/docker/volumes`, `/var/lib/docker/swarm` i `/etc/docker` jako `:ro`;
- obejmuje dane wszystkich nazwanych wolumenów używanych przez stacki, w tym `portainer_portainer_data`, dane RustFS i dane aplikacji;
- nie obejmuje warstw obrazów, logów kontenerów ani całego systemu plików;
- zapisuje lokalny stan w `monitoring_duplicati_data_v2`;
- wykonuje szyfrowany backup co 24 godziny;
- zapisuje obiekty do `s3://ovh1backup/vps/portainer-volumes` przez Cloudflare R2;
- nie publikuje portu i nie tworzy routera Traefika.

Obraz jest przypięty digestem. Zmiana obrazu wymaga osobnego przeglądu i testu
odtworzenia.

## Sekrety Swarma

Przed redeployem stacka utwórz trzy sekrety na managerze Swarma. Wartości nie
trafiają do repozytorium, pliku env ani logów:

```bash
docker secret create monitoring-duplicati-secretprovider-v1 ./duplicati-secrets.json
docker secret create monitoring-r2-access-v1 ./r2-access-key
docker secret create monitoring-r2-secret-v1 ./r2-secret-key
```

`duplicati-secrets.json` ma format:

```json
{
  "s3-user": "ACCESS_KEY_ID",
  "s3-pass": "SECRET_ACCESS_KEY",
  "backup-passphrase": "dlugie-losowe-haslo-backupu"
}
```

Pliki tymczasowe z kluczami usuń po utworzeniu sekretów. Klucz R2 musi mieć
prawo zapisu i odczytu obiektów w `ovh1backup`; osobny klucz tylko do odczytu
można stosować dla `health-ping`, ale wtedy nazwa sekretu w env musi wskazywać
na ten klucz.

## Wdrożenie

1. W Portainerze dodaj sekrety do endpointu `primary` i sprawdź, że ich nazwy
   odpowiadają `env.portainer.example`.
2. Ustaw niesekretne zmienne R2 oraz `BACKUP_SERVICE=monitoring_duplicati`.
3. Wykonaj redeploy tylko stacka `monitoring` z repozytorium Git.
4. Sprawdź zadanie:

```bash
docker service ps monitoring_duplicati
docker service logs --tail 200 monitoring_duplicati
```

Pierwszy udany przebieg musi zawierać linię `[duplicati] backup complete`.
Watchdog dodatkowo listuje obiekty R2 pod `vps/portainer-volumes/`; sam log nie jest dowodem
istnienia kopii.

## Odtworzenie i drill

Do odtworzenia potrzebne są: nowy host, obraz Duplicati, `backup-passphrase`,
klucze R2 oraz plik secret providera. Najpierw odtwórz pojedynczy plik do
katalogu testowego, potem wykonaj pełny drill na czystym wolumenie:

```bash
/opt/duplicati/duplicati-cli restore \
  's3://ovh1backup/vps/portainer-volumes?aws-access-key-id=$s3-user&aws-secret-access-key=$s3-pass&s3-server-name=3d399a03e559532edbd9380548e1426e.r2.cloudflarestorage.com&use-ssl=true&s3-client=minio' \
  '*' --restore-path=/restore-drill \
  --secret-provider=file-secret:///run/secrets/duplicati-secretprovider \
  '--passphrase=$backup-passphrase'
```

Po drillu zapisz datę w pliku monitoringu `restore-test.json`; do czasu
pierwszego potwierdzonego drill'a health-ping powinien raportować brak testu
odtworzenia jako stan niegotowy do produkcji.

## Granice spójności

Backup systemu plików działa best-effort (`--ignore-advisory-locking=true`).
Duplicati zaleca snapshot LVM dla spójnego punktu w czasie. Bazy danych i inne
usługi stanowe muszą mieć własny logiczny dump, który również należy objąć
backupem i okresowym testem odtworzenia. Bez tego nie oznaczamy VPS jako
produkcyjnie gotowego do pełnego disaster recovery.
