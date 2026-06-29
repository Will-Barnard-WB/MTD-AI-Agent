"""Pipeline nodes (Stream B). Each node is a small, independently testable unit.

The spine: ingest → extract → completeness → compute_vat → approval → submit,
with audit emitted at every step. compute_vat is PURE; the LLM lives only in
extract and emits no figure (see CONTRACT.md §1).
"""
