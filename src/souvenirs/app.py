import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Annotated

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import Response

from souvenirs.immich import ImmichClient, ImmichKeyRejected, ImmichUnavailable
from souvenirs.mattermost import MattermostClient
from souvenirs.schedule import parse_time
from souvenirs.sender import Outcome, Sender
from souvenirs.store import Store

DIALOG_STATE_LIFETIME = timedelta(minutes=10)
DEFAULT_SEND_TIME = time(9, 0)

HELP = """Commandes disponibles :
- `/souvenirs activer` : t'inscrire ou remplacer ta clé Immich
- `/souvenirs statut` : voir ton inscription
- `/souvenirs heure HH:MM` : changer l'heure d'envoi quotidienne
- `/souvenirs test` : recevoir tout de suite les souvenirs du jour, ou le dernier s'il n'y en a pas
- `/souvenirs désactiver` : te désinscrire et supprimer ta clé"""

NOT_REGISTERED = "Tu n'es pas inscrit. Lance `/souvenirs activer`."

KEY_PERMISSIONS_REMINDER = (
    "Dans Immich : Paramètres du compte → Clés API. Coche uniquement la lecture des souvenirs et la lecture des photos."
)


@dataclass(frozen=True)
class PendingDialog:
    mm_user_id: str
    expires_at: datetime


def ephemeral(text: str) -> dict:
    return {"response_type": "ephemeral", "text": text}


def create_app(
    store: Store,
    mattermost: MattermostClient,
    immich_for: Callable[[str], ImmichClient],
    sender: Sender,
    command_tokens: set[str],
    callback_url: str,
    clock: Callable[[], datetime] = datetime.now,
    lifespan=None,
) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    pending_dialogs: dict[str, PendingDialog] = {}

    async def activate(user_id: str, trigger_id: str) -> Response:
        state = secrets.token_urlsafe(32)
        registered = store.get(user_id)
        current_send_time = registered.send_time if registered else DEFAULT_SEND_TIME
        pending_dialogs[state] = PendingDialog(user_id, clock() + DIALOG_STATE_LIFETIME)
        await mattermost.open_dialog(
            trigger_id,
            callback_url.rstrip("/") + "/dialog",
            {
                "callback_id": "activate",
                "title": "Activer les souvenirs",
                "introduction_text": KEY_PERMISSIONS_REMINDER,
                "submit_label": "Activer",
                "state": state,
                "elements": [
                    {
                        "display_name": "Clé API Immich",
                        "name": "immich_key",
                        "type": "text",
                        "subtype": "password",
                    },
                    {
                        "display_name": "Heure d'envoi quotidienne",
                        "name": "send_time",
                        "type": "text",
                        "default": f"{current_send_time:%H:%M}",
                        "placeholder": "HH:MM",
                        "help_text": "Format HH:MM, modifiable ensuite avec /souvenirs heure.",
                    },
                ],
            },
        )
        return Response(status_code=200)

    def status(user_id: str) -> dict:
        user = store.get(user_id)
        if user is None:
            return ephemeral(NOT_REGISTERED)
        lines = [
            f"Souvenirs : {'actifs' if user.active else 'inactifs'}",
            f"Heure d'envoi : {user.send_time:%H:%M}",
            f"Inscrit le : {user.created_at:%d/%m/%Y}",
            f"Dernier envoi : {user.last_sent_on:%d/%m/%Y}" if user.last_sent_on else "Dernier envoi : jamais",
        ]
        if user.last_error:
            lines.append(f"Dernière erreur : {user.last_error}")
        return ephemeral("\n".join(lines))

    def send_time(user_id: str, value: str) -> dict:
        user = store.get(user_id)
        if user is None:
            return ephemeral(NOT_REGISTERED)
        if not value:
            return ephemeral(f"Ton heure d'envoi est {user.send_time:%H:%M}.")
        new_time = parse_time(value)
        if new_time is None:
            return ephemeral("Heure invalide, utilise le format HH:MM (ex. `/souvenirs heure 07:30`).")
        store.set_send_time(user_id, new_time)
        return ephemeral(f"Tes souvenirs arriveront désormais à {new_time:%H:%M}.")

    async def send_test(user_id: str) -> dict:
        user = store.get(user_id)
        if user is None:
            return ephemeral(NOT_REGISTERED)
        outcome = await sender.deliver(user, clock().date())
        if outcome is Outcome.NO_MEMORIES:
            outcome = await sender.deliver_latest(user)
            if outcome is Outcome.SENT:
                return ephemeral("Pas de souvenir aujourd'hui, je t'ai envoyé le dernier dans ta conversation privée.")
        return ephemeral(
            {
                Outcome.SENT: "C'est envoyé, regarde ta conversation privée avec le bot.",
                Outcome.NO_MEMORIES: "Aucun souvenir dans Immich pour l'instant.",
                Outcome.KEY_REJECTED: "Ta clé Immich ne fonctionne plus, relance `/souvenirs activer`.",
                Outcome.FAILED: "L'envoi a échoué, réessaie plus tard (`/souvenirs statut` pour le détail).",
            }[outcome]
        )

    @app.post("/command", response_model=None)
    async def slash_command(
        token: Annotated[str, Form()],
        user_id: Annotated[str, Form()],
        text: Annotated[str, Form()] = "",
        trigger_id: Annotated[str, Form()] = "",
    ) -> dict | Response:
        if not any(secrets.compare_digest(token, known) for known in command_tokens):
            raise HTTPException(status_code=401)
        action, _, argument = text.strip().partition(" ")
        match action.lower():
            case "activer":
                return await activate(user_id, trigger_id)
            case "statut":
                return status(user_id)
            case "heure":
                return send_time(user_id, argument.strip())
            case "test":
                return await send_test(user_id)
            case "désactiver" | "desactiver":
                store.delete(user_id)
                return ephemeral("Souvenirs désactivés, ta clé a été supprimée.")
            case _:
                return ephemeral(HELP)

    @app.post("/dialog")
    async def dialog_submission(payload: dict) -> dict:
        state = payload.get("state", "")
        user_id = payload.get("user_id", "")
        pending = pending_dialogs.get(state)
        if pending is None or pending.mm_user_id != user_id or clock() > pending.expires_at:
            raise HTTPException(status_code=403)

        submission = payload.get("submission", {})
        immich_key = submission.get("immich_key", "").strip()
        chosen_send_time = parse_time(submission.get("send_time", "").strip())
        if chosen_send_time is None:
            return {"errors": {"send_time": "Heure invalide, utilise le format HH:MM."}}
        try:
            await immich_for(immich_key).memories_on(clock().date())
        except ImmichKeyRejected:
            return {"errors": {"immich_key": "Clé invalide ou permissions insuffisantes."}}
        except ImmichUnavailable:
            return {"errors": {"immich_key": "Immich est injoignable, réessaie dans quelques minutes."}}

        del pending_dialogs[state]
        dm_channel_id = await mattermost.direct_channel(user_id)
        user = store.register(user_id, dm_channel_id, immich_key, chosen_send_time)
        await mattermost.post(
            dm_channel_id,
            f"Souvenirs activés. Tu recevras un message chaque jour où tu as des souvenirs, à {user.send_time:%H:%M} "
            "(`/souvenirs heure` pour changer).",
            [],
        )
        return {}

    return app
