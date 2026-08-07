# Wdrożenie na VPS (Debian / Ubuntu)

Timer systemd budzi detektor na początku każdej minuty. To, czy minuta jest „robocza”, decyduje
sekcja `schedule` w `config.yaml` — poza oknem proces kończy się natychmiast z kodem 0, bez
jednego zapytania HTTP i bez dotykania pliku stanu.

Wszystkie polecenia uruchamiaj jako `root` (albo poprzedź `sudo`).

## 1. Pakiety

```bash
apt update
apt install -y git python3 python3-venv
```

## 2. Użytkownik systemowy

```bash
useradd --system --home-dir /opt/ccdrop --shell /usr/sbin/nologin ccdrop
```

## 3. Kod i virtualenv

```bash
git clone <adres-repozytorium> /opt/ccdrop
python3 -m venv /opt/ccdrop/.venv
/opt/ccdrop/.venv/bin/pip install --upgrade pip
/opt/ccdrop/.venv/bin/pip install -e /opt/ccdrop
chown -R ccdrop:ccdrop /opt/ccdrop
```

## 4. Katalog stanu

```bash
install -d -o ccdrop -g ccdrop -m 750 /var/lib/ccdrop
```

## 5. Konfiguracja i okno czasowe

Sekcja `schedule` w `/opt/ccdrop/config.yaml` jest opcjonalna. Bez niej każde uruchomienie
wykonuje pełny cykl — dlatego to samo repozytorium dalej działa na GitHub Actions.

```yaml
schedule:
  hours: [8, 22]
  before: 2
  after: 3
```

Powyższe ustawienia dają okna 07:58–08:03, 08:58–09:03, …, 21:58–22:03. Godziny są zawsze
liczone w strefie `Europe/Warsaw`, niezależnie od strefy czasowej VPS-a, więc zmiana czasu
letni/zimowy nie przesuwa okien.

Ograniczenia: `hours` to dwie liczby 0–23, początek nie może być większy od końca, `before`
i `after` nie mogą być ujemne, a ich suma musi być mniejsza niż 59 (inaczej okna nachodziłyby
na siebie).

## 6. Sekrety

```bash
install -d -o root -g root -m 755 /etc/ccdrop
cat > /etc/ccdrop/ccdrop.env <<'EOF'
TELEGRAM_BOT_TOKEN=wklej-token-bota
TELEGRAM_CHAT_ID=wklej-id-czatu
EOF
chown root:root /etc/ccdrop/ccdrop.env
chmod 600 /etc/ccdrop/ccdrop.env
```

`EnvironmentFile` czyta systemd jako root, zanim zrzuci uprawnienia do użytkownika `ccdrop`,
więc plik nie musi być czytelny dla nikogo poza rootem.

## 7. Instalacja unitów

```bash
cp /opt/ccdrop/deploy/ccdrop.service /etc/systemd/system/ccdrop.service
cp /opt/ccdrop/deploy/ccdrop.timer /etc/systemd/system/ccdrop.timer
systemctl daemon-reload
systemctl enable --now ccdrop.timer
```

Timer sam włącza usługę — `ccdrop.service` zostaje wyłączony (`Type=oneshot`), nie trzeba go
`enable`ować osobno.

## 8. Weryfikacja

```bash
systemctl start ccdrop.service     # jednorazowy przebieg na żądanie
systemctl list-timers ccdrop.timer # kiedy najbliższe uruchomienie
journalctl -u ccdrop -n 50         # ostatnie przebiegi
journalctl -u ccdrop -f            # podgląd na żywo
```

Poza oknem w logu zobaczysz jedną linię `INFO ... poza oknem harmonogramu, cykl pominięty`.
Podgląd bez wysyłki (również respektuje okno):

```bash
sudo -u ccdrop /opt/ccdrop/.venv/bin/python -m ccdrop.main \
  --state-dir /var/lib/ccdrop --dry-run
```

## 9. Wyłącz GitHub Actions — obowiązkowe

Gdy VPS zacznie działać, **wyłącz workflow na GitHubie**. Dwie instancje mają osobne pliki stanu,
więc każda wykryje ten sam drop niezależnie i **obie wyślą powiadomienie** — dostaniesz wszystko
podwójnie. Do tego runner nadal commitowałby stan na gałąź `state`, co przy braku VPS-a w tej
gałęzi tylko myli.

W repozytorium: `Actions` → `check` → menu `···` → **Disable workflow**.

Sekcja `schedule` w `config.yaml` sama nie wystarczy. Ucisza runner niemal całkowicie, bo
nieregularnie dostarczany cron rzadko trafia w sześciominutowe okno — ale „niemal" znaczy, że
czasem trafi i wyśle duplikat.

## 10. Aktualizacja

```bash
git -C /opt/ccdrop pull
/opt/ccdrop/.venv/bin/pip install -e /opt/ccdrop
chown -R ccdrop:ccdrop /opt/ccdrop
systemctl restart ccdrop.timer
```

## 11. Wyłączenie

```bash
systemctl disable --now ccdrop.timer
```
