# Hermes Web Admin

React/TypeScript single-page application for managing Hermes projects, Prompt Studio workflows, and jobs.

## Getting Started

```powershell
cd web
npm install
npm run dev
```

The app runs at `http://127.0.0.1:3000` and proxies API requests to `http://127.0.0.1:8000`.

## Endpoints

- `/projects` — Project list and creation
- `/projects/:id/prompt-studio` — Prompt Studio workflow with 7 steps
- `/api/events` — Server-Sent Events for live job/project updates

## Testing

```powershell
npm run test:e2e
```