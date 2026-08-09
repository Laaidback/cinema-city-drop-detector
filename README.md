# Cinema City drop detector

Pilnuje repertuaru kin i wysyła powiadomienie na Telegram, gdy dla obserwowanego filmu pojawią
się nowe seanse. Obsługuje **Cinema City** i **Helios**.

Film można zawęzić do formatu lub sali: `attributes: [imax]` w Cinema City, `attributes: [dream]`
w Heliosie — to samo pojęcie w konfiguracji, mimo że sieci opisują to zupełnie inaczej.

- Co śledzić: `config.yaml`
- Projekt i uzasadnienia decyzji: `docs/superpowers/specs/`
- Plan implementacji: `docs/superpowers/plans/`
- Uruchamianie: cron na VPS, okno wokół pełnej godziny (`deploy/README.md`).
  Workflow GitHub Actions jest **wyłączony celowo** — dwie instancje wysyłałyby wszystko podwójnie
- Wdrożenie na VPS z oknem wokół pełnej godziny: `deploy/README.md`
