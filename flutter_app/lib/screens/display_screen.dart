import 'package:flutter/material.dart';
import '../core/socket_service.dart';

class DisplayScreen extends StatefulWidget {
  const DisplayScreen({super.key});

  @override
  State<DisplayScreen> createState() => _DisplayScreenState();
}

class _DisplayScreenState extends State<DisplayScreen> {
  bool _connected = true;

  @override
  void initState() {
    super.initState();
    SocketService().on('connect', (_) => setState(() => _connected = true));
    SocketService().on('disconnect', (_) => setState(() => _connected = false));
    // Phase 2: Spiel-Events kommen hier dazu
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF05070D),
      body: Stack(
        children: [
          // Hintergrund-Muster
          Positioned.fill(
            child: CustomPaint(painter: _GridPainter()),
          ),
          // Inhalt
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text(
                  'SCHLAGFERTIG',
                  style: TextStyle(
                    fontSize: 64,
                    fontWeight: FontWeight.w900,
                    color: Color(0xFFF5C518),
                    letterSpacing: 8,
                  ),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Bereit für das Quiz',
                  style: TextStyle(
                    color: Colors.white38,
                    fontSize: 22,
                    letterSpacing: 3,
                  ),
                ),
              ],
            ),
          ),
          // Verbindungsstatus (unten rechts, klein)
          Positioned(
            bottom: 20,
            right: 24,
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
                  _connected
                      ? 'Verbunden · ${SocketService().serverUrl}'
                      : 'Verbindung getrennt – reconnecting...',
                  style: const TextStyle(color: Colors.white24, fontSize: 12),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withOpacity(0.025)
      ..strokeWidth = 1;
    const step = 80.0;
    for (double x = 0; x < size.width; x += step) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += step) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(_) => false;
}
