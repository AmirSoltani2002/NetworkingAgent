# A factory alarm, explained

The current deliverable is **`manufacturing-meta-harness.pdf`**, a **16-page** story-led guide for general engineers unfamiliar with the manufacturing line. It follows the actual factory game from material flow and sensors through an alarm, AI investigation, technician inspection, simulated repair and restart. The backstage story explains LLM connection, the agent execution loop, tool calling/security, RAG, memory/context management and validation/recovery at a high level. It includes genuine saved game screenshots and redrawn diagrams/graphs using exact source records.

The original 29-page research audit is preserved as `technical-report-2026-10-09.pdf`; its source entry point is `technical-report.tex` with the original `chapters/`, `figures/`, bibliography and evidence. Treat it as the dated 9 October snapshot, not a specification of the later factory extension.

## Build the short guide

From this directory, with a TeX Live installation including LuaLaTeX:

```sh
mkdir -p .build/fonts
# Place licensed calibri.ttf, calibrib.ttf, calibrii.ttf and calibriz.ttf here.
latexmk -lualatex -interaction=nonstopmode -halt-on-error main.tex
cp main.pdf manufacturing-meta-harness.pdf
```

Requires LuaLaTeX, fontspec, TikZ, PGFPlots, titlesec, fancyhdr and standard LaTeX packages. The guide uses genuine Calibri for body, headings, captions, chart labels and numbers; all authored text is black. The four Calibri faces come from the user's mounted Windows installation and are held only in ignored `.build/fonts/`; font binaries are not redistributed in the archive. `guide/font-setup.tex` owns the explicit font selection. There is no silent substitute: compiling requires a licensed local font copy. No shell escape or network access is needed for compilation.

`guide/` owns the short narrative, nine editable vector figures, two unchanged saved screenshot copies, derived plot CSVs and data audit. Figure notes are placed within or visibly connected to their owning boxes; flow labels and chart annotations are checked in the rendered PDF. Chart lines and diagram borders/fills retain visual distinctions while text stays black. Original screenshot typography/colors remain part of the unchanged evidence images. The last five story pages distinguish enforced permission/evidence checks from instructions to the model and the limits of summaries, retrieval and diagnosis.

To regenerate and verify the plot inputs from the source checkout:

```sh
python3 guide/build_data.py
```

This reads the original CSV and saved evidence; it performs no inference, database access or training. It verifies the historical readings, recorded episode, matrices, routing examples and screenshot provenance. The packaged CSVs/images and a separately supplied licensed Calibri copy are sufficient to compile the guide without the complete checkout.

To rebuild the original detailed report, use `latexmk -pdf technical-report.tex`.

## Evidence boundary

- Historical chart: all 1,000 supplied synthetic readings, 1-4 September 2026; supplied health tags are not model predictions or restored runtime labels.
- Episode chart: six exact readings from the earlier recorded factory task, not a new execution.
- Current and future-onset matrices: separate saved synthetic evaluations, with their different class semantics and candidate/deployed-model limitations.
- Screenshots: actual saved browser verification captures, cropped only by LaTeX. No invented UI or new screenshots are claimed.
- The factory/RAG identity mapping is explicit demonstration configuration, not verified physical-machine identity. No industrial diagnosis or real-machine control is claimed.

The current game retains known component-routing, incident-retention and gearbox-only repair-button limitations; this guide explains them rather than changing application behavior. Engineering contracts and service READMEs remain authoritative for configuration and startup.

`QA.md` records the checks performed. `manufacturing-meta-harness-sources.zip` contains both source entry points and their local assets; build intermediates and secrets are excluded.
