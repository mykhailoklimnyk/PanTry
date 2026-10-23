from __future__ import annotations

from typing import Any

import pytest

from komora.agent.llm import Decision, Usage
from komora.agent.pantry import forget_loop, refine
from komora.config import Settings
from komora.core.said import Said
from test_pantry_spin import (
    HERE,
    NOW,
    _batch,
    _Home,
    _stand,
    read_receipts,
)

pytestmark = pytest.mark.anyio


async def _spin(
    tmp_path,
    llm: Any,
    *,
    forget: bool = True,
    drawn: Any = None,
    answered: Any = None,
    more: bool = False,
):
    if forget:
        forget_loop()
    stand = _stand(tmp_path)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    from komora.agent.basket import pantry_live

    cold = drawn or await pantry_live(
        stand, llm=None, place=HERE, now=NOW, receipts=read, said=said
    )
    return await refine(
        stand,
        drawn=cold,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
        answered=answered,
        more=more,
        settings=Settings.model_construct(pantry_turns=1),
    )


async def test_the_guest_who_asked_for_more_questions_gets_them(tmp_path) -> None:
    answered = {"хліб · житній": 3}
    plan = "pantry.name", "pantry.rhythm"

    def _asked(done: Any) -> Any:
        (duty,) = [row for row in done.goal.duties if "питання" in row.name]
        return duty

    heard = _asked(await _spin(tmp_path, _Home(_batch(*plan)), answered=answered))
    assert heard.ok, "після «Готово» борг закритий: гість щойно відповів"
    assert heard.name == "питання цього відкриття почуті"

    owed = _asked(await _spin(tmp_path, _Home(_batch(*plan)), answered=answered, more=True))
    assert not owed.ok, "після «Ще питання» борг лишається: гість просить іще"
    assert "а питання не поставлено" in owed.why


async def test_the_agent_picks_what_to_ask_about_inside_the_loop(tmp_path) -> None:
    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))

    done = await _spin(tmp_path, llm)

    (asked,) = [step for step in done.pantry.trace if step.id == "step-pantry-ask"]
    assert asked.args["питань"] == 1
    assert asked.args["стеля"] == "3 питання"


async def test_the_model_is_given_a_closed_list_of_silent_rows(tmp_path) -> None:
    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))

    await _spin(tmp_path, llm)

    assert llm.offered, "модель не побачила жодного мовчазного рядка"


async def test_a_pantry_with_nothing_to_ask_does_not_invent_questions(tmp_path) -> None:

    class _Silent(_Home):
        async def decide(self, *, system, user, schema, **kw: Any) -> Decision:
            if "questions" in schema.get("properties", {}):
                return Decision(
                    data={"questions": []},
                    text="",
                    model="fake-model",
                    usage=Usage(1, 1),
                    duration_ms=1,
                )
            return await super().decide(system=system, user=user, schema=schema, **kw)

    llm = _Silent(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))

    done = await _spin(tmp_path, llm)

    (asked,) = [step for step in done.pantry.trace if step.id == "step-pantry-ask"]
    assert asked.args["питань"] == 0
    assert "нема про що" in asked.result_summary


async def test_the_step_is_skipped_when_the_plan_did_not_ask_for_it(tmp_path) -> None:
    llm = _Home(_batch("pantry.name", "pantry.rhythm"))

    done = await _spin(tmp_path, llm)

    assert [step for step in done.pantry.trace if step.id == "step-pantry-ask"] == []
    assert llm.offered == []


async def test_a_run_that_waits_for_the_guest_is_not_remembered_as_done(tmp_path) -> None:
    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))
    first = await _spin(tmp_path, llm)
    assert first.probes, "стенд не поставив жодного питання"

    again = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))
    second = await _spin(tmp_path, again, forget=False, drawn=first.pantry)

    assert second.probes, "петля другого разу промовчала: питання загубились"


async def test_a_row_without_a_kind_label_is_not_asked_about(tmp_path) -> None:
    llm = _Home(_batch("pantry.ask"))

    done = await _spin(tmp_path, llm)

    (asked,) = [step for step in done.pantry.trace if step.id == "step-pantry-ask"]
    assert llm.offered == [], "моделі показали рядок, у якого ще немає виду"
    assert asked.args["ще без мітки"] == 1
    assert done.probes == ()


async def test_the_agent_keeps_asking_after_an_answer_and_the_screen_decides_where(
    tmp_path,
) -> None:
    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))

    done = await _spin(tmp_path, llm, answered={"хліб": 3})

    assert done.probes, "гість відповів, а агент замовк -- питання нема кому показати"
    assert llm.offered, "переліку мовчазних рядків моделі не показали"
