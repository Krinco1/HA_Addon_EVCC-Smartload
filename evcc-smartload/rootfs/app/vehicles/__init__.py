"""
vehicles package for EVCC-Smartload.

Provides vehicle data providers and the VehicleManager coordinator.

Usage:
    from vehicles.manager import VehicleManager
    from vehicles.base import VehicleData

Provider types (configured via vehicles.yaml):
    - renault                  → RenaultProvider (renault-api, e.g. Twingo/Dacia)
    - custom                   → CustomProvider (configurable local HTTP, e.g. ORA via LAN)
    - evcc                     → EvccProvider (SoC via evcc state only, no active poll)

Legacy types (kia/hyundai/genesis) silently downgrade to EvccProvider with a warning.
The Bluelink cloud was never reliable enough — use evcc.yaml with poll.mode: always
for Kia/Hyundai/Genesis vehicles instead.
"""

from vehicles.base import VehicleData
from vehicles.manager import VehicleManager

__all__ = ["VehicleData", "VehicleManager"]
