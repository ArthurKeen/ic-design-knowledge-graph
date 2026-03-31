"""
Shared constants and helpers for bridger.py and bridger_bulk.py.
"""

import logging

from config import (
    COL_MODULE, COL_PORT, COL_SIGNAL, COL_LOGIC,
    COL_CHUNKS, COL_ENTITIES,
    COL_FSM, COL_PARAMETER, COL_MEMORY,
    COL_CLOCK, COL_BUS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type Compatibility Matrix
# Maps RTL collection types to sets of compatible Golden Entity types.
# ---------------------------------------------------------------------------
TYPE_COMPATIBILITY: dict[str, set] = {
    COL_MODULE: {'processor_component', 'architecture_feature', 'memory_unit', 'hardware_interface', 'configuration', 'UNKNOWN', None},
    COL_PORT: {'register', 'signal', 'hardware_interface', 'architecture_feature', 'UNKNOWN', None},
    COL_SIGNAL: {'register', 'signal', 'architecture_feature', 'UNKNOWN', None},
    COL_LOGIC: {'instruction', 'architecture_feature', 'configuration', 'exception_type', 'UNKNOWN', None},
    COL_BUS: {'hardware_interface', 'bus_protocol', 'architecture_feature', 'processor_component', 'UNKNOWN', None},
    COL_CLOCK: {'architecture_feature', 'clock_domain', 'processor_component', 'UNKNOWN', None},
    COL_FSM: {'architecture_feature', 'state_machine', 'processor_component', 'UNKNOWN', None},
    COL_PARAMETER: {'configuration', 'UNKNOWN', None},
    COL_MEMORY: {'memory_unit', 'processor_component', 'UNKNOWN', None},
}

# ---------------------------------------------------------------------------
# ArangoSearch view link definitions
# ---------------------------------------------------------------------------
HARMONIZED_SEARCH_VIEW_LINKS: dict[str, dict] = {
    COL_MODULE: {
        "fields": {
            "label": {"analyzers": ["text_en", "identity"]},
            "metadata": {"fields": {"summary": {"analyzers": ["text_en"]}}},
        }
    },
    COL_PORT: {
        "fields": {
            "label": {"analyzers": ["text_en", "identity"]},
            "metadata": {"fields": {"description": {"analyzers": ["text_en"]}}},
        }
    },
    COL_SIGNAL: {
        "fields": {
            "label": {"analyzers": ["text_en", "identity"]},
            "metadata": {"fields": {"description": {"analyzers": ["text_en"]}}},
        }
    },
    COL_LOGIC: {
        "fields": {
            "label": {"analyzers": ["text_en", "identity"]},
            "metadata": {"fields": {"code": {"analyzers": ["text_en"]}}},
        }
    },
    COL_BUS: {
        "fields": {
            "name": {"analyzers": ["text_en", "identity"]},
            "interface_type": {"analyzers": ["text_en", "identity"]},
        }
    },
    COL_CLOCK: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
    COL_FSM: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
    COL_PARAMETER: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
    COL_MEMORY: {"fields": {"name": {"analyzers": ["text_en", "identity"]}}},
    COL_ENTITIES: {
        "fields": {
            "label": {"analyzers": ["text_en", "identity"]},
            "entity_name": {"analyzers": ["text_en", "identity"]},
            "description": {"analyzers": ["text_en"]},
        }
    },
    COL_CHUNKS: {"fields": {"content": {"analyzers": ["text_en"]}}},
}


def create_or_update_search_view(
    db,
    view_name: str = "harmonized_search_view",
    *,
    filter_missing: bool = False,
):
    """Create or replace the harmonized ArangoSearch view.

    Args:
        db: ArangoDB database handle.
        view_name: Name for the ArangoSearch view.
        filter_missing: When *True*, silently skip collections that do not
            exist in the database (bridger_bulk behaviour).  When *False*,
            include all configured links regardless (bridger behaviour).
    """
    existing_views = [v["name"] for v in db.views()]

    if filter_missing:
        links = {
            name: cfg
            for name, cfg in HARMONIZED_SEARCH_VIEW_LINKS.items()
            if db.has_collection(name)
        }
    else:
        links = dict(HARMONIZED_SEARCH_VIEW_LINKS)

    properties = {"links": links}

    if view_name in existing_views:
        logger.info("Updating ArangoSearch View '%s'...", view_name)
        db.update_view(name=view_name, properties=properties)
        return view_name

    logger.info("Creating ArangoSearch View '%s'...", view_name)
    db.create_view(name=view_name, view_type="arangosearch", properties=properties)
    return view_name
