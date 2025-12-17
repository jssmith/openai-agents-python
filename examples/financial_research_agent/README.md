# Financial Research Agent Example

This example shows how you might compose a richer financial research agent using the Agents SDK. The pattern is similar to the `research_bot` example, but with more specialized sub‑agents and a verification step.

The flow is:

1. **Planning**: A planner agent turns the end user's request into a list of search terms relevant to financial analysis – recent news, earnings calls, corporate filings, industry commentary, etc.
2. **Search**: A search agent uses the built‑in `WebSearchTool` to retrieve terse summaries for each search term. (You could also add `FileSearchTool` if you have indexed PDFs or 10‑Ks.)
3. **Sub‑analysts**: Additional agents (e.g. a fundamentals analyst and a risk analyst) are exposed as tools so the writer can call them inline and incorporate their outputs.
4. **Writing**: A senior writer agent brings together the search snippets and any sub‑analyst summaries into a long‑form markdown report plus a short executive summary.
5. **Verification**: A final verifier agent audits the report for obvious inconsistencies or missing sourcing.

## OpenTelemetry Tracing

This example uses **OpenTelemetry** for tracing instead of the default OpenAI platform logging. Traces are exported via OTLP and can be sent to any OTEL-compatible backend (Jaeger, Zipkin, Honeycomb, Arize Phoenix, etc.).

### Setup

1. **Install dependencies including OTEL support**:

```bash
uv sync --extra otel
```

2. **Run an OTEL collector** (example using Jaeger):

```bash
docker run -d --name jaeger \
  -p 4318:4318 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

Or use [Arize Phoenix](https://docs.arize.com/phoenix) for a lightweight local option:

```bash
pip install arize-phoenix
phoenix serve
```

3. **Run the example**:

```bash
python -m examples.financial_research_agent.main
```

and enter a query like:

```
Write up an analysis of Apple Inc.'s most recent quarter.
```

4. **View traces**:
   - Jaeger UI: http://localhost:16686
   - Phoenix UI: http://localhost:6006

### How It Works

The example uses the [`openinference-instrumentation-openai-agents`](https://github.com/Arize-ai/openinference/tree/main/python/instrumentation/openinference-instrumentation-openai-agents) package, which implements the SDK's `TracingProcessor` interface to convert SDK traces/spans into standard OpenTelemetry spans.

Key changes in `main.py`:
- Calls `set_tracing_disabled(True)` to disable the default OpenAI platform exporter
- Sets up an OTEL `TracerProvider` with an OTLP exporter
- Calls `OpenAIAgentsInstrumentor().instrument()` to register the OTEL processor

### Starter prompt

The writer agent is seeded with instructions similar to:

```
You are a senior financial analyst. You will be provided with the original query
and a set of raw search summaries. Your job is to synthesize these into a
long‑form markdown report (at least several paragraphs) with a short executive
summary. You also have access to tools like `fundamentals_analysis` and
`risk_analysis` to get short specialist write‑ups if you want to incorporate them.
Add a few follow‑up questions for further research.
```

You can tweak these prompts and sub‑agents to suit your own data sources and preferred report structure.
