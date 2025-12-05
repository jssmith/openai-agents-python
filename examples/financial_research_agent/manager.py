from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

from rich.console import Console

from agents import Runner, RunResult

from .agents.financials_agent import financials_agent
from .agents.planner_agent import FinancialSearchItem, FinancialSearchPlan, planner_agent
from .agents.risk_agent import risk_agent
from .agents.search_agent import search_agent
from .agents.verifier_agent import VerificationResult, verifier_agent
from .agents.writer_agent import FinancialReportData, writer_agent
from .printer import Printer

from opentelemetry import trace as otel_trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
from opentelemetry.trace import Status, StatusCode


async def _summary_extractor(run_result: RunResult) -> str:
    """Custom output extractor for sub‑agents that return an AnalysisSummary."""
    # The financial/risk analyst agents emit an AnalysisSummary with a `summary` field.
    # We want the tool call to return just that summary text so the writer can drop it inline.
    return str(run_result.final_output.summary)


class FinancialResearchManager:
    """
    Orchestrates the full flow: planning, searching, sub‑analysis, writing, and verification.
    """

    def __init__(self) -> None:
        self.console = Console()
        self.printer = Printer(self.console)
        
        # Set up OpenTelemetry tracing.
        resource = Resource.create(
            {
                "service.name": "FINANCIAL_RESEARCH_AGENT",
                "service_version": "0.1.0",
                "deployment.environment": "development",
            }
        )
        provider = TracerProvider(resource=resource)
        otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        otel_trace.set_tracer_provider(provider)
        
        # Instrument OpenAI to automatically trace all LLM calls.
        OpenAIInstrumentor(
            enrich_assistant=True,
            enable_trace_context_propagation=True,
        ).instrument()
        
        self.tracer = otel_trace.get_tracer(__name__)

    async def run(self, query: str) -> None:
        with self.tracer.start_as_current_span("financial_research.run") as span:
            span.set_attribute("query", query)
            self.printer.update_item(
                "trace_id",
                "Financial research trace started",
                is_done=True,
                hide_checkmark=True,
            )
            self.printer.update_item("start", "Starting financial research...", is_done=True)
            search_plan = await self._plan_searches(query)
            search_results = await self._perform_searches(search_plan)
            report = await self._write_report(query, search_results)
            verification = await self._verify_report(report)

            final_report = f"Report summary\n\n{report.short_summary}"
            self.printer.update_item("final_report", final_report, is_done=True)

            self.printer.end()

        # Print to stdout
        print("\n\n=====REPORT=====\n\n")
        print(f"Report:\n{report.markdown_report}")
        print("\n\n=====FOLLOW UP QUESTIONS=====\n\n")
        print("\n".join(report.follow_up_questions))
        print("\n\n=====VERIFICATION=====\n\n")
        print(verification)

    async def _plan_searches(self, query: str) -> FinancialSearchPlan:
        with self.tracer.start_as_current_span("financial_research.plan_searches") as span:
            span.set_attribute("query", query)
            span.set_attribute("agent_model", planner_agent.model)
            self.printer.update_item("planning", "Planning searches...")
            result = await Runner.run(planner_agent, f"Query: {query}")
            plan = result.final_output_as(FinancialSearchPlan)
            span.set_attribute("num_searches_planned", len(plan.searches))
            self.printer.update_item(
                "planning",
                f"Will perform {len(plan.searches)} searches",
                is_done=True,
            )
            return plan

    async def _perform_searches(self, search_plan: FinancialSearchPlan) -> Sequence[str]:
        with self.tracer.start_as_current_span("financial_research.perform_searches") as span:
            span.set_attribute("num_searches_total", len(search_plan.searches))
            self.printer.update_item("searching", "Searching...")
            tasks = [asyncio.create_task(self._search(item)) for item in search_plan.searches]
            results: list[str] = []
            num_completed = 0
            num_failed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                else:
                    num_failed += 1
                num_completed += 1
                self.printer.update_item(
                    "searching", f"Searching... {num_completed}/{len(tasks)} completed"
                )
            span.set_attribute("num_searches_completed", len(results))
            span.set_attribute("num_searches_failed", num_failed)
            self.printer.mark_item_done("searching")
            return results

    async def _search(self, item: FinancialSearchItem) -> str | None:
        with self.tracer.start_as_current_span("financial_research.search") as span:
            span.set_attribute("search.query", item.query)
            span.set_attribute("search.reason", item.reason)
            span.set_attribute("agent_model", search_agent.model)
            input_data = f"Search term: {item.query}\nReason: {item.reason}"
            try:
                result = await Runner.run(search_agent, input_data)
                span.set_attribute("search.success", True)
                return str(result.final_output)
            except Exception as e:
                span.set_attribute("search.success", False)
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                return None

    async def _write_report(self, query: str, search_results: Sequence[str]) -> FinancialReportData:
        with self.tracer.start_as_current_span("financial_research.write_report") as span:
            span.set_attribute("query", query)
            span.set_attribute("num_search_results", len(search_results))
            span.set_attribute("agent_model", writer_agent.model)
            # Expose the specialist analysts as tools so the writer can invoke them inline
            # and still produce the final FinancialReportData output.
            fundamentals_tool = financials_agent.as_tool(
                tool_name="fundamentals_analysis",
                tool_description="Use to get a short write‑up of key financial metrics",
                custom_output_extractor=_summary_extractor,
            )
            risk_tool = risk_agent.as_tool(
                tool_name="risk_analysis",
                tool_description="Use to get a short write‑up of potential red flags",
                custom_output_extractor=_summary_extractor,
            )
            writer_with_tools = writer_agent.clone(tools=[fundamentals_tool, risk_tool])
            self.printer.update_item("writing", "Thinking about report...")
            input_data = f"Original query: {query}\nSummarized search results: {search_results}"
            result = Runner.run_streamed(writer_with_tools, input_data)
            update_messages = [
                "Planning report structure...",
                "Writing sections...",
                "Finalizing report...",
            ]
            last_update = time.time()
            next_message = 0
            async for _ in result.stream_events():
                if time.time() - last_update > 5 and next_message < len(update_messages):
                    self.printer.update_item("writing", update_messages[next_message])
                    next_message += 1
                    last_update = time.time()
            self.printer.mark_item_done("writing")
            report = result.final_output_as(FinancialReportData)
            span.set_attribute("report.length", len(report.markdown_report))
            return report

    async def _verify_report(self, report: FinancialReportData) -> VerificationResult:
        with self.tracer.start_as_current_span("financial_research.verify_report") as span:
            span.set_attribute("agent_model", verifier_agent.model)
            self.printer.update_item("verifying", "Verifying report...")
            result = await Runner.run(verifier_agent, report.markdown_report)
            self.printer.mark_item_done("verifying")
            verification = result.final_output_as(VerificationResult)
            span.set_attribute("verification.passed", verification.verified)
            return verification
