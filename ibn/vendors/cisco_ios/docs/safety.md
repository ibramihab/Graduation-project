# What must never be broken (the program manages the devices through it)
- Never: reload, erase/write erase, delete the admin user, change the enable password, turn off SSH,
  "transport input none" on the VTY lines. Plans asking for these must be refused with an explanation.
- Don't shut down or re-address the interface that holds the device's management IP.
- Don't block SSH from the management network in an access list.
- Changing settings on a link (OSPF timers, authentication, trunk native VLAN): do BOTH ends in the same plan.
- Every config step needs a rollback that really undoes it.
