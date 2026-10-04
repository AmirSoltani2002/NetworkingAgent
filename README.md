# Local Meta-Harness

A local operator control plane for composing allowlisted MCP tools, an analyzer profile, optional RAG retrieval, and an optional validator. ML, RAG, and validator capabilities remain external MCP services.

See the [User Guide](docs/USER_GUIDE.md) for configuration and workflow instructions.

## Start locally

Requirements: Docker Engine and the Docker Compose plugin.

```sh
docker compose up --build
```

Open [http://localhost:8080](http://localhost:8080). The core API is available at `http://localhost:8000`; local configuration and run history persist in the `meta-harness-data` Docker volume.

To call an OpenAI-compatible analyzer, set `ANALYZER_API_KEY` in the shell or a local `.env` file before starting Compose. You can also set `ANALYZER_BASE_URL` for a compatible API endpoint. Analyzer profiles store model/configuration only. For MCP credentials, add their environment variables to `.env`; in the registry, enter the variable name as the secret reference. If an MCP server runs directly on the host, use `host.docker.internal` in its endpoint URL.

Stop the services with `docker compose down`. To remove locally persisted configuration too, remove the `meta-harness-data` volume explicitly.

## Configure and run

1. In **MCP Registry**, register external MCP endpoint URLs, test connections, discover tools, and explicitly allowlist the tools that may run.
2. In **Workflow Builder**, create ordered ML steps, select allowlisted tools, name outputs, and map every tool argument to the operator prompt, static input, run metadata, or a prior step output.
3. In **Knowledge / RAG**, configure a RAG profile and add document location metadata. The app does not transfer, chunk, embed, or index document contents. An ingestion tool is called only when explicitly requested.
4. In **Analyzer & Validator**, configure an OpenAI-compatible analyzer profile and optional validator profile. The core reads the analyzer key from `ANALYZER_API_KEY` or the selected environment variable name.
5. In **Operator Console**, select workflow/analyzer/validator, enter a prompt, and run. Inspect evidence, step outputs, errors, timing, and validator output. **Run History** reopens recorded traces.

The included tests use in-process fake MCP and analyzer HTTP endpoints as test doubles; no domain services or mock production servers are shipped.

For a manual UI walkthrough when external services are unavailable, start `python3 tests/mock_services.py` in another terminal. Register `http://host.docker.internal:9000/mcp` in MCP Registry (you can use it for ML, RAG, and Validator categories), then discover and explicitly allowlist `enrich_summary`, `search_documents`, `validate_candidate`, and optionally `register_document` as appropriate. Set the analyzer profile's base URL to `http://host.docker.internal:9001/v1` and any model identifier (for example `demo-model`). These fixtures return labeled demo outputs and are not application services.

## Development and verification

The core uses Python's standard library and needs no package installation. Run the automated suite with:

```sh
python3 -m unittest discover -s tests -v
```

Check Python syntax with `python3 -m py_compile core/server.py tests/test_core.py`. The UI is plain HTML/CSS/JavaScript and is served by Nginx in Compose.

## Local boundaries

No cloud infrastructure or domain-specific ML, RAG, validator, or BGP implementation is included. The MCP client uses JSON-RPC over streamable HTTP and captures failures in the run trace. Runs stop on an ML or RAG failure. A validator failure is traced separately and does not replace the analyzer answer. The analyzer currently supports the OpenAI-compatible Chat Completions API.
