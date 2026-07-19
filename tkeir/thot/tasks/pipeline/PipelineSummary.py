"""Aggregate pipeline output statistics for result documents."""

from __future__ import annotations


def _count_token_nodes(tokens) -> int:
    """Count tokenizer nodes in nested token lists.

    Args:
        tokens: ``title_tokens`` or ``content_tokens`` structure.

    Returns:
        Number of token dicts found.

    Example:
        >>> _count_token_nodes([{"token": "Hi", "start_sentence": True}])
        1
    """
    if not isinstance(tokens, list):
        return 0
    if not tokens:
        return 0
    first = tokens[0]
    if isinstance(first, dict) and "token" in first:
        return len(tokens)
    return sum(_count_token_nodes(item) for item in tokens)


def count_document_tokens(document: dict) -> dict:
    """Count tokenizer output tokens when present.

    Args:
        document: Pipeline JSON document.

    Returns:
        Dict with title, content, and total token counts.

    Example:
        >>> count_document_tokens({"title_tokens": [], "content_tokens": []})
        {'title-token-count': 0, 'content-token-count': 0, 'token-count': 0}
    """
    title_count = _count_token_nodes(document.get("title_tokens"))
    content_count = _count_token_nodes(document.get("content_tokens"))
    return {
        "title-token-count": title_count,
        "content-token-count": content_count,
        "token-count": title_count + content_count,
    }


def annotate_pipeline_summary(
    document: dict,
    call_context: dict | None,
    step_timings: dict[str, float],
) -> dict:
    """Add file, token, conversion, and timing metadata to a pipeline result.

    Args:
        document: Pipeline JSON document to annotate in place.
        call_context: Optional call metadata (file size, input path).
        step_timings: Per-task elapsed seconds.

    Returns:
        The same document with summary fields added.

    Example:
        >>> doc = {"content": ["x"], "conversion-info": {"source-size-bytes": 10}}
        >>> annotate_pipeline_summary(doc, None, {"converter": 1.0})["token-count"]
        0
    """
    token_counts = count_document_tokens(document)
    document["title-token-count"] = token_counts["title-token-count"]
    document["content-token-count"] = token_counts["content-token-count"]
    document["token-count"] = token_counts["token-count"]

    conversion_info = document.get("conversion-info")
    if call_context and call_context.get("source-file-size-bytes") is not None:
        document["source-file-size-bytes"] = int(
            call_context["source-file-size-bytes"]
        )
    elif (
        isinstance(conversion_info, dict)
        and conversion_info.get("source-size-bytes") is not None
    ):
        document["source-file-size-bytes"] = int(
            conversion_info["source-size-bytes"]
        )

    if isinstance(conversion_info, dict):
        image_extraction = conversion_info.get("image-extraction")
        if isinstance(image_extraction, dict):
            document["image-extraction"] = image_extraction

    total_elapsed = round(sum(step_timings.values()), 3)
    document["pipeline-timing"] = {
        "elapsed-seconds": total_elapsed,
        "tasks": {
            task: round(elapsed, 3) for task, elapsed in step_timings.items()
        },
    }
    return document
