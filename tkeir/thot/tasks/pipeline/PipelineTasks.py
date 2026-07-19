"""Pipeline task ordering and dependency resolution."""

from __future__ import annotations

TASK_ORDER = [
    "converter",
    "tokenizer",
    "morphosyntax",
    "ner",
    "syntax",
    "keywords",
    "chunking",
    "ontology",
    "chunk-questions",
]

NLP_TASKS = frozenset(TASK_ORDER[1:])

TASK_DEPENDENCIES: dict[str, list[str]] = {
    "converter": [],
    "tokenizer": ["converter"],
    "morphosyntax": ["tokenizer"],
    "ner": ["morphosyntax"],
    "syntax": ["morphosyntax", "ner"],
    "keywords": ["morphosyntax"],
    "chunking": ["syntax", "ner", "morphosyntax"],
    "ontology": ["chunking", "syntax", "ner"],
    "chunk-questions": ["ontology", "chunking"],
}

TASK_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "converter": ("content",),
    "tokenizer": ("content_tokens",),
    "morphosyntax": ("content_morphosyntax",),
    "ner": ("content_ner",),
    "syntax": ("content_deps",),
    "keywords": ("keywords",),
    "chunking": ("golden_chunks",),
    "ontology": ("document_ontology",),
    "chunk-questions": ("chunk_questions_ready",),
}


def parse_tasks(tasks_arg: str | None) -> list[str] | None:
    """Parse a comma-separated task list from the CLI.

    Args:
        tasks_arg: Comma-separated task names, or ``None``.

    Returns:
        Parsed task list, or ``None`` when empty.

    Example:
        >>> parse_tasks("tokenizer,ner")
        ['tokenizer', 'ner']
    """
    if not tasks_arg:
        return None
    requested = [part.strip() for part in tasks_arg.split(",") if part.strip()]
    if not requested:
        return None
    return requested


def validate_tasks(tasks: list[str]) -> None:
    """Validate that requested tasks exist in the pipeline.

    Args:
        tasks: Task names to validate.

    Raises:
        ValueError: If any task name is unknown.

    Example:
        >>> validate_tasks(["tokenizer"])
    """
    unknown = sorted(set(tasks) - set(TASK_ORDER))
    if unknown:
        raise ValueError(
            "Unknown pipeline task(s): "
            + ", ".join(unknown)
            + ". Available: "
            + ", ".join(TASK_ORDER)
        )


def expand_tasks(
    requested: list[str] | None,
    skip_converter: bool = False,
) -> list[str]:
    """Return tasks to run in pipeline order, including dependencies.

    Args:
        requested: Explicit task subset, or ``None`` for the full pipeline.
        skip_converter: When ``True``, omit the converter step.

    Returns:
        Ordered task names with dependencies expanded.

    Example:
        >>> expand_tasks(["keywords"])[:3]
        ['converter', 'tokenizer', 'morphosyntax']
    """
    if requested is None:
        tasks = list(TASK_ORDER)
    else:
        validate_tasks(requested)
        expanded: set[str] = set()

        def add_with_dependencies(task: str) -> None:
            for dependency in TASK_DEPENDENCIES.get(task, []):
                if dependency == "converter" and skip_converter:
                    continue
                add_with_dependencies(dependency)
            expanded.add(task)

        for task in requested:
            add_with_dependencies(task)
        tasks = [task for task in TASK_ORDER if task in expanded]

    if skip_converter:
        tasks = [task for task in tasks if task != "converter"]
    return tasks


def task_output_present(document: dict, task: str) -> bool:
    """Return True when the document already contains this task output.

    Args:
        document: Pipeline JSON document.
        task: Pipeline task name.

    Returns:
        ``True`` when all output fields for the task are present.

    Example:
        >>> task_output_present({"content_tokens": []}, "tokenizer")
        True
    """
    fields = TASK_OUTPUT_FIELDS.get(task, ())
    return bool(fields) and all(field in document for field in fields)


def needs_language_setup(tasks: list[str]) -> bool:
    """Return whether NLP tasks require language/resource setup.

    Args:
        tasks: Pipeline tasks scheduled to run.

    Returns:
        ``True`` when any NLP task is included.

    Example:
        >>> needs_language_setup(["tokenizer", "converter"])
        True
    """
    return bool(set(tasks) & NLP_TASKS)
