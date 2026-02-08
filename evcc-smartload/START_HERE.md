# 🚀 START HERE - EVCC-Smartload v3.0.0

## Hey Krinco1! 👋

Dein Repository ist bereits richtig benannt: `HA_Addon_EVCC-Smartload`

Ich habe alles für dich vorbereitet. Folge einfach diesen Schritten:

---

## ✅ Was bereits erledigt ist

- ✅ Repository existiert: `https://github.com/Krinco1/HA_Addon_EVCC-Smartload`
- ✅ Name geändert: "EVCC-Smartload" statt "SmartPrice"
- ✅ Alle Dateien angepasst
- ✅ URLs zeigen auf dein Repo
- ✅ Korrekte Struktur für Home Assistant

---

## 📦 Repository-Struktur (MUSS SO SEIN!)

```
HA_Addon_EVCC-Smartload/          ← Dein GitHub Repo
├── repository.json               ← WICHTIG: Im Root!
├── README.md                     ← Repository-Beschreibung
├── .gitignore
└── evcc-smartload/               ← Add-on Ordner
    ├── config.yaml               ← version: "3.0.0"
    ├── Dockerfile
    ├── README.md                 ← Add-on Docs
    ├── CHANGELOG_v3.0.0.md
    ├── rootfs/
    │   ├── app/
    │   │   └── main.py
    │   └── etc/
    └── ...
```

---

## 🎯 Deployment (3 einfache Schritte)

### Schritt 1: Entpacke das ZIP

```bash
# Du hast: evcc-smartload-repo.zip
unzip evcc-smartload-repo.zip
cd evcc-smartload
```

**Du solltest sehen:**
```
repository.json     ← Im Root!
README.md
.gitignore
evcc-smartload/     ← Add-on
```

### Schritt 2: Push zu GitHub

```bash
# Lösche altes (wenn vorhanden):
cd /pfad/zu/deinem/lokalen/repo
rm -rf *

# Kopiere neue Struktur:
cp -r /pfad/zum/entpackten/evcc-smartload/* .

# Commit und Push:
git add .
git commit -m "Release v3.0.0 - Pro-Device RL Control"
git push origin main --force
```

⚠️ **WICHTIG:** Der `--force` überschreibt dein Repo mit der korrekten Struktur!

### Schritt 3: In Home Assistant hinzufügen

1. **Einstellungen** → **Add-ons** → **Add-on Store**
2. **⋮** (oben rechts) → **Repositories**
3. Füge hinzu:
   ```
   https://github.com/Krinco1/HA_Addon_EVCC-Smartload
   ```
4. **Warte 2 Minuten**
5. Zurück zum Store → Suche "EVCC-Smartload"

---

## ✅ Validierung (WICHTIG!)

**Teste diese URLs im Browser:**

```
https://raw.githubusercontent.com/Krinco1/HA_Addon_EVCC-Smartload/main/repository.json
```
→ Muss JSON zeigen

```
https://raw.githubusercontent.com/Krinco1/HA_Addon_EVCC-Smartload/main/evcc-smartload/config.yaml
```
→ Muss YAML zeigen mit `version: "3.0.0"`

**Beide funktionieren? → Add-on wird in HA erscheinen! 🎉**

---

## 🎨 Optional: Icon hinzufügen

Erstelle ein 192x192px PNG Icon und speichere als:
```
evcc-smartload/icon.png
```

Dann:
```bash
git add evcc-smartload/icon.png
git commit -m "Add add-on icon"
git push
```

---

## 📊 Nach Installation

### Dashboard öffnen
```
http://homeassistant:8099
```

### Dokumentation lesen
```
http://homeassistant:8099/docs
```

### API testen
```bash
# Device Status:
curl http://homeassistant:8099/rl-devices

# System Status:
curl http://homeassistant:8099/status
```

---

## ⚙️ Konfiguration

**Minimum:**
```yaml
evcc_url: "http://192.168.1.66:7070"
influxdb_host: "192.168.1.67"
influxdb_database: "smartload"
battery_capacity_kwh: 33.1
battery_max_price_ct: 25.0
```

**Mit deinen Fahrzeugen:**
```yaml
vehicle_providers: |
  [
    {
      "evcc_name": "KIA_EV9",
      "type": "kia",
      "user": "deine-email@example.com",
      "password": "dein-passwort",
      "capacity_kwh": 99.8,
      "rl_mode": "auto"
    },
    {
      "evcc_name": "Twingo",
      "type": "renault",
      "user": "deine-email@example.com",
      "password": "dein-passwort",
      "capacity_kwh": 22,
      "rl_mode": "auto"
    }
  ]
```

---

## 🐛 Troubleshooting

### Add-on erscheint nicht in HA?

**Check 1: Repository PUBLIC?**
```
https://github.com/Krinco1/HA_Addon_EVCC-Smartload
→ Muss ohne Login sichtbar sein!
```

**Check 2: Struktur korrekt?**
```
repository.json im Root? ✅
evcc-smartload/ Ordner da? ✅
```

**Check 3: Raw URLs funktionieren?**
```
Teste die beiden URLs oben!
```

**Check 4: Warten!**
```
HA cached Repos → Warte 5 Minuten → F5 im Browser
```

---

## 🎯 Erwartetes Ergebnis

**In Home Assistant solltest du sehen:**

```
Add-on Store
└── 📦 EVCC-Smartload - Intelligent Energy Management
    └── EVCC-Smartload - Hybrid Optimizer
        Version: 3.0.0
        by Krinco1
        [INSTALLIEREN]
```

---

## 📚 Weitere Dokumentation

Im Package findest du:
- **README.md** - Vollständige Dokumentation (1200+ Zeilen)
- **CHANGELOG_v3.0.0.md** - Was ist neu?
- **INSTALL.md** - Installation & Konfiguration
- **evcc-smartload/README.md** - Add-on Dokumentation

---

## 💡 Pro-Tips

1. **Icon**: Füge `evcc-smartload/icon.png` hinzu für schöneres Add-on
2. **Testing**: Teste erstmal die Raw URLs bevor du in HA hinzufügst
3. **Updates**: Ändere `version` in config.yaml für Updates
4. **Backup**: Sichere `/data/` regelmäßig (enthält RL-Modelle)

---

## 🆘 Support

**Funktioniert nicht?**

1. Prüfe Raw URLs (siehe oben)
2. Check GitHub Repo Sichtbarkeit (PUBLIC?)
3. Poste Issue mit:
   - Screenshot deiner Repo-Struktur
   - Welche Raw URL funktioniert nicht?
   - HA Logs (Einstellungen → System → Logs)

---

## 🎉 Los geht's!

1. ✅ Entpacke ZIP
2. ✅ Push zu GitHub (mit --force)
3. ✅ Teste Raw URLs
4. ✅ Füge in HA hinzu
5. ✅ **FERTIG!**

---

<div align="center">

**Viel Erfolg mit EVCC-Smartload v3.0.0!** 🚀

Bei Fragen: GitHub Issues

</div>
