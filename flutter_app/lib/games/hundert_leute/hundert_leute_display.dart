import 'dart:math' show pi;
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import '../../core/socket_service.dart';
import '../../core/game_state.dart';

// ── Farben ───────────────────────────────────────────────────────────────────
const _kGold   = Color(0xFFF5C518);
const _kDark   = Color(0xFF05070D);
const _kTeamA  = Color(0xFF2F6FED);
const _kTeamB  = Color(0xFFE0473A);

TextStyle _bc(double size, FontWeight weight, Color color,
    {double? letterSpacing, double? height}) =>
    GoogleFonts.barlowCondensed(fontSize: size, fontWeight: weight, color: color,
        letterSpacing: letterSpacing, height: height,
        decoration: TextDecoration.none);

// ═════════════════════════════════════════════════════════════════════════════
class HundertLeuteDisplay extends StatefulWidget {
  final SpielState100Leute? initialState;
  const HundertLeuteDisplay({super.key, this.initialState});
  @override State<HundertLeuteDisplay> createState() => _HundertLeuteDisplayState();
}

class _HundertLeuteDisplayState extends State<HundertLeuteDisplay> {
  late final IO.Socket _ns;
  SpielState100Leute? _state;
  late final void Function(dynamic) _onState;

  @override
  void initState() {
    super.initState();
    _state = widget.initialState;
    _ns = SocketService().connectNamespace('/100leute');
    _onState = (data) {
      if (data is Map && mounted) setState(() => _state = SpielState100Leute.fromMap(data));
    };
    _ns.on('state', _onState);
    _ns.emit('get_state');
  }

  @override
  void dispose() {
    _ns.off('state', _onState);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = _state;
    // DefaultTextStyle.none setzt alle vom Theme geerbten Dekorationen zurück
    Widget inner;
    if (s == null || !s.beamerAktiv) {
      inner = _buildIdle(s);
    } else {
      inner = switch (s.phase) {
        'buzzerduell'              => _buildBuzzerduell(s),
        'hauptrunde' || 'stehlen'  => _buildHauptrunde(s),
        'rundenende'               => _buildRundenende(s),
        'fastfive'                 => _buildFastFive(s),
        'ende'                     => _buildEnde(s),
        _                          => _buildIdle(s),
      };
    }
    return DefaultTextStyle(
      style: const TextStyle(decoration: TextDecoration.none, color: Colors.white),
      child: inner,
    );
  }

  // ══ IDLE ════════════════════════════════════════════════════════════════════
  Widget _buildIdle(SpielState100Leute? s) => Container(
    color: _kDark,
    child: Stack(children: [
      Positioned.fill(child: CustomPaint(painter: _DotGridPainter())),
      Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
        RichText(text: TextSpan(children: [
          TextSpan(text: 'SCHLAG', style: _bc(96, FontWeight.w900, Colors.white, letterSpacing: 6)),
          TextSpan(text: 'FERTIG', style: _bc(96, FontWeight.w900, _kGold, letterSpacing: 6)),
        ])),
        const SizedBox(height: 10),
        Text('100 LEUTE GEFRAGT',
            style: _bc(26, FontWeight.w300, Colors.white38, letterSpacing: 8)),
        if (s != null && (s.teamA.name != 'Team A' || s.teamB.name != 'Team B')) ...[
          const SizedBox(height: 60),
          Row(mainAxisSize: MainAxisSize.min, children: [
            _idleBadge(s.teamA.name, _kTeamA),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 32),
              child: Text('VS', style: _bc(24, FontWeight.w900, Colors.white30, letterSpacing: 4)),
            ),
            _idleBadge(s.teamB.name, _kTeamB),
          ]),
        ],
      ])),
    ]),
  );

  Widget _idleBadge(String name, Color c) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 14),
    decoration: BoxDecoration(
      color: c.withOpacity(0.18), borderRadius: BorderRadius.circular(8),
      border: Border.all(color: c.withOpacity(0.6), width: 2),
    ),
    child: Text(name, style: _bc(24, FontWeight.w700, Colors.white)),
  );

  // ══ GAME BASE ═══════════════════════════════════════════════════════════════
  // Legt Team-Hintergründe, Logo und Scores unter den eigentlichen Inhalt.
  Widget _gameBase({
    required SpielState100Leute s,
    String? activeTeam,
    required Widget child,
    bool showScores = true,
    bool showLogo  = true,
    bool fullChild  = false, // wenn true: child füllt Positoned.fill statt Center
  }) {
    return Stack(children: [
      // Team-Hintergründe
      Positioned.fill(child: Row(children: [
        Expanded(child: _TeamBg(team: s.teamA, isLeft: true,  active: activeTeam == 'A', color: _kTeamA)),
        Expanded(child: _TeamBg(team: s.teamB, isLeft: false, active: activeTeam == 'B', color: _kTeamB)),
      ])),
      // Trennlinie
      Positioned.fill(child: IgnorePointer(child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [Container(width: 2, decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter, end: Alignment.bottomCenter,
            colors: [Colors.transparent, Color(0x40FFFFFF), Colors.transparent],
          ),
        ))],
      ))),
      // Logo
      if (showLogo)
        Positioned(top: 22, left: 0, right: 0,
          child: Center(child: RichText(text: TextSpan(children: [
            TextSpan(text: 'SCHLAG', style: _bc(15, FontWeight.w700, const Color(0xFF5B6478), letterSpacing: 4)),
            TextSpan(text: 'FERTIG', style: _bc(15, FontWeight.w700, _kGold, letterSpacing: 4)),
            TextSpan(text: '  ·  100 LEUTE GEFRAGT',
                style: _bc(15, FontWeight.w400, const Color(0xFF5B6478), letterSpacing: 4)),
          ]))),
        ),
      // Inhalt
      if (fullChild)
        Positioned.fill(child: child)
      else
        Positioned(top: 50, left: 0, right: 0, bottom: showScores ? 100 : 0,
          child: Center(child: child)),
      // Team-Scores unten links/rechts
      if (showScores) ...[
        Positioned(bottom: 28, left: 40,
            child: _scoreLabel(s.teamA, _kTeamA, active: activeTeam == 'A')),
        Positioned(bottom: 28, right: 40,
            child: _scoreLabel(s.teamB, _kTeamB, active: activeTeam == 'B')),
      ],
    ]);
  }

  Widget _scoreLabel(Team t, Color c, {bool active = false}) => Row(
    crossAxisAlignment: CrossAxisAlignment.end,
    children: [
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(t.name, style: _bc(18, FontWeight.w700,
            active ? Colors.white : Colors.white60, letterSpacing: 1)),
        Text('${t.punkte}', style: _bc(54, FontWeight.w900,
            active ? c : c.withOpacity(0.65), height: 1.0)),
      ]),
    ],
  );

  // ══ BUZZERDUELL ════════════════════════════════════════════════════════════
  Widget _buildBuzzerduell(SpielState100Leute s) {
    final d = s.duell;
    final activeTeam = d.gewinner ?? d.ersterTeam;
    return _gameBase(
      s: s, activeTeam: activeTeam,
      child: SizedBox(
        width: 880,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('BUZZER-DUELL  ·  RUNDE ${s.runde}',
              style: _bc(20, FontWeight.w400, _kGold.withOpacity(0.85), letterSpacing: 6)),
          const SizedBox(height: 28),
          if (s.aktiveFrage != null && (d.ersterTeam != null || d.buzzerOffen)) ...[
            _questionBox(s.aktiveFrage!.frage),
            const SizedBox(height: 36),
          ] else if (s.aktiveFrage != null) ...[
            _questionBox(s.aktiveFrage!.frage),
            const SizedBox(height: 36),
          ],
          _buildBuzzerStatus(s),
        ]),
      ),
    );
  }

  Widget _buildBuzzerStatus(SpielState100Leute s) {
    final d = s.duell;
    if (d.gewinner != null) {
      final c = d.gewinner == 'A' ? _kTeamA : _kTeamB;
      return Column(mainAxisSize: MainAxisSize.min, children: [
        Text('GEWINNER DES DUELLS',
            style: _bc(16, FontWeight.w300, Colors.white38, letterSpacing: 5)),
        const SizedBox(height: 12),
        Text('>> ${s.teamFor(d.gewinner!).name}  spielt die Hauptrunde',
            style: _bc(40, FontWeight.w900, c, letterSpacing: 1)),
      ]);
    }
    if (d.ersterTeam != null) {
      final c = d.ersterTeam == 'A' ? _kTeamA : _kTeamB;
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 20),
        decoration: BoxDecoration(
          color: c.withOpacity(0.2), borderRadius: BorderRadius.circular(12),
          border: Border.all(color: c, width: 2),
        ),
        child: Text('>> ${s.teamFor(d.ersterTeam!).name} hat zuerst gebuzzert!',
            style: _bc(32, FontWeight.w800, Colors.white)),
      );
    }
    if (d.buzzerOffen) {
      return _PulseWidget(child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 56, vertical: 22),
        decoration: BoxDecoration(
          color: _kGold.withOpacity(0.1), borderRadius: BorderRadius.circular(14),
          border: Border.all(color: _kGold, width: 2.5),
        ),
        child: Text('BUZZER OFFEN', style: _bc(48, FontWeight.w900, _kGold, letterSpacing: 8)),
      ));
    }
    return Text('Warten auf Moderator …',
        style: _bc(22, FontWeight.w300, Colors.white24, letterSpacing: 2));
  }

  // ══ HAUPTRUNDE / STEHLEN ════════════════════════════════════════════════════
  Widget _buildHauptrunde(SpielState100Leute s) {
    final isStehlen  = s.phase == 'stehlen';
    final activeTeam = isStehlen
        ? (s.aktivesTeam == 'A' ? 'B' : 'A')
        : s.aktivesTeam;
    final frage = s.aktiveFrage;

    return _gameBase(
      s: s, activeTeam: activeTeam,
      child: SizedBox(
        width: 880,
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          // Kopfzeile
          Row(children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 5),
              decoration: BoxDecoration(
                color: isStehlen ? Colors.orange.withOpacity(0.2) : Colors.white.withOpacity(0.06),
                borderRadius: BorderRadius.circular(6),
                border: isStehlen ? Border.all(color: Colors.orange.withOpacity(0.7), width: 1.5) : null,
              ),
              child: Text(
                isStehlen ? 'STEHLEN!' : 'HAUPTRUNDE  ·  RUNDE ${s.runde}',
                style: _bc(16, isStehlen ? FontWeight.w900 : FontWeight.w500,
                    isStehlen ? Colors.orange : Colors.white54, letterSpacing: 3),
              ),
            ),
            const Spacer(),
            Text('RUNDENTOPF', style: _bc(12, FontWeight.w300, Colors.white38, letterSpacing: 3)),
            const SizedBox(width: 8),
            Text('${s.rundentopf}', style: _bc(22, FontWeight.w900, _kGold)),
          ]),
          const SizedBox(height: 14),
          // Frage
          if (frage != null) _questionBox(frage.frage),
          const SizedBox(height: 12),
          // Tiles
          if (frage != null)
            ...frage.antworten.asMap().entries.map((e) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _FlipTile(index: e.key, antwort: e.value, tileHeight: 62),
            )),
          const SizedBox(height: 8),
          // Strikes + Status
          Row(children: [
            ...List.generate(3, (i) {
              final hit = i < s.strikes;
              return Padding(
                padding: const EdgeInsets.only(right: 12),
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 300),
                  width: 44, height: 44,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: hit ? _kTeamB.withOpacity(0.25) : Colors.white.withOpacity(0.06),
                    border: Border.all(color: hit ? _kTeamB : Colors.white24, width: 2),
                  ),
                  child: Center(child: Text(hit ? '✗' : '',
                      style: _bc(22, FontWeight.w900, _kTeamB))),
                ),
              );
            }),
            const Spacer(),
            if (isStehlen && s.aktivesTeam != null)
              Text('** ${s.teamFor(s.aktivesTeam!).name} – eine Chance!',
                  style: _bc(17, FontWeight.w700, Colors.orange, letterSpacing: 0.5))
            else if (s.aktivesTeam != null)
              Text('>> ${s.teamFor(s.aktivesTeam!).name} ist dran',
                  style: _bc(17, FontWeight.w400, Colors.white60, letterSpacing: 0.5)),
          ]),
        ]),
      ),
    );
  }

  // ══ RUNDENENDE ══════════════════════════════════════════════════════════════
  Widget _buildRundenende(SpielState100Leute s) {
    final re   = s.rundenende;
    final isA  = re?.gewinner == 'A';
    final c    = isA ? _kTeamA : _kTeamB;
    final name = re?.gewinner != null ? s.teamFor(re!.gewinner!).name : '—';

    return _gameBase(
      s: s, activeTeam: re?.gewinner, showScores: false,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('RUNDE ${s.runde} GEWONNEN',
            style: _bc(20, FontWeight.w300, Colors.white38, letterSpacing: 6)),
        const SizedBox(height: 20),
        Text(name, style: _bc(64, FontWeight.w900, c, letterSpacing: 2)),
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 16),
          decoration: BoxDecoration(
            color: _kGold.withOpacity(0.1), borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _kGold, width: 2),
          ),
          child: Text('+${re?.topf ?? 0} Punkte',
              style: _bc(36, FontWeight.w900, _kGold, letterSpacing: 1)),
        ),
        const SizedBox(height: 52),
        Row(mainAxisSize: MainAxisSize.min, children: [
          _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamA, highlight: isA),
          const SizedBox(width: 40),
          _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamB, highlight: !isA),
        ]),
      ]),
    );
  }

  // ══ FAST FIVE ═══════════════════════════════════════════════════════════════
  Widget _buildFastFive(SpielState100Leute s) {
    final ff = s.ff;
    if (ff == null) {
      return _gameBase(s: s, child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('FAST', style: _bc(30, FontWeight.w300, Colors.white38, letterSpacing: 12)),
        Text('FIVE', style: _bc(88, FontWeight.w900, _kGold, letterSpacing: 14)),
      ]));
    }

    final dranC   = ff.dran == 'A' ? _kTeamA : _kTeamB;
    final maxZeit = (ff.dran == 'A' ? s.config.ffZeit1 : s.config.ffZeit2).toDouble();
    final ratio   = maxZeit > 0 ? (ff.timerRest / maxZeit).clamp(0.0, 1.0) : 0.0;
    final warn    = ff.timerRest <= 10 && ff.timerRest > 0;
    final crit    = ff.timerRest <= 3  && ff.timerRest > 0;
    final runde   = ff.fertigA ? 2 : 1;
    final fq      = ff.aktuelleFrage;

    return _gameBase(
      s: s, activeTeam: ff.dran,
      showScores: false, showLogo: false, fullChild: true,
      child: Column(children: [
        // ── FF-Header ──────────────────────────────────────────────────────
        Container(
          padding: const EdgeInsets.fromLTRB(36, 14, 36, 12),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter, end: Alignment.bottomCenter,
              colors: [const Color(0xE005070D), Colors.transparent],
            ),
          ),
          child: Row(children: [
            Text('FAST FIVE  ·  RUNDE $runde  ·  ${s.teamFor(ff.dran).name}',
                style: _bc(24, FontWeight.w900, dranC, letterSpacing: 2)),
            const Spacer(),
            if (s.config.ffTimer && (ff.timerLaueft || ff.timerRest > 0))
              Text('${ff.timerRest}s', style: _bc(
                crit ? 52 : warn ? 44 : 34, FontWeight.w900,
                crit ? _kTeamB : warn ? _kGold : Colors.white70,
              )),
          ]),
        ),
        // ── Timer-Bar ──────────────────────────────────────────────────────
        if (s.config.ffTimer && (ff.timerLaueft || ff.timerRest > 0))
          Padding(
            padding: const EdgeInsets.fromLTRB(36, 0, 36, 6),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(5),
              child: LinearProgressIndicator(
                value: ratio, backgroundColor: Colors.white12,
                color: crit ? _kTeamB : warn ? _kGold : const Color(0xFF4ADE80),
                minHeight: 10,
              ),
            ),
          ),
        // ── Hauptinhalt ────────────────────────────────────────────────────
        Expanded(child: Center(child: SizedBox(
          width: 880,
          child: fq == null
              ? Text('Nächste Frage …',
                  style: _bc(28, FontWeight.w300, Colors.white24, letterSpacing: 2))
              : Column(mainAxisSize: MainAxisSize.min, children: [
                  _questionBox(fq.frage),
                  const SizedBox(height: 14),
                  ...fq.antworten.asMap().entries.map((e) => Padding(
                    padding: const EdgeInsets.only(bottom: 10),
                    child: _FlipTile(
                      index: e.key,
                      ffAntwort: e.value,
                      teamColor: e.value.von == 'A' ? _kTeamA
                                : e.value.von == 'B' ? _kTeamB : null,
                      tileHeight: 56,
                    ),
                  )),
                ]),
        ))),
        // ── Fortschrittsbalken unten ────────────────────────────────────────
        Container(
          height: 64,
          padding: const EdgeInsets.symmetric(horizontal: 40),
          color: const Color(0xC005070D),
          child: Row(children: [
            Text('${s.teamA.name}',
                style: _bc(13, FontWeight.w400, Colors.white38, letterSpacing: 1)),
            const SizedBox(width: 10),
            Text('${ff.punkteA}',
                style: _bc(22, FontWeight.w900, ff.dran == 'A' ? _kTeamA : Colors.white38)),
            const SizedBox(width: 20),
            Expanded(child: ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: LinearProgressIndicator(
                value: ((ff.punkteA + ff.punkteB) / s.config.ffZiel).clamp(0.0, 1.0),
                backgroundColor: Colors.white.withOpacity(0.07),
                color: const Color(0xFF4ADE80),
                minHeight: 14,
              ),
            )),
            const SizedBox(width: 20),
            Text('${ff.punkteB}',
                style: _bc(22, FontWeight.w900, ff.dran == 'B' ? _kTeamB : Colors.white38)),
            const SizedBox(width: 10),
            Text('${s.teamB.name}',
                style: _bc(13, FontWeight.w400, Colors.white38, letterSpacing: 1)),
          ]),
        ),
      ]),
    );
  }

  // ══ ENDE ════════════════════════════════════════════════════════════════════
  Widget _buildEnde(SpielState100Leute s) {
    final aWins  = s.teamA.punkte > s.teamB.punkte;
    final draw   = s.teamA.punkte == s.teamB.punkte;
    final winner = aWins ? s.teamA : s.teamB;
    final wc     = aWins ? _kTeamA : _kTeamB;

    return _gameBase(
      s: s, activeTeam: draw ? null : (aWins ? 'A' : 'B'), showScores: false,
      child: Column(mainAxisSize: MainAxisSize.min, children: [
        Text('SPIELENDE', style: _bc(18, FontWeight.w300, Colors.white38, letterSpacing: 7)),
        const SizedBox(height: 28),
        if (draw)
          Text('UNENTSCHIEDEN', style: _bc(58, FontWeight.w900, _kGold, letterSpacing: 4))
        else ...[
          Text(winner.name, style: _bc(72, FontWeight.w900, wc, letterSpacing: 2)),
          const SizedBox(height: 8),
          Text('GEWINNT DAS SPIEL!',
              style: _bc(26, FontWeight.w900, Colors.white70, letterSpacing: 4)),
        ],
        const SizedBox(height: 48),
        Row(mainAxisSize: MainAxisSize.min, children: [
          _scoreTile(s.teamA.name, s.teamA.punkte, _kTeamA, highlight: aWins && !draw),
          const SizedBox(width: 56),
          _scoreTile(s.teamB.name, s.teamB.punkte, _kTeamB, highlight: !aWins && !draw),
        ]),
      ]),
    );
  }

  // ══ HELPERS ═════════════════════════════════════════════════════════════════
  Widget _questionBox(String frage) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 28, vertical: 16),
    decoration: BoxDecoration(
      color: Colors.black.withOpacity(0.45),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: Colors.white.withOpacity(0.12), width: 1),
    ),
    child: Text(frage, textAlign: TextAlign.center,
        style: _bc(28, FontWeight.w700, Colors.white, height: 1.3)),
  );

  Widget _scoreTile(String name, int pts, Color c, {bool highlight = false}) => Container(
    padding: const EdgeInsets.symmetric(horizontal: 36, vertical: 20),
    decoration: BoxDecoration(
      color: c.withOpacity(highlight ? 0.3 : 0.15),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: c, width: highlight ? 2.5 : 1.5),
      boxShadow: highlight ? [BoxShadow(color: c.withOpacity(0.3), blurRadius: 20)] : null,
    ),
    child: Column(children: [
      Text(name, style: _bc(18, FontWeight.w700, Colors.white, letterSpacing: 0.5)),
      const SizedBox(height: 6),
      Text('$pts', style: _bc(56, FontWeight.w900, c, height: 1.0)),
      Text('Pkt', style: _bc(14, FontWeight.w300, Colors.white38, letterSpacing: 3)),
    ]),
  );
}

// ════ TEAM-HINTERGRUND MIT FOTO + PULS-GLOW ══════════════════════════════════
class _TeamBg extends StatefulWidget {
  final Team   team;
  final bool   isLeft;
  final bool   active;
  final Color  color;
  const _TeamBg({required this.team, required this.isLeft,
      required this.active, required this.color});
  @override State<_TeamBg> createState() => _TeamBgState();
}

class _TeamBgState extends State<_TeamBg> with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double>   _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 1400))
      ..repeat(reverse: true);
    _anim = CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut);
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) {
    final fotoPath = widget.team.foto;
    final fotoUrl  = fotoPath.isNotEmpty
        ? '${SocketService().serverUrl}$fotoPath'
        : null;

    return AnimatedBuilder(
      animation: _anim,
      builder: (ctx, _) {
        final glow = widget.active ? (0.25 + _anim.value * 0.45) : 0.0;
        return Stack(children: [
          // Basis-Dunkel
          Container(color: const Color(0xFF050810)),
          // Team-Foto (Graustufen, abgedunkelt)
          if (fotoUrl != null)
            Positioned.fill(child: ColorFiltered(
              colorFilter: const ColorFilter.matrix([
                0.213, 0.715, 0.072, 0, 0,
                0.213, 0.715, 0.072, 0, 0,
                0.213, 0.715, 0.072, 0, 0,
                0,     0,     0,     1, 0,
              ]),
              child: Image.network(fotoUrl, fit: BoxFit.cover,
                  opacity: const AlwaysStoppedAnimation(0.32),
                  errorBuilder: (_, __, ___) => const SizedBox()),
            )),
          // Farbiger Gradient-Overlay
          Positioned.fill(child: DecoratedBox(decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: widget.isLeft ? Alignment.centerLeft : Alignment.centerRight,
              end:   widget.isLeft ? Alignment.centerRight : Alignment.centerLeft,
              colors: [widget.color.withOpacity(0.28), Colors.transparent],
              stops: const [0.0, 0.70],
            ),
          ))),
          // Pulsierender Glow (radial, von innen nach außen)
          Positioned.fill(child: Opacity(
            opacity: glow,
            child: DecoratedBox(decoration: BoxDecoration(
              gradient: RadialGradient(
                center: widget.isLeft
                    ? const Alignment(-0.5, 0)
                    : const Alignment(0.5, 0),
                radius: 1.1,
                colors: [
                  widget.color.withOpacity(0.75),
                  widget.color.withOpacity(0.0),
                ],
                stops: const [0.0, 1.0],
              ),
            )),
          )),
        ]);
      },
    );
  }
}

// ════ FLIP-TILE ═══════════════════════════════════════════════════════════════
class _FlipTile extends StatefulWidget {
  final int        index;
  final Antwort?   antwort;
  final FfAntwort? ffAntwort;
  final Color?     teamColor;
  final double     tileHeight;

  const _FlipTile({
    required this.index,
    this.antwort,
    this.ffAntwort,
    this.teamColor,
    this.tileHeight = 64,
  });

  bool   get revealed => antwort?.auf   ?? ffAntwort?.auf   ?? false;
  String get text     => antwort?.text  ?? ffAntwort?.text  ?? '';
  int    get points   => antwort?.punkte ?? ffAntwort?.punkte ?? 0;

  @override State<_FlipTile> createState() => _FlipTileState();
}

class _FlipTileState extends State<_FlipTile>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double>   _anim;
  bool _showBack = false;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 600));
    _anim = Tween(begin: 0.0, end: 1.0).animate(
        CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
    if (widget.revealed) {
      _ctrl.value = 1.0;
      _showBack   = true;
    }
  }

  @override
  void didUpdateWidget(_FlipTile old) {
    super.didUpdateWidget(old);
    if (widget.revealed && !old.revealed) {
      _ctrl.forward();
      Future.delayed(const Duration(milliseconds: 280), () {
        if (mounted) setState(() => _showBack = true);
      });
    } else if (!widget.revealed && old.revealed) {
      setState(() => _showBack = false);
      _ctrl.reverse();
    }
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) => SizedBox(
    height: widget.tileHeight,
    child: AnimatedBuilder(
      animation: _anim,
      builder: (ctx, _) {
        final angle = _anim.value * pi;
        if (angle <= pi / 2) {
          return Transform(
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.001)
              ..rotateX(angle),
            alignment: Alignment.center,
            child: _front(),
          );
        } else {
          return Transform(
            transform: Matrix4.identity()
              ..setEntry(3, 2, 0.001)
              ..rotateX(angle - pi),
            alignment: Alignment.center,
            child: _back(),
          );
        }
      },
    ),
  );

  Widget _front() => Container(
    decoration: BoxDecoration(
      color: Colors.white.withOpacity(0.05),
      borderRadius: BorderRadius.circular(12),
      border: Border.all(color: Colors.white.withOpacity(0.12), width: 1),
      boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 4,
          offset: const Offset(0, 2))],
    ),
    alignment: Alignment.center,
    child: Text('${widget.index + 1}',
        style: _bc(widget.tileHeight * 0.50, FontWeight.w900,
            const Color(0xFF7E8AA3))),
  );

  Widget _back() {
    final bc = widget.teamColor ?? _kGold;
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          begin: Alignment.topLeft, end: Alignment.bottomRight,
          colors: [Color(0xFF1C1608), Color(0xFF0C0A03)],
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: bc, width: 1.5),
        boxShadow: [BoxShadow(color: bc.withOpacity(0.25), blurRadius: 22)],
      ),
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(children: [
        Expanded(child: Text(widget.text.toUpperCase(),
            style: _bc(widget.tileHeight * 0.42, FontWeight.w800, Colors.white,
                letterSpacing: 0.5),
            overflow: TextOverflow.ellipsis)),
        Text('${widget.points}',
            style: _bc(widget.tileHeight * 0.50, FontWeight.w900, bc)),
      ]),
    );
  }
}

// ════ PULS-WIDGET ═════════════════════════════════════════════════════════════
class _PulseWidget extends StatefulWidget {
  final Widget child;
  const _PulseWidget({required this.child});
  @override State<_PulseWidget> createState() => _PulseWidgetState();
}

class _PulseWidgetState extends State<_PulseWidget>
    with SingleTickerProviderStateMixin {
  late AnimationController _ctrl;
  late Animation<double>   _anim;

  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 900))
      ..repeat(reverse: true);
    _anim = Tween<double>(begin: 0.65, end: 1.0)
        .animate(CurvedAnimation(parent: _ctrl, curve: Curves.easeInOut));
  }

  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }

  @override
  Widget build(BuildContext context) =>
      FadeTransition(opacity: _anim, child: widget.child);
}

// ════ PUNKT-RASTER HINTERGRUND ════════════════════════════════════════════════
class _DotGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final p = Paint()..color = Colors.white.withOpacity(0.04);
    const step = 72.0;
    for (double x = step; x < size.width; x += step) {
      for (double y = step; y < size.height; y += step) {
        canvas.drawCircle(Offset(x, y), 1.5, p);
      }
    }
  }
  @override bool shouldRepaint(_) => false;
}
