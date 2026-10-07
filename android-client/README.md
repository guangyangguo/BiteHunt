# BiteHunt Android Client

Android WebView MVP for the public user-facing map page. The admin page remains a normal web page.

## What It Loads

By default the app loads:

```text
http://10.0.2.2:5000/
```

`10.0.2.2` is the Android emulator alias for the host machine. For a physical phone, edit `gradle.properties`:

```properties
TANDIAN_WEB_URL=http://YOUR_SERVER_OR_LAN_IP:5000/
```

Then rebuild the app.

## Build

This repo does not currently include a Gradle wrapper. Build from Android Studio or with a machine that has Android Gradle tooling installed:

```powershell
cd F:\tandian\tandian-app\android-client
gradle :app:assembleDebug
```

## Notes

- The Flask backend must be reachable from the Android device.
- Dev HTTP is allowed through `network_security_config.xml`.
- Location permission is requested when the WebView page asks for geolocation.
