"""HMRC integration package.

Stream A owns this directory (auth, fraud_headers, vat_client). The exception is
fake_client.py, created in Phase 0 because it is part of the interface contract
that Stream B builds against. Stream A must keep the real vat_client behaviour
consistent with the Fake's contract (idempotency, obligation lookup).
"""
