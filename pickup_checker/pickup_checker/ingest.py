"""Input-mode detection and document loading. Mode is a RUN-LEVEL property,
resolved once here and threaded through the whole pipeline -- Finding and
Assessment don't each re-derive it."""
from __future__ import annotations

from dataclasses import dataclass

import pdfplumber

from pickup_checker.models import InputMode


def detect_input_mode(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
) -> InputMode:
    if prior_marked and prior_clean:
        raise ValueError("provide prior_marked OR prior_clean, not both")
    if not prior_marked and not prior_clean:
        raise ValueError("a prior issue is required (prior_marked or prior_clean)")
    if prior_marked:
        return InputMode.MARKED_PRIOR
    if markup_file:
        return InputMode.SEPARATE_MARKUP
    return InputMode.CLEAN_ONLY


@dataclass
class DocumentSet:
    mode: InputMode
    prior: pdfplumber.PDF
    revised: pdfplumber.PDF
    markup: pdfplumber.PDF | None
    prior_id: str
    revised_id: str

    def close(self) -> None:
        self.prior.close()
        self.revised.close()
        if self.markup is not None:
            self.markup.close()


def load_documents(
    prior_marked: str | None,
    prior_clean: str | None,
    markup_file: str | None,
    revised: str,
) -> DocumentSet:
    mode = detect_input_mode(prior_marked, prior_clean, markup_file, revised)
    prior_path = prior_marked or prior_clean
    assert prior_path is not None  # detect_input_mode already guarantees this
    return DocumentSet(
        mode=mode,
        prior=pdfplumber.open(prior_path),
        revised=pdfplumber.open(revised),
        markup=pdfplumber.open(markup_file) if markup_file else None,
        prior_id=prior_path,
        revised_id=revised,
    )
