# Teensy Tracker Chat

*** If you are able to test v1.1.6(with GPS and beaconing) Beta (simple chat) and the Alpha mapping v0960 (GPS and Grid mapping) and report any issues or bugs please do so. Thank you M0OLI

A desktop chat application (PyQt5 + pyserial) for person-to-person communication over ham bands using a Teensy Tracker TNC device.

## Features

- **Serial connection**  
  - Select COM port and baud rate.  
  - Reliable connect/disconnect with live status bar.  

- **Chat interface**  
  - Black background, lime green text (retro terminal style).  
  - **Send** format: `<Target> DE <MyCALL> <message>`.  
  - **Receive** format: `<TO> DE <FROM> <message>` (CQ handled).  
  - Sent messages = lime, received messages = orange.  
  - Console/device output (e.g. RPR/AX.25 prompts) = turquoise, or fully hidden with a checkbox.  
  - Echo suppression prevents your sent lines reappearing as received.

- **Callsign handling**  
  - “To” and “From (MyCALL)” fields in uppercase, lime on black.  
  - Larger font, auto-uppercase input.  
  - “Load Callsign” button queries the device and fills in MyCALL.  

- **KISS mode controls**  
  - **Enter KISS Mode (@K)** button.  
  - **KISS Permanent (@KP1)** toggle (OFF sends `192,255,192,13` to exit).  
  - Reminder that chat requires KISS OFF.  

- **Safety**  
  - Only text typed into the Send box is transmitted.  
  - Console/device output is never transmitted.  
  - Status bar shows TX count for confirmation.  

## Requirements

- Python 3.8+ (tested with 3.13)
- [PyQt5](https://pypi.org/project/PyQt5/)
- [pyserial](https://pypi.org/project/pyserial/)

Install dependencies:

```bash
pip install pyqt5 pyserial
