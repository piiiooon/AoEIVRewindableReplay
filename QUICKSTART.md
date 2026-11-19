# Fogline quickstart: profile → match → 3D replay

The usual run: open a player's recent games, download one, record it and build the 3D page.
All commands run in PowerShell from `C:\aoe4\aoe4-analyzer`. The full cheat sheet is in `COMMANDS.md`.

```powershell
cd C:\aoe4\aoe4-analyzer
```

## 0. One-time setup: models and icons (not in git)

`models\` and `icons\` hold game art, so they are never committed or shipped. Each PC makes its own copy.

**Models** (3D page; without them the 3D page draws plain boxes). They are read from your own game installation:
```powershell
python tools\setup.py                        # finds the game through Steam, installs .NET + AOEMods.Essence into toolchain\
python tools\setup.py --game "F:\SteamLibrary\steamapps\common\Age of Empires IV"   # if the game isn't found
python tools\setup.py --heavy eng,jpn        # also the textured models for these civs (--detail medium / heavy)
python tools\setup.py --clean                # delete the unpacked archives (several GB) when done
```
It writes `data\game_weapons.json`, `models\artmap.json`, `models\stamps.json`, `models\unit_models.json` and
`models\parts\`; steps already done are skipped, so it is safe to run again. The same steps by hand:
```powershell
python tools\game_assets.py check            # .NET, Essence and the game archives found?
python tools\game_assets.py attrib; python tools\game_assets.py weapons
python tools\game_assets.py artmap; python tools\game_assets.py stamps
python tools\unit_models.py
python tools\game_assets.py export-parts
python tools\game_assets.py export-parts --detail heavy --civs eng,jpn   # optional, textured -> models\parts_heavy\
```

**Icons** need no setup: `--icons` downloads the ones a game needs from data.aoe4world.com and caches them in `icons\`.
To work offline, put a copy of github.com/aoe4world/data named `data-main` (or `aoe4world-data`) in or next to this
folder (here `C:\aoe4\data-main`): `run.py` then takes the icons from it, with icons on by default.

## 1. Open the player's recent games

```powershell
python tools\get_replay.py --recent 14940077 --page --n 10
```
This opens `views\history_14940077.html`. It lists the last 10 games with their type, map, players and match ID.
Tick a game there and copy the download command.

Without the page: `python tools\get_replay.py --recent 14940077 --list --n 5` prints the same list in the terminal.

## 2. Download the match

Paste the command the page copied, or type it:
```powershell
python tools\get_replay.py 260952857:14940077          # matchId:profileId
python tools\get_replay.py --recent 14940077 --n 1     # or just that player's most recent game
```
The replay is unpacked into the playback folder as `AgeIV_Replay_<matchId>`.

## 3. Record it and build the 3D page

```powershell
python tools\record.py AgeIV_Replay_260952857 --name mygame --icons --out "fights,3d"
```
Result: `views\mygame.3d.html`. The game starts, plays the replay at 8x, closes, and the pages are built.
For the 2D page as well, use `--out "viewer,fights,3d"`.

**Always quote the `--out` value.** Unquoted, PowerShell turns `3d` into `3` and the build fails with
`--out: unknown page(s) 3`.

## Rebuild without recording again

The recording is kept as `logs\<name>.recorded.log`. After a failed build or a Fogline update, run:
```powershell
python run.py logs\mygame.recorded.log --name mygame --icons --out "fights,3d" `
  --replay "$env:USERPROFILE\Documents\My Games\Age of Empires IV\playback\AgeIV_Replay_260952857"
```
`--replay` adds the cameras, orders and rally points.

## Useful options

| Option | Command | Effect |
| --- | --- | --- |
| `--custom` | get_replay | custom lobbies only (no matchmaking games) |
| `--speed 32` | record | slower playback, for when the game crashes at 8x |
| `--keep-open` | record | leave the game open afterwards |
| `--full-read` | record | re-read every value every second (default caches values that rarely change; decision 0007) |
| `--detail medium` / `heavy` | record, run | textured 3D models (needs the textured export) |
| `--player <name>` | record, run | basics page from that player's side |
| `--no-open` | run | don't open the browser |

## When it doesn't work

- **The replay won't load:** a replay plays only on the game build it was made on. Record games before the next patch.
- **Untextured boxes instead of models:** the 3D page needs the models exported on this PC (`models\`,
  `python tools\game_assets.py export-parts`). They are game files and are not in git.
- **Recording failed:** the log is kept as `logs\<name>.failed.log`. Try again with `--speed 32`.
