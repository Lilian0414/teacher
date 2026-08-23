import multiprocessing
import time

import uvicorn

from companion.settings import get_settings


def core() -> None:
    """Run the Core API using the shared environment-backed settings."""
    settings = get_settings()
    uvicorn.run("companion.main:app", host=settings.host, port=settings.port)


def local() -> None:
    """Run Core and UI together for a simple local development experience."""
    from terminal_ui.app import run

    process = multiprocessing.Process(target=core)
    process.start()
    try:
        time.sleep(0.5)
        run()
    finally:
        process.terminate()
        process.join()
