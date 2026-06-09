"""ContextaApp — top-level Textual application.

Holds the shared ``aiosqlite.Connection``, ``ContextaConfig``,
``ArtifactRegistry``, and ``PromptBlueprintManager``.  Registers
``MainScreen`` as the default screen and ``AdminScreen`` as a named screen.
"""

from __future__ import annotations

import aiosqlite
from textual.app import App, ComposeResult

from ..admin.blueprint_manager import PromptBlueprintManager
from ..config import ContextaConfig
from ..llm.provider import LLMConfig
from ..mcp.artifact_registry import ArtifactRegistry
from .screens.admin_screen import AdminScreen
from .screens.main_screen import MainScreen


class ContextaApp(App):
    """Single-process Textual application for Project Contexta.

    Parameters
    ----------
    config:
        Validated ``ContextaConfig`` loaded from environment variables.
    db:
        Open ``aiosqlite.Connection`` (created by ``init_database()``).
    """

    CSS = """
    Screen {
        background: $surface;
    }
    Header {
        background: $primary;
    }
    Footer {
        background: $panel;
    }
    """

    TITLE = "Project Contexta"
    SUB_TITLE = "Deterministic Solution Validation Pipeline"

    def __init__(
        self,
        config: ContextaConfig,
        db: aiosqlite.Connection,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.db = db

        # Shared singletons
        self.registry = ArtifactRegistry()
        self.blueprint_manager = PromptBlueprintManager(db)
        self.llm_config = LLMConfig(
            model=config.llm_backend,
            api_key=config.llm_api_key,
            base_url=config.llm_base_url,
        )

    def on_mount(self) -> None:
        # Register the admin screen as a named screen
        self.install_screen(
            AdminScreen(
                blueprint_manager=self.blueprint_manager,
                db_conn=self.db,
            ),
            name="admin",
        )

    def compose(self) -> ComposeResult:
        yield MainScreen(
            registry=self.registry,
            llm_config=self.llm_config,
            blueprint_manager=self.blueprint_manager,
            export_path=self.config.export_path,
        )
