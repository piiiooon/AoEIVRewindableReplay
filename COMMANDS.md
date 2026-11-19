# Fogline: commands

The usual run (recent games -> download -> 3D page) is in `QUICKSTART.md`.

Folders: `C:\aoe4\aoe4-analyzer` (Fogline), `C:\aoe4\fogline-profile` (player profile),
`C:\aoe4\data-main` (aoe4world data, for icons). Replays play only on the game build they were made on.

## Record one replay (game runs, records, closes, builds both pages)

```powershell
cd C:\aoe4\aoe4-analyzer
python tools\record.py --name game4 --icons                        # newest replay in the playback folder
python tools\record.py C:\Downloads\replay.gz --name game4 --icons # a downloaded .gz (unpacked into playback)
python tools\record.py AgeIV_Replay_<id> --name game4 --icons      # a replay already in the playback folder
```
Options: `--speed 32` (slower, if the game crashes at 64 = 8x), `--keep-open`, `--no-run` (record only).
Output: `logs\<name>.log`, `views\<name>.html` (Fogline), `views\<name>.fights.html` (fight review).
After a failure: `logs\<name>.failed.log`.

## Rebuild pages from a recorded log (after an update; no re-recording)

```powershell
cd C:\aoe4\aoe4-analyzer
python run.py logs\game4.log --name game4 --icons
```
Options: `--no-open` (don't open the browser), `--replay <path>` (if the replay isn't found: no cameras / orders),
`--no-replay`, `--rate 0.4` (gather rate for the bank estimate).

Rebuild every recorded game:
```powershell
cd C:\aoe4\aoe4-analyzer
Get-ChildItem logs\*.log | Where-Object { $_.Name -notmatch '\.(recorded|failed)\.log$' } |
  ForEach-Object { python run.py $_.FullName --name $_.BaseName --icons --no-open }
```

## Batch: record a folder of replays, then profile a player

```powershell
cd C:\aoe4\fogline-profile
python batch.py C:/aoe4/marinelord --player marinelord                  # record what's missing, then profile
python batch.py C:/aoe4/marinelord --player marinelord --retry-failed   # also retry earlier failures
python batch.py C:/aoe4/marinelord --player marinelord --no-record      # profile only
```
Options: `--speed 32`, `--retries 1` (after a crash / stall, retry at half speed). Stop with Ctrl+C and run again
to continue. Status per replay: `profile\batch_state.json`.

## Profile only (after rebuilding games)

```powershell
cd C:\aoe4\fogline-profile
python profile.py --player marinelord
python profile.py --player marinelord --games replay_252595969 replay_252604108
```
Output: `profile\<player>.html` (links to each game's Fogline and fight pages).

## Basics page (your rules: gathering, floating, age-up saves, spending, trades)

Written by every rebuild as `views\<name>.basics.html`, from your side with `--player` (part of your in-game name):
```powershell
python run.py logs\game4.log --name game4 --icons --player 上杉謙信
```
Without `--player` it is written from player 1's side.

## Spikes page (army value + gap, power spikes, fights by line, composition / rally, resource nodes)

Written by every rebuild as `views\<name>.spikes.html` (rally points need the replay file). For an already recorded game:
```powershell
python analyzer\spikes.py work\game4.analyzed.json work\game4.spikes.json --replay <replay file>
python viewer\build_spikes.py work\game4.spikes.json views\game4.spikes.html
```
Unique techs / units need the `unique` flags in data\ (`python tools\update_data.py` adds them).

## Japanese pages (labels and controls; unit / tech names and longer explanations stay English)

Add `--lang ja` to any build; output gets a `.ja` suffix next to the English pages.
```powershell
cd C:\aoe4\aoe4-analyzer
python run.py logs\game4.log --name game4 --icons --lang ja        # views\game4.ja.html, views\game4.fights.ja.html
Get-ChildItem logs\*.log | Where-Object { $_.Name -notmatch '\.(recorded|failed)\.log$' } |
  ForEach-Object { python run.py $_.FullName --name $_.BaseName --icons --no-open --lang ja }
cd C:\aoe4\fogline-profile
python profile.py --player marinelord --lang ja                    # profile\marinelord.ja.html (links to .ja game pages)
```

## Geometry lines from a log (for checking map sizes)

```powershell
Select-String -Path 'C:\aoe4\aoe4-analyzer\logs\<name>.log' -Pattern 'A4D\|(V|PCAPS|PCV|PG|S|BH|HMH|RT)\|' |
  ForEach-Object { $_.Line } | Set-Content -Encoding UTF8 'C:\aoe4\geom.txt'
```

## In the pages

- Fogline: Sight (whose view; Everything = both), Show true values (review), Read (Gold / Bank / Castle timing /
  Economy (review)), Orders, Command rings, Impassable, Resources, Buildings (shapes / icons), Rotate, wheel = zoom,
  drag = pan, Shift+drag = rotate, double-click = whole map.
- Fight page: fight list and timeline marks jump to a fight; same zoom / pan / rotate.

## Download replays from the official stats API

`matchId:profileId` (any player of that match); unpacked into the playback folder, 5 s between requests:
```powershell
python tools\get_replay.py 252754529:1102458
python tools\get_replay.py --file matches.txt        # one matchId:profileId per line
python tools\record.py AgeIV_Replay_252754529 --name qual_1 --icons
```
