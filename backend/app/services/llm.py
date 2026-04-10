

from langchain_core.messages import HumanMessage, SystemMessage
from typing import Dict, List

from sympy import use
from core.state import FamilyLawState
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
    
    def analyze_query(self, state: FamilyLawState) -> Dict:
        """
        Analyze the user's query to understand intent and information needs.
        
        Args:
            state: FamilyLawState containing the query
            
        Returns:
            Dict with analysis results
        """
        query = state["query"]
        
        # Prepare prompt
        prompt = self.QUERY_ANALYSIS_PROMPT.format(query=query)
        
        try:
            # Get LLM analysis
            conversation = [
                SystemMessage(content="You are a legal query analyzer. Respond ONLY with valid JSON."),
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
            
            # Validate and set defaults

            user_intent = analysis.get("user_intent", "")
            intent_confidence = analysis.get("intent_confidence", "medium")
            info_provided = analysis.get("info_provided", {})
            info_needed = analysis.get("info_needed", [])
            user_gender = analysis.get("user_gender", None)
            
            # Determine if we have sufficient info
            has_sufficient_info = len(info_needed) == 0 and len(info_provided) > 0
            
            logger.info(f"Query analysis: intent_confidence={intent_confidence}, "
                       f"user_type={user_intent}, needs={len(info_needed)} items,"
                       f"gender={user_gender}")
            
            return {
                "user_intent": user_intent,
                "intent_confidence": intent_confidence,
                "info_collected": info_provided,
                "info_needed_list": info_needed,
                "has_sufficient_info": has_sufficient_info,
                "user_gender": user_gender
            }
        
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {str(e)}\nResponse: {response_text[:200]}")
            return self.fallback_analysis(query)
        
        except Exception as e:
            logger.error(f"Query analysis error: {str(e)}")
            return self.fallback_analysis(query)
    
    def fallback_analysis(self, query: str) -> Dict:
        """
        Fallback keyword-based analysis if LLM fails.
        """
        query_lower = query.lower()
        
        # Determine case type
        if any(word in query_lower for word in ["violence", "abuse", "beat", "assault", "hit", "threat"]):
            case_type = "domestic_violence"
            user_intent = "Seeking help with domestic violence"
        elif any(word in query_lower for word in ["dowry", "dahej", "demand", "harassment"]):
            case_type = "dowry"
            user_intent = "Seeking help with dowry-related issues"
        elif any(word in query_lower for word in ["custody", "children", "child", "visitation"]):
            case_type = "child_custody"
            user_intent = "Seeking help with child custody"
        elif any(word in query_lower for word in ["divorce", "separation", "marriage"]):
            case_type = "divorce"
            user_intent = "Seeking help with divorce/separation"
        elif any(word in query_lower for word in ["maintenance", "alimony", "support"]):
            case_type = "maintenance"
            user_intent = "Seeking help with maintenance/alimony"
        else:
            case_type = "general"
            user_intent = "Seeking family law advice"
        
        # Basic information extraction
        info_provided = {}
        if "married" in query_lower or "marriage" in query_lower:
            info_provided["marriage_mentioned"] = "yes"
        if "child" in query_lower:
            info_provided["children_mentioned"] = "yes"
        
        # Determine confidence and info needs
        word_count = len(query.split())
        if word_count > 50:
            intent_confidence = "high"
            info_needed = []
            has_sufficient_info = True
        elif word_count > 20:
            intent_confidence = "medium"
            info_needed = self._get_case_specific_needs(case_type)
            has_sufficient_info = False
        else:
            intent_confidence = "low"
            info_needed = []  # Will trigger clarification
            has_sufficient_info = False
        
        logger.info(f"Fallback analysis: case_type={case_type}, confidence={intent_confidence}")
        
        return {
            "user_intent": user_intent,
            "intent_confidence": intent_confidence,
            "case_type": case_type,
            "info_collected": info_provided,
            "info_needed_list": info_needed,
            "has_sufficient_info": has_sufficient_info
        }
    
    def _get_case_specific_needs(self, case_type: str) -> List[str]:
        """Get case-specific information needs."""
        needs_map = {
            "divorce": ["marriage_date", "grounds_for_divorce", "children_details", "property_details"],
            "domestic_violence": ["current_safety_status", "incident_details", "relationship_to_perpetrator", "previous_complaints"],
            "child_custody": ["children_ages", "current_custody_arrangement", "reason_for_custody_change"],
            "dowry": ["marriage_date", "dowry_demands_details", "evidence_available", "complaints_filed"],
            "maintenance": ["marriage_duration", "income_details", "dependents", "current_financial_status"],
            "general": ["detailed_situation", "timeline_of_events", "desired_outcome"]
        }
        return needs_map.get(case_type, needs_map["general"])

if __name__ == "__main__":
    # Example usage
    analyzer = QueryAnalyzer()
    state = {
        "user_id": "1",
        "project": {
            "name": "AI Task Manager",
            "tech_stack": ["React", "FastAPI"]
        },
        "known_stack": ["HTML", "CSS"],
        "unknown_stack": ["React", "FastAPI"],

        "prerequisites": [],
        "quiz": []
    }
    analysis_result = analyzer.analyze_query(state)
    print(json.dumps(analysis_result, indent=2))