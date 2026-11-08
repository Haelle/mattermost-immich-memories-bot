from datetime import date

from souvenirs.immich import Memory
from souvenirs.message import format_message


def test_message_has_a_single_link_then_lists_each_memory():
    memories = [
        Memory(id="m2021", year=2021, asset_count=23, cover_asset_id="a1"),
        Memory(id="m2016", year=2016, asset_count=4, cover_asset_id="a2"),
    ]

    message = format_message(date(2026, 10, 11), memories, "immich://memory")

    assert message == (
        "#### Tes souvenirs du 11 octobre\n"
        "[Voir les souvenirs](immich://memory)\n"
        "- Il y a 5 ans — 2021 · 23 photos\n"
        "- Il y a 10 ans — 2016 · 4 photos"
    )


def test_singular_year_and_photo():
    memories = [Memory(id="m2025", year=2025, asset_count=1, cover_asset_id="a1")]

    message = format_message(date(2026, 1, 1), memories, "immich://memory?id=m2025")

    assert message == (
        "#### Tes souvenirs du 1er janvier\n"
        "[Voir les souvenirs](immich://memory?id=m2025)\n"
        "- Il y a 1 an — 2025 · 1 photo"
    )
