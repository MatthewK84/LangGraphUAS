"""What a thread id may look like (the replan-child squat fix).

A replan runs on ``<parent>:<n>``, and an id with a ``:`` is owned through its
parent. A client choosing a new id therefore may not use ``:``: letters, digits,
``_`` and ``-`` only, at most 128 characters (a UUID is 36). Ids are only looked
up, never created, on GET, ack and replan, so those accept anything up to 255
characters: ids stored before this format keep working, and nothing longer
was ever accepted on replan.
"""

from typing import Final

NEW_THREAD_ID_PATTERN: Final[str] = r"^[A-Za-z0-9_-]{1,128}$"
MAX_THREAD_ID_LENGTH: Final[int] = 255
