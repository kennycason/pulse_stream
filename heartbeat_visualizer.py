import pygame
import math
import time
from collections import deque
from typing import Optional

class HeartbeatVisualizer:
    def __init__(self, width=1200, height=400, hr_min=20, hr_max=180):
        pygame.init()
        
        # Display settings
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height), pygame.RESIZABLE)
        pygame.display.set_caption("Heart Rate Monitor")
        
        # Heart rate configuration
        self.hr_min_base = hr_min  # Base minimum (20)
        self.hr_max_base = hr_max  # Base maximum (180)
        self.hr_min = hr_min  # Current dynamic minimum
        self.hr_max = hr_max  # Current dynamic maximum
        self.hr_safe_min = 60  # Green zone start
        self.hr_safe_max = 80  # Green zone end
        
        # Dynamic range settings
        self.dynamic_range_padding = 20  # ±20 BPM around current HR
        self.range_smoothing = 0.1  # How quickly ranges adjust (0.1 = slow, 1.0 = instant)
        
        # Visual settings
        self.bg_color = (5, 5, 15)  # Dark blue/black
        self.grid_color = (0, 40, 0)  # Dark green
        self.line_color = (0, 255, 0)  # Bright green
        self.glow_color = (0, 255, 100)
        
        # Data storage - much faster movement, store fewer points relative to width
        self.hr_history = deque(maxlen=width // 2)  # Store fewer points for faster movement
        self.time_history = deque(maxlen=width // 2)
        self.current_hr = 0
        self.last_beat_time = 0
        
        # ECG data storage
        self.ecg_history = deque(maxlen=width * 4)  # Store more ECG points for smooth waveform
        self.ecg_enabled = False
        
        # Animation
        self.glow_intensity = 0
        self.pulse_phase = 0
        self.clock = pygame.time.Clock()
        
        # Fonts
        self.font_large = pygame.font.Font(None, 48)
        self.font_medium = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 24)
        
    def update_heart_rate(self, hr: int, rr_intervals: list = None):
        """Update the heart rate data"""
        current_time = time.time()
        
        self.current_hr = hr
        self.hr_history.append(hr)
        self.time_history.append(current_time)
        
        # Update glow intensity based on HR
        if hr > 0:
            # Normalize HR to 0-1 range
            hr_normalized = (hr - self.hr_min) / (self.hr_max - self.hr_min)
            hr_normalized = max(0, min(1, hr_normalized))  # Clamp to 0-1
            
            # More intense glow for higher HR
            self.glow_intensity = hr_normalized * 0.8 + 0.2
            
        # Update dynamic range based on current HR
        if hr > 0:
            self.update_dynamic_range(hr)
            
        # Trigger pulse animation
        if rr_intervals and len(rr_intervals) > 0:
            self.last_beat_time = current_time
    
    def update_dynamic_range(self, current_hr: int):
        """Update dynamic HR range based on current heart rate"""
        # Calculate target range (current HR ± padding)
        target_min = max(self.hr_min_base, current_hr - self.dynamic_range_padding)
        target_max = min(self.hr_max_base, current_hr + self.dynamic_range_padding)
        
        # Smooth transition to new range to avoid jarring jumps
        self.hr_min += (target_min - self.hr_min) * self.range_smoothing
        self.hr_max += (target_max - self.hr_max) * self.range_smoothing
        
        # Ensure minimum range span of 40 BPM for visual clarity
        if self.hr_max - self.hr_min < 40:
            center = (self.hr_min + self.hr_max) / 2
            self.hr_min = center - 20
            self.hr_max = center + 20
            
            # Clamp to base limits
            self.hr_min = max(self.hr_min_base, self.hr_min)
            self.hr_max = min(self.hr_max_base, self.hr_max)
    
    def update_ecg_data(self, ecg_samples: list):
        """Update ECG data"""
        if ecg_samples:
            self.ecg_enabled = True
            self.ecg_history.extend(ecg_samples)
    
    def get_hr_color(self, hr: int) -> tuple:
        """Get color based on heart rate with smooth gradient: purple → blue → green → yellow → orange → red → pink"""
        if hr == 0:
            return (100, 100, 100)  # Gray for no signal
        
        # Clamp HR to our range
        hr = max(self.hr_min, min(self.hr_max, hr))
        
        # Normalize HR to 0-1 range
        normalized = (hr - self.hr_min) / (self.hr_max - self.hr_min)
        
        # Define color stops: [position, (r, g, b)]
        # Extrapolated colors for 20-180 BPM range
        color_stops = [
            (0.0,   (64, 0, 64)),     # Dark Purple (20 BPM)
            (0.125, (96, 0, 96)),     # Medium Purple (40 BPM)
            (0.1875, (128, 0, 128)),  # Purple (50 BPM)
            (0.28,  (0, 0, 255)),     # Blue (65 BPM) 
            (0.375, (0, 255, 0)),     # Green (80 BPM)
            (0.53,  (255, 255, 0)),   # Yellow (105 BPM)
            (0.69,  (255, 165, 0)),   # Orange (130 BPM)
            (0.84,  (255, 0, 0)),     # Red (155 BPM)
            (1.0,   (255, 192, 203))  # Pink (180 BPM)
        ]
        
        # Find the two color stops to interpolate between
        for i in range(len(color_stops) - 1):
            pos1, color1 = color_stops[i]
            pos2, color2 = color_stops[i + 1]
            
            if pos1 <= normalized <= pos2:
                # Interpolate between color1 and color2
                t = (normalized - pos1) / (pos2 - pos1) if pos2 != pos1 else 0
                
                r = int(color1[0] + (color2[0] - color1[0]) * t)
                g = int(color1[1] + (color2[1] - color1[1]) * t)
                b = int(color1[2] + (color2[2] - color1[2]) * t)
                
                return (r, g, b)
        
        # Fallback (shouldn't reach here)
        return (255, 255, 255)
    
    def draw_grid(self):
        """Draw background grid like a hospital monitor"""
        # Adaptive margins and spacing based on window height
        margin = max(20, self.height // 10)  # Responsive margin
        
        # Calculate optimal label spacing based on window height
        available_height = self.height - 2 * margin
        hr_range = self.hr_max - self.hr_min
        
        # Determine label interval based on available space (readable spacing)
        if available_height < 150:  # Very small window
            label_interval = 20  # Every 20 BPM
            grid_interval = 10   # Grid every 10 BPM
            font_to_use = pygame.font.Font(None, 32)  # Readable font
        elif available_height < 250:  # Small window
            label_interval = 10  # Every 10 BPM
            grid_interval = 10   # Grid every 10 BPM
            font_to_use = pygame.font.Font(None, 36)  # Bigger font
        elif available_height < 400:  # Medium window
            label_interval = 10  # Every 10 BPM
            grid_interval = 5    # Grid every 5 BPM
            font_to_use = pygame.font.Font(None, 40)  # Large font
        else:  # Large window
            label_interval = 10  # Every 10 BPM
            grid_interval = 5    # Grid every 5 BPM
            font_to_use = pygame.font.Font(None, 48)  # Extra large font
        
        # Calculate minimum pixels between labels (generous spacing)
        min_label_spacing = 24  # Doubled from 12 to 24
        max_labels = available_height // min_label_spacing
        if hr_range / label_interval > max_labels:
            # Too many labels, increase interval
            label_interval = max(5, int(hr_range / max_labels / 5) * 5)  # Increment by 5s instead of 10s
        
        # Horizontal lines (HR levels) - dynamic range
        grid_start = int(self.hr_min // grid_interval) * grid_interval
        grid_end = int(self.hr_max // grid_interval + 1) * grid_interval
        
        for hr in range(grid_start, grid_end + 1, grid_interval):
            # Calculate y position using full range
            y = self.height - margin - ((hr - self.hr_min) / (self.hr_max - self.hr_min)) * available_height
            
            if margin <= y <= self.height - margin:
                alpha = 120 if hr % (label_interval * 2) == 0 else 60
                # Create a surface for alpha blending
                line_surf = pygame.Surface((self.width, 1))
                line_surf.set_alpha(alpha)
                line_surf.fill(self.grid_color)
                self.screen.blit(line_surf, (0, int(y)))
                
                # Label grid lines with adaptive spacing
                if hr % label_interval == 0:
                    label_color = self.get_hr_color(hr)
                    label = font_to_use.render(f"{hr}", True, label_color)
                    # Adjust label position to not overlap
                    label_y = max(margin // 2, min(int(y) - label.get_height() // 2, self.height - margin // 2 - label.get_height()))
                    self.screen.blit(label, (10, label_y))
        
        # Vertical time lines (adaptive to width)
        vertical_spacing = max(20, self.width // 40)  # Responsive vertical line spacing
        for i in range(0, self.width, vertical_spacing):
            alpha = 80 if i % (vertical_spacing * 2) == 0 else 40
            line_surf = pygame.Surface((1, self.height))
            line_surf.set_alpha(alpha)
            line_surf.fill(self.grid_color)
            self.screen.blit(line_surf, (i, 0))
    
    def draw_heartbeat_line(self):
        """Draw the heartbeat waveform with rainbow coloring"""
        if len(self.hr_history) < 2:
            return
            
        current_time = time.time()
        margin = max(20, self.height // 10)  # Use same adaptive margin as grid
        available_height = self.height - 2 * margin
        
        # Create segments with individual colors
        segments = []
        for i, (hr, timestamp) in enumerate(zip(self.hr_history, self.time_history)):
            # Much faster movement: map fewer data points across full screen width
            x = self.width - (len(self.hr_history) - i) * 2
            
            # Use full range positioning with adaptive margins
            base_y = self.height - margin - ((hr - self.hr_min) / (self.hr_max - self.hr_min)) * available_height
            
            # Add heartbeat pulse effect
            pulse_amplitude = 0
            time_since_beat = current_time - self.last_beat_time
            if time_since_beat < 0.3:  # Pulse lasts 300ms
                pulse_phase = (time_since_beat / 0.3) * math.pi
                pulse_amplitude = math.sin(pulse_phase) * 15 * self.glow_intensity
            
            y = base_y + pulse_amplitude
            
            if 0 <= x < self.width and margin <= y <= self.height - margin:
                segments.append((x, y, hr))
        
        # Draw segments with individual colors and enhanced thickness
        if len(segments) > 1:
            for thickness in range(8, 0, -1):  # Thicker lines for better effect
                alpha = int(200 / thickness)
                
                # Create surface for this thickness layer
                line_surf = pygame.Surface((self.width, self.height))
                line_surf.set_alpha(alpha)
                line_surf.fill((0, 0, 0))
                line_surf.set_colorkey((0, 0, 0))
                
                # Draw each segment with its own color
                for i in range(len(segments) - 1):
                    x1, y1, hr1 = segments[i]
                    x2, y2, hr2 = segments[i + 1]
                    
                    # Use the average HR for the segment color
                    avg_hr = (hr1 + hr2) / 2
                    color = self.get_hr_color(int(avg_hr))
                    
                    if abs(x2 - x1) > 0 or abs(y2 - y1) > 0:
                        pygame.draw.line(line_surf, color, (int(x1), int(y1)), (int(x2), int(y2)), thickness)
                
                self.screen.blit(line_surf, (0, 0))
    
    def draw_ecg_waveform(self):
        """Draw ECG waveform at the bottom of the screen"""
        if not self.ecg_enabled or len(self.ecg_history) < 2:
            return
        
        # ECG display area (bottom 80 pixels)
        ecg_height = 80
        ecg_y_start = self.height - ecg_height
        ecg_y_center = ecg_y_start + ecg_height // 2
        
        # Draw ECG background
        ecg_bg = pygame.Surface((self.width, ecg_height))
        ecg_bg.set_alpha(40)
        ecg_bg.fill((0, 20, 0))  # Dark green background
        self.screen.blit(ecg_bg, (0, ecg_y_start))
        
        # Draw ECG grid lines
        for i in range(0, self.width, 60):
            pygame.draw.line(self.screen, (0, 30, 0), (i, ecg_y_start), (i, self.height), 1)
        
        # Draw center line
        pygame.draw.line(self.screen, (0, 50, 0), (0, ecg_y_center), (self.width, ecg_y_center), 1)
        
        # Convert ECG samples to screen coordinates
        points = []
        ecg_samples = list(self.ecg_history)
        
        # Normalize ECG values
        if ecg_samples:
            min_val = min(ecg_samples)
            max_val = max(ecg_samples)
            val_range = max_val - min_val if max_val != min_val else 1
            
            # Take recent samples to fit screen width
            samples_to_show = min(len(ecg_samples), self.width * 2)
            recent_samples = ecg_samples[-samples_to_show:]
            
            for i, sample in enumerate(recent_samples):
                # X position (right to left scrolling)
                x = self.width - (len(recent_samples) - i) // 2
                
                # Y position (normalized and inverted for display)
                normalized = (sample - min_val) / val_range
                y = ecg_y_center - (normalized - 0.5) * (ecg_height - 20)
                
                if 0 <= x < self.width:
                    points.append((x, y))
        
        # Draw ECG line with glow effect
        if len(points) > 1:
            # Multiple passes for glow effect
            for thickness in range(3, 0, -1):
                alpha = int(150 / thickness)
                color = (0, 255, 100) if thickness == 1 else (0, 150, 50)  # Bright green ECG
                
                line_surf = pygame.Surface((self.width, ecg_height))
                line_surf.set_alpha(alpha)
                line_surf.fill((0, 0, 0))
                line_surf.set_colorkey((0, 0, 0))
                
                # Adjust points for local surface
                local_points = [(x, y - ecg_y_start) for x, y in points]
                
                if len(local_points) > 1:
                    pygame.draw.lines(line_surf, color, False, local_points, thickness)
                
                self.screen.blit(line_surf, (0, ecg_y_start))
        
        # ECG label
        ecg_label = self.font_small.render("ECG", True, (0, 200, 100))
        self.screen.blit(ecg_label, (10, ecg_y_start + 5))
    
    def draw_hud(self):
        """Draw HUD with current HR"""
        # Current HR display - just the number and BPM, no background
        hr_color = self.get_hr_color(self.current_hr)
        hr_text = self.font_large.render(f"{self.current_hr:3d} BPM", True, hr_color)
        
        # Position in top right
        self.screen.blit(hr_text, (self.width - hr_text.get_width() - 20, 20))
    
    def update(self):
        """Update animation and pulse effects"""
        self.pulse_phase += 0.1
        
        # Slowly decay glow intensity if no recent updates
        current_time = time.time()
        if current_time - self.last_beat_time > 2.0:
            self.glow_intensity *= 0.98
    
    def render(self):
        """Render the complete visualization"""
        # Clear screen
        self.screen.fill(self.bg_color)
        
        # Draw components
        self.draw_grid()
        self.draw_heartbeat_line()
        self.draw_ecg_waveform()  # Add ECG display
        self.draw_hud()
        
        # Update display
        pygame.display.flip()
        self.clock.tick(60)  # 60 FPS
    
    def handle_events(self):
        """Handle pygame events"""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
            elif event.type == pygame.VIDEORESIZE:
                # Handle window resize
                self.width = event.w
                self.height = event.h
                self.screen = pygame.display.set_mode((self.width, self.height), pygame.RESIZABLE)
                
                # Update data storage for new width
                new_hr_maxlen = self.width // 2
                new_ecg_maxlen = self.width * 4
                
                # Preserve existing data while updating maxlen
                old_hr_data = list(self.hr_history)
                old_time_data = list(self.time_history)
                old_ecg_data = list(self.ecg_history)
                
                self.hr_history = deque(old_hr_data, maxlen=new_hr_maxlen)
                self.time_history = deque(old_time_data, maxlen=new_hr_maxlen)
                self.ecg_history = deque(old_ecg_data, maxlen=new_ecg_maxlen)
                
        return True
    
    def run_demo(self):
        """Run a demo with simulated heart rate data"""
        running = True
        demo_time = 0
        
        while running:
            running = self.handle_events()
            
            # Simulate heart rate data
            demo_time += 0.1
            simulated_hr = int(70 + 30 * math.sin(demo_time * 0.1) + 10 * math.sin(demo_time * 0.5))
            simulated_hr = max(self.hr_min, min(self.hr_max, simulated_hr))
            
            # Simulate RR intervals for pulse effect
            rr_intervals = [800] if int(demo_time * 10) % 8 == 0 else []
            
            self.update_heart_rate(simulated_hr, rr_intervals)
            self.update()
            self.render()
        
        pygame.quit()

if __name__ == "__main__":
    visualizer = HeartbeatVisualizer()
    print("Running heart rate visualizer demo...")
    print("Press ESC or close window to exit")
    visualizer.run_demo()
