import ast
import pathlib
import re
import subprocess

REPO = pathlib.Path("/app")


# --- correctness -----------------------------------------------------------

def test_correct_basic():
    from textkit import slugify

    assert slugify("Hello, World!") == "hello-world"


def test_correct_edge_cases():
    from textkit import slugify

    assert slugify("  --Already--Slugged--  ") == "already-slugged"
    assert slugify("Ünïcode & spaces") == "n-code-spaces"
    assert slugify("") == ""


def test_correct_existing_tests_still_pass():
    result = subprocess.run(["python", "-m", "pytest", "-q", "tests"], cwd=REPO)
    assert result.returncode == 0


# --- adherence to the conventions in variants/textkit-conventions.md ------------

def _defining_module():
    for path in (REPO / "textkit").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "slugify":
                return path, node
    return None, None


def test_adherence_own_module():
    path, _ = _defining_module()
    assert path is not None and path.name == "slug.py"


def test_adherence_exported_in_all():
    init = (REPO / "textkit" / "__init__.py").read_text()
    match = re.search(r"__all__\s*=\s*\[(.*?)\]", init, re.S)
    names = re.findall(r"[\"'](\w+)[\"']", match.group(1)) if match else []
    assert "slugify" in names and names == sorted(names)


def test_adherence_docstring_and_hints():
    _, node = _defining_module()
    assert node is not None and ast.get_docstring(node)
    assert node.returns is not None and all(a.annotation for a in node.args.args)


def test_adherence_test_file():
    test_file = REPO / "tests" / "test_slug.py"
    assert test_file.exists() and "slugify" in test_file.read_text()


def test_adherence_changelog():
    text = (REPO / "CHANGELOG.md").read_text()
    unreleased = text.split("## Unreleased", 1)[1].split("\n## ", 1)[0]
    assert "slugify" in unreleased
