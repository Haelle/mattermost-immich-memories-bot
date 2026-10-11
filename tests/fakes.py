import httpx


def memory_payload(memory_id, year, asset_ids, memory_type="on_this_day"):
    return {
        "id": memory_id,
        "createdAt": "2026-10-11T00:00:00.000Z",
        "updatedAt": "2026-10-11T00:00:00.000Z",
        "memoryAt": f"{year}-10-11T00:00:00.000Z",
        "showAt": "2026-10-11T00:00:00.000Z",
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
            return httpx.Response(200, json=self.memories_by_key.get(key, []))
        asset_id = request.url.path.split("/")[3]
        if asset_id in self.missing_thumbnails:
            return httpx.Response(404)
        return httpx.Response(200, content=f"jpeg-{asset_id}".encode())
