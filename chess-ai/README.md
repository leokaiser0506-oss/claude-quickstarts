# Chess AI

Eine kleine Schach-Engine in Python (Alpha-Beta-Suche) mit Kommandozeile zum
**Spielen**, **Stellungen analysieren** und **eigene Partien auswerten**.
Optional kann statt der eigenen Engine **Stockfish** verwendet werden.

## Ehrliche Einordnung vorweg

- **Keine KI gewinnt dir „jedes“ Spiel.** Die eingebaute Engine ist reines Python und
  rechnet in ein paar Sekunden ca. 6–8 Halbzüge tief. Grob geschätzt (nicht gemessen)
  liegt das im Bereich eines Club-Anfängers bis mittleren Vereinsspielers: Sie schlägt
  Einsteiger und bestraft grobe Patzer, verliert aber klar gegen starke Spieler und
  chancenlos gegen Stockfish. Es gibt kein Eröffnungsbuch und keine Endspieltabellen.
- **Wer wirklich maximale Stärke will, nimmt Stockfish** (`--stockfish`). Das ist
  kostenlos und um Welten stärker als alles, was sich hier in Python schreiben lässt.
- **Engine-Hilfe in laufenden Online-Partien gegen Menschen ist Betrug.** Chess.com,
  Lichess usw. erkennen das zuverlässig statistisch und sperren den Account dauerhaft.
  Das Tool ist zum Üben gegen den Computer und zum Analysieren *nach* der Partie gedacht –
  so wirst du tatsächlich besser, statt nur gesperrt.

## Installation

```bash
cd chess-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Optional Stockfish: `sudo apt install stockfish` (Linux), `brew install stockfish` (macOS)
oder Download von stockfishchess.org.

## Benutzung

Gegen die Engine spielen (Züge als `e4`, `Nf3`, `O-O` oder `e2e4`):

```bash
python -m chess_ai play --color white --time 3
python -m chess_ai play --color black --time 5 -v          # zeigt Suchfortschritt
python -m chess_ai play --stockfish /usr/games/stockfish     # gegen Stockfish
```

Im Spiel: `hint` (Vorschlag), `undo` (Zug zurück), `fen`, `pgn`, `quit`.

Besten Zug für eine Stellung (FEN) finden:

```bash
python -m chess_ai analyze "r1bqkb1r/pppp1ppp/2n2n2/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR w KQkq - 4 4"
```

Eigene Partie auswerten (markiert Ungenauigkeiten `?!`, Fehler `?`, Patzer `??`):

```bash
python -m chess_ai analyze --pgn meine_partie.pgn --time 1
python -m chess_ai analyze --pgn meine_partie.pgn --stockfish stockfish   # genauer
```

## Wie die Engine funktioniert

| Datei | Inhalt |
| --- | --- |
| `chess_ai/evaluation.py` | Bewertung: Material, Figuren-Feld-Tabellen (Mittel-/Endspiel überblendet), Läuferpaar |
| `chess_ai/engine.py` | Iterative Vertiefung, Negamax mit Alpha-Beta, PVS, Transpositionstabelle, Null-Move-Pruning, Late-Move-Reductions, Schach-Verlängerung, Ruhesuche, Zugsortierung (MVV-LVA, Killer, History) |
| `chess_ai/cli.py` | Kommandozeile, Stockfish-Anbindung über UCI |

Schwächen, die bekannt sind und nicht behoben wurden: keine Bauernstruktur- oder
Königssicherheitsbewertung, kein Eröffnungsbuch, Python ist ~100× langsamer als C++.

## Tests

```bash
pip install pytest
pytest
```
