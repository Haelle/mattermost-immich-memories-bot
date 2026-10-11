from datetime import date

from souvenirs.immich import Memory
from souvenirs.message import format_message

LINK_TEMPLATE = "immich://memory?id={id}"


def test_message_lists_each_memory_with_age_year_count_and_link():
    memories = [
        Memory(id="m2021", year=2021, asset_count=23, cover_asset_id="a1"),
        Memory(id="m2016", year=2016, asset_count=4, cover_asset_id="a2"),
    ]

    message = format_message(date(2026, 10, 11), memories, LINK_TEMPLATE)

    assert message == (
        "#### Tes souvenirs du 11 octobre\n"
        "- [Il y a 5 ans — 2021 · 23 photos](immich://memory?id=m2021)\n"
        "- [Il y a 10 ans — 2016 · 4 photos](immich://memory?id=m2016)"
    )


def test_singular_year_and_photo():
    memories = [Memory(id="m2025", year=2025, asset_count=1, cover_asset_id="a1")]

    message = format_message(date(2026, 1, 1), memories, LINK_TEMPLATE)

    assert message == "#### Tes souvenirs du 1er janvier\n- [Il y a 1 an — 2025 · 1 photo](immich://memory?id=m2025)"


def test_link_template_is_configurable():
    memories = [Memory(id="m2020", year=2020, asset_count=2, cover_asset_id="a1")]

    message = format_message(date(2026, 8, 15), memories, "https://photos.example/memories/{id}")

    assert message.splitlines() == [
        "#### Tes souvenirs du 15 août",
        "- [Il y a 6 ans — 2020 · 2 photos](https://photos.example/memories/m2020)",
    ]
