from __future__ import annotations

from komora.core.instructions import (
    KINDS,
    Audit,
    Verdict,
    audit,
    blocks,
    digest,
    fingerprint,
    rebind,
)


def tool(name: str, description: str) -> dict[str, object]:
    return {"name": name, "description": description}


def test_blocks_split_on_blank_line() -> None:
    got = blocks("Перший абзац.\n\nДРУГИЙ: текст\nз переносом.\n\n\n")
    assert got == ("Перший абзац.", "ДРУГИЙ: текст з переносом.")


def test_blocks_of_empty_description_are_empty() -> None:
    assert blocks("") == ()
    assert blocks("\n\n   \n\n") == ()


def test_fingerprint_survives_reflow_but_not_a_changed_word() -> None:
    same = fingerprint("ALWAYS fill the cart\nas close as possible")
    assert same == fingerprint("ALWAYS  fill the cart as close as possible")
    assert same != fingerprint("NEVER fill the cart as close as possible")
    assert len(same) == 12


def test_verdict_needs_a_known_kind_and_a_text() -> None:
    assert Verdict("t", "sha", "code", "виконує код").valid()
    assert not Verdict("t", "sha", "невідомий", "виконує код").valid()
    assert not Verdict("t", "sha", "code", "").valid()
    assert not Verdict("", "sha", "code", "текст").valid()
    assert not Verdict("t", "", "code", "текст").valid()


def test_audit_names_the_unjudged_block() -> None:
    tools = [tool("silpo_x", "Перше.\n\nДруге.")]
    sha = fingerprint("Перше.")
    report = audit(tools, [Verdict("silpo_x", sha, "code", "виконує код")])
    assert report.judged == 1
    assert [gap.head for gap in report.unjudged] == ["Друге."]
    assert not report.ok()
    assert report.lines() == [f"+ без вироку: silpo_x [{fingerprint('Друге.')}] Друге."]


def test_audit_names_the_verdict_that_lost_its_block() -> None:
    report = audit([tool("silpo_x", "Перше.")], [Verdict("silpo_x", "0" * 12, "code", "було")])
    assert report.judged == 0
    assert [gap.sha for gap in report.orphaned] == ["0" * 12]
    assert report.lines()[-1].startswith("- вирок без абзацу: silpo_x")


def test_audit_catches_a_broken_register_row() -> None:
    sha = fingerprint("Перше.")
    tools = [tool("silpo_x", "Перше.")]
    report = audit(tools, [Verdict("silpo_x", sha, "вигаданий", "текст")])
    assert [gap.sha for gap in report.broken] == [sha]
    assert report.lines()[-1].startswith("! кривий рядок")


def test_audit_catches_the_same_key_twice() -> None:
    sha = fingerprint("Перше.")
    rows = [Verdict("silpo_x", sha, "code", "перший"), Verdict("silpo_x", sha, "off", "другий")]
    report = audit([tool("silpo_x", "Перше.")], rows)
    assert [gap.head for gap in report.broken] == ["ключ уже є в реєстрі"]


def test_audit_of_a_matching_register_is_silent() -> None:
    tools = [tool("silpo_x", "Перше.\n\nДруге.")]
    rows = [
        Verdict("silpo_x", fingerprint(text), "code", "виконує код")
        for text in ("Перше.", "Друге.")
    ]
    report = audit(tools, rows)
    assert report.ok()
    assert report.lines() == []
    assert report.judged == 2


def test_audit_keys_by_tool_not_by_text_alone() -> None:
    tools = [tool("silpo_a", "PACKAGE SIZE: текст."), tool("silpo_b", "PACKAGE SIZE: текст.")]
    sha = fingerprint("PACKAGE SIZE: текст.")
    report = audit(tools, [Verdict("silpo_a", sha, "code", "виконує код")])
    assert [gap.tool for gap in report.unjudged] == ["silpo_b"]


def test_digest_sends_facts_whole_and_overrides_policy() -> None:
    body = "ЩО РОБИТЬ: шукає товари.\n\nBUDGET: fill the cart to the limit."
    tools = [tool("silpo_find", body)]
    rows = [
        Verdict("silpo_find", fingerprint("ЩО РОБИТЬ: шукає товари."), "code", "виконує код"),
        Verdict(
            "silpo_find",
            fingerprint("BUDGET: fill the cart to the limit."),
            "ours",
            "ціль з коридором",
        ),
    ]
    got = digest(tools, rows)
    assert got.rows == (
        "- silpo_find: ЩО РОБИТЬ: шукає товари."
        " [BUDGET: fill the cart to the limit. -- у Коморі інакше: ціль з коридором]",
    )
    assert got.dropped == 0
    assert got.unjudged == 0


def test_digest_drops_what_is_not_ours_and_counts_it() -> None:
    tools = [tool("silpo_x", "Факт.\n\nSHOW to the user.")]
    rows = [
        Verdict("silpo_x", fingerprint("Факт."), "code", "виконує код"),
        Verdict("silpo_x", fingerprint("SHOW to the user."), "off", "чат-інструкція"),
    ]
    got = digest(tools, rows)
    assert got.rows == ("- silpo_x: Факт.",)
    assert got.dropped == 1


def test_digest_marks_what_we_do_not_execute_yet() -> None:
    tools = [tool("silpo_x", "STOCK LIMIT: ніколи не перевищуй залишок.")]
    sha = fingerprint("STOCK LIMIT: ніколи не перевищуй залишок.")
    got = digest(tools, [Verdict("silpo_x", sha, "open", "кількість не ріжемо до запису")])
    assert "поки не виконуємо: кількість не ріжемо до запису" in got.rows[0]


def test_digest_skips_the_unjudged_block_and_says_how_many() -> None:
    tools = [tool("silpo_x", "Факт.\n\nНОВЕ: щойно дописали.")]
    rows = [Verdict("silpo_x", fingerprint("Факт."), "code", "виконує код")]
    got = digest(tools, rows)
    assert got.rows == ("- silpo_x: Факт.",)
    assert got.unjudged == 1


def test_digest_keeps_only_the_wanted_tools() -> None:
    tools = [tool("silpo_a", "Факт А."), tool("silpo_b", "Факт Б.")]
    rows = [
        Verdict("silpo_a", fingerprint("Факт А."), "code", "виконує код"),
        Verdict("silpo_b", fingerprint("Факт Б."), "code", "виконує код"),
    ]
    got = digest(tools, rows, wanted=["silpo_b"])
    assert got.rows == ("- silpo_b: Факт Б.",)


def test_digest_leaves_no_row_for_a_tool_with_nothing_to_say() -> None:
    tools = [tool("silpo_x", "SHOW to the user.")]
    rows = [Verdict("silpo_x", fingerprint("SHOW to the user."), "off", "чат-інструкція")]
    got = digest(tools, rows)
    assert got.rows == ()
    assert got.text() == ""


def test_digest_ignores_a_broken_register_row() -> None:
    tools = [tool("silpo_x", "Факт.")]
    got = digest(tools, [Verdict("silpo_x", fingerprint("Факт."), "вигаданий", "текст")])
    assert got.rows == ()
    assert got.unjudged == 1


def test_empty_audit_is_ok() -> None:
    assert Audit().ok()
    assert set(KINDS) == {"code", "ours", "open", "off"}


def renamed_pair() -> tuple[list[dict[str, object]], list[Verdict]]:
    body = "ЩО РОБИТЬ: шукає товари.\n\nBUDGET: fill to the limit.\n\nSIZE: displayRatio."
    rows = [
        Verdict("silpo_find_products_batch", fingerprint(block), "code", "виконує код")
        for block in blocks(body)
    ]
    return [tool("silpo_search_products", body)], rows


def test_a_renamed_tool_keeps_its_instructions_in_the_prompt() -> None:
    tools, rows = renamed_pair()
    got = digest(tools, rows, wanted=["silpo_find_products_batch"])
    assert got.unjudged == 0
    assert "ЩО РОБИТЬ: шукає товари." in got.rows[0]
    assert got.rows[0].startswith("- silpo_search_products (був silpo_find_products_batch): ")
    assert [(r.was, r.now) for r in got.renamed] == [
        ("silpo_find_products_batch", "silpo_search_products")
    ]


def test_a_rename_is_one_event_in_the_audit_and_still_red() -> None:
    tools, rows = renamed_pair()
    report = audit(tools, rows)
    assert not report.ok()
    assert report.unjudged == () and report.orphaned == ()
    assert report.lines() == [
        "~ перейменовано: silpo_find_products_batch -> silpo_search_products"
        " (3 з 3 інструкцій ті самі)"
    ]


def test_a_tool_that_also_rewrote_its_text_is_not_rebound() -> None:
    _, rows = renamed_pair()
    tools = [tool("silpo_search_products", "ЩО РОБИТЬ: шукає товари.\n\nNEW: інше.\n\nNEW2: інше.")]
    assert rebind(tools, rows) == ()
    assert digest(tools, rows).rows == ()


def test_a_shared_boilerplate_paragraph_proves_nothing() -> None:
    shared = "PACKAGE SIZE: displayRatio."
    rows = [
        Verdict("silpo_gone", fingerprint(shared), "code", "виконує код"),
        Verdict("silpo_gone", fingerprint("ЩО РОБИТЬ: своє."), "code", "виконує код"),
        Verdict("silpo_here", fingerprint(shared), "code", "виконує код"),
    ]
    tools = [tool("silpo_here", shared), tool("silpo_new", shared + "\n\nІНШЕ: зовсім.")]
    assert rebind(tools, rows) == ()


def test_a_single_paragraph_tool_proves_itself_when_that_paragraph_is_its_own() -> None:
    body = "Get loyalty card info and balance for the authenticated user."
    rows = [Verdict("silpo_get_loyalty_info", fingerprint(body), "off", "не кличемо")]
    got = rebind([tool("silpo_loyalty", body)], rows)
    assert [(r.was, r.now, r.shared, r.of) for r in got] == [
        ("silpo_get_loyalty_info", "silpo_loyalty", 1, 1)
    ]


def test_a_tie_binds_nothing() -> None:
    body = "ОДИН: текст.\n\nДВА: текст."
    rows = [Verdict("silpo_gone", fingerprint(b), "code", "виконує код") for b in blocks(body)]
    twins = [tool("silpo_a", body), tool("silpo_b", body)]
    assert rebind(twins, rows) == ()


def test_a_tool_that_is_still_here_does_not_lend_its_verdicts() -> None:
    body = "ОДИН: текст.\n\nДВА: текст."
    rows = [
        Verdict("silpo_old", fingerprint(block), "code", "виконує код") for block in blocks(body)
    ]
    tools = [tool("silpo_old", body), tool("silpo_copy", body)]
    assert rebind(tools, rows) == ()
    got = digest(tools, rows)
    assert got.rows == ("- silpo_old: ОДИН: текст. ДВА: текст.",)
    assert got.unjudged == 2
