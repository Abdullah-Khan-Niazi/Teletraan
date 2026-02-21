# MODEL CONTEXT PROTOCOL (MCP) SKILL
## SKILL: mcp | Version: 1.0 | Priority: HIGH

---

## PURPOSE

This skill defines how TELETRAAN implements Model Context Protocol (MCP) —
the standardized interface through which AI models interact with external
tools, databases, and services at inference time.

MCP allows the TELETRAAN AI layer to call structured tools (catalog lookup,
order write, customer profile fetch) rather than relying on the model to
hallucinate data or produce free-form text that must be parsed downstream.

This is not optional. Without MCP tool definitions, the AI model has no
reliable mechanism to interact with live business data.

---

## ARCHITECTURE

```
Customer WhatsApp Message
         ↓
  Message Handler (FastAPI)
         ↓
  Orchestrator (app/core/orchestrator.py)
         ↓
  AI Provider (with MCP tools registered)
         ↓
  Model decides: respond OR call tool
         ↓
  Tool Executor (app/mcp/executor.py)
         ↓
  Tool Result → back to model → final response
```

The model receives tool definitions at inference time. When the model decides
to call a tool, TELETRAAN's executor runs the corresponding Python function
and returns the result. The model then generates the final customer-facing
response incorporating the tool result.

---

## DIRECTORY STRUCTURE

```
app/
  mcp/
    __init__.py
    schemas.py          ← MCPTool, MCPToolResult dataclasses
    registry.py         ← Tool registration (all tools in one place)
    executor.py         ← Tool dispatch and execution
    tools/
      __init__.py
      catalog.py        ← Medicine catalog tools
      orders.py         ← Order management tools
      customers.py      ← Customer profile tools
      inventory.py      ← Stock checking tools
      billing.py        ← Billing calculation tools
      sessions.py       ← Session state tools
      notifications.py  ← WhatsApp send tools
      admin.py          ← Owner admin tools
```

---

## MCP TOOL SCHEMA

```python
# app/mcp/schemas.py

from dataclasses import dataclass, field
from typing import Any, Optional
from enum import Enum


class ToolStatus(str, Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    ERROR = "error"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"


@dataclass
class MCPToolParameter:
    name: str
    type: str           # "string" | "number" | "boolean" | "array" | "object"
    description: str
    required: bool = True
    enum: Optional[list] = None
    default: Any = None


@dataclass
class MCPTool:
    name: str           # snake_case, globally unique
    description: str    # what this tool does (model reads this to decide when to call)
    parameters: list[MCPToolParameter]
    requires_distributor_context: bool = True
    requires_customer_context: bool = False
    is_read_only: bool = True       # False for tools that write data


@dataclass
class MCPToolResult:
    tool_name: str
    status: ToolStatus
    data: Optional[dict | list] = None
    error_message: Optional[str] = None
    cache_hit: bool = False
    execution_ms: int = 0
```

---

## TOOL REGISTRY

```python
# app/mcp/registry.py

# All tools available to the AI model during inference.
# The model reads tool descriptions and parameters to decide which to call.
# Keep descriptions precise — the model uses them for tool selection.

TELETRAAN_TOOLS: list[MCPTool] = [

    # ── CATALOG TOOLS ──────────────────────────────────────────────────

    MCPTool(
        name="search_medicine_catalog",
        description=(
            "Search the distributor's medicine catalog by name. "
            "Use when a customer requests a medicine. Returns matching items "
            "with price, stock, and product details. Always call this before "
            "adding an item to an order."
        ),
        parameters=[
            MCPToolParameter("query", "string", "Medicine name as stated by customer"),
            MCPToolParameter("limit", "number", "Max results to return", required=False, default=5),
            MCPToolParameter("include_out_of_stock", "boolean", "Include OOS items", required=False, default=False),
        ],
        is_read_only=True,
    ),

    MCPTool(
        name="get_medicine_by_id",
        description="Get full details of a specific medicine by its catalog ID.",
        parameters=[
            MCPToolParameter("catalog_id", "string", "UUID of the catalog item"),
        ],
        is_read_only=True,
    ),

    # ── ORDER TOOLS ────────────────────────────────────────────────────

    MCPTool(
        name="add_item_to_order",
        description=(
            "Add a confirmed medicine item to the customer's current order. "
            "Only call this AFTER the customer has confirmed the item and quantity. "
            "Never call speculatively."
        ),
        parameters=[
            MCPToolParameter("catalog_id", "string", "UUID of the confirmed catalog item"),
            MCPToolParameter("quantity", "number", "Quantity requested by customer"),
            MCPToolParameter("unit", "string", "Unit: strip | box | bottle | piece | pack"),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    MCPTool(
        name="remove_item_from_order",
        description="Remove an item from the customer's current draft order.",
        parameters=[
            MCPToolParameter("draft_item_id", "string", "UUID of the draft order item"),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    MCPTool(
        name="update_item_quantity",
        description="Update the quantity of an existing item in the draft order.",
        parameters=[
            MCPToolParameter("draft_item_id", "string", "UUID of the draft order item"),
            MCPToolParameter("new_quantity", "number", "New quantity"),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    MCPTool(
        name="get_current_order",
        description=(
            "Retrieve the customer's current draft order with all items, "
            "quantities, prices, and running total. Call when customer asks "
            "to see the bill or review their order."
        ),
        parameters=[],
        requires_customer_context=True,
        is_read_only=True,
    ),

    MCPTool(
        name="calculate_bill",
        description=(
            "Calculate the full bill for the current order including "
            "applicable auto-discounts, delivery charges, and credit balance. "
            "Returns a structured billing summary."
        ),
        parameters=[
            MCPToolParameter("apply_auto_discount", "boolean", "Apply distributor auto-discount rules", required=False, default=True),
            MCPToolParameter("delivery_zone", "string", "Customer delivery zone for charge calculation", required=False),
        ],
        requires_customer_context=True,
        is_read_only=True,
    ),

    MCPTool(
        name="confirm_order",
        description=(
            "Finalize and confirm the customer's order. This writes the order "
            "to the database, decrements inventory, and triggers the order "
            "confirmation flow. Only call when customer explicitly says CONFIRM "
            "or equivalent confirmation intent."
        ),
        parameters=[
            MCPToolParameter("delivery_address", "string", "Delivery address if not on file", required=False),
            MCPToolParameter("special_instructions", "string", "Any special delivery notes", required=False),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    MCPTool(
        name="cancel_order",
        description="Cancel the customer's current draft order and clear order context.",
        parameters=[
            MCPToolParameter("reason", "string", "Cancellation reason (internal log)", required=False),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    # ── CUSTOMER TOOLS ─────────────────────────────────────────────────

    MCPTool(
        name="get_customer_profile",
        description=(
            "Get the customer's profile including name, credit limit, "
            "outstanding balance, order history count, and VIP status."
        ),
        parameters=[],
        requires_customer_context=True,
        is_read_only=True,
    ),

    MCPTool(
        name="get_customer_order_history",
        description="Get the customer's recent order history for reorder suggestions.",
        parameters=[
            MCPToolParameter("limit", "number", "Max orders to return", required=False, default=5),
        ],
        requires_customer_context=True,
        is_read_only=True,
    ),

    MCPTool(
        name="check_credit_balance",
        description="Check if customer has sufficient credit for the current order total.",
        parameters=[
            MCPToolParameter("order_total_paisas", "number", "Order total in paisas"),
        ],
        requires_customer_context=True,
        is_read_only=True,
    ),

    # ── INVENTORY TOOLS ────────────────────────────────────────────────

    MCPTool(
        name="check_stock",
        description="Check current stock level for a specific medicine.",
        parameters=[
            MCPToolParameter("catalog_id", "string", "UUID of the catalog item"),
        ],
        is_read_only=True,
    ),

    # ── DISCOUNT TOOLS ─────────────────────────────────────────────────

    MCPTool(
        name="apply_discount_request",
        description=(
            "Log a customer discount request for owner review. "
            "Use when customer asks for a price reduction. "
            "Do NOT apply the discount directly — it requires owner approval "
            "unless within auto-discount thresholds."
        ),
        parameters=[
            MCPToolParameter("requested_percent", "number", "Discount percentage requested", required=False),
            MCPToolParameter("customer_note", "string", "Customer's exact words regarding discount"),
        ],
        requires_customer_context=True,
        is_read_only=False,
    ),

    # ── ADMIN TOOLS (owner-only) ───────────────────────────────────────

    MCPTool(
        name="approve_discount",
        description="Owner approves a pending discount request for a customer order.",
        parameters=[
            MCPToolParameter("order_id", "string", "Order UUID"),
            MCPToolParameter("approved_percent", "number", "Approved discount percentage"),
        ],
        requires_customer_context=False,
        is_read_only=False,
    ),

    MCPTool(
        name="get_daily_order_summary",
        description="Get today's order summary for the distributor (owner/admin only).",
        parameters=[
            MCPToolParameter("date", "string", "Date in YYYY-MM-DD format", required=False),
        ],
        is_read_only=True,
    ),

]
```

---

## TOOL EXECUTOR

```python
# app/mcp/executor.py

import time
from loguru import logger
from app.mcp.schemas import MCPTool, MCPToolResult, ToolStatus
from app.mcp.registry import TELETRAAN_TOOLS


class MCPExecutor:
    """
    Dispatches AI-requested tool calls to the appropriate handler function.

    Receives a tool_name + parameters dict from the AI model,
    validates the call, executes the handler, and returns MCPToolResult.
    """

    def __init__(self, distributor_id: str, customer_phone: str | None, db):
        self.distributor_id = distributor_id
        self.customer_phone = customer_phone
        self.db = db
        self._tool_map = {t.name: t for t in TELETRAAN_TOOLS}

    async def execute(self, tool_name: str, parameters: dict) -> MCPToolResult:
        start = time.monotonic()

        tool = self._tool_map.get(tool_name)
        if not tool:
            return MCPToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                error_message=f"Unknown tool: {tool_name}",
            )

        if tool.requires_customer_context and not self.customer_phone:
            return MCPToolResult(
                tool_name=tool_name,
                status=ToolStatus.PERMISSION_DENIED,
                error_message="Customer context required but not provided.",
            )

        handler = self._get_handler(tool_name)
        if not handler:
            return MCPToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                error_message=f"No handler registered for tool: {tool_name}",
            )

        try:
            result = await handler(parameters, self.distributor_id, self.customer_phone, self.db)
            elapsed = int((time.monotonic() - start) * 1000)
            logger.info(
                "MCP tool executed",
                tool=tool_name,
                status=result.status,
                duration_ms=elapsed,
                distributor_id=self.distributor_id,
            )
            result.execution_ms = elapsed
            return result
        except Exception as exc:
            logger.error("MCP tool execution failed", tool=tool_name, error=str(exc))
            return MCPToolResult(
                tool_name=tool_name,
                status=ToolStatus.ERROR,
                error_message=f"Tool execution failed: {exc}",
                execution_ms=int((time.monotonic() - start) * 1000),
            )

    def _get_handler(self, tool_name: str):
        from app.mcp.tools import catalog, orders, customers, inventory, billing, admin
        handlers = {
            "search_medicine_catalog": catalog.search_medicine_catalog,
            "get_medicine_by_id": catalog.get_medicine_by_id,
            "add_item_to_order": orders.add_item_to_order,
            "remove_item_from_order": orders.remove_item_from_order,
            "update_item_quantity": orders.update_item_quantity,
            "get_current_order": orders.get_current_order,
            "calculate_bill": billing.calculate_bill,
            "confirm_order": orders.confirm_order,
            "cancel_order": orders.cancel_order,
            "get_customer_profile": customers.get_customer_profile,
            "get_customer_order_history": customers.get_customer_order_history,
            "check_credit_balance": customers.check_credit_balance,
            "check_stock": inventory.check_stock,
            "apply_discount_request": orders.apply_discount_request,
            "approve_discount": admin.approve_discount,
            "get_daily_order_summary": admin.get_daily_order_summary,
        }
        return handlers.get(tool_name)
```

---

## AI PROVIDER TOOL REGISTRATION

Each AI provider's `generate_text()` method accepts a `tools` parameter.
The provider converts the TELETRAAN MCPTool list to the provider's native
tool format (Gemini FunctionDeclaration, OpenAI functions schema, etc.).

```python
# app/ai/providers/gemini.py (example tool conversion)

def _convert_tools(self, tools: list[MCPTool]) -> list:
    """Convert MCPTool list to Gemini FunctionDeclaration format."""
    declarations = []
    for tool in tools:
        properties = {}
        required = []
        for param in tool.parameters:
            properties[param.name] = {
                "type": param.type.upper(),
                "description": param.description,
            }
            if param.enum:
                properties[param.name]["enum"] = param.enum
            if param.required:
                required.append(param.name)
        declarations.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            }
        })
    return declarations
```

---

## MCP TOOL IMPLEMENTATION RULES

### RULE 1 — TOOLS ARE ATOMIC
Each tool does exactly one thing. A tool that searches AND adds an item
is a design error.

### RULE 2 — TOOLS NEVER ASSUME
A tool that receives a `catalog_id` must validate that the catalog_id
belongs to the current `distributor_id`. Never trust the model-provided
parameter without a database check.

### RULE 3 — TOOLS ARE IDEMPOTENT WHERE POSSIBLE
`add_item_to_order` called twice with the same parameters should update
quantity, not add a duplicate item. This prevents duplication bugs when
the model retries a tool call.

### RULE 4 — TOOL RESULTS MUST BE STRUCTURED
Tool results must be clean JSON that the model can reason over.
Never return raw database rows or internal Python objects.
Clean, named fields only.

### RULE 5 — WRITE TOOLS LOG TO ai_tool_log TABLE
Every tool call (success and failure) is logged:
```sql
INSERT INTO ai_tool_log (
    distributor_id, customer_phone, tool_name, parameters_json,
    result_status, result_data_json, execution_ms, created_at
)
```

### RULE 6 — ADMIN TOOLS REQUIRE EXPLICIT PERMISSION CHECK
Before executing any admin tool, verify that the calling number matches
`distributors.owner_whatsapp_number` for the current distributor.

---

## DATABASE TABLE: ai_tool_log

```sql
CREATE TABLE ai_tool_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    distributor_id  UUID NOT NULL REFERENCES distributors(id),
    customer_phone  TEXT,
    tool_name       TEXT NOT NULL,
    parameters_json JSONB NOT NULL DEFAULT '{}',
    result_status   TEXT NOT NULL,  -- success | not_found | error | permission_denied
    result_data_json JSONB,
    error_message   TEXT,
    execution_ms    INTEGER,
    session_id      UUID REFERENCES sessions(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_ai_tool_log_distributor ON ai_tool_log(distributor_id, created_at DESC);
CREATE INDEX idx_ai_tool_log_tool_name ON ai_tool_log(tool_name, created_at DESC);
```

---

## TESTING MCP TOOLS

```python
# tests/mcp/test_executor.py

async def test_search_medicine_catalog_returns_results(mock_db, sample_distributor):
    executor = MCPExecutor(sample_distributor.id, None, mock_db)
    result = await executor.execute("search_medicine_catalog", {"query": "paracetamol"})
    assert result.status == ToolStatus.SUCCESS
    assert isinstance(result.data, list)
    assert len(result.data) > 0
    assert "catalog_id" in result.data[0]
    assert "price_per_unit_paisas" in result.data[0]

async def test_add_item_requires_customer_context(mock_db, sample_distributor):
    executor = MCPExecutor(sample_distributor.id, None, mock_db)
    result = await executor.execute("add_item_to_order", {"catalog_id": "abc", "quantity": 5, "unit": "strip"})
    assert result.status == ToolStatus.PERMISSION_DENIED

async def test_unknown_tool_returns_error(mock_db, sample_distributor):
    executor = MCPExecutor(sample_distributor.id, "+92300000001", mock_db)
    result = await executor.execute("nonexistent_tool", {})
    assert result.status == ToolStatus.ERROR
```

---

## GIT COMMIT FORMAT FOR MCP CHANGES

```
feat(mcp): add calculate_bill tool with auto-discount support

New MCP tool allows AI model to request bill calculation including:
- Auto-discount rules from distributor configuration
- Delivery charge by zone
- Credit balance check
- Returns structured BillingResult for model-readable consumption

Tool is read-only (no DB writes). Logged to ai_tool_log.

Signed-off-by: Abdullah-Khan-Niazi
```

---

*End of SKILL: mcp v1.0*
