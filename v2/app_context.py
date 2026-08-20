import os
import re
import json
import hashlib
from pathlib import Path
from typing import Optional

import psycopg2
from psycopg2.extras import Json


# ============================================================
# CONFIGURATION
# ============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/agent"
)

DEFAULT_IGNORE_DIRS = {
    ".git",
    ".svn",
    ".hg",

    "node_modules",
    ".venv",
    "venv",
    "env",

    "__pycache__",
    ".pytest_cache",

    "dist",
    "build",
    "target",

    ".next",
    ".nuxt",
    ".angular",

    "coverage",
    ".idea",
    ".vscode",

    "vendor",
}

TEXT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",

    ".java",
    ".kt",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",

    ".sql",

    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".env",

    ".xml",

    ".html",
    ".css",
    ".scss",
    ".less",

    ".md",
    ".txt",

    ".sh",
    ".bash",

    ".dart",
    ".php",
    ".rb",
    ".swift",
}


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ============================================================
# FILE UTILITIES
# ============================================================

def sha256_text(content: str) -> str:
    return hashlib.sha256(
        content.encode("utf-8", errors="ignore")
    ).hexdigest()


def is_binary_file(file_path: Path) -> bool:
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(4096)

        return b"\x00" in chunk

    except Exception:
        return True


def read_file(file_path: Path) -> Optional[str]:
    try:
        return file_path.read_text(
            encoding="utf-8",
            errors="ignore"
        )
    except Exception:
        return None


def detect_language(extension: str) -> Optional[str]:

    mapping = {
        ".py": "python",

        ".js": "javascript",
        ".jsx": "javascript",

        ".ts": "typescript",
        ".tsx": "typescript",

        ".java": "java",
        ".kt": "kotlin",

        ".go": "go",
        ".rs": "rust",

        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",

        ".sql": "sql",

        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",

        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".less": "less",

        ".md": "markdown",

        ".sh": "shell",
        ".bash": "shell",

        ".dart": "dart",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
    }

    return mapping.get(extension.lower())


def detect_file_type(
    file_path: Path
) -> str:

    name = file_path.name.lower()
    ext = file_path.suffix.lower()

    if ext == ".sql":
        return "schema"

    if name.startswith("test_") or name.endswith("_test.py"):
        return "test"

    if ".test." in name or ".spec." in name:
        return "test"

    if name in {
        "package.json",
        "tsconfig.json",
        "angular.json",
        "vite.config.js",
        "vite.config.ts",
        "webpack.config.js",
        "docker-compose.yml",
        "docker-compose.yaml",
        "pyproject.toml",
        "requirements.txt",
    }:
        return "config"

    if ext in {
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".ini",
    }:
        return "config"

    if ext in {
        ".md",
        ".txt",
    }:
        return "documentation"

    return "source"


# ============================================================
# PROJECT STACK DETECTION
# ============================================================

def detect_frameworks(files):
    names = {
        Path(f).name.lower()
        for f in files
    }

    stack = {}

    if "package.json" in names:
        stack["runtime"] = "node"

    if "angular.json" in names:
        stack["frontend"] = "angular"

    if "next.config.js" in names or "next.config.ts" in names:
        stack["frontend"] = "nextjs"

    if "vite.config.js" in names or "vite.config.ts" in names:
        stack["frontend"] = "vite"

    if "requirements.txt" in names:
        stack["runtime"] = "python"

    if "pyproject.toml" in names:
        stack["runtime"] = "python"

    if "pom.xml" in names:
        stack["runtime"] = "java"

    if "go.mod" in names:
        stack["runtime"] = "go"

    if "Cargo.toml" in names:
        stack["runtime"] = "rust"

    return stack


# ============================================================
# PYTHON AST
# ============================================================

def parse_python(file_path: Path):

    content = read_file(file_path)

    if content is None:
        return None

    try:
        return ast.parse(content)
    except Exception:
        return None


def extract_python_dependencies(tree):

    dependencies = set()

    if tree is None:
        return dependencies

    for node in ast.walk(tree):

        if isinstance(node, ast.Import):

            for alias in node.names:
                dependencies.add(alias.name)

        elif isinstance(node, ast.ImportFrom):

            if node.module:
                dependencies.add(node.module)

    return dependencies


def extract_python_symbols(tree):

    symbols = []

    if tree is None:
        return symbols

    for node in ast.walk(tree):

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef
            )
        ):

            symbols.append({
                "name": node.name,
                "type": (
                    "class"
                    if isinstance(node, ast.ClassDef)
                    else "function"
                ),
                "start_line": node.lineno,
                "end_line": getattr(
                    node,
                    "end_lineno",
                    node.lineno
                ),
            })

    return symbols


# ============================================================
# GENERIC SYMBOL EXTRACTION
# ============================================================

def extract_generic_symbols(
    content,
    language
):

    symbols = []

    patterns = []

    if language in {
        "javascript",
        "typescript"
    }:

        patterns = [
            (
                r"\bfunction\s+([A-Za-z_$][\w$]*)",
                "function"
            ),
            (
                r"\bclass\s+([A-Za-z_$][\w$]*)",
                "class"
            ),
            (
                r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=",
                "variable"
            ),
        ]

    elif language == "sql":

        patterns = [
            (
                r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_.\"]+)",
                "table"
            ),
            (
                r"\bCREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+([A-Za-z0-9_.\"]+)",
                "function"
            ),
            (
                r"\bCREATE\s+INDEX\s+([A-Za-z0-9_.\"]+)",
                "index"
            ),
        ]

    for pattern, symbol_type in patterns:

        for match in re.finditer(
            pattern,
            content,
            re.IGNORECASE
        ):

            line = content[:match.start()].count("\n") + 1

            symbols.append({
                "name": match.group(1),
                "type": symbol_type,
                "start_line": line,
                "end_line": line,
            })

    return symbols


# ============================================================
# DEPENDENCY EXTRACTION
# ============================================================

def extract_dependencies(
    file_path: Path,
    content: str,
    language: str
):

    dependencies = set()

    if language == "python":

        tree = parse_python(file_path)

        dependencies.update(
            extract_python_dependencies(tree)
        )

    elif language in {
        "javascript",
        "typescript"
    }:

        patterns = [
            r'import\s+.*?\s+from\s+[\'"]([^\'"]+)',
            r'import\s*[\'"]([^\'"]+)[\'"]',
            r'require\s*\(\s*[\'"]([^\'"]+)[\'"]',
        ]

        for pattern in patterns:

            for match in re.finditer(
                pattern,
                content
            ):
                dependencies.add(
                    match.group(1)
                )

    elif language == "sql":

        for match in re.finditer(
            r'\b(?:FROM|JOIN)\s+([A-Za-z0-9_."]+)',
            content,
            re.IGNORECASE
        ):
            dependencies.add(
                match.group(1)
            )

    return sorted(dependencies)


# ============================================================
# CHUNKING
# ============================================================

def chunk_text(
    content: str,
    chunk_size: int = 120,
    overlap: int = 20
):

    lines = content.splitlines()

    chunks = []

    start = 0
    chunk_index = 0

    while start < len(lines):

        end = min(
            start + chunk_size,
            len(lines)
        )

        chunk_lines = lines[start:end]

        chunks.append({
            "chunk_index": chunk_index,
            "start_line": start + 1,
            "end_line": end,
            "content": "\n".join(chunk_lines),
        })

        chunk_index += 1

        if end >= len(lines):
            break

        start = end - overlap

    return chunks


# ============================================================
# FILE DISCOVERY
# ============================================================

def discover_files(
    folders,
    ignore_dirs=None
):

    ignore_dirs = ignore_dirs or DEFAULT_IGNORE_DIRS

    discovered = []

    for folder in folders:

        root = Path(folder).resolve()

        if not root.exists():
            raise FileNotFoundError(
                f"Folder does not exist: {root}"
            )

        if not root.is_dir():
            raise ValueError(
                f"Not a directory: {root}"
            )

        for current_root, dirs, files in os.walk(root):

            dirs[:] = [
                d for d in dirs
                if d not in ignore_dirs
            ]

            for filename in files:

                path = Path(current_root) / filename

                if path.suffix.lower() not in TEXT_EXTENSIONS:
                    continue

                if is_binary_file(path):
                    continue

                discovered.append(
                    path.resolve()
                )

    return sorted(
        set(discovered)
    )


# ============================================================
# PROJECT ROOT
# ============================================================

def determine_project_root(
    folders
):

    roots = [
        Path(folder).resolve()
        for folder in folders
    ]

    if len(roots) == 1:
        return roots[0]

    try:
        return Path(
            os.path.commonpath(
                [str(x) for x in roots]
            )
        )
    except Exception:
        return roots[0]


# ============================================================
# INIT CONTEXT
# ============================================================

def init_context(
    folders,
    project_name=None
):

    """
    Scan project folders and populate app_context.

    Example:

        project_id = init_context([
            "./backend",
            "./frontend",
            "./database"
        ])
    """

    files = discover_files(folders)

    root = determine_project_root(folders)

    if not project_name:
        project_name = root.name

    stack = detect_frameworks(files)

    conn = get_connection()

    try:

        with conn.cursor() as cur:

            # ------------------------------------------------
            # PROJECT
            # ------------------------------------------------

            cur.execute(
                """
                INSERT INTO app_context_projects
                (
                    project_name,
                    root_path,
                    detected_stack
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (root_path)
                DO UPDATE SET
                    project_name = EXCLUDED.project_name,
                    detected_stack = EXCLUDED.detected_stack,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING context_project_id
                """,
                (
                    project_name,
                    str(root),
                    Json(stack)
                )
            )

            project_id = cur.fetchone()[0]

            # ------------------------------------------------
            # FILES
            # ------------------------------------------------

            for file_path in files:

                relative_path = str(
                    file_path.relative_to(root)
                ).replace("\\", "/")

                content = read_file(file_path)

                if content is None:
                    continue

                extension = file_path.suffix.lower()

                language = detect_language(
                    extension
                )

                file_type = detect_file_type(
                    file_path
                )

                content_hash = sha256_text(
                    content
                )

                size_bytes = file_path.stat().st_size

                # --------------------------------------------
                # FILE RECORD
                # --------------------------------------------

                cur.execute(
                    """
                    INSERT INTO app_context_files
                    (
                        context_project_id,
                        file_path,
                        relative_path,
                        file_name,
                        extension,
                        language,
                        framework,
                        file_type,
                        size_bytes,
                        content_hash,
                        is_binary
                    )
                    VALUES
                    (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE
                    )
                    ON CONFLICT
                    (
                        context_project_id,
                        relative_path
                    )
                    DO UPDATE SET
                        file_path = EXCLUDED.file_path,
                        file_name = EXCLUDED.file_name,
                        extension = EXCLUDED.extension,
                        language = EXCLUDED.language,
                        framework = EXCLUDED.framework,
                        file_type = EXCLUDED.file_type,
                        size_bytes = EXCLUDED.size_bytes,
                        content_hash = EXCLUDED.content_hash,
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING context_file_id
                    """,
                    (
                        project_id,
                        str(file_path),
                        relative_path,
                        file_path.name,
                        extension,
                        language,
                        None,
                        file_type,
                        size_bytes,
                        content_hash
                    )
                )

                file_id = cur.fetchone()[0]

                # --------------------------------------------
                # CHECK WHETHER CONTENT CHANGED
                # --------------------------------------------

                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM app_context_chunks
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

                existing_chunks = cur.fetchone()[0]

                if existing_chunks:

                    cur.execute(
                        """
                        SELECT content_hash
                        FROM app_context_chunks
                        WHERE context_file_id = %s
                        ORDER BY chunk_index
                        LIMIT 1
                        """,
                        (file_id,)
                    )

                    old_hash = cur.fetchone()

                    if (
                        old_hash
                        and old_hash[0] == content_hash
                    ):
                        continue

                # --------------------------------------------
                # REMOVE OLD CHUNKS
                # --------------------------------------------

                cur.execute(
                    """
                    DELETE FROM app_context_chunks
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

                # --------------------------------------------
                # CHUNKS
                # --------------------------------------------

                chunks = chunk_text(content)

                for chunk in chunks:

                    cur.execute(
                        """
                        INSERT INTO app_context_chunks
                        (
                            context_file_id,
                            chunk_index,
                            start_line,
                            end_line,
                            content,
                            content_hash
                        )
                        VALUES
                        (
                            %s,%s,%s,%s,%s,%s
                        )
                        """,
                        (
                            file_id,
                            chunk["chunk_index"],
                            chunk["start_line"],
                            chunk["end_line"],
                            chunk["content"],
                            content_hash
                        )
                    )

                # --------------------------------------------
                # SYMBOLS
                # --------------------------------------------

                cur.execute(
                    """
                    DELETE FROM app_context_symbols
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

                if language == "python":

                    tree = parse_python(file_path)

                    symbols = extract_python_symbols(
                        tree
                    )

                else:

                    symbols = extract_generic_symbols(
                        content,
                        language
                    )

                for symbol in symbols:

                    cur.execute(
                        """
                        INSERT INTO app_context_symbols
                        (
                            context_file_id,
                            symbol_name,
                            symbol_type,
                            start_line,
                            end_line
                        )
                        VALUES
                        (
                            %s,%s,%s,%s,%s
                        )
                        """,
                        (
                            file_id,
                            symbol["name"],
                            symbol["type"],
                            symbol["start_line"],
                            symbol["end_line"]
                        )
                    )

                # --------------------------------------------
                # DEPENDENCIES
                # --------------------------------------------

                dependencies = extract_dependencies(
                    file_path,
                    content,
                    language
                )

                cur.execute(
                    """
                    DELETE FROM app_context_dependencies
                    WHERE source_file_id = %s
                    """,
                    (file_id,)
                )

                for dependency in dependencies:

                    cur.execute(
                        """
                        INSERT INTO app_context_dependencies
                        (
                            context_project_id,
                            source_file_id,
                            dependency_name,
                            dependency_type
                        )
                        VALUES
                        (
                            %s,%s,%s,%s
                        )
                        """,
                        (
                            project_id,
                            file_id,
                            dependency,
                            "import"
                        )
                    )

            # ------------------------------------------------
            # MARK REMOVED FILES
            # ------------------------------------------------

            current_paths = {
                str(
                    p.relative_to(root)
                ).replace("\\", "/")
                for p in files
            }

            cur.execute(
                """
                SELECT
                    context_file_id,
                    relative_path
                FROM app_context_files
                WHERE context_project_id = %s
                """,
                (project_id,)
            )

            existing_files = cur.fetchall()

            for file_id, relative_path in existing_files:

                if relative_path not in current_paths:

                    cur.execute(
                        """
                        UPDATE app_context_files
                        SET is_active = FALSE,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE context_file_id = %s
                        """,
                        (file_id,)
                    )

        conn.commit()

        return project_id

    finally:
        conn.close()


# ============================================================
# TOKEN-LIKE SEARCH
# ============================================================

def tokenize(text):

    return set(
        re.findall(
            r"[A-Za-z_][A-Za-z0-9_.-]{2,}",
            text.lower()
        )
    )


def lexical_score(
    requirement,
    content
):

    requirement_tokens = tokenize(
        requirement
    )

    content_tokens = tokenize(
        content
    )

    if not requirement_tokens:
        return 0.0

    intersection = (
        requirement_tokens &
        content_tokens
    )

    return (
        len(intersection)
        /
        len(requirement_tokens)
    )


# ============================================================
# GET RELEVANT CONTEXT
# ============================================================

def get_relevant_context(
    requirement,
    project_id,
    max_files=15,
    max_chunks=40
):

    """
    Retrieve repository context relevant to a requirement.

    Returns data ready for the Supervisor/Ollama prompt.
    """

    conn = get_connection()

    try:

        with conn.cursor() as cur:

            # ------------------------------------------------
            # PROJECT
            # ------------------------------------------------

            cur.execute(
                """
                SELECT
                    project_name,
                    root_path,
                    detected_stack
                FROM app_context_projects
                WHERE context_project_id = %s
                """,
                (project_id,)
            )

            project = cur.fetchone()

            if not project:
                raise ValueError(
                    f"Unknown context project: {project_id}"
                )

            project_name, root_path, stack = project

            # ------------------------------------------------
            # ALL ACTIVE FILES
            # ------------------------------------------------

            cur.execute(
                """
                SELECT
                    context_file_id,
                    relative_path,
                    file_name,
                    language,
                    file_type,
                    content_hash
                FROM app_context_files
                WHERE context_project_id = %s
                  AND is_active = TRUE
                """,
                (project_id,)
            )

            files = cur.fetchall()

            # ------------------------------------------------
            # SCORE FILES
            # ------------------------------------------------

            scored_files = []

            for row in files:

                (
                    file_id,
                    relative_path,
                    file_name,
                    language,
                    file_type,
                    content_hash
                ) = row

                cur.execute(
                    """
                    SELECT content
                    FROM app_context_chunks
                    WHERE context_file_id = %s
                    ORDER BY chunk_index
                    """,
                    (file_id,)
                )

                chunks = [
                    x[0]
                    for x in cur.fetchall()
                ]

                combined_content = "\n".join(
                    chunks
                )

                score = lexical_score(
                    requirement,
                    (
                        relative_path
                        + "\n"
                        + combined_content
                    )
                )

                scored_files.append({
                    "context_file_id": file_id,
                    "path": relative_path,
                    "file_name": file_name,
                    "language": language,
                    "file_type": file_type,
                    "score": score,
                    "content_hash": content_hash,
                })

            scored_files.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            relevant_files = scored_files[
                :max_files
            ]

            # ------------------------------------------------
            # RELEVANT CHUNKS
            # ------------------------------------------------

            relevant_chunks = []

            for file in relevant_files:

                cur.execute(
                    """
                    SELECT
                        context_chunk_id,
                        chunk_index,
                        start_line,
                        end_line,
                        content
                    FROM app_context_chunks
                    WHERE context_file_id = %s
                    ORDER BY chunk_index
                    """,
                    (
                        file["context_file_id"],
                    )
                )

                chunks = cur.fetchall()

                for (
                    chunk_id,
                    chunk_index,
                    start_line,
                    end_line,
                    content
                ) in chunks:

                    score = lexical_score(
                        requirement,
                        content
                    )

                    relevant_chunks.append({
                        "context_chunk_id": chunk_id,
                        "file": file["path"],
                        "start_line": start_line,
                        "end_line": end_line,
                        "content": content,
                        "score": score,
                    })

            relevant_chunks.sort(
                key=lambda x: x["score"],
                reverse=True
            )

            relevant_chunks = relevant_chunks[
                :max_chunks
            ]

            # ------------------------------------------------
            # EXISTING PATH SET
            # ------------------------------------------------

            existing_paths = {
                f["path"]
                for f in scored_files
            }

            # ------------------------------------------------
            # CONTEXT RESULT
            # ------------------------------------------------

            return {
                "project": {
                    "id": project_id,
                    "name": project_name,
                    "root_path": root_path,
                    "stack": stack or {},
                },

                "requirement": requirement,

                "existing_files": [
                    {
                        "path": f["path"],
                        "language": f["language"],
                        "file_type": f["file_type"],
                        "change_type": "edit",
                        "relevance": round(
                            f["score"],
                            4
                        ),
                    }
                    for f in relevant_files
                ],

                "relevant_chunks": relevant_chunks,

                "all_existing_paths": sorted(
                    existing_paths
                ),
            }

    finally:
        conn.close()


# ============================================================
# BUILD OLLAMA SUPERVISOR PROMPT
# ============================================================

def build_supervisor_prompt(
    requirement,
    context
):

    existing_files = context[
        "existing_files"
    ]

    chunks = context[
        "relevant_chunks"
    ]

    stack = context[
        "project"
    ]["stack"]

    files_text = "\n".join(
        f"- {f['path']} "
        f"({f['language']}, {f['file_type']})"
        for f in existing_files
    )

    context_text = "\n\n".join(
        (
            f"--- {chunk['file']} "
            f"lines {chunk['start_line']}-"
            f"{chunk['end_line']} ---\n"
            f"{chunk['content']}"
        )
        for chunk in chunks
    )

    return f"""
You are the Supervisor of a multi-agent software
development system.

Your responsibility is to convert the user requirement
into an ordered implementation task checklist.

PROJECT STACK:

{json.dumps(stack, indent=2)}

EXISTING REPOSITORY FILES:

{files_text}

RELEVANT CODE CONTEXT:

{context_text}

USER REQUIREMENT:

{requirement}

IMPORTANT RULES:

1. Do not invent existing files.
2. If a required file exists, use change_type "edit".
3. If a required file does not exist, use change_type "create".
4. Do not modify unrelated files.
5. Break the requirement into sequential implementation tasks.
6. Assign every task to an appropriate domain.
7. Include the exact file path for every affected file.
8. Tasks must be ordered by dependency.
9. Return ONLY valid JSON.

OUTPUT FORMAT:

{{
    "tasks": [
        {{
            "step_id": 1,
            "domain": "postgres",
            "description": "Create ...",
            "files_affected": [
                {{
                    "path": "db/schema.sql",
                    "change_type": "edit"
                }}
            ]
        }}
    ]
}}
"""

# ============================================================
# SIMPLE EXAMPLE
# ============================================================

# if __name__ == "__main__":

#     # --------------------------------------------
#     # 1. Index project
#     # --------------------------------------------

#     project_id = init_context([
#         "./backend",
#         "./frontend",
#         "./database"
#     ])

#     print(
#         f"Context initialized: {project_id}"
#     )

#     # --------------------------------------------
#     # 2. Requirement
#     # --------------------------------------------

#     requirement = """
#     Add audit logging to all authenticated API requests.
#     Store the user, endpoint, HTTP method, timestamp and
#     response status in PostgreSQL.
#     """

#     # --------------------------------------------
#     # 3. Retrieve context
#     # --------------------------------------------

#     context = get_relevant_context(
#         requirement,
#         project_id
#     )

#     print(
#         json.dumps(
#             context,
#             indent=4,
#             default=str
#         )
#     )

#     # --------------------------------------------
#     # 4. Build Ollama prompt
#     # --------------------------------------------

#     prompt = build_supervisor_prompt(
#         requirement,
#         context
#     )

#     print("\n\n===== SUPERVISOR PROMPT =====\n")

#     print(prompt)