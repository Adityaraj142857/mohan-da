"""Bank-specific SMS parser plug-ins (SPEC 11.2, 3.7). Each module exposes
SENDER_REGEX and BANK_NAME; `registry.py` tries them in order before
falling back to `generic.py`. These four are SYNTHETIC examples matching
SPEC Appendix D — replace/extend with the owner's real (redacted) bank
sender IDs and, if needed, bank-specific extraction quirks."""
