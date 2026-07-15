"""Synthetic quality-check example; this file is never executed by Folder Mode."""

EXPECTED_HEADINGS = ("Introduction", "Methods", "Results", "Discussion")


def missing_headings(observed):
    """Return expected headings that are absent from supplied text."""
    return [heading for heading in EXPECTED_HEADINGS if heading not in observed]
