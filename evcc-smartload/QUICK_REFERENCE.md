# ⚡ EVCC-Smartload Quick Reference - Krinco1

## 🔗 Deine URLs

**GitHub Repo:**
```
https://github.com/Krinco1/HA_Addon_EVCC-Smartload
```

**Home Assistant Repository URL:**
```
https://github.com/Krinco1/HA_Addon_EVCC-Smartload
```

**Dashboard nach Installation:**
```
http://homeassistant:8099
```

**Dokumentation:**
```
http://homeassistant:8099/docs
```

---

## 🧪 Test-URLs (öffne im Browser)

**Repository JSON:**
```
https://raw.githubusercontent.com/Krinco1/HA_Addon_EVCC-Smartload/main/repository.json
```
→ Muss JSON zeigen

**Config YAML:**
```
https://raw.githubusercontent.com/Krinco1/HA_Addon_EVCC-Smartload/main/evcc-smartload/config.yaml
```
→ Muss YAML mit version: "3.0.0" zeigen

---

## 📁 Korrekte Struktur

```
HA_Addon_EVCC-Smartload/
├── repository.json          ← Muss im Root sein!
├── README.md
├── .gitignore
└── evcc-smartload/
    ├── config.yaml
    ├── Dockerfile
    ├── README.md
    └── rootfs/
```

---

## 🚀 Git Commands

```bash
# Alles neu deployen:
cd /dein/lokales/repo
rm -rf *
cp -r /entpacktes/evcc-smartload/* .
git add .
git commit -m "Release v3.0.0"
git push origin main --force

# Tag erstellen (optional):
git tag v3.0.0
git push origin v3.0.0
```

---

## 🏠 Home Assistant Commands

```bash
# In HA Repository hinzufügen:
Einstellungen → Add-ons → ⋮ → Repositories
+ https://github.com/Krinco1/HA_Addon_EVCC-Smartload

# Logs checken:
docker logs addon_evcc_smartload -f

# API testen:
curl http://homeassistant:8099/status
curl http://homeassistant:8099/rl-devices

# Config prüfen:
docker exec addon_evcc_smartload cat /data/options.json
```

---

## ⚙️ Deine Config (Beispiel)

```yaml
evcc_url: "http://192.168.1.66:7070"
influxdb_host: "192.168.1.67"
influxdb_database: "smartload"
battery_capacity_kwh: 33.1
battery_max_price_ct: 25.0

vehicle_providers: |
  [
    {
      "evcc_name": "KIA_EV9",
      "type": "kia",
      "user": "deine-email",
      "password": "password",
      "capacity_kwh": 99.8,
      "rl_mode": "auto"
    },
    {
      "evcc_name": "Twingo",
      "type": "renault",
      "user": "deine-email",
      "password": "password",
      "capacity_kwh": 22,
      "rl_mode": "auto"
    }
  ]

rl_enabled: true
rl_auto_switch: true
rl_fallback_threshold: 0.7
```

---

## 🎯 Checklist

- [ ] ZIP entpackt
- [ ] Struktur geprüft (repository.json im Root?)
- [ ] Zu GitHub gepusht
- [ ] Test-URLs funktionieren (siehe oben)
- [ ] Repository in HA hinzugefügt
- [ ] Add-on erscheint im Store
- [ ] Add-on installiert
- [ ] Konfiguriert
- [ ] Gestartet
- [ ] Dashboard erreichbar (Port 8099)
- [ ] Logs OK (keine ERROR)

---

## 📊 API Endpoints

```bash
# Health
curl http://homeassistant:8099/health

# Full Status
curl http://homeassistant:8099/status | jq

# RL Device Status
curl http://homeassistant:8099/rl-devices | jq

# Vehicles
curl http://homeassistant:8099/vehicles | jq

# Documentation
http://homeassistant:8099/docs
http://homeassistant:8099/docs/readme
http://homeassistant:8099/docs/api
```

---

## 🐛 Quick Troubleshooting

| Problem | Lösung |
|---------|--------|
| Add-on erscheint nicht | Test-URLs prüfen, Repo PUBLIC? |
| Installation fehl | Logs checken, Dockerfile OK? |
| Start fehl | evcc erreichbar? InfluxDB OK? |
| Port belegt | Anderen Port in config.yaml |
| Kein RL Training | LP läuft? Logs prüfen |

---

## 📝 Version Updates

```bash
# In evcc-smartload/config.yaml:
version: "3.0.1"  # Erhöhen

# Commit:
git add evcc-smartload/config.yaml
git commit -m "Bump to v3.0.1"
git tag v3.0.1
git push origin main --tags

# HA zeigt automatisch Update an!
```

---

## 🔧 Maintenance

```bash
# Backup
docker exec addon_evcc_smartload tar -czf /share/evcc-smartload-backup.tar.gz /data

# Restore
docker exec addon_evcc_smartload tar -xzf /share/evcc-smartload-backup.tar.gz -C /

# Reset RL
docker exec addon_evcc_smartload rm /data/smartload_rl_*
docker exec addon_evcc_smartload rm /data/smartload_device_control.db

# Reload
ha addons reload
ha addons restart addon_evcc_smartload
```

---

## 💡 Pro-Tips

1. **Icon**: Erstelle `evcc-smartload/icon.png` (192x192px)
2. **Docs**: Alle Docs sind im Dashboard unter `/docs`
3. **Monitoring**: Nutze InfluxDB + Grafana für Metriken
4. **Testing**: Lass System 2 Wochen laufen vor Production

---

## 🎉 Success Indicators

✅ Add-on im Store sichtbar  
✅ Installation ohne Fehler  
✅ Status: RUNNING  
✅ Dashboard lädt (Port 8099)  
✅ Logs zeigen v3.0.0  
✅ Keine ERROR messages  

---

**Alles Gut? → Ready to go! 🚀**

Bei Fragen: GitHub Issues oder Discussions
