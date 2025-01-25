# linksys_mon

## Setup

Create/edit `.env` with the following (filled out):

```sh
LINKSYS_USERNAME=
LINKSYS_PASSWORD=
```

## Usage

```sh
> uv run --script linksys_mon.py --help
usage: linksys_mon.py [-h] [--online] [--offline] [--friendly FRIENDLY] [--mac MAC]

Display device connection status from Linksys router

options:
  -h, --help           Show this help message and exit
  --online             Show only online devices
  --offline             Show only offline devices
  --friendly FRIENDLY  Filter devices by friendly name
  --mac MAC            Filter devices by MAC address
```