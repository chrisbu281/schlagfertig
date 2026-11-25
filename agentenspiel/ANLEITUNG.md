# Agentenspiel-Bot – Anleitung (Minimalversion für den Orga-Test)

## 1. Bot bei Telegram anlegen (5 Minuten)

1. In Telegram **@BotFather** öffnen und `/newbot` senden.
2. Namen eingeben, den die Gäste sehen, z. B. `Zentrale Silvester`.
3. Benutzernamen eingeben, er muss auf `bot` enden, z. B. `zentrale_silvester26_bot`.
4. BotFather antwortet mit einem **Schlüssel** (sieht aus wie `1234567890:AAH…`).
   Diesen Schlüssel **nur** in die Datei `einstellungen.ini` eintragen, nirgendwo sonst.

## 2. Einmalig auf dem Laptop einrichten

1. **Python installieren** (falls noch nicht da): https://www.python.org/downloads/
   *Windows:* beim Installieren unbedingt **„Add python.exe to PATH“** anhaken.
2. Den Ordner `agentenspiel` irgendwohin kopieren, z. B. auf den Desktop.
3. Im Ordner eine Eingabeaufforderung / ein Terminal öffnen und einmal ausführen:
   - Windows: `python -m pip install -r requirements.txt`
   - Mac: `python3 -m pip install -r requirements.txt`
4. `einstellungen.beispiel.ini` kopieren, die Kopie in **`einstellungen.ini`** umbenennen,
   den Schlüssel bei `token =` eintragen und eine eigene PIN bei `pin =` wählen.
5. In **`gaeste.txt`** die Namen eintragen, einen pro Zeile. Für den Test nur die Orga-Gruppe.

## 3. Starten

- Windows: Doppelklick auf **`start-windows.bat`**
- Mac: Doppelklick auf **`start-mac.command`** (beim ersten Mal: Rechtsklick → Öffnen)

Im schwarzen Fenster muss stehen: `Bot @… läuft. Zentrale: http://localhost:8080`.
Das Fenster offen lassen, solange gespielt wird. Schließen = Bot aus.
Alle Daten bleiben in `spiel.db` und `fotos/` erhalten, ein Neustart verliert nichts.

- **Zentrale:** im Browser `http://localhost:8080` öffnen. Sie ist nur auf diesem Laptop erreichbar, nicht im WLAN.
- **Dein Handy verbinden:** im Bot `/zentrale DEINE-PIN` senden. Ab dann bekommst du jede Anmeldung aufs Handy.

## 4. Test mit der Orga-Gruppe (ca. 20 Minuten)

| Schritt | Wer | Was prüfen |
|---|---|---|
| 1 | alle | Bot-Link öffnen → Start → Namen wählen → Selfie schicken (einer ohne Foto) |
| 2 | Christoph | Zentrale: alle angemeldet? Fotos da? Du bekommst Meldungen aufs Handy? |
| 3 | Christoph | Spion wählen, Merkmale 1–4 eintragen, **Speichern** |
| 4 | Christoph | **Spiel starten** → alle Handys: „STRENG GEHEIM“ → *Akte öffnen*. Spion sieht seine Merkmale? |
| 5 | Christoph | **Welle 1 senden** → alle melden: Name + Begründung. Einer schreibt nur „der da“ → muss abgelehnt werden |
| 6 | Christoph | **Welle 2 senden** → wer nicht gemeldet hat, bekommt die „verpasst“-Nachricht statt des Hinweises |
| 7 | Christoph | Eine Meldung als ☆ Verschwörungstheorie markieren, jemanden sperren und wieder entsperren |
| 8 | Christoph | Wellen 3–5 durchklicken (Welle 5 = zwei Namen) |
| 9 | Christoph | Beamer-Fenster öffnen, **Auflösung starten**, mit „weiter ▶“ alle 6 Schritte durchgehen |
| 10 | Christoph | Danach **Zurücksetzen → Alles inkl. Fotos** |

Notiert euch alles, was hakt oder komisch klingt. Das ist genau der Sinn des Tests.

## 5. Beamer und Auflösung

- Beamer in Windows/Mac auf **„Bildschirm erweitern“**, nie spiegeln.
- In der Zentrale auf **„Beamer-Fenster öffnen“**, das Fenster auf den Beamer ziehen,
  **einmal hineinklicken** (damit das Video Ton hat) und **F11** für Vollbild.
- Vor der Auflösung zeigt der Beamer nur „OPERATION SILVESTER“, nichts Geheimes.
- Die Schritte der Auflösung: Spion mit Foto → Stempel → Liveschaltung → Erkannt von → Verschwörungstheorien → Rangliste.
- **Fluchtvideo:** fertige Datei als `static/flucht.mp4` in den Ordner legen. Ohne Datei zeigt Schritt 3 „Verbindung wird hergestellt …“.

## 6. Regeln, wie der Bot sie umsetzt

- Punkte für eine richtige Meldung: Welle 1 = 5, Welle 2 = 4, Welle 3 = 3, Welle 4 = 2, Welle 5 = 1.
- Den nächsten Hinweis bekommt nur, wer in der Welle davor gemeldet hat. Der Spion bekommt immer alles.
- Wer verpasst hat, bekommt stattdessen eine Nachricht und kann sofort wieder einsteigen.
- Meldungen des Spions zählen nicht.
- **ENTTARNT**, wenn in Welle 5 mindestens die Hälfte der Agenten richtig liegt, sonst **UNENTDECKT**.
- Gesperrte Gäste bekommen keine Hinweise mehr und erscheinen nicht in der Rangliste.
- Wer einen falschen Namen gewählt hat: in der Zentrale bei „Gäste“ auf **lösen**, dann im Bot neu `/start`.

## 7. Am Abend

- Laptop am **Netzteil**, **Ruhezustand aus**, Bildschirmschoner aus.
- Der Laptop braucht **Internet**, sonst ist der Bot tot.
- Gäste ohne Internet bekommen ihre Nachrichten, sobald sie wieder online sind. Sie gehen nicht verloren, kommen aber zu spät.
- Nach der Party: **Zurücksetzen → Alles inkl. Fotos** löscht alle Fotos.

## Noch nicht drin (kommt nach dem Test)

Dienstausweis als Bild, verschwommene Bilder, Gestaltung des Beamers, Erinnerungsnachricht.
