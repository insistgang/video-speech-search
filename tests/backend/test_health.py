from __future__ import annotations

import ast
from pathlib import Path


def _load_module_ast(relative_path: str) -> ast.Module:
    source = Path(relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def _find_function(module: ast.Module, function_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            return node
    raise AssertionError(f"Function {function_name} not found")


def _decorator_values(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    values: list[str] = []
    for decorator in function_node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "limiter"
            and decorator.func.attr == "limit"
            and decorator.args
            and isinstance(decorator.args[0], ast.Constant)
        ):
            values.append(str(decorator.args[0].value))
    return values


def test_health_route_source_is_router_only_and_matches_frontend_shape():
    main_source = Path("backend/main.py").read_text(encoding="utf-8")
    assert '@app.get("/api/health")' not in main_source

    health_module = _load_module_ast("backend/api/health.py")
    healthcheck = _find_function(health_module, "healthcheck")

    assert "request" in [arg.arg for arg in healthcheck.args.args]
    assert _decorator_values(healthcheck) == ["10/minute"]

    return_nodes = [node for node in ast.walk(healthcheck) if isinstance(node, ast.Return)]
    assert len(return_nodes) == 1
    returned_value = return_nodes[0].value
    assert isinstance(returned_value, ast.Dict)
    keys = {key.value for key in returned_value.keys if isinstance(key, ast.Constant)}
    assert keys == {"status", "vision_analyzer_mode"}
