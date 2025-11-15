#!/usr/bin/env python3
"""
Niodoo Shimeji Bridge
Connects Niodoo telemetry to Shijima-Qt desktop pet
- Reads telemetry from localhost:9999 (via SSH tunnel to RunPod)
- Controls Shimeji behavior via HTTP API (localhost:32456)
- Displays AI responses in chat bubbles above the Shimeji
"""

import asyncio
import json
import requests
from typing import Optional, Dict, Any
import sys

class NiodooShimejiBridge:
    def __init__(self, telemetry_host='127.0.0.1', telemetry_port=9999, shimeji_port=32456):
        self.telemetry_host = telemetry_host
        self.telemetry_port = telemetry_port
        self.shimeji_api = f"http://127.0.0.1:{shimeji_port}/shijima/api/v1"
        self.current_mascot_id = None
        self.last_behavior = None
        
    def get_mascots(self) -> list:
        """Get list of active mascots"""
        try:
            response = requests.get(f"{self.shimeji_api}/mascots", timeout=2)
            if response.status_code == 200:
                return response.json().get('mascots', [])
        except Exception as e:
            print(f"⚠️  Failed to get mascots: {e}")
        return []
    
    def set_behavior(self, mascot_id: int, behavior: str):
        """Change mascot behavior"""
        try:
            payload = {"behavior": behavior}
            response = requests.put(
                f"{self.shimeji_api}/mascots/{mascot_id}",
                json=payload,
                timeout=2
            )
            if response.status_code == 200:
                print(f"✅ Set behavior to: {behavior}")
                self.last_behavior = behavior
                return True
        except Exception as e:
            print(f"⚠️  Failed to set behavior: {e}")
        return False
    
    def map_emotional_state_to_behavior(self, telemetry: Dict[str, Any]) -> Optional[str]:
        """Map Niodoo emotional/cognitive state to Shimeji behavior"""
        
        # Extract emotional state (PAD model)
        pad = telemetry.get('pad_state', {})
        pleasure = pad.get('pleasure', 0.0)
        arousal = pad.get('arousal', 0.0)
        dominance = pad.get('dominance', 0.0)
        
        # Extract compass quadrant
        compass = telemetry.get('compass_quadrant', '')
        
        # Extract consciousness state
        consciousness = telemetry.get('consciousness_point', {})
        
        # Behavior mapping based on emotional state
        # High arousal + positive pleasure = excited/active
        if arousal > 0.5 and pleasure > 0.5:
            return "Jump"  # Happy, energetic
        
        # High arousal + negative pleasure = stressed
        elif arousal > 0.5 and pleasure < -0.5:
            return "Fall"  # Panic, distress
        
        # Low arousal + positive pleasure = content
        elif arousal < -0.5 and pleasure > 0.5:
            return "SitDown"  # Relaxed, content
        
        # Low arousal + negative pleasure = sad
        elif arousal < -0.5 and pleasure < -0.5:
            return "SitDown"  # Sad, low energy
        
        # Compass quadrant behaviors
        if compass == "Panic":
            return "Fall"
        elif compass == "Discover":
            return "ClimbIEWall"  # Exploring
        elif compass == "Persist":
            return "Walk"  # Steady progress
        elif compass == "Master":
            return "Jump"  # Achievement!
        
        # Default: let it do its thing
        return None
    
    def display_chat_bubble(self, mascot_id: int, text: str):
        """Display chat bubble above mascot (placeholder - needs Qt overlay)"""
        # TODO: Implement Qt overlay window for chat bubbles
        # For now, just print to console
        print(f"💬 AI says: {text[:100]}...")
    
    async def handle_telemetry_stream(self):
        """Connect to Niodoo telemetry and process stream"""
        print(f"🔌 Connecting to Niodoo telemetry at {self.telemetry_host}:{self.telemetry_port}")
        
        while True:
            try:
                # Connect to telemetry TCP server
                reader, writer = await asyncio.open_connection(
                    self.telemetry_host, 
                    self.telemetry_port
                )
                print(f"✅ Connected to Niodoo telemetry!")
                
                # Get current mascot
                mascots = self.get_mascots()
                if mascots:
                    self.current_mascot_id = mascots[0]['id']
                    print(f"🎭 Controlling mascot ID: {self.current_mascot_id}")
                else:
                    print("⚠️  No mascots found! Make sure Shijima-Qt is running.")
                
                # Read telemetry stream
                while True:
                    try:
                        line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                        if not line:
                            print("⚠️  Connection closed by server")
                            break
                        
                        line = line.decode('utf-8').strip()
                        if not line:
                            continue
                        
                        # Parse JSON telemetry packet
                        try:
                            packet = json.loads(line)
                            
                            # Print telemetry info
                            iteration = packet.get('iteration', '?')
                            compass = packet.get('compass_quadrant', 'Unknown')
                            pad = packet.get('pad_state', {})
                            
                            print(f"📊 Iteration {iteration} | Compass: {compass} | "
                                  f"P:{pad.get('pleasure', 0):.2f} A:{pad.get('arousal', 0):.2f} D:{pad.get('dominance', 0):.2f}")
                            
                            # Map to behavior
                            if self.current_mascot_id:
                                behavior = self.map_emotional_state_to_behavior(packet)
                                if behavior and behavior != self.last_behavior:
                                    self.set_behavior(self.current_mascot_id, behavior)
                            
                            # Handle AI response text if present
                            if 'response_text' in packet:
                                self.display_chat_bubble(self.current_mascot_id, packet['response_text'])
                            
                        except json.JSONDecodeError as e:
                            print(f"⚠️  Failed to parse JSON: {e}")
                            continue
                    
                    except asyncio.TimeoutError:
                        # No data for 5 seconds, check if mascot still exists
                        if self.current_mascot_id:
                            mascots = self.get_mascots()
                            if not any(m['id'] == self.current_mascot_id for m in mascots):
                                print("⚠️  Mascot disappeared, finding new one...")
                                if mascots:
                                    self.current_mascot_id = mascots[0]['id']
                        continue
                    
                    except Exception as e:
                        print(f"⚠️  Error processing telemetry: {e}")
                        break
                
                writer.close()
                await writer.wait_closed()
                
            except ConnectionRefusedError:
                print(f"❌ Failed to connect to telemetry server. Is SSH tunnel running?")
                print(f"   Run: ssh -N -L 9999:localhost:9999 root@38.80.152.77 -p 30534 -i ~/.ssh/id_ed25519 &")
                await asyncio.sleep(5)
            
            except Exception as e:
                print(f"❌ Error: {e}")
                await asyncio.sleep(5)
            
            print("🔄 Reconnecting in 2 seconds...")
            await asyncio.sleep(2)
    
    async def start(self):
        """Start the bridge"""
        print("=" * 60)
        print("🌉 Niodoo Shimeji Bridge")
        print("=" * 60)
        print(f"Telemetry: {self.telemetry_host}:{self.telemetry_port}")
        print(f"Shimeji API: {self.shimeji_api}")
        print()
        
        # Check if Shijima-Qt is running
        try:
            response = requests.get(f"{self.shimeji_api}/ping", timeout=2)
            if response.status_code == 200:
                print("✅ Shijima-Qt is running!")
            else:
                print("⚠️  Shijima-Qt API returned unexpected status")
        except Exception as e:
            print(f"❌ Cannot connect to Shijima-Qt! Is it running?")
            print(f"   Run: cd /home/ruffian/NiodooLocal/Shijima-Qt && ./shijima-qt &")
            print(f"   Error: {e}")
            return
        
        print()
        await self.handle_telemetry_stream()

if __name__ == "__main__":
    bridge = NiodooShimejiBridge()
    try:
        asyncio.run(bridge.start())
    except KeyboardInterrupt:
        print("\n👋 Shutting down bridge...")
        sys.exit(0)




