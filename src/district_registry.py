"""DistrictRegistry — auto-discovers district agents from config/tenants/*.yaml.

How it works
------------
1. Scans every YAML file under config/tenants/.
2. Reads the `agent_module` key (e.g. 'src.agents.frisco_isd_tx_agent').
3. Imports that module and reads the module-level `agent` variable.
4. Stores the agent instance keyed by district_id.

To plug in a new district
-------------------------
  1. Drop  config/tenants/<district-id>.yaml   with at minimum:
         district_id: frisco_isd_tx
         name:        Frisco ISD
         state:       TX
         agent_module: src.agents.frisco_isd_tx_agent
         intents:
           - course_catalog
           - admin_policy

  2. Drop  src/agents/frisco_isd_tx_agent.py  that:
         - Subclasses DistrictAgent
         - Implements retrieve() and synthesize()
         - Exposes a module-level variable:  agent = FriscoIsdAgent()

  That's it.  No changes to orchestrator.py or app.py required.
"""
from __future__ import annotations

import glob
import importlib
import os
from typing import Dict, Optional

import yaml

from src.agents.base_agent import DistrictAgent


class DistrictRegistry:
    """Singleton-style registry.  Initialise once at startup and pass around."""

    def __init__(self, tenants_dir: str = "config/tenants"):
        self._agents: Dict[str, DistrictAgent] = {}
        self._configs: Dict[str, dict] = {}
        self._load(tenants_dir)

    def _load(self, tenants_dir: str) -> None:
        pattern = os.path.join(tenants_dir, "*.yaml")
        for yaml_path in sorted(glob.glob(pattern)):
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)

                district_id = cfg.get("district_id")
                agent_module_path = cfg.get("agent_module")

                if not district_id or not agent_module_path:
                    print(f"[registry] Skipping {yaml_path}: missing district_id or agent_module")
                    continue

                module = importlib.import_module(agent_module_path)

                if not hasattr(module, "agent"):
                    print(f"[registry] Skipping {yaml_path}: module {agent_module_path} has no 'agent' variable")
                    continue

                instance: DistrictAgent = module.agent
                self._agents[district_id] = instance
                self._configs[district_id] = cfg
                print(f"[registry] Loaded agent for district: {district_id}  ({cfg.get('name', '')})")

            except Exception as exc:
                print(f"[registry] Failed to load {yaml_path}: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, district_id: str) -> Optional[DistrictAgent]:
        """Return the agent for a district, or None if not registered."""
        return self._agents.get(district_id)

    def all_district_ids(self) -> list[str]:
        """All registered district IDs."""
        return list(self._agents.keys())

    def all_configs(self) -> Dict[str, dict]:
        """All raw tenant YAML configs, keyed by district_id."""
        return dict(self._configs)

    def display_names(self) -> Dict[str, str]:
        """Mapping of district_id -> human-readable name for UI dropdowns."""
        return {
            did: cfg.get("name", did)
            for did, cfg in self._configs.items()
        }

    def supported_intents(self, district_id: str) -> list[str]:
        """Intents supported by a specific district agent."""
        agent = self._agents.get(district_id)
        if agent:
            return agent.supported_intents
        return []
