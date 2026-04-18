import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from pathlib import Path

env_path = Path("C:/Users/SAURAV/OneDrive/Desktop/EduChat/.env")
load_dotenv(env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

chat_memories: Dict[str, Any] = {}


def get_langchain_llm():
    """Get LangChain Gemini LLM with Groq fallback"""
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=GEMINI_API_KEY,
        temperature=0.7,
        convert_system_message_to_human=True
    )
    
    groq_api_key = os.environ.get("GROQ_API_KEY", "")
    if groq_api_key:
        from langchain_groq import ChatGroq
        fallback_llm = ChatGroq(
            model="llama-3.3-70b-versatile",
            api_key=groq_api_key,
            temperature=0.7
        )
        return llm.with_fallbacks([fallback_llm])
        
    return llm


def get_embeddings():
    """Get HuggingFace embeddings for RAG"""
    from langchain_huggingface import HuggingFaceEmbeddings
    
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        model_kwargs={'device': 'cpu'}
    )
    return embeddings


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
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_community.vectorstores import FAISS
        from langchain_huggingface import HuggingFaceEmbeddings
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        self.embeddings = get_embeddings()
        self.vector_stores: Dict[str, Any] = {}
    
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


rag_system = DocumentRAG()


async def process_rag_query(
    message: str, 
    user: str, 
    files: List[Dict[str, Any]],
    session_id: int
) -> str:
    """Process query with RAG and Chat Memory"""
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    from langchain_core.runnables import RunnablePassthrough
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    memory = get_chat_memory(user, session_id)
    memory.add_message("user", message)
    
    context = ""
    if files and len(files) > 0:
        for file in files:
            file_type = file.get("type", "")
            file_data = file.get("data", "")
            file_name = file.get("name", "document")
            
            import base64
            from io import BytesIO
            
            if file_type == "pdf":
                try:
                    pdf_bytes = base64.b64decode(file_data)
                    if rag_system.process_pdf(pdf_bytes, file_name):
                        context = "\n\n".join(rag_system.similarity_search(message, file_name, k=2))
                except Exception as e:
                    print(f"Error processing PDF: {e}")
            
            elif file_type == "text":
                try:
                    text_data = base64.b64decode(file_data).decode() if file_data else file.get("data", "")
                    if text_data and rag_system.process_text(text_data, file_name):
                        context = "\n\n".join(rag_system.similarity_search(message, file_name, k=2))
                except Exception as e:
                    print(f"Error processing text: {e}")
    
    history = memory.get_conversation_history()
    
    llm = get_langchain_llm()
    
    if context:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are EduChat, an AI tutor. Use the provided context from documents to answer.
If context is relevant, cite it in your answer.
Be helpful and educational."""),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
    else:
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are EduChat, an AI tutor specialized in helping students learn.
Provide helpful, educational responses. Use conversation history for context."""),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
    
    chain = (
        {"input": RunnablePassthrough(), "history": lambda x: history}
        | prompt
        | llm
    )
    
    try:
        response = chain.invoke(message)
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"LangChain error: {e}")
        answer = f"I encountered an error: {str(e)}"
    
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
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    memory = get_chat_memory(user, session_id)
    history = memory.get_conversation_history()
    
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
        ("human", f"Topic: {topic}\n\nGenerate the quiz now.")
    ])
    
    chain = prompt | llm
    
    try:
        response = chain.invoke({})
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"Quiz generation error: {e}")
        answer = f"Error generating quiz: {str(e)}"
    
    return answer


async def generate_flashcards_with_rag(
    topic: str,
    num_cards: int,
    user: str,
    session_id: int
) -> str:
    """Generate flashcards using LangChain"""
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI
    
    llm = get_langchain_llm()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", f"""You are an expert educator. Create {num_cards} flashcards about the given topic.
Format each card as:
Q: [question]
A: [answer]

Make questions that test understanding. Answers should be concise but complete."""),
        ("human", f"Topic: {topic}\n\nGenerate flashcards now.")
    ])
    
    chain = prompt | llm
    
    try:
        response = chain.invoke({})
        answer = response.content if hasattr(response, 'content') else str(response)
    except Exception as e:
        print(f"Flashcard generation error: {e}")
        answer = f"Error generating flashcards: {str(e)}"
    
    return answer