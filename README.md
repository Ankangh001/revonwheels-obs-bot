# RevOnWheels OBS Bot

A local Windows app and command bot that prepare and control landscape and portrait OBS scenes for PC GTA gameplay or a PS5 HDMI capture card. The terminal controller uses Python's standard library; desktop image rendering uses Pillow. No API subscription is required.

## Windows desktop app

The desktop preview is **RevOnWheels.exe**. Download it from this repository's Releases page and double-click it. The executable bundles Python, Tk and the media pack; users do not need a separate Python installation. OBS and Aitum remain separate requirements. This preview is unsigned and has not been tested on a clean Windows VM or certified for general public distribution.

The app has five tabs, with a neon pink/cyan/plum sunset theme, an original tropical background and a generated RevOnWheels logo:

- **Stream controls:** Starting Soon, Gameplay, BRB, Safe Screen/resume, microphone/camera controls, quality selection, replay highlights and Go Live/Stop buttons. Go Live asks for a choice before requesting the configured outputs. Launching or closing the app does not start/stop streams.
- **Prerequisite guide:** eight steps from OBS installation through platform checks. Select steps on the left, read the instructions, use the relevant action buttons, and mark completion. Progress stays local and is user-reported, not proof of readiness.
- **Artwork & music:** choose the included theme or select your own local banner images/music, preview artwork, switch banner music/countdown on or off, and apply changes with outputs stopped. See media details below.
- **Setup tools:** official dependency download/install buttons, PS5/PC setup, device selection and setup validation. It does not auto-install software or change console settings.
- **Activity:** command results and errors. Connection/output/scene cards refresh approximately every six seconds. They report encoder activity, not guaranteed public platform reception. There are no live audio meters or embedded video preview in this version; check OBS for those.

Packaged-app settings, downloads, assets, backups and safe-state live in `%LOCALAPPDATA%/RevOnWheels`. They persist across launches and are not bundled into the executable. Existing files are preserved on subsequent launches; new bundled media is copied only when absent. To carry over an existing bot setup, use **First-time setup > Import existing bot** and choose its folder. This copies local config/ownership/safe-state files and backs up the app's current copies. Do this against the same OBS collection and use one controller at a time; the source CLI and packaged app keep separate local state folders. Local import and OBS status/setup validation passed in the actual executable.

To run the graphical app from source (Python required):

```powershell
python -m pip install -r requirements-desktop.txt
python desktop.py
```

Or double-click `Start App.cmd`. The original `Start Bot.cmd` remains available for terminal commands.

To build your own Windows x64 executable with Python 3.12:

```powershell
python -m pip install -r requirements-build.txt
python build_app.py
```

The result is `dist/RevOnWheels.exe`. Build on Windows. Build tools and generated binaries are ignored by Git; attach the executable to a GitHub Release for distribution. Code signing and an installer are separate distribution steps, not included in this portable preview.

## What it does

- Builds eight scenes: Starting Soon, Gameplay, Be Right Back and Safe Screen in both formats.
- Adds bundled artwork, banner music and a local browser countdown.
- Fits landscape gameplay and uses a centre crop for portrait.
- Detects a unique recognised HDMI capture card or running GTA game window.
- Automatically selects an advertised PS5 capture mode up to 1080p60 and matches the main OBS output resolution/frame rate. It falls back to a supported 1080p or 720p mode at 30–60 fps. It backs up the prior settings and restores them if selection or readback fails. Portrait resolution, audio, colour interpretation and encoder bitrate remain unchanged.
- Creates game audio and a microphone when needed, reusing existing global audio to avoid doubled sound. A newly created microphone starts muted.
- Keeps the webcam off and supports manual scene changes, Safe Screen, microphone control, stream start/stop and replay highlights.
- Downloads the official OBS or Aitum Windows installer and checks the SHA-256 digest published with its GitHub release.

## Requirements

Windows x64, Python 3.10+, OBS Studio and Aitum Stream Suite. Windows ARM and macOS/Linux are not supported by the installer helper. OBS must remain open for scene commands.

OBS includes WebSocket; do not install an old standalone obs-websocket plugin. In OBS, open **Tools > WebSocket Server Settings**, enable the server and keep authentication enabled. The bot reads the existing password locally from OBS configuration and connects only to `127.0.0.1`. It does not print or upload it. Keep the server private; firewall/network exposure is controlled by OBS and Windows.

Create one Aitum canvas named exactly **YouTube Vertical**, sized **720 x 1280**. This is a one-time manual step: the API exposed by the tested installation does not create canvases. A completely fresh OBS installation still requires this bootstrap; empty scene/source lists are supported after it.

## Install or download dependencies

Clone or download this repository, keeping the assets folder beside the scripts. Install Python 3.10+ from https://www.python.org/downloads/windows/ if necessary.

Before OBS is configured, the standalone helper works:

```powershell
python dependencies.py check
python dependencies.py download aitum
python dependencies.py download obs
```

Or type these inside the bot:

```text
dependencies check
dependencies download aitum
dependencies download obs
```

Downloads come only from the official `Aitum/obs-aitum-stream-suite` and `obsproject/obs-studio` GitHub release repositories. The helper chooses the latest stable release and refuses assets without a SHA-256 digest or with a mismatched download. This verifies against GitHub release metadata, not a separate publisher signature or a compatibility guarantee. Installers stay in the ignored `downloads` folder. No installer runs as part of download.

**Close OBS yourself before installing.** To open the verified native installer:

```powershell
python dependencies.py install aitum
python dependencies.py install obs
```

The Windows installer may request administrator approval, licence acceptance and destination choices. Finish its prompts, reopen OBS, then run `doctor`. Installer launch alone does not mean installation succeeded. The helper does not silently close OBS, bypass UAC, choose additional optional plugins, or upgrade an existing installation automatically. Check release notes for your OBS version before replacing a working plugin. Your machine may already have everything required.

Official references: [OBS Windows installation](https://obsproject.com/kb/windows-installation), [Aitum releases](https://github.com/Aitum/obs-aitum-stream-suite/releases), [OBS releases](https://github.com/obsproject/obs-studio/releases).

## First run

1. Optionally copy `config.example.json` to `config.json`. The bot uses the example if no local config exists; setup writes a local config when required.
2. Open OBS and complete WebSocket/Aitum bootstrap above.
3. Stop every stream, recording, replay buffer and virtual-camera output before automatic setup.
4. Double-click **Start Bot.cmd**, or run `python bot.py`.
5. Run `doctor`, then one setup command below.

### PS5

Connect PS5 HDMI OUT to the capture card HDMI IN, then connect the card USB port to the laptop. For passthrough, connect capture HDMI OUT to your display if available. Disable PS5 HDCP under Settings > System > HDMI for game capture. Headset/party-chat routing may need separate setup; check actual game sound in OBS.

```text
setup auto ps5
```

The bot creates scenes/sources, selects a single clearly recognised capture card, prepares audio, routes its commands and shows Starting Soon. It never starts broadcasting during setup. No card gives a pending placeholder. Multiple candidates require selection:

```text
devices
capture ps5 2
setup check
```

Use the actual device number, not necessarily 2. Obvious webcams and virtual cameras are rejected. Generic USB device names may need manual selection. Video/audio signal quality cannot be established just from the device name. Preview both layouts and audio meters before streaming.

### PC GTA

Launch exactly one GTA game, then run:

```text
setup auto pc
```

The bot creates a window-specific Game Capture source and selects a recognised GTA window. If the game is absent or ambiguous, capture stays pending; launch the game and rerun. It does not fall back to sharing your desktop. Default desktop audio may include other application sounds; mute them or adjust OBS audio routing.

### Existing setups

`setup plan` inspects without changing OBS. `setup pc` reuses an existing `GTA V Game Capture` source unless the automatic source has already been configured. `setup ps5` builds/repairs PS5 scenes without automatically choosing a card. `setup stage` adds inactive PS5 scenes while live, but refuses to change any active managed source. `setup activate` selects the managed scenes and routes the bot. `setup rollback` restores saved bot routing and deletes nothing; it does not undo every scene/source change.

Only bot-owned `ROW - ...` scenes and sources are repaired. Unmanaged name collisions stop setup. Existing scenes, encoder profile, output destinations, account settings and stream keys are preserved. Do not delete the ownership manifest if you intend to repair an existing managed setup; without it, existing ROW names are treated as collisions. Each bot folder should manage one OBS scene collection; ownership is local and not a universal cross-collection registry.

## Commands

| Command | Result |
| --- | --- |
| `help`, `quit` | List commands or exit bot; quitting does not stop streams |
| `doctor`, `status` | Connection checks and sanitised output activity |
| `setup auto ps5`, `setup auto pc` | Create capture, scenes and audio, then select Starting Soon |
| `setup plan`, `setup check` | Inspect plan or validate scene structure |
| `setup ps5`, `setup pc`, `setup stage` | Build/repair or stage layouts |
| `setup activate`, `setup rollback` | Select managed setup or restore saved routing |
| `devices`, `capture ps5 N` | Enumerate capture devices and choose a card |
| `quality auto` | Choose supported PS5 capture quality and match main OBS output; outputs must be stopped |
| `prepare`, `gameplay`, `brb` | Switch both formats |
| `safe`, `resume` | Cover/mute, or restore saved scenes/mutes |
| `camera off`, `mic on`, `mic off` | Camera visibility and microphone mute |
| `live all` | Request main YouTube, Twitch, Kick and YouTube Vertical outputs |
| `live youtube` | Request main YouTube and YouTube Vertical outputs |
| `stop` | Stop stream outputs; recordings remain running |
| `highlight` | Save an already-running Replay Buffer |
| `links` | Show links you added to local config |
| `dependencies check` | Explain dependency setup |
| `dependencies download aitum`, `dependencies download obs` | Download and verify official installer |
| `dependencies install aitum`, `dependencies install obs` | Recheck download and open native installer |

Single commands also work from a terminal: `python bot.py setup auto ps5`.

## Before broadcasting

`setup auto ps5` and `capture ps5 N` now include automatic quality selection. For an already configured card, run `quality auto`. The command targets 1920x1080 first, then 1280x720, with the highest enabled advertised frame rate between 30 and 60 fps. OBS's Auto video format negotiates with the driver. It will not force an unsupported 4K mode or overwrite colour/audio settings. A smaller-than-selected base canvas is rejected so existing layouts are not silently moved.

Live verification with UGREEN 25773: capture requested at 1920x1080/60, main OBS output changed from 1280x720/60 to 1920x1080/60, and settings readback passed. This does not prove USB stability, effective delivered frame rate or Internet streaming quality. Preview and check sound; choose platform bitrates for your connection separately. This bot cannot remotely change PS5 resolution or HDCP: use the console's Settings > Screen and Video > Video Output > Resolution > 1080p if necessary. Reopen the bot after code updates to load new commands.

Connect your platform accounts or paste stream keys directly into OBS/Aitum. Do not put keys in this repository or chat. Match your output names to the `outputs` array in local config. Main OBS streaming must target YouTube for `live youtube` to mean YouTube; the bot uses existing settings and does not reconfigure services.

Create/select the correct YouTube broadcast in Studio/OBS. Set up the separate vertical encoder and match its key where required. The bot starts encoder outputs, not new YouTube events, metadata, schedules or guaranteed public broadcasts. YouTube may require **Go live** in Studio. Check all platform dashboards and stream visibility. `live` can broadcast publicly with existing settings.

Set your own channel links in local config; the example deliberately has none. Existing event URLs may refer to ended broadcasts.

## Artwork, countdown and music

The **Artwork & music** tab offers **Included theme** and **My images & music**. Choose a landscape Starting Soon image, portrait Starting Soon image, a shared break/safe background and optional banner music. Images support PNG/JPG/JPEG/WebP; music supports WAV/MP3/OGG/FLAC/M4A. Image contents are checked; audio playback must still be checked in OBS. Selecting files copies them to the local `custom-media` folder with unique names; originals are untouched and nothing is uploaded. Slots without a custom file use the bundled asset. Reset restores a slot to its included asset without deleting your original or copied file.

Selections save immediately, but **Apply media to OBS** updates the existing managed scenes only after all outputs stop. Alternatively, your next automatic setup uses the choices. Stop streams, recordings/replay buffers and virtual camera first. Turning banner music/countdown off disables their existing scene items in both layouts; turning them back on re-enables them. Media application preserves the current scene selection and capture settings.

The app's header/logo are bundled brand graphics, separate from the stream banner choices. Files: `assets/revonwheels-logo.png` (transparent channel logo) and `assets/vice-sunset-background.png` (original GTA VI-inspired coastal artwork, not official Rockstar key art). Full generation prompts are in `assets/ASSET-PROMPTS.md`. The app icon uses the same logo. Imported custom media and tutorial progress are excluded from Git.

The assets are the existing RevOnWheels stream pack. Replace the three images and WAV with your own assets if desired, keeping filenames or updating `FILES` in `setup_obs.py`. Ensure you have permission to use any replacement media. The images are not an official Rockstar product or endorsement.

**The bundled countdown date is a sample copied from the existing setup, not a verified GTA VI launch time.** Edit `assets/gta-vi-countdown.html` before going live: change both `target` in the script and the visible note. It does not check release announcements. Never present its date as an official release promise.

Music loops on banner scenes at -8 dB. If either canvas still shows a banner, music may remain audible even when the other shows gameplay. Balance microphone/game/music in OBS and preview the stream. No music is added directly to gameplay scenes.

## Safety and limitations

Safe Screen is manual, with an opaque card and configured audio mutes; it is not automatic sexual-content detection, nudity blurring or guaranteed censorship. It cannot retract already transmitted frames. Test both canvases. Safe Screen keeps a local latch until `resume`; Cut transitions remain selected afterward. Camera stays off on resume. An error may leave a partially applied action: inspect OBS.

No voice control, AI scene understanding, OAuth onboarding, automatic platform metadata, automatic capture-loss recovery, stream-key discovery or unattended fresh-install bootstrap is implemented. The laptop and OBS must remain running. Dependency downloads need Internet; normal local OBS commands do not need a cloud service.

## Troubleshooting

- **OBS config/server missing:** open OBS, enable authenticated WebSocket and Apply. Portable OBS configuration is not auto-discovered; the current reader uses `%APPDATA%/obs-studio`.
- **Aitum canvas missing:** install Aitum, restart OBS, add the exact canvas name/dimensions above.
- **Outputs active:** stop OBS and Aitum streams plus recordings/replay/virtual camera before setup. `stop` only stops streams.
- **Capture pending:** connect the card or launch GTA, then rerun the matching automatic command. Check devices and game window selection.
- **Black PS5 picture/no audio:** verify HDMI/USB connections, HDCP and PS5 output/headset routing; confirm card compatibility and OBS meters.
- **Browser countdown invisible:** check the HTML file path/source, preview after the scene becomes active and verify Browser Source is installed with OBS.
- **Unmanaged name collision:** rename your conflicting source/scene or use a separate collection; the bot will not overwrite it.
- **Partial setup:** correct the reported issue and rerun. Managed creation is repeatable, not a transaction that undoes all prior actions.
- **OBS not ready during collection switching:** wait for OBS to finish. The tested OBS 33.0.1 instance failed during an empty-collection integration attempt; restarting with the original collection recovered it. Do not switch collections during a broadcast.
- **Download failed:** check Internet/GitHub API rate limits. A missing digest is an intentional refusal; use the linked official release page to inspect manually.

## Privacy and local files

Git ignores `config.json`, device IDs, ownership/safe-state manifests, backups, preview images, downloads and logs. No stream keys or OBS passwords belong in committed files. Configuration/backups may include channel links and local device information. Review `git status` before publishing changes. Add credentials only inside OBS's own account/settings UI.

## Development and validation

```powershell
python -m unittest -v
```

53 tests cover authenticated WebSocket framing, scene/canvas routing, zero-source mock construction, repeat builds, device ambiguity, safe-screen behaviour, official-download selection, quality fallback/rollback, desktop status, local import, Go Live confirmation, custom media copying/validation and disabling/re-enabling media in both formats. These mocks cannot prove a working PS5 HDMI signal or public platform reception. The standalone executable was also launched on the development machine, connected to OBS, imported existing settings, and verified all eight scenes without starting a broadcast.

Live validation on 18 November 2026: backed up the existing collection, cleared both canvas scene lists and all inputs, verified zero remaining inputs and scene items, then ran `setup auto ps5`. The bot rebuilt all eight scenes from scratch. Landscape/portrait artwork, countdown and safety cards were visually checked; `safe`, `resume` and `prepare` passed. All stream outputs remained stopped, and absent capture hardware was correctly reported as pending. This proves the empty-scene/source workflow with an existing Aitum canvas and configured OBS; a fresh installation and real HDMI signal remain unverified. Back up your own collection before attempting a destructive reset.

Protocol references: [OBS WebSocket](https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md), [Aitum vendor API](https://github.com/Aitum/obs-aitum-stream-suite/blob/main/src/utils/obs-websocket.cpp).
