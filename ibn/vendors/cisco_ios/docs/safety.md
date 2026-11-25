# What must never be broken (the program manages the devices through it)

## Requests that must be refused
- Never: reload, erase/write erase, delete the admin user, change the enable password, turn off SSH,
  "transport input none" on the VTY lines. Plans asking for these must be refused with an explanation.

Example: restart R2
    Refuse: reloading a device is blocked, because the network and the program would lose it. Restart it by hand from EVE-NG.

Example: delete the admin user on all routers
    Refuse: the program logs in with the admin user; removing it would lock the program out of the devices.

Example: erase the configuration of SW2
    Refuse: erasing a device's configuration is blocked; it would cut the device and the program's access.

## Passwords and remote access
- Changing the enable password or turning off SSH locks the program out of the device: refuse.

Example: change the enable password of R5
    Refuse: changing the enable password is blocked; the program needs it to manage the device. Do it by hand on the console.

Example: turn off ssh on R6
    Refuse: the program manages R6 over SSH; turning it off would lock the program out.

## Unclear requests
- If the request doesn't say what should change, don't guess: explain what is missing.

Example: make the network better
    Refuse: The request is unclear. What should change? For example: add routes between two networks, block one network from another, or create a VLAN.

## Don't cut the program's access
- Don't shut down or re-address the interface that holds the device's management IP.
- Don't block SSH from the management network in an access list.
- Changing settings on a link (OSPF timers, authentication, trunk native VLAN): do BOTH ends in the same plan.
- Every config step needs a rollback that really undoes it.
