# Batch 20 — Safe `None` and `print` transformations

Base source: GitHub `iigi71944/capstone_main`, `main` commit `5785c7f` (19th batch).

This ZIP **does not overwrite project sources during extraction**. It extracts only a new installer and three `.source` payloads under `backend/tools`. The installer then checks all anchors before making changes.

## What changes

- `None 사용`: limited to top-level `result = {}.get(<str/int/bool literal>)` → `result = None`. Dynamic keys, non-empty dictionaries, default arguments, nested statements and multiline spans are skipped.
- `print 사용`: limited to top-level direct `builtins.print(...)` after a unique prior `import builtins` → `print(...)`. Static shadowing/rebindings, wildcard imports and dynamic global access are skipped.
- Plan selection requires evidence in existing saved style metrics and candidate target metrics; it never runs merely because a tag was missing.
- No changes to frontend, saved-style JSON schema, code indentation/line-break features or stdin function verification.

## PowerShell setup (run from `capstone_main`)

```powershell
Expand-Archive -LiteralPath ".\capstone_batch20_20261116_windows_safe.zip" -DestinationPath "." -Force
python backend\tools\install_batch20.py --check
python backend\tools\install_batch20.py
```

### Tests

```powershell
docker compose run --rm backend python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm backend python tools/audit_transform_batch20.py --output transform_audit_batch20.json
```

Expected audit targets (not yet tested in your Docker environment): **102 listed conversion tags, 82 linked, 20 comparison-only, 246/246 representative cases**. The 31 new unittest cases should bring the prior 1,807 cases to approximately 1,838.

## Safety and rollback

The installer stops before modifying files when the expected Batch 19 source anchors or payloads are absent, or any file is partially installed. Existing project files are backed up beneath `.git/capstone_batch20_backups/`; a failed write triggers restoration. The installer is idempotent.

These syntactic changes do not prove general execution equivalence. Existing runtime verification and source restoration remain responsible for detecting differences at the supported observation points. Do not run untrusted source without an isolated sandbox.

## File changes

**Modified after installation:**

- `backend/app/services/style_tag_transform_map_service.py`
- `backend/app/services/style_transform_plan_service.py`
- `backend/app/services/style_apply_service.py`

**Added after installation:**

- `backend/app/services/improvement/safe_batch20_service.py`
- `backend/tests/test_style_batch20_new_links.py`
- `backend/tools/audit_transform_batch20.py`

The package also contains the installer and its 3 payload source files.
