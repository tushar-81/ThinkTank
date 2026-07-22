from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.Graph import build_graph
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.checkpoint.sqlite import SqliteSaver
from backend.Agents.Common_State import State
from langgraph.types import Command, interrupt
import sqlite3

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

node_display_names = {
    'Orchestrator':     'Orchestrator',
    'Email_Content':    'Email Agent',
    'HITL_Email':       'Email Review',
    'Send_Email':       'Sending Email',
    'Schedule_Meeting': 'Meeting Scheduler',
    'Create_Meet':      'Creating Meeting',
    'HITL_Meet':        'Meeting Review',
    'PDF_Report':       'Analysing Discussion',
    'PDF_create':       'Generating Report',
    'Search':           'Searching Web',
    'Get_Members':      'Fetching Members',
    'Extract_Tasks':    'Extracting Tasks',
    'HITL_Trello':      'Board Review',
    'Trello':           'Creating Trello Board',
    'General':          'General Agent',
}

result = None
interrupt_found = False

class WebSocket_Manager:
    def __init__(self) -> None:
        self.active_websocket_clients=[]
        self.is_it_command= False

    async def Connect(self, websocket : WebSocket):
        await websocket.accept()
        self.active_websocket_clients.append(websocket)

    def disconnect(self, websocket : WebSocket):
        self.active_websocket_clients.remove(websocket)

    async def broadcast(self, message : dict):
        for conn in self.active_websocket_clients:
            await conn.send_json(message)


app=FastAPI()
manager=WebSocket_Manager()

app.mount("/static", StaticFiles(directory="static"), name="static")

config = {'configurable': {'thread_id': 'ThinkTank'}}
checkpointer12 = AsyncSqliteSaver.from_conn_string('checkpoints.db')

from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
graph=build_graph(checkpointer)

@app.get("/")
async def serve_frontend():
    return FileResponse("./frontend/thinktank.html")


@app.websocket('/ws')
async def Websocket_Chat(websocket : WebSocket):
    await manager.Connect(websocket=websocket)
    try:
        while True:
            #receiving message from websocket client
            data = await websocket.receive_json()
            if not manager.is_it_command:
                username= data.get('username', 'Anonymous')
                user_message = data.get('text')
            
            #displaying this message to all the other websocket clients
                await manager.broadcast(
                {
                    'role' : 'human',
                    'username' : username,
                    'text' : user_message
                })

                defined_state = {
                "messages": [HumanMessage(content=user_message)],
                'sender_address' : 'tusharbailwal81@gmail.com',
                'members_list' :  [{'username' : 'tushar22', 'member_role': 'AI Engineer'}, {'username' : 'tusharbailwal1', 'member_role': 'Backend Developer'},{'username' : 'tushar13', 'member_role': 'Marketing'},{'username' : 'tusharbailwal18', 'member_role': 'Manager'}],
                'board_name' :  'ThinkTank'}

                try:
                    result = None
                    interrupt_found = False

                    async for chunk in graph.astream(defined_state, config, stream_mode='updates'):
                        
                        print(f"[STREAM CHUNK] keys: {list(chunk.keys())}")
                        print(f"[STREAM CHUNK] full: {chunk}")
                        node_name = list(chunk.keys())[0]

                        if '__interrupt__' in chunk or any('__interrupt__' in str(v) for v in chunk.values()):
                            interrupt_data = chunk['__interrupt__'][0].value
                            type_agent = interrupt_data.get('type')

                            await manager.broadcast({
                                'type': 'node_update',
                                'node': node_display_names.get(node_name, node_name),
                            'status': 'waiting'})

                            manager.is_it_command = True
                            await manager.broadcast({
                                'type': 'interrupt',
                                'subtype': type_agent,
                                'data': interrupt_data
                            })
                            interrupt_found = True
                            break

                        display = node_display_names.get(node_name, node_name)
                        await manager.broadcast({
                            'type': 'node_update',
                            'node': display,
                            'status': 'done'
                        })
                        result = chunk[node_name]

                        if not interrupt_found and result:
                            messages = result.get('messages', [])
                            last_msg = messages[-1] if messages else None
                            if last_msg and isinstance(last_msg, AIMessage):
                                await manager.broadcast({'role': 'AI', 'text': last_msg.content})
                            await manager.broadcast({'type': 'node_clear'})

                except Exception as e:
                    await manager.broadcast({"type": "error", "message": str(e)})
                continue
            
            else:
                data_response=data.get('response')
                print(f"[Resume] data_response: {data_response}")
                result_after=graph.invoke(Command(resume=data_response), config)
                
                await manager.broadcast({"type": "close_interrupt"})

                if "__interrupt__" in result_after:
                    interrupt_data = result_after["__interrupt__"][0].value

                    await manager.broadcast({
                        "type": "interrupt",
                        "subtype": interrupt_data.get('type'),
                        "data": interrupt_data
                    })

                    manager.is_it_command = True
                    continue
                
                await manager.broadcast(
                        {   
                            'role' : 'AI',
                            'messages' : result_after.get('messages')[-1].content
                        }
                    )
                manager.is_it_command = False   
                continue
    except WebSocketDisconnect:
        manager.disconnect(websocket)