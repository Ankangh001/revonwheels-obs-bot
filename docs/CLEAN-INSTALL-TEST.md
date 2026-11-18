# Clean-install test — 18 November 2026

The local clean-install workflow was exercised on the user's laptop with OBS Studio 33.0.1, Aitum Stream Suite 1.2.6 and the rebuilt Windows app. Automatic setup, live capture and audio were verified. One native OBS shutdown crash remains unresolved; a stop-music-before-exit workaround passed two later shutdowns. This is not a claim of fault-free software or public-platform reception.

## Verified

- Backed up original OBS configuration, controller data, installed files and plugins: 2,859 snapshot files, approximately 672 MiB, with a checksum manifest. Original directories and clean-test results remain local and ignored by Git.
- Uninstalled OBS and verified its executable was absent. Installed the official, SHA-256-verified OBS and Aitum downloads.
- OBS installer initially returned code 6 because Chrome and Slack background processes held the OBS virtual-camera DLL. After the user saved/closed the apps and their residual processes were stopped, installation returned 0.
- Started with fresh OBS and app data. The packaged app opened its prerequisite guide. The user enabled authenticated WebSocket access; the portrait canvas was configured manually at 720x1280.
- Used the packaged Prepare PS5 button to create eight managed scenes. Repeated preparation with the final rebuilt executable succeeded without duplicating scenes.
- Selected UGREEN 25773, verified 1920x1080 at 60 fps, moving Tekken 8 frames, and the portrait centre crop. Camera was not added.
- Selected the uniquely matched UGREEN audio interface. OBS input-meter peak reached approximately 0.57 linear amplitude while game sound played. Muted the duplicate default Mic/Aux card route during clean testing.
- Verified custom artwork copying/application, included artwork restoration, banner music playback state, Safe Screen and Resume on both canvases.
- Saved short local recordings, including gameplay. Verified scene and quality persistence after restart. Recordings were not externally uploaded; local save does not prove platform delivery.
- Restored original profiles, channel/output settings and app data; applied capture fixes and disabled the unverified sample countdown in managed scenes. Main, Twitch, Kick and vertical outputs were stopped. No public broadcast was started.
- 62 automated tests pass. The executable was rebuilt and its Prepare PS5 flow was retested.

## Fixes from the test

1. Replaced stalling GetOutputList with independent core status calls plus Aitum status. Unknown activity blocks changes; explicitly unavailable replay buffer is handled. Other vendors' custom outputs are outside the supported guard.
2. Prevented the Open OBS button launching a second OBS process.
3. Opened the prerequisite guide for first-time users.
4. Preferred an advertised MJPEG capture mode. Auto selected YUY2 on this UGREEN card and produced a zero-size/black source at 1080p60; MJPEG produced live video.
5. Matched a separate audio interface only when its displayed name uniquely includes the selected card name. Other microphones are not selected as card audio.
6. Corrected the portrait transform field to cropToBounds.
7. Disabled the unverified sample release countdown by default. Existing explicitly enabled preferences remain opt-in.
8. Added installer-lock and default-microphone duplication guidance.

## Remaining limitation

OBS crashed once during shutdown while banner media was playing. Its saved native stack points to obs.dll copy_audio_data / obs-ffmpeg mp_media_thread during obs_shutdown. Stopping banner media before closing avoided the crash on two subsequent checks, but the native defect has not been fixed. Stop the media source before exiting; retain the local crash log for further diagnosis. Normal app closure does not close OBS.

Windows administrator prompts, enabling authenticated control, canvas creation, console HDCP/audio settings and platform account/stream-key setup still require one-time manual steps. This laptop test is not a clean Windows VM test. Public YouTube/Twitch/Kick reception, long-duration stability and end-viewer quality were not tested.
