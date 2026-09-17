from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from komora.agent.executor import Trace
from komora.config import Settings
from komora.core.facts import Facts
from komora.db.pool import DictPool
from komora.mcp.client import SilpoMCP


@dataclass(frozen=True, slots=True)
class Ground:

    mcp: SilpoMCP
    cfg: Settings
    moment: datetime
    facts: Facts
    trace: Trace
    """Куди крок пише СВОЇ підкроки.

    Більшість кроків трейс не чіпає: їхній голос їде через `Made`, і пише
    його виконавець -- рівно один раз, зі своїм заміром часу. Але
    `intents.compose` це вісім джерел намірів, і кожне вже має власний крок
    («дописане в комору», «за циклами», «під подію», «добір під суму»).
    Злити їх в один рядок означало б забрати з трейсу ті числа, по які туди
    й заходять (#231, #209)."""
    """Мішок цілком -- для НЕОБОВ'ЯЗКОВИХ входів.

    Оголошений `needs` крок дістає зв'язаним (`Executor.run` -> `bind`), і
    саме це робить його переставним. Але є входи, яких у словнику не
    виразити: філію можна взяти з адреси АБО з кошика (#47), і жодне з двох
    не є обов'язковим -- в акаунта без адреси немає першого, у вході Б немає
    другого. Оголосити їх `needs` означало б відмовляти крокові в законному
    стані продукту; вигадати «необов'язковий вхід» у словнику -- дати моделі
    крок, чий вхід ніхто не зобов'язаний покласти. Тому такий крок читає
    мішок сам і КАЖЕ в трейсі, що саме він узяв (`source_note`).
    """
    pool: DictPool | None = None
    account: str = ""
    delivery_type: str = ""
    """Спосіб отримання цього прогону -- чисте похідне від запиту гостя
    (`delivery_type_for`), а не рішення кроку."""
    llm: Any = None
    batches: int | None = None
    """На скільки паралельних пачок різати виклики цього прогону (#198).

    `None` -- гість перемикача не чіпав, отже діє число з `.env`; це не те
    саме, що 1 (вимкнув сам). Розв'язує неоднозначність одна властивість
    нижче, а не кожен читач: читачів у пачок чотири, і четвертий забув би
    цю умову мовчки (#158)."""

    @property
    def packs(self) -> int:
        return self.cfg.pantry_batches if self.batches is None else self.batches


__all__ = ["Ground"]
