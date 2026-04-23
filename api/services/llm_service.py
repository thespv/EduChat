import os
import json
from typing import List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv

env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path)

for key in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "ANTHROPIC_API_KEY"]:
    if not os.getenv(key):
        os.environ[key] = os.environ.get(key, "")

from api.services.api_manager import get_api_manager

conversation_history: Dict[str, List[Dict]] = {}

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


async def process_multimodal_query(message: str, user: str, files: List[Dict[str, Any]]) -> str:
    api_manager = get_api_manager()
    
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
    
    answer = await api_manager.call_with_fallback(prompt, history_text)
    
    history.append({"user": message, "bot": answer})
    conversation_history[user] = history
    
    return answer


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
        from langchain_text_splitters import RecursiveCharacterTextSplitter
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