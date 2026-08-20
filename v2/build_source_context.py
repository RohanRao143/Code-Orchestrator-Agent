import os
import ast
import json

def parse_file(file_path):
    with open(file_path, 'r') as file:
        tree = ast.parse(file.read())
        return tree

def extract_dependencies(tree):
    dependencies = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dependencies.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            dependencies.add(node.module)
    return dependencies

def build_context(file_paths):
    context = {}
    for file_path in file_paths:
        tree = parse_file(file_path)
        dependencies = extract_dependencies(tree)
        context[file_path] = {
            'dependencies': dependencies
        }
    return context

# Example usage
file_paths = ['src/main.py', 'src/utils.py']
context = build_context(file_paths)
print(json.dumps(context, indent=4))