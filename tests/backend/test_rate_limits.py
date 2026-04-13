from __future__ import annotations

import ast
from pathlib import Path


PROTECTED_ROUTE_FILES = [
    "backend/api/videos.py",
    "backend/api/tasks.py",
    "backend/api/search.py",
    "backend/api/keywords.py",
    "backend/api/frames.py",
    "backend/api/stats.py",
]


def _load_module_ast(relative_path: str) -> ast.Module:
    source = Path(relative_path).read_text(encoding="utf-8")
    return ast.parse(source)


def _route_functions(module: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    route_functions: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and isinstance(decorator.func.value, ast.Name)
                and decorator.func.value.id == "router"
            ):
                route_functions.append(node)
                break
    return route_functions


def _limiter_values(function_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
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


def test_protected_endpoints_use_limiter_decorators_and_request_param():
    main_source = Path("backend/main.py").read_text(encoding="utf-8")
    assert 'Depends(limiter.limit("60/minute"))' not in main_source

    for relative_path in PROTECTED_ROUTE_FILES:
        module = _load_module_ast(relative_path)
        route_functions = _route_functions(module)
        assert route_functions, f"No route functions found in {relative_path}"

        for function_node in route_functions:
            arg_names = [arg.arg for arg in function_node.args.args]
            assert "request" in arg_names, f"{relative_path}:{function_node.name} missing request parameter"
            assert _limiter_values(function_node) == ["60/minute"], (
                f"{relative_path}:{function_node.name} missing @limiter.limit('60/minute')"
            )
