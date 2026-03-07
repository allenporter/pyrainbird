# Rain Bird Controller - Communication Protocol Specification (V2)

This document outlines the communication protocol for Rain Bird WiFi-enabled irrigation controllers.

## 1. Discovery Protocol (UDP)
To find devices on the local network, a UDP broadcast is used.

- **Broadcast Address:** `255.255.255.255`
- **Destination Port:** `33667`
- **Source/Listening Port:** `33668` (Standard API uses HTTP), or other ports if specified in the app.
- **Discovery Payload:** `RBD-ANDROID` (Hex: `52 42 44 2d 41 4e 44 52 4f 49 44`)
- **Controller Response:** The controller returns a UDP packet where the payload is the **Hexadecimal representation of the Controller MAC Address**.

### Discovery Protocol Versioning
The communication protocol (HTTP vs HTTPS) is often determined by the response port:
- **Port 33668:** Historically associated with standard HTTP communication.
- Newer versions of the app/firmware might signal HTTPS support via these ports.

## 2. API Communication (JSON-RPC 2.0)
Most interaction occurs via standard JSON-RPC 2.0.

- **Endpoint:** `http://<CONTROLLER_IP>/stick` (Default), `http://<CONTROLLER_IP>/stick:80`, or `https://<CONTROLLER_IP>/stick`.
- **Format:** Standard JSON-RPC 2.0 (`jsonrpc: "2.0"`, `method`, `params`, `id`)
- **Key Method:** `tunnel` (Used for wrapping serial commands).

### Common JSON-RPC Methods
While `tunnel` is the most important for control, others include:
- `getControllerInfo`: Returns basic device metadata.
- `setControllerPassword`: Used to change the device password.
- `tunnel`: Wraps SIP commands (see below).

## 3. Security & Encryption
The application uses AES-256-CBC for payload security when encryption is enabled.

- **Encryption Algorithm:** AES-256-CBC
- **Padding:** `NoPadding` (Plaintext JSON must be null-padded (`\x00`) to the nearest 16-byte boundary).
- **Key Derivation:** The AES key is a `SHA-256` hash of the controller's password.
- **Initialization Vector (IV):** A random 16-byte IV is generated for each request.

### Request Packet Structure (Binary)
Encrypted requests follow this header structure:
1. **Plaintext Hash (32 bytes):** SHA-256 hash of the **unencrypted** JSON-RPC payload.
2. **IV (16 bytes):** The random Initialization Vector.
3. **Encrypted Payload (Variable):** The AES-encrypted JSON-RPC payload.

**Note:** If encryption is disabled, the request is sent as a raw JSON string (often with backslashes removed, though this appears to be an app-side optimization).

## 4. SIP Tunneling (Serial Interface Protocol)
Rain Bird uses a "tunnel" method to send low-level serial commands (SIP) over the RPC interface.

### Example Request
```json
{
  "jsonrpc": "2.0",
  "method": "tunnel",
  "params": {
    "data": "<HEX_COMMAND>",
    "length": <HEX_COMMAND_LENGTH>
  },
  "id": 1
}
```

### SIP Command Keys & Hex Codes
Below is a list of known SIP command hex codes used in the `data` field:

| Command Name | Hex Code | Description |
|--------------|----------|-------------|
| `NOT_ACKNOWLEDGE_RESPONSE` | `00` | NACK |
| `ACKNOWLEDGE_RESPONSE` | `01` | ACK |
| `MODEL_AND_VERSION_REQUEST` | `02` | Request Model/Version |
| `AVAILABLE_STATIONS_REQUEST` | `03` | Get available zones |
| `SERIAL_NUMBER_REQUEST` | `05` | Get Serial Number |
| `CURRENT_TIME_REQUEST` | `10` | Get Controller Time |
| `SET_CURRENT_TIME_REQUEST` | `11` | Set Controller Time |
| `CURRENT_DATE_REQUEST` | `12` | Get Controller Date |
| `SET_CURRENT_DATE_REQUEST` | `13` | Set Controller Date |
| `RAIN_DELAY_REQUEST` | `36` | Get Rain Delay |
| `RAIN_DELAY_SET_REQUEST` | `37` | Set Rain Delay |
| `MANUALLY_RUN_PROGRAM_REQUEST` | `38` | Run a specific program |
| `MANUALLY_RUN_STATION_REQUEST` | `39` | Run a specific zone |
| `CURRENT_RAIN_SENSOR_STATE` | `3E` | Get Rain Sensor status |
| `STOP_IRRIGATION_REQUEST` | `40` | Stop all watering |
| `ADVANCE_STATION` | `42` | Skip to next station |
| `IRRIGATION_STATE_REQUEST` | `48` | Get current irrigation state |
| `COMBINED_CONTROLLER_STATE_REQUEST` | `4C` | Get full status summary |

*Note: Response codes are typically the request code + 0x80 (e.g., Request 0x02 has Response 0x82).*

## 5. Implementation Notes for Home Assistant
To implement this in Home Assistant, the integration should:
1. **Discovery:** Use UDP broadcast on port 33667 to locate controllers.
2. **Authentication:** The user must provide the controller password, which is hashed via SHA-256 to create the AES key.
3. **Communication:** Wrap SIP commands in a JSON-RPC `tunnel` call, encrypt the JSON payload (if required), prepend the hash and IV, and send via POST to the controller's `/stick` endpoint.
