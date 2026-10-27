import 'dart:async';
import 'dart:io' show Platform;
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../core/socket_service.dart';
import 'display_screen.dart';
import 'moderator_screen.dart';

class StartupScreen extends StatefulWidget {
  const StartupScreen({super.key});

  @override
  State<StartupScreen> createState() => _StartupScreenState();
}

class _StartupScreenState extends State<StartupScreen> {
  final _urlController = TextEditingController(text: 'http://localhost:5000');
  bool _connecting = false;
  String? _error;

  bool get _isDisplayPlatform {
    try {
      return Platform.isLinux;
    } catch (_) {
      return false;
    }
  }

  @override
  void initState() {
    super.initState();
    _ladeGespeicherteUrl();
  }

  Future<void> _ladeGespeicherteUrl() async {
    final prefs = await SharedPreferences.getInstance();
    final gespeichert = prefs.getString('server_url');
    if (gespeichert != null) {
      _urlController.text = gespeichert;
    }
    // Auf Linux (Pi): sofort im Display-Modus starten
    if (_isDisplayPlatform) {
      _verbinden(display: true);
    }
  }

  Future<void> _verbinden({required bool display}) async {
    setState(() {
      _connecting = true;
      _error = null;
    });

    final url = _urlController.text.trim();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('server_url', url);

      await SocketService().connect(url);

      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (_) => display ? const DisplayScreen() : const ModeratorScreen(),
        ),
      );
    } on TimeoutException {
      setState(() {
        _error = 'Server nicht erreichbar.\nIP-Adresse prüfen: $url';
        _connecting = false;
      });
    } catch (e) {
      setState(() {
        _error = 'Verbindung fehlgeschlagen:\n$e';
        _connecting = false;
      });
    }
  }

  @override
  void dispose() {
    _urlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Padding(
              padding: const EdgeInsets.all(32),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Text(
                    'SCHLAGFERTIG',
                    style: TextStyle(
                      fontSize: 32,
                      fontWeight: FontWeight.w900,
                      color: Color(0xFFF5C518),
                      letterSpacing: 5,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _isDisplayPlatform ? 'Display-Gerät' : 'Quiz-App',
                    style: const TextStyle(color: Colors.white38, fontSize: 13, letterSpacing: 2),
                  ),
                  const SizedBox(height: 48),
                  TextField(
                    controller: _urlController,
                    enabled: !_connecting,
                    decoration: const InputDecoration(
                      labelText: 'Server-Adresse',
                      hintText: 'http://192.168.1.x:5000',
                      prefixIcon: Icon(Icons.wifi),
                    ),
                    keyboardType: TextInputType.url,
                    onSubmitted: (_) => _isDisplayPlatform ? null : _verbinden(display: false),
                  ),
                  const SizedBox(height: 28),
                  if (_error != null) ...[
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.red.withOpacity(0.12),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.redAccent.withOpacity(0.4)),
                      ),
                      child: Text(
                        _error!,
                        style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    const SizedBox(height: 20),
                  ],
                  if (_connecting)
                    const Column(
                      children: [
                        CircularProgressIndicator(color: Color(0xFFF5C518)),
                        SizedBox(height: 16),
                        Text('Verbinde...', style: TextStyle(color: Colors.white38)),
                      ],
                    )
                  else if (!_isDisplayPlatform) ...[
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        onPressed: () => _verbinden(display: false),
                        icon: const Icon(Icons.tune),
                        label: const Text('Moderator-Modus', style: TextStyle(fontSize: 16)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFFF5C518),
                          foregroundColor: Colors.black,
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: OutlinedButton.icon(
                        onPressed: () => _verbinden(display: true),
                        icon: const Icon(Icons.tv),
                        label: const Text('Display-Modus', style: TextStyle(fontSize: 16)),
                        style: OutlinedButton.styleFrom(
                          foregroundColor: Colors.white38,
                          side: const BorderSide(color: Colors.white24),
                          padding: const EdgeInsets.symmetric(vertical: 16),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
