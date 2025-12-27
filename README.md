# OpenVPN-AS Patch Utility

This script patches OpenVPN Access Server to allow 200 concurrent VPN connections by modifying the `pyovpn-*.egg` file.

**Note**: Modifying OpenVPN-AS may violate its license agreement.

**Tested on:**
- OpenVPN Access Server 2.14.3 (Docker)
- OpenVPN Access Server 3.0.2 (Docker)
- OpenVPN Access Server 3.0.2 (Service)

## How to Use

### With Docker

1. **Copy the script** to the OpenVPN-AS container:

   ```sh
   docker cp ovpn.py openvpn-as:/tmp/ovpn.py
   ```
2. **Run**:

   ```sh
   docker exec -it openvpn-as python3 /tmp/ovpn.py
   ```

   **On OpenVPN-AS 3+ run this:**
      ```sh
   docker exec -it openvpn-as apt-get update
   docker exec -it openvpn-as apt-get install -y python3-pip
   docker exec -it openvpn-as pip3 install colorama --break-system-packages
   docker exec -it openvpn-as python3 /tmp/ovpn.py
   ```

   Select `1` to patch or `q` to quit.
4. **Restart OpenVPN-AS**:

   ```sh
   docker exec openvpn-as systemctl restart openvpnas
   ```

   Or:

   ```sh
   docker restart openvpn-as
   ```

### Without Docker

1. **Save the script** as `ovpn.py` on the system running OpenVPN-AS.
2. **Run** (as root):

   ```sh
   sudo python3 ovpn.py
   ```

   **On OpenVPN-AS 3+ run this:**
      ```sh
   sudo apt update
   sudo apt-get install -y python3-pip
   sudo pip3 install colorama --break-system-packages
   sudo python3 ./ovpn.py
   ```

   Select `1` to patch or `q` to quit.
4. **Restart OpenVPN-AS**:

   ```sh
   sudo systemctl restart openvpnas
   ```

## Docker Compose Example

```yaml
---
services:
  openvpn-as:
    image: openvpn/openvpn-as
    container_name: openvpn-as
    restart: unless-stopped
    ports:
      - "1194:1194/udp"
      - "943:943"
      - "443:443"
    volumes:
      - ./openvpn-data:/openvpn
    cap_add:
      - MKNOD
      - NET_ADMIN
    devices:
      - /dev/net/tun
```

Start the container:

```sh
docker-compose up -d
```
