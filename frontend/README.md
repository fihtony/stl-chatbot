# Collège Saint-Louis Chatbot - Frontend

Frontend application for the Collège Saint-Louis chatbot, built with Next.js.

## Features

- 🎨 Modern chat interface
- 💬 Real-time message interaction
- 🔗 Integrated with Python RAG backend
- 📱 Responsive design
- 🌐 Multi-language support (French, English, Chinese)

## Tech Stack

- **Framework**: Next.js 15
- **UI**: React 18 + Tailwind CSS
- **Language**: TypeScript
- **Backend Communication**: REST API (FastAPI)

## Quick Start

### Prerequisites

- Node.js >= 22.0.0
- npm >= 10.0.0
- Python backend service running on `http://localhost:8086`

### Install Dependencies

```bash
cd frontend
npm install
```

### Configure Environment

Create `.env.local` file:

```bash
cp .env.example .env.local
```

Edit `.env.local`:

```env
NEXT_PUBLIC_BACKEND_URL=http://localhost:8086
```

### Run Development Server

```bash
npm run dev
```

Application will start at http://localhost:3086

### Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── app/                    # Next.js App Router
│   ├── api/               # API routes
│   │   └── chat/         # Chat API (proxies to backend)
│   ├── admin/            # Admin panel (authentication required)
│   ├── globals.css       # Global styles
│   └── page.tsx          # Main page
├── components/            # React components
│   ├── admin/            # Admin components
│   ├── ChatInterface.tsx # Main chat interface
│   └── MessageBubble.tsx # Message bubble component
├── lib/                   # Utility libraries
│   ├── api.ts            # API client
│   └── security.ts       # Security utilities
├── next.config.js        # Next.js configuration
├── tailwind.config.ts    # Tailwind CSS configuration
└── package.json          # Project dependencies
```

## API Endpoints

### POST /api/chat

Send chat message to backend

**Request:**
```json
{
  "message": "Your question",
  "provider": "zhipu"
}
```

**Response:**
```json
{
  "response": "AI answer",
  "provider": "zhipu",
  "metadata": {
    "method": "hybrid",
    "chunksUsed": 5,
    "timing": { "total": 1234 }
  }
}
```

### GET /api/chat?action=health

Health check endpoint

## Admin Panel

The admin panel provides secured access to system management:

- **Content Status**: View and manage indexed files
- **Crawler Management**: Configure and trigger web scraping
- **File Upload**: Upload documents for indexing
- **AI Configuration**: View and test AI connection
- **Performance Metrics**: Monitor system performance

**Access:** http://localhost:8086/admin (requires authentication)

## Backend Integration

The frontend proxies requests to the Python FastAPI backend via `/api/chat` route. Ensure:

1. Python backend is running on `http://localhost:8086`
2. Backend RAG system is initialized with document index
3. Environment variable `NEXT_PUBLIC_BACKEND_URL` is correctly configured

## Development

### Modify UI

- Edit `components/ChatInterface.tsx` for chat interface
- Edit `components/MessageBubble.tsx` for message styles
- Edit `app/globals.css` for global styles

### Modify API Integration

- Edit `app/api/chat/route.ts` for backend communication logic

### Add New Features

1. Create new components in `components/`
2. Add new pages in `app/`
3. Add new API routes in `app/api/`

## Troubleshooting

### Backend Connection Failed

Error: `Backend service is unavailable`

**Solutions:**
1. Confirm Python backend is running: `cd ../backend && python api_server.py`
2. Check `NEXT_PUBLIC_BACKEND_URL` environment variable
3. Check firewall settings

### TypeScript Errors

Run to regenerate types:

```bash
npm run build
```

### Port Conflicts

If port 3000 is occupied, modify `package.json`:

```json
"scripts": {
  "dev": "next dev -p 3001"
}
```

## License

MIT License - see project root LICENSE file.
