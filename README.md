# EduChat - AI-Powered Educational Assistant

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue" alt="Version">
  <!-- <img src="https://img.shields.io/badge/license-MIT-green" alt="License"> -->
  <img src="https://img.shields.io/badge/python-3.10+-orange" alt="Python">
  <img src="https://img.shields.io/badge/fastapi-red" alt="FastAPI">
</p>

EduChat is an AI-powered multimodal learning assistant designed for students and educators. It combines RAG (Retrieval Augmented Generation) technology with large language models to provide personalized tutoring, study tools, and interactive learning experiences.

## Features

### Core Functionality
- **AI Tutoring** - Chat with an intelligent tutor that understands academic content
- **Document Upload** - Upload PDFs, Word documents, PowerPoint slides, and more
- **Automatic Summarization** - Get concise summaries of uploaded materials
- **Quiz Generation** - Create interactive quizzes from your study materials

### Study Tools
- **Flashcards** - Create and study with AI-generated flashcards
- **Lecture Notes** - Upload and organize lecture materials
- **Study Plans** - Plan and track your learning progress
- **Chat History** - Resume previous conversations anytime

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (Python 3.10+) |
| Database | SQLite / PostgreSQL |
| AI/ML | LangChain, OpenAI/Gemini APIs |
| Frontend | Vanilla JavaScript, CSS |
| Build Tool | Vite |

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Node.js 18+
- API key (OpenAI or Gemini)

### Installation

1. **Clone the repository**
   ```bash
   cd EduChat
   ```

2. **Set up Python virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate   # Windows
   ```

3. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Install Node dependencies**
   ```bash
   npm install
   ```

### Running the Application

1. **Start the backend server**
   ```bash
   npm run server
   ```
   The API will be available at `http://localhost:8000`

2. **Start the frontend (development)**
   ```bash
   npm run dev
   ```
   Open `http://localhost:5173` in your browser

3. **Build for production**
   ```bash
   npm run build
   ```

## Environment Variables

Create a `.env` file in the root directory:

```env
# API Configuration
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database (optional)
DATABASE_URL=postgresql://user:password@localhost:5432/educhat

# Server
API_BASE_URL=http://localhost:8000
```

## Project Structure

```
EduChat/
├── api/                    # Backend API
│   ├── index.py           # FastAPI application
│   ├── database.py       # Database operations
│   └── services/         # Business logic
│       ├── langchain_service.py
│       ├── llm_service.py
│       └── api_manager.py
├── public/                # Static assets
├── dist/                  # Build output
├── main.js               # Frontend JavaScript
├── style.css             # Frontend styles
├── chat.html            # Main chat page
├── index.html           # Login page
├── package.json         # Node configuration
├── vite.config.js       # Vite configuration
└── requirements.txt   # Python dependencies
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat` | Send a message to the AI |
| GET | `/api/chat/history` | Get chat history |
| POST | `/api/chat/session` | Create new chat session |
| GET | `/api/chat/session/{id}` | Load specific session |
| PUT | `/api/chat/session/{id}` | Update session title |
| DELETE | `/api/chat/session/{id}` | Delete session |
| POST | `/api/notes` | Upload lecture notes |
| GET | `/api/notes` | Get all notes |
| GET | `/api/notes/{id}/content` | Get note content |

## Deployment

See [DEPLOY.md](DEPLOY.md) for detailed deployment instructions.

### Quick Deploy Options

- **Vercel** - `npm run build` then deploy the `dist/` folder
- **Render** - Connect your GitHub repository
- **Railway** - `pip install -r requirements.txt` and start command

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request


## Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- AI powered by [Gemini](https://aistudio.google.com/) and [OpenAI](https://openai.com/)
- Learning framework by [LangChain](https://langchain.com/)

---

<p align="center">Made with care for education 🤖📚</p>
