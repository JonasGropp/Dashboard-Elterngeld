# 👶 Elterngeld- & Haushaltseinkommens-Planer (Streamlit)

Szenarioplaner für das **gemeinsame verfügbare Netto-Haushaltseinkommen nach
Geburt eines Kindes** in Deutschland – mit variablem Elterngeldmodell je
Lebensmonat, Mutterschutz, Kindergeld, Plausibilitätsprüfungen,
transponierter Dashboard-Tabelle (Monate = Spalten, Kennzahlen = Zeilen),
Diagrammen und Szenariovergleich.

> ⚠️ Dieses Programm ersetzt **keine Steuer- oder Rechtsberatung**. Es dient
> der transparenten Liquiditäts- und Szenarioplanung. Die tatsächliche
> Elterngeldstelle kann abweichend rechnen.

## Installation

Voraussetzung: Python 3.10+

```bash
# 1. In den Projektordner wechseln
cd elterngeld_planner

# 2. (Empfohlen) virtuelle Umgebung anlegen
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt
```

## Start

```bash
streamlit run app.py
```

Der Browser öffnet sich automatisch unter `http://localhost:8501`.

## Als Website aufrufen (drei Wege)

### Weg 1: Im eigenen Netzwerk (WLAN/LAN) – ohne weitere Tools

Die mitgelieferte `.streamlit/config.toml` konfiguriert den Server bereits auf
`0.0.0.0`. Einfach starten:

```bash
streamlit run app.py
```

Dann von jedem Gerät im selben Netzwerk (auch Handy/Tablet) aufrufen:

```
http://<IP-des-Rechners>:8501     z. B. http://192.168.178.42:8501
```

Die eigene IP zeigt Streamlit beim Start als „Network URL" an
(alternativ: `ipconfig` unter Windows, `ip a` unter Linux/macOS).
Ggf. Port 8501 in der Firewall freigeben.

### Weg 2: Öffentliche Website – kostenlos über Streamlit Community Cloud

1. Projektordner als Repository auf GitHub hochladen
   (`app.py`, `calculations.py`, `requirements.txt` genügen).
2. Auf https://share.streamlit.io mit GitHub anmelden.
3. „New app" → Repository und `app.py` auswählen → Deploy.
4. Die App ist danach dauerhaft unter einer eigenen URL erreichbar,
   z. B. `https://elterngeld-planner.streamlit.app`.

Hinweis: Die URL ist öffentlich. In den App-Einstellungen kann der Zugriff
auf bestimmte (Google-)E-Mail-Adressen beschränkt werden – sinnvoll, da es
sich um private Finanzdaten handelt.

### Weg 3: Eigener Server / NAS – per Docker

```bash
docker compose up -d
```

Danach erreichbar unter `http://<server-ip>:8501`. Für eine eigene Domain
mit HTTPS einen Reverse-Proxy (z. B. Caddy, nginx, Traefik) auf Port 8501
zeigen lassen.

**Datenhaltung:** Jede Browser-Sitzung hat ihre eigenen Eingaben und
Szenarien (Streamlit-Session-State). Mehrere Nutzer stören sich nicht
gegenseitig; nach dem Schließen des Tabs sind Szenarien allerdings weg –
wichtige Stände daher per CSV-Export sichern.

## Projektstruktur

| Datei                  | Inhalt                                                        |
|------------------------|---------------------------------------------------------------|
| `app.py`               | Streamlit-Dashboard (Eingaben, Tabelle, Diagramme, Szenarien) |
| `calculations.py`      | Reine, kommentierte Berechnungslogik (ohne Streamlit)         |
| `test_calculations.py` | Smoke-Tests der Berechnungslogik (`python test_calculations.py`) |
| `requirements.txt`     | Python-Abhängigkeiten                                         |
| `.streamlit/config.toml` | Server-Konfiguration für den Website-Betrieb                |
| `Dockerfile`, `docker-compose.yml` | Betrieb als Website auf eigenem Server/NAS        |

## Bedienung in Kürze

1. **Stammdaten**: Namen, Geburtstermin (Default 19.02.2027), Hochzeit,
   Steuerklassen (Default 5/3 nach Hochzeit), Kindergeld (259 €),
   Betrachtungszeitraum (36 Monate), Fixkosten, sowie alle
   Elterngeld-Parameter (Ersatzrate 65 %, 300/1.800 €, Plus 150/900 € …)
   zentral editierbar.
2. **Einkommen & Mutterschutz**: Netto vor Geburt (Jana 3.095 €,
   Jonas 3.109 €), optionale grobe Brutto-Netto-Näherung, Mutterschutz
   (Default 6 Wochen vor / 8 Wochen nach Geburt, editierbar),
   Mutterschaftsleistung optional als echter Wert.
3. **Elterngeldplanung**: Tabelle je **Lebensmonat** und Elternteil:
   Modell (Kein EG / Basis / Plus / Partnerschaftsbonus), Status,
   Wochenstunden, % vom Netto, fixes Netto, sonstige Einnahmen, Bemerkung.
   Vorlagen A/B/C per Knopfdruck.
4. **Ergebnis**: Transponierte Dashboard-Tabelle (horizontal scrollbar,
   Euro-Format), Warnungen, vier Diagramme, CSV-Export.
5. **Szenarien**: Speichern, Duplizieren, Löschen, Vergleichen
   (Kennzahlentabelle + Verlaufsdiagramme).

## Kernlogik: Lebensmonate vs. Kalendermonate

- Lebensmonat m: `Geburt + (m−1) Monate` bis `Geburt + m Monate − 1 Tag`
  (Geburt 19.02.2027 → LM 1: 19.02.–18.03.2027).
- **Eingaben** gelten je Lebensmonat, **ausgewertet** wird je Kalendermonat.
- Elterngeld (Zahlung je Lebensmonat) wird **tagesgenau anteilig** auf die
  überlappenden Kalendermonate verteilt.
- Gehalt und Mutterschutzleistung sind laufende Monatsbezüge und werden auf
  Kalendertage normiert (ein konstantes Gehalt bleibt so je Kalendermonat
  konstant).

## Wichtige vereinfachte Annahmen

- Berechnung standardmäßig auf **Netto-Basis**; Brutto-Netto nur grob genähert.
- Elterngeld = `Ersatzrate × (Netto vor − Netto nach Geburt)` mit Min/Max;
  Teilzeit wird über die Netto-Differenz abgebildet.
- Mutterschaftsgeld + Arbeitgeberzuschuss ≈ Fortführung des bisherigen Nettos,
  sofern kein echter Wert gepflegt ist; sie werden auf das Elterngeld
  **angerechnet** (Mutterschutzmonate zählen als Basiselterngeld-Monate der
  Mutter).
- Elterngeld ist steuerfrei, unterliegt aber dem **Progressionsvorbehalt**
  (mögliche spätere Steuerbelastung ist nicht eingerechnet).
- Steuerklassenkombination 3/5 wird als zulässig akzeptiert; der Wechsel wird
  nicht automatisch in Netto-Werte umgerechnet.
