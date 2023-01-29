from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Repair:
    failure_id: str
    repaired_cont_desc: Optional[str]
    repaired_text: Optional[str]
    repaired_hint_text: Optional[str]
