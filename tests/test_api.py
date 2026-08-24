from fastapi.testclient import TestClient

from backend import models
from backend.auth import get_current_user
from backend.main import app
from backend.routers.chat import get_llm


class FakeLLM:
    configured = True

    async def generate_main_response(self, message: str) -> str:
        return (
            "A convolutional neural network, or CNN, is designed for image-like data.\n\n"
            "Because the same filter scans across an image, the network learns spatially invariant features. "
            "This helps it detect useful patterns wherever they appear."
        )

    async def enhance_prompt(self, prompt: str) -> str:
        return f"Please explain {prompt.strip()} clearly with a simple example."

    async def generate_thread_response(
        self,
        *,
        original_question: str,
        original_response: str,
        selected_text: str,
        surrounding_context: str,
        history: list[dict[str, str]],
        current_question: str,
    ) -> str:
        return f"Thread answer about {selected_text}: {current_question}"


def override_llm() -> FakeLLM:
    return FakeLLM()


def override_user() -> models.User:
    return models.User(
        id="test-user",
        email="test@thread.ai",
        name="Test User",
        provider="google",
        provider_sub="google-test-user",
    )


app.dependency_overrides[get_llm] = override_llm
app.dependency_overrides[get_current_user] = override_user


def client() -> TestClient:
    return TestClient(app)


def create_response(test_client: TestClient) -> dict:
    response = test_client.post("/api/chat", json={"message": "Explain how CNNs work"})
    assert response.status_code == 201
    return response.json()


def anchor_payload(chat: dict, phrase: str, question: str = "What does this mean?") -> dict:
    start = chat["response_text"].index(phrase)
    return {
        "response_id": chat["response_id"],
        "selected_text": phrase,
        "start_offset": start,
        "end_offset": start + len(phrase),
        "surrounding_context": chat["response_text"],
        "question": question,
    }


def test_health_endpoint():
    with client() as test_client:
        response = test_client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_main_chat_endpoint():
    with client() as test_client:
        data = create_response(test_client)
    assert data["conversation_id"]
    assert data["response_id"]
    assert "spatially invariant features" in data["response_text"]


def test_prompt_enhancement_endpoint():
    with client() as test_client:
        response = test_client.post("/api/enhance-prompt", json={"prompt": "quantum computng explain easy"})
    assert response.status_code == 200
    body = response.json()
    assert body["original_prompt"] == "quantum computng explain easy"
    assert body["enhanced_prompt"].startswith("Please explain")


def test_thread_creation_and_retrieval():
    with client() as test_client:
        chat = create_response(test_client)
        created = test_client.post("/api/threads", json=anchor_payload(chat, "spatially invariant features"))
        assert created.status_code == 201
        thread_id = created.json()["thread_id"]
        fetched = test_client.get(f"/api/threads/{thread_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["selected_text"] == "spatially invariant features"
    assert [message["role"] for message in body["messages"]] == ["user", "assistant"]


def test_thread_creation_recovers_nearby_offset_drift():
    with client() as test_client:
        chat = create_response(test_client)
        phrase = "spatially invariant features"
        real_start = chat["response_text"].index(phrase)
        payload = {
            "response_id": chat["response_id"],
            "selected_text": phrase,
            "start_offset": real_start - 4,
            "end_offset": real_start - 4 + len(phrase),
            "surrounding_context": chat["response_text"],
            "question": "What does this mean?",
        }
        created = test_client.post("/api/threads", json=payload)
        fetched = test_client.get(f"/api/threads/{created.json()['thread_id']}")
    assert created.status_code == 201
    assert fetched.json()["start_offset"] == real_start
    assert fetched.json()["end_offset"] == real_start + len(phrase)


def test_same_anchor_reuses_existing_thread():
    with client() as test_client:
        chat = create_response(test_client)
        payload = anchor_payload(chat, "spatially invariant features")
        first = test_client.post("/api/threads", json=payload)
        second = test_client.post("/api/threads", json={**payload, "question": "Why is this useful?"})
        fetched = test_client.get(f"/api/threads/{first.json()['thread_id']}")
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["thread_id"] == second.json()["thread_id"]
    assert len(fetched.json()["messages"]) == 4


def test_follow_up_message():
    with client() as test_client:
        chat = create_response(test_client)
        created = test_client.post("/api/threads", json=anchor_payload(chat, "spatially invariant features"))
        thread_id = created.json()["thread_id"]
        follow_up = test_client.post(f"/api/threads/{thread_id}/messages", json={"question": "Can you give an example?"})
        fetched = test_client.get(f"/api/threads/{thread_id}")
    assert follow_up.status_code == 200
    assert len(fetched.json()["messages"]) == 4


def test_multiple_threads_on_one_response():
    with client() as test_client:
        chat = create_response(test_client)
        first = test_client.post("/api/threads", json=anchor_payload(chat, "same filter"))
        second = test_client.post("/api/threads", json=anchor_payload(chat, "useful patterns"))
        listing = test_client.get(f"/api/responses/{chat['response_id']}/threads")
    assert first.status_code == 201
    assert second.status_code == 201
    assert listing.status_code == 200
    selected = {thread["selected_text"] for thread in listing.json()}
    assert {"same filter", "useful patterns"}.issubset(selected)


def test_invalid_thread_id():
    with client() as test_client:
        response = test_client.get("/api/threads/not-a-thread")
    assert response.status_code == 404


def test_empty_question_validation():
    with client() as test_client:
        chat = create_response(test_client)
        payload = anchor_payload(chat, "spatially invariant features", question="   ")
        response = test_client.post("/api/threads", json=payload)
    assert response.status_code == 422
