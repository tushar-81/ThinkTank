from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.graph import START, END
from datetime import datetime, timedelta
from langgraph.types import Command, interrupt
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from backend.Agents.Common_State import State
from dotenv import load_dotenv
import pytz
import uuid
import os

load_dotenv()

OPENAI_API_KEY=os.getenv('OPENAI_API_KEY')

SCOPES = ["https://www.googleapis.com/auth/calendar"]

class Meeting_detail(BaseModel):
    summary : str = Field(description='Title of the meeting')
    duration_min : int = Field(description='Duration of the meeting in minutes')
    start_date_time : str = Field(description='Meeting date and time in ISO format')
    end_date_time : str = Field(description='When the meeting will end will be end_date_time, also give this is ISO format')

def Scheduler_Agent(state : State):
    Last_output=state.get('Last_Scheduler_Agent_output')
    LLM_instruction = state.get('LLM_instruction')
    feedback=state.get('Meet_feedback', '')
    # Fetching meeting details from user's last interaction
    user_input=state['messages'][-1].content
    tz = pytz.timezone("Asia/Kolkata")
    today=datetime.now(tz)
    prompt = f"""
Extract meeting details from the text.

User feedback on if there were any last attempt to extract meeting details : 
Feedback : {feedback}  for output : {Last_output}

today's date for reference : 
{today}

Return ONLY valid JSON in this format:
{{
  "summary": "...",
  "duration_min": ...,
  "start_date_time": "...",
  "end_date_time": "..."
}}

Rules:
- If time is relative (e.g., "today 5pm"), convert to ISO format
- End date time -- ('today 5pm, 1 hour duration, so end time will be 6pm)
- If duration not given, default to 30
- Be precise

LLM_Instruction : 
{LLM_instruction}
Text:
{user_input}
"""

    llm=ChatOpenAI(api_key=OPENAI_API_KEY, model='gpt-4o-mini')

    llm_structured=llm.with_structured_output(Meeting_detail)
    response=llm_structured.invoke([HumanMessage(content=prompt)])
    meet_dict={
        'summary': response.summary,
        'duration_min' : response.duration_min,
        'start_date_time' : response.start_date_time,
        'end_date_time' : response.end_date_time
    }

    return {
        'Meet_dict' : meet_dict
    }


def get_calendar_service():
    creds = None

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as f:
            f.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds)

def create_meeting(state : State):

    meet_dict=state["Meet_dict"]
    summary=meet_dict.get('summary', '')
    duration_min = meet_dict.get('duration_min')
    start_date_time=meet_dict.get('start_date_time')
    end_date_time=meet_dict.get('end_date_time')

    service = get_calendar_service()

    event = {
        "summary": summary,
        "start": {
            "dateTime": start_date_time,
            "timeZone": "Asia/Kolkata"
        },
        "end": {
            "dateTime": end_date_time,
            "timeZone": "Asia/Kolkata"
        },
        "conferenceData": {
            "createRequest": {
                "requestId": str(uuid.uuid4()),
                "conferenceSolutionKey": {"type": "hangoutsMeet"}
            }}}

    event = service.events().insert(
        calendarId="primary",
        body=event,
        conferenceDataVersion=1
    ).execute()

    return {
        'Meet_link' : event["hangoutLink"],
        'messages' : [AIMessage(content=f'meeting link {event["hangoutLink"]}')]    }

def review_meeting(state: State):
    response= interrupt({
        "type": "Meet_scheduler_agent",
        "fields": [
            {"name": "decision", "type": "select", "options": ["approve", "reject"]},
            {"name": "feedback", "type": "text"}
        ],
        "initial_values": {
            "Meeting_Details": state["Meet_dict"],
            "Meet_Link": state["Meet_link"]
        }
    })
    print('HITL_scheduler resumed')
    print(response)
    if isinstance(response, dict):
        decision= response.get('decision')
        feedback= response.get('feedback')

    else:
        decision = response
        feedback=None

    if decision == 'approve':
        return Command(goto=END, update={'Meet_feedback' : None})
    
    else:
        return Command(
            goto='Schedule_Meeting',
            update={'Meet_feedback' : feedback}
        )
    