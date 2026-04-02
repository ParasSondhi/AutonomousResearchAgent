from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import AgentState
from src.nodes import planner_node, wait_for_user_node, researcher_node, evaluator_node, analyzer_node

# --- ROUTER FUNCTION ---
def check_relevance(state: AgentState) -> str:
    """Decides where the graph goes after the evaluator node."""
    if state["data_is_relevant"]:
        return "analyzer" # Data is good, write the report
    elif state["attempt_count"] >= 3:
        print("--- MAX ATTEMPTS REACHED. FORCING REPORT GENERATION ---")
        return "analyzer" # Prevent infinite loops, just do your best with what you have
    else:
        return "researcher" # Data is bad, loop back and search again

# --- GRAPH BUILDER ---
memory = MemorySaver()
workflow = StateGraph(AgentState)

# Add all nodes
workflow.add_node("planner", planner_node)
workflow.add_node("wait_for_user", wait_for_user_node) # <-- The new waiting room
workflow.add_node("researcher", researcher_node)
workflow.add_node("evaluator", evaluator_node)         # <-- The new QA checker
workflow.add_node("analyzer", analyzer_node)

# Define the flow
workflow.set_entry_point("planner")

# Planner -> Waiting Room -> Researcher -> Evaluator
workflow.add_edge("planner", "wait_for_user")
workflow.add_edge("wait_for_user", "researcher")
workflow.add_edge("researcher", "evaluator")

# Evaluator -> (Conditional) -> Analyzer OR Researcher
workflow.add_conditional_edges(
    "evaluator",
    check_relevance,
    {
        "analyzer": "analyzer",
        "researcher": "researcher"
    }
)

workflow.add_edge("analyzer", END)

# --- COMPILE ---
# Notice we now interrupt before "wait_for_user", NOT "researcher"!
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["wait_for_user"] 
)

# --- TEST SCRIPT ---
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    initial_state = {
        "original_topic": "apple",
        "clarified_intent": "",
        "search_queries": [],
        "raw_web_data": [],
        "draft_report": ""
    }
    
    print("Starting agent...")
    final_state = app.invoke(initial_state)
    print("\n--- FINAL OUTPUT ---")
    print(final_state["draft_report"])