from backend.Agents.Common_State import State
from pydantic import BaseModel,Field
from langgraph.types import Command, interrupt  
from typing import List
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
import requests
from datetime import date
import logging
import time

import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('TRELLO_API')
TOKEN = os.getenv('TRELLO_TOKEN')
today = date.today()

class checklist_item(BaseModel):
    name: str = Field(
        description="A short, actionable subtask (should be specific and executable)")

class checklist(BaseModel):
    name: str = Field(
        description="Title of the checklist grouping related subtasks")
    items: List[checklist_item] = Field(
        description="List of subtasks under this checklist")

class card(BaseModel):
    name: str = Field(
        description="Title of the task")
    assignee: str = Field(
        description="Trello member ID assigned to this task")
    description: str = Field(
        description="Detailed explanation of what needs to be done")
    checklists: List[checklist] = Field(
        description="Breakdown of the task into smaller steps")
    due_date: str = Field(
        description="Deadline in ISO format (YYYY-MM-DDTHH:MM:SSZ), or empty string if none")

class Card_List(BaseModel):
    name: str = Field(
        description="Stage or phase of the project (e.g., To Do, Backend, Testing)")
    cards: List[card] = Field(
        description="Tasks belonging to this phase")

class Boards(BaseModel):
    Board_name: str = Field(
        description="Name of the overall project board")
    lists: List[Card_List] = Field(
        description="All workflow stages and their tasks")
    
def get_boards():
    url = "https://api.trello.com/1/members/me/boards"
    
    params = {
        "key": API_KEY,
        "token": TOKEN
    }

    return requests.get(url, params=params).json()

def get_board_id_by_name(name):
    boards = get_boards()
    
    for board in boards:
        if board["name"] == name:
            return board["id"]
    
    return None


def get_board_members(board_id):
    url = f"https://api.trello.com/1/boards/{board_id}/members"
    
    params = {
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.get(url, params=params)
    return response.json()

def Board_members_list(state: State):
    start = time.time()

    board_name = state['board_name']
    board_id = get_board_id_by_name(name=board_name)

    if not board_id:
        raise Exception("Board not found")

    member_details = get_board_members(board_id)
    members = state['members_list']

    trello_lookup = {}

    for m in member_details:
        full_name = m.get("username", "").lower()
        first_name = full_name.split(" ")[0]

        trello_lookup[first_name] = m.get("id")

    updated_members = []
    for member in members:
        updated = {**member} 
        name = updated.get('username', '').lower().split(" ")[0]
        updated['member_trello_id'] = trello_lookup.get(name, "")
        updated_members.append(updated)

    end = time.time()
    print(f'Assign members {end-start}')
    return {
        'board_id' : board_id,
        'members_list': updated_members
    }


def Extract_tasks(state : State):
    print(f'Trello Agent called')
    start=time.time()
    board_name=state['board_name']

    messages = state['messages']
    conversation_history = ''
    
    messages = state['messages']
    for message in messages:
        if isinstance(message, HumanMessage):
            content=str(message.content).lower().split(' ')
            if '@AI' or '@ai' or '@Ai' in content:
                continue
            conversation_history+= f"Role : Human, Content : {message.content}\n"
        if isinstance(message, AIMessage):
            conversation_history+= f"Role : Assistant, Content : {message.content}\n"
    
    members=state['members_list']
    members_info=''

    for member in members:
        members_info+=f""" Username : {member.get('username')}, 
                           Role : {member.get('member_role')},
                           Member Trello_id : {member.get('member_trello_id')} \n"""

    system_instruction = """
You are a project planning assistant.

Your task is to analyze a conversation and convert it into a structured Trello board plan.

You must:
1. Extract the project goal
2. Break it into logical phases (lists)
3. Break phases into tasks (cards)
4. Break tasks into subtasks (checklists)
5. Assign each task to the most suitable team member using their role
6. Add a short, clear description for each task
7. Add due dates only if explicitly mentioned or strongly implied

---

You are given:

1. Conversation history (brainstorming discussion)
2. Board Name
3. Information of the Team Members

---

Assignment rules:
- Match task requirements with member roles
- Assign ONLY the Trello member_id 

---

Checklist rules:
- Break each task into small, actionable steps
- Each checklist item should be atomic (can be done in 1–2 hours)

---

Due Date Rules:
- You MUST assign a due_date for every task
- Use the provided today's date as reference
- Estimate duration based on task complexity:
  • Small tasks → 1–2 days
  • Medium tasks → 3–5 days
  • Large tasks → 5–10 days
- Ensure due_date is AFTER today's date
- Use strict Trello format: YYYY-MM-DDTHH:MM:SSZ
- Always set time to 18:00:00Z
- Do NOT leave due_date empty
- Do NOT use relative terms (e.g., tomorrow, next week)

---

Output rules:
- Output ONLY valid JSON
- Follow the schema exactly
- Do NOT include explanations
- Do NOT include extra fields
- Do NOT generate IDs (except member_id which is provided)
- Keep names concise and meaningful

---

Schema to follow:

{
  "Board_name": str,
  "lists": [
    {
      "name": str,
      "cards": [
        {
          "name": str,
          "assignee": str = '',
          "description": str,
          "due_date": str = '',
          "checklists": [
            {
              "name": str,
              "items": [
                {"name": str}
              ]
            }
          ]
        }
      ]
    }
  ]
}

"""
    human_instruction=f"""
Board Name : {board_name}

Brainstorming discussion : {conversation_history}

Team Information : {members_info}

Today's date for reference : {today}
    
If there was a previous generation of the Trello board plan and the user has rejected the result:
Feedback : {state.get('Board_feedback', '')} For Output : {state.get('board_outline', '')}
"""

    llm = ChatOpenAI(model='gpt-4o-mini')
    llm=llm.with_structured_output(Boards)
    response=llm.invoke([SystemMessage(content=system_instruction), HumanMessage(content=human_instruction)])
    end=time.time()
    print(f'Extract tasks {end-start}')
    return {
        'board_outline' : response.model_dump()
    }

def human_review(state : State):
    response=interrupt({
        "type": "Assign_task",
        "fields": [
            {"name": "status", "type": "select", "options": ["approved", "rejected"]},
            {"name": "Board_Outline", "type": "textarea"},
            {"name": "feedback", "type": "text"}
        ],
        "initial_values": {
            "Board_Outline": state["board_outline"]
        }
    })
    print('HITL_Trello resumed')
    changes = response.get('Board_Outline', '') # if only minor changes
    approval = response.get('status', '') # if start agent again
    feedback = response.get('feedback', '')
    print(response)
    if approval=='approved':
        return Command(
            goto='Trello',
            update={
                'board_outline' : changes if changes else state['board_outline']
            }
        )
    
    if approval=='rejected':
        return Command(
            goto='Extract_Tasks',
            update={
                'Board_feedback' : feedback
            }
        )


def create_list(board_id, list_name):
    url = "https://api.trello.com/1/lists"
    
    params = {
        "name": list_name,
        "idBoard": board_id,
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.post(url, params=params)
    return response.json()

def create_card(list_id, title, description):
    url = "https://api.trello.com/1/cards"
    
    params = {
        "idList": list_id,
        "name": title,
        "desc": description,  
        "key": API_KEY,
        "token": TOKEN
    }

    return requests.post(url, params=params).json()


BASE_URL = "https://api.trello.com/1"

def create_checklist(card_id, checklist_name):
    url = f"{BASE_URL}/checklists"
    
    params = {
        "idCard": card_id,
        "name": checklist_name,
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.post(url, params=params)
    return response.json()

def add_checklist_item(checklist_id, item_name):
    url = f"{BASE_URL}/checklists/{checklist_id}/checkItems"
    
    params = {
        "name": item_name,
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.post(url, params=params)
    return response.json()

def assign_member(card_id, member_id):
    url = f"https://api.trello.com/1/cards/{card_id}/idMembers"
    
    params = {
        "value": member_id,
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.post(url, params=params)
    return response.json()

def set_due_date(card_id, due_date):
    url = f"https://api.trello.com/1/cards/{card_id}"
    
    params = {
        "due": due_date,
        "key": API_KEY,
        "token": TOKEN
    }

    response = requests.put(url, params=params)
    return response.json()


def Trello_agent(state:State):

    print(f'Trello Agent started')
    board_outline=state['board_outline']

    board_name=state['board_name']

    Trello_board_id=state['board_id']

    Lists=board_outline.get('lists')
    


    for lst in Lists:
        lst_name=lst.get('name')

        Trello_lst=create_list(board_id=Trello_board_id, list_name=lst_name)

        Trello_list_id=Trello_lst.get('id')

        cards=lst.get('cards')

        for card in cards:
            card_name=card.get('name')
            card_desc=card.get('description')
            card_assignee_id=card.get('assignee', None)
            card_due_date=card.get('due_date', None)


            Trello_card=create_card(Trello_list_id, card_name, card_desc)

            Trello_card_id=Trello_card.get('id')
            print(f'{board_outline}\n {lst} \n{card}')
            
            if card_due_date:
                set_due_date(Trello_card_id, card_due_date)

            if card_assignee_id:
                assign_member(Trello_card_id, card_assignee_id)

            checklists=card.get('checklists')

            for Checklist in checklists:
                checklist_name=Checklist.get('name')

                Trello_checklist=create_checklist(Trello_card_id, checklist_name)

                Trello_checklist_id=Trello_checklist.get('id')

                Checklist_items=Checklist.get('items')

                for item in Checklist_items:
                    item_name=item.get('name')

                    Trello_item = add_checklist_item(Trello_checklist_id, item_name)
                    
    

    return {
        'board_id' : Trello_board_id,
        'messages': [AIMessage(content=f"Trello board '{board_name}' created successfully.")]
    }
