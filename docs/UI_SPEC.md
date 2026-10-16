# Current UI Specification

The implemented screen is a dark chat interface based on the user's screenshot, with working Send/file controls, saved Chats, LLM settings, and collapsible RAG/MCP sections. Ordered workflow screens belong to [ROADMAP.md](ROADMAP.md).

Responding… stays visible while budget checkpoints automatically request the next prompt for the same saved user turn. Only the final reply is added to the conversation. Tool confirmation pauses continuation for explicit approval; errors or continuation safety limits expose the existing Retry response control. Model context summaries are private and do not add chat bubbles or sidebar controls. Limits are owned by API_SPEC.md.

## Layout and appearance

- Black page, sidebar, and main panel; a thin dark sidebar divider.
- Desktop sidebar width is clamp(260px, 18.584vw, 336px). It contains Meta-Harness branding, a visibility toggle, New chat, and a collapsible Chats heading with saved title rows.
- Main header shows the active chat title. The conversation scrolls independently above the bottom composer.
- Composer and conversation content share a maximum width of 768px. The composer is dark gray and rounded; user messages are blue, rounded, and right aligned. Assistant answers are white plain text, left aligned without a colored bubble, matching the reference.
- Typography uses Ubuntu when available, then Segoe UI, Arial, and sans-serif. No font assets are bundled.
- At widths up to 700px, the sidebar starts closed and opens as a 240px overlay. Selecting a chat or New chat closes it.
- chat.css owns reference-specific geometry/colors; index.css owns Tailwind and shadcn theme tokens.

## Implemented controls

| Control | Behavior |
| --- | --- |
| Sidebar visibility | Hide/open the sidebar |
| Chats heading/chevron | Collapse/expand saved titles independently of the sidebar |
| New chat | Clear selected history and draft; create a saved chat on first send |
| Saved title | Load that conversation and mark it selected |
| + | Open the native multi-file picker |
| Pending file remove | Remove a selected file before sending |
| Message textarea | Grow with content; Enter sends; Shift+Enter inserts a newline |
| Send | Save nonblank text/files, then request and display an OpenAI reply; disable during loads/saves/generation |
| Retry response | Request the latest unanswered user's reply; visible after failure or reopening unanswered history |
| Saved file card | Download the original saved bytes |

Unused search, share, settings, menu, dictation, voice, and reaction controls are removed. There are no placeholder MCP or workflow controls. A separate collapsible LLM section below Chats contains the authorized OpenAI settings.

The UI does not receive database credentials or saved full API keys. It accepts a new OpenAI key in a password field, clears it on submission, and displays only server-generated masked metadata afterward. No key reveal control, local storage, or Vite secret variable is used.

## Chat and attachment behavior

Core generates titles from the first message or first attachment filename. The title stays unchanged on later sends. Title generation/storage and upload limits are specified in [DATA_MODELS.md](DATA_MODELS.md) and [API_SPEC.md](API_SPEC.md).

Chats list by recent activity; opening one fetches persisted messages. Reload loads the saved title list but starts with no selected conversation. Draft text/files, sidebar visibility, and the Chats section's open state are browser-session state; they are not stored in local storage. Chats starts expanded. Its heading remains visible when collapsed; both the title list and empty-state message are hidden. Collapsing it keeps the selected conversation and its draft intact. The heading is a keyboard-operable button with aria-expanded and aria-controls.

File selections show name/size cards and can be removed. Duplicate file selections with the same name, size, and last-modified value are suppressed. Successful user saves immediately clear the composer; failed saves preserve the draft. File-only messages are supported. A pending-file note explains that file contents stay local; the model receives filenames with an explicit contents-unavailable note, not file bytes.

Loading status and request errors are visible. Stale chat loads are cancelled. Navigation/submission pauses while saving or responding. Responding… appears below the saved user. Answers appear on completion without token streaming; generated text is escaped/plain text, not executable HTML or rendered Markdown. Response failures preserve the saved user, display a sanitized error, and offer Retry response. Reopening history offers retry for its latest unanswered user without automatically issuing a paid call. Empty conversations have no generated assistant content.

## Components

- App: chat state, loading, sending, errors, and selected history.
- Sidebar: branding, visibility, New chat, independently collapsible Chats section, and saved navigation.
- Composer: textarea, file selection/removal, limits, and submission UUID.
- MessageList: ordered user/assistant messages, attachment downloads, response progress/retry, automatic scrolling.
- AttachmentCard: shared pending/saved file presentation.
- Icon: custom SVG controls matching the reference.
- shadcn Button/Textarea: source primitives configured by ui/components.json.

## Screenshot review

For every UI change, render the app, capture screenshots at reference and mobile sizes, compare them visually to the user's reference and approved layout, then iterate. Inspect the final captures before completion.

Representative reviewed captures are under screenshots:

| Capture | Purpose |
| --- | --- |
| [ui-desktop.png](screenshots/ui-desktop.png) | Default desktop with the Chats section expanded |
| [ui-chats.png](screenshots/ui-chats.png) | Saved titles and selected conversation |
| [ui-chats-collapsed.png](screenshots/ui-chats-collapsed.png) | Chats closed while active history and draft remain visible |
| [ui-attachments.png](screenshots/ui-attachments.png) | Pending file cards in the composer |
| [ui-mobile.png](screenshots/ui-mobile.png) | Compact mobile conversation/composer |
| [ui-mobile-chats.png](screenshots/ui-mobile-chats.png) | Mobile drawer with Chats expanded |
| [ui-mobile-chats-collapsed.png](screenshots/ui-mobile-chats-collapsed.png) | Mobile drawer with Chats collapsed |
| [ui-llm.png](screenshots/ui-llm.png) | New LLM configuration form |
| [ui-llm-saved.png](screenshots/ui-llm-saved.png) | Masked saved fixture key, selected model, and High thinking |
| [ui-llm-collapsed.png](screenshots/ui-llm-collapsed.png) | Independently collapsed LLM section |
| [ui-mobile-llm.png](screenshots/ui-mobile-llm.png) | Mobile LLM settings |
| [ui-assistant.png](screenshots/ui-assistant.png) | Live OpenAI conversation, white assistant text and blue user bubbles |
| [ui-mobile-assistant.png](screenshots/ui-mobile-assistant.png) | Same live conversation at 390px width |
| [ui-responding.png](screenshots/ui-responding.png) | Saved user and response progress |
| [ui-response-error.png](screenshots/ui-response-error.png) | Simulated connection failure with saved user and Retry response |

Initial chat captures are from 2026-10-08; LLM and inference captures are from 2026-10-09. Sample chats used for review were removed afterward. LLM saved-key/model screenshots use an isolated temporary .env and fixture catalog. Assistant captures use real replies from the saved model; the response-error capture uses a browser-intercepted simulated failure. The LLM section is collapsed in inference captures to avoid including saved key metadata.

## LLM sidebar section

LLM has its own keyboard-operable chevron toggle and starts expanded. Its form contains:

- Company: OpenAI, the only supported provider.
- API key: password input plus Save API key; a saved-key row shows the first four characters and stars for every remaining character. Long masks truncate visually without revealing characters.
- Model: IDs fetched online for the saved key, with Refresh and loading/error states. There is no hardcoded model list.
- Thinking: Instant, Medium, High (default Medium).
- Save settings: persists a selected available model and thinking preference.

Saving a replacement key clears the old model selection; successful key saves refresh the list. Unknown/unavailable models cannot be saved. OpenAI/provider/network errors are visible without key/error-body disclosure. Configuration changes preserve the active chat/draft.

The model catalog contains all IDs returned by OpenAI, including specialized models. Model-list metadata does not establish reasoning/endpoint compatibility; the UI notes that thinking support depends on the model. Chat inference uses the currently saved settings, not unsaved form changes. Unsupported combinations fail visibly; the app does not silently change the selected model or thinking.

## RAG navigation and management

RAG and MCP are independent keyboard-operable collapsible sidebar sections after LLM, sharing Chats typography, hover styles, spacing and chevron behavior. Forms/tables open in the main area; no large sidebar forms. Mobile navigation closes the drawer. Back to chat restores the mounted conversation/composer and draft/files; selecting a different chat retains existing draft-reset rules.

- Connection: persisted registry profiles, separately entered MCP and REST base URLs, None/Bearer authentication, write-only token field cleared on every submission. Saved credentials show an indicator only. Test initializes/discovers actual MCP tools and independently tests the authenticated REST device-list contract. Draft tests do not overwrite different saved endpoints. Save resets connectivity/agent enablement; test the saved profile before enabling retrieval. Disconnect retains settings and revokes chat use. Status/error/server/tools shown independently.
- Available tools: discovered read-only tools can be explicitly selected; a separate chat-enable checkbox and Save tool permissions activate them. The UI explains that retrieved context goes to the saved OpenAI model. No forced retrieval on every message.
- Devices: complete bounded remote catalog, search/manufacturer filter, sorting, pagination, real issue/document counts, add/edit/detail/delete confirmation. Details show issues/documents and support adding issues, associating existing documents or uploading related documents. Actual API requires name/model/manufacturer.
- Known Issues: search/device/category filters, pagination/sorting, add/edit/delete, detail and evidence search. Actual API requires device/title/category/symptoms. Possible cause remains visibly unconfirmed.
- Documents: PDF/TXT/Markdown file picker/drop area, title/type/version/description/metadata, searchable multiple device selection; metadata edit/association, delete confirmation, retry failed processing, status values without invented percentages. Pending records poll every three seconds; polling stops on ready/failed and pauses on network failure until Refresh. Detail shows chunks, section/page/order, local text filtering and explicit issue links. Original-file downloads are unavailable in the verified API and are not fabricated. Embeddings are not displayed.
- Evidence: search relevant passages scoped to the issue device, display source titles/pages/chunk references, select passage and choose one of four explicit evidence types. No manual IDs or automatic similarity-based links. Removal requires confirmation.
- Knowledge Search: query, searchable optional device, category/top_k; display matched device/issues and source passages with expandable technical IDs/method/score. Rankings are not confidence probabilities. This view never requests an LLM answer.

Dark cards/inputs/tables share chat colors and shadcn Button styling; Radix dialogs provide focus/keyboard handling. Lists load complete remote pages up to 5,000 records; larger catalogs fail visibly rather than showing misleading partial counts/filter results. Search/sort/pagination are local because the current RAG API lacks those operations for several catalogs.

Reviewed screenshots: [connection](screenshots/ui-rag-connection.png), [tools](screenshots/ui-rag-tools.png), [devices](screenshots/ui-rag-devices.png), [upload](screenshots/ui-rag-upload.png), [document](screenshots/ui-rag-document.png), [evidence](screenshots/ui-rag-evidence.png), [search](screenshots/ui-rag-search.png), [passages](screenshots/ui-rag-results.png), [mobile](screenshots/ui-mobile-rag.png), [chat regression](screenshots/ui-rag-chat.png). Test knowledge is removed after review.

## Generic MCP connections and chat confirmation

MCP is a separate collapsible sidebar section with **Connections** and **Add MCP Server**. Connection forms open in the main area and support a user description, URL, None/Bearer authentication, environment-variable credential reference, and enabled state. Test initializes the server; Discover Tools renders only schemas returned by the server. Save is server-side; credentials are write-only. Permissions require selecting discovered tools and explicitly enabling the server for chat. Removal and destructive operations use a confirmation dialog.

Chat tool activity is shown as a compact expandable trace. Read-only permitted tools can be selected by the existing model. State-changing calls show the exact server/tool/arguments and expiry in the existing chat; the user must press **Confirm and run** or **Decline**. A pending call remains after reload and disables another send until resolved. New chat starts a separate normal conversation. No extra LLM or chat interface is added.

Reviewed screens include [MCP connections](screenshots/ui-mcp-connections.png), [new server form](screenshots/ui-mcp-add.png), [discovered tools](screenshots/ui-mcp-tools.png), [live prediction](screenshots/ui-mcp-agent-prediction.png), [dataset analysis](screenshots/ui-mcp-agent-dataset.png), [metrics](screenshots/ui-mcp-agent-metrics.png), and [training confirmation](screenshots/ui-mcp-training-confirmation.png). Test captures are not application data.

## Context continuation review artifacts

- [ui-context-responding.png](screenshots/ui-context-responding.png): existing Responding… state across three automatic budget checkpoints.
- [ui-context-completed.png](screenshots/ui-context-completed.png): one final reply after four prompts for one saved user turn.

These are browser-only fixture captures of the rendered Docker UI; no live model calls or saved chat records were created.

## TASKS

The compact independent TASKS sidebar group contains Active Tasks, Task History and Scheduled Tasks. Management uses the existing dark forms/tables/dialogs in the main area. Task detail shows goal/status/verified progress, plan/checkpoints, next action, tool evidence, checks and retries. Exact approval and unknown-outcome reconciliation require explicit action. Cancellation/deletion use confirmation dialogs. SSE updates keep task state current. A small Run as task checkbox beside the chat composer opts into durable execution; ordinary chat remains default. Submission stays in chat. Each task request shows a live assistant card with progress/outcome, readable failure or clarification text, expandable requests and outputs, and an optional View task details link. Chat shows no red task error banner. Event triggers are temporarily removed. Back to chat and Open conversation preserve the existing experience. Screenshot references: ui-tasks-active.png, ui-tasks-details.png, ui-tasks-schedule.png, ui-tasks-mobile.png.

Vague/incomplete task requests are interpreted automatically rather than requiring a concrete objective first. A response-only task displays “Your response is ready. No external operation was verified.” Partial responses remain visible alongside any unmet external-task checks.

## FACTORY navigation and simulation

Independent collapsible **FACTORY** sidebar contains **Factory Simulation**, **Machine Monitoring**, **Alarms**, **Simulation Settings**. The existing dark chat, drafts and composer persist while navigating. Phaser lazily loads only the factory workspace; original side-view industrial art follows both supplied visual references. It renders committed backend state rather than generating local faults/sensors.

The large clickable environment shows hopper/feeder, drive/gearbox, segmented twin-screw barrel/zones, die/conveyor, cooling/HMI and technician. Running/stopped/maintenance animations reflect authority. Controls are Pause/Resume, 1×/5×/10×/60× and confirmed Reset. Component inspector shows readings/inspection and **Send technician**. Separate cards show current classification, future synthetic onset/warm-up, monitoring and technician. Monitoring plots all ten actual stored signals; Alarms shows linked task status/tool/report/history. Settings marks manual fault injection explicitly and presents actual automatic policy; operator stop/restart/repair enforce backend preconditions and confirmation. Exact label/behavior evidence: `docs/verification/factory/` screenshots/browser checks.
