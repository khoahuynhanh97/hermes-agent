import ast
from pathlib import Path


APP_PATH = Path(__file__).parents[2] / "gui" / "app.py"


def _called_methods(function_name):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == function_name
    )
    return {
        node.func.attr
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }


def test_project_selection_routes_through_prompt_studio_project_load():
    assert "load_project_details" in _called_methods("on_project_combobox_change")
    assert "load_for_project" in _called_methods("load_project_details")


def test_successful_quick_project_creation_routes_through_project_load():
    assert "load_project_details" in _called_methods("create_quick_project")
    assert "load_for_project" in _called_methods("load_project_details")
