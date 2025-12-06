import os
import importlib
from typing import Dict, Any

PLUGIN_REGISTRY: Dict[str, Dict[str, Any]] = {}


def load_plugins():
    """Auto-discover and load all plugins from the plugins directory"""
    plugin_dir = os.path.dirname(__file__)
    
    if not os.path.exists(plugin_dir):
        return
    
    for filename in os.listdir(plugin_dir):
        if filename.endswith(".py") and filename != "__init__.py":
            module_name = filename[:-3]  # Remove .py extension
            
            try:
                # Import the module
                module = importlib.import_module(f"plugins.{module_name}")
                
                # Check if module has a register function
                if hasattr(module, "register"):
                    info = module.register()
                    
                    if isinstance(info, dict) and "name" in info:
                        PLUGIN_REGISTRY[info["name"]] = info
                        print(f"[PLUGIN] ✅ Loaded: {info['name']}")
                    else:
                        print(f"[PLUGIN] ⚠️ Invalid register() return value in {module_name}")
                else:
                    print(f"[PLUGIN] ⚠️ No register() function in {module_name}")
            except Exception as e:
                print(f"[PLUGIN] ❌ Failed to load {module_name}: {e}")


def get_plugin_tools():
    """Get all tool schemas from loaded plugins"""
    tools = []
    for plugin_name, plugin_info in PLUGIN_REGISTRY.items():
        if "schema" in plugin_info:
            tools.append(plugin_info["schema"])
    return tools


def execute_plugin_tool(tool_name: str, args: Dict[str, Any]) -> Any:
    """Execute a plugin tool by name"""
    if tool_name in PLUGIN_REGISTRY:
        plugin_info = PLUGIN_REGISTRY[tool_name]
        if "handler" in plugin_info:
            return plugin_info["handler"](args)
        else:
            return {"error": f"Plugin {tool_name} has no handler function"}
    else:
        return {"error": f"Unknown plugin tool: {tool_name}"}

