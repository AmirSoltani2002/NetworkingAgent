# Guide verification - 10 October 2026

The revised main deliverable is `manufacturing-meta-harness.pdf`, a 16-page A4 guide for general engineers, below the user's 20-page limit. It uses the factory game as the running explanation, with two actual saved screenshots and nine editable diagram/plot figures. The previous 29-page research report is preserved as `technical-report-2026-10-09.pdf`, with `technical-report.tex` and its original chapters/figures.

## Data and source checks

- `python3 guide/build_data.py` passed: 1,000 exact source readings and five-minute cadence; equality with the original plot CSV; six exact saved factory-episode readings; both 200-case confusion matrices; eight source-derived component routing examples; byte-identical screenshot copies.
- `guide/data-audit.json` records the inputs' SHA-256 hashes, plot records, operation/task IDs and routing examples. No smoothing, resampling, fabricated thresholds or extra sensor readings.
- The current classifier and future-onset evaluations use different synthetic datasets, class meanings and deployment procedures. Both are explicitly separated in text and figures.
- Inspection, action acceptance/completion, simulated repair, restart and alarm resolution are checked against current source. Known gearbox-routing, incident-retention and repair-button limitations are disclosed.
- Added high-level agent sections were checked against current architecture, API/data, MCP, task execution and RAG contracts: saved-model connection and remote inference; sequential proposals and bounded execution; tool permissions and approvals; read-only sourced retrieval; durable records versus limited context; immutable evidence checks and UNKNOWN-write reconciliation. Model instructions are distinguished from backend enforcement and industrial diagnosis is not claimed.

## PDF checks

- Built with `meta-report-calibri:local`, the existing document-builder image extended with LuaLaTeX font support. Compilation has networking disabled. Source checkout is mounted read-only; only the dedicated `.build` output folder is writable.
- Final compilation has no errors, overfull/underfull boxes or unresolved reference warnings. PDF has 16 A4 pages.
- Final pages rendered with Poppler at 130 dpi and inspected individually, including screenshots, axes, recipe boundaries, alarm marker, matrix orientation, flow-arrow meanings and page breaks.
- Calibri Regular and Bold are embedded in the final PDF; no fallback fonts are used. All native PDF text, including headings, notes, figure labels and chart ticks, is checked as black through Poppler XML extraction. The regular/bold/italic/bold-italic source faces are genuine local Calibri from the user's mounted Windows installation; binaries remain in ignored build storage and are excluded from the archive.
- The notebook note is boxed directly under its owner and joined by a dotted leader. Flow labels fit between boxes, mechanical-power text clears box edges, and vertical process diagrams use explicit heading/body line breaks. Every diagram, plot, screenshot and page is reviewed after the typography change. Dark boxes are lightened to retain contrast with black lettering. Screenshot pixels and their original UI fonts/colors are preserved.
- The packaged source contains unchanged screenshot copies and derived plot CSVs. Standalone compilation also requires a separately supplied licensed Calibri copy; it needs no sibling repository data. Regenerating/verifying data with `guide/build_data.py` requires the source checkout.

No application code or service state was changed. No new model training, paid-model task, physical test or application test suite was run for this document rewrite. The episode, metrics and screenshots are saved historical evidence, not a new demonstration.

---

## Original report QA (retained historical record)

# Delivery verification — 9 October 2026

- Final PDF: 29 A4 pages, using an 11-point report class.
- Front matter: pages 1–2. User manual: exactly pages 27–28. References: page 29.
- Compilation: latexmk / pdfLaTeX / BibTeX in the isolated `meta-report-latex:local` Docker builder; completed without errors, unresolved references/citations, or overfull boxes.
- Every page rendered with Poppler at 110 dpi and visually inspected in five contact sheets; title, plots, and manual screenshots also inspected individually.
- Thirteen informative diagram/plot figures and two genuine screenshot figures. Screenshot viewports crop original project captures; no generated interfaces.
- Current full npm test run: core 30 passed, 4 skipped; UI 22 passed, 1 failed. The UI regression expects the exact text “Connection failed”, while the rendered error includes an explanatory prefix. This failure is disclosed in the evaluation; application code was not changed.
- Optional isolated database tests and external-service suites were not freshly rerun. Historical validation records are explicitly identified as historical.
- No fresh paid LLM maintenance workflow was executed. The combined maintenance example is explicitly illustrative; actual recorded ML calls and a fresh read-only RAG search are distinguished.
- Synthetic ZSK-SIM-01 readings and RAG asset ZSK-001 have no verified physical identity mapping. Model performance is proof-of-concept evidence, not industrial validation.

The source archive includes LaTeX, bibliography, editable diagrams, exact plot records, genuine screenshot assets, provenance evidence, and build instructions. Build products and secrets are excluded.
