# Final empty-directory and generated-artifact cleanup

## Removed

- 71 Unity runtime directories under 38 root-level UUID paths. Five UUID roots
  and eleven nested `Logs/` directories were initially empty; the remaining
  runtime directories became empty after 22 audited `heartbeat.txt` files were
  removed.
- 3 empty generated-output directories: `Output/script/0`, `Output/script`, and
  `Output`.
- 1 sensor-log directory, `tools/Log`, after removing 80 small generated logs
  and its runtime symlink.
- 50 `__pycache__` directories, the 3-directory `.pytest_cache` tree, and 2
  generated `*.egg-info` directories.
- Generated editor database files under `.vscode/`; project settings were
  preserved.
- Local LaTeX intermediate files (`.aux`, `.bbl`, `.blg`, `.fdb_latexmk`,
  `.fls`, `.log`, and `.synctex.gz`); paper sources and the compiled PDF were
  preserved.
- One ignored simulator port log.

Removed empty/runtime/output directories: **75**. Generated/cache directories
removed separately: **55**.

## Preserved

- `.agents`, because it is environment-owned project tooling state.
- Empty directories inside the two upstream `.git` stores under `third_party/`.
- All upstream-required `third_party/` source directories and license files.
- The local RA-L paper workspace and its source, bibliography, presentation,
  media, and compiled PDF.
- Every non-empty artifact under `phase6`, `phase7`, `phase8`, `phase9`,
  `phase10`, and `phase10_regression`.
- All formal records, protocol/manifest locks, hash records, audit reports, and
  CSV summaries.

## Reason

The removed paths were confirmed generated caches, temporary runtime logs, or
structurally meaningless output directories. Git does not track truly empty
directories. Environment-owned, upstream-owned, research-history, and frozen
experiment paths were retained for reproducibility and auditability.
