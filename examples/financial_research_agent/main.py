import argparse
import asyncio

from .manager import FinancialResearchManager


# Entrypoint for the financial bot example.
# Run this as `python -m examples.financial_research_agent.main` and enter a
# financial research query, for example:
# "Write up an analysis of Apple Inc.'s most recent quarter."
# Or specify the query directly: `python -m examples.financial_research_agent.main --query "..."`
async def main() -> None:
    parser = argparse.ArgumentParser(description="Financial research agent")
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Financial research query to execute",
    )
    args = parser.parse_args()

    query = args.query if args.query else input("Enter a financial research query: ")
    mgr = FinancialResearchManager()
    await mgr.run(query)


if __name__ == "__main__":
    asyncio.run(main())
