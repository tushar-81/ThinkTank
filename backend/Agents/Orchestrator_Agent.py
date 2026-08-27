from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, BaseMessage, AIMessage, ToolMessage, SystemMessage
from backend.Agents.Common_State import State
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import json
import os
load_dotenv()

OPENAI_API_KEY=os.getenv('OPENAI_API_KEY')

llm=ChatOpenAI(api_key=OPENAI_API_KEY, model='gpt-4o-mini')

class Orchestration_Outline(BaseModel):
        LLM_instruction : str = Field(description="Clear, detailed instruction for the selected agent including all extracted inputs required to perform the task")
        next: str = Field(description="Name of the next agent to be called")


async def Orchestrator_Agent(state : State):
        print('Orchestration agent called')
        message=state['messages'][-1].content
        instruction=f'''instruction = f"""
You are an orchestrator agent. Your job is to:
1. Identify the user's intent
2. Select the most appropriate agent
3. Generate a COMPLETE instruction for that agent

## Available agents

1. Email_agent — send/draft emails
2. Meet_scheduler_agent — schedule meetings/events
3. PDF_agent — generate summaries or PDFs
4. Search_agent — search external information
5. Task_assign_agent — break ideas into tasks
6. General_agent — handle general queries

## Your Output MUST include:
- next → the selected agent (exact name)
- LLM_instruction → a fully detailed instruction for that agent

## IMPORTANT RULES

- Extract ALL relevant details from the user message
- If something is missing, make reasonable assumptions (do NOT ask questions)
- Make the instruction directly executable by the next agent
- Be specific and structured

## What "good instruction" means

Each agent should receive:
- clear goal
- required inputs
- expected output format

---

## Agent-specific expectations

### Email_agent
Include:
- recipient
- subject (generate if missing)
- email body (clear and professional)

### Meet_scheduler_agent
Include:
- participants
- date & time
- duration (default 30 mins if missing)
- agenda (if possible)

### PDF_agent
Include:
- to create a insight report/PDF of the project being discussed
- format (brief/detailed)
- title if relevant

### Search_agent
Include:
- refined search query
- what kind of information is needed

### Task_assign_agent
Include:
- project/idea
- break into actionable tasks
- include priorities or sequence
- assign work to team members

### General_agent
Include:
- clear explanation request

---

## Output format (STRICT)

Return ONLY:

{{
  "next": "<agent_name>",
  "LLM_instruction": "<detailed instruction>"
}}

---

## Example

User: "Email John the project update and tell him we are delayed"

Output:
{{
  "next": "Email_agent",
  "LLM_instruction": "Write a professional email to John informing him that the project is delayed. Include an apology, current status, and expected revised timeline. Generate a suitable subject line."
}}

---

User message:
{message}
'''
        
        structure_llm=llm.with_structured_output(Orchestration_Outline)
        response=structure_llm.invoke([SystemMessage(content=instruction), HumanMessage(content=message)])
        print(response.LLM_instruction)
        print(response.next)
        return {
                'LLM_instruction' : response.LLM_instruction,
                'next' : response.next
        }