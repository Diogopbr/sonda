import asyncio


def selector_loop() -> asyncio.AbstractEventLoop:
    """Uvicorn factory compatible with psycopg on Windows and Linux."""
    return asyncio.SelectorEventLoop()
