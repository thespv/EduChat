import os
import httpx
import re
from typing import Optional, List, Dict, Any, Tuple
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
        self._provider_order = ["gemini", "groq", "openrouter", "openai", "anthropic"]
        
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
    
    def get_active_provider(self) -> str:
        return self._active_provider
    
    def set_active_provider(self, provider: str):
        self._active_provider = provider

    def _is_complete(self, text: str) -> bool:
        """Check if response appears complete (not truncated mid-sentence)"""
        if not text or len(text.strip()) < 10:
            return False
        
        stripped = text.strip()
        
        # Ends with proper sentence/paragraph markers
        complete_endings = ['.', '!', '?', '```', '```python', '```java', '```javascript', '```c', '```cpp']
        if any(stripped.endswith(e) for e in complete_endings):
            return True
        
        # Ends with numbered list item that has content
        if re.search(r'\d+\.\s+.*[.!?:]$', stripped):
            return True
        
        # Check for unclosed code blocks
        code_block_count = stripped.count('```')
        if code_block_count % 2 != 0:
            return False
        
        # Check for unclosed quotes/brackets at end
        last_100 = stripped[-100:]
        open_brackets = last_100.count('(') - last_100.count(')')
        open_braces = last_100.count('{') - last_100.count('}')
        if open_brackets > 0 or open_braces > 0:
            return False
        
        # Check if ends mid-word (no space/punctuation at end)
        if stripped[-1].isalpha() and len(stripped) > 5:
            # Likely truncated if last word is short and no punctuation
            words = stripped.split()
            if words and len(words[-1]) < 3:
                return False
        
        # Check for common truncation patterns
        truncation_patterns = [
            r'\.\.\.\s*$',
            r'and so on\.?\s*$',
            r'etc\.?\s*$',
            r'continue\.\.\.',
            r'\[truncated',
        ]
        if any(re.search(p, stripped, re.IGNORECASE) for p in truncation_patterns):
            return True
        
        return True

    async def call_gemini(self, prompt: str, max_tokens: int = 8192, timeout: float = 30.0) -> Optional[str]:
        api_key = self.get_current_gemini_key()
        if not api_key:
            return None
            
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent",
                    params={"key": api_key},
                    json={
                        "contents": [{"parts": [{"text": prompt}]}],
                        "generationConfig": {
                            "temperature": 0.7,
                            "maxOutputTokens": max_tokens,
                            "topP": 0.9,
                            "topK": 40
                        }
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "candidates" in data and data["candidates"]:
                        return data["candidates"][0]["content"]["parts"][0]["text"]
                    else:
                        print(f"Gemini 200 but no candidates: {data}")
                        return None
                elif response.status_code in [429, 503]:
                    self.rotate_gemini_key()
                    raise Exception("Gemini rate limit")
                else:
                    print(f"Gemini error {response.status_code}: {response.text[:300]}")
                    return None
        except Exception as e:
            err_str = str(e).lower()
            if "quota" in err_str or "429" in err_str or "503" in err_str or "rate" in err_str:
                self.rotate_gemini_key()
                raise
            print(f"Gemini exception: {e}")
            return None
    
    async def call_groq(self, prompt: str, max_tokens: int = 8192, timeout: float = 30.0) -> Optional[str]:
        if not self.groq_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.7
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    print(f"Groq 200 but no choices: {data}")
                    return None
                elif response.status_code == 429:
                    raise Exception("Groq rate limit")
                else:
                    print(f"Groq error {response.status_code}: {response.text[:300]}")
                    return None
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str:
                raise
            print(f"Groq exception: {e}")
            return None
    
    async def call_openrouter(self, prompt: str, max_tokens: int = 8192, timeout: float = 30.0) -> Optional[str]:
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
                    json={
                        "model": "meta-llama/llama-3.1-8b-instruct",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.7
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    print(f"OpenRouter 200 but no choices: {data}")
                    return None
                elif response.status_code == 429:
                    raise Exception("OpenRouter rate limit")
                else:
                    print(f"OpenRouter error {response.status_code}: {response.text[:300]}")
                    return None
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                raise
            print(f"OpenRouter exception: {e}")
            return None
    
    async def call_openai(self, prompt: str, max_tokens: int = 8192, timeout: float = 30.0) -> Optional[str]:
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
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "temperature": 0.7
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and data["choices"]:
                        return data["choices"][0]["message"]["content"]
                    print(f"OpenAI 200 but no choices: {data}")
                    return None
                elif response.status_code == 429:
                    raise Exception("OpenAI rate limit")
                else:
                    print(f"OpenAI error {response.status_code}: {response.text[:300]}")
                    return None
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                raise
            print(f"OpenAI exception: {e}")
            return None
    
    async def call_anthropic(self, prompt: str, max_tokens: int = 8192, timeout: float = 30.0) -> Optional[str]:
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
                    json={
                        "model": "claude-3-haiku-20240307",
                        "max_tokens": max_tokens,
                        "messages": [{"role": "user", "content": prompt}]
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    if "content" in data and data["content"]:
                        return data["content"][0]["text"]
                    print(f"Anthropic 200 but no content: {data}")
                    return None
                elif response.status_code == 429:
                    raise Exception("Anthropic rate limit")
                else:
                    print(f"Anthropic error {response.status_code}: {response.text[:300]}")
                    return None
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                raise
            print(f"Anthropic exception: {e}")
            return None

    async def _call_provider(self, provider: str, prompt: str, max_tokens: int) -> Tuple[Optional[str], bool]:
        """Call a specific provider. Returns (response, rate_limited)"""
        try:
            if provider == "gemini":
                result = await self.call_gemini(prompt, max_tokens)
                if result:
                    print(f"OK: Gemini ({len(result)} chars)")
                else:
                    print(f"WARN: Gemini returned None")
                return result, False
            elif provider == "groq":
                result = await self.call_groq(prompt, max_tokens)
                if result:
                    print(f"OK: Groq ({len(result)} chars)")
                else:
                    print(f"WARN: Groq returned None")
                return result, False
            elif provider == "openrouter":
                result = await self.call_openrouter(prompt, max_tokens)
                if result:
                    print(f"OK: OpenRouter ({len(result)} chars)")
                else:
                    print(f"WARN: OpenRouter returned None")
                return result, False
            elif provider == "openai":
                result = await self.call_openai(prompt, max_tokens)
                if result:
                    print(f"OK: OpenAI ({len(result)} chars)")
                else:
                    print(f"WARN: OpenAI returned None")
                return result, False
            elif provider == "anthropic":
                result = await self.call_anthropic(prompt, max_tokens)
                if result:
                    print(f"OK: Anthropic ({len(result)} chars)")
                else:
                    print(f"WARN: Anthropic returned None")
                return result, False
        except Exception as e:
            err_str = str(e).lower()
            if "rate" in err_str or "429" in err_str or "quota" in err_str:
                print(f"RATE LIMIT: {provider}")
                return None, True
            print(f"ERROR: {provider} - {e}")
            return None, False
        return None, False

    async def call_with_fallback(self, prompt: str, history_text: str = "", max_tokens: int = 8192) -> str:
        """Call providers with fallback AND continuation for incomplete answers"""
        full_answer = ""
        providers_tried = set()
        max_continuations = 3
        
        for attempt in range(max_continuations + 1):
            result = None
            rate_limited_provider = None
            
            print(f"--- Attempt {attempt + 1}, providers tried: {providers_tried} ---")
            
            # Try each provider in order, skipping already tried ones
            for provider in self._provider_order:
                if provider in providers_tried:
                    continue
                    
                # Skip providers without keys
                if provider == "gemini" and not self.gemini_keys:
                    print(f"SKIP: {provider} (no keys)")
                    continue
                if provider == "groq" and not self.groq_key:
                    print(f"SKIP: {provider} (no key)")
                    continue
                if provider == "openrouter" and not self.openrouter_key:
                    print(f"SKIP: {provider} (no key)")
                    continue
                if provider == "openai" and not self.openai_key:
                    print(f"SKIP: {provider} (no key)")
                    continue
                if provider == "anthropic" and not self.anthropic_key:
                    print(f"SKIP: {provider} (no key)")
                    continue
                
                current_prompt = prompt
                if attempt > 0 and full_answer:
                    # Get the last numbered item from the response
                    import re
                    numbers = re.findall(r'^(\d+)\.', full_answer.split('\n')[-10:], re.MULTILINE)
                    next_num = int(numbers[-1]) + 1 if numbers else 0
                    last_200 = full_answer[-200:]
                    current_prompt = f"""Continue numbered list from item {next_num}. Do NOT repeat previous items. Do NOT restart at 1.

Last item done:
{last_200}

Start with {next_num}. """
                    print(f"CONTINUATION: Asking {provider} to continue...")
                else:
                    print(f"TRYING: {provider}")
                
                result, was_rate_limited = await self._call_provider(provider, current_prompt, max_tokens)
                providers_tried.add(provider)
                
                if was_rate_limited:
                    rate_limited_provider = provider
                    continue
                
                if result:
                    self.set_active_provider(provider)
                    break
            
            if not result:
                if full_answer:
                    print(f"Returning partial answer ({len(full_answer)} chars)")
                    return full_answer
                print(f"ALL PROVIDERS FAILED")
                return "I'm having technical issues. Please try again."
            
            full_answer += result
            
            # Check if answer is complete
            if self._is_complete(full_answer):
                print(f"Answer complete ({len(full_answer)} chars)")
                break
            
            print(f"Answer incomplete, trying continuation...")
            # If incomplete, try next provider for continuation
            if rate_limited_provider:
                providers_tried.discard(rate_limited_provider)
        
        return full_answer

_api_manager = None

def get_api_manager() -> APIManager:
    global _api_manager
    if _api_manager is None:
        _api_manager = APIManager()
    return _api_manager
