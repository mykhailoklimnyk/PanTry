from komora.core.batching import interleave, key, split


def named(names, parts):
    return [tuple(names[index] for index in group) for group in split(names, parts)]


def test_a_single_batch_is_the_whole_list_untouched():
    names = ["молоко", "хліб", "кава"]
    assert named(names, 1) == [("молоко", "хліб", "кава")]


def test_zero_and_negative_parts_do_not_disable_the_call():
    assert named(["молоко", "хліб"], 0) == [("молоко", "хліб")]
    assert named(["молоко", "хліб"], -1) == [("молоко", "хліб")]


def test_nothing_to_decide_gives_no_batches_at_all():
    assert split([], 2) == ()


def test_one_intent_stays_one_call():
    assert named(["молоко"], 2) == [("молоко",)]


def test_exactly_two_intents_still_ride_in_two_batches():
    assert named(["молоко", "хліб"], 2) == [("молоко",), ("хліб",)]


def test_twins_ride_in_the_same_batch():
    names = ["молоко", "хліб", "молоко 2.5%", "кава"]
    batches = named(names, 2)
    together = next(batch for batch in batches if "молоко" in batch)
    assert "молоко 2.5%" in together


def test_batches_stay_even_when_one_kind_is_crowded():
    names = ["сир", "сир твердий", "сир кисломолочний", "хліб", "кава", "чай"]
    sizes = sorted(len(batch) for batch in named(names, 2))
    assert sizes == [3, 3]


def test_guest_order_survives_inside_a_batch():
    names = ["хліб", "сир", "сир твердий", "кава"]
    for batch in named(names, 2):
        assert list(batch) == [name for name in names if name in batch]


def test_more_batches_than_kinds_gives_no_empty_call():
    assert len(named(["молоко", "молоко 2.5%", "хліб"], 4)) == 2


def test_a_name_of_only_noise_keeps_to_itself():
    assert key("7up 0.5") == "7up 0.5"


def test_two_brands_of_one_kind_share_a_key():
    assert key("Молоко Яготинське 2.5%") == key("Молоко Простонаше 2,5% п/п")


def test_receipt_names_of_one_kind_ride_together():
    names = [
        "Молоко Яготинське 2.5% 900г",
        "Хліб «Рум'янець» цільнозерновий",
        "Молоко Простонаше 2,5% п/п",
        "Кава Jacobs Monarch розчинна",
    ]
    batches = named(names, 2)
    together = next(batch for batch in batches if names[0] in batch)
    assert names[2] in together


def test_queues_merge_by_turns_keeping_each_batch_order():
    assert interleave([["а1", "а2", "а3"], ["б1", "б2"]]) == ("а1", "б1", "а2", "б2", "а3")


def test_an_empty_queue_does_not_shift_the_other():
    assert interleave([[], ["б1", "б2"]]) == ("б1", "б2")
    assert interleave([]) == ()


def test_blyzniuky_odnoho_vydu_lyshaiutsia_v_odnii_pachtsi() -> None:
    names = [
        "Молоко Яготинське 2,5%",
        "Кефір Простонаше",
        "Молоко Простонаше ультрапастеризоване",
        "Кефір Яготинський",
    ]
    groups = split(names, 2)

    where = {index: number for number, group in enumerate(groups) for index in group}
    assert where[0] == where[2], "молоко двох марок роз'їхалось по пачках"
    assert where[1] == where[3], "кефір двох марок роз'їхався по пачках"
