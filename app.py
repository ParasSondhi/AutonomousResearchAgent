import streamlit as st
import requests
import time
import base64
from streamlit_pdf_viewer import pdf_viewer

# Point to your local FastAPI backend
API_URL = "https://autonomousresearchagent.onrender.com"

st.set_page_config(page_title="AI Researcher", page_icon="🕵️‍♂️")
st.title("Autonomous Research Agent")

# --- STATE MANAGEMENT ---
# This acts as the frontend's memory so it remembers the thread_id
if "step" not in st.session_state:
    st.session_state.step = 1
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "queries" not in st.session_state:
    st.session_state.queries = []

# --- STEP 1: INITIATE RESEARCH ---
if st.session_state.step == 1:
    with st.form(key="research_form"):
        topic = st.text_input("Enter a research topic:")
        
        # --- EMAIL OPT-IN ---
        st.write("---")
        want_email = st.checkbox("Email me a copy of the final report")
        user_email = st.text_input("Your Email Address:") if want_email else None
        
        submit_button = st.form_submit_button(label="Start Research")
        st.caption("⏳ *Note: This project runs on a free cloud tier. The very first search may take 40-50 seconds to wake the server up.*")
        
    if submit_button:
        if topic.strip(): 
            if want_email and not user_email:
                st.warning("Please enter your email address if you want a copy.")
            else:
                with st.spinner("Planning search strategy..."):
                    payload = {"topic": topic, "email": user_email}
                    
                    # 1. Make the request WITHOUT instantly trying to parse JSON
                    try:
                        raw_response = requests.post(f"{API_URL}/start-research", json=payload)
                        
                        # 2. If the backend succeeds (Both APIs didn't crash)
                        if raw_response.status_code == 200:
                            response = raw_response.json()
                            st.session_state.thread_id = response["thread_id"]
                            st.session_state.queries = response["proposed_queries"]
                            st.session_state.step = 2
                            st.rerun()
                        
                        # 3. THE NEW FALLBACK: If both APIs hit limits and the backend crashes
                        else:
                            st.error("🚦 Currently due to heavy traffic, the demo version is not working. Please try again later.")
                    
                    # 4. In case the FastAPI server is completely offline/not running
                    except requests.exceptions.ConnectionError:
                        st.error("🔌 The backend server is currently offline. Please try again later.")
        else:
            st.warning("Please enter a topic before searching.")

# --- STEP 2: REVIEW & APPROVE ---
elif st.session_state.step == 2:
    st.subheader("Proposed Search Queries")
    for q in st.session_state.queries:
        st.markdown(f"- `{q}`")
    
    st.write("---")
    feedback = st.text_input("Refine these queries (optional):")
    
    col1, col2 = st.columns(2)
    with col1:
        # The bypass button
        if st.button("✅ Approve & Proceed", use_container_width=True):
            requests.post(f"{API_URL}/proceed", json={"thread_id": st.session_state.thread_id})
            st.session_state.step = 3
            st.rerun()
            
    with col2:
        # The feedback button
        if st.button("🔄 Submit Feedback", use_container_width=True):
            if feedback:
                requests.post(f"{API_URL}/provide-feedback", json={
                    "thread_id": st.session_state.thread_id, 
                    "feedback": feedback
                })
                st.session_state.step = 3
                st.rerun()
            else:
                st.warning("Please enter feedback before submitting.")

# --- STEP 3: BACKGROUND PROCESSING ---
elif st.session_state.step == 3:
    st.success("✅ Research in progress!")
    st.info("The backend agent is currently scraping the web, evaluating data, and drafting the report.")
    
    pdf_ready = False
    filename = ""
    
    # --- NEW: WATCHDOG TIMER ---
    timeout_seconds = 180 # 3 minutes maximum wait time
    start_time = time.time()
    
    # This spinner will stay on the screen while the while-loop runs
    with st.spinner("Waiting for the final PDF... This may take a minute."):
        while not pdf_ready:
            
            # 1. Check if we have been waiting too long!
            if time.time() - start_time > timeout_seconds:
                st.error("🚦 Currently due to heavy traffic, the demo version is not working. Please try again later.")
                break # Kill the infinite loop
                
            try:
                # 2. Ask FastAPI: "Is it done yet?"
                res = requests.get(f"{API_URL}/status/{st.session_state.thread_id}").json()
                
                if res.get("status") == "completed":
                    pdf_ready = True
                    filename = res.get("filename")
                elif res.get("status") == "error":
                    st.error("🚦 Currently due to heavy traffic, the demo version is not working. Please try again later.")
                    break
                else:
                    time.sleep(3) 
            except Exception:
                time.sleep(3)
                
    # Once the loop breaks, the PDF is ready!
    if pdf_ready:
        st.success("✅ PDF Generated Successfully!")
        
        # Fetch the actual PDF bytes from FastAPI
        pdf_bytes = requests.get(f"{API_URL}/download/{filename}").content
        
       # --- NEW: NATIVE PDF PREVIEW ---
        st.write("### Document Preview")
        
        # This native component bypasses the browser's base64 block
        pdf_viewer(input=pdf_bytes, width=700)
        # ------------------------
        
        # Display the download button below the preview
        st.download_button(
            label="⬇️ Download PDF File",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf"
        )
        
    st.write("---")
    if st.button("Start New Research"):
        st.session_state.step = 1
        st.session_state.thread_id = None
        st.rerun()
