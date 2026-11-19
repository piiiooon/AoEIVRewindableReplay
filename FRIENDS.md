# Fogline: quick start

Reads an Age of Empires IV replay and builds pages you open in the browser: the replay viewer (what one player could
see, their bank estimate, reviews), the fights page, and a 3D replay. Windows, Steam version of the game.

## 1. Once

1. Install **Python 3.8 or newer** from python.org (tick "Add python.exe to PATH" in the installer).
2. Unzip this folder anywhere, e.g. `C:\fogline`.
3. Open PowerShell in that folder and run:
   ```powershell
   python tools\setup.py
   ```
   It finds the game through Steam (otherwise add `--game "D:\SteamLibrary\steamapps\common\Age of Empires IV"`),
   downloads the archive reader (AOEMods.Essence) and, if needed, a .NET runtime into `toolchain\`, then reads
   weapon values and 3D models from your game. The first run unpacks several GB and takes a while; `--clean` deletes
   the unpacked archives afterwards. Run it again after a game patch.

## 2. Record a replay

Close the game first. Then:
```powershell
python tools\record.py --name game1 --out viewer,fights,3d --icons     # newest replay in the playback folder
python tools\record.py C:\Downloads\replay.gz --name game2 --icons      # a downloaded replay
```
The script starts the replay with `-dev` through Steam, records it at 8x speed and closes the game. Don't use the PC
for typing while it runs (it sends keys to the game console). `-dev` turns off multiplayer for that session only; start
the game normally to play online. Replays only play on the game version they were made on.

Pages appear in `views\`: `game1.html` (viewer), `game1.fights.html` (fights), `game1.3d.html` (3D).

## 3. Rebuild pages without re-recording

```powershell
python run.py logs\game1.log --name game1 --out viewer,fights,3d --icons
```
Options: `--player <part of your name>` (your side for the review pages), `--detail medium|heavy` for the 3D page with
the game's textures (first: `python tools\setup.py --heavy vik,sco` with the art prefixes of the civs you want, e.g.
eng, fre, hre, rus, mon, chi, abb, sul, mal, ott, jpn, byz, jin, lan, tem, sco, vik).

## Notes

- The 3D page needs an internet connection when opened (it loads three.js from cdnjs).
- See NOTICE.txt: nothing from the game is in this zip; your own installation provides it. Free, non-commercial use.
- More commands: COMMANDS.md.
