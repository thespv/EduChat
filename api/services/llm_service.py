import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pathlib import Path

env_path = Path("C:/Users/SAURAV/OneDrive/Desktop/EduChat/.env")
load_dotenv(env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

llm = None

conversation_history: Dict[str, List[Dict]] = {}


def set_api_key(api_key: str):
    global GEMINI_API_KEY
    GEMINI_API_KEY = api_key
    os.environ["GEMINI_API_KEY"] = api_key
    global llm
    llm = None


def get_gemini_llm():
    global llm
    if llm is None:
        from google import genai
        api_key = GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        print(f"get_gemini_llm - API Key: {api_key[:20] if api_key else 'None'}...")
        if not api_key:
            print("No API key available")
            return None
        try:
            client = genai.Client(api_key=api_key)
            llm = client
            print("Gemini client initialized successfully!")
            return llm
        except Exception as e:
            print(f"Error initializing Gemini: {e}")
            return None
    return llm


async def process_multimodal_query(message: str, user: str, files: List[Dict[str, Any]]) -> str:
    from google import genai
    
    api_key = os.environ.get("GEMINI_API_KEY") or "YOUR_GEMINI_API_KEY"
    
    if user not in conversation_history:
        conversation_history[user] = []
    
    history = conversation_history[user]
    chat_messages = history[-5:]
    
    history_text = ""
    if chat_messages:
        history_text = "\n".join([f"User: {m['user']}\nBot: {m['bot']}" for m in chat_messages])
    
    extracted_content = ""
    if files and len(files) > 0:
        extracted_content = extract_file_content(files)
    
    prompt = """You are EduChat, a friendly and helpful AI tutor. Provide CONCISE and MEDIUM-length educational responses.
 """
    
    if extracted_content:
        prompt += f"""
DOCUMENT CONTENT:
{extracted_content}

"""
    
    if history_text:
        prompt += f"""CONVERSATION HISTORY:
{history_text}

"""
    
    # If the user message contains its own formatting instructions (e.g. from Summarize Notes),
    # respect those instead of forcing the default paragraph format.
    has_format_override = "STRICT REQUIREMENT" in message
    
    prompt += f"""User question: {message}

"""
    if has_format_override:
        prompt += """Follow the formatting instructions given in the user question EXACTLY. Do not add paragraphs, preambles, introductions, or conversational filler.

Answer:"""
    else:
        prompt += """Keep your response:
- Concise (2-4 paragraphs max)
- Use bullet points for lists (max 5 items)
- Include code examples only if essential
- Skip elaborate headings

Answer:"""
    
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[prompt]
        )
        answer = response.text
    except Exception as e:
        print(f"Gemini API failed: {e}. Attempting fallback to Groq...")
        try:
            groq_key = os.environ.get("GROQ_API_KEY", "")
            if not groq_key:
                raise ValueError("GROQ_API_KEY not found")
            answer = await call_groq(prompt, groq_key, "llama-3.3-70b-versatile")
            print("Successfully used Groq fallback.")
        except Exception as groq_e:
            print(f"Groq API fallback failed: {groq_e}. Attempting fallback to OpenRouter...")
            try:
                openrouter_key = os.environ.get("OPENROUTER_API_KEY", "")
                if not openrouter_key:
                    raise ValueError("OPENROUTER_API_KEY not found")
                answer = await call_openrouter(prompt, openrouter_key, "meta-llama/llama-3.3-70b-instruct")
                print("Successfully used OpenRouter fallback.")
            except Exception as or_e:
                print(f"OpenRouter API fallback failed: {or_e}")
                answer = "I apologize, but all AI APIs are currently unavailable due to errors or rate limits. Please try again later."
    
    history.append({"user": message, "bot": answer})
    conversation_history[user] = history
    
    return answer


async def call_groq(prompt: str, api_key: str, model: str) -> str:
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=60.0
        )
        if response.status_code != 200:
            raise Exception(f"Groq error: {response.status_code} - {response.text}")
        return response.json()["choices"][0]["message"]["content"]


async def call_openrouter(prompt: str, api_key: str, model: str) -> str:
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "HTTP-Referer": "https://educhat.com", "X-Title": "EduChat"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=60.0
        )
        if response.status_code != 200:
            raise Exception(f"OpenRouter error: {response.status_code} - {response.text}")
        return response.json()["choices"][0]["message"]["content"]


def extract_file_content(files: List[Dict[str, Any]]) -> str:
    content_parts = []
    
    for file in files:
        file_type = file.get("type", "")
        file_name = file.get("name", "unknown")
        file_data = file.get("data", "")
        
        if file_type == "text":
            content_parts.append(f"--- File: {file_name} ---\n{file_data[:10000]}\n")
        
        elif file_type == "pdf":
            try:
                import base64
                from io import BytesIO
                from pypdf import PdfReader
                
                pdf_bytes = base64.b64decode(file_data)
                pdf_file = BytesIO(pdf_bytes)
                reader = PdfReader(pdf_file)
                
                text = ""
                for page in reader.pages:
                    text += page.extract_text() or ""
                
                if text.strip():
                    content_parts.append(f"--- PDF: {file_name} ---\n{text[:15000]}\n")
                else:
                    content_parts.append(f"--- PDF: {file_name} ---\n[PDF contains no extractable text or is scanned]\n")
            except Exception as e:
                content_parts.append(f"--- PDF: {file_name} ---\n[Error reading PDF: {str(e)}]\n")
        
        elif file_type == "image":
            content_parts.append(f"--- Image: {file_name} ---\n[Image uploaded - describe what you see in the image]\n")
        
        elif file_type == "audio":
            content_parts.append(f"--- Audio: {file_name} ---\n[Audio file uploaded - for detailed transcription, please use a specialized audio model]\n")
        
        elif file_type == "doc":
            try:
                import base64
                from io import BytesIO
                from docx import Document
                
                doc_bytes = base64.b64decode(file_data)
                doc_file = BytesIO(doc_bytes)
                doc = Document(doc_file)
                
                text = ""
                for para in doc.paragraphs:
                    text += para.text + "\n"
                
                if text.strip():
                    content_parts.append(f"--- Word Document: {file_name} ---\n{text[:15000]}\n")
                else:
                    content_parts.append(f"--- Word Document: {file_name} ---\n[Document appears to be empty]\n")
            except Exception as e:
                content_parts.append(f"--- Document: {file_name} ---\n[Error reading Word document: {str(e)}]\n")
        
        elif file_type == "pptx":
            content_parts.append(f"--- Presentation: {file_name} ---\n[PowerPoint uploaded - for full extraction, please convert to PDF]\n")
    
    return "\n".join(content_parts)


async def process_text_only(message: str, user: str, groq_llm) -> str:
    prompt = f"""You are EduChat, an AI tutor specialized in helping students learn.
User: {user}

User's message: {message}

Provide a helpful, educational response. If appropriate, include examples or explanations to help the student understand the topic better."""

    messages = [HumanMessage(content=prompt)]
    response = groq_llm.invoke(messages)
    return response.content

def generate_mock_response(message: str, user: str, files: List[Dict[str, Any]]) -> str:
    message_lower = message.lower()
    
    if files:
        file_info = f"I received {len(files)} file(s): "
        file_info += ", ".join([f["name"] for f in files])
        
        if any(f["type"] == "image" for f in files):
            file_info += ". I can see the image you've uploaded."
        elif any(f["type"] == "audio" for f in files):
            file_info += ". I've processed the audio file."
        elif any(f["type"] == "pdf" for f in files):
            file_info += ". I've analyzed the PDF content."
    else:
        file_info = ""
    
    educational_responses = {
        "tree": f"""{file_info}

Great question about trees! Here's an explanation of Binary Search Trees:

A **Binary Search Tree (BST)** is a hierarchical data structure where:
- Each node has at most two children (left and right)
- Left child contains values smaller than the parent
- Right child contains values larger than the parent

This property makes search operations efficient - O(log n) on average.

**Key Operations:**
- **Search**: Compare target with node, go left or right accordingly
- **Insert**: Find correct position, add new leaf
- **Delete**: Three cases - no children, one child, or two children

Would you like me to show code examples for any of these operations?""",
        
        "graph": f"""{file_info}

Excellent question about graphs! Let me explain:

A **Graph** consists of:
- **Vertices (V)**: Nodes representing entities
- **Edges (E)**: Connections between vertices

**Types:**
- **Directed** vs Undirected
- **Weighted** vs Unweighted
- **Cyclic** vs Acyclic

**Common Representations:**
- Adjacency Matrix
- Adjacency List

**Key Algorithms:**
- BFS (Breadth-First Search) - Level by level traversal
- DFS (Depth-First Search) - Go deep before backtracking
- Dijkstra's Algorithm - Shortest path in weighted graphs

Which specific graph topic would you like to explore further?""",
        
        "algorithm": f"""{file_info}

Algorithms are fundamental to computer science! Here are key concepts:

**Time Complexity (Big O):**
- O(1) - Constant
- O(log n) - Logarithmic  
- O(n) - Linear
- O(n log n) - Linearithmic
- O(n²) - Quadratic

**Space Complexity:**
- How much memory the algorithm needs

**Common Patterns:**
- Divide and Conquer
- Dynamic Programming
- Greedy Algorithms
- Backtracking

What specific algorithm or concept would you like to learn about?""",
        
        "default": f"""{file_info}

Thanks for your message! I'm EduChat, your AI tutor.

I can help you with:
- **Data Structures**: Trees, Graphs, Arrays, Linked Lists, etc.
- **Algorithms**: Sorting, Searching, Dynamic Programming
- **Concept Explanation**: Any CS topic you're studying
- **Code Review**: Analyzing your code
- **Practice Problems**: Generating exercises

{get_encouragement()}

What would you like to learn about today?"""
    }
    
    for key in educational_responses:
        if key in message_lower and key != "default":
            return educational_responses[key]
    
    return educational_responses["default"]

def get_encouragement():
    encouragements = [
        "Every expert was once a beginner. I'm here to help you every step of the way!",
        "Great questions lead to great learning. Keep asking!",
        "You're building strong foundations for your CS journey!",
        "Learning is a journey, and I'm here to guide you."
    ]
    import random
    return random.choice(encouragements)

class DocumentProcessor:
    @staticmethod
    def process_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return splitter.split_text(text)
    
    @staticmethod
    def process_pdf_bytes(pdf_bytes: bytes) -> List[str]:
        try:
            from pypdf import PdfReader
            from io import BytesIO
            
            pdf_file = BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            
            return DocumentProcessor.process_text(text)
        except Exception as e:
            return [f"Error processing PDF: str(e)"]
    
    @staticmethod
    def summarize_text(text: str, max_words: int = 100) -> str:
        words = text.split()
        if len(words) <= max_words:
            return text
        
        summary = " ".join(words[:max_words])
        return summary + "... [truncated]"