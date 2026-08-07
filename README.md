# Cinema City drop detector

Pilnuje repertuaru Cinema City i wysyła powiadomienie na Telegram, gdy dla obserwowanego filmu
pojawią się nowe seanse.

- Co śledzić: `config.yaml`
- Projekt i uzasadnienia decyzji: `docs/superpowers/specs/`
- Plan implementacji: `docs/superpowers/plans/`
- Uruchamianie: GitHub Actions, cron `*/15` (GitHub dostarcza realnie ok. raz na 2 h),
  stan na gałęzi `state`
- Wdrożenie na VPS z oknem wokół pełnej godziny: `deploy/README.md`
