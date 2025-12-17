import asyncio

from openinference.instrumentation.openai_agents import OpenAIAgentsInstrumentor
#from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk import trace as trace_sdk
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource
from agents import set_tracing_disabled

from .manager import FinancialResearchManager


# Entrypoint for the financial bot example.
# Run this as `python -m examples.financial_research_agent.main` and enter a
# financial research query, for example:
# "Write up an analysis of Apple Inc.'s most recent quarter."
def setup_otel_tracing() -> None:
    """Setup OpenTelemetry tracing using OpenInference instrumentation."""

    # Setup OTEL with OTLP exporter
    resource = Resource.create(attributes={"service.name": "financial-research-agent"})
    tracer_provider = trace_sdk.TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
    tracer_provider.add_span_processor(SimpleSpanProcessor(otlp_exporter))

    # Instrument the OpenAI Agents SDK
    OpenAIAgentsInstrumentor().instrument(tracer_provider=tracer_provider)


async def main() -> None:
    setup_otel_tracing()

    query = input("Enter a financial research query: ")
    mgr = FinancialResearchManager()
    await mgr.run(query)


if __name__ == "__main__":
    asyncio.run(main())
