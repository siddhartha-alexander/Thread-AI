import httpx

from backend.config import Settings


class LLMService:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return self.provider is not None

    @property
    def provider(self) -> str | None:
        requested = self.settings.llm_provider.lower().strip()
        if requested == "gemini":
            return "gemini" if self.settings.gemini_api_key else None
        if requested == "groq":
            return "groq" if self.settings.groq_api_key else None
        if self.settings.gemini_api_key:
            return "gemini"
        if self.settings.groq_api_key:
            return "groq"
        return None

    async def generate_main_response(self, message: str) -> str:
        system = (
            "Write a clear, useful answer in 3 to 4 short paragraphs of plain prose. "
            "No markdown headings, no bullets, and no formatting syntax."
        )
        if not self.configured:
            return self._fallback_main(message)
        messages = [{"role": "user", "content": message}]
        return await self._call_provider(system, messages, max_tokens=700)

    async def enhance_prompt(self, prompt: str) -> str:
        system = (
            "You are THREAD AI's prompt enhancer. Rewrite the user's rough question into a clear, specific, "
            "well-structured prompt for an AI assistant.\n\n"
            "Preserve the user's intent. Fix grammar and spelling. Add helpful context, constraints, or desired "
            "output style only when they are strongly implied by the user's draft. Do not answer the prompt. "
            "Return only the improved prompt with no quotes, no label, and no extra commentary."
        )
        if not self.configured:
            return self._fallback_enhance(prompt)
        enhanced = await self._call_provider(system, [{"role": "user", "content": prompt}], max_tokens=220)
        return enhanced.strip().strip('"')

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
        system = (
            "You are THREAD AI, a contextual explanation assistant.\n\n"
            "The user has highlighted a specific portion of an AI-generated response. "
            "Answer specifically in relation to the highlighted text.\n\n"
            f"Selected text:\n{selected_text}\n\n"
            f"Surrounding context:\n{surrounding_context}\n\n"
            f"Original user question:\n{original_question}\n\n"
            f"Original AI response:\n{original_response[:5000]}\n\n"
            "Rules:\n"
            "- Focus on the selected text.\n"
            "- Use surrounding context when necessary.\n"
            "- Maintain continuity with previous thread messages.\n"
            "- Do not unnecessarily repeat the entire original answer.\n"
            "- Explain technical concepts clearly.\n"
            "- If useful, use a simple example or analogy.\n"
            "- Keep the response appropriately concise unless the user asks for detail."
        )
        if not self.configured:
            return self._fallback_thread(selected_text, current_question)
        return await self._call_provider(system, [*history, {"role": "user", "content": current_question}], max_tokens=550)

    async def _call_provider(self, system: str, messages: list[dict[str, str]], max_tokens: int = 700) -> str:
        if self.provider == "gemini":
            return await self._call_gemini(system, messages, max_tokens)
        if self.provider == "groq":
            return await self._call_groq([{"role": "system", "content": system}, *messages], max_tokens)
        raise RuntimeError("No LLM provider is configured")

    async def _call_groq(self, messages: list[dict[str, str]], max_tokens: int) -> str:
        headers = {
            "Authorization": f"Bearer {self.settings.groq_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.model_name,
            "messages": messages,
            "temperature": 0.35,
            "max_tokens": max_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(self._provider_error_message("Groq", exc.response)) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Could not connect to Groq. Check your network connection and try again.") from exc
        content = response.json()["choices"][0]["message"]["content"].strip()
        if not content:
            raise RuntimeError("LLM provider returned an empty response")
        return content

    async def _call_gemini(self, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        models_to_try = [
            self.settings.gemini_model_name,
            "gemini-3.5-flash-lite",
            "gemini-flash-lite-latest",
            "gemini-3.6-flash",
        ]
        last_error: RuntimeError | None = None
        for model_name in dict.fromkeys(models_to_try):
            try:
                return await self._call_gemini_model(model_name, system, messages, max_tokens)
            except RuntimeError as exc:
                last_error = exc
                if "status 503" not in str(exc) and "rate limit" not in str(exc).lower():
                    raise
        raise last_error or RuntimeError("Gemini request failed.")

    async def _call_gemini_model(self, model_name: str, system: str, messages: list[dict[str, str]], max_tokens: int) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {
            "x-goog-api-key": self.settings.gemini_api_key or "",
            "Content-Type": "application/json",
        }
        contents = [
            {
                "role": "model" if message["role"] == "assistant" else "user",
                "parts": [{"text": message["content"]}],
            }
            for message in messages
        ]
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.25, "maxOutputTokens": max_tokens},
        }
        try:
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(self._provider_error_message("Gemini", exc.response)) from exc
        except httpx.HTTPError as exc:
            raise RuntimeError("Could not connect to Gemini. Check your network connection and try again.") from exc
        parts = response.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
        content = "\n".join(part.get("text", "") for part in parts).strip()
        if not content:
            raise RuntimeError("Gemini returned an empty response")
        return content

    def _provider_error_message(self, provider: str, response: httpx.Response) -> str:
        try:
            message = response.json().get("error", {}).get("message")
        except ValueError:
            message = response.text
        if response.status_code in {400, 401, 403} and message:
            return f"{provider} rejected the request: {message}"
        if response.status_code == 404:
            return f"{provider} model was not found. Check the model name in .env."
        if response.status_code == 429:
            return f"{provider} rate limit reached. Try again later or use another model/key."
        return f"{provider} request failed with status {response.status_code}."

    def _fallback_main(self, message: str) -> str:
        if "convolutional" in message.lower() or "cnn" in message.lower():
            return (
                "A convolutional neural network, or CNN, is a deep learning model designed for grid-like data such as images. "
                "Instead of treating every pixel as unrelated, it preserves spatial relationships so nearby pixels can form meaningful patterns like edges, corners, and textures.\n\n"
                "The main building block is the convolutional layer. A small learned filter slides across the image and produces a feature map showing where a pattern appears.\n\n"
                "Because the same filter is reused at every position, the network learns spatially invariant features. "
                "That means once it learns to detect an edge or texture, it can recognize that feature wherever it appears in the image.\n\n"
                "Pooling layers often reduce the size of feature maps by keeping the strongest signals in small regions. "
                "This lowers computation and makes the model less sensitive to tiny shifts in the input.\n\n"
                "By stacking layers, CNNs build a hierarchy: early layers detect simple features, middle layers combine them into shapes, and later layers use those shapes to recognize objects or categories."
            )
        return (
            "THREAD AI is running in local demo mode because no Gemini or Groq API key is configured.\n\n"
            "For real answers, add GEMINI_API_KEY to the .env file and restart the backend. The app will then generate full AI responses instead of this demo placeholder.\n\n"
            f"Your question was: {message}"
        )

    def _fallback_thread(self, selected_text: str, question: str) -> str:
        if "spatially invariant" in selected_text.lower():
            return (
                "It means the network can recognize a feature regardless of where it appears in the image. "
                "For example, if a filter learns to detect a vertical edge, it can detect that edge near the top, center, or bottom because the same filter scans the whole image."
            )
        return (
            "THREAD AI is running in local demo mode because no Gemini or Groq API key is configured. "
            "Add GEMINI_API_KEY to .env and restart the backend to get contextual thread answers. "
            f"You highlighted \"{selected_text}\" and asked: {question}"
        )

    def _fallback_enhance(self, prompt: str) -> str:
        cleaned = " ".join(prompt.strip().split())
        if not cleaned:
            return cleaned
        first = cleaned[0].upper() + cleaned[1:]
        if first[-1] not in ".?!":
            first += "."
        return f"{first} Please explain it clearly, include the key ideas, and use a simple example."
