import 'package:flutter/material.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import '../../core/socket_service.dart';
import '../../core/game_state.dart';

// ── Farbpalette ──────────────────────────────────────────────────────────────
const _kGold       = Color(0xFFF5C518);
const _kGoldDim    = Color(0xFF8B7012);
const _kDark       = Color(0xFF050810);
const _kAnswerBg   = Color(0xFF080D1A);
const _kAnswerOpen = Color(0xFF0C1B30);
const _kTeamADark  = Color(0xFF0A1E50);
const _kTeamBDark  = Color(0xFF4A0A0A);
const _kTeamABrt   = Color(0xFF1E4DB8);
const _kTeamBBrt   = Color(0xFFB82020);
const _kStrike     = Color(0xFFFF2222);
const _kWhite22    = Color(0x38FFFFFF);
const _kWhite15    = Color(0x26FFFFFF);

class HundertLeuteDisplay extends StatefulWidget {
  const HundertLeuteDisplay({super.key});

  @override
  State<HundertLeuteDisplay> createState() => _HundertLeuteDisplayState();
}

class _HundertLeuteDisplayState extends State<HundertLeuteDisplay> {
  late final IO.Socket _ns;
  SpielState100Leute? _state;
  late final void Function(dynamic) _onState;

  @override
  void initState() {
    super.initState();
    _ns = SocketService().connectNamespace('/100leute');
    _onState = (data) {
      if (data is Map && mounted) {
        setState(() => _state = SpielState100Leute.fromMap(data));
      }
    };
    _ns.on('state', _onState);
  }

  @override
  void dispose() {
    // Nur diesen spezifischen Callback entfernen, nicht alle 'state'-Listener
    // (der Namespace-Socket ist geteilt – display_screen.dart hat ebenfalls einen Listener)
    _ns.off('state', _onState);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = _state;
    if (s == null || !s.beamerAktiv) return _buildIdle(s);
    return switch (s.phase) {
      'buzzerduell'             => _buildBuzzerduell(s),
      'hauptrunde' || 'stehlen' => _buildHauptrunde(s),
      'rundenende'              => _buildRundenende(s),
      'fastfive'                => _buildFastFive(s),
      'ende'                    => _buildEnde(s),
      _                         => _buildIdle(s),
    };
  }

  // ══════════════════════════════════════════════════════════════════════════
  // IDLE
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildIdle(SpielState100Leute? s) {
    return Container(
      color: _kDark,
      child: Stack(children: [
        Positioned.fill(child: CustomPaint(painter: _DotGridPainter())),
        Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            // Großer Logo-Text
            RichText(
              text: const TextSpan(
                style: TextStyle(fontSize: 80, fontWeight: FontWeight.w900, letterSpacing: 8),
                children: [
                  TextSpan(text: 'SCHLAG', style: TextStyle(color: Colors.white)),
                  TextSpan(text: 'FERTIG', style: TextStyle(color: _kGold)),
                ],
              ),
            ),
            const SizedBox(height: 10),
            const Text('100 LEUTE GEFRAGT',
                style: TextStyle(color: Colors.white38, fontSize: 22, letterSpacing: 6, fontWeight: FontWeight.w300)),
            if (s != null && (s.teamA.name != 'Team A' || s.teamB.name != 'Team B')) ...[
              const SizedBox(height: 60),
              Row(mainAxisSize: MainAxisSize.min, children: [
                _idleBadge(s.teamA.name, _kTeamABrt),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 32),
                  child: Text('VS', style: TextStyle(
                    color: Colors.white.withOpacity(0.3),
                    fontSize: 24, fontWeight: FontWeight.w900, letterSpacing: 4)),
                ),
                _idleBadge(s.teamB.name, _kTeamBBrt),
              ]),
            ],
          ]),
        ),
      ]),
    );
  }

  Widget _idleBadge(String name, Color color) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
    decoration: BoxDecoration(
      color: color.withOpacity(0.18),
      borderRadius: BorderRadius.circular(8),
      border: Border.all(color: color.withOpacity(0.6), width: 2),
    ),
    child: Text(name, style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.bold)),
  );

  // ══════════════════════════════════════════════════════════════════════════
  // BUZZERDUELL
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildBuzzerduell(SpielState100Leute s) {
    return _gameLayout(
      state: s,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _roundChip(s),
          const SizedBox(height: 32),
          if (s.aktiveFrage != null)
            _questionBox(s.aktiveFrage!.frage)
          else
            const Center(child: Text('Warten auf Frage…',
                style: TextStyle(color: Colors.white38, fontSize: 28))),
          const SizedBox(height: 48),
          _buildBuzzerStatus(s),
        ],
      ),
    );
  }

  Widget _buildBuzzerStatus(SpielState100Leute s) {
    final d = s.duell;
    if (d.gewinner != null) {
      final w = s.teamFor(d.gewinner!);
      final c = d.gewinner == 'A' ? _kTeamABrt : _kTeamBBrt;
      return Center(child: Column(children: [
        const Text('GEWINNER DES DUELLS',
            style: TextStyle(color: Colors.white38, fontSize: 16, letterSpacing: 4)),
        const SizedBox(height: 12),
        Text(w.name, style: TextStyle(color: c, fontSize: 52, fontWeight: FontWeight.w900, letterSpacing: 2)),
      ]));
    }
    if (d.ersterTeam != null) {
      final t = s.teamFor(d.ersterTeam!);
      final c = d.ersterTeam == 'A' ? _kTeamABrt : _kTeamBBrt;
      return Center(child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 20),
        decoration: BoxDecoration(
          color: c.withOpacity(0.2),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: c, width: 2),
        ),
        child: Text('${t.name} hat gebuzzt!',
            style: const TextStyle(color: Colors.white, fontSize: 32, fontWeight: FontWeight.bold)),
      ));
    }
    if (d.buzzerOffen) {
      return Center(child: _PulseWidget(
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 56, vertical: 22),
          decoration: BoxDecoration(
            color: _kGold.withOpacity(0.1),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: _kGold, width: 2.5),
          ),
          child: const Text('BUZZER OFFEN',
              style: TextStyle(color: _kGold, fontSize: 38, fontWeight: FontWeight.w900, letterSpacing: 6)),
        ),
      ));
    }
    return const Center(child: Text('Warten auf Moderator…',
        style: TextStyle(color: Colors.white24, fontSize: 20)));
  }

  // ══════════════════════════════════════════════════════════════════════════
  // HAUPTRUNDE / STEHLEN
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildHauptrunde(SpielState100Leute s) {
    final frage = s.aktiveFrage;
    return _gameLayout(
      state: s,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ── Kopfzeile: Runde + Topf ──────────────────────────
          _buildHauptrundHeader(s),
          const SizedBox(height: 14),
          // ── Frage ──────────────────────────────────────────────
          if (frage != null) _questionBox(frage.frage),
          const SizedBox(height: 14),
          // ── Antwort-Board (füllt restlichen Platz) ─────────────
          if (frage != null)
            Expanded(
              child: Column(
                children: List.generate(
                  frage.antworten.length,
                  (i) => Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: _buildAntwortRow(i, frage.antworten[i]),
                    ),
                  ),
                ),
              ),
            )
          else
            const Expanded(child: SizedBox()),
          // ── Fußzeile: Strikes + Stehlen-Badge ──────────────────
          const SizedBox(height: 10),
          _buildStreikenBar(s),
        ],
      ),
    );
  }

  Widget _buildHauptrundHeader(SpielState100Leute s) {
    return Row(children: [
      Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.06),
          borderRadius: BorderRadius.circular(6),
        ),
        child: Text('RUNDE ${s.runde} / ${s.config.runden}',
            style: const TextStyle(color: Colors.white54, fontSize: 16, letterSpacing: 3, fontWeight: FontWeight.w500)),
      ),
      const Spacer(),
      if (s.phase == 'stehlen')
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 6),
          decoration: BoxDecoration(
            color: Colors.orange.withOpacity(0.2),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: Colors.orange.withOpacity(0.8), width: 1.5),
          ),
          child: const Text('STEHLEN',
              style: TextStyle(color: Colors.orange, fontSize: 17, fontWeight: FontWeight.w900, letterSpacing: 3)),
        ),
      const Spacer(),
      Column(crossAxisAlignment: CrossAxisAlignment.end, children: [
        const Text('TOPF', style: TextStyle(color: Colors.white38, fontSize: 12, letterSpacing: 3)),
        Text('${s.rundentopf} PKT',
            style: const TextStyle(color: _kGold, fontSize: 22, fontWeight: FontWeight.w900, letterSpacing: 1)),
      ]),
    ]);
  }

  Widget _buildAntwortRow(int idx, Antwort a) {
    return AnimatedContainer(
      duration: const Duration(milliseconds: 500),
      curve: Curves.easeOut,
      decoration: BoxDecoration(
        color: a.auf ? _kAnswerOpen : _kAnswerBg,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: a.auf ? _kGold.withOpacity(0.75) : Colors.white.withOpacity(0.07),
          width: a.auf ? 1.5 : 1.0,
        ),
        boxShadow: a.auf
            ? [BoxShadow(color: _kGold.withOpacity(0.12), blurRadius: 12, spreadRadius: 0)]
            : null,
      ),
      child: Row(children: [
        // Nummer-Badge
        Container(
          width: 56,
          margin: const EdgeInsets.all(6),
          decoration: BoxDecoration(
            color: a.auf ? _kGold.withOpacity(0.15) : Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(5),
          ),
          alignment: Alignment.center,
          child: Text('${idx + 1}',
              style: TextStyle(
                color: a.auf ? _kGold : Colors.white30,
                fontSize: 20,
                fontWeight: FontWeight.w900,
              )),
        ),
        // Antwort-Text
        Expanded(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8),
            child: Text(
              a.auf ? a.text.toUpperCase() : '— — —',
              style: TextStyle(
                color: a.auf ? Colors.white : _kWhite22,
                fontSize: 22,
                fontWeight: a.auf ? FontWeight.w700 : FontWeight.w400,
                letterSpacing: a.auf ? 0.5 : 2,
              ),
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ),
        // Punkte
        Container(
          width: 72,
          alignment: Alignment.center,
          padding: const EdgeInsets.symmetric(horizontal: 8),
          child: Text(
            a.auf ? '${a.punkte}' : '?',
            style: TextStyle(
              color: a.auf ? _kGold : _kWhite15,
              fontSize: 26,
              fontWeight: FontWeight.w900,
            ),
          ),
        ),
      ]),
    );
  }

  Widget _buildStreikenBar(SpielState100Leute s) {
    return Row(children: [
      // Strike-Symbole
      Row(children: List.generate(3, (i) {
        final hit = i < s.strikes;
        return Padding(
          padding: const EdgeInsets.only(right: 10),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 300),
            width: 44, height: 44,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: hit ? _kStrike.withOpacity(0.25) : Colors.white.withOpacity(0.05),
              border: Border.all(
                color: hit ? _kStrike : Colors.white24,
                width: 2,
              ),
            ),
            child: Center(
              child: Text(hit ? '✕' : '',
                  style: TextStyle(
                    color: hit ? _kStrike : Colors.transparent,
                    fontSize: 20, fontWeight: FontWeight.w900)),
            ),
          ),
        );
      })),
    ]);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // RUNDENENDE
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildRundenende(SpielState100Leute s) {
    final re = s.rundenende;
    final isA = re?.gewinner == 'A';
    final winnerName = re?.gewinner != null ? s.teamFor(re!.gewinner!).name : '—';
    final color = isA ? _kTeamABrt : _kTeamBBrt;
    return Container(
      color: _kDark,
      child: Stack(children: [
        Positioned.fill(child: CustomPaint(painter: _DotGridPainter())),
        Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Text('RUNDE GEWONNEN',
                style: TextStyle(color: Colors.white38, fontSize: 18, letterSpacing: 5)),
            const SizedBox(height: 20),
            Text(winnerName,
                style: TextStyle(color: color, fontSize: 68, fontWeight: FontWeight.w900, letterSpacing: 2)),
            const SizedBox(height: 28),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 18),
              decoration: BoxDecoration(
                color: _kGold.withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: _kGold, width: 2),
              ),
              child: Text('+${re?.topf ?? 0} Punkte',
                  style: const TextStyle(color: _kGold, fontSize: 36, fontWeight: FontWeight.w900)),
            ),
            const SizedBox(height: 56),
            Row(mainAxisSize: MainAxisSize.min, children: [
              _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABrt, highlight: isA),
              const SizedBox(width: 48),
              _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBrt, highlight: !isA),
            ]),
          ]),
        ),
      ]),
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // FAST FIVE
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildFastFive(SpielState100Leute s) {
    final ff = s.ff;
    if (ff == null) {
      return Container(
        color: _kDark,
        child: Center(child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Text('FAST', style: TextStyle(color: Colors.white38, fontSize: 28, letterSpacing: 8, fontWeight: FontWeight.w300)),
          const Text('FIVE', style: TextStyle(color: _kGold, fontSize: 80, fontWeight: FontWeight.w900, letterSpacing: 12)),
          const SizedBox(height: 48),
          Row(mainAxisSize: MainAxisSize.min, children: [
            _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABrt),
            const SizedBox(width: 48),
            _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBrt),
          ]),
        ])),
      );
    }

    final dranColor = ff.dran == 'A' ? _kTeamABrt : _kTeamBBrt;
    final dranName  = s.teamFor(ff.dran).name;
    final maxZeit   = (ff.dran == 'A' ? s.config.ffZeit1 : s.config.ffZeit2).toDouble();
    final zeitRatio = maxZeit > 0 ? (ff.timerRest / maxZeit).clamp(0.0, 1.0) : 0.0;
    final timerWarn = ff.timerRest <= 5 && ff.timerRest > 0;

    return _gameLayout(
      state: s,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
              decoration: BoxDecoration(
                color: dranColor.withOpacity(0.2),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: dranColor, width: 2),
              ),
              child: Text('FAST FIVE · $dranName',
                  style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w900,
                      fontSize: 20, letterSpacing: 2)),
            ),
            const Spacer(),
            if (ff.timerLaueft || ff.timerRest > 0) ...[
              Text('${ff.timerRest}s',
                  style: TextStyle(
                    color: timerWarn ? _kStrike : Colors.white70,
                    fontSize: timerWarn ? 40 : 32,
                    fontWeight: FontWeight.w900,
                  )),
            ],
          ]),
          // Timer-Bar
          if (ff.timerLaueft || ff.timerRest > 0) ...[
            const SizedBox(height: 10),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: zeitRatio,
                backgroundColor: Colors.white12,
                color: timerWarn ? _kStrike : _kGold,
                minHeight: 10,
              ),
            ),
          ],
          const SizedBox(height: 14),
          // Frage
          if (ff.aktuelleFrage != null) ...[
            _questionBox(ff.aktuelleFrage!.frage),
            const SizedBox(height: 14),
            // Antworten
            Expanded(
              child: Column(
                children: List.generate(ff.aktuelleFrage!.antworten.length, (i) {
                  final a = ff.aktuelleFrage!.antworten[i];
                  final tColor = a.von == 'A' ? _kTeamABrt : _kTeamBBrt;
                  return Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(vertical: 3),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 400),
                        decoration: BoxDecoration(
                          color: a.auf
                              ? (a.von == 'A' ? _kTeamADark.withOpacity(0.6) : _kTeamBDark.withOpacity(0.6))
                              : _kAnswerBg,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                            color: a.auf ? tColor.withOpacity(0.7) : Colors.white.withOpacity(0.07),
                            width: a.auf ? 1.5 : 1.0,
                          ),
                        ),
                        child: Row(children: [
                          Container(
                            width: 56,
                            margin: const EdgeInsets.all(6),
                            decoration: BoxDecoration(
                              color: a.auf ? tColor.withOpacity(0.2) : Colors.white.withOpacity(0.05),
                              borderRadius: BorderRadius.circular(5),
                            ),
                            alignment: Alignment.center,
                            child: Text('${i + 1}',
                                style: TextStyle(
                                  color: a.auf ? tColor : Colors.white30,
                                  fontSize: 20, fontWeight: FontWeight.w900)),
                          ),
                          Expanded(
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Text(
                                a.auf ? a.text.toUpperCase() : '— — —',
                                style: TextStyle(
                                  color: a.auf ? Colors.white : _kWhite22,
                                  fontSize: 22, fontWeight: a.auf ? FontWeight.w700 : FontWeight.w400),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ),
                          Container(
                            width: 72,
                            alignment: Alignment.center,
                            child: Text(a.auf ? '${a.punkte}' : '?',
                                style: TextStyle(
                                  color: a.auf ? _kGold : _kWhite15,
                                  fontSize: 26, fontWeight: FontWeight.w900)),
                          ),
                        ]),
                      ),
                    ),
                  );
                }),
              ),
            ),
          ] else
            const Expanded(child: Center(
              child: Text('Nächste Frage…',
                  style: TextStyle(color: Colors.white24, fontSize: 28)),
            )),
          const SizedBox(height: 10),
          // FF-Punkte
          Row(children: [
            Text('A: ${ff.punkteA} Pkt',
                style: TextStyle(
                    color: ff.dran == 'A' ? _kTeamABrt : Colors.white38,
                    fontWeight: FontWeight.bold, fontSize: 18)),
            const Spacer(),
            Text('B: ${ff.punkteB} Pkt',
                style: TextStyle(
                    color: ff.dran == 'B' ? _kTeamBBrt : Colors.white38,
                    fontWeight: FontWeight.bold, fontSize: 18)),
          ]),
        ],
      ),
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ENDE
  // ══════════════════════════════════════════════════════════════════════════
  Widget _buildEnde(SpielState100Leute s) {
    final aWins = s.teamA.punkte > s.teamB.punkte;
    final draw  = s.teamA.punkte == s.teamB.punkte;
    final winnerColor = aWins ? _kTeamABrt : _kTeamBBrt;
    return Container(
      color: _kDark,
      child: Stack(children: [
        Positioned.fill(child: CustomPaint(painter: _DotGridPainter())),
        Center(
          child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
            const Text('SPIELENDE',
                style: TextStyle(color: Colors.white38, fontSize: 18, letterSpacing: 6)),
            const SizedBox(height: 28),
            if (draw)
              const Text('UNENTSCHIEDEN',
                  style: TextStyle(color: _kGold, fontSize: 56, fontWeight: FontWeight.w900, letterSpacing: 3))
            else ...[
              Text(aWins ? s.teamA.name : s.teamB.name,
                  style: TextStyle(color: winnerColor, fontSize: 68, fontWeight: FontWeight.w900, letterSpacing: 2)),
              const SizedBox(height: 8),
              const Text('S I E G T !',
                  style: TextStyle(color: _kGold, fontSize: 26, fontWeight: FontWeight.w900, letterSpacing: 10)),
            ],
            const SizedBox(height: 56),
            Row(mainAxisSize: MainAxisSize.min, children: [
              _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamABrt, highlight: aWins && !draw),
              const SizedBox(width: 56),
              _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamBBrt, highlight: !aWins && !draw),
            ]),
          ]),
        ),
      ]),
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // SHARED LAYOUT — Seitenpanels + Mitte
  // ══════════════════════════════════════════════════════════════════════════
  Widget _gameLayout({required SpielState100Leute state, required Widget child}) {
    return Row(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      // Team A — links
      SizedBox(width: 220, child: _buildTeamPanel(state.teamA, 'A', state.aktivesTeam == 'A')),
      // Mittiger Inhalt
      Expanded(
        child: Container(
          color: _kDark,
          padding: const EdgeInsets.fromLTRB(28, 24, 28, 20),
          child: child,
        ),
      ),
      // Team B — rechts
      SizedBox(width: 220, child: _buildTeamPanel(state.teamB, 'B', state.aktivesTeam == 'B')),
    ]);
  }

  Widget _buildTeamPanel(Team team, String key, bool active) {
    final bright = key == 'A' ? _kTeamABrt : _kTeamBBrt;
    final dark   = key == 'A' ? _kTeamADark : _kTeamBDark;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 400),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: active
              ? [bright.withOpacity(0.55), dark.withOpacity(0.7)]
              : [dark.withOpacity(0.5), _kDark.withOpacity(0.9)],
        ),
        border: Border(
          right: key == 'A' ? BorderSide(color: active ? bright.withOpacity(0.5) : Colors.white12, width: 1) : BorderSide.none,
          left:  key == 'B' ? BorderSide(color: active ? bright.withOpacity(0.5) : Colors.white12, width: 1) : BorderSide.none,
        ),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 28),
      child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
        // "AM ZUG" Badge
        AnimatedOpacity(
          duration: const Duration(milliseconds: 400),
          opacity: active ? 1.0 : 0.0,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 5),
            margin: const EdgeInsets.only(bottom: 14),
            decoration: BoxDecoration(
              color: _kGold.withOpacity(0.2),
              borderRadius: BorderRadius.circular(5),
              border: Border.all(color: _kGold.withOpacity(0.7), width: 1.5),
            ),
            child: const Text('AM ZUG',
                style: TextStyle(color: _kGold, fontSize: 13, fontWeight: FontWeight.w900, letterSpacing: 3)),
          ),
        ),
        // TEAM A / B Label
        Text('TEAM $key',
            style: TextStyle(color: bright.withOpacity(active ? 0.9 : 0.5), fontSize: 13,
                fontWeight: FontWeight.w900, letterSpacing: 4)),
        const SizedBox(height: 8),
        // Team-Name
        Text(team.name,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: active ? Colors.white : Colors.white60,
              fontSize: 20,
              fontWeight: FontWeight.bold,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis),
        const SizedBox(height: 28),
        // Punktzahl — groß
        Text('${team.punkte}',
            style: TextStyle(
              color: active ? _kGold : Colors.white60,
              fontSize: 72,
              fontWeight: FontWeight.w900,
              height: 1.0,
            )),
        const SizedBox(height: 4),
        Text('PUNKTE',
            style: TextStyle(color: active ? Colors.white38 : Colors.white24,
                fontSize: 12, letterSpacing: 4)),
      ]),
    );
  }

  // ══════════════════════════════════════════════════════════════════════════
  // HILFSMETHODEN
  // ══════════════════════════════════════════════════════════════════════════

  Widget _roundChip(SpielState100Leute s) => Center(
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 7),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.06),
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text('RUNDE ${s.runde} / ${s.config.runden}',
          style: const TextStyle(color: Colors.white54, fontSize: 16, letterSpacing: 4, fontWeight: FontWeight.w500)),
    ),
  );

  Widget _questionBox(String frage) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.06),
      borderRadius: BorderRadius.circular(10),
      border: Border.all(color: Colors.white.withOpacity(0.1), width: 1),
    ),
    child: Text(frage,
        textAlign: TextAlign.center,
        style: const TextStyle(
          color: Colors.white,
          fontSize: 28,
          fontWeight: FontWeight.w600,
          height: 1.35,
        )),
  );

  Widget _scoreTile(String name, int pts, Color color, {bool highlight = false}) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 20),
    decoration: BoxDecoration(
      color: color.withOpacity(highlight ? 0.3 : 0.15),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: color, width: highlight ? 2.5 : 1.5),
      boxShadow: highlight ? [BoxShadow(color: color.withOpacity(0.3), blurRadius: 20)] : null,
    ),
    child: Column(children: [
      Text(name, style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
      const SizedBox(height: 6),
      Text('$pts', style: TextStyle(color: color, fontSize: 52, fontWeight: FontWeight.w900, height: 1.0)),
      const SizedBox(height: 2),
      const Text('Pkt', style: TextStyle(color: Colors.white38, fontSize: 14)),
    ]),
  );
}

// ── Pulsierender Container (Buzzer-Offen-Indikator) ──────────────────────────
class _PulseWidget extends StatefulWidget {
  final Widget child;
  const _PulseWidget({required this.child});

  @override
  State<_PulseWidget> createState() => _PulseWidgetState();
}

class _PulseWidgetState extends State<_PulseWidget> with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  late final Animation<double> _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(vsync: this, duration: const Duration(milliseconds: 900))..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.65, end: 1.0).animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => FadeTransition(opacity: _anim, child: widget.child);
}

// ── Hintergrund-Punktraster ───────────────────────────────────────────────────
class _DotGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = Colors.white.withOpacity(0.04)..strokeWidth = 0;
    const step = 72.0;
    for (double x = step; x < size.width; x += step) {
      for (double y = step; y < size.height; y += step) {
        canvas.drawCircle(Offset(x, y), 1.5, paint);
      }
    }
  }

  @override
  bool shouldRepaint(_) => false;
}
