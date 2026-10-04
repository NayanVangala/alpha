"""Splits a list into pages for a long feed."""


def page(items, number, size=10):
    """The items on page `number`, counting pages from 1."""
    start = (number - 1) * size
    return items[start : start + size]


def page_count(items, size=10):
    return (len(items) + size - 1) // size
