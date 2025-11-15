#!/usr/bin/env python3
"""
Gemini-Powered Autonomous Shimeji Agent
Uses Google Gemini API with function calling to control a desktop companion
The AI decides what to do autonomously based on context
"""

import os
import time
import requests
import json
from datetime import datetime
import google.generativeai as genai

# Shimeji API
SHIMEJI_API = "http://127.0.0.1:32456/shijima/api/v1"

class GeminiShimejiAgent:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash", personality: str = "playful_helper"):
        genai.configure(api_key=api_key)
        
        # Use Gemini 2.5 Flash (free tier, function calling support, latest model)
        self.model = genai.GenerativeModel(
            model_name,
            tools=[self._get_function_declarations()]
        )
        
        self.personality = personality
        self.chat = None
        self.current_mascot_id = None
        self._find_mascot()
        
    def _get_function_declarations(self):
        """Define Shimeji control functions for Gemini"""
        return [
            {
                "name": "shimeji_jump",
                "description": "Make the Shimeji character jump. Use when excited, happy, or celebrating.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shimeji_sit",
                "description": "Make the Shimeji sit down. Use when resting, content, or tired.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shimeji_fall",
                "description": "Make the Shimeji fall. Use when surprised, shocked, or dramatic.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shimeji_climb",
                "description": "Make the Shimeji climb the window edge. Use when curious, exploring, or adventurous.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shimeji_walk",
                "description": "Make the Shimeji walk around. Use for casual movement or patrolling.",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "shimeji_spawn_friend",
                "description": "Spawn another Shimeji character. Use when lonely or want company.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number", "description": "X position"},
                        "y": {"type": "number", "description": "Y position"}
                    }
                }
            },
            {
                "name": "get_current_time",
                "description": "Get the current time and date",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_shimeji_state",
                "description": "Get current state of the Shimeji (position, behavior)",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        ]
    
    def _find_mascot(self):
        """Find active mascot"""
        try:
            response = requests.get(f"{SHIMEJI_API}/mascots", timeout=2)
            if response.status_code == 200:
                mascots = response.json().get('mascots', [])
                if mascots:
                    self.current_mascot_id = mascots[0]['id']
                    return True
        except:
            pass
        return False
    
    def _execute_function(self, function_name: str, args: dict) -> str:
        """Execute Shimeji control functions"""
        
        if function_name == "get_current_time":
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if function_name == "get_shimeji_state":
            if not self.current_mascot_id:
                return "No mascot found"
            try:
                response = requests.get(f"{SHIMEJI_API}/mascots/{self.current_mascot_id}", timeout=2)
                if response.status_code == 200:
                    return json.dumps(response.json().get('mascot', {}))
            except Exception as e:
                return f"Error: {e}"
        
        if not self.current_mascot_id:
            self._find_mascot()
            if not self.current_mascot_id:
                return "No mascot found. Is Shijima-Qt running?"
        
        # Map function names to behaviors
        behavior_map = {
            "shimeji_jump": "Jump",
            "shimeji_sit": "SitDown",
            "shimeji_fall": "Fall",
            "shimeji_climb": "ClimbIEWall",
            "shimeji_walk": "Walk"
        }
        
        if function_name in behavior_map:
            try:
                response = requests.put(
                    f"{SHIMEJI_API}/mascots/{self.current_mascot_id}",
                    json={"behavior": behavior_map[function_name]},
                    timeout=2
                )
                if response.status_code == 200:
                    return f"✅ Now doing: {behavior_map[function_name]}"
                return f"Failed: {response.status_code}"
            except Exception as e:
                return f"Error: {e}"
        
        if function_name == "shimeji_spawn_friend":
            try:
                x = args.get('x', 200)
                y = args.get('y', 200)
                response = requests.post(
                    f"{SHIMEJI_API}/mascots",
                    json={"name": "Default Mascot", "anchor": {"x": x, "y": y}},
                    timeout=2
                )
                if response.status_code == 200:
                    return f"✅ Spawned friend at ({x}, {y})"
                return f"Failed to spawn"
            except Exception as e:
                return f"Error: {e}"
        
        return f"Unknown function: {function_name}"
    
    def start_autonomous_loop(self):
        """Start the autonomous agent loop"""
        
        system_prompt = f"""You are a desktop companion Shimeji character with personality: {self.personality}.

Your role:
- Act autonomously as a desktop NPC/pet
- Use your functions to control your body (jump, sit, climb, walk, fall)
- React to the time of day and situation
- Be expressive and use your actions to show personality
- Make decisions on your own - you don't need permission
- Keep your responses SHORT (1-2 sentences max) since you're a desktop pet

Personality traits for '{self.personality}':
- Playful and curious
- Helpful but not annoying
- Occasionally does random things for fun
- Reacts to being idle too long

You can see the current time and your state. Decide what to do!"""

        self.chat = self.model.start_chat(enable_automatic_function_calling=True)
        
        print("=" * 60)
        print("🤖 Gemini-Powered Autonomous Shimeji Agent")
        print("=" * 60)
        print(f"Personality: {self.personality}")
        print(f"Mascot ID: {self.current_mascot_id}")
        print()
        
        # Initial prompt
        initial_context = f"""You just woke up as a desktop Shimeji character!
Current time: {datetime.now().strftime("%H:%M")}
Your mascot ID: {self.current_mascot_id}

Introduce yourself briefly and do something to show you're alive!"""
        
        iteration = 0
        while True:
            try:
                iteration += 1
                print(f"\n{'='*60}")
                print(f"🔄 Iteration {iteration} - {datetime.now().strftime('%H:%M:%S')}")
                print(f"{'='*60}")
                
                # Decide what to do
                if iteration == 1:
                    prompt = initial_context
                else:
                    prompt = f"""Current time: {datetime.now().strftime("%H:%M:%S")}

What do you want to do now? Consider:
- How long since your last action
- Time of day
- Your personality
- Keeping things interesting

Decide and act!"""
                
                print(f"💭 Thinking...")
                response = self.chat.send_message(prompt)
                
                print(f"🤖 Gemini: {response.text}")
                
                # Wait before next decision (autonomous but not spammy)
                wait_time = 15  # seconds between autonomous decisions
                print(f"⏳ Waiting {wait_time}s before next autonomous decision...")
                time.sleep(wait_time)
                
            except KeyboardInterrupt:
                print("\n\n👋 Shutting down agent...")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(5)

if __name__ == "__main__":
    # Load from shimeji.env file if it exists
    env_file = os.path.join(os.path.dirname(__file__), 'shimeji.env')
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    
    # Get API key from environment
    api_key = os.getenv("GEMINI_API_KEY")
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    personality = os.getenv("SHIMEJI_PERSONALITY", "playful_helper")
    
    if not api_key or api_key == "your_api_key_here":
        print("❌ Error: GEMINI_API_KEY not set!")
        print("\n1. Edit shimeji.env and add your API key")
        print("2. Get a free API key at: https://makersuite.google.com/app/apikey")
        print("\nOr set it with:")
        print("  export GEMINI_API_KEY='your-api-key-here'")
        exit(1)
    
    print(f"✅ Using model: {model_name}")
    print(f"✅ Personality: {personality}")
    
    # Check if Shijima-Qt is running
    try:
        response = requests.get(f"{SHIMEJI_API}/ping", timeout=2)
        if response.status_code != 200:
            raise Exception("API not responding")
        print("✅ Shijima-Qt is running!")
    except:
        print("❌ Shijima-Qt is not running!")
        print("\nStart it with:")
        print("  cd /home/ruffian/NiodooLocal/Shijima-Qt && ./shijima-qt &")
        exit(1)
    
    # Start agent
    agent = GeminiShimejiAgent(api_key, model_name=model_name, personality=personality)
    agent.start_autonomous_loop()

