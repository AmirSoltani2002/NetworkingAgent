# Meta-Harness User Guide

This guide walks through configuring and running the local meta-harness. ML, RAG, and validator capabilities are provided by external MCP services. The application connects to those services; it does not implement their domain logic.

## Start the application

From the repository directory, run:

```bash
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). The core API is available at `http://localhost:8000`.

To stop the services, press `Ctrl+C` or run `docker compose down` in another terminal. Configuration and run history persist in the `meta-harness-data` Docker volume.

## 1. Register MCP services

Open **MCP Registry**. For each external service:

1. Enter a display name and capability category: **ML**, **RAG**, or **VALIDATOR**.
2. Enter its MCP endpoint URL. If the service runs directly on the host while the core runs in Docker, use `host.docker.internal` in the URL instead of `localhost`.
3. If it requires a token, provide that token to the core through an environment variable and enter only the **environment variable name** in the secret reference field. Do not enter the token itself in the UI.
4. Click **Add MCP server**, then **Test connection** and **Discover tools**.
5. Explicitly allowlist each tool that may be used in a workflow.

Only discovered and allowlisted tools can be called by workflow steps.

## 2. Build an ordered ML workflow

Open **Workflow Builder**:

1. Create a workflow and give it a name.
2. Add an ML step, then select its MCP server and an allowlisted tool.
3. Give the step an output name so later steps can refer to its result.
4. For each required tool argument, choose an explicit input mapping. Sources include the operator prompt, a static value, run metadata, or a prior step's output. A prior step field can select a nested field path.
5. Add further steps and use the up/down controls to set their order.
6. Validate the workflow and save it.

The workflow editor does not infer argument mappings. A required argument without an explicit mapping fails validation. Disabled steps are skipped and shown as skipped in the execution trace. A failed ML step stops the run and its error is recorded.

## 3. Configure RAG and document metadata (optional)

Open **Knowledge / RAG**:

1. Create a RAG profile by selecting a registered RAG server, an allowlisted retrieval tool, and a collection/index/profile identifier.
2. Enter retrieval argument mappings as JSON. For example:

   ```json
   {
     "query": {
       "source_type": "OPERATOR_PROMPT"
     }
   }
   ```

3. Register document metadata, including a title, local path or URI, tags, relation label, and RAG profile.
4. If the selected profile has an ingestion tool, click **Explicitly register with RAG** to call that external tool.

The app stores document metadata and forwards it to the configured ingestion tool when requested. It does not upload file contents or implement chunking, embeddings, indexing, vector search, or retrieval. The local path is metadata; the external service must be able to use whatever reference you provide.

Retrieved results are shown separately as RAG evidence. Analyzer-generated statements are not labeled as retrieved evidence.

## 4. Configure the analyzer and validator

Open **Analyzer & Validator**.

### Analyzer

Create an analyzer profile with a name, adapter, model identifier, and instructions. The initial adapter uses an OpenAI-compatible Chat Completions API. Configure `ANALYZER_API_KEY` through the core environment or a local `.env` file; set `ANALYZER_BASE_URL` if the compatible API is not at the default endpoint. You can also set a base URL on the profile. Do not store API keys in the browser.

To enable retrieval context, turn on RAG access and select a RAG profile.

### Validator (optional)

Create a validator profile by selecting a registered validator server and one of its allowlisted tools. Enter explicit argument mappings as JSON. For example:

```json
{
  "answer": {"source_type": "ANALYZER_ANSWER"},
  "evidence": {"source_type": "RAG_EVIDENCE"}
}
```

Validator results and errors appear separately in the run trace. The validator never rewrites the analyzer answer.

After changing `.env`, recreate the core container so it receives the new environment:

```bash
docker compose up -d
```

## 5. Run a workflow

Open **Operator Console**:

1. Select a workflow and analyzer profile. Select a validator profile if you want validation on this run.
2. Enter the operator question or prompt.
3. Click **Run workflow**.
4. Follow the refreshing execution timeline and inspect each MCP call, its arguments and result, RAG evidence, the analyzer answer, validator result, errors, and timing.

Runs stop after ML or RAG failures. A validator failure is recorded separately; it does not discard or rewrite the analyzer answer. Run cancellation is not supported in this version.

## 6. Reopen a prior run

Open **Run History** and select **Inspect** to reopen a run. The stored trace includes the workflow version and configuration snapshot used for that run, even if the workflow is edited later.

## Try the demo fixtures

When external MCP or analyzer services are unavailable, start the development fixtures in a second terminal:

```bash
python3 tests/mock_services.py
```

In MCP Registry, register `http://host.docker.internal:9000/mcp` for the capability categories you want to try. Discover its tools and allowlist the ones needed by your workflow. The fixture exposes:

- `enrich_summary` for an ML workflow step;
- `search_documents` for RAG retrieval;
- `validate_candidate` for the validator;
- `register_document` for explicit document registration.

Set the analyzer profile base URL to `http://host.docker.internal:9001/v1` and use any model identifier, such as `demo-model`. No API key is needed for the fixture analyzer. The fixture returns demo outputs and is intended only for local walkthroughs and tests; it is not an ML, RAG, or validator implementation.
