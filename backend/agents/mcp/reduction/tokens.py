"""Token counting for budget enforcement and benchmarking."""
import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    return len(_enc.encode(text, disallowed_special=()))
