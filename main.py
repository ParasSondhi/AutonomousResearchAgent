import uuid
import asyncio
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
import uvicorn
from src.pdf_generator import generate_pdf
from dotenv import load_dotenv
from fastapi.responses import FileResponse
import os
from src.email_service import send_pdf_email
load_dotenv()

# Import your compiled LangGraph app
from src.graph import app as agent_app

api = FastAPI(title="Autonomous Research Agent API")

# --- REQUEST MODELS ---
class ResearchRequest(BaseModel):
    topic: str
    email: str | None = None 


class FeedbackRequest(BaseModel):
    thread_id: str
    feedback: str
class ProceedRequest(BaseModel):
    thread_id: str

# --- HELPER FUNCTIONS ---
def finish_research_and_generate(config: dict, thread_id: str):
    """Wakes the graph, runs it to the end, and handles the PDF output."""
    
    # Run the rest of the graph
    agent_app.invoke(None, config)
    
    # Grab the final state
    final_state = agent_app.get_state(config)
    
    # Extract the markdown report and the original topic
    draft_report = final_state.values.get("draft_report", "No report generated.")
    topic = final_state.values.get("original_topic", "Research").replace(" ", "_")
    
    print(f"[{thread_id}] Research Complete. Ready to generate PDF.")
    
    # Trigger the PDF generation!
    filename = f"{topic}_{thread_id[:8]}.pdf"
    filepath = generate_pdf(draft_report, filename) # Assuming generate_pdf returns the filepath
    
    # Grab the email from the final state
    user_email = final_state.values.get("user_email") 
    
    # Trigger Native Python SMTP
    if user_email:
        print(f"[{thread_id}] Preparing to email PDF to {user_email}...")
        send_pdf_email(
            receiver_email=user_email, 
            topic=topic, 
            pdf_filepath=filepath
        )
    

# --- BACKGROUND TIMER TASK ---
async def auto_resume_timer(thread_id: str, delay_seconds: int = 120):
    """Waits, checks if the graph is paused, and forces it forward if ignored."""
    print(f"[{thread_id}] Timer started for {delay_seconds} seconds...")
    await asyncio.sleep(delay_seconds)
    
    config = {"configurable": {"thread_id": thread_id}}
    current_state = agent_app.get_state(config)
    
    if current_state.next and current_state.next[0] == "wait_for_user":
        print(f"[{thread_id}] TIMEOUT REACHED. Proceeding automatically.")
        agent_app.update_state(
            config, 
            {"user_feedback": "No user feedback provided. Proceed with original plan."}
        )
        finish_research_and_generate(config, thread_id)
# --- API ENDPOINTS ---
@api.post("/start-research")
async def start_research(request: ResearchRequest, background_tasks: BackgroundTasks):
    """Kicks off the research planner and starts the timer."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    
    # Initialize the state and run the planner (it will pause after planner)
    initial_state = {"original_topic": request.topic,
                     "user_email": request.email}
    agent_app.invoke(initial_state, config)
    
    # Grab the planner's output to send back to the user
    current_state = agent_app.get_state(config)
    proposed_queries = current_state.values.get("search_queries", [])
    
    # Start the countdown clock in the background
    background_tasks.add_task(auto_resume_timer, thread_id, delay_seconds=120)
    
    return {
        "status": "planner_complete_waiting_for_approval",
        "thread_id": thread_id,
        "proposed_queries": proposed_queries,
        "timeout_seconds": 120,
        "message": "Send a POST request to /provide-feedback with your suggestions before the timeout."
    }

@api.post("/provide-feedback")
async def provide_feedback(request: FeedbackRequest, background_tasks: BackgroundTasks):
    """Receives user feedback and wakes the graph up immediately."""
    config = {"configurable": {"thread_id": request.thread_id}}
    current_state = agent_app.get_state(config)
    
    # Ensure the graph actually exists and is paused
    if not current_state.next:
        raise HTTPException(status_code=400, detail="Graph is not paused or thread_id is invalid.")
        
    print(f"[{request.thread_id}] HUMAN INTERVENTION RECEIVED.")
    
    # Inject the actual feedback into the state
    agent_app.update_state(config, {"user_feedback": request.feedback})
    
    # Wake the graph up immediately in the background so the API responds instantly
    background_tasks.add_task(finish_research_and_generate, config, request.thread_id)
    
    return {
        "status": "resumed_with_feedback",
        "thread_id": request.thread_id,
        "message": "Feedback accepted. Research is continuing in the background."
    }
@api.post("/proceed")
async def proceed_immediately(request: ProceedRequest, background_tasks: BackgroundTasks):
    """Bypasses the timer and approves the plan immediately."""
    config = {"configurable": {"thread_id": request.thread_id}}
    current_state = agent_app.get_state(config)
    
    if not current_state.next:
        raise HTTPException(status_code=400, detail="Graph is not paused or invalid thread_id.")
        
    print(f"[{request.thread_id}] PLAN APPROVED BY USER. Bypassing timer.")
    
    # Inject the exact bypass string our researcher_node is programmed to ignore
    agent_app.update_state(
        config, 
        {"user_feedback": "No user feedback provided. Proceed with original plan."}
    )
    
    # Wake the graph up immediately
    background_tasks.add_task(finish_research_and_generate, config, request.thread_id)
    
    return {
        "status": "resumed_approved",
        "thread_id": request.thread_id,
        "message": "Plan approved! Research is starting immediately."
    }
@api.get("/status/{thread_id}")
async def check_status(thread_id: str):
    """Allows the frontend to check if the graph has finished."""
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        current_state = agent_app.get_state(config)
        
        # If the graph has no 'next' node, it has completed its run!
        if not current_state.next:
            topic = current_state.values.get("original_topic", "Research").replace(" ", "_")
            filename = f"{topic}_{thread_id[:8]}.pdf"
            filepath = os.path.join("output", filename)
            
            if os.path.exists(filepath):
                return {"status": "completed", "filename": filename}
                
        return {"status": "processing"}
        
    except Exception as e:
        # If get_state crashes, or the background task blew up the thread
        return {"status": "error"}

@api.get("/download/{filename}")
async def download_pdf(filename: str):
    """Serves the actual PDF file to the frontend."""
    filepath = os.path.join("output", filename)
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="application/pdf", filename=filename)
    raise HTTPException(status_code=404, detail="File not found.")
if __name__ == "__main__":
    uvicorn.run(api, host="0.0.0.0", port=8000)