#standard
import asyncio
from dataclasses import dataclass
import html
import json
import traceback
import random
from datetime import datetime
import logging
from logging import debug, getLevelName, info, warning, error, critical, exception
import os
from pprint import pprint
import threading
import time
import uuid
from os.path import exists
import imageio

from requests.api import delete
#custom
#import dataset
#import hsluv
#from readerwriterlock import rwlock
from fastapi import FastAPI, WebSocket, Form, File, UploadFile, Response, Request, WebSocketDisconnect, websockets
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import starlette.status as status
from starlette.responses import RedirectResponse

import banana_dev as banana
import base64
from io import BytesIO
from PIL import Image
from configparser import ConfigParser


app = FastAPI()
app.mount('/www', StaticFiles(directory="./www"), name="www")
app.mount('/generatedImages', StaticFiles(directory="../generatedImages"), name="generatedImages")
#templates = Jinja2Templates(directory="templates")
@app.get('/', response_class=HTMLResponse)
async def getRoot(request: Request):
    return RedirectResponse('/www/index.html', status_code=status.HTTP_302_FOUND)

#########

@dataclass
class PlayerConnection:
    timeCreated: float
    id: str
    websocket: WebSocket
    playerName: str = None

playerConns: dict[str, PlayerConnection] = {}
gameStarted = False
round = 0
currTurnPlayerName: str = None
prompt = []
playerNames: list[str] = []
currImageFilename = ""
latestImageName = 'output1046.jpg'#None
generatingImage = False
lastSentGameState = ''
lastPlayer = 0
lastRound = 0
mostRecentPromptAdded = None
playerGoals: dict[str, str] = {}
gameID = uuid.uuid4().hex

presenterConns: list[WebSocket] = []

config = ConfigParser()
config.read('.env')
imageLog = []

##########

@dataclass
class PromptPiece:
    playerName: str
    word: str
    submittedTime: float
    submittedNum: int
    # TODO: player and time and order and stuff

def promptToString(prompt):
    """take the list of prompt info objects and assemble them into a string for display"""
    return ' '.join([p.word for p in prompt])

def promptToHTML(prompt):
    def wordToHTML(piece:PromptPiece):
        if piece.submittedNum == len(prompt) - 1:
            return f'<span class="mostrecentword">{piece.word}</span>'
        if len(prompt) - piece.submittedNum < 5:
            return f'<span class="recentword">{piece.word}</span>'
        else:
            return piece.word
    #def wrapWithSnipeLink(s: str):
    #    return f'<a href="#" @click="socket.send({{type:''snipeWord'',wordNum:{} }})">{s}</a>'
    return ' '.join([wordToHTML(p) for p in prompt])

async def broadcastGameStateToPlayers():
    global lastSentGameState
    # Set up message
    msg = {
        'type': 'gamestate',
        'currTurnPlayerName': currTurnPlayerName,
        'gameStarted': gameStarted,
        'playerNames': playerNames,
        'round': round,
        'promptString': promptToString(prompt),
        'latestImageName': latestImageName,
        'generatingImage': generatingImage,
        'promptHTML': promptToHTML(prompt),
        'playerGoals': playerGoals,
        'gameID': gameID,
        'recentWords': sorted([{'word':piece.word,'playerName':piece.playerName,'submittedNum':piece.submittedNum} for piece in prompt], key=lambda x: x['submittedNum'])
    }
    lastSentGameState = msg
    # Send it
    print(f'broadcasting to {len(playerConns.values())} players: {msg}')
    for currConn in [c.websocket for c in playerConns.values()] + presenterConns:
        try:
            await currConn.send_json(msg)
        except Exception as e:
            #traceback.print_exc()
            pass

async def broadcastGameStateToPresenters():
    pass

GOAL_WORDS_LIST = []
if exists('goalWords.txt'):
    with open('goalWords.txt', 'r', encoding='utf-8') as f:
        GOAL_WORDS_LIST = [s.strip() for s in json.load(f)]

async def addPlayer(name):
    """add new player to end of playerlist"""
    if not name in playerNames:
        playerNames.append(name)
        playerGoals[name] = random.choice(GOAL_WORDS_LIST)
        #playerGoals[name] = 'asdfasdfas dfasdf asdfasdfasdf asdfasdfasdfas dfasdfasdf'
        await broadcastGameStateToPlayers()

async def getNextPlayerName(currPlayerName):
    """return None if at end of list or current player not in list"""
    if not currPlayerName in playerNames:
        return None
    nextPlayerIndex = playerNames.index(currPlayerName)+1
    if nextPlayerIndex >= len(playerNames):
        return None
    else:
        return playerNames[nextPlayerIndex]

async def goToNextTurn():
    global currTurnPlayerName, round, lastPlayer, lastRound
    # increment turn. if at end of turn, reset and go to next round. 
    nextPlayer = await getNextPlayerName(currTurnPlayerName)
    lastRound = round
    lastPlayer = currTurnPlayerName
    if not nextPlayer:
        # New round!
        round += 1
        currTurnPlayerName = playerNames[0]
    else:
        currTurnPlayerName = nextPlayer

    await broadcastGameStateToPlayers()
    for currConn in [c.websocket for c in playerConns.values() if c.playerName == currTurnPlayerName]:
        try:
            await currConn.send_json({'type':'unlockEnterWord'})
        except Exception as e:
            pass


async def undoTurn():
    # go to last player. if resetting list, decrement round. remove last-added prompt from list. 
    global round, currTurnPlayerName
    round = lastRound
    currTurnPlayerName = lastPlayer
    prompt.remove(mostRecentPromptAdded)
    await broadcastGameStateToPlayers()
    asyncio.create_task(updatePictureFromPrompt(prompt))

async def onPlayerConnectionEnded(name):
    # No more connections with this player name? remove from player list    
    if not len([c for c in playerConns.values() if c.playerName == name]) > 1:
        if currTurnPlayerName == name:
            await goToNextTurn()
        playerNames.remove(name)
        # TODO: Broadcast change!
        await broadcastGameStateToPlayers()

# Load bad words list on startup
BAD_WORDS_LIST = []
if exists('badWords.txt'):
    with open('badWords.txt', 'r') as f:
        BAD_WORDS_LIST = [s.strip() for s in f.read().split(',')]

async def isWordAcceptable(word: str):
    """return 2-tuple: first value true/false, second value reason if false"""
    # Verify there are no spaces
    if len(word.strip().split(' ')) > 1:
        return False, "Too many words!"
    if (word.strip().lower() in BAD_WORDS_LIST):
        return False, f"You naughty {word}"
    return True, None

async def updatePictureFromPrompt(prompt):
    global latestImageName
    global generatingImage
    # Make banana request
    model_inputs = {
        "prompt": promptToString(prompt),
        "num_inference_steps":50,
        "guidance_scale":9,
        "height":512,
        "width":512,
        "seed":69420
    }
    model_inputs_to_save = {
        'model_inputs': model_inputs,
        'lastSentGameState': lastSentGameState
    }
    # Save banana request and prompt array as json
    imageID = uuid.uuid4().hex
    with open(f'../generatedImages/{imageID}.json', 'w') as f:
        json.dump(model_inputs_to_save, f)
    # Download results to a folder of static files
    generatingImage = True
    await broadcastGameStateToPlayers() # to send true flag
    out = banana.run(config['DEFAULT']['api_key'] , config['DEFAULT']['model_key'], model_inputs)
    image_byte_string = out["modelOutputs"][0]["image_base64"]
    image_encoded = image_byte_string.encode('utf-8')
    image_bytes = BytesIO(base64.b64decode(image_encoded))
    image = Image.open(image_bytes)
    imageLog.append(image)
    image.save(f"../generatedImages/{imageID}.jpg", quality=92)
    # Publish a status update with the filename
    latestImageName = f'{imageID}.jpg'
    generatingImage = False
    await broadcastGameStateToPlayers()

async def submitWord(playerName:str, word: str):
    global mostRecentPromptAdded
    mostRecentPromptAdded = PromptPiece(playerName, word, time.monotonic(), len(prompt))
    for currConn in [c.websocket for c in playerConns.values() if c.playerName == playerName]:
        try:
            await currConn.send_json({'type':'lockEnterWord'})
        except Exception as e:
            pass
    prompt.insert(random.randint(0, len(prompt)), mostRecentPromptAdded)
    await updatePictureFromPrompt(prompt)
    await goToNextTurn()

async def snipeWord(wordNum: int):
    global prompt
    prompt = [p for p in prompt if p.submittedNum != wordNum]
    asyncio.create_task(updatePictureFromPrompt(prompt))

async def gameLoopRunner():
    pass

async def kickPlayer(playerName:str):
    playerNames.remove(playerName)
    # Kick the player
    for currConn in [c.websocket for c in playerConns.values()]:
        try:
            await currConn.send_json({'type':'refreshKickedPlayer','playerName':playerName})
        except Exception as e:
            #traceback.print_exc()
            pass
    await broadcastGameStateToPlayers()

@app.on_event("startup")
async def setupSimulator():
    asyncio.create_task(gameLoopRunner())

@app.websocket('/playersocket')
async def runPlayerConnection(websocket: WebSocket):
    myID = uuid.uuid4().hex
    myStartedTime = time.monotonic()
    myConn = PlayerConnection(myStartedTime, myID, websocket)
    playerConns[myID] = myConn

    await websocket.accept()

    try:
        await broadcastGameStateToPlayers()
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=100)
                print("received message")
                print(msg)

                if msg['type'] == 'changeName':
                    myConn.playerName = msg['name']
                    # TODO: REMOVE PLAYER. handle actually changing names...
                    await addPlayer(msg['name'])
                if msg['type'] == 'submitWord':
                    asyncio.create_task(submitWord(myConn.playerName, msg['word']))
                if msg['type'] == 'testWord':
                    good, reason = await isWordAcceptable(msg['word'])
                    await websocket.send_json({
                        'type':'wordCheckResponse',
                        'wordValid': good,
                        'wordValidReason': reason,
                    })

                """if msg['type'] == 'dismissWrapDialog':
                    print('dismissing wrap dialog')
                    await websocket.send_json({'type':'stateUpdate', 'newState':{'wrapDialog':{'visible':False}}})
                if msg['type'] == 'move':
                    # perform move
                    movePlayer(msg['direction'])
                    await sendAnyUpdate(websocket)

                await sendAnyUpdate(websocket)"""
            except asyncio.exceptions.TimeoutError:
                pass # wholly uninteresting
    except websockets.WebSocketDisconnect as e:
        print('websocket disconnected')
    except Exception as e:
        traceback.print_exc()

    # Remove player if this was last connection for that player
    await onPlayerConnectionEnded(playerConns[myID].playerName)
    # Once player disconnects, remove connection
    playerConns.pop(myID)

@app.websocket('/presentersocket')
async def runPresenterConnection(websocket: WebSocket):
    global gameStarted, currTurnPlayerName, prompt, round, gameID
    presenterConns.append(websocket)

    await websocket.accept()

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_json(), timeout=1000)
                print("received message")
                print(msg)

                if msg['type'] == 'startGame':
                    gameStarted = True
                    # Shuffle player list
                    random.shuffle(playerNames)
                    # Set round and turn
                    round = 0
                    currTurnPlayerName = playerNames[0]
                    gameID = uuid.uuid4().hex
                    prompt = []
                    await broadcastGameStateToPlayers()
                if msg['type'] == 'endGame':
                    gameStarted = False
                    currTurnPlayerName = None
                    timeAsString = str(time.monotonic())
                    imageio.mimwrite('../generatedImageGifs/{timeAsString}.gif', imageLog, format= '.gif', fps = 1)
                    imageLog = []
                    await broadcastGameStateToPlayers()
                if msg['type'] == 'forceNextTurn':
                    await goToNextTurn()
                if msg['type'] == 'undoTurn':
                    await undoTurn()
                if msg['type'] == 'snipeWord':
                    asyncio.create_task(snipeWord(msg['wordNum']))
                if msg['type'] == 'kickPlayer':
                    await kickPlayer(msg['playerName'])

            except asyncio.exceptions.TimeoutError:
                pass # wholly uninteresting
    except websockets.WebSocketDisconnect as e:
        print('websocket disconnected')
    except Exception as e:
        traceback.print_exc()

    presenterConns.remove(websocket)

