"""US English wordlist and repo scanner used by the spelling lint."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ALLOWLIST_FILE: Final[Path] = Path(__file__).resolve().parent / "american_english_allowlist.txt"

# Longest British forms first so a shorter stem does not eat a longer word.
# Boundaries treat underscore as a separator so get_acknowledgement is caught.
BRITISH_TO_AMERICAN: Final[tuple[tuple[str, str], ...]] = (
    ("acknowledgements", "acknowledgments"),
    ("acknowledgement", "acknowledgment"),
    ("serialisable", "serializable"),
    ("unlabelled", "unlabeled"),
    ("mislabelled", "mislabeled"),
    ("penalising", "penalizing"),
    ("penalises", "penalizes"),
    ("penalised", "penalized"),
    ("penalise", "penalize"),
    ("authorisations", "authorizations"),
    ("authorisation", "authorization"),
    ("authorising", "authorizing"),
    ("authorises", "authorizes"),
    ("authorised", "authorized"),
    ("authorise", "authorize"),
    ("initialisation", "initialization"),
    ("initialising", "initializing"),
    ("initialises", "initializes"),
    ("initialised", "initialized"),
    ("initialise", "initialize"),
    ("serialisation", "serialization"),
    ("serialising", "serializing"),
    ("serialises", "serializes"),
    ("serialised", "serialized"),
    ("serialise", "serialize"),
    ("normalisation", "normalization"),
    ("normalising", "normalizing"),
    ("normalises", "normalizes"),
    ("normalised", "normalized"),
    ("normalise", "normalize"),
    ("characterising", "characterizing"),
    ("characterises", "characterizes"),
    ("characterised", "characterized"),
    ("characterise", "characterize"),
    ("standardising", "standardizing"),
    ("standardises", "standardizes"),
    ("standardised", "standardized"),
    ("standardise", "standardize"),
    ("organisation", "organization"),
    ("organisations", "organizations"),
    ("organising", "organizing"),
    ("organises", "organizes"),
    ("organised", "organized"),
    ("organise", "organize"),
    ("optimisation", "optimization"),
    ("optimising", "optimizing"),
    ("optimises", "optimizes"),
    ("optimised", "optimized"),
    ("optimise", "optimize"),
    ("visualising", "visualizing"),
    ("visualises", "visualizes"),
    ("visualised", "visualized"),
    ("visualise", "visualize"),
    ("specialising", "specializing"),
    ("specialises", "specializes"),
    ("specialised", "specialized"),
    ("specialise", "specialize"),
    ("customising", "customizing"),
    ("customises", "customizes"),
    ("customised", "customized"),
    ("customise", "customize"),
    ("generalising", "generalizing"),
    ("generalises", "generalizes"),
    ("generalised", "generalized"),
    ("generalise", "generalize"),
    ("summarises", "summarizes"),
    ("summarised", "summarized"),
    ("summarise", "summarize"),
    ("recognising", "recognizing"),
    ("recognises", "recognizes"),
    ("recognised", "recognized"),
    ("recognise", "recognize"),
    ("prioritises", "prioritizes"),
    ("prioritised", "prioritized"),
    ("prioritise", "prioritize"),
    ("formalises", "formalizes"),
    ("formalised", "formalized"),
    ("formalise", "formalize"),
    ("minimising", "minimizing"),
    ("minimises", "minimizes"),
    ("minimised", "minimized"),
    ("minimise", "minimize"),
    ("maximises", "maximizes"),
    ("maximised", "maximized"),
    ("maximise", "maximize"),
    ("analysing", "analyzing"),
    ("analysed", "analyzed"),
    ("analyser", "analyzer"),
    ("analyse", "analyze"),
    ("realising", "realizing"),
    ("realises", "realizes"),
    ("realised", "realized"),
    ("realise", "realize"),
    ("utilises", "utilizes"),
    ("utilised", "utilized"),
    ("utilise", "utilize"),
    ("behaviours", "behaviors"),
    ("behaviour", "behavior"),
    ("colouring", "coloring"),
    ("coloured", "colored"),
    ("colours", "colors"),
    ("colour", "color"),
    ("licences", "licenses"),
    ("licenced", "licensed"),
    ("licence", "license"),
    ("catalogues", "catalogs"),
    ("catalogued", "cataloged"),
    ("catalogue", "catalog"),
    ("centres", "centers"),
    ("centred", "centered"),
    ("centre", "center"),
    ("metres", "meters"),
    ("metre", "meter"),
    ("favourable", "favorable"),
    ("favourite", "favorite"),
    ("favours", "favors"),
    ("favour", "favor"),
    ("travelling", "traveling"),
    ("traveller", "traveler"),
    ("travelled", "traveled"),
    ("modelling", "modeling"),
    ("modelled", "modeled"),
    ("signalling", "signaling"),
    ("signalled", "signaled"),
    ("cancelling", "canceling"),
    ("cancelled", "canceled"),
    ("labelling", "labeling"),
    ("labelled", "labeled"),
    ("judgements", "judgments"),
    ("judgement", "judgment"),
    ("programmes", "programs"),
    ("programme", "program"),
    ("defences", "defenses"),
    ("defence", "defense"),
    ("offences", "offenses"),
    ("offence", "offense"),
    ("honouring", "honoring"),
    ("honoured", "honored"),
    ("honours", "honors"),
    ("honour", "honor"),
    ("rumours", "rumors"),
    ("rumour", "rumor"),
    ("neighbours", "neighbors"),
    ("neighbourhood", "neighborhood"),
    ("neighbour", "neighbor"),
    ("dialogues", "dialogs"),
    ("dialogue", "dialog"),
    ("analogues", "analogs"),
    ("analogue", "analog"),
    ("artefacts", "artifacts"),
    ("artefact", "artifact"),
    ("fulfilment", "fulfillment"),
    ("fulfil", "fulfill"),
    ("skilful", "skillful"),
    ("focussed", "focused"),
    ("aeroplane", "airplane"),
    ("aluminium", "aluminum"),
    ("amongst", "among"),
    ("whilst", "while"),
    ("tyres", "tires"),
    ("tyre", "tire"),
    ("cheque", "check"),
    ("grey", "gray"),
)

# Underscore is a separator, not a word character, so snake_case identifiers match.
BRITISH_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![A-Za-z])("
    + "|".join(re.escape(src) for src, _ in BRITISH_TO_AMERICAN)
    + r")(?![A-Za-z])",
    re.IGNORECASE,
)

SKIP_DIRS: Final[frozenset[str]] = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "coverage",
        ".metrics",
        "__pycache__",
        ".ruff_cache",
        ".pytest_cache",
        ".next",
    }
)
SKIP_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".lock",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".webm",
        ".pdf",
        ".ulg",
        ".woff",
        ".woff2",
        ".ttf",
        ".ico",
        ".map",
        ".pyc",
        ".tsbuildinfo",
    }
)
# This module must itself list British forms; the allowlist file names @img/colour.
SELF_RELATIVE: Final[frozenset[str]] = frozenset(
    {
        "backend/tests/american_english.py",
        "backend/tests/american_english_allowlist.txt",
    }
)


def allowlisted_prefixes() -> tuple[str, ...]:
    """Return repo-relative path prefixes that the lint leaves alone."""
    prefixes: list[str] = []
    for raw in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            prefixes.append(line)
    return tuple(prefixes)


def is_allowlisted(relative: str, prefixes: tuple[str, ...]) -> bool:
    """Return whether this repo-relative path is exempt from the spelling lint."""
    posix = relative.replace("\\", "/")
    if posix in SELF_RELATIVE:
        return True
    for prefix in prefixes:
        if posix == prefix or posix.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def iter_text_files() -> Iterator[Path]:
    """Yield first-party text files under the repo root, excluding noise."""
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("eval/results/"):
            continue
        if path.suffix.lower() in SKIP_SUFFIXES:
            continue
        if path.name == "package-lock.json":
            continue
        yield path


def british_hits(text: str) -> list[tuple[int, str, str]]:
    """Return (line number, matched word, line) for each British spelling."""
    found: list[tuple[int, str, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        found.extend(
            (number, match.group(1), line.strip()) for match in BRITISH_PATTERN.finditer(line)
        )
    return found
