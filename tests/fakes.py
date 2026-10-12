import json

import httpx


class FakeMattermost:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.uploaded = 0
        self.deleted_users = {"u-gone"}
        self.failing_posts = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["authorization"] == "Bearer bot-token"
        path = request.url.path
        if path == "/api/v4/users/me":
            return httpx.Response(200, json={"id": "bot-id", "username": "souvenirs", "delete_at": 0})
        if path.startswith("/api/v4/users/"):
            user_id = path.rsplit("/", 1)[1]
            return httpx.Response(
                200, json={"id": user_id, "delete_at": 1700000000000 if user_id in self.deleted_users else 0}
            )
        if path == "/api/v4/channels/direct":
            return httpx.Response(201, json={"id": "dm-channel", "type": "D"})
        if path == "/api/v4/files":
            self.uploaded += 1
            return httpx.Response(201, json={"file_infos": [{"id": f"file-{self.uploaded}"}], "client_ids": []})
        if path == "/api/v4/posts":
            if self.failing_posts:
                return httpx.Response(500)
            return httpx.Response(201, json={"id": "post-1"})
        if path == "/api/v4/actions/dialogs/open":
            return httpx.Response(200, json={"status": "OK"})
        return httpx.Response(404)

    def bodies(self, path):
        return [json.loads(request.content) for request in self.requests if request.url.path == path]


def memory_payload(memory_id, year, asset_ids, memory_type="on_this_day", show_at="2026-10-11T00:00:00.000Z"):
    return {
        "id": memory_id,
        "createdAt": "2026-10-11T00:00:00.000Z",
        "updatedAt": "2026-10-11T00:00:00.000Z",
        "memoryAt": f"{year}-10-11T00:00:00.000Z",
        "showAt": show_at,
        "hideAt": "2026-10-12T00:00:00.000Z",
        "seenAt": None,
        "ownerId": "owner-1",
        "type": memory_type,
        "data": {"year": year},
        "isSaved": False,
        "assets": [{"id": asset_id, "type": "IMAGE"} for asset_id in asset_ids],
    }


class FakeImmich:
    def __init__(self):
        self.memories_by_key: dict[str, list[dict]] = {}
        self.latest_by_key: dict[str, list[dict]] = {}
        self.rejected_keys: set[str] = set()
        self.down = False
        self.missing_thumbnails: set[str] = set()
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return httpx.Response(503)
        key = request.headers["x-api-key"]
        if key in self.rejected_keys:
            return httpx.Response(401, json={"message": "Invalid API key"})
        if request.url.path == "/api/memories":
            memories = self.memories_by_key if "for" in request.url.params else self.latest_by_key
            return httpx.Response(200, json=memories.get(key, []))
        asset_id = request.url.path.split("/")[3]
        if asset_id in self.missing_thumbnails:
            return httpx.Response(404)
        return httpx.Response(200, content=f"jpeg-{asset_id}".encode())
