import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pathlib import Path

env_path = Path("C:/Users/SAURAV/OneDrive/Desktop/EduChat/.env")
load_dotenv(env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

from api.services.api_manager import get_api_manager

chat_memories: Dict[str, Any] = {}


def get_langchain_llm():
    """Get LangChain Gemini LLM with automatic fallback to other providers"""
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    api_manager = get_api_manager()
    gemini_key = api_manager.get_current_gemini_key()
    
    if not gemini_key:
        return get_fallback_llm()
    
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            google_api_key=gemini_key,
            temperature=0.7,
            convert_system_message_to_human=True
        )
        return llm.with_fallbacks([get_fallback_llm()])
    except Exception as e:
        print(f"Gemini LangChain init error: {e}")
        return get_fallback_llm()


def get_fallback_llm():
    """Get fallback LLM from any available provider"""
    api_manager = get_api_manager()
    
    if api_manager.groq_key:
        from langchain_groq import ChatGroq
        return ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=api_manager.groq_key,
            temperature=0.7
        )
    elif api_manager.openrouter_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct",
            api_key=api_manager.openrouter_key,
            base_url="https://openrouter.ai/api/v1"
        )
    elif api_manager.openai_key:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_manager.openai_key
        )
    
    raise Exception("No fallback API available")


_embeddings = None

def get_embeddings():
    """Get HuggingFace embeddings for RAG (Lazy Loaded)"""
    global _embeddings
    if _embeddings is None:
        print("Initializing HuggingFace embeddings (this may take a few seconds on first use)...")
        from langchain_huggingface import HuggingFaceEmbeddings
        
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cpu'}
        )
    return _embeddings


class ChatMemoryManager:
    """Manage chat history using LangChain"""
    
    def __init__(self, session_id: int, max_messages: int = 10):
        self.session_id = session_id
        self.max_messages = max_messages
        self.messages: List[Dict] = []
    
    def add_message(self, role: str, content: str):
        """Add message to memory"""
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_messages(self) -> List[Dict]:
        """Get all messages"""
        return self.messages
    
    def get_conversation_history(self) -> str:
        """Get formatted conversation history"""
        history = []
        for msg in self.messages:
            role = "User" if msg["role"] == "user" else "Assistant"
            history.append(f"{role}: {msg['content']}")
        return "\n".join(history)
    
    def clear(self):
        """Clear memory"""
        self.messages = []


def get_chat_memory(user: str, session_id: int) -> ChatMemoryManager:
    """Get or create chat memory for user/session"""
    key = f"{user}_{session_id}"
    if key not in chat_memories:
        chat_memories[key] = ChatMemoryManager(session_id)
    return chat_memories[key]


class DocumentRAG:
    """RAG system for document processing"""
    
    def __init__(self):
        self._text_splitter = None
        self._embeddings = None
        self.vector_stores: Dict[str, Any] = {}

    @property
    def text_splitter(self):
        if self._text_splitter is None:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
            self._text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200
            )
        return self._text_splitter

    @property
    def embeddings(self):
        return get_embeddings()
    
    def process_pdf(self, pdf_content: bytes, doc_name: str) -> bool:
        """Process PDF and create embeddings"""
        try:
            from pypdf import PdfReader
            from io import BytesIO
            
            pdf_file = BytesIO(pdf_content)
            reader = PdfReader(pdf_file)
            
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            
            return self._create_vector_store(text, doc_name)
        except Exception as e:
            print(f"Error processing PDF: {e}")
            return False
    
    def process_text(self, text: str, doc_name: str) -> bool:
        """Process text and create embeddings"""
        return self._create_vector_store(text, doc_name)
    
    def _create_vector_store(self, text: str, doc_name: str) -> bool:
        """Create vector store from text"""
        try:
            chunks = self.text_splitter.split_text(text)
            
            if not chunks:
                return False
            
            from langchain_community.vectorstores import FAISS
            vectorstore = FAISS.from_texts(chunks, self.embeddings)
            self.vector_stores[doc_name] = vectorstore
            return True
        except Exception as e:
            print(f"Error creating vector store: {e}")
            return False
    
    def similarity_search(self, query: str, doc_name: Optional[str] = None, k: int = 3) -> List[str]:
        """Search similar documents"""
        try:
            if doc_name and doc_name in self.vector_stores:
                docs = self.vector_stores[doc_name].similarity_search(query, k=k)
                return [doc.page_content for doc in docs]
            elif self.vector_stores:
                all_docs = []
                for vs in self.vector_stores.values():
                    docs = vs.similarity_search(query, k=k)
                    all_docs.extend([doc.page_content for doc in docs])
                return all_docs[:k]
            return []
        except Exception as e:
            print(f"Error searching: {e}")
            return []
    
    def get_retriever(self, doc_name: Optional[str] = None, k: int = 3):
        """Get retriever for chain"""
        if doc_name and doc_name in self.vector_stores:
            return self.vector_stores[doc_name].as_retriever(k=k)
        elif self.vector_stores:
            vs = list(self.vector_stores.values())[0]
            return vs.as_retriever(k=k)
        return None


_rag_system = None

def get_rag_system():
    """Get or create singleton RAG system (Lazy Loaded)"""
    global _rag_system
    if _rag_system is None:
        _rag_system = DocumentRAG()
    return _rag_system


async def process_rag_query(
    message: str, 
    user: str, 
    files: List[Dict[str, Any]],
    session_id: int
) -> str:
    """Process query with RAG and Chat Memory"""
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnablePassthrough
    
    api_manager = get_api_manager()
    memory = get_chat_memory(user, session_id)
    memory.add_message("user", message)
    
    context = ""
    print(f"RAG DEBUG: Processing {len(files) if files else 0} files")
    if files and len(files) > 0:
        for file in files:
            file_type = file.get("type", "")
            file_data = file.get("data", "")
            file_name = file.get("name", "document")
            print(f"RAG DEBUG: File type={file_type}, name={file_name}, data_len={len(file_data) if file_data else 0}")
            
            import base64
            from io import BytesIO
            
            if file_type in ("text", "pdf", "doc", "pptx"):
                try:
                    text_data = file_data if file_data else file.get("data", "")
                    
                    print(f"RAG DEBUG: Processing {file_type} {file_name}, text_len={len(text_data) if text_data else 0}")
                    print(f"RAG DEBUG: Sample text: {repr(text_data[:200])}")
                    
                    if text_data and len(text_data) > 10:
                        context = text_data
                        print(f"RAG DEBUG: Using full extracted text directly")
                except Exception as e:
                    print(f"Error processing document: {e}")
    
    history = memory.get_conversation_history()
    
    if context:
        system_msg = f"""You are EduChat, an AI tutor. A document has been uploaded. Use the following document content to answer the user's question:

DOCUMENT CONTENT:
{context}

Provide a detailed answer based on the document content above. Be helpful and educational."""
    else:
        system_msg = """You are EduChat, an AI tutor specialized in helping students learn.
Provide helpful, educational responses. Use conversation history for context."""
    
    if context:
        full_prompt = f"""{system_msg}

CONVERSATION HISTORY:
{history}

User Question: {message}

Answer:"""
    else:
        full_prompt = f"""{system_msg}

CONVERSATION HISTORY:
{history}

User Question: {message}

Answer:"""
    
    try:
        answer = await api_manager.call_with_fallback(full_prompt, "")
    except Exception as e:
        print(f"Error getting response: {e}")
        answer = "I apologize, but I encountered an error processing your document. Please try again."
    
    memory.add_message("assistant", answer)
    return answer


async def generate_quiz_with_rag(
    topic: str,
    difficulty: str,
    num_questions: int,
    user: str,
    session_id: int
) -> str:
    """Generate quiz using LangChain with context"""
    from langchain_core.prompts import ChatPromptTemplate
    
    api_manager = get_api_manager()
    memory = get_chat_memory(user, session_id)
    history = memory.get_conversation_history()
    
    prompt_text = f"""You are an expert quiz generator. Create a {difficulty} quiz with {num_questions} multiple choice questions about the given topic.
Format each question as:
Q1) [question]
A) [option1]
B) [option2]  
C) [option3]
D) [option4]
Answer: [correct answer letter]

Provide educational questions that test understanding, not just memorization.

Topic: {topic}

Generate the quiz now."""

    try:
        llm = get_langchain_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are an expert quiz generator. Create a {difficulty} quiz with {num_questions} multiple choice questions about the given topic.
Format each question as:
Q1) [question]
A) [option1]
B) [option2]  
C) [option3]
D) [option4]
Answer: [correct answer letter]

Provide educational questions that test understanding, not just memorization."""),
            ("human", "Topic: {topic}")
        ])
        
        chain = prompt | llm
        response = chain.invoke({"topic": topic})
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"Quiz generation error: {e}")
        answer = await api_manager.call_with_fallback(prompt_text, history)
    
    return answer


async def generate_flashcards_with_rag(
    topic: str,
    num_cards: int,
    user: str,
    session_id: int
) -> str:
    """Generate flashcards using LangChain"""
    from langchain_core.prompts import ChatPromptTemplate
    
    api_manager = get_api_manager()
    
    prompt_text = f"""You are an expert educator. Create {num_cards} flashcards about the given topic.
Format each card as:
Q: [question]
A: [answer]

Make questions that test understanding. Answers should be concise but complete.

Topic: {topic}

Generate flashcards now."""

    try:
        llm = get_langchain_llm()
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are an expert educator. Create {num_cards} flashcards about the given topic.
Format each card as:
Q: [question]
A: [answer]

Make questions that test understanding. Answers should be concise but complete."""),
            ("human", "Topic: {topic}")
        ])
        
        chain = prompt | llm
        response = chain.invoke({"topic": topic})
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"Flashcard generation error: {e}")
        answer = await api_manager.call_with_fallback(prompt_text, "")
    
    return answer