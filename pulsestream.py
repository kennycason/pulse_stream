# h10_hrm.py
import asyncio
import threading
import queue
import time
import os
from datetime import datetime
from bleak import BleakScanner, BleakClient
from heartbeat_visualizer import HeartbeatVisualizer

# Standard BLE UUIDs
HRS_UUID = "0000180d-0000-1000-8000-00805f9b34fb"      # Heart Rate Service
HRM_CHAR = "00002a37-0000-1000-8000-00805f9b34fb"      # Heart Rate Measurement characteristic

# Polar PMD (Proprietary Measurement Data) UUIDs for ECG
PMD_SERVICE = "FB005C80-02E7-F387-1CAD-8ACD2D8DF0C8"    # PMD Service
PMD_CONTROL = "FB005C81-02E7-F387-1CAD-8ACD2D8DF0C8"    # PMD Control Point
PMD_DATA = "FB005C82-02E7-F387-1CAD-8ACD2D8DF0C8"       # PMD Data

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

# Global data queues for passing data from BLE thread to main thread
hr_data_queue = queue.Queue()
ecg_data_queue = queue.Queue()

# CSV logging setup
csv_filename = None
def setup_csv_logging():
    """Create a new CSV file with timestamp for this session"""
    global csv_filename
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Replace colons with dashes for filename compatibility
    safe_timestamp = timestamp.replace(":", "-")
    csv_filename = f"hr_{safe_timestamp}.csv"
    
    # Create directory if it doesn't exist
    os.makedirs("data", exist_ok=True)
    filepath = os.path.join("data", csv_filename)
    
    # Write CSV header
    with open(filepath, "w") as f:
        f.write("timestamp,unix_time,hr_bpm,rr_intervals_ms,ecg_samples\n")
    
    print(f"📊 Logging heart rate data to: data/{csv_filename}")
    return filepath

def log_hr_data(hr, rr_list, ecg_samples=None):
    """Log heart rate and ECG data to CSV"""
    if csv_filename:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        unix_time = time.time()
        rr_str = ";".join(f"{r:.1f}" for r in rr_list) if rr_list else ""
        ecg_str = ";".join(f"{s:.0f}" for s in ecg_samples) if ecg_samples else ""
        
        filepath = os.path.join("data", csv_filename)
        with open(filepath, "a") as f:
            f.write(f"{timestamp},{unix_time:.3f},{hr},{rr_str},{ecg_str}\n")

def parse_ecg_data(data: bytes):
    """Parse Polar ECG data from PMD service"""
    if len(data) < 10:
        return []
    
    # Polar ECG format: first byte is frame type, skip some header bytes
    # ECG samples are typically 3 bytes each, signed 24-bit values
    samples = []
    
    # Skip header (varies, but typically ~10 bytes)
    start_idx = 10
    
    # Parse 3-byte signed ECG samples
    for i in range(start_idx, len(data) - 2, 3):
        if i + 2 < len(data):
            # Convert 3-byte signed value to int (little endian)
            sample = int.from_bytes(data[i:i+3], 'little', signed=True)
            samples.append(sample)
    
    return samples

def ecg_notification_handler(_, data: bytearray):
    """Handle ECG data notifications"""
    try:
        samples = parse_ecg_data(data)
        if samples:
            # Put ECG data in queue for main thread
            try:
                ecg_data_queue.put_nowait(samples)
            except queue.Full:
                pass  # Skip if queue is full
    except Exception as e:
        print(f"ECG parsing error: {e}")

def notification_handler(_, data: bytearray):
    hr, rr_list, flags = parse_hrm(data)
    rr_str = ", ".join(f"{x:.1f} ms" for x in rr_list) if rr_list else "—"
    contact = "yes" if flags["sensor_contact_detected"] else "no/unknown"
    print(f"HR: {hr:3d} bpm | contact: {contact} | RR: {rr_str}")
    
    # Log to CSV
    log_hr_data(hr, rr_list)
    
    # Put HR data in queue for main thread to consume
    try:
        hr_data_queue.put_nowait((hr, rr_list, flags))
    except queue.Full:
        pass  # Skip if queue is full

async def start_ecg_stream(client):
    """Start ECG data streaming via PMD service"""
    try:
        # Check if PMD service is available
        if PMD_SERVICE not in [s.uuid for s in client.services]:
            print("⚠️  PMD service not found - ECG not available")
            return False
        
        print("📡 Starting ECG stream...")
        
        # Subscribe to ECG data notifications
        await client.start_notify(PMD_DATA, ecg_notification_handler)
        
        # Send command to start ECG streaming (130 Hz)
        # Command format: [CMD, TYPE, SAMPLE_RATE, RESOLUTION, RANGE]
        start_cmd = bytearray([
            0x02,  # Start measurement command
            0x00,  # ECG type
            0x82, 0x00,  # 130 Hz sample rate (little endian)
            0x01, 0x01, 0x0E, 0x00  # Settings
        ])
        
        await client.write_gatt_char(PMD_CONTROL, start_cmd)
        print("✅ ECG streaming started (130 Hz)")
        return True
        
    except Exception as e:
        print(f"❌ ECG setup failed: {e}")
        return False

async def run_bluetooth():
    """Run the Bluetooth connection in background"""
    try:
        dev = await find_device()
        async with BleakClient(dev) as client:
            # Verify heart rate service exists
            svcs = client.services
            assert HRS_UUID in [s.uuid for s in svcs], "Heart Rate Service not found."

            print("Subscribing to Heart Rate notifications…")
            await client.start_notify(HRM_CHAR, notification_handler)

            # Try to start ECG streaming
            ecg_started = await start_ecg_stream(client)
            
            print("Bluetooth connected. Streaming heart rate data" + (" + ECG" if ecg_started else "") + "...")
            
            # Keep running until the main thread stops
            try:
                while True:
                    await asyncio.sleep(1)
            finally:
                await client.stop_notify(HRM_CHAR)
                if ecg_started:
                    try:
                        # Stop ECG streaming
                        stop_cmd = bytearray([0x03, 0x00])  # Stop command for ECG
                        await client.write_gatt_char(PMD_CONTROL, stop_cmd)
                        await client.stop_notify(PMD_DATA)
                        print("🛑 ECG streaming stopped")
                    except:
                        pass
                        
    except Exception as e:
        print(f"Bluetooth error: {e}")
        # Put error marker in queue
        hr_data_queue.put_nowait((0, [], {"error": str(e)}))

def main():
    """Main function - runs pygame on main thread, Bluetooth in background"""
    print("Starting heart rate monitor with visualization...")
    
    # Setup CSV logging for this session
    setup_csv_logging()
    
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
        
        # Process any ECG data from the queue
        try:
            while True:
                ecg_samples = ecg_data_queue.get_nowait()
                visualizer.update_ecg_data(ecg_samples)
        except queue.Empty:
            pass  # No new ECG data
        
        # Update and render
        visualizer.update()
        visualizer.render()
    
    print("Visualizer closed")

if __name__ == "__main__":
    main()