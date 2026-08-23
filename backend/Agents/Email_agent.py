from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from backend.Agents.Common_State import State
from langgraph.types import Command, interrupt
import os
load_dotenv()

class Email_Arguments(BaseModel):
    subject: str = Field(description='Concise email subject line summarizing the purpose of the email in a clear and professional tone.')
    body: str = Field(description='Well-structured email body containing the complete message, written clearly and professionally, suitable to be sent directly to the recipient.')

def Email_agent(state : State):
    print('Email Agent calleed')
    feedback=state.get('Email_Feedback', None)
    last_generated_body=state.get('body', '')

    LLM_instruction = state['LLM_instruction']
    user_message= state['messages'][-1].content
    llm=ChatOpenAI(model='gpt-4o-mini')
    structured_llm=llm.with_structured_output(Email_Arguments)

    instruction=f"""
You are an AI assistant responsible for drafting a professional email based on the given instruction and user input.

##Feedback for last generation
Feedback : {feedback} for Output : {last_generated_body}
if feedback empty ignore it

## Inputs

* Instruction: {LLM_instruction}
* User Message: {user_message}

## Task

Generate a clear, concise, and professional email draft.

## Requirements

1. **Keep it simple**

   * Do not include unnecessary sections
   * Only include information explicitly provided or logically required

2. **Tone and style**

   * Maintain a professional and polite tone
   * Be concise and to the point
   * Avoid overly formal or verbose language

3. **Content guidelines**

   * Clearly state the purpose of the email
   * Include relevant details from the user message
   * Ensure the message is complete and understandable
   * Do not assume missing details

4. **Subject line**

   * Generate a concise and relevant subject line

5. **Optional placeholders (only if needed)**

   * If the context requires personalization, leave clean placeholders such as:

     * [Salutation]
     * [Recipient Name]
     * [Closing]
     * [Signature]
   * Do not force placeholders if they are not necessary

6. **Avoid**

   * Guessing names, roles, or organizations unless explicitly given
   * Redundant or repetitive content

## Goal

Produce a clean, professional email draft that can be easily finalized by a human with minimal edits if needed.
"""
    response=structured_llm.invoke([HumanMessage(content=instruction)])
    app_password=os.getenv('GOOGLE_MAIL')
    print(response)
    return {
        'subject' : response.subject,
        'body' : response.body
    }


def review_node(state: State):
    print('HITL Called')
    user_input = interrupt({
    "type": "Email_agent",
    "fields": [
        {"name": "status", "type": "select", "options": ["approved", "rejected"]},
        {"name": "subject", "type": "text"},
        {"name": "body", "type": "textarea"},
        {"name": "to", "type": "text"},
        {"name": "cc", "type": "text"},
        {"name": "bcc", "type": "text"}
    ],
    "initial_values": {
        "subject": state["subject"],
        "body": state["body"]
    }})
    print('HITL_Trello resumed')
    updated_subject = user_input.get("subject", state["subject"])
    updated_body = user_input.get("body", state["body"])
    status = user_input.get("status")
    sender_adress=user_input.get('sender')
    to_email = user_input.get('to')
    cc=user_input.get('cc', None)
    bcc=user_input.get('bcc', None)
    print(user_input)

    if status == "approved":
        return Command(
            goto="Send_Email",
            update={
                "subject": updated_subject,
                "body": updated_body,
                "status": "approved",
                "to_email" : to_email,
                "cc_email" : cc,
                "bcc_email" : bcc,
                "sender_address" : sender_adress
            }
        )
    else:
        return Command(
            goto="Email_Content",
            update={
                "subject": updated_subject,
                "body": updated_body
            }
        )
    
def send_email(state : State):
    print("🔥 SEND_EMAIL NODE CALLED")
    sender= state["sender_address"]
    app_password = os.getenv('GOOGLE_MAIL')

    to_email=state['to_email']
    cc_email=state['cc_email']
    bcc_email = state['bcc_email']
    
    msg=MIMEMultipart()
    msg["From"] = sender
    msg["To"] = ", ".join(to_email)

    if cc_email:
        msg["Cc"] = ", ".join(cc_email)
    if bcc_email:
        msg["Bcc"] = ", ".join(bcc_email)

    msg["Subject"] = state['subject']
    
    body=state['body']
    msg.attach(MIMEText(body, 'plain'))
    all_recipients = to_email + cc_email + bcc_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, app_password)
            server.sendmail(sender, all_recipients, msg.as_string())
        print("✅ EMAIL SENT")
        return {'email_status': 'sent successfully', 'messages': [AIMessage(content='email sent successfully')]}
        

    except smtplib.SMTPException as e:
        print("❌ EMAIL FAILED:", str(e))
        return {'email_status': f'failed: {str(e)}'}