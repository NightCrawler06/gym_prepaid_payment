# Gym QR Credit Mobile

Mobile companion app for the gym prepaid credit system. This version is designed for phones when the client does not have a laptop available.

## Features

- Register members on the phone
- Generate a unique QR token per member
- Show the generated QR on screen
- Top up credits
- Scan member QR codes using the phone camera
- Deduct one credit only on the first valid scan of the day
- Mark same-day duplicate scans as already scanned
- Use the same XAMPP MySQL database as the desktop app through a PHP API

## Stack

- Expo
- React Native
- expo-camera
- PHP API on XAMPP

## Install

```powershell
cd C:\Users\USER\Documents\Playground\mobile_app
npm install
```

## Run

```powershell
cd C:\Users\USER\Documents\Playground\mobile_app
npm run start
```

Then open the project in Expo Go or run it on an Android device/emulator.

## API setup

1. Copy [xampp_api](C:\Users\USER\Documents\Playground\xampp_api) into your XAMPP `htdocs` folder.
2. Copy `xampp_api/config.example.php` to `xampp_api/config.php`.
3. Update the database settings in `config.php`.
4. Set the correct API URL in [src/apiConfig.js](C:\Users\USER\Documents\Playground\mobile_app\src\apiConfig.js).

Example:

```javascript
export const API_BASE_URL = "http://192.168.1.100/xampp_api";
```

Use the laptop's local network IP address so the phone can reach it.

## Notes

- The phone and the laptop must be on the same Wi-Fi network.
- Apache and MySQL must be running in XAMPP.
- The desktop app can use the same MySQL database by creating `db_config.json` in the repo root.
