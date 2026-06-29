"""CLI entrypoint — `python -m mtd_agent.cli demo`.

v1 runs against the FakeHmrcVatClient (Stream A's real client lands in Phase 3).
Use --fake-llm to categorise offline with zero API cost; --real-llm calls OpenAI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mtd_agent.config import Settings
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.nodes.approval import CLIApprover
from mtd_agent.nodes.extract import FakeCategoriser, OpenAICategoriser

_DEFAULT_CSV = Path("examples/sample_transactions.csv")


def _demo(args: argparse.Namespace) -> int:
    if args.real_llm:
        settings = Settings.load()
        if not settings.openai_api_key:
            print("OPENAI_API_KEY not set — use --fake-llm for an offline run.")
            return 2
        categoriser = OpenAICategoriser(settings.openai_api_key, settings.extraction_model)
        vrn = settings.hmrc_test_vrn or "123456789"
    else:
        categoriser = FakeCategoriser()
        vrn = "123456789"

    # v1: fake HMRC client. Phase 3 swaps in Stream A's real vat_client.
    client = FakeHmrcVatClient()

    result = run_pipeline(
        csv_path=args.csv,
        vrn=vrn,
        client=client,
        categoriser=categoriser,
        approver=CLIApprover(),
        finalised=not args.draft,
    )

    print(f"\nStatus: {result.status.value}")
    print(f"Audit log: {result.audit_path}")
    if result.status == Status.SUBMITTED and result.receipt:
        print(f"Period: {result.period_key}")
        print(f"HMRC form bundle: {result.receipt.form_bundle_number}")
    elif result.status == Status.INCOMPLETE:
        print(f"Issues: {result.issues}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="mtd_agent")
    sub = parser.add_subparsers(dest="command", required=True)

    demo = sub.add_parser("demo", help="Run the VAT slice end to end.")
    demo.add_argument("--csv", type=Path, default=_DEFAULT_CSV)
    demo.add_argument("--real-llm", action="store_true", help="Use OpenAI (spends credits).")
    demo.add_argument("--fake-llm", dest="real_llm", action="store_false",
                      help="Offline keyword categoriser (default).")
    demo.add_argument("--draft", action="store_true", help="Submit with finalised=false.")
    demo.set_defaults(func=_demo, real_llm=False)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
