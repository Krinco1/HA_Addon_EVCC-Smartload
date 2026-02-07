# SmartPrice Home Assistant Add-on Repository

Intelligente Energieoptimierung für evcc mit dynamischen Stromtarifen.

## Installation

1. **Repository zu Home Assistant hinzufügen:**
   - Settings → Add-ons → Add-on Store
   - ⋮ (oben rechts) → Repositories
   - URL einfügen: `https://github.com/Krinco1/HA_Addon_EVCC_Ostrom_EV-Bat-logic`
   - Add → Close

2. **Add-on installieren:**
   - Im Add-on Store nach "SmartPrice" suchen
   - Installieren & Konfigurieren

## Add-ons in diesem Repository

### SmartPrice v2 - Hybrid Optimizer

Optimiert Batterie- und EV-Ladung basierend auf dynamischen Strompreisen.

**Features:**
- 🔋 LP-Optimierung für Hausbatterie (produktiv)
- 🚗 Modulares Fahrzeug-System (KIA, Renault, Custom)
- 🤖 Shadow RL zum Lernen (optional)
- 📊 Dashboard mit Ladeslot-Planung
- ⚡ evcc-Integration

**Unterstützte Fahrzeug-APIs:**
| Provider | Fahrzeuge |
|----------|-----------|
| `kia` | KIA, Hyundai (Bluelink) |
| `renault` | Renault, Dacia (MY Renault) |
| `custom` | Beliebige (via Script) |
| `evcc` | Fallback für alle |

## Konfiguration

Siehe [smartprice/README.md](smartprice/README.md) für Details.

## Support

Issues auf GitHub melden.
