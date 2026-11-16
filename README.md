# Capstone Batch 19 - Remove strict-verification checkbox; link safe transformations

Target: `iigi71944/capstone_main`, based on GitHub commit `8a1001e` plus the locally installed Batch 16/17/18 patches.

## Changes

1. **Remove frontend strict-verification checkbox, explanatory panel, and local state** from `frontend/components/sections/StyleApplySection.tsx`. Existing `handleApplyStyle` invocation explicitly passes `false` (legacy/default behavior). The backend strict API option is retained for API compatibility. Function test input fields, including per-case stdin, are unchanged.
2. Link previously comparison-only syntax tags **`함수 호출`** and **`비교 연산`** to real transformations.
   - `함수 호출`: reuses existing `create_safe_operator_call` (a directly imported `operator` module and constrained arithmetic assignment expression).
   - `비교 연산`: converts `operator.eq/ne/lt/le/gt/ge(<primitive literal>, <primitive literal>)` into corresponding comparison expressions, only in direct module-level single-variable assignments with a unique prior `import operator`, without textual rebindings. Source comments and CRLF are preserved; ambiguous cases are left unchanged.
3. Gate the two new actions by previously saved style metrics and target metrics; no changes to saved style schema or frontend syntax tag filter.
4. Update the Batch 13 registry regression assertion to allow later additions while still checking unique keys and total 102 registered tags.
5. Add dedicated positive triplets (3 each), safety tests, and a new audit.

**Unchanged:** Existing 78 action links, frontend input/stdin verification, styles, backend execution verification logic, API schemas and code transformations unrelated to these tags. The 2 new tags increase the linked registry from 78 to 80, reducing compare-only tags from 24 to 22. The separate 2 formatting concept tags are not in this 102-tag auto-transform audit.

## Windows installer correction (2026-11-16)

The original Batch 19 installer stopped during `--check` with
`Strict UI reference remains in frontend component.` because it removed the
checkbox, state and call-site references but failed to rename the leftover
`strictRuntimeValidation?: boolean` in the component callback type. The corrected
installer patches this annotation while preserving the existing API argument
position (the UI passes `false`). If the original `--check` stopped at this
message, no project code was changed: the installer prepares all modifications
before writing. Replace the old ZIP with this corrected ZIP and repeat the
normal install commands below.

This correction was tested against a simulated Batch 18 component, and with a
synthetic full eight-file installation including CRLF preservation, backup and
re-run idempotence. It has **not** run your actual project's Docker suite.

## Install in Windows PowerShell (project root)

```powershell
Expand-Archive -LiteralPath ".\capstone_batch19_windows_fix_20261116.zip" -DestinationPath "." -Force
python backend\tools\install_batch19.py --check
python backend\tools\install_batch19.py
```

The installer checks all anchors and registry uniqueness before writing, refuses partial installs or conflicting payloads, preserves BOM/CRLF, and backs up existing files under `.git/capstone_batch19_backups/`. Re-running it after successful installation should report `already installed`.

## Verify

```powershell
docker compose run --rm backend python -m unittest discover -s tests -p "test_*.py"
docker compose run --rm backend python tools/audit_transform_batch19.py --output transform_audit_batch19.json
docker compose build frontend
docker compose up -d --build frontend
```

Expected batch19 audit: `102 total / 80 linked / 22 compare-only`, **240/240 positive representative tests** (234 from prior batches + 6 newly added), provided the existing suite and environment stay unchanged. This is a target, not a result already verified on your machine.

The historical batch13-15 standalone audit CLIs contain exact-count assertions for their own historical snapshots; use the **batch19 audit** for the current registry. Existing full `unittest` tests are still expected to pass, including the Batch13 regression test updated here.

## Safety caveats

- The transformation preserves syntax for recognized narrow cases; it cannot prove full semantic equivalence when runtime code dynamically monkeypatches `operator`, uses hidden side effects, or uses untested inputs.
- Runtime verification itself is not a security sandbox. Do not execute untrusted code.
- Do not stage temporary ZIP archives, backups or audit JSON files unless you specifically want them versioned.
