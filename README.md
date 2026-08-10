# Cinema City drop detector

Pilnuje repertuaru kin i wysyła powiadomienie na Telegram, gdy dla obserwowanego filmu pojawią
się nowe seanse. Obsługuje **Cinema City** i **Helios**.

Film można zawęzić do formatu lub sali: `attributes: [imax]` w Cinema City, `attributes: [dream]`
w Heliosie — to samo pojęcie w konfiguracji, mimo że sieci opisują to zupełnie inaczej.

Wpis z `notify: false` jest tylko obserwowany: przechodzi przez wykrywanie i trafia do `drop_log`
(pole `notified`), ale nie wysyła nic. Służy do pomiaru godzin, o których kina publikują
repertuar — `tools/drop_hours.py` liczy obie grupy osobno.

- Co śledzić: `config.yaml`
- Projekt i uzasadnienia decyzji: `docs/superpowers/specs/`
- Plan implementacji: `docs/superpowers/plans/`
- Wdrożenie i uruchamianie: cron na VPS (Alpine, bez systemd) — `deploy/README.md`.
  Teraz tryb pomiarowy co minutę, docelowo okno wokół pełnej godziny.
  Workflow GitHub Actions jest **wyłączony celowo** — dwie instancje wysyłałyby wszystko podwójnie
