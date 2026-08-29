from backend.Agents.Common_State import State

def Pass_AI(state: State):
    messages = state.get('messages', [])
    
    if not messages:
        return 'CHAT'
    
    last_message = messages[-1].content.lower()
    print(f"[Pass_AI] last message: '{last_message}'")
    print(f"[Pass_AI] @ai found: {'@ai' in last_message}")
    
    if '@ai' in last_message:
        return 'AI'
    
    return 'CHAT'

def orchestrator_function(state : State):
    next=state.get('next', '')
    return str(next)

