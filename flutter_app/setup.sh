#!/bin/bash
# Einmalig ausführen um das Flutter-Projekt zu initialisieren
set -e

echo "=== Schlagfertig Flutter-Projekt Setup ==="

# Prüfen ob Flutter installiert ist
if ! command -v flutter &> /dev/null; then
    echo "FEHLER: Flutter nicht gefunden."
    echo "Installation: https://docs.flutter.dev/get-started/install"
    exit 1
fi

echo "Flutter Version: $(flutter --version | head -1)"

# Platform-spezifische Verzeichnisse erstellen (ohne bestehende lib/ zu überschreiben)
echo "Erstelle Platform-Verzeichnisse..."
flutter create --platforms=linux,android --org=de.schlagfertig --project-name=schlagfertig . 2>/dev/null || true

# Pakete laden
echo "Lade Pakete..."
flutter pub get

echo ""
echo "=== Setup abgeschlossen ==="
echo ""
echo "Starten:"
echo "  Linux (Pi):   flutter run -d linux"
echo "  Android:      flutter run -d <device-id>"
echo "  Release-Build Android: flutter build apk --release"
echo "  Release-Build Linux:   flutter build linux --release"
