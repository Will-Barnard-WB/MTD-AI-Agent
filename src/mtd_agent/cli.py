"""CLI entrypoint — `python -m mtd_agent.cli demo`.

Two independent axes:
  * categoriser: --fake-llm (offline keyword rules, default, zero cost) | --real-llm (OpenAI)
  * HMRC client: default FakeHmrcVatClient (offline) | --live (real sandbox vat_client)

The default `demo` is fully offline (Fake + Fake). `--live` runs the real slice against the
HMRC VAT *sandbox* and needs creds in .env (HMRC_CLIENT_ID/SECRET + an authorised token via
get_token, and HMRC_TEST_VRN). It stays sandbox-only — config.assert_sandbox blocks production.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from mtd_agent.config import Settings
from mtd_agent.graph.pipeline import run_pipeline
from mtd_agent.graph.state import Status
from mtd_agent.hmrc.errors import HmrcAuthError, HmrcError
from mtd_agent.hmrc.fake_client import FakeHmrcVatClient
from mtd_agent.hmrc.vat_client import HmrcVatClient
from mtd_agent.nodes.approval import CLIApprover
from mtd_agent.nodes.extract import FakeCategoriser, OpenAICategoriser

_DEFAULT_CSV = Path("examples/sample_transactions.csv")


def _demo(args: argparse.Namespace) -> int:
    settings = Settings.load()

    # Categoriser (the LLM axis)
    if args.real_llm:
        if not settings.openai_api_key:
            print("OPENAI_API_KEY not set — use --fake-llm for an offline run.")
            return 2
        categoriser = OpenAICategoriser(settings.openai_api_key, settings.extraction_model)
    else:
        categoriser = FakeCategoriser()

    # HMRC client (the submission axis)
    if args.live:
        if not (settings.hmrc_client_id and settings.hmrc_client_secret):
            print("HMRC sandbox creds not set in .env (HMRC_CLIENT_ID/HMRC_CLIENT_SECRET).\n"
                  "See BLOCKERS.md. Omit --live for an offline Fake run.")
            return 2
        if not settings.hmrc_test_vrn:
            print("HMRC_TEST_VRN not set — needed for a --live run. See BLOCKERS.md.")
            return 2
        client = HmrcVatClient(settings)
        vrn = settings.hmrc_test_vrn
    else:
        client = FakeHmrcVatClient()
        vrn = "123456789"

    try:
        result = run_pipeline(
            csv_path=args.csv,
            vrn=vrn,
            client=client,
            categoriser=categoriser,
            approver=CLIApprover(),
            finalised=not args.draft,
        )
    except HmrcError as exc:
        print(f"\nHMRC error ({exc.kind}): {exc.message}")
        if isinstance(exc, HmrcAuthError):
            print("Authorise the sandbox first:  python -m mtd_agent.hmrc.get_token")
        return 1

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
    demo.add_argument("--live", action="store_true",
                      help="Submit to the real HMRC VAT sandbox (needs .env creds + test user). "
                           "Default: offline FakeHmrcVatClient.")
    demo.add_argument("--draft", action="store_true", help="Submit with finalised=false.")
    demo.set_defaults(func=_demo, real_llm=False)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
