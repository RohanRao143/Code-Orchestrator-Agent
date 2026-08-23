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
    "postgresql://postgres:password@localhost:5432/multi_agent_coder"
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


def init_context_code_graph(
    folders,
    project_name=None
):
    """
    Scan project folders and populate the code-context graph.

    Graph model:

        FILE
          |
          +---- contains ----> SYMBOL
          |                      |
          |                      +---- parent ----> SYMBOL
          |                      |
          |                      +---- calls ------> SYMBOL
          |                      |
          |                      +---- references -> SYMBOL
          |
          +---- imports -----> FILE

        CHUNK
          |
          +---- evidence for ----> SYMBOL

    The function keeps incremental file ingestion using content hashes.

    Returns:
        int: context_project_id
    """

    # ============================================================
    # DISCOVER PROJECT
    # ============================================================

    files = discover_files(folders)

    root = determine_project_root(folders)

    if not project_name:
        project_name = root.name

    stack = detect_frameworks(files)

    conn = get_connection()

    try:

        with conn.cursor() as cur:

            # ====================================================
            # PROJECT
            # ====================================================

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

            # ====================================================
            # BUILD CURRENT FILE MAP
            # ====================================================

            current_file_map = {}

            for file_path in files:

                try:
                    relative_path = str(
                        file_path.relative_to(root)
                    ).replace("\\", "/")
                except ValueError:
                    continue

                current_file_map[relative_path] = file_path

            # ====================================================
            # LOAD EXISTING FILE MAP
            #
            # This allows dependency resolution later.
            # ====================================================

            cur.execute(
                """
                SELECT
                    context_file_id,
                    relative_path,
                    file_name,
                    file_path,
                    is_active
                FROM app_context_files
                WHERE context_project_id = %s
                """,
                (project_id,)
            )

            existing_file_rows = cur.fetchall()

            file_id_by_relative_path = {}

            for (
                existing_file_id,
                existing_relative_path,
                existing_file_name,
                existing_file_path,
                existing_is_active
            ) in existing_file_rows:

                normalized_path = (
                    str(existing_relative_path)
                    .replace("\\", "/")
                )

                file_id_by_relative_path[
                    normalized_path
                ] = existing_file_id

            # ====================================================
            # PROCESS FILES
            # ====================================================

            for file_path in files:

                # ------------------------------------------------
                # RELATIVE PATH
                # ------------------------------------------------

                try:
                    relative_path = str(
                        file_path.relative_to(root)
                    ).replace("\\", "/")
                except ValueError:
                    continue

                # ------------------------------------------------
                # READ CONTENT
                # ------------------------------------------------

                content = read_file(file_path)

                if content is None:
                    continue

                # ------------------------------------------------
                # FILE METADATA
                # ------------------------------------------------

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

                # =================================================
                # FILE RECORD
                # =================================================

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
                        is_binary,
                        is_active
                    )
                    VALUES
                    (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,TRUE
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
                        is_binary = EXCLUDED.is_binary,
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

                # ------------------------------------------------
                # UPDATE FILE MAP
                # ------------------------------------------------

                file_id_by_relative_path[
                    relative_path
                ] = file_id

                # =================================================
                # CHECK WHETHER CONTENT CHANGED
                # =================================================

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

                old_hash_row = cur.fetchone()

                content_changed = (
                    old_hash_row is None
                    or old_hash_row[0] != content_hash
                )

                # =================================================
                # IF CONTENT DID NOT CHANGE
                #
                # We can leave the existing graph data untouched.
                # =================================================

                if not content_changed:
                    continue

                # =================================================
                # REMOVE OLD GRAPH DATA
                # =================================================

                # Dependencies referencing this file as target
                cur.execute(
                    """
                    DELETE FROM app_context_dependencies
                    WHERE target_file_id = %s
                    """,
                    (file_id,)
                )

                # Dependencies originating from this file
                cur.execute(
                    """
                    DELETE FROM app_context_dependencies
                    WHERE source_file_id = %s
                    """,
                    (file_id,)
                )

                # Symbols are deleted before chunks because chunks
                # may reference primary_symbol_id.
                cur.execute(
                    """
                    UPDATE app_context_chunks
                    SET primary_symbol_id = NULL
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

                cur.execute(
                    """
                    DELETE FROM app_context_symbols
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

                # =================================================
                # CHUNKS
                # =================================================

                cur.execute(
                    """
                    DELETE FROM app_context_chunks
                    WHERE context_file_id = %s
                    """,
                    (file_id,)
                )

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
                        RETURNING context_chunk_id
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

                # =================================================
                # SYMBOLS
                # =================================================

                if language == "python":

                    tree = parse_python(
                        file_path
                    )

                    symbols = extract_python_symbols(
                        tree
                    )

                else:

                    symbols = extract_generic_symbols(
                        content,
                        language
                    )

                # -------------------------------------------------
                # Normalize symbol records.
                #
                # Existing extractors may only return:
                #
                # {
                #     name,
                #     type,
                #     start_line,
                #     end_line
                # }
                #
                # This keeps them compatible while supporting the
                # richer graph metadata.
                # -------------------------------------------------

                normalized_symbols = []

                for symbol in symbols or []:

                    if not isinstance(symbol, dict):
                        continue

                    name = (
                        symbol.get("name")
                        or symbol.get("symbol_name")
                    )

                    if not name:
                        continue

                    symbol_type = (
                        symbol.get("type")
                        or symbol.get("symbol_type")
                        or "unknown"
                    )

                    start_line = symbol.get(
                        "start_line"
                    )

                    end_line = symbol.get(
                        "end_line"
                    )

                    qualified_name = (
                        symbol.get("qualified_name")
                        or symbol.get("qualname")
                        or name
                    )

                    parent_name = (
                        symbol.get("parent_name")
                        or symbol.get("parent")
                    )

                    signature = (
                        symbol.get("signature")
                    )

                    normalized_symbols.append(
                        {
                            "name": str(name),
                            "qualified_name": str(
                                qualified_name
                            ),
                            "type": str(symbol_type),
                            "parent_name": (
                                str(parent_name)
                                if parent_name
                                else None
                            ),
                            "signature": (
                                str(signature)
                                if signature
                                else None
                            ),
                            "start_line": start_line,
                            "end_line": end_line,
                        }
                    )

                # -------------------------------------------------
                # Insert symbols first.
                #
                # Parent relationships are resolved afterwards
                # because parent_symbol_id requires an actual ID.
                # -------------------------------------------------

                symbol_records = []

                for symbol in normalized_symbols:

                    signature_hash = None

                    if symbol["signature"]:
                        signature_hash = sha256_text(
                            symbol["signature"]
                        )

                    cur.execute(
                        """
                        INSERT INTO app_context_symbols
                        (
                            context_file_id,
                            symbol_name,
                            qualified_name,
                            symbol_type,
                            signature,
                            signature_hash,
                            start_line,
                            end_line
                        )
                        VALUES
                        (
                            %s,%s,%s,%s,%s,%s,%s,%s
                        )
                        RETURNING symbol_id
                        """,
                        (
                            file_id,
                            symbol["name"],
                            symbol["qualified_name"],
                            symbol["type"],
                            symbol["signature"],
                            signature_hash,
                            symbol["start_line"],
                            symbol["end_line"]
                        )
                    )

                    symbol_id = cur.fetchone()[0]

                    symbol_records.append(
                        {
                            "symbol_id": symbol_id,
                            **symbol
                        }
                    )

                # =================================================
                # SYMBOL LOOKUP MAPS
                # =================================================

                symbol_by_name = {}

                symbol_by_qualified_name = {}

                for symbol in symbol_records:

                    symbol_by_name.setdefault(
                        symbol["name"],
                        []
                    ).append(symbol)

                    symbol_by_qualified_name[
                        symbol["qualified_name"]
                    ] = symbol

                # =================================================
                # RESOLVE PARENT SYMBOLS
                # =================================================

                for symbol in symbol_records:

                    parent_name = symbol.get(
                        "parent_name"
                    )

                    if not parent_name:
                        continue

                    parent = (
                        symbol_by_qualified_name.get(
                            parent_name
                        )
                    )

                    if parent is None:

                        candidates = (
                            symbol_by_name.get(
                                parent_name,
                                []
                            )
                        )

                        if len(candidates) == 1:
                            parent = candidates[0]

                    if parent is None:
                        continue

                    cur.execute(
                        """
                        UPDATE app_context_symbols
                        SET parent_symbol_id = %s
                        WHERE symbol_id = %s
                        """,
                        (
                            parent["symbol_id"],
                            symbol["symbol_id"]
                        )
                    )

                # =================================================
                # ASSIGN CHUNKS TO PRIMARY SYMBOL
                # =================================================

                #
                # A chunk is considered evidence for a symbol when
                # the symbol's line range overlaps the chunk range.
                #
                # Prefer the smallest containing symbol.
                #

                cur.execute(
                    """
                    SELECT
                        context_chunk_id,
                        start_line,
                        end_line
                    FROM app_context_chunks
                    WHERE context_file_id = %s
                    ORDER BY chunk_index
                    """,
                    (file_id,)
                )

                chunk_rows = cur.fetchall()

                for (
                    chunk_id,
                    chunk_start,
                    chunk_end
                ) in chunk_rows:

                    candidates = []

                    for symbol in symbol_records:

                        symbol_start = (
                            symbol.get("start_line")
                        )

                        symbol_end = (
                            symbol.get("end_line")
                        )

                        if (
                            symbol_start is None
                            or symbol_end is None
                        ):
                            continue

                        overlaps = (
                            symbol_start <= chunk_end
                            and symbol_end >= chunk_start
                        )

                        if not overlaps:
                            continue

                        symbol_size = (
                            symbol_end - symbol_start
                        )

                        candidates.append(
                            (
                                symbol_size,
                                symbol
                            )
                        )

                    if not candidates:
                        continue

                    candidates.sort(
                        key=lambda x: x[0]
                    )

                    primary_symbol = candidates[0][1]

                    cur.execute(
                        """
                        UPDATE app_context_chunks
                        SET primary_symbol_id = %s
                        WHERE context_chunk_id = %s
                        """,
                        (
                            primary_symbol["symbol_id"],
                            chunk_id
                        )
                    )

                # =================================================
                # DEPENDENCIES
                # =================================================

                dependencies = extract_dependencies(
                    file_path,
                    content,
                    language
                )

                for dependency in dependencies or []:

                    # ------------------------------------------------
                    # Support both old extractor format:
                    #
                    #     "foo/bar"
                    #
                    # and richer format:
                    #
                    #     {
                    #         "dependency_name": "...",
                    #         "dependency_type": "...",
                    #         "target_file": "...",
                    #         "source_symbol": "...",
                    #         "target_symbol": "..."
                    #     }
                    # ------------------------------------------------

                    if isinstance(
                        dependency,
                        str
                    ):

                        dependency_name = dependency
                        dependency_type = "import"
                        target_path = None
                        source_symbol_name = None
                        target_symbol_name = None

                    elif isinstance(
                        dependency,
                        dict
                    ):

                        dependency_name = (
                            dependency.get(
                                "dependency_name"
                            )
                            or dependency.get(
                                "name"
                            )
                            or dependency.get(
                                "target"
                            )
                        )

                        dependency_type = (
                            dependency.get(
                                "dependency_type"
                            )
                            or dependency.get(
                                "type"
                            )
                            or "import"
                        )

                        target_path = (
                            dependency.get(
                                "target_file"
                            )
                            or dependency.get(
                                "target_path"
                            )
                            or dependency.get(
                                "file"
                            )
                        )

                        source_symbol_name = (
                            dependency.get(
                                "source_symbol"
                            )
                        )

                        target_symbol_name = (
                            dependency.get(
                                "target_symbol"
                            )
                        )

                    else:
                        continue

                    if not dependency_name:
                        continue

                    # =================================================
                    # RESOLVE TARGET FILE
                    # =================================================

                    target_file_id = None

                    if target_path:

                        target_path = str(
                            target_path
                        ).replace("\\", "/")

                        # Direct relative path
                        if target_path in file_id_by_relative_path:

                            target_file_id = (
                                file_id_by_relative_path[
                                    target_path
                                ]
                            )

                        else:

                            # Try normalized ./ prefix
                            normalized_target = (
                                target_path
                                .lstrip("./")
                            )

                            target_file_id = (
                                file_id_by_relative_path.get(
                                    normalized_target
                                )
                            )

                    # ------------------------------------------------
                    # If extractor didn't give us a target path,
                    # attempt a lightweight resolution using the
                    # dependency name.
                    # ------------------------------------------------

                    if target_file_id is None:

                        dependency_normalized = (
                            str(dependency_name)
                            .replace("\\", "/")
                            .strip()
                        )

                        dependency_candidates = []

                        for (
                            candidate_path,
                            candidate_id
                        ) in file_id_by_relative_path.items():

                            candidate_no_ext = (
                                candidate_path
                            )

                            # Exact path match
                            if (
                                candidate_path
                                == dependency_normalized
                            ):
                                dependency_candidates.append(
                                    candidate_id
                                )
                                continue

                            # Remove extension
                            candidate_stem = (
                                candidate_path
                            )

                            for ext in (
                                ".py",
                                ".ts",
                                ".tsx",
                                ".js",
                                ".jsx",
                                ".java",
                                ".cs",
                                ".go",
                                ".rs",
                                ".cpp",
                                ".c"
                            ):
                                if candidate_stem.endswith(ext):
                                    candidate_stem = (
                                        candidate_stem[
                                            :-len(ext)
                                        ]
                                    )
                                    break

                            normalized_candidate = (
                                candidate_stem
                                .replace("\\", "/")
                            )

                            if (
                                normalized_candidate
                                == dependency_normalized
                            ):
                                dependency_candidates.append(
                                    candidate_id
                                )

                            elif (
                                normalized_candidate.endswith(
                                    "/" + dependency_normalized
                                )
                            ):
                                dependency_candidates.append(
                                    candidate_id
                                )

                        if len(
                            dependency_candidates
                        ) == 1:

                            target_file_id = (
                                dependency_candidates[0]
                            )

                    # =================================================
                    # RESOLVE SOURCE SYMBOL
                    # =================================================

                    source_symbol_id = None

                    if source_symbol_name:

                        source_symbol_name = str(
                            source_symbol_name
                        )

                        source_symbol = (
                            symbol_by_qualified_name.get(
                                source_symbol_name
                            )
                        )

                        if source_symbol is None:

                            candidates = (
                                symbol_by_name.get(
                                    source_symbol_name,
                                    []
                                )
                            )

                            if len(candidates) == 1:
                                source_symbol = (
                                    candidates[0]
                                )

                        if source_symbol:
                            source_symbol_id = (
                                source_symbol["symbol_id"]
                            )

                    # =================================================
                    # TARGET SYMBOL
                    #
                    # If target file is known, target symbol cannot
                    # necessarily be resolved until all project files
                    # have been processed.
                    #
                    # We therefore store the dependency edge now.
                    # A later graph-resolution pass can populate
                    # target_symbol_id.
                    # =================================================

                    target_symbol_id = None

                    if (
                        target_symbol_name
                        and target_file_id
                    ):

                        cur.execute(
                            """
                            SELECT
                                symbol_id
                            FROM app_context_symbols
                            WHERE
                                context_file_id = %s
                                AND (
                                    symbol_name = %s
                                    OR qualified_name = %s
                                )
                            LIMIT 1
                            """,
                            (
                                target_file_id,
                                target_symbol_name,
                                target_symbol_name
                            )
                        )

                        target_symbol_row = (
                            cur.fetchone()
                        )

                        if target_symbol_row:
                            target_symbol_id = (
                                target_symbol_row[0]
                            )

                    # =================================================
                    # INSERT GRAPH EDGE
                    # =================================================

                    cur.execute(
                        """
                        INSERT INTO app_context_dependencies
                        (
                            context_project_id,
                            source_file_id,
                            target_file_id,
                            source_symbol_id,
                            target_symbol_id,
                            dependency_name,
                            dependency_type
                        )
                        VALUES
                        (
                            %s,%s,%s,%s,%s,%s,%s
                        )
                        """,
                        (
                            project_id,
                            file_id,
                            target_file_id,
                            source_symbol_id,
                            target_symbol_id,
                            str(dependency_name),
                            str(dependency_type)
                        )
                    )

            # ========================================================
            # MARK REMOVED FILES
            # ========================================================

            current_paths = set(
                current_file_map.keys()
            )

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

            for (
                existing_file_id,
                existing_relative_path
            ) in existing_files:

                normalized_path = (
                    str(existing_relative_path)
                    .replace("\\", "/")
                )

                if normalized_path not in current_paths:

                    # --------------------------------------------
                    # Mark file inactive
                    # --------------------------------------------

                    cur.execute(
                        """
                        UPDATE app_context_files
                        SET
                            is_active = FALSE,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE context_file_id = %s
                        """,
                        (existing_file_id,)
                    )

                    # --------------------------------------------
                    # Remove graph edges involving removed file
                    # --------------------------------------------

                    cur.execute(
                        """
                        DELETE FROM app_context_dependencies
                        WHERE
                            source_file_id = %s
                            OR target_file_id = %s
                        """,
                        (
                            existing_file_id,
                            existing_file_id
                        )
                    )

            # ========================================================
            # SECOND PASS:
            #
            # Resolve unresolved target symbols.
            #
            # This matters when:
            #
            #     A.ts
            #       references B.foo
            #
            # but B.ts was processed after A.ts.
            # ========================================================

            cur.execute(
                """
                SELECT
                    d.dependency_id,
                    d.target_file_id,
                    d.dependency_name
                FROM app_context_dependencies d
                WHERE
                    d.context_project_id = %s
                    AND d.target_file_id IS NOT NULL
                    AND d.target_symbol_id IS NULL
                """,
                (project_id,)
            )

            unresolved_dependencies = (
                cur.fetchall()
            )

            for (
                dependency_id,
                target_file_id,
                dependency_name
            ) in unresolved_dependencies:

                if not dependency_name:
                    continue

                dependency_name = str(
                    dependency_name
                )

                # --------------------------------------------
                # Try exact symbol name
                # --------------------------------------------

                cur.execute(
                    """
                    SELECT
                        symbol_id
                    FROM app_context_symbols
                    WHERE
                        context_file_id = %s
                        AND (
                            symbol_name = %s
                            OR qualified_name = %s
                        )
                    ORDER BY
                        CASE
                            WHEN symbol_name = %s
                            THEN 0
                            ELSE 1
                        END
                    LIMIT 1
                    """,
                    (
                        target_file_id,
                        dependency_name,
                        dependency_name,
                        dependency_name
                    )
                )

                target_symbol_row = (
                    cur.fetchone()
                )

                if target_symbol_row:

                    cur.execute(
                        """
                        UPDATE app_context_dependencies
                        SET target_symbol_id = %s
                        WHERE dependency_id = %s
                        """,
                        (
                            target_symbol_row[0],
                            dependency_id
                        )
                    )

            # ========================================================
            # SNAPSHOT
            # ========================================================

            # cur.execute(
            #     """
            #     SELECT COUNT(*)
            #     FROM app_context_files
            #     WHERE
            #         context_project_id = %s
            #         AND is_active = TRUE
            #     """,
            #     (project_id,)
            # )

            # active_file_count = (
            #     cur.fetchone()[0]
            # )

            # Snapshot hash based on active file hashes.
            cur.execute(
                """
                SELECT
                    COALESCE(
                        string_agg(
                            content_hash,
                            '' ORDER BY relative_path
                        ),
                        ''
                    )
                FROM app_context_files
                WHERE
                    context_project_id = %s
                    AND is_active = TRUE
                """,
                (project_id,)
            )

            # snapshot_input = (
            #     cur.fetchone()[0]
            #     or ""
            # )

            # snapshot_hash = sha256_text(
            #     snapshot_input
            # )

            # cur.execute(
            #     """
            #     INSERT INTO app_context_snapshots
            #     (
            #         context_project_id,
            #         snapshot_hash,
            #         file_count
            #     )
            #     VALUES
            #     (
            #         %s,%s,%s
            #     )
            #     """,
            #     (
            #         project_id,
            #         snapshot_hash,
            #         active_file_count
            #     )
            # )

        conn.commit()

        return project_id

    except Exception:
        conn.rollback()
        raise

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

                # "all_existing_paths": sorted(
                #     existing_paths
                # ),
            }

    finally:
        conn.close()

# ============================================================
# GET RELEVANT CODE GRAPH
# ============================================================

def get_code_graph_context(
    requirement: str,
    project_id: int,
    max_files: int = 20,
    max_symbols: int = 40,
    max_chunks: int = 30,
    graph_depth: int = 2,
):
    """
    Retrieve repository context using the code graph.

    Retrieval priority:

        requirement
            ↓
        file/symbol candidates
            ↓
        dependency graph expansion
            ↓
        related files/symbols
            ↓
        source chunks

    Chunks are evidence, not the primary retrieval mechanism.
    """

    import re

    conn = psycopg2.connect(DATABASE_URL)

    try:
        cur = conn.cursor()

        # ---------------------------------------------------------
        # 1. Normalize requirement
        # ---------------------------------------------------------

        requirement_text = (
            requirement or ""
        ).strip()

        tokens = set(
            re.findall(
                r"[A-Za-z_][A-Za-z0-9_.-]{2,}",
                requirement_text.lower(),
            )
        )

        # Remove generic software words.
        stop_words = {
            "add",
            "change",
            "create",
            "update",
            "modify",
            "implement",
            "make",
            "allow",
            "should",
            "need",
            "needs",
            "using",
            "with",
            "from",
            "into",
            "this",
            "that",
            "feature",
            "support",
            "system",
            "application",
            "page",
            "screen",
        }

        tokens -= stop_words

        if not tokens:
            tokens = {
                word
                for word in requirement_text.lower().split()
                if len(word) >= 3
            }

        # ---------------------------------------------------------
        # 2. Find candidate files
        # ---------------------------------------------------------

        cur.execute(
            """
            SELECT
                context_file_id,
                relative_path,
                file_name,
                language,
                file_type
            FROM app_context_files
            WHERE context_project_id = %s
              AND is_active = TRUE
            """,
            (project_id,),
        )

        file_rows = cur.fetchall()

        file_candidates = []

        for row in file_rows:

            (
                file_id,
                relative_path,
                file_name,
                language,
                file_type,
            ) = row

            path_text = (
                f"{relative_path} {file_name}"
            ).lower()

            score = 0

            for token in tokens:

                if token in path_text:
                    score += 10

                # Handle camelCase/PascalCase style names.
                compact = token.replace(
                    "_",
                    ""
                ).replace(
                    "-",
                    ""
                )

                if compact and compact in path_text.replace(
                    "_",
                    ""
                ).replace(
                    "-",
                    ""
                ):
                    score += 4

            if score > 0:

                file_candidates.append(
                    (
                        file_id,
                        relative_path,
                        language,
                        file_type,
                        score,
                    )
                )

        file_candidates.sort(
            key=lambda x: x[4],
            reverse=True,
        )

        seed_file_ids = [
            row[0]
            for row in file_candidates[:max_files]
        ]

        # ---------------------------------------------------------
        # 3. Find symbols matching requirement
        # ---------------------------------------------------------

        cur.execute(
            """
            SELECT
                s.symbol_id,
                s.context_file_id,
                s.symbol_name,
                s.symbol_type,
                s.qualified_name,
                s.signature,
                s.start_line,
                s.end_line,
                f.relative_path
            FROM app_context_symbols s
            JOIN app_context_files f
              ON f.context_file_id = s.context_file_id
            WHERE f.context_project_id = %s
              AND f.is_active = TRUE
            """,
            (project_id,),
        )

        symbol_rows = cur.fetchall()

        symbol_candidates = []

        for row in symbol_rows:

            (
                symbol_id,
                file_id,
                symbol_name,
                symbol_type,
                qualified_name,
                signature,
                start_line,
                end_line,
                relative_path,
            ) = row

            searchable = " ".join(
                filter(
                    None,
                    [
                        symbol_name,
                        qualified_name,
                        signature,
                        relative_path,
                    ],
                )
            ).lower()

            score = 0

            for token in tokens:

                if token in searchable:
                    score += 12

                if token in (
                    symbol_name or ""
                ).lower():
                    score += 15

                if token in (
                    qualified_name or ""
                ).lower():
                    score += 15

            if score > 0:

                symbol_candidates.append(
                    {
                        "symbol_id": symbol_id,
                        "file_id": file_id,
                        "symbol_name": symbol_name,
                        "symbol_type": symbol_type,
                        "qualified_name": qualified_name,
                        "signature": signature,
                        "start_line": start_line,
                        "end_line": end_line,
                        "file": relative_path,
                        "score": score,
                    }
                )

        symbol_candidates.sort(
            key=lambda x: x["score"],
            reverse=True,
        )

        seed_symbol_ids = {
            item["symbol_id"]
            for item in symbol_candidates[
                :max_symbols
            ]
        }

        # Seed files from symbols.
        seed_file_ids.extend(
            item["file_id"]
            for item in symbol_candidates[
                :max_symbols
            ]
        )

        # ---------------------------------------------------------
        # 4. Graph expansion
        # ---------------------------------------------------------

        visited_files = set(
            seed_file_ids
        )

        visited_symbols = set(
            seed_symbol_ids
        )

        frontier_files = set(
            seed_file_ids
        )

        frontier_symbols = set(
            seed_symbol_ids
        )

        graph_edges = []

        for _ in range(graph_depth):

            if not frontier_files and not frontier_symbols:
                break

            # ---------------------------------------------
            # File-level edges
            # ---------------------------------------------

            if frontier_files:

                cur.execute(
                    """
                    SELECT
                        dependency_id,
                        source_file_id,
                        target_file_id,
                        dependency_type,
                        dependency_name,
                        source_symbol_id,
                        target_symbol_id
                    FROM app_context_dependencies
                    WHERE source_file_id = ANY(%s)
                       OR target_file_id = ANY(%s)
                    """,
                    (
                        list(frontier_files),
                        list(frontier_files),
                    ),
                )

                rows = cur.fetchall()

            else:
                rows = []

            next_files = set()
            next_symbols = set()

            for row in rows:

                (
                    dependency_id,
                    source_file_id,
                    target_file_id,
                    dependency_type,
                    dependency_name,
                    source_symbol_id,
                    target_symbol_id,
                ) = row

                graph_edges.append(
                    {
                        "dependency_id": dependency_id,
                        "source_file_id": source_file_id,
                        "target_file_id": target_file_id,
                        "dependency_type": dependency_type,
                        "dependency_name": dependency_name,
                        "source_symbol_id": source_symbol_id,
                        "target_symbol_id": target_symbol_id,
                    }
                )

                if source_file_id not in visited_files:
                    next_files.add(
                        source_file_id
                    )

                if target_file_id not in visited_files:
                    next_files.add(
                        target_file_id
                    )

                if source_symbol_id:
                    if source_symbol_id not in visited_symbols:
                        next_symbols.add(
                            source_symbol_id
                        )

                if target_symbol_id:
                    if target_symbol_id not in visited_symbols:
                        next_symbols.add(
                            target_symbol_id
                        )

            visited_files.update(
                next_files
            )

            visited_symbols.update(
                next_symbols
            )

            frontier_files = next_files
            frontier_symbols = next_symbols

            if len(visited_files) > max_files:
                break

        # ---------------------------------------------------------
        # 5. Fetch selected files
        # ---------------------------------------------------------

        selected_file_ids = list(
            visited_files
        )[:max_files]

        if selected_file_ids:

            cur.execute(
                """
                SELECT
                    context_file_id,
                    relative_path,
                    file_name,
                    language,
                    file_type,
                    size_bytes
                FROM app_context_files
                WHERE context_file_id = ANY(%s)
                """,
                (selected_file_ids,),
            )

            selected_files = []

            for row in cur.fetchall():

                (
                    file_id,
                    relative_path,
                    file_name,
                    language,
                    file_type,
                    size_bytes,
                ) = row

                selected_files.append(
                    {
                        "context_file_id": file_id,
                        "path": relative_path,
                        "file_name": file_name,
                        "language": language,
                        "file_type": file_type,
                        "size_bytes": size_bytes,
                    }
                )

        else:

            selected_files = []

        # ---------------------------------------------------------
        # 6. Fetch selected symbols
        # ---------------------------------------------------------

        selected_symbols = []

        if visited_symbols:

            cur.execute(
                """
                SELECT
                    s.symbol_id,
                    s.context_file_id,
                    s.symbol_name,
                    s.symbol_type,
                    s.qualified_name,
                    s.signature,
                    s.start_line,
                    s.end_line,
                    f.relative_path
                FROM app_context_symbols s
                JOIN app_context_files f
                  ON f.context_file_id = s.context_file_id
                WHERE s.symbol_id = ANY(%s)
                """,
                (list(visited_symbols),),
            )

            for row in cur.fetchall():

                (
                    symbol_id,
                    file_id,
                    symbol_name,
                    symbol_type,
                    qualified_name,
                    signature,
                    start_line,
                    end_line,
                    relative_path,
                ) = row

                selected_symbols.append(
                    {
                        "symbol_id": symbol_id,
                        "context_file_id": file_id,
                        "symbol_name": symbol_name,
                        "symbol_type": symbol_type,
                        "qualified_name": qualified_name,
                        "signature": signature,
                        "start_line": start_line,
                        "end_line": end_line,
                        "file": relative_path,
                    }
                )

        # ---------------------------------------------------------
        # 7. Fetch chunks ONLY from selected files
        # ---------------------------------------------------------

        chunks = []

        if selected_file_ids:

            cur.execute(
                """
                SELECT
                    c.context_chunk_id,
                    c.context_file_id,
                    c.chunk_index,
                    c.start_line,
                    c.end_line,
                    c.content,
                    f.relative_path
                FROM app_context_chunks c
                JOIN app_context_files f
                  ON f.context_file_id = c.context_file_id
                WHERE c.context_file_id = ANY(%s)
                ORDER BY
                    c.context_file_id,
                    c.chunk_index
                """,
                (selected_file_ids,),
            )

            for row in cur.fetchall():

                (
                    chunk_id,
                    file_id,
                    chunk_index,
                    start_line,
                    end_line,
                    content,
                    relative_path,
                ) = row

                chunks.append(
                    {
                        "context_chunk_id": chunk_id,
                        "context_file_id": file_id,
                        "chunk_index": chunk_index,
                        "start_line": start_line,
                        "end_line": end_line,
                        "file": relative_path,
                        "content": content,
                    }
                )

                if len(chunks) >= max_chunks:
                    break

        # ---------------------------------------------------------
        # 8. Build graph representation
        # ---------------------------------------------------------

        return {
            "project_id": project_id,
            "requirement": requirement_text,

            "seed": {
                "tokens": sorted(tokens),
                "files": seed_file_ids,
                "symbols": list(seed_symbol_ids),
            },

            "existing_files": selected_files,

            "symbols": selected_symbols,

            "dependencies": graph_edges,

            "relevant_chunks": chunks,

            "retrieval": {
                "strategy": "code_graph",
                "graph_depth": graph_depth,
                "max_files": max_files,
                "max_symbols": max_symbols,
                "max_chunks": max_chunks,
            },
        }

    finally:
        conn.close()


def format_code_graph_context(
    graph_context: dict,
    max_chars: int = 18000,
) -> str:
    """
    Convert code graph retrieval results into compact
    LLM-readable repository context.
    """

    parts = []

    parts.append(
        "CODE GRAPH CONTEXT"
    )

    parts.append(
        f"Requirement:\n"
        f"{graph_context.get('requirement', '')}"
    )

    # ---------------------------------------------------------
    # Files
    # ---------------------------------------------------------

    parts.append(
        "\nRELEVANT FILES"
    )

    for file_info in graph_context.get(
        "existing_files",
        []
    ):

        parts.append(
            "- "
            + file_info["path"]
            + f" [{file_info.get('language', '')}]"
        )

    # ---------------------------------------------------------
    # Symbols
    # ---------------------------------------------------------

    parts.append(
        "\nRELEVANT SYMBOLS"
    )

    for symbol in graph_context.get(
        "symbols",
        []
    ):

        name = (
            symbol.get("qualified_name")
            or symbol.get("symbol_name")
        )

        location = (
            f'{symbol.get("file")}:'
            f'{symbol.get("start_line")}-'
            f'{symbol.get("end_line")}'
        )

        signature = (
            symbol.get("signature")
            or ""
        )

        parts.append(
            f"- {name} "
            f"[{symbol.get('symbol_type', '')}] "
            f"({location}) "
            f"{signature}"
        )

    # ---------------------------------------------------------
    # Dependencies
    # ---------------------------------------------------------

    parts.append(
        "\nCODE RELATIONSHIPS"
    )

    for edge in graph_context.get(
        "dependencies",
        []
    ):

        dependency_type = (
            edge.get("dependency_type")
            or "depends_on"
        )

        dependency_name = (
            edge.get("dependency_name")
            or ""
        )

        parts.append(
            f"- "
            f"{edge.get('source_file_id')}"
            f" --[{dependency_type}]--> "
            f"{edge.get('target_file_id')}"
            f" {dependency_name}"
        )

    # ---------------------------------------------------------
    # Source evidence
    # ---------------------------------------------------------

    parts.append(
        "\nSOURCE EVIDENCE"
    )

    for chunk in graph_context.get(
        "relevant_chunks",
        []
    ):

        block = (
            f'\nFILE: {chunk["file"]}\n'
            f'LINES: {chunk["start_line"]}-'
            f'{chunk["end_line"]}\n'
            f'{chunk["content"]}\n'
        )

        parts.append(block)

        current = "\n".join(parts)

        if len(current) >= max_chars:
            break

    result = "\n".join(parts)

    return result[:max_chars]

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

    # stack = context[
    #     "project"
    # ]["stack"]

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

    prompt = f"""
USER REQUIREMENT
================

{requirement}


REPOSITORY CONTEXT
==================

{json.dumps(context, indent=2)}


YOUR TASK
=========

Create the ordered implementation task checklist.

Remember:

You are the SUPERVISOR.

Do NOT implement anything.

Return in the following format:

{{
  "task_checklist": [
    {{
      "step_id": 1,
      "domain": "string",
      "description": "string",
      "files_affected": [
        {{
          "path": "string",
          "change_type": "edit"
        }}
      ]
    }}
  ]
}}
"""

    return prompt

def build_supervisor_prompt_from_code_graph(
    requirement: str,
    context_text: str,
) -> str:
    """
    Build the Supervisor prompt using code-graph context.
    """

    return f"""
USER REQUIREMENT
================

{requirement}


REPOSITORY CODE GRAPH
=====================

{context_text}


SUPERVISOR OBJECTIVE
====================

Convert the user's requirement into an ordered implementation
task checklist.

You are NOT implementing the requirement.

You must determine:

1. Which existing files are relevant.
2. Which existing files should be edited.
3. Which files genuinely need to be created.
4. Which tasks depend on other tasks.
5. The smallest set of files required to implement the feature.

Use the repository code graph as the primary source of truth.

Do not invent files that are not supported by the repository context.

Return ONLY the required JSON object.
"""


def build_supervisor_prompt_code_graph(
    requirement: str,
    context: dict,
    context_text: str,
    ui_graph_text: str,
) -> str:
    """
    Build the Supervisor prompt using:

        1. User requirement
        2. Code graph retrieval
        3. UI/component graph
        4. Source evidence

    The UI graph is treated as structural evidence for deciding
    which files/components are actually affected.
    """

    return f"""
USER REQUIREMENT
================

{requirement}


============================================================
REPOSITORY CODE GRAPH
============================================================

{context_text}


============================================================
UI COMPONENT GRAPH
============================================================

The following graph represents the discovered UI/component
structure of the repository.

Use this graph to understand:

- which pages contain which components
- which components contain child components
- which UI elements belong to which component
- which handlers belong to UI components
- which state is associated with UI elements
- which symbols call other symbols
- which UI components eventually reach APIs or services

{ui_graph_text}


============================================================
SUPERVISOR ANALYSIS RULE
============================================================

The retrieved repository context may contain files that are
semantically similar to the requirement but are NOT actually
affected by it.

Do NOT assume that every retrieved file is relevant.

The UI COMPONENT GRAPH is structural evidence.

Use the following priority when deciding whether a file is
actually affected:

1. Direct UI component relationship
2. Parent/child UI relationship
3. Event handler relationship
4. State relationship
5. Call/dependency relationship
6. API/service relationship
7. File-level dependency
8. Semantic similarity alone

Semantic similarity alone is NOT sufficient to mark a file
as affected.

A retrieved file that merely contains similar words, similar
components, or a similar feature must be excluded unless
there is a graph relationship connecting it to the requested
change.


============================================================
RELEVANCE / FILE SELECTION
============================================================

For every candidate file from the repository context, determine:

A. Is it structurally connected to the requested UI/component?

B. Is it part of the parent/child component hierarchy?

C. Does it contain a handler/state/API path affected by the
   requirement?

D. Is it required to propagate the requested change?

E. Is it merely semantically similar?

If E is true and A-D are false:

    EXCLUDE THE FILE.

Do not include irrelevant retrieved files merely because they
appear in the context.


============================================================
UI REQUIREMENT INTERPRETATION
============================================================

When the requirement describes a UI change, identify the
smallest structural path:

    PAGE
      ↓
    SECTION
      ↓
    COMPONENT
      ↓
    ELEMENT
      ↓
    EVENT / STATE
      ↓
    HANDLER
      ↓
    SERVICE / API

Only include files that participate in this path or are
necessary to implement the requested behavior.


============================================================
RELATIONSHIP VALIDATION
============================================================

When possible, validate every affected file through at least
one explicit graph relationship.

Examples:

Component A
    contains
Component B

Component B
    triggers
Handler C

Handler C
    updates
State D

Handler C
    calls
Service E

Service E
    sends
API F

This is stronger evidence than filename similarity or
semantic relevance.


============================================================
MISSING GRAPH INFORMATION
============================================================

The UI graph may be incomplete.

If the graph does not explicitly establish a relationship,
do NOT invent one.

Use the source evidence and symbol relationships only when
they support the conclusion.

If a candidate file cannot be justified by repository evidence,
exclude it from files_affected.


============================================================
TASK DECOMPOSITION
============================================================

Convert the requirement into the smallest ordered sequence
of implementation tasks.

Tasks must represent coherent implementation steps.

Tasks must be ordered according to dependencies.

For a UI requirement, prefer:

1. state/model change
2. API/service change
3. UI component change
4. event/handler change
5. tests

Only create a task category when the requirement actually
requires it.


============================================================
FILE SELECTION PRINCIPLE
============================================================

Your goal is NOT to list all relevant-looking files.

Your goal is to identify:

    THE SMALLEST SET OF FILES REQUIRED
    TO IMPLEMENT THE REQUIREMENT.

False-positive files are worse than omitted speculative files.

Only include a file when repository evidence supports that
the requirement requires changing it.


============================================================
STRICT OUTPUT CONTRACT
============================================================

Your response MUST be valid JSON.

Your response MUST contain EXACTLY this top-level structure:

{{
  "task_checklist": [
    {{
      "step_id": 1,
      "domain": "string",
      "description": "string",
      "files_affected": [
        {{
          "path": "string",
          "change_type": "edit"
        }}
      ]
    }}
  ]
}}

Required fields:

task_checklist
step_id
domain
description
files_affected
path
change_type

change_type MUST be one of:

"edit"
"create"


============================================================
FILE RULES
============================================================

If a file exists in the repository context:

    change_type = "edit"

If the file does not exist and is genuinely required:

    change_type = "create"

Never invent a file when an existing file can be modified.

Use repository paths exactly as supplied by the context.


============================================================
STRICT PROHIBITIONS
============================================================

DO NOT output:

- source code
- TypeScript
- JavaScript
- Python
- SQL
- Markdown
- explanations
- comments outside JSON
- ``` fences
- technical specifications
- generated code
- complete AgentOrchestratorState

You are the SUPERVISOR.

You are NOT a coder.

You are NOT an architect.

Do NOT implement the requirement.


============================================================
FINAL REQUIREMENT
============================================================

Return JSON ONLY.

The first character of your response MUST be '{{'.

The last character of your response MUST be '}}'.

Return in the following format:

{{
  "task_checklist": [
    {{
      "step_id": 1,
      "domain": "string",
      "description": "string",
      "files_affected": [
        {{
          "path": "string",
          "change_type": "edit"
        }}
      ]
    }}
  ]
}}
"""

def visualize_ui_graph(
    project_id: int,
    root_component: str | None = None,
    max_depth: int = 5,
    output: str = "terminal"
):
    """
    Visualize the UI/component portion of the code graph.

    This is a terminal-first diagnostic tool intended to validate
    whether the indexed code graph correctly represents:

        FILE
          └── COMPONENT
                ├── child COMPONENT
                ├── child ELEMENT
                ├── STATE
                ├── HANDLER
                └── API / dependency

    The function does NOT modify the database.

    Parameters
    ----------
    project_id:
        app_context_projects.context_project_id

    root_component:
        Optional component name / qualified name.

        Examples:
            "ExperioOverview"
            "OverviewSettings"
            "src/components/OverviewSettings.tsx"

        If omitted, all detected UI roots are displayed.

    max_depth:
        Maximum hierarchy depth to display.

    Returns
    -------
    str
        Terminal-friendly graph representation.
    """

    conn = get_connection()

    try:
        with conn.cursor() as cur:

            # ========================================================
            # 1. LOAD UI-RELEVANT SYMBOLS
            # ========================================================

            cur.execute(
                """
                SELECT
                    s.symbol_id,
                    s.context_file_id,
                    s.symbol_name,
                    s.symbol_type,
                    s.qualified_name,
                    s.signature,
                    s.start_line,
                    s.end_line,
                    s.parent_symbol_id,
                    f.relative_path,
                    f.language,
                    f.framework
                FROM app_context_symbols s
                JOIN app_context_files f
                  ON f.context_file_id = s.context_file_id
                WHERE
                    f.context_project_id = %s
                    AND f.is_active = TRUE
                ORDER BY
                    f.relative_path,
                    s.start_line,
                    s.symbol_name
                """,
                (project_id,),
            )

            rows = cur.fetchall()

            if not rows:
                return (
                    "\n"
                    "============================================================\n"
                    "UI COMPONENT GRAPH\n"
                    "============================================================\n"
                    "\n"
                    "No symbols found for project.\n"
                )

            # ========================================================
            # 2. BUILD SYMBOL MAP
            # ========================================================

            symbols = {}

            for row in rows:
                (
                    symbol_id,
                    file_id,
                    symbol_name,
                    symbol_type,
                    qualified_name,
                    signature,
                    start_line,
                    end_line,
                    parent_symbol_id,
                    relative_path,
                    language,
                    framework,
                ) = row

                symbols[symbol_id] = {
                    "symbol_id": symbol_id,
                    "file_id": file_id,
                    "name": symbol_name,
                    "type": symbol_type or "unknown",
                    "qualified_name": qualified_name,
                    "signature": signature,
                    "start_line": start_line,
                    "end_line": end_line,
                    "parent_id": parent_symbol_id,
                    "file": relative_path,
                    "language": language,
                    "framework": framework,
                    "children": [],
                }

            # ========================================================
            # 3. BUILD PARENT -> CHILD RELATIONSHIP
            # ========================================================

            for symbol in symbols.values():

                parent_id = symbol["parent_id"]

                if parent_id in symbols:
                    symbols[parent_id]["children"].append(
                        symbol["symbol_id"]
                    )

            # ========================================================
            # 4. LOAD SYMBOL DEPENDENCIES
            # ========================================================

            cur.execute(
                """
                SELECT
                    d.dependency_id,
                    d.source_symbol_id,
                    d.target_symbol_id,
                    d.source_file_id,
                    d.target_file_id,
                    d.dependency_type,
                    d.dependency_name
                FROM app_context_dependencies d
                WHERE
                    d.context_project_id = %s
                    AND (
                        d.source_symbol_id IS NOT NULL
                        OR d.target_symbol_id IS NOT NULL
                    )
                ORDER BY
                    d.source_symbol_id,
                    d.dependency_type,
                    d.dependency_name
                """,
                (project_id,),
            )

            dependency_rows = cur.fetchall()

            relationships = {}

            for (
                dependency_id,
                source_symbol_id,
                target_symbol_id,
                source_file_id,
                target_file_id,
                dependency_type,
                dependency_name,
            ) in dependency_rows:

                if source_symbol_id is None:
                    continue

                relationships.setdefault(
                    source_symbol_id,
                    []
                ).append(
                    {
                        "dependency_id": dependency_id,
                        "target_symbol_id": target_symbol_id,
                        "source_file_id": source_file_id,
                        "target_file_id": target_file_id,
                        "type": dependency_type or "depends_on",
                        "name": dependency_name,
                    }
                )

            # ========================================================
            # 5. IDENTIFY UI SYMBOLS
            # ========================================================

            ui_types = {
                "component",
                "page",
                "screen",
                "view",
                "layout",
                "widget",
                "element",
                "hook",
                "state",
                "handler",
                "event",
                "route",
                "form",
                "modal",
                "dialog",
                "button",
                "input",
                "select",
                "checkbox",
                "toggle",
                "icon",
            }

            def is_ui_symbol(symbol):
                symbol_type = (
                    symbol["type"]
                    .lower()
                    .strip()
                )

                if symbol_type in ui_types:
                    return True

                name = symbol["name"].lower()

                ui_name_patterns = (
                    "component",
                    "page",
                    "screen",
                    "view",
                    "modal",
                    "dialog",
                    "button",
                    "toggle",
                    "input",
                    "form",
                    "layout",
                )

                return any(
                    pattern in name
                    for pattern in ui_name_patterns
                )

            ui_symbols = {
                symbol_id: symbol
                for symbol_id, symbol in symbols.items()
                if is_ui_symbol(symbol)
            }

            # ========================================================
            # 6. FIND ROOT UI COMPONENTS
            # ========================================================

            roots = []

            for symbol_id, symbol in ui_symbols.items():

                parent_id = symbol["parent_id"]

                if (
                    parent_id is None
                    or parent_id not in ui_symbols
                ):
                    roots.append(symbol_id)

            # ========================================================
            # 7. OPTIONAL ROOT FILTER
            # ========================================================

            if root_component:

                root_query = (
                    root_component
                    .replace("\\", "/")
                    .strip()
                    .lower()
                )

                filtered_roots = []

                for symbol_id, symbol in ui_symbols.items():

                    candidates = [
                        symbol["name"],
                        symbol["qualified_name"],
                        symbol["file"],
                    ]

                    matched = any(
                        value
                        and (
                            root_query
                            == str(value).lower()
                            or root_query
                            in str(value).lower()
                        )
                        for value in candidates
                    )

                    if matched:
                        filtered_roots.append(symbol_id)

                roots = filtered_roots

            # ========================================================
            # 8. SORT ROOTS
            # ========================================================

            roots.sort(
                key=lambda symbol_id: (
                    ui_symbols[symbol_id]["file"],
                    ui_symbols[symbol_id]["start_line"] or 0,
                    ui_symbols[symbol_id]["name"],
                )
            )

            # ========================================================
            # 9. RENDER
            # ========================================================

            lines = []

            lines.append("")
            lines.append(
                "============================================================"
            )
            lines.append(
                "UI COMPONENT GRAPH"
            )
            lines.append(
                "============================================================"
            )
            lines.append(
                f"Project ID: {project_id}"
            )

            if root_component:
                lines.append(
                    f"Root filter: {root_component}"
                )

            lines.append(
                f"UI symbols: {len(ui_symbols)}"
            )
            lines.append(
                ""
            )

            visited = set()

            def render_symbol(
                symbol_id,
                depth,
                prefix="",
                is_last=True,
            ):

                if depth > max_depth:
                    return

                symbol = ui_symbols.get(symbol_id)

                if symbol is None:
                    return

                connector = "└── " if is_last else "├── "

                name = symbol["name"]

                symbol_type = symbol["type"]

                lines.append(
                    f"{prefix}"
                    f"{connector}"
                    f"{name}"
                    f" [{symbol_type}]"
                )

                child_prefix = (
                    prefix
                    + (
                        "    "
                        if is_last
                        else "│   "
                    )
                )

                # ----------------------------------------------------
                # SOURCE LOCATION
                # ----------------------------------------------------

                location = (
                    f"{symbol['file']}:"
                    f"{symbol['start_line'] or '?'}"
                    f"-"
                    f"{symbol['end_line'] or '?'}"
                )

                lines.append(
                    f"{child_prefix}"
                    f"    source: {location}"
                )

                # ----------------------------------------------------
                # CHILDREN
                # ----------------------------------------------------

                children = [
                    child_id
                    for child_id in symbol["children"]
                    if child_id in ui_symbols
                ]

                children.sort(
                    key=lambda child_id: (
                        ui_symbols[child_id]["start_line"] or 0,
                        ui_symbols[child_id]["name"],
                    )
                )

                for index, child_id in enumerate(children):

                    render_symbol(
                        child_id,
                        depth + 1,
                        child_prefix,
                        index == len(children) - 1,
                    )

                # ----------------------------------------------------
                # RELATIONSHIPS
                # ----------------------------------------------------

                edges = relationships.get(
                    symbol_id,
                    []
                )

                for edge in edges:

                    target_id = edge["target_symbol_id"]

                    target = symbols.get(target_id)

                    if target:

                        target_name = target["name"]

                    elif edge["name"]:

                        target_name = edge["name"]

                    else:

                        target_name = (
                            f"file:{edge['target_file_id']}"
                        )

                    relation_type = edge["type"]

                    lines.append(
                        f"{child_prefix}"
                        f"    "
                        f"↳ [{relation_type}] "
                        f"{target_name}"
                    )

            # ========================================================
            # 10. RENDER ROOTS
            # ========================================================

            if not roots:

                lines.append(
                    "No UI roots detected."
                )

            else:

                for index, root_id in enumerate(roots):

                    if root_id in visited:
                        continue

                    visited.add(root_id)

                    render_symbol(
                        root_id,
                        depth=0,
                        prefix="",
                        is_last=(
                            index == len(roots) - 1
                        ),
                    )

            # ========================================================
            # 11. RELATIONSHIP SUMMARY
            # ========================================================

            lines.append("")
            lines.append(
                "============================================================"
            )
            lines.append(
                "RELATIONSHIP SUMMARY"
            )
            lines.append(
                "============================================================"
            )

            relation_counts = {}

            for edges in relationships.values():

                for edge in edges:

                    relation_type = edge["type"]

                    relation_counts[
                        relation_type
                    ] = (
                        relation_counts.get(
                            relation_type,
                            0
                        ) + 1
                    )

            for relation_type, count in sorted(
                relation_counts.items()
            ):

                lines.append(
                    f"{relation_type:<25} {count}"
                )

            # ========================================================
            # 12. COMPONENT -> FILE SUMMARY
            # ========================================================

            lines.append("")
            lines.append(
                "============================================================"
            )
            lines.append(
                "UI COMPONENTS BY FILE"
            )
            lines.append(
                "============================================================"
            )

            file_components = {}

            for symbol in ui_symbols.values():

                file_components.setdefault(
                    symbol["file"],
                    []
                ).append(symbol)

            for file_path in sorted(
                file_components
            ):

                lines.append("")
                lines.append(
                    f"{file_path}"
                )

                components = sorted(
                    file_components[file_path],
                    key=lambda item: (
                        item["start_line"] or 0,
                        item["name"],
                    ),
                )

                for component in components:

                    lines.append(
                        f"  "
                        f"- {component['name']} "
                        f"[{component['type']}] "
                        f""
                        f"{component['start_line'] or '?'}"
                        f"-"
                        f"{component['end_line'] or '?'}"
                    )

            # ========================================================
            # 13. RETURN / PRINT
            # ========================================================

            output_text = "\n".join(lines)

            if output == "terminal":
                print(output_text)

            return output_text

    finally:
        conn.close()



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