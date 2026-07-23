from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from athena.database import Database
from athena.debug_log import PromptLogger
from athena.model_router import ModelRouter
from athena.saved_items import SavedItemsService
from athena.search_service import SearchService
from athena.tasks import TasksService


def test_database_migrates_phase1_tasks(tmp_path: Path) -> None:
    database = Database(tmp_path / "athena.db")
    database.initialize()
    user_id = database.upsert_user(123, None, "Test", None)

    task_id = database.add_task(user_id, "finish physics homework", "2026-06-12")
    tasks = database.active_tasks(user_id)

    assert tasks[0]["id"] == task_id
    assert tasks[0]["task"] == "finish physics homework"
    assert tasks[0]["due_date"] == "2026-06-12"


def test_tasks_complete_visible_number(tmp_path: Path) -> None:
    database = Database(tmp_path / "athena.db")
    database.initialize()
    user_id = database.upsert_user(123, None, "Test", None)
    service = TasksService(database, SavedItemsService(tmp_path / "tasks"))

    service.save_task(user_id, "first task", None)
    second_id = service.save_task(user_id, "second task", None)

    reply = service.complete_task(user_id, 2)
    active = database.active_tasks(user_id)

    assert reply == "Task 2 completed."
    assert all(int(row["id"]) != second_id for row in active)


def test_tasks_can_have_no_due_date(tmp_path: Path) -> None:
    database = Database(tmp_path / "athena.db")
    database.initialize()
    user_id = database.upsert_user(123, None, "Test", None)
    service = TasksService(database, SavedItemsService(tmp_path / "tasks"))

    task_id = service.save_task(user_id, "clean desk", None)
    active = database.active_tasks(user_id)
    assert active[0]["id"] == task_id
    assert active[0]["due_date"] is None


def test_tasks_delete_visible_number(tmp_path: Path) -> None:
    database = Database(tmp_path / "athena.db")
    database.initialize()
    user_id = database.upsert_user(123, None, "Test", None)
    service = TasksService(database, SavedItemsService(tmp_path / "tasks"))

    service.save_task(user_id, "first task", None)
    second_id = service.save_task(user_id, "second task", None)

    reply = service.delete_task(user_id, 2)
    active = database.active_tasks(user_id)

    assert reply == "Task 2 deleted."
    assert all(int(row["id"]) != second_id for row in active)


def test_saved_items_file_adds_lists_and_deletes(tmp_path: Path) -> None:
    service = SavedItemsService(tmp_path / "tasks")

    service.add(1, "call mom")
    service.add(1, "finish homework")

    assert "1. call mom" in service.format_items(1)
    assert "2. finish homework" in service.format_items(1)
    assert service.delete_visible(1, 1)
    assert "call mom" not in service.format_items(1)
    assert "finish homework" in service.format_items(1)


def test_saved_items_delete_expired(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    service = SavedItemsService(tmp_path / "tasks")
    service.add(1, "drink water", datetime.now(timezone.utc) - timedelta(minutes=1))
    service.add(1, "future item", datetime.now(timezone.utc) + timedelta(minutes=5))

    removed = service.delete_expired()

    assert removed == 1
    items = service.list_active(1)
    assert [item.text for item in items] == ["future item"]


def test_search_service_parses_searxng_results(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            import json as _json
            self.content = _json.dumps(payload).encode("utf-8")

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            import json as _json
            return _json.loads(self.content.decode("utf-8"))

    payload = {
        "results": [
            {
                "title": "Weather",
                "url": "https://example.com/weather",
                "content": "Rain this afternoon.",
            }
        ]
    }

    def fake_get(*args, **kwargs):
        return FakeResponse(payload)

    monkeypatch.setattr("athena.search_service.httpx.get", fake_get)

    # Disable page fetching in the test so it only exercises the JSON parser.
    results = SearchService("http://localhost:8080", fetch_pages=False).search("weather")

    assert len(results) == 1
    assert results[0].title == "Weather"
    assert results[0].snippet == "Rain this afternoon."


def test_model_router_falls_back_from_flash_to_local(monkeypatch) -> None:
    settings = SimpleNamespace(
        gemini_api_key="key",
        gemini_flash_model="flash",
        gemini_pro_model="pro",
        alt_cloud_base_url="",
        alt_cloud_api_key="",
        alt_cloud_model="",
        ollama_url="http://localhost:11434",
        ollama_model="gemma3:4b",
    )
    router = ModelRouter.__new__(ModelRouter)
    router.settings = settings
    router.local_llm = SimpleNamespace(generate=lambda prompt: "local")
    router.prompt_logger = PromptLogger("")  # disabled

    calls: list[str] = []

    def fake_generate(model: str, prompt: str) -> str:
        calls.append(model)
        raise RuntimeError("empty")

    router.gemini_client = object()
    monkeypatch.setattr(router, "_generate_gemini", fake_generate)
    monkeypatch.setattr(router, "_has_alt_cloud", lambda: False)

    response = router.generate_response("hello", [], [])

    assert response.text == "local"
    assert response.model_name == "gemma3:4b"
    assert calls == ["flash"]
