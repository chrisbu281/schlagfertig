import 'package:flutter/material.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import '../../core/socket_service.dart';
import '../../core/game_state.dart';

const _kGold = Color(0xFFF5C518);
const _kDark = Color(0xFF05070D);
const _kPanel = Color(0xFF0D1117);
const _kTeamA = Color(0xFF0F2B6B);
const _kTeamB = Color(0xFF6B0F0F);
const _kTeamABright = Color(0xFF1E4DB8);
const _kTeamBBright = Color(0xFFB82020);

class HundertLeuteDisplay extends StatefulWidget {
  const HundertLeuteDisplay({super.key});

  @override
  State<HundertLeuteDisplay> createState() => _HundertLeuteDisplayState();
}

class _HundertLeuteDisplayState extends State<HundertLeuteDisplay> {
  late final IO.Socket _ns;
  SpielState100Leute? _state;

  @override
  void initState() {
    super.initState();
    _ns = SocketService().connectNamespace('/100leute');
    _ns.on('state', (data) {
      if (data is Map && mounted) {
        setState(() => _state = SpielState100Leute.fromMap(data));
      }
    });
  }

  @override
  void dispose() {
    _ns.off('state');
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = _state;
    if (s == null || !s.beamerAktiv) return _buildIdle(s);
    return switch (s.phase) {
      'buzzerduell' => _buildBuzzerduell(s),
      'hauptrunde' || 'stehlen' => _buildHauptrunde(s),
      'rundenende' => _buildRundenende(s),
      'fastfive' => _buildFastFive(s),
      'ende' => _buildEnde(s),
      _ => _buildIdle(s),
    };
  }

  // ── Idle / Setup ────────────────────────────────────────────────────
  Widget _buildIdle(SpielState100Leute? s) {
    return Container(
      color: _kDark,
      child: Stack(
        children: [
          Positioned.fill(child: CustomPaint(painter: _GridPainter())),
          Center(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                const Text('SCHLAGFERTIG',
                    style: TextStyle(fontSize: 72, fontWeight: FontWeight.w900, color: _kGold, letterSpacing: 10)),
                const SizedBox(height: 12),
                const Text('100 LEUTE GEFRAGT',
                    style: TextStyle(fontSize: 22, color: Colors.white38, letterSpacing: 4)),
                if (s != null && (s.teamA.name != 'Team A' || s.teamB.name != 'Team B')) ...[
                  const SizedBox(height: 48),
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _teamBadge(s.teamA.name, _kTeamABright),
                      const SizedBox(width: 32),
                      const Text('VS', style: TextStyle(color: Colors.white38, fontWeight: FontWeight.bold, fontSize: 20)),
                      const SizedBox(width: 32),
                      _teamBadge(s.teamB.name, _kTeamBBright),
                    ],
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _teamBadge(String name, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
        decoration: BoxDecoration(color: color.withOpacity(0.3), borderRadius: BorderRadius.circular(8), border: Border.all(color: color, width: 1.5)),
        child: Text(name, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
      );

  // ── Buzzerduell ─────────────────────────────────────────────────────
  Widget _buildBuzzerduell(SpielState100Leute s) {
    final d = s.duell;
    return _gameLayout(
      state: s,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _roundBadge(s),
          const SizedBox(height: 24),
          if (s.aktiveFrage != null)
            _questionText(s.aktiveFrage!.frage)
          else
            const Text('Warten auf Frage…', style: TextStyle(color: Colors.white38, fontSize: 24)),
          const SizedBox(height: 40),
          _buildBuzzerStatus(s, d),
        ],
      ),
    );
  }

  Widget _buildBuzzerStatus(SpielState100Leute s, DuellState d) {
    if (d.gewinner != null) {
      final w = s.teamFor(d.gewinner!);
      return Column(children: [
        const Text('GEWINNER DES DUELLS', style: TextStyle(color: Colors.white38, fontSize: 14, letterSpacing: 3)),
        const SizedBox(height: 8),
        Text(w.name, style: const TextStyle(color: _kGold, fontSize: 40, fontWeight: FontWeight.w900, letterSpacing: 2)),
      ]);
    }
    if (d.ersterTeam != null) {
      final t = s.teamFor(d.ersterTeam!);
      final color = d.ersterTeam == 'A' ? _kTeamABright : _kTeamBBright;
      return Column(children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 16),
          decoration: BoxDecoration(color: color.withOpacity(0.25), borderRadius: BorderRadius.circular(12), border: Border.all(color: color, width: 2)),
          child: Text('${t.name} hat gebuzzt!', style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.bold)),
        ),
      ]);
    }
    if (d.buzzerOffen) {
      return TweenAnimationBuilder<double>(
        tween: Tween(begin: 0.6, end: 1.0),
        duration: const Duration(milliseconds: 800),
        builder: (_, v, child) => Opacity(opacity: v, child: child),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 40, vertical: 18),
          decoration: BoxDecoration(
            color: _kGold.withOpacity(0.12),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _kGold, width: 2),
          ),
          child: const Text('BUZZER OFFEN', style: TextStyle(color: _kGold, fontSize: 30, fontWeight: FontWeight.w900, letterSpacing: 4)),
        ),
      );
    }
    return const Text('Warten auf Moderator…', style: TextStyle(color: Colors.white24, fontSize: 18));
  }

  // ── Hauptrunde / Stehlen ────────────────────────────────────────────
  Widget _buildHauptrunde(SpielState100Leute s) {
    return _gameLayout(
      state: s,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _roundBadge(s),
          const SizedBox(height: 12),
          if (s.aktiveFrage != null) _questionText(s.aktiveFrage!.frage),
          const SizedBox(height: 16),
          if (s.aktiveFrage != null) ...[
            ...List.generate(
              s.aktiveFrage!.antworten.length,
              (i) => _buildAntwortRow(i, s.aktiveFrage!.antworten[i]),
            ),
          ],
          const SizedBox(height: 16),
          Row(
            children: [
              Row(children: List.generate(3, (i) => Padding(
                padding: const EdgeInsets.only(right: 8),
                child: Text(i < s.strikes ? '❌' : '○',
                    style: TextStyle(fontSize: 28, color: i < s.strikes ? Colors.redAccent : Colors.white24)),
              ))),
              const Spacer(),
              if (s.phase == 'stehlen')
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                  decoration: BoxDecoration(color: Colors.orange.withOpacity(0.2), borderRadius: BorderRadius.circular(6), border: Border.all(color: Colors.orange, width: 1.5)),
                  child: const Text('STEHLEN', style: TextStyle(color: Colors.orange, fontWeight: FontWeight.bold, letterSpacing: 3)),
                ),
              const Spacer(),
              Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
                const Text('TOPF', style: TextStyle(color: Colors.white38, fontSize: 11, letterSpacing: 2)),
                Text('${s.rundentopf} Pkt', style: const TextStyle(color: _kGold, fontWeight: FontWeight.bold, fontSize: 20)),
              ]),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAntwortRow(int idx, Antwort a) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      margin: const EdgeInsets.symmetric(vertical: 3),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
      decoration: BoxDecoration(
        color: a.auf ? const Color(0xFF0D1A2A) : const Color(0xFF080B12),
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: a.auf ? _kGold.withOpacity(0.7) : Colors.white12, width: 1.5),
      ),
      child: Row(children: [
        SizedBox(
          width: 28,
          child: Text('${idx + 1}', style: TextStyle(color: a.auf ? _kGold : Colors.white24, fontWeight: FontWeight.bold, fontSize: 16)),
        ),
        Expanded(
          child: Text(a.auf ? a.text : '? ? ?',
              style: TextStyle(color: a.auf ? Colors.white : Colors.white24, fontSize: 17, fontWeight: a.auf ? FontWeight.w600 : FontWeight.normal)),
        ),
        Text(a.auf ? '${a.punkte}' : '??',
            style: TextStyle(color: a.auf ? _kGold : Colors.white12, fontWeight: FontWeight.bold, fontSize: 20)),
      ]),
    );
  }

  // ── Rundenende ──────────────────────────────────────────────────────
  Widget _buildRundenende(SpielState100Leute s) {
    final re = s.rundenende;
    final winnerName = re?.gewinner != null ? s.teamFor(re!.gewinner!).name : '—';
    final color = re?.gewinner == 'A' ? _kTeamABright : _kTeamBBright;
    return Container(
      color: _kDark,
      child: Center(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Text('RUNDE GEWONNEN', style: TextStyle(color: Colors.white38, fontSize: 16, letterSpacing: 4)),
          const SizedBox(height: 16),
          Text(winnerName, style: TextStyle(color: color, fontSize: 56, fontWeight: FontWeight.w900, letterSpacing: 2)),
          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
            decoration: BoxDecoration(color: _kGold.withOpacity(0.1), borderRadius: BorderRadius.circular(10), border: Border.all(color: _kGold, width: 1.5)),
            child: Text('+${re?.topf ?? 0} Punkte', style: const TextStyle(color: _kGold, fontSize: 32, fontWeight: FontWeight.bold)),
          ),
          const SizedBox(height: 48),
          Row(mainAxisSize: MainAxisSize.min, children: [
            _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABright),
            const SizedBox(width: 40),
            _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBright),
          ]),
        ]),
      ),
    );
  }

  // ── FastFive ────────────────────────────────────────────────────────
  Widget _buildFastFive(SpielState100Leute s) {
    final ff = s.ff;
    if (ff == null) {
      return Container(
        color: _kDark,
        child: Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Text('FAST FIVE', style: TextStyle(color: _kGold, fontSize: 48, fontWeight: FontWeight.w900, letterSpacing: 6)),
          const SizedBox(height: 16),
          Row(mainAxisSize: MainAxisSize.min, children: [
            _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABright),
            const SizedBox(width: 40),
            _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBright),
          ]),
        ])),
      );
    }
    final frage = ff.aktuelleFrage;
    final dranColor = ff.dran == 'A' ? _kTeamABright : _kTeamBBright;
    final dranName = s.teamFor(ff.dran).name;
    return Container(
      color: _kDark,
      padding: const EdgeInsets.all(32),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
            decoration: BoxDecoration(color: dranColor.withOpacity(0.25), borderRadius: BorderRadius.circular(8), border: Border.all(color: dranColor, width: 2)),
            child: Text('FAST FIVE · $dranName', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18, letterSpacing: 2)),
          ),
          const Spacer(),
          Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
            Text('A: ${ff.punkteA} Pkt', style: TextStyle(color: ff.dran == 'A' ? _kTeamABright : Colors.white38, fontWeight: FontWeight.bold)),
            Text('B: ${ff.punkteB} Pkt', style: TextStyle(color: ff.dran == 'B' ? _kTeamBBright : Colors.white38, fontWeight: FontWeight.bold)),
          ]),
        ]),
        const SizedBox(height: 16),
        if (ff.timerLaueft || ff.timerRest > 0) ...[
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: ff.timerRest / (ff.dran == 'A' ? s.config.ffZeit1 : s.config.ffZeit2).toDouble().clamp(0.0, 1.0),
              backgroundColor: Colors.white12,
              color: ff.timerRest < 5 ? Colors.redAccent : _kGold,
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 8),
          Align(alignment: Alignment.centerRight,
              child: Text('${ff.timerRest}s', style: TextStyle(color: ff.timerRest < 5 ? Colors.redAccent : Colors.white54, fontWeight: FontWeight.bold))),
          const SizedBox(height: 8),
        ],
        if (frage != null) ...[
          _questionText(frage.frage),
          const SizedBox(height: 16),
          ...List.generate(frage.antworten.length, (i) {
            final a = frage.antworten[i];
            return AnimatedContainer(
              duration: const Duration(milliseconds: 400),
              margin: const EdgeInsets.symmetric(vertical: 3),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
              decoration: BoxDecoration(
                color: a.auf ? (a.von == 'A' ? _kTeamA.withOpacity(0.4) : _kTeamB.withOpacity(0.4)) : const Color(0xFF080B12),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: a.auf ? _kGold.withOpacity(0.7) : Colors.white12, width: 1.5),
              ),
              child: Row(children: [
                SizedBox(width: 28, child: Text('${i + 1}', style: TextStyle(color: a.auf ? _kGold : Colors.white24, fontWeight: FontWeight.bold))),
                Expanded(child: Text(a.auf ? a.text : '? ? ?', style: TextStyle(color: a.auf ? Colors.white : Colors.white24, fontSize: 16, fontWeight: a.auf ? FontWeight.w600 : FontWeight.normal))),
                Text(a.auf ? '${a.punkte}' : '??', style: TextStyle(color: a.auf ? _kGold : Colors.white12, fontWeight: FontWeight.bold, fontSize: 18)),
              ]),
            );
          }),
        ],
      ]),
    );
  }

  // ── Ende ────────────────────────────────────────────────────────────
  Widget _buildEnde(SpielState100Leute s) {
    final aWins = s.teamA.punkte > s.teamB.punkte;
    final draw = s.teamA.punkte == s.teamB.punkte;
    return Container(
      color: _kDark,
      child: Center(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Text('SPIELENDE', style: TextStyle(color: Colors.white38, fontSize: 16, letterSpacing: 5)),
          const SizedBox(height: 24),
          if (!draw)
            Text(aWins ? s.teamA.name : s.teamB.name,
                style: TextStyle(color: aWins ? _kTeamABright : _kTeamBBright, fontSize: 60, fontWeight: FontWeight.w900, letterSpacing: 2)),
          if (draw) const Text('UNENTSCHIEDEN', style: TextStyle(color: _kGold, fontSize: 48, fontWeight: FontWeight.w900)),
          if (!draw) const Text('SIEGT!', style: TextStyle(color: _kGold, fontSize: 28, fontWeight: FontWeight.bold, letterSpacing: 4)),
          const SizedBox(height: 48),
          Row(mainAxisSize: MainAxisSize.min, children: [
            _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABright),
            const SizedBox(width: 48),
            _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBright),
          ]),
        ]),
      ),
    );
  }

  // ── Shared layout ───────────────────────────────────────────────────
  Widget _gameLayout({required SpielState100Leute state, required Widget child}) {
    final isAActive = state.aktivesTeam == 'A';
    final isBActive = state.aktivesTeam == 'B';
    return Stack(children: [
      Positioned.fill(child: Row(children: [
        Expanded(child: Container(color: (isAActive ? _kTeamABright : _kTeamA).withOpacity(isAActive ? 0.3 : 0.15))),
        Expanded(child: Container(color: (isBActive ? _kTeamBBright : _kTeamB).withOpacity(isBActive ? 0.3 : 0.15))),
      ])),
      Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SizedBox(width: 200, child: _buildTeamPanel(state.teamA, 'A', state.aktivesTeam == 'A')),
        Expanded(
          child: Container(
            color: _kDark.withOpacity(0.85),
            padding: const EdgeInsets.all(24),
            child: child,
          ),
        ),
        SizedBox(width: 200, child: _buildTeamPanel(state.teamB, 'B', state.aktivesTeam == 'B')),
      ]),
    ]);
  }

  Widget _buildTeamPanel(Team team, String key, bool active) {
    final color = key == 'A' ? (active ? _kTeamABright : _kTeamA) : (active ? _kTeamBBright : _kTeamB);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      color: color.withOpacity(active ? 0.55 : 0.3),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        if (active)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            margin: const EdgeInsets.only(bottom: 8),
            decoration: BoxDecoration(color: _kGold.withOpacity(0.15), borderRadius: BorderRadius.circular(4), border: Border.all(color: _kGold.withOpacity(0.6))),
            child: const Text('AM ZUG', style: TextStyle(color: _kGold, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 2)),
          ),
        Text('TEAM $key', style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 3)),
        const SizedBox(height: 4),
        Text(team.name,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
            maxLines: 2,
            overflow: TextOverflow.ellipsis),
        const SizedBox(height: 24),
        Text('${team.punkte}', style: const TextStyle(color: _kGold, fontSize: 52, fontWeight: FontWeight.w900)),
        const Text('PUNKTE', style: TextStyle(color: Colors.white38, fontSize: 11, letterSpacing: 3)),
      ]),
    );
  }

  Widget _roundBadge(SpielState100Leute s) => Row(mainAxisAlignment: MainAxisAlignment.center, children: [
        Text('RUNDE ${s.runde} / ${s.config.runden}',
            style: const TextStyle(color: Colors.white38, fontSize: 13, letterSpacing: 3)),
      ]);

  Widget _questionText(String q) => Text(q,
      textAlign: TextAlign.center,
      style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w600, height: 1.3));

  Widget _scoreTile(String name, int pts, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
        decoration: BoxDecoration(color: color.withOpacity(0.25), borderRadius: BorderRadius.circular(10), border: Border.all(color: color, width: 2)),
        child: Column(children: [
          Text(name, style: const TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
          const SizedBox(height: 4),
          Text('$pts', style: TextStyle(color: color, fontSize: 40, fontWeight: FontWeight.w900)),
          const Text('Pkt', style: TextStyle(color: Colors.white38, fontSize: 13)),
        ]),
      );
}

class _GridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white.withOpacity(0.025)..strokeWidth = 1;
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
