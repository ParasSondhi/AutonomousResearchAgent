# ⚡ Autonomous AI Research Agent

A production-deployed, asynchronous LangGraph agent that conducts deep, recursive web research. 

**The Workflow:**
1. You provide a research topic.
2. The agent instantly formulates a multi-step research strategy and halts to ask for your specific feedback or direction.
3. Once you approve the strategy, **you can close the tab.**
4. The agent's backend engine takes over, autonomously scraping the web, evaluating the data, and synthesizing a highly structured Markdown and PDF report.
   
### 🔗 Live Deployment & Demo
* **[Live Web App](https://getwellresearchedreport.streamlit.app/)**
* **[🎥 Watch the 60-Second Loom Demo](https://www.loom.com/share/ad7905b8e029476882c42ae648d7fa59)** - *Shows the decoupled backend agent executing recursive loops and Human-in-the-Loop feedback in real-time.*

> ⚠️ **Note on Live Demo:** This application is currently deployed in a demo phase utilizing free-tier API limits. Because autonomous agents are heavily recursive and token-intensive (especially running a 70B parameter model), the live deployment may occasionally hit HTTP 429 Rate Limits during high traffic. For unrestricted execution, clone the repository and run locally with your own API keys.

> ⏳ **Cold Start Notice:** The backend engine is hosted on Render's free tier, which spins down after 15 minutes of inactivity. If the app hasn't been used recently, the very first request may take 30–50 seconds to 'wake up' the server before execution begins.

---

## 🧠 Cloud Architecture & Deployment

This is not a monolithic script; it is built with a decoupled architecture to handle heavy LLM reasoning without freezing the client interface.

* **The Frontend (Streamlit Cloud):** Provides a lightweight, clean UI to handle user intent, capture Human-in-the-Loop (HITL) feedback, and trigger the remote agent.
* **The Hosted Brain (Render Cloud):** The actual autonomous LangGraph engine is deployed as a standalone backend service on Render. It handles the heavy state management, API rate limits, and recursive scraping loops.

---

## 🛠️ Engineering Highlights & Problem Solving

Unlike basic linear LLM wrappers, this system utilizes a stateful, cyclic graph architecture to perform multi-step reasoning.

* **Autonomous Evaluator Gate:** The agent doesn't just scrape and summarize. It uses an internal QA node that actively grades the scraped data against the original intent. If the data is irrelevant, the agent flushes the context window, engineers entirely new lateral search queries, and restarts the research loop without user intervention.
* **Strict Schema Enforcement:** To prevent pipeline collapse across multiple recursive loops, the flagship model (Llama 3.3 70B) is bound to strict `Pydantic` models. This guarantees deterministic JSON outputs for all programmatic routing, query generation, and evaluation steps.
* **Context Window Management:** Engineered the graph state to aggressively clear out rejected web-scraping data before retry loops, preventing token bloat, API limit crashes, and hallucination cascades.

---

## 💻 Tech Stack
* **Orchestration:** LangGraph, LangChain
* **Flagship Model:** Groq API (Llama 3.3 70B Versatile)
* **Data Ingestion:** Tavily Search API
* **Data Validation:** Pydantic
* **Deployment:** Streamlit (UI) + Render Cloud (Backend Graph Engine)

---

## 🚦 Running Locally

To bypass the free-tier Render cold-starts or API rate limits of the live demo, deploy the brain locally.

1. **Clone the repo:**
   ```bash
   git clone https://github.com/ParasSondhi/AutonomousResearchAgent
   cd AutonomousResearchAgent
    ```

2. **Set your environment variables:**

   Create a .env file in the root directory with your API keys and the email credentials used to send the final reports:
   
   ```bash
   GROQ_API_KEY="your_groq_key"
   TAVILY_API_KEY="your_tavily_key"
    ```

3. **Install dependencies and run:**
   ```bash
   pip install -r requirements.txt
   streamlit run app.py
    ```   
