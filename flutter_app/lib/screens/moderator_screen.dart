import 'package:flutter/material.dart';
import '../core/socket_service.dart';
import '../games/hundert_leute/hundert_leute_moderator.dart';
import 'startup_screen.dart';

class ModeratorScreen extends StatefulWidget {
  const ModeratorScreen({super.key});

  @override
  State<ModeratorScreen> createState() => _ModeratorScreenState();
}

class _ModeratorScreenState extends State<ModeratorScreen> {
  bool _connected = true;

  @override
  void initState() {
    super.initState();
    SocketService().on('connect', (_) => setState(() => _connected = true));
    SocketService().on('disconnect', (_) => setState(() => _connected = false));
  }

  @override
  void dispose() {
    SocketService().off('connect');
    SocketService().off('disconnect');
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
          style: TextStyle(color: Color(0xFFF5C518), fontWeight: FontWeight.w900, letterSpacing: 3, fontSize: 18),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: Row(children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _connected ? Colors.greenAccent : Colors.redAccent,
                ),
              ),
              const SizedBox(width: 8),
              TextButton(
                onPressed: _trennen,
                child: const Text('Trennen', style: TextStyle(color: Colors.white38, fontSize: 12)),
              ),
            ]),
          ),
        ],
      ),
      body: const HundertLeuteModeratorView(),
    );
  }
}
