# Qt main application and Windows release

User explicitly approved: save current working project in Git, make Qt the default,
remove Tkinter code, keep old checkpoints safe, build executable and installer.
Continue directly in this checkout on codex/qt-main-release.

- [x] Save all working source in Git commit 136e7ae, backup branch
      codex/backup-before-qt-main-20261113 and tag backup/pre-qt-main-2026-11-13.
- [x] Make consistent read-only SQLite backups outside the repository. Preserve
      original legacy/Qt checkpoint and preference directories; do not migrate,
      delete or include student data in Git or distribution files.
- [x] Add launcher smoke/report regression test before changing entry point.
- [x] Make checker.py launch Qt; remove Tk UI/widgets/tests, Legacy and obsolete
      prototype source. Keep shared backend and Qt workflow/mock tests. Use a clean
      root .venv with Qt and backend dependencies only; update launch scripts/docs.
- [x] Bundle QML, Qt runtime/plugins, subject catalogue and Selenium Manager using
      PyInstaller. Include third-party licence notices. Bump version to 0.3.0.
- [x] Update per-user Inno Setup installer. Keep the AppId/install path for upgrade;
      remove only obsolete installed payload on upgrade, never any app-data folder.
- [x] Run retained backend and Qt tests; build EXE; verify relocated bundle starts
      with isolated app-data and no source checkout dependencies. Run a packaged
      offline collection/export test and verify results.
- [x] Compile installer, test isolated install/launch/uninstall; ensure checkpoint
      directories remain unchanged. Record hashes, sizes and remaining clean-machine
      limitations. Review changes, commit the completed release source.

Rulings: reuse this checkout as requested; no extra worktree. Use one-folder EXE
bundle plus installer for reliable QML/plugin loading. Keep Qt's existing app-data
namespace so the user's tested progress continues working. Preserve legacy progress
in place and a consistent local backup; recovery source is available at the tag.
## Verification record

- Git backup commit/tag/branch were created before removing the legacy interface.
  Two consistent SQLite backups were saved outside the repository. Original
  checkpoint and preference hashes remain unchanged after installer/uninstaller tests.
- All 60 source tests pass in the clean root environment without CustomTkinter.
- Rebuilt the EXE, portable ZIP and installer with the requested purple graduation
  cap. Confirmed all seven embedded EXE icon frames and runtime/ZIP icon bytes.
- Relocated bundle and installed application passed startup, bundled Selenium
  Manager execution, and complete 1,500-row stop/export/resume/export verification.
- Final installer test used a separate product identity. It removed stale Tk
  runtime files, preserved a user-owned file, and uninstalled cleanly without
  changing original checkpoints/preferences. No live student lookup was performed.
- Fixed a smoke-report failure hang with regression tests. Restricted build PATH
  after proving that a foreign ICU DLL caused a bundled QtCore import failure.
- Static review found no remaining important issues. The local user archive was
  excluded from the source commit. Previously tracked Python bytecode was removed
  from the index; the existing ignore rule now keeps it out.
- Remaining external acceptance: unsigned builds need a clean Windows machine
  installation and a small real collection test before public release.
