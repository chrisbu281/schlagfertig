class Team {
  final String name;
  final String foto;
  final int punkte;
  Team({required this.name, required this.foto, required this.punkte});
  factory Team.fromMap(Map m) => Team(
        name: (m['name'] ?? 'Team').toString(),
        foto: (m['foto'] ?? '').toString(),
        punkte: (m['punkte'] as num? ?? 0).toInt(),
      );
}

class Antwort {
  final String text;
  final int punkte;
  final bool auf;
  Antwort({required this.text, required this.punkte, required this.auf});
  factory Antwort.fromMap(Map m) => Antwort(
        text: (m['text'] ?? '').toString(),
        punkte: (m['punkte'] as num? ?? 0).toInt(),
        auf: m['auf'] == true,
      );
}

class AktiveFrage {
  final String id;
  final String frage;
  final List<Antwort> antworten;
  AktiveFrage({required this.id, required this.frage, required this.antworten});
  factory AktiveFrage.fromMap(Map m) => AktiveFrage(
        id: (m['id'] ?? '').toString(),
        frage: (m['frage'] ?? '').toString(),
        antworten: (m['antworten'] as List? ?? [])
            .map((a) => Antwort.fromMap(a as Map))
            .toList(),
      );
}

class DuellState {
  final String? ersterTeam;
  final int? antwortA;
  final int? antwortB;
  final String? gewinner;
  final bool buzzerOffen;
  DuellState({this.ersterTeam, this.antwortA, this.antwortB, this.gewinner, required this.buzzerOffen});
  factory DuellState.fromMap(Map m) => DuellState(
        ersterTeam: m['erster_team']?.toString(),
        antwortA: (m['antwort_a'] as num?)?.toInt(),
        antwortB: (m['antwort_b'] as num?)?.toInt(),
        gewinner: m['gewinner']?.toString(),
        buzzerOffen: m['buzzer_offen'] == true,
      );
}

class SpielConfig {
  final int runden;
  final bool ffTimer;
  final int ffZeit1;
  final int ffZeit2;
  final int ffZiel;
  SpielConfig({required this.runden, required this.ffTimer, required this.ffZeit1, required this.ffZeit2, required this.ffZiel});
  factory SpielConfig.fromMap(Map m) => SpielConfig(
        runden: (m['runden'] as num? ?? 3).toInt(),
        ffTimer: m['ff_timer'] != false,
        ffZeit1: (m['ff_zeit1'] as num? ?? 20).toInt(),
        ffZeit2: (m['ff_zeit2'] as num? ?? 25).toInt(),
        ffZiel: (m['ff_ziel'] as num? ?? 400).toInt(),
      );
  Map<String, dynamic> toMap() => {'runden': runden, 'ff_timer': ffTimer, 'ff_zeit1': ffZeit1, 'ff_zeit2': ffZeit2, 'ff_ziel': ffZiel};
}

class RundenendeState {
  final String? gewinner;
  final int topf;
  RundenendeState({this.gewinner, required this.topf});
  factory RundenendeState.fromMap(Map m) => RundenendeState(
        gewinner: m['gewinner']?.toString(),
        topf: (m['topf'] as num? ?? 0).toInt(),
      );
}

class FfAntwort {
  final String text;
  final int punkte;
  final bool auf;
  final String? von;
  FfAntwort({required this.text, required this.punkte, required this.auf, this.von});
  factory FfAntwort.fromMap(Map m) => FfAntwort(
        text: (m['text'] ?? '').toString(),
        punkte: (m['punkte'] as num? ?? 0).toInt(),
        auf: m['auf'] == true,
        von: m['von']?.toString(),
      );
}

class FfFrage {
  final String id;
  final String frage;
  final List<FfAntwort> antworten;
  FfFrage({required this.id, required this.frage, required this.antworten});
  factory FfFrage.fromMap(Map m) => FfFrage(
        id: (m['id'] ?? '').toString(),
        frage: (m['frage'] ?? '').toString(),
        antworten: (m['antworten'] as List? ?? [])
            .map((a) => FfAntwort.fromMap(a as Map))
            .toList(),
      );
}

class FfState {
  final List<FfFrage> fragen;
  final int aktuell;
  final String dran;
  final bool timerLaueft;
  final int timerRest;
  final int punkteA;
  final int punkteB;
  final bool fertigA;
  final bool fertigB;
  FfState({required this.fragen, required this.aktuell, required this.dran, required this.timerLaueft, required this.timerRest, required this.punkteA, required this.punkteB, required this.fertigA, required this.fertigB});
  factory FfState.fromMap(Map m) => FfState(
        fragen: (m['fragen'] as List? ?? []).map((f) => FfFrage.fromMap(f as Map)).toList(),
        aktuell: (m['aktuell'] as num? ?? 0).toInt(),
        dran: (m['dran'] ?? 'A').toString(),
        timerLaueft: m['timer_laueft'] == true,
        timerRest: (m['timer_rest'] as num? ?? 0).toInt(),
        punkteA: (m['punkte_a'] as num? ?? 0).toInt(),
        punkteB: (m['punkte_b'] as num? ?? 0).toInt(),
        fertigA: m['fertig_a'] == true,
        fertigB: m['fertig_b'] == true,
      );
  FfFrage? get aktuelleFrage => (aktuell >= 0 && aktuell < fragen.length) ? fragen[aktuell] : null;
}

class SpielState100Leute {
  final String phase;
  final SpielConfig config;
  final Team teamA;
  final Team teamB;
  final int runde;
  final AktiveFrage? aktiveFrage;
  final DuellState duell;
  final int strikes;
  final String? aktivesTeam;
  final int rundentopf;
  final RundenendeState? rundenende;
  final bool musik;
  final bool beamerAktiv;
  final FfState? ff;
  final int fragenQueueLen;

  SpielState100Leute({required this.phase, required this.config, required this.teamA, required this.teamB, required this.runde, this.aktiveFrage, required this.duell, required this.strikes, this.aktivesTeam, required this.rundentopf, this.rundenende, required this.musik, required this.beamerAktiv, this.ff, required this.fragenQueueLen});

  factory SpielState100Leute.fromMap(Map m) {
    final teams = m['teams'] as Map? ?? {};
    return SpielState100Leute(
      phase: (m['phase'] ?? 'setup').toString(),
      config: SpielConfig.fromMap(m['config'] as Map? ?? {}),
      teamA: Team.fromMap(teams['A'] as Map? ?? {}),
      teamB: Team.fromMap(teams['B'] as Map? ?? {}),
      runde: (m['runde'] as num? ?? 0).toInt(),
      aktiveFrage: m['aktive_frage'] != null ? AktiveFrage.fromMap(m['aktive_frage'] as Map) : null,
      duell: DuellState.fromMap(m['duell'] as Map? ?? {}),
      strikes: (m['strikes'] as num? ?? 0).toInt(),
      aktivesTeam: m['aktives_team']?.toString(),
      rundentopf: (m['rundentopf'] as num? ?? 0).toInt(),
      rundenende: m['rundenende'] != null ? RundenendeState.fromMap(m['rundenende'] as Map) : null,
      musik: m['musik'] == true,
      beamerAktiv: m['beamer_aktiv'] == true,
      ff: m['ff'] != null ? FfState.fromMap(m['ff'] as Map) : null,
      fragenQueueLen: (m['fragen_queue'] as List? ?? []).length,
    );
  }

  Team teamFor(String t) => t == 'A' ? teamA : teamB;
  String gegenTeamKey(String t) => t == 'A' ? 'B' : 'A';
}
