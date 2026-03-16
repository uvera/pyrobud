import asyncio
import logging
import sys
from pathlib import Path

import tomlkit

from . import DEFAULT_CONFIG_PATH, util
from .core import Bot

log = logging.getLogger("launch")


def setup_asyncio(config: util.config.Config) -> None:
    """Configures asyncio settings from the given config."""

    asyncio_config: util.config.AsyncIOConfig = config["asyncio"]

    if sys.platform == "win32":
        # Force ProactorEventLoop on Windows for subprocess support
        policy = asyncio.WindowsProactorEventLoopPolicy()
        asyncio.set_event_loop_policy(policy)
    elif not asyncio_config["disable_uvloop"]:
        # Initialize uvloop if available
        try:
            # noinspection PyUnresolvedReferences
            import uvloop

            uvloop.install()
            log.info("Using uvloop event loop")
        except ImportError:
            pass

    if asyncio_config["debug"]:
        log.info("Enabling asyncio debug mode")
        asyncio.get_event_loop().set_debug(True)


async def _upgrade(config: util.config.Config, config_path: str) -> None:
    await util.config.upgrade(config, config_path)


def main(*, config_path: str = DEFAULT_CONFIG_PATH) -> None:
    """Main entry point for the default bot launcher."""

    log.info("Loading config")
    config_data = Path(config_path).read_text()
    config: util.config.Config = tomlkit.loads(config_data)

    # Initialize Sentry reporting here to exempt config syntax errors and query
    # the user's report_errors value, defaulting to enabled if not specified
    if config["bot"].get("report_errors", True):
        log.info("Initializing Sentry error reporting")
        util.sentry.init()

    # Setup asyncio (including uvloop) before any asyncio.run() calls
    setup_asyncio(config)

    # Run config upgrade
    asyncio.run(_upgrade(config, config_path))

    # Start bot
    log.info("Initializing bot")
    asyncio.run(Bot.create_and_run(config))
