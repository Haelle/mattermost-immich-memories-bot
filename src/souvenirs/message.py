from datetime import date

from souvenirs.immich import Memory

FRENCH_MONTHS = [
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
]


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _french_day(day: date) -> str:
    day_number = "1er" if day.day == 1 else str(day.day)
    return f"{day_number} {FRENCH_MONTHS[day.month - 1]}"


def format_message(day: date, memories: list[Memory], app_link: str, web_link: str) -> str:
    lines = [
        f"#### Tes souvenirs du {_french_day(day)}",
        f"[Ouvrir dans l'app]({app_link}) · [Ouvrir sur le web]({web_link})",
    ]
    for memory in memories:
        lines.append(
            f"- Il y a {_plural(day.year - memory.year, 'an', 'ans')} — {memory.year}"
            f" · {_plural(memory.asset_count, 'photo', 'photos')}"
        )
    return "\n".join(lines)
