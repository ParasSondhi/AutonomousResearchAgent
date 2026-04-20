import yaml
from typing import List
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_groq import ChatGroq
from src.state import AgentState

# 1. Initialize your single, primary LLM
llm = ChatGroq(
    model="llama-3.3-70b-versatile", 
    temperature=0.2,
    max_retries=2 # Let LangChain attempt a quick retry if there is a network hiccup
)
try:
    with open("config.yaml", "r") as file:
        config = yaml.safe_load(file)
        behavior = config.get("agent_behavior", {})
        TARGET_AUDIENCE = behavior.get("target_audience", "general reader")
        OUTPUT_FORMAT = behavior.get("output_format", "standard text")
        DEPTH = behavior.get("depth", "standard")
except FileNotFoundError:
    print("Warning: config.yaml not found. Using default settings.")
    TARGET_AUDIENCE = "general reader"
    OUTPUT_FORMAT = "standard text"
    DEPTH = "standard"

# Define the expected JSON structure for the Evaluator
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
    
    # Bind the LLM directly to the structured output
    structured_llm = llm.with_structured_output(PlannerOutput)
    
    sys_msg = SystemMessage(content="""You are an expert research director. 
    Your job is to take a user's prompt, figure out exactly what they mean (disambiguate if necessary), 
    and write 3 highly targeted search queries to feed to a search engine.
    If user feedback is provided, prioritize it completely.""")
    
    user_prompt = f"Original Topic: {state['original_topic']}\n"
    if state.get("user_feedback"):
        user_prompt += f"\nCRITICAL USER FEEDBACK TO APPLY: {state['user_feedback']}\n"
        
    user_msg = HumanMessage(content=user_prompt)
    
    result = structured_llm.invoke([sys_msg, user_msg])
    
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
    
    # 1. HANDLE HUMAN FEEDBACK
    if user_feedback and "No user feedback provided" not in user_feedback:
        print(f"--- APPLYING HUMAN FEEDBACK: {user_feedback} ---")
        
        structured_llm = llm.with_structured_output(PlannerOutput)
        
        sys_msg = SystemMessage(content="""You are a research assistant. 
        Update the search queries based STRICTLY on the user's new feedback. 
        Output the updated intent and 3 new search queries.""")
        
        user_msg = HumanMessage(content=f"""
        Original Intent: {state['clarified_intent']}
        Original Queries: {current_queries}
        User Feedback: {user_feedback}
        
        Revise the search queries to perfectly match the user's instructions.
        """)
        
        revised_plan = structured_llm.invoke([sys_msg, user_msg])
        current_queries = revised_plan.search_queries
        state['clarified_intent'] = revised_plan.clarified_intent

    # 2. EXECUTE SEARCHES
    if DEPTH == "comprehensive":
        result_limit = 5
    elif DEPTH == "shallow":
        result_limit = 1
    else:
        result_limit = 3 # The "standard" default
        
    search_tool = TavilySearchResults(max_results=result_limit)
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
        "user_feedback": None 
    }

def evaluator_node(state: AgentState) -> AgentState:
    print("--- EVALUATING SCRAPED DATA ---")
    
    current_attempts = state.get("attempt_count", 0) + 1
    
    structured_llm = llm.with_structured_output(EvaluatorOutput)
    
    sys_msg = SystemMessage(content="""You are a Quality Assurance reviewer. 
    Look at the target intent and the scraped web data. Does the data actually answer the intent?
    If the data is irrelevant (e.g., about fruit instead of a tech company), return False and suggest new queries.
    CRITICAL: You must output valid JSON. Use strictly lowercase 'true' or 'false' for booleans.""")
    
    compiled_data = "\n\n".join(state['raw_web_data'])
    
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
        return {
            "data_is_relevant": False, 
            "search_queries": result.new_search_queries,
            "raw_web_data": [], 
            "attempt_count": current_attempts
        }
    
def analyzer_node(state: AgentState) -> AgentState:
    print("--- ANALYZING & DRAFTING ---")
    
    compiled_research = "\n\n".join(state['raw_web_data'])
    
    sys_msg = SystemMessage(content="""You are an elite research analyst. Your target audience is a {TARGET_AUDIENCE}
    Write a highly structured {OUTPUT_FORMAT} based strictly on the provided research data.
    Use clear headings, bullet points, and maintain an objective tone. 
    Do not invent facts; rely only on the provided text.""")
    
    user_msg = HumanMessage(content=f"""
    Target Intent: {state['clarified_intent']}
    
    Here is the scraped web data:
    {compiled_research}
    
    Synthesize this information and output the final markdown report.
    """)
    
    # Just call the single LLM directly
    response = llm.invoke([sys_msg, user_msg])
    
    return {"draft_report": response.content}