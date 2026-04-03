from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_groq import ChatGroq
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state import AgentState

# Initialize your LLM
# primary_llm = ChatGroq(
#     model="llama-3.3-70b-versatile", 
#     temperature=0.2,
#     max_retries=1 # Don't waste time retrying if the limit is reached, just fail over
# )
primary_llm = ChatGoogleGenerativeAI(
    model="gemini-1.5-flash", 
    temperature=0.2,
    max_retries=1
)

# 2. Define your Fallback Model (Gemini - Very generous free tier)
# gemini-1.5-flash is extremely fast and handles complex reasoning well
# fallback_llm = ChatGoogleGenerativeAI(
#     model="gemini-1.5-flash", 
#     temperature=0.2,
#     max_retries=1
# )
fallback_llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    temperature=0.2,
    max_retries=1 # Don't waste time retrying if the limit is reached, just fail over
)

# 3. Create the Resilient Chain
# If primary_llm throws an error (like HTTP 429 Rate Limit), it automatically routes to fallback_llm
# llm = primary_llm.with_fallbacks([fallback_llm])
class EvaluatorOutput(BaseModel):
    is_relevant: bool = Field(description="True if the scraped data provides enough information to satisfy the target intent. False if it is irrelevant or insufficient.")
    reasoning: str = Field(description="A 1-sentence explanation of WHY you are approving or rejecting this data.")
    new_search_queries: List[str] = Field(description="If is_relevant is False, provide 3 completely new, different search queries to find better data. If True, leave empty.")

# Define the expected JSON structure for the Planner
class PlannerOutput(BaseModel):
    clarified_intent: str = Field(description="A clear, 1-2 sentence definition of the exact research focus to prevent ambiguity.")
    search_queries: List[str] = Field(description="A list of 3 highly optimized Google search queries to gather comprehensive data.")

def planner_node(state: AgentState) -> AgentState:
    print(f"--- PLANNING FOR: {state['original_topic']} ---")
    
    # 1. Bind the LLM to our Pydantic model to guarantee structured JSON output
    primary_structured = primary_llm.with_structured_output(PlannerOutput)
    fallback_structured = fallback_llm.with_structured_output(PlannerOutput)
    structured_llm = primary_structured.with_fallbacks([fallback_structured])
    
    # 2. Build the system instructions
    sys_msg = SystemMessage(content="""You are an expert research director. 
    Your job is to take a user's prompt, figure out exactly what they mean (disambiguate if necessary), 
    and write 3 highly targeted search queries to feed to a search engine.
    If user feedback is provided, prioritize it completely.""")
    
    # 3. Build the user prompt, injecting state data
    user_prompt = f"Original Topic: {state['original_topic']}\n"
    if state.get("user_feedback"):
        user_prompt += f"\nCRITICAL USER FEEDBACK TO APPLY: {state['user_feedback']}\n"
        
    user_msg = HumanMessage(content=user_prompt)
    
    # 4. Call the LLM
    result = structured_llm.invoke([sys_msg, user_msg])
    
    # 5. Return the exact keys defined in AgentState
    return {
        "clarified_intent": result.clarified_intent,
        "search_queries": result.search_queries
    }
def wait_for_user_node(state: AgentState) -> AgentState:
    # This node does absolutely nothing to the data. 
    # It just exists so LangGraph has a safe place to pause.
    return state
def researcher_node(state: AgentState) -> AgentState:
    print("--- RESEARCHING ---")
    
    current_queries = state['search_queries']
    user_feedback = state.get("user_feedback")
    
    # 1. HANDLE HUMAN FEEDBACK (Only triggers once right after the pause)
    if user_feedback and "No user feedback provided" not in user_feedback:
        print(f"--- APPLYING HUMAN FEEDBACK: {user_feedback} ---")
        
        primary_structured = primary_llm.with_structured_output(PlannerOutput)
        fallback_structured = fallback_llm.with_structured_output(PlannerOutput)
        structured_llm = primary_structured.with_fallbacks([fallback_structured])
        
        sys_msg = SystemMessage(content="""You are a research assistant. 
        Update the search queries based STRICTLY on the user's new feedback. 
        Output the updated intent and 3 new search queries.""")
        
        user_msg = HumanMessage(content=f"""
        Original Intent: {state['clarified_intent']}
        Original Queries: {current_queries}
        User Feedback: {user_feedback}
        
        Revise the search queries to perfectly match the user's instructions.
        """)
        
        # Rewrite the queries
        revised_plan = structured_llm.invoke([sys_msg, user_msg])
        current_queries = revised_plan.search_queries
        state['clarified_intent'] = revised_plan.clarified_intent

    # 2. EXECUTE SEARCHES (Tavily runs whatever queries it currently holds)
    
    # Use include_raw_content to get the full article, search_depth="basic" is faster and safer for the free tier
    search_tool = TavilySearchResults(max_results=3)
    all_web_content = []
    
    for query in current_queries:
        print(f"Executing search: {query}")
        try:
            results = search_tool.invoke({"query": query})
            for page in results:
                if "content" in page:
                    all_web_content.append(f"Source URL: {page.get('url', 'Unknown')}\nContent: {page['content']}\n---")
        except Exception as e:
            print(f"Search failed for query '{query}': {e}")
            
    # 3. RETURN STATE
    return {
        "raw_web_data": all_web_content, 
        "search_queries": current_queries,
        "clarified_intent": state['clarified_intent'],
        # CRITICAL: Wipe the feedback so the Evaluator's automated retries don't trigger step 1 again!
        "user_feedback": None 
    }
def evaluator_node(state: AgentState) -> AgentState:
    print("--- EVALUATING SCRAPED DATA ---")
    
    # Initialize attempt count if it doesn't exist
    current_attempts = state.get("attempt_count", 0) + 1
    
    primary_structured = primary_llm.with_structured_output(EvaluatorOutput)
    fallback_structured = fallback_llm.with_structured_output(EvaluatorOutput)
    structured_llm = primary_structured.with_fallbacks([fallback_structured])
    
    sys_msg = SystemMessage(content="""You are a Quality Assurance reviewer. 
    Look at the target intent and the scraped web data. Does the data actually answer the intent?
    If the data is irrelevant (e.g., about fruit instead of a tech company), return False and suggest new queries.
    CRITICAL: You must output valid JSON. Use strictly lowercase 'true' or 'false' for booleans.""")
    
    compiled_data = "\n\n".join(state['raw_web_data'])
    # Inside evaluator_node...
    user_msg = HumanMessage(content=f"""
    Target Intent: {state['clarified_intent']}
    
    Queries You Just Tried (DO NOT REUSE THESE): {state['search_queries']}
    
    Scraped Data:
    {compiled_data}
    
    If rejecting, you MUST write 3 entirely new queries that take a different approach.
    """)
    
    result = structured_llm.invoke([sys_msg, user_msg])
    
    if result.is_relevant:
        print("--- DATA APPROVED ---")
        print(f"Reasoning: {result.reasoning}")
        return {"data_is_relevant": True, "attempt_count": current_attempts}
    else:
        print(f"--- DATA REJECTED. GENERATING NEW QUERIES (Attempt {current_attempts}) ---")
        print(f"Reasoning: {result.reasoning}")
        # Clear the bad data and replace the queries with the new ones
        return {
            "data_is_relevant": False, 
            "search_queries": result.new_search_queries,
            "raw_web_data": [], # Clear out the bad data!
            "attempt_count": current_attempts
        }
    
def analyzer_node(state: AgentState) -> AgentState:
    print("--- ANALYZING & DRAFTING ---")
    
    # 1. Join all the raw scraped text into one massive string
    compiled_research = "\n\n".join(state['raw_web_data'])
    
    # 2. Build the system instructions for the final report
    sys_msg = SystemMessage(content="""You are an elite research analyst. 
    Write a highly structured, professional Markdown report based strictly on the provided research data.
    Use clear headings, bullet points, and maintain an objective tone. 
    Do not invent facts; rely only on the provided text.""")
    
    # 3. Feed the intent and the massive text block to the LLM
    user_msg = HumanMessage(content=f"""
    Target Intent: {state['clarified_intent']}
    
    Here is the scraped web data:
    {compiled_research}
    
    Synthesize this information and output the final markdown report.
    """)
    
    # 4. Call the LLM (standard string output, no Pydantic needed here)
    llm = primary_llm.with_fallbacks([fallback_llm])
    response = llm.invoke([sys_msg, user_msg])
    
    # 5. Return the final markdown text
    return {"draft_report": response.content}