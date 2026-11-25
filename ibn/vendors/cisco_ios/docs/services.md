# Device services: time, logs, banner (Cisco IOS)

## Time (NTP)
- ntp server <ip>. Undo: no ntp server <ip>.

Example: make R5 and R6 take their time from the ntp server 10.250.0.1
    Plan: NTP server 10.250.0.1 on R5 and R6
    R5 config:
        ntp server 10.250.0.1
    R5 undo:
        no ntp server 10.250.0.1
    R6 config:
        ntp server 10.250.0.1
    R6 undo:
        no ntp server 10.250.0.1

## Logs (syslog)
- logging host <ip> + logging trap <level> (informational, warnings...). Undo: no logging host <ip> + no logging trap.

Example: send the logs of R7 to the syslog server 10.250.0.5
    Plan: Syslog to 10.250.0.5 (level informational) on R7
    R7 config:
        logging host 10.250.0.5
        logging trap informational
    R7 undo:
        no logging host 10.250.0.5
        no logging trap

## Login banner
- banner motd #<text>#. Undo: no banner motd.

Example: put a login warning banner on SW2
    Plan: Message-of-the-day banner on SW2
    SW2 config:
        banner motd #Authorized access only#
    SW2 undo:
        no banner motd
