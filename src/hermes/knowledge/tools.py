import json
from typing import Dict, Any
from hermes.tools.registry import registry, tool_error
from hermes.knowledge.service import get_knowledge_service, KnowledgeService
from hermes.knowledge.models import ViralVideoPlaybook, PromptTemplate, LessonLearned, BrandGuideline

def _handle_knowledge_search(args: Dict[str, Any], **kwargs) -> str:
    """Handler for the knowledge_search tool."""
    try:
        service: KnowledgeService = next(get_knowledge_service())
        
        resource_type = args.get("resource_type")
        project_id = args.get("project_id")
        category = args.get("category")
        industry = args.get("industry")

        results = []
        if resource_type == "playbook":
            results = service.list_playbooks(category=category)
        elif resource_type == "prompt_template":
            results = service.list_prompt_templates(industry=industry, category=category)
        elif resource_type == "lesson_learned":
            if not project_id:
                return tool_error("project_id is required for lesson_learned")
            results = service.get_lessons_for_project(project_id=project_id)
        elif resource_type == "brand_guideline":
            if not project_id:
                return tool_error("project_id is required for brand_guideline")
            guideline = service.get_brand_guideline(project_id)
            results = [guideline] if guideline else []
        else:
            return tool_error(f"Unknown resource_type: {resource_type}")

        # Convert SQLModel objects to dicts for JSON serialization
        results_dict = [r.model_dump() for r in results]
        return json.dumps({"results": results_dict}, ensure_ascii=False)

    except Exception as e:
        return tool_error(f"Error during knowledge search: {e}")

def _handle_knowledge_save(args: Dict[str, Any], **kwargs) -> str:
    """Handler for the knowledge_save tool."""
    try:
        service: KnowledgeService = next(get_knowledge_service())
        
        resource_type = args.get("resource_type")
        data = args.get("data")
        
        if not data:
            return tool_error("data is required")

        saved_obj = None
        if resource_type == "playbook":
            saved_obj = service.save_playbook(ViralVideoPlaybook.model_validate(data))
        elif resource_type == "prompt_template":
            saved_obj = service.save_prompt_template(PromptTemplate.model_validate(data))
        elif resource_type == "lesson_learned":
            saved_obj = service.save_lesson(LessonLearned.model_validate(data))
        elif resource_type == "brand_guideline":
            saved_obj = service.save_brand_guideline(BrandGuideline.model_validate(data))
        else:
            return tool_error(f"Unknown resource_type: {resource_type}")

        return json.dumps({"saved": saved_obj.model_dump()}, ensure_ascii=False)

    except Exception as e:
        return tool_error(f"Error during knowledge save: {e}")

# Schemas for the tools
KNOWLEDGE_SEARCH_SCHEMA = {
    "name": "knowledge_search",
    "description": "Searches the knowledge base for playbooks, templates, lessons, and guidelines.",
    "parameters": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "enum": ["playbook", "prompt_template", "lesson_learned", "brand_guideline"]},
            "project_id": {"type": "string", "description": "Project ID for project-specific resources."},
            "category": {"type": "string", "description": "Category for playbooks or templates."},
            "industry": {"type": "string", "description": "Industry for prompt templates."},
        },
        "required": ["resource_type"],
    },
}

KNOWLEDGE_SAVE_SCHEMA = {
    "name": "knowledge_save",
    "description": "Saves or updates a resource in the knowledge base.",
    "parameters": {
        "type": "object",
        "properties": {
            "resource_type": {"type": "string", "enum": ["playbook", "prompt_template", "lesson_learned", "brand_guideline"]},
            "data": {"type": "object", "description": "The resource data to save."},
        },
        "required": ["resource_type", "data"],
    },
}

# Register the tools
registry.register(
    name="knowledge_search",
    toolset="knowledge",
    schema=KNOWLEDGE_SEARCH_SCHEMA,
    handler=_handle_knowledge_search,
    description="Search the knowledge base.",
    emoji="📚"
)

registry.register(
    name="knowledge_save",
    toolset="knowledge",
    schema=KNOWLEDGE_SAVE_SCHEMA,
    handler=_handle_knowledge_save,
    description="Save to the knowledge base.",
    emoji="💾"
)
