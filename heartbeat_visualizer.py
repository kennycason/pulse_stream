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
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Heart Rate Monitor")
        
        # Heart rate configuration
        self.hr_min = hr_min
        self.hr_max = hr_max
        self.hr_safe_min = 60  # Green zone start
        self.hr_safe_max = 80  # Green zone end
        
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
            
        # Trigger pulse animation
        if rr_intervals and len(rr_intervals) > 0:
            self.last_beat_time = current_time
    
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
        # Use full range 50-180 BPM
        margin = 40  # Top and bottom margin
        
        # Horizontal lines (HR levels) - full range
        for hr in range(self.hr_min, self.hr_max + 1, 10):
            # Calculate y position using full range
            y = self.height - margin - ((hr - self.hr_min) / (self.hr_max - self.hr_min)) * (self.height - 2 * margin)
            
            if margin <= y <= self.height - margin:
                alpha = 120 if hr % 20 == 0 else 60
                # Create a surface for alpha blending
                line_surf = pygame.Surface((self.width, 1))
                line_surf.set_alpha(alpha)
                line_surf.fill(self.grid_color)
                self.screen.blit(line_surf, (0, int(y)))
                
                # Label major grid lines with colors based on HR zones
                if hr % 20 == 0:
                    label_color = self.get_hr_color(hr)
                    label = self.font_medium.render(f"{hr}", True, label_color)
                    self.screen.blit(label, (10, int(y) - 12))
        
        # Vertical time lines
        for i in range(0, self.width, 30):  # Closer vertical lines for 2x speed
            alpha = 80 if i % 60 == 0 else 40
            line_surf = pygame.Surface((1, self.height))
            line_surf.set_alpha(alpha)
            line_surf.fill(self.grid_color)
            self.screen.blit(line_surf, (i, 0))
    
    def draw_heartbeat_line(self):
        """Draw the heartbeat waveform with rainbow coloring"""
        if len(self.hr_history) < 2:
            return
            
        current_time = time.time()
        margin = 40
        
        # Create segments with individual colors
        segments = []
        for i, (hr, timestamp) in enumerate(zip(self.hr_history, self.time_history)):
            # Much faster movement: map fewer data points across full screen width
            x = self.width - (len(self.hr_history) - i) * 2
            
            # Use full range positioning
            base_y = self.height - margin - ((hr - self.hr_min) / (self.hr_max - self.hr_min)) * (self.height - 2 * margin)
            
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
