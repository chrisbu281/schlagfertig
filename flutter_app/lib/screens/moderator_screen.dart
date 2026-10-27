import 'package:flutter/material.dart';
import '../core/socket_service.dart';
import 'startup_screen.dart';

class ModeratorScreen extends StatefulWidget {
  const ModeratorScreen({super.key});

  @override
  State<ModeratorScreen> createState() => _ModeratorScreenState();
}

class _ModeratorScreenState extends State<ModeratorScreen> {
  bool _connected = true;
  Map<String, dynamic> _serverState = {};

  @override
  void initState() {
    super.initState();
    SocketService().on('connect', (_) => setState(() => _connected = true));
    SocketService().on('disconnect', (_) => setState(() => _connected = false));
    SocketService().on('state', (data) {
      if (data is Map) {
        setState(() => _serverState = Map<String, dynamic>.from(data));
      }
    });
    // Phase 2: Spiel-spezifische Events kommen hier dazu
  }

  @override
  void dispose() {
    SocketService().off('connect');
    SocketService().off('disconnect');
    SocketService().off('state');
    super.dispose();
  }

  void _trennen() {
    SocketService().disconnect();
    Navigator.pushReplacement(
      context,
      MaterialPageRoute(builder: (_) => const StartupScreen()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF05070D),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0D1117),
        title: const Text(
          'SCHLAGFERTIG',
          style: TextStyle(
            color: Color(0xFFF5C518),
            fontWeight: FontWeight.w900,
            letterSpacing: 3,
            fontSize: 18,
          ),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 16),
            child: Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: _connected ? Colors.greenAccent : Colors.redAccent,
                  ),
                ),
                const SizedBox(width: 8),
                Text(
                  _connected ? 'Verbunden' : 'Getrennt',
                  style: TextStyle(
                    color: _connected ? Colors.greenAccent : Colors.redAccent,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              SocketService().serverUrl,
              style: const TextStyle(color: Colors.white38, fontSize: 13),
            ),
            const SizedBox(height: 24),
            const Text(
              'Server-Status',
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: Colors.white70,
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFF0D1117),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.white12),
              ),
              child: _serverState.isEmpty
                  ? const Text(
                      'Warte auf Spiel-Status...',
                      style: TextStyle(color: Colors.white38),
                    )
                  : Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: _serverState.entries
                          .map((e) => Padding(
                                padding: const EdgeInsets.symmetric(vertical: 3),
                                child: Row(
                                  children: [
                                    Text(
                                      '${e.key}:  ',
                                      style: const TextStyle(
                                          color: Colors.white38, fontSize: 13),
                                    ),
                                    Text(
                                      '${e.value}',
                                      style: const TextStyle(
                                          color: Colors.white70, fontSize: 13),
                                    ),
                                  ],
                                ),
                              ))
                          .toList(),
                    ),
            ),
            const Spacer(),
            // Phase 2: Spiel-Steuerung kommt hier
            const Center(
              child: Text(
                'Phase 2: Spiel-Steuerung folgt',
                style: TextStyle(color: Colors.white24, fontSize: 13),
              ),
            ),
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _trennen,
                icon: const Icon(Icons.logout, size: 18),
                label: const Text('Verbindung trennen'),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white38,
                  side: const BorderSide(color: Colors.white12),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
