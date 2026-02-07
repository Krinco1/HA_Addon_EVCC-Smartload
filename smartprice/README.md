# SmartPrice v2.0 - Hybrid LP + Shadow RL

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   LP OPTIMIZER          vs          SHADOW RL                   │
│   ════════════                      ═════════                   │
│                                                                 │
│   ✓ Steuert evcc                    ✗ Schreibt NIEMALS          │
│   ✓ Sofort optimal                  ✓ Lernt parallel            │
│   ✓ Erklärbar                       ✓ Simuliert                 │
│                                     ✓ Vergleicht                │
│                                     ✓ "RL READY" wenn besser    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 🎯 Konzept

**PRODUKTION (LP):** Linear Programming Optimizer trifft alle Entscheidungen und steuert evcc.

**SHADOW (RL):** Reinforcement Learning Agent beobachtet, simuliert eigene Entscheidungen, vergleicht – aber schreibt NIEMALS nach evcc.

**GRADUATION:** Nach ~200 Vergleichen mit ≥80% Win-Rate erscheint im Log:
```
🎉 RL READY! Agent hat ausreichend gelernt.
```

---

## 🚀 Beschleunigungstechniken

### 1. Imitation Learning
RL lernt initial von LP-Entscheidungen:
```python
rl_agent.imitation_learn(state, lp_action)
```
→ Startet nicht bei Null, sondern mit LP-Wissen

### 2. Reward Shaping
Zusätzliche Signale für schnelleres Feedback:
- Laden bei niedrigem Preis → +Reward
- Entladen bei hohem Preis → +Reward
- Laden über Maximum → -Penalty

### 3. Prioritized Experience Replay
Wichtige Erfahrungen (Events) werden öfter wiederholt:
- `EV_CHARGED_EXTERNALLY` → Priority 2x
- `PRICE_SPIKE` → Priority 2x

### 4. Event Detection
Erkennt und priorisiert interessante Situationen:
```
EV_CONNECTED         - Auto angeschlossen
EV_DISCONNECTED      - Auto weg
EV_CHARGED_EXTERNALLY- Auto woanders geladen!
PRICE_DROP           - Preiseinbruch
PRICE_SPIKE          - Preisspitze
BATTERY_LOW          - SoC < 15%
BATTERY_FULL         - SoC > 85%
PV_SURGE             - PV plötzlich hoch
PV_DROP              - PV plötzlich weg
GRID_EXPORT          - Einspeisung aktiv
```

---

## 📊 Action Space

```
BATTERIE (4 Aktionen):
  0 = hold         (nichts tun)
  1 = charge_grid  (aus Netz laden)
  2 = charge_pv    (nur PV)
  3 = discharge    (entladen)

EV (4 Aktionen):
  0 = no_charge    (nicht laden)
  1 = charge_cheap (günstig laden)
  2 = charge_now   (sofort laden)
  3 = charge_pv    (nur PV)

Kombiniert: 4 × 4 = 16 mögliche Aktionen
```

---

## 📈 API Endpoints

| Endpoint | Beschreibung |
|----------|--------------|
| `GET /health` | Status |
| `GET /status` | RL-Status, Vergleiche, Progress |
| `GET /comparisons` | Letzte 50 LP vs RL Vergleiche |
| `POST /save` | Speichert RL-Modell sofort |

### Beispiel `/status`:
```json
{
  "rl": {
    "enabled": true,
    "epsilon": 0.15,
    "total_steps": 1523,
    "memory_size": 1523,
    "q_table_size": 847
  },
  "comparison": {
    "comparisons": 1523,
    "rl_wins": 1294,
    "win_rate": 0.85,
    "lp_total_cost": 45.23,
    "rl_total_cost": 41.87,
    "rl_ready": true,
    "ready_threshold": 0.8,
    "ready_min_comparisons": 200
  }
}
```

---

## 📋 Logs

```
[INFO ] ======================================================================
[INFO ]   SmartPrice v2.0 - Hybrid LP + Shadow RL
[INFO ] ======================================================================
[INFO ]   LP Optimizer:  PRODUCTION (steuert evcc)
[INFO ]   Shadow RL:     LEARNING (beobachtet, vergleicht)
[INFO ] ======================================================================
[INFO ] RL model loaded (steps: 0, memory: 0)
[INFO ] Background data collection started
[INFO ] API server on port 8099
[INFO ] Starting main decision loop...
[INFO ] Battery: charge @ max 18.5 ct/kWh
[DEBUG] LP: bat=1 ev=0 | RL: bat=1 ev=0 | ε=0.300
[INFO ] Events detected: ['PRICE_DROP']
[DEBUG] LP: bat=1 ev=0 | RL: bat=1 ev=0 | ε=0.299
...
[INFO ] RL Progress: 50 comparisons, win rate 72.0%, ε=0.250
...
[INFO ] RL Progress: 100 comparisons, win rate 78.0%, ε=0.200
...
[INFO ] RL Progress: 150 comparisons, win rate 81.0%, ε=0.150
...
[INFO ] ============================================================
[INFO ] 🎉 RL READY! Agent hat ausreichend gelernt.
[INFO ]    Win-Rate: 82.5% (165/200)
[INFO ]    LP Gesamtkosten: €12.34
[INFO ]    RL Gesamtkosten: €10.87
[INFO ]    Ersparnis: €1.47
[INFO ] ============================================================
```

---

## ⚙️ Konfiguration

### RL Parameter
| Option | Default | Beschreibung |
|--------|---------|--------------|
| `rl_enabled` | `true` | Shadow RL aktivieren |
| `rl_learning_rate` | `0.001` | Lernrate |
| `rl_epsilon_start` | `0.3` | Start-Exploration (niedrig wg. Imitation) |
| `rl_epsilon_min` | `0.05` | Minimum Exploration |
| `rl_epsilon_decay` | `0.995` | Decay pro Schritt |
| `rl_ready_threshold` | `0.8` | 80% Win-Rate für "Ready" |
| `rl_ready_min_comparisons` | `200` | Mindestens 200 Vergleiche |

---

## 🕐 Zeitplan

```
Woche 1:     RL lernt von LP (Imitation Learning)
             Win-Rate steigt auf ~60-70%

Woche 2:     RL entwickelt eigene Strategien
             Win-Rate ~75-80%

Woche 3-4:   "RL READY" wenn Win-Rate ≥80%
             Ab jetzt: RL könnte produktiv übernehmen

Optional:    Manuell umschalten auf RL-Steuerung
             (erfordert Code-Änderung)
```

---

## 🔒 Sicherheit

**RL schreibt NIEMALS nach evcc!**

Der Shadow RL Agent:
- Beobachtet nur
- Simuliert Entscheidungen
- Vergleicht mit LP
- Lernt aus dem Vergleich

Erst wenn du manuell entscheidest (nach "RL READY"), kann RL produktiv werden.

---

## 📁 Persistierte Dateien

```
/data/
├── smartprice_state.json      # Letzter Zustand
├── smartprice_rl_model.json   # Q-Table + Hyperparameter
├── smartprice_rl_memory.json  # Replay Buffer
└── smartprice_comparison.json # LP vs RL Vergleiche
```

Alle werden bei Add-on Restart automatisch geladen.
