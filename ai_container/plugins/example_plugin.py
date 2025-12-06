"""
Example plugin template for Gem-bot

To create a new plugin:
1. Copy this file to a new name (e.g., my_plugin.py)
2. Implement the register() function
3. Define your tool schema
4. Implement your handler function
5. Place the file in the plugins/ directory
"""


def register():
    """
    Register this plugin with the system.
    
    Returns a dictionary with:
    - name: Unique tool name (used in tool calls)
    - description: Human-readable description
    - schema: Tool schema compatible with LLM function calling
    - handler: Function to call when tool is invoked
    """
    return {
        "name": "calculator",
        "description": "Perform advanced math operations",
        "schema": {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Perform a math calculation. Supports basic arithmetic and common functions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "The mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/2)')"
                        }
                    },
                    "required": ["expression"]
                },
            },
        },
        "handler": calc_handler
    }


def calc_handler(args: dict) -> dict:
    """
    Handle calculator tool calls.
    
    Args:
        args: Dictionary containing tool arguments
        
    Returns:
        Dictionary with result or error
    """
    import math
    import re
    
    expression = args.get("expression", "").strip()
    
    if not expression:
        return {"error": "No expression provided"}
    
    # Security: Only allow safe math operations
    # Remove any potentially dangerous operations
    safe_chars = set("0123456789+-*/.() ,")
    if not all(c in safe_chars or c.isalpha() for c in expression):
        return {"error": "Expression contains invalid characters"}
    
    # Create a safe evaluation context
    safe_dict = {
        "__builtins__": {},
        "math": math,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "exp": math.exp,
        "pi": math.pi,
        "e": math.e,
    }
    
    try:
        # Evaluate the expression safely
        result = eval(expression, safe_dict)
        return {"result": result, "expression": expression}
    except Exception as e:
        return {"error": f"Calculation failed: {str(e)}"}

