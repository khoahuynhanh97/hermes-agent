import json
from typing import Dict, Any
from hermes.tools.registry import registry, tool_error, tool_result
from .service import ProductScoutService, AssetProjectionService

def _handle_product_scout(args: Dict[str, Any], **kwargs) -> str:
    """
    Handler for the product_scout tool.
    It can scout for product info or get resource pack details.
    """
    sku = args.get("sku")
    action = args.get("action", "scout_info")

    if not sku:
        return tool_error("SKU is required.")

    try:
        if action == "scout_info":
            service = ProductScoutService()
            product_info = service.scout_by_sku(sku)
            if not product_info:
                return tool_error(f"Product info not found for SKU: {sku}")
            return tool_result(product_info.model_dump())

        elif action == "get_resource_pack":
            service = AssetProjectionService()
            resource_pack = service.load_and_verify_resource_pack(sku)
            if not resource_pack:
                return tool_error(f"Resource pack not found or failed verification for SKU: {sku}")
            # Paths are not JSON serializable, so convert them to strings
            pack_dict = resource_pack.model_dump()
            for asset in pack_dict.get("assets", []):
                if asset.get("physical_path"):
                    asset["physical_path"] = str(asset["physical_path"])
            return tool_result(pack_dict)

        else:
            return tool_error(f"Invalid action: {action}. Must be 'scout_info' or 'get_resource_pack'.")

    except Exception as e:
        return tool_error(f"An error occurred in product_scout: {e}")


PRODUCT_SCOUT_SCHEMA = {
    "name": "product_scout",
    "description": "Scouts for product information or retrieves a verified resource pack from the Product Intelligence data store.",
    "parameters": {
        "type": "object",
        "properties": {
            "sku": {
                "type": "string",
                "description": "The SKU of the product to scout for."
            },
            "action": {
                "type": "string",
                "enum": ["scout_info", "get_resource_pack"],
                "description": "The action to perform: 'scout_info' to get product details, 'get_resource_pack' to get the asset list.",
                "default": "scout_info"
            }
        },
        "required": ["sku"]
    }
}

registry.register(
    name="product_scout",
    toolset="product_intelligence",
    schema=PRODUCT_SCOUT_SCHEMA,
    handler=_handle_product_scout,
    description="Scout for product data and resources.",
    emoji="🕵️"
)
