"""Helpers for extracting structured content from LLM responses."""


def extract_fenced_block(response: str, language: str | None = None) -> str:
    """Extract a Markdown fenced block, tolerating missing closing fences.

    Some models return long code/JSON blocks that are truncated before the final
    ``` marker. In that case we return everything after the opening fence so the
    caller can still save/debug/compile the partial output instead of crashing.
    """
    if not response:
        return ""

    if language:
        marker = f"```{language}"
        start = response.find(marker)
        if start != -1:
            content_start = start + len(marker)
            if content_start < len(response) and response[content_start] == "\n":
                content_start += 1
            end = response.find("```", content_start)
            if end == -1:
                return response[content_start:].strip()
            return response[content_start:end].strip()

    start = response.find("```")
    if start != -1:
        content_start = start + 3
        line_end = response.find("\n", content_start)
        if line_end != -1:
            language_hint = response[content_start:line_end].strip()
            if language_hint and " " not in language_hint:
                content_start = line_end + 1
        end = response.find("```", content_start)
        if end == -1:
            return response[content_start:].strip()
        return response[content_start:end].strip()

    return response.strip()
