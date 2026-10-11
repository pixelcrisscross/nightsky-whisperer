# NightSky Whisperer — starter milestone 1

This is the first vertical slice: **Android orientation/location → local WebSocket → UNO Q**.
It does not yet run Whisper, Gemma, Piper, astronomy matching, or the screen-off service. Those are deliberately added after sensor transport is proven.

## Architecture decision

- USB-C may power the UNO Q if the phone can supply enough power; do not assume it can sustain the board under AI load.
- Use local Wi-Fi for telemetry for the first prototype. Phone and UNO Q must be on the same LAN; a phone hotspot is okay if it permits communication with connected clients.
- The Android app currently runs as a visible activity. Screen-off/foreground services and microphone/speaker streaming are a later milestone because Android imposes permission/lifecycle requirements for background microphone/location use.
- No cloud endpoints are used by this starter.

## A. Start the bridge on the UNO Q

Copy the `uno-q/` folder to the board (from your development PC):

```bash
scp -r uno-q arduino@192.168.29.53:~/nightsky-whisperer
```

On the UNO Q:

```bash
cd ~/nightsky-whisperer
sudo apt update
sudo apt install -y python3-venv
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python server.py
```

Expected output includes `Uvicorn running on http://0.0.0.0:8765`.

In another UNO Q terminal, find its LAN IP and test the service:

```bash
hostname -I
curl http://127.0.0.1:8765/health
```

It should return JSON with `"ok": true`. The service listens on all network interfaces but is intended for a trusted local network only; do not port-forward it to the internet.

## B. Build/install the Android sensor app

Requirements on the development PC: JDK 17, Android SDK Platform 35 + Build Tools, and Gradle. You do **not** need Android Studio if your Android SDK command-line tools are already configured. Check `flutter doctor -v` if you already have Flutter installed; it shows the Android SDK path.

Use **Gradle 8.9 specifically** for this starter (it pins Android Gradle Plugin 8.7.3). Download the binary ZIP from [the official Gradle 8.9 distribution](https://services.gradle.org/distributions/gradle-8.9-bin.zip), extract it (for example to `C:\Gradle\gradle-8.9`), and add `C:\Gradle\gradle-8.9\bin` to your Windows `PATH`. Reopen VS Code after changing `PATH`. Open the `android/` folder in VS Code. In its terminal, run the following once to generate a project-local Gradle Wrapper:

```powershell
gradle --version
gradle wrapper --gradle-version 8.9
.\gradlew.bat assembleDebug
```

After the first wrapper setup, build using `\gradlew.bat assembleDebug` from the `android/` directory. Android Gradle Plugin 8.7 requires Gradle 8.9 and JDK 17, and supports API level 35. See the [AGP compatibility table](https://developer.android.com/build/releases/about-agp) and [Gradle installation guide](https://docs.gradle.org/current/userguide/installation.html).

APK output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Install over USB with Android platform-tools/ADB:

```bash
adb devices
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

If the Android SDK is not configured, set `ANDROID_HOME` to the SDK directory reported by `flutter doctor -v` and install Android SDK Platform 35 + Build Tools using `sdkmanager`. Ensure `JAVA_HOME` points to JDK 17.

## C. Connect the phone to the UNO Q

1. Put the phone and UNO Q on the same local Wi-Fi, or enable the phone hotspot and connect the UNO Q to it.
2. On the UNO Q, run `hostname -I` and identify the IP on that shared network (not `127.0.0.1`).
3. Open **NightSky Phone Bridge** on the phone.
4. Enter `ws://<UNO_Q_IP>:8765/ws/phone` in the URL box and press **Connect to UNO Q**.
5. Grant location permission. Enable phone Location and wait outdoors/near a window for a location fix.
6. Rotate/tilt the phone. The UI should display heading/pitch/roll and location; the event log should show a server acknowledgement periodically.

On the UNO Q, `/latest` should now include the most recent telemetry:

```bash
curl http://127.0.0.1:8765/latest
```

`/health` should show a non-zero `telemetry_count` and `connected_clients: 1` while the app is connected.

## D. First milestone acceptance criteria

- [ ] Phone WebSocket connects to UNO Q.
- [ ] Telemetry arrives at about 5 Hz (200 ms cadence).
- [ ] Location fields populate after permission and a fix.
- [ ] Rotation vector and heading/pitch/roll change when the phone is moved.
- [ ] No external internet is required after packages/build tools are installed.

Do not use the heading values for sky-object acquisition yet. First calibrate how the phone is physically held and determine which phone axis points toward the sky. The displayed heading is the **top-edge azimuth**, not necessarily the screen-normal azimuth.

## Next milestones

1. Define the phone pointing vector and calibrate with known directions.
2. Add deterministic sky coordinates/ephemeris and a target database; validate Alt/Az output.
3. Drive the UNO Q LED matrix for scan/arrow/acquired states.
4. Stream microphone PCM from phone → UNO Q, then validate Whisper.cpp transcription.
5. Add Piper TTS and stream audio back to Android `AudioTrack`/speaker.
6. Add Gemma with structured astronomy facts, guided story trees, and persisted session memory.
7. Move sensors/audio into a permission-correct Android foreground service for screen-off operation.
8. Test power draw and thermal stability before claiming phone-powered standalone operation.
