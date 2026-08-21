from backend.Agents.Common_State import State
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
load_dotenv()


def general_agent(state : State):
    messages=state['messages']
    conversation_info=""

    for message in messages:
        if isinstance(message, HumanMessage):
            conversation_info+=f"Role : Human, Content : {message.content}"
        if isinstance(message, SystemMessage):
            conversation_info+=f"Role : System, Content : {message.content}"
        if isinstance(message, AIMessage):
            conversation_info+=f"Role : Assistant, Content : {message.content}"
        if isinstance(message, ToolMessage):
            conversation_info+=f"Role : Tool, Content : {message.content}"

    LLM_instruction = state['LLM_instruction']

    llm=ChatOpenAI(model='gpt-4o-mini')
    
    system=f"""
    Conversation : {conversation_info}
    Instruction : {LLM_instruction}
    """

    user_message = messages[-1].content

    response=llm.invoke([SystemMessage(content=system), HumanMessage(content=user_message)])

    return {
        'messages' : response
    }