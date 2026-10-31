# Garage Tracker (22RE tracker)

Offline-first maintenance tracker PWA for multiple vehicles: checklists, per-item dated notes, a specs store, parts reference, maintenance log, diagnostics, and import/export. Live: https://mw26r28kdm-arch.github.io/22re-tracker/

## Data storage
All data lives on the device in IndexedDB database `tracker22re`, object store `kv`, key `state`: one garage object `{version:3, activeVehicleId, vehicles:[...], specs:[...], ui}`.
- Notes: `vehicles[].sections[].items[].noteLog = [{id, text, postedAt, editedAt?}]` (the older single `notes` field on each item is kept unchanged).
- Specs: top-level `specs = [{id, vehicleId, topic, name, value, unit, notes, taskIds[], createdAt, updatedAt}]`.
- Export: "garage" = the same object (minus `ui`); "vehicle" = `{version:3, vehicleId, info, sections, log, cases, tests, parts, mileageLog, specs}`. Older exports without notes/specs still import.

## Tests
```
pip install playwright && python -m playwright install chromium
python tests/smoke.py                                   # local (serves this folder)
BASE_URL=https://mw26r28kdm-arch.github.io/22re-tracker/ python tests/smoke.py   # live
```
Optional: `CHROME_PATH=/usr/bin/google-chrome` to use an installed Chrome, `SCREENS=dir` to save screenshots. Exits non-zero on any failure.
