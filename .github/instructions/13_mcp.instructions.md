---
applyTo: "app/mcp/**,app/**/*mcp*.py,app/**/*tool*.py"
---

# SKILL 13 — MODEL CONTEXT PROTOCOL (MCP)
## Source: `docs/skills/SKILL_mcp.md`

---

## PURPOSE

MCP allows the AI layer to call structured tools (catalog lookup, order write,
customer profile fetch) rather than hallucinating data. Without MCP tool
definitions, the AI has no reliable mechanism to interact with live business data.

---

## ARCHITECTURE

```
Customer WhatsApp Message
         ↓
  Orchestrator (app/core/orchestrator.py)
         ↓
  AI Provider — receives tool definitions at inference time
         ↓
  Model decides: respond OR call tool
         ↓
  Tool Executor (app/mcp/executor.py)
         ↓
  Tool Result → back to model → final customer response
```

---

## DIRECTORY STRUCTURE

```
app/mcp/
├── __init__.py
├── schemas.py          # MCPTool, MCPToolResult dataclasses
├── registry.py         # All tool registrations in one place
├── executor.py         # Tool dispatch and execution
└── tools/
    ├── catalog.py      # Medicine catalog lookups
    ├── orders.py       # Order management
    ├── customers.py    # Customer profile
    ├── inventory.py    # Stock checking
    ├── billing.py      # Billing calculations
    ├── sessions.py     # Session state
    ├── notifications.py# WhatsApp send
    └── admin.py        # Owner admin actions
```

---

## MCP TOOL SCHEMA (app/mcp/schemas.py)

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum

class ToolStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"
    PERMISSION_DENIED = "permission_denied"

@dataclass
class MCPTool:
    name: str                       # snake_case, unique
    description: str                # Clear, single-sentence description for model
    input_schema: dict              # JSON Schema of parameters
    requires_distributor_id: bool = True  # Most tools are tenant-scoped

@dataclass
class MCPToolResult:
    tool_name: str
    status: ToolStatus
    data: dict | None = None        # Tool output data
    error_message: str | None = None
    execution_time_ms: int = 0
```

---

## TOOL REGISTRATION (app/mcp/registry.py)

```python
REGISTERED_TOOLS: list[MCPTool] = [
    MCPTool(
        name="lookup_medicine",
        description="Look up a medicine by name in the distributor's catalog. Returns price, stock, and product info.",
        input_schema={
            "type": "object",
            "properties": {
                "medicine_name": {"type": "string", "description": "Medicine name as spoken by customer"},
                "distributor_id": {"type": "string", "description": "Distributor UUID"},
            },
            "required": ["medicine_name", "distributor_id"],
        },
    ),
    # ... all tools registered here
]

def get_tools_for_provider(provider: str) -> list[dict]:
    """Convert MCPTool list to provider-specific format."""
```

---

## TOOL EXECUTOR (app/mcp/executor.py)

```python
async def execute_tool(
    tool_name: str,
    arguments: dict,
    distributor_id: str,
    context: RequestContext,
) -> MCPToolResult:
    """Dispatch tool call to the appropriate handler.

    All tool calls are:
    1. Validated against the tool's input_schema
    2. Scoped to distributor_id (tenant isolation)
    3. Logged with execution time
    4. Errors returned as MCPToolResult(status=ERROR), never raised
    """
```

---

## TOOL IMPLEMENTATION RULES

1. Every tool function must be `async def` and fully typed
2. Tools never raise exceptions — return `MCPToolResult(status=ERROR, error_message=...)`
3. Every tool call logged to `mcp_tool_invocation_log` table
4. Tools are tenant-scoped — always pass `distributor_id` as filter
5. Tool execution time logged for performance monitoring
6. Tools should be idempotent where possible

---

## TOOLS TO IMPLEMENT

| Tool Name | File | Description |
|---|---|---|
| `lookup_medicine` | catalog.py | Fuzzy search medicine by name |
| `get_medicine_stock` | inventory.py | Real-time stock level |
| `add_order_item` | orders.py | Add item to pending order draft |
| `remove_order_item` | orders.py | Remove item from pending draft |
| `get_order_summary` | orders.py | Current draft order details |
| `confirm_order` | orders.py | Finalize and submit order |
| `get_customer_profile` | customers.py | Customer info + order history |
| `calculate_bill` | billing.py | Compute order total with discounts |
| `send_whatsapp_message` | notifications.py | Send message to customer |
| `get_active_discounts` | billing.py | Active discount rules for distributor |
