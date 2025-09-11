# Teensy Tracker Chat

The excellent Teensy RPR TNC can either be built (perhaps a group buy) via files from http://robust-packet.st or Robert, DM4RW may have a few left built. The Hardware was developed by Robert DM4RW and the Firmware for the device is from Pactor SCS staff inventor of robust packet Hans-Peter, DL6MAA. This chat software is to utilize the messaging capacity and ability of the device and mode. Teensy Tracker Chat was developed with ideas from Oliver M0OLI with the help of his A.I friend! 

**** WARNING **** DISCONNECT DATA CABLE TO RADIO WHEN CHANGING KISS CONDITION AS IT WILL PTT. There is no issue after KISS condition is off, chat is available.

*** If you are able to test v1.1.9(with GPS and beaconing) Beta, Requires VT323-regular.ttf file in same folder ,Thank you M0OLI
** IMPORTANT: If using the Artificial Intelligence version starting 1.2.0 (Edit with notepad and ctrl+F enter System to search for the system field and edit with your callsign as the responsible callsign for the remote station, likely this is set with mine M0OLI so change that out)

WINDOWS EXE Files for versions v1.1.9 and v1.2.0 A.I are available https://drive.google.com/drive/folders/1YWG1WdnSl9yJcV1gUq-lT6Ze3UAo1xDj?usp=drive_link

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
