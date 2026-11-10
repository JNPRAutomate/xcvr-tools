# xcvr-tools

Junos op scripts for inspecting and configuring coherent 400G ZR/ZR+ transceivers through CMIS register access.

| Script | Purpose |
|---|---|
| `cdc.py` | Changes the maximum Chromatic Dispersion Compensation (CDC) of a single interface. |
| `xcvr_tools.py` | Multi-purpose tool: check/change CDC, Data Path control, Rx threshold, soft OIR, and more. Supports a single interface or `all`. |

Both scripts work on Junos releases with or without the `page` knob on the `test picd optics read/write` PFE commands.

## Supported Modules

| Vendor | JPN | CDC (`cdc.py`) | CDC (`xcvr_tools.py`) | Rx threshold |
|---|---|---|---|---|
| JUNIPER-1T | 740-131168, 740-131169 | Yes | Yes | Yes |
| JUNIPER-2E | 740-157138 | Yes | Yes | Yes |
| JUNIPER-1A | 740-151745 | Yes | Yes | Yes (incl. `DSPLOL`) |
| JUNIPER-1A | 740-179331 | No | Yes | No |

Unsupported modules are reported as `UNSUPPORTED` (`xcvr_tools.py`) or rejected with `Module not supported` (`cdc.py`).

## Prerequisites

NETCONF over SSH must be enabled on the router:

```
set system services netconf ssh
```

---

## cdc.py

### 1. Upload the script

Copy `cdc.py` to `/var/db/scripts/op/` on the router.

### 2. Apply the configuration

```
set system services netconf ssh
set system scripts op file cdc.py arguments interface description "Desired interface to configure"
set system scripts op file cdc.py arguments max_cdc description "Desired max CDC setting in ps/nm"
set system scripts language python3
set system scripts synchronize
```

### 3. Run the script

```
root@router> op cdc.py ?
Possible completions:
  <[Enter]>            Execute this command
  <name>               Argument name
  detail               Display detailed output
  interface            Desired interface to configure
  invoke-debugger      Invoke script in debugger mode
  max_cdc              Desired max CDC setting in ps/nm
  |                    Pipe through a command
```

Example:

```
root@router> op cdc.py interface et-0/0/2 max_cdc 9000
```

The script waits for the Data Path to be activated, deactivates it, writes the new CDC value, verifies it, reactivates the Data Path and waits (up to 300 seconds) for the link to come up. If the module enters a fault state, it offers to perform a soft OIR and retry.

---

## xcvr_tools.py

### 1. Upload the script

Copy `xcvr_tools.py` to `/var/db/scripts/op/` on the router.

### 2. Apply the configuration

```
set system services netconf ssh
set system scripts op file xcvr_tools.py arguments command description "checkCDC,changeCDC,checkRxSquelch,checkDP,softOIR,dpReset,dpDeinit,dpInit,xcvrPeriodicStop,xcvrPeriodicStart,changeRXThreshold"
set system scripts op file xcvr_tools.py arguments interface description "Interface Name or all"
set system scripts op file xcvr_tools.py arguments max_cdc description "Target CDC in ps/nm"
set system scripts op file xcvr_tools.py arguments rxLOSthreshold description "Rx LOS threshold in dBm"
set system scripts language python3
set system scripts synchronize
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `interface` | Yes | Interface name (e.g. `et-0/0/0`) or `all` for every transceiver in the chassis. |
| `command` | Yes | Operation to perform (see below). |
| `max_cdc` | `changeCDC` only | Target max CDC in ps/nm. |
| `rxLOSthreshold` | `changeRXThreshold` only | Rx LOS alarm threshold in dBm, or `DSPLOL`. |

With `interface all`, the command runs in parallel on every transceiver, except `changeCDC`, which does not support parallel execution.

### Commands

| Command | Description | `all` supported |
|---|---|---|
| `checkCDC` | Reads the current max CDC setting. | Yes |
| `changeCDC` | Changes the max CDC setting (same flow as `cdc.py`). | No |
| `checkDP` | Reads the Data Path state (page `0x11`, byte `0x80`). | Yes |
| `checkRxSquelch` | Reads the Rx auto squelch disable bitmask (page `0x10`, byte `139`, `AutoSquelchDisableRx`). One bit per lane: `0` = squelch enabled, `1` = squelch disabled. | Yes |
| `dpDeinit` | Deactivates the Data Path. | Yes |
| `dpInit` | Activates the Data Path. | Yes |
| `dpReset` | Deactivates then reactivates the Data Path. | Yes |
| `softOIR` | Performs a software removal and reinsertion of the module. | Yes |
| `xcvrPeriodicStop` | Stops the PFE periodic polling of the transceiver. | Yes |
| `xcvrPeriodicStart` | Starts the PFE periodic polling of the transceiver. | Yes |
| `changeRXThreshold` | Sets the Rx LOS alarm threshold in dBm (warning is set to alarm + 1). With `DSPLOL`, uses DSP Loss of Lock instead of a fixed Rx power threshold to bring the link down (JUNIPER-1A only, see [DSPLOL mode](#examples)). | Yes |

The output of each command is one line per interface:

```
<interface> - <JPN> - <description> - <result>
```

### Examples

**Check CDC on all interfaces**

```
root@router> op xcvr_tools.py interface all command checkCDC
et-0/0/0    - 740-157138   - QSFP56-DD-400G-ZR-M            -   19000 ps/nm
et-0/0/2    - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/0/8    - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/0/10   - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/1/0    - 740-157138   - QSFP56-DD-400G-ZR-M            -   19000 ps/nm
et-0/1/2    - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/1/8    - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/1/10   - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
et-0/2/10   - 740-085351   - QSFP56-DD-400GBASE-DR4         -    UNSUPPORTED
```

**Check CDC on one interface**

```
root@router> op xcvr_tools.py interface et-0/0/0 command checkCDC
et-0/0/0    - 740-157138   - QSFP56-DD-400G-ZR-M            -   20000 ps/nm
```

**Change CDC** (one interface at a time only)

```
root@router> op xcvr_tools.py interface et-0/0/0 command changeCDC max_cdc 18000
DP Activated (4)! Deactivating DP.
Reading Current Max CDC Setting
Current Max CDC Setting is 20000 ps/nm.
Changing CDC Setting to 18000 ps/nm.
Done! Verifying if accepted by the module.
Current Max CDC Setting is now 18000 ps/nm.
Waiting for Link Up.  Time elapsed: 0 seconds.
Waiting for Link Up.  Time elapsed: 5 seconds.
... output truncated ...
Link Up!
```

**Check Data Path state**

```
root@router> op xcvr_tools.py interface all command checkDP
```

The result is the raw register value, one nibble per lane, using CMIS DP states (e.g. `0x44` = DPActivated, `0x11` = DPDeactivated).

**Reset the Data Path**

```
root@router> op xcvr_tools.py interface et-0/0/0 command dpReset
```

**Soft OIR**

```
root@router> op xcvr_tools.py interface et-0/0/0 command softOIR
```

**Change Rx LOS threshold**

```
root@router> op xcvr_tools.py interface et-0/0/0 command changeRXThreshold rxLOSthreshold -20
root@router> op xcvr_tools.py interface et-0/0/0 command changeRXThreshold rxLOSthreshold DSPLOL
```

**DSPLOL mode** (JUNIPER-1A only)

By default, the optics declares Rx LOS and brings the link down when the Rx power falls below a fixed threshold. With `DSPLOL`, the fixed Rx power threshold is no longer used: the link stays up as long as the DSP can keep the signal locked, and only goes down on DSP Loss of Lock (LOL).

> **Warning:** Use at your own risk. Since the link is kept up at Rx power levels below the normal threshold, uncorrected FEC errors (packet loss) can occur before the link goes down. This mode is intended only for link and performance testing, or for links that have been properly designed and evaluated according to your SOP.

## Notes

- Changing CDC or the Data Path state is traffic-affecting.
- `changeCDC` does not support parallel execution: it only accepts a single interface, not `interface all`. To change multiple interfaces, run the command once per interface.
- For JUNIPER-2E modules, CDC values above 65535 ps/nm are stored as value x multiplier. If the requested value is prime, 1 is added to it.
