import httpx

MAX_ATTACHMENTS = 10


class MattermostClient:
    def __init__(self, base_url: str, bot_token: str, http: httpx.AsyncClient):
        self._api = base_url.rstrip("/") + "/api/v4"
        self._headers = {"Authorization": f"Bearer {bot_token}"}
        self._http = http
        self._bot_user_id: str | None = None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = await self._http.request(method, self._api + path, headers=self._headers, **kwargs)
        response.raise_for_status()
        return response

    async def bot_user_id(self) -> str:
        if self._bot_user_id is None:
            self._bot_user_id = (await self._request("GET", "/users/me")).json()["id"]
        return str(self._bot_user_id)

    async def user_is_active(self, user_id: str) -> bool:
        return (await self._request("GET", f"/users/{user_id}")).json()["delete_at"] == 0

    async def direct_channel(self, user_id: str) -> str:
        response = await self._request("POST", "/channels/direct", json=[await self.bot_user_id(), user_id])
        return response.json()["id"]

    async def open_dialog(self, trigger_id: str, url: str, dialog: dict) -> None:
        await self._request(
            "POST", "/actions/dialogs/open", json={"trigger_id": trigger_id, "url": url, "dialog": dialog}
        )

    async def post(self, channel_id: str, message: str, images: list[bytes]) -> None:
        file_ids = []
        for index, image in enumerate(images[:MAX_ATTACHMENTS], start=1):
            response = await self._request(
                "POST",
                "/files",
                data={"channel_id": channel_id},
                files={"files": (f"souvenir-{index}.jpg", image, "image/jpeg")},
            )
            file_ids.append(response.json()["file_infos"][0]["id"])
        await self._request("POST", "/posts", json={"channel_id": channel_id, "message": message, "file_ids": file_ids})
