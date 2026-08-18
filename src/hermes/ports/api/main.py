import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import time

app = FastAPI()

class ChatRequest(BaseModel):
    message: str
    project_id: str

@app.get("/health")
async def health_check():
    return {"status": "ok"}

@app.post("/api/chat/stream")
async def chat_stream(chat_request: ChatRequest):
    """
    Streams back a simulated agent response using Server-Sent Events.
    """
    async def event_generator():
        # In a real app, this would interact with the Hermes agent
        # and stream back tokens as they are generated.
        fake_response = f"Đây là phản hồi cho tin nhắn '{chat_request.message}' của dự án {chat_request.project_id}. "
        for word in fake_response.split():
            data = {"token": f"{word} "}
            yield f"data: {json.dumps(data)}\n\n"
            await asyncio.sleep(0.1)
        
        # Simulate tool execution progress
        progress_data = {
            "type": "progress",
            "payload": { "step": "Resource Pack", "status": "completed" }
        }
        yield f"data: {json.dumps(progress_data)}\n\n"
        await asyncio.sleep(1)

        progress_data = {
            "type": "progress",
            "payload": { "step": "Brief", "status": "in_progress" }
        }
        yield f"data: {json.dumps(progress_data)}\n\n"


    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/api/vf/projects/{project_id}/progress")
async def get_video_factory_progress(project_id: str):
    """
    Returns the detailed 8-stage progress for a video factory project.
    This is a mocked response. A real implementation would query the job status from the database.
    """
    stages = [
        "Resource Pack", "Brief", "Scene Plan", "Storyboard",
        "TTS", "Render Scenes", "Timeline", "MP4 Export"
    ]
    
    # Simulate some progress
    current_stage_index = int(time.time()) % len(stages)
    
    progress = [
        {"stage": name, "status": "completed" if i < current_stage_index else "pending"}
        for i, name in enumerate(stages)
    ]
    if current_stage_index < len(stages):
        progress[current_stage_index]["status"] = "in_progress"

    return {"project_id": project_id, "progress": progress}

# To run this app:
# uvicorn src.hermes.ports.api.main:app --reload
