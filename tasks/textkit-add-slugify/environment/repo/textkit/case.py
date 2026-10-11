def title_case(text: str) -> str:
    """Capitalize the first letter of every word."""
    return " ".join(word[:1].upper() + word[1:] for word in text.split(" "))
