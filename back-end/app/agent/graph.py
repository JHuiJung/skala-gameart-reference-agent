"""노드를 연결해 에이전트 그래프를 만든다. 단계가 늘어나면 여기에 노드와 edge 를 추가한다."""
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import analyze_input
from app.agent.state import AgentState

builder = StateGraph(AgentState)
builder.add_node("analyze_input", analyze_input)

builder.add_edge(START, "analyze_input")
builder.add_edge("analyze_input", END)

graph = builder.compile()
