"""Screening text before it is allowed into the corpus.

A document is untrusted input. Its bytes were written by someone else, and the
chunks made from it end up in the same context window as a system prompt, so
this module is the boundary where that text is examined before it can travel any
further.

Two rules shape everything here.

**Normalise before you compare.** Invisible characters are stripped and the text
is NFKC-normalised *before* the content hash is taken and before any pattern is
matched. Zero-width joiners and bidirectional overrides exist precisely to make
two different strings look identical to a person and different to a matcher; a
screener that runs after hashing can be walked straight past.

**Quarantine, never drop.** A chunk that trips the tripwire is stored with the
pattern that caught it. Silently discarding it would remove a paragraph of a
manufacturer's document from the corpus without anyone knowing a limit had gone
missing, which is its own hazard.
"""

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

# Zero-width characters, bidirectional overrides, word joiners, and the BOM.
# None of these have any business in a datasheet, and all of them are standard
# ways to hide one string inside another.
INVISIBLE: Final[re.Pattern[str]] = re.compile("[​-‏‪-‮⁠-⁤﻿]")

# Markdown and HTML link syntax. URLs come from the document record, never from
# body text: a link in a chunk is either an exfiltration target or noise.
MARKDOWN_LINK: Final[re.Pattern[str]] = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
HTML_TAG: Final[re.Pattern[str]] = re.compile(r"<[^>]{1,200}>")

# The tripwire. Deliberately a small set of phrasings that have no place in a
# specification document and every place in an instruction aimed at a model.
IMPERATIVE: Final[re.Pattern[str]] = re.compile(
    r"(?i)\b("
    r"ignore (?:all |the |any )?(?:previous |prior |above )?instructions"
    r"|disregard (?:the |all )?(?:above|previous|prior)"
    r"|you are (?:now )?an? \w+"
    r"|system prompt"
    r"|always (?:say|answer|output|report|respond)"
    r"|set \w+ to \d"
    r"|assistant:"
    r"|<\|im_start\|>"
    r")"
)

# One chunk cannot be allowed to consume the context window on its own.
MAX_CHUNK_CHARS: Final[int] = 4000


class Verdict(StrEnum):
    """What screening decided about a chunk."""

    CLEAN = "clean"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class ScreenResult:
    """The outcome of screening one chunk."""

    text: str
    verdict: Verdict
    pattern: str = ""

    @property
    def is_clean(self) -> bool:
        """Return whether this chunk may enter the corpus."""
        return self.verdict is Verdict.CLEAN


def normalise(text: str) -> str:
    """Return text with invisibles stripped, NFKC-normalised, and links removed.

    Order matters. Invisible characters come out first, so a zero-width joiner
    cannot hide a keyword from the tripwire or split a word the hash would
    otherwise cover. Link syntax goes last, leaving the visible label behind so
    the sentence still reads.
    """
    stripped: str = INVISIBLE.sub("", text)
    normalised: str = unicodedata.normalize("NFKC", stripped)
    without_html: str = HTML_TAG.sub(" ", normalised)
    return MARKDOWN_LINK.sub(r"\1", without_html).strip()


def screen_chunk(text: str) -> ScreenResult:
    """Return the normalised chunk and whether it may enter the corpus.

    The tripwire is a heuristic and will occasionally fire on an innocent
    sentence in a real manual. That is why it quarantines rather than deletes,
    and why the false-positive rate is worth watching: a tripwire nobody trusts
    gets switched off, which is worse than not having one.
    """
    cleaned: str = normalise(text)[:MAX_CHUNK_CHARS]
    match = IMPERATIVE.search(cleaned)
    if match is not None:
        return ScreenResult(text=cleaned, verdict=Verdict.QUARANTINE, pattern=match.group(1))
    return ScreenResult(text=cleaned, verdict=Verdict.CLEAN)
