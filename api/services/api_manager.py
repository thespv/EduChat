import os
import httpx
from typing import Optional, List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"]:
    if not os.getenv(key):
        os.environ[key] = os.environ.get(key, "")

class APIManager:
    def __init__(self):
        self.gemini_keys = self._load_keys("GEMINI_API_KEY")
        self.current_gemini_index = 0
        self.groq_key = os.getenv("GROQ_API_KEY", "")
        self.openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        self.anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self._active_provider = "gemini"
        
        print(f"APIManager initialized:")
        print(f"  - Gemini keys: {len(self.gemini_keys)}")
        if self.groq_key:
            print(f"  - Groq key: {self.groq_key[:15]}...")
        else:
            print(f"  - Groq key: NOT SET")
        if self.openrouter_key:
            print(f"  - OpenRouter key: {self.openrouter_key[:15]}...")
        else:
            print(f"  - OpenRouter key: NOT SET")
        
    def _load_keys(self, env_var: str) -> List[str]:
        keys_str = os.getenv(env_var, "")
        if not keys_str:
            return []
        if "," in keys_str:
            return [k.strip() for k in keys_str.split(",") if k.strip()]
        return [keys_str] if keys_str else []
    
    def get_current_gemini_key(self) -> Optional[str]:
        if not self.gemini_keys:
            return None
        return self.gemini_keys[self.current_gemini_index % len(self.gemini_keys)]
    
    def rotate_gemini_key(self):
        if self.gemini_keys and len(self.gemini_keys) > 1:
            self.current_gemini_index = (self.current_gemini_index + 1) % len(self.gemini_keys)
            print(f"Rotated to Gemini key #{self.current_gemini_index + 1}")
    
    def get_active_provider(self) -> str:
        return self._active_provider
    
    def set_active_provider(self, provider: str):
        self._active_provider = provider
    
    async def call_gemini(self, prompt: str, history_text: str = "", timeout: float = 15.0) -> Optional[str]:
        api_key = self.get_current_gemini_key()
        if not api_key:
            print("No Gemini API key available")
            return None
            
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
                    params={"key": api_key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.9,
                            "maxOutputTokens": 2048,
                            "topP": 0.95,
                            "topK": 40
                        }
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "candidates" in data and data["candidates"]:
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    elif "promptFeedback" in data or "error" in data:
                        error_msg = data.get("error", {}).get("message", str(data))
                        print(f"Gemini error response: {error_msg}")
                        if "quota" in error_msg.lower() or "rate" in error_msg.lower():
                            self.rotate_gemini_key()
                            raise Exception("Gemini quota/rate limit")
                        return None
                elif response.status_code in [429, 503]:
                    print(f"Gemini error status: {response.status_code}")
                    self.rotate_gemini_key()
                    raise Exception(f"Gemini quota/rate limit")
                else:
                    print(f"Gemini unexpected status: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str or "503" in err_str or "rate" in err_str:
                self.rotate_gemini_key()
                raise Exception(f"Gemini quota/rate limit")
            # Don't re-raise other errors, just return None to allow fallback
            print(f"Gemini exception (returning None for fallback): {e}")
            return None
    
    async def call_groq(self, prompt: str, model: str = "llama-3.3-70b-versatile", timeout: float = 45.0) -> Optional[str]:
        if not self.groq_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]}
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    return None
                elif response.status_code == 429:
                    raise Exception("Groq rate limit")
                else:
                    print(f"Groq error {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            print(f"Groq exception: {e}")
            raise
    
    async def call_openrouter(self, prompt: str, model: str = "meta-llama/llama-3.3-70b-instruct", timeout: float = 45.0) -> Optional[str]:
        if not self.openrouter_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openrouter_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://educhat.com",
                        "X-Title": "EduChat"
                    },
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]}
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                elif response.status_code == 429:
                    raise Exception("OpenRouter rate limit")
                return None
        except:
            return None
    
    async def call_openai(self, prompt: str, model: str = "gpt-4o-mini", timeout: float = 45.0) -> Optional[str]:
        if not self.openai_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type": "application/json"
                    },
                    json={"model": model, "messages": [{"role": "user", "content": prompt}]}
                )
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                elif response.status_code == 429:
                    raise Exception("OpenAI rate limit")
                return None
        except:
            return None
    
    async def call_anthropic(self, prompt: str, model: str = "claude-3-haiku-20240307", timeout: float = 45.0) -> Optional[str]:
        if not self.anthropic_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.anthropic_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json"
                    },
                    json={"model": model, "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]}
                )
                if response.status_code == 200:
                    return response.json()["content"][0]["text"]
                elif response.status_code == 429:
                    raise Exception("Anthropic rate limit")
                return None
        except:
            return None
    
    async def call_with_fallback(self, prompt: str, history_text: str = "") -> str:
        print(f"call_with_fallback - Gemini keys: {len(self.gemini_keys)}, Groq key: {'set' if self.groq_key else 'not set'}")
        
        # Try Gemini
        if self.gemini_keys:
            try:
                print("Trying Gemini...")
                result = await self.call_gemini(prompt, history_text, timeout=20.0)
                if result:
                    self.set_active_provider("gemini")
                    print("Success with Gemini")
                    return result
                print("Gemini returned None")
            except Exception as e:
                print(f"Gemini exception: {e}")
        
        # Try Groq
        if self.groq_key:
            try:
                print("Trying Groq...")
                result = await self.call_groq(prompt)
                if result:
                    self.set_active_provider("groq")
                    print("Success with Groq")
                    return result
                print("Groq returned None")
            except Exception as e:
                print(f"Groq exception: {e}")
        
        # Try OpenRouter
        if self.openrouter_key:
            try:
                print("Trying OpenRouter...")
                result = await self.call_openrouter(prompt)
                if result:
                    self.set_active_provider("openrouter")
                    print("Success with OpenRouter")
                    return result
                print("OpenRouter returned None")
            except Exception as e:
                print(f"OpenRouter exception: {e}")
        
        # Try OpenAI
        if self.openai_key:
            try:
                print("Trying OpenAI...")
                result = await self.call_openai(prompt)
                if result:
                    self.set_active_provider("openai")
                    print("Success with OpenAI")
                    return result
                print("OpenAI returned None")
            except Exception as e:
                print(f"OpenAI exception: {e}")
        
        # Try Anthropic
        if self.anthropic_key:
            try:
                print("Trying Anthropic...")
                result = await self.call_anthropic(prompt)
                if result:
                    self.set_active_provider("anthropic")
                    print("Success with Anthropic")
                    return result
                print("Anthropic returned None")
            except Exception as e:
                print(f"Anthropic exception: {e}")
        
        print("All API providers failed")
        return "I apologize, but I'm experiencing technical difficulties. Please try again in a moment."

_api_manager = None

def get_api_manager() -> APIManager:
    global _api_manager
    if _api_manager is None:
        _api_manager = APIManager()
    return _api_manager