#!/usr/bin/env python3
"""
Shimeji MCP Server
Exposes Shimeji-Qt controls as MCP tools so AI agents can control their own desktop companion
"""

import json
import requests
from typing import Any, Sequence
from mcp.server import Server
from mcp.types import Tool, TextContent
import mcp.server.stdio

# Shimeji API configuration
SHIMEJI_API_BASE = "http://127.0.0.1:32456/shijima/api/v1"

class ShimejiMCPServer:
    def __init__(self):
        self.server = Server("shimeji-controller")
        self.current_mascot_id = None
        
        # Register MCP tools
        self._register_tools()
        
    def _register_tools(self):
        """Register all Shimeji control tools"""
        
        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            return [
                Tool(
                    name="shimeji_get_state",
                    description="Get current state of the Shimeji character (position, behavior, etc.)",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_jump",
                    description="Make the Shimeji jump (shows excitement/happiness)",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_sit",
                    description="Make the Shimeji sit down (shows contentment/rest)",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_fall",
                    description="Make the Shimeji fall (shows surprise/panic)",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_climb",
                    description="Make the Shimeji climb the window edge (shows curiosity/exploration)",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_walk",
                    description="Make the Shimeji walk around",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    }
                ),
                Tool(
                    name="shimeji_spawn_friend",
                    description="Spawn another Shimeji character (make a friend!)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "x": {
                                "type": "number",
                                "description": "X position to spawn at"
                            },
                            "y": {
                                "type": "number",
                                "description": "Y position to spawn at"
                            }
                        }
                    }
                ),
                Tool(
                    name="shimeji_speak",
                    description="Make the Shimeji say something (shows text in a speech bubble) - NOT IMPLEMENTED YET, returns message",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "What the Shimeji should say"
                            }
                        },
                        "required": ["text"]
                    }
                ),
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
            """Handle tool calls"""
            
            # Ensure we have a mascot
            if not self.current_mascot_id:
                self._find_mascot()
            
            if name == "shimeji_get_state":
                return await self._get_state()
            elif name == "shimeji_jump":
                return await self._set_behavior("Jump")
            elif name == "shimeji_sit":
                return await self._set_behavior("SitDown")
            elif name == "shimeji_fall":
                return await self._set_behavior("Fall")
            elif name == "shimeji_climb":
                return await self._set_behavior("ClimbIEWall")
            elif name == "shimeji_walk":
                return await self._set_behavior("Walk")
            elif name == "shimeji_spawn_friend":
                return await self._spawn_mascot(
                    arguments.get("x", 200),
                    arguments.get("y", 200)
                )
            elif name == "shimeji_speak":
                # TODO: Implement speech bubbles with Qt overlay
                text = arguments.get("text", "...")
                return [TextContent(
                    type="text",
                    text=f"Speech bubble not implemented yet, but Shimeji would say: '{text}'"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Unknown tool: {name}"
                )]
    
    def _find_mascot(self):
        """Find an active mascot to control"""
        try:
            response = requests.get(f"{SHIMEJI_API_BASE}/mascots", timeout=2)
            if response.status_code == 200:
                mascots = response.json().get('mascots', [])
                if mascots:
                    self.current_mascot_id = mascots[0]['id']
                    return True
        except Exception as e:
            print(f"Error finding mascot: {e}")
        return False
    
    async def _get_state(self) -> Sequence[TextContent]:
        """Get current mascot state"""
        if not self.current_mascot_id:
            return [TextContent(
                type="text",
                text="No mascot found. Is Shijima-Qt running?"
            )]
        
        try:
            response = requests.get(
                f"{SHIMEJI_API_BASE}/mascots/{self.current_mascot_id}",
                timeout=2
            )
            if response.status_code == 200:
                mascot = response.json().get('mascot', {})
                return [TextContent(
                    type="text",
                    text=json.dumps(mascot, indent=2)
                )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error getting state: {e}"
            )]
    
    async def _set_behavior(self, behavior: str) -> Sequence[TextContent]:
        """Set mascot behavior"""
        if not self.current_mascot_id:
            return [TextContent(
                type="text",
                text="No mascot found. Is Shijima-Qt running?"
            )]
        
        try:
            response = requests.put(
                f"{SHIMEJI_API_BASE}/mascots/{self.current_mascot_id}",
                json={"behavior": behavior},
                timeout=2
            )
            if response.status_code == 200:
                return [TextContent(
                    type="text",
                    text=f"✅ Shimeji is now doing: {behavior}"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Failed to set behavior: {response.status_code}"
                )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error setting behavior: {e}"
            )]
    
    async def _spawn_mascot(self, x: float, y: float) -> Sequence[TextContent]:
        """Spawn a new mascot"""
        try:
            response = requests.post(
                f"{SHIMEJI_API_BASE}/mascots",
                json={
                    "name": "Default Mascot",
                    "anchor": {"x": x, "y": y}
                },
                timeout=2
            )
            if response.status_code == 200:
                mascot = response.json().get('mascot', {})
                return [TextContent(
                    type="text",
                    text=f"✅ Spawned new friend at ({x}, {y})! ID: {mascot.get('id')}"
                )]
            else:
                return [TextContent(
                    type="text",
                    text=f"Failed to spawn mascot: {response.status_code}"
                )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error spawning mascot: {e}"
            )]
    
    async def run(self):
        """Run the MCP server"""
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options()
            )

if __name__ == "__main__":
    import asyncio
    server = ShimejiMCPServer()
    asyncio.run(server.run())




