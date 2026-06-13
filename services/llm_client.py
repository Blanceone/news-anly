"""统一 LLM 调用客户端"""
import requests

from config import Config


class LLMClient:
    def __init__(self):
        self.provider = self._detect()
        self.model = self._resolve_model()

    def _detect(self) -> str:
        if Config.GEMINI_API_KEY:
            return "gemini"
        if Config.DEEPSEEK_API_KEY:
            return "deepseek"
        if Config.OPENAI_API_KEY:
            return "openai"
        return "none"

    def _resolve_model(self) -> str:
        return {
            "gemini": "gemini-2.0-flash",
            "deepseek": Config.DEEPSEEK_MODEL,
            "openai": Config.OPENAI_MODEL,
        }.get(self.provider, "")

    @property
    def available(self) -> bool:
        return self.provider != "none"

    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
        if not self.available:
            return ""
        if self.provider == "gemini":
            return self._call_gemini(system_prompt, user_prompt, temperature)
        return self._call_openai_compat(system_prompt, user_prompt, temperature)

    def _call_gemini(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={Config.GEMINI_API_KEY}"
        contents = []
        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": system_prompt}]})
            contents.append({"role": "model", "parts": [{"text": "好的，我明白要求了。"}]})
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})
        payload = {"contents": contents, "generationConfig": {"temperature": temperature}}
        try:
            resp = requests.post(url, json=payload, timeout=60)
            data = resp.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        except Exception as e:
            return f""

    def _call_openai_compat(self, system_prompt: str, user_prompt: str, temperature: float) -> str:
        if self.provider == "deepseek":
            api_key, base_url = Config.DEEPSEEK_API_KEY, "https://api.deepseek.com/v1"
        else:
            api_key, base_url = Config.OPENAI_API_KEY, Config.OPENAI_BASE_URL or "https://api.openai.com/v1"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})
        payload = {"model": self.model, "messages": messages, "temperature": temperature}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        try:
            resp = requests.post(f"{base_url.rstrip('/')}/chat/completions", json=payload, headers=headers, timeout=60)
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
        except Exception as e:
            return ""
