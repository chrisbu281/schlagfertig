import 'package:flutter/material.dart';
import 'package:socket_io_client/socket_io_client.dart' as IO;
import '../../core/socket_service.dart';
import '../../core/game_state.dart';

const _kGold = Color(0xFFF5C518);
const _kPanel = Color(0xFF0D1117);
const _kTeamA = Color(0xFF1E4DB8);
const _kTeamB = Color(0xFFB82020);

class HundertLeuteModeratorView extends StatefulWidget {
  const HundertLeuteModeratorView({super.key});

  @override
  State<HundertLeuteModeratorView> createState() => _HundertLeuteModeratorViewState();
}

class _HundertLeuteModeratorViewState extends State<HundertLeuteModeratorView> {
  late final IO.Socket _ns;
  SpielState100Leute? _state;

  // Setup form fields
  final _nameACtrl = TextEditingController(text: 'Team A');
  final _nameBCtrl = TextEditingController(text: 'Team B');
  int _runden = 3;
  bool _ffTimer = true;

  @override
  void initState() {
    super.initState();
    _ns = SocketService().connectNamespace('/100leute');
    _ns.on('state', (data) {
      if (data is Map && mounted) {
        final s = SpielState100Leute.fromMap(data);
        setState(() {
          _state = s;
          // sync form fields on first load
          if (_nameACtrl.text == 'Team A') _nameACtrl.text = s.teamA.name;
          if (_nameBCtrl.text == 'Team B') _nameBCtrl.text = s.teamB.name;
          _runden = s.config.runden;
          _ffTimer = s.config.ffTimer;
        });
      }
    });
  }

  @override
  void dispose() {
    _ns.off('state');
    _nameACtrl.dispose();
    _nameBCtrl.dispose();
    super.dispose();
  }

  void _emit(String event, [dynamic data]) => _ns.emit(event, data);

  // ── Build ───────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    final s = _state;
    if (s == null) {
      return const Center(child: CircularProgressIndicator(color: _kGold));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildHeader(s),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(16),
            child: switch (s.phase) {
              'setup' => _buildSetup(s),
              'buzzerduell' => _buildBuzzerduell(s),
              'hauptrunde' => _buildHauptrunde(s),
              'stehlen' => _buildStehlen(s),
              'rundenende' => _buildRundenende(s),
              'fastfive' => _buildFastFive(s),
              'ende' => _buildEnde(s),
              _ => _buildSetup(s),
            },
          ),
        ),
      ],
    );
  }

  // ── Header ──────────────────────────────────────────────────────────
  Widget _buildHeader(SpielState100Leute s) {
    return Container(
      color: _kPanel,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      child: Row(children: [
        _scoreChip(s.teamA.name, s.teamA.punkte, _kTeamA),
        const SizedBox(width: 12),
        Expanded(child: Center(child: Column(children: [
          Text(_phaseLabel(s.phase), style: const TextStyle(color: Colors.white54, fontSize: 12, letterSpacing: 2)),
          if (s.runde > 0)
            Text('Runde ${s.runde} / ${s.config.runden}', style: const TextStyle(color: Colors.white38, fontSize: 11)),
        ]))),
        const SizedBox(width: 12),
        _scoreChip(s.teamB.name, s.teamB.punkte, _kTeamB),
      ]),
    );
  }

  Widget _scoreChip(String name, int pts, Color color) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(color: color.withOpacity(0.25), borderRadius: BorderRadius.circular(6), border: Border.all(color: color.withOpacity(0.5))),
        child: Column(children: [
          Text(name, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold), maxLines: 1, overflow: TextOverflow.ellipsis),
          Text('$pts Pkt', style: TextStyle(color: color, fontSize: 14, fontWeight: FontWeight.bold)),
        ]),
      );

  // ── Setup ───────────────────────────────────────────────────────────
  Widget _buildSetup(SpielState100Leute s) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Teams'),
      _card(Column(children: [
        _textRow('Team A Name', _nameACtrl, _kTeamA),
        const SizedBox(height: 10),
        _textRow('Team B Name', _nameBCtrl, _kTeamB),
      ])),
      const SizedBox(height: 16),
      _sectionTitle('Spielkonfiguration'),
      _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Row(children: [
          const Text('Runden:', style: TextStyle(color: Colors.white70)),
          const SizedBox(width: 16),
          ...List.generate(5, (i) => Padding(
            padding: const EdgeInsets.only(right: 8),
            child: _choiceChip('${i + 1}', _runden == i + 1, () => setState(() => _runden = i + 1)),
          )),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          const Text('FF Timer:', style: TextStyle(color: Colors.white70)),
          const Spacer(),
          Switch(value: _ffTimer, onChanged: (v) => setState(() => _ffTimer = v), activeColor: _kGold),
        ]),
      ])),
      const SizedBox(height: 20),
      Row(children: [
        Expanded(child: _btn('Auf Beamer zeigen', Icons.tv, Colors.white38, () {
          _sendSetup();
          _emit('beamer_starten');
        })),
        const SizedBox(width: 12),
        Expanded(child: _btnPrimary('Spiel starten ▶', () {
          _sendSetup();
          _emit('spiel_starten');
        })),
      ]),
      const SizedBox(height: 12),
      if (s.beamerAktiv)
        _btn('Beamer / Spiel beenden', Icons.stop, Colors.redAccent, () => _emit('spiel_beenden')),
    ]);
  }

  void _sendSetup() {
    _emit('setup', {
      'teams': {'A': {'name': _nameACtrl.text.trim()}, 'B': {'name': _nameBCtrl.text.trim()}},
      'config': {'runden': _runden, 'ff_timer': _ffTimer},
    });
  }

  // ── Buzzerduell ─────────────────────────────────────────────────────
  Widget _buildBuzzerduell(SpielState100Leute s) {
    final d = s.duell;
    final af = s.aktiveFrage;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Buzzerduell – Runde ${s.runde}'),
      if (af == null)
        _btnPrimary('Frage laden & Buzzer öffnen', () => _emit('frage_freigeben'))
      else ...[
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text(af.frage, style: const TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          const Text('Buzzer simulieren:', style: TextStyle(color: Colors.white38, fontSize: 12)),
          const SizedBox(height: 6),
          Row(children: [
            Expanded(child: _btn('⚡ Buzzer A', Icons.gamepad, _kTeamA, () => _emit('sim_buzzer', {'team': 'A'}))),
            const SizedBox(width: 12),
            Expanded(child: _btn('⚡ Buzzer B', Icons.gamepad, _kTeamB, () => _emit('sim_buzzer', {'team': 'B'}))),
          ]),
          if (d.ersterTeam != null) ...[
            const SizedBox(height: 8),
            Center(child: Text('Erster: Team ${d.ersterTeam}', style: TextStyle(color: d.ersterTeam == 'A' ? _kTeamA : _kTeamB, fontWeight: FontWeight.bold))),
          ],
        ])),
        const SizedBox(height: 16),
        _sectionTitle('Antworten'),
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          _buildDuellAntwortPicker('Team A', 'A', d.antwortA, af),
          const Divider(color: Colors.white12, height: 24),
          _buildDuellAntwortPicker('Team B', 'B', d.antwortB, af),
          if (d.antwortA != null || d.antwortB != null) ...[
            const SizedBox(height: 12),
            _btn('Antworten zurücksetzen', Icons.undo, Colors.white38, () => _emit('duell_reset_antworten')),
          ],
          if (d.gewinner != null) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(color: _kGold.withOpacity(0.1), borderRadius: BorderRadius.circular(8), border: Border.all(color: _kGold.withOpacity(0.4))),
              child: Text('Gewinner: Team ${d.gewinner}', style: const TextStyle(color: _kGold, fontWeight: FontWeight.bold, textBaseline: TextBaseline.alphabetic), textAlign: TextAlign.center),
            ),
            const SizedBox(height: 12),
            _btnPrimary('Hauptrunde starten ▶', () => _emit('hauptrunde_starten')),
          ],
        ])),
        const SizedBox(height: 12),
        _btn('Spiel beenden', Icons.stop, Colors.redAccent, () => _emit('spiel_beenden')),
      ],
    ]);
  }

  Widget _buildDuellAntwortPicker(String label, String team, int? selected, AktiveFrage af) {
    final color = team == 'A' ? _kTeamA : _kTeamB;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      Text(label, style: TextStyle(color: color, fontWeight: FontWeight.bold, fontSize: 13)),
      const SizedBox(height: 6),
      ...List.generate(af.antworten.length, (i) {
        final a = af.antworten[i];
        final isSel = selected == i;
        return GestureDetector(
          onTap: selected != null ? null : () => _emit('duell_antwort', {'team': team, 'idx': i}),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            margin: const EdgeInsets.only(bottom: 4),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: isSel ? color.withOpacity(0.3) : Colors.white.withOpacity(0.04),
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: isSel ? color : Colors.white12, width: isSel ? 2 : 1),
            ),
            child: Row(children: [
              Text('${i + 1} · ${a.text}', style: TextStyle(color: isSel ? Colors.white : Colors.white54, fontSize: 13)),
              const Spacer(),
              Text('${a.punkte} Pkt', style: TextStyle(color: isSel ? _kGold : Colors.white24, fontSize: 12, fontWeight: FontWeight.bold)),
            ]),
          ),
        );
      }),
      GestureDetector(
        onTap: selected != null ? null : () => _emit('duell_antwort', {'team': team, 'idx': null}),
        child: Container(
          margin: const EdgeInsets.only(bottom: 4),
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(color: Colors.white.withOpacity(0.04), borderRadius: BorderRadius.circular(6), border: Border.all(color: Colors.white12)),
          child: const Text('Nicht auf der Tafel (0 Pkt)', style: TextStyle(color: Colors.white38, fontSize: 13)),
        ),
      ),
    ]);
  }

  // ── Hauptrunde ──────────────────────────────────────────────────────
  Widget _buildHauptrunde(SpielState100Leute s) {
    final af = s.aktiveFrage;
    final activeColor = s.aktivesTeam == 'A' ? _kTeamA : _kTeamB;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Hauptrunde – Team ${s.aktivesTeam ?? "?"}'),
      _card(Row(children: [
        Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text('Am Zug: ${s.aktivesTeam != null ? s.teamFor(s.aktivesTeam!).name : "—"}',
              style: TextStyle(color: activeColor, fontWeight: FontWeight.bold)),
          Text('Topf: ${s.rundentopf} Pkt', style: const TextStyle(color: _kGold)),
        ])),
        Row(children: List.generate(3, (i) => Padding(
          padding: const EdgeInsets.only(left: 8),
          child: Text(i < s.strikes ? '❌' : '○', style: const TextStyle(fontSize: 22)),
        ))),
      ])),
      const SizedBox(height: 12),
      if (af != null) ...[
        _sectionTitle('Antworten aufdecken'),
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ...List.generate(af.antworten.length, (i) {
            final a = af.antworten[i];
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                Text('${i + 1}. ', style: const TextStyle(color: Colors.white38, fontSize: 13)),
                Expanded(child: a.auf
                    ? Text('${a.text}  (${a.punkte} Pkt)', style: const TextStyle(color: Colors.white70, fontSize: 13))
                    : const Text('Verdeckt', style: TextStyle(color: Colors.white24, fontSize: 13))),
                if (!a.auf)
                  SizedBox(
                    height: 30,
                    child: ElevatedButton(
                      onPressed: () => _emit('hauptrunde_aufdecken', {'idx': i}),
                      style: ElevatedButton.styleFrom(backgroundColor: _kGold, foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(horizontal: 14), textStyle: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                      child: const Text('Aufdecken'),
                    ),
                  )
                else
                  const Icon(Icons.check_circle, color: Colors.greenAccent, size: 20),
              ]),
            );
          }),
        ])),
      ],
      const SizedBox(height: 12),
      _btn('❌ Strike (${s.strikes}/3)', Icons.close, Colors.redAccent, s.strikes < 3 ? () => _emit('hauptrunde_strike') : null),
      const SizedBox(height: 8),
      _btn('Spiel beenden', Icons.stop, Colors.white38, () => _emit('spiel_beenden')),
    ]);
  }

  // ── Stehlen ─────────────────────────────────────────────────────────
  Widget _buildStehlen(SpielState100Leute s) {
    final af = s.aktiveFrage;
    final stehlerTeam = s.aktivesTeam == 'A' ? 'B' : 'A';
    final stehlerName = s.teamFor(stehlerTeam).name;
    final stehlerColor = stehlerTeam == 'A' ? _kTeamA : _kTeamB;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Stehlen – $stehlerName'),
      _card(Text('Team $stehlerTeam ($stehlerName) kann stehlen!', style: TextStyle(color: stehlerColor, fontWeight: FontWeight.bold))),
      if (af != null) ...[
        const SizedBox(height: 12),
        _sectionTitle('Welche Antwort wird gestohlen?'),
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          ...List.generate(af.antworten.length, (i) {
            final a = af.antworten[i];
            if (a.auf) return const SizedBox.shrink();
            return Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(children: [
                Expanded(child: Text('${i + 1}. ${a.text} (${a.punkte} Pkt)', style: const TextStyle(color: Colors.white70, fontSize: 13))),
                SizedBox(
                  height: 30,
                  child: ElevatedButton(
                    onPressed: () => _emit('stehlen_aufdecken', {'idx': i}),
                    style: ElevatedButton.styleFrom(backgroundColor: stehlerColor, foregroundColor: Colors.white, padding: const EdgeInsets.symmetric(horizontal: 14), textStyle: const TextStyle(fontSize: 12)),
                    child: const Text('Stehlen!'),
                  ),
                ),
              ]),
            );
          }),
        ])),
      ],
      const SizedBox(height: 12),
      _btn('Falsche Antwort (bleibt bei Team ${s.aktivesTeam})', Icons.close, Colors.orange, () => _emit('stehlen_falsch')),
    ]);
  }

  // ── Rundenende ──────────────────────────────────────────────────────
  Widget _buildRundenende(SpielState100Leute s) {
    final re = s.rundenende;
    final winnerName = re?.gewinner != null ? s.teamFor(re!.gewinner!).name : '—';
    final nextIsFF = s.runde >= s.config.runden;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Rundenende'),
      _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text('Sieger: $winnerName', style: const TextStyle(color: _kGold, fontSize: 18, fontWeight: FontWeight.bold)),
        Text('+${re?.topf ?? 0} Punkte', style: const TextStyle(color: Colors.white70)),
        const SizedBox(height: 8),
        Text('Stand: ${s.teamA.name} ${s.teamA.punkte} : ${s.teamB.punkte} ${s.teamB.name}', style: const TextStyle(color: Colors.white54, fontSize: 13)),
      ])),
      const SizedBox(height: 16),
      _btnPrimary(nextIsFF ? 'Weiter zu Fast Five ▶' : 'Nächste Runde ▶', () => _emit('naechste_runde')),
      const SizedBox(height: 8),
      _btn('Spiel beenden', Icons.stop, Colors.white38, () => _emit('spiel_beenden')),
    ]);
  }

  // ── FastFive ────────────────────────────────────────────────────────
  Widget _buildFastFive(SpielState100Leute s) {
    final ff = s.ff;
    if (ff == null) {
      return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        _sectionTitle('Fast Five'),
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Ziel: ${s.config.ffZiel} Punkte', style: const TextStyle(color: Colors.white54)),
          Text('Zeit A: ${s.config.ffZeit1}s / Zeit B: ${s.config.ffZeit2}s', style: const TextStyle(color: Colors.white54)),
        ])),
        const SizedBox(height: 12),
        _btnPrimary('Fast Five starten ▶', () => _emit('ff_starten')),
      ]);
    }

    final frage = ff.aktuelleFrage;
    final dranColor = ff.dran == 'A' ? _kTeamA : _kTeamB;
    final dranName = s.teamFor(ff.dran).name;

    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Fast Five – $dranName (Team ${ff.dran})'),
      _card(Row(children: [
        Text('Punkte A: ${ff.punkteA}', style: const TextStyle(color: Colors.white54)),
        const Spacer(),
        Text('Punkte B: ${ff.punkteB}', style: const TextStyle(color: Colors.white54)),
        const Spacer(),
        Text('${ff.timerRest}s', style: TextStyle(color: ff.timerRest < 5 ? Colors.redAccent : Colors.white70, fontWeight: FontWeight.bold)),
      ])),
      const SizedBox(height: 8),
      Row(children: [
        Expanded(child: _btn('▶ Timer', Icons.timer, _kGold, ff.timerLaueft ? null : () => _emit('ff_timer_start'))),
        const SizedBox(width: 8),
        Expanded(child: _btn('⏸ Stop', Icons.timer_off, Colors.white38, ff.timerLaueft ? () => _emit('ff_timer_stop') : null)),
      ]),
      const SizedBox(height: 12),
      if (frage != null) ...[
        _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          Text('Frage ${ff.aktuell + 1}/5: ${frage.frage}', style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          const SizedBox(height: 10),
          ...List.generate(frage.antworten.length, (i) {
            final a = frage.antworten[i];
            return Padding(
              padding: const EdgeInsets.only(bottom: 5),
              child: Row(children: [
                Text('${i + 1}. ', style: const TextStyle(color: Colors.white38)),
                Expanded(child: a.auf
                    ? Text('${a.text}  (${a.punkte} Pkt)', style: const TextStyle(color: Colors.white70, fontSize: 13))
                    : const Text('Verdeckt', style: TextStyle(color: Colors.white24, fontSize: 13))),
                if (!a.auf)
                  SizedBox(
                    height: 30,
                    child: ElevatedButton(
                      onPressed: () => _emit('ff_aufdecken', {'idx': i}),
                      style: ElevatedButton.styleFrom(backgroundColor: dranColor, foregroundColor: Colors.white, padding: const EdgeInsets.symmetric(horizontal: 12), textStyle: const TextStyle(fontSize: 11)),
                      child: const Text('Aufdecken'),
                    ),
                  )
                else
                  Text(a.von == ff.dran ? '✓' : '✗', style: TextStyle(color: a.von == ff.dran ? Colors.greenAccent : Colors.redAccent, fontWeight: FontWeight.bold)),
              ]),
            );
          }),
        ])),
        const SizedBox(height: 8),
        _btn('Nächste Frage ▶', Icons.skip_next, Colors.white70, () => _emit('ff_naechste_frage')),
      ],
      const SizedBox(height: 12),
      _btn('Fast Five beenden', Icons.stop, Colors.orange, () => _emit('ff_beenden')),
    ]);
  }

  // ── Ende ────────────────────────────────────────────────────────────
  Widget _buildEnde(SpielState100Leute s) {
    final aWins = s.teamA.punkte > s.teamB.punkte;
    final draw = s.teamA.punkte == s.teamB.punkte;
    final winnerName = draw ? 'Unentschieden' : (aWins ? s.teamA.name : s.teamB.name);
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      _sectionTitle('Spielende'),
      _card(Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        Text(winnerName, style: const TextStyle(color: _kGold, fontSize: 24, fontWeight: FontWeight.bold)),
        const SizedBox(height: 8),
        Text('${s.teamA.name}: ${s.teamA.punkte} Pkt', style: const TextStyle(color: Colors.white54)),
        Text('${s.teamB.name}: ${s.teamB.punkte} Pkt', style: const TextStyle(color: Colors.white54)),
      ])),
      const SizedBox(height: 16),
      _btn('Neues Spiel (zurücksetzen)', Icons.refresh, _kGold, () => _emit('reset')),
      const SizedBox(height: 8),
      _btn('Beamer beenden', Icons.tv_off, Colors.white38, () => _emit('spiel_beenden')),
    ]);
  }

  // ── Shared helpers ──────────────────────────────────────────────────
  Widget _sectionTitle(String title) => Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Text(title.toUpperCase(), style: const TextStyle(color: Colors.white38, fontSize: 11, letterSpacing: 2, fontWeight: FontWeight.bold)),
      );

  Widget _card(Widget child) => Container(
        margin: const EdgeInsets.only(bottom: 0),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(color: _kPanel, borderRadius: BorderRadius.circular(8), border: Border.all(color: Colors.white12)),
        child: child,
      );

  Widget _textRow(String label, TextEditingController ctrl, Color color) => Row(children: [
        SizedBox(width: 80, child: Text(label, style: const TextStyle(color: Colors.white54, fontSize: 13))),
        Expanded(child: TextField(
          controller: ctrl,
          style: TextStyle(color: color),
          decoration: InputDecoration(
            isDense: true, contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            filled: true, fillColor: color.withOpacity(0.1),
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: color.withOpacity(0.4))),
            enabledBorder: OutlineInputBorder(borderRadius: BorderRadius.circular(6), borderSide: BorderSide(color: color.withOpacity(0.4))),
          ),
        )),
      ]);

  Widget _choiceChip(String label, bool selected, VoidCallback onTap) => GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
          decoration: BoxDecoration(
            color: selected ? _kGold.withOpacity(0.2) : Colors.white.withOpacity(0.06),
            borderRadius: BorderRadius.circular(6),
            border: Border.all(color: selected ? _kGold : Colors.white24),
          ),
          child: Text(label, style: TextStyle(color: selected ? _kGold : Colors.white54, fontWeight: selected ? FontWeight.bold : FontWeight.normal)),
        ),
      );

  Widget _btn(String label, IconData icon, Color color, VoidCallback? onTap) => Opacity(
        opacity: onTap == null ? 0.35 : 1.0,
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
            decoration: BoxDecoration(
              color: color.withOpacity(0.1),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: color.withOpacity(0.4)),
            ),
            child: Row(mainAxisAlignment: MainAxisAlignment.center, children: [
              Icon(icon, color: color, size: 16),
              const SizedBox(width: 8),
              Text(label, style: TextStyle(color: color, fontWeight: FontWeight.w600, fontSize: 13)),
            ]),
          ),
        ),
      );

  Widget _btnPrimary(String label, VoidCallback onTap) => ElevatedButton(
        onPressed: onTap,
        style: ElevatedButton.styleFrom(
          backgroundColor: _kGold, foregroundColor: Colors.black,
          padding: const EdgeInsets.symmetric(vertical: 14),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
        ),
        child: Text(label),
      );

  String _phaseLabel(String phase) => switch (phase) {
        'setup' => 'SETUP',
        'buzzerduell' => 'BUZZERDUELL',
        'hauptrunde' => 'HAUPTRUNDE',
        'stehlen' => 'STEHLEN',
        'rundenende' => 'RUNDENENDE',
        'fastfive' => 'FAST FIVE',
        'ende' => 'ENDE',
        _ => phase.toUpperCase(),
      };
}
