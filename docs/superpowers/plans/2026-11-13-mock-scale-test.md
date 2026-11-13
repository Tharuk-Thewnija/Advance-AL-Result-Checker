# Local mock scale test

User approved a separate test mode: 1,500 fictional students, simulated delays,
missing subjects and errors; real Qt UI, workbook import, parsing, checkpoints,
stop/resume and Excel export. No examination website requests or generated NICs
submitted to any service. Preserve both normal launchers and the old prototype.

Approach: inject an offline collector into the Qt controller. It produces synthetic
result-card text and uses the shared parser/checkpoint interfaces. Mock NIC values
are deliberately invalid for live collection. A separate process-local mock-data
namespace contains generated inputs, checkpoints, exports and performance reports.
Show a persistent MOCK TEST label; disable changing the input file in this mode.
Normal collection keeps its existing backend and app-data namespace.

- [x] Write failing tests for deterministic data/outcomes, no browser/network,
      stop/resume, skip, missing subjects, invalid rows, and 1,500-row export accuracy.
- [x] Implement offline data generator/collector, injection and isolated mock launcher.
- [x] Show mock status and session CPU/RAM/UI-event-gap diagnostics; save report on close.
- [x] Run a visible 1,500-row benchmark through the real QML view, including stop,
      partial export, resume, window changes and final Excel verification.
- [x] Run all Qt and original tests; verify baseline original files unchanged;
      document launch and the distinction between simulated and live performance.

Direct execution continues under the user's prior instruction. No live student
lookups or irreversible changes are needed. Tests replace only the collector in
mock mode; this scale test does not measure Selenium/network/CAPTCHA overhead.


## Verification record

- Original suite: 52 tests passed; original 16 source/config/catalogue files and
  their 16 snapshot copies still match the saved SHA-256 manifest.
- Qt suite: 21 tests passed, including offline data generation, exact 1,500-row
  results, unchanged source, stop/resume, skip, missing grades and storage isolation.
- Final visible benchmark: .superpowers/mock-scale-1500-final/benchmark-report.json.
  All 1,500 rows exported: 1,455 completed, 30 skipped, 15 simulated errors; 64
  completed ICT grades missing intentionally, 1,391 nonblank ICT grades. Stop at
  113 rows, partial export, resume, final export and row order all verified.
- Sampled process RAM peak 231.95 MiB. CPU normalized across 16 logical CPUs 4.55%
  average. Window frame submission samples 26.88–35.21 ms. Largest heartbeat gap
  361.07 ms matched first-frame time 361.10 ms; collection max gap 91.20 ms.
  These are local simulated measurements, not live scraping performance.
- Manual UI check: normal-delay mock run started, progressed past 100 rows, stopped,
  window closed and report saved, with persistent mock labels and visible metrics.
  It used .superpowers/mock-ui-sandbox, separate from the user's mock workspace.
- Review: no safety/data-integrity blockers. Corrected the mock startup count after
  a failing regression test; clarified monitor scope and approximate phase labels.
- Existing app/prototype and user changes remain uncommitted and available.
