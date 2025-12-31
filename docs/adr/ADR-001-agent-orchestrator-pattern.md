---
title: ADR-001 - Agent-as-Orchestrator Pattern
status: Accepted
date: 2025-12-30
decision-makers: Architecture Team
consulted: Development Team
informed: All Stakeholders
---

# ADR-001: Agent-as-Orchestrator Pattern

## Status
**Accepted** - Implemented in v1.0

## Context

We need to build an AI agent that can use multiple specialized tools (file extraction, web search, code execution, image generation) to accomplish complex user tasks. The agent must:
- Decide which tools to use based on user requests
- Chain tool calls when needed (multi-step workflows)
- Handle errors and retry with alternatives
- Provide transparency about tool usage

### Options Considered

1. **LLM-as-Orchestrator (Chosen)**
   - LLM receives tool schemas and decides which to call
   - Agent implements execution infrastructure
   - Recursive pattern: LLM → tools → LLM → ...

2. **Rule-Based Orchestrator**
   - Hardcoded rules for tool selection
   - If-else logic for routing
   - Agent contains decision logic

3. **Separate Planning Agent + Execution Agent**
   - Planning agent creates execution plan
   - Execution agent runs the plan
   - Two-phase approach

## Decision

**We will use the LLM-as-Orchestrator pattern** where the LLM (GPT-4o/Claude) acts as the decision-making engine, selecting and coordinating tool executions.

### Implementation

```python
async def handle_request():
    while True:
        # LLM decides which tools to call
        response = await llm.stream(messages, tools=tool_schemas)
        
        if response.tool_calls:
            # Execute tools in parallel
            results = await execute_tools(response.tool_calls)
            
            # Append results to conversation
            messages.append(assistant_message)
            messages.extend(tool_results)
            
            # Recurse: LLM sees results, decides next action
            continue
        else:
            # No more tools needed, return final response
            return response
```

## Rationale

### Advantages

**1. Flexibility**
- LLM can handle novel combinations of tools without code changes
- Natural language understanding guides tool selection
- Can adapt strategy based on intermediate results

**Example**: User asks "Analyze this CSV and create a chart"
- LLM decides: extract file → analyze with Python → generate chart
- No hardcoded workflow needed

**2. Error Recovery**
- LLM can reason about errors and try alternatives
- If file extraction fails, might try RAG search instead
- Human-like problem-solving

**Example**: Large file extraction times out
- LLM sees error message
- Decides to use RAG search for specific information instead

**3. Explainability**
- LLM can explain why it's using a tool
- Natural language descriptions in responses
- Users understand agent's reasoning

**4. Extensibility**
- Adding new tools requires only schema definition
- LLM automatically learns tool capabilities
- No retraining or complex integration

**5. State-of-the-Art Performance**
- Leverages latest LLM capabilities (GPT-4o, Claude)
- Benefits from continuous LLM improvements
- Function calling is battle-tested by OpenAI/Anthropic

### Disadvantages & Mitigations

**1. LLM API Dependency**
- Risk: API downtime breaks agent
- Mitigation: Retry logic, fallback models, caching

**2. Non-Deterministic Behavior**
- Risk: Same input may yield different tool calls
- Mitigation: Temperature=0 for consistency, logging for debugging

**3. Latency**
- Risk: LLM calls add latency (200-500ms per call)
- Mitigation: Streaming responses, parallel tool execution

**4. Cost**
- Risk: LLM API calls cost money
- Mitigation: Per-user API keys (user pays), caching, prompt optimization

**5. Limited Reasoning**
- Risk: LLM may make suboptimal tool choices
- Mitigation: System prompt guidance, tool descriptions, feedback loop

### Rejected Alternatives

**Rule-Based Orchestrator**

Rejected because:
- Brittle: Requires explicit rules for every scenario
- Not extensible: Adding tools requires code changes
- Poor UX: Can't explain decisions naturally
- Limited: Can't handle novel tool combinations

**Separate Planning + Execution**

Rejected because:
- Over-engineered: Adds complexity without clear benefit
- Slower: Two LLM calls per workflow
- Less adaptive: Can't adjust plan based on intermediate results
- More expensive: Double LLM costs

## Consequences

### Positive

✅ **Rapid Development**: Added 5 tools in ~2 weeks without complex orchestration logic

✅ **Natural UX**: Users interact in natural language, agent explains its actions

✅ **Flexible Workflows**: Handles unexpected tool combinations (e.g., "search weather → generate image")

✅ **Easy Maintenance**: Tool schema changes don't require agent code changes

### Negative

⚠️ **API Dependency**: Requires stable LLM API access

⚠️ **Debugging Complexity**: Non-deterministic behavior harder to debug

⚠️ **Cost Sensitivity**: High usage scenarios need cost optimization

### Neutral

🔄 **Prompt Engineering**: System prompt quality critical for good tool selection

## Related Decisions

- [ADR-002: MCP for External Tools](./ADR-002-mcp-external-tools.md) - Integration pattern
- [ADR-003: Hidden State Management](./ADR-003-hidden-state-management.md) - Security pattern
- [ADR-004: Async-First Architecture](./ADR-004-async-first-architecture.md) - Performance pattern

## References

- [OpenAI Function Calling Guide](https://platform.openai.com/docs/guides/function-calling)
- [LangChain Agent Docs](https://python.langchain.com/docs/modules/agents/)
- [Anthropic Tool Use](https://docs.anthropic.com/claude/docs/tool-use)

## Revision History

| Date | Author | Changes |
|------|--------|---------|
| 2025-12-30 | Architecture Team | Initial decision |
