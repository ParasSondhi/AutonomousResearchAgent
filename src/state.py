from typing import Optional, TypedDict, List

class AgentState(TypedDict):
    original_topic: str
    clarified_intent: str
    search_queries: List[str]
    user_feedback: Optional[str]
    raw_web_data: List[str]
    draft_report: str
    # NEW FIELDS FOR THE RETRY LOOP
    data_is_relevant: bool
    attempt_count: int
    user_email: str | None