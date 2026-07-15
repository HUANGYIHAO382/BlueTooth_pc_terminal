PC BLE Gateway (Windows portable)
=================================

No Python install required. Copy this whole folder to another PC.

1) Start
   Double-click PCBleGateway.exe

2) First use
   - Turn on Windows Bluetooth
   - Scan devices, right-click to set type (BP / Band), then connect
   - Fill TV LAN IP in the bottom bar and enable TV push

3) Config files (same folder as the exe; editable with Notepad)
   gateway.json  - TV IP, ports, protocol stage
   devices.json  - saved BLE device profiles

4) Requirements
   - Windows 10 / 11 (64-bit)
   - BLE-capable Bluetooth adapter

5) Tips
   - SmartScreen may warn on first run: choose "Run anyway"
   - If scan finds nothing: make sure phone is not connected to the device
   - If TV link fails: PC and TV must be on the same LAN; check IP/ports

See GitHub Releases notes for the version of this package.
