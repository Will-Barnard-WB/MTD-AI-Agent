"""MTD Agent — VAT vertical slice to the HMRC sandbox.

See CONTRACT.md for the binding safety rules. The cardinal one: the LLM never
produces a figure that reaches HMRC — it only categorises; pure Python computes
every box. This package is the shared foundation both build streams depend on.
"""

__version__ = "0.1.0"
