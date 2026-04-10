

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Dict, List

from sympy import use
from app.agents.state import AgentState
import os
import json
import logging
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint

logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """
    Analyzes user queries to understand intent, case type, and information needs.
    """
    
    QUERY_ANALYSIS_PROMPT = """You are an expert teacher.

    STRICT RULES:
    - Output ONLY valid JSON
    - Do NOT include explanations
    - Do NOT include text before or after JSON
    - Ensure JSON is parsable

    Format:
    [
    {{
        "concept": "",
        "toy_task": ""
    }}
    ]
    Student knows: {known_stack}
    Student does not know: {unknown_stack}
    Project: {project}
    
    """
    def __init__(self, huggingface_api_key: str = None):
        """Initialize the QueryAnalyzer with LLM."""
        api_key = huggingface_api_key or os.getenv("HF_API_KEY")
        
        self.llm = ChatHuggingFace(
            llm=HuggingFaceEndpoint(
                repo_id = os.getenv("LLM_MODEL", "meta-llama/Llama-3.1-8B-Instruct"),
                huggingfacehub_api_token=api_key,
                task="text-generation",
                max_new_tokens=1024,
            )
        )
    
    def analyze_query(self, state: AgentState):
        """
        Analyze the user's query to understand intent and information needs.
        
        Args:
            state: AgentState containing the query
            
        Returns:
            Dict with analysis results
        """
        project = state["project"]
        unknown_stack = state["unknown_stack"]
        stack = state["known_stack"]
        
        # Prepare prompt
        prompt = self.QUERY_ANALYSIS_PROMPT.format(project=project, known_stack=stack, unknown_stack=unknown_stack)
        
        try:
            # Get LLM analysis
            conversation = [
                SystemMessage(content="Respond ONLY with valid JSON."),
                HumanMessage(content=prompt)
            ]
            
            logger.info("Invoking LLM for query analysis")
            response = self.llm.invoke(conversation)
            response_text = response.content.strip()
            
            # Extract JSON from response
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            
            # Parse JSON
            analysis = json.loads(response_text)
            
            print(json.dumps(analysis, indent=2))
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}\nResponse: {response_text[:200]}")
            
        
        except Exception as e:
            logger.error(f"Query analysis error: {str(e)}")
            
    
if __name__ == "__main__":
    # Example usage
    analyzer = QueryAnalyzer()
    state = AgentState({
        "user_id": "1",
        "project": {
            "name": "AI Task Manager",
            "tech_stack": ["React", "FastAPI"]
        },
        "known_stack": ["HTML", "CSS"],
        "unknown_stack": ["React", "FastAPI"],

        "prerequisites": [],
        "quiz": []
    })
    analysis_result = analyzer.analyze_query(state)
    # print(json.dumps(analysis_result, indent=2))