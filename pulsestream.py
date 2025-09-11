# h10_hrm.py
import asyncio
import threading
import queue
from bleak import BleakScanner, BleakClient
from heartbeat_visualizer import HeartbeatVisualizer

# Standard BLE UUIDs
HRS_UUID = "0000180d-0000-1000-8000-00805f9b34fb"      # Heart Rate Service
HRM_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"      # Heart Rate Measurement characteristic

def parse_hrm(data: bytes):
    """
    Parse BLE Heart Rate Measurement packet (Bluetooth SIG spec).
    Returns (hr_bpm, rr_intervals_ms_list, flags_dict).
    """
    i = 0
    flags = data[i]; i += 1

    hr_16bit = bool(flags & 0x01)
    sensor_contact_supported = bool(flags & 0x04)
    sensor_contact_detected  = bool(flags & 0x02)
    energy_expended_present  = bool(flags & 0x08)
    rr_present               = bool(flags & 0x10)

    if hr_16bit:
        hr = int.from_bytes(data[i:i+2], "little"); i += 2
    else:
        hr = data[i]; i += 1

    if energy_expended_present:
        i += 2  # skip energy expended

    rr_list = []
    if rr_present:
        while i + 1 < len(data):
            rr = int.from_bytes(data[i:i+2], "little"); i += 2
            # RR is in units of 1/1024 s; convert to ms
            rr_ms = rr * 1000 / 1024
            rr_list.append(rr_ms)

    return hr, rr_list, {
        "sensor_contact_supported": sensor_contact_supported,
        "sensor_contact_detected": sensor_contact_detected,
        "hr_16bit": hr_16bit
    }

async def find_device():
    print("Scanning for Polar H10…")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        name = (d.name or "").lower()
        if "polar" in name or "h10" in name:
            print(f"Found: {d.name} [{d.address}]")
            return d
    raise RuntimeError("Polar H10 not found. Make sure it's on your chest and not fully connected elsewhere.")

# Global data queue for passing HR data from BLE thread to main thread
hr_data_queue = queue.Queue()

def notification_handler(_, data: bytearray):
    hr, rr_list, flags = parse_hrm(data)
    rr_str = ", ".join(f"{x:.1f} ms" for x in rr_list) if rr_list else "—"
    contact = "yes" if flags["sensor_contact_detected"] else "no/unknown"
    print(f"HR: {hr:3d} bpm | contact: {contact} | RR: {rr_str}")
    
    # Put HR data in queue for main thread to consume
    try:
        hr_data_queue.put_nowait((hr, rr_list, flags))
    except queue.Full:
        pass  # Skip if queue is full

async def run_bluetooth():
    """Run the Bluetooth connection in background"""
    try:
        dev = await find_device()
        async with BleakClient(dev) as client:
            # Optional: verify the service exists
            svcs = client.services
            assert HRS_UUID in [s.uuid for s in svcs], "Heart Rate Service not found."

            print("Subscribing to Heart Rate notifications…")
            await client.start_notify(HRM_CHAR, notification_handler)

            print("Bluetooth connected. Streaming heart rate data...")
            # Keep running until the main thread stops
            try:
                while True:
                    await asyncio.sleep(1)
            finally:
                await client.stop_notify(HRM_CHAR)
    except Exception as e:
        print(f"Bluetooth error: {e}")
        # Put error marker in queue
        hr_data_queue.put_nowait((0, [], {"error": str(e)}))

def main():
    """Main function - runs pygame on main thread, Bluetooth in background"""
    print("Starting heart rate monitor with visualization...")
    
    # Start Bluetooth in background thread
    def run_async_bluetooth():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_bluetooth())
    
    bt_thread = threading.Thread(target=run_async_bluetooth, daemon=True)
    bt_thread.start()
    
    # Run pygame visualizer on main thread (required for macOS)
    visualizer = HeartbeatVisualizer(hr_min=20, hr_max=180)
    print("Pygame visualizer started on main thread")
    print("Press ESC or close window to exit")
    
    running = True
    while running:
        # Handle pygame events
        running = visualizer.handle_events()
        
        # Process any heart rate data from the queue
        try:
            while True:
                hr, rr_list, flags = hr_data_queue.get_nowait()
                visualizer.update_heart_rate(hr, rr_list)
        except queue.Empty:
            pass  # No new data
        
        # Update and render
        visualizer.update()
        visualizer.render()
    
    print("Visualizer closed")

if __name__ == "__main__":
    main()